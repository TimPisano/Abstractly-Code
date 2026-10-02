"""
Formula tests for app/loan_underwriting.py.

Every expected value below is hand-calculated and the arithmetic is shown
in a comment, so a reviewer can check the test rather than having to
trust it. Where a figure is irrational (anything involving the
amortization factor), the expectation is a hand-derived number compared
with a tolerance, not a value copied back out of the implementation --
copying the implementation's own output would make the test assert only
that the code does what it does.

Deliberate edge coverage, because these are the cases that produce
confidently wrong numbers rather than crashes:
  * interest-only, both full-year and part-year
  * a 0% interest rate (the amortization formula divides by zero there)
  * zero vacancy
  * negative and exactly-zero NOI
  * the management fee double-count guard
  * loss to lease, which is silently omittable and overstates NOI
  * a missing value basis (no appraisal yet)
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.loan_underwriting import (
    annual_payment_factor,
    build_underwritten_noi,
    compute_breakeven_occupancy,
    compute_debt_service,
    compute_ratios,
    compute_value_basis,
    default_assumptions,
    default_constraints,
    max_loan_by_constraint,
    monthly_amortizing_payment,
    monthly_interest_only_payment,
    run_stress_tests,
    underwrite,
)
from app.t12_import import build_t12_financials


def _close(actual, expected, tolerance=0.01):
    return actual is not None and abs(actual - expected) <= tolerance


# ----------------------------------------------------------------------
# Debt service
# ----------------------------------------------------------------------

def test_amortizing_payment_1m_at_6pct_30yr():
    """
    Hand calculation:
      i = 0.06/12 = 0.005 ; n = 360
      1.005^360  = 6.022575
      1.005^-360 = 0.16604189
      1 - 0.16604189 = 0.83395811
      P = 1,000,000 * 0.005 / 0.83395811 = 5,000 / 0.83395811 = 5,995.51
    This is the textbook figure for a $1M 30-year 6% mortgage.
    """
    payment = monthly_amortizing_payment(1_000_000, 6.0, 30)
    assert _close(payment, 5995.51, 0.01), payment
    print("✓ test_amortizing_payment_1m_at_6pct_30yr: PASS")


def test_zero_rate_amortizing_payment_is_principal_divided_evenly():
    """
    A 0% loan is legitimate (seller financing, some affordable
    structures) and the standard formula divides by zero at i=0.
    Hand calculation: 1,200,000 / 360 months = 3,333.33/month,
    and 12 x that = 40,000/yr = 1,200,000 / 30 years exactly.
    """
    payment = monthly_amortizing_payment(1_200_000, 0.0, 30)
    assert _close(payment, 3333.3333, 0.0001), payment

    debt_service = compute_debt_service(1_200_000, 0.0, 30)
    assert _close(debt_service["annual_debt_service_amortizing"], 40_000.00), debt_service
    print("✓ test_zero_rate_amortizing_payment_is_principal_divided_evenly: PASS")


def test_zero_loan_amount_is_a_real_zero_payment_not_none():
    """A $0 loan has a genuinely $0 payment -- that's a real answer, not an uncomputable one."""
    assert monthly_amortizing_payment(0, 6.0, 30) == 0.0
    print("✓ test_zero_loan_amount_is_a_real_zero_payment_not_none: PASS")


def test_non_positive_amortization_is_none_not_zero():
    """No amortization period means no amortizing payment exists. None, never 0.0 -- a 0 here would read as 'free loan'."""
    assert monthly_amortizing_payment(1_000_000, 6.0, 0) is None
    assert monthly_amortizing_payment(1_000_000, 6.0, -5) is None

    debt_service = compute_debt_service(1_000_000, 6.0, 0)
    assert debt_service["annual_debt_service_amortizing"] is None, debt_service
    print("✓ test_non_positive_amortization_is_none_not_zero: PASS")


def test_interest_only_payment_is_balance_times_rate_over_12():
    """Hand calculation: 10,000,000 x 6% / 12 = 50,000/month, 600,000/year."""
    assert _close(monthly_interest_only_payment(10_000_000, 6.0), 50_000.00)
    debt_service = compute_debt_service(10_000_000, 6.0, 30, interest_only_months=0)
    assert _close(debt_service["annual_debt_service_interest_only"], 600_000.00), debt_service
    print("✓ test_interest_only_payment_is_balance_times_rate_over_12: PASS")


def test_full_year_interest_only_makes_year_one_equal_the_io_figure():
    """
    24 months IO: all 12 months of year one are interest-only, so year
    one equals the IO annual figure (600,000), while the amortizing
    figure stays at the post-IO payment.
    Hand calculation: 10,000,000 at 6%/30yr amortizing = 59,955.05/mo
    (5,995.51 x 10), so 719,460.62/yr.
    """
    debt_service = compute_debt_service(10_000_000, 6.0, 30, interest_only_months=24)
    assert _close(debt_service["annual_debt_service_year_one"], 600_000.00), debt_service
    assert _close(debt_service["annual_debt_service_interest_only"], 600_000.00), debt_service
    assert _close(debt_service["annual_debt_service_amortizing"], 719_460.62, 0.05), debt_service
    assert debt_service["io_months_in_year_one"] == 12
    print("✓ test_full_year_interest_only_makes_year_one_equal_the_io_figure: PASS")


