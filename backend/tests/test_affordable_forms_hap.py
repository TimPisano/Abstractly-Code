"""
End-to-end tests for the HAP contract mappings in app/affordable/forms/:
HUD-52641 (HCV, two PHA re-saves with different text spacing) and
HUD-52530A / 52530B (PBV). Uses the synthetic eval samples in
tests/eval/affordable/samples/ (fictional values). No API, no DB.

Run: python backend/tests/test_affordable_forms_hap.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
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


def _run(name):
    return extract_document(os.path.join(SAMPLES, name))


def _same_text(a, b):
    norm = lambda s: " ".join("".join(c if c.isalnum() else " " for c in s.lower()).split())  # noqa: E731
    return a is not None and norm(a) == norm(b)


def test_hcv_hap_contract_both_renditions():
    for doc_id in ("hud_52641_rhanc", "hud_52641_tarrant"):
        key = _key(doc_id)
        res = _run(f"{doc_id}.pdf")
        assert res["form_id"] == "hud_52641", (doc_id, res["form_id"])
        lf, pf = res["lease_fields"], res["program_fields"]
        exp = key["lease_fields"]
        assert _same_text(lf["tenant"]["value"], exp["tenant"]), doc_id
        assert _same_text(lf["landlord"]["value"], exp["landlord"]), doc_id
        assert _same_text(lf["property_address"]["value"], exp["property_address"]), doc_id
        assert parse_money(lf["rent_amount"]["value"]) == parse_money(exp["rent_amount"]), doc_id
        assert parse_date(lf["lease_start_date"]["value"]) == parse_date(exp["lease_start_date"]), doc_id
        assert parse_date(lf["lease_end_date"]["value"]) == parse_date(exp["lease_end_date"]), doc_id
        # program fields: the initial HAP and the household list
        assert parse_money(pf["initial_hap"]["value"]) == parse_money(str(key["program_fields"]["initial_hap"]["value"]))
        for i in (1, 2, 3):
            name = f"household_member_{i}"
            assert _same_text(pf[name]["value"], key["program_fields"][name]["value"]), (doc_id, name)
    print("✓ test_hcv_hap_contract_both_renditions: PASS")


def test_pbv_contracts_detected_and_owner_read():
    for doc_id, form_id in (("hud_52530a", "hud_52530a"), ("hud_52530b_pt1", "hud_52530b")):
        key = _key(doc_id)
        for variant in (f"{doc_id}.pdf", f"{doc_id}.acroform.pdf"):
            res = _run(variant)
            assert res["form_id"] == form_id, (variant, res["form_id"])
            assert _same_text(res["lease_fields"]["landlord"]["value"], key["lease_fields"]["landlord"]), variant
            pf = res["program_fields"]
            assert _same_text(pf["pha_name"]["value"], key["program_fields"]["pha_name"]["value"]), variant
            for name in ("units_prior_hud_assistance", "units_federal_rent_restriction", "elderly_designated_units"):
                assert pf[name]["value"] == str(key["program_fields"][name]["value"]), (variant, name)
    # the effective date: from the form field when unflattened, and from the page for 52530B
    for variant in ("hud_52530a.acroform.pdf", "hud_52530b_pt1.acroform.pdf", "hud_52530b_pt1.pdf"):
        doc_id = variant.split(".")[0]
        res = _run(variant)
        assert parse_date(res["lease_fields"]["lease_start_date"]["value"]) == \
            parse_date(_key(doc_id)["lease_fields"]["lease_start_date"]), variant
    print("✓ test_pbv_contracts_detected_and_owner_read: PASS")


def test_forms_are_not_confused():
    # each HAP contract is recognised as itself, never as the RFTA or the other edition
    expected = {"hud_52641_rhanc.pdf": "hud_52641", "hud_52641_tarrant.pdf": "hud_52641",
                "hud_52530a.pdf": "hud_52530a", "hud_52530b_pt1.pdf": "hud_52530b",
                "hud_52517_rfta.pdf": "hud_52517"}
    for name, form_id in expected.items():
        assert _run(name)["form_id"] == form_id, name
    print("✓ test_forms_are_not_confused: PASS")


if __name__ == "__main__":
    test_hcv_hap_contract_both_renditions()
    test_pbv_contracts_detected_and_owner_read()
    test_forms_are_not_confused()
    print("\nAll affordable HAP contract tests passed.")
