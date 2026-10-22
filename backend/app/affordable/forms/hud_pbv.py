"""
Project-Based Voucher HAP contracts (07/2019 editions):

  HUD-52530A  Part 1, new construction / rehabilitation
  HUD-52530B  Part 1, existing housing

Boxes were measured on the blank forms. The fillable-field names (Text1,
Text2, ...) are specific to these editions, so they're matched exactly.

Not mapped, on purpose: the contract number and the project name/address.
Part 1 of these forms has no printed field for either (the project and its
units are listed in Exhibit A, a separate attachment), so any value found
would depend on where a particular PHA happened to type it.
"""

from .base import Anchor, FormSpec, Rule

# A signatory line is read from the region around its label, which can also
# hold a typed "/s/ Name" signature or a date; strip those.
SIGNATORY_STRIP = (r"/s/\s*\S+(?:\s+\S+)?", r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
                   r"\b[A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+\d{4}\b", r"\bBy:")


def _right(phrase, width, page, dy0=-6, dy1=10, dx0=-2, occurrence=1):
    """Value on the same line, right of the label (over the printed rule)."""
    return Anchor(phrase, (dx0, dy0, width, dy1), origin="x1", page=page, occurrence=occurrence)


def _below(phrase, width, page, dy0=10, dy1=70, dx0=-12, occurrence=1):
    return Anchor(phrase, (dx0, dy0, width, dy1), origin="x0", page=page, occurrence=occurrence)


def _left(phrase, page, dy0=-8, dy1=12):
    """Value typed over the rule that precedes the label, e.g. "______ (PHA) and"."""
    return Anchor(phrase, (-300, dy0, -2, dy1), origin="x0", page=page)


def _signature_block(sig_page, pha_name_acro, pha_title_acro, pha_date_acro,
                     owner_name_acro, owner_title_acro, owner_date_acro):
    # Captions sit *under* their lines on these forms, so each field belongs to
    # the caption below it: name/title -> "Name and official title", date -> "Date".
    return (
        Rule("pha_name", "text", acro=(pha_name_acro, r"^Text1$"), strip=(r"\bBy:",),
             anchors=(_below("Name of PHA (Print)", 430, sig_page), _left("(PHA) and", 1)), canonical="pha_name"),
        Rule("owner_name", "text", acro=(owner_name_acro, r"^Text2$"), strip=(r"\bBy:",),
             anchors=(_below("Name of Owner (Print)", 430, sig_page), _left("(owner).", 1)), canonical="owner_name"),
        Rule("pha_signatory", "text", acro=(pha_title_acro,), strip=SIGNATORY_STRIP,
             anchors=(Anchor("Name and official title (Print)", (-12, -30, 430, 40), origin="x0",
                             page=sig_page, occurrence=1),)),
        Rule("owner_signatory", "text", acro=(owner_title_acro,), strip=SIGNATORY_STRIP,
             anchors=(Anchor("Name and official title (Print)", (-12, -30, 430, 40), origin="x0",
                             page=sig_page, occurrence=2),)),
        # No date fields on the single-stage execution page: dates are typed by
        # the "Date" label (on the line above it, beside it, or just under it).
        Rule("pha_signature_date", "date", acro=(pha_date_acro,),
             anchors=(Anchor("Date", (-12, -24, 300, 18), origin="x0", page=sig_page, occurrence=1),)),
        Rule("owner_signature_date", "date", acro=(owner_date_acro,),
             anchors=(Anchor("Date", (-12, -24, 300, 18), origin="x0", page=sig_page, occurrence=2),)),
    )


PBV_NEW_CONSTRUCTION = FormSpec(
    id="hud_52530a",
    route="ai",                 # units, bedroom mix and rents are in the PHA's own Exhibit A
    name="HUD-52530A PBV HAP Contract, Part 1 (New Construction/Rehab)",
    doc_kind="hap_contract",
    program="PBV",
    detect=(("HUD 52530A", 2.0), ("HAP Contract for New Construction/Rehab", 1.0), ("Project-Based Voucher Program", 0.5)),
    rules=(
        Rule("effective_date", "date", acro=(r"^Text3$",),
             anchors=(_right("the HAP contract is:", 210, page=2),), canonical="contract_effective_date"),
        Rule("initial_term", "text", acro=(r"^Text6$",),
             anchors=(Anchor("Subject to paragraph 2.b, the initial term of the HAP contract for",
                             (122, 8, 340, 24), origin="x0", page=3),
                      _right("any contract units is:", 210, page=3)), canonical="contract_term"),
        Rule("units_prior_hud_assistance", "int", acro=(r"^Text14$",),
             anchors=(_right("assistance listed above:", 180, page=7),)),
        Rule("units_federal_rent_restriction", "int", acro=(r"^Text20$",),
             anchors=(_right("restriction listed above:", 180, page=7),)),
        Rule("elderly_designated_units", "int", acro=(r"^Text28$",),
             anchors=(_below("contract units shall be rented to elderly families:", 270, page=7, dy0=10, dy1=36),)),
    ) + _signature_block(9, r"^Text30$", r"^Text31$", r"^Text32$", r"^Text33$", r"^Text34$", r"^Text35$"),
    lease_map={"landlord": "owner_name", "lease_start_date": "effective_date"},
)

PBV_EXISTING = FormSpec(
    id="hud_52530b",
    route="ai",                 # units, bedroom mix and rents are in the PHA's own Exhibit A
    name="HUD-52530B PBV HAP Contract, Part 1 (Existing Housing)",
    doc_kind="hap_contract",
    program="PBV",
    detect=(("HUD 52530B", 2.0), ("HAP Contract for Existing Housing", 1.0), ("Project-Based Voucher Program", 0.5)),
    rules=(
        Rule("effective_date", "date", acro=(r"^Text3$",),
             anchors=(_below("effective date of the HAP contract is:", 240, page=2, dx0=-140, dy0=14, dy1=36),
                      Anchor("The term of the HAP contract begins on the effective date.", (-40, -34, 250, -14),
                             origin="x0", page=2)),
             canonical="contract_effective_date"),
        Rule("initial_term", "text", acro=(r"^Text4$",),
             anchors=(Anchor("Length of initial term", (-20, 58, 300, 80), origin="x0", page=2),
                      _below("all contract units is:", 260, page=2, dy0=14, dy1=36)), canonical="contract_term"),
        Rule("units_prior_hud_assistance", "int", acro=(r"^Text12$",),
             anchors=(_right("assistance listed above:", 180, page=6),)),
        Rule("units_federal_rent_restriction", "int", acro=(r"^Text18$",),
             anchors=(_right("restriction listed above:", 180, page=6),)),
        Rule("elderly_designated_units", "int", acro=(r"^Text21$",),
             anchors=(_below("contract units shall be rented to elderly families:", 270, page=7, dy0=10, dy1=36),)),
    ) + _signature_block(8, r"^Text23$", r"^Text24$", r"^Text25$", r"^Text26$", r"^Text27$", r"^Text28$"),
    lease_map={"landlord": "owner_name", "lease_start_date": "effective_date"},
)

FORMS = [PBV_NEW_CONSTRUCTION, PBV_EXISTING]