def test_partial_year_interest_only_blends_both_payments():
    """
    6 months IO, then amortizing for the rest of year one.
    Hand calculation:
      6 x 50,000.00    = 300,000.00
      6 x 59,955.05    = 359,730.31
      year one total   = 659,730.31
    """
    debt_service = compute_debt_service(10_000_000, 6.0, 30, interest_only_months=6)
    assert _close(debt_service["annual_debt_service_year_one"], 659_730.31, 0.10), debt_service
    assert debt_service["io_months_in_year_one"] == 6
    print("✓ test_partial_year_interest_only_blends_both_payments: PASS")


def test_no_interest_only_makes_year_one_equal_the_amortizing_figure():
    debt_service = compute_debt_service(10_000_000, 6.0, 30, interest_only_months=0)
    assert debt_service["annual_debt_service_year_one"] == debt_service["annual_debt_service_amortizing"]
    print("✓ test_no_interest_only_makes_year_one_equal_the_amortizing_figure: PASS")


def test_negative_interest_only_months_is_treated_as_none():
    """A negative IO period is meaningless input, clamped to 0 rather than raising or producing a negative blend."""
    debt_service = compute_debt_service(10_000_000, 6.0, 30, interest_only_months=-6)
    assert debt_service["interest_only_months"] == 0
    assert debt_service["annual_debt_service_year_one"] == debt_service["annual_debt_service_amortizing"]
    print("✓ test_negative_interest_only_months_is_treated_as_none: PASS")


# ----------------------------------------------------------------------
# NOI build-up
# ----------------------------------------------------------------------

def test_noi_build_up_with_zero_vacancy_and_no_other_deductions():
    """
    Hand calculation (zero vacancy edge case):
      GPR                       1,000,000
      less vacancy at 0%                0
      = effective rental income 1,000,000
      + other income                    0
      = EGI                     1,000,000
      less opex (ex mgmt)         300,000
      less mgmt fee 0%                  0
      less reserves 0/unit              0
      = NOI                       700,000
    """
    result = build_underwritten_noi(
        gross_potential_rent=1_000_000,
        operating_expenses_ex_management=300_000,
        unit_count=100,
        vacancy_pct=0.0,
        management_fee_pct=0.0,
        replacement_reserves_per_unit=0.0,
    )
    assert result["vacancy_amount"] == 0.0, result
    assert result["effective_gross_income"] == 1_000_000.0, result
    assert result["underwritten_noi"] == 700_000.0, result
    print("✓ test_noi_build_up_with_zero_vacancy_and_no_other_deductions: PASS")


def test_noi_build_up_applies_all_three_assumptions():
    """
    Hand calculation:
      GPR                           1,000,000
      less vacancy 5%                  50,000  -> 950,000
      + other income                        0
      = EGI                           950,000
      less opex (ex mgmt)             300,000
      less mgmt fee 3% of 950,000      28,500
      less reserves 250 x 100 units    25,000
      = total opex                    353,500
      = NOI                           596,500
    """
    result = build_underwritten_noi(
        gross_potential_rent=1_000_000,
        operating_expenses_ex_management=300_000,
        unit_count=100,
        vacancy_pct=5.0,
        management_fee_pct=3.0,
        replacement_reserves_per_unit=250.0,
    )
    assert result["vacancy_amount"] == 50_000.0, result
    assert result["management_fee"] == 28_500.0, result
    assert result["replacement_reserves"] == 25_000.0, result
    assert result["total_operating_expenses"] == 353_500.0, result
    assert result["underwritten_noi"] == 596_500.0, result
    print("✓ test_noi_build_up_applies_all_three_assumptions: PASS")


def test_loss_to_lease_is_deducted():
    """
    Loss to lease is silently omittable and overstates NOI when missed.
    Hand calculation: GPR 1,000,000 - 0 vacancy - 25,000 loss to lease
    = 975,000 effective rental income, so NOI is 25,000 lower than the
    same build-up without it.
    """
    with_ltl = build_underwritten_noi(
        gross_potential_rent=1_000_000, loss_to_lease=25_000,
        vacancy_pct=0.0, management_fee_pct=0.0, replacement_reserves_per_unit=0.0,
    )
    without_ltl = build_underwritten_noi(
        gross_potential_rent=1_000_000, loss_to_lease=0,
        vacancy_pct=0.0, management_fee_pct=0.0, replacement_reserves_per_unit=0.0,
    )
    assert with_ltl["effective_rental_income"] == 975_000.0, with_ltl
    assert without_ltl["underwritten_noi"] - with_ltl["underwritten_noi"] == 25_000.0
    print("✓ test_loss_to_lease_is_deducted: PASS")


def test_vacancy_is_not_applied_to_other_income():
    """
    Other income is already an actual collected figure on the T-12;
    applying a vacancy factor to it would double-count a loss.
    Hand calculation: GPR 1,000,000 less 10% vacancy = 900,000, plus
    other income 50,000 untouched = EGI 950,000.
    """
    result = build_underwritten_noi(
        gross_potential_rent=1_000_000, other_income=50_000,
        vacancy_pct=10.0, management_fee_pct=0.0, replacement_reserves_per_unit=0.0,
    )
    assert result["effective_rental_income"] == 900_000.0, result
    assert result["effective_gross_income"] == 950_000.0, result
    print("✓ test_vacancy_is_not_applied_to_other_income: PASS")


