"""
Live API regression test for multi-lease PDF splitting — confirms
/extract, /leases, and /leases/batch all correctly split a real merged
multi-lease PDF into individually-accurate lease records (never a
single merged/mixed record, and never a rejection — that was an earlier
iteration of this fix; see DECISIONS.md), with a normal single-lease
upload completely unaffected.

Requires the backend already running at API_BASE_URL. Builds the merged
PDF at runtime from this repo's own real fixture PDFs via PyPDF2 — a
real merged document, not synthetic text.
"""
import os
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyPDF2 import PdfReader, PdfWriter

API_BASE_URL = "http://localhost:5000"
FIXTURES_DIR = os.path.dirname(__file__)


def _request(method, path, data=None, headers=None):
    req = urllib.request.Request(f"{API_BASE_URL}{path}", data=data, headers=headers or {}, method=method)
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
    boundary = "----MultiLeaseApiTestBoundary"
    parts = []
    for field_name, filename, content in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _merged_pdf_bytes(*filenames):
    writer = PdfWriter()
    for filename in filenames:
        reader = PdfReader(os.path.join(FIXTURES_DIR, filename))
        for page in reader.pages:
            writer.add_page(page)
    merged_path = "/tmp/test_live_merge.pdf"
    with open(merged_path, "wb") as f:
        writer.write(f)
    with open(merged_path, "rb") as f:
        content = f.read()
    os.unlink(merged_path)
    return content


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

    status, health = _request("GET", "/health")
    check("server is reachable", status == 200 and health.get("status") == "healthy")

    merged_two = _merged_pdf_bytes("retail_lease.pdf", "office_lease.pdf")
    created_lease_ids = []

    try:
        clear_all_leases()

        # ---- /extract (stateless): must return a list, split correctly ----
        body, content_type = _multipart_body([("file", "merged.pdf", merged_two)])
        status, resp = _request("POST", "/extract", data=body, headers={"Content-Type": content_type})
        check("/extract on a merged PDF returns 200 (not a rejection)", status == 200, str(status))
        check("/extract returns a 'leases' list with 2 entries", isinstance(resp, dict) and len(resp.get("leases", [])) == 2, str(resp))
        if isinstance(resp, dict) and len(resp.get("leases", [])) == 2:
            tenants = {r["fields"]["tenant"]["value"] for r in resp["leases"]}
            check("/extract's 2 leases have the correct, distinct tenants", tenants == {"Cascade Apparel Co.", "Vertex Analytics LLC"}, str(tenants))
        check("/extract did not persist anything (still stateless)", _request("GET", "/leases")[1] == [])

        # ---- POST /leases (persisted): splits into 2 separate lease rows ----
        body, content_type = _multipart_body([("file", "merged.pdf", merged_two)])
        status, resp = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
        check("POST /leases on a merged PDF returns 201", status == 201, str(status))
        check("split_count is 2", resp.get("split_count") == 2, str(resp))
        check("response carries a 'leases' list with 2 entries", len(resp.get("leases", [])) == 2, str(resp))

        if len(resp.get("leases", [])) == 2:
            for lease in resp["leases"]:
                created_lease_ids.append(lease["id"])
            by_tenant = {l["extracted_fields"]["tenant"]["value"]: l for l in resp["leases"]}
            check("both distinct tenants are present as separate leases", set(by_tenant) == {"Cascade Apparel Co.", "Vertex Analytics LLC"}, str(set(by_tenant)))

            retail = by_tenant.get("Cascade Apparel Co.")
            office = by_tenant.get("Vertex Analytics LLC")
            if retail and office:
                check("split lease #1 has its OWN rent, not the other lease's", retail["extracted_fields"]["rent_amount"]["value"] == "$6,000.00", retail["extracted_fields"]["rent_amount"]["value"])
                check("split lease #2 has its OWN rent, not the other lease's", office["extracted_fields"]["rent_amount"]["value"] == "$9,500.00", office["extracted_fields"]["rent_amount"]["value"])
                check("split lease #1 has its own auto-generated display_name", "Cascade Apparel Co." in retail["display_name"] and "Riverside Plaza" in retail["display_name"], retail["display_name"])
                check("split lease #2 has its own auto-generated display_name", "Vertex Analytics LLC" in office["display_name"] and "Wilshire" in office["display_name"], office["display_name"])
                check("split leases record distinct, non-overlapping source page ranges", retail["source_page_start"] != office["source_page_start"], f"{retail['source_page_start']} vs {office['source_page_start']}")

        # ---- Each split lease is independently persisted and independently queryable ----
        status, all_leases = _request("GET", "/leases")
        check("both split leases are independently listed", status == 200 and len(all_leases) == 2, str(len(all_leases) if isinstance(all_leases, list) else all_leases))

        if len(created_lease_ids) == 2:
            for lease_id in created_lease_ids:
                status, risks = _request("GET", f"/leases/{lease_id}/risks")
                date_conflict_flags = [f for f in risks if f.get("category") == "date_inconsistency"] if isinstance(risks, list) else None
                check(
                    f"lease {lease_id} has no spurious date-conflict flag (the original bug: 30+ smeared dates)",
                    date_conflict_flags == [],
                    str(date_conflict_flags),
                )

        # ---- POST /leases/batch: one good single-lease file + one merged (2-lease) file ----
        clear_all_leases()
        created_lease_ids.clear()

        with open(os.path.join(FIXTURES_DIR, "sample_lease.pdf"), "rb") as f:
            good_bytes = f.read()
        merged_three = _merged_pdf_bytes("retail_lease.pdf", "office_lease.pdf", "sample_lease_commercial.pdf")
        body, content_type = _multipart_body([
            ("files", "sample_lease.pdf", good_bytes),
            ("files", "merged3.pdf", merged_three),
        ])
        status, resp = _request("POST", "/leases/batch", data=body, headers={"Content-Type": content_type})
        check("batch upload with one single-lease + one 3-lease-merged file returns 200", status == 200, str(status))
        check("batch reports 2 files succeeded (both files processed, no rejection)", resp.get("succeeded") == 2, str(resp))
        check("batch reports total_leases_created == 4 (1 + 3)", resp.get("total_leases_created") == 4, str(resp))

        merged_result = next((r for r in resp.get("results", []) if r["filename"] == "merged3.pdf"), None)
        check("the merged file's batch result split into 3 leases", merged_result is not None and merged_result.get("split_count") == 3, str(merged_result))
        good_result = next((r for r in resp.get("results", []) if r["filename"] == "sample_lease.pdf"), None)
        check("the single-lease file's batch result split into 1 lease", good_result is not None and good_result.get("split_count") == 1, str(good_result))

        for r in resp.get("results", []):
            if r.get("success"):
                created_lease_ids.extend(l["id"] for l in r["leases"])

        status, all_leases = _request("GET", "/leases")
        check("dashboard-level GET /leases reflects all 4 individual leases", status == 200 and len(all_leases) == 4, str(len(all_leases) if isinstance(all_leases, list) else all_leases))

        status, summary = _request("GET", "/portfolio/summary")
        check("portfolio summary lease_count reflects individual (post-split) leases, not the 2 uploaded files", summary.get("lease_count") == 4, str(summary))

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
