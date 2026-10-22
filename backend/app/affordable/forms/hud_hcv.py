"""
Housing Choice Voucher forms the owner fills in or receives:

  HUD-52517  Request for Tenancy Approval (RFTA)      -- 04/2023 edition
  HUD-52641  HAP Contract, tenant-based (Parts A-C)   -- 04/2023 edition

Boxes were measured on the blank forms (printed label positions). The
52641 circulates as PHA re-saves whose text spacing differs, so its labels
are matched spacing-insensitively and its boxes are generous.
"""

from .base import Anchor, FormSpec, Rule


def _below(phrase, width, dy0=8, dy1=40, dx0=-14, page=None, occurrence=1):
    """Value printed under the label, within `width` points from the label's left edge."""
    return Anchor(phrase, (dx0, dy0, width, dy1), origin="x0", page=page, occurrence=occurrence)


RFTA = FormSpec(
    id="hud_52517",
    name="HUD-52517 Request for Tenancy Approval",
    doc_kind="rfta",
    program="HCV",
    detect=(("Request for Tenancy Approval", 2.0), ("HUD-52517", 2.0), ("Housing Choice Voucher Program", 0.5)),
    rules=(
        Rule("pha_name", "text", acro=(r"^1 Name of Public Housing Agency",),
             anchors=(_below("Name of Public Housing Agency (PHA)", 300, page=1),), canonical="pha_name"),
        Rule("unit_address", "text", acro=(r"^2 Address of Unit",),
             anchors=(_below("Address of Unit", 250, dx0=-16, page=1),), canonical="unit_address"),
        Rule("requested_lease_start", "date", acro=(r"^3 Requested Lease Start",),
             anchors=(_below("Requested Lease Start", 112, dy0=18, dy1=48, page=1),), canonical="lease_start"),
        Rule("bedrooms", "int", acro=(r"^4 Number of Bedrooms",),
             anchors=(_below("Number of Bedrooms", 92, dy0=18, dy1=48, page=1),), canonical="bedrooms"),
        Rule("year_constructed", "int", acro=(r"^5\s*Year Constructed",),
             anchors=(_below("Year Constructed", 80, dy0=18, dy1=48, page=1),)),
        Rule("proposed_rent", "money", acro=(r"^6 Proposed Rent",),
             anchors=(_below("Proposed Rent", 66, dy0=18, dy1=48, page=1),), canonical="contract_rent"),
        Rule("security_deposit", "money", acro=(r"^7\s*Security Deposit",),
             anchors=(_below("Security Deposit", 82, dy0=18, dy1=48, page=1),), canonical="security_deposit"),
        Rule("date_unit_available", "date", acro=(r"^Text4$",),
             anchors=(_below("Date Unit Available", 90, dy0=18, dy1=48, page=1),)),
        Rule("owner_name", "text", acro=(r"^Print or Type Name of Owner",),
             anchors=(_below("Print or Type Name of Owner/Owner Representative", 268, dy0=9, dy1=34, page=2),),
             canonical="owner_name"),
        Rule("household_head", "text", acro=(r"^Print or Type Name of Household Head",),
             anchors=(_below("Print or Type Name of Household Head", 268, dy0=9, dy1=34, page=2),),
             canonical="head_of_household"),
        Rule("owner_signed_date", "date", acro=(r"^Date mmddyyyy$",),
             anchors=(_below("Date (mm/dd/yyyy)", 100, dy0=9, dy1=34, page=2, occurrence=1),)),
        Rule("household_signed_date", "date", acro=(r"^Date mmddyyyy-0$",),
             anchors=(_below("Date (mm/dd/yyyy)", 100, dy0=9, dy1=34, page=2, occurrence=2),)),
    ),
    acro_signature=(r"^1 Name of Public Housing Agency", r"^6 Proposed Rent"),
    lease_map={
        "tenant": "household_head",
        "landlord": "owner_name",
        "rent_amount": "proposed_rent",
        "lease_start_date": "requested_lease_start",
        "property_address": "unit_address",
        "security_deposit": "security_deposit",
    },
)

