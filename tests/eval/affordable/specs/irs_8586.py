"""IRS Form 8586 (Rev. 12-2023), Low-Income Housing Credit. AcroForm.

Fictional partnership return for Cedar Hollow Housing LP, tax year 2026 (first
credit year). Building placed in service 09/30/2026 and fully occupied for
October-December, so the first-year credit is 3/12 of the 415,800 annual
credit = 103,950 (simplified; the real first-year computation averages
qualified basis month by month on Form 8609-A).
"""

OWNER = "Cedar Hollow Housing LP"

SPEC = {
    "id": "irs_8586",
    "source": "irs_8586.pdf",
    "form": "IRS Form 8586 Low-Income Housing Credit (Rev. 12-2023)",
    "program": "LIHTC",
    "doc_type": "irs_lihtc_form",
    "notes": "Same fictional building as irs_8609. First-year credit simplified to 3/12 of the annual amount.",
    "placements": [
        {"acro": "f1_1[0]", "text": OWNER},
        {"acro": "f1_2[0]", "text": "XX-XXX4821"},
        {"acro": "f1_3[0]", "text": "1"},
        {"acro": "c1_1[1]", "text": "X", "size": 8},   # line 2: No
        {"acro": "f1_8[0]", "text": "103,950"},
        {"acro": "f1_10[0]", "text": "103,950"},
    ],
    "lease_fields": {
        "tenant": None,
        "landlord": OWNER,
        "rent_amount": None,
        "lease_start_date": None,
        "lease_end_date": None,
        "property_address": None,
        "security_deposit": None,
    },
    "program_fields": {
        "taxpayer_name": {"value": OWNER, "type": "text"},
        "identifying_number_masked": {"value": "XX-XXX4821", "type": "text"},
        "forms_8609a_attached": {"value": "1", "type": "int"},
        "qualified_basis_decreased": {"value": "No", "type": "checkbox"},
        "current_year_credit": {"value": "103,950", "type": "money"},
        "total_credit_line5": {"value": "103,950", "type": "money"},
    },
}
