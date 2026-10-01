"""
Loan underwriting engine for multifamily lenders: underwritten NOI,
debt service, the four sizing ratios (DSCR, LTV, debt yield, breakeven
occupancy), maximum loan by each configurable constraint, and the five
stress cases.

**Everything in this module is plain Python arithmetic. No AI, no
database, no Flask, no I/O of any kind.** That is a deliberate boundary,
not an accident of layering: a credit memo's numbers have to be
reproducible and auditable by hand, and a language model cannot be
either. `credit_memo.py` is allowed to ask Claude for narrative prose;
it is never allowed to ask Claude for a number. Every figure that
reaches a memo originates here.

The module is also importable and fully testable without the feature
flag being on and without a Flask app context -- which is what lets
tests/test_loan_underwriting.py check every formula against
hand-calculated values directly.

Sign conventions, stated once because getting them wrong is the easiest
way to silently produce a wrong NOI:

  * Every deduction argument below (vacancy, concessions, bad debt,
    operating expenses, reserves) is a POSITIVE magnitude. A T-12
    typically stores these as negatives; `t12_import.build_t12_financials`
    normalizes the sign at that boundary so this module never has to
    guess whether a number arrived negated.
  * Percentages are whole numbers, not fractions: 5.0 means 5%, not 500%.
    `annual_rate_pct=6.25` is 6.25% per year.
  * A figure that genuinely cannot be computed is None, never 0.0 --
    the same "None means not enough data, never a guessed zero"
    discipline portfolio.py and deal_mismatch.py already insist on. A
    zero here would read as a real, defensible zero to a credit officer.

Rounding happens only at the boundary of each returned dict: money to
2dp, ratios to 4dp. Intermediate arithmetic keeps full float precision,
so a chain of five deductions doesn't accumulate rounding drift.
"""
from typing import Any, Dict, List, Optional

# Multifamily agency/bank conventions. All three are overridable per
# request -- these are the starting point a lender adjusts, not a rule
# this module enforces.
DEFAULT_TARGET_DSCR = 1.25
DEFAULT_MAX_LTV_PCT = 75.0
DEFAULT_MIN_DEBT_YIELD_PCT = 8.0

# Underwriting assumption defaults. Replacement reserves at $250/unit/yr
# is a standard multifamily figure; vacancy and management fee are
# deliberately conservative relative to a typical T-12 actual.
DEFAULT_VACANCY_PCT = 5.0
DEFAULT_MANAGEMENT_FEE_PCT = 3.0
DEFAULT_REPLACEMENT_RESERVES_PER_UNIT = 250.0

CONSTRAINT_LABELS = {
    "dscr": "Target DSCR",
    "ltv": "Maximum LTV",
    "debt_yield": "Minimum debt yield",
}


def default_assumptions() -> Dict[str, float]:
    """The three adjustable underwriting assumptions, as a fresh mutable dict (never a shared module-level one a caller could mutate for everyone)."""
    return {
        "vacancy_pct": DEFAULT_VACANCY_PCT,
        "management_fee_pct": DEFAULT_MANAGEMENT_FEE_PCT,
        "replacement_reserves_per_unit": DEFAULT_REPLACEMENT_RESERVES_PER_UNIT,
    }


def default_constraints() -> Dict[str, float]:
    """The three configurable sizing constraints, as a fresh mutable dict."""
    return {
        "target_dscr": DEFAULT_TARGET_DSCR,
        "max_ltv_pct": DEFAULT_MAX_LTV_PCT,
        "min_debt_yield_pct": DEFAULT_MIN_DEBT_YIELD_PCT,
    }


# ----------------------------------------------------------------------
# Debt service
# ----------------------------------------------------------------------

