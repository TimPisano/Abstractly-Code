"""
Tests for Phase 5 observability: app/extraction_quality.py (pure) and
the GET /extraction-quality/{trend,field-reliability} routes.
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app import extraction_quality as eq
from app.portfolio import FIELD_NAMES


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _fields(**overrides):
    out = {}
    for name in FIELD_NAMES:
        v = overrides.get(name)
        out[name] = ({"value": v, "source": {"page": 1, "quote": "..."}, "confidence": "high"}
                     if v is not None else {"value": None, "source": None, "confidence": None})
    return out


# ----------------------------------------------------------------------
# compute_field_reliability (pure)
# ----------------------------------------------------------------------

def test_field_reliability_combines_training_and_production_signal():
    training_report = {"field_accuracy": [
        {"field": "tenant", "accuracy": 0.98, "n": 60, "importance": 3},
        {"field": "cam_charges", "accuracy": 0.55, "n": 60, "importance": 1},
        {"field": "rent_escalation", "accuracy": 0.9, "n": 60, "importance": 2},
    ]}
    ai_leases = []
    for i in range(10):
        ai_leases.append({"id": i, "extracted_fields": _fields(tenant="Acme", rent_escalation="3% annually", security_deposit="$5,000")})
    # humans corrected security_deposit on 3 of 10 -> 30% correction rate -> weak
    edits = [{"lease_id": i, "field_name": "security_deposit"} for i in range(3)]

    rel = eq.compute_field_reliability(latest_training_report=training_report, ai_extracted_leases=ai_leases, field_edits=edits)

    assert rel["tenant"]["reliability"] == "strong"
    assert rel["cam_charges"]["reliability"] == "weak", "low training accuracy -> weak"
    assert rel["rent_escalation"]["reliability"] == "mixed", "0.9 training accuracy -> mixed"
    assert rel["security_deposit"]["reliability"] == "weak", "high production correction rate -> weak"
    assert rel["security_deposit"]["production_correction_rate"] == 0.3
    assert rel["cam_charges"]["advice"]
    print("✓ test_field_reliability_combines_training_and_production_signal: PASS")


def test_field_reliability_with_no_training_data_falls_back_to_production_only():
    ai_leases = [{"id": i, "extracted_fields": _fields(tenant="Acme")} for i in range(8)]
    rel = eq.compute_field_reliability(latest_training_report=None, ai_extracted_leases=ai_leases, field_edits=[])
    assert rel["tenant"]["reliability"] == "strong"
    assert rel["tenant"]["training_accuracy"] is None
    print("✓ test_field_reliability_with_no_training_data_falls_back_to_production_only: PASS")


def test_field_reliability_ignores_edits_on_non_ai_leases():
    ai_leases = [{"id": 1, "extracted_fields": _fields(tenant="Acme")}]
    edits = [{"lease_id": 999, "field_name": "tenant"}]  # lease not in the AI set
    rel = eq.compute_field_reliability(latest_training_report=None, ai_extracted_leases=ai_leases, field_edits=edits)
    assert rel["tenant"]["production_corrections"] == 0
    print("✓ test_field_reliability_ignores_edits_on_non_ai_leases: PASS")


# ----------------------------------------------------------------------
# compute_quality_trend (pure)
# ----------------------------------------------------------------------

def test_quality_trend_shows_round_progression_and_production_daily():
    rounds = [
        {"round_label": "baseline", "created_at": "2026-09-01T00:00:00", "prompt_version": "v1", "model": "m",
         "overall_accuracy": 0.80, "high_conf_wrong_count": 12, "high_conf_wrong_rate": 0.1,
         "calibration_gap": 0.2, "p_correct_given_high": 0.9, "changed_this_round": "initial"},
        {"round_label": "r2", "created_at": "2026-09-02T00:00:00", "prompt_version": "v2", "model": "m",
         "overall_accuracy": 0.88, "high_conf_wrong_count": 5, "high_conf_wrong_rate": 0.04,
         "calibration_gap": 0.4, "p_correct_given_high": 0.97, "changed_this_round": "tightened confidence rubric"},
    ]
    ai_runs = [
        {"created_at": "2026-09-03T10:00:00", "status": "ok", "latency_ms": 4000, "high_count": 8, "medium_count": 4, "low_count": 3, "not_found_count": 0},
        {"created_at": "2026-09-03T11:00:00", "status": "error", "latency_ms": None, "high_count": 0, "medium_count": 0, "low_count": 0, "not_found_count": 0},
    ]
    trend = eq.compute_quality_trend(training_rounds=rounds, ai_runs=ai_runs)
    assert trend["accuracy_delta_vs_previous_round"] == 0.08
    assert trend["latest_round"]["prompt_version"] == "v2"
    assert trend["latest_round"]["changed_this_round"] == "tightened confidence rubric"
    day = trend["production_daily"][0]
    assert day["runs"] == 2 and day["error_rate"] == 0.5
    assert day["confidence_mix"]["high"] == round(8 / 15, 3)
    print("✓ test_quality_trend_shows_round_progression_and_production_daily: PASS")


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

def _client(role="analyst", is_owner=False):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"user_id": 1, "email": "a@example.com", "name": "A", "role": role, "is_owner": is_owner})
    return c


def test_trend_route_owner_only():
    db_path = _fresh_temp_db()
    try:
        # require_owner() returns 404 (not 403) to non-owners by design -- the route must be undiscoverable
        assert _client(role="admin", is_owner=False).get("/extraction-quality/trend").status_code == 404
        resp = _client(role="admin", is_owner=True).get("/extraction-quality/trend")
        assert resp.status_code == 200
        assert resp.get_json()["has_training_data"] is False
    finally:
        os.unlink(db_path)
    print("✓ test_trend_route_owner_only: PASS")


def test_field_reliability_route_available_to_any_logged_in_user():
    db_path = _fresh_temp_db()
    try:
        database.record_training_round(
            round_label="baseline",
            report={"field_accuracy": [{"field": "cam_charges", "accuracy": 0.5, "n": 20, "importance": 1}],
                    "calibration": {}},
        )
        resp = _client(role="viewer").get("/extraction-quality/field-reliability")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["based_on_training_round"] == "baseline"
        assert body["fields"]["cam_charges"]["reliability"] == "weak"
        assert body["fields"]["tenant"]["reliability"] == "strong"

        assert app.test_client().get("/extraction-quality/field-reliability").status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_field_reliability_route_available_to_any_logged_in_user: PASS")


if __name__ == "__main__":
    test_field_reliability_combines_training_and_production_signal()
    test_field_reliability_with_no_training_data_falls_back_to_production_only()
    test_field_reliability_ignores_edits_on_non_ai_leases()
    test_quality_trend_shows_round_progression_and_production_daily()
    test_trend_route_owner_only()
    test_field_reliability_route_available_to_any_logged_in_user()
    print("\nAll extraction quality tests passed.")
