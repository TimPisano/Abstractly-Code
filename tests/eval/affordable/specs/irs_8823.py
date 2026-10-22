"""IRS Form 8823 (Rev. 12-2019), agency report of noncompliance. AcroForm.

Fictional: CHFA reports that one Cedar Hollow unit was leased on 11/01/2026 to
a household over the income limit at initial occupancy (line 11a), corrected
05/15/2027 when the unit was re-leased to a qualified household. Same building
as irs_8609 / irs_8586 / lura_co_chfa (46 units, 44 low-income, 415,800 credit).
"""

OWNER = "Cedar Hollow Housing LP"
BUILDING_ADDRESS = "2750 Cedar Hollow Lane, Alder Springs, CO 81099"

SPEC = {
    "id": "irs_8823",
    "source": "irs_8823.pdf",
    "form": "IRS Form 8823 Low-Income Housing Credit Agencies Report of Noncompliance (Rev. 12-2019)",
    "program": "LIHTC",
    "doc_type": "irs_lihtc_form",
    "notes": "Fictional 11a finding (over-income at initial occupancy), corrected. Owner TIN masked.",
    "placements": [
        {"acro": "f1_01[0]", "text": "Cedar Hollow Apartments"},
        {"acro": "f1_02[0]", "text": "2750 Cedar Hollow Lane"},
        {"acro": "f1_03[0]", "text": "Alder Springs, CO 81099"},
        {"acro": "f1_04[0]", "text": "CO-26-00417"},
        {"acro": "f1_05[0]", "text": OWNER},
        {"acro": "f1_06[0]", "text": "410 Pinecrest Avenue, Suite 200"},
        {"acro": "f1_07[0]", "text": "Alder Springs, CO 81099"},
        {"acro": "f1_08[0]", "text": "XX-XXX4821"},
        {"acro": "c1_4[0]", "text": "X", "size": 8},          # EIN
        {"acro": "f1_09[0]", "text": "415,800"},
        {"acro": "f1_11[0]", "text": "46"},
        {"acro": "f1_12[0]", "text": "44"},
        {"acro": "f1_13[0]", "text": "1"},
        {"acro": "f1_14[0]", "text": "9"},
        {"acro": "f1_15[0]", "text": "11/01/2026"},
        {"acro": "f1_16[0]", "text": "05/15/2027"},
        {"acro": "c1_6[0]", "text": "X", "size": 8},          # 11a out of compliance
        {"acro": "c1_7[0]", "text": "X", "size": 8},          # 11a noncompliance corrected
        {"acro": "f1_22[0]", "text": "Priya Lindqvist-Haber, Compliance Officer"},
        {"acro": "f1_23[0]", "text": "(303) 555-0177"},
        {"acro": "f1_25[0]", "text": "Gareth Monroe-Ito, Director of Asset Management", "size": 8},
        {"at": (504, 734), "page": 1, "text": "06/02/2027"},
    ],
    "lease_fields": {
        "tenant": None,
        "landlord": OWNER,
        "rent_amount": None,
        "lease_start_date": None,
        "lease_end_date": None,
        "property_address": "2750 Cedar Hollow Lane",
        "security_deposit": None,
    },
    "program_fields": {
        "building_name": {"value": "Cedar Hollow Apartments", "type": "text"},
        "building_street": {"value": "2750 Cedar Hollow Lane", "type": "text"},
        "building_city_state_zip": {"value": "Alder Springs, CO 81099", "type": "text"},
        "bin": {"value": "CO-26-00417", "type": "text"},
        "owner_name": {"value": OWNER, "type": "text"},
        "owner_tin_masked": {"value": "XX-XXX4821", "type": "text"},
        "total_credit_allocated": {"value": "415,800", "type": "money"},
        "residential_units": {"value": "46", "type": "int"},
        "low_income_units": {"value": "44", "type": "int"},
        "units_with_noncompliance": {"value": "1", "type": "int"},
        "units_reviewed": {"value": "9", "type": "int"},
        "date_ceased_to_comply": {"value": "11/01/2026", "type": "date"},
        "date_noncompliance_corrected": {"value": "05/15/2027", "type": "date"},
        "noncompliance_category": {"value": "11a Household income above income limit upon initial occupancy (out of compliance + corrected)", "type": "checkbox"},
        "contact_person": {"value": "Priya Lindqvist-Haber", "type": "text"},
        "contact_phone": {"value": "(303) 555-0177", "type": "text"},
        "agency_official": {"value": "Gareth Monroe-Ito", "type": "text"},
        "signature_date": {"value": "06/02/2027", "type": "date"},
    },
}
