"""
Upload hardening (fix/upload-hardening): the security re-audit's open
items on the upload routes, one regression test per fix.

1. No route accepts an Office file whose XML declares entities ("billion
   laughs"). POST /uploads already refused them (file_types._declares_dtd);
   POST /leases and POST /leases/import-rent-roll parsed them with
   openpyxl, whose stdlib XML parser expanded every entity.

The bombs here nest only 5 levels (~300 KB once expanded) so a run
without the fix stays cheap; a real attack nests 9+ levels (~2.5 GB).
"""
import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import io
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _session_users import sync_session_user  # noqa: E402

from app import database, usage_limits  # noqa: E402
from app.api import app  # noqa: E402

BOMB_LEVELS = 5
BOMB_MESSAGE = "save a fresh copy"


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    usage_limits._reset_extraction_rate_limit_for_tests()
    return tmp.name


def _client(user_id=1, team_id=1, role="analyst"):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"user_id": user_id, "email": f"u{user_id}@example.com", "name": f"U{user_id}", "role": role,
                  "team_id": team_id})
        sync_session_user(s)
    return c


def _xlsx_with_sheet(sheet_xml):
    """A real openpyxl workbook whose first sheet is replaced by `sheet_xml`."""
    import openpyxl
    buf = io.BytesIO()
    openpyxl.Workbook().save(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            body = sheet_xml.encode() if item.filename == "xl/worksheets/sheet1.xml" else src.read(item.filename)
            dst.writestr(item.filename, body)
    return out.getvalue()


def _cell(ref, text):
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _rent_roll_bomb(levels=BOMB_LEVELS):
    """A one-tenant rent roll whose tenant name is an entity that expands to 3 * 10**levels characters."""
    entities = '<!ENTITY l0 "lol">' + "".join(f'<!ENTITY l{i} "{("&l%d;" % (i - 1)) * 10}">' for i in range(1, levels + 1))
    rows = [
        ("1", ["Unit", "Tenant", "Monthly Rent", "Lease Start", "Lease End"]),
        ("2", ["101", f"&l{levels};", "2500", "2024-01-01", "2026-12-31"]),
    ]
    sheet_rows = "".join(
        f'<row r="{r}">' + "".join(_cell(f"{chr(65 + i)}{r}", v) for i, v in enumerate(values)) + "</row>"
        for r, values in rows
    )
    return _xlsx_with_sheet(
        f'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE worksheet [{entities}]>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{sheet_rows}</sheetData></worksheet>"
    )


def _team_lease_count(team_id=1):
    conn = database.get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM leases WHERE team_id = ?", (team_id,)).fetchone()[0]
    finally:
        conn.close()


def _assert_refused(resp, route):
    body = resp.get_json() or {}
    assert resp.status_code == 400, f"{route}: {resp.status_code} {str(body)[:300]}"
    assert BOMB_MESSAGE in (body.get("error") or "").lower(), f"{route}: {body!r}"


# ---------------------------------------------------------------------------
# Fix 1: the Excel entity bomb on the routes that read uploads in memory


def test_post_leases_refuses_an_excel_entity_bomb():
    db = _fresh_db()
    try:
        resp = _client().post("/leases", data={"file": (io.BytesIO(_rent_roll_bomb()), "lease.xlsx")},
                              content_type="multipart/form-data")
        _assert_refused(resp, "POST /leases")
        assert _team_lease_count() == 0, "nothing saved"
    finally:
        os.unlink(db)
    print("✓ test_post_leases_refuses_an_excel_entity_bomb: PASS")


def test_post_leases_batch_refuses_an_excel_entity_bomb():
    db = _fresh_db()
    try:
        resp = _client().post("/leases/batch", data={"files": [(io.BytesIO(_rent_roll_bomb()), "lease.xlsx")]},
                              content_type="multipart/form-data")
        body = resp.get_json() or {}
        errors = " ".join(str(r.get("error") or "") for r in body.get("results", []) if isinstance(r, dict))
        assert BOMB_MESSAGE in (errors or str(body)).lower(), f"POST /leases/batch: {resp.status_code} {str(body)[:300]}"
        assert _team_lease_count() == 0, "nothing saved"
    finally:
        os.unlink(db)
    print("✓ test_post_leases_batch_refuses_an_excel_entity_bomb: PASS")


def test_import_rent_roll_refuses_an_excel_entity_bomb():
    db = _fresh_db()
    try:
        resp = _client().post("/leases/import-rent-roll",
                              data={"file": (io.BytesIO(_rent_roll_bomb()), "roll.xlsx")},
                              content_type="multipart/form-data")
        _assert_refused(resp, "POST /leases/import-rent-roll")
        assert _team_lease_count() == 0, "nothing imported"
    finally:
        os.unlink(db)
    print("✓ test_import_rent_roll_refuses_an_excel_entity_bomb: PASS")


def test_every_excel_reader_refuses_entities_instead_of_expanding_them():
    """
    Backstop for every other route that reads Excel (T-12 reconciliation,
    the deal mismatch reports, the table path inside POST /leases):
    openpyxl must parse with defusedxml, so a bomb that reaches a parser
    raises instead of expanding.
    """
    import openpyxl
    from app import document_extractor, rent_roll_import, t12_import
    bomb = _rent_roll_bomb()
    expanded = "lol" * 10 ** BOMB_LEVELS
    readers = {
        "rent_roll_import.parse_xlsx_rent_roll": lambda: rent_roll_import.parse_xlsx_rent_roll(bomb, "roll.xlsx"),
        "document_extractor.extract_pages": lambda: document_extractor.extract_pages(bomb, "lease.xlsx", None),
        "t12_import.load_workbook_sheets": lambda: t12_import.load_workbook_sheets(bomb),
    }
    for name, read in readers.items():
        try:
            result = read()
        except Exception:
            continue  # refused: what we want (each route maps its own parser errors)
        raise AssertionError(f"{name} parsed the bomb (expanded: {expanded in repr(result)}; "
                             f"openpyxl.DEFUSEDXML={openpyxl.DEFUSEDXML}, pip install -r backend/requirements.txt)")
    print("✓ test_every_excel_reader_refuses_entities_instead_of_expanding_them: PASS")


def test_real_excel_uploads_still_import():
    import openpyxl
    db = _fresh_db()
    try:
        wb = openpyxl.Workbook()
        wb.active.append(["Unit", "Tenant", "Monthly Rent", "Lease Start", "Lease End"])
        wb.active.append(["101", "Example Tenant LLC", 2500, "2024-01-01", "2026-12-31"])
        buf = io.BytesIO()
        wb.save(buf)
        resp = _client().post("/leases/import-rent-roll", data={"file": (io.BytesIO(buf.getvalue()), "roll.xlsx")},
                              content_type="multipart/form-data")
        assert resp.status_code == 201, (resp.status_code, resp.get_json())
        assert _team_lease_count() == 1
    finally:
        os.unlink(db)
    print("✓ test_real_excel_uploads_still_import: PASS")


# ---------------------------------------------------------------------------
# Fix 2: time limits on reading a PDF in the background pipeline


def _pdf(path, pages_text):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path)
    for text in pages_text:
        if text:
            c.drawString(72, 720, text)
        c.showPage()
    c.save()
    return path


