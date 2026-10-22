"""
Reproduces what happens to large / unusual uploads on the CURRENT pipeline
and prints a diagnosis per scenario: HTTP status, wall time, memory, and
what was lost. Not part of run_all_tests.py -- it is a measuring tool, not
a pass/fail test (the regression tests live in test_large_files.py). Its
output is saved in docs/plans/large-files-repro.txt.

The Anthropic API is never called: the AI scenario uses a fake client that
records the prompt it would have been sent.

Usage: python backend/tests/repro_large_files.py
"""
import io
import os
import resource
import sys
import tempfile
import time
import tracemalloc
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("LEASE_EXTRACTION_ENGINE", "regex")
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ.pop("ADMIN_EMAIL", None)
os.environ.pop("ADMIN_PASSWORD_HASH", None)

from create_large_fixtures import (  # noqa: E402
    RENT_ROLL_CSV, RENT_ROLL_XLSX, SCANNED_LEASE, TEXT_LEASE, ensure_large_fixtures, load_expected, path_of,
)
from _session_users import sync_session_user  # noqa: E402

from app import ai_extraction, database  # noqa: E402
from app.api import app  # noqa: E402

GUNICORN_TIMEOUT_S = 120  # backend/start.sh


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    database.create_user("a@example.com", "A", "x", role="analyst")
    return tmp.name


def _client():
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"user_id": 1, "email": "a@example.com", "name": "A", "role": "analyst", "team_id": 1})
        sync_session_user(s)
    return c


def _maxrss_mb():
    # macOS reports bytes, Linux kilobytes.
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024


def _post(client, route, path, filename=None, extra=None):
    with open(path, "rb") as f:
        body = f.read()
    data = {"file": (io.BytesIO(body), filename or os.path.basename(path))}
    data.update(extra or {})
    started = time.perf_counter()
    resp = client.post(route, data=data, content_type="multipart/form-data")
    return resp, time.perf_counter() - started


def _subset_pdf(src, pages, dest):
    import pypdf
    reader, writer = pypdf.PdfReader(src), pypdf.PdfWriter()
    for i in range(pages):
        writer.add_page(reader.pages[i])
    with open(dest, "wb") as f:
        writer.write(f)
    return dest


