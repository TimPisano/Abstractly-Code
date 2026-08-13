"""
Tests for the daily-use dashboard additions (Phase 1 of the "daily
habit" expansion): the "what needs attention today" computation, the
portfolio health strip, and the activity log.

compute_attention_items/compute_portfolio_health tests use hand-built
lease fixtures (same pattern as test_portfolio.py) so the aggregation
logic is tested independently of extraction accuracy. The activity_log
tests point database.py at an isolated temp SQLite file (via
database.configure()) rather than touching the real dev database, since
this file doesn't need a live server — it's exercising the persistence
functions directly.
"""

import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.portfolio import compute_attention_items, compute_portfolio_health
from app import database


REFERENCE_DATE = date(2026, 1, 15)


def _field(value, page=1, confidence="high"):
    if value is None:
        return {"value": None, "source": None, "confidence": None}
    return {"value": value, "source": {"page": page, "quote": f"...{value}..."}, "confidence": confidence}


def _lease(lease_id, filename, **values):
    """Only the fields passed in are present — attention/health checks
    must tolerate a lease dict that doesn't carry all 15 keys, since
    that's also true of a record fresh out of the DB."""
    return {
        "id": lease_id,
        "filename": filename,
        "date_candidates": None,
        "extracted_fields": {name: _field(value) for name, value in values.items()},
    }


# Complete, healthy lease with no risk flags and an expiration far out.
LEASE_HEALTHY = _lease(
    1, "healthy_lease.pdf",
    tenant="Blue Sky Coffee Roasters, Inc.",
    landlord="Harborview Properties LLC",
    rent_amount="$6,000.00",
    lease_start_date="April 1, 2021",
    lease_end_date="March 31, 2029",
    security_deposit="$12,000.00",
    rent_escalation="3% annually",
    insurance_requirements="$2,000,000 per occurrence",
    default_cure_period="10 days after written notice",
    square_footage="2,400 sq ft",
)

# Expires in 45 days relative to REFERENCE_DATE (2026-01-15 -> 2026-03-01).
LEASE_EXPIRING_SOON = _lease(
    2, "expiring_soon_lease.pdf",
    tenant="Meridian Analytics Group",
    landlord="Harborview Properties LLC",
    rent_amount="$9,000.00",
    lease_start_date="January 1, 2022",
    lease_end_date="March 1, 2026",
    security_deposit="$18,000.00",
    rent_escalation="5% annually",
    insurance_requirements="$1,000,000 per occurrence",
    default_cure_period="30 days after written notice",
    square_footage="3,000 sq ft",
)

# Expires in 200 days — outside the 90-day attention window, but still
# inside the 6-month "monthly_rent_expiring_6mo" health-strip window.
LEASE_EXPIRING_LATER = _lease(
    3, "expiring_later_lease.pdf",
    tenant="Northgate Logistics Co.",
    landlord="Pinebrook Industrial Trust",
    rent_amount="$3,000.00",
    lease_start_date="July 1, 2023",
    lease_end_date="August 3, 2026",  # ~200 days after 2026-01-15
    security_deposit="$6,000.00",
    rent_escalation="4% annually",
    insurance_requirements="$3,000,000 per occurrence",
    default_cure_period="15 days after written notice",
)

# Missing tenant and rent — a core-completeness gap.
LEASE_INCOMPLETE = _lease(
    4, "incomplete_lease.pdf",
    landlord="Jordan Blake",
    lease_start_date="July 1, 2024",
    lease_end_date="June 30, 2030",
)

# Already expired relative to REFERENCE_DATE — must NOT appear in
# expiring_soon (that's for leases still ahead of you to plan for).
LEASE_ALREADY_EXPIRED = _lease(
    5, "expired_lease.pdf",
    tenant="Alex Chen",
    landlord="Casco Bay Holdings",
    rent_amount="$2,000.00",
    lease_start_date="July 1, 2024",
    lease_end_date="June 30, 2025",
)

