"""
Tests for app/ai_rent_roll_validation.py -- model-backed rent-roll vs.
lease cross-checking. Mocked anthropic client (real anthropic.types),
same convention as test_ai_extraction.py / test_assistant.py.

Covers: the abstracted-or-skip guardrail, payload -> stored-discrepancy
shape + severity coercion, agree -> empty result, unit pairing by
address, stable persistence (re-run updates, doesn't duplicate), and
the POST /portfolio/rent-roll-ai-validation route (503 when AI off,
skip-not-abstracted, persist with the model's severity).
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app.api import app
from app import database
from app import ai_extraction
from app import ai_rent_roll_validation as rrv
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
        if name in overrides and overrides[name] is not None:
            out[name] = {"value": overrides[name], "source": {"page": 1, "quote": f"...{overrides[name]}..."}, "confidence": "high"}
        else:
            out[name] = {"value": None, "source": None, "confidence": None}
    return out


def _mock_client(payload):
    resp = mock.Mock()
    resp.content = [ToolUseBlock(id="toolu_x", input=payload, name="record_rent_roll_validation", type="tool_use")]
    resp.usage = mock.Mock(input_tokens=800, output_tokens=120)
    resp.stop_reason = "tool_use"
    c = mock.Mock()
    c.messages.create.return_value = resp
    return c


def _rr_lease(**f):
    return {"id": 1, "filename": "rent_roll.csv", "extracted_fields": _fields(**f)}


def _doc_lease(**f):
    return {"id": 2, "filename": "lease.pdf", "extracted_fields": _fields(**f)}


# ----------------------------------------------------------------------

def test_is_abstracted():
    assert rrv.is_abstracted(_doc_lease(tenant="Acme")) is True
    assert rrv.is_abstracted(_doc_lease()) is False
    assert rrv.is_abstracted(_doc_lease(square_footage="2,400 sq ft")) is False, "sqft alone isn't evidence of a real abstraction"
    print("✓ test_is_abstracted: PASS")


def test_validate_skips_when_lease_not_abstracted_no_model_call():
    fake = mock.Mock()
    result = rrv.validate_rent_roll_against_lease(_rr_lease(tenant="Acme", rent_amount="$6,250.00"), _doc_lease(), client=fake)
    assert result["status"] == "not_abstracted"
    assert result["discrepancies"] == []
    fake.messages.create.assert_not_called()
    print("✓ test_validate_skips_when_lease_not_abstracted_no_model_call: PASS")


def test_validate_returns_discrepancies_with_model_severity():
    payload = {
        "discrepancies": [
            {"field": "rent_amount", "severity": "high", "rent_roll_value": "$6,000.00", "lease_value": "$6,250.00",
             "explanation": "Rent roll is $250/mo below the lease.", "recommendation": "Confirm against any side letter."},
            {"field": "lease_end_date", "severity": "medium", "rent_roll_value": "2027-12-31", "lease_value": "March 31, 2030",
             "explanation": "Rent roll expiration predates the lease term -- possible unrecorded renewal.", "recommendation": "Check for a renewal amendment."},
        ],
        "overall_assessment": "The two records disagree on rent and term.",
    }
    result = rrv.validate_rent_roll_against_lease(
        _rr_lease(tenant="Acme", rent_amount="$6,000.00", lease_end_date="2027-12-31"),
        _doc_lease(tenant="Acme", rent_amount="$6,250.00", lease_end_date="March 31, 2030"),
        client=_mock_client(payload),
    )
    assert result["status"] == "validated"
    assert [d["severity"] for d in result["discrepancies"]] == ["high", "medium"]
    assert result["discrepancies"][0]["field"] == "rent_amount"
    assert result["_ai_meta"]["discrepancy_count"] == 2
    print("✓ test_validate_returns_discrepancies_with_model_severity: PASS")


def test_validate_agree_returns_empty():
    result = rrv.validate_rent_roll_against_lease(
        _rr_lease(tenant="Acme", rent_amount="$6,250.00"),
        _doc_lease(tenant="Acme", rent_amount="$6,250.00"),
        client=_mock_client({"discrepancies": [], "overall_assessment": "Consistent."}),
    )
    assert result["status"] == "validated"
    assert result["discrepancies"] == []
    print("✓ test_validate_agree_returns_empty: PASS")


def test_coerce_discrepancy_degrades_bad_severity_and_drops_empty_explanation():
    payload = {"discrepancies": [
        {"field": "made_up_field", "severity": "catastrophic", "explanation": "something", "recommendation": ""},
        {"field": "tenant", "severity": "high", "explanation": "   ", "recommendation": "x"},
    ], "overall_assessment": ""}
    result = rrv.validate_rent_roll_against_lease(
        _rr_lease(tenant="A"), _doc_lease(tenant="B"), client=_mock_client(payload),
    )
    assert len(result["discrepancies"]) == 1, "the empty-explanation one is dropped"
    d = result["discrepancies"][0]
    assert d["field"] == "other", "unknown field -> other"
    assert d["severity"] == "low", "unknown severity -> low, not dropped"
    assert d["recommendation"]
    print("✓ test_coerce_discrepancy_degrades_bad_severity_and_drops_empty_explanation: PASS")


def test_find_unit_pairs_matches_by_address():
    leases = [
        {"id": 1, "filename": "rr.csv", "extracted_fields": _fields(property_address="100 Main Street, Suite 200", tenant="Acme")},
        {"id": 2, "filename": "lease.pdf", "extracted_fields": _fields(property_address="100 Main Street, Suite 200", tenant="Acme Corp")},
        {"id": 3, "filename": "rr.csv", "extracted_fields": _fields(property_address="999 Nowhere Blvd", tenant="Ghost")},
    ]
    pairs = rrv.find_unit_pairs(leases)
    assert len(pairs) == 1
    assert pairs[0][0]["id"] == 1 and pairs[0][1]["id"] == 2
    print("✓ test_find_unit_pairs_matches_by_address: PASS")


def test_sync_validation_result_persists_and_is_stable_on_rerun():
    db_path = _fresh_temp_db()
    try:
        rr_id = database.insert_lease("rr.csv", _fields(property_address="100 Main St", tenant="Acme", rent_amount="$6,000.00"))
        doc_id = database.insert_lease("lease.pdf", _fields(property_address="100 Main St", tenant="Acme", rent_amount="$6,250.00"))
        result = {
            "rent_roll_lease_id": rr_id, "lease_document_id": doc_id, "address": "100 Main St",
            "assessment": "disagree on rent",
            "discrepancies": [{"field": "rent_amount", "severity": "high", "rent_roll_value": "$6,000.00",
                               "lease_value": "$6,250.00", "explanation": "off by $250", "recommendation": "check"}],
        }
        rrv.sync_validation_result(result)
        rrv.sync_validation_result(result)  # re-run

        open_discrepancies = database.list_discrepancies()
        ai_rows = [d for d in open_discrepancies if d["discrepancy_type"] == "rent_roll_ai_validation"]
        assert len(ai_rows) == 1, "re-running must update the same row, not duplicate"
        assert ai_rows[0]["severity"] == "high", "the model's severity is stored, not a hardcoded default"
        assert ai_rows[0]["field"] == "rent_amount"
    finally:
        os.unlink(db_path)
    print("✓ test_sync_validation_result_persists_and_is_stable_on_rerun: PASS")


# ----------------------------------------------------------------------
# Route
# ----------------------------------------------------------------------

def _analyst_client():
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"user_id": 1, "email": "a@example.com", "name": "A", "role": "analyst"})
    return c


def test_route_503_when_ai_disabled():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.object(ai_extraction, "resolve_engine", return_value="regex"):
            resp = _analyst_client().post("/portfolio/rent-roll-ai-validation")
        assert resp.status_code == 503
    finally:
        os.unlink(db_path)
    print("✓ test_route_503_when_ai_disabled: PASS")


def test_route_validates_pairs_skips_unabstracted_and_persists():
    db_path = _fresh_temp_db()
    try:
        # pair A: rent roll + abstracted lease -> validated, 1 discrepancy
        rr_a = database.insert_lease("rr.csv", _fields(property_address="1 A St", tenant="Acme", rent_amount="$6,000.00"))
        database.insert_lease("lease_a.pdf", _fields(property_address="1 A St", tenant="Acme", rent_amount="$6,250.00"))
        # pair B: rent roll + un-abstracted lease -> skipped
        database.insert_lease("rr.csv", _fields(property_address="2 B Ave", tenant="Beta"))
        database.insert_lease("lease_b.pdf", _fields(property_address="2 B Ave"))

        payload = {"discrepancies": [{"field": "rent_amount", "severity": "high", "rent_roll_value": "$6,000.00",
                                      "lease_value": "$6,250.00", "explanation": "off by $250", "recommendation": "check"}],
                   "overall_assessment": "rent disagrees"}

        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"), \
             mock.patch.object(rrv, "validate_rent_roll_against_lease", wraps=rrv.validate_rent_roll_against_lease) as spy, \
             mock.patch("app.ai_rent_roll_validation.call_forced_tool", return_value=_mock_client(payload).messages.create.return_value):
            resp = _analyst_client().post("/portfolio/rent-roll-ai-validation")

        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["pairs_found"] == 2
        assert body["validated"] == 1
        assert body["skipped_not_abstracted"] == 1
        assert len(body["discrepancies"]) == 1

        ai_rows = [d for d in database.list_discrepancies() if d["discrepancy_type"] == "rent_roll_ai_validation"]
        assert len(ai_rows) == 1 and ai_rows[0]["severity"] == "high"

        runs = [r for r in database.list_ai_extraction_runs() if r["kind"] == "rent_roll_validation"]
        assert len(runs) == 1
    finally:
        os.unlink(db_path)
    print("✓ test_route_validates_pairs_skips_unabstracted_and_persists: PASS")


if __name__ == "__main__":
    test_is_abstracted()
    test_validate_skips_when_lease_not_abstracted_no_model_call()
    test_validate_returns_discrepancies_with_model_severity()
    test_validate_agree_returns_empty()
    test_coerce_discrepancy_degrades_bad_severity_and_drops_empty_explanation()
    test_find_unit_pairs_matches_by_address()
    test_sync_validation_result_persists_and_is_stable_on_rerun()
    test_route_503_when_ai_disabled()
    test_route_validates_pairs_skips_unabstracted_and_persists()
    print("\nAll AI rent-roll validation tests passed.")
