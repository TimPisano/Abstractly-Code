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


if __name__ == "__main__":
    test_post_leases_refuses_an_excel_entity_bomb()
    test_post_leases_batch_refuses_an_excel_entity_bomb()
    test_import_rent_roll_refuses_an_excel_entity_bomb()
    test_every_excel_reader_refuses_entities_instead_of_expanding_them()
    test_real_excel_uploads_still_import()
    print("\nAll upload hardening tests passed!")
