"""
The credit memo TEMPLATE -- and nothing else.

This file exists on its own so a specific lender's memo format can
replace it without touching any logic. It holds the section order, the
headings, which sections carry engine tables, and which carry AI-drafted
prose. It deliberately contains:

  * no Anthropic calls          (credit_memo.py)
  * no .docx rendering          (credit_memo_export.py)
  * no arithmetic whatsoever    (loan_underwriting.py)

To swap in a lender's format, change SECTIONS below. A section's `blocks`
name data the engine already produces; adding a heading or reordering
sections needs no code change anywhere else. The only hard requirement is
that `loan_summary` keeps a `recommendation_placeholder` block -- see
RECOMMENDATION_PLACEHOLDER.

Standard bank structure, in order:
  1. Loan summary and recommendation
  2. Property
  3. Sponsor
  4. Rent roll and lease analysis
  5. Historical and underwritten financials
  6. Ratios and stress tests
  7. Risks and mitigants
  8. Conditions
"""

MEMO_TITLE = "Credit Memorandum"

# The recommendation line. This is a PLACEHOLDER, permanently.
#
# The tool does not recommend approval or denial, and must not appear to.
# Underwriting a loan is a credit decision with legal and fiduciary
# weight that belongs to a credit officer, who has context this tool
# never sees -- borrower relationship, portfolio concentration, market
# knowledge, the lender's own appetite. A model that emitted "recommend
# approval" here would be producing the single most consequential
# sentence in the document from the least information.
#
# So: the engine computes every ratio and says which constraint binds,
# and a human writes the recommendation. credit_memo.py also instructs
# the model explicitly not to state one, and
# tests/test_credit_memo.py asserts the generated memo contains this
# placeholder and no approval language -- enforced as behavior, not just
# as a prompt line, because a prompt instruction is not a guarantee.
RECOMMENDATION_PLACEHOLDER = (
    "[ FOR CREDIT OFFICER DETERMINATION -- this analysis does not recommend "
    "approval or denial. The ratios, constraint tests and stress cases above "
    "are provided so that a credit officer can reach their own conclusion. ]"
)

SPONSOR_PLACEHOLDER = (
    "[ SPONSOR ANALYSIS TO BE COMPLETED -- this tool holds no sponsor "
    "information. Net worth, liquidity, track record, schedule of real estate "
    "owned, credit history and guarantor structure must be added by the "
    "analyst from sources outside this application. ]"
)

# Every figure a memo can print comes from one of these named blocks, and
# each block is rendered from the engine's output by
# credit_memo_export.py. A section lists the blocks it wants, in order.
#
# "narrative" sections get AI-drafted prose. Those are the ONLY places a
# model writes anything, and even there it is given the computed numbers
# as context and told to reference them rather than produce them.
SECTIONS = [
    {
        "key": "loan_summary",
        "heading": "1. Loan Summary and Recommendation",
        "blocks": ["loan_terms_table", "headline_ratios_table", "binding_constraint_statement",
                   "recommendation_placeholder"],
        "narrative": False,
    },
    {
        "key": "property",
        "heading": "2. Property",
        "blocks": ["property_table", "narrative"],
        "narrative": True,
        # What the model is asked to write about. Kept here beside the
        # section rather than in credit_memo.py so that swapping this
        # file for a lender's format also swaps what the prose covers.
        "narrative_brief": (
            "Describe the property as a lending proposition: unit count, location, "
            "and what the trailing financials indicate about its operating "
            "performance. Reference the figures given; do not introduce new ones."
        ),
    },
    {
        "key": "sponsor",
        "heading": "3. Sponsor",
        "blocks": ["sponsor_placeholder"],
        "narrative": False,
    },
    {
        "key": "rent_roll_analysis",
        "heading": "4. Rent Roll and Lease Analysis",
        "blocks": ["rent_roll_table", "narrative"],
        "narrative": True,
        "narrative_brief": (
            "Explain what the rent roll and lease review means for credit: whether the "
            "in-place rent the rent roll claims is supported by the signed leases, and "
            "what the T-12's collection history says about how much of billed rent "
            "actually converts to cash. Reference the figures given; do not introduce "
            "new ones."
        ),
    },
    {
        "key": "financials",
        "heading": "5. Historical and Underwritten Financials",
        "blocks": ["noi_build_up_table", "historical_vs_underwritten_table", "t12_line_items_table"],
        "narrative": False,
    },
    {
        "key": "ratios_and_stress",
        "heading": "6. Ratios and Stress Tests",
        "blocks": ["ratios_table", "max_loan_table", "stress_table"],
        "narrative": False,
    },
    {
        "key": "risks",
        "heading": "7. Risks and Mitigants",
        "blocks": ["narrative"],
        "narrative": True,
        "narrative_brief": (
            "Identify the material credit risks this specific deal's numbers reveal, each "
            "with a mitigant where one genuinely exists. Be concrete and tie each risk to "
            "a figure above. If a risk has no real mitigant, say so plainly rather than "
            "inventing one. Do not state an overall recommendation."
        ),
    },
    {
        "key": "conditions",
        "heading": "8. Conditions",
        "blocks": ["narrative"],
        "narrative": True,
        "narrative_brief": (
            "List conditions a lender would reasonably require before closing, given these "
            "numbers and any data gaps noted. Frame them as proposed conditions for the "
            "credit officer's consideration, not as decisions already made."
        ),
    },
]

# Shown once under the title. States what the document is and what it is
# not, so a reader who opens the .docx with no other context cannot
# mistake it for an approved credit decision or for audited figures.
MEMO_PREAMBLE = (
    "This memorandum was prepared from the loan request, the trailing twelve-month "
    "operating statement, and the lease and rent roll documents on file. Every figure "
    "in the tables below is computed arithmetically from those inputs; narrative "
    "sections are drafted text for analyst review. Figures sourced from a document "
    "cite that document and the row or page they came from. This memorandum contains "
    "no credit recommendation."
)

# Printed at the end of the document.
MEMO_FOOTER = (
    "Prepared by Abstractly. Computed figures are reproducible from the cited source "
    "documents. Narrative sections are drafts for analyst review and are not "
    "independent verification. This memorandum does not constitute a credit decision, "
    "a commitment to lend, or an appraisal."
)


def narrative_sections():
    """The sections that get AI-drafted prose, as (key, heading, brief) tuples -- the single source of truth for what credit_memo.py asks the model to write."""
    return [
        (section["key"], section["heading"], section["narrative_brief"])
        for section in SECTIONS
        if section.get("narrative")
    ]


def section_by_key(key: str):
    """One section spec by key, or None."""
    return next((section for section in SECTIONS if section["key"] == key), None)
