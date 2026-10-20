"""CHFA 2024 LIHTC Land Use Restriction Agreement template (9/23 rev). No AcroForm.

Values are typed onto the template's blanks (underscore runs and inline gaps)
for the fictional Cedar Hollow Apartments (46 units, 44 Tax Credit Units at 60%
AMI, 40-60 set-aside, BIN CO-26-00417, minimum applicable fraction 95.65%).
Bracketed options the template leaves to the drafter ([4%][9%], [30/40]
years) are left as printed: a typed overlay can't delete them, so the
extended use term isn't in the key.
"""

OWNER = "Cedar Hollow Housing LP"
ADDRESS = "2750 Cedar Hollow Lane, Alder Springs, CO 81099"

SPEC = {
    "id": "lura_co_chfa",
    "source": "lura_co_chfa.pdf",
    "form": "CHFA Low-Income Housing Tax Credit Land Use Restriction Agreement (2024 template, 9/23 rev)",
    "program": "LIHTC",
    "doc_type": "lura",
    "notes": "Agreement date's year (2024) is printed by the template; only 'December 9' is typed. "
             "Bracketed drafter options left unresolved. Signers are fictional.",
    "placements": [
        # p1 preamble: "dated as of ____, 2024, is by and between ____, a Colorado ____ and its successors"
        {"at": (74, 232), "page": 1, "text": "December 9"},
        {"at": (330, 232), "page": 1, "text": OWNER},
        {"at": (74, 244), "page": 1, "text": "limited partnership"},
        # Recital C: "owner of a ( ) unit ... City of , County of , ... commonly known as ____"
        {"at": (300, 397), "page": 1, "text": "46"},
        {"at": (165, 408.5), "page": 1, "text": "Alder Springs"},
        {"at": (311, 408.5), "page": 1, "text": "Larkspur"},
        {"at": (251, 420), "page": 1, "text": "Cedar Hollow Apartments", "size": 8},
        # 6: set-aside election, 40-60 line
        {"at": (151, 490.5), "page": 6, "text": "X"},
        # 7(b): 44 units at 60% or less of AMI
        {"at": (184, 235.5), "page": 7, "text": "Forty-four", "size": 5.5},
        {"at": (218.5, 235.5), "page": 7, "text": "44", "size": 7},
        # 12/13: notice address for the Owner
        {"at": (254, 313.5), "page": 13, "text": OWNER},
        {"at": (254, 325.5), "page": 13, "text": "410 Pinecrest Avenue, Suite 200, Alder Springs, CO 81099", "size": 8},
        {"anchor": "Attention:", "occurrence": 2, "page": 13, "text": "Dana Whitlock-Reyes", "dy": -1},
        {"anchor": "Email:", "page": 13, "text": "notices@cedarhollow.example", "dy": -1},
        # 14: owner signature block and acknowledgment
        {"anchor": "By:", "page": 14, "text": "Dana Whitlock-Reyes", "dy": -1},
        {"anchor": "Its:", "page": 14, "text": "Manager, Cedar Hollow GP LLC, its general partner", "dy": -1, "size": 8},
        {"anchor": "STATE OF", "page": 14, "text": "Colorado", "dy": -1},
        {"anchor": "COUNTY OF", "page": 14, "text": "Larkspur", "dy": -1},
        # 15: Authority signature block
        {"anchor": "Name:", "page": 15, "text": "Marta Evergreen-Soto", "dy": -1},
        {"anchor": "Title:", "page": 15, "text": "Director, Asset Management", "dy": -1},
        # Exhibit A: legal description and street address
        {"at": (72, 195), "page": 16, "text": "Lot 3, Block 2, Cedar Hollow Subdivision, County of Larkspur, State of Colorado", "size": 8},
        {"at": (72, 219), "page": 16, "text": ADDRESS},
        # Exhibit B: minimum applicable fraction by building
        {"at": (130, 196.5), "page": 17, "text": "CO-26-00417"},
        {"at": (400, 196.5), "page": 17, "text": "95.65%"},
    ],
    "lease_fields": {
        "tenant": None,
        "landlord": OWNER,
        "rent_amount": None,
        "lease_start_date": None,
        "lease_end_date": None,
        "property_address": ADDRESS,
        "security_deposit": None,
    },
    "program_fields": {
        "agreement_date": {"value": "December 9, 2024", "shown_as": "December 9", "type": "date"},
        "owner_name": {"value": OWNER, "type": "text"},
        "owner_entity_type": {"value": "limited partnership", "type": "text"},
        "total_units": {"value": "46", "type": "int"},
        "city": {"value": "Alder Springs", "type": "text"},
        "county": {"value": "Larkspur", "type": "text"},
        "project_name": {"value": "Cedar Hollow Apartments", "type": "text"},
        "minimum_set_aside": {"value": "40-60", "type": "checkbox"},
        "units_at_60_pct_ami": {"value": "44", "type": "int"},
        "owner_notice_contact": {"value": "Dana Whitlock-Reyes", "type": "text"},
        "owner_notice_email": {"value": "notices@cedarhollow.example", "type": "text"},
        "authority_signer": {"value": "Marta Evergreen-Soto", "type": "text"},
        "street_address": {"value": ADDRESS, "type": "text"},
        "bin": {"value": "CO-26-00417", "type": "text"},
        "min_applicable_fraction": {"value": "95.65", "type": "pct"},
    },
}
