"""
Tests for app/portfolio_history.py (rent growth, tenant turnover,
rollover pattern, per-property history timeline) and
GET /portfolio/property-trends.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_rollover_api.py.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES
from app.portfolio_history import (
    compute_property_trends,
    compute_portfolio_trends,
    compute_rent_growth,
    compute_rollover_pattern,
    compute_tenant_turnover,
    get_property_history,
)

ADDRESS = "100 Elm St, Suite 200, Springfield, IL"


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _fields(tenant=None, rent_amount=None, property_address=None, lease_end_date=None, square_footage=None):
    def field(v):
        return {"value": v, "source": {"page": 1, "quote": "..."} if v else None, "confidence": "high" if v else None}
    fields = {name: field(None) for name in FIELD_NAMES}
    fields["tenant"] = field(tenant)
    fields["rent_amount"] = field(rent_amount)
    fields["property_address"] = field(property_address)
    fields["lease_end_date"] = field(lease_end_date)
    fields["square_footage"] = field(square_footage)
    return fields


def _insert(tenant, rent, address=ADDRESS, end_date=None, filename="upload.pdf"):
    return database.insert_lease(filename, _fields(tenant=tenant, rent_amount=rent, property_address=address, lease_end_date=end_date))


def _get_all():
    return database.get_all_effective_leases()


# ------------------------------------------------------------------
# get_property_history
# ------------------------------------------------------------------

def test_history_matches_building_ignoring_suite():
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", "$4,000.00", "100 Elm St, Suite 200, Springfield, IL")
        _insert("Beta", "$5,000.00", "100 Elm St, Suite 300, Springfield, IL")  # different suite, same building
        _insert("Gamma", "$6,000.00", "999 Oak Ave, Springfield, IL")  # different building entirely

        history = get_property_history(_get_all(), "100 Elm St, Springfield, IL")
        assert len(history) == 2, "both suites at the same building must match"
        assert {h["tenant"] for h in history} == {"Acme", "Beta"}
    finally:
        os.unlink(db_path)
    print("✓ test_history_matches_building_ignoring_suite: PASS")


def test_history_ordered_oldest_first():
    db_path = _fresh_temp_db()
    try:
        id1 = _insert("Acme", "$4,000.00")
        id2 = _insert("Acme", "$4,200.00")
        history = get_property_history(_get_all(), ADDRESS)
        assert [h["lease_id"] for h in history] == [id1, id2]
    finally:
        os.unlink(db_path)
    print("✓ test_history_ordered_oldest_first: PASS")


def test_history_blank_address_returns_empty():
    db_path = _fresh_temp_db()
    try:
        assert get_property_history(_get_all(), "") == []
        assert get_property_history(_get_all(), None) == []
    finally:
        os.unlink(db_path)
    print("✓ test_history_blank_address_returns_empty: PASS")


# ------------------------------------------------------------------
# compute_rent_growth
# ------------------------------------------------------------------

def test_rent_growth_computes_pct_change_same_unit_same_tenant():
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", "$4,000.00")
        _insert("Acme", "$4,400.00")  # +10%, same tenant -> escalation/renewal, not turnover
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_rent_growth(history)

        assert result["units_with_growth_data"] == 1
        unit = result["units"][0]
        assert len(unit["transitions"]) == 1
        t = unit["transitions"][0]
        assert t["pct_change"] == 10.0
        assert t["tenant_changed"] is False
        assert unit["total_pct_change"] == 10.0
    finally:
        os.unlink(db_path)
    print("✓ test_rent_growth_computes_pct_change_same_unit_same_tenant: PASS")


def test_rent_growth_flags_tenant_change_at_transition():
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", "$4,000.00")
        _insert("Zenith Corp", "$3,600.00")  # new tenant, rent reset DOWN -- a real, honest scenario
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_rent_growth(history)
        t = result["units"][0]["transitions"][0]
        assert t["tenant_changed"] is True
        assert t["pct_change"] == -10.0
    finally:
        os.unlink(db_path)
    print("✓ test_rent_growth_flags_tenant_change_at_transition: PASS")


def test_rent_growth_unparseable_rent_produces_no_transition_but_unit_still_tracked():
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", None)  # never found
        _insert("Acme", "$4,000.00")
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_rent_growth(history)
        assert result["units_with_growth_data"] == 0
        assert result["units"][0]["data_points"] == 2
        assert result["units"][0]["transitions"] == []
        assert result["units"][0]["total_pct_change"] is None
    finally:
        os.unlink(db_path)
    print("✓ test_rent_growth_unparseable_rent_produces_no_transition_but_unit_still_tracked: PASS")


def test_rent_growth_different_units_tracked_independently():
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", "$4,000.00", "100 Elm St, Suite 200, Springfield, IL")
        _insert("Acme", "$4,400.00", "100 Elm St, Suite 200, Springfield, IL")
        _insert("Beta", "$5,000.00", "100 Elm St, Suite 300, Springfield, IL")
        _insert("Beta", "$4,500.00", "100 Elm St, Suite 300, Springfield, IL")

        history = get_property_history(_get_all(), "100 Elm St, Springfield, IL")
        result = compute_rent_growth(history)
        assert result["units_with_growth_data"] == 2
        by_unit = {u["unit_address"]: u["total_pct_change"] for u in result["units"]}
        assert by_unit["100 Elm St, Suite 200, Springfield, IL"] == 10.0
        assert by_unit["100 Elm St, Suite 300, Springfield, IL"] == -10.0
    finally:
        os.unlink(db_path)
    print("✓ test_rent_growth_different_units_tracked_independently: PASS")


# ------------------------------------------------------------------
# compute_tenant_turnover
# ------------------------------------------------------------------

def test_tenant_turnover_detects_a_real_change():
    db_path = _fresh_temp_db()
    try:
        old_id = _insert("Acme", "$4,000.00")
        new_id = _insert("Zenith Corp", "$4,200.00")
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_tenant_turnover(history)

        assert result["turnover_count"] == 1
        assert result["units_tracked"] == 1
        event = result["events"][0]
        assert event["from_tenant"] == "Acme"
        assert event["to_tenant"] == "Zenith Corp"
        assert event["old_lease_id"] == old_id
        assert event["new_lease_id"] == new_id
    finally:
        os.unlink(db_path)
    print("✓ test_tenant_turnover_detects_a_real_change: PASS")


def test_tenant_turnover_same_tenant_reworded_is_not_a_false_positive():
    """_normalize_tenant_name already handles case/punctuation -- confirms turnover detection reuses it rather than doing a naive string compare."""
    db_path = _fresh_temp_db()
    try:
        _insert("Acme Corp", "$4,000.00")
        _insert("ACME CORP", "$4,200.00")
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_tenant_turnover(history)
        assert result["turnover_count"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_tenant_turnover_same_tenant_reworded_is_not_a_false_positive: PASS")


def test_tenant_turnover_missing_tenant_on_either_side_is_not_flagged():
    db_path = _fresh_temp_db()
    try:
        _insert(None, "$4,000.00")
        _insert("Acme", "$4,200.00")
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_tenant_turnover(history)
        assert result["turnover_count"] == 0, "a missing tenant on one side is nothing to compare, not evidence of a change"
    finally:
        os.unlink(db_path)
    print("✓ test_tenant_turnover_missing_tenant_on_either_side_is_not_flagged: PASS")


# ------------------------------------------------------------------
# compute_rollover_pattern
# ------------------------------------------------------------------

def test_rollover_pattern_buckets_by_month_and_year():
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", "$4,000.00", end_date="December 31, 2027")
        _insert("Beta", "$5,000.00", end_date="December 15, 2028")
        _insert("Gamma", "$6,000.00", end_date="June 30, 2027")
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_rollover_pattern(history)

        assert result["by_month"]["12"] == 2
        assert result["by_month"]["06"] == 1
        assert result["by_month"]["01"] == 0
        assert result["by_year"] == {"2027": 2, "2028": 1}
        assert result["total_expirations_tracked"] == 3
    finally:
        os.unlink(db_path)
    print("✓ test_rollover_pattern_buckets_by_month_and_year: PASS")


def test_rollover_pattern_unparseable_end_date_not_counted():
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", "$4,000.00", end_date=None)
        history = get_property_history(_get_all(), ADDRESS)
        result = compute_rollover_pattern(history)
        assert result["total_expirations_tracked"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_rollover_pattern_unparseable_end_date_not_counted: PASS")


# ------------------------------------------------------------------
# compute_property_trends (combined) + the route
# ------------------------------------------------------------------

def test_compute_property_trends_blank_address_returns_none():
    db_path = _fresh_temp_db()
    try:
        assert compute_property_trends(_get_all(), "") is None
    finally:
        os.unlink(db_path)
    print("✓ test_compute_property_trends_blank_address_returns_none: PASS")


def test_compute_property_trends_no_matching_records_is_empty_not_error():
    db_path = _fresh_temp_db()
    try:
        trends = compute_property_trends(_get_all(), "1 Nowhere Rd")
        assert trends is not None
        assert trends["record_count"] == 0
        assert trends["rent_growth"]["units"] == []
        assert trends["tenant_turnover"]["events"] == []
        assert trends["rollover_pattern"]["total_expirations_tracked"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_compute_property_trends_no_matching_records_is_empty_not_error: PASS")


def test_property_trends_route_happy_path():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        _insert("Acme", "$4,000.00", end_date="December 31, 2027")
        _insert("Zenith Corp", "$4,400.00", end_date="December 31, 2029")

        resp = client.get(f"/portfolio/property-trends?property_address={ADDRESS}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["record_count"] == 2
        assert data["rent_growth"]["units"][0]["transitions"][0]["tenant_changed"] is True
        assert data["tenant_turnover"]["turnover_count"] == 1
        assert data["rollover_pattern"]["total_expirations_tracked"] == 2
    finally:
        os.unlink(db_path)
    print("✓ test_property_trends_route_happy_path: PASS")


def test_property_trends_route_missing_address_returns_400():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/portfolio/property-trends")
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_property_trends_route_missing_address_returns_400: PASS")


def test_property_trends_route_no_history_still_200():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/portfolio/property-trends?property_address=1 Nowhere Rd")
        assert resp.status_code == 200
        assert resp.get_json()["record_count"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_property_trends_route_no_history_still_200: PASS")


def test_deletion_removes_history_documented_limitation():
    """Not a bug -- a documented, deliberate scope boundary: DELETE is still a real hard delete, so a deleted lease's history goes with it."""
    db_path = _fresh_temp_db()
    try:
        lease_id = _insert("Acme", "$4,000.00")
        assert len(get_property_history(_get_all(), ADDRESS)) == 1
        database.delete_lease(lease_id)
        assert len(get_property_history(_get_all(), ADDRESS)) == 0
    finally:
        os.unlink(db_path)
    print("✓ test_deletion_removes_history_documented_limitation: PASS")


