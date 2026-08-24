"""
Live API regression suite for the discrepancy resolution system
(GET/POST /discrepancies*) -- follows the exact convention established
by test_live_audit_trail_api.py / test_live_t12_api.py: runs against
the actually-running dev server over real HTTP, specifically to catch
"the route/logic is right in the source file, but the currently-running
server process is stale" (a real bug class this project has hit
before -- see DECISIONS.md).

Uses a real PDF upload that's known to raise real missing_clause risk
flags (missing_clauses_office.pdf), resolves one through the real
route, and confirms the resolution persists across a fresh GET (the
actual point of this feature: resolving something once means it stops
needing a manual re-read).
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


def _multipart_body(fields, files):
    boundary = "----DiscrepanciesApiTestBoundary"
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

        # ---- Real upload that produces real missing_clause flags ----
        print("\n--- Real PDF upload with real risk flags ----")
        body, content_type = _multipart_body(
            {}, [("file", "missing_clauses_office.pdf", _read_fixture("missing_clauses_office.pdf"), "application/pdf")]
        )
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
        check("lease upload succeeds", status == 201, str(result))
        lease_id = result["leases"][0]["id"]
        created_lease_ids.append(lease_id)

        status, flags = _request("GET", f"/leases/{lease_id}/risks")
        check("risks route returns 200", status == 200, str(flags))
        check("real fixture raises at least one flag", len(flags) > 0, str(flags))
        check("every flag carries a discrepancy_id + resolution_status", all("discrepancy_id" in f and f["resolution_status"] == "open" for f in flags), str(flags))
        disc_id = flags[0]["discrepancy_id"]

        # ---- List/detail routes ----
        print("\n--- List/detail routes ----")
        status, disc_list = _request("GET", "/discrepancies")
        check("GET /discrepancies returns 200", status == 200, str(status))
        check("the flag we just saw is in the list", any(d["id"] == disc_id for d in disc_list), str(disc_id))

        status, disc_detail = _request("GET", f"/discrepancies/{disc_id}")
        check("GET /discrepancies/<id> returns 200", status == 200 and disc_detail["id"] == disc_id, str(disc_detail))
        check("detail includes an empty resolutions history before any action", disc_detail["resolutions"] == [], str(disc_detail["resolutions"]))

        status, err = _request("GET", "/discrepancies/999999")
        check("nonexistent discrepancy returns 404", status == 404, str(status))

        # ---- Resolve, and confirm it persists across a fresh read ----
        print("\n--- Resolve ----")
        status, err = _request("POST", f"/discrepancies/{disc_id}/resolve", json_body={"note": "only a note, missing required fields"})
        check("resolve with missing fields returns 400", status == 400, str(err))

        status, resolved = _request("POST", f"/discrepancies/{disc_id}/resolve", json_body={
            "correct_source": "lease_document",
            "note": "Confirmed via source PDF -- clause genuinely absent, acceptable for this deal.",
            "resolved_by": "Jane Analyst",
            "resolved_by_email": "jane@example.com",
        })
        check("resolve returns 200", status == 200, str(resolved))
        check("status flips to resolved", resolved.get("status") == "resolved", str(resolved))
        check("resolution is permanently logged with who/when/why", len(resolved.get("resolutions", [])) == 1, str(resolved))
        check("resolved_by recorded correctly", resolved["resolutions"][0]["resolved_by"] == "Jane Analyst", str(resolved["resolutions"][0]))

        status, flags_again = _request("GET", f"/leases/{lease_id}/risks")
        matching = next((f for f in flags_again if f["discrepancy_id"] == disc_id), None)
        check("re-fetching risks shows it resolved -- no manual re-read needed", matching is not None and matching["resolution_status"] == "resolved", str(matching))
        check("re-fetched flag carries the resolution note", matching is not None and "Confirmed via source PDF" in matching["resolution"]["note"], str(matching))

        # ---- Reopen ----
        print("\n--- Reopen ----")
        second_disc_id = next((f["discrepancy_id"] for f in flags if f["discrepancy_id"] != disc_id), None)
        if second_disc_id:
            status, err = _request("POST", f"/discrepancies/{second_disc_id}/reopen", json_body={"note": "n", "resolved_by": "y"})
            check("reopening a still-open discrepancy returns 400", status == 400, str(err))

        status, reopened = _request("POST", f"/discrepancies/{disc_id}/reopen", json_body={
            "note": "Need a second look after all.", "resolved_by": "Bob Reviewer",
        })
        check("reopen returns 200", status == 200, str(reopened))
        check("status flips back to open", reopened.get("status") == "open", str(reopened))
        check("reopen is also permanently logged (2 entries now)", len(reopened.get("resolutions", [])) == 2, str(reopened))

        status, filtered = _request("GET", f"/discrepancies?status=open&lease_id={lease_id}")
        check("filtered list finds the reopened discrepancy", any(d["id"] == disc_id for d in filtered), str(filtered))

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
