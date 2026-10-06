"""Held-out synthetic lease corpus (independent wording from generate.py).

Usage: python tools/lease_corpus/holdout.py --out tools/lease_corpus/holdout_out

All parties, properties, addresses and housing authorities are fictional.
Deterministic (seeded). Python 3.9 compatible.
"""
import argparse
import json
import os
import random
from xml.sax.saxutils import escape

SEED = 20261005

# --------------------------------------------------------------------------
# block helpers: ("h", text) heading, ("p", text) paragraph, ("b", text) bold,
# ("kv", [(label, value)]) two-column table, ("t", rows) grid table (row 0 header),
# ("pb",) page break, ("sp",) spacer
# --------------------------------------------------------------------------


def H(t):
    return ("h", t)


def P(t):
    return ("p", t)


def B(t):
    return ("b", t)


def KV(rows):
    return ("kv", rows)


def T(rows):
    return ("t", rows)


PB = ("pb",)


def money(x):
    return "${:,.2f}".format(x)


CASES = []


def case(cid, family, style, blocks, tenant, landlord, rent, start, end, addr, dep, unit,
         cur_rent=None, cur_end=None, scanned=False, count=1, pet=None, park=None, util=None,
         s8=None, conc=False, changes=None, second=None):
    c = {
        "file": "%s_%s.pdf" % (cid, family),
        "case_id": cid,
        "family": family,
        "style": style,
        "scanned": scanned,
        "expected_lease_count": count,
        "fields": {
            "tenant": tenant,
            "landlord": landlord,
            "rent_amount": money(rent),
            "lease_start_date": start,
            "lease_end_date": end,
            "property_address": addr,
            "security_deposit": money(dep) if dep is not None else None,
            "unit_number": unit,
            "current_rent_amount": money(cur_rent if cur_rent is not None else rent),
            "current_lease_end_date": cur_end or end,
        },
        "pet_charges": pet,
        "parking_charges": park,
        "utility_charges": util,
        "section_8": s8,
        "has_concession": conc,
        "lease_changes": changes or [],
    }
    if second:
        c["second_lease"] = second
    CASES.append((c, blocks))


# ---------------------------------------------------------------- H001
case("H001", "naa_style", "NAA-style numbered paragraphs, whole-dollar rent", [
    H("APARTMENT LEASE CONTRACT"),
    P("Date of Lease Contract: February 12, 2026"),
    P("1. PARTIES. This Lease Contract is between you, the resident(s) named here: Marisol T. Quenby, "
      "and us, the owner: Larkspur Residential Partners LLC. You've agreed to rent the apartment "
      "described below from us."),
    P("2. APARTMENT. You are renting Apartment No. 14-C at 4410 Harbor Pointe Blvd, in the city of Port Alder."),
    P("3. LEASE TERM. The initial term of the Lease Contract begins on the 1st day of March, 2026, and "
      "ends at 11:59 p.m. on the 28th day of February, 2027."),
    P("4. MONTHLY RENT. Monthly rent for the apartment is $1,350, payable in advance on or before the "
      "first day of each month without demand. Prorated rent for a partial first month, if any, is "
      "calculated by dividing monthly rent by the number of days in that month."),
    P("5. SECURITY DEPOSIT. Total security deposit at time of move-in: $500. Refund is made within 30 "
      "days after surrender."),
    P("6. LATE CHARGES. If rent is not received by the 3rd day of the month, you must pay a late charge "
      "of 10% of monthly rent."),
    P("7. KEYS AND LOCKS. You will be given two apartment keys and one mailbox key."),
    P("8. SPECIAL PROVISIONS. None."),
], "Marisol T. Quenby", "Larkspur Residential Partners LLC", 1350, "March 1, 2026", "February 28, 2027",
    "4410 Harbor Pointe Blvd", 500, "14-C")

# ---------------------------------------------------------------- H002
case("H002", "naa_addenda", "NAA-style with RUBS, flat valet/pest/package fees, pet and parking terms", [
    H("APARTMENT LEASE CONTRACT"),
    P("Contract Date: August 3, 2026"),
    P("1. Residents: Devonte R. Halvorsen. Owner: Brightwater Terrace Owner, LP."),
    P("2. Dwelling. Unit No. 3107, 2250 Quillan Creek Drive."),
    P("3. Term. The lease begins on August 15, 2026 and ends on August 14, 2027."),
    P("4. Rent. Resident agrees to pay $1,785.00 per month as monthly rent."),
    P("5. Security deposit. $750.00 is due at signing."),
    H("UTILITY AND SERVICE ADDENDUM"),
    P("A. Water and sewer service to your unit is not separately metered. Owner allocates the property's "
      "water and sewer bills among residents by a ratio billing method (occupant-count formula) and "
      "you will pay your share each month."),
    P("B. Flat monthly services: valet trash collection $25.00; pest control $5.00; package locker "
      "service $4.00. These are billed with rent."),
    H("PET ADDENDUM"),
    P("Resident may keep one (1) dog, 40 lbs. Pet rent: $35.00 per month. Non-refundable pet fee: "
      "$300.00. Refundable pet deposit: $250.00."),
    H("PARKING ADDENDUM"),
    P("Resident is assigned covered space #44. The monthly fee for the space is $60.00."),
], "Devonte R. Halvorsen", "Brightwater Terrace Owner, LP", 1785, "August 15, 2026", "August 14, 2027",
    "2250 Quillan Creek Drive", 750, "3107",
    pet={"monthly_rent": 35.0, "fee": 300.0, "deposit": 250.0}, park={"monthly_fee": 60.0},
    util={"rubs": True, "rubs_utilities": ["sewer", "water"], "flat_monthly_total": 34.0})