# ------------------------------------------------------------------
# compute_portfolio_trends / GET /portfolio/trends -- the portfolio-
# wide sibling, replacing the "fetch property-trends once per building
# and merge client-side" workaround
# ------------------------------------------------------------------

def test_compute_portfolio_trends_empty_portfolio():
    db_path = _fresh_temp_db()
    try:
        result = compute_portfolio_trends(_get_all())
        assert result == {
            "property_count": 0, "record_count": 0, "properties": [],
            "portfolio_tenant_turnover": {"turnover_count": 0, "units_tracked": 0},
            "portfolio_rollover_pattern": {"by_month": {f"{m:02d}": 0 for m in range(1, 13)}, "by_year": {}, "total_expirations_tracked": 0},
        }
    finally:
        os.unlink(db_path)
    print("✓ test_compute_portfolio_trends_empty_portfolio: PASS")


def test_compute_portfolio_trends_matches_per_property_calls_summed():
    """The real point of this endpoint: its totals must equal what calling compute_property_trends once per building and summing yourself would have produced -- proving the aggregation is genuinely equivalent, not just plausible-looking."""
    db_path = _fresh_temp_db()
    try:
        _insert("Acme", "$4,000.00", "1 Main St", end_date="December 31, 2027")
        _insert("Zenith Corp", "$4,400.00", "1 Main St", end_date="December 31, 2029")  # turnover at 1 Main St
        _insert("Beta", "$5,000.00", "2 Oak Ave", end_date="June 30, 2028")

        leases = _get_all()
        portfolio_result = compute_portfolio_trends(leases)
        assert portfolio_result["property_count"] == 2

        manual_turnover_total = 0
        manual_expirations_total = 0
        for address in ("1 Main St", "2 Oak Ave"):
            per_property = compute_property_trends(leases, address)
            manual_turnover_total += per_property["tenant_turnover"]["turnover_count"]
            manual_expirations_total += per_property["rollover_pattern"]["total_expirations_tracked"]

        assert portfolio_result["portfolio_tenant_turnover"]["turnover_count"] == manual_turnover_total == 1
        assert portfolio_result["portfolio_rollover_pattern"]["total_expirations_tracked"] == manual_expirations_total == 3
        assert portfolio_result["record_count"] == 3
    finally:
        os.unlink(db_path)
    print("✓ test_compute_portfolio_trends_matches_per_property_calls_summed: PASS")


