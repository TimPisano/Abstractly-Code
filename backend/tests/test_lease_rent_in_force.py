"""
Regression tests (reviewer, 2026-10-06), run through the Deal Mismatch
Report's real detectors with LEASE_MULTIFAMILY_FIELDS OFF:

1. A Section 8 lease whose body states only the family's share ("Resident
   will pay $312.00 per month ...") reported rent_amount = $312, so the
   report showed a false $1,138/mo rent mismatch against a rent roll
   carrying the $1,450 contract rent stated in the HAP contract.
2. A lease with its renewal (or a rent amendment) in the same file kept the
   ORIGINAL rent and term, so a renewed unit showed a false rent mismatch,
   two false date mismatches and a false "expired but occupied".

And the guard rails: real mismatches are still reported, and a Section 8
file with no contract rent at all reports "not found", never $312.
All lease text is fictional. The Anthropic client is mocked.
"""

import os
import sys
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from anthropic.types import ToolUseBlock

from app import ai_extraction, deal_mismatch as dm, multifamily_charges as mf
from app.field_extractor import FieldExtractor

ADDR = "1250 Cedar Bend Lane, Apt. 204, Columbus, OH 43215"
HEAD = (f'APARTMENT LEASE CONTRACT\nThis Lease is made by and between Cedar Bend Apartments Holdings LLC ("Owner") '
        f'and Wen Pruitt ("Resident").\nThe dwelling is located at {ADDR}.\n'
        "The initial term begins on March 1, 2026 and ends on February 28, 2027.\n")
ADDENDUM = "TENANCY ADDENDUM\nSection 8 Tenant-Based Assistance, Housing Choice Voucher Program\nTenant Rent: $312.00 per month"
HAP = ("HOUSING ASSISTANCE PAYMENTS CONTRACT (HAP CONTRACT)\n5. Initial Rent to Owner. The initial rent to owner is: "
       "$1,450.00.\n6. Housing Assistance Payment. The initial housing assistance payment is: $1,138.00 per month.")
SHARE_PHRASINGS = [
    "4. RENT. Resident will pay $312.00 per month as Resident's share of the rent.",
    "Monthly Rent: $312.00",
    "Rent: $312.00 (tenant portion)",
    "Monthly rent payable by Tenant: $312.00",
    "Tenant shall pay $312.00 per month, the balance being paid by the PHA.",
    "Rent is $312.00 per month; the PHA pays the remainder directly to Owner.",
]
RENEWAL = ("LEASE RENEWAL AGREEMENT\nThe Lease dated March 1, 2026 is renewed for a term beginning March 1, 2027 and "
           "ending February 29, 2028.\nEffective March 1, 2027, the monthly rent shall be $1,510.00.")
AMENDMENT = "FIRST AMENDMENT TO LEASE\nEffective July 1, 2026, monthly rent is changed to $1,400.00 per month."
BASE = HEAD + "Resident will pay $1,450.00 per month as rent for the Apartment."


def _pages(*texts):
    return [{"page": i + 1, "text": t} for i, t in enumerate(texts)]


def _extract(*texts):
    with mock.patch.dict(os.environ, {mf.FLAG_ENV: ""}):  # flag OFF, as reported
        return FieldExtractor().extract_fields(_pages(*texts))


def _rent_roll(rent, start, end):
    return {"id": 1, "filename": "rentroll.csv", "extracted_fields": {
        "property_address": {"value": ADDR}, "tenant": {"value": "Wen Pruitt"}, "rent_amount": {"value": rent},
        "lease_start_date": {"value": start}, "lease_end_date": {"value": end}}}


def _findings(rent_roll, fields, today):
    leases = [rent_roll, {"id": 2, "filename": "lease.pdf", "extracted_fields": fields}]
    rows = (dm.detect_rent_mismatch(leases, today=today) + dm.detect_dates_mismatch(leases)
            + dm.detect_expired_but_occupied(leases, today=today))
    return [(r["discrepancy_type"], r.get("field")) for r in rows]


def test_section_8_share_in_the_lease_body_is_never_the_rent():
    rr = _rent_roll("$1,450.00", "March 1, 2026", "February 28, 2027")
    for phrasing in SHARE_PHRASINGS:
        f = _extract(HEAD + phrasing, ADDENDUM, HAP)
        assert f["rent_amount"]["value"] == "$1,450.00", (phrasing, f["rent_amount"])
        assert _findings(rr, f, date(2026, 6, 1)) == [], phrasing
    print(f"✓ Section 8: {len(SHARE_PHRASINGS)} tenant-share phrasings -> contract rent $1,450, no false mismatch: PASS")


