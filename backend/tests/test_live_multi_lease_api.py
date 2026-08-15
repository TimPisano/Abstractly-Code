"""
Live API regression test for the multi-lease-PDF rejection added to
_extract_fields_from_file_storage in api.py — confirms /extract,
/leases, and /leases/batch all reject a real merged multi-lease PDF
with a clear 400 (never persisting a mixed-data record), while a normal
single-lease upload is unaffected.

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


def _build_merged_pdf():
    writer = PdfWriter()
    for filename in ("retail_lease.pdf", "office_lease.pdf"):
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

    merged_pdf_bytes = _build_merged_pdf()
    created_lease_ids = []

    try:
        clear_all_leases()

        # ---- /extract (stateless) ----
        body, content_type = _multipart_body([("file", "merged.pdf", merged_pdf_bytes)])
        status, resp = _request("POST", "/extract", data=body, headers={"Content-Type": content_type})
        check("/extract rejects a merged multi-lease PDF with 400", status == 400, str(status))
        check("/extract error message names the field that triggered it", isinstance(resp, dict) and "more than one lease" in resp.get("error", ""), str(resp))

        # ---- POST /leases (persisted single upload) ----
        body, content_type = _multipart_body([("file", "merged.pdf", merged_pdf_bytes)])
        status, resp = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
        check("POST /leases rejects a merged multi-lease PDF with 400", status == 400, str(status))

        status, leases = _request("GET", "/leases")
        check("rejected merged PDF was never persisted", status == 200 and leases == [], f"{len(leases) if isinstance(leases, list) else leases} leases found")

        # ---- POST /leases/batch (one good file + one merged file) ----
        with open(os.path.join(FIXTURES_DIR, "sample_lease.pdf"), "rb") as f:
            good_bytes = f.read()
        body, content_type = _multipart_body([
            ("files", "sample_lease.pdf", good_bytes),
            ("files", "merged.pdf", merged_pdf_bytes),
        ])
        status, resp = _request("POST", "/leases/batch", data=body, headers={"Content-Type": content_type})
        check("batch upload with one good + one merged file returns 200 overall", status == 200, str(status))
        check("batch reports 1 succeeded, 1 failed", isinstance(resp, dict) and resp.get("succeeded") == 1 and resp.get("failed") == 1, str(resp))
        merged_result = next((r for r in resp.get("results", []) if r["filename"] == "merged.pdf"), None)
        check("the merged file's batch result carries the clear rejection message", merged_result is not None and "more than one lease" in merged_result.get("error", ""), str(merged_result))
        good_result = next((r for r in resp.get("results", []) if r["filename"] == "sample_lease.pdf"), None)
        check("the good file in the same batch still succeeded", good_result is not None and good_result.get("success") is True, str(good_result))
        if good_result and good_result.get("success"):
            created_lease_ids.append(good_result["lease"]["id"])

        # ---- Sanity: a normal single-lease upload is completely unaffected ----
        with open(os.path.join(FIXTURES_DIR, "office_lease.pdf"), "rb") as f:
            office_bytes = f.read()
        body, content_type = _multipart_body([("file", "office_lease.pdf", office_bytes)])
        status, resp = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
        check("a normal single-lease upload still succeeds", status == 201, str(status))
        if status == 201:
            created_lease_ids.append(resp["id"])
            check("its tenant field extracted correctly", resp["extracted_fields"]["tenant"]["value"] == "Vertex Analytics LLC", str(resp["extracted_fields"]["tenant"]))

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