def test_management_fee_is_computed_on_egi_not_gpr():
    """
    Hand calculation: GPR 1,000,000 less 20% vacancy = EGI 800,000.
    3% of EGI = 24,000. (3% of GPR would be 30,000 -- the wrong answer,
    and the one you get by applying the fee to the wrong base.)
    """
    result = build_underwritten_noi(
        gross_potential_rent=1_000_000, vacancy_pct=20.0,
        management_fee_pct=3.0, replacement_reserves_per_unit=0.0,
    )
    assert result["effective_gross_income"] == 800_000.0, result
    assert result["management_fee"] == 24_000.0, result
    print("✓ test_management_fee_is_computed_on_egi_not_gpr: PASS")


def test_t12_management_fee_is_stripped_so_it_cannot_be_double_counted():
    """
    The double-count guard, tested at the t12_import boundary where it
    lives. A T-12's expense total INCLUDES the fee actually paid; the
    engine then applies its own fee assumption. Without stripping, the
    property pays a management fee twice.

    Hand calculation using the Maple Ridge demo figures:
      total operating expenses   766,762.83
      less management fee         59,899.54
      = opex excluding mgmt      706,863.29
    """
    line_items = [
        {"label": "Management Fee (3% of Total Income)", "normalized_label": "management fee 3 of total income",
         "bucket": "management_fee", "annual_amount": 59_899.54,
         "source": {"row": 35, "file": "t12.xlsx", "quote": "Management Fee (3% of Total Income)"}},
        {"label": "TOTAL OPERATING EXPENSES", "normalized_label": "total operating expenses",
         "bucket": "total_operating_expenses", "annual_amount": 766_762.83,
         "source": {"row": 36, "file": "t12.xlsx", "quote": "TOTAL OPERATING EXPENSES"}},
        {"label": "Gross Potential Rent", "normalized_label": "gross potential rent",
         "bucket": "gross_potential_rent", "annual_amount": 2_177_280.0,
         "source": {"row": 7, "file": "t12.xlsx", "quote": "Gross Potential Rent"}},
    ]
    financials = build_t12_financials(line_items, unit_count=120)
    assert financials["t12_inputs"]["operating_expenses_ex_management"] == 706_863.29, financials
    assert financials["management_fee_removed"] == 59_899.54, financials
    assert financials["warnings"] == [], financials
    print("✓ test_t12_management_fee_is_stripped_so_it_cannot_be_double_counted: PASS")


def test_missing_t12_management_fee_warns_rather_than_guessing():
    """With no fee line found, the total passes through unchanged AND a warning says so -- never a guessed fee."""
    line_items = [
        {"label": "Gross Potential Rent", "normalized_label": "gross potential rent",
         "bucket": "gross_potential_rent", "annual_amount": 1_000_000.0,
         "source": {"row": 5, "file": "t12.csv", "quote": "Gross Potential Rent"}},
        {"label": "Total Operating Expenses", "normalized_label": "total operating expenses",
         "bucket": "total_operating_expenses", "annual_amount": 400_000.0,
         "source": {"row": 20, "file": "t12.csv", "quote": "Total Operating Expenses"}},
    ]
    financials = build_t12_financials(line_items)
    assert financials["t12_inputs"]["operating_expenses_ex_management"] == 400_000.0
    assert financials["management_fee_removed"] is None
    assert any("management fee" in w.lower() for w in financials["warnings"]), financials["warnings"]
    print("✓ test_missing_t12_management_fee_warns_rather_than_guessing: PASS")


def test_t12_deductions_are_normalized_to_positive_magnitudes():
    """
    A deduction may arrive negative (xlsx float) or positive (CSV with
    parentheses stripped). Both must behave identically, or a CSV and an
    XLSX of the same statement would produce two different NOIs.
    """
    def _items(sign):
        return [
            {"label": "Gross Potential Rent", "normalized_label": "gross potential rent",
             "bucket": "gross_potential_rent", "annual_amount": 1_000_000.0,
             "source": {"row": 1, "file": "f", "quote": "q"}},
            {"label": "Vacancy Loss", "normalized_label": "vacancy loss",
             "bucket": "vacancy_loss", "annual_amount": sign * 50_000.0,
             "source": {"row": 2, "file": "f", "quote": "q"}},
            {"label": "Concessions", "normalized_label": "concessions",
             "bucket": "concessions", "annual_amount": sign * 10_000.0,
             "source": {"row": 3, "file": "f", "quote": "q"}},
            {"label": "Total Operating Expenses", "normalized_label": "total operating expenses",
             "bucket": "total_operating_expenses", "annual_amount": sign * 400_000.0,
             "source": {"row": 4, "file": "f", "quote": "q"}},
        ]
    negative = build_t12_financials(_items(-1))["t12_inputs"]
    positive = build_t12_financials(_items(1))["t12_inputs"]
    assert negative["concessions"] == positive["concessions"] == 10_000.0
    assert negative["operating_expenses_ex_management"] == positive["operating_expenses_ex_management"] == 400_000.0
    print("✓ test_t12_deductions_are_normalized_to_positive_magnitudes: PASS")


def test_negative_noi_is_reported_as_negative_not_clamped():
    """
    Hand calculation:
      GPR                     100,000
      less vacancy 5%           5,000  -> 95,000
      = EGI                    95,000
      less opex (ex mgmt)     200,000
      less mgmt fee 3%          2,850
      = total opex            202,850
      = NOI                  -107,850
    """
    result = build_underwritten_noi(
        gross_potential_rent=100_000, operating_expenses_ex_management=200_000,
        unit_count=0, vacancy_pct=5.0, management_fee_pct=3.0,
        replacement_reserves_per_unit=0.0,
    )
    assert result["underwritten_noi"] == -107_850.0, result
    print("✓ test_negative_noi_is_reported_as_negative_not_clamped: PASS")


