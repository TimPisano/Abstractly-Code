"""
Live API regression suite for POST /portfolio/t12-reconciliation --
follows the exact convention established by test_live_composition_api.py
(see that file's own docstring for the full reasoning): runs against the
actually-running dev server over real HTTP, not Flask's test_client(),
specifically because test_client() re-imports the app fresh every run
and so can never catch "the route/logic is right in the source file, but
the currently-running server process is stale" -- a real bug that hit
this exact project earlier in this same feature batch (see DECISIONS.md).

Uses the same synthetic Yardi rent roll + T12 fixtures as
test_t12_synthetic_fixture.py (both clearly labeled fabricated test
fixtures, not real files -- see that file's own docstring), imported
through the real live /leases/import-rent-roll route first so this
exercises the true end-to-end story: import a rent roll, upload a T12,
get a real cross-check back.
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
    boundary = "----T12ApiTestBoundary"
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

        # ---- Wiring smoke check: route is live, error paths honest ----
        print("\n--- Route wiring and error paths ----")
        body, content_type = _multipart_body({}, [("file", "t12.csv", b"Notes\nnothing here\n", "text/csv")])
        status, err = _request("POST", "/portfolio/t12-reconciliation", data=body, headers={"Content-Type": content_type})
        check("t12-reconciliation route is live (not 404)", status != 404, str(status))
        check("missing property_address on an otherwise-unparseable file still surfaces a 4xx", 400 <= status < 500, str(status))

        body2, content_type2 = _multipart_body(
            {"property_address": "Nowhere"},
            [("file", "t12.csv", b"Notes\nnothing here\n", "text/csv")],
        )
        status, err = _request("POST", "/portfolio/t12-reconciliation", data=body2, headers={"Content-Type": content_type2})
        check("unparseable T12 returns 400 with a real error message", status == 400 and "error" in err, f"{status} {err}")

        # ---- Real end-to-end story: import a rent roll, upload a T12 for
        # the same property, confirm a genuine cross-check. ----
        print("\n--- Real rent roll import + real T12 upload, same property ----")
        rr_body, rr_content_type = _multipart_body(
            {"property_address": "Riverside Commons Shopping Center"},
            [("file", "synthetic_yardi_rent_roll.csv", _read_fixture("synthetic_yardi_rent_roll.csv"), "text/csv")],
        )
        status, import_result = _request("POST", "/leases/import-rent-roll", data=rr_body, headers={"Content-Type": rr_content_type})
        check("rent roll import succeeds", status == 201, str(import_result))
        for lease in import_result.get("leases", []):
            created_lease_ids.append(lease["id"])
        check("rent roll import created 3 leases", len(created_lease_ids) == 3, str(len(created_lease_ids)))

        t12_body, t12_content_type = _multipart_body(
            {"property_address": "Riverside Commons Shopping Center"},
            [("file", "synthetic_t12_operating_statement.csv", _read_fixture("synthetic_t12_operating_statement.csv"), "text/csv")],
        )
        status, result = _request("POST", "/portfolio/t12-reconciliation", data=t12_body, headers={"Content-Type": t12_content_type})
        check("t12-reconciliation returns 200 for a real matching property", status == 200, str(result))
        check("matched all 3 rent-roll leases at this building", result.get("matched_lease_count") == 3, str(result))
        check(
            "rent_roll_annual_rent is the real (3200+4950+6800)*12 total",
            result.get("rent_roll_annual_rent") == 179400.0,
            str(result.get("rent_roll_annual_rent")),
        )
        check(
            "t12_annual_rental_income is Total Rental Income, NOT Gross Potential Rent",
            result.get("t12_annual_rental_income") == 187900.0,
            str(result.get("t12_annual_rental_income")),
        )
        check("small realistic gap (4.5%) correctly not flagged", result.get("flagged") is False, str(result.get("flagged")))
        check("t12_source cites the real matched line item", result.get("t12_source", {}).get("quote") == "Total Rental Income", str(result.get("t12_source")))

        # ---- T12 upload must never persist a lease record ----
        status, leases_after = _request("GET", "/leases")
        check("T12 upload created no lease records (still exactly 3)", status == 200 and len(leases_after) == 3, str(len(leases_after) if isinstance(leases_after, list) else leases_after))

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