def header(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def scenario_size_limit():
    header("A. 300-page scanned PDF (image-only) uploaded to POST /leases")
    size_mb = os.path.getsize(path_of(SCANNED_LEASE)) / (1024 * 1024)
    resp, secs = _post(_client(), "/leases", path_of(SCANNED_LEASE))
    print(f"file size: {size_mb:.1f} MB; Flask MAX_CONTENT_LENGTH: {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB")
    print(f"-> HTTP {resp.status_code} in {secs:.1f}s: {resp.get_json()}")
    print("   Also: frontend/app/upload-view.js drops any file over 16 MB before it is ever sent.")


def scenario_scanned_ocr_in_request():
    header("B. OCR runs inside the web request and rasterizes every page at once")
    pages = 12
    sub = _subset_pdf(path_of(SCANNED_LEASE), pages, os.path.join(tempfile.mkdtemp(), "scanned_subset.pdf"))
    size_mb = os.path.getsize(sub) / (1024 * 1024)
    from pdf2image import convert_from_path
    calls = []
    real = convert_from_path

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    rss_before = _maxrss_mb()
    with mock.patch("app.pdf_extractor.convert_from_path", side_effect=spy):
        resp, secs = _post(_client(), "/leases", sub)
    rss_after = _maxrss_mb()
    body = resp.get_json() or {}
    lease = (body.get("leases") or [{}])[0]
    tenant = ((lease.get("extracted_fields") or {}).get("tenant") or {}).get("value")
    print(f"{pages}-page subset ({size_mb:.1f} MB) -> HTTP {resp.status_code} in {secs:.1f}s, all of it inside the request")
    print(f"   convert_from_path called {len(calls)}x with kwargs {calls} (no first_page/last_page: whole document at once)")
    print(f"   peak RSS grew {rss_before:.0f} -> {rss_after:.0f} MB for {pages} pages")
    per_page_s = secs / pages
    print(f"   tenant found: {tenant!r}")
    print(f"   projected for 300 pages: ~{per_page_s * 300:.0f}s (gunicorn kills the worker at {GUNICORN_TIMEOUT_S}s)")
    width, height = int(8.5 * 200), int(11 * 200)
    print(f"   projected raster memory for 300 pages at pdf2image's default 200 DPI RGB: "
          f"{300 * width * height * 3 / (1024 ** 3):.1f} GB held at once (Render starter = 512 MB RAM)")


def scenario_text_lease_regex():
    header("C. 500-page text lease, regex engine (the default), POST /leases")
    expected = load_expected()["text_lease"]
    tracemalloc.start()
    resp, secs = _post(_client(), "/leases", path_of(TEXT_LEASE))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    body = resp.get_json() or {}
    leases = body.get("leases") or []
    print(f"-> HTTP {resp.status_code} in {secs:.1f}s; split into {len(leases)} lease(s); Python peak alloc {peak / 1e6:.0f} MB")
    print(f"   usage limit MAX_PAGES_PER_FILE = 150, but a {expected['pages']}-page file was accepted "
          f"(usage_limits.check_file_limits passes temp_path=None -> open(None) raises -> swallowed)")
    for lease in leases[:3]:
        f = lease.get("extracted_fields") or {}
        print(f"   pages {lease.get('source_page_start')}-{lease.get('source_page_end')}: tenant={(f.get('tenant') or {}).get('value')!r} "
              f"deposit={(f.get('security_deposit') or {}).get('value')!r} sqft={(f.get('square_footage') or {}).get('value')!r}")


def _pages_of(path):
    from app.document_extractor import extract_pages
    with open(path, "rb") as f:
        body = f.read()
    return extract_pages(body, os.path.basename(path), path)


def scenario_ai_truncation():
    header("D. 500-page text lease, AI engine: what the model is actually sent")
    expected = load_expected()["text_lease"]
    pages = _pages_of(path_of(TEXT_LEASE))
    sent = {}

    class FakeMessages:
        def create(self, **kwargs):
            sent["text"] = kwargs["messages"][0]["content"]
            raise ai_extraction.AIExtractionError("stop after capturing the prompt")

    fake = mock.Mock()
    fake.messages = FakeMessages()
    try:
        ai_extraction.extract_lease_fields(pages, client=fake)
    except ai_extraction.AIExtractionError:
        pass
    text = sent.get("text", "")
    last_page = max(int(m) for m in __import__("re").findall(r"===== PAGE (\d+) =====", text))
    total_chars = sum(len(p["text"] or "") for p in pages)
    print(f"document: {len(pages)} pages, {total_chars:,} chars; prompt sent: {len(text):,} chars, last page included: {last_page}")
    print(f"   truncated: {'DOCUMENT TRUNCATED' in text}")
    for name, page in expected["planted_terms"].items():
        print(f"   {name} (page {page}) sent to the model: {page <= last_page}")


def scenario_rent_roll(path):
    header(f"E. 5,000-row messy rent roll ({os.path.basename(path)}) via POST /leases/import-rent-roll")
    expected = load_expected()["rent_roll"]
    tracemalloc.start()
    resp, secs = _post(_client(), "/leases/import-rent-roll", path, extra={"property_address": "1000 Juniper Row"})
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    body = resp.get_json() or {}
    print(f"-> HTTP {resp.status_code} in {secs:.1f}s (gunicorn limit {GUNICORN_TIMEOUT_S}s); Python peak alloc {peak / 1e6:.0f} MB")
    if resp.status_code == 201:
        skipped = body.get("skipped_rows") or []
        print(f"   imported {body.get('imported_count')} (expected {expected['occupied_rows']} occupied); skipped {len(skipped)} rows")
    else:
        print(f"   error: {body.get('error')}")


def scenario_type_by_extension():
    header("F. File type is decided by extension only")
    tmpdir = tempfile.mkdtemp()
    from PIL import Image
    png = os.path.join(tmpdir, "photo.png")
    Image.new("RGB", (40, 40), "white").save(png)
    cases = [
        ("PNG bytes named lease.pdf", png, "lease.pdf"),
        ("PDF bytes named lease.txt", _subset_pdf(path_of(TEXT_LEASE), 3, os.path.join(tmpdir, "three.pdf")), "lease.txt"),
    ]
    exe = os.path.join(tmpdir, "tool.pdf")
    with open(exe, "wb") as f:
        f.write(b"MZ\x90\x00" + os.urandom(2048))
    cases.append(("Windows executable named tool.pdf", exe, "tool.pdf"))
    heic_note = "HEIC lease photo (iPhone default)"
    for label, path, name in cases:
        resp, _ = _post(_client(), "/leases", path, filename=name)
        body = resp.get_json() or {}
        detail = body.get("error") or f"accepted, {len(body.get('leases') or [])} lease(s) created"
        print(f"   {label}: HTTP {resp.status_code}: {str(detail)[:140]}")
    resp, _ = _post(_client(), "/leases", png, filename="lease.heic")
    print(f"   {heic_note} (.heic): HTTP {resp.status_code}: {(resp.get_json() or {}).get('error')}")


def scenario_memory_copies():
    header("G. The upload is copied into memory several times per request")
    # A ~14 MB upload (just under the 16 MB cap). Extraction itself is
    # stubbed out so the number below is only the cost of receiving and
    # copying the file, not of parsing it.
    sub = _subset_pdf(path_of(SCANNED_LEASE), 35, os.path.join(tempfile.mkdtemp(), "fourteen_mb.pdf"))
    size_mb = os.path.getsize(sub) / 1e6
    from app.document_extractor import DocumentExtractionError
    with open(sub, "rb") as f:
        body = f.read()
    client = _client()
    with mock.patch("app.document_extractor.extract_pages", side_effect=DocumentExtractionError("stub")), \
         mock.patch("app.usage_limits.check_file_limits", return_value=None):
        tracemalloc.start()
        client.post("/leases", data={"file": (io.BytesIO(body), "fourteen_mb.pdf")}, content_type="multipart/form-data")
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    print(f"   {size_mb:.1f} MB upload -> {peak / 1e6:.0f} MB peak Python allocation just to receive it "
          f"({peak / 1e6 / size_mb:.1f}x the file): read() in _validate_upload, again in upload_lease, "
          f"and again from the temp file in _extract_leases_from_file_storage")


def main():
    ensure_large_fixtures()
    db = _fresh_db()
    try:
        scenario_size_limit()
        scenario_scanned_ocr_in_request()
        scenario_text_lease_regex()
        scenario_ai_truncation()
        scenario_rent_roll(path_of(RENT_ROLL_XLSX))
        scenario_rent_roll(path_of(RENT_ROLL_CSV))
        scenario_type_by_extension()
        scenario_memory_copies()
    finally:
        os.unlink(db)


if __name__ == "__main__":
    main()
