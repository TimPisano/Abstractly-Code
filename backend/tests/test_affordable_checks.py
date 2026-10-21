"""
Tests for app/affordable/checks.py -- arithmetic cross-checks that flag, and
never change, extracted values. NO real Claude calls: the anthropic client is
mocked with real anthropic.types objects. Rent figures for the regression test
are the ones printed in a public 1990 HUD contract exhibit (no tenant data);
everything else is fictional.

Run: python backend/tests/test_affordable_checks.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import copy
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app.affordable import ai_fields
from app.affordable.checks import run_checks

# Coppertree Village 1990 HAP contract, p.11 Exhibit 1 (stage 2), as typed on
# the document and checked by hand by the user on 2026-10-21. The 1BR row
# doesn't add up on the document itself: $250 + $35 = $285, not $295. A
# handwritten 2-11-91 note flags it as a known error.
COPPERTREE_PAGES = [
    {"page": 1, "text": "HOUSING ASSISTANCE PAYMENTS CONTRACT\nContract No. TX24-E000-008"},
    {"page": 11, "text": "EXHIBIT 1\nNo. of Units  Bedrooms  Contract Rent  Utility Allowance  Gross Rent\n"
                         "49  1  $250  $35  $295\n39  2  $350  $45  $395\n2  3  $395  $53  $448"},
]
COPPERTREE_ROWS = [
    {"bedrooms": "1", "total_units": None, "contract_units": "49", "contract_rent": "$250",
     "utility_allowance": "$35", "gross_rent": "$295", "proposed_rent": None},
    {"bedrooms": "2", "total_units": None, "contract_units": "39", "contract_rent": "$350",
     "utility_allowance": "$45", "gross_rent": "$395", "proposed_rent": None},
    {"bedrooms": "3", "total_units": None, "contract_units": "2", "contract_rent": "$395",
     "utility_allowance": "$53", "gross_rent": "$448", "proposed_rent": None},
]


def _mock_client(tool_input):
    response = mock.Mock()
    response.content = [ToolUseBlock(id="toolu_x", input=tool_input, name=ai_fields.TOOL_NAME, type="tool_use")]
    response.usage = mock.Mock(input_tokens=2000, output_tokens=800)
    response.stop_reason = "tool_use"
    client = mock.Mock()
    client.messages.create.return_value = response
    return client


def _hap_payload(rows):
    fields, tables = ai_fields.FIELD_LISTS["hap_contract"]
    payload = {name: {"value": None, "confidence": None, "source_text": None} for name, _, _ in fields}
    payload["contract_units"] = {"value": "90", "confidence": "medium", "source_text": "49 1 ... 39 2 ... 2 3"}
    for name in tables:
        payload[name] = {"rows": [], "confidence": None, "source_text": None}
    payload["unit_mix"] = {"rows": rows, "confidence": "medium", "source_text": "49  1  $250  $35  $295"}
    return payload


def _f(value, confidence="medium", page=1):
    return {"value": value, "source": {"page": page, "quote": value}, "confidence": confidence, "method": "layout"}


def test_coppertree_1br_row_is_flagged_and_keeps_its_printed_rent():
    """Regression: the 1990 Exhibit 1 1BR row ($250 + $35 vs $295 gross) must be
    flagged low confidence with "Verify with your PHA", and stay $250."""
    out = ai_fields.extract_program_fields(COPPERTREE_PAGES, "hap_contract",
                                           client=_mock_client(_hap_payload(COPPERTREE_ROWS)))
    pf = out["program_fields"]
    assert pf["contract_rent_1br"]["value"] == "$250", pf.get("contract_rent_1br")
    assert pf["utility_allowance_1br"]["value"] == "$35"
    assert pf["gross_rent_1br"]["value"] == "$295"
    for name in ("contract_rent_1br", "utility_allowance_1br", "gross_rent_1br"):
        assert pf[name]["confidence"] == "low", (name, pf[name])
        assert "Verify with your PHA" in pf[name]["check_note"], pf[name]
        assert "$285" in pf[name]["check_note"] and "$295" in pf[name]["check_note"]
    # rows that add up are left alone
    for n in (2, 3):
        assert pf[f"contract_rent_{n}br"]["confidence"] != "low"
        assert "check_note" not in pf[f"contract_rent_{n}br"]
    assert pf["contract_rent_2br"]["value"] == "$350" and pf["contract_rent_3br"]["value"] == "$395"
    flagged = [c for c in out["checks"] if c["status"] == "mismatch"]
    assert len(flagged) == 1 and "contract_rent_1br" in flagged[0]["fields"], out["checks"]
    assert flagged[0]["citation"]
    # 49 + 39 + 2 = 90 contract units: consistent, nothing flagged
    assert pf["contract_units"]["confidence"] != "low"


def test_checks_never_change_an_extracted_value():
    fields = {"contract_rent": _f("$841.00"), "utility_allowance": _f("$50.00"), "gross_rent": _f("$900.00"),
              "total_tenant_payment": _f("$400.00"), "tenant_rent": _f("$300.00"),
              "assistance_payment": _f("$491.00")}
    before = {k: v["value"] for k, v in fields.items()}
    checks = run_checks(fields)
    assert {k: fields[k]["value"] for k in before} == before
    assert sum(c["status"] == "mismatch" for c in checks) == 3, checks
    assert all(fields[k]["confidence"] == "low" for k in before)


def test_consistent_50059_numbers_pass_untouched():
    fields = {"contract_rent": _f("$841.00"), "utility_allowance": _f("$50.00"), "gross_rent": _f("$891.00"),
              "total_tenant_payment": _f("$400.00"), "tenant_rent": _f("$350.00"),
              "assistance_payment": _f("$491.00")}
    snapshot = copy.deepcopy(fields)
    checks = run_checks(fields)
    assert fields == snapshot
    assert [c["status"] for c in checks] == ["ok", "ok", "ok"], checks


def test_missing_values_are_derived_and_labelled():
    fields = {"utility_allowance": _f("$50.00"), "gross_rent": _f("$891.00"), "total_tenant_payment": _f("$400.00")}
    run_checks(fields)
    assert fields["tenant_rent"]["value"] == "$350" and fields["tenant_rent"]["method"] == "derived"
    assert fields["assistance_payment"]["value"] == "$491"
    for name in ("tenant_rent", "assistance_payment"):
        assert fields[name]["confidence"] == "medium"
        assert "Verify with your PHA" in fields[name]["check_note"]
        assert fields[name]["source"]["quote"].startswith("derived:")


def test_utility_allowance_above_ttp_floors_tenant_rent_at_zero():
    fields = {"total_tenant_payment": _f("$25.00"), "utility_allowance": _f("$60.00")}
    run_checks(fields)
    assert fields["tenant_rent"]["value"] == "$0"


def test_no_derivation_from_a_doubtful_number():
    fields = {"contract_rent": _f("$250"), "utility_allowance": _f("$35"), "gross_rent": _f("$295"),
              "total_tenant_payment": _f("$100")}
    run_checks(fields)
    assert fields["utility_allowance"]["confidence"] == "low"
    assert "tenant_rent" not in fields


def test_bedroom_counts_that_dont_add_up_are_flagged():
    fields = {"contract_units": _f("40"), "contract_units_1br": _f("35"), "contract_units_2br": _f("4")}
    checks = run_checks(fields)
    assert checks[-1]["status"] == "mismatch" and "39" in checks[-1]["message"]
    assert fields["contract_units"]["value"] == "40" and fields["contract_units"]["confidence"] == "low"


def _lura_payload(rows, total_units="50"):
    fields, tables = ai_fields.FIELD_LISTS["lura"]
    payload = {name: {"value": None, "confidence": None, "source_text": None} for name, _, _ in fields}
    payload["total_units"] = {"value": total_units, "confidence": "high", "source_text": f"{total_units} units"}
    for name in tables:
        payload[name] = {"rows": [], "confidence": None, "source_text": None}
    payload["unit_mix"] = {"rows": rows, "confidence": "medium", "source_text": "Building 1 ..."}
    return payload


# One row per building and bedroom size, the way a multi-building tax-credit
# agreement lists its units (fictional buildings, 27 / 11 / 12 in total).
PER_BUILDING_ROWS = [
    {"bedrooms": "2", "units": "1"}, {"bedrooms": "3", "units": "1"}, {"bedrooms": "4", "units": "8"},
    {"bedrooms": "2", "units": "14"}, {"bedrooms": "3", "units": "6"},
    {"bedrooms": "2", "units": "12"}, {"bedrooms": "3", "units": "4"}, {"bedrooms": "4", "units": "4"},
]
LURA_PAGES = [{"page": 1, "text": "REGULATORY AGREEMENT\nBuilding 1: 1 two-bedroom, 1 three-bedroom, 8 four-bedroom."}]


def test_unit_mix_rows_for_the_same_size_add_up():
    """Regression: only the first row per bedroom size was kept (1 / 1 / 8 instead of 27 / 11 / 12)."""
    out = ai_fields.extract_program_fields(LURA_PAGES, "lura", client=_mock_client(_lura_payload(PER_BUILDING_ROWS)))
    pf = out["program_fields"]
    assert (pf["units_2br"]["value"], pf["units_3br"]["value"], pf["units_4br"]["value"]) == ("27", "11", "12"), pf
    assert [c["status"] for c in out["checks"]] == ["ok"], out["checks"]


def test_lura_unit_mix_that_matches_no_total_is_flagged():
    out = ai_fields.extract_program_fields(LURA_PAGES, "lura",
                                           client=_mock_client(_lura_payload(PER_BUILDING_ROWS, total_units="60")))
    flagged = [c for c in out["checks"] if c["status"] == "mismatch"]
    assert len(flagged) == 1 and "50" in flagged[0]["message"] and "60" in flagged[0]["message"], out["checks"]
    assert out["program_fields"]["total_units"]["value"] == "60"


if __name__ == "__main__":
    test_coppertree_1br_row_is_flagged_and_keeps_its_printed_rent()
    test_checks_never_change_an_extracted_value()
    test_consistent_50059_numbers_pass_untouched()
    test_missing_values_are_derived_and_labelled()
    test_utility_allowance_above_ttp_floors_tenant_rent_at_zero()
    test_no_derivation_from_a_doubtful_number()
    test_bedroom_counts_that_dont_add_up_are_flagged()
    test_unit_mix_rows_for_the_same_size_add_up()
    test_lura_unit_mix_that_matches_no_total_is_flagged()
    print("\nAll affordable cross-check tests passed.")