# ----------------------------------------------------------------------
# Value basis and ratios
# ----------------------------------------------------------------------

def test_value_basis_takes_the_lesser_of_price_and_appraisal():
    """Buyer overpaying (price 11M, appraisal 10M) -> basis is the appraisal. Appraisal above price -> basis is the price."""
    basis = compute_value_basis(purchase_price=11_000_000, appraised_value=10_000_000)
    assert basis["value_basis"] == 10_000_000.0, basis
    assert basis["value_basis_source"] == "appraised_value", basis

    basis = compute_value_basis(purchase_price=10_000_000, appraised_value=11_000_000)
    assert basis["value_basis"] == 10_000_000.0, basis
    assert basis["value_basis_source"] == "purchase_price", basis
    print("✓ test_value_basis_takes_the_lesser_of_price_and_appraisal: PASS")


def test_value_basis_with_only_one_figure_uses_that_one():
    assert compute_value_basis(None, 9_000_000)["value_basis_source"] == "appraised_value"
    assert compute_value_basis(9_000_000, None)["value_basis_source"] == "purchase_price"
    print("✓ test_value_basis_with_only_one_figure_uses_that_one: PASS")


def test_value_basis_with_neither_figure_is_none_not_zero():
    """No appraisal yet and no price: LTV is genuinely unknown, so None -- a 0 basis would make LTV infinite or crash."""
    basis = compute_value_basis(None, None)
    assert basis["value_basis"] is None, basis
    assert basis["value_basis_source"] is None, basis
    print("✓ test_value_basis_with_neither_figure_is_none_not_zero: PASS")


def test_dscr_ltv_and_debt_yield_hand_calculated():
    """
    Hand calculation:
      DSCR             = 1,250,000 NOI / 1,000,000 ADS = 1.25x
      LTV              = 7,500,000 / 10,000,000 basis  = 75.00%
      LTV vs appraised = 7,500,000 / 11,000,000        = 68.1818%
      debt yield       = 1,250,000 / 7,500,000         = 16.6667%
    """
    debt_service = {
        "annual_debt_service_amortizing": 1_000_000.0,
        "annual_debt_service_year_one": 1_000_000.0,
        "annual_debt_service_interest_only": 800_000.0,
    }
    basis = compute_value_basis(purchase_price=10_000_000, appraised_value=11_000_000)
    ratios = compute_ratios(
        noi=1_250_000, loan_amount=7_500_000,
        debt_service=debt_service, value_basis_info=basis,
    )
    assert ratios["dscr"] == 1.25, ratios
    assert ratios["ltv_pct"] == 75.0, ratios
    assert ratios["ltv_basis"] == "purchase_price", ratios
    assert _close(ratios["ltv_vs_appraised_value_pct"], 68.1818, 0.0001), ratios
    assert _close(ratios["debt_yield_pct"], 16.6667, 0.0001), ratios
    print("✓ test_dscr_ltv_and_debt_yield_hand_calculated: PASS")


def test_dscr_is_reported_on_all_three_debt_service_conventions():
    """
    An IO deal has three different DSCRs and the headline must be the
    amortizing (most conservative) one.
    Hand calculation: NOI 1,000,000 / 800,000 amortizing = 1.25x;
    NOI 1,000,000 / 600,000 IO = 1.6667x.
    """
    debt_service = {
        "annual_debt_service_amortizing": 800_000.0,
        "annual_debt_service_year_one": 600_000.0,
        "annual_debt_service_interest_only": 600_000.0,
    }
    ratios = compute_ratios(
        noi=1_000_000, loan_amount=10_000_000,
        debt_service=debt_service, value_basis_info=compute_value_basis(12_000_000, None),
    )
    assert ratios["dscr"] == 1.25, ratios
    assert _close(ratios["dscr_interest_only"], 1.6667, 0.0001), ratios
    assert _close(ratios["dscr_year_one"], 1.6667, 0.0001), ratios
    print("✓ test_dscr_is_reported_on_all_three_debt_service_conventions: PASS")


def test_negative_noi_gives_negative_dscr_and_debt_yield():
    """The magnitude of a shortfall is information -- these are deliberately not clamped at zero."""
    debt_service = {"annual_debt_service_amortizing": 500_000.0,
                    "annual_debt_service_year_one": 500_000.0,
                    "annual_debt_service_interest_only": 400_000.0}
    ratios = compute_ratios(
        noi=-100_000, loan_amount=5_000_000,
        debt_service=debt_service, value_basis_info=compute_value_basis(8_000_000, None),
    )
    assert ratios["dscr"] == -0.2, ratios            # -100,000 / 500,000
    assert ratios["debt_yield_pct"] == -2.0, ratios   # -100,000 / 5,000,000
    print("✓ test_negative_noi_gives_negative_dscr_and_debt_yield: PASS")


