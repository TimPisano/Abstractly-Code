"""
Regression tests: multifamily party names and lease boundaries.

Each case reproduces a bug found by the synthetic multifamily / Section 8
lease corpus (tools/lease_corpus/), all fictional text:

  - One Section 8 lease + its HUD Tenancy Addendum was split into two
    "leases", and the tenant was read as "Lease" -- from "(To be attached
    to Tenant Lease)" -- or "Rent" from "Tenant Rent: $312.00".
  - A renewal agreement ("This Renewal Agreement is between X ...") split
    off as a separate lease.
  - Co-residents "Wen Pruitt and Wen Quintero" came back as "Wen Quintero"
    only, and the second resident's signature line split the lease.
  - The landlord came back as "This Apartment Lease Contract is entered
    into between Cedar Bend Apartments, LLC".
  - "Owner:" / "Resident(s):" labels (apartment-lease wording) were not
    recognized at all.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.field_extractor import FieldExtractor


def _pages(*texts):
    return [{"page": i + 1, "text": t} for i, t in enumerate(texts)]


LEASE_P1 = (
    "APARTMENT LEASE CONTRACT\n1. PARTIES.\nThis Apartment Lease Contract is entered into between "
    'Cedar Bend Apartments Holdings LLC ("Owner") and Wen Pruitt\nand Wen Quintero ("Resident").\n'
    "2. PREMISES. Owner leases to Resident the dwelling located at 1250 Cedar Bend Lane, Apt. 204, "
    "Columbus, OH 43215.\n3. TERM. The initial term begins on March 1, 2026 and ends on February 28, 2027.\n"
    "4. RENT. Resident will pay $1,450.00 per month as rent for the Apartment.\n"
)
LEASE_P2 = (
    "SIGNATURES.\nOWNER: Cedar Bend Apartments Holdings LLC\n"
    "RESIDENT: Wen Pruitt\nRESIDENT: Wen Quintero\n"
)
TENANCY_ADDENDUM = (
    "TENANCY ADDENDUM\nSection 8 Tenant-Based Assistance, Housing Choice Voucher Program\n"
    "(To be attached to Tenant Lease)\n1. Section 8 Voucher Program\n"
    "a. The owner is leasing the contract unit to the tenant.\n"
    "5. Family Payment to Owner\nTenant Rent: $312.00 per month\n"
)
HAP_CONTRACT = (
    "HOUSING ASSISTANCE PAYMENTS CONTRACT (HAP CONTRACT)\nPart A of the HAP Contract: Contract Information\n"
    "1. This HAP contract is between Riverbend County Housing Authority and Cedar Bend Apartments Holdings LLC.\n"
    "2. Tenant: Wen Pruitt\n5. Initial Rent to Owner. The initial rent to owner is: $1,450.00.\n"
)
RENEWAL = (
    "LEASE RENEWAL AGREEMENT\nThis Renewal Agreement is between Cedar Bend Apartments Holdings LLC "
    '("Owner") and Wen Pruitt and Wen Quintero ("Resident") for 1250 Cedar Bend Lane, Apt. 204.\n'
    "The Lease is renewed for a term beginning March 1, 2027 and ending February 29, 2028.\n"
)


def test_tenancy_addendum_and_hap_contract_stay_with_their_lease():
    fe = FieldExtractor()
    pages = _pages(LEASE_P1, LEASE_P2, TENANCY_ADDENDUM, HAP_CONTRACT)
    assert fe.detect_lease_boundaries(pages) == [(1, 4)], fe.detect_lease_boundaries(pages)
    fields = fe.extract_fields(pages)
    assert fields["tenant"]["value"] == "Wen Pruitt", fields["tenant"]
    print("✓ HUD Tenancy Addendum + HAP contract stay one lease; tenant is not 'Lease'/'Rent': PASS")


def test_heading_words_are_never_party_names():
    fe = FieldExtractor()
    fields = fe.extract_fields(_pages(TENANCY_ADDENDUM))
    assert fields["tenant"]["value"] not in ("Lease", "Rent"), fields["tenant"]
    print("✓ 'Tenant Lease' / 'Tenant Rent' are not read as a tenant: PASS")


def test_renewal_agreement_does_not_split():
    fe = FieldExtractor()
    pages = _pages(LEASE_P1, LEASE_P2, RENEWAL)
    assert fe.detect_lease_boundaries(pages) == [(1, 3)], fe.detect_lease_boundaries(pages)
    print("✓ Renewal agreement stays with its lease: PASS")


def test_co_residents_first_named_is_tenant_all_kept():
    fe = FieldExtractor()
    fields = fe.extract_fields(_pages(LEASE_P1, LEASE_P2))
    assert fields["tenant"]["value"] == "Wen Pruitt", fields["tenant"]
    assert fields["tenant"]["details"]["residents"] == ["Wen Pruitt", "Wen Quintero"], fields["tenant"]
    assert fe.detect_lease_boundaries(_pages(LEASE_P1, LEASE_P2)) == [(1, 2)]
    print("✓ Co-residents: first-named is the tenant, all kept, no split: PASS")


def test_landlord_lead_in_prose_is_stripped():
    fe = FieldExtractor()
    fields = fe.extract_fields(_pages(LEASE_P1))
    assert fields["landlord"]["value"] == "Cedar Bend Apartments Holdings LLC", fields["landlord"]
    print("✓ 'is entered into between' lead-in stripped from landlord: PASS")


def test_owner_and_residents_labels():
    fe = FieldExtractor()
    fields = fe.extract_fields(_pages(
        "APARTMENT LEASE CONTRACT\nCommunity: Willow Creek Commons\nOwner: Willow Creek Commons Owner, LLC\n"
        "Resident(s): Leah Ellis and Owen Varga\nMonthly Rent: $1,210.00\n"
    ))
    assert fields["landlord"]["value"] == "Willow Creek Commons Owner, LLC", fields["landlord"]
    assert fields["tenant"]["value"] == "Leah Ellis", fields["tenant"]
    # The label match stops at the first name; every co-resident is still kept.
    assert fields["tenant"]["details"]["residents"] == ["Leah Ellis", "Owen Varga"], fields["tenant"]
    print("✓ 'Owner:' and 'Resident(s):' labels recognized, co-residents kept: PASS")


def test_company_names_with_and_are_not_split():
    fe = FieldExtractor()
    assert FieldExtractor.split_person_list("Smith and Jones Holdings LLC") is None
    fields = fe.extract_fields(_pages(
        'This Lease is made between Acme Realty LLC and Blue Sky Roasters, Inc. ("Tenant").\n'
    ))
    assert fields["tenant"]["value"] == "Blue Sky Roasters, Inc.", fields["tenant"]
    fields = fe.extract_fields(_pages(
        'This Lease is made by Dover Retail, Inc., having an address at 525 Great Road, Littleton ("Landlord") '
        'and Acme Co. ("Tenant").'
    ))
    assert fields["landlord"]["value"] == "Dover Retail, Inc.", fields["landlord"]
    print("✓ Company names with 'and' handled as before; 'having an address at' tail dropped: PASS")


def test_two_real_leases_still_split_around_an_addendum():
    fe = FieldExtractor()
    other = (
        "APARTMENT LEASE CONTRACT\nThis Lease is made by and between Juniper Ridge Residential, LLC "
        '("Owner") and Darnell Okafor ("Resident").\nResident will pay $980.00 per month as rent.\n'
    )
    pages = _pages(LEASE_P1, LEASE_P2, TENANCY_ADDENDUM, other)
    assert fe.detect_lease_boundaries(pages) == [(1, 3), (4, 4)], fe.detect_lease_boundaries(pages)
    print("✓ Two genuinely separate leases still split (addendum stays with the first): PASS")


if __name__ == "__main__":
    test_tenancy_addendum_and_hap_contract_stay_with_their_lease()
    test_heading_words_are_never_party_names()
    test_renewal_agreement_does_not_split()
    test_co_residents_first_named_is_tenant_all_kept()
    test_landlord_lead_in_prose_is_stripped()
    test_owner_and_residents_labels()
    test_company_names_with_and_are_not_split()
    test_two_real_leases_still_split_around_an_addendum()
    print("\nAll multifamily party/boundary tests passed.")
