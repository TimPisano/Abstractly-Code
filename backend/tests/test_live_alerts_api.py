"""
Live API regression suite for the proactive alerting system
(POST /alerts/generate, GET /alerts*, POST /alerts/<id>/dismiss) --
follows the exact convention established by test_live_discrepancies_api.py:
runs against the actually-running dev server over real HTTP,
specifically to catch "the route/logic is right in the source file, but
the currently-running server process is stale" (a real bug class this
project has hit before -- see DECISIONS.md).

Builds a real portfolio that genuinely trips all four alert types
(a near-term expiration, a real discrepancy from a real messy PDF, a
real below-market unit at a shared building, and a dominant tenant),
generates alerts against the live server, and confirms the whole
resolve/dismiss lifecycle end to end.
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
    boundary = "----AlertsApiTestBoundary"
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

        # ---- Build a real portfolio that trips all four alert types ----
        print("\n--- Building a real portfolio with all 4 alert conditions ----")

        near_term_end = (date.today() + timedelta(days=15)).strftime("%m/%d/%Y")
        expiring_csv = _csv_bytes([["Tenant", "Rent", "Lease End"], ["Expiring Tenant Co", "$3,000.00", near_term_end]])
        body, ct = _multipart_body({"property_address": "1 Alert Test Ave"}, [("file", "expiring.csv", expiring_csv, "text/csv")])
        status, result = _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": ct})
        check("expiring-lease rent roll import succeeds", status == 201, str(result))
        created_lease_ids.extend(l["id"] for l in result.get("leases", []))

        below_market_csv = _csv_bytes([
            ["Tenant", "Rent", "Suite", "Square Feet"],
            ["Top Rate Co", "$10,000.00", "100", "1000"],
            ["Discount Co", "$6,000.00", "200", "1000"],
        ])
        body, ct = _multipart_body({"property_address": "2 Comp Building Blvd"}, [("file", "belowmarket.csv", below_market_csv, "text/csv")])
        status, result = _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": ct})
        check("below-market rent roll import succeeds", status == 201, str(result))
        created_lease_ids.extend(l["id"] for l in result.get("leases", []))

        concentration_csv = _csv_bytes([["Tenant", "Rent"], ["Dominant Tenant Corp", "$50,000.00"]])
        body, ct = _multipart_body({"property_address": "3 Concentration Way"}, [("file", "concentration.csv", concentration_csv, "text/csv")])
        status, result = _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": ct})
        check("concentration rent roll import succeeds", status == 201, str(result))
        created_lease_ids.extend(l["id"] for l in result.get("leases", []))

        body, ct = _multipart_body({}, [("file", "missing_clauses_office.pdf", _read_fixture("missing_clauses_office.pdf"), "application/pdf")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        check("real messy PDF upload succeeds", status == 201, str(result))
        discrepancy_lease_id = result["leases"][0]["id"]
        created_lease_ids.append(discrepancy_lease_id)
        status, flags = _request("GET", f"/leases/{discrepancy_lease_id}/risks")
        check("real risk flags exist to become a discrepancy", status == 200 and len(flags) > 0, str(flags))

        # ---- Generate, against the live server ----
        print("\n--- POST /alerts/generate ----")
        status, gen_result = _request("POST", "/alerts/generate")
        check("generate returns 200", status == 200, str(gen_result))
        check("at least 4 alerts created (one per type)", gen_result.get("created", 0) >= 4, str(gen_result))

        status, all_alerts = _request("GET", "/alerts")
        check("list route returns 200", status == 200, str(status))
        types_seen = {a["alert_type"] for a in all_alerts}
        check("all 4 alert types present", types_seen == {"lease_expiration", "below_market_rent", "tenant_concentration", "new_discrepancy"}, str(types_seen))

        expiration_alert = next(a for a in all_alerts if a["alert_type"] == "lease_expiration")
        check("expiration alert names the real tenant", "Expiring Tenant Co" in expiration_alert["message"], str(expiration_alert["message"]))
        check("expiration alert is high severity (within 30 days)", expiration_alert["severity"] == "high", str(expiration_alert))

        concentration_alert = next(a for a in all_alerts if a["alert_type"] == "tenant_concentration")
        check("concentration alert names the real dominant tenant", "Dominant Tenant Corp" in concentration_alert["title"], str(concentration_alert))

        below_market_alert = next(a for a in all_alerts if a["alert_type"] == "below_market_rent")
        check("below-market alert names the real underpriced tenant", "Discount Co" in below_market_alert["message"], str(below_market_alert))

        # ---- Idempotence: re-running must not duplicate ----
        status, gen_again = _request("POST", "/alerts/generate")
        check("second generate creates 0 new (idempotent)", gen_again.get("created") == 0, str(gen_again))
        check("second generate refreshed the same alerts", gen_again.get("refreshed", 0) >= 4, str(gen_again))

        # ---- Digest ----
        status, digest = _request("GET", "/alerts/summary")
        check("summary route returns 200", status == 200, str(digest))
        status, active_only = _request("GET", "/alerts?status=active")
        check(
            "digest active_count matches the active-filtered list length "
            "(NOT the unfiltered /alerts list, which accumulates dismissed/auto_resolved "
            "alerts from every prior live-test run against this same dev DB, by design)",
            digest.get("active_count") == len(active_only), str((digest, len(active_only))),
        )

        # ---- Dismiss lifecycle ----
        print("\n--- Dismiss lifecycle ----")
        status, err = _request("POST", f"/alerts/{concentration_alert['id']}/dismiss", json_body={})
        check("dismiss with no dismissed_by returns 400", status == 400, str(err))

        status, dismissed = _request("POST", f"/alerts/{concentration_alert['id']}/dismiss", json_body={
            "dismissed_by": "Jane Analyst", "note": "Known and accepted for this deal.",
        })
        check("dismiss succeeds", status == 200 and dismissed["status"] == "dismissed", str(dismissed))

        status, gen_after_dismiss = _request("POST", "/alerts/generate")
        status, refetched = _request("GET", f"/alerts/{concentration_alert['id']}")
        check("dismissed alert stays dismissed after regenerating (condition unchanged)", refetched["status"] == "dismissed", str(refetched))

        status, err = _request("GET", "/alerts/999999")
        check("nonexistent alert returns 404", status == 404, str(err))

        # ---- Auto-resolve: resolve the underlying discrepancy, confirm its alert clears ----
        print("\n--- Auto-resolve when the underlying condition clears ----")
        new_disc_alert = next(a for a in all_alerts if a["alert_type"] == "new_discrepancy")
        disc_id = new_disc_alert["details"]["discrepancy_id"]
        status, _ = _request("POST", f"/discrepancies/{disc_id}/resolve", json_body={
            "correct_source": "lease_document", "note": "Confirmed fine.", "resolved_by": "Jane Analyst",
        })
        check("resolving the underlying discrepancy succeeds", status == 200, str(status))

        status, gen_final = _request("POST", "/alerts/generate")
        check("generate after resolving auto-resolves the matching alert", gen_final.get("auto_resolved", 0) >= 1, str(gen_final))
        status, refetched_disc_alert = _request("GET", f"/alerts/{new_disc_alert['id']}")
        check("that specific alert is now auto_resolved", refetched_disc_alert["status"] == "auto_resolved", str(refetched_disc_alert))

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
