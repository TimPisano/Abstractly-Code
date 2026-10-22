"""
LIHTC Tenant Income Certifications (TIC).

  TIC_NATIONAL  the widely shared TIC layout (Parts I-IX, "Initial LIHTC
                Qualification Date", rent in Part VII). Used, with small
                differences in margins and extra lines, by South Carolina
                Housing (2024), Louisiana Housing Corporation (HOTMA forms)
                and NJ HMFA (an OCR'd scan of the same layout).
  TIC_IL_IHDA   Illinois Housing Development Authority / City of Chicago /
                Cook County TIC (rev. 11/2025), a fillable AcroForm with its
                own layout (assets in Part IV with (K), rent in Part VI).

Boxes were measured on the blank forms. The three national copies sit at
different page offsets, which anchor-relative boxes absorb; where a line is
laid out differently between copies, a second Anchor covers it.

Not read: dates of birth and SSN digits (restricted), circle-one / checkbox
items (certification type, program, set-aside designation).
"""

from dataclasses import replace

from .base import Anchor, FormSpec, Rule


def _right(phrase, dx1, dx0=-2, dy0=-6, dy1=9, page=1, occurrence=1):
    """Value on the label's line, starting at the label's right edge."""
    return Anchor(phrase, (dx0, dy0, dx1, dy1), origin="x1", page=page, occurrence=occurrence)


def _cell(phrase, dx0, dx1, dy0, dy1, page=1, occurrence=1, origin="x0"):
    """Value in a box positioned from the label's left edge (table cells, rows below headers)."""
    return Anchor(phrase, (dx0, dy0, dx1, dy1), origin=origin, page=page, occurrence=occurrence)


# ---------------------------------------------------------------------------
# National TIC (SC, LA, NJ)
# ---------------------------------------------------------------------------

# Part II household rows sit under the "Last Name" column header, 11.3pt apart.
_ROW0, _ROW_STEP = 12.0, 11.3


def _member_rules(n):
    mid = _ROW0 + _ROW_STEP * (n - 1) + 4.5
    dy0, dy1 = mid - 5.5, mid + 5.5
    return (
        Rule(f"member_{n}_last_name", "text", anchors=(_cell("Last Name", -45, 78, dy0, dy1),)),
        Rule(f"member_{n}_first_name", "text", anchors=(_cell("Last Name", 78, 168, dy0, dy1),)),
        Rule(f"member_{n}_relationship", "text", anchors=(_cell("Last Name", 168, 262, dy0, dy1),),
             label_guard=False),   # real values are label words ("Head", "Spouse")
    )


# Part III TOTALS row: columns (A) employment, (B) Social Security/pensions,
# (C) public assistance, (D) other income. Measured from "Total Income (E):",
# the line just below: "TOTALS" itself is a weak anchor on scans (OCR
# fuzzy-matches "Total" in other lines), and a misplaced column box can run
# off the page.
def _totals(dx0, dx1):
    return _cell("Total Income (E):", dx0, dx1, -18, -4)