# ---------------------------------------------------------------- H003
case("H003", "state_bar_form", "State bar residential lease form, rent spelled out in words and numerals", [
    H("RESIDENTIAL LEASE AGREEMENT"),
    P("THIS AGREEMENT is made on May 20, 2026, between Copperfield Holdings LP, hereinafter called "
      "\"Landlord\", and Rhiannon Okafor-Bell, hereinafter called \"Tenant\"."),
    P("WITNESSETH: Landlord hereby leases to Tenant the premises known as 88 Ashgrove Lane, Unit 2B "
      "(the \"Premises\"), for a term commencing June 1, 2026 and terminating May 31, 2027."),
    P("RENT. Tenant shall pay to Landlord as rent for the Premises the sum of One Thousand Four Hundred "
      "Fifty and 00/100 Dollars ($1,450.00) per month, in advance, on the first day of each calendar month."),
    P("SECURITY. Tenant has deposited with Landlord the sum of $1,450.00 as security for performance of "
      "Tenant's obligations."),
    P("USE. The Premises shall be used solely as a private residence for the Tenant."),
    P("IN WITNESS WHEREOF the parties have signed this agreement."),
], "Rhiannon Okafor-Bell", "Copperfield Holdings LP", 1450, "June 1, 2026", "May 31, 2027",
    "88 Ashgrove Lane", 1450, "2B")

# ---------------------------------------------------------------- H004
case("H004", "plain_english", "Small-landlord plain English, informal", [
    H("Our Rental Agreement"),
    P("This is a simple agreement between me, Walter Pemberton (I own the building and I'm called the "
      "landlord below), and Priya Nandakumar (the tenant). I'm renting you the downstairs apartment at "
      "1207 Birchwood Court, Unit B."),
    P("You can move in on 9/1/2026 and the lease runs until 8/31/2027."),
    P("The rent is $975 a month. Please pay by the 1st. Put a check in my mailbox or use the online "
      "portal. I'll take a $500 security deposit, which you get back if the place is clean and nothing "
      "is broken."),
    P("No smoking. No pets, sorry. Quiet hours start at 10pm. Call me if the heat goes out."),
    P("Signed: Walter Pemberton        Priya Nandakumar"),
], "Priya Nandakumar", "Walter Pemberton", 975, "September 1, 2026", "August 31, 2027",
    "1207 Birchwood Court", 500, "B")

# ---------------------------------------------------------------- H005
case("H005", "hud_model_lease", "HUD Model Lease for Subsidized Programs, project-based Section 8", [
    H("MODEL LEASE FOR SUBSIDIZED PROGRAMS"),
    P("PART I. IDENTIFICATION"),
    KV([("Landlord (Owner)", "Elmstead Gardens Preservation Corp."),
        ("Tenant(s)", "Gloria Mae Tashjian"),
        ("Dwelling Unit", "Apt. 5-F, 1900 Elmstead Place"),
        ("Contract Administrator", "Calloway Valley Housing Authority")]),
    P("1. Term of Lease. The term of this Lease shall be one year beginning on January 1, 2026 and "
      "ending on December 31, 2026. The Lease will renew automatically for successive terms of one year."),
    P("2. Rent. The Contract Rent for the unit is $1,265.00 per month. Total Tenant Payment is $412.00 "
      "per month. The assistance payment made by the Contract Administrator on behalf of the Tenant is "
      "$853.00 per month. The Tenant's rent portion may be adjusted when income is recertified. A utility "
      "allowance of $62.00 is included in the Total Tenant Payment calculation."),
    P("3. Security Deposit. The Tenant has paid a security deposit of $412.00."),
    P("4. Obligations of the Tenant. The Tenant agrees to use the unit solely as a private dwelling."),
], "Gloria Mae Tashjian", "Elmstead Gardens Preservation Corp.", 1265, "January 1, 2026", "December 31, 2026",
    "1900 Elmstead Place", 412, "5-F",
    s8={"is_section_8": True, "pha_name": "Calloway Valley Housing Authority", "contract_rent": 1265.0,
        "tenant_rent": 412.0, "hap_amount": 853.0, "utility_allowance": 62.0})

