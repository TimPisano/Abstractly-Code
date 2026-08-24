"""
Live API regression suite for GET /portfolio/property-trends -- follows
the exact convention established by test_live_discrepancies_api.py /
test_live_t12_api.py: runs against the actually-running dev server
over real HTTP, specifically to catch "the route/logic is right in the
source file, but the currently-running server process is stale" (a
real bug class this project has hit before -- see DECISIONS.md).

Simulates the real workflow this feature exists for: the SAME rent
roll re-imported for the same property at two different points in
time (a real, expected workflow now that portfolio history is a first-
class thing), with a deliberate rent increase on one row (same tenant
-- a real escalation/renewal story) and a tenant change on another
(same unit, different tenant -- a real turnover story).
"""
import os
import sys
import csv
import io
import json
import urllib.request
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

API_BASE_URL = "http://localhost:5000"
PROPERTY = "777 Trend Ave, Springfield, IL"


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
    boundary = "----HistoryApiTestBoundary"
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


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def clear_all_leases():
    status, leases = _request("GET", "/leases")
    assert status == 200, f"could not list leases to clear: {status} {leases}"
    for lease in leases:
        _request("DELETE", f"/leases/{lease['id']}")


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

        # ---- Real "same property, re-imported later" workflow ----
        print("\n--- Real rent roll re-imported for the same property, two points in time ----")
        import_1 = _csv_bytes([
            ["Tenant", "Rent", "Lease End"],
            ["Acme Corp", "$3,000.00", "12/31/2027"],
        ])
        body, content_type = _multipart_body({"property_address": PROPERTY}, [("file", "rentroll_q1.csv", import_1, "text/csv")])
        status, result = _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": content_type})
        check("first rent roll import succeeds", status == 201, str(result))
        created_lease_ids.extend(l["id"] for l in result.get("leases", []))

        import_2 = _csv_bytes([
            ["Tenant", "Rent", "Lease End"],
            ["Acme Corp", "$3,300.00", "12/31/2029"],  # +10%, same tenant -- escalation/renewal
        ])
        body, content_type = _multipart_body({"property_address": PROPERTY}, [("file", "rentroll_q2.csv", import_2, "text/csv")])
        status, result = _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": content_type})
        check("second rent roll import succeeds", status == 201, str(result))
        created_lease_ids.extend(l["id"] for l in result.get("leases", []))

        # ---- Query trends for the real property ----
        print("\n--- GET /portfolio/property-trends ----")
        status, trends = _request("GET", f"/portfolio/property-trends?property_address={urllib.parse.quote(PROPERTY)}")
        check("route returns 200", status == 200, str(trends))
        check("both historical uploads are in the timeline", trends.get("record_count") == 2, str(trends.get("record_count")))
        check("history is chronologically ordered", trends["history"][0]["rent_amount"] == "$3,000.00", str(trends.get("history")))

        rent_growth = trends.get("rent_growth", {})
        check("exactly one unit tracked for rent growth", rent_growth.get("units_with_growth_data") == 1, str(rent_growth))
        transition = rent_growth["units"][0]["transitions"][0]
        check("real +10% rent increase computed correctly", transition["pct_change"] == 10.0, str(transition))
        check("same tenant across the transition -- correctly NOT flagged as turnover", transition["tenant_changed"] is False, str(transition))

        turnover = trends.get("tenant_turnover", {})
        check("no real turnover occurred -- correctly 0 events", turnover.get("turnover_count") == 0, str(turnover))

        rollover = trends.get("rollover_pattern", {})
        check("both real lease-end dates counted", rollover.get("total_expirations_tracked") == 2, str(rollover))
        check("December correctly bucketed twice", rollover.get("by_month", {}).get("12") == 2, str(rollover.get("by_month")))

        # ---- Error paths ----
        print("\n--- Error paths ----")
        status, err = _request("GET", "/portfolio/property-trends")
        check("missing property_address returns 400", status == 400, str(err))

        status, empty_trends = _request("GET", "/portfolio/property-trends?property_address=" + urllib.parse.quote("1 Nowhere Rd, Nowhere, XX"))
        check("a real but unmatched address returns 200 with zero records, not an error", status == 200 and empty_trends.get("record_count") == 0, str(empty_trends))

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
