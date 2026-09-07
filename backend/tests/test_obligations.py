"""
Tests for the obligations engine (app/obligations.py): renewal/
termination notice deadlines, rent-escalation trigger dates, and the
insurance "present but not date-computable" case -- plus a route-level
smoke test for GET /portfolio/obligations.

Date math is checked against independently-verified expected values
(plain date/timedelta arithmetic worked out by hand, not by re-running
the code under test) -- see tools/stress_test/generate_lease_fixtures.py
for the fuller, full-lease-text version of this same discipline.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date

from app.api import app
from app import database, obligations
from app.portfolio import FIELD_NAMES


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _authed_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["email"] = "test@example.com"
        sess["name"] = "Test User"
        sess["role"] = "analyst"
    return client


def _fields(**overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            value = overrides[name]
            result[name] = {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


def _lease(**field_overrides):
    return {"id": 1, "extracted_fields": _fields(**field_overrides)}


REF = date(2024, 1, 1)


# ----------------------------------------------------------------------
# Renewal notice deadline
# ----------------------------------------------------------------------

def test_renewal_notice_deadline_computed_correctly():
    lease = _lease(
        lease_end_date="March 31, 2028",
        renewal_options="2 option(s) of 5 year(s) each; 180 days notice; renewal rent based on then-prevailing fair market rate",
    )
    result = obligations.compute_renewal_notice_deadline(lease, REF)
    assert result["due_date"] == "2027-10-03"  # verified: date(2028,3,31) - timedelta(days=180)
    assert result["obligation_type"] == "renewal_notice_deadline"
    assert result["currently_exercisable"] is True  # REF (2024-01-01) is before the deadline
    print("✓ test_renewal_notice_deadline_computed_correctly: PASS")


def test_renewal_notice_deadline_none_without_end_date():
    lease = _lease(renewal_options="1 option(s) of 5 year(s) each; 90 days notice")
    assert obligations.compute_renewal_notice_deadline(lease, REF) is None
    print("✓ test_renewal_notice_deadline_none_without_end_date: PASS")


def test_renewal_notice_deadline_none_without_notice_days():
    lease = _lease(lease_end_date="March 31, 2028", renewal_options="1 option(s) of 5 year(s) each")
    assert obligations.compute_renewal_notice_deadline(lease, REF) is None
    print("✓ test_renewal_notice_deadline_none_without_notice_days: PASS")


def test_renewal_notice_deadline_overdue_status():
    lease = _lease(lease_end_date="February 1, 2024", renewal_options="1 option(s) of 5 year(s) each; 90 days notice")
    result = obligations.compute_renewal_notice_deadline(lease, REF)
    # deadline = 2024-02-01 - 90 days = 2023-11-03, before REF (2024-01-01)
    assert result["due_date"] == "2023-11-03"
    assert result["status"] == "overdue"
    assert result["currently_exercisable"] is False
    print("✓ test_renewal_notice_deadline_overdue_status: PASS")


# ----------------------------------------------------------------------
# Termination notice deadline
# ----------------------------------------------------------------------

def test_termination_notice_deadline_last_day_of_year_semantics():
    """
    The 5th year of a Term starting 2022-07-01 runs 2026-07-01 through
    2027-06-30 -- its LAST day is 2027-06-30, one day before the 5-year
    anniversary (2027-07-01), not the anniversary itself. This is the
    off-by-one caught by hand-verifying the lease-text fixture before
    trusting the code (see tools/stress_test/generate_lease_fixtures.py
    fixture 05) -- pinned here so it can never silently regress.
    """
    lease = _lease(
        lease_start_date="July 1, 2022",
        termination_options="terminable after year 5 of the term; 180 days notice",
    )
    result = obligations.compute_termination_notice_deadline(lease, REF)
    assert result["due_date"] == "2027-01-01"  # verified: date(2027,6,30) - timedelta(days=180)
    print("✓ test_termination_notice_deadline_last_day_of_year_semantics: PASS")


def test_termination_notice_deadline_none_without_notice_days():
    lease = _lease(lease_start_date="April 1, 2021", termination_options="terminable after year 7 of the term")
    assert obligations.compute_termination_notice_deadline(lease, REF) is None
    print("✓ test_termination_notice_deadline_none_without_notice_days: PASS")


def test_termination_notice_deadline_none_without_start_date():
    lease = _lease(termination_options="terminable after year 5 of the term; 180 days notice")
    assert obligations.compute_termination_notice_deadline(lease, REF) is None
    print("✓ test_termination_notice_deadline_none_without_start_date: PASS")


# ----------------------------------------------------------------------
# Escalation trigger dates
# ----------------------------------------------------------------------

def test_escalation_year_by_year_schedule():
    lease = _lease(
        lease_start_date="March 1, 2023",
        rent_escalation="Year 1: $8,000.00; Year 2: $8,240.00; Year 3: $8,487.00",
    )
    results = obligations.compute_escalation_trigger_dates(lease, REF)
    due_dates = sorted(r["due_date"] for r in results)
    # Year 1 is the starting rent (no trigger); Year 2 triggers on the
    # 1-year anniversary, Year 3 on the 2-year anniversary.
    assert due_dates == ["2024-03-01", "2025-03-01"]
    print("✓ test_escalation_year_by_year_schedule: PASS")


def test_escalation_flat_annual_percentage():
    lease = _lease(lease_start_date="January 1, 2024", lease_end_date="December 31, 2026", rent_escalation="3% annually")
    results = obligations.compute_escalation_trigger_dates(lease, REF)
    due_dates = sorted(r["due_date"] for r in results)
    assert due_dates == ["2025-01-01", "2026-01-01"]
    print("✓ test_escalation_flat_annual_percentage: PASS")


def test_escalation_one_time_bump_is_not_annual():
    """A percentage with no 'annual'/'anniversary' cue is a one-time bump, not a recurring escalation -- must produce zero trigger dates, not one guessed at some arbitrary point."""
    lease = _lease(lease_start_date="September 1, 2023", lease_end_date="August 31, 2028", rent_escalation="10% increase")
    assert obligations.compute_escalation_trigger_dates(lease, REF) == []
    print("✓ test_escalation_one_time_bump_is_not_annual: PASS")


def test_escalation_none_without_start_date():
    lease = _lease(rent_escalation="3% annually")
    assert obligations.compute_escalation_trigger_dates(lease, REF) == []
    print("✓ test_escalation_none_without_start_date: PASS")


# ----------------------------------------------------------------------
# Insurance -- present but never a fabricated date
# ----------------------------------------------------------------------

def test_insurance_obligation_present_with_no_fabricated_date():
    lease = _lease(insurance_requirements="$2,000,000.00 per occurrence CGL")
    result = obligations.compute_insurance_obligation(lease)
    assert result is not None
    assert result["due_date"] is None
    assert result["status"] == "not_date_computable"
    print("✓ test_insurance_obligation_present_with_no_fabricated_date: PASS")


def test_insurance_obligation_absent_without_requirement_text():
    lease = _lease()
    assert obligations.compute_insurance_obligation(lease) is None
    print("✓ test_insurance_obligation_absent_without_requirement_text: PASS")


# ----------------------------------------------------------------------
# Portfolio-level: sorting
# ----------------------------------------------------------------------

def test_portfolio_obligations_sorted_soonest_first_nulls_last():
    lease_soon = {"id": 1, "extracted_fields": _fields(
        lease_end_date="February 1, 2024", renewal_options="1 option(s) of 5 year(s) each; 30 days notice",
    )}
    lease_later = {"id": 2, "extracted_fields": _fields(
        lease_end_date="December 31, 2029", renewal_options="1 option(s) of 5 year(s) each; 90 days notice",
    )}
    lease_no_date = {"id": 3, "extracted_fields": _fields(insurance_requirements="$1,000,000 CGL")}

    results = obligations.compute_portfolio_obligations([lease_later, lease_no_date, lease_soon], REF)
    lease_ids_in_order = [r["lease_id"] for r in results]
    assert lease_ids_in_order == [1, 2, 3]  # soonest due_date first, null due_date (insurance) last
    print("✓ test_portfolio_obligations_sorted_soonest_first_nulls_last: PASS")


# ----------------------------------------------------------------------
# Route-level smoke test
# ----------------------------------------------------------------------

def test_obligations_route_requires_auth_and_returns_computed_list():
    db_path = _fresh_temp_db()
    try:
        anon = app.test_client()
        assert anon.get("/portfolio/obligations").status_code == 401

        lease_id = database.insert_lease("lease.pdf", _fields(
            tenant="Acme Corp",
            lease_start_date="January 1, 2023",
            lease_end_date="December 31, 2027",
            renewal_options="1 option(s) of 5 year(s) each; 180 days notice",
        ))
        client = _authed_client()
        resp = client.get("/portfolio/obligations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(o["lease_id"] == lease_id and o["obligation_type"] == "renewal_notice_deadline" for o in data)
    finally:
        os.unlink(db_path)
    print("✓ test_obligations_route_requires_auth_and_returns_computed_list: PASS")


if __name__ == "__main__":
    test_renewal_notice_deadline_computed_correctly()
    test_renewal_notice_deadline_none_without_end_date()
    test_renewal_notice_deadline_none_without_notice_days()
    test_renewal_notice_deadline_overdue_status()
    test_termination_notice_deadline_last_day_of_year_semantics()
    test_termination_notice_deadline_none_without_notice_days()
    test_termination_notice_deadline_none_without_start_date()
    test_escalation_year_by_year_schedule()
    test_escalation_flat_annual_percentage()
    test_escalation_one_time_bump_is_not_annual()
    test_escalation_none_without_start_date()
    test_insurance_obligation_present_with_no_fabricated_date()
    test_insurance_obligation_absent_without_requirement_text()
    test_portfolio_obligations_sorted_soonest_first_nulls_last()
    test_obligations_route_requires_auth_and_returns_computed_list()
