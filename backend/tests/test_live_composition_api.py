"""
Live API regression suite for the "Portfolio Composition & Risk" endpoints
added in this feature batch: GET /portfolio/tenant-concentration,
GET /portfolio/rollover, GET /portfolio/loss-to-lease,
GET /portfolio/rent-roll-reconciliation, and POST /leases/import-rent-roll.

Requires the backend already running at API_BASE_URL. Wipes leases at the
start (same convention as test_live_portfolio_api.py / test_live_dashboard_
api.py) so assertions can be exact.

This file deliberately does NOT re-verify the exact math behind HHI, WALT,
rollover bucketing, or loss-to-lease percentages -- that's already covered
exhaustively (~45+ cases, including rounding-compounding and boundary
edge cases) by test_portfolio.py's unit tests, and the request/response
shape is already covered by test_tenant_concentration_api.py,
test_rollover_api.py, test_loss_to_lease_api.py, test_rent_roll_import_
api.py, and test_rent_roll_reconciliation_api.py's Flask test_client()
tests. What NONE of those catch: a route that exists in the source file
but isn't actually live on the currently-running server process (Flask's
test_client() re-imports the app fresh every run, so a stale, un-restarted
dev server never shows up as a failure there). That exact class of bug was
found by hand during this feature's own live-browser verification pass
(see DECISIONS.md's "Dashboard UI for the 4 new portfolio metrics" entry)
-- this file exists so future regressions of that same kind get caught by
running the suite, not by luck.

Uses only POST /leases/import-rent-roll (not PDF fixture uploads) to build
its test portfolio, since rent roll import gives full, exact control over
every field's value with no OCR/regex extraction uncertainty involved --
appropriate for a wiring/shape smoke test that needs known values, not
appropriate as a replacement for the fixture-PDF-based extraction tests
elsewhere in this suite.

Like every other file in this "live" family, this assumes exclusive use
of the shared local dev database for the duration of the run -- a real
lease uploaded by another concurrently-running session (e.g. a peer
Claude session sharing this same backend process) between this file's
clear_all_leases() and its assertions will make the exact-value checks
here (total_rent, top_1_pct, etc.) spuriously fail, not because of a
real regression, but because the portfolio genuinely contained more
data than this file assumed. If a run fails on exact totals that don't
match what this file itself imported, check for concurrent activity on
the shared dev DB before assuming a real bug.
"""
import os
import sys
import csv
import io
import json
import urllib.request
import urllib.error
from datetime import date, timedelta

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
    """Builds a multipart/form-data body. files: list of (field_name, filename, bytes, content_type)."""
    boundary = "----CompositionApiTestBoundary"
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
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def clear_all_leases():
    status, leases = _request("GET", "/leases")
    assert status == 200, f"could not list leases to clear: {status} {leases}"
    for lease in leases:
        _request("DELETE", f"/leases/{lease['id']}")


