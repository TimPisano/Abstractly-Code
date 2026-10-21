"""
Tests for app/affordable/route.py -- which reader gets an affordable-housing
document: the form reader or the AI. No API, no DB.

Uses the synthetic eval samples in tests/eval/affordable/samples/ (fictional
values only). Run: python backend/tests/test_affordable_route.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.affordable import choose_route, extract_document
from app.affordable.forms import all_forms

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SAMPLES = os.path.join(REPO, "tests", "eval", "affordable", "samples")


def test_tenant_forms_go_to_the_form_reader():
    # HUD-50059 and the TICs are the forms the reader handles: no AI call for them
    for doc_id in ("hud_50059", "tic_sc", "tic_il_ihda", "hud_52517_rfta"):
        res = extract_document(os.path.join(SAMPLES, f"{doc_id}.pdf"))
        assert res["form_id"] and res["route"] == "form", (doc_id, res["form_id"], res["route"])
        assert choose_route(res) == "form", doc_id
    print("✓ test_tenant_forms_go_to_the_form_reader: PASS")


def test_contracts_and_luras_go_to_the_ai():
    # recognised, but their facts live in exhibits or prose
    for doc_id, form_id in (("hud_52530a", "hud_52530a"), ("hud_52530b_pt1", "hud_52530b"), ("lura_co_chfa", "chfa_lura")):
        res = extract_document(os.path.join(SAMPLES, f"{doc_id}.pdf"))
        assert res["form_id"] == form_id and res["route"] == "ai", (doc_id, res["form_id"], res["route"])
        assert choose_route(res) == "ai", doc_id
    print("✓ test_contracts_and_luras_go_to_the_ai: PASS")


def test_unrecognised_documents_go_to_the_ai():
    assert choose_route({"form_id": None, "route": None, "program_fields": {}, "fields_possible": 0}) == "ai"
    print("✓ test_unrecognised_documents_go_to_the_ai: PASS")


def test_a_misread_form_falls_back_to_the_ai():
    # a recognised form that yields almost nothing (another edition, a bad scan)
    base = {"form_id": "hud_50059", "route": "form", "fields_possible": 20}
    assert choose_route({**base, "program_fields": {f"f{i}": {} for i in range(4)}}) == "ai"
    assert choose_route({**base, "program_fields": {f"f{i}": {} for i in range(5)}}) == "form"
    print("✓ test_a_misread_form_falls_back_to_the_ai: PASS")


def test_every_form_has_a_known_route():
    for spec in all_forms():
        assert spec.route in ("form", "ai"), (spec.id, spec.route)
    print("✓ test_every_form_has_a_known_route: PASS")


if __name__ == "__main__":
    test_tenant_forms_go_to_the_form_reader()
    test_contracts_and_luras_go_to_the_ai()
    test_unrecognised_documents_go_to_the_ai()
    test_a_misread_form_falls_back_to_the_ai()
    test_every_form_has_a_known_route()
    print("\nAll affordable routing tests passed.")
