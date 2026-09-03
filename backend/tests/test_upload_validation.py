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
        s.update({"user_id": 1, "email": "a@x.com", "name": "A", "role": "analyst"})
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


if __name__ == "__main__":
    test_missing_file_is_400_on_every_upload_route()
    test_disallowed_extension_is_rejected_server_side()
    test_crafted_traversal_filename_never_500s_or_escapes_tmp()
    test_oversized_upload_is_413()
    test_empty_file_gets_a_clear_error_not_a_crash()
    test_corrupt_pdf_is_422_not_500()
    print("\nAll upload validation tests passed.")
