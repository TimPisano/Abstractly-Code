"""
Live API regression suite for the Phase 1 daily-use dashboard endpoints:
GET /portfolio/attention, GET /portfolio/health, GET /activity, and the
activity-logging side effects of upload/delete/compare/export.

Requires the backend already running at API_BASE_URL. Wipes leases at
the start (same convention as test_live_portfolio_api.py) so assertions
can be exact. Does NOT wipe activity_log (there's no endpoint to do
that, and the log is meant to be an append-only history) — assertions
about activity therefore check "a new matching entry appeared", not
"the feed contains exactly N entries".
"""
import os
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

API_BASE_URL = "http://localhost:5000"
FIXTURES_DIR = os.path.dirname(__file__)


def _request(method, path, data=None, json_body=None, headers=None):
    url = f"{API_BASE_URL}{path}"
    body = None
    req_headers = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body).encode()
        req_headers["Content-Type"] = "application/json"
    elif data is not None:
        body = data

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "application/json" in content_type:
                return resp.status, json.loads(raw.decode())
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return e.code, raw


def _multipart_body(files):
    boundary = "----DashboardApiTestBoundary"
    parts = []
    for field_name, filename, content in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def clear_all_leases():
    status, leases = _request("GET", "/leases")
    assert status == 200, f"could not list leases to clear: {status} {leases}"
    for lease in leases:
        _request("DELETE", f"/leases/{lease['id']}")


def _upload_fixture(filename):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "rb") as f:
        content = f.read()
    body, content_type = _multipart_body([("file", filename, content)])
    status, lease = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
    assert status == 201, f"upload of {filename} failed: {status} {lease}"
    return lease["id"]


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    status, health_check = _request("GET", "/health")
    check("server is reachable", status == 200 and health_check.get("status") == "healthy")

    created_lease_ids = []
    try:
        clear_all_leases()

        # ---- Empty-portfolio shape (no leases yet) ----
        status, attention = _request("GET", "/portfolio/attention")
        check("attention endpoint returns 200 on empty portfolio", status == 200, str(status))
        check(
            "attention has the three expected keys",
            isinstance(attention, dict) and set(attention.keys()) == {"expiring_soon", "missing_data", "unusual_terms"},
            str(attention.keys()) if isinstance(attention, dict) else str(attention),
        )
        check("attention lists are empty for an empty portfolio", attention == {"expiring_soon": [], "missing_data": [], "unusual_terms": []})

        status, portfolio_health = _request("GET", "/portfolio/health")
        check("health endpoint returns 200 on empty portfolio", status == 200, str(status))
        check("health total_leases is 0 for an empty portfolio", portfolio_health.get("total_leases") == 0)
        check("health fully_verified_pct is None for an empty portfolio", portfolio_health.get("fully_verified_pct") is None)

        # ---- Upload real fixtures and confirm attention/health react ----
        lease1_id = _upload_fixture("sample_lease.pdf")
        lease2_id = _upload_fixture("office_lease.pdf")
        created_lease_ids.extend([lease1_id, lease2_id])

        status, attention = _request("GET", "/portfolio/attention")
        check("attention endpoint 200 with real leases", status == 200, str(status))
        all_ids_seen = set()
        for bucket in ("expiring_soon", "missing_data", "unusual_terms"):
            for entry in attention[bucket]:
                all_ids_seen.add(entry["lease_id"])
        check(
            "at least one uploaded lease shows up somewhere in attention",
            bool(all_ids_seen & {lease1_id, lease2_id}),
            f"attention lease ids seen: {all_ids_seen}",
        )

        status, portfolio_health = _request("GET", "/portfolio/health")
        check("health total_leases matches uploaded count", portfolio_health.get("total_leases") == 2, str(portfolio_health))
        check(
            "health needs_review_count + fully_verified_count == total",
            portfolio_health.get("needs_review_count", -1) + portfolio_health.get("fully_verified_count", -1) == 2,
            str(portfolio_health),
        )

        # ---- Activity log reacts to real actions ----
        # Uses the freshest entries (small `limit`) and checks their
        # action_type/order directly, rather than comparing total counts
        # against a capped fetch — this dev DB accumulates activity
        # across every test/manual run, so "did the count grow" against
        # a `limit=N` snapshot stops being meaningful once the table has
        # more than N rows in it. Checking "are the N most recent entries
        # exactly what we expect" stays correct at any table size.
        status, before = _request("GET", "/activity?limit=10")
        check("activity endpoint returns 200", status == 200, str(status))

        # The single upload above should already be the most recent
        # "lease_uploaded" entries (uploads happened just before this).
        upload_entries = [a for a in before if a.get("action_type") == "lease_uploaded"]
        check("upload actions were logged", len(upload_entries) >= 2, f"found {len(upload_entries)}")
        check(
            "an upload activity entry references a real lease_id",
            any(a.get("lease_id") in (lease1_id, lease2_id) for a in upload_entries),
        )

        status, _ = _request("GET", "/leases/compare?ids=%d,%d" % (lease1_id, lease2_id))
        check("comparison request succeeded", status == 200, str(status))

        status, _ = _request("GET", "/portfolio/rent-roll.csv")
        check("rent roll CSV export succeeded", status == 200, str(status))

        # The export ran last, then the comparison just before it — so
        # the 2 most recent entries must be exactly these two, in order.
        status, latest_two = _request("GET", "/activity?limit=2")
        check(
            "the 2 most recent activity entries are the export then the comparison",
            status == 200 and isinstance(latest_two, list) and len(latest_two) == 2
            and latest_two[0]["action_type"] == "rent_roll_exported"
            and latest_two[1]["action_type"] == "comparison_run",
            str(latest_two),
        )

        status, after = _request("GET", "/activity?limit=10")
        check(
            "activity feed is sorted most-recent-first",
            status == 200 and all(after[i]["created_at"] >= after[i + 1]["created_at"] for i in range(len(after) - 1)),
            str(after),
        )

        status, limited = _request("GET", "/activity?limit=1")
        check("limit query param is honored", status == 200 and isinstance(limited, list) and len(limited) == 1, str(limited))

        # ---- Deleting a lease logs its own activity and doesn't break the feed ----
        status, _ = _request("DELETE", f"/leases/{lease1_id}")
        check("lease delete succeeded", status == 200, str(status))
        created_lease_ids.remove(lease1_id)

        status, after_delete = _request("GET", "/activity?limit=50")
        check(
            "lease_deleted activity was logged",
            status == 200 and any(a.get("action_type") == "lease_deleted" for a in after_delete),
        )

    finally:
        print("\nCleaning up test data...")
        for lease_id in created_lease_ids:
            _request("DELETE", f"/leases/{lease_id}")
        status, remaining = _request("GET", "/leases")
        check("cleanup leaves DB empty", status == 200 and remaining == [], f"{len(remaining) if isinstance(remaining, list) else remaining} leases remain")

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    print("=" * 70)

    failed = [c for c in checks if not c[1]]
    if failed:
        print("\nFAILED:")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")

    return len(failed) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
