"""
Regression tests: multifamily rent and lease dates (regex engine).

Each case is a miss or wrong value the synthetic multifamily / Section 8
corpus (tools/lease_corpus/) found. All text is fictional.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.field_extractor import FieldExtractor, _words_to_number


def _pages(*texts):
    return [{"page": i + 1, "text": t} for i, t in enumerate(texts)]


def _f(*texts):
    return FieldExtractor().extract_fields(_pages(*texts))


def test_apartment_prose_rent():
    f = _f("4. RENT.\nResident will pay $1,245.00 per month as rent for the Apartment, due on or before the 1st day.")
    assert f["rent_amount"]["value"] == "$1,245.00", f["rent_amount"]
    assert f["rent_amount"]["confidence"] == "high"
    print("✓ '$X per month as rent' found: PASS")


def test_pet_rent_is_not_the_rent():
    f = _f(
        "4. RENT. Resident will pay $2,170.00 per month as rent for the Apartment.",
        "PET ADDENDUM\nResident agrees to pay additional monthly rent of $50.00 for the animal.",
    )
    assert f["rent_amount"]["value"] == "$2,170.00", f["rent_amount"]
    f = _f("PET ADDENDUM\nResident agrees to pay additional monthly rent of $50.00 for the animal.")
    assert f["rent_amount"]["value"] is None, f["rent_amount"]
    print("✓ Pet rent never reported as the apartment rent: PASS")


def test_renewal_rent_does_not_replace_base_rent():
    f = _f(
        "APARTMENT LEASE CONTRACT\nThe initial term of the Lease begins on March 1, 2026 and ends at 11:59 p.m. on "
        "February 28, 2027.\nThe Owner and Resident agree to a monthly rent described in the rent schedule.",
        "FIRST AMENDMENT TO LEASE\nEffective July 1, 2026, monthly rent is changed to $2,040.00 per month.",
        "RENT SCHEDULE\nMonthly Rent: $2,115.00",
    )
    # With no rent stated on the lease pages, fall back to the whole
    # document -- but "ends at 11:59 p.m." must still give the lease's end.
    assert f["lease_end_date"]["value"] == "February 28, 2027", f["lease_end_date"]
    f = _f(
        "APARTMENT LEASE CONTRACT\nMonthly Rent: $2,115.00\nLease End Date: February 28, 2027",
        "LEASE RENEWAL AGREEMENT\nThe Lease is renewed for a term beginning March 1, 2027 and ending "
        "February 29, 2028. Effective March 1, 2027, the monthly rent shall be $2,200.00.",
    )
    assert f["rent_amount"]["value"] == "$2,115.00", f["rent_amount"]
    assert f["lease_end_date"]["value"] == "February 28, 2027", f["lease_end_date"]
    print("✓ Renewal rent/end date don't overwrite the base lease's: PASS")


def test_end_date_with_clock_time():
    f = _f("The initial term of the Lease begins on November 1, 2026 and ends at 11:59 p.m. on October 31, 2027.")
    assert f["lease_end_date"]["value"] == "October 31, 2027", f["lease_end_date"]
    print("✓ 'ends at 11:59 p.m. on DATE' found: PASS")


def test_section8_contract_rent_not_tenant_portion():
    f = _f(
        "TENANCY ADDENDUM\nTenant Rent: $312.00 per month",
        "HAP CONTRACT\n5. Initial Rent to Owner. The initial rent to owner is: $1,450.00.",
    )
    assert f["rent_amount"]["value"] == "$1,450.00", f["rent_amount"]
    print("✓ Section 8: rent is the contract rent, not the tenant portion: PASS")


def test_rent_in_words_only():
    assert _words_to_number("Seventeen Hundred Eighty") == 1780
    assert _words_to_number("One Thousand Two Hundred Five") == 1205
    assert _words_to_number("Monthly") is None
    f = _f("Resident shall pay Owner the sum of One Thousand Seven Hundred Eighty Dollars per month as rent.")
    assert f["rent_amount"]["value"] == "$1,780.00", f["rent_amount"]
    assert f["rent_amount"]["confidence"] == "medium"
    print("✓ Rent written only in words converted, medium confidence: PASS")


if __name__ == "__main__":
    test_apartment_prose_rent()
    test_pet_rent_is_not_the_rent()
    test_renewal_rent_does_not_replace_base_rent()
    test_end_date_with_clock_time()
    test_section8_contract_rent_not_tenant_portion()
    test_rent_in_words_only()
    print("\nAll multifamily rent/date tests passed.")