def monthly_amortizing_payment(loan_amount: float, annual_rate_pct: float, amortization_years: float) -> Optional[float]:
    """
    Level monthly payment that fully amortizes `loan_amount` over
    `amortization_years` at `annual_rate_pct`:

        P = L * i / (1 - (1 + i)^-n)        where i = rate/12, n = years*12

    The zero-rate case is not a rounding edge, it's a different formula:
    at i == 0 the expression above divides by zero, and the real answer
    is simply principal spread evenly, L / n. Handled explicitly rather
    than guarded with an epsilon, since a 0% loan is a legitimate input
    (seller financing, certain agency/affordable structures).

    Returns None if the loan can never amortize -- a non-positive
    amortization period. A zero loan amount is a real $0 payment, not an
    uncomputable one, so that returns 0.0.
    """
    if amortization_years is None or amortization_years <= 0:
        return None
    if loan_amount is None or loan_amount == 0:
        return 0.0

    periods = amortization_years * 12
    monthly_rate = (annual_rate_pct or 0.0) / 100.0 / 12.0

    if monthly_rate == 0:
        return loan_amount / periods
    return loan_amount * monthly_rate / (1 - (1 + monthly_rate) ** -periods)


def monthly_interest_only_payment(loan_amount: float, annual_rate_pct: float) -> float:
    """Interest accrued in one month on the full outstanding balance: L * rate / 12. No principal, so the balance never moves during an IO period."""
    return (loan_amount or 0.0) * (annual_rate_pct or 0.0) / 100.0 / 12.0


def compute_debt_service(
    loan_amount: float,
    annual_rate_pct: float,
    amortization_years: float,
    interest_only_months: int = 0,
) -> Dict[str, Any]:
    """
    Three annual debt service figures, because a loan with an
    interest-only period genuinely has three different ones and
    collapsing them to a single number is how an IO deal gets
    accidentally flattered:

      * `annual_debt_service_amortizing` -- 12 fully-amortizing
        payments. This is the figure DSCR and loan sizing use by
        default (see compute_ratios/max_loan_by_constraint): it's the
        payment the borrower faces once IO burns off, and sizing off a
        temporary IO payment would approve a loan the property can't
        service in year 3.
      * `annual_debt_service_interest_only` -- 12 IO payments. Only
        meaningful while the IO period is running.
      * `annual_debt_service_year_one` -- what actually leaves the bank
        account in the first 12 months: the IO months that fall inside
        year one at the IO payment, the remainder amortizing. With
        interest_only_months >= 12 this equals the IO figure; with 0 it
        equals the amortizing figure; in between it's a genuine blend.

    `interest_only_months` is clamped at 0 (a negative IO period is
    meaningless, not an error worth raising -- it's treated as "no IO").
    """
    io_months = max(0, int(interest_only_months or 0))

    amortizing_monthly = monthly_amortizing_payment(loan_amount, annual_rate_pct, amortization_years)
    io_monthly = monthly_interest_only_payment(loan_amount, annual_rate_pct)

    io_months_in_year_one = min(io_months, 12)
    amortizing_months_in_year_one = 12 - io_months_in_year_one

    if amortizing_monthly is None:
        # No valid amortization period: an amortizing figure doesn't
        # exist, and year one can only be stated if it's entirely IO.
        annual_amortizing = None
        annual_year_one = round(io_monthly * 12, 2) if io_months_in_year_one == 12 else None
    else:
        annual_amortizing = round(amortizing_monthly * 12, 2)
        annual_year_one = round(
            io_monthly * io_months_in_year_one + amortizing_monthly * amortizing_months_in_year_one, 2
        )

    return {
        "monthly_payment_amortizing": round(amortizing_monthly, 2) if amortizing_monthly is not None else None,
        "monthly_payment_interest_only": round(io_monthly, 2),
        "annual_debt_service_amortizing": annual_amortizing,
        "annual_debt_service_interest_only": round(io_monthly * 12, 2),
        "annual_debt_service_year_one": annual_year_one,
        "interest_only_months": io_months,
        "io_months_in_year_one": io_months_in_year_one,
    }


# ----------------------------------------------------------------------
# Underwritten NOI
# ----------------------------------------------------------------------