# ---------------------------------------------------------------- H006
case("H006", "s8_lease", "Section 8 voucher lease, split stated in a single sentence", [
    H("LEASE AGREEMENT - HOUSING CHOICE VOUCHER PROGRAM"),
    P("Owner: Stonebridge Rentals Group, LLC. Resident: Lashonda Veazey-Pruitt. Premises: Unit 5-A, "
      "615 Fenwick Terrace."),
    P("Initial Term. The term begins April 1, 2026 and ends March 31, 2027 and then continues month to month."),
    P("Rent. The rent is $1,400.00 of which the PHA pays $1,050.00 and Resident pays $350.00. The PHA "
      "is Brindlemoor County Housing Authority. Resident is responsible for the Resident portion; the PHA "
      "makes its housing assistance payments directly to Owner. PHA utility allowance: $85.00."),
    P("Security Deposit. Resident has paid $350.00 as a security deposit."),
    P("The Tenancy Addendum (HUD-52641-A) is attached and controls if it conflicts with this lease."),
], "Lashonda Veazey-Pruitt", "Stonebridge Rentals Group, LLC", 1400, "April 1, 2026", "March 31, 2027",
    "615 Fenwick Terrace", 350, "5-A",
    s8={"is_section_8": True, "pha_name": "Brindlemoor County Housing Authority", "contract_rent": 1400.0,
        "tenant_rent": 350.0, "hap_amount": 1050.0, "utility_allowance": 85.0})

# ---------------------------------------------------------------- H007
case("H007", "hap_contract", "HAP contract Part A (contract information) / Part B (body)", [
    H("HOUSING ASSISTANCE PAYMENTS CONTRACT (HAP CONTRACT)"),
    H("Part A of the HAP Contract: Contract Information"),
    P("1. Tenant: Ignacio Delacroix-Mbeki"),
    P("2. Contract unit: 902 Marlowe Street, Apt 4D"),
    P("3. Owner: Pinnacle Ridge Housing Partners LLC"),
    P("4. Initial lease term begins 11/1/25 and ends 10/31/26."),
    P("5. Initial rent to owner: $1,620.00 per month."),
    P("6. Initial housing assistance payment to owner: $1,170.00 per month. The tenant rent to owner "
      "is $450.00 per month. Utility allowance: $110.00."),
    P("7. Security deposit: $450.00."),
    P("8. PHA: Ostrander Valley Housing Commission"),
    H("Part B of the HAP Contract: Body of Contract"),
    P("1. Purpose. The PHA will make housing assistance payments to the owner for the contract unit "
      "leased by the tenant under the lease. The HAP contract term begins on the first day of the lease "
      "term and ends upon termination of the lease."),
], "Ignacio Delacroix-Mbeki", "Pinnacle Ridge Housing Partners LLC", 1620, "November 1, 2025", "October 31, 2026",
    "902 Marlowe Street", 450, "4D",
    s8={"is_section_8": True, "pha_name": "Ostrander Valley Housing Commission", "contract_rent": 1620.0,
        "tenant_rent": 450.0, "hap_amount": 1170.0, "utility_allowance": 110.0})

# ---------------------------------------------------------------- H008
case("H008", "s8_rent_change", "Section 8 lease followed by PHA Notice of Rent Change that raises contract rent", [
    H("RESIDENTIAL LEASE - ASSISTED TENANCY"),
    P("Owner: Greywood Terrace Associates LLC. Tenant: Tamsin Rourke-Aldana. Unit: 7A, 1730 Corbin Avenue."),
    P("Lease term: January 1, 2026 through December 31, 2026."),
    P("Rent to owner is $1,180.00 monthly. Of this amount the Halcyon Bay Housing Authority pays "
      "$880.00 as the housing assistance payment and the tenant pays $300.00. Security deposit: $300.00."),
    PB,
    H("HALCYON BAY HOUSING AUTHORITY"),
    H("NOTICE OF RENT CHANGE"),
    P("Re: Tamsin Rourke-Aldana, 1730 Corbin Avenue, Unit 7A. Owner: Greywood Terrace Associates LLC."),
    P("Following your rent increase request, the contract rent for this unit is approved at $1,235.00 "
      "per month effective July 1, 2026. New tenant rent: $320.00. New housing assistance payment: "
      "$915.00. All other lease terms are unchanged."),
], "Tamsin Rourke-Aldana", "Greywood Terrace Associates LLC", 1180, "January 1, 2026", "December 31, 2026",
    "1730 Corbin Avenue", 300, "7A", cur_rent=1235,
    s8={"is_section_8": True, "pha_name": "Halcyon Bay Housing Authority", "contract_rent": 1180.0,
        "tenant_rent": 300.0, "hap_amount": 880.0, "utility_allowance": None},
    changes=[{"kind": "amendment", "note": "PHA notice of rent change, contract rent 1235 effective July 1, 2026"}])

