"""
Tests for app/loan_underwriting.py's build_dscr_sensitivity_grid: a full
matrix of DSCR across interest rates (rows) and occupancy levels
(columns), as distinct from run_stress_tests' five independent named
cases -- the grid is what shows a credit officer the INTERACTION between
a rate move and an occupancy drop, which five single-variable stresses
can't.

Every expected cell below was computed independently (see
test_loan_underwriting_three_deals.py's Deal A for the base-case figures
this file reuses, plus a hand calculation for the 100%-occupancy /
zero-vacancy column) and cross-checked against the grid's output.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.loan_underwriting import build_dscr_sensitivity_grid, underwrite


def _close(actual, expected, tolerance=0.01):
    return actual is not None and abs(actual - expected) <= tolerance


# Same deal as test_loan_underwriting_three_deals.py's Deal A (Sunset
# Gardens), reused here because its base-case DSCR (1.7256x at 6.0% / 95%
# occupancy) is already independently hand-verified there -- this file's
# tests cross-check the GRID against that known-good anchor rather than
# re-deriving the NOI arithmetic from scratch.
_TERMS = {
    "loan_amount": 8_000_000.0, "annual_rate_pct": 6.0, "amortization_years": 30,
    "term_years": 10, "interest_only_months": 0,
}
_T12 = {
    "gross_potential_rent": 1_600_000.0, "loss_to_lease": 0.0, "concessions": 0.0,
    "bad_debt": 0.0, "other_income": 40_000.0,
    "operating_expenses_ex_management": 500_000.0, "unit_count": 80,
}
_ASSUMPTIONS = {"vacancy_pct": 5.0, "management_fee_pct": 3.0, "replacement_reserves_per_unit": 250.0}


def _cell(grid, rate_delta_bps, occupancy_pct):
    row = next(r for r in grid["rows"] if r["rate_delta_bps"] == rate_delta_bps)
    return next(c for c in row["cells"] if c["occupancy_pct"] == occupancy_pct)


def test_grid_shape_is_five_rates_by_four_occupancy_levels_by_default():
    grid = build_dscr_sensitivity_grid(_T12, _TERMS, _ASSUMPTIONS)
    assert grid["rate_deltas_bps"] == [-100, 0, 100, 200, 300], grid["rate_deltas_bps"]
    assert grid["occupancy_levels_pct"] == [85.0, 90.0, 95.0, 100.0], grid["occupancy_levels_pct"]
    assert len(grid["rows"]) == 5, grid["rows"]
    assert all(len(row["cells"]) == 4 for row in grid["rows"])
    print("✓ test_grid_shape_is_five_rates_by_four_occupancy_levels_by_default: PASS")


def test_base_rate_base_occupancy_cell_matches_the_known_good_deal_a_dscr():
    """The (0bp, 95% occupancy) cell is exactly Deal A's base case: rate 6.0%, vacancy 5.0%, DSCR 1.7256x."""
    grid = build_dscr_sensitivity_grid(_T12, _TERMS, _ASSUMPTIONS)
    cell = _cell(grid, 0, 95.0)
    assert cell["vacancy_pct"] == 5.0, cell
    assert cell["underwritten_noi"] == 993_200.00, cell
    assert _close(cell["annual_debt_service"], 575_568.50, 0.05), cell
    assert _close(cell["dscr"], 1.7256, 0.0001), cell
    print("✓ test_base_rate_base_occupancy_cell_matches_the_known_good_deal_a_dscr: PASS")


def test_full_occupancy_column_matches_hand_calculated_zero_vacancy_noi():
    """
    Hand calculation at 100% occupancy (0% vacancy):
      EGI = 1,600,000 + 40,000 = 1,640,000 (no vacancy deduction)
      mgmt fee 3% of EGI = 49,200
      total opex = 500,000 + 49,200 + 20,000 = 569,200
      NOI = 1,640,000 - 569,200 = 1,070,800.00
    """
    grid = build_dscr_sensitivity_grid(_T12, _TERMS, _ASSUMPTIONS)
    cell = _cell(grid, 0, 100.0)
    assert cell["vacancy_pct"] == 0.0, cell
    assert cell["underwritten_noi"] == 1_070_800.00, cell
    print("✓ test_full_occupancy_column_matches_hand_calculated_zero_vacancy_noi: PASS")


def test_dscr_decreases_monotonically_as_rate_rises_at_fixed_occupancy():
    """Higher rate -> higher debt service -> lower DSCR, holding occupancy fixed. A basic sanity invariant the grid must satisfy everywhere."""
    grid = build_dscr_sensitivity_grid(_T12, _TERMS, _ASSUMPTIONS)
    for occupancy in grid["occupancy_levels_pct"]:
        dscrs = [_cell(grid, delta, occupancy)["dscr"] for delta in grid["rate_deltas_bps"]]
        assert dscrs == sorted(dscrs, reverse=True), (occupancy, dscrs)
    print("✓ test_dscr_decreases_monotonically_as_rate_rises_at_fixed_occupancy: PASS")