def test_a_hung_pdf_renderer_is_stopped_at_its_time_limit():
    """
    Security re-audit: rendering a page for OCR had no time limit, so a
    crafted PDF that hangs poppler held the single worker for up to the
    3-hour job timeout. A stand-in pdftoppm that never finishes must be
    stopped at the per-page limit; that page just comes back without text.
    """
    import time
    from unittest import mock
    from app import document_extractor

    tmpdir = tempfile.mkdtemp()
    fake_bin = os.path.join(tmpdir, "bin")
    os.mkdir(fake_bin)
    for tool in ("pdftoppm", "pdfinfo", "pdftocairo"):
        with open(os.path.join(fake_bin, tool), "w") as f:
            f.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(os.path.join(fake_bin, tool), 0o755)
    scan = _pdf(os.path.join(tmpdir, "scan.pdf"), [""])  # no text layer, so it's sent to OCR
    try:
        with mock.patch.dict(os.environ, {"PATH": fake_bin + os.pathsep + os.environ["PATH"]}), \
                mock.patch.object(document_extractor, "_PDF_RASTERIZE_TIMEOUT_S", 1, create=True):
            started = time.monotonic()
            pages = document_extractor.extract_pages_from_path(scan, "pdf")
            elapsed = time.monotonic() - started
        assert elapsed < 10, f"a hung renderer held the reader for {elapsed:.0f} s"
        assert [p["page"] for p in pages] == [1] and not pages[0]["text"].strip()
    finally:
        import shutil
        shutil.rmtree(tmpdir)
    print("✓ test_a_hung_pdf_renderer_is_stopped_at_its_time_limit: PASS")