# ---------------------------------------------------------------- H009
case("H009", "s8_tenant_share_change", "Section 8 lease plus rent-change letter that moves only the tenant/HAP split", [
    H("LEASE AGREEMENT"),
    P("This Lease is made between Riverbend Commons Owner LLC (Owner) and Odalys Fenstermacher "
      "(Tenant) for Apartment 12 at 300 Kestrel Run. The lease starts on February 1, 2026 and ends on "
      "January 31, 2027. Tallgrass Regional Housing Authority administers the Tenant's voucher."),
    KV([("Contract rent to owner", "$1,500.00"),
        ("Tenant share", "$540.00"),
        ("Housing assistance payment", "$960.00"),
        ("Security deposit", "$540.00")]),
    PB,
    H("TALLGRASS REGIONAL HOUSING AUTHORITY"),
    H("Rent Change Notice"),
    P("Due to a change in household income reported at interim recertification, effective June 1, "
      "2026 your portion of rent will be $410.00 and our payment to your landlord will be $1,090.00. "
      "The contract rent to owner of $1,500.00 does not change."),
], "Odalys Fenstermacher", "Riverbend Commons Owner LLC", 1500, "February 1, 2026", "January 31, 2027",
    "300 Kestrel Run", 540, "12",
    s8={"is_section_8": True, "pha_name": "Tallgrass Regional Housing Authority", "contract_rent": 1500.0,
        "tenant_rent": 540.0, "hap_amount": 960.0, "utility_allowance": None},
    changes=[{"kind": "amendment", "note": "tenant share lowered to 410, HAP 1090, contract rent unchanged"}])

# ---------------------------------------------------------------- H010
case("H010", "pet_addendum", "Plain lease followed by Animal Addendum", [
    H("Residential Lease"),
    P("Landlord: Salt Marsh Properties Inc. Tenant: Bartholomew Quint. Premises: 9 Cordgrass Way, #204."),
    P("The tenancy will start July 1, 2026 and expire June 30, 2027. Rent: $1,525.00 each month. "
      "Deposit: $1,000.00."),
    PB,
    H("ANIMAL ADDENDUM"),
    P("The Tenant has asked permission to keep two cats at the Premises. Landlord agrees on these terms: "
      "an additional $50.00 is added to the monthly rent while the animals reside in the unit; "
      "a one-time, non-refundable animal fee of $400.00 is due at move-in. No separate animal deposit "
      "is required."),
    P("Tenant is liable for any damage caused by the animals."),
], "Bartholomew Quint", "Salt Marsh Properties Inc.", 1525, "July 1, 2026", "June 30, 2027",
    "9 Cordgrass Way", 1000, "204", pet={"monthly_rent": 50.0, "fee": 400.0, "deposit": None})

# ---------------------------------------------------------------- H011
case("H011", "garage_addendum", "Lease with garage/parking addendum", [
    H("LEASE"),
    KV([("Landlord", "Ironwood Crossing Holdings LLC"),
        ("Tenant", "Henrietta Vosskuhler"),
        ("Residence", "500 Alder Street, Unit 1204"),
        ("From", "October 1, 2026"),
        ("To", "September 30, 2027"),
        ("Rent", "$2,140.00 / month"),
        ("Deposit", "$2,140.00")]),
    PB,
    H("GARAGE AND PARKING ADDENDUM"),
    P("Tenant is granted use of garage stall G-17. In consideration, Tenant shall pay a monthly garage "
      "charge of $125.00, due with rent. Vehicles must be registered with the office."),
], "Henrietta Vosskuhler", "Ironwood Crossing Holdings LLC", 2140, "October 1, 2026", "September 30, 2027",
    "500 Alder Street", 2140, "1204", park={"monthly_fee": 125.0})

# ---------------------------------------------------------------- H012
case("H012", "utility_addendum", "Lease with ratio-billing addendum covering four utilities plus flat fees", [
    H("RESIDENTIAL LEASE CONTRACT"),
    P("Owner: Cinder Hill Communities LLC. Resident: Zebulon Ashby-Okonkwo. Home: Apartment Unit 14-C, "
      "7600 Cinder Hill Road. Term: 1 April 2026 to 31 March 2027. Monthly rent: $1,295."),
    P("Security deposit: $650.00."),
    H("ADDENDUM: UTILITY BILLING"),
    P("Resident's share of the community's water, sewer, stormwater and trash expenses will be "
      "determined by square footage ratio billing and invoiced monthly by a third-party billing company."),
    P("Resident also pays these fixed monthly charges: pest control, $3.00; valet trash, $30.00."),
], "Zebulon Ashby-Okonkwo", "Cinder Hill Communities LLC", 1295, "April 1, 2026", "March 31, 2027",
    "7600 Cinder Hill Road", 650, "14-C",
    util={"rubs": True, "rubs_utilities": ["sewer", "stormwater", "trash", "water"], "flat_monthly_total": 33.0})

# ---------------------------------------------------------------- H013
case("H013", "renewal_offer", "Original lease summary followed by a signed renewal offer with new rent and term", [
    H("LEASE AGREEMENT SUMMARY"),
    KV([("Landlord", "Lanternfly Court Owners, LLC"),
        ("Resident", "Isaura Montenegro-Quill"),
        ("Address", "95 Lanternfly Court, Apt 22"),
        ("Term", "September 1, 2025 - August 31, 2026"),
        ("Monthly Rent", "$1,310.00"),
        ("Security Deposit", "$655.00")]),
    PB,
    H("LEASE RENEWAL OFFER"),
    P("Dear Isaura, we would like you to stay! Your current lease ends August 31, 2026. We are pleased "
      "to offer you a 12-month renewal from September 1, 2026 through August 31, 2027 at a new monthly "
      "rent of $1,355.00. Please sign and return by July 15."),
    P("Accepted: ______________________   Isaura Montenegro-Quill"),
], "Isaura Montenegro-Quill", "Lanternfly Court Owners, LLC", 1310, "September 1, 2025", "August 31, 2026",
    "95 Lanternfly Court", 655, "22", cur_rent=1355, cur_end="August 31, 2027",
    changes=[{"kind": "renewal"}])