def test_dscr_increases_monotonically_as_occupancy_rises_at_fixed_rate():
    """Higher occupancy -> higher NOI -> higher DSCR, holding rate fixed."""
    grid = build_dscr_sensitivity_grid(_T12, _TERMS, _ASSUMPTIONS)
    for delta in grid["rate_deltas_bps"]:
        dscrs = [_cell(grid, delta, occ)["dscr"] for occ in grid["occupancy_levels_pct"]]
        assert dscrs == sorted(dscrs), (delta, dscrs)
    print("✓ test_dscr_increases_monotonically_as_occupancy_rises_at_fixed_rate: PASS")


def test_noi_is_identical_across_every_row_for_a_given_occupancy_column():
    """A rate change must not move NOI -- NOI is a property-level figure, debt service is a loan-level one. Only DSCR should vary down a rate column... across a row, rather: NOI must be constant ACROSS rows (rates) for a fixed occupancy."""
    grid = build_dscr_sensitivity_grid(_T12, _TERMS, _ASSUMPTIONS)
    for occupancy in grid["occupancy_levels_pct"]:
        nois = {_cell(grid, delta, occupancy)["underwritten_noi"] for delta in grid["rate_deltas_bps"]}
        assert len(nois) == 1, (occupancy, nois)
    print("✓ test_noi_is_identical_across_every_row_for_a_given_occupancy_column: PASS")


def test_rate_axis_floors_at_zero_rather_than_going_negative():
    """A rate delta that would push the tested rate below 0% is clamped -- a negative interest rate has no meaning for this product."""
    low_rate_terms = {**_TERMS, "annual_rate_pct": 0.5}
    grid = build_dscr_sensitivity_grid(_T12, low_rate_terms, _ASSUMPTIONS, rate_deltas_bps=[-100, 0, 100])
    floored_row = next(r for r in grid["rows"] if r["rate_delta_bps"] == -100)
    assert floored_row["annual_rate_pct"] == 0.0, floored_row
    print("✓ test_rate_axis_floors_at_zero_rather_than_going_negative: PASS")


def test_custom_axes_are_honored():
    grid = build_dscr_sensitivity_grid(
        _T12, _TERMS, _ASSUMPTIONS,
        rate_deltas_bps=[0, 50], occupancy_levels_pct=[92.5],
    )
    assert grid["rate_deltas_bps"] == [0, 50]
    assert grid["occupancy_levels_pct"] == [92.5]
    assert len(grid["rows"]) == 2
    assert len(grid["rows"][0]["cells"]) == 1
    print("✓ test_custom_axes_are_honored: PASS")


def test_grid_handles_negative_noi_without_crashing():
    """The distressed-deal edge case: every cell must still compute (and report a real negative DSCR), never raise."""
    broke_t12 = {**_T12, "operating_expenses_ex_management": 2_000_000.0}
    grid = build_dscr_sensitivity_grid(broke_t12, _TERMS, _ASSUMPTIONS)
    worst_cell = _cell(grid, 300, 85.0)
    assert worst_cell["underwritten_noi"] < 0, worst_cell
    assert worst_cell["dscr"] < 0, worst_cell
    print("✓ test_grid_handles_negative_noi_without_crashing: PASS")


def test_underwrite_includes_the_sensitivity_grid_in_its_result():
    """The grid is wired into the top-level result, not just callable standalone."""
    result = underwrite(_TERMS, _T12, assumptions=_ASSUMPTIONS)
    assert "sensitivity_grid" in result
    grid = result["sensitivity_grid"]
    assert len(grid["rows"]) == 5
    # The grid's own (0bp, base-occupancy) cell must agree with the
    # top-level headline DSCR for the same deal -- two different code
    # paths computing the same thing must not disagree.
    base_occupancy = round(100.0 - _ASSUMPTIONS["vacancy_pct"], 4)
    grid_cell = _cell(grid, 0, base_occupancy) if any(
        c["occupancy_pct"] == base_occupancy for c in grid["rows"][1]["cells"]
    ) else None
    if grid_cell is not None:
        assert _close(grid_cell["dscr"], result["ratios"]["dscr"], 0.0001), (grid_cell, result["ratios"])
    print("✓ test_underwrite_includes_the_sensitivity_grid_in_its_result: PASS")


if __name__ == "__main__":
    test_grid_shape_is_five_rates_by_four_occupancy_levels_by_default()
    test_base_rate_base_occupancy_cell_matches_the_known_good_deal_a_dscr()
    test_full_occupancy_column_matches_hand_calculated_zero_vacancy_noi()
    test_dscr_decreases_monotonically_as_rate_rises_at_fixed_occupancy()
    test_dscr_increases_monotonically_as_occupancy_rises_at_fixed_rate()
    test_noi_is_identical_across_every_row_for_a_given_occupancy_column()
    test_rate_axis_floors_at_zero_rather_than_going_negative()
    test_custom_axes_are_honored()
    test_grid_handles_negative_noi_without_crashing()
    test_underwrite_includes_the_sensitivity_grid_in_its_result()
    print("\nAll sensitivity grid tests passed.")
