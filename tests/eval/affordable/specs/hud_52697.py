"""HUD-52697 LIHTC Tenant Data Collection Form (OMB 2528-0320, exp. 10/31/2025). No AcroForm: values placed at measured positions.

Fictional 2-person recertification at fictional "Cedar Hollow Apartments".
Income limit, 140% limit and max rent come from world.LihtcCert, so the
household is under its limit and gross rent is under the cap. Codes follow
the form's own instructions (pages 3-5): certification type 2 =
recertification; relationship H/C; race 8 and ethnicity 3 = tenant did not
respond; disabled 2 = no. SSN last-4 is left blank. Dates use the form's
YYYY-MM-DD / YYYY/MM/DD formats.
"""

from world import Household, LihtcCert, Member, num

HH = Household(members=[
    Member("Tobias", "Wren", "Head", 41, "1985/04/17", annual_wages=32_400),
    Member("Lena", "Wren", "Child", 9, "2017/06/30"),
])
CERT = LihtcCert(hh=HH, bedrooms=2, ami_pct=60, utility_allowance=118)
CERT.check()

LIMIT_140 = round(CERT.income_limit * 1.4)
QUAL_INCOME = 29_800
PROPERTY = "Cedar Hollow Apartments"
STREET = "312 Cedar Hollow Lane"

ROW_TOPS = [224.0, 235.5]
COLS = {"last": 76, "first": 118, "rel": 232, "race": 285, "eth": 322, "dis": 370, "dob": 408, "student": 495}

placements = [
    # page 1 header
    {"at": (136, 47.5), "page": 1, "text": "2"},
    {"at": (503, 47.5), "page": 1, "text": "2026-09-01", "size": 8},
    {"at": (503, 62.0), "page": 1, "text": "2024-09-01", "size": 8},
    # Part I: development data
    {"at": (157, 115.0), "page": 1, "text": "Maple Ridge Housing Finance Authority", "size": 7.5},
    {"at": (345, 115.0), "page": 1, "text": "Maple Ridge County", "size": 8},
    {"at": (124, 129.5), "page": 1, "text": PROPERTY, "size": 7.5},
    {"at": (305, 129.5), "page": 1, "text": "MR-2019-044", "size": 8},
    {"at": (476, 129.5), "page": 1, "text": "MR-19-04401", "size": 8},
    {"at": (124, 144.0), "page": 1, "text": STREET, "size": 7.5},
    {"at": (124, 154.0), "page": 1, "text": "Riverbend, IN 46990", "size": 7.5},
    {"at": (305, 144.0), "page": 1, "text": "204", "size": 8},
    {"at": (476, 144.0), "page": 1, "text": "2", "size": 8},
    # Part II: vacant on Dec 31? -> No
    {"at": (251.5, 185.5), "page": 1, "text": "X", "size": 8},
]
RACE, ETH, DISABLED, STUDENT = "8", "3", "2", "N"
for top, mem in zip(ROW_TOPS, HH.members):
    rel = "H" if mem.relationship == "Head" else "C"
    for col, text in (("last", mem.last), ("first", mem.first), ("rel", rel), ("race", RACE),
                      ("eth", ETH), ("dis", DISABLED), ("dob", mem.dob), ("student", STUDENT)):
        placements.append({"at": (COLS[col], top), "page": 1, "text": text, "size": 7.5})