def test_breakeven_occupancy_hand_calculated():
    """
    Hand calculation:
      (operating expenses 500,000 + debt service 1,000,000) = 1,500,000
      (GPR 2,000,000 + other income 0)                      = 2,000,000
      breakeven = 1,500,000 / 2,000,000 = 75.00%
    """
    breakeven = compute_breakeven_occupancy(
        total_operating_expenses=500_000, annual_debt_service=1_000_000,
        gross_potential_rent=2_000_000, other_income=0,
    )
    assert breakeven == 75.0, breakeven
    print("✓ test_breakeven_occupancy_hand_calculated: PASS")


def test_breakeven_occupancy_includes_other_income_in_the_denominator():
    """
    Hand calculation:
      (400,000 + 1,100,000) = 1,500,000
      (2,000,000 + 500,000) = 2,500,000
      breakeven = 60.00%
    """
    breakeven = compute_breakeven_occupancy(400_000, 1_100_000, 2_000_000, 500_000)
    assert breakeven == 60.0, breakeven
    print("✓ test_breakeven_occupancy_includes_other_income_in_the_denominator: PASS")


def test_breakeven_occupancy_is_none_with_no_potential_income():
    """Zero denominator -- None, not a meaningless 0%."""
    assert compute_breakeven_occupancy(100_000, 200_000, 0, 0) is None
    assert compute_breakeven_occupancy(100_000, None, 2_000_000, 0) is None
    print("✓ test_breakeven_occupancy_is_none_with_no_potential_income: PASS")


# ----------------------------------------------------------------------
# Maximum loan by constraint
# ----------------------------------------------------------------------

def test_annual_payment_factor_hand_calculated():
    """
    Hand calculation at 6% / 30yr:
      12 x 0.005 / 0.83395811 = 0.06 / 0.83395811 = 0.0719461
    i.e. just over 7.19c of annual debt service per dollar of loan.
    Zero-rate: 12/360 = 0.0333333.
    """
    assert _close(annual_payment_factor(6.0, 30), 0.0719461, 0.0000001)
    assert _close(annual_payment_factor(0.0, 30), 0.0333333, 0.0000001)
    assert annual_payment_factor(6.0, 0) is None
    print("✓ test_annual_payment_factor_hand_calculated: PASS")


def test_max_loan_by_dscr_hand_calculated():
    """
    Hand calculation:
      supportable ADS = NOI 1,000,000 / 1.25 target = 800,000
      annuity factor  = 0.83395811 / 0.06 = 13.8993018
      max loan        = 800,000 x 13.8993018 = 11,119,441.46
    """
    sizing = max_loan_by_constraint(
        noi=1_000_000, value_basis=None, annual_rate_pct=6.0, amortization_years=30,
        constraints={"target_dscr": 1.25, "max_ltv_pct": 75.0, "min_debt_yield_pct": 8.0},
    )
    assert _close(sizing["max_loan_by_dscr"], 11_119_441.46, 2.0), sizing
    print("✓ test_max_loan_by_dscr_hand_calculated: PASS")


def test_max_loan_by_ltv_and_debt_yield_hand_calculated():
    """
    Hand calculation:
      by LTV        = 10,000,000 basis x 75%  = 7,500,000
      by debt yield = 800,000 NOI / 8%        = 10,000,000
    """
    sizing = max_loan_by_constraint(
        noi=800_000, value_basis=10_000_000, annual_rate_pct=6.0, amortization_years=30,
    )
    assert sizing["max_loan_by_ltv"] == 7_500_000.0, sizing
    assert sizing["max_loan_by_debt_yield"] == 10_000_000.0, sizing
    print("✓ test_max_loan_by_ltv_and_debt_yield_hand_calculated: PASS")


def test_binding_constraint_is_the_smallest_and_is_named():
    """
    Hand calculation with NOI 1,000,000, basis 10,000,000, 6%/30yr:
      by DSCR       = 11,119,441.46
      by LTV        =  7,500,000.00   <- smallest, so this binds
      by debt yield = 12,500,000.00
    """
    sizing = max_loan_by_constraint(
        noi=1_000_000, value_basis=10_000_000, annual_rate_pct=6.0, amortization_years=30,
    )
    assert sizing["binding_constraint"] == "ltv", sizing
    assert sizing["binding_constraint_label"] == "Maximum LTV", sizing
    assert sizing["maximum_loan"] == 7_500_000.0, sizing
    print("✓ test_binding_constraint_is_the_smallest_and_is_named: PASS")


def test_dscr_can_be_the_binding_constraint():
    """
    A low-NOI deal: NOI 500,000, basis 20,000,000.
      by DSCR       = (500,000/1.25) x 13.8993018 = 5,559,720.73  <- binds
      by LTV        = 15,000,000
      by debt yield =  6,250,000
    """
    sizing = max_loan_by_constraint(
        noi=500_000, value_basis=20_000_000, annual_rate_pct=6.0, amortization_years=30,
    )
    assert sizing["binding_constraint"] == "dscr", sizing
    assert _close(sizing["max_loan_by_dscr"], 5_559_720.73, 2.0), sizing
    print("✓ test_dscr_can_be_the_binding_constraint: PASS")


def test_debt_yield_can_be_the_binding_constraint():
    """
    Hand calculation with NOI 800,000, basis 20,000,000, 4%/30yr:
      by debt yield = 800,000 / 8% = 10,000,000  <- smallest
      by LTV        = 15,000,000
      by DSCR at 4%/30yr is larger still (a lower rate supports more debt).
    """
    sizing = max_loan_by_constraint(
        noi=800_000, value_basis=20_000_000, annual_rate_pct=4.0, amortization_years=30,
    )
    assert sizing["binding_constraint"] == "debt_yield", sizing
    assert sizing["maximum_loan"] == 10_000_000.0, sizing
    print("✓ test_debt_yield_can_be_the_binding_constraint: PASS")