# ---------------------------------------------------------------- H014
case("H014", "rent_amendment", "Lease then mid-term amendment changing rent when an occupant is added", [
    H("LEASE"),
    P("Verbena Row Partners LLC (Landlord) leases 2 Verbena Row, Apartment 305 to Leopold Strand "
      "(Tenant) beginning March 1, 2026 and ending February 28, 2027 for monthly rent of $1,540. "
      "Security deposit $770."),
    PB,
    H("LEASE MODIFICATION AGREEMENT"),
    P("The parties amend the Lease as follows. Effective May 1, 2026, an additional occupant, "
      "Kasimir Strand, is approved to reside in the apartment and the monthly rent is increased to "
      "$1,640.00. Except as modified, the Lease continues in full force."),
], "Leopold Strand", "Verbena Row Partners LLC", 1540, "March 1, 2026", "February 28, 2027",
    "2 Verbena Row", 770, "305", cur_rent=1640, changes=[{"kind": "amendment"}])

# ---------------------------------------------------------------- H015
case("H015", "concession_dollar", "Lease with a dollar-amount move-in concession", [
    H("APARTMENT LEASE"),
    P("Owner: Mariner Walk Apartments LP. Resident: Tobias Greenfield-Ng. Unit 418, 1015 Mariner Walk."),
    P("Lease period: November 1, 2026 to October 31, 2027."),
    P("Monthly rent is $1,675.00. Security deposit is $400.00."),
    P("Special offer: Resident will receive $500 off first month's rent. This is a one-time "
      "concession and is not a rent reduction for later months."),
], "Tobias Greenfield-Ng", "Mariner Walk Apartments LP", 1675, "November 1, 2026", "October 31, 2027",
    "1015 Mariner Walk", 400, "418", conc=True)

# ---------------------------------------------------------------- H016
case("H016", "concession_free_weeks", "14-month lease with six weeks free rent", [
    H("LEASE CONTRACT"),
    P("This lease is between Aspen Slate Residential LLC, Owner, and Winifred O'Callaghan-Sato, Resident, "
      "for Apt 233, 7 Slate Quarry Road. The lease begins May 1, 2026 and ends June 30, 2027 (14 months)."),
    P("Rent per month: $1,820.00. Deposit: $900.00."),
    P("CONCESSION: To make up for the longer term, Owner gives Resident 6 weeks free rent, applied "
      "as the first month and two weeks of the second month."),
], "Winifred O'Callaghan-Sato", "Aspen Slate Residential LLC", 1820, "May 1, 2026", "June 30, 2027",
    "7 Slate Quarry Road", 900, "233", conc=True)

# ---------------------------------------------------------------- H017
case("H017", "two_column_table", "Label/value tables, numeric dates and whole-dollar amounts", [
    H("Residential Lease Summary"),
    KV([("Resident Name", "Cornelius P. Ibarra"),
        ("Owner", "Mossy Oak Flats Owner LLC"),
        ("Premises", "1180 Tamarack Parkway, Unit 308"),
        ("Lease Start", "3/1/26"),
        ("Lease End", "2/28/27"),
        ("Monthly Rent", "$1,350"),
        ("Security Deposit", "$600")]),
    P("By signing below, the resident agrees to the Terms and Conditions on the following pages."),
], "Cornelius P. Ibarra", "Mossy Oak Flats Owner LLC", 1350, "March 1, 2026", "February 28, 2027",
    "1180 Tamarack Parkway", 600, "308")

# ---------------------------------------------------------------- H018
case("H018", "payment_schedule", "Rent only appears in a payment-schedule table", [
    H("LEASE AGREEMENT"),
    P("Landlord: Humboldt Park Terrace LLC. Resident: Everett Lindqvist-Amoah. "
      "Dwelling: 2800 Humboldt Park Terrace, Apt 9. Term: April 1, 2026 to March 31, 2027. "
      "Security deposit: $612.50."),
    P("Resident will pay the amounts in the following schedule on the first of each month."),
    T([["Due date", "Description", "Amount"],
       ["04/01/2026", "Apartment rent", "$1,225.00"],
       ["05/01/2026", "Apartment rent", "$1,225.00"],
       ["06/01/2026", "Apartment rent", "$1,225.00"],
       ["07/01/2026", "Apartment rent", "$1,225.00"],
       ["08/01/2026", "Apartment rent", "$1,225.00"],
       ["09/01/2026", "Apartment rent", "$1,225.00"],
       ["10/01/2026", "Apartment rent", "$1,225.00"],
       ["11/01/2026", "Apartment rent", "$1,225.00"],
       ["12/01/2026", "Apartment rent", "$1,225.00"],
       ["01/01/2027", "Apartment rent", "$1,225.00"],
       ["02/01/2027", "Apartment rent", "$1,225.00"],
       ["03/01/2027", "Apartment rent", "$1,225.00"]]),
], "Everett Lindqvist-Amoah", "Humboldt Park Terrace LLC", 1225, "April 1, 2026", "March 31, 2027",
    "2800 Humboldt Park Terrace", 612.50, "9")