ALL_LEASES = [LEASE_HEALTHY, LEASE_EXPIRING_SOON, LEASE_EXPIRING_LATER, LEASE_INCOMPLETE, LEASE_ALREADY_EXPIRED]


def test_expiring_soon_window():
    """Only leases expiring within 90 days (and not already expired) qualify."""
    attention = compute_attention_items(ALL_LEASES, reference_date=REFERENCE_DATE)
    ids = [e["lease_id"] for e in attention["expiring_soon"]]

    assert ids == [2], f"expected only the 45-days-out lease, got {ids}"
    assert attention["expiring_soon"][0]["days_remaining"] == 45

    print("✓ test_expiring_soon_window: PASS")


def test_missing_data_flags_incomplete_leases():
    attention = compute_attention_items(ALL_LEASES, reference_date=REFERENCE_DATE)
    entries = {e["lease_id"]: e["missing_fields"] for e in attention["missing_data"]}

    assert 4 in entries, "the incomplete lease must be flagged"
    assert set(entries[4]) >= {"tenant", "rent_amount"}
    assert 1 not in entries, "a fully-populated lease must not be flagged"

    print("✓ test_missing_data_flags_incomplete_leases: PASS")


def test_unusual_terms_reuses_risk_engine():
    """
    unusual_terms must be driven by the same risk engine the lease
    detail page uses — a lease with real risk flags (below-market rent,
    given a portfolio average) shows up here too, and a clean lease with
    no flags does not.
    """
    attention = compute_attention_items(ALL_LEASES, reference_date=REFERENCE_DATE)
    flagged_ids = {e["lease_id"] for e in attention["unusual_terms"]}

    # LEASE_EXPIRING_LATER's $3,000 rent is well below the portfolio
    # average of the other leases ($6,000/$9,000) -> below-market flag.
    assert 3 in flagged_ids, "a materially below-market lease must be flagged"
    for entry in attention["unusual_terms"]:
        assert entry["flags"], "every unusual_terms entry must carry at least one flag"
        assert all(f["severity"] in ("high", "medium") for f in entry["flags"]), \
            "low-severity-only flags must not surface here"

    print("✓ test_unusual_terms_reuses_risk_engine: PASS")


def test_attention_items_empty_portfolio():
    attention = compute_attention_items([], reference_date=REFERENCE_DATE)
    assert attention == {"expiring_soon": [], "missing_data": [], "unusual_terms": []}

    print("✓ test_attention_items_empty_portfolio: PASS")


def test_health_verified_count_matches_attention():
    """
    fully_verified_count must be exactly "total minus leases that appear
    in missing_data or unusual_terms" — the whole point of deriving it
    from compute_attention_items rather than a separate heuristic.
    """
    health = compute_portfolio_health(ALL_LEASES, reference_date=REFERENCE_DATE)
    attention = compute_attention_items(ALL_LEASES, reference_date=REFERENCE_DATE)

    needs_review_ids = {e["lease_id"] for e in attention["missing_data"]} | {e["lease_id"] for e in attention["unusual_terms"]}
    assert health["total_leases"] == 5
    assert health["needs_review_count"] == len(needs_review_ids)
    assert health["fully_verified_count"] == 5 - len(needs_review_ids)
    assert health["fully_verified_pct"] == round((5 - len(needs_review_ids)) / 5 * 100, 1)

    print("✓ test_health_verified_count_matches_attention: PASS")


def test_health_excludes_already_expired_from_days_remaining():
    """An expired lease has no 'days until expiration' — it must not pull the average down or count as exposure."""
    health = compute_portfolio_health([LEASE_ALREADY_EXPIRED], reference_date=REFERENCE_DATE)
    assert health["avg_days_to_expiration"] is None
    assert health["monthly_rent_expiring_6mo"] is None
    assert health["monthly_rent_expiring_12mo"] is None

    print("✓ test_health_excludes_already_expired_from_days_remaining: PASS")