def build_underwritten_noi(
    gross_potential_rent: float,
    loss_to_lease: float = 0.0,
    concessions: float = 0.0,
    bad_debt: float = 0.0,
    other_income: float = 0.0,
    operating_expenses_ex_management: float = 0.0,
    unit_count: int = 0,
    vacancy_pct: float = DEFAULT_VACANCY_PCT,
    management_fee_pct: float = DEFAULT_MANAGEMENT_FEE_PCT,
    replacement_reserves_per_unit: float = DEFAULT_REPLACEMENT_RESERVES_PER_UNIT,
) -> Dict[str, Any]:
    """
    The standard lender NOI build-up. T-12 figures are the verified
    base; the three named assumptions replace specific lines rather than
    adjusting the total:

        Gross Potential Rent                 (T-12, verified)
      - Vacancy                              (ASSUMPTION % of GPR)
      - Loss to lease                        (T-12)
      - Concessions                          (T-12)
      - Bad debt / collection loss           (T-12)
      = Effective Rental Income
      + Other income                         (T-12)
      = Effective Gross Income (EGI)
      - Operating expenses                   (T-12, management fee EXCLUDED)
      - Management fee                       (ASSUMPTION % of EGI)
      - Replacement reserves                 (ASSUMPTION $/unit)
      = Underwritten NOI

    `loss_to_lease` is the gap between market rent and the rent actually
    contracted on in-place leases. It has to be deducted whenever Gross
    Potential Rent is stated at MARKET rent, which is the normal
    convention -- otherwise the build-up credits the property with rent
    no signed lease obliges anyone to pay. On the demo T-12 the identity
    holds exactly: 2,177,280 GPR - 107,685.39 vacancy - 25,521.97 loss
    to lease = 2,044,072.64, the statement's own "Net Rental Income
    Billed" line. Omitting it would overstate NOI by the full $25,521.97
    with nothing in the output hinting anything was missing, which is
    precisely the kind of silent error this build-up exists to prevent.
    Defaults to 0.0 for a T-12 whose GPR is already stated at in-place
    contract rent (no loss-to-lease line to find).

    Two more things here are easy to get quietly wrong, so both are
    explicit:

    `operating_expenses_ex_management` must ALREADY have the T-12's own
    management fee line removed. The underwritten fee is computed from
    the assumption percentage below; if the actual fee were still sitting
    in the expense total, the property would be charged a management fee
    twice. The demo T-12 carries a real "Management Fee (3% of Total
    Income)" line, so this is a live hazard on real input, not a
    hypothetical -- `t12_import.build_t12_financials` is what strips it,
    and it reports the stripped amount separately so the subtraction is
    visible rather than implicit.

    Replacement reserves are an underwriting ADD, not a T-12 line -- an
    operating statement records what was spent, and a lender charges a
    forward-looking per-unit reserve regardless. So underwritten NOI sits
    structurally below a T-12's historical NOI even at identical vacancy.
    That gap is expected and the memo shows both figures side by side;
    it is not a sign either number is wrong.

    Vacancy is applied to GPR only, not to other income -- other income
    (RUBS, fees, parking) is already an actual collected figure on the
    T-12 and isn't a function of the rent roll's occupancy in the way
    scheduled rent is. Applying a vacancy factor to it would be double-
    counting a loss already baked into the actual.

    Returns every intermediate line, not just the NOI, so a credit memo
    can show the whole build-up and a reviewer can check each step.
    """
    gpr = gross_potential_rent or 0.0
    vacancy_amount = gpr * (vacancy_pct or 0.0) / 100.0
    effective_rental_income = (
        gpr - vacancy_amount - (loss_to_lease or 0.0) - (concessions or 0.0) - (bad_debt or 0.0)
    )
    egi = effective_rental_income + (other_income or 0.0)

    management_fee = egi * (management_fee_pct or 0.0) / 100.0
    replacement_reserves = (unit_count or 0) * (replacement_reserves_per_unit or 0.0)
    total_operating_expenses = (operating_expenses_ex_management or 0.0) + management_fee + replacement_reserves

    noi = egi - total_operating_expenses

    return {
        "gross_potential_rent": round(gpr, 2),
        "vacancy_pct": vacancy_pct,
        "vacancy_amount": round(vacancy_amount, 2),
        "loss_to_lease": round(loss_to_lease or 0.0, 2),
        "concessions": round(concessions or 0.0, 2),
        "bad_debt": round(bad_debt or 0.0, 2),
        "effective_rental_income": round(effective_rental_income, 2),
        "other_income": round(other_income or 0.0, 2),
        "effective_gross_income": round(egi, 2),
        "operating_expenses_ex_management": round(operating_expenses_ex_management or 0.0, 2),
        "management_fee_pct": management_fee_pct,
        "management_fee": round(management_fee, 2),
        "replacement_reserves_per_unit": replacement_reserves_per_unit,
        "unit_count": unit_count,
        "replacement_reserves": round(replacement_reserves, 2),
        "total_operating_expenses": round(total_operating_expenses, 2),
        "underwritten_noi": round(noi, 2),
    }


