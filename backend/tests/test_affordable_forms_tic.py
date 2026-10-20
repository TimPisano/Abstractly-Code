"""
End-to-end tests for the LIHTC Tenant Income Certification mappings
(app/affordable/forms/lihtc_tic.py), on the synthetic eval samples in
tests/eval/affordable/samples/ (fictional values). No API, no DB.

Run: python backend/tests/test_affordable_forms_tic.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.affordable import extract_document
from app.affordable.values import parse_date, parse_money

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SAMPLES = os.path.join(REPO, "tests", "eval", "affordable", "samples")


def _key(doc_id):
    with open(os.path.join(SAMPLES, f"{doc_id}.answer_key.json")) as f:
        return json.load(f)


def _same(vtype, got, expected):
    if got is None:
        return False
    if vtype == "money":
        return abs(parse_money(got) - parse_money(str(expected))) < 0.5
    if vtype == "date":
        return parse_date(got) == parse_date(str(expected))
    if vtype in ("int", "pct"):
        return float(got.rstrip("%")) == float(str(expected).rstrip("%"))
    return " ".join(got.lower().split()) == " ".join(str(expected).lower().split())


def _check(doc_id, filename, form_id, fields):
    key = _key(doc_id)
    res = extract_document(os.path.join(SAMPLES, filename))
    assert res["form_id"] == form_id, (filename, res["form_id"])
    for name in fields:
        entry = key["program_fields"][name]
        got = (res["program_fields"].get(name) or {}).get("value")
        assert _same(entry["type"], got, entry["value"]), (filename, name, got, entry["value"])
    return res, key


def test_national_tic_louisiana():
    res, key = _check("tic_la_lhc", "tic_la_lhc.pdf", "tic_national", [
        "effective_date", "move_in_date", "property_name", "county", "bin", "building_address", "unit_number",
        "bedrooms", "head_of_household", "member_2_relationship", "total_ss_pension_income", "total_annual_income",
        "income_limit", "household_income_at_move_in", "household_size", "tenant_paid_rent", "utility_allowance",
        "rental_assistance", "gross_rent",
    ])
    lf = res["lease_fields"]
    assert lf["tenant"]["value"] == key["lease_fields"]["tenant"]
    assert parse_money(lf["rent_amount"]["value"]) == parse_money(key["lease_fields"]["rent_amount"])
    assert lf["property_address"]["value"] == key["lease_fields"]["property_address"]
    assert lf["landlord"]["value"] is None and lf["lease_start_date"]["value"] is None
    print("✓ test_national_tic_louisiana: PASS")


def test_national_tic_new_jersey_scanned_blank():
    # NJ's blank is itself an OCR'd scan of the same layout, at a different offset
    res, key = _check("tic_nj_scan", "tic_nj_scan.pdf", "tic_national", [
        "effective_date", "move_in_date", "property_name", "county", "bin", "building_address", "unit_number",
        "bedrooms", "head_of_household", "member_5_first_name", "total_employment_income", "total_annual_income",
        "income_limit", "household_size_at_move_in", "tenant_paid_rent", "utility_allowance",
        "other_non_optional_fees", "gross_rent",
    ])
    assert res["lease_fields"]["tenant"]["value"] == key["lease_fields"]["tenant"]
    print("✓ test_national_tic_new_jersey_scanned_blank: PASS")


def test_county_value_containing_the_word_county():
    # "Maple Ridge County" must not be mistaken for the "County:" label
    res, key = _check("tic_nj_scan", "tic_nj_scan.pdf", "tic_national", ["county", "bin"])
    assert "County" in res["program_fields"]["county"]["value"]
    print("✓ test_county_value_containing_the_word_county: PASS")


def test_national_tic_south_carolina_detected():
    # SC's blank leaves space characters under its fill areas, which split the
    # filled values into letters in the text layer; only the head-of-household
    # line (drawn clear of them) is asserted until layout handles that.
    res, key = _check("tic_sc", "tic_sc.pdf", "tic_national", ["head_of_household"])
    assert res["lease_fields"]["tenant"]["value"] == key["lease_fields"]["tenant"]
    print("✓ test_national_tic_south_carolina_detected: PASS")


def test_illinois_tic_flattened():
    res, key = _check("tic_il_ihda", "tic_il_ihda.pdf", "tic_il_ihda", [
        "effective_date", "move_in_date", "property_name", "tc_number", "building_address", "city", "zip", "bin",
        "county", "unit_number", "bedrooms", "head_of_household", "total_employment_income", "total_income_e",
        "asset_1_cash_value", "total_asset_cash_value", "passbook_rate", "asset_income", "total_annual_income",
        "income_limit", "household_income_at_move_in", "household_size_at_move_in", "tenant_paid_rent",
        "utility_allowance", "gross_rent", "maximum_rent_limit", "household_signature_date", "owner_signature_date",
    ])
    lf = res["lease_fields"]
    assert lf["tenant"]["value"] == key["lease_fields"]["tenant"]
    assert lf["property_address"]["value"] == key["lease_fields"]["property_address"]
    print("✓ test_illinois_tic_flattened: PASS")


def test_illinois_tic_unflattened_form_fields():
    key = _key("tic_il_ihda")
    res = extract_document(os.path.join(SAMPLES, "tic_il_ihda.acroform.pdf"))
    assert res["form_id"] == "tic_il_ihda" and res["had_form_fields"]
    for name, entry in key["program_fields"].items():
        if entry["type"] == "checkbox" or name.endswith("_dob"):
            continue
        got = (res["program_fields"].get(name) or {}).get("value")
        assert _same(entry["type"], got, entry.get("value")), (name, got, entry["value"])
        assert res["program_fields"][name]["method"] == "acroform", name
    assert not any(n.endswith("_dob") for n in res["program_fields"]), "dates of birth are never extracted"
    print("✓ test_illinois_tic_unflattened_form_fields: PASS")


if __name__ == "__main__":
    test_national_tic_louisiana()
    test_national_tic_new_jersey_scanned_blank()
    test_county_value_containing_the_word_county()
    test_national_tic_south_carolina_detected()
    test_illinois_tic_flattened()
    test_illinois_tic_unflattened_form_fields()
    print("\nAll TIC form tests passed.")