TIC_NATIONAL = FormSpec(
    id="tic_national",
    name="LIHTC Tenant Income Certification (shared layout: SC, LA, NJ and others)",
    doc_kind="tic",
    program="LIHTC",
    detect=(("Tenant Income Certification", 1.0), ("Initial LIHTC Qualification Date", 2.0),
            ("PART VII. RENT", 1.0), ("Enter Total of ACTUAL INCOME earned from all Assets (F)", 1.0)),
    min_score=3.5,
    rules=(
        Rule("effective_date", "date", anchors=(_right("Effective Date:", 115),), canonical="effective_date"),
        Rule("initial_qualification_date", "date", anchors=(_right("Initial LIHTC Qualification Date:", 90),)),
        Rule("move_in_date", "date", anchors=(_right("Move-in Date:", 115),), canonical="move_in_date"),
        Rule("property_name", "text", anchors=(_right("Property Name:", 160),), canonical="property_name"),
        # Measured from "Property Name:" -- a county value often contains the word "County",
        # which would match a "County:" anchor.
        Rule("county", "text", anchors=(_right("Property Name:", 318, dx0=195),)),
        Rule("bin", "text", anchors=(_right("BIN #:", 120),), canonical="bin"),
        Rule("building_address", "text", anchors=(_right("Address:", 198),), canonical="unit_address"),
        Rule("unit_number", "text", anchors=(_right("Unit Number:", 70),), canonical="unit_number"),
        Rule("bedrooms", "int", anchors=(_right("#Bedrooms:", 60),), canonical="bedrooms"),
        # Typed name on the first household signature line, just under the
        # certification paragraph that ends "...termination of the lease agreement."
        Rule("head_of_household", "text",
             anchors=(_cell("termination of the lease agreement", -28, 150, 15, 40),
                      _cell("Signature", -12, 165, -24, -3, occurrence=2)),
             canonical="head_of_household"),
        *_member_rules(1), *_member_rules(2), *_member_rules(3), *_member_rules(4), *_member_rules(5),
        Rule("total_employment_income", "money", anchors=(_totals(-305, -180),)),
        Rule("total_ss_pension_income", "money", anchors=(_totals(-180, -85),)),
        Rule("total_public_assistance_income", "money", anchors=(_totals(-85, 20),)),
        Rule("total_other_income", "money", anchors=(_totals(20, 165),)),
        Rule("total_income_e", "money", anchors=(_right("Total Income (E):", 110),)),
        Rule("asset_income", "money",
             anchors=(_right("earned from all Assets (F)", 110), _right("Total Income from all Assets (M)", 110))),
        Rule("total_annual_income", "money",
             anchors=(_right("SOURCES:", 90, page=2), _right("(E) + (M)]", 115)),
             canonical="annual_income"),
        Rule("designated_limit_x_140", "money", anchors=(_right("Skewing):", 95, page=2),)),
        Rule("income_limit", "money", anchors=(_right("Current Income Limit per Family Size:", 90, page=2),),
             canonical="income_limit"),
        Rule("household_income_at_move_in", "money",
             anchors=(_right("Income at Move-in:", 90, page=2),)),
        Rule("household_size_at_move_in", "int", anchors=(_right("Size at Move-in:", 60, page=2),)),
        # The form has no separate household-size line; on these certifications
        # the size at move-in is the household size.
        Rule("household_size", "int", anchors=(_right("Size at Move-in:", 60, page=2),),
             canonical="household_size"),
        Rule("tenant_paid_rent", "money", anchors=(_right("Tenant Rent:", 100, dx0=0, page=2),),
             canonical="tenant_rent"),
        Rule("utility_allowance", "money", anchors=(_right("Utility Allowance:", 100, dx0=0, page=2),),
             canonical="utility_allowance"),
        Rule("rental_assistance", "money", anchors=(_right("Rental Assistance:", 100, dx0=0, page=2),)),
        Rule("other_non_optional_fees", "money",
             anchors=(_right("Other non-optional / mandatory", 110, dx0=0, dy0=-6, dy1=16, page=2),)),
        # SC/NJ print the amount on the label's row (or just above it); LA one
        # row lower, after "(See".
        Rule("gross_rent", "money", anchors=(_right("Gross Rent for Unit", 135, dx0=0, dy0=-12, dy1=14, page=2),),
             canonical="gross_rent"),
        Rule("maximum_rent_limit", "money", anchors=(_right("Maximum Rent Limit", 140, dx0=0, page=2),),
             canonical="max_rent"),
    ),
    lease_map={
        "tenant": "head_of_household",
        "rent_amount": "tenant_paid_rent",
        "property_address": "building_address",
    },
)


# ---------------------------------------------------------------------------
# Illinois (IHDA / City of Chicago / Cook County)
# ---------------------------------------------------------------------------

def _il_acro(name):
    return (rf"^{name}$",)


