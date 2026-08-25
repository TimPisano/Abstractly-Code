"""
Live API regression suite for the new sidebar-support backend work:
GET /discrepancies/summary, GET /comments/recent, GET /portfolio/trends
(the portfolio-wide sibling of /portfolio/property-trends), and the
real caching + invalidation behavior on /portfolio/health-score and
/portfolio/trends -- follows the exact convention established by
test_live_discrepancies_api.py: runs against the actually-running dev
server over real HTTP, specifically to catch "the route/logic is right
in the source file, but the currently-running server process is
stale" (a real bug class this project has hit before -- see
DECISIONS.md).
"""
import os
import sys
import json
import time
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


def _multipart_body(fields, files):
    boundary = "----SidebarEndpointsApiTestBoundary"
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for field_name, filename, content, content_type in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def clear_all_leases():
    status, leases = _request("GET", "/leases")
    assert status == 200, f"could not list leases to clear: {status} {leases}"
    for lease in leases:
        _request("DELETE", f"/leases/{lease['id']}")


def _read_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


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

        # ---- New endpoints exist and return the right shape ----
        print("\n--- New endpoints ----")
        status, summary = _request("GET", "/discrepancies/summary")
        check("GET /discrepancies/summary returns 200", status == 200, str(summary))
        check("summary has the expected shape", set(summary.keys()) >= {"total", "by_status", "by_severity", "by_type"}, str(summary))

        status, recent = _request("GET", "/comments/recent")
        check("GET /comments/recent returns 200", status == 200 and isinstance(recent, list), str(recent))

        status, portfolio_trends = _request("GET", "/portfolio/trends")
        check("GET /portfolio/trends returns 200", status == 200, str(portfolio_trends))
        check("portfolio trends has the expected shape", set(portfolio_trends.keys()) >= {"property_count", "properties", "portfolio_tenant_turnover", "portfolio_rollover_pattern"}, str(portfolio_trends))

        # ---- Real caching behavior: health-score ----
        print("\n--- Real caching: health-score ----")
        body, ct = _multipart_body({}, [("file", "sample_lease_commercial.pdf", _read_fixture("sample_lease_commercial.pdf"), "application/pdf")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        check("real lease upload succeeds", status == 201, str(result))
        lease_id = result["leases"][0]["id"]
        created_lease_ids.append(lease_id)

        status, score_after_upload = _request("GET", "/portfolio/health-score")
        check("health-score reflects the just-uploaded lease immediately (cache correctly busted by the upload)", score_after_upload.get("lease_count", 0) >= 1, str(score_after_upload))

        # Second call within the TTL must be identical (served from cache) -- can't observe cache HIT directly over HTTP, but computed_at staying frozen across two rapid calls is exactly what a cache produces
        status, score_call_2 = _request("GET", "/portfolio/health-score")
        check("two rapid health-score calls return the identical computed_at (served from cache, not recomputed)", score_after_upload.get("computed_at") == score_call_2.get("computed_at"), str((score_after_upload.get("computed_at"), score_call_2.get("computed_at"))))

        # ---- Real caching behavior: portfolio trends ----
        print("\n--- Real caching: portfolio trends ----")
        status, trends_before_delete = _request("GET", "/portfolio/trends")
        property_count_before = trends_before_delete["property_count"]

        status, _ = _request("DELETE", f"/leases/{lease_id}")
        check("real delete succeeds", status == 200, str(status))
        created_lease_ids.remove(lease_id)

        status, trends_after_delete = _request("GET", "/portfolio/trends")
        check("portfolio trends reflects the deletion immediately (cache correctly busted by the delete)", trends_after_delete["property_count"] < property_count_before or property_count_before == 0, str((property_count_before, trends_after_delete["property_count"])))

        # ---- Real caching behavior: discrepancy resolve busts health-score ----
        print("\n--- Real caching: resolving a discrepancy busts the health-score cache ----")
        body, ct = _multipart_body({}, [("file", "missing_clauses_office.pdf", _read_fixture("missing_clauses_office.pdf"), "application/pdf")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        messy_lease_id = result["leases"][0]["id"]
        created_lease_ids.append(messy_lease_id)

        status, flags = _request("GET", f"/leases/{messy_lease_id}/risks")
        check("real risk flags exist", status == 200 and len(flags) > 0, str(flags))
        disc_id = flags[0]["discrepancy_id"]

        status, score_before_resolve = _request("GET", "/portfolio/health-score")
        open_before = score_before_resolve["components"]["unresolved_discrepancies"]["open_count"]

        status, _ = _request("POST", f"/discrepancies/{disc_id}/resolve", json_body={
            "correct_source": "lease_document", "note": "Reviewed and accepted.", "resolved_by": "Jane Analyst",
        })
        check("real resolve succeeds", status == 200, str(status))

        status, score_after_resolve = _request("GET", "/portfolio/health-score")
        open_after = score_after_resolve["components"]["unresolved_discrepancies"]["open_count"]
        check("health-score open_count drops immediately after resolving (cache correctly busted)", open_after < open_before, str((open_before, open_after)))

        # ---- Real comments feed reflects real comments ----
        print("\n--- Real comments feed ----")
        status, _ = _request("POST", f"/leases/{messy_lease_id}/comments", json_body={"author_name": "Jane", "body": "A real team note."})
        check("real comment post succeeds", status == 201, str(status))
        status, recent_after = _request("GET", "/comments/recent")
        check("the real comment appears in the recent feed", any(c["body"] == "A real team note." for c in recent_after), str(recent_after[:3]))

        # ---- Discrepancy summary reflects real state ----
        status, summary_final = _request("GET", "/discrepancies/summary")
        check("discrepancy summary total matches the real full list", summary_final["total"] == len(_request("GET", "/discrepancies")[1]), str(summary_final))

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