def _at(phrase, box, page, occurrence=1):
    """Box relative to the label's left edge and top: (dx0, dy0, dx1, dy1)."""
    return Anchor(phrase, box, origin="x0", page=page, occurrence=occurrence)


# Part A (page 2) and the signature / payee block (page 3). No fillable fields
# in the 4/2023 edition. Signature-block labels sit *under* their lines, so
# those values are read from just above the label.
_HH_ROWS = ((13, 26.5), (26.5, 39.5), (39.5, 52.5))   # typed household lines under section 4's text

HAP_CONTRACT = FormSpec(
    id="hud_52641",
    name="HUD-52641 HAP Contract (Housing Choice Voucher), Part A",
    doc_kind="hap_contract",
    program="HCV",
    detect=(("HUD-52641", 2.0), ("Housing Assistance Payments Contract", 1.0),
            ("Section 8 Tenant-Based Assistance", 1.0)),
    rules=(
        Rule("tenant_name", "text", anchors=(_at("2. Tenant", (-10, 10, 500, 56), page=2),),
             canonical="head_of_household"),
        Rule("contract_unit_address", "text", anchors=(_at("3. Contract Unit", (-10, 10, 500, 56), page=2),),
             canonical="unit_address"),
    ) + tuple(
        Rule(f"household_member_{i}", "text",
             anchors=(_at("the owner and the PHA.", (-30, lo, 480, hi), page=2),))
        for i, (lo, hi) in enumerate(_HH_ROWS, start=1)
    ) + (
        # Section headings are the anchors here: they're distinct from each other,
        # while the sentence labels ("...term begins on" / "...term ends on") are
        # near-identical and easy to confuse on a scan.
        Rule("lease_term_start", "date",
             anchors=(_at("5. Initial Lease Term", (130, 9, 360, 25), page=2),
                      _at("The initial lease term begins on", (120, -8, 340, 12), page=2)), canonical="lease_start"),
        Rule("lease_term_end", "date",
             anchors=(_at("5. Initial Lease Term", (130, 30, 360, 46), page=2),
                      _at("The initial lease term ends on", (120, -8, 340, 12), page=2)), canonical="lease_end"),
        Rule("initial_rent_to_owner", "money",
             anchors=(_at("6. Initial Rent to Owner", (110, 7, 300, 22), page=2),
                      _at("The initial rent to owner is:", (95, -8, 270, 9), page=2)), canonical="contract_rent"),
        Rule("initial_hap", "money",
             anchors=(_at("7. Initial Housing Assistance Payment", (200, 28, 360, 43.5), page=2),
                      _at("of the housing assistance payment by the PHA to the owner is", (200, -8, 350, 9), page=2)),
             canonical="hap_amount"),
        # "Name of PHA" / "Name of Owner" rather than the full "Print or Type ..."
        # labels, which differ only in their last word.
        Rule("pha_name", "text", anchors=(_at("Name of PHA", (-80, -22, 200, -1), page=3),), canonical="pha_name"),
        Rule("owner_name", "text", anchors=(_at("Name of Owner", (-80, -22, 180, -1), page=3),), canonical="owner_name"),
        # Dates sit two label rows under each name column.
        Rule("pha_signature_date", "date", anchors=(_at("Name of PHA", (-80, 88, 200, 110), page=3),)),
        Rule("owner_signature_date", "date", anchors=(_at("Name of Owner", (-80, 88, 180, 110), page=3),)),
        Rule("payee_address", "text",
             anchors=(_at("Address (street, city, state, zip code)", (-10, -48, 250, -1), page=3),)),
    ),
    lease_map={
        "tenant": "tenant_name",
        "landlord": "owner_name",
        "rent_amount": "initial_rent_to_owner",
        "lease_start_date": "lease_term_start",
        "lease_end_date": "lease_term_end",
        "property_address": "contract_unit_address",
    },
    notes="Both PHA re-saves in the eval (normal and squashed text spacing) share this layout.",
)

FORMS = [RFTA, HAP_CONTRACT]