def test_non_positive_noi_floors_dscr_and_debt_yield_max_loan_at_zero():
    """
    A property with no net income supports no debt. Without the floor,
    both formulas return NEGATIVE loan amounts, which would then sort as
    'smallest' and propagate into a memo as the maximum loan.
    """
    for noi in (-250_000, 0):
        sizing = max_loan_by_constraint(
            noi=noi, value_basis=10_000_000, annual_rate_pct=6.0, amortization_years=30,
        )
        assert sizing["max_loan_by_dscr"] == 0.0, (noi, sizing)
        assert sizing["max_loan_by_debt_yield"] == 0.0, (noi, sizing)
        assert sizing["maximum_loan"] == 0.0, (noi, sizing)
        assert sizing["binding_constraint"] in ("dscr", "debt_yield"), sizing
    print("✓ test_non_positive_noi_floors_dscr_and_debt_yield_max_loan_at_zero: PASS")


def test_missing_value_basis_leaves_ltv_constraint_none_not_zero():
    """
    No appraisal and no price: the LTV constraint is unknowable, so it's
    None and the other two decide. A 0 here would wrongly bind at zero
    and report 'no loan supportable'.
    """
    sizing = max_loan_by_constraint(
        noi=1_000_000, value_basis=None, annual_rate_pct=6.0, amortization_years=30,
    )
    assert sizing["max_loan_by_ltv"] is None, sizing
    assert sizing["binding_constraint"] in ("dscr", "debt_yield"), sizing
    print("✓ test_missing_value_basis_leaves_ltv_constraint_none_not_zero: PASS")


def test_binding_constraint_tie_is_deterministic():
    """
    When two constraints bind at the same dollar amount either label is
    accurate, but the choice must be reproducible run to run.

    Construction, and the DSCR constraint has to be deliberately pushed
    OUT of the way for the tie to be the actual minimum:
      debt yield at 8% on NOI 600,000     = 7,500,000
      LTV at 75% of basis 10,000,000      = 7,500,000   <- tied minimum
      DSCR at a 1.00x target and 4%/30yr:
        annuity factor = 0.69822 / 0.04   = 17.4555
        (600,000 / 1.00) x 17.4555        = 10,473,300   <- well above
    A 1.25x target at 6% would put DSCR at 6,671,664, below both, so the
    tie would never be reached -- that was the first version of this test
    and it was simply a badly-built fixture.
    """
    kwargs = dict(
        noi=600_000, value_basis=10_000_000, annual_rate_pct=4.0, amortization_years=30,
        constraints={"target_dscr": 1.00, "max_ltv_pct": 75.0, "min_debt_yield_pct": 8.0},
    )
    sizing = max_loan_by_constraint(**kwargs)
    assert sizing["max_loan_by_ltv"] == sizing["max_loan_by_debt_yield"] == 7_500_000.0, sizing
    assert sizing["max_loan_by_dscr"] > 7_500_000.0, sizing
    assert sizing["binding_constraint"] == "ltv", sizing
    # Reproducible: same inputs, same label, every time.
    assert max_loan_by_constraint(**kwargs)["binding_constraint"] == "ltv"
    print("✓ test_binding_constraint_tie_is_deterministic: PASS")


def test_constraints_are_configurable():
    """
    Hand calculation with a tighter box: 1.40x DSCR, 65% LTV, 10% yield.
      by LTV        = 10,000,000 x 65% = 6,500,000
      by debt yield = 1,000,000 / 10%  = 10,000,000
    """
    sizing = max_loan_by_constraint(
        noi=1_000_000, value_basis=10_000_000, annual_rate_pct=6.0, amortization_years=30,
        constraints={"target_dscr": 1.40, "max_ltv_pct": 65.0, "min_debt_yield_pct": 10.0},
    )
    assert sizing["max_loan_by_ltv"] == 6_500_000.0, sizing
    assert sizing["max_loan_by_debt_yield"] == 10_000_000.0, sizing
    assert sizing["constraints_used"]["target_dscr"] == 1.40
    print("✓ test_constraints_are_configurable: PASS")


# ----------------------------------------------------------------------
# Stress tests
# ----------------------------------------------------------------------

_STRESS_T12 = {
    "gross_potential_rent": 2_000_000.0,
    "loss_to_lease": 0.0,
    "concessions": 0.0,
    "bad_debt": 0.0,
    "other_income": 0.0,
    "operating_expenses_ex_management": 600_000.0,
    "unit_count": 100,
}
_STRESS_TERMS = {
    "loan_amount": 10_000_000.0,
    "annual_rate_pct": 6.0,
    "amortization_years": 30,
    "term_years": 10,
    "interest_only_months": 0,
    "purchase_price": 15_000_000.0,
    "appraised_value": None,
}


def test_all_five_stress_cases_are_present_in_order():
    cases = run_stress_tests(_STRESS_T12, _STRESS_TERMS, default_assumptions())
    assert [c["key"] for c in cases] == [
        "rate_plus_100bp", "rate_plus_200bp",
        "occupancy_down_5pt", "occupancy_down_10pt", "noi_down_10pct",
    ], [c["key"] for c in cases]
    print("✓ test_all_five_stress_cases_are_present_in_order: PASS")