def test_health_rent_exposure_windows():
    """
    45-day lease ($9,000) is within both the ~182-day 6mo window and the
    ~365-day 12mo window. 200-day lease ($3,000) is past the 6mo window
    (200 > 182) but within the 12mo one. Healthy lease (>1400 days out)
    counts toward neither.
    """
    health = compute_portfolio_health(
        [LEASE_HEALTHY, LEASE_EXPIRING_SOON, LEASE_EXPIRING_LATER], reference_date=REFERENCE_DATE
    )
    assert health["monthly_rent_expiring_6mo"] == 9000.0, health["monthly_rent_expiring_6mo"]
    assert health["monthly_rent_expiring_12mo"] == 12000.0, health["monthly_rent_expiring_12mo"]

    print("✓ test_health_rent_exposure_windows: PASS")


def test_health_empty_portfolio_does_not_crash():
    health = compute_portfolio_health([], reference_date=REFERENCE_DATE)
    assert health["total_leases"] == 0
    assert health["fully_verified_pct"] is None
    assert health["avg_days_to_expiration"] is None

    print("✓ test_health_empty_portfolio_does_not_crash: PASS")


def test_activity_log_records_and_orders_recent_first():
    """insert_activity/get_recent_activity against an isolated temp DB — never the real dev database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    original_path = database.get_db_path()
    try:
        database.configure(tmp.name)
        database.init_db()

        lease_id = database.insert_lease("test.pdf", {"tenant": _field("Acme Co")})
        database.insert_activity("lease_uploaded", "Uploaded test.pdf", lease_id=lease_id)
        database.insert_activity("comparison_run", "Compared 2 leases")

        recent = database.get_recent_activity(10)
        assert len(recent) == 2
        assert recent[0]["action_type"] == "comparison_run", "most recent first"
        assert recent[1]["lease_id"] == lease_id

        print("✓ test_activity_log_records_and_orders_recent_first: PASS")
    finally:
        database.configure(original_path)
        os.unlink(tmp.name)


def test_activity_log_survives_lease_deletion():
    """
    Deleting a lease must not be blocked by its own activity history, and
    the history entry must survive with lease_id nulled out rather than
    being deleted itself or violating a foreign-key constraint.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    original_path = database.get_db_path()
    try:
        database.configure(tmp.name)
        database.init_db()

        lease_id = database.insert_lease("doomed.pdf", {"tenant": _field("Acme Co")})
        database.insert_activity("lease_uploaded", "Uploaded doomed.pdf", lease_id=lease_id)

        database.delete_lease(lease_id)  # must not raise

        recent = database.get_recent_activity(10)
        assert len(recent) == 1
        assert recent[0]["description"] == "Uploaded doomed.pdf"
        assert recent[0]["lease_id"] is None, "lease_id must be nulled, not left dangling"

        print("✓ test_activity_log_survives_lease_deletion: PASS")
    finally:
        database.configure(original_path)
        os.unlink(tmp.name)


def test_activity_log_limit_is_clamped():
    """A bogus/huge limit must not force an unbounded query."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    original_path = database.get_db_path()
    try:
        database.configure(tmp.name)
        database.init_db()

        for i in range(5):
            database.insert_activity("lease_uploaded", f"Uploaded lease{i}.pdf")

        assert len(database.get_recent_activity(0)) >= 1, "limit below 1 must be clamped up, not return nothing"
        assert len(database.get_recent_activity(100000)) == 5, "asking for more than exist just returns what's there"

        print("✓ test_activity_log_limit_is_clamped: PASS")
    finally:
        database.configure(original_path)
        os.unlink(tmp.name)


if __name__ == "__main__":
    test_expiring_soon_window()
    test_missing_data_flags_incomplete_leases()
    test_unusual_terms_reuses_risk_engine()
    test_attention_items_empty_portfolio()
    test_health_verified_count_matches_attention()
    test_health_excludes_already_expired_from_days_remaining()
    test_health_rent_exposure_windows()
    test_health_empty_portfolio_does_not_crash()
    test_activity_log_records_and_orders_recent_first()
    test_activity_log_survives_lease_deletion()
    test_activity_log_limit_is_clamped()
    print("\nAll dashboard-feature tests passed.")
