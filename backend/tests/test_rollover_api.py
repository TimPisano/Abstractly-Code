"""
Tests the GET /portfolio/rollover route (WALT + rollover schedule
together) end to end through Flask's in-process test_client() --
confirms the real route works, not just the underlying compute_walt/
compute_rollover_schedule functions (already covered thoroughly in
test_portfolio.py). Points database.py at an isolated temp SQLite
file, so this never touches the real dev database or requires a live
server running.

Uses real (today-relative) dates rather than a fixed reference date,
since the route itself always calls date.today() -- these tests can't
pass an explicit reference_date the way the unit tests in
test_portfolio.py do.
"""

import os
import sys
import tempfile
from datetime import date, timedelta

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


def _fields(rent_amount=None, lease_end_date=None):
    def field(v):
        return {"value": v, "source": {"page": 1, "quote": "..."} if v else None, "confidence": "high" if v else None}

    fields = {name: field(None) for name in FIELD_NAMES}
    fields["rent_amount"] = field(rent_amount)
    fields["lease_end_date"] = field(lease_end_date)
    return fields


def _days_from_today(days):
    return (date.today() + timedelta(days=days)).strftime("%B %d, %Y")


def test_rollover_route_empty_portfolio():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/portfolio/rollover")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["walt"]["walt_years"] is None
        assert data["rollover_schedule"]["buckets"] is None
    finally:
        os.unlink(db_path)

    print("✓ test_rollover_route_empty_portfolio: PASS")


def test_rollover_route_real_leases_walt_and_schedule_agree():
    """WALT and the rollover schedule must be computed against the same reference_date -- both derived from the same 2 leases here should describe a consistent picture."""
    db_path = _fresh_temp_db()
    try:
        database.insert_lease("a.pdf", _fields(rent_amount="$9,000.00", lease_end_date=_days_from_today(100)))
        database.insert_lease("b.pdf", _fields(rent_amount="$1,000.00", lease_end_date=_days_from_today(800)))

        client = app.test_client()
        resp = client.get("/portfolio/rollover")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["walt"]["lease_count"] == 2
        assert data["rollover_schedule"]["lease_count"] == 2
        # Both leases' total rent must match between the two sub-results --
        # if reference_date drifted between the two calls, this could disagree.
        assert data["walt"]["total_weighted_rent"] == data["rollover_schedule"]["total_rent"] == 10000.0
        assert data["rollover_schedule"]["buckets"]["year_1"]["rent"] == 9000.0
        assert data["rollover_schedule"]["rollover_risk_level"] == "high"  # 90% in year_1
    finally:
        os.unlink(db_path)

    print("✓ test_rollover_route_real_leases_walt_and_schedule_agree: PASS")


def test_rollover_route_reflects_amendments():
    """A lease-end-date-extending amendment must change both WALT and the rollover bucket, not just the base lease's original figure."""
    db_path = _fresh_temp_db()
    try:
        base_id = database.insert_lease(
            "base.pdf", _fields(rent_amount="$5,000.00", lease_end_date=_days_from_today(100)),  # originally year_1
        )
        database.insert_lease(
            "amendment.pdf",
            _fields(lease_end_date=_days_from_today(800)),  # extended into year_2/3
            document_type="amendment",
            base_lease_id=base_id,
        )

        client = app.test_client()
        resp = client.get("/portfolio/rollover")
        data = resp.get_json()

        assert data["rollover_schedule"]["buckets"]["year_1"]["lease_count"] == 0  # NOT still in year_1
        assert data["walt"]["walt_years"] > 1.0  # pulled out past 1 year by the amendment
    finally:
        os.unlink(db_path)

    print("✓ test_rollover_route_reflects_amendments: PASS")


if __name__ == "__main__":
    test_rollover_route_empty_portfolio()
    test_rollover_route_real_leases_walt_and_schedule_agree()
    test_rollover_route_reflects_amendments()
    print("\nAll rollover API tests passed.")