def test_rate_stresses_add_exactly_100_and_200_basis_points():
    """100bp = 1.00 percentage point, so 6.00% -> 7.00% and 8.00%."""
    cases = {c["key"]: c for c in run_stress_tests(_STRESS_T12, _STRESS_TERMS, default_assumptions())}
    assert cases["rate_plus_100bp"]["stressed_annual_rate_pct"] == 7.0, cases["rate_plus_100bp"]
    assert cases["rate_plus_200bp"]["stressed_annual_rate_pct"] == 8.0, cases["rate_plus_200bp"]
    # A higher rate means higher debt service and therefore lower DSCR.
    assert cases["rate_plus_200bp"]["dscr"] < cases["rate_plus_100bp"]["dscr"]
    print("✓ test_rate_stresses_add_exactly_100_and_200_basis_points: PASS")


def test_rate_stress_does_not_change_noi():
    """A rate change affects debt service only -- NOI is a property-level figure and must be untouched."""
    assumptions = {"vacancy_pct": 5.0, "management_fee_pct": 3.0, "replacement_reserves_per_unit": 250.0}
    base = build_underwritten_noi(
        gross_potential_rent=2_000_000, operating_expenses_ex_management=600_000,
        unit_count=100, **assumptions,
    )["underwritten_noi"]
    cases = {c["key"]: c for c in run_stress_tests(_STRESS_T12, _STRESS_TERMS, assumptions)}
    assert cases["rate_plus_100bp"]["underwritten_noi"] == base
    assert cases["rate_plus_200bp"]["underwritten_noi"] == base
    print("✓ test_rate_stress_does_not_change_noi: PASS")


def test_occupancy_stress_adds_vacancy_points_on_top_of_the_assumption():
    """
    "Occupancy down 5 points" against a 5% vacancy assumption means 10%
    vacancy, not 5%.
    Hand calculation on GPR 2,000,000: vacancy rises from 100,000 (5%) to
    200,000 (10%), so EGI falls by 100,000. The management fee is 3% of
    EGI, so it falls by 3,000, and NOI falls by 100,000 - 3,000 = 97,000.
    At -10 points, vacancy is 15% and NOI falls by 194,000.
    """
    assumptions = {"vacancy_pct": 5.0, "management_fee_pct": 3.0, "replacement_reserves_per_unit": 250.0}
    cases = {c["key"]: c for c in run_stress_tests(_STRESS_T12, _STRESS_TERMS, assumptions)}
    base = build_underwritten_noi(
        gross_potential_rent=2_000_000, operating_expenses_ex_management=600_000,
        unit_count=100, **assumptions,
    )["underwritten_noi"]

    assert cases["occupancy_down_5pt"]["stressed_vacancy_pct"] == 10.0, cases["occupancy_down_5pt"]
    assert cases["occupancy_down_10pt"]["stressed_vacancy_pct"] == 15.0, cases["occupancy_down_10pt"]
    assert _close(base - cases["occupancy_down_5pt"]["underwritten_noi"], 97_000.00), cases["occupancy_down_5pt"]
    assert _close(base - cases["occupancy_down_10pt"]["underwritten_noi"], 194_000.00), cases["occupancy_down_10pt"]
    print("✓ test_occupancy_stress_adds_vacancy_points_on_top_of_the_assumption: PASS")


def test_noi_stress_scales_noi_by_exactly_ten_percent():
    assumptions = default_assumptions()
    base = build_underwritten_noi(
        gross_potential_rent=2_000_000, operating_expenses_ex_management=600_000,
        unit_count=100, **assumptions,
    )["underwritten_noi"]
    cases = {c["key"]: c for c in run_stress_tests(_STRESS_T12, _STRESS_TERMS, assumptions)}
    assert _close(cases["noi_down_10pct"]["underwritten_noi"], round(base * 0.90, 2)), cases["noi_down_10pct"]
    print("✓ test_noi_stress_scales_noi_by_exactly_ten_percent: PASS")


def test_stress_cases_recompute_every_ratio_not_just_dscr():
    """A stress that changes NOI must move debt yield and breakeven too, or the table is misleading."""
    cases = {c["key"]: c for c in run_stress_tests(_STRESS_T12, _STRESS_TERMS, default_assumptions())}
    stressed = cases["occupancy_down_10pt"]
    for key in ("dscr", "debt_yield_pct", "breakeven_occupancy_pct", "maximum_loan", "binding_constraint"):
        assert key in stressed, (key, stressed)
    assert stressed["debt_yield_pct"] is not None
    assert stressed["breakeven_occupancy_pct"] is not None
    print("✓ test_stress_cases_recompute_every_ratio_not_just_dscr: PASS")


# ----------------------------------------------------------------------
# Top-level underwrite()
# ----------------------------------------------------------------------

def test_underwrite_returns_the_assumptions_it_actually_used():
    """A stored result must never disagree with the inputs that produced it."""
    result = underwrite(_STRESS_TERMS, _STRESS_T12, assumptions={"vacancy_pct": 7.5})
    assert result["assumptions_used"]["vacancy_pct"] == 7.5
    assert result["assumptions_used"]["management_fee_pct"] == default_assumptions()["management_fee_pct"]
    assert result["constraints_used"]["target_dscr"] == default_constraints()["target_dscr"]
    assert result["noi_build_up"]["vacancy_pct"] == 7.5
    print("✓ test_underwrite_returns_the_assumptions_it_actually_used: PASS")


