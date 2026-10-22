"""
Tests for app/affordable/ai_fields.py -- AI field lists for HAP contracts
and LURAs. NO real Claude calls: the anthropic client is mocked with real
anthropic.types objects, as in test_ai_extraction.py. Fictional values only.

Run: python backend/tests/test_affordable_ai_fields.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app import ai_extraction
from app.affordable import ai_fields
from app.affordable.route import ai_doc_kind

HAP_PAGES = [
    {"page": 1, "text": "SECTION 8 HOUSING ASSISTANCE PAYMENTS CONTRACT\nContract Number: ZZ99E000001\n"
                        "Owner: Maple Ridge Housing LP. Project: Maple Ridge Apartments, 100 Example Way, Springfield."},
    {"page": 2, "text": "Exhibit A. Contract units: 1 BR, 12 units, $900; 2 BR, 8 units, $1,100. "
                        "The term of this contract begins on January 1, 2026 and is 20 years."},
]
LURA_PAGES = [
    {"page": 1, "text": "REGULATORY AGREEMENT AND DECLARATION OF RESTRICTIVE COVENANTS\n"
                        "Maple Ridge Housing LP and the State Housing Agency."},
    {"page": 2, "text": "Not less than 100% of the units shall be low-income units. 4 units at 30% of AMI; "
                        "the rest at 60% of AMI. BIN: ZZ-26-00001. Extended use period: 30 years."},
]


def _entry(value, quote, confidence="high"):
    return {"value": value, "confidence": confidence, "source_text": quote}


def _payload(kind, scalars, tables):
    fields, table_specs = ai_fields.FIELD_LISTS[kind]
    payload = {name: scalars.get(name, {"value": None, "confidence": None, "source_text": None}) for name, _, _ in fields}
    for name in table_specs:
        payload[name] = tables.get(name, {"rows": [], "confidence": None, "source_text": None})
    return payload


def _mock_client(tool_input):
    response = mock.Mock()
    response.content = [ToolUseBlock(id="toolu_x", input=tool_input, name=ai_fields.TOOL_NAME, type="tool_use")]
    response.usage = mock.Mock(input_tokens=2000, output_tokens=800)
    response.stop_reason = "tool_use"
    client = mock.Mock()
    client.messages.create.return_value = response
    return client


def test_classify_doc_kind():
    assert ai_fields.classify_doc_kind(HAP_PAGES) == "hap_contract"
    assert ai_fields.classify_doc_kind(LURA_PAGES) == "lura"
    # a retail lease mentioning restrictive covenants is still a lease
    lease = [{"page": 1, "text": "RETAIL LEASE. Tenant shall comply with all restrictive covenants of record."}]
    assert ai_fields.classify_doc_kind(lease) is None
    # ...and so is one whose subordination clause, deep in the body, names a declaration
    # (a one-page .txt upload: the whole lease is "page 1")
    long_lease = [{"page": 1, "text": "RETAIL LEASE. " + "Tenant shall pay rent. " * 2000 +
                   "subordinate to any declaration of restrictive covenants now or hereafter imposed"}]
    assert ai_fields.classify_doc_kind(long_lease) is None
    # the earliest title wins: a LURA that mentions a HAP contract later is a LURA
    mixed = [{"page": 1, "text": "REGULATORY AGREEMENT ... units under a HAP contract shall ..."}]
    assert ai_fields.classify_doc_kind(mixed) == "lura"
    # a recognised form's kind wins over the title
    assert ai_doc_kind({"doc_kind": "hap_contract"}, LURA_PAGES) == "hap_contract"
    assert ai_doc_kind({"doc_kind": None}, LURA_PAGES) == "lura"
    print("✓ test_classify_doc_kind: PASS")


def test_the_ai_is_asked_for_program_fields():
    hap = ai_fields._build_tool("hap_contract")
    props = hap["input_schema"]["properties"]
    for name in ("contract_number", "contract_units", "effective_date", "expiration_date", "renewal_term_years", "unit_mix"):
        assert name in props, name
    assert {"contract_units", "contract_rent"} <= set(props["unit_mix"]["properties"]["rows"]["items"]["properties"])
    lura = ai_fields._build_tool("lura")["input_schema"]["properties"]
    for name in ("min_applicable_fraction", "ami_limit_pct", "compliance_period_years", "extended_use_years",
                 "low_income_units", "set_asides", "bins"):
        assert name in lura, name
    # no CRE-only slots, so no permitted use or exclusivity to invent
    assert "permitted_use" not in props and "exclusivity_clause" not in lura
    print("✓ test_the_ai_is_asked_for_program_fields: PASS")


def test_hap_contract_values_and_unit_mix():
    payload = _payload("hap_contract", {
        "contract_number": _entry("ZZ99E000001", "Contract Number: ZZ99E000001"),
        "owner_name": _entry("Maple Ridge Housing LP", "Owner: Maple Ridge Housing LP"),
        "effective_date": _entry("January 1, 2026", "begins on January 1, 2026"),
        "contract_units": _entry("20", "Contract units", "medium"),
    }, {"unit_mix": {"rows": [
        {"bedrooms": "1", "total_units": None, "contract_units": "12 units", "contract_rent": "$900", "proposed_rent": None},
        {"bedrooms": "2", "total_units": None, "contract_units": "8", "contract_rent": "$1,100", "proposed_rent": None},
    ], "confidence": "high", "source_text": "1 BR, 12 units, $900; 2 BR, 8 units, $1,100"}})
    client = _mock_client(payload)
    out = ai_fields.extract_program_fields(HAP_PAGES, "hap_contract", client=client)
    pf = out["program_fields"]
    assert pf["contract_number"]["value"] == "ZZ99E000001" and pf["contract_number"]["method"] == "ai"
    assert pf["contract_number"]["source"]["page"] == 1
    assert pf["contract_units_1br"]["value"] == "12" and pf["units_2br"]["value"] == "8"
    assert pf["contract_rent_2br"]["value"] == "$1,100" and pf["contract_rent_2br"]["source"]["page"] == 2
    assert "proposed_rent_1br" not in pf and "expiration_date" not in pf     # not stated -> not reported
    # lease fields come from the program values; no tenant on a HAP contract
    assert out["lease_fields"]["landlord"]["value"] == "Maple Ridge Housing LP"
    assert out["lease_fields"]["lease_start_date"]["value"] == "January 1, 2026"
    assert out["lease_fields"]["tenant"]["value"] is None
    assert out["_ai_meta"]["input_tokens"] == 2000 and out["_ai_meta"]["doc_kind"] == "hap_contract"
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": ai_fields.TOOL_NAME}
    assert "HAP" in kwargs["messages"][0]["content"]
    print("✓ test_hap_contract_values_and_unit_mix: PASS")


def test_lura_set_asides_and_bins():
    payload = _payload("lura", {
        "min_applicable_fraction": _entry("100%", "Not less than 100% of the units"),
        "extended_use_years": _entry("30", "Extended use period: 30 years"),
    }, {
        "set_asides": {"rows": [{"ami_pct": "30%", "units": "4", "pct_of_units": None},
                                {"ami_pct": "60% of AMI", "units": None, "pct_of_units": None}],
                       "confidence": "medium", "source_text": "4 units at 30% of AMI"},
        "bins": {"rows": [{"bin": "ZZ-26-00001"}, {"bin": "ZZ-26-00002"}], "confidence": "high", "source_text": "BIN: ZZ-26-00001"},
    })
    out = ai_fields.extract_program_fields(LURA_PAGES, "lura", client=_mock_client(payload))
    pf = out["program_fields"]
    assert pf["units_at_30_pct_ami"]["value"] == "4"
    assert "units_at_60_pct_ami" not in pf          # tier named, no count given
    assert pf["bin"]["value"] == "ZZ-26-00001" and pf["bin_2"]["value"] == "ZZ-26-00002"
    assert pf["extended_use_years"]["value"] == "30"
    assert out["lease_fields"]["landlord"]["value"] is None
    print("✓ test_lura_set_asides_and_bins: PASS")


def test_failures_raise_like_the_lease_engine():
    client = mock.Mock()
    client.messages.create.return_value = mock.Mock(content=[], stop_reason="end_turn")
    try:
        ai_fields.extract_program_fields(HAP_PAGES, "hap_contract", client=client)
        raise AssertionError("expected AIExtractionError")
    except ai_extraction.AIExtractionError:
        pass
    try:
        ai_fields.extract_program_fields(HAP_PAGES, "tic")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    print("✓ test_failures_raise_like_the_lease_engine: PASS")


if __name__ == "__main__":
    test_classify_doc_kind()
    test_the_ai_is_asked_for_program_fields()
    test_hap_contract_values_and_unit_mix()
    test_lura_set_asides_and_bins()
    test_failures_raise_like_the_lease_engine()
    print("\nAll affordable AI field-list tests passed.")
