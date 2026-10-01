"""
Server-side upload validation coverage: file type, size, and
attacker-controlled filename handling must be enforced by the API, not
just the UI.
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    # a real base lease so /leases/<id>/amendments reaches file validation
    # instead of 404-ing on a missing lease
    lid = database.insert_lease("base.pdf", {n: {"value": None, "source": None, "confidence": None} for n in FIELD_NAMES})
    return tmp.name, lid


def _analyst():
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"user_id": 1, "email": "a@x.com", "name": "A", "role": "analyst", "team_id": 1})
    return c


def _post_file(client, path, filename, data=b"hello", field="file"):
    return client.post(path, data={field: (io.BytesIO(data), filename)}, content_type="multipart/form-data")


def _single_file_routes(base_id):
    return ["/extract", "/leases", f"/leases/{base_id}/amendments"]


# ----------------------------------------------------------------------

def test_missing_file_is_400_on_every_upload_route():
    db, base_id = _fresh_temp_db()
    try:
        c = _analyst()
        for path in _single_file_routes(base_id) + ["/leases/import-rent-roll"]:
            r = c.post(path, data={}, content_type="multipart/form-data")
            assert r.status_code == 400, f"{path} -> {r.status_code}"
        assert c.post("/leases/batch", data={}, content_type="multipart/form-data").status_code == 400
    finally:
        os.unlink(db)
    print("✓ test_missing_file_is_400_on_every_upload_route: PASS")


def test_disallowed_extension_is_rejected_server_side():
    db, base_id = _fresh_temp_db()
    try:
        c = _analyst()
        for path in _single_file_routes(base_id):
            for bad in ("payload.exe", "archive.zip", "script.sh", "noext"):
                r = _post_file(c, path, bad)
                assert r.status_code == 400, f"{path} accepted {bad!r} -> {r.status_code}"
        assert _post_file(c, "/leases/import-rent-roll", "roll.pdf").status_code == 400
        r = c.post("/portfolio/t12-reconciliation",
                   data={"file": (io.BytesIO(b"x"), "t12.pdf"), "property_address": "1 Main St"},
                   content_type="multipart/form-data")
        assert r.status_code == 400
    finally:
        os.unlink(db)
    print("✓ test_disallowed_extension_is_rejected_server_side: PASS")


def test_crafted_traversal_filename_never_500s_or_escapes_tmp():
    db, base_id = _fresh_temp_db()
    try:
        c = _analyst()
        tmp_root = tempfile.gettempdir()
        before = set(os.listdir(tmp_root))
        for name in ("../../../../etc/passwd.pdf", "x.pdf/../../../y.pdf", "..%2f..%2fx.pdf", "a\x00.pdf.png"):
            r = _post_file(c, "/leases", name)
            assert r.status_code in (400, 422), f"{name!r} -> {r.status_code}"
        after = set(os.listdir(tmp_root))
        leaked = [f for f in (after - before) if "passwd" in f or f == "y.pdf"]
        assert not leaked, f"crafted filename produced files outside the temp slot: {leaked}"
    finally:
        os.unlink(db)
    print("✓ test_crafted_traversal_filename_never_500s_or_escapes_tmp: PASS")


def test_oversized_upload_is_413():
    db, base_id = _fresh_temp_db()
    try:
        big = b"%PDF-1.4\n" + b"0" * (17 * 1024 * 1024)  # > MAX_CONTENT_LENGTH (16 MB)
        r = _post_file(_analyst(), "/leases", "big.pdf", data=big)
        assert r.status_code == 413, r.status_code
        assert "16" in r.get_json()["error"]
    finally:
        os.unlink(db)
    print("✓ test_oversized_upload_is_413: PASS")


def test_empty_file_gets_a_clear_error_not_a_crash():
    db, base_id = _fresh_temp_db()
    try:
        r = _post_file(_analyst(), "/leases", "empty.pdf", data=b"")
        assert r.status_code == 422, r.status_code
        assert "empty" in r.get_json()["error"].lower()
        assert "Traceback" not in str(r.get_json())
    finally:
        os.unlink(db)
    print("✓ test_empty_file_gets_a_clear_error_not_a_crash: PASS")


def test_corrupt_pdf_is_422_not_500():
    db, base_id = _fresh_temp_db()
    try:
        r = _post_file(_analyst(), "/leases", "corrupt.pdf", data=b"%PDF-1.4\n" + bytes(range(256)) * 3)
        assert r.status_code == 422, r.status_code
        body = r.get_json()
        assert "Traceback" not in str(body)
        assert not body["error"].split()[0].startswith("/"), "error message must not leak a filesystem path"
    finally:
        os.unlink(db)
    print("✓ test_corrupt_pdf_is_422_not_500: PASS")


# Gap 1: empty file on /leases/import-rent-roll

def test_empty_rent_roll_csv_is_4xx_with_clear_error():
    db, _ = _fresh_temp_db()
    try:
        r = _post_file(_analyst(), "/leases/import-rent-roll", "empty.csv", data=b"")
        assert r.status_code in (400, 422), r.status_code
        body = r.get_json()
        assert "empty" in body.get("error", "").lower() or "no" in body.get("error", "").lower()
        assert "Traceback" not in str(body)
    finally:
        os.unlink(db)
    print("✓ test_empty_rent_roll_csv_is_4xx_with_clear_error: PASS")


def test_empty_rent_roll_xlsx_is_4xx_with_clear_error():
    db, _ = _fresh_temp_db()
    try:
        r = _post_file(_analyst(), "/leases/import-rent-roll", "empty.xlsx", data=b"")
        assert r.status_code in (400, 422), r.status_code
        body = r.get_json()
        assert "error" in body
        assert "Traceback" not in str(body)
    finally:
        os.unlink(db)
    print("✓ test_empty_rent_roll_xlsx_is_4xx_with_clear_error: PASS")


# Gap 2: corrupted XLSX

def test_corrupt_xlsx_on_rent_roll_import_is_4xx_not_500():
    db, _ = _fresh_temp_db()
    try:
        # Garbage bytes with .xlsx extension
        garbage = b"PK\x03\x04" + bytes(range(256)) * 2  # looks like a zip header but is garbage
        r = _post_file(_analyst(), "/leases/import-rent-roll", "corrupt.xlsx", data=garbage)
        assert r.status_code in (400, 422), r.status_code
        body = r.get_json()
        assert "error" in body
        assert "Traceback" not in str(body)
        # Error message should be plain English, not a raw exception
        error_msg = body.get("error", "")
        assert not error_msg.startswith("(") and not error_msg.startswith("<"), \
            f"error looks like raw exception repr: {error_msg}"
    finally:
        os.unlink(db)
    print("✓ test_corrupt_xlsx_on_rent_roll_import_is_4xx_not_500: PASS")


# Gap 3: password-protected XLSX (OLE2 magic header)

def test_password_protected_xlsx_is_4xx_with_clear_error():
    db, _ = _fresh_temp_db()
    try:
        # OLE2/CFB magic header D0 CF 11 E0 A1 B1 1A E1 (password-protected Excel format)
        ole2_header = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
        r = _post_file(_analyst(), "/leases/import-rent-roll", "protected.xlsx", data=ole2_header)
        assert r.status_code in (400, 422), r.status_code
        body = r.get_json()
        error_msg = body.get("error", "").lower()
        # Ideally says "password-protected", but at minimum a clear error
        assert "error" in body
        assert "Traceback" not in str(body)
    finally:
        os.unlink(db)
    print("✓ test_password_protected_xlsx_is_4xx_with_clear_error: PASS")


# Gap 4: rent roll with zero matching leases

def test_rent_roll_with_no_matching_leases_produces_all_unit_no_lease():
    db, _ = _fresh_temp_db()
    try:
        c = _analyst()
        # Import a rent roll with no lease PDFs on file at all
        rows = [["Tenant", "Unit", "Rent"], ["A", "101", "$1000"]]
        import csv as csv_mod
        buf = io.StringIO()
        csv_mod.writer(buf).writerows(rows)
        resp = c.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(buf.getvalue().encode()), "test.csv")},
            content_type="multipart/form-data"
        )
        assert resp.status_code == 201, resp.get_json()

        # Now generate the deal mismatch report
        report_resp = c.post("/portfolio/deal-mismatch-report")
        assert report_resp.status_code == 200, report_resp.get_json()
        report_data = report_resp.get_json()
        discrepancies = report_data.get("discrepancies", [])

        # All should be unit_no_lease
        unit_no_lease = [d for d in discrepancies if d["discrepancy_type"] == "unit_no_lease"]
        assert len(unit_no_lease) > 0, "expected at least one unit_no_lease finding"
        assert len(unit_no_lease) == len(discrepancies), "all findings should be unit_no_lease"

        # PDF and Excel exports should succeed too (non-trivial size)
        pdf_resp = c.post("/portfolio/deal-mismatch-report.pdf")
        assert pdf_resp.status_code == 200
        assert len(pdf_resp.data) > 500, "PDF should have non-trivial content"

        xlsx_resp = c.post("/portfolio/deal-mismatch-report.xlsx")
        assert xlsx_resp.status_code == 200
        assert len(xlsx_resp.data) > 500, "XLSX should have non-trivial content"
    finally:
        os.unlink(db)
    print("✓ test_rent_roll_with_no_matching_leases_produces_all_unit_no_lease: PASS")


# Gap 5: huge file (2000 units)

def test_huge_rent_roll_file_imports_successfully():
    db, _ = _fresh_temp_db()
    try:
        c = _analyst()
        # Generate 2000-unit CSV
        rows = [["Tenant", "Unit", "Rent"]]
        for i in range(1, 2001):
            rows.append([f"Tenant {i}", f"{i:04d}", f"${1000 + (i % 1000)}.00"])

        import csv as csv_mod
        buf = io.StringIO()
        csv_mod.writer(buf).writerows(rows)

        resp = c.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(buf.getvalue().encode()), "huge.csv")},
            content_type="multipart/form-data"
        )
        assert resp.status_code == 201, resp.get_json()
        leases = resp.get_json().get("leases", [])
        assert len(leases) == 2000, f"expected 2000, got {len(leases)}"
    finally:
        os.unlink(db)
    print("✓ test_huge_rent_roll_file_imports_successfully: PASS")


if __name__ == "__main__":
    test_missing_file_is_400_on_every_upload_route()
    test_disallowed_extension_is_rejected_server_side()
    test_crafted_traversal_filename_never_500s_or_escapes_tmp()
    test_oversized_upload_is_413()
    test_empty_file_gets_a_clear_error_not_a_crash()
    test_corrupt_pdf_is_422_not_500()
    test_empty_rent_roll_csv_is_4xx_with_clear_error()
    test_empty_rent_roll_xlsx_is_4xx_with_clear_error()
    test_corrupt_xlsx_on_rent_roll_import_is_4xx_not_500()
    test_password_protected_xlsx_is_4xx_with_clear_error()
    test_rent_roll_with_no_matching_leases_produces_all_unit_no_lease()
    test_huge_rent_roll_file_imports_successfully()
    print("\nAll upload validation tests passed.")
