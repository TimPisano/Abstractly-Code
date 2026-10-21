"""
Tests for values.tidy() -- OCR and typing cleanup applied to every value the
form reader and the AI field lists return. NO real Claude calls (mocked
client). Fictional values, plus the shapes seen in public documents.

Run: python backend/tests/test_affordable_tidy.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app.affordable import ai_fields
from app.affordable.values import tidy


def test_ocr_lowercase_roman_numerals():
    assert tidy("owner_name", "Courtyards at Cottonwood ll, L.P.") == "Courtyards at Cottonwood II, L.P."
    assert tidy("project_name", "Maple Ridge Phase lll") == "Maple Ridge Phase III"
    # "Ill" is a word (Illinois); words and names are left alone
    assert tidy("city", "Springfield Ill") == "Springfield Ill"
    assert tidy("owner_name", "Bill Hall LLC") == "Bill Hall LLC"


def test_vulgar_fractions_are_spelled_out():
    assert tidy("street_address", "674 23¾ Road") == "674 23 3/4 Road"
    assert tidy("street_address", "12½ Elm St") == "12 1/2 Elm St"


def test_hud_contract_numbers_lose_separators():
    assert tidy("contract_number", "TX24-E000-008") == "TX24E000008"
    assert tidy("contract_number", "ZZ99 E000 001") == "ZZ99E000001"
    assert tidy("contract_number", "ZZ99E000001") == "ZZ99E000001"
    # other fields and other shapes are untouched
    assert tidy("recording_number", "TX24-E000-008") == "TX24-E000-008"
    assert tidy("contract_number", "2013-0042") == "2013-0042"


def test_numbers_are_never_rewritten():
    for v in ("$1,592.00", "32", "30%", "04/01/2013"):
        assert tidy("contract_rent_2br", v) == v
    assert tidy("total_units", None) is None


def test_ai_values_are_tidied():
    """Regression: the AI's 'TX24-E000-008' and 'Cottonwood ll' came through as read."""
    fields, tables = ai_fields.FIELD_LISTS["hap_contract"]
    payload = {name: {"value": None, "confidence": None, "source_text": None} for name, _, _ in fields}
    for name in tables:
        payload[name] = {"rows": [], "confidence": None, "source_text": None}
    payload["contract_number"] = {"value": "ZZ99-E000-001", "confidence": "high", "source_text": "No. ZZ99-E000-001"}
    payload["owner_name"] = {"value": "Maple Ridge ll, L.P.", "confidence": "high", "source_text": "Maple Ridge ll, L.P."}
    response = mock.Mock()
    response.content = [ToolUseBlock(id="toolu_x", input=payload, name=ai_fields.TOOL_NAME, type="tool_use")]
    response.usage = mock.Mock(input_tokens=10, output_tokens=10)
    client = mock.Mock()
    client.messages.create.return_value = response
    pages = [{"page": 1, "text": "HOUSING ASSISTANCE PAYMENTS CONTRACT No. ZZ99-E000-001 Owner: Maple Ridge ll, L.P."}]
    out = ai_fields.extract_program_fields(pages, "hap_contract", client=client)
    assert out["program_fields"]["contract_number"]["value"] == "ZZ99E000001"
    assert out["program_fields"]["owner_name"]["value"] == "Maple Ridge II, L.P."
    assert out["lease_fields"]["landlord"]["value"] == "Maple Ridge II, L.P."


if __name__ == "__main__":
    test_ocr_lowercase_roman_numerals()
    test_vulgar_fractions_are_spelled_out()
    test_hud_contract_numbers_lose_separators()
    test_numbers_are_never_rewritten()
    test_ai_values_are_tidied()
    print("\nAll affordable value cleanup tests passed.")
