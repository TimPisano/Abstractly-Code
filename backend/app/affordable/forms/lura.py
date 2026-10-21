"""
CHFA (Colorado) Land Use Restriction Agreement, low-income housing tax credit
template (9/23 rev). Partial mapping, by design.

A LURA is prose. Only the blanks that sit in open gaps of a sentence, or in
the exhibits, can be read by label position: unit count, city, county,
the street address (Exhibit A), BIN and minimum applicable fraction
(Exhibit B), and the 60% AMI unit count.

Not mapped: values typed over underscore lines (agreement date, owner,
project name, notice contacts, signers). pdfplumber interleaves the
underscore glyphs with the typed characters ("_C_e_d_a_r"), and the engine
can't rejoin them yet. Those, and other states' LURAs, are a job for the
AI route.
"""

from .base import Anchor, FormSpec, Rule

CHFA_LURA = FormSpec(
    id="chfa_lura",
    route="ai",                     # prose with inline blanks; and the title also matches non-CHFA LURAs
    name="CHFA Low-Income Housing Tax Credit Land Use Restriction Agreement",
    doc_kind="lura",
    program="LIHTC",
    detect=(("Land Use Restriction Agreement", 2.0), ("Colorado Housing and Finance Authority", 1.0)),
    min_score=3.0,
    rules=(
        # "the owner of a ( 46 ) unit rental housing development"
        Rule("total_units", "int",
             anchors=(Anchor("unit rental housing development", (-40, -4, -3, 9), origin="x0", page=1),)),
        # "lands in the City of Alder Springs , County of Larkspur , State of Colorado"
        Rule("city", "text",
             anchors=(Anchor("lands in the City of", (2, -4, 96, 9), origin="x1", page=1),)),
        Rule("county", "text",
             anchors=(Anchor("County of", (2, -4, 62, 9), origin="x1", page=1, occurrence=1),)),
        # "_____ (44) units 60% or less of AMI"
        Rule("units_at_60_pct_ami", "int",
             anchors=(Anchor("60% or less of AMI", (-100, -4, -25, 9), origin="x0", page=7),)),
        # Exhibit A: street address typed under "Also known as:"
        Rule("street_address", "text",
             anchors=(Anchor("Also known as:", (-6, 9, 400, 26), origin="x0", page=16),), canonical="property_address"),
        # Exhibit B table
        Rule("bin", "text",
             anchors=(Anchor("Building Identification Number", (-30, 14, 170, 45), origin="x0", page=17),),
             canonical="bin"),
        Rule("min_applicable_fraction", "pct",
             anchors=(Anchor("Minimum Applicable Fraction", (-60, 14, 120, 45), origin="x0", page=17, occurrence=2),)),
    ),
    lease_map={"property_address": "street_address"},
)

FORMS = [CHFA_LURA]