def test_pdf_reading_stops_at_the_overall_time_limit():
    """A PDF that takes longer than the read limit in all is stopped with a message saying so, not read for hours."""
    from unittest import mock
    from app import document_extractor
    from app.document_extractor import DocumentExtractionError

    tmpdir = tempfile.mkdtemp()
    lease = _pdf(os.path.join(tmpdir, "lease.pdf"), [f"Page {n}: Tenant shall pay rent monthly." for n in range(1, 4)])
    try:
        with mock.patch.object(document_extractor, "PDF_READ_LIMIT_SECONDS", 0, create=True):
            try:
                pages = document_extractor.extract_pages_from_path(lease, "pdf")
            except DocumentExtractionError as e:
                assert "took longer than" in str(e), e
            else:
                raise AssertionError(f"read all {len(pages)} pages past the time limit")
        assert len(document_extractor.extract_pages_from_path(lease, "pdf")) == 3, "a normal PDF still reads"
    finally:
        import shutil
        shutil.rmtree(tmpdir)
    print("✓ test_pdf_reading_stops_at_the_overall_time_limit: PASS")


# ---------------------------------------------------------------------------
# Fixes 3-4: POST /uploads (LARGE_FILE_UPLOADS on)

LEASE_TEXT = b"Lease between Example Landlord LLC and Example Tenant Inc. Base Rent of $2,500.00 per month.\n" * 20


def _large_uploads_on():
    """LARGE_FILE_UPLOADS on (read per request) with a throwaway upload dir; jobs are recorded, never run."""
    from unittest import mock
    from app import upload_jobs
    upload_dir = tempfile.mkdtemp(prefix="abstractly-test-uploads-")
    patches = [
        mock.patch.dict(os.environ, {"LARGE_FILE_UPLOADS": "true", "LARGE_FILE_UPLOAD_DIR": upload_dir}),
        mock.patch.object(upload_jobs, "start_job", lambda job_id: None),
    ]
    for p in patches:
        p.start()
    return upload_dir, patches


def _post_upload(client, n=0, kind="lease"):
    body = LEASE_TEXT + f"Copy {n}\n".encode()  # distinct content: no duplicate-upload short cut
    return client.post("/uploads", data={"file": (io.BytesIO(body), f"lease{n}.txt"), "kind": kind},
                       content_type="multipart/form-data")


def _active_jobs(team_id=1):
    return database.count_active_upload_jobs(team_id)


def test_simultaneous_uploads_cannot_pass_the_active_job_cap():
    """
    Security re-audit: the 3-active-jobs cap was count-then-insert, so
    uploads that arrived together all saw room and all queued. Both
    requests passing the early count (as two simultaneous requests do)
    must still leave the team at the cap.
    """
    from unittest import mock
    from app import upload_jobs
    db = _fresh_db()
    upload_dir, patches = _large_uploads_on()
    try:
        client = _client()
        for n in range(upload_jobs.MAX_ACTIVE_JOBS_PER_TEAM):
            assert _post_upload(client, n).status_code == 202
        assert _active_jobs() == upload_jobs.MAX_ACTIVE_JOBS_PER_TEAM

        # Both requests checked the count before either one's job existed.
        with mock.patch.object(database, "count_active_upload_jobs", return_value=0):
            resp = _post_upload(client, 99)
        assert resp.status_code == 429, (resp.status_code, resp.get_json())
        assert "uploads processing" in resp.get_json()["error"]
        assert _active_jobs() == upload_jobs.MAX_ACTIVE_JOBS_PER_TEAM, "a job past the cap was queued"
        assert len([n for n in os.listdir(upload_dir) if n.endswith(".upload")]) == upload_jobs.MAX_ACTIVE_JOBS_PER_TEAM, \
            "the refused upload's file was left behind"
        # Another team has its own cap.
        assert _post_upload(_client(user_id=2, team_id=2), 100).status_code == 202
    finally:
        for p in patches:
            p.stop()
        os.unlink(db)
    print("✓ test_simultaneous_uploads_cannot_pass_the_active_job_cap: PASS")