# ----------------------------------------------------------------------
# Ratios
# ----------------------------------------------------------------------

def compute_value_basis(purchase_price: Optional[float], appraised_value: Optional[float]) -> Dict[str, Any]:
    """
    The value LTV is measured against: the LESSER of purchase price and
    appraised value when both are known.

    This is standard conservative acquisition practice, and it matters
    in both directions. If a buyer pays $19M for a property that
    appraises at $18M, the lender sizes against $18M -- it won't lend
    against a premium the market didn't confirm. If the property
    appraises ABOVE the price, the lender still sizes against the price,
    because the buyer's actual cost is the real exposure and an
    above-price appraisal on a just-transacted asset is not realized
    value.

    Both inputs are optional (an appraisal may not be back yet). With
    only one, that one is the basis. With neither, the basis is None and
    every LTV-dependent figure downstream is None rather than invented.

    Returns which figure was used, by name, so the memo can show it --
    an LTV whose denominator is ambiguous is not a reviewable number.
    """
    candidates = {
        "purchase_price": purchase_price,
        "appraised_value": appraised_value,
    }
    usable = {name: value for name, value in candidates.items() if value is not None and value > 0}

    if not usable:
        return {
            "value_basis": None,
            "value_basis_source": None,
            "purchase_price": purchase_price,
            "appraised_value": appraised_value,
        }

    basis_name = min(usable, key=lambda name: usable[name])
    return {
        "value_basis": round(usable[basis_name], 2),
        "value_basis_source": basis_name,
        "purchase_price": purchase_price,
        "appraised_value": appraised_value,
    }


def compute_breakeven_occupancy(
    total_operating_expenses: float,
    annual_debt_service: Optional[float],
    gross_potential_rent: float,
    other_income: float = 0.0,
) -> Optional[float]:
    """
    The occupancy level at which income exactly covers operating
    expenses plus debt service -- i.e. the point where the deal stops
    breaking even:

        (total operating expenses + annual debt service)
        -----------------------------------------------  x 100
              (gross potential rent + other income)

    Returned as a percentage.

    Two convention choices, stated because lenders genuinely differ and
    an unlabelled breakeven number isn't comparable across shops:

      * Replacement reserves ARE included in the numerator (they're part
        of `total_operating_expenses` as this module builds it). Some
        lenders exclude them, which produces a lower, friendlier
        breakeven. Ours is the more conservative of the two.
      * Operating expenses are held FIXED as occupancy falls. In reality
        the management fee is a percentage of income and would fall too,
        which makes the true breakeven marginally lower. The standard
        formula ignores this second-order effect and so does this one;
        the error is small and in the conservative direction.

    None if there's no potential income to measure against -- dividing
    by a zero denominator, not a meaningful 0% breakeven.
    """
    potential_income = (gross_potential_rent or 0.0) + (other_income or 0.0)
    if potential_income <= 0 or annual_debt_service is None:
        return None
    return round((total_operating_expenses + annual_debt_service) / potential_income * 100, 4)


