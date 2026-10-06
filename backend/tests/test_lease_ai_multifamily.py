"""
AI engine (prompt v3): residential / Section 8 guidance and the
multifamily fields behind LEASE_MULTIFAMILY_FIELDS. The Anthropic client
is always mocked -- no real API call is made here.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from anthropic.types import ToolUseBlock

from app import ai_extraction, multifamily_charges as mf

PAGES = [
    {"page": 1, "text": "APARTMENT LEASE CONTRACT\nThis Lease is made by and between Cedar Bend Apartments Holdings LLC "
                        "(\"Owner\") and Wen Pruitt (\"Resident\") for 1250 Cedar Bend Lane, Apt. 204, Columbus, OH 43215.\n"
                        "The initial term begins on March 1, 2026 and ends on February 28, 2027.\n"
                        "Resident will pay $1,450.00 per month as rent for the Apartment."},
    {"page": 2, "text": "TENANCY ADDENDUM\nSection 8 Tenant-Based Assistance, Housing Choice Voucher Program\n"
                        "The owner has entered into a HAP contract with Granite Valley Public Housing Agency.\n"
                        "Tenant Rent: $312.00 per month"},
    {"page": 3, "text": "HAP CONTRACT\n5. Initial Rent to Owner. The initial rent to owner is: $1,450.00.\n"
                        "6. Housing Assistance Payment. The initial housing assistance payment is: $1,138.00 per month."},
    {"page": 4, "text": "PET ADDENDUM\nMonthly Pet Rent: $35.00 per month, in addition to rent.\n"
                        "Resident shall pay a one-time non-refundable pet fee of $300.00."},
    {"page": 5, "text": "LEASE RENEWAL AGREEMENT\nThe Lease is renewed for a term beginning March 1, 2027 and ending "
                        "February 29, 2028.\nEffective March 1, 2027, the monthly rent shall be $1,510.00."},
]


def _payload(fields, **overrides):
    payload = {n: {"value": None, "confidence": None, "source_text": None} for n in fields}
    for name, (value, confidence, quote) in overrides.items():
        payload[name] = {"value": value, "confidence": confidence, "source_text": quote}
    return payload


def _client(tool_input):
    response = mock.Mock()
    response.content = [ToolUseBlock(id="toolu_x", input=tool_input, name="record_lease_abstraction", type="tool_use")]
    response.usage = mock.Mock(input_tokens=10, output_tokens=10)
    response.stop_reason = "tool_use"
    client = mock.Mock()
    client.messages.create.return_value = response
    return client


def _flag(on):
    return mock.patch.dict(os.environ, {mf.FLAG_ENV: "1" if on else ""})


def test_flag_off_schema_is_core_fields_plus_termination():
    with _flag(False):
        tool = ai_extraction._build_tool()
        assert set(tool["input_schema"]["properties"]) == set(ai_extraction.LEASE_FIELDS)
        assert "termination_options" in tool["input_schema"]["properties"]
        assert not set(mf.MF_FIELDS) & set(tool["input_schema"]["properties"])
        assert ai_extraction.prompt_version() == "v3"
    print("✓ Flag off: core fields + termination_options only, prompt v3: PASS")


def test_prompt_is_residential_and_section_8_aware():
    assert "Section 8" in ai_extraction.SYSTEM_PROMPT and "multifamily" in ai_extraction.SYSTEM_PROMPT
    assert "commercial lease." not in ai_extraction._user_message(PAGES)
    rent = ai_extraction.FIELD_GUIDANCE["rent_amount"]
    assert "CONTRACT RENT" in rent and "pet rent" in rent and "renewal" in rent
    print("✓ Prompt covers multifamily, Section 8 contract rent, renewals: PASS")


def test_flag_on_schema_asks_for_mf_fields_but_not_derived_ones():
    with _flag(True):
        props = set(ai_extraction._build_tool()["input_schema"]["properties"])
        assert set(ai_extraction.MF_FIELDS) <= props
        assert "current_rent_amount" not in props and "current_lease_end_date" not in props
        assert ai_extraction.prompt_version() == "v3+mf"
    print("✓ Flag on: MF fields requested, current_* derived not asked: PASS")


def test_details_come_from_the_quote_not_the_models_arithmetic():
    with _flag(True):
        fields_list = ai_extraction.active_fields()
        payload = _payload(
            fields_list,
            rent_amount=("$1,450.00", "high", "Resident will pay $1,450.00 per month as rent for the Apartment."),
            lease_end_date=("February 28, 2027", "high", "ends on February 28, 2027"),
            unit_number=("Apt. 204", "high", "1250 Cedar Bend Lane, Apt. 204"),
            # The model's display says HAP $9,999 -- the quote says $1,138.00. The quote wins.
            section_8=("Section 8; PHA Granite Valley Public Housing Agency; HAP $9,999", "high",
                       "HAP contract with Granite Valley Public Housing Agency ... Tenant Rent: $312.00 per month ... "
                       "The initial rent to owner is: $1,450.00 ... The initial housing assistance payment is: $1,138.00 per month"),
            pet_charges=("$35.00/mo pet rent; $300.00 pet fee", "high",
                         "Monthly Pet Rent: $35.00 per month ... a one-time non-refundable pet fee of $300.00"),
            lease_changes=("Renewal effective March 1, 2027: rent $1,510.00", "high",
                           "Effective March 1, 2027, the monthly rent shall be $1,510.00."),
        )
        f = ai_extraction.extract_lease_fields(PAGES, client=_client(payload))
    s8 = f["section_8"]["details"]
    assert (s8["contract_rent"], s8["tenant_rent"], s8["hap_amount"]) == (1450.0, 312.0, 1138.0), s8
    assert s8["pha_name"] == "Granite Valley Public Housing Agency"
    assert f["pet_charges"]["details"] == {"monthly_rent": 35.0, "fee": 300.0, "deposit": None}
    assert f["unit_number"]["value"] == "204"
    assert f["lease_changes"]["details"]["changes"][0]["new_rent"] == 1510.0
    assert f["current_rent_amount"]["value"] == "$1,510.00"
    assert f["current_lease_end_date"]["value"] == "February 29, 2028"
    assert f["rent_amount"]["value"] == "$1,450.00"
    assert f["_ai_meta"]["prompt_version"] == "v3+mf"
    print("✓ AI multifamily details parsed from the verbatim quote; current_* derived: PASS")


def test_unparseable_ai_value_is_kept_but_low_confidence():
    pages = [{"page": 1, "text": "Resident will pay $1,000.00 per month as rent."}]
    with _flag(True):
        payload = _payload(ai_extraction.active_fields(),
                           pet_charges=("pet fees apply", "high", "pet fees apply per the community policy"))
        f = ai_extraction.extract_lease_fields(pages, client=_client(payload))
    assert f["pet_charges"]["value"] == "pet fees apply"
    assert f["pet_charges"]["confidence"] == "low" and "verify" in f["pet_charges"]["validation_note"]
    print("✓ A value nobody can price is kept, marked low, never $0: PASS")


def test_model_not_found_stays_not_found():
    with _flag(True):
        f = ai_extraction.extract_lease_fields(PAGES, client=_client(_payload(ai_extraction.active_fields())))
    assert f["section_8"]["value"] is None and f["pet_charges"]["value"] is None
    print("✓ The regex parser doesn't overrule the model's 'not found': PASS")


if __name__ == "__main__":
    test_flag_off_schema_is_core_fields_plus_termination()
    test_prompt_is_residential_and_section_8_aware()
    test_flag_on_schema_asks_for_mf_fields_but_not_derived_ones()
    test_details_come_from_the_quote_not_the_models_arithmetic()
    test_unparseable_ai_value_is_kept_but_low_confidence()
    test_model_not_found_stays_not_found()
    print("\nAll AI multifamily tests passed.")
