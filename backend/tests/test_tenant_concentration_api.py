"""
Tests the GET /portfolio/tenant-concentration route end to end through
Flask's in-process test_client() -- confirms the real route (JSON
serialization, status code, database wiring) works, not just the
underlying compute_tenant_concentration function (already covered
thoroughly in test_portfolio.py). Points database.py at an isolated
temp SQLite file, so this never touches the real dev database or
requires a live server running.
"""

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


def _fields(tenant=None, rent_amount=None):
    from app.portfolio import FIELD_NAMES

    def field(v):
        return {"value": v, "source": {"page": 1, "quote": "..."} if v else None, "confidence": "high" if v else None}

    fields = {name: field(None) for name in FIELD_NAMES}
    fields["tenant"] = field(tenant)
    fields["rent_amount"] = field(rent_amount)
    return fields


def test_tenant_concentration_route_empty_portfolio():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/portfolio/tenant-concentration")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tenant_count"] == 0
        assert data["total_rent"] is None
        assert data["concentration_level"] is None
    finally:
        os.unlink(db_path)

    print("✓ test_tenant_concentration_route_empty_portfolio: PASS")


def test_tenant_concentration_route_real_leases():
    db_path = _fresh_temp_db()
    try:
        database.insert_lease("a.pdf", _fields(tenant="Big Tenant", rent_amount="$8,000.00"))
        database.insert_lease("b.pdf", _fields(tenant="Small Tenant", rent_amount="$2,000.00"))

        client = app.test_client()
        resp = client.get("/portfolio/tenant-concentration")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["tenant_count"] == 2
        assert data["total_rent"] == 10000.0
        assert data["top_1_pct"] == 80.0
        assert data["concentration_level"] == "high"
        names = {t["tenant"] for t in data["tenants"]}
        assert names == {"Big Tenant", "Small Tenant"}
    finally:
        os.unlink(db_path)

    print("✓ test_tenant_concentration_route_real_leases: PASS")


def test_tenant_concentration_route_reflects_amendments():
    """An amendment that changes the tenant's rent must be reflected -- the route reads get_all_effective_leases(), not raw base leases."""
    db_path = _fresh_temp_db()
    try:
        base_id = database.insert_lease("base.pdf", _fields(tenant="Amended Tenant", rent_amount="$5,000.00"))
        database.insert_lease(
            "amendment.pdf",
            _fields(rent_amount="$7,500.00"),  # rent increase, tenant name not restated in the amendment
            document_type="amendment",
            base_lease_id=base_id,
        )

        client = app.test_client()
        resp = client.get("/portfolio/tenant-concentration")
        data = resp.get_json()

        assert data["tenant_count"] == 1
        assert data["total_rent"] == 7500.0  # the amended rent, not the original $5,000
    finally:
        os.unlink(db_path)

    print("✓ test_tenant_concentration_route_reflects_amendments: PASS")


if __name__ == "__main__":
    test_tenant_concentration_route_empty_portfolio()
    test_tenant_concentration_route_real_leases()
    test_tenant_concentration_route_reflects_amendments()
    print("\nAll tenant concentration API tests passed.")
