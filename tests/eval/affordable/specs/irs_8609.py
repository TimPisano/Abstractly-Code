"""IRS Form 8609 (Rev. 12-2021), LIHTC allocation and first-year certification. AcroForm.

Fictional building "Cedar Hollow Apartments", shared with irs_8586, irs_8823 and
lura_co_chfa. Numbers tie out: eligible basis 4,830,000 x applicable fraction
44/46 (95.65%) = qualified basis 4,620,000; 4,620,000 x 9.00% = 415,800 annual credit.
"""

OWNER = "Cedar Hollow Housing LP"
BUILDING_ADDRESS = "2750 Cedar Hollow Lane, Alder Springs, CO 81099"
AGENCY = "Colorado Housing and Finance Authority"

SPEC = {
    "id": "irs_8609",
    "source": "irs_8609.pdf",
    "form": "IRS Form 8609 Low-Income Housing Credit Allocation and Certification (Rev. 12-2021)",
    "program": "LIHTC",
    "doc_type": "irs_lihtc_form",
    "notes": "Same fictional building as irs_8586, irs_8823 and lura_co_chfa. TINs/EINs are masked on purpose.",
    "placements": [
        # A: building address (two typed lines inside the box)
        {"at": (38, 124), "page": 1, "text": "Cedar Hollow Apartments (Building 1)"},
        {"at": (38, 136), "page": 1, "text": BUILDING_ADDRESS},
        # B: agency
        {"at": (298, 124), "page": 1, "text": AGENCY},
        {"at": (298, 136), "page": 1, "text": "1981 Blake Street, Denver, CO 80202"},
        # C: owner name and address, TIN
        {"at": (38, 171), "page": 1, "text": OWNER},
        {"at": (38, 182), "page": 1, "text": "410 Pinecrest Avenue, Suite 200"},
        {"at": (38, 193), "page": 1, "text": "Alder Springs, CO 81099"},
        {"acro": "f1_4[0]", "text": "XX-XXX4821"},
        {"acro": "f1_5[0]", "text": "XX-XXX0093"},
        {"acro": "f1_6[0]", "text": "CO-26-00417"},
        # Lines 1-5
        {"acro": "f1_7[0]", "text": "06/14/2024", "size": 8},
        {"acro": "f1_8[0]", "text": "415,800"},
        {"acro": "f1_9[0]", "text": "9.00"},
        {"acro": "f1_10[0]", "text": "4,620,000"},
        {"acro": "f1_13[0]", "text": "-0-"},
        {"acro": "f1_14[0]", "text": "09/30/2026", "size": 8},
        # 6b newly constructed and not federally subsidized
        {"acro": "c1_6[0]", "text": "X", "size": 8},
        # Part I agency official
        {"acro": "f1_15[0]", "text": "Marta Evergreen-Soto"},
        {"at": (470, 468), "page": 1, "text": "11/20/2026"},
        # Part II
        {"acro": "f1_16[0]", "text": "4,830,000"},
        {"acro": "f1_17[0]", "text": "4,620,000"},
        {"acro": "c1_11[1]", "text": "X", "size": 8},   # 8b No
        {"acro": "c1_13[1]", "text": "X", "size": 8},   # 9b No
        {"acro": "c1_14[1]", "text": "X", "size": 8},   # 10a No
        {"acro": "c1_17[0]", "text": "X", "size": 8},   # 10c 40-60 (c1_16 = 20-50, c1_18 = average income)
        {"acro": "f1_18[0]", "text": "XX-XXX4821"},
        {"at": (470, 696), "page": 1, "text": "02/15/2027"},
        {"acro": "f1_19[0]", "text": "Dana Whitlock-Reyes"},
        {"acro": "f1_20[0]", "text": "2026"},
    ],
    "lease_fields": {
        "tenant": None,
        "landlord": OWNER,
        "rent_amount": None,
        "lease_start_date": None,
        "lease_end_date": None,
        "property_address": BUILDING_ADDRESS,
        "security_deposit": None,
    },
    "program_fields": {
        "building_name": {"value": "Cedar Hollow Apartments", "type": "text"},
        "building_address": {"value": BUILDING_ADDRESS, "type": "text"},
        "agency_name": {"value": AGENCY, "type": "text"},
        "owner_name": {"value": OWNER, "type": "text"},
        "owner_tin_masked": {"value": "XX-XXX4821", "type": "text"},
        "bin": {"value": "CO-26-00417", "type": "text"},
        "allocation_date": {"value": "06/14/2024", "type": "date"},
        "max_credit_amount": {"value": "415,800", "type": "money"},
        "credit_percentage": {"value": "9.00", "type": "pct"},
        "max_qualified_basis": {"value": "4,620,000", "type": "money"},
        "placed_in_service_date": {"value": "09/30/2026", "type": "date"},
        "agency_official": {"value": "Marta Evergreen-Soto", "type": "text"},
        "agency_signature_date": {"value": "11/20/2026", "type": "date"},
        "eligible_basis": {"value": "4,830,000", "type": "money"},
        "original_qualified_basis": {"value": "4,620,000", "type": "money"},
        "owner_signature_date": {"value": "02/15/2027", "type": "date"},
        "owner_signer": {"value": "Dana Whitlock-Reyes", "type": "text"},
        "first_credit_year": {"value": "2026", "type": "int"},
        "allocation_type": {"value": "6b Newly constructed and not federally subsidized", "type": "checkbox"},
        "multiple_building_project": {"value": "No", "type": "checkbox"},
        "begin_credit_year_after_pis": {"value": "No", "type": "checkbox"},
        "minimum_set_aside": {"value": "40-60", "type": "checkbox"},
    },
}
