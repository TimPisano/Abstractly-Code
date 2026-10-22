"""
IRS low-income housing credit forms:

  Form 8609  Low-Income Housing Credit Allocation and Certification (Rev. 12-2021)
  Form 8823  Low-Income Housing Credit Agencies Report of Noncompliance (Rev. 12-2019)
  Form 8586  Low-Income Housing Credit (Rev. 12-2023)

All three are IRS fillable PDFs, so each field maps by its AcroForm name
(topmostSubform[0].Page1[0].f1_N[0]) and, for flattened copies and scans,
by a box next to its printed label. Boxes were measured on the blank forms.

Amounts on these forms are printed without "$" (the "$" is in the label),
which values.parse_money accepts.

Multi-line fields (8609 boxes A-C: name on the first line, address below)
are read by layout only: an AcroForm value can't be split by line, so a
fillable copy typed into those boxes will miss them.
"""

from .base import Anchor, FormSpec, Rule


# "Print name and title" / "Name of contact person": keep the person, drop a
# trailing ", Title" so the field holds a name like the other person fields.
_TITLE = (r",[^,]*$",)
# A line label ("8a", "1b") that OCR glued onto the amount: "8a-|4,620,000".
# Part II perjury statement, unique to the owner block (the agency block lacks "accompanying attachments")
_OWNER_STATEMENT = "examined this form and accompanying attachments"
_LINE_NO = (r"(^|\s)\d{1,2}[a-z][-|.:]*",)


def _acro(n):
    return (rf"\.f1_{n}\[0\]$",)


def _below(phrase, dx0, dx1, dy0, dy1, occurrence=1):
    return Anchor(phrase, (dx0, dy0, dx1, dy1), origin="x0", page=1, occurrence=occurrence)


def _right(phrase, dx0, dx1, dy0=-4, dy1=9, origin="x1", occurrence=1):
    return Anchor(phrase, (dx0, dy0, dx1, dy1), origin=origin, page=1, occurrence=occurrence)


F8609 = FormSpec(
    id="irs_8609",
    name="IRS Form 8609 Low-Income Housing Credit Allocation and Certification",
    doc_kind="irs_lihtc_form",
    program="LIHTC",
    detect=(("Low-Income Housing Credit Allocation", 2.0), ("First-Year Certification", 1.0),
            ("Building identification number (BIN)", 0.5)),
    min_score=2.5,
    acro_signature=(r"Page1\[0\]\.LineC_ReadOrder\[0\]",),
    rules=(
        # Box A: building name on the first line, its address on the next
        Rule("building_name", "text",
             anchors=(_below("Address of building", -16, 245, 10, 27),), canonical="property_name"),
        Rule("building_address", "text",
             anchors=(_below("Address of building", -16, 245, 27.5, 47),), canonical="property_address"),
        # Box B: agency name on the first line
        Rule("agency_name", "text",
             anchors=(_below("Name and address of housing credit agency", -18, 265, 10, 27),)),
        # Box C: owner name on the first line; owner TIN on the "TIN" row below the box
        Rule("owner_name", "text",
             anchors=(_below("Name, address, and TIN of building owner", -14, 240, 9, 25),), canonical="owner_name"),
        Rule("owner_tin_masked", "text", acro=_acro(4) + _acro(18),
             anchors=(_below("Name, address, and TIN of building owner", 20, 170, 46, 60),)),
        Rule("bin", "text", acro=_acro(6),
             anchors=(_below("Building identification number (BIN)", -18, 260, 14, 37),), canonical="bin"),
        Rule("allocation_date", "date", acro=_acro(7), anchors=(_right("Date of allocation", 85, 155, origin="x0"),)),
        Rule("max_credit_amount", "money", acro=_acro(8),
             anchors=(_right("Maximum housing credit dollar amount allowable", 240, 345, origin="x0"),), strip=_LINE_NO),
        Rule("credit_percentage", "pct", acro=_acro(9),
             anchors=(_right("Maximum applicable credit percentage allowable", 413, 518, origin="x0"),),
             strip=(r"^\s*2\b(?=\s*[\d.])",)),
        Rule("max_qualified_basis", "money", acro=_acro(10),
             anchors=(_right("Maximum qualified basis", 413, 518, origin="x0"),), strip=_LINE_NO),
        Rule("placed_in_service_date", "date", acro=_acro(14),
             anchors=(_right("Date building placed in service", 330, 412, origin="x0"),), canonical="placed_in_service_date"),
        # Agency signature row: name and date sit above the printed captions
        Rule("agency_official", "text", acro=_acro(15),
             anchors=(_below("I declare that the allocation made", 118, 316, 27, 44),
                      _below("Name (please type or print)", -60, 135, -16, -3, occurrence=1))),
        Rule("agency_signature_date", "date",
             anchors=(_below("I declare that the allocation made", 326, 410, 27, 44),
                      _below("Name (please type or print)", 150, 232, -16, -3, occurrence=1))),
        Rule("eligible_basis", "money", acro=_acro(16), anchors=(_right("Eligible basis of building", 413, 518, origin="x0"),), strip=_LINE_NO),
        Rule("original_qualified_basis", "money", acro=_acro(17),
             anchors=(_right("Original qualified basis of the building", 413, 518, origin="x0"),), strip=_LINE_NO),
        # Owner signature rows
        Rule("owner_signature_date", "date",
             anchors=(_below(_OWNER_STATEMENT, 255, 340, 20, 33),
                      _below("Taxpayer identification number", 158, 240, -16, -3))),
        Rule("owner_signer", "text", acro=_acro(19),
             anchors=(_below(_OWNER_STATEMENT, -165, 30, 44, 58),
                      _below("Name (please type or print)", -60, 135, -16, -3, occurrence=2))),
        Rule("first_credit_year", "int", acro=_acro(20),
             anchors=(_below(_OWNER_STATEMENT, 45, 240, 44, 58),
                      _below("First year of the credit period", -55, 130, -16, -3, occurrence=2))),
    ),
    lease_map={"landlord": "owner_name", "property_address": "building_address"},
)


