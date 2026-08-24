"""
Tests for the discrepancy resolution system: database.py's
discrepancies/discrepancy_resolutions CRUD, app/discrepancies.py's
natural-key derivation + sync/annotate logic, and the
GET/POST /discrepancies routes.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_lease_naming_and_tags.py.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES
from app.discrepancies import sync_lease_risk_flags, sync_rent_roll_reconciliation, sync_t12_reconciliation

FIXTURES_DIR = os.path.dirname(__file__)


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


# ------------------------------------------------------------------
# database.py: upsert / list / resolve / reopen
# ------------------------------------------------------------------

def test_upsert_creates_open_discrepancy_on_first_seen():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("base.pdf", _fields())
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k1", category="missing_clause",
            message="No insurance clause", details={"x": 1}, lease_id=lease_id, field="insurance_requirements", severity="medium",
        )
        disc = database.get_discrepancy(disc_id)
        assert disc["status"] == "open"
        assert disc["first_detected_at"] == disc["last_seen_at"]
    finally:
        os.unlink(db_path)
    print("✓ test_upsert_creates_open_discrepancy_on_first_seen: PASS")


def test_upsert_same_natural_key_updates_snapshot_but_not_status():
    db_path = _fresh_temp_db()
    try:
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k1", category="below_market_rent",
            message="20% below", details={"pct": 20}, lease_id=1, field="rent_amount", severity="medium",
        )
        database.resolve_discrepancy(disc_id, "lease_document", "confirmed accurate", "Jane Analyst")
        assert database.get_discrepancy(disc_id)["status"] == "resolved"

        disc_id_2 = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k1", category="below_market_rent",
            message="22% below (recomputed)", details={"pct": 22}, lease_id=1, field="rent_amount", severity="medium",
        )
        assert disc_id_2 == disc_id, "same natural_key must resolve to the same row"
        disc = database.get_discrepancy(disc_id)
        assert disc["status"] == "resolved", "recomputing must NOT silently un-resolve"
        assert disc["message"] == "22% below (recomputed)", "snapshot must still refresh"
        assert disc["details"]["pct"] == 22
    finally:
        os.unlink(db_path)
    print("✓ test_upsert_same_natural_key_updates_snapshot_but_not_status: PASS")


def test_resolve_then_reopen_full_permanent_history():
    db_path = _fresh_temp_db()
    try:
        disc_id = database.upsert_discrepancy(
            discrepancy_type="rent_roll_reconciliation", natural_key="k2", category="rent_roll_reconciliation",
            message="tenant mismatch", details={}, lease_id=1, related_lease_id=2, field="tenant",
        )
        database.resolve_discrepancy(disc_id, "rent_roll", "rent roll is current, lease PDF is stale", "Jane Analyst", "jane@firm.com")
        assert database.get_discrepancy(disc_id)["status"] == "resolved"

        reopen_result = database.reopen_discrepancy(disc_id, "actually need to double check this", "Bob Reviewer")
        assert reopen_result is not None
        assert database.get_discrepancy(disc_id)["status"] == "open"

        database.resolve_discrepancy(disc_id, "lease_document", "lease PDF was right after all", "Bob Reviewer")

        history = database.get_discrepancy_resolutions(disc_id)
        assert len(history) == 3, "every action must be permanently logged, nothing overwritten"
        assert [h["action"] for h in history] == ["resolved", "reopened", "resolved"]
        assert history[0]["resolved_by"] == "Jane Analyst"
        assert history[0]["resolved_by_email"] == "jane@firm.com"
        assert history[0]["correct_source"] == "rent_roll"
        assert history[2]["correct_source"] == "lease_document"
    finally:
        os.unlink(db_path)
    print("✓ test_resolve_then_reopen_full_permanent_history: PASS")


def test_resolve_nonexistent_discrepancy_returns_none():
    db_path = _fresh_temp_db()
    try:
        assert database.resolve_discrepancy(999999, "x", "note", "someone") is None
    finally:
        os.unlink(db_path)
    print("✓ test_resolve_nonexistent_discrepancy_returns_none: PASS")


def test_list_discrepancies_filters():
    db_path = _fresh_temp_db()
    try:
        id1 = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="a", category="missing_clause",
            message="m1", details={}, lease_id=1,
        )
        id2 = database.upsert_discrepancy(
            discrepancy_type="cross_lease_mismatch", natural_key="b", category="cross_lease_mismatch",
            message="m2", details={}, lease_id=1, related_lease_id=2,
        )
        database.upsert_discrepancy(
            discrepancy_type="rent_roll_reconciliation", natural_key="c", category="rent_roll_reconciliation",
            message="m3", details={}, lease_id=3,
        )
        database.resolve_discrepancy(id1, "x", "note", "someone")

        assert len(database.list_discrepancies()) == 3
        assert {d["id"] for d in database.list_discrepancies(status="open")} == {id2, database.list_discrepancies(discrepancy_type="rent_roll_reconciliation")[0]["id"]}
        assert len(database.list_discrepancies(status="resolved")) == 1
        assert len(database.list_discrepancies(lease_id=1)) == 2, "lease_id must match either lease_id or related_lease_id"
        assert len(database.list_discrepancies(discrepancy_type="cross_lease_mismatch")) == 1
    finally:
        os.unlink(db_path)
    print("✓ test_list_discrepancies_filters: PASS")


# ------------------------------------------------------------------
# app/discrepancies.py: natural-key derivation + annotation
# ------------------------------------------------------------------

def test_sync_lease_risk_flags_annotates_and_persists():
    db_path = _fresh_temp_db()
    try:
        flags = [
            {"severity": "medium", "category": "missing_clause", "field": "insurance_requirements", "message": "No insurance clause"},
            {"severity": "high", "category": "below_market_rent", "field": "rent_amount", "message": "22% below"},
        ]
        result = sync_lease_risk_flags(5, flags)
        assert all(f["resolution_status"] == "open" for f in result)
        assert all(f["resolution"] is None for f in result)
        assert all(f["discrepancy_id"] is not None for f in result)
        assert len(database.list_discrepancies(lease_id=5)) == 2
    finally:
        os.unlink(db_path)
    print("✓ test_sync_lease_risk_flags_annotates_and_persists: PASS")


def test_sync_lease_risk_flags_same_category_field_gets_distinct_natural_keys():
    """A lease can raise two different date_inconsistency/lease_end_date flags (date_range check + date_candidate_conflict check) -- they must not collide onto one discrepancy."""
    db_path = _fresh_temp_db()
    try:
        flags = [
            {"severity": "high", "category": "date_inconsistency", "field": "lease_end_date", "message": "end before start"},
            {"severity": "high", "category": "date_inconsistency", "field": "lease_end_date", "message": "multiple end dates found"},
        ]
        result = sync_lease_risk_flags(7, flags)
        assert result[0]["discrepancy_id"] != result[1]["discrepancy_id"]
        assert len(database.list_discrepancies(lease_id=7)) == 2
    finally:
        os.unlink(db_path)
    print("✓ test_sync_lease_risk_flags_same_category_field_gets_distinct_natural_keys: PASS")


def test_sync_cross_lease_mismatch_dedupes_across_both_leases_perspectives():
    """The same pair mismatch, seen from lease A's flag list and from lease B's flag list, must resolve to the SAME discrepancy row."""
    db_path = _fresh_temp_db()
    try:
        flag_from_a = {"severity": "high", "category": "cross_lease_mismatch", "field": "rent_amount", "message": "A vs B", "other_lease_id": 20}
        flag_from_b = {"severity": "high", "category": "cross_lease_mismatch", "field": "rent_amount", "message": "B vs A", "other_lease_id": 10}

        result_a = sync_lease_risk_flags(10, [flag_from_a])
        result_b = sync_lease_risk_flags(20, [flag_from_b])

        assert result_a[0]["discrepancy_id"] == result_b[0]["discrepancy_id"]
        assert len(database.list_discrepancies(discrepancy_type="cross_lease_mismatch")) == 1

        # resolving from lease A's perspective must show as resolved from lease B's perspective too
        database.resolve_discrepancy(result_a[0]["discrepancy_id"], "lease_document_a", "confirmed A is right", "Reviewer")
        re_synced_b = sync_lease_risk_flags(20, [dict(flag_from_b)])
        assert re_synced_b[0]["resolution_status"] == "resolved"
        assert re_synced_b[0]["resolution"]["correct_source"] == "lease_document_a"
    finally:
        os.unlink(db_path)
    print("✓ test_sync_cross_lease_mismatch_dedupes_across_both_leases_perspectives: PASS")


def test_sync_rent_roll_reconciliation():
    db_path = _fresh_temp_db()
    try:
        mismatches = [
            {"rent_roll_lease_id": 1, "lease_document_id": 2, "address": "123 Main St", "field": "tenant", "rent_roll_value": "Acme", "lease_document_value": "Acme Inc"},
        ]
        result = sync_rent_roll_reconciliation(mismatches)
        assert result[0]["resolution_status"] == "open"
        disc = database.list_discrepancies(discrepancy_type="rent_roll_reconciliation")
        assert len(disc) == 1
        assert disc[0]["lease_id"] == 1
        assert disc[0]["related_lease_id"] == 2
    finally:
        os.unlink(db_path)
    print("✓ test_sync_rent_roll_reconciliation: PASS")


def test_sync_t12_reconciliation_only_persists_when_flagged_or_already_tracked():
    db_path = _fresh_temp_db()
    try:
        unflagged = {"property_address": "500 Elm St", "flagged": False, "rent_roll_annual_rent": 100000, "t12_annual_rental_income": 101000}
        result = sync_t12_reconciliation(dict(unflagged))
        assert "discrepancy_id" not in result, "an unflagged result with no history must not create a discrepancy"
        assert database.list_discrepancies(discrepancy_type="t12_reconciliation") == []

        flagged = {"property_address": "500 Elm St", "flagged": True, "rent_roll_annual_rent": 100000, "t12_annual_rental_income": 130000}
        result = sync_t12_reconciliation(dict(flagged))
        assert result["resolution_status"] == "open"
        assert len(database.list_discrepancies(discrepancy_type="t12_reconciliation")) == 1

        # Now that a discrepancy exists for this property, even an unflagged recheck should still surface its (still-open) status
        result = sync_t12_reconciliation(dict(unflagged))
        assert result["resolution_status"] == "open"
        assert len(database.list_discrepancies(discrepancy_type="t12_reconciliation")) == 1, "must update the SAME row, not create a second one"
    finally:
        os.unlink(db_path)
    print("✓ test_sync_t12_reconciliation_only_persists_when_flagged_or_already_tracked: PASS")


# ------------------------------------------------------------------
# API routes
# ------------------------------------------------------------------

def test_lease_risks_route_flags_carry_resolution_status():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())  # missing everything -> missing_clause flags
        resp = client.get(f"/leases/{lease_id}/risks")
        assert resp.status_code == 200
        flags = resp.get_json()
        assert flags, "expected at least one missing_clause flag"
        assert all("discrepancy_id" in f and "resolution_status" in f for f in flags)
    finally:
        os.unlink(db_path)
    print("✓ test_lease_risks_route_flags_carry_resolution_status: PASS")


def test_resolve_route_happy_path_and_persists():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())
        flags = client.get(f"/leases/{lease_id}/risks").get_json()
        disc_id = flags[0]["discrepancy_id"]

        resp = client.post(f"/discrepancies/{disc_id}/resolve", json={
            "correct_source": "lease_document", "note": "confirmed via source PDF", "resolved_by": "Jane Analyst", "resolved_by_email": "jane@firm.com",
        })
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["status"] == "resolved"
        assert len(data["resolutions"]) == 1
        assert data["resolutions"][0]["resolved_by"] == "Jane Analyst"

        # Re-fetching the same lease's risks must now show it resolved -- no manual re-read needed
        flags_again = client.get(f"/leases/{lease_id}/risks").get_json()
        matching = next(f for f in flags_again if f["discrepancy_id"] == disc_id)
        assert matching["resolution_status"] == "resolved"
        assert matching["resolution"]["note"] == "confirmed via source PDF"
    finally:
        os.unlink(db_path)
    print("✓ test_resolve_route_happy_path_and_persists: PASS")


def test_resolve_route_missing_fields_returns_400():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k", category="missing_clause", message="m", details={}, lease_id=1,
        )
        resp = client.post(f"/discrepancies/{disc_id}/resolve", json={"note": "only a note"})
        assert resp.status_code == 400
        assert "correct_source" in resp.get_json()["error"]
        assert "resolved_by" in resp.get_json()["error"]
    finally:
        os.unlink(db_path)
    print("✓ test_resolve_route_missing_fields_returns_400: PASS")


def test_resolve_route_nonexistent_discrepancy_returns_404():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/discrepancies/999999/resolve", json={"correct_source": "x", "note": "n", "resolved_by": "y"})
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_resolve_route_nonexistent_discrepancy_returns_404: PASS")


def test_reopen_route_requires_currently_resolved():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k", category="missing_clause", message="m", details={}, lease_id=1,
        )
        resp = client.post(f"/discrepancies/{disc_id}/reopen", json={"note": "n", "resolved_by": "y"})
        assert resp.status_code == 400, "cannot reopen an already-open discrepancy"

        client.post(f"/discrepancies/{disc_id}/resolve", json={"correct_source": "x", "note": "n", "resolved_by": "y"})
        resp = client.post(f"/discrepancies/{disc_id}/reopen", json={"note": "need another look", "resolved_by": "z"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "open"
    finally:
        os.unlink(db_path)
    print("✓ test_reopen_route_requires_currently_resolved: PASS")


def test_list_discrepancies_route_filters():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())
        client.get(f"/leases/{lease_id}/risks")  # populates discrepancies

        resp = client.get("/discrepancies")
        assert resp.status_code == 200
        assert len(resp.get_json()) > 0

        resp = client.get(f"/discrepancies?lease_id={lease_id}")
        assert resp.status_code == 200
        assert all(d["lease_id"] == lease_id for d in resp.get_json())

        resp = client.get("/discrepancies?status=bogus")
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_list_discrepancies_route_filters: PASS")


def test_get_discrepancy_route_404_for_nonexistent():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/discrepancies/999999")
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_get_discrepancy_route_404_for_nonexistent: PASS")


if __name__ == "__main__":
    test_upsert_creates_open_discrepancy_on_first_seen()
    test_upsert_same_natural_key_updates_snapshot_but_not_status()
    test_resolve_then_reopen_full_permanent_history()
    test_resolve_nonexistent_discrepancy_returns_none()
    test_list_discrepancies_filters()
    test_sync_lease_risk_flags_annotates_and_persists()
    test_sync_lease_risk_flags_same_category_field_gets_distinct_natural_keys()
    test_sync_cross_lease_mismatch_dedupes_across_both_leases_perspectives()
    test_sync_rent_roll_reconciliation()
    test_sync_t12_reconciliation_only_persists_when_flagged_or_already_tracked()
    test_lease_risks_route_flags_carry_resolution_status()
    test_resolve_route_happy_path_and_persists()
    test_resolve_route_missing_fields_returns_400()
    test_resolve_route_nonexistent_discrepancy_returns_404()
    test_reopen_route_requires_currently_resolved()
    test_list_discrepancies_route_filters()
    test_get_discrepancy_route_404_for_nonexistent()
    print("\nAll discrepancy tests passed.")
