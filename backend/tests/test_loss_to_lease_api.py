"""
Tests the GET /portfolio/loss-to-lease route end to end through Flask's
in-process test_client() -- confirms the real route works, not just the
underlying compute_loss_to_lease function (already covered thoroughly
in test_portfolio.py). Points database.py at an isolated temp SQLite
file, so this never touches the real dev database or requires a live
server running.
"""

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


def _fields(property_address=None, rent_amount=None, square_footage=None):
    def field(v):
        return {"value": v, "source": {"page": 1, "quote": "..."} if v else None, "confidence": "high" if v else None}

    fields = {name: field(None) for name in FIELD_NAMES}
    fields["property_address"] = field(property_address)
    fields["rent_amount"] = field(rent_amount)
    fields["square_footage"] = field(square_footage)
    return fields


def test_loss_to_lease_route_empty_portfolio():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        resp = client.get("/portfolio/loss-to-lease")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["leases"] == []
        assert data["total_monthly_upside"] is None
    finally:
        os.unlink(db_path)

    print("✓ test_loss_to_lease_route_empty_portfolio: PASS")


def test_loss_to_lease_route_groups_different_suites_same_building():
    """End-to-end confirmation (through the real route, real DB round-trip) of the same-building/different-suite grouping fix."""
    db_path = _fresh_temp_db()
    try:
        database.insert_lease("a.pdf", _fields(property_address="500 Commerce Blvd, Suite 100", rent_amount="$2,000.00", square_footage="1,000 sq ft"))
        database.insert_lease("b.pdf", _fields(property_address="500 Commerce Blvd, Suite 200", rent_amount="$4,000.00", square_footage="1,000 sq ft"))

        client = _authed_client()
        resp = client.get("/portfolio/loss-to-lease")
        data = resp.get_json()

        assert data["lease_count"] == 2
        assert data["total_monthly_upside"] == 2000.0
    finally:
        os.unlink(db_path)

    print("✓ test_loss_to_lease_route_groups_different_suites_same_building: PASS")


def test_loss_to_lease_route_reflects_amendments():
    """A rent-increase amendment must change which lease is the building's top rent, not just the base lease's original figure."""
    db_path = _fresh_temp_db()
    try:
        base_id = database.insert_lease(
            "base.pdf", _fields(property_address="1 Plaza Dr, Suite A", rent_amount="$1,000.00", square_footage="1,000 sq ft"),
        )
        database.insert_lease(
            "amendment.pdf",
            _fields(rent_amount="$9,000.00"),  # big rent increase via amendment
            document_type="amendment",
            base_lease_id=base_id,
        )
        database.insert_lease("other.pdf", _fields(property_address="1 Plaza Dr, Suite B", rent_amount="$3,000.00", square_footage="1,000 sq ft"))

        client = _authed_client()
        resp = client.get("/portfolio/loss-to-lease")
        data = resp.get_json()

        # The amended (now $9/sqft) lease should be the building's top, not Suite B
        top_lease = next(r for r in data["leases"] if r["loss_pct"] == 0.0)
        assert top_lease["rent_per_sqft"] == 9.0
    finally:
        os.unlink(db_path)

    print("✓ test_loss_to_lease_route_reflects_amendments: PASS")


if __name__ == "__main__":
    test_loss_to_lease_route_empty_portfolio()
    test_loss_to_lease_route_groups_different_suites_same_building()
    test_loss_to_lease_route_reflects_amendments()
    print("\nAll loss-to-lease API tests passed.")
