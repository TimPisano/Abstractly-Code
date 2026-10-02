"""
Three complete fictional deals, each hand-calculated end to end (NOI,
debt service, DSCR, LTV, debt yield, breakeven occupancy, max loan by
every constraint, and which one binds) and checked against the engine.

Unlike test_loan_underwriting.py (which isolates one formula at a time),
these exercise the full underwrite() pipeline on a realistic, internally
consistent deal -- the kind of check that catches a bug in how functions
compose, not just a bug in one function.

Every number below was derived independently with the standard annuity
formula and plain arithmetic (see each docstring for the full build-up),
not copied from the implementation's own output.

  * Deal A, Sunset Gardens -- a healthy, ordinary deal. LTV binds, and
    comes in BELOW the requested loan amount (the deal is oversized).
  * Deal B, Oakmont Terrace -- interest-only, tighter margins, two
    constraints (LTV and DSCR) land close together.
  * Deal C, Distressed Pointe -- the negative-NOI edge case: a property
    whose expenses exceed its effective income supports zero debt by
    both the DSCR and debt-yield tests, while LTV alone would still
    suggest a nonzero loan. All fictional; no real property.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.loan_underwriting import underwrite


def _close(actual, expected, tolerance=0.01):
    return actual is not None and abs(actual - expected) <= tolerance


# ----------------------------------------------------------------------
# Deal A: Sunset Gardens Apartments (80 units) -- ordinary, healthy deal
# ----------------------------------------------------------------------

_DEAL_A_TERMS = {
    "loan_amount": 8_000_000.0, "annual_rate_pct": 6.0, "amortization_years": 30,
    "term_years": 10, "interest_only_months": 0,
    "purchase_price": 10_500_000.0, "appraised_value": 11_000_000.0, "unit_count": 80,
}
_DEAL_A_T12 = {
    "gross_potential_rent": 1_600_000.0, "loss_to_lease": 0.0, "concessions": 0.0,
    "bad_debt": 0.0, "other_income": 40_000.0,
    "operating_expenses_ex_management": 500_000.0, "unit_count": 80,
}
_DEAL_A_ASSUMPTIONS = {"vacancy_pct": 5.0, "management_fee_pct": 3.0, "replacement_reserves_per_unit": 250.0}


def test_deal_a_sunset_gardens_full_hand_calculation():
    """
    NOI build-up:
      GPR                         1,600,000.00
      less vacancy 5%                80,000.00  -> 1,520,000.00
      less loss to lease, concessions, bad debt: none
      = effective rental income   1,520,000.00
      plus other income               40,000.00
      = EGI                       1,560,000.00
      less opex ex mgmt              500,000.00
      less mgmt fee 3% of EGI         46,800.00
      less reserves 250 x 80 units    20,000.00
      = total opex                   566,800.00
      = NOI                          993,200.00

    Debt service, $8,000,000 @ 6.0% / 30yr, no IO:
      i = 0.06/12 = 0.005, n = 360
      1.005^-360 = 0.16604189 (same constant test_loan_underwriting.py
      derives for the $1M case; here scaled x8)
      annual payment factor = 12*0.005/0.83395811 = 0.07194606
      ADS = 8,000,000 x 0.07194606 = 575,568.50
      (no IO, so year-one ADS equals this too)

    Ratios:
      DSCR = 993,200 / 575,568.50               = 1.7256x
      value basis = min(10,500,000, 11,000,000) = 10,500,000 (purchase)
      LTV = 8,000,000 / 10,500,000               = 76.1905%
      debt yield = 993,200 / 8,000,000           = 12.4150%
      breakeven = (566,800 + 575,568.50)
                  / (1,600,000 + 40,000)         = 69.6566%

    Sizing at default constraints (1.25x / 75% / 8%):
      by DSCR       = (993,200/1.25) / 0.07194606 = 11,043,828.76
      by LTV        = 10,500,000 x 75%            =  7,875,000.00  <- binds
      by debt yield = 993,200 / 8%                = 12,415,000.00

    The requested $8,000,000 EXCEEDS the $7,875,000 LTV-bound maximum --
    this deal, as structured, is oversized by $125,000.
    """
    result = underwrite(_DEAL_A_TERMS, _DEAL_A_T12, assumptions=_DEAL_A_ASSUMPTIONS)

    build_up = result["noi_build_up"]
    assert build_up["vacancy_amount"] == 80_000.00, build_up
    assert build_up["effective_rental_income"] == 1_520_000.00, build_up
    assert build_up["effective_gross_income"] == 1_560_000.00, build_up
    assert build_up["management_fee"] == 46_800.00, build_up
    assert build_up["replacement_reserves"] == 20_000.00, build_up
    assert build_up["total_operating_expenses"] == 566_800.00, build_up
    assert build_up["underwritten_noi"] == 993_200.00, build_up

    debt_service = result["debt_service"]
    assert _close(debt_service["annual_debt_service_amortizing"], 575_568.50, 0.05), debt_service

    ratios = result["ratios"]
    assert _close(ratios["dscr"], 1.7256, 0.0001), ratios
    assert ratios["ltv_pct"] == 76.1905, ratios
    assert ratios["ltv_basis"] == "purchase_price", ratios
    assert ratios["debt_yield_pct"] == 12.4150, ratios
    assert _close(ratios["breakeven_occupancy_pct"], 69.6566, 0.001), ratios

    sizing = result["sizing"]
    assert _close(sizing["max_loan_by_dscr"], 11_043_828.76, 1.0), sizing
    assert sizing["max_loan_by_ltv"] == 7_875_000.00, sizing
    assert sizing["max_loan_by_debt_yield"] == 12_415_000.00, sizing
    assert sizing["binding_constraint"] == "ltv", sizing
    assert sizing["maximum_loan"] == 7_875_000.00, sizing
    assert sizing["maximum_loan"] < _DEAL_A_TERMS["loan_amount"], "deal is oversized -- the interesting result"
    print("✓ test_deal_a_sunset_gardens_full_hand_calculation: PASS")


# ----------------------------------------------------------------------
# Deal B: Oakmont Terrace (60 units) -- interest-only, tighter margins
# ----------------------------------------------------------------------

_DEAL_B_TERMS = {
    "loan_amount": 6_500_000.0, "annual_rate_pct": 7.0, "amortization_years": 30,
    "term_years": 10, "interest_only_months": 36,
    "purchase_price": 8_500_000.0, "appraised_value": 9_000_000.0, "unit_count": 60,
}
_DEAL_B_T12 = {
    "gross_potential_rent": 1_200_000.0, "loss_to_lease": 15_000.0, "concessions": 5_000.0,
    "bad_debt": 10_000.0, "other_income": 30_000.0,
    "operating_expenses_ex_management": 420_000.0, "unit_count": 60,
}
_DEAL_B_ASSUMPTIONS = {"vacancy_pct": 7.0, "management_fee_pct": 3.0, "replacement_reserves_per_unit": 300.0}


def test_deal_b_oakmont_terrace_full_hand_calculation():
    """
    NOI build-up:
      GPR                          1,200,000.00
      less vacancy 7%                 84,000.00
      less loss to lease              15,000.00
      less concessions                 5,000.00
      less bad debt                   10,000.00
      = effective rental income    1,086,000.00
      plus other income               30,000.00
      = EGI                        1,116,000.00
      less opex ex mgmt               420,000.00
      less mgmt fee 3% of EGI          33,480.00
      less reserves 300 x 60 units     18,000.00
      = total opex                    471,480.00
      = NOI                           644,520.00

    Debt service, $6,500,000 @ 7.0% / 30yr, 36 months interest-only:
      amortizing monthly payment      43,244.66  -> annual 518,935.95
      IO monthly payment              37,916.67  -> annual 455,000.00
      36 months IO >= 12, so ALL of year one is interest-only:
      year-one ADS = 455,000.00 (equals the IO figure exactly)
      annual payment factor = 12 x (0.07/12) / (1-(1.00583333)^-360)
                             = 0.07983630

    Ratios:
      DSCR (amortizing, the headline) = 644,520 / 518,935.95 = 1.2420x
      DSCR (year one, as actually paid) = 644,520 / 455,000  = 1.4165x
      -- the IO period makes year-one coverage look meaningfully better
      than the real, post-IO number. The headline uses the amortizing
      figure precisely so this gap doesn't get missed.
      value basis = min(8,500,000, 9,000,000)  = 8,500,000 (purchase)
      LTV = 6,500,000 / 8,500,000                = 76.4706%
      debt yield = 644,520 / 6,500,000           = 9.9157%
      breakeven = (471,480 + 518,935.95)
                  / (1,200,000 + 30,000)          = 80.5216%

    Sizing at default constraints (1.25x / 75% / 8%):
      by DSCR       = (644,520/1.25) / 0.07983630 = 6,458,415.58
      by LTV        = 8,500,000 x 75%             = 6,375,000.00  <- binds
      by debt yield = 644,520 / 8%                = 8,056,500.00

    LTV and DSCR land within ~$83K of each other -- a deal where either
    constraint plausibly binds depending on small input changes, unlike
    Deal A where LTV binds with room to spare.
    """
    result = underwrite(_DEAL_B_TERMS, _DEAL_B_T12, assumptions=_DEAL_B_ASSUMPTIONS)

    build_up = result["noi_build_up"]
    assert build_up["vacancy_amount"] == 84_000.00, build_up
    assert build_up["effective_rental_income"] == 1_086_000.00, build_up
    assert build_up["effective_gross_income"] == 1_116_000.00, build_up
    assert build_up["management_fee"] == 33_480.00, build_up
    assert build_up["replacement_reserves"] == 18_000.00, build_up
    assert build_up["total_operating_expenses"] == 471_480.00, build_up
    assert build_up["underwritten_noi"] == 644_520.00, build_up

    debt_service = result["debt_service"]
    assert _close(debt_service["annual_debt_service_amortizing"], 518_935.95, 0.05), debt_service
    assert debt_service["annual_debt_service_year_one"] == debt_service["annual_debt_service_interest_only"], \
        "36 months IO means all of year one is interest-only"
    assert _close(debt_service["annual_debt_service_year_one"], 455_000.00, 0.01), debt_service

    ratios = result["ratios"]
    assert _close(ratios["dscr"], 1.2420, 0.0001), ratios
    assert _close(ratios["dscr_year_one"], 1.4165, 0.0001), ratios
    assert ratios["dscr"] < ratios["dscr_year_one"], "the IO period must flatter year-one coverage"
    assert ratios["ltv_pct"] == 76.4706, ratios
    assert ratios["debt_yield_pct"] == 9.9157, ratios
    assert _close(ratios["breakeven_occupancy_pct"], 80.5216, 0.001), ratios

    sizing = result["sizing"]
    assert _close(sizing["max_loan_by_dscr"], 6_458_415.58, 1.0), sizing
    assert sizing["max_loan_by_ltv"] == 6_375_000.00, sizing
    assert sizing["max_loan_by_debt_yield"] == 8_056_500.00, sizing
    assert sizing["binding_constraint"] == "ltv", sizing
    assert sizing["maximum_loan"] == 6_375_000.00, sizing
    print("✓ test_deal_b_oakmont_terrace_full_hand_calculation: PASS")


# ----------------------------------------------------------------------
# Deal C: Distressed Pointe (50 units) -- NEGATIVE NOI edge case
# ----------------------------------------------------------------------

_DEAL_C_TERMS = {
    "loan_amount": 3_000_000.0, "annual_rate_pct": 6.5, "amortization_years": 25,
    "term_years": 5, "interest_only_months": 0,
    "purchase_price": 4_000_000.0, "appraised_value": 3_800_000.0, "unit_count": 50,
}
_DEAL_C_T12 = {
    "gross_potential_rent": 750_000.0, "loss_to_lease": 0.0, "concessions": 20_000.0,
    "bad_debt": 40_000.0, "other_income": 15_000.0,
    "operating_expenses_ex_management": 650_000.0, "unit_count": 50,
}
_DEAL_C_ASSUMPTIONS = {"vacancy_pct": 15.0, "management_fee_pct": 3.0, "replacement_reserves_per_unit": 250.0}


def test_deal_c_distressed_pointe_negative_noi_full_hand_calculation():
    """
    A fictional distressed property: high vacancy, real concessions and
    bad debt, and an elevated expense load (deferred maintenance,
    post-claim insurance) that together push NOI negative -- the
    realistic shape of a deal that genuinely can't support debt, not a
    contrived zero.

    NOI build-up:
      GPR                           750,000.00
      less vacancy 15%               112,500.00
      less loss to lease                   0.00
      less concessions                20,000.00
      less bad debt                   40,000.00
      = effective rental income      577,500.00
      plus other income               15,000.00
      = EGI                           592,500.00
      less opex ex mgmt               650,000.00
      less mgmt fee 3% of EGI          17,775.00
      less reserves 250 x 50 units     12,500.00
      = total opex                    680,275.00
      = NOI                           -87,775.00   <- NEGATIVE

    Debt service, $3,000,000 @ 6.5% / 25yr, no IO:
      annual debt service = 243,074.58

    Ratios (deliberately NOT clamped -- the magnitude is the signal):
      DSCR = -87,775 / 243,074.58                 = -0.3611x
      value basis = min(4,000,000, 3,800,000)      = 3,800,000 (appraised)
      LTV = 3,000,000 / 3,800,000                  = 78.9474%
      debt yield = -87,775 / 3,000,000             = -2.9258%
      breakeven = (680,275 + 243,074.58)
                  / (750,000 + 15,000)              = 120.6993%
      -- a breakeven ABOVE 100% is itself a finding: no occupancy level
      covers this property's costs plus this debt load.

    Sizing -- the actual edge-case behavior under test:
      by DSCR       = 0.00   (floored: negative NOI supports no debt)
      by LTV        = 3,800,000 x 75% = 2,850,000.00  (LTV alone doesn't
                      know the property is unprofitable, which is exactly
                      why a lender needs all three tests, not just one)
      by debt yield = 0.00   (floored, same reasoning as DSCR)
      binding = "dscr" (tie with debt_yield at 0.00; dscr wins by the
                 documented insertion-order tie-break)
      maximum_loan = 0.00

    The requested $3,000,000 is entirely unsupportable -- not "reduced",
    zero.
    """
    result = underwrite(_DEAL_C_TERMS, _DEAL_C_T12, assumptions=_DEAL_C_ASSUMPTIONS)

    build_up = result["noi_build_up"]
    assert build_up["vacancy_amount"] == 112_500.00, build_up
    assert build_up["effective_rental_income"] == 577_500.00, build_up
    assert build_up["effective_gross_income"] == 592_500.00, build_up
    assert build_up["management_fee"] == 17_775.00, build_up
    assert build_up["replacement_reserves"] == 12_500.00, build_up
    assert build_up["total_operating_expenses"] == 680_275.00, build_up
    assert build_up["underwritten_noi"] == -87_775.00, build_up
    assert build_up["underwritten_noi"] < 0, "this deal must be the negative-NOI case"

    debt_service = result["debt_service"]
    assert _close(debt_service["annual_debt_service_amortizing"], 243_074.58, 0.05), debt_service

    ratios = result["ratios"]
    assert _close(ratios["dscr"], -0.3611, 0.0001), ratios
    assert ratios["dscr"] < 0, "a negative DSCR is real information and must not be clamped"
    assert ratios["ltv_basis"] == "appraised_value", ratios
    assert ratios["ltv_pct"] == 78.9474, ratios
    assert _close(ratios["debt_yield_pct"], -2.9258, 0.0001), ratios
    assert ratios["debt_yield_pct"] < 0, "negative debt yield must also not be clamped"
    assert _close(ratios["breakeven_occupancy_pct"], 120.6993, 0.001), ratios
    assert ratios["breakeven_occupancy_pct"] > 100.0, "no occupancy level covers this property's costs"

    sizing = result["sizing"]
    assert sizing["max_loan_by_dscr"] == 0.0, sizing
    assert sizing["max_loan_by_debt_yield"] == 0.0, sizing
    assert sizing["max_loan_by_ltv"] == 2_850_000.00, sizing
    assert sizing["binding_constraint"] == "dscr", sizing
    assert sizing["maximum_loan"] == 0.0, sizing
    print("✓ test_deal_c_distressed_pointe_negative_noi_full_hand_calculation: PASS")


# ----------------------------------------------------------------------
# Cross-deal sanity: three different deals must not silently collide
# ----------------------------------------------------------------------

def test_three_deals_produce_three_distinct_binding_stories():
    """A property-level sanity check: these aren't three copies of the same math with different labels."""
    a = underwrite(_DEAL_A_TERMS, _DEAL_A_T12, assumptions=_DEAL_A_ASSUMPTIONS)
    b = underwrite(_DEAL_B_TERMS, _DEAL_B_T12, assumptions=_DEAL_B_ASSUMPTIONS)
    c = underwrite(_DEAL_C_TERMS, _DEAL_C_T12, assumptions=_DEAL_C_ASSUMPTIONS)

    nois = {a["noi_build_up"]["underwritten_noi"], b["noi_build_up"]["underwritten_noi"],
            c["noi_build_up"]["underwritten_noi"]}
    assert len(nois) == 3, "three distinct deals must produce three distinct NOIs"
    assert c["noi_build_up"]["underwritten_noi"] < 0 < min(
        a["noi_build_up"]["underwritten_noi"], b["noi_build_up"]["underwritten_noi"]
    )
    print("✓ test_three_deals_produce_three_distinct_binding_stories: PASS")


if __name__ == "__main__":
    test_deal_a_sunset_gardens_full_hand_calculation()
    test_deal_b_oakmont_terrace_full_hand_calculation()
    test_deal_c_distressed_pointe_negative_noi_full_hand_calculation()
    test_three_deals_produce_three_distinct_binding_stories()
    print("\nAll three-deal hand-calculation tests passed.")
