"""
Live API regression suite for POST /portfolio/investment-memo.pdf and
.xlsx -- follows the exact convention established by
test_live_discrepancies_api.py: runs against the actually-running dev
server over real HTTP, specifically to catch "the route/logic is right
in the source file, but the currently-running server process is
stale" (a real bug class this project has hit before -- see
DECISIONS.md).

Builds the exact real-world scenario that caught a real double-
counting bug during manual review (see DECISIONS.md): a real PDF lease
and a real rent-roll import for the SAME unit, a real resulting
discrepancy, a real resolution, and a real T12 file attached to the
memo request itself -- then confirms the PDF and Excel outputs agree
with each other and are not double-counted.
"""
import os
import sys
import csv
import io
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pypdf
from openpyxl import load_workbook

API_BASE_URL = "http://localhost:5000"
FIXTURES_DIR = os.path.dirname(__file__)
PROPERTY = "4200 Commerce Parkway, Austin, Texas 78701"
# The exact address sample_lease_commercial.pdf's own property_address field
# extracts to (suite included) -- the rent-roll import below must match this
# EXACTLY (reconciliation is exact-unit matching, suite included, not just
# same building) for a real mismatch to be found at all.
UNIT_ADDRESS = "4200 Commerce Parkway, Suite 110, Austin, Texas 78701"


def _request(method, path, data=None, headers=None):
    url = f"{API_BASE_URL}{path}"
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "application/json" in content_type:
                return resp.status, json.loads(raw.decode()), dict(resp.headers)
            return resp.status, raw, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode()), dict(e.headers)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return e.code, raw, dict(e.headers)


def _multipart_body(fields, files):
    boundary = "----InvestmentMemoApiTestBoundary"
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


def _json_request(method, path, json_body=None):
    body = json.dumps(json_body).encode() if json_body is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    status, data, _ = _request(method, path, data=body, headers=headers)
    return status, data


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def clear_all_leases():
    status, leases = _json_request("GET", "/leases")
    assert status == 200, f"could not list leases to clear: {status} {leases}"
    for lease in leases:
        _json_request("DELETE", f"/leases/{lease['id']}")


def _read_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