def compute_ratios(
    noi: float,
    loan_amount: float,
    debt_service: Dict[str, Any],
    value_basis_info: Dict[str, Any],
    noi_build_up: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    DSCR, LTV, debt yield and breakeven occupancy.

    DSCR is reported against all three debt service figures, with the
    AMORTIZING one as the headline `dscr`: that's the payment the deal
    has to live with after any IO period expires, and it's what sizes
    the loan. `dscr_year_one` and `dscr_interest_only` are included and
    labelled so an IO deal's near-term coverage is visible too -- but a
    reader is never handed a single unlabelled "DSCR" that silently
    means the flattering one.

    A negative NOI produces a genuinely negative DSCR and debt yield.
    Those are not clamped: "-0.42x coverage" is real, legible
    information about a property that doesn't cover its debt, and
    flooring it at zero would hide the magnitude of the shortfall.
    (Loan SIZING does floor at zero -- see max_loan_by_constraint --
    because a negative maximum loan amount is not information, it's
    nonsense.)

    Every ratio is None where its denominator is missing or zero, never
    a substituted 0.
    """
    value_basis = value_basis_info.get("value_basis")

    def _dscr(annual_ds: Optional[float]) -> Optional[float]:
        if annual_ds is None or annual_ds == 0:
            return None
        return round(noi / annual_ds, 4)

    ltv_pct = None
    if value_basis:
        ltv_pct = round(loan_amount / value_basis * 100, 4)

    debt_yield_pct = None
    if loan_amount:
        debt_yield_pct = round(noi / loan_amount * 100, 4)

    breakeven = None
    if noi_build_up is not None:
        breakeven = compute_breakeven_occupancy(
            total_operating_expenses=noi_build_up["total_operating_expenses"],
            annual_debt_service=debt_service.get("annual_debt_service_amortizing"),
            gross_potential_rent=noi_build_up["gross_potential_rent"],
            other_income=noi_build_up["other_income"],
        )

    return {
        "dscr": _dscr(debt_service.get("annual_debt_service_amortizing")),
        "dscr_year_one": _dscr(debt_service.get("annual_debt_service_year_one")),
        "dscr_interest_only": _dscr(debt_service.get("annual_debt_service_interest_only")),
        "ltv_pct": ltv_pct,
        "ltv_basis": value_basis_info.get("value_basis_source"),
        "ltv_vs_purchase_price_pct": (
            round(loan_amount / value_basis_info["purchase_price"] * 100, 4)
            if value_basis_info.get("purchase_price") else None
        ),
        "ltv_vs_appraised_value_pct": (
            round(loan_amount / value_basis_info["appraised_value"] * 100, 4)
            if value_basis_info.get("appraised_value") else None
        ),
        "debt_yield_pct": debt_yield_pct,
        "breakeven_occupancy_pct": breakeven,
    }


# ----------------------------------------------------------------------
# Maximum loan by constraint
# ----------------------------------------------------------------------

def annual_payment_factor(
    annual_rate_pct: float,
    amortization_years: float,
    size_on_interest_only: bool = False,
) -> Optional[float]:
    """
    Annual debt service per $1 of loan -- the conversion factor between
    a supportable payment and a supportable loan balance.

    Amortizing: 12 * i / (1 - (1+i)^-n). Interest-only: just the annual
    rate. Zero-rate amortizing: 12/n (principal spread evenly). None if
    there's no valid amortization period and we're not sizing IO.
    """
    rate = (annual_rate_pct or 0.0) / 100.0
    if size_on_interest_only:
        return rate if rate > 0 else None

    if amortization_years is None or amortization_years <= 0:
        return None

    periods = amortization_years * 12
    monthly_rate = rate / 12.0
    if monthly_rate == 0:
        return 12.0 / periods
    return 12 * monthly_rate / (1 - (1 + monthly_rate) ** -periods)


def max_loan_by_constraint(
    noi: float,
    value_basis: Optional[float],
    annual_rate_pct: float,
    amortization_years: float,
    constraints: Optional[Dict[str, float]] = None,
    size_on_interest_only: bool = False,
) -> Dict[str, Any]:
    """
    The largest loan each of the three constraints permits, and which
    one binds.

      * DSCR:       supportable annual debt service = NOI / target DSCR,
                    then converted to a balance by the annual payment
                    factor.
      * LTV:        value basis * max LTV%.
      * Debt yield: NOI / min debt yield%.

    The binding constraint is the minimum of whichever are computable --
    that's the actual maximum loan, and it's reported by name alongside
    all three values so a credit officer can see how much room the other
    two had.

    A non-positive NOI floors the DSCR and debt-yield maximums at 0.0: a
    property with no net income supports no debt. Without that floor,
    both formulas return negative loan amounts, which isn't a
    conservative result -- it's a number that would sort as "smallest"
    and could propagate into a memo as if it meant something. (Contrast
    compute_ratios, which deliberately does NOT clamp the negative
    ratios themselves -- there, the magnitude is the information.)

    Constraints default per default_constraints() and every one is
    overridable. A constraint whose input is missing (no appraisal yet,
    so no value basis) yields None for that constraint rather than
    dropping silently to a different binding one without saying so.
    """
    constraints = {**default_constraints(), **(constraints or {})}
    target_dscr = constraints.get("target_dscr")
    max_ltv_pct = constraints.get("max_ltv_pct")
    min_debt_yield_pct = constraints.get("min_debt_yield_pct")

    factor = annual_payment_factor(annual_rate_pct, amortization_years, size_on_interest_only)

    max_by_dscr = None
    if target_dscr and target_dscr > 0 and factor:
        if noi <= 0:
            max_by_dscr = 0.0
        else:
            max_by_dscr = round((noi / target_dscr) / factor, 2)

    max_by_ltv = None
    if value_basis and max_ltv_pct is not None:
        max_by_ltv = round(value_basis * max_ltv_pct / 100.0, 2)

    max_by_debt_yield = None
    if min_debt_yield_pct and min_debt_yield_pct > 0:
        max_by_debt_yield = 0.0 if noi <= 0 else round(noi / (min_debt_yield_pct / 100.0), 2)

    by_constraint = {
        "dscr": max_by_dscr,
        "ltv": max_by_ltv,
        "debt_yield": max_by_debt_yield,
    }
    computable = {name: value for name, value in by_constraint.items() if value is not None}

    binding_constraint = None
    maximum_loan = None
    if computable:
        # min() over dict keys is deterministic on ties by insertion
        # order (dscr, ltv, debt_yield) -- a tie means both genuinely
        # bind at the same dollar amount, so either label is accurate;
        # picking deterministically keeps the output reproducible rather
        # than varying run to run.
        binding_constraint = min(computable, key=lambda name: computable[name])
        maximum_loan = computable[binding_constraint]

    return {
        "max_loan_by_dscr": max_by_dscr,
        "max_loan_by_ltv": max_by_ltv,
        "max_loan_by_debt_yield": max_by_debt_yield,
        "binding_constraint": binding_constraint,
        "binding_constraint_label": CONSTRAINT_LABELS.get(binding_constraint) if binding_constraint else None,
        "maximum_loan": maximum_loan,
        "constraints_used": constraints,
        "sized_on_interest_only": size_on_interest_only,
    }


# ----------------------------------------------------------------------
# Stress tests
# ----------------------------------------------------------------------

# The five cases, in the order a memo presents them. `kind` tells
# run_stress_tests which input to perturb; nothing here recomputes
# anything itself, so adding a sixth case is a one-line change.
STRESS_CASES = [
    {"key": "rate_plus_100bp", "label": "Interest rate +100 bps", "kind": "rate", "delta_bps": 100},
    {"key": "rate_plus_200bp", "label": "Interest rate +200 bps", "kind": "rate", "delta_bps": 200},
    {"key": "occupancy_down_5pt", "label": "Occupancy -5 points", "kind": "occupancy", "delta_points": 5.0},
    {"key": "occupancy_down_10pt", "label": "Occupancy -10 points", "kind": "occupancy", "delta_points": 10.0},
    {"key": "noi_down_10pct", "label": "NOI -10%", "kind": "noi", "factor": 0.90},
]


def run_stress_tests(
    t12_inputs: Dict[str, Any],
    loan_terms: Dict[str, Any],
    assumptions: Dict[str, float],
    constraints: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Each of the five cases, recomputed end to end -- NOI, debt service,
    every ratio, and the binding constraint. Not a sensitivity table of
    one figure: a rate stress changes debt service and therefore DSCR
    and the DSCR-bound maximum loan, while an occupancy stress changes
    NOI and therefore debt yield, breakeven AND the DSCR. Reporting only
    the headline DSCR would hide which constraint takes over under
    stress, which is usually the point of running one.

    An occupancy stress is applied as vacancy ADDED to the vacancy
    assumption (occupancy down 5 points == vacancy up 5 points), so it
    flows through the same NOI build-up as the base case rather than
    scaling the result. That's why "occupancy down 10 points" on a
    property underwritten at 5% vacancy means 15% vacancy, not 10%.

    The NOI stress scales the final underwritten NOI by 0.90 directly
    rather than reverse-engineering which line item moved -- "NOI down
    10%" is a statement about the outcome, not about a cause.
    """
    results: List[Dict[str, Any]] = []

    for case in STRESS_CASES:
        stressed_assumptions = dict(assumptions)
        stressed_rate = loan_terms["annual_rate_pct"]
        noi_factor = 1.0

        if case["kind"] == "rate":
            stressed_rate = loan_terms["annual_rate_pct"] + case["delta_bps"] / 100.0
        elif case["kind"] == "occupancy":
            stressed_assumptions["vacancy_pct"] = (
                stressed_assumptions.get("vacancy_pct", DEFAULT_VACANCY_PCT) + case["delta_points"]
            )
        elif case["kind"] == "noi":
            noi_factor = case["factor"]

        build_up = build_underwritten_noi(
            gross_potential_rent=t12_inputs.get("gross_potential_rent", 0.0),
            loss_to_lease=t12_inputs.get("loss_to_lease", 0.0),
            concessions=t12_inputs.get("concessions", 0.0),
            bad_debt=t12_inputs.get("bad_debt", 0.0),
            other_income=t12_inputs.get("other_income", 0.0),
            operating_expenses_ex_management=t12_inputs.get("operating_expenses_ex_management", 0.0),
            unit_count=t12_inputs.get("unit_count", 0),
            **stressed_assumptions,
        )
        stressed_noi = round(build_up["underwritten_noi"] * noi_factor, 2)

        debt_service = compute_debt_service(
            loan_amount=loan_terms["loan_amount"],
            annual_rate_pct=stressed_rate,
            amortization_years=loan_terms["amortization_years"],
            interest_only_months=loan_terms.get("interest_only_months", 0),
        )
        value_basis_info = compute_value_basis(
            loan_terms.get("purchase_price"), loan_terms.get("appraised_value")
        )
        ratios = compute_ratios(
            noi=stressed_noi,
            loan_amount=loan_terms["loan_amount"],
            debt_service=debt_service,
            value_basis_info=value_basis_info,
            noi_build_up=build_up,
        )
        sizing = max_loan_by_constraint(
            noi=stressed_noi,
            value_basis=value_basis_info.get("value_basis"),
            annual_rate_pct=stressed_rate,
            amortization_years=loan_terms["amortization_years"],
            constraints=constraints,
        )

        results.append({
            "key": case["key"],
            "label": case["label"],
            "stressed_annual_rate_pct": round(stressed_rate, 4),
            "stressed_vacancy_pct": stressed_assumptions.get("vacancy_pct"),
            "underwritten_noi": stressed_noi,
            "annual_debt_service": debt_service["annual_debt_service_amortizing"],
            "dscr": ratios["dscr"],
            "debt_yield_pct": ratios["debt_yield_pct"],
            "ltv_pct": ratios["ltv_pct"],
            "breakeven_occupancy_pct": ratios["breakeven_occupancy_pct"],
            "maximum_loan": sizing["maximum_loan"],
            "binding_constraint": sizing["binding_constraint"],
        })

    return results


# ----------------------------------------------------------------------
# Top-level entry point
# ----------------------------------------------------------------------

def underwrite(
    loan_terms: Dict[str, Any],
    t12_inputs: Dict[str, Any],
    assumptions: Optional[Dict[str, float]] = None,
    constraints: Optional[Dict[str, float]] = None,
    sources: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    One call, one complete underwriting result -- the single structure
    both the API response and the credit memo read from, the same "one
    shared computation, multiple renderers" convention
    investment_memo.build_investment_memo_data and
    deal_mismatch.build_deal_mismatch_report_data already follow. The
    memo and the API can therefore never disagree about what they're
    reporting for the same request.

    `loan_terms`: loan_amount, annual_rate_pct, amortization_years,
    term_years, interest_only_months, purchase_price, appraised_value,
    unit_count.

    `t12_inputs`: gross_potential_rent, loss_to_lease, concessions,
    bad_debt, other_income, operating_expenses_ex_management,
    unit_count, and optionally historical_noi (the T-12's own stated
    NOI, passed through untouched for the memo's historical column).

    `sources`: per-input-key provenance, as produced by
    t12_import.build_t12_financials -- carried through onto the result
    so every number on a memo page can cite where it came from. Inputs
    with no source document (the three assumptions, the loan terms the
    user typed) are absent from this map rather than given a fabricated
    citation.

    The exact assumptions and constraints used are returned alongside
    the results, so a stored result can never drift out of sync with the
    inputs that produced it.
    """
    assumptions = {**default_assumptions(), **(assumptions or {})}
    constraints = {**default_constraints(), **(constraints or {})}

    unit_count = t12_inputs.get("unit_count") or loan_terms.get("unit_count") or 0

    noi_build_up = build_underwritten_noi(
        gross_potential_rent=t12_inputs.get("gross_potential_rent", 0.0),
        loss_to_lease=t12_inputs.get("loss_to_lease", 0.0),
        concessions=t12_inputs.get("concessions", 0.0),
        bad_debt=t12_inputs.get("bad_debt", 0.0),
        other_income=t12_inputs.get("other_income", 0.0),
        operating_expenses_ex_management=t12_inputs.get("operating_expenses_ex_management", 0.0),
        unit_count=unit_count,
        **assumptions,
    )
    noi = noi_build_up["underwritten_noi"]

    debt_service = compute_debt_service(
        loan_amount=loan_terms["loan_amount"],
        annual_rate_pct=loan_terms["annual_rate_pct"],
        amortization_years=loan_terms["amortization_years"],
        interest_only_months=loan_terms.get("interest_only_months", 0),
    )
    value_basis_info = compute_value_basis(
        loan_terms.get("purchase_price"), loan_terms.get("appraised_value")
    )
    ratios = compute_ratios(
        noi=noi,
        loan_amount=loan_terms["loan_amount"],
        debt_service=debt_service,
        value_basis_info=value_basis_info,
        noi_build_up=noi_build_up,
    )
    sizing = max_loan_by_constraint(
        noi=noi,
        value_basis=value_basis_info.get("value_basis"),
        annual_rate_pct=loan_terms["annual_rate_pct"],
        amortization_years=loan_terms["amortization_years"],
        constraints=constraints,
    )
    stress_tests = run_stress_tests(
        t12_inputs={**t12_inputs, "unit_count": unit_count},
        loan_terms=loan_terms,
        assumptions=assumptions,
        constraints=constraints,
    )

    return {
        "loan_terms": dict(loan_terms),
        "assumptions_used": assumptions,
        "constraints_used": constraints,
        "noi_build_up": noi_build_up,
        "historical_noi": t12_inputs.get("historical_noi"),
        "debt_service": debt_service,
        "value_basis": value_basis_info,
        "ratios": ratios,
        "sizing": sizing,
        "stress_tests": stress_tests,
        "sources": sources or {},
    }