def test_portfolio_trends_route():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        _insert("Acme", "$4,000.00", "1 Main St", end_date="December 31, 2027")
        _insert("Beta", "$5,000.00", "2 Oak Ave", end_date="June 30, 2028")

        resp = client.get("/portfolio/trends")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["property_count"] == 2
        assert {p["property_address"] for p in data["properties"]} == {"1 Main St", "2 Oak Ave"}
    finally:
        os.unlink(db_path)
    print("✓ test_portfolio_trends_route: PASS")


if __name__ == "__main__":
    test_history_matches_building_ignoring_suite()
    test_history_ordered_oldest_first()
    test_history_blank_address_returns_empty()
    test_rent_growth_computes_pct_change_same_unit_same_tenant()
    test_rent_growth_flags_tenant_change_at_transition()
    test_rent_growth_unparseable_rent_produces_no_transition_but_unit_still_tracked()
    test_rent_growth_different_units_tracked_independently()
    test_tenant_turnover_detects_a_real_change()
    test_tenant_turnover_same_tenant_reworded_is_not_a_false_positive()
    test_tenant_turnover_missing_tenant_on_either_side_is_not_flagged()
    test_rollover_pattern_buckets_by_month_and_year()
    test_rollover_pattern_unparseable_end_date_not_counted()
    test_compute_property_trends_blank_address_returns_none()
    test_compute_property_trends_no_matching_records_is_empty_not_error()
    test_property_trends_route_happy_path()
    test_property_trends_route_missing_address_returns_400()
    test_property_trends_route_no_history_still_200()
    test_deletion_removes_history_documented_limitation()
    test_compute_portfolio_trends_empty_portfolio()
    test_compute_portfolio_trends_matches_per_property_calls_summed()
    test_portfolio_trends_route()
    print("\nAll portfolio history tests passed.")