placements += [
    # page 2, Part V: income eligibility
    {"at": (256, 53.8), "page": 2, "text": num(HH.annual_income), "size": 8},
    {"at": (256, 68.9), "page": 2, "text": "2026-09-01", "size": 8},
    {"at": (260, 83.5), "page": 2, "text": str(HH.size), "size": 8},
    {"at": (534, 83.5), "page": 2, "text": num(LIMIT_140), "size": 7.5},
    {"at": (104, 129.0), "page": 2, "text": "X", "size": 8},          # 60% AMGI
    {"at": (457.5, 113.4), "page": 2, "text": "X", "size": 8},        # exceeds 140%: No
    {"at": (533, 174.6), "page": 2, "text": num(QUAL_INCOME), "size": 7.5},
    {"at": (256, 194.3), "page": 2, "text": num(CERT.income_limit), "size": 8},
    {"at": (538, 194.3), "page": 2, "text": str(HH.size), "size": 8},
    # Part VI: monthly rent
    {"at": (233, 241.6), "page": 2, "text": f"{CERT.tenant_paid_rent:,}.00", "size": 8},
    {"at": (233, 256.1), "page": 2, "text": f"{CERT.utility_allowance:,}.00", "size": 8},
    {"at": (233, 270.6), "page": 2, "text": "0.00", "size": 8},
    {"at": (233, 286.8), "page": 2, "text": f"{CERT.gross_rent:,}.00", "size": 8},
    {"at": (507, 286.8), "page": 2, "text": f"{CERT.max_gross_rent:,}.00", "size": 8},
    {"at": (397, 333.8), "page": 2, "text": "X", "size": 8},          # rent restriction 60%
    {"at": (233, 362.5), "page": 2, "text": "0.00", "size": 8},
    {"at": (233, 377.1), "page": 2, "text": "0.00", "size": 8},
    {"at": (233, 391.6), "page": 2, "text": "0.00", "size": 8},
    # Part VII: all occupants full-time students? -> No
    {"at": (242.5, 530.6), "page": 2, "text": "X", "size": 8},
    # Part VIII: 9% allocated credit
    {"at": (42.2, 645.6), "page": 2, "text": "X", "size": 8},
]


def money(n, shown):
    return {"value": f"${n:,}.00", "type": "money", "shown_as": shown}


SPEC = {
    "id": "hud_52697",
    "source": "hud_52697.pdf",
    "form": "HUD-52697 LIHTC Tenant Data Collection Form (exp. 10/31/2025)",
    "program": "LIHTC",
    "doc_type": "lihtc_tenant_data",
    "notes": ("Recertification for a fictional 2-person household in a 2BR 60% AMI unit. The street line and "
              "city line are written on separate lines under 'Building Address', so property_address is the "
              "street only. The form has no lease dates, rent to owner or owner name."),
    "placements": placements,
    "lease_fields": {
        "tenant": None,                       # names split across Last/First columns; no single tenant name line
        "landlord": None,
        "rent_amount": None,
        "lease_start_date": None,
        "lease_end_date": None,
        "property_address": STREET,
        "security_deposit": None,
    },
    "program_fields": {
        "certification_type": {"value": "2", "type": "int"},
        "effective_date": {"value": "2026-09-01", "type": "date"},
        "lihtc_qualification_date": {"value": "2024-09-01", "type": "date"},
        "compliance_agency": {"value": "Maple Ridge Housing Finance Authority", "type": "text"},
        "county": {"value": "Maple Ridge County", "type": "text"},
        "property_name": {"value": PROPERTY, "type": "text"},
        "pin": {"value": "MR-2019-044", "type": "text"},
        "bin": {"value": "MR-19-04401", "type": "text"},
        "building_street": {"value": STREET, "type": "text"},
        "unit_number": {"value": "204", "type": "text"},
        "bedrooms": {"value": "2", "type": "int"},
        "head_last_name": {"value": "Wren", "type": "text"},
        "head_first_name": {"value": "Tobias", "type": "text"},
        "head_dob": {"value": "1985/04/17", "type": "date"},
        "member_2_first_name": {"value": "Lena", "type": "text"},
        "total_annual_income": money(HH.annual_income, num(HH.annual_income)),
        "household_size": {"value": str(HH.size), "type": "int"},
        "income_limit_140pct": money(LIMIT_140, num(LIMIT_140)),
        "household_income_at_qualification": money(QUAL_INCOME, num(QUAL_INCOME)),
        "income_limit": money(CERT.income_limit, num(CERT.income_limit)),
        "tenant_paid_rent": money(CERT.tenant_paid_rent, f"{CERT.tenant_paid_rent:,}.00"),
        "utility_allowance": money(CERT.utility_allowance, f"{CERT.utility_allowance:,}.00"),
        "gross_rent": money(CERT.gross_rent, f"{CERT.gross_rent:,}.00"),
        "max_lihtc_rent": money(CERT.max_gross_rent, f"{CERT.max_gross_rent:,}.00"),
        "income_restriction_ami": {"value": "60% AMGI", "type": "checkbox"},
        "rent_restriction_ami": {"value": "60% AMGI", "type": "checkbox"},
        "exceeds_140pct": {"value": "No", "type": "checkbox"},
        "all_students": {"value": "No", "type": "checkbox"},
        "program_type": {"value": "9% Allocated Federal Housing Tax Credit", "type": "checkbox"},
    },
}
