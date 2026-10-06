"""
Multifamily lease terms (app/multifamily_charges.py) and the
LEASE_MULTIFAMILY_FIELDS flag. All lease text here is fictional.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import multifamily_charges as mf
from app.field_extractor import FieldExtractor


def _pages(*texts):
    return [{"page": i + 1, "text": t} for i, t in enumerate(texts)]


def _doc(*texts):
    return mf._Doc(_pages(*texts))


LEASE = (
    "APARTMENT LEASE CONTRACT\nThis Lease is made by and between Juniper Ridge Residential, LLC (\"Owner\") and "
    "Darnell Okafor (\"Resident\").\nThe dwelling is located at 730 Juniper Ridge Road, Apt. 3B, Boise, ID 83702.\n"
    "The initial term begins on March 1, 2026 and ends at 11:59 p.m. on February 28, 2027.\n"
    "Resident will pay $1,450.00 per month as rent for the Apartment.\n"
)


def test_flag_off_by_default_adds_no_keys():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop(mf.FLAG_ENV, None)
        fields = FieldExtractor().extract_fields(_pages(LEASE))
    assert not set(mf.MF_FIELDS) & set(fields), sorted(fields)
    print("✓ Flag off (default): no multifamily keys: PASS")


def test_flag_on_adds_every_key():
    with mock.patch.dict(os.environ, {mf.FLAG_ENV: "1"}):
        fields = FieldExtractor().extract_fields(_pages(LEASE))
    assert set(mf.MF_FIELDS) <= set(fields), sorted(fields)
    assert fields["unit_number"]["value"] == "3B"
    assert fields["current_rent_amount"]["value"] == "$1,450.00"
    assert fields["current_rent_amount"]["details"] == {"from": "lease"}
    assert fields["current_lease_end_date"]["value"] == "February 28, 2027"
    assert fields["section_8"]["value"] is None and fields["pet_charges"]["value"] is None
    print("✓ Flag on: every multifamily key present, base values carried: PASS")


def test_unit_number_shapes():
    cases = {
        "Unit: 14C\n": "14C",
        "Apartment No. 204\n": "204",
        "located at 88 Willow Creek Drive, Unit # 111, Raleigh": "111",
        "2200 Brookstone\nParkway, Apt. 412, Kansas City, MO": "412",
        "1609 Sable Oaks Circle, Unit B-215, San Antonio": "B-215",
    }
    for text, want in cases.items():
        got = mf.parse_unit_number(_doc(text))["value"]
        assert got == want, (text, got)
    assert mf.parse_unit_number(_doc("the owner is leasing the contract unit to the tenant"))["value"] is None
    print("✓ Unit number shapes: PASS")


def test_pet_charges():
    e = mf.parse_pet_charges(_doc(
        "PET ADDENDUM\nMonthly Pet Rent: $35.00 per month, in addition to rent.\n"
        "Resident shall pay a one-time non-refundable pet fee of $300.00.\n"
        "Additional Pet Deposit: $250.00. The pet deposit is refundable."
    ))
    assert e["details"] == {"monthly_rent": 35.0, "fee": 300.0, "deposit": 250.0}, e
    e = mf.parse_pet_charges(_doc("Resident agrees to pay additional monthly rent of $40.00 for the animal."))
    assert e["details"]["monthly_rent"] == 40.0 and e["details"]["fee"] is None
    assert mf.parse_pet_charges(_doc("No animals are allowed. Pet Deposit: N/A"))["value"] is None
    # Adjacent clauses are quoted once, not repeated per charge.
    e = mf.parse_pet_charges(_doc("Monthly Pet Rent: $35.00 per month. Resident shall pay a one-time non-refundable pet fee of $300.00."))
    assert e["source"]["quote"].count("$35.00") == 1, e["source"]
    print("✓ Pet rent / fee / deposit: PASS")


def test_parking_charges():
    e = mf.parse_parking_charges(_doc("PARKING ADDENDUM\nAssigned Space: P-14\nMonthly Parking Fee: $75.00"))
    assert e["details"] == {"monthly_fee": 75.0, "space": "P-14"}, e
    e = mf.parse_parking_charges(_doc("Resident will pay a garage rental fee of $125.00 per month for detached garage G-7."))
    assert e["details"]["monthly_fee"] == 125.0, e
    assert mf.parse_parking_charges(_doc("Resident may park in unassigned spaces at no additional charge."))["value"] is None
    print("✓ Parking fee and space: PASS")


def test_utility_charges():
    e = mf.parse_utility_charges(_doc(
        "UTILITY ADDENDUM\nWater, sewer and trash service will be billed to Resident by Owner using a ratio utility "
        "billing system (RUBS) allocation based on the number of occupants.\nValet Trash: $25.00 per month flat fee\n"
        "Pest Control: $3.00 per month flat fee\n"
    ))
    d = e["details"]
    assert d["rubs"] and d["rubs_utilities"] == ["water", "sewer", "trash"], d
    assert d["flat_monthly_total"] == 28.0, d
    # Maple Ridge wording: pro-rata bill-back, "wastewater" means sewer.
    e = mf.parse_utility_charges(_doc(
        "Owner bills back water, wastewater, and trash removal on a pro-rata basis each month as additional rent."
    ))
    assert e["details"]["rubs_utilities"] == ["water", "sewer", "trash"], e
    # Owner-paid utilities and an operating-expense pro rata share are not RUBS.
    assert mf.parse_utility_charges(_doc("Owner pays for water, sewer, and trash."))["value"] is None
    assert mf.parse_utility_charges(_doc("Tenant pays its pro rata share of operating expenses."))["value"] is None
    print("✓ RUBS utilities and flat monthly fees: PASS")


S8 = (
    "TENANCY ADDENDUM\nSection 8 Tenant-Based Assistance, Housing Choice Voucher Program\n"
    "b. The owner has entered into a HAP contract with Granite Valley Public Housing Agency (the \"PHA\").\n"
    "Tenant Rent: $312.00 per month\n",
    "HOUSING ASSISTANCE PAYMENTS CONTRACT (HAP CONTRACT)\n5. Initial Rent to Owner. The initial rent to owner is: $1,450.00.\n"
    "6. Housing Assistance Payment. The initial housing assistance payment is: $1,138.00 per month.\n"
    "7. Utility Allowance: $88.00 per month (tenant-paid electric).\n",
)


def test_section_8_split():
    e = mf.parse_section_8(_doc(*S8))
    d = e["details"]
    assert d["pha_name"] == "Granite Valley Public Housing Agency", d
    assert (d["contract_rent"], d["tenant_rent"], d["hap_amount"], d["utility_allowance"]) == (1450.0, 312.0, 1138.0, 88.0), d
    assert e["confidence"] == "high" and "validation_note" not in e
    print("✓ Section 8: PHA, contract rent = tenant rent + HAP, utility allowance: PASS")


def test_section_8_split_that_does_not_add_up_is_flagged_not_fixed():
    bad = (S8[0], S8[1].replace("$1,138.00", "$1,038.00"))
    e = mf.parse_section_8(_doc(*bad))
    assert e["details"]["hap_amount"] == 1038.0  # reported as written
    assert e["confidence"] == "medium" and "not the contract rent" in e["validation_note"], e
    print("✓ Section 8 split that doesn't add up: flagged, numbers kept as written: PASS")


def test_non_section_8_lease_has_no_section_8_entry():
    assert mf.parse_section_8(_doc(LEASE))["value"] is None
    print("✓ Market-rate lease: no Section 8 entry: PASS")


def test_lease_changes_and_current_terms():
    pages = _pages(
        LEASE,
        "LEASE RENEWAL AGREEMENT\nThe Lease dated March 1, 2026 is renewed for a term beginning March 1, 2027 and "
        "ending February 29, 2028.\nEffective March 1, 2027, the monthly rent shall be $1,510.00.\n",
    )
    with mock.patch.dict(os.environ, {mf.FLAG_ENV: "1"}):
        f = FieldExtractor().extract_fields(pages)
    assert f["rent_amount"]["value"] == "$1,450.00"  # base lease unchanged
    changes = f["lease_changes"]["details"]["changes"]
    assert len(changes) == 1 and changes[0]["kind"] == "renewal" and changes[0]["new_rent"] == 1510.0, changes
    assert f["current_rent_amount"]["value"] == "$1,510.00", f["current_rent_amount"]
    assert f["current_rent_amount"]["source"]["page"] == 2
    assert f["current_lease_end_date"]["value"] == "February 29, 2028", f["current_lease_end_date"]
    print("✓ In-document renewal: change listed, current rent/end follow it, base untouched: PASS")


def test_lease_page_mentioning_renewal_options_is_not_a_change():
    pages = _pages(LEASE, "12. RENEWAL. Resident may renew by giving 60 days notice. Rent upon renewal is set by Owner.")
    assert mf.parse_lease_changes(pages)["value"] is None
    print("✓ A lease clause about renewal isn't a renewal document: PASS")


def test_section_8_prose_and_table_wording():
    # Voucher lease that never says "Section 8".
    e = mf.parse_section_8(_doc(
        "LEASE AGREEMENT - HOUSING CHOICE VOUCHER PROGRAM\nRent. The rent is $1,400.00 of which the PHA pays "
        "$1,050.00 and Resident pays $350.00. The PHA is Brindlemoor County Housing Authority. PHA utility allowance: $85.00."
    ), base_rent=1400.0)
    d = e["details"]
    assert (d["contract_rent"], d["tenant_rent"], d["hap_amount"], d["utility_allowance"]) == (1400.0, 350.0, 1050.0, 85.0), d
    # HUD model lease: Total Tenant Payment + Contract Administrator.
    e = mf.parse_section_8(_doc(
        "Contract Administrator\nCalloway Valley Housing Authority\n2. Rent. The Contract Rent for the unit is $1,265.00 per "
        "month. Total Tenant Payment is $412.00 per month. The assistance payment made by the Contract Administrator on "
        "behalf of the Tenant is $853.00 per month."
    ))
    d = e["details"]
    assert (d["contract_rent"], d["tenant_rent"], d["hap_amount"]) == (1265.0, 412.0, 853.0), d
    assert d["pha_name"] == "Calloway Valley Housing Authority", d
    # Payer-first: the HAP is the authority's figure, not the tenant's that follows.
    e = mf.parse_section_8(_doc(
        "Rent to owner is $1,180.00 monthly. Of this amount the Halcyon Bay Housing Authority pays $880.00\n"
        "as the housing assistance payment and the tenant pays $300.00."
    ))
    assert (e["details"]["hap_amount"], e["details"]["tenant_rent"]) == (880.0, 300.0), e["details"]
    # Two-column table.
    e = mf.parse_section_8(_doc(
        "Tallgrass Regional Housing Authority administers the Tenant's voucher.\nContract rent to owner\n$1,500.00\n"
        "Tenant share\n$540.00\nHousing assistance payment\n$960.00\n"
    ))
    d = e["details"]
    assert (d["contract_rent"], d["tenant_rent"], d["hap_amount"]) == (1500.0, 540.0, 960.0), d
    # A PHA name wrapped across a line break is kept whole.
    e = mf.parse_section_8(_doc("Section 8. The owner has a HAP contract with Granite\nValley Public Housing Agency (the PHA)."))
    assert e["details"]["pha_name"] == "Granite Valley Public Housing Agency", e["details"]
    print("✓ Section 8 split from prose, HUD model lease and table wording: PASS")


def test_rent_change_notice_is_a_change_not_the_lease_split():
    pages = _pages(
        "LEASE\nRent to owner is $1,180.00 monthly. Of this amount the Halcyon Bay Housing Authority pays $880.00 "
        "as the housing assistance payment and the tenant pays $300.00.",
        "HALCYON BAY HOUSING AUTHORITY\nNOTICE OF RENT CHANGE\nThe contract rent for this unit is approved at $1,235.00 "
        "per month effective July 1, 2026. New tenant rent: $320.00. New housing assistance payment: $915.00.",
    )
    ch = mf.parse_lease_changes(pages)["details"]["changes"]
    assert len(ch) == 1 and ch[0]["new_rent"] == 1235.0, ch  # contract rent, not "New tenant rent"
    assert (ch[0]["new_tenant_rent"], ch[0]["new_hap_amount"]) == (320.0, 915.0), ch
    s8 = mf.parse_section_8(mf._Doc(pages))["details"]
    assert (s8["tenant_rent"], s8["hap_amount"]) == (300.0, 880.0), s8  # the lease's own split
    # An income-only change: no new contract rent, still recorded.
    ch = mf.parse_lease_changes(_pages(
        "LEASE\nRent: $1,500.00",
        "TALLGRASS REGIONAL HOUSING AUTHORITY\nRent Change Notice\nEffective June 1, 2026 your portion of rent will be "
        "$410.00 and our payment to your landlord will be $1,090.00.",
    ))["details"]["changes"]
    assert (ch[0]["new_tenant_rent"], ch[0]["new_hap_amount"]) == (410.0, 1090.0), ch
    print("✓ Rent change notices: contract rent vs tenant/HAP split, lease split kept separate: PASS")


def test_renewal_running_from_range_sets_new_end():
    ch = mf.parse_lease_changes(_pages(
        "RESIDENTIAL LEASE\nRent is $1,360.00 per month.",
        "RENEWAL OF LEASE\nThe Lease is renewed for another twelve (12) month term, running from\nJune 1, 2026 to "
        "May 31, 2027, except that monthly rent will be\n$1,420.00.",
    ))["details"]["changes"]
    assert (ch[0]["effective_date"], ch[0]["new_end_date"], ch[0]["new_rent"]) == ("June 1, 2026", "May 31, 2027", 1420.0), ch
    print("✓ Renewal 'running from X to Y': new end date and rent: PASS")


def test_utility_wording_variants():
    e = mf.parse_utility_charges(_doc(
        "A. Water and sewer service to your unit is not separately metered. Owner allocates the property's water\n"
        "and sewer bill among residents.\nB. Flat monthly services: valet trash collection $25.00; pest control $5.00; "
        "package locker service\n$4.00. These are billed with rent."
    ))
    d = e["details"]
    assert d["rubs_utilities"] == ["water", "sewer"] and d["flat_monthly_total"] == 34.0, d
    e = mf.parse_utility_charges(_doc(
        "Resident's share of the community's water, sewer, stormwater and trash expenses will be determined\n"
        "by square footage ratio billing.\nResident also pays these fixed monthly charges: pest control, $3.00; valet trash, $30.00."
    ))
    d = e["details"]
    assert d["rubs_utilities"] == ["water", "sewer", "trash", "stormwater"] and d["flat_monthly_total"] == 33.0, d
    e = mf.parse_utility_charges(_doc("Monthly Charges\nBase Rent\n$1,480.00\nValet Trash\n$28.00\nPest Control\n$15.00\n"))
    assert e["details"]["flat_monthly_total"] == 43.0, e
    # A one-time fee with no "monthly" anywhere near it is not a monthly charge.
    assert mf.parse_utility_charges(_doc("Move-in: trash can deposit $50.00 at signing."))["value"] is None
    print("✓ Utility wording: not separately metered, ratio billing, fee lists and tables: PASS")


def test_pet_and_parking_wording_variants():
    e = mf.parse_pet_charges(_doc("an additional $50.00 is added to the monthly rent while the animals reside in the unit; "
                                  "a one-time, non-refundable animal fee of $400.00 is due at move-in."))
    assert (e["details"]["monthly_rent"], e["details"]["fee"]) == (50.0, 400.0), e
    e = mf.parse_parking_charges(_doc("Resident is assigned covered space #44. The monthly fee for the space is $60.00."))
    assert e["details"] == {"monthly_fee": 60.0, "space": "44"}, e
    e = mf.parse_parking_charges(_doc("Tenant is granted use of garage stall G-17. Tenant shall pay a monthly garage charge\nof $125.00."))
    assert e["details"]["monthly_fee"] == 125.0, e
    print("✓ Pet 'added to the monthly rent' and parking 'fee for the space': PASS")


if __name__ == "__main__":
    test_flag_off_by_default_adds_no_keys()
    test_flag_on_adds_every_key()
    test_unit_number_shapes()
    test_pet_charges()
    test_parking_charges()
    test_utility_charges()
    test_section_8_split()
    test_section_8_split_that_does_not_add_up_is_flagged_not_fixed()
    test_non_section_8_lease_has_no_section_8_entry()
    test_lease_changes_and_current_terms()
    test_lease_page_mentioning_renewal_options_is_not_a_change()
    test_section_8_prose_and_table_wording()
    test_rent_change_notice_is_a_change_not_the_lease_split()
    test_renewal_running_from_range_sets_new_end()
    test_utility_wording_variants()
    test_pet_and_parking_wording_variants()
    print("\nAll multifamily charge tests passed.")