def _csv_bytes(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _import_rent_roll(csv_rows, filename, property_address=None):
    body, content_type = _multipart_body(
        {"property_address": property_address} if property_address else {},
        [("file", filename, _csv_bytes(csv_rows), "text/csv")],
    )
    return _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": content_type})


def _upload_pdf_fixture(filename):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "rb") as f:
        content = f.read()
    body, content_type = _multipart_body({}, [("file", filename, content, "application/pdf")])
    status, result = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
    assert status == 201, f"upload of {filename} failed: {status} {result}"
    assert result["split_count"] == 1, f"{filename} unexpectedly split into {result['split_count']} leases"
    return result["leases"][0]["id"]


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

        # ---- Empty-portfolio shape: every endpoint must be LIVE (not
        # 404) and must return an honest "not enough data" shape rather
        # than an error or a fabricated zero. ----
        print("\n--- Empty portfolio: routes are live, shapes are honest ----")
        status, concentration = _request("GET", "/portfolio/tenant-concentration")
        check("tenant-concentration route is live (not 404)", status == 200, str(status))
        check("tenant-concentration is honest about no data", concentration.get("tenant_count") == 0, str(concentration))

        status, rollover = _request("GET", "/portfolio/rollover")
        check("rollover route is live (not 404)", status == 200, str(status))
        check(
            "rollover is honest about no data",
            rollover.get("walt", {}).get("walt_years") is None,
            str(rollover),
        )

        status, loss_to_lease = _request("GET", "/portfolio/loss-to-lease")
        check("loss-to-lease route is live (not 404)", status == 200, str(status))
        check("loss-to-lease is honest about no data", loss_to_lease.get("lease_count") == 0, str(loss_to_lease))

        status, reconciliation = _request("GET", "/portfolio/rent-roll-reconciliation")
        check("rent-roll-reconciliation route is live (not 404)", status == 200, str(status))
        check(
            "reconciliation is honest about no data",
            reconciliation.get("rent_roll_lease_count") == 0 and reconciliation.get("mismatches") == [],
            str(reconciliation),
        )

        # ---- Build a small, fully-known portfolio entirely through
        # POST /leases/import-rent-roll -- exact field values, no OCR/
        # regex extraction uncertainty, so every expectation below is
        # hand-computable. ----
        print("\n--- Importing a small controlled rent roll ----")
        in_90_days = (date.today() + timedelta(days=90)).strftime("%m/%d/%Y")
        in_500_days = (date.today() + timedelta(days=500)).strftime("%m/%d/%Y")
        status, import_result = _import_rent_roll(
            [
                ["Tenant", "Unit", "Square Footage", "Rent", "Lease End"],
                ["Regression Anchor Corp", "Suite 100", "3000", "9000.00", in_90_days],
                ["Regression Minor Co", "Suite 200", "1000", "1000.00", in_500_days],
            ],
            "live_composition_test.csv",
            property_address="750 Regression Test Ave",
        )
        check("import-rent-roll route is live and succeeds", status == 201, str(import_result))
        check("import-rent-roll imported both rows", import_result.get("imported_count") == 2, str(import_result))
        for lease in import_result.get("leases", []):
            created_lease_ids.append(lease["id"])
        check("collected 2 lease ids from the import", len(created_lease_ids) == 2, str(len(created_lease_ids)))

        # ---- Tenant concentration: 2 tenants, $9,000 + $1,000 = $10,000
        # total, top tenant (Anchor) is exactly 90% -- comfortably past
        # both the HHI and top-tenant "high" thresholds. ----
        print("\n--- Tenant concentration with real, known data ----")
        status, concentration = _request("GET", "/portfolio/tenant-concentration")
        check("tenant-concentration returns 200 with real data", status == 200, str(status))
        check("tenant-concentration sees both tenants", concentration.get("tenant_count") == 2, str(concentration))
        check("tenant-concentration total_rent is $10,000", concentration.get("total_rent") == 10000.0, str(concentration.get("total_rent")))
        check(
            "tenant-concentration top_1_pct is 90%",
            concentration.get("top_1_pct") == 90.0,
            str(concentration.get("top_1_pct")),
        )
        check(
            "tenant-concentration reads high risk (90% concentration)",
            concentration.get("concentration_level") == "high",
            str(concentration.get("concentration_level")),
        )

        # ---- Rollover: the Anchor lease is 90 days out (year_1 bucket,
        # rent-weighted 90% of the roll) -- comfortably past the 25%
        # high-risk threshold. ----
        print("\n--- Rollover risk with real, known data ----")
        status, rollover = _request("GET", "/portfolio/rollover")
        check("rollover returns 200 with real data", status == 200, str(status))
        check("rollover WALT is a real (non-null) number now", isinstance(rollover.get("walt", {}).get("walt_years"), (int, float)), str(rollover))
        check(
            "rollover year_1 bucket rent is $9,000 (the 90-day lease)",
            rollover.get("rollover_schedule", {}).get("buckets", {}).get("year_1", {}).get("rent") == 9000.0,
            str(rollover.get("rollover_schedule", {}).get("buckets", {}).get("year_1")),
        )
        check(
            "rollover reads high risk (90% rolling over within a year)",
            rollover.get("rollover_schedule", {}).get("rollover_risk_level") == "high",
            str(rollover.get("rollover_schedule", {}).get("rollover_risk_level")),
        )

        # ---- Loss to lease: both rows share a building ("750
        # Regression Test Ave"), so they comp against each other.
        # Anchor is $3.00/sqft (9000/3000), Minor is $1.00/sqft
        # (1000/1000) -- Anchor is the building's top rent (0% loss),
        # Minor is 66.7% below it. ----
        print("\n--- Loss to lease with real, known data ----")
        status, loss_to_lease = _request("GET", "/portfolio/loss-to-lease")
        check("loss-to-lease returns 200 with real data", status == 200, str(status))
        check("loss-to-lease groups both same-building leases", loss_to_lease.get("lease_count") == 2, str(loss_to_lease))
        by_tenant = {l["tenant"]: l for l in loss_to_lease.get("leases", [])}
        check(
            "loss-to-lease: Anchor is the building's top rent (0% loss)",
            by_tenant.get("Regression Anchor Corp", {}).get("loss_pct") == 0.0,
            str(by_tenant.get("Regression Anchor Corp")),
        )
        check(
            "loss-to-lease: Minor is 66.7% below the building's top rent",
            by_tenant.get("Regression Minor Co", {}).get("loss_pct") == 66.67,
            str(by_tenant.get("Regression Minor Co")),
        )

        # ---- Reconciliation: upload one real PDF lease document (an
        # unrelated address) now, AFTER the three checks above, so it
        # doesn't also feed into their tenant-concentration/rollover/
        # loss-to-lease numbers (those functions run over every lease
        # regardless of source, PDF or rent roll, by design -- see
        # DECISIONS.md). It correctly finds nothing to compare -- an
        # honest empty result with non-zero counts on both sides, not
        # the same shape as the true "no data at all" case checked
        # above. ----
        print("\n--- Reconciliation: real data present, but no matching addresses ----")
        pdf_lease_id = _upload_pdf_fixture("sample_lease.pdf")
        created_lease_ids.append(pdf_lease_id)
        status, reconciliation = _request("GET", "/portfolio/rent-roll-reconciliation")
        check("reconciliation returns 200 with real data", status == 200, str(status))
        check("reconciliation sees both rent roll rows", reconciliation.get("rent_roll_lease_count") == 2, str(reconciliation))
        check("reconciliation sees the one lease document", reconciliation.get("lease_document_count") == 1, str(reconciliation))
        check(
            "reconciliation correctly finds no address overlap to compare",
            reconciliation.get("compared_pair_count") == 0 and reconciliation.get("mismatches") == [],
            str(reconciliation),
        )

        # ---- Error path: import-rent-roll with a file that has no
        # recognizable tenant/rent columns fails cleanly, not a 500. ----
        print("\n--- import-rent-roll error path ----")
        status, err = _import_rent_roll(
            [["Notes", "Parking Spaces"], ["decorative header row, no real data", "4"]],
            "unrecognizable.csv",
        )
        check(
            "import-rent-roll with no recognizable columns returns 400, not a 500",
            status == 400 and "error" in err,
            f"{status} {err}",
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
