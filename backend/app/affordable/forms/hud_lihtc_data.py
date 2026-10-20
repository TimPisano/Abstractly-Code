"""
HUD-52697 LIHTC Tenant Data Collection Form (OMB 2528-0320, exp. 10/31/2025).

No fillable fields: values are typed on underscore blanks after inline
labels ("Property Name: ________"). Each box runs from the end of its label
to just before the next printed label on the same row, measured on the
blank form. Household names come from the Part II table, located from its
"Head of Household" column header. Dates of birth and SSN digits in that
table are never read.
"""

from .base import Anchor, FormSpec, Rule

INLINE = (-7, 9)   # dy range around an inline label: values sit on the underline, a little above it


def _inline(phrase, width, page, occurrence=1):
    return Anchor(phrase, (1, INLINE[0], width, INLINE[1]), origin="x1", page=page, occurrence=occurrence)


# Part II table, relative to the "Head of Household" header (x0 197.0, top 211.6):
# Last Name column x ~70-115, First Name x ~115-153; row 1 centre ~229, row 2 ~240.
HOH = "Head of Household"
ROW1, ROW2 = (11.9, 22.3), (23.4, 33.8)
LAST_COL, FIRST_COL = (-127.0, -82.0), (-82.0, -44.0)


def _cell(col, row):
    return Anchor(HOH, (col[0], row[0], col[1], row[1]), origin="x0", page=1)


HUD_52697 = FormSpec(
    id="hud_52697",
    name="HUD-52697 LIHTC Tenant Data Collection Form",
    doc_kind="lihtc_tenant_data",
    program="LIHTC",
    detect=(("HUD LIHTC Tenant Data Collection Form", 2.0), ("HUD-52697", 2.0)),
    rules=(
        Rule("certification_type", "int", anchors=(_inline("Certification Type:", 47.5, 1),)),
        Rule("effective_date", "date",
             anchors=(_inline("Effective Date of Certification:", 100.6, 1),
                      _inline("Effective Date of LIHTC Income Certification:", 150.0, 2)),
             canonical="effective_date"),
        Rule("lihtc_qualification_date", "date", anchors=(_inline("LIHTC Qualification Date:", 116.4, 1),)),
        Rule("compliance_agency", "text", anchors=(_inline("Compliance Agency Name:", 152.1, 1),)),
        Rule("county", "text", anchors=(_inline("County:", 220.0, 1),)),
        Rule("property_name", "text", anchors=(_inline("Property Name:", 118.6, 1),), canonical="project_name"),
        Rule("pin", "text", anchors=(_inline("PIN:", 158.2, 1),)),
        Rule("bin", "text", anchors=(_inline("BIN:", 150.0, 1),), canonical="bin"),
        Rule("building_street", "text", anchors=(_inline("Building Address:", 109.3, 1),),
             canonical="building_address"),
        Rule("unit_number", "text", anchors=(_inline("Unit Number:", 128.6, 1),), canonical="unit_number"),
        Rule("bedrooms", "int", anchors=(_inline("# Bedrooms:", 110.0, 1),), canonical="bedrooms"),
        Rule("head_last_name", "text", anchors=(_cell(LAST_COL, ROW1),)),
        Rule("head_first_name", "text", anchors=(_cell(FIRST_COL, ROW1),)),
        Rule("member_2_first_name", "text", anchors=(_cell(FIRST_COL, ROW2),)),
        Rule("total_annual_income", "money", anchors=(_inline("Total Annual Income From All Sources:", 120.0, 2),),
             canonical="annual_income"),
        Rule("household_size", "int",
             anchors=(_inline("Household Size at LIHTC Certification:", 118.8, 2),
                      _inline("Household Size at LIHTC Qualification Date:", 70.0, 2)),
             canonical="household_size"),
        Rule("income_limit_140pct", "money", anchors=(_inline("Current Income Limit x 140%:", 125.0, 2),)),
        Rule("household_income_at_qualification", "money",
             anchors=(_inline("Household Income at LIHTC Qualification Date:", 60.0, 2),)),
        Rule("income_limit", "money", anchors=(_inline("Current LIHTC Income Limit per Family Size:", 91.1, 2),),
             canonical="income_limit"),
        Rule("tenant_paid_rent", "money", anchors=(_inline("Tenant Paid Monthly Rent:", 110.0, 2),),
             canonical="tenant_rent"),
        Rule("utility_allowance", "money", anchors=(_inline("Monthly Utility Allowance:", 110.0, 2),),
             canonical="utility_allowance"),
        Rule("gross_rent", "money", anchors=(_inline("Gross Monthly Rent for Unit:", 113.1, 2),),
             canonical="gross_rent"),
        Rule("max_lihtc_rent", "money", anchors=(_inline("Maximum LIHTC Rent for this Unit:", 95.0, 2),),
             canonical="max_rent"),
    ),
    lease_map={"property_address": "building_street"},
)

FORMS = [HUD_52697]