# ---------------------------------------------------------------- H019
case("H019", "co_tenants", "Three residents listed one per line, joint and several", [
    H("RESIDENT(S) AGREEMENT"),
    P("Owner: Whitcomb Lane Apartments, LLC"),
    P("Resident(s):"),
    P("1. Anneliese K. Brandvold"),
    P("2. Tomas Brandvold"),
    P("3. Jun-ho Seo"),
    P("Each of the above is jointly and severally liable for all obligations."),
    P("Home: 47 Whitcomb Lane, Apt. 2R. Term: August 1, 2026 to July 31, 2027. "
      "Rent for the apartment is $2,260.00 per month. Security deposit: $1,000.00."),
], "Anneliese K. Brandvold", "Whitcomb Lane Apartments, LLC", 2260, "August 1, 2026", "July 31, 2027",
    "47 Whitcomb Lane", 1000, "2R")

# ---------------------------------------------------------------- H020
case("H020", "bldg_unit", "Unit given as 'Bldg 3, Unit 210'", [
    H("APARTMENT LEASE CONTRACT"),
    P("1. Parties. Resident: Marguerite Dufresne-Lowe. Owner: Tidewater Row Owner LLC."),
    P("2. Premises. Bldg 3, Unit 210, 3300 Tidewater Row."),
    P("3. Term. January 15, 2026 until January 14, 2027."),
    P("4. Rent. $1,895 per month."),
    P("5. Deposit. $900."),
], "Marguerite Dufresne-Lowe", "Tidewater Row Owner LLC", 1895, "January 15, 2026", "January 14, 2027",
    "3300 Tidewater Row", 900, "210")

# ---------------------------------------------------------------- H021
case("H021", "total_monthly_rent", "'Total Monthly Rent' with breakdown into base rent and fixed fees", [
    H("LEASE AGREEMENT"),
    P("Owner: Pelican Court Residential LLC. Resident: Ravi Chandrasekaran-Doyle. "
      "Premises: 12 Pelican Court, Unit 6-D. The Lease starts February 1, 2026 and ends January 31, 2027. "
      "Security Deposit: $750.00."),
    T([["Monthly Charges", "Amount"],
       ["Base Rent", "$1,480.00"],
       ["Valet Trash", "$28.00"],
       ["Pest Control", "$15.00"],
       ["Package Locker", "$10.00"],
       ["Total Monthly Rent", "$1,533.00"]]),
], "Ravi Chandrasekaran-Doyle", "Pelican Court Residential LLC", 1480, "February 1, 2026", "January 31, 2027",
    "12 Pelican Court", 750, "6-D",
    util={"rubs": False, "rubs_utilities": [], "flat_monthly_total": 53.0})

# ---------------------------------------------------------------- H022
case("H022", "all_caps", "Entire document in capital letters", [
    H("RESIDENTIAL LEASE AGREEMENT"),
    P("THIS LEASE IS ENTERED INTO BETWEEN TALLOW BAY MANAGEMENT, LLC (\"LANDLORD\") AND "
      "ELIAS W. PRENDERGAST (\"TENANT\")."),
    P("PREMISES: 2020 N. LANTERN HILL RD., APT. A-12."),
    P("TERM: THE LEASE TERM BEGINS MARCH 1, 2026 AND ENDS FEBRUARY 28, 2027."),
    P("RENT: TENANT SHALL PAY $1,085.00 PER MONTH, DUE ON THE FIRST DAY OF EACH MONTH."),
    P("SECURITY DEPOSIT: $500.00."),
], "ELIAS W. PRENDERGAST", "TALLOW BAY MANAGEMENT, LLC", 1085, "March 1, 2026", "February 28, 2027",
    "2020 N. LANTERN HILL RD.", 500, "A-12")

# ---------------------------------------------------------------- H023
case("H023", "renewal_rent_bump", "Renewal agreement raising rent while repeating 'same terms' wording", [
    H("RESIDENTIAL LEASE"),
    P("Gannet Point Apartments LP, as Landlord, rents 1500 Gannet Point Road, #11-B to Burke Halloran, "
      "as Tenant, from June 1, 2025 to May 31, 2026. Rent is $1,360.00 per month. Security deposit "
      "is $700.00."),
    PB,
    H("RENEWAL OF LEASE"),
    P("Landlord and Tenant agree the Lease is renewed for another twelve (12) month term, running from "
      "June 1, 2026 to May 31, 2027, on the same terms and conditions, except that monthly rent "
      "will be $1,420.00."),
], "Burke Halloran", "Gannet Point Apartments LP", 1360, "June 1, 2025", "May 31, 2026",
    "1500 Gannet Point Road", 700, "11-B", cur_rent=1420, cur_end="May 31, 2027",
    changes=[{"kind": "renewal"}])