def test_underwrite_is_internally_consistent():
    """
    The headline DSCR must equal NOI / the amortizing debt service that
    the same call reported -- i.e. the ratios and the debt service in one
    result can't be computed from different inputs.
    """
    result = underwrite(_STRESS_TERMS, _STRESS_T12)
    noi = result["noi_build_up"]["underwritten_noi"]
    ads = result["debt_service"]["annual_debt_service_amortizing"]
    assert _close(result["ratios"]["dscr"], round(noi / ads, 4), 0.0001), result["ratios"]
    print("✓ test_underwrite_is_internally_consistent: PASS")


def test_underwrite_carries_source_citations_through():
    sources = {"gross_potential_rent": {"row": 7, "file": "t12.xlsx", "quote": "Gross Potential Rent"}}
    result = underwrite(_STRESS_TERMS, _STRESS_T12, sources=sources)
    assert result["sources"]["gross_potential_rent"]["row"] == 7
    print("✓ test_underwrite_carries_source_citations_through: PASS")


def test_underwrite_with_zero_rate_does_not_crash():
    """The 0% path has to survive the whole pipeline, not just the payment function."""
    terms = {**_STRESS_TERMS, "annual_rate_pct": 0.0}
    result = underwrite(terms, _STRESS_T12)
    assert result["debt_service"]["annual_debt_service_amortizing"] is not None
    assert result["ratios"]["dscr"] is not None
    assert result["sizing"]["maximum_loan"] is not None
    print("✓ test_underwrite_with_zero_rate_does_not_crash: PASS")


def test_underwrite_with_negative_noi_produces_a_coherent_result():
    """End-to-end negative-NOI case: negative ratios reported, zero loan supportable, nothing crashes."""
    broke = {**_STRESS_T12, "operating_expenses_ex_management": 2_500_000.0}
    result = underwrite(_STRESS_TERMS, broke)
    assert result["noi_build_up"]["underwritten_noi"] < 0
    assert result["ratios"]["dscr"] < 0
    assert result["sizing"]["maximum_loan"] == 0.0, result["sizing"]
    assert len(result["stress_tests"]) == 5
    print("✓ test_underwrite_with_negative_noi_produces_a_coherent_result: PASS")


if __name__ == "__main__":
    test_amortizing_payment_1m_at_6pct_30yr()
    test_zero_rate_amortizing_payment_is_principal_divided_evenly()
    test_zero_loan_amount_is_a_real_zero_payment_not_none()
    test_non_positive_amortization_is_none_not_zero()
    test_interest_only_payment_is_balance_times_rate_over_12()
    test_full_year_interest_only_makes_year_one_equal_the_io_figure()
    test_partial_year_interest_only_blends_both_payments()
    test_no_interest_only_makes_year_one_equal_the_amortizing_figure()
    test_negative_interest_only_months_is_treated_as_none()

    test_noi_build_up_with_zero_vacancy_and_no_other_deductions()
    test_noi_build_up_applies_all_three_assumptions()
    test_loss_to_lease_is_deducted()
    test_vacancy_is_not_applied_to_other_income()
    test_management_fee_is_computed_on_egi_not_gpr()
    test_t12_management_fee_is_stripped_so_it_cannot_be_double_counted()
    test_missing_t12_management_fee_warns_rather_than_guessing()
    test_t12_deductions_are_normalized_to_positive_magnitudes()
    test_negative_noi_is_reported_as_negative_not_clamped()

    test_value_basis_takes_the_lesser_of_price_and_appraisal()
    test_value_basis_with_only_one_figure_uses_that_one()
    test_value_basis_with_neither_figure_is_none_not_zero()
    test_dscr_ltv_and_debt_yield_hand_calculated()
    test_dscr_is_reported_on_all_three_debt_service_conventions()
    test_negative_noi_gives_negative_dscr_and_debt_yield()
    test_breakeven_occupancy_hand_calculated()
    test_breakeven_occupancy_includes_other_income_in_the_denominator()
    test_breakeven_occupancy_is_none_with_no_potential_income()

    test_annual_payment_factor_hand_calculated()
    test_max_loan_by_dscr_hand_calculated()
    test_max_loan_by_ltv_and_debt_yield_hand_calculated()
    test_binding_constraint_is_the_smallest_and_is_named()
    test_dscr_can_be_the_binding_constraint()
    test_debt_yield_can_be_the_binding_constraint()
    test_non_positive_noi_floors_dscr_and_debt_yield_max_loan_at_zero()
    test_missing_value_basis_leaves_ltv_constraint_none_not_zero()
    test_binding_constraint_tie_is_deterministic()
    test_constraints_are_configurable()

    test_all_five_stress_cases_are_present_in_order()
    test_rate_stresses_add_exactly_100_and_200_basis_points()
    test_rate_stress_does_not_change_noi()
    test_occupancy_stress_adds_vacancy_points_on_top_of_the_assumption()
    test_noi_stress_scales_noi_by_exactly_ten_percent()
    test_stress_cases_recompute_every_ratio_not_just_dscr()

    test_underwrite_returns_the_assumptions_it_actually_used()
    test_underwrite_is_internally_consistent()
    test_underwrite_carries_source_citations_through()
    test_underwrite_with_zero_rate_does_not_crash()
    test_underwrite_with_negative_noi_produces_a_coherent_result()

    print("\nAll loan underwriting formula tests passed.")
