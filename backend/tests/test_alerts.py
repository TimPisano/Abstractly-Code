"""
Tests for the proactive alerting system: database.py's alerts CRUD,
app/alerts.py's four detectors + generate_alerts orchestration, and
the GET/POST /alerts routes.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_discrepancies.py.
"""

import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES
from app.alerts import generate_alerts, get_alert_digest, detect_all_candidates

REF_DATE = date(2026, 6, 1)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _fields(**overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            value = overrides[name]
            result[name] = {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


def _insert(**overrides):
    return database.insert_lease("lease.pdf", _fields(**overrides))


def _get_all():
    return database.get_all_effective_leases()


# ------------------------------------------------------------------
# database.py CRUD
# ------------------------------------------------------------------

def test_upsert_creates_active_alert_on_first_seen():
    db_path = _fresh_temp_db()
    try:
        alert_id = database.upsert_alert(
            alert_type="lease_expiration", natural_key="k1", severity="high",
            title="t", message="m", details={"x": 1}, lease_id=1,
        )
        alert = database.get_alert(alert_id)
        assert alert["status"] == "active"
        assert alert["first_detected_at"] == alert["last_seen_at"]
    finally:
        os.unlink(db_path)
    print("✓ test_upsert_creates_active_alert_on_first_seen: PASS")


def test_upsert_never_reactivates_a_dismissed_alert():
    db_path = _fresh_temp_db()
    try:
        alert_id = database.upsert_alert(
            alert_type="tenant_concentration", natural_key="k1", severity="high", title="t", message="m", details={},
        )
        database.dismiss_alert(alert_id, "Jane Analyst", "Aware, acceptable risk for now.")
        assert database.get_alert(alert_id)["status"] == "dismissed"

        database.upsert_alert(
            alert_type="tenant_concentration", natural_key="k1", severity="high", title="t2", message="m2 (recomputed)", details={"pct": 30},
        )
        alert = database.get_alert(alert_id)
        assert alert["status"] == "dismissed", "recomputing must NEVER silently un-dismiss"
        assert alert["message"] == "m2 (recomputed)", "snapshot must still refresh"
    finally:
        os.unlink(db_path)
    print("✓ test_upsert_never_reactivates_a_dismissed_alert: PASS")


def test_upsert_reactivates_an_auto_resolved_alert_if_condition_recurs():
    db_path = _fresh_temp_db()
    try:
        alert_id = database.upsert_alert(
            alert_type="below_market_rent", natural_key="k1", severity="medium", title="t", message="m", details={},
        )
        database.auto_resolve_alert(alert_id)
        assert database.get_alert(alert_id)["status"] == "auto_resolved"

        database.upsert_alert(
            alert_type="below_market_rent", natural_key="k1", severity="high", title="t2", message="m2", details={},
        )
        alert = database.get_alert(alert_id)
        assert alert["status"] == "active", "a genuinely recurring condition must come back as active"
        assert alert["severity"] == "high"
    finally:
        os.unlink(db_path)
    print("✓ test_upsert_reactivates_an_auto_resolved_alert_if_condition_recurs: PASS")


def test_auto_resolve_only_transitions_from_active():
    db_path = _fresh_temp_db()
    try:
        alert_id = database.upsert_alert(alert_type="lease_expiration", natural_key="k1", severity="high", title="t", message="m", details={})
        database.dismiss_alert(alert_id, "Jane")
        assert database.auto_resolve_alert(alert_id) is False, "must not touch a dismissed alert"
        assert database.get_alert(alert_id)["status"] == "dismissed"
    finally:
        os.unlink(db_path)
    print("✓ test_auto_resolve_only_transitions_from_active: PASS")


def test_dismiss_nonexistent_alert_returns_false():
    db_path = _fresh_temp_db()
    try:
        assert database.dismiss_alert(999999, "someone") is False
    finally:
        os.unlink(db_path)
    print("✓ test_dismiss_nonexistent_alert_returns_false: PASS")


def test_list_alerts_filters_and_severity_ordering():
    db_path = _fresh_temp_db()
    try:
        low_id = database.upsert_alert(alert_type="lease_expiration", natural_key="a", severity="low", title="t", message="m", details={}, lease_id=1)
        high_id = database.upsert_alert(alert_type="lease_expiration", natural_key="b", severity="high", title="t", message="m", details={}, lease_id=1)
        database.upsert_alert(alert_type="tenant_concentration", natural_key="c", severity="medium", title="t", message="m", details={})
        database.dismiss_alert(low_id, "Jane")

        all_alerts = database.list_alerts()
        assert len(all_alerts) == 3
        assert all_alerts[0]["id"] == high_id, "high severity must sort first"

        assert len(database.list_alerts(status="active")) == 2
        assert len(database.list_alerts(status="dismissed")) == 1
        assert len(database.list_alerts(alert_type="tenant_concentration")) == 1
        assert len(database.list_alerts(lease_id=1)) == 2
        assert len(database.list_alerts(severity="high")) == 1
    finally:
        os.unlink(db_path)
    print("✓ test_list_alerts_filters_and_severity_ordering: PASS")


# ------------------------------------------------------------------
# Edge case: no alerts (empty/healthy portfolio)
# ------------------------------------------------------------------

def test_generate_alerts_empty_portfolio_produces_nothing():
    db_path = _fresh_temp_db()
    try:
        result = generate_alerts(reference_date=REF_DATE)
        assert result == {"created": 0, "refreshed": 0, "auto_resolved": 0, "active_count": 0, "by_severity": {"high": 0, "medium": 0, "low": 0}}
        assert database.list_alerts() == []
    finally:
        os.unlink(db_path)
    print("✓ test_generate_alerts_empty_portfolio_produces_nothing: PASS")


def test_generate_alerts_healthy_portfolio_produces_nothing():
    """A portfolio with real leases but nothing wrong: no near-term expirations, no discrepancies, no below-market rent, no tenant over any threshold (5 even tenants, each 20% -- below the 25%/15% thresholds)."""
    db_path = _fresh_temp_db()
    try:
        for i in range(5):
            _insert(
                tenant=f"Tenant {i}", rent_amount="$4,000.00", property_address=f"{i} Main St",
                square_footage="2,000 sq ft", lease_end_date="January 1, 2030",
            )

        result = generate_alerts(reference_date=REF_DATE)
        assert result["created"] == 0
        assert result["active_count"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_generate_alerts_healthy_portfolio_produces_nothing: PASS")


# ------------------------------------------------------------------
# Each detector, individually
# ------------------------------------------------------------------

def test_lease_expiration_alerts_bucketed_correctly():
    db_path = _fresh_temp_db()
    try:
        id_30 = _insert(tenant="Acme", lease_end_date=(REF_DATE + timedelta(days=20)).strftime("%B %d, %Y"))
        id_60 = _insert(tenant="Beta", lease_end_date=(REF_DATE + timedelta(days=50)).strftime("%B %d, %Y"))
        id_90 = _insert(tenant="Gamma", lease_end_date=(REF_DATE + timedelta(days=80)).strftime("%B %d, %Y"))
        _insert(tenant="Delta", lease_end_date=(REF_DATE + timedelta(days=200)).strftime("%B %d, %Y"))  # outside window -- no alert

        candidates = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        expiration_alerts = {c["lease_id"]: c for c in candidates if c["alert_type"] == "lease_expiration"}

        assert set(expiration_alerts.keys()) == {id_30, id_60, id_90}
        assert expiration_alerts[id_30]["severity"] == "high"
        assert expiration_alerts[id_60]["severity"] == "medium"
        assert expiration_alerts[id_90]["severity"] == "low"
        assert "Acme" in expiration_alerts[id_30]["message"]
    finally:
        os.unlink(db_path)
    print("✓ test_lease_expiration_alerts_bucketed_correctly: PASS")


def test_new_discrepancy_alerts_only_for_open_discrepancies():
    db_path = _fresh_temp_db()
    try:
        lease_id = _insert()  # missing everything -> real missing_clause risk flags
        # Populate discrepancies via the real risk-sync path (same as the live API does)
        from app.discrepancies import sync_lease_risk_flags
        from app.risk_analysis import analyze_lease_risks
        flags = analyze_lease_risks(_get_all()[0]["extracted_fields"], None, None, [])
        flags = sync_lease_risk_flags(lease_id, flags)
        assert flags, "fixture must produce at least one real flag"
        disc_id = flags[0]["discrepancy_id"]

        candidates = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        discrepancy_alerts = [c for c in candidates if c["alert_type"] == "new_discrepancy"]
        assert any(c["natural_key"] == f"new_discrepancy:{disc_id}" for c in discrepancy_alerts)

        database.resolve_discrepancy(disc_id, "lease_document", "confirmed fine", "Jane")
        candidates_after = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        discrepancy_alerts_after = [c for c in candidates_after if c["alert_type"] == "new_discrepancy"]
        assert not any(c["natural_key"] == f"new_discrepancy:{disc_id}" for c in discrepancy_alerts_after), "a resolved discrepancy must not keep generating a candidate"
    finally:
        os.unlink(db_path)
    print("✓ test_new_discrepancy_alerts_only_for_open_discrepancies: PASS")


def test_below_market_rent_alert_uses_loss_to_lease():
    db_path = _fresh_temp_db()
    try:
        _insert(tenant="Premium Co", rent_amount="$10,000.00", property_address="1 Main St", square_footage="1,000 sq ft")  # $10/sqft -- the property's top
        underpriced_id = _insert(tenant="Discount Co", rent_amount="$7,500.00", property_address="1 Main St", square_footage="1,000 sq ft")  # $7.50/sqft -- 25% below

        candidates = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        below_market = [c for c in candidates if c["alert_type"] == "below_market_rent"]
        assert len(below_market) == 1
        assert below_market[0]["lease_id"] == underpriced_id
        assert below_market[0]["severity"] == "high"  # 25% >= 20% high threshold
        assert "Discount Co" in below_market[0]["message"]
    finally:
        os.unlink(db_path)
    print("✓ test_below_market_rent_alert_uses_loss_to_lease: PASS")


def test_below_market_rent_no_comp_no_alert():
    """A single lease at a building with no comp can't compute loss-to-lease -- must not alert on nothing."""
    db_path = _fresh_temp_db()
    try:
        _insert(tenant="Solo Co", rent_amount="$3,000.00", property_address="Only One Here", square_footage="1,000 sq ft")
        candidates = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        assert not [c for c in candidates if c["alert_type"] == "below_market_rent"]
    finally:
        os.unlink(db_path)
    print("✓ test_below_market_rent_no_comp_no_alert: PASS")


def test_tenant_concentration_alert_crosses_25_pct_threshold():
    db_path = _fresh_temp_db()
    try:
        big_tenant_id = _insert(tenant="Mega Corp", rent_amount="$8,000.00")
        _insert(tenant="Small Co A", rent_amount="$1,000.00")
        _insert(tenant="Small Co B", rent_amount="$1,000.00")
        # Mega Corp = 8000 / 10000 = 80% -- well above 25%

        candidates = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        concentration = [c for c in candidates if c["alert_type"] == "tenant_concentration"]
        assert len(concentration) == 1
        assert concentration[0]["severity"] == "high"
        assert "Mega Corp" in concentration[0]["title"]
        assert concentration[0]["lease_id"] is None, "concentration is portfolio-wide, not tied to one lease"
    finally:
        os.unlink(db_path)
    print("✓ test_tenant_concentration_alert_crosses_25_pct_threshold: PASS")


def test_tenant_concentration_exactly_at_threshold_still_alerts():
    """>= not >: landing exactly on the 25% threshold counts as crossing it, not just going over it."""
    db_path = _fresh_temp_db()
    try:
        _insert(tenant="Even A", rent_amount="$2,500.00")
        _insert(tenant="Even B", rent_amount="$2,500.00")
        _insert(tenant="Even C", rent_amount="$2,500.00")
        _insert(tenant="Even D", rent_amount="$2,500.00")
        # each exactly 25%

        candidates = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        concentration = [c for c in candidates if c["alert_type"] == "tenant_concentration"]
        assert len(concentration) == 4
        assert all(c["severity"] == "high" for c in concentration)
    finally:
        os.unlink(db_path)
    print("✓ test_tenant_concentration_exactly_at_threshold_still_alerts: PASS")


def test_tenant_concentration_evenly_split_stays_quiet():
    db_path = _fresh_temp_db()
    try:
        for i in range(5):
            _insert(tenant=f"Tenant {i}", rent_amount="$2,000.00")  # exactly 20% each -- below both thresholds
        candidates = detect_all_candidates(_get_all(), reference_date=REF_DATE)
        assert not [c for c in candidates if c["alert_type"] == "tenant_concentration"]
    finally:
        os.unlink(db_path)
    print("✓ test_tenant_concentration_evenly_split_stays_quiet: PASS")


# ------------------------------------------------------------------
# Edge case: many alerts at once
# ------------------------------------------------------------------

def test_generate_alerts_many_at_once_across_all_four_types():
    db_path = _fresh_temp_db()
    try:
        # Expiration
        _insert(tenant="Expiring Co", lease_end_date=(REF_DATE + timedelta(days=10)).strftime("%B %d, %Y"))
        # Below-market rent (needs a comp)
        _insert(tenant="Top Co", rent_amount="$10,000.00", property_address="1 Main St", square_footage="1,000 sq ft")
        _insert(tenant="Cheap Co", rent_amount="$6,000.00", property_address="1 Main St", square_footage="1,000 sq ft")
        # Tenant concentration
        _insert(tenant="Dominant Co", rent_amount="$50,000.00")
        # Discrepancy (missing everything -> real flags)
        disc_lease_id = _insert()
        from app.discrepancies import sync_lease_risk_flags
        from app.risk_analysis import analyze_lease_risks
        disc_lease = database.get_effective_lease(disc_lease_id)
        flags = analyze_lease_risks(disc_lease["extracted_fields"], None, None, [])
        sync_lease_risk_flags(disc_lease_id, flags)

        result = generate_alerts(reference_date=REF_DATE)
        assert result["created"] >= 4, f"expected alerts across all 4 types, got {result}"
        assert result["active_count"] == result["created"]

        by_type = {a["alert_type"] for a in database.list_alerts()}
        assert by_type == {"lease_expiration", "below_market_rent", "tenant_concentration", "new_discrepancy"}
    finally:
        os.unlink(db_path)
    print("✓ test_generate_alerts_many_at_once_across_all_four_types: PASS")


def test_generate_alerts_is_idempotent():
    db_path = _fresh_temp_db()
    try:
        _insert(tenant="Expiring Co", lease_end_date=(REF_DATE + timedelta(days=10)).strftime("%B %d, %Y"))
        first = generate_alerts(reference_date=REF_DATE)
        second = generate_alerts(reference_date=REF_DATE)
        assert first["created"] == 1
        assert second["created"] == 0
        assert second["refreshed"] == 1
        assert len(database.list_alerts()) == 1, "re-running must not create duplicates"
    finally:
        os.unlink(db_path)
    print("✓ test_generate_alerts_is_idempotent: PASS")


# ------------------------------------------------------------------
# Edge case: alerts that get resolved (auto) / dismissed (manual)
# ------------------------------------------------------------------

def test_alert_auto_resolves_when_condition_clears():
    db_path = _fresh_temp_db()
    try:
        lease_id = _insert(tenant="Renewing Co", lease_end_date=(REF_DATE + timedelta(days=10)).strftime("%B %d, %Y"))
        first = generate_alerts(reference_date=REF_DATE)
        assert first["created"] == 1
        alert = database.list_alerts()[0]
        assert alert["status"] == "active"

        # The lease gets renewed/extended well past the window (simulating a re-upload)
        database.get_connection()
        conn = database.get_connection()
        import json as _json
        fields = dict(_fields(tenant="Renewing Co", lease_end_date=(REF_DATE + timedelta(days=900)).strftime("%B %d, %Y")))
        conn.execute("UPDATE leases SET extracted_fields = ? WHERE id = ?", (_json.dumps(fields), lease_id))
        conn.commit()
        conn.close()

        second = generate_alerts(reference_date=REF_DATE)
        assert second["auto_resolved"] == 1
        assert database.get_alert(alert["id"])["status"] == "auto_resolved"
    finally:
        os.unlink(db_path)
    print("✓ test_alert_auto_resolves_when_condition_clears: PASS")


def test_alert_dismiss_is_permanent_across_regeneration():
    db_path = _fresh_temp_db()
    try:
        _insert(tenant="Persistent Co", lease_end_date=(REF_DATE + timedelta(days=10)).strftime("%B %d, %Y"))
        generate_alerts(reference_date=REF_DATE)
        alert = database.list_alerts()[0]

        database.dismiss_alert(alert["id"], "Jane Analyst", "Already renewing, tracked elsewhere.")
        assert database.get_alert(alert["id"])["status"] == "dismissed"

        # Condition is UNCHANGED (still expiring soon) -- regenerating must not un-dismiss it
        result = generate_alerts(reference_date=REF_DATE)
        assert database.get_alert(alert["id"])["status"] == "dismissed"
        assert result["active_count"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_alert_dismiss_is_permanent_across_regeneration: PASS")


def test_get_alert_digest():
    db_path = _fresh_temp_db()
    try:
        database.upsert_alert(alert_type="lease_expiration", natural_key="a", severity="high", title="t", message="m", details={})
        database.upsert_alert(alert_type="tenant_concentration", natural_key="b", severity="medium", title="t", message="m", details={})
        dismissed_id = database.upsert_alert(alert_type="below_market_rent", natural_key="c", severity="low", title="t", message="m", details={})
        database.dismiss_alert(dismissed_id, "Jane")

        digest = get_alert_digest()
        assert digest["active_count"] == 2
        assert digest["by_severity"] == {"high": 1, "medium": 1, "low": 0}
        assert digest["by_type"]["lease_expiration"] == 1
        assert digest["by_type"]["below_market_rent"] == 0, "dismissed alert must not count toward the active digest"
    finally:
        os.unlink(db_path)
    print("✓ test_get_alert_digest: PASS")


# ------------------------------------------------------------------
# API routes
# ------------------------------------------------------------------

def test_generate_route_and_list_route():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        _insert(tenant="Expiring Co", lease_end_date=(date.today() + timedelta(days=10)).strftime("%B %d, %Y"))

        resp = client.post("/alerts/generate")
        assert resp.status_code == 200
        assert resp.get_json()["created"] == 1

        resp = client.get("/alerts")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

        resp = client.get("/alerts?status=active")
        assert len(resp.get_json()) == 1

        resp = client.get("/alerts?status=bogus")
        assert resp.status_code == 400

        resp = client.get("/alerts?severity=bogus")
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_generate_route_and_list_route: PASS")


def test_get_and_dismiss_alert_routes():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        alert_id = database.upsert_alert(alert_type="lease_expiration", natural_key="a", severity="high", title="t", message="m", details={})

        resp = client.get(f"/alerts/{alert_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "active"

        resp = client.get("/alerts/999999")
        assert resp.status_code == 404

        resp = client.post(f"/alerts/{alert_id}/dismiss", json={})
        assert resp.status_code == 400
        assert "dismissed_by" in resp.get_json()["error"]

        resp = client.post(f"/alerts/{alert_id}/dismiss", json={"dismissed_by": "Jane Analyst", "note": "handled"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "dismissed"
        assert data["dismissed_by"] == "Jane Analyst"
        assert data["dismissal_note"] == "handled"

        resp = client.post("/alerts/999999/dismiss", json={"dismissed_by": "x"})
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_get_and_dismiss_alert_routes: PASS")


def test_summary_route():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        database.upsert_alert(alert_type="lease_expiration", natural_key="a", severity="high", title="t", message="m", details={})
        resp = client.get("/alerts/summary")
        assert resp.status_code == 200
        assert resp.get_json()["active_count"] == 1
    finally:
        os.unlink(db_path)
    print("✓ test_summary_route: PASS")


if __name__ == "__main__":
    test_upsert_creates_active_alert_on_first_seen()
    test_upsert_never_reactivates_a_dismissed_alert()
    test_upsert_reactivates_an_auto_resolved_alert_if_condition_recurs()
    test_auto_resolve_only_transitions_from_active()
    test_dismiss_nonexistent_alert_returns_false()
    test_list_alerts_filters_and_severity_ordering()
    test_generate_alerts_empty_portfolio_produces_nothing()
    test_generate_alerts_healthy_portfolio_produces_nothing()
    test_lease_expiration_alerts_bucketed_correctly()
    test_new_discrepancy_alerts_only_for_open_discrepancies()
    test_below_market_rent_alert_uses_loss_to_lease()
    test_below_market_rent_no_comp_no_alert()
    test_tenant_concentration_alert_crosses_25_pct_threshold()
    test_tenant_concentration_exactly_at_threshold_still_alerts()
    test_tenant_concentration_evenly_split_stays_quiet()
    test_generate_alerts_many_at_once_across_all_four_types()
    test_generate_alerts_is_idempotent()
    test_alert_auto_resolves_when_condition_clears()
    test_alert_dismiss_is_permanent_across_regeneration()
    test_get_alert_digest()
    test_generate_route_and_list_route()
    test_get_and_dismiss_alert_routes()
    test_summary_route()
    print("\nAll alert tests passed.")