TIC_IL_IHDA = FormSpec(
    id="tic_il_ihda",
    name="Illinois Tenant Income Certification (IHDA / City of Chicago / Cook County, rev. 11/2025)",
    doc_kind="tic",
    program="LIHTC",
    detect=(("Tenant Income Certification", 1.0), ("TOTAL INCOME FROM ASSETS (K)", 2.0),
            ("Current Passbook", 1.0), ("Did Not Disclose", 1.0), ("Section 1602", 1.0)),
    acro_signature=(r"^First Name  Middle Initial1$", r"^fill_128$", r"^HH Mbr Row1$"),
    min_score=3.0,
    rules=(
        Rule("effective_date", "date", acro=_il_acro("Effective Date"),
             anchors=(_right("Effective Date:", 110, dx0=-5, dy0=-12, dy1=6),), canonical="effective_date"),
        Rule("move_in_date", "date", acro=_il_acro("Movein Date"),
             anchors=(_right("Move-in Date:", 110, dx0=-5, dy0=-12, dy1=6),), canonical="move_in_date"),
        Rule("property_name", "text", acro=_il_acro("Property Name"),
             anchors=(_right("Property Name:", 210, dx0=-5, dy0=-12, dy1=6),), canonical="property_name"),
        # "TC #:" can't be the anchor: the value itself ("TC-26-...") starts with "TC".
        Rule("tc_number", "text", acro=_il_acro("TC"),
             anchors=(_right("Property Name:", 400, dx0=230, dy0=-12, dy1=6),)),
        Rule("building_address", "text", acro=_il_acro("Property Address"),
             anchors=(_right("Property Address:", 200, dx0=-3, dy0=-12, dy1=6),), canonical="unit_address"),
        Rule("city", "text", acro=_il_acro("City"), anchors=(_right("City:", 70, dx0=-3, dy0=-12, dy1=6),)),
        # "Zip:" is too short to fuzzy-match on scans; "State:" two labels left is the fallback.
        Rule("zip", "int", acro=_il_acro("Zip"),
             anchors=(_right("Zip:", 60, dx0=-3, dy0=-12, dy1=6), _right("State:", 105, dx0=38, dy0=-12, dy1=6))),
        Rule("bin", "text", acro=_il_acro("BIN"), anchors=(_right("BIN #:", 130, dx0=-4, dy0=-12, dy1=6),),
             canonical="bin"),
        Rule("county", "text", acro=_il_acro("County"),
             anchors=(_cell("Unit Number:", -70, -3, -12, 6),)),
        Rule("unit_number", "text", acro=_il_acro("Unit Number"),
             anchors=(_right("Unit Number:", 58, dx0=-3, dy0=-12, dy1=6),), canonical="unit_number"),
        Rule("bedrooms", "int", acro=_il_acro("Bedrooms"),
             anchors=(_right("Bedrooms:", 60, dx0=-3, dy0=-12, dy1=6),), canonical="bedrooms"),
        Rule("member_1_last_name", "text", acro=_il_acro("Last Name1"),
             anchors=(_cell("Last Name", -40, 74, 22, 38),)),
        Rule("member_1_first_name", "text", acro=_il_acro("First Name  Middle Initial1"),
             anchors=(_cell("Last Name", 76, 170, 22, 38),)),
        # The household head types their name on the first signature line (page 3).
        Rule("head_of_household", "text", acro=_il_acro("Signature"),
             anchors=(_cell("termination of the lease agreement", -112, 50, 12, 26, page=3),
                      _cell("Signature", -12, 150, -20, -3, page=3, occurrence=2)),
             canonical="head_of_household"),
        # TOTALS row, measured from "TOTAL INCOME (E):" on the line below (see _totals above).
        Rule("total_employment_income", "money", acro=_il_acro("fill_122"),
             anchors=(_cell("TOTAL INCOME (E):", -255, -120, -24, -10),)),
        Rule("total_ss_pension_income", "money", acro=_il_acro("fill_123"),
             anchors=(_cell("TOTAL INCOME (E):", -120, 2, -24, -10),)),
        Rule("total_public_assistance_income", "money", acro=_il_acro("fill_124"),
             anchors=(_cell("TOTAL INCOME (E):", 2, 128, -24, -10),)),
        Rule("total_other_income", "money", acro=_il_acro("fill_125"),
             anchors=(_cell("TOTAL INCOME (E):", 128, 250, -24, -10),)),
        Rule("total_income_e", "money", acro=_il_acro("fill_126"),
             anchors=(_right("TOTAL INCOME (E):", 130, dx0=0, dy0=-6, dy1=8),)),
        Rule("asset_1_type", "text", acro=_il_acro("F Type of AssetRow1"),
             anchors=(_cell("Type of Asset", -40, 90, 5, 17),)),
        Rule("asset_1_cash_value", "money", acro=_il_acro("H Cash Value of AssetRow1"),
             anchors=(_cell("Cash Value of Asset", -40, 110, 5, 17),)),
        Rule("asset_2_type", "text", acro=_il_acro("F Type of AssetRow2"),
             anchors=(_cell("Type of Asset", -40, 90, 18, 30),)),
        Rule("asset_2_cash_value", "money", acro=_il_acro("H Cash Value of AssetRow2"),
             anchors=(_cell("Cash Value of Asset", -40, 110, 18, 30),)),
        Rule("total_asset_cash_value", "money", acro=_il_acro("H Cash Value of Asset Total"),
             anchors=(_cell("Current Passbook", 195, 350, -8, 8),)),
        Rule("passbook_rate", "pct", acro=_il_acro("Rate"), anchors=(_right("Rate:", 50, dx0=-2, dy0=-8, dy1=8),)),
        Rule("asset_income", "money", acro=_il_acro("fill_127"),
             anchors=(_right("TOTAL INCOME FROM ASSETS (K)", 140, dx0=0, dy0=-8, dy1=8),)),
        Rule("total_annual_income", "money", acro=(r"^fill_128$", r"^fill_40$"),
             anchors=(_right("[Add (E) + (K)]", 150, dx0=0, dy0=-4, dy1=14),
                      _right("SOURCES:", 110, dx0=15, dy0=-5, dy1=28, page=2)),
             canonical="annual_income"),
        Rule("income_limit", "money", acro=_il_acro("Text1"),
             anchors=(_right("Current Income Limit per Family Size:", 95, dx0=0, dy0=-10, dy1=8, page=2),),
             canonical="income_limit"),
        Rule("household_income_at_move_in", "money", acro=_il_acro("Text2"),
             anchors=(_right("Income at Move-in:", 95, dx0=0, dy0=-10, dy1=8, page=2),)),
        Rule("household_size_at_move_in", "int", acro=_il_acro("Text7"),
             anchors=(_right("Size at Move-in:", 80, dx0=0, dy0=-10, dy1=8, page=2),),
             canonical="household_size"),
        Rule("tenant_paid_rent", "money", acro=_il_acro("Text3"),
             anchors=(_right("Tenant Paid Rent:", 100, dx0=0, dy0=-8, dy1=8, page=2),), canonical="tenant_rent"),
        Rule("rental_assistance", "money", acro=_il_acro("Rental Assistance"),
             anchors=(_right("Rental Assistance:", 120, dx0=0, dy0=-8, dy1=8, page=2),)),
        Rule("utility_allowance", "money", acro=_il_acro("Text4"),
             anchors=(_right("Utility Allowance:", 100, dx0=0, dy0=-8, dy1=8, page=2),),
             canonical="utility_allowance"),
        Rule("gross_rent", "money", acro=_il_acro("fill_41"),
             anchors=(_right("GROSS RENT FOR UNIT:", 100, dx0=12, dy0=-4, dy1=26, page=2),), canonical="gross_rent"),
        Rule("maximum_rent_limit", "money", acro=_il_acro("Text5"),
             anchors=(_right("Maximum Rent Limit for this unit:", 100, dx0=0, dy0=-10, dy1=8, page=2),),
             canonical="max_rent"),
        Rule("household_signature_date", "date", acro=_il_acro("Date"),
             anchors=(_cell("(Date)", -30, 55, -20, -3, page=3),)),
        Rule("owner_signature_date", "date", acro=_il_acro("DATE"),
             anchors=(_cell("SIGNATURE OF OWNER/REPRESENTATIVE", 200, 290, -20, -3, page=3, occurrence=2),)),
    ),
    lease_map={
        "tenant": "head_of_household",
        "rent_amount": "tenant_paid_rent",
        "property_address": "building_address",
    },
)

# OCR often reads the pre-printed "$" as a lone "5" or "S" ("5 76,064"),
# and the first number in a box wins. Drop a lone 5/S/$ that sits right
# before another number in any money box.
DOLLAR_MISREAD = (r"(?<![\d,.])[5S§$](?=\s+\d)",)


def _with_dollar_fix(spec):
    spec.rules = tuple(replace(r, strip=tuple(r.strip) + DOLLAR_MISREAD) if r.type == "money" else r
                       for r in spec.rules)
    return spec


FORMS = [_with_dollar_fix(TIC_NATIONAL), _with_dollar_fix(TIC_IL_IHDA)]
