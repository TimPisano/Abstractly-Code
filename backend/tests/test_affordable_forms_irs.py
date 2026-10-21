"""
Tests for the IRS LIHTC form mappings (app/affordable/forms/irs_lihtc.py)
and the partial CHFA LURA mapping (forms/lura.py), end to end on the
synthetic eval samples in tests/eval/affordable/samples/ (fictional values).
No API, no DB. Run: python backend/tests/test_affordable_forms_irs.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.affordable import extract_document
from app.affordable.values import parse_money

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SAMPLES = os.path.join(REPO, "tests", "eval", "affordable", "samples")


def _key(doc_id):
    with open(os.path.join(SAMPLES, f"{doc_id}.answer_key.json")) as f:
        return json.load(f)


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _value(res, name):
    return (res["program_fields"].get(name) or {}).get("value")


def _assert_money(res, key, name):
    want = parse_money(str(key["program_fields"][name]["value"]))
    got = _value(res, name)
    assert got is not None and abs(parse_money(got) - want) < 0.5, (name, got, want)


def _assert_text(res, key, name):
    assert _norm(_value(res, name)) == _norm(key["program_fields"][name]["value"]), (name, _value(res, name))


def test_8609_clean_and_fillable():
    key = _key("irs_8609")
    for name in ("irs_8609.pdf", "irs_8609.acroform.pdf"):
        res = extract_document(os.path.join(SAMPLES, name))
        assert res["form_id"] == "irs_8609", name
        assert _norm(res["lease_fields"]["landlord"]["value"]) == _norm(key["lease_fields"]["landlord"]), name
        assert _norm(key["lease_fields"]["property_address"]) in _norm(res["lease_fields"]["property_address"]["value"]), name
        assert res["lease_fields"]["tenant"]["value"] is None, "a credit allocation names no tenant"
        for money in ("max_credit_amount", "max_qualified_basis", "eligible_basis", "original_qualified_basis"):
            _assert_money(res, key, money)
        for text in ("bin", "owner_tin_masked", "agency_official", "owner_signer"):
            _assert_text(res, key, text)
        assert _value(res, "placed_in_service_date") is not None
        assert "XX-XXX" in _value(res, "owner_tin_masked"), "the TIN stays masked as printed"
    print("✓ test_8609_clean_and_fillable: PASS")


def test_8823_clean_and_fillable():
    key = _key("irs_8823")
    for name in ("irs_8823.pdf", "irs_8823.acroform.pdf"):
        res = extract_document(os.path.join(SAMPLES, name))
        assert res["form_id"] == "irs_8823", name
        assert _norm(res["lease_fields"]["landlord"]["value"]) == _norm(key["lease_fields"]["landlord"]), name
        _assert_money(res, key, "total_credit_allocated")
        for n in ("residential_units", "low_income_units", "units_with_noncompliance", "units_reviewed"):
            assert _value(res, n) == str(key["program_fields"][n]["value"]), (name, n, _value(res, n))
        for d in ("date_ceased_to_comply", "date_noncompliance_corrected"):
            assert _value(res, d) is not None, (name, d)
        _assert_text(res, key, "bin")
    # On a flattened copy, "Print name and title" keeps the person and drops the title
    flat = extract_document(os.path.join(SAMPLES, "irs_8823.pdf"))
    assert "," not in _value(flat, "agency_official")
    print("✓ test_8823_clean_and_fillable: PASS")


def test_8586_clean_and_fillable():
    key = _key("irs_8586")
    for name in ("irs_8586.pdf", "irs_8586.acroform.pdf"):
        res = extract_document(os.path.join(SAMPLES, name))
        assert res["form_id"] == "irs_8586", name
        _assert_text(res, key, "taxpayer_name")
        _assert_money(res, key, "current_year_credit")
        _assert_money(res, key, "total_credit_line5")
        assert _value(res, "forms_8609a_attached") == str(key["program_fields"]["forms_8609a_attached"]["value"])
    print("✓ test_8586_clean_and_fillable: PASS")


def test_chfa_lura_partial():
    key = _key("lura_co_chfa")
    res = extract_document(os.path.join(SAMPLES, "lura_co_chfa.pdf"))
    assert res["form_id"] == "chfa_lura"
    for n in ("total_units", "units_at_60_pct_ami"):
        assert _value(res, n) == str(key["program_fields"][n]["value"]), (n, _value(res, n))
    for n in ("city", "county", "street_address", "bin"):
        _assert_text(res, key, n)
    # Values typed over underscore lines aren't read (see forms/lura.py), and must not come back garbled
    assert "owner_name" not in res["program_fields"] and res["lease_fields"]["landlord"]["value"] is None
    print("✓ test_chfa_lura_partial: PASS")


def test_irs_forms_dont_claim_other_forms():
    for name, expected in (("hud_52517_rfta.pdf", "hud_52517"), ("tic_sc.pdf", None)):
        res = extract_document(os.path.join(SAMPLES, name))
        assert not (res["form_id"] or "").startswith("irs_") and res["form_id"] != "chfa_lura", (name, res["form_id"])
    print("✓ test_irs_forms_dont_claim_other_forms: PASS")


if __name__ == "__main__":
    test_8609_clean_and_fillable()
    test_8823_clean_and_fillable()
    test_8586_clean_and_fillable()
    test_chfa_lura_partial()
    test_irs_forms_dont_claim_other_forms()
    print("\nAll IRS / LURA form tests passed.")
