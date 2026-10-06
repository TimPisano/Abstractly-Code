"""
Regression tests: real-world residential lease phrasings the regex engine
missed on the independently written held-out corpus
(tools/lease_corpus/holdout.py). Text here is fictional and reworded.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import multifamily_charges as mf
from app.field_extractor import FieldExtractor


def _f(*texts):
    return FieldExtractor().extract_fields([{"page": i + 1, "text": t} for i, t in enumerate(texts)])


def _v(fields, name):
    return fields[name]["value"]


def test_term_ranges_and_day_first_dates():
    f = _f("Term: 1 April 2026 to 31 March 2027. Monthly rent: $1,295.")
    assert (_v(f, "lease_start_date"), _v(f, "lease_end_date")) == ("April 1, 2026", "March 31, 2027"), f
    f = _f("Lease term: January 1, 2026 through December 31, 2026.")
    assert (_v(f, "lease_start_date"), _v(f, "lease_end_date")) == ("January 1, 2026", "December 31, 2026")
    f = _f("3. Term. January 15, 2026 until January 14, 2027.")
    assert (_v(f, "lease_start_date"), _v(f, "lease_end_date")) == ("January 15, 2026", "January 14, 2027")
    f = _f("The lease starts on February 1, 2026 and ends on January 31, 2027.")
    assert (_v(f, "lease_start_date"), _v(f, "lease_end_date")) == ("February 1, 2026", "January 31, 2027")
    print("✓ Term ranges, 'starts on', 'until', day-first dates: PASS")


def test_rent_labels_and_prose():
    cases = {
        "Rent: $1,525.00 each month. Deposit: $1,000.00.": "$1,525.00",
        "Rent per month: $1,820.00.": "$1,820.00",
        "4. Rent. $1,895 per month.": "$1,895",
        "The rent is $975 a month. Please pay by the 1st.": "$975",
        "RENT: TENANT SHALL PAY $1,085.00 PER MONTH, DUE ON THE FIRST DAY.": "$1,085.00",
        "LEASE\nLandlord\nAcme Rentals LLC\nRent\n$2,140.00 / month\nDeposit\n$2,140.00": "$2,140.00",
        "to Casimir Obuya from November 1, 2025 to October 31, 2026 at $1,240.00 per month.": "$1,240.00",
        "Tenant shall pay as rent for the Premises the sum of One Thousand Four Hundred Fifty and 00/100 "
        "Dollars ($1,450.00) per month, in advance.": "$1,450.00",
        "The Contract Rent for the unit is $1,265.00 per month. Total Tenant Payment is $412.00 per month.": "$1,265.00",
    }
    for text, want in cases.items():
        got = _v(_f(text), "rent_amount")
        assert got == want, (text, got)
    # A charges table: the base rent, never the total including fees.
    f = _f("Monthly Charges\nTotal Monthly Rent\n$1,533.00\nBase Rent\n$1,480.00\n")
    assert _v(f, "rent_amount") == "$1,480.00", f["rent_amount"]
    print("✓ Rent labels, table rows and prose with a per-month cue: PASS")


def test_plain_deposit_label_not_pet_deposit():
    assert _v(_f("Rent per month: $1,820.00. Deposit: $900.00."), "security_deposit") == "$900.00"
    assert _v(_f("Pet deposit: $300.00."), "security_deposit") is None
    print("✓ Plain 'Deposit:' label, never a pet deposit: PASS")


def test_party_phrasings():
    f = _f('THIS AGREEMENT is made between Copperfield Holdings LP, hereinafter called\n"Landlord", and '
           'Rhiannon Okafor-Bell, hereinafter called "Tenant".')
    assert (_v(f, "landlord"), _v(f, "tenant")) == ("Copperfield Holdings LP", "Rhiannon Okafor-Bell"), f
    f = _f("LEASE\nGannet Point Apartments LP, as Landlord, rents 1500 Gannet Point Road, #11-B to Burke Halloran, as\nTenant, "
           "from June 1, 2025 to May 31, 2026.")
    assert (_v(f, "landlord"), _v(f, "tenant")) == ("Gannet Point Apartments LP", "Burke Halloran"), f
    f = _f("LEASE AGREEMENT\nSparrowhill Apartments LLC (Owner) rents Apartment 1A, 33 Sparrowhill Road to Ottoline Reyes\n(Resident).")
    assert (_v(f, "landlord"), _v(f, "tenant")) == ("Sparrowhill Apartments LLC", "Ottoline Reyes"), f
    f = _f('Parties: Hutchins Family Rentals LLC ("we") and Sunniva Albrecht ("you").')
    assert (_v(f, "landlord"), _v(f, "tenant")) == ("Hutchins Family Rentals LLC", "Sunniva Albrecht"), f
    f = _f("Residential Lease Summary\nResident Name\nCornelius P. Ibarra\nOwner\nMossy Oak Flats Owner LLC\n")
    assert (_v(f, "landlord"), _v(f, "tenant")) == ("Mossy Oak Flats Owner LLC", "Cornelius P. Ibarra"), f
    f = _f("RESIDENT(S) AGREEMENT\nOwner: Whitcomb Lane Apartments, LLC\nResident(s):\n1. Anneliese K. Brandvold\n2. Tomas Brandvold\n")
    assert _v(f, "tenant") == "Anneliese K. Brandvold", f["tenant"]
    f = _f("MODEL LEASE FOR SUBSIDIZED PROGRAMS\nPART I. IDENTIFICATION\nLandlord (Owner)\nElmstead Gardens Preservation Corp.\n"
           "Tenant(s)\nGloria Mae Tashjian\n")
    assert (_v(f, "landlord"), _v(f, "tenant")) == ("Elmstead Gardens Preservation Corp.", "Gloria Mae Tashjian"), f
    f = _f("1. PARTIES. This Lease Contract is between you, the resident(s) named here: Marisol T. Quenby, and\n"
           "us, the owner: Larkspur Residential Partners LLC.")
    assert (_v(f, "landlord"), _v(f, "tenant")) == ("Larkspur Residential Partners LLC", "Marisol T. Quenby"), f
    print("✓ hereinafter called / as Landlord / (Owner) / (\"we\") / table labels / numbered list / NAA: PASS")


def test_street_address_without_located_at():
    cases = {
        "Premises: Unit 5-A, 615 Fenwick Terrace, Dayton, OH 45402.": "615 Fenwick Terrace",
        "I'm renting you the downstairs apartment at 1207\nBirchwood Court, Unit B.": "1207 Birchwood Court",
        "PREMISES: 2020 N. LANTERN HILL RD., APT. A-12.": "2020 N. LANTERN HILL RD",
        "Dwelling Unit\nApt. 5-F, 1900 Elmstead Place\n": "1900 Elmstead Place",
    }
    for text, want in cases.items():
        got = _v(_f(text), "property_address")
        assert got and got.startswith(want), (text, got)
    f = _f("Send all notices to Owner at 77 Commerce Street, Suite 400.\nPremises: 12 Pelican Court, Unit 6-D.")
    assert _v(f, "property_address").startswith("12 Pelican Court"), f["property_address"]
    # The unit stays in the address -- the report matches leases to rent roll
    # units by address, and the lease's display name is built from it.
    cases = {
        'the dwelling located at 9021 Pinehaven Court, Apartment No. 3B, Richmond, VA 23233 (the "Premises")':
            "9021 Pinehaven Court, Apartment No. 3B, Richmond, VA 23233",
        "You are renting Apartment No. 14-C at 4410 Harbor Pointe Blvd, in the city of Port Alder.":
            "4410 Harbor Pointe Blvd, Apartment No. 14-C",
        "Dwelling Unit\nApt. 5-F, 1900 Elmstead Place\n": "1900 Elmstead Place, Apt. 5-F",
        "Tenant: Tamsin Rourke. Unit: 7A, 1730 Corbin Avenue, Fairview.": "1730 Corbin Avenue, Unit: 7A",
        "PREMISES: 2020 N. LANTERN HILL RD., APT. A-12.": "2020 N. LANTERN HILL RD., APT. A-12",
    }
    for text, want in cases.items():
        got = _v(_f(text), "property_address")
        assert got == want, (text, got)
    print("✓ Street address found by premises cue, not the owner's notice address; unit kept: PASS")


def test_unit_ids_with_letters_and_hyphens():
    cases = {
        "You are renting Apartment No. 14-C at 4410 Harbor Pointe Blvd.": "14-C",
        "Home: Apartment Unit 14-C, 7600 Cinder Hill Road.": "14-C",
        "Premises: 9 Cordgrass Way, #204.": "204",
        "rents 1500 Gannet Point Road, #11-B to Burke Halloran": "11-B",
        "Rental unit: Unit B, 58 Linden Alley.": "B",
        "Resident: Tobias Greenfield-Ng. Unit 418, 1015 Mariner Walk.": "418",
    }
    for text, want in cases.items():
        got = mf.parse_unit_number(mf._Doc([{"page": 1, "text": text}]))["value"]
        assert got == want, (text, got)
    print("✓ Unit IDs like 14-C, #11-B, Unit B: PASS")


if __name__ == "__main__":
    with mock.patch.dict(os.environ, {"LEASE_MULTIFAMILY_FIELDS": ""}):
        test_term_ranges_and_day_first_dates()
        test_rent_labels_and_prose()
        test_plain_deposit_label_not_pet_deposit()
        test_party_phrasings()
        test_street_address_without_located_at()
        test_unit_ids_with_letters_and_hyphens()
    print("\nAll residential phrasing tests passed.")
