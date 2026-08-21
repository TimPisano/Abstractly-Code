"""
Tests the POST /leases/import-rent-roll route end to end through
Flask's in-process test_client() -- confirms the real route (file
upload handling, database persistence, activity logging) works, not
just the underlying rent_roll_import.py parsing functions (already
covered thoroughly in test_rent_roll_import.py). Points database.py at
an isolated temp SQLite file, so this never touches the real dev
database or requires a live server running.
"""

import csv
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_import_route_happy_path_persists_real_leases():
    db_path = _fresh_temp_db()
    try:
        file_bytes = _csv_bytes([
            ["Tenant", "Rent", "Square Footage"],
            ["Acme Corp", "$4,500.00", "2,000 sq ft"],
            ["Beta LLC", "$3,200.00", "1,500 sq ft"],
        ])
        client = app.test_client()
        resp = client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(file_bytes), "rentroll.csv"), "property_address": "100 Main St"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["imported_count"] == 2
        assert data["skipped_rows"] == []

        leases = database.get_all_effective_leases()
        assert len(leases) == 2
        tenants = {l["extracted_fields"]["tenant"]["value"] for l in leases}
        assert tenants == {"Acme Corp", "Beta LLC"}
    finally:
        os.unlink(db_path)

    print("✓ test_import_route_happy_path_persists_real_leases: PASS")


def test_import_route_persisted_leases_feed_portfolio_computations():
    """
    The whole point of matching the PDF extractor's field shape: an
    imported lease must work with existing portfolio math (tenant
    concentration here) with zero special-casing, verified through the
    real route + real DB + real downstream API, not just checked in
    isolation.
    """
    db_path = _fresh_temp_db()
    try:
        file_bytes = _csv_bytes([
            ["Tenant", "Rent"],
            ["Big Tenant", "$8,000.00"],
            ["Small Tenant", "$2,000.00"],
        ])
        client = app.test_client()
        client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(file_bytes), "rentroll.csv")},
            content_type="multipart/form-data",
        )

        resp = client.get("/portfolio/tenant-concentration")
        data = resp.get_json()
        assert data["tenant_count"] == 2
        assert data["top_1_pct"] == 80.0
    finally:
        os.unlink(db_path)

    print("✓ test_import_route_persisted_leases_feed_portfolio_computations: PASS")


def test_import_route_skipped_rows_reported_not_silently_dropped():
    db_path = _fresh_temp_db()
    try:
        file_bytes = _csv_bytes([
            ["Tenant", "Rent"],
            ["Real Co", "$1,000.00"],
            ["VACANT", "$0.00"],
            ["Total", "$1,000.00"],
        ])
        client = app.test_client()
        resp = client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(file_bytes), "rentroll.csv")},
            content_type="multipart/form-data",
        )
        data = resp.get_json()
        assert data["imported_count"] == 1
        assert len(data["skipped_rows"]) == 2
    finally:
        os.unlink(db_path)

    print("✓ test_import_route_skipped_rows_reported_not_silently_dropped: PASS")


def test_import_route_rejects_wrong_file_type():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "lease.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert database.get_all_effective_leases() == []
    finally:
        os.unlink(db_path)

    print("✓ test_import_route_rejects_wrong_file_type: PASS")


def test_import_route_rejects_file_with_no_recognizable_columns():
    db_path = _fresh_temp_db()
    try:
        file_bytes = _csv_bytes([["Notes", "Parking"], ["some note", "2"]])
        client = app.test_client()
        resp = client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(file_bytes), "rentroll.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "error" in resp.get_json()
        assert database.get_all_effective_leases() == []  # nothing partially imported
    finally:
        os.unlink(db_path)

    print("✓ test_import_route_rejects_file_with_no_recognizable_columns: PASS")


def test_import_route_no_file_uploaded():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/leases/import-rent-roll", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)

    print("✓ test_import_route_no_file_uploaded: PASS")


def test_import_route_xlsx_also_works():
    from openpyxl import Workbook

    db_path = _fresh_temp_db()
    try:
        wb = Workbook()
        ws = wb.active
        ws.append(["Tenant", "Rent"])
        ws.append(["Xlsx Tenant", 5000])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        client = app.test_client()
        resp = client.post(
            "/leases/import-rent-roll",
            data={"file": (buf, "rentroll.xlsx")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["imported_count"] == 1
    finally:
        os.unlink(db_path)

    print("✓ test_import_route_xlsx_also_works: PASS")


if __name__ == "__main__":
    test_import_route_happy_path_persists_real_leases()
    test_import_route_persisted_leases_feed_portfolio_computations()
    test_import_route_skipped_rows_reported_not_silently_dropped()
    test_import_route_rejects_wrong_file_type()
    test_import_route_rejects_file_with_no_recognizable_columns()
    test_import_route_no_file_uploaded()
    test_import_route_xlsx_also_works()
    print("\nAll rent roll import API tests passed.")
