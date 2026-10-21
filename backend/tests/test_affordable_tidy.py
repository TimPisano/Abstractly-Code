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
from app.affordable.exhibits import read_exhibit_a
from app.affordable.values import expand_address_list, fill_address_parts, split_address, tidy


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


def test_legal_entity_descriptors_are_not_part_of_the_name():
    assert tidy("owner_name", "Maple Ridge Senior Housing LP, a California limited partnership") == \
        "Maple Ridge Senior Housing LP"
    assert tidy("assignee_name", "Maple Ridge Holdings LLC, a Delaware limited liability company") == \
        "Maple Ridge Holdings LLC"
    assert tidy("project_name", "Maple Ridge, a California limited partnership") == \
        "Maple Ridge, a California limited partnership"      # only party names
    assert tidy("owner_name", "Maple Ridge II, L.P.") == "Maple Ridge II, L.P."


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


def test_split_address_into_street_city_state_zip():
    assert split_address("100 and 102 W. Example Street, Springfield, ZZ 00000") == {
        "street": "100 and 102 W. Example Street", "city": "Springfield", "state": "ZZ", "zip": "00000"}
    assert split_address("24 Example Avenue, Springfield ZZ 00000-1234")["city"] == "Springfield"
    assert split_address("9 Example Blvd., Moab, Utah 84532")["state"] == "Utah"
    assert split_address("24550 & 24570 Example  Springfeld  00000") is None      # no commas, no state: don't guess


def test_expand_a_list_of_building_addresses():
    assert expand_address_list("57, 81, 101, 109, 115 and 119 Example Creek Blvd, Building 1") == [
        "57 Example Creek Blvd", "81 Example Creek Blvd", "101 Example Creek Blvd", "109 Example Creek Blvd",
        "115 Example Creek Blvd", "119 Example Creek Blvd"]
    assert expand_address_list("926 and 932 W. Example Street") == ["926 W. Example Street", "932 W. Example Street"]
    assert expand_address_list("9 Example Blvd.") == ["9 Example Blvd."]


def test_address_parts_are_their_own_fields():
    """Regression: the PBV exhibit reader returned only the full address."""
    text = ("EXHIBIT A\nProject Name: Maple Ridge\nAddress: 100 and 102 W. Example Street, Springfield, ZZ 00000\n"
            "Total Number of PBV Units in Project Covered by HAP Contract: 4\n")
    f = read_exhibit_a([{"page": 9, "text": text}])
    fill_address_parts(f)
    assert (f["street_address"]["value"], f["city"]["value"], f["state"]["value"], f["zip"]["value"]) == (
        "100 and 102 W. Example Street", "Springfield", "ZZ", "00000")
    assert f["property_address"]["value"] == "100 and 102 W. Example Street, Springfield, ZZ 00000"
    assert [f[f"building_address_{i}"]["value"] for i in (1, 2)] == ["100 W. Example Street", "102 W. Example Street"]


def test_all_listed_building_addresses_come_out():
    fields = {"street_address": {"value": "57, 81 and 119 Example Creek Blvd", "source": {"page": 1}, "confidence": "high"}}
    fill_address_parts(fields)
    assert [fields[f"building_address_{i}"]["value"] for i in (1, 2, 3)] == [
        "57 Example Creek Blvd", "81 Example Creek Blvd", "119 Example Creek Blvd"]
    assert fields["street_address"]["value"] == "57, 81 and 119 Example Creek Blvd"   # the read value is kept


if __name__ == "__main__":
    test_split_address_into_street_city_state_zip()
    test_expand_a_list_of_building_addresses()
    test_address_parts_are_their_own_fields()
    test_all_listed_building_addresses_come_out()
    test_ocr_lowercase_roman_numerals()
    test_vulgar_fractions_are_spelled_out()
    test_hud_contract_numbers_lose_separators()
    test_legal_entity_descriptors_are_not_part_of_the_name()
    test_numbers_are_never_rewritten()
    test_ai_values_are_tidied()
    print("\nAll affordable value cleanup tests passed.")