def _pdf_text(pdf_bytes):
    """Whitespace-normalized (single spaces, no newlines) -- reportlab wraps long lines at arbitrary points, and PyPDF2 renders each wrapped line as a real newline, so a substring check against the raw text would be fragile against wrapping that has nothing to do with correctness."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    raw = "\n".join(page.extract_text() for page in reader.pages)
    return " ".join(raw.split())


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    status, health_check = _json_request("GET", "/health")
    check("server is reachable", status == 200 and health_check.get("status") == "healthy")

    created_lease_ids = []
    try:
        clear_all_leases()

        # ---- Real PDF lease + a real rent-roll snapshot of the SAME unit ----
        print("\n--- Building the real double-count scenario ----")
        body, ct = _multipart_body({}, [("file", "sample_lease_commercial.pdf", _read_fixture("sample_lease_commercial.pdf"), "application/pdf")])
        status, result, _ = _request("POST", "/leases", data=body, headers={"Content-Type": ct})

        check("real PDF lease upload succeeds", status == 201, str(result))
        pdf_lease_id = result["leases"][0]["id"]
        created_lease_ids.append(pdf_lease_id)
        real_rent = result["leases"][0]["extracted_fields"]["rent_amount"]["value"]

        rr_csv = _csv_bytes([["Tenant", "Rent", "Lease End"], ["Blue Sky Coffee Roasters, Inc.", "$6,000.00", "03/31/2030"]])
        body, ct = _multipart_body({"property_address": UNIT_ADDRESS}, [("file", "rentroll.csv", rr_csv, "text/csv")])
        status, result, _ = _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": ct})

        check("real rent roll import of the same unit succeeds", status == 201, str(result))
        created_lease_ids.extend(l["id"] for l in result.get("leases", []))

        # Trigger reconciliation + resolve the resulting discrepancy
        status, recon = _json_request("GET", "/portfolio/rent-roll-reconciliation")
        check("reconciliation finds the real mismatch", status == 200 and len(recon["mismatches"]) >= 1, str(recon))
        disc_id = recon["mismatches"][0]["discrepancy_id"]
        status, _resolved = _json_request("POST", f"/discrepancies/{disc_id}/resolve", {
            "correct_source": "lease_document", "note": "Confirmed against the signed PDF; rent roll predates the escalation step.", "resolved_by": "Jane Analyst",
        })
        check("resolving the real discrepancy succeeds", status == 200, str(status))

        # ---- PDF export, with a real T12 file attached ----
        print("\n--- POST /portfolio/investment-memo.pdf with a real T12 attached ----")
        t12_body, t12_ct = _multipart_body(
            {"property_address": PROPERTY},
            [("t12_file", "synthetic_t12_operating_statement.csv", _read_fixture("synthetic_t12_operating_statement.csv"), "text/csv")],
        )
        status, pdf_bytes, headers = _request("POST", "/portfolio/investment-memo.pdf", data=t12_body, headers={"Content-Type": t12_ct})
        check("PDF export returns 200", status == 200, str(status))
        check("PDF export has the right content type", headers.get("Content-Type", "").startswith("application/pdf"), str(headers.get("Content-Type")))
        check("PDF export has a real attachment filename", "attachment" in headers.get("Content-Disposition", ""), str(headers.get("Content-Disposition")))

        text = _pdf_text(pdf_bytes)
        check("PDF names the real tenant", "Blue Sky Coffee Roasters" in text, "tenant missing from PDF text")
        check("PDF total rent is NOT double-counted (shows the real single-lease rent, not rent+rent-roll-duplicate)", real_rent in text, f"expected {real_rent!r} in PDF text")
        check("PDF explicitly notes the excluded duplicate record", "excluded from these totals to avoid double-counting" in text, "dedup note missing from PDF")
        check("PDF shows the resolution", "Jane Analyst" in text and "Confirmed against the signed PDF" in text, "resolution text missing from PDF")
        check("PDF shows a real T12 cross-check result (not 'unavailable')", "T12 just uploaded for this memo" in text, "fresh T12 basis line missing")

        # ---- Excel export, same scenario, must agree with the PDF ----
        print("\n--- POST /portfolio/investment-memo.xlsx ----")
        body, ct = _multipart_body({"property_address": PROPERTY}, [])
        status, xlsx_bytes, headers = _request("POST", "/portfolio/investment-memo.xlsx", data=body, headers={"Content-Type": ct})
        check("Excel export returns 200", status == 200, str(status))
        check("Excel export has the right content type", "spreadsheetml" in headers.get("Content-Type", ""), str(headers.get("Content-Type")))

        workbook = load_workbook(io.BytesIO(xlsx_bytes))
        check("Excel has all 5 expected sheets", workbook.sheetnames == ["Overview", "Key Lease Terms", "Discrepancies & Resolutions", "T12 Cross-Check", "Rollover Schedule"], str(workbook.sheetnames))

        overview_rows = {row[0]: row[1] for row in workbook["Overview"].iter_rows(values_only=True) if row[0]}
        check("Excel overview shows exactly 1 lease covered (deduped)", overview_rows.get("Leases Covered (excl. rent-roll cross-check duplicates)") == 1, str(overview_rows))

        key_terms_sources = [row[1] for row in workbook["Key Lease Terms"].iter_rows(min_row=2, values_only=True)]
        check("Excel Key Lease Terms still LISTS both records (just doesn't double-count them)", set(key_terms_sources) == {"Lease Document", "Rent Roll Import"}, str(key_terms_sources))

        disc_rows = list(workbook["Discrepancies & Resolutions"].iter_rows(min_row=2, values_only=True))
        check("Excel discrepancies sheet has the real resolved discrepancy", len(disc_rows) >= 1 and disc_rows[0][4] == "Resolved", str(disc_rows))

        # ---- Portfolio-wide export still works ----
        print("\n--- Portfolio-wide export ----")
        status, portfolio_pdf, _ = _request("POST", "/portfolio/investment-memo.pdf", data=b"", headers={})
        check("portfolio-wide PDF export (no property_address) returns 200", status == 200, str(status))

        # ---- Error paths ----
        print("\n--- Error paths ----")
        bad_body, bad_ct = _multipart_body({}, [("t12_file", "t12.csv", b"Notes\nfake\n", "text/csv")])
        status, err, _ = _request("POST", "/portfolio/investment-memo.pdf", data=bad_body, headers={"Content-Type": bad_ct})

        check("t12_file without property_address returns 400", status == 400 and "property_address" in err.get("error", ""), str(err))

    finally:
        print("\nCleaning up test data...")
        for lease_id in created_lease_ids:
            _json_request("DELETE", f"/leases/{lease_id}")
        status, remaining = _json_request("GET", "/leases")
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