def test_section_8_with_no_contract_rent_is_not_found_not_the_share():
    f = _extract(HEAD + "Monthly Rent: $312.00", ADDENDUM)
    assert f["rent_amount"]["value"] is None, f["rent_amount"]
    assert "tenant's share" in f["rent_amount"]["validation_note"]
    print("✓ Section 8 file with no contract rent: rent not found (with a note), never the $312 share: PASS")


def test_renewed_unit_has_no_false_findings():
    rr = _rent_roll("$1,510.00", "March 1, 2027", "February 29, 2028")
    for base in (BASE, HEAD.replace("The initial term begins on March 1, 2026 and ends on February 28, 2027.\n",
                                    "Lease Start Date: March 1, 2026\nLease End Date: February 28, 2027\n")
                 + "Monthly Rent: $1,450.00"):
        f = _extract(base, RENEWAL)
        assert (f["rent_amount"]["value"], f["lease_start_date"]["value"], f["lease_end_date"]["value"]) == \
            ("$1,510.00", "March 1, 2027", "February 29, 2028"), f
        assert _findings(rr, f, date(2027, 6, 1)) == []
    f = _extract(BASE, AMENDMENT)
    assert f["rent_amount"]["value"] == "$1,400.00"
    assert _findings(_rent_roll("$1,400.00", "March 1, 2026", "February 28, 2027"), f, date(2026, 9, 1)) == []
    print("✓ Renewal / amendment in the file: in-force rent and term, no false findings: PASS")


def test_real_mismatches_are_still_reported():
    # Contract rent $1,450 vs a rent roll showing $1,500 -> still a rent mismatch.
    f = _extract(HEAD + "Monthly Rent: $312.00", ADDENDUM, HAP)
    assert _findings(_rent_roll("$1,500.00", "March 1, 2026", "February 28, 2027"), f, date(2026, 6, 1)) == \
        [("rent_mismatch", "rent_amount")]
    # Renewed to $1,510, rent roll still shows the old $1,450 -> a real finding.
    f = _extract(BASE, RENEWAL)
    found = _findings(_rent_roll("$1,450.00", "March 1, 2027", "February 29, 2028"), f, date(2027, 6, 1))
    assert found == [("rent_mismatch", "rent_amount")], found
    print("✓ Real mismatches (wrong contract rent, rent roll not updated after renewal) still reported: PASS")


def _ai(pages, **overrides):
    payload = {n: {"value": None, "confidence": None, "source_text": None} for n in ai_extraction.active_fields()}
    for name, (value, quote) in overrides.items():
        payload[name] = {"value": value, "confidence": "high", "source_text": quote}
    response = mock.Mock()
    response.content = [ToolUseBlock(id="t", input=payload, name="record_lease_abstraction", type="tool_use")]
    response.usage = mock.Mock(input_tokens=1, output_tokens=1)
    client = mock.Mock()
    client.messages.create.return_value = response
    return ai_extraction.extract_lease_fields(pages, client=client)


def test_ai_engine_follows_the_same_rules():
    with mock.patch.dict(os.environ, {mf.FLAG_ENV: ""}):
        f = _ai(_pages(HEAD + SHARE_PHRASINGS[0], ADDENDUM, HAP),
                rent_amount=("$312.00", "Resident will pay $312.00 per month as Resident's share of the rent."))
        assert f["rent_amount"]["value"] == "$1,450.00", f["rent_amount"]
        f = _ai(_pages(BASE, RENEWAL),
                rent_amount=("$1,450.00", "Resident will pay $1,450.00 per month as rent for the Apartment."),
                lease_end_date=("February 28, 2027", "ends on February 28, 2027"))
        assert (f["rent_amount"]["value"], f["lease_end_date"]["value"]) == ("$1,510.00", "February 29, 2028"), f
    assert "IN FORCE" in ai_extraction.SYSTEM_PROMPT and "CONTRACT RENT" in ai_extraction.FIELD_GUIDANCE["rent_amount"]
    print("✓ AI engine (mocked): tenant share replaced by contract rent; renewal in force: PASS")


if __name__ == "__main__":
    test_section_8_share_in_the_lease_body_is_never_the_rent()
    test_section_8_with_no_contract_rent_is_not_found_not_the_share()
    test_renewed_unit_has_no_false_findings()
    test_real_mismatches_are_still_reported()
    test_ai_engine_follows_the_same_rules()
    print("\nAll in-force rent / Section 8 rent regression tests passed.")
