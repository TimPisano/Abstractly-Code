"""
Section 811 Project Rental Assistance (PRA) lease:

  HUD-92236-PRA  811 Project Rental Assistance Lease -- 02/2014 edition

The lease is prose, but its money blanks are printed in fixed places:
paragraph 1 names the project, paragraph 2 the total (contract) rent,
paragraph 3 the utility allowance, paragraph 4 splits the total rent into
the part HUD pays and the part the tenant pays, paragraph 6 the deposit.
This reader takes those blanks; the AI lease engine still reads parties,
dates and clauses (route "ai"), and the eval keeps both reads.

HUD's blank isn't in tests/eval/affordable/sources, so the boxes were
measured from the printed underscore runs on TDHCA's filled training copy
(the form's own label text and blank lines, not its typed values). Values
are typed on top of the blanks, sometimes a line below the label.
"""

from .base import Anchor, FormSpec, Rule

HUD_92236_PRA = FormSpec(
    id="hud_92236_pra",
    name="HUD-92236-PRA 811 Project Rental Assistance Lease",
    doc_kind="pra_lease",
    program="Section 811 PRA",
    detect=(("811 Project Rental Assistance Lease", 1.5), ("HUD-92236-PRA", 2.0),
            ("SUPPORTIVE HOUSING FOR PERSONS WITH DISABILITIES", 0.5)),
    route="ai",
    rules=(
        # "...dwelling unit in the project known as" / "____<project>____ for a term of one year"
        Rule("project_name", "text",
             anchors=(Anchor("dwelling unit in the project known as", (-81.0, 6.0, 137.0, 18.0), origin="x0"),),
             canonical="project_name"),
        # "The total rent (Contract Rent) shall be $____ per month."
        Rule("contract_rent", "money", strip=(r"\$",),
             anchors=(Anchor("The total rent (Contract Rent) shall be", (0.0, -4.0, 76.0, 8.0)),),
             canonical="contract_rent"),
        # "...for which the Utility Allowance is" / "$____."
        Rule("utility_allowance", "money", strip=(r"\$",),
             anchors=(Anchor("following utility service(s), for which the Utility Allowance is",
                             (-3.0, 6.0, 30.0, 18.0), origin="x0"),),
             canonical="utility_allowance"),
        # "Of the total rent, $____ shall be payable by or at the direction of HUD..."
        Rule("assistance_payment", "money", strip=(r"\$",),
             anchors=(Anchor("Of the total rent,", (0.0, -4.0, 68.0, 8.0)),),
             canonical="assistance_payment"),
        # "...TENANT, and $____ shall be payable by the TENANT."
        Rule("tenant_rent", "money", strip=(r"\$",),
             anchors=(Anchor("shall be payable by the TENANT", (-86.0, -4.0, -3.0, 8.0), origin="x0"),),
             canonical="tenant_rent"),
        # "...makes a deposit of $____ against any damage except reasonable wear"
        Rule("security_deposit", "money", strip=(r"\$",),
             anchors=(Anchor("against any damage except reasonable wear", (-118.0, -4.0, -3.0, 8.0), origin="x0"),),
             canonical="security_deposit"),
    ),
    lease_map={"rent_amount": "contract_rent", "security_deposit": "security_deposit"},
)

FORMS = [HUD_92236_PRA]