# ---------------------------------------------------------------- H024
case("H024", "two_leases", "Two separate leases for different units concatenated in one PDF", [
    H("LEASE AGREEMENT"),
    P("Sparrowhill Apartments LLC (Owner) rents Apartment 1A, 33 Sparrowhill Road to Ottoline Reyes "
      "(Resident) from January 1, 2026 to December 31, 2026. Monthly rent: $1,175.00. Deposit: $600.00."),
    P("Owner signature: ____________   Resident signature: ____________"),
    PB,
    H("LEASE AGREEMENT"),
    P("Sparrowhill Apartments LLC (Owner) rents Apartment 1B, 33 Sparrowhill Road to Dmitri Kaplan-Eze "
      "(Resident) from January 1, 2026 to December 31, 2026. Monthly rent: $1,260.00. Deposit: $650.00."),
    P("Owner signature: ____________   Resident signature: ____________"),
], "Ottoline Reyes", "Sparrowhill Apartments LLC", 1175, "January 1, 2026", "December 31, 2026",
    "33 Sparrowhill Road", 600, "1A", count=2,
    second={"tenant": "Dmitri Kaplan-Eze", "rent_amount": "$1,260.00"})

# ---------------------------------------------------------------- H025
case("H025", "no_deposit", "Deposit waived with surety bond; no deposit amount stated", [
    H("RENTAL AGREEMENT"),
    P("Parties: Hutchins Family Rentals LLC (\"we\") and Sunniva Albrecht (\"you\")."),
    P("Your home is Apt 1 at 6 Quarry Hill Road. You may live there from October 1, 2026 to "
      "September 30, 2027."),
    P("You will pay $860 on the first of every month. Instead of a security deposit you have bought "
      "a lease surety bond; no deposit is collected."),
], "Sunniva Albrecht", "Hutchins Family Rentals LLC", 860, "October 1, 2026", "September 30, 2027",
    "6 Quarry Hill Road", None, "1")

# ---------------------------------------------------------------- scanned H026-H030
case("H026", "scan_naa", "Scanned NAA-style lease, image only, slight rotation", [
    H("APARTMENT LEASE CONTRACT"),
    P("1. PARTIES. This Lease Contract is between you, the resident(s): Delphine A. Wrenfield, and us, "
      "the owner: Maplecrest Flats Owner, LLC."),
    P("2. APARTMENT. Unit No. 118 at 7140 Sorrel Ridge Drive."),
    P("3. TERM. The initial term begins on the 1st day of May, 2026 and ends on the 30th day of April, 2027."),
    P("4. RENT. Monthly rent is $1,100.00 due on the first of each month."),
    P("5. SECURITY DEPOSIT. $400.00."),
], "Delphine A. Wrenfield", "Maplecrest Flats Owner, LLC", 1100, "May 1, 2026", "April 30, 2027",
    "7140 Sorrel Ridge Drive", 400, "118", scanned=True)

case("H027", "scan_plain", "Scanned small-landlord lease, image only", [
    H("Rental Agreement"),
    P("Landlord: Nadine Voss-Hartley. Tenant: Oswin Tarkington. "
      "Rental unit: Unit B, 58 Linden Alley."),
    P("Beginning June 15, 2026 and ending June 14, 2027."),
    P("Tenant agrees to pay $1,050 per month rent. A security deposit of $1,050 is due at signing."),
], "Oswin Tarkington", "Nadine Voss-Hartley", 1050, "June 15, 2026", "June 14, 2027",
    "58 Linden Alley", 1050, "B", scanned=True)

case("H028", "scan_s8", "Scanned Section 8 lease, rent split in one sentence", [
    H("LEASE - HOUSING CHOICE VOUCHER"),
    P("Owner: Hollis Park Apartments LLC. Resident: Yolanda Prewitt-Nakamura. Unit 9C, 2415 Hollis "
      "Park Drive."),
    P("Term: September 1, 2026 to August 31, 2027."),
    P("The monthly rent is $1,325.00 of which the PHA pays $995.00 and Resident pays $330.00. "
      "PHA: Wexcombe Housing Authority. Utility allowance: $74.00. Security deposit: $330.00."),
], "Yolanda Prewitt-Nakamura", "Hollis Park Apartments LLC", 1325, "September 1, 2026", "August 31, 2027",
    "2415 Hollis Park Drive", 330, "9C", scanned=True,
    s8={"is_section_8": True, "pha_name": "Wexcombe Housing Authority", "contract_rent": 1325.0,
        "tenant_rent": 330.0, "hap_amount": 995.0, "utility_allowance": 74.0})

case("H029", "scan_renewal", "Scanned lease with renewal page, image only", [
    H("LEASE"),
    P("Fernhill Terrace LP rents Unit C-5, 810 Fernhill Terrace to Casimir J. Obuya from "
      "November 1, 2025 to October 31, 2026 at $1,240.00 per month. Deposit $620.00."),
    PB,
    H("RENEWAL AGREEMENT"),
    P("The lease is renewed from November 1, 2026 to October 31, 2027. New monthly rent: $1,290.00."),
], "Casimir J. Obuya", "Fernhill Terrace LP", 1240, "November 1, 2025", "October 31, 2026",
    "810 Fernhill Terrace", 620, "C-5", cur_rent=1290, cur_end="October 31, 2027", scanned=True,
    changes=[{"kind": "renewal"}])