F8823 = FormSpec(
    id="irs_8823",
    name="IRS Form 8823 Low-Income Housing Credit Agencies Report of Noncompliance or Building Disposition",
    doc_kind="irs_lihtc_form",
    program="LIHTC",
    detect=(("Report of Noncompliance or Building Disposition", 3.0), ("Form 8823", 1.0)),
    min_score=3.0,
    acro_signature=(r"\.f1_01\[0\]$", r"\.f1_25\[0\]$"),
    rules=(
        Rule("building_name", "text", acro=(r"\.f1_01\[0\]$",),
             anchors=(_below("Building name (if any)", -20, 245, 7, 21),), canonical="property_name"),
        Rule("building_street", "text", acro=(r"\.f1_02\[0\]$",),
             anchors=(_below("Street address", -20, 245, 7, 21, occurrence=1),), canonical="property_address"),
        Rule("building_city_state_zip", "text", acro=(r"\.f1_03\[0\]$",),
             anchors=(_below("City or town, state, and ZIP code", -20, 118, 7, 21, occurrence=1),)),
        Rule("bin", "text", acro=(r"\.f1_04\[0\]$",),
             anchors=(_right("Building identification number (BIN)", 0, 125),), canonical="bin"),
        Rule("owner_name", "text", acro=(r"\.f1_05\[0\]$",),
             anchors=(_below("Owner’s name", -20, 245, 7, 21, occurrence=1),), canonical="owner_name"),
        Rule("owner_tin_masked", "text", acro=(r"\.f1_08\[0\]$",),
             anchors=(_below("Owner’s taxpayer identification number", -20, 158, 7, 21, occurrence=1),)),
        Rule("total_credit_allocated", "money", acro=(r"\.f1_09\[0\]$",),
             anchors=(_right("Total credit allocated to this BIN", 435, 515, origin="x0"),)),
        Rule("residential_units", "int", acro=(r"\.f1_11\[0\]$",),
             anchors=(_right("Total number of residential units in this building", 435, 515, origin="x0", occurrence=1),)),
        Rule("low_income_units", "int", acro=(r"\.f1_12\[0\]$",),
             anchors=(_right("Total number of low-income units in this building", 435, 515, origin="x0"),)),
        Rule("units_with_noncompliance", "int", acro=(r"\.f1_13\[0\]$",),
             anchors=(_right("determined to have noncompliance issues", 264, 344, origin="x0"),)),
        Rule("units_reviewed", "int", acro=(r"\.f1_14\[0\]$",),
             anchors=(_right("Total number of units reviewed by agency", 435, 515, origin="x0"),)),
        Rule("date_ceased_to_comply", "date", acro=(r"\.f1_15\[0\]$",),
             anchors=(_right("Date building ceased to comply", 420, 515, origin="x0"),)),
        Rule("date_noncompliance_corrected", "date", acro=(r"\.f1_16\[0\]$",),
             anchors=(_right("Date noncompliance corrected", 420, 515, origin="x0"),)),
        Rule("contact_person", "text", acro=(r"\.f1_22\[0\]$",), strip=_TITLE,
             anchors=(_below("Name of contact person", -16, 240, 7, 21),)),
        Rule("contact_phone", "text", acro=(r"\.f1_23\[0\]$",),
             anchors=(_below("Telephone number of contact person", -16, 150, 7, 21),)),
        Rule("agency_official", "text", acro=(r"\.f1_25\[0\]$",), strip=_TITLE,
             anchors=(_below("Print name and title", -4, 214, -16, -3),)),
        Rule("signature_date", "date",
             anchors=(_below("Date (MMDDYYYY)", -6, 72, -16, -3),)),
    ),
    lease_map={"landlord": "owner_name", "property_address": ("building_street", "building_city_state_zip")},
)


F8586 = FormSpec(
    id="irs_8586",
    name="IRS Form 8586 Low-Income Housing Credit",
    doc_kind="irs_lihtc_form",
    program="LIHTC",
    detect=(("Number of Forms 8609-A attached", 2.0), ("Form 8586", 1.0),
            ("Current year credit from attached Form(s) 8609-A", 1.0)),
    min_score=2.5,
    rules=(
        Rule("taxpayer_name", "text", acro=_acro(1),
             anchors=(_below("Name(s) shown on return", -6, 410, 6, 22),), canonical="owner_name"),
        Rule("identifying_number_masked", "text", acro=_acro(2),
             anchors=(_below("Identifying number", -6, 120, 6, 22),)),
        Rule("forms_8609a_attached", "int", acro=_acro(3),
             anchors=(_right("Number of Forms 8609-A attached", 336, 420, origin="x0"),)),
        Rule("current_year_credit", "money", acro=_acro(8),
             anchors=(_right("Current year credit from attached Form(s) 8609-A", 437, 517, origin="x0"),)),
        Rule("total_credit_line5", "money", acro=_acro(10),
             anchors=(_right("this amount on Schedule K", 437, 517, origin="x0"),)),
    ),
    lease_map={"landlord": "taxpayer_name"},
)

FORMS = [F8609, F8823, F8586]
