"""
Tests for the portfolio health score: each of the four weighted
components individually, the combined formula against genuinely
different portfolio states (perfect, messy, mixed), and the
GET /portfolio/health-score route.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_alerts.py.
"""

import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app import cache
from app.portfolio import FIELD_NAMES
from app.portfolio_health_score import compute_portfolio_health_score, WEIGHTS

REF_DATE = date(2026, 6, 1)


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


def _fields(confidence="high", **overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            result[name] = {"value": overrides[name], "source": {"page": 1, "quote": "q"}, "confidence": confidence}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


def _all_field_kwargs(prefix=""):
    return {
        "tenant": f"{prefix}Tenant Co", "landlord": f"{prefix}Landlord LLC", "rent_amount": "$5,000.00",
        "lease_start_date": "January 1, 2025", "lease_end_date": "January 1, 2030",
        "property_address": "1 Main St", "security_deposit": "$5,000.00", "cam_charges": "$500.00",
        "rent_escalation": "3% annually", "renewal_options": "1 option of 5 years; 90 days notice",
        "termination_options": "terminable after year 5 of the term; 180 days notice",
        "permitted_use": "office", "exclusivity_clause": "none", "insurance_requirements": "$1,000,000",
        "default_cure_period": "10 days", "square_footage": "1,000 sq ft",
    }


def _uploaded_at_override(lease_id, iso_timestamp):
    conn = database.get_connection()
    conn.execute("UPDATE leases SET uploaded_at = ? WHERE id = ?", (iso_timestamp, lease_id))
    conn.commit()
    conn.close()


def _days_ago(n):
    """A real, valid ISO datetime (with UTC offset) n days before REF_DATE -- matches the exact format insert_lease itself writes (datetime.now(timezone.utc).isoformat())."""
    return datetime.combine(REF_DATE - timedelta(days=n), datetime.min.time(), tzinfo=timezone.utc).isoformat()


# ------------------------------------------------------------------
# Weights sanity
# ------------------------------------------------------------------

def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    print("✓ test_weights_sum_to_one: PASS")


# ------------------------------------------------------------------
# Empty portfolio
# ------------------------------------------------------------------

def test_empty_portfolio_returns_no_data_not_zero():
    db_path = _fresh_temp_db()
    try:
        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["score"] is None
        assert result["rating"] == "No Data"
        assert result["lease_count"] == 0
        for component in result["components"].values():
            assert component["score"] is None
    finally:
        os.unlink(db_path)
    print("✓ test_empty_portfolio_returns_no_data_not_zero: PASS")


# ------------------------------------------------------------------
# Perfect portfolio: every field found, high confidence, no
# discrepancies, uploaded today
# ------------------------------------------------------------------

def test_perfect_portfolio_scores_near_100_excellent():
    db_path = _fresh_temp_db()
    try:
        for i in range(3):
            database.insert_lease(f"lease{i}.pdf", _fields(confidence="high", **_all_field_kwargs(f"L{i} ")))

        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["score"] >= 95, f"a genuinely perfect portfolio should score in the high 90s, got {result['score']}"
        assert result["rating"] == "Excellent"
        assert result["components"]["confidence_distribution"]["score"] == 100.0
        assert result["components"]["source_verification"]["score"] == 100.0
        assert result["components"]["unresolved_discrepancies"]["score"] == 100.0
        assert result["components"]["data_freshness"]["score"] == 100.0
    finally:
        os.unlink(db_path)
    print("✓ test_perfect_portfolio_scores_near_100_excellent: PASS")


# ------------------------------------------------------------------
# Messy portfolio: mostly missing fields, low confidence, many open
# discrepancies, stale uploads
# ------------------------------------------------------------------

def test_messy_portfolio_scores_low_critical():
    db_path = _fresh_temp_db()
    try:
        stale_timestamp = _days_ago(400)

        for i in range(3):
            # Only 2 of 15 fields found, low confidence, missing core fields (no landlord)
            lease_id = database.insert_lease(
                f"messy{i}.pdf",
                _fields(confidence="low", tenant=f"Tenant {i}", rent_amount="$1,000.00"),
            )
            _uploaded_at_override(lease_id, stale_timestamp)

            database.upsert_discrepancy(
                discrepancy_type="lease_risk_flag", natural_key=f"messy-disc-{i}-a", category="missing_clause",
                message="No insurance clause", details={}, lease_id=lease_id, severity="medium",
            )
            database.upsert_discrepancy(
                discrepancy_type="lease_risk_flag", natural_key=f"messy-disc-{i}-b", category="missing_clause",
                message="No default/cure clause", details={}, lease_id=lease_id, severity="medium",
            )

        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["score"] < 40, f"a genuinely messy portfolio should score Critical, got {result['score']} ({result['rating']})"
        assert result["rating"] == "Critical"
        assert result["components"]["source_verification"]["score"] == 0.0, "missing core fields (landlord, dates) -- zero leases should count as fully verified"
        assert result["components"]["data_freshness"]["score"] == 0.0, "every lease is well past the staleness threshold"
        assert result["components"]["unresolved_discrepancies"]["open_count"] == 6
    finally:
        os.unlink(db_path)
    print("✓ test_messy_portfolio_scores_low_critical: PASS")


# ------------------------------------------------------------------
# Mixed portfolio: some good, some bad -- score should land in the
# middle, not at either extreme
# ------------------------------------------------------------------

def test_mixed_portfolio_scores_in_the_middle():
    db_path = _fresh_temp_db()
    try:
        # 2 excellent leases
        for i in range(2):
            database.insert_lease(f"good{i}.pdf", _fields(confidence="high", **_all_field_kwargs(f"Good{i} ")))
        # 2 messy leases: missing core fields, stale, with an open discrepancy each
        stale_timestamp = _days_ago(400)
        for i in range(2):
            lease_id = database.insert_lease(f"bad{i}.pdf", _fields(confidence="low", tenant=f"Bad {i}", rent_amount="$1,000.00"))
            _uploaded_at_override(lease_id, stale_timestamp)
            database.upsert_discrepancy(
                discrepancy_type="lease_risk_flag", natural_key=f"mixed-disc-{i}", category="missing_clause",
                message="No insurance clause", details={}, lease_id=lease_id, severity="medium",
            )

        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert 30 < result["score"] < 80, f"a genuinely mixed portfolio should land in the middle, got {result['score']}"
        assert result["rating"] not in ("Excellent", "Critical")
        # Exactly half fully verified, half stale -- the arithmetic must actually reflect the 50/50 split
        assert result["components"]["source_verification"]["score"] == 50.0
        assert result["components"]["data_freshness"]["score"] == 50.0
    finally:
        os.unlink(db_path)
    print("✓ test_mixed_portfolio_scores_in_the_middle: PASS")


# ------------------------------------------------------------------
# Each component, individually, against a targeted scenario
# ------------------------------------------------------------------

def test_confidence_distribution_gives_partial_credit_for_medium_and_low():
    db_path = _fresh_temp_db()
    try:
        database.insert_lease("a.pdf", _fields(confidence="medium", tenant="Acme"))
        result = compute_portfolio_health_score(reference_date=REF_DATE)
        # 1 of 16 fields found at medium confidence: round((0.6 * 1) / 16 * 100, 1) = 3.8
        assert result["components"]["confidence_distribution"]["score"] == 3.8
    finally:
        os.unlink(db_path)
    print("✓ test_confidence_distribution_gives_partial_credit_for_medium_and_low: PASS")


def test_source_verification_requires_zero_flagged_fields_too():
    """A lease with all core fields present but at least one field flagged for review during validation must NOT count as fully verified."""
    db_path = _fresh_temp_db()
    try:
        fields = _fields(confidence="high", **_all_field_kwargs())
        fields["rent_amount"]["validation_note"] = "Unusually high rent for this property type -- please verify"
        database.insert_lease("a.pdf", fields)
        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["components"]["source_verification"]["score"] == 0.0
        assert result["components"]["source_verification"]["fully_verified_count"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_source_verification_requires_zero_flagged_fields_too: PASS")


def test_unresolved_discrepancies_smooth_decay_not_a_cliff():
    db_path = _fresh_temp_db()
    try:
        lease_ids = [database.insert_lease(f"l{i}.pdf", _fields(**_all_field_kwargs())) for i in range(4)]
        # exactly 4 open discrepancies across 4 leases -> 1.0 per lease -> score should be exactly 50
        for i, lease_id in enumerate(lease_ids):
            database.upsert_discrepancy(
                discrepancy_type="lease_risk_flag", natural_key=f"k{i}", category="missing_clause",
                message="m", details={}, lease_id=lease_id, severity="low",
            )
        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["components"]["unresolved_discrepancies"]["score"] == 50.0
        assert result["components"]["unresolved_discrepancies"]["discrepancies_per_lease"] == 1.0
    finally:
        os.unlink(db_path)
    print("✓ test_unresolved_discrepancies_smooth_decay_not_a_cliff: PASS")


def test_resolved_discrepancies_do_not_count_against_the_score():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("a.pdf", _fields(**_all_field_kwargs()))
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k", category="missing_clause",
            message="m", details={}, lease_id=lease_id, severity="low",
        )
        database.resolve_discrepancy(disc_id, "lease_document", "confirmed fine", "Jane")

        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["components"]["unresolved_discrepancies"]["open_count"] == 0
        assert result["components"]["unresolved_discrepancies"]["score"] == 100.0
    finally:
        os.unlink(db_path)
    print("✓ test_resolved_discrepancies_do_not_count_against_the_score: PASS")


def test_discrepancies_from_deleted_leases_do_not_count_against_a_healthy_current_portfolio():
    """
    Real bug caught live (not by a fresh-temp-DB unit test): discrepancies
    are permanent records that outlive their lease (Item 2's own design --
    they're not cascade-deleted). An unscoped open-discrepancy count would
    keep accumulating forever across a long-lived database's full history,
    swamping any signal from leases actually in the portfolio right now.
    """
    db_path = _fresh_temp_db()
    try:
        old_lease_id = database.insert_lease("old.pdf", _fields(**_all_field_kwargs()))
        for i in range(20):  # a pile of old discrepancies for a lease that's about to be deleted
            database.upsert_discrepancy(
                discrepancy_type="lease_risk_flag", natural_key=f"stale-{i}", category="missing_clause",
                message="m", details={}, lease_id=old_lease_id, severity="low",
            )
        database.delete_lease(old_lease_id)  # discrepancies survive -- by design, see Item 2

        # A brand new, otherwise-perfect current portfolio
        database.insert_lease("current.pdf", _fields(confidence="high", **_all_field_kwargs()))

        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["components"]["unresolved_discrepancies"]["open_count"] == 0, "the 20 orphaned discrepancies from the deleted lease must not count"
        assert result["components"]["unresolved_discrepancies"]["score"] == 100.0
        assert result["score"] >= 95, f"a genuinely healthy current portfolio must not be dragged down by history, got {result['score']}"
    finally:
        os.unlink(db_path)
    print("✓ test_discrepancies_from_deleted_leases_do_not_count_against_a_healthy_current_portfolio: PASS")


def test_portfolio_wide_discrepancy_counts_only_if_its_subject_is_still_current():
    """
    tenant_concentration/t12_reconciliation discrepancies have no
    lease_id at all -- they're facts about a TENANT or an ADDRESS, not
    one lease row, so they can't be scoped by lease id the way the
    other three discrepancy types are. Real bug caught live (second
    accumulation problem, distinct from the lease_id one above): 351
    of these had piled up from tenant names / addresses used across
    this whole project's entire test history that no longer appear
    anywhere in the current portfolio. Must count only when their
    subject is still actually present now.
    """
    db_path = _fresh_temp_db()
    try:
        database.insert_lease("a.pdf", _fields(**_all_field_kwargs()))  # tenant: "Tenant Co"
        database.upsert_discrepancy(
            discrepancy_type="tenant_concentration", natural_key="tc-current", category="tenant_concentration",
            message="Tenant Co is 80% of portfolio rent", details={"tenant": "Tenant Co"}, severity="high",
        )
        database.upsert_discrepancy(
            discrepancy_type="tenant_concentration", natural_key="tc-stale", category="tenant_concentration",
            message="Mega Corp is 80% of portfolio rent", details={"tenant": "Mega Corp"}, severity="high",
        )
        database.upsert_discrepancy(
            discrepancy_type="t12_reconciliation", natural_key="t12-current", category="t12_reconciliation",
            message="T12 mismatch at 1 Main St", details={"property_address": "1 Main St"}, severity="medium",
        )
        database.upsert_discrepancy(
            discrepancy_type="t12_reconciliation", natural_key="t12-stale", category="t12_reconciliation",
            message="T12 mismatch at 999 Long-Gone Ave", details={"property_address": "999 Long-Gone Ave"}, severity="medium",
        )

        result = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result["components"]["unresolved_discrepancies"]["open_count"] == 2, "only the 2 whose subject is still in the current portfolio must count"
    finally:
        os.unlink(db_path)
    print("✓ test_portfolio_wide_discrepancy_counts_only_if_its_subject_is_still_current: PASS")


def test_data_freshness_amendment_counts_as_a_refresh():
    db_path = _fresh_temp_db()
    try:
        old_timestamp = _days_ago(400)
        base_id = database.insert_lease("base.pdf", _fields(**_all_field_kwargs()))
        _uploaded_at_override(base_id, old_timestamp)

        result_before_amendment = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result_before_amendment["components"]["data_freshness"]["score"] == 0.0, "the base lease alone is stale"

        database.insert_lease("amendment.pdf", _fields(rent_amount="$5,500.00"), document_type="amendment", base_lease_id=base_id)
        result_after_amendment = compute_portfolio_health_score(reference_date=REF_DATE)
        assert result_after_amendment["components"]["data_freshness"]["score"] == 100.0, "a recent amendment must count as refreshing the base lease's data"
    finally:
        os.unlink(db_path)
    print("✓ test_data_freshness_amendment_counts_as_a_refresh: PASS")


def test_data_freshness_custom_threshold():
    db_path = _fresh_temp_db()
    try:
        timestamp = _days_ago(45)
        lease_id = database.insert_lease("a.pdf", _fields(**_all_field_kwargs()))
        _uploaded_at_override(lease_id, timestamp)

        result_6mo = compute_portfolio_health_score(reference_date=REF_DATE, staleness_threshold_months=6)
        assert result_6mo["components"]["data_freshness"]["score"] == 100.0, "45 days is fresh under a 6-month threshold"

        result_1mo = compute_portfolio_health_score(reference_date=REF_DATE, staleness_threshold_months=1)
        assert result_1mo["components"]["data_freshness"]["score"] == 0.0, "45 days is stale under a 1-month threshold"
    finally:
        os.unlink(db_path)
    print("✓ test_data_freshness_custom_threshold: PASS")


# ------------------------------------------------------------------
# API route
# ------------------------------------------------------------------

def test_health_score_route():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        resp = client.get("/portfolio/health-score")
        assert resp.status_code == 200
        assert resp.get_json()["rating"] == "No Data"

        # Inserting directly via database.py (this test's own shortcut,
        # not a real upload through the API) doesn't trigger api.py's
        # cache-invalidation hooks -- those only fire on the real
        # mutation ROUTES a real client would hit. Clearing the cache
        # here simulates that side effect for this direct-insert test;
        # see test_cache.py for tests of the real invalidation hooks
        # themselves, through the real routes.
        database.insert_lease("a.pdf", _fields(confidence="high", **_all_field_kwargs()))
        cache.invalidate_all()
        resp = client.get("/portfolio/health-score")
        data = resp.get_json()
        assert data["score"] is not None
        assert "components" in data

        resp = client.get("/portfolio/health-score?staleness_threshold_months=1")
        assert resp.status_code == 200
        assert resp.get_json()["components"]["data_freshness"]["threshold_months"] == 1.0

        resp = client.get("/portfolio/health-score?staleness_threshold_months=not_a_number")
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_health_score_route: PASS")


if __name__ == "__main__":
    test_weights_sum_to_one()
    test_empty_portfolio_returns_no_data_not_zero()
    test_perfect_portfolio_scores_near_100_excellent()
    test_messy_portfolio_scores_low_critical()
    test_mixed_portfolio_scores_in_the_middle()
    test_confidence_distribution_gives_partial_credit_for_medium_and_low()
    test_source_verification_requires_zero_flagged_fields_too()
    test_unresolved_discrepancies_smooth_decay_not_a_cliff()
    test_resolved_discrepancies_do_not_count_against_the_score()
    test_discrepancies_from_deleted_leases_do_not_count_against_a_healthy_current_portfolio()
    test_portfolio_wide_discrepancy_counts_only_if_its_subject_is_still_current()
    test_data_freshness_amendment_counts_as_a_refresh()
    test_data_freshness_custom_threshold()
    test_health_score_route()
    print("\nAll portfolio health score tests passed.")
