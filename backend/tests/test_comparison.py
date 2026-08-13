"""
Tests for side-by-side lease comparison and single-lease benchmarking.

The benchmark fixtures are built around a portfolio whose averages are
deliberately round numbers (rent $6,000, CAM $500, deposit $12,000,
escalation 4%), so a subject lease can be placed at exactly the average,
exactly 20% above, exactly 20% below, and exactly on the +/-10% in-line
boundary. Testing the boundary matters more than testing the middle of
each band — "is 10.0% in line or above average?" is the only part of the
classification a reader could reasonably guess wrong.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.comparison import benchmark_lease, compare_leases
from app.portfolio import FIELD_NAMES


def _field(value, page=1, confidence="high"):
    """One extracted field in the standard {value, source, confidence} shape."""
    if value is None:
        return {"value": None, "source": None, "confidence": None}
    return {
        "value": value,
        "source": {"page": page, "quote": f"...{value}..."},
        "confidence": confidence,
    }


def _lease(lease_id, filename, **values):
    """A lease record with all 15 fields present; unspecified ones are None."""
    return {
        "id": lease_id,
        "filename": filename,
        "uploaded_at": "2026-01-10T09:00:00",
        "document_type": "lease",
        "base_lease_id": None,
        "amendment_count": 0,
        "extracted_fields": {name: _field(values.get(name)) for name in FIELD_NAMES},
    }


LEASE_RETAIL = _lease(
    1, "retail_lease.pdf",
    tenant="Blue Sky Coffee Roasters, Inc.",
    landlord="Harborview Properties LLC",
    rent_amount="$6,000.00",
    lease_start_date="April 1, 2021",
    lease_end_date="March 31, 2026",
    property_address="120 Harbor Street, Suite 4, Portland, ME",
    security_deposit="$12,000.00",
    cam_charges="$800.00",
    rent_escalation="3% annually",
    renewal_options="2 option(s) of 5 year(s) each; 180 days notice; renewal rent based on then-prevailing fair market rate",
    permitted_use="retail coffee roasting and cafe",
    exclusivity_clause="No other coffee retailer in the shopping center",
    insurance_requirements="$2,000,000 per occurrence",
    default_cure_period="10 days after written notice",
    square_footage="2,400 sq ft",
)

LEASE_OFFICE = _lease(
    2, "office_lease.pdf",
    tenant="Meridian Analytics Group",
    landlord="Harborview Properties LLC",
    rent_amount="$9,000.00",
    lease_start_date="January 1, 2022",
    lease_end_date="December 31, 2026",
    property_address="400 Congress Street, Floor 3, Portland, ME",
    security_deposit="$18,000.00",
    cam_charges="$1,200.00",
    rent_escalation="5% annually",
    renewal_options="1 option(s) of 3 year(s) each; 90 days notice; renewal rent based on fixed 4% increase",
    permitted_use="general office use",
    insurance_requirements="$1,000,000 per occurrence",
    default_cure_period="30 days after written notice",
    square_footage="3,000 sq ft",
)

# Sparse: most clauses genuinely absent.
LEASE_SUBLEASE = _lease(
    3, "casual_sublease.pdf",
    tenant="Alex Chen",
    landlord="Jordan Blake",
    rent_amount="$2,000.00",
    lease_start_date="July 1, 2024",
    lease_end_date="June 30, 2025",
    property_address="17 Elm Street, Apt 2, Portland, ME",
)


def _benchmark_portfolio():
    """
    Three leases with intentionally round averages:
      rent       5000, 6000, 7000  -> 6000
      CAM         400,  500,  600  ->  500
      deposit   10000,12000,14000  -> 12000
      escalation   3%,   4%,   5%  ->    4.0
    """
    return [
        _lease(101, "bench_a.pdf", rent_amount="$5,000.00", cam_charges="$400.00",
               security_deposit="$10,000.00", rent_escalation="3% annually"),
        _lease(102, "bench_b.pdf", rent_amount="$6,000.00", cam_charges="$500.00",
               security_deposit="$12,000.00", rent_escalation="4% annually"),
        _lease(103, "bench_c.pdf", rent_amount="$7,000.00", cam_charges="$600.00",
               security_deposit="$14,000.00", rent_escalation="5% annually"),
    ]


def test_compare_two_leases():
    """Two-lease comparison: one column per lease, in the order given."""
    result = compare_leases([LEASE_RETAIL, LEASE_OFFICE])

    assert result["lease_ids"] == [1, 2]
    assert result["filenames"] == ["retail_lease.pdf", "office_lease.pdf"]
    assert set(result["fields"].keys()) == set(FIELD_NAMES), "all 15 fields must appear"

    assert result["fields"]["rent_amount"] == ["$6,000.00", "$9,000.00"]
    assert result["fields"]["tenant"] == ["Blue Sky Coffee Roasters, Inc.", "Meridian Analytics Group"]
    assert result["fields"]["square_footage"] == ["2,400 sq ft", "3,000 sq ft"]

    print("✓ test_compare_two_leases: PASS")


def test_compare_three_leases_preserves_order_and_gaps():
    """
    Three leases, including a sparse one. A field that's missing on one
    lease must hold its column position as None rather than shifting the
    remaining values left.
    """
    result = compare_leases([LEASE_RETAIL, LEASE_SUBLEASE, LEASE_OFFICE])

    assert result["lease_ids"] == [1, 3, 2]
    assert result["filenames"] == ["retail_lease.pdf", "casual_sublease.pdf", "office_lease.pdf"]

    assert result["fields"]["rent_amount"] == ["$6,000.00", "$2,000.00", "$9,000.00"]
    assert result["fields"]["cam_charges"] == ["$800.00", None, "$1,200.00"]
    assert result["fields"]["exclusivity_clause"] == [
        "No other coffee retailer in the shopping center", None, None
    ]

    for name in FIELD_NAMES:
        assert len(result["fields"][name]) == 3, f"{name} must have one entry per lease"

    print("✓ test_compare_three_leases_preserves_order_and_gaps: PASS")


def test_compare_keeps_display_values_verbatim():
    """
    Comparison is a human-verification view, so values are the extractor's
    own strings — not parsed, rounded, or reformatted.
    """
    result = compare_leases([LEASE_RETAIL, LEASE_OFFICE])

    assert result["fields"]["insurance_requirements"][0] == "$2,000,000 per occurrence"
    assert result["fields"]["default_cure_period"][0] == "10 days after written notice"
    assert result["fields"]["renewal_options"][1] == (
        "1 option(s) of 3 year(s) each; 90 days notice; renewal rent based on fixed 4% increase"
    )

    print("✓ test_compare_keeps_display_values_verbatim: PASS")


def test_compare_requires_at_least_two_leases():
    """A one-lease "comparison" is a caller bug, not a degenerate table."""
    for bad_input in ([LEASE_RETAIL], []):
        try:
            compare_leases(bad_input)
            raise AssertionError(f"expected ValueError for input of length {len(bad_input)}")
        except ValueError:
            pass

    print("✓ test_compare_requires_at_least_two_leases: PASS")


def test_benchmark_at_exactly_average_is_in_line():
    """A lease sitting exactly on every portfolio average is in line across the board."""
    subject = _lease(200, "exactly_average.pdf", rent_amount="$6,000.00",
                     cam_charges="$500.00", security_deposit="$12,000.00",
                     rent_escalation="4% annually")

    result = benchmark_lease(subject, _benchmark_portfolio())

    assert set(result.keys()) == {
        "rent_amount", "cam_charges", "security_deposit", "rent_escalation_pct"
    }
    for key, entry in result.items():
        assert entry["diff_pct"] == 0.0, f"{key} should be 0% off the average"
        assert entry["assessment"] == "in_line", f"{key} should be in_line"

    assert result["rent_amount"]["value"] == 6000.0
    assert result["rent_amount"]["portfolio_avg"] == 6000.0
    assert result["rent_escalation_pct"]["value"] == 4.0

    print("✓ test_benchmark_at_exactly_average_is_in_line: PASS")


def test_benchmark_twenty_percent_above():
    """20% above the average on every metric, with a signed positive diff."""
    subject = _lease(201, "premium.pdf", rent_amount="$7,200.00",
                     cam_charges="$600.00", security_deposit="$14,400.00",
                     rent_escalation="4.8% annually")

    result = benchmark_lease(subject, _benchmark_portfolio())

    assert result["rent_amount"]["diff_pct"] == 20.0
    assert result["rent_amount"]["assessment"] == "above_average"
    assert result["cam_charges"]["diff_pct"] == 20.0
    assert result["cam_charges"]["assessment"] == "above_average"
    assert result["security_deposit"]["diff_pct"] == 20.0
    assert result["security_deposit"]["assessment"] == "above_average"
    assert result["rent_escalation_pct"]["diff_pct"] == 20.0
    assert result["rent_escalation_pct"]["assessment"] == "above_average"

    print("✓ test_benchmark_twenty_percent_above: PASS")


def test_benchmark_twenty_percent_below():
    """20% below, with a signed negative diff."""
    subject = _lease(202, "bargain.pdf", rent_amount="$4,800.00",
                     cam_charges="$400.00", security_deposit="$9,600.00",
                     rent_escalation="3.2% annually")

    result = benchmark_lease(subject, _benchmark_portfolio())

    assert result["rent_amount"]["diff_pct"] == -20.0
    assert result["rent_amount"]["assessment"] == "below_average"
    assert result["cam_charges"]["diff_pct"] == -20.0
    assert result["cam_charges"]["assessment"] == "below_average"
    assert result["security_deposit"]["diff_pct"] == -20.0
    assert result["security_deposit"]["assessment"] == "below_average"
    assert result["rent_escalation_pct"]["diff_pct"] == -20.0
    assert result["rent_escalation_pct"]["assessment"] == "below_average"

    print("✓ test_benchmark_twenty_percent_below: PASS")


def test_benchmark_in_line_boundary_is_inclusive():
    """
    Exactly +/-10% is still "in line"; a hair past it is not. This is the
    only genuinely ambiguous point in the classification, so it is pinned
    down explicitly.
    """
    portfolio = _benchmark_portfolio()

    at_boundary = _lease(203, "boundary.pdf", rent_amount="$6,600.00")       # +10.0%
    below_boundary = _lease(204, "neg_boundary.pdf", rent_amount="$5,400.00")  # -10.0%
    past_boundary = _lease(205, "past.pdf", rent_amount="$6,700.00")         # +11.7%

    assert benchmark_lease(at_boundary, portfolio)["rent_amount"]["diff_pct"] == 10.0
    assert benchmark_lease(at_boundary, portfolio)["rent_amount"]["assessment"] == "in_line"
    assert benchmark_lease(below_boundary, portfolio)["rent_amount"]["assessment"] == "in_line"

    past = benchmark_lease(past_boundary, portfolio)["rent_amount"]
    assert past["diff_pct"] == 11.7
    assert past["assessment"] == "above_average"

    print("✓ test_benchmark_in_line_boundary_is_inclusive: PASS")


def test_benchmark_unknown_when_lease_value_missing():
    """
    A metric the subject lease doesn't have is reported as unknown with
    the key still present, so the caller renders a complete table.
    """
    result = benchmark_lease(LEASE_SUBLEASE, _benchmark_portfolio())

    assert result["rent_amount"]["assessment"] == "below_average"  # $2,000 vs $6,000
    assert result["rent_amount"]["diff_pct"] == -66.7

    for key in ("cam_charges", "security_deposit", "rent_escalation_pct"):
        assert result[key] == {
            "value": None, "portfolio_avg": None, "diff_pct": None, "assessment": "unknown"
        }, f"{key} should be the unknown shape"

    print("✓ test_benchmark_unknown_when_lease_value_missing: PASS")


def test_benchmark_unknown_when_portfolio_average_missing():
    """
    Even a fully-extracted lease can't be benchmarked against a portfolio
    that has no comparable data — including an empty portfolio, which must
    not crash or divide by zero.
    """
    for portfolio in ([], [_lease(300, "no_numbers.pdf", tenant="Nobody Inc.")]):
        result = benchmark_lease(LEASE_RETAIL, portfolio)
        for key, entry in result.items():
            assert entry["assessment"] == "unknown", f"{key} should be unknown"
            assert entry["diff_pct"] is None
            assert entry["portfolio_avg"] is None
            assert entry["value"] is None

    print("✓ test_benchmark_unknown_when_portfolio_average_missing: PASS")


def test_benchmark_year_table_escalation():
    """
    A lease whose escalation is a year-by-year dollar table still
    benchmarks: the implied rate (3000 -> 3120 -> 3244.80 = 4%/yr) is
    derived and then compared exactly like a stated percentage would be.
    """
    subject = _lease(206, "table_escalation.pdf",
                     rent_escalation="Year 1: $3,000.00; Year 2: $3,120.00; Year 3: $3,244.80")

    entry = benchmark_lease(subject, _benchmark_portfolio())["rent_escalation_pct"]

    assert entry["value"] == 4.0, "derived 4%/yr from the dollar table"
    assert entry["portfolio_avg"] == 4.0
    assert entry["assessment"] == "in_line"

    print("✓ test_benchmark_year_table_escalation: PASS")


def test_benchmark_does_not_special_case_self_inclusion():
    """
    Whether the subject lease is inside the comparison set is the caller's
    decision. Including it shifts the average (as it should) rather than
    being silently corrected for.
    """
    portfolio = _benchmark_portfolio()
    subject = _lease(207, "outlier.pdf", rent_amount="$12,000.00")

    excluded = benchmark_lease(subject, portfolio)["rent_amount"]
    included = benchmark_lease(subject, portfolio + [subject])["rent_amount"]

    assert excluded["portfolio_avg"] == 6000.0
    assert included["portfolio_avg"] == 7500.0, "self-inclusion must move the average"
    assert excluded["diff_pct"] == 100.0
    assert included["diff_pct"] == 60.0
    assert excluded["assessment"] == included["assessment"] == "above_average"

    print("✓ test_benchmark_does_not_special_case_self_inclusion: PASS")


if __name__ == "__main__":
    test_compare_two_leases()
    test_compare_three_leases_preserves_order_and_gaps()
    test_compare_keeps_display_values_verbatim()
    test_compare_requires_at_least_two_leases()
    test_benchmark_at_exactly_average_is_in_line()
    test_benchmark_twenty_percent_above()
    test_benchmark_twenty_percent_below()
    test_benchmark_in_line_boundary_is_inclusive()
    test_benchmark_unknown_when_lease_value_missing()
    test_benchmark_unknown_when_portfolio_average_missing()
    test_benchmark_year_table_escalation()
    test_benchmark_does_not_special_case_self_inclusion()
    print("\nAll comparison tests passed.")
