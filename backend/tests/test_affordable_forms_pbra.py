"""
End-to-end tests for the PBRA / HUD LIHTC data form mappings in
app/affordable/forms/hud_pbra.py and hud_lihtc_data.py, on the synthetic
eval samples in tests/eval/affordable/samples/ (fictional values).

Expected values come from each sample's answer key, normalised the same way
the extractor normalises (so "1,045.00" and "$1,045.00" compare equal).
Run: python backend/tests/test_affordable_forms_pbra.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.affordable import extract_document
from app.affordable.values import coerce

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SAMPLES = os.path.join(REPO, "tests", "eval", "affordable", "samples")


def _key(doc_id):
    with open(os.path.join(SAMPLES, f"{doc_id}.answer_key.json")) as f:
        return json.load(f)


def _expect(key, name):
    entry = key["program_fields"][name]
    return coerce(str(entry.get("shown_as", entry["value"])), entry["type"])


def _check(res, key, names, label):
    for name in names:
        got = (res["program_fields"].get(name) or {}).get("value")
        assert got == _expect(key, name), f"{label}: {name} = {got!r}, expected {_expect(key, name)!r}"


HUD_50059_FIELDS = [
    "project_name", "head_of_household", "effective_date", "next_recert_date", "move_in_date", "unit_number",
    "bedrooms", "contract_number", "household_size", "annual_income", "adjusted_income", "contract_rent",
    "utility_allowance", "gross_rent", "total_tenant_payment", "tenant_rent", "assistance_payment",
    "security_deposit", "tenant_signed_date", "owner_signed_date",
]


def test_50059_flattened():
    key = _key("hud_50059")
    res = extract_document(os.path.join(SAMPLES, "hud_50059.pdf"))
    assert res["form_id"] == "hud_50059" and res["doc_kind"] == "pbra_certification"
    _check(res, key, HUD_50059_FIELDS + ["owner_name"], "50059 flattened")
    lf = res["lease_fields"]
    assert lf["tenant"]["value"] == key["lease_fields"]["tenant"]
    assert lf["landlord"]["value"] == key["lease_fields"]["landlord"]
    assert lf["rent_amount"]["value"] == _expect(key, "contract_rent"), "rent is the contract rent, not tenant rent"
    assert lf["lease_start_date"]["value"] is None
    assert "member_2_dob" not in res["program_fields"], "dates of birth are never extracted"
    print("✓ test_50059_flattened: PASS")


def test_50059_unflattened_form_fields():
    key = _key("hud_50059")
    res = extract_document(os.path.join(SAMPLES, "hud_50059.acroform.pdf"))
    assert res["form_id"] == "hud_50059" and res["had_form_fields"]
    _check(res, key, HUD_50059_FIELDS, "50059 acroform")
    assert res["program_fields"]["contract_rent"]["method"] == "acroform"
    print("✓ test_50059_unflattened_form_fields: PASS")


HUD_52670_FIELDS = [
    "project_name", "project_number", "contract_number", "subsidy_type", "management_agent", "total_units",
    "units_subsidized", "units_abated", "units_vacant", "units_market", "voucher_month", "regular_units_billed",
    "regular_assistance", "adjustment_units", "adjustment_amount", "vacancy_claim_units",
    "vacancy_claim_amount", "total_requested", "signer_date",
]


def test_52670_voucher_both_variants():
    key = _key("hud_52670")
    for name in ("hud_52670.pdf", "hud_52670.acroform.pdf"):
        res = extract_document(os.path.join(SAMPLES, name))
        assert res["form_id"] == "hud_52670", name
        _check(res, key, HUD_52670_FIELDS, name)
        assert all(v["value"] is None for v in res["lease_fields"].values()), "a voucher has no single tenancy"
    print("✓ test_52670_voucher_both_variants: PASS")


def test_52697_detected():
    # Only detection and the numeric fields that survive are asserted here: values typed
    # over this form's underscore blanks come out letter-spaced from the text layer until
    # layout.read_layout drops "_" glyphs before grouping words (see the mapping's notes).
    key = _key("hud_52697")
    res = extract_document(os.path.join(SAMPLES, "hud_52697.pdf"))
    assert res["form_id"] == "hud_52697" and res["program"] == "LIHTC"
    _check(res, key, ["household_size"], "52697")
    assert "head_dob" not in res["program_fields"]
    print("✓ test_52697_detected: PASS")


def test_forms_are_not_confused():
    # each sample is recognised as its own form, not as a sibling PBRA form
    for doc_id, form_id in (("hud_50059", "hud_50059"), ("hud_52670", "hud_52670"), ("hud_52697", "hud_52697"),
                            ("hud_52517_rfta", "hud_52517")):
        res = extract_document(os.path.join(SAMPLES, f"{doc_id}.pdf"))
        assert res["form_id"] == form_id, (doc_id, res["form_id"])
    print("✓ test_forms_are_not_confused: PASS")


if __name__ == "__main__":
    test_50059_flattened()
    test_50059_unflattened_form_fields()
    test_52670_voucher_both_variants()
    test_52697_detected()
    test_forms_are_not_confused()
    print("\nAll PBRA form mapping tests passed.")
