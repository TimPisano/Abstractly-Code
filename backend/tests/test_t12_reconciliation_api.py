"""
Tests the POST /portfolio/t12-reconciliation route end to end through
Flask's in-process test_client() -- confirms the real route works
against real persisted leases, real multipart file upload, and the
compute_t12_reconciliation function together (already covered
thoroughly in isolation in test_portfolio.py). Points database.py at
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
from app.portfolio import FIELD_NAMES


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _authed_client():
    """
    A test_client() pre-authenticated as a logged-in analyst, via
    Flask's session_transaction() -- the standard way to test a
    session-gated route without driving an actual login POST through
    bcrypt for every test, same convention as test_admin_auth.py's
    _create_admin()/session pattern. Most routes now require at least
    a logged-in session (see app/auth.py's require_role()) since the
    RBAC audit -- analyst covers every route these tests exercise.
    """
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["email"] = "test-analyst@example.com"
        sess["name"] = "Test Analyst"
        sess["role"] = "analyst"
    return client


def _pdf_fields(tenant=None, address=None, rent=None):
    def field(v):
        return {"value": v, "source": {"page": 1, "quote": "..."} if v else None, "confidence": "high" if v else None}
    fields = {name: field(None) for name in FIELD_NAMES}
    fields["tenant"] = field(tenant)
    fields["property_address"] = field(address)
    fields["rent_amount"] = field(rent)
    return fields


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def test_t12_route_requires_a_file():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        resp = client.post("/portfolio/t12-reconciliation", data={"property_address": "100 Main St"}, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert "file" in resp.get_json()["error"].lower()
    finally:
        os.unlink(db_path)
    print("✓ test_t12_route_requires_a_file: PASS")


def test_t12_route_requires_property_address():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        file_bytes = _csv_bytes([["Line Item", "Total"], ["Total Rental Income", "120000"]])
        resp = client.post(
            "/portfolio/t12-reconciliation",
            data={"file": (io.BytesIO(file_bytes), "t12.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "property_address" in resp.get_json()["error"]
    finally:
        os.unlink(db_path)
    print("✓ test_t12_route_requires_property_address: PASS")


def test_t12_route_rejects_bad_file_type():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        resp = client.post(
            "/portfolio/t12-reconciliation",
            data={"file": (io.BytesIO(b"not a t12"), "t12.pdf"), "property_address": "100 Main St"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_t12_route_rejects_bad_file_type: PASS")


def test_t12_route_unparseable_t12_returns_400():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        file_bytes = _csv_bytes([["Notes"], ["nothing recognizable"]])
        resp = client.post(
            "/portfolio/t12-reconciliation",
            data={"file": (io.BytesIO(file_bytes), "t12.csv"), "property_address": "100 Main St"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "error" in resp.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_t12_route_unparseable_t12_returns_400: PASS")


def test_t12_route_real_leases_plus_real_t12_flags_a_real_discrepancy():
    """Real persisted leases at a building, a real T12 upload through the real route -- confirms the whole pipeline end to end, not just each half in isolation."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        database.insert_lease("acme_lease.pdf", _pdf_fields(tenant="Acme Corp", address="700 Retail Plaza, Suite 100", rent="$10,000.00"))
        database.insert_lease("beta_lease.pdf", _pdf_fields(tenant="Beta LLC", address="700 Retail Plaza, Suite 200", rent="$8,000.00"))
        # rent roll annual = (10000+8000)*12 = 216000

        file_bytes = _csv_bytes([
            ["700 Retail Plaza"],
            ["Operating Statement"],
            ["Line Item", "Total"],
            ["Gross Potential Rent", "260000"],
            ["Total Rental Income", "180000"],  # a real, flaggable gap vs. the 216000 rent roll total
        ])
        resp = client.post(
            "/portfolio/t12-reconciliation",
            data={"file": (io.BytesIO(file_bytes), "t12.csv"), "property_address": "700 Retail Plaza"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["rent_roll_annual_rent"] == 216000.0, data
        assert data["t12_annual_rental_income"] == 180000.0, data  # NOT the 260000 gross potential figure
        assert data["flagged"] is True
        assert data["direction"] == "rent_roll_higher"
        assert data["t12_source"]["quote"] == "Total Rental Income"
    finally:
        os.unlink(db_path)
    print("✓ test_t12_route_real_leases_plus_real_t12_flags_a_real_discrepancy: PASS")


def test_t12_route_does_not_persist_anything():
    """A T12 upload must never create a lease record -- it's not a lease, and doing so would corrupt every other per-lease computation."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        before = client.get("/leases").get_json()
        assert before == []

        file_bytes = _csv_bytes([["Line Item", "Total"], ["Total Rental Income", "120000"]])
        client.post(
            "/portfolio/t12-reconciliation",
            data={"file": (io.BytesIO(file_bytes), "t12.csv"), "property_address": "100 Main St"},
            content_type="multipart/form-data",
        )

        after = client.get("/leases").get_json()
        assert after == []  # still empty -- nothing was persisted
    finally:
        os.unlink(db_path)
    print("✓ test_t12_route_does_not_persist_anything: PASS")


def test_t12_route_no_matching_leases_returns_honest_not_found():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        database.insert_lease("unrelated.pdf", _pdf_fields(tenant="Unrelated Co", address="999 Other Ave", rent="$5,000.00"))

        file_bytes = _csv_bytes([["Line Item", "Total"], ["Total Rental Income", "120000"]])
        resp = client.post(
            "/portfolio/t12-reconciliation",
            data={"file": (io.BytesIO(file_bytes), "t12.csv"), "property_address": "100 Main St"},
            content_type="multipart/form-data",
        )
        data = resp.get_json()
        assert data["matched_lease_count"] == 0
        assert data["rent_roll_annual_rent"] is None
        assert data["flagged"] is None
    finally:
        os.unlink(db_path)
    print("✓ test_t12_route_no_matching_leases_returns_honest_not_found: PASS")


if __name__ == "__main__":
    test_t12_route_requires_a_file()
    test_t12_route_requires_property_address()
    test_t12_route_rejects_bad_file_type()
    test_t12_route_unparseable_t12_returns_400()
    test_t12_route_real_leases_plus_real_t12_flags_a_real_discrepancy()
    test_t12_route_does_not_persist_anything()
    test_t12_route_no_matching_leases_returns_honest_not_found()
    print("\nAll T12 reconciliation API tests passed.")
