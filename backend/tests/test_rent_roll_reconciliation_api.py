"""
Tests the GET /portfolio/rent-roll-reconciliation route end to end
through Flask's in-process test_client() -- confirms the real route
works against real persisted data (a real rent roll import + real
PDF-style leases in the DB), not just the underlying
compute_rent_roll_reconciliation function (already covered thoroughly
in test_portfolio.py). Points database.py at an isolated temp SQLite
file, so this never touches the real dev database or requires a live
server running.
"""

import csv
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
    return tmp.name


def _pdf_fields(tenant=None, address=None, rent=None, end_date=None):
    def field(v):
        return {"value": v, "source": {"page": 1, "quote": "..."} if v else None, "confidence": "high" if v else None}
    fields = {name: field(None) for name in FIELD_NAMES}
    fields["tenant"] = field(tenant)
    fields["property_address"] = field(address)
    fields["rent_amount"] = field(rent)
    fields["lease_end_date"] = field(end_date)
    return fields


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_reconciliation_route_empty_portfolio():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/portfolio/rent-roll-reconciliation")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mismatches"] == []
        assert data["rent_roll_lease_count"] == 0
    finally:
        os.unlink(db_path)

    print("✓ test_reconciliation_route_empty_portfolio: PASS")


def test_reconciliation_route_real_import_plus_real_pdf_style_lease():
    """A real rent roll import (through the real import route) plus a real 'PDF' lease (a normal insert_lease call, .pdf filename) with a stale rent -- confirmed flagged through the real reconciliation route."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()

        # Real rent roll import, through the real route
        file_bytes = _csv_bytes([
            ["Tenant", "Rent"],
            ["Acme Corp", "$4,000.00"],
        ])
        client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(file_bytes), "rentroll.csv"), "property_address": "500 Main St"},
            content_type="multipart/form-data",
        )

        # Real "lease PDF" record (ordinary insert_lease, .pdf filename) with a different (stale) rent
        database.insert_lease("acme_lease.pdf", _pdf_fields(tenant="Acme Corp", address="500 Main St", rent="$4,800.00"))

        resp = client.get("/portfolio/rent-roll-reconciliation")
        data = resp.get_json()

        assert data["rent_roll_lease_count"] == 1
        assert data["lease_document_count"] == 1
        assert data["compared_pair_count"] == 1
        rent_mismatches = [m for m in data["mismatches"] if m["field"] == "rent_amount"]
        assert len(rent_mismatches) == 1
        assert rent_mismatches[0]["rent_roll_value"] == "$4,000.00"
        assert rent_mismatches[0]["lease_document_value"] == "$4,800.00"
    finally:
        os.unlink(db_path)

    print("✓ test_reconciliation_route_real_import_plus_real_pdf_style_lease: PASS")


def test_reconciliation_route_reflects_amendment_on_lease_document_side():
    """An amendment changing the lease PDF's rent must be reflected (route reads get_all_effective_leases()), not the base lease's original figure."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        file_bytes = _csv_bytes([["Tenant", "Rent"], ["Acme Corp", "$4,000.00"]])
        client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(file_bytes), "rentroll.csv"), "property_address": "500 Main St"},
            content_type="multipart/form-data",
        )

        base_id = database.insert_lease("acme_lease.pdf", _pdf_fields(tenant="Acme Corp", address="500 Main St", rent="$4,000.00"))
        database.insert_lease(
            "amendment.pdf", _pdf_fields(rent="$5,500.00"),
            document_type="amendment", base_lease_id=base_id,
        )

        resp = client.get("/portfolio/rent-roll-reconciliation")
        data = resp.get_json()
        rent_mismatches = [m for m in data["mismatches"] if m["field"] == "rent_amount"]
        assert len(rent_mismatches) == 1
        assert rent_mismatches[0]["lease_document_value"] == "$5,500.00"  # the amended rent, not the original $4,000
    finally:
        os.unlink(db_path)

    print("✓ test_reconciliation_route_reflects_amendment_on_lease_document_side: PASS")


if __name__ == "__main__":
    test_reconciliation_route_empty_portfolio()
    test_reconciliation_route_real_import_plus_real_pdf_style_lease()
    test_reconciliation_route_reflects_amendment_on_lease_document_side()
    print("\nAll rent roll reconciliation API tests passed.")