def test_concurrent_job_creation_holds_the_cap_exactly():
    """Eight threads creating jobs at the same moment, cap 3: exactly three rows."""
    import threading
    db = _fresh_db()
    try:
        _client()  # creates user 1 / team 1
        barrier = threading.Barrier(8)
        created, errors = [], []

        def create(n):
            barrier.wait()
            try:
                created.append(database.create_upload_job(1, 1, "lease", f"l{n}.txt", f"/nowhere/{n}", 1, f"h{n}",
                                                          "txt", max_active=3))
            except Exception as e:  # noqa: BLE001 -- reported below
                errors.append(repr(e))

        threads = [threading.Thread(target=create, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert len([c for c in created if c is not None]) == 3, created
        assert _active_jobs() == 3
    finally:
        os.unlink(db)
    print("✓ test_concurrent_job_creation_holds_the_cap_exactly: PASS")


def test_rent_roll_uploads_are_rate_limited_like_leases():
    """Security re-audit: POST /uploads rate-limited lease uploads only; rent rolls could be sent without limit."""
    from unittest import mock
    from app import upload_jobs
    db = _fresh_db()
    upload_dir, patches = _large_uploads_on()
    try:
        client = _client()
        limit = usage_limits.EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE
        with mock.patch.object(upload_jobs, "MAX_ACTIVE_JOBS_PER_TEAM", limit + 10):
            statuses = [_post_upload(client, n, kind="rent_roll").status_code for n in range(limit)]
            assert statuses == [202] * limit, statuses
            stored = len(os.listdir(upload_dir))
            resp = _post_upload(client, limit, kind="rent_roll")
            assert resp.status_code == 429, (resp.status_code, resp.get_json())
            assert "Rate limit exceeded" in resp.get_json()["error"]
            assert len(os.listdir(upload_dir)) == stored, "a rate-limited upload was still saved"
            # Per user: a teammate isn't held up.
            assert _post_upload(_client(user_id=2, team_id=1), 999, kind="rent_roll").status_code == 202
    finally:
        for p in patches:
            p.stop()
        os.unlink(db)
    print("✓ test_rent_roll_uploads_are_rate_limited_like_leases: PASS")


def test_refused_uploads_are_refused_before_the_body_is_read():
    """
    Security re-audit: a rate-limited (or capped) request still had its
    whole body, up to 150 MB, received and spooled to disk before being
    refused. Those checks now run before the form is parsed at all.
    """
    from unittest import mock
    from app import upload_jobs
    db = _fresh_db()
    upload_dir, patches = _large_uploads_on()
    body_read = mock.PropertyMock(side_effect=AssertionError("request body parsed before the refusal"))
    try:
        client = _client()
        with mock.patch.object(usage_limits, "_extraction_rate_limited", return_value=True), \
                mock.patch.object(app.request_class, "form", body_read, create=True), \
                mock.patch.object(app.request_class, "files", body_read, create=True):
            for kind in ("lease", "rent_roll"):
                resp = _post_upload(client, 1, kind=kind)
                assert resp.status_code == 429, (kind, resp.status_code, resp.get_json())
        with mock.patch.object(database, "count_active_upload_jobs", return_value=upload_jobs.MAX_ACTIVE_JOBS_PER_TEAM), \
                mock.patch.object(app.request_class, "form", body_read, create=True), \
                mock.patch.object(app.request_class, "files", body_read, create=True):
            resp = _post_upload(client, 2)
            assert resp.status_code == 429 and "uploads processing" in resp.get_json()["error"], resp.get_json()
        assert not os.listdir(upload_dir)
    finally:
        for p in patches:
            p.stop()
        os.unlink(db)
    print("✓ test_refused_uploads_are_refused_before_the_body_is_read: PASS")


if __name__ == "__main__":
    test_post_leases_refuses_an_excel_entity_bomb()
    test_post_leases_batch_refuses_an_excel_entity_bomb()
    test_import_rent_roll_refuses_an_excel_entity_bomb()
    test_every_excel_reader_refuses_entities_instead_of_expanding_them()
    test_real_excel_uploads_still_import()
    test_a_hung_pdf_renderer_is_stopped_at_its_time_limit()
    test_pdf_reading_stops_at_the_overall_time_limit()
    test_simultaneous_uploads_cannot_pass_the_active_job_cap()
    test_concurrent_job_creation_holds_the_cap_exactly()
    test_rent_roll_uploads_are_rate_limited_like_leases()
    test_refused_uploads_are_refused_before_the_body_is_read()
    print("\nAll upload hardening tests passed!")