case("H030", "scan_addenda", "Scanned lease with pet and parking terms, image only", [
    H("APARTMENT LEASE"),
    P("Owner: Osprey Landing Residential LLC. Resident: Philippa Gagnon-Treadwell. "
      "Apartment 412, 401 Osprey Landing Way. Term: December 1, 2025 to November 30, 2026. "
      "Rent: $1,960.00 per month. Security deposit: $1,000.00."),
    P("Pet terms: monthly pet rent $40.00; one-time pet fee $250.00 (non-refundable); pet deposit $300.00."),
    P("Reserved parking space: $75.00 per month."),
], "Philippa Gagnon-Treadwell", "Osprey Landing Residential LLC", 1960, "December 1, 2025", "November 30, 2026",
    "401 Osprey Landing Way", 1000, "412", scanned=True,
    pet={"monthly_rent": 40.0, "fee": 250.0, "deposit": 300.0}, park={"monthly_fee": 75.0})


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def render_text_pdf(path, blocks):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    body, head = ss["BodyText"], ss["Heading2"]
    story = []
    for b in blocks:
        k = b[0]
        if k == "h":
            story += [Paragraph(escape(b[1]), head), Spacer(1, 4)]
        elif k == "p":
            story += [Paragraph(escape(b[1]), body), Spacer(1, 6)]
        elif k == "b":
            story += [Paragraph("<b>%s</b>" % escape(b[1]), body), Spacer(1, 6)]
        elif k == "kv":
            data = [[Paragraph(escape(l), body), Paragraph(escape(v), body)] for l, v in b[1]]
            t = Table(data, colWidths=[2.2 * inch, 4.2 * inch])
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                   ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [t, Spacer(1, 8)]
        elif k == "t":
            data = [[Paragraph(escape(c), body) for c in row] for row in b[1]]
            t = Table(data)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
            story += [t, Spacer(1, 8)]
        elif k == "pb":
            story.append(PageBreak())
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=72, rightMargin=72, topMargin=72,
                            bottomMargin=72, invariant=1, title="Lease")
    doc.build(story)


def render_scanned_pdf(path, blocks, rng):
    """Image-only PDF: draw text onto bitmaps with PIL, add noise and a slight tilt."""
    import reportlab
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    fdir = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    reg = ImageFont.truetype(os.path.join(fdir, "Vera.ttf"), 25)
    bold = ImageFont.truetype(os.path.join(fdir, "VeraBd.ttf"), 30)
    W, Hh, margin = 1275, 1650, 130

    def wrap(text, font, draw, width):
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=font) <= width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    pages = []

    def new_page():
        im = Image.new("L", (W, Hh), 255)
        return im, ImageDraw.Draw(im), margin

    im, d, y = new_page()
    for b in blocks:
        k = b[0]
        if k == "pb":
            pages.append(im)
            im, d, y = new_page()
            continue
        if k in ("h", "b"):
            for ln in wrap(b[1], bold, d, W - 2 * margin):
                d.text((margin, y), ln, font=bold, fill=20)
                y += 42
            y += 10
        elif k == "p":
            for ln in wrap(b[1], reg, d, W - 2 * margin):
                d.text((margin, y), ln, font=reg, fill=25)
                y += 36
            y += 14
        elif k == "kv":
            for l, v in b[1]:
                d.text((margin, y), l + ":", font=bold, fill=20)
                d.text((margin + 380, y), v, font=reg, fill=25)
                y += 42
            y += 10
        elif k == "t":
            for row in b[1]:
                for i, c in enumerate(row):
                    d.text((margin + i * 360, y), c, font=reg, fill=25)
                y += 38
            y += 10
    pages.append(im)

    out = []
    for im in pages:
        angle = rng.uniform(-1.2, 1.2)
        im = im.rotate(angle, resample=Image.BICUBIC, fillcolor=245)
        px = im.load()
        for _ in range(9000):  # salt-and-pepper speckle
            x, yy = rng.randrange(W), rng.randrange(Hh)
            px[x, yy] = rng.choice((40, 90, 200))
        im = im.filter(ImageFilter.GaussianBlur(0.6))
        out.append(im.convert("RGB"))
    out[0].save(path, "PDF", resolution=150.0, save_all=True, append_images=out[1:])


def generate(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(SEED)
    cases = []
    for c, blocks in CASES:
        path = os.path.join(out_dir, c["file"])
        if c["scanned"]:
            render_scanned_pdf(path, blocks, rng)
        else:
            render_text_pdf(path, blocks)
        cases.append(c)
    manifest = {
        "seed": SEED,
        "note": "Held-out synthetic corpus: wording written independently of the extractor patterns. "
                "All parties/properties/housing authorities are fictional.",
        "cases": cases,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdout_out"))
    a = ap.parse_args()
    m = generate(a.out)
    print("wrote %d cases to %s" % (len(m["cases"]), a.out))


if __name__ == "__main__":
    main()
