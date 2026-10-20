"""HUD-52641 HCV HAP contract (4/2023), Tarrant County (TX) copy. No AcroForm: absolute placements.

This copy's text layer has no spaces between words (e.g. "Theinitialleasetermbeginson").
Values use long-form dates and different money formatting from hud_52641_rhanc.

Same fictional HCV unit as hud_52517_rfta (requested rent = contract rent).
"""

from world import Household, Member, VoucherTenancy

OWNER = "Maple Ridge Housing Partners LP"
PHA = "Riverbend Housing Authority"
HEAD = "Renata Quillfeather"
UNIT = "1450 Maple Ridge Drive, Apt 2B, Riverbend, IN 46990"

HH = Household(members=[
    Member("Renata", "Quillfeather", "Head", 34, "03/14/1992", annual_wages=31_200),
    Member("Milo", "Quillfeather", "Child", 9, "06/02/2017"),
    Member("Ivy", "Quillfeather", "Child", 6, "09/21/2020"),
])
T = VoucherTenancy(HH, contract_rent=1_325, utility_allowance=142, payment_standard=1_480)

# "Paid by" column for 8. Utilities and Appliances (matches the RFTA).
PAID_BY = [("Heating", 128, "T"), ("Cooking", 153, "T"), ("Water Heating", 178, "O"),
           ("Other Electric", 200, "T"), ("Water", 226, "O"), ("Sewer", 252, "O"),
           ("Trash", 279, "O"), ("Air Conditioning", 305, "T"), ("Refrigerator", 369, "O"),
           ("Range", 390, "O")]

SPEC = {
    "id": "hud_52641_tarrant",
    "source": "hud_52641_tarrant.pdf",
    "form": "HUD-52641 HAP Contract, Section 8 Tenant-Based Assistance (4/2023)",
    "program": "HCV",
    "doc_type": "hap_contract",
    "notes": ("Same fictional HCV unit as hud_52517_rfta and hud_52641_rhanc. Text layer of the source has no "
              f"word spaces. HAP = min(payment standard $1,480, gross rent ${T.gross_rent:,}) - TTP ${T.total_tenant_payment:,}."),
    "placements": [
        # Part A, page 2
        {"page": 2, "at": (72, 242), "text": HEAD},
        {"page": 2, "at": (72, 306), "text": UNIT},
        *[{"page": 2, "at": (72, 395 + 13 * i), "text": m.name} for i, m in enumerate(HH.members)],
        {"page": 2, "at": (232, 537), "text": "December 1, 2026"},
        {"page": 2, "at": (232, 558), "text": "November 30, 2027"},
        {"page": 2, "at": (170, 592), "text": f"{T.contract_rent:,}.00"},
        {"page": 2, "at": (272, 670), "text": f"{T.hap:,}"},
        # Utilities, page 3
        {"page": 3, "at": (143, 129), "size": 10, "text": "X"},   # heating: natural gas
        {"page": 3, "at": (290, 154), "size": 10, "text": "X"},   # cooking: electric
        {"page": 3, "at": (143, 179), "size": 10, "text": "X"},   # water heating: natural gas
        *[{"page": 3, "at": (530, top), "text": who} for _, top, who in PAID_BY],
        # Signatures, page 3
        {"page": 3, "at": (45, 484), "text": PHA},
        {"page": 3, "at": (325, 484), "text": OWNER},
        {"page": 3, "at": (45, 522), "text": "/s/ Delphine Arkwright"},
        {"page": 3, "at": (325, 522), "text": "/s/ Callum Northey"},
        {"page": 3, "at": (45, 559), "text": "Delphine Arkwright, HCV Program Manager"},
        {"page": 3, "at": (325, 559), "text": "Callum Northey, Managing Member"},
        {"page": 3, "at": (45, 596), "text": "11/24/2026"},
        {"page": 3, "at": (325, 596), "text": "11/20/2026"},
        {"page": 3, "at": (325, 632), "text": OWNER},
        {"page": 3, "at": (325, 671), "text": "200 Commerce Way, Suite 410"},
        {"page": 3, "at": (325, 698), "text": "Riverbend, IN 46990"},
    ],
    "lease_fields": {
        "tenant": HEAD,
        "landlord": OWNER,
        "rent_amount": "$1,325.00",
        "lease_start_date": "December 1, 2026",
        "lease_end_date": "November 30, 2027",
        "property_address": UNIT,
        "security_deposit": None,
    },
    "program_fields": {
        "tenant_name": {"value": HEAD, "type": "text"},
        "contract_unit_address": {"value": UNIT, "type": "text"},
        **{f"household_member_{i + 1}": {"value": m.name, "type": "text"} for i, m in enumerate(HH.members)},
        "lease_term_start": {"value": "12/01/2026", "type": "date", "shown_as": "December 1, 2026"},
        "lease_term_end": {"value": "11/30/2027", "type": "date", "shown_as": "November 30, 2027"},
        "initial_rent_to_owner": {"value": f"${T.contract_rent:,}", "type": "money", "shown_as": f"{T.contract_rent:,}.00"},
        "initial_hap": {"value": f"${T.hap:,}", "type": "money", "shown_as": f"{T.hap:,}"},
        "pha_name": {"value": PHA, "type": "text"},
        "owner_name": {"value": OWNER, "type": "text"},
        "pha_signature_date": {"value": "11/24/2026", "type": "date"},
        "owner_signature_date": {"value": "11/20/2026", "type": "date"},
        "payee_address": {"value": "200 Commerce Way, Suite 410", "type": "text"},
        "heating_paid_by": {"value": "T", "type": "checkbox"},
        "water_paid_by": {"value": "O", "type": "checkbox"},
    },
}
