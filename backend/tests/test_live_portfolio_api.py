"""
Automated regression suite for the portfolio API layer, run against the
ACTUAL LIVE backend server (not a direct function call) via HTTP.

Requires the backend to already be running at API_BASE_URL, using its
normal SQLite dev database. This test WIPES that database's leases at
the start (see clear_all_leases()) so every assertion can be exact
rather than relative to whatever pre-existing data happened to be
there — reasonable for a local dev DB that's gitignored and disposable,
not appropriate to run against anything holding real data.

Covers: batch upload with a deliberately corrupted file (error
recovery), amendments (effective-field override), portfolio summary/
timeline/risks, per-lease risks, Q&A (with citation grounding),
compare, benchmark, CSV/Excel/HTML export, and the 404/400 error paths.
Re-run this any time the API layer or any analysis module changes to
catch regressions — this is the "can be re-run to catch regressions
in future sessions" test the project's quality bar calls for.
"""
import os
import sys
import json
import csv
import io
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

API_BASE_URL = "http://localhost:5000"
FIXTURES_DIR = os.path.dirname(__file__)

ALL_FIXTURES = [
    "sample_lease.pdf", "sample_lease_commercial.pdf", "retail_lease.pdf",
    "office_lease.pdf", "casual_sublease.pdf", "underpriced_downtown.pdf",
    "missing_clauses_office.pdf", "tenant_friendly_terms.pdf",
    "inconsistent_escalation.pdf", "reversed_dates.pdf",
]


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
    """Builds a multipart/form-data body. files: list of (field_name, filename, bytes)."""
    boundary = "----PortfolioApiTestBoundary"
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for field_name, filename, content in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


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

    # Sanity: server reachable
    status, health = _request("GET", "/health")
    check("server is reachable", status == 200 and health.get("status") == "healthy")

    print("\nClearing existing leases for a clean baseline...")
    clear_all_leases()
    status, leases = _request("GET", "/leases")
    check("DB is empty after clearing", status == 200 and leases == [], f"{len(leases)} leases remain")

    created_lease_ids = []
    try:
        # ---- Batch upload with error recovery ----
        print("\n--- Batch upload (10 valid + 1 corrupted) ---")
        corrupted_path = "/tmp/portfolio_test_corrupted.pdf"
        with open(corrupted_path, "wb") as f:
            f.write(os.urandom(300))

        files = []
        for name in ALL_FIXTURES:
            with open(os.path.join(FIXTURES_DIR, name), "rb") as f:
                files.append(("files", name, f.read()))
        with open(corrupted_path, "rb") as f:
            files.append(("files", "corrupted.pdf", f.read()))
        body, content_type = _multipart_body({}, files)
        status, batch_result = _request("POST", "/leases/batch", data=body, headers={"Content-Type": content_type})

        check("batch upload returns 200", status == 200, str(status))
        check("batch reports 11 total", batch_result.get("total") == 11, str(batch_result.get("total")))
        check("batch reports 10 succeeded", batch_result.get("succeeded") == 10, str(batch_result.get("succeeded")))
        check("batch reports 1 failed", batch_result.get("failed") == 1, str(batch_result.get("failed")))

        corrupted_result = next((r for r in batch_result["results"] if r["filename"] == "corrupted.pdf"), None)
        check("corrupted file result has success=False", corrupted_result and corrupted_result["success"] is False)
        check("corrupted file has a clear error message", corrupted_result and "error" in corrupted_result and len(corrupted_result["error"]) > 0)

        for r in batch_result["results"]:
            if r["success"]:
                # Every fixture here is a genuine single lease, so
                # each successful file result carries exactly one
                # entry in its (now-plural) "leases" list.
                check(f"{r['filename']} split into exactly 1 lease", r.get("split_count") == 1, str(r.get("split_count")))
                created_lease_ids.append(r["leases"][0]["id"])
        check("collected 10 lease ids from successful uploads", len(created_lease_ids) == 10, str(len(created_lease_ids)))

        lease_by_filename = {}
        for lease_id in created_lease_ids:
            status, lease = _request("GET", f"/leases/{lease_id}")
            lease_by_filename[lease["filename"]] = lease
        commercial_id = lease_by_filename["sample_lease_commercial.pdf"]["id"]
        underpriced_id = lease_by_filename["underpriced_downtown.pdf"]["id"]

        # ---- List leases ----
        status, leases = _request("GET", "/leases")
        check("GET /leases returns all 10", status == 200 and len(leases) == 10, str(len(leases)))

        # ---- Amendments: effective-field override ----
        print("\n--- Amendments ---")
        # Reuse the retail lease fixture as a stand-in "amendment" document —
        # its own rent value should override the commercial lease's rent in
        # the effective view.
        with open(os.path.join(FIXTURES_DIR, "retail_lease.pdf"), "rb") as f:
            content = f.read()
        body, content_type = _multipart_body({}, [("file", "rent_amendment.pdf", content)])
        status, updated_lease = _request(
            "POST", f"/leases/{commercial_id}/amendments", data=body, headers={"Content-Type": content_type}
        )
        check("amendment upload returns 201", status == 201, str(status))
        check("amendment_count is 1 after upload", updated_lease.get("amendment_count") == 1, str(updated_lease.get("amendment_count")))
        original_rent = "$6,250.00"
        amended_rent = updated_lease["extracted_fields"]["rent_amount"]["value"]
        check("effective rent reflects the amendment, not the original", amended_rent == "$6,000.00", f"got {amended_rent!r}")

        status, amendments = _request("GET", f"/leases/{commercial_id}/amendments")
        check("GET amendments lists 1 amendment", status == 200 and len(amendments) == 1, str(len(amendments) if isinstance(amendments, list) else amendments))

        # Undo: delete and re-verify effective fields revert (delete cascades to amendments only when deleting the base — here we just re-fetch to confirm base is untouched)
        status, base_only = _request("GET", f"/leases/{commercial_id}")
        check("effective lease still shows amendment after re-fetch", base_only["extracted_fields"]["rent_amount"]["value"] == "$6,000.00")

        # ---- Portfolio summary ----
        print("\n--- Portfolio summary & timeline ---")
        status, summary = _request("GET", "/portfolio/summary")
        check("portfolio summary returns 200", status == 200, str(status))
        check("lease_count is 10", summary.get("lease_count") == 10, str(summary.get("lease_count")))
        check("total_monthly_rent is a positive number", isinstance(summary.get("total_monthly_rent"), (int, float)) and summary["total_monthly_rent"] > 0)
        check("fields_missing_count covers all 15 fields", len(summary.get("fields_missing_count", {})) == 15, str(len(summary.get("fields_missing_count", {}))))

        # ---- Timeline ----
        status, timeline = _request("GET", "/portfolio/timeline")
        check("portfolio timeline returns 200", status == 200, str(status))
        bucket_total = sum(len(v) for v in timeline.values())
        check("timeline accounts for all 10 leases", bucket_total == 10, str(bucket_total))

        # ---- Risks ----
        print("\n--- Risk flags ---")
        status, all_risks = _request("GET", "/portfolio/risks")
        check("portfolio risks returns 200", status == 200, str(status))
        check("portfolio risks covers all 10 leases", len(all_risks) == 10, str(len(all_risks)))
        total_flags = sum(len(r["flags"]) for r in all_risks)
        check("portfolio has a substantial number of real flags", total_flags >= 15, f"{total_flags} total flags")

        status, underpriced_risks = _request("GET", f"/leases/{underpriced_id}/risks")
        check("single-lease risk endpoint returns 200", status == 200, str(status))
        check(
            "underpriced lease is flagged below_market_rent",
            any(f["category"] == "below_market_rent" for f in underpriced_risks),
            str([f["category"] for f in underpriced_risks]),
        )

        # ---- Q&A ----
        print("\n--- Q&A ---")
        status, qa_result = _request("POST", "/qa", json_body={"question": "which leases expire in the next year"})
        check("qa returns 200", status == 200, str(status))
        check("qa answer references real lease data", "lease(s)" in qa_result["answer"] or "expire" in qa_result["answer"].lower())
        check("qa citations trace to real pages", all("page" in c and "quote" in c for c in qa_result["citations"]))

        status, scoped_qa = _request("POST", "/qa", json_body={"question": "does this lease have an exclusivity clause", "lease_id": commercial_id})
        check("lease-scoped qa returns 200", status == 200, str(status))
        check("lease-scoped qa answers about the right lease", "coffee" in scoped_qa["answer"].lower() or "yes" in scoped_qa["answer"].lower(), scoped_qa["answer"][:100])

        # ---- Compare & benchmark ----
        print("\n--- Compare & benchmark ---")
        status, comparison = _request("GET", f"/leases/compare?ids={commercial_id},{underpriced_id}")
        check("compare returns 200", status == 200, str(status))
        check("compare returns 2 filenames", len(comparison.get("filenames", [])) == 2, str(comparison.get("filenames")))

        status, err = _request("GET", f"/leases/compare?ids={commercial_id}")
        check("compare with 1 id returns 400", status == 400, str(status))

        status, benchmark = _request("GET", f"/leases/{underpriced_id}/benchmark")
        check("benchmark returns 200", status == 200, str(status))
        check(
            "underpriced lease benchmarks below_average on rent",
            benchmark.get("rent_amount", {}).get("assessment") == "below_average",
            json.dumps(benchmark.get("rent_amount")),
        )

        # ---- Selection summary (checkbox-selected rollup, distinct from compare) ----
        print("\n--- Selection summary ---")
        status, summary = _request("GET", f"/leases/selection-summary?ids={commercial_id},{underpriced_id}")
        check("selection-summary returns 200", status == 200, str(status))
        check("selection-summary lease_count is 2", summary.get("lease_count") == 2, json.dumps(summary))

        status, single_summary = _request("GET", f"/leases/selection-summary?ids={commercial_id}")
        check("selection-summary allows a single id (unlike compare)", status == 200, str(status))
        check("single-lease selection-summary lease_count is 1", single_summary.get("lease_count") == 1, json.dumps(single_summary))

        status, err = _request("GET", "/leases/selection-summary?ids=")
        check("selection-summary with no ids returns 400", status == 400, str(status))
        status, err = _request("GET", "/leases/selection-summary?ids=999999")
        check("selection-summary with a nonexistent id returns 404", status == 404, str(status))

        # ---- Exports ----
        print("\n--- Exports ---")
        status, csv_bytes = _request("GET", "/portfolio/rent-roll.csv")
        check("rent roll CSV returns 200", status == 200, str(status))
        csv_text = csv_bytes.decode() if isinstance(csv_bytes, bytes) else csv_bytes
        csv_rows = list(csv.reader(io.StringIO(csv_text)))
        check("rent roll CSV has 11 rows (header + 10 leases)", len(csv_rows) == 11, str(len(csv_rows)))

        status, excel_bytes = _request("GET", "/portfolio/rent-roll.xlsx")
        check("rent roll Excel returns 200", status == 200, str(status))
        check("rent roll Excel has substantial content", isinstance(excel_bytes, bytes) and len(excel_bytes) > 1000, str(len(excel_bytes) if isinstance(excel_bytes, bytes) else 'n/a'))

        # ---- Single-lease Excel export (distinct route from the portfolio-wide one above) ----
        print("\n--- Single-lease export ---")
        status, single_excel_bytes = _request("GET", f"/leases/{commercial_id}/export.xlsx")
        check("single-lease Excel export returns 200", status == 200, str(status))
        check(
            "single-lease Excel export is a real xlsx (zip signature)",
            isinstance(single_excel_bytes, bytes) and single_excel_bytes[:2] == b"PK",
            str(single_excel_bytes[:20] if isinstance(single_excel_bytes, bytes) else single_excel_bytes),
        )
        import openpyxl as _openpyxl
        _single_wb = _openpyxl.load_workbook(io.BytesIO(single_excel_bytes))
        _single_sheet = _single_wb.active
        check(
            "single-lease Excel export has exactly 1 header + 1 data row",
            _single_sheet.max_row == 2,
            f"got {_single_sheet.max_row} rows",
        )
        check(
            "single-lease Excel export's row matches the requested lease's filename",
            _single_sheet.cell(row=2, column=1).value == "sample_lease_commercial.pdf",
            str(_single_sheet.cell(row=2, column=1).value),
        )

        status, err = _request("GET", "/leases/999999/export.xlsx")
        check("single-lease Excel export for nonexistent lease returns 404", status == 404, str(status))

        status, report_html = _request("GET", "/portfolio/report")
        check("portfolio report returns 200", status == 200, str(status))
        report_text = report_html.decode() if isinstance(report_html, bytes) else report_html
        check("report contains lease filenames", all(name in report_text for name in ALL_FIXTURES))

        # ---- Error paths ----
        print("\n--- Error paths ---")
        status, err = _request("GET", "/leases/999999")
        check("nonexistent lease returns 404", status == 404, str(status))
        status, err = _request("DELETE", "/leases/999999")
        check("deleting nonexistent lease returns 404", status == 404, str(status))
        status, err = _request("GET", "/leases/999999/risks")
        check("risks for nonexistent lease returns 404", status == 404, str(status))
        status, err = _request("GET", "/leases/999999/benchmark")
        check("benchmark for nonexistent lease returns 404", status == 404, str(status))
        status, err = _request("POST", "/qa", json_body={})
        check("qa with no question returns 400", status == 400, str(status))

        os.remove(corrupted_path)

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
