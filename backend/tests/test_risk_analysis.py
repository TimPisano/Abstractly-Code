"""
Tests for the risk/anomaly detection engine in app/risk_analysis.py.

These build lease field dicts directly (in the exact shape
FieldExtractor.extract_fields() produces) rather than going through a
PDF, so each rule can be driven to both sides of its threshold
deliberately — the point here is whether the *rules* fire correctly on
known inputs, which a real fixture PDF can only exercise incidentally.

Every assertion checks the flag's category and severity, and the
threshold cases also assert the actual numbers appear in the message,
since a flag that can't cite what it fired on is exactly what this
module is designed not to produce.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.risk_analysis import analyze_lease_risks


FIELD_NAMES = [
    "tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date",
    "property_address", "security_deposit", "cam_charges", "rent_escalation",
    "renewal_options", "permitted_use", "exclusivity_clause",
    "insurance_requirements", "default_cure_period", "square_footage",
]

CLEAN_VALUES = {
    "tenant": "Blue Sky Coffee Roasters, Inc.",
    "landlord": "Harborview Properties LLC",
    "rent_amount": "$6,250.00",
    "lease_start_date": "April 1, 2025",
    "lease_end_date": "March 31, 2030",
    "property_address": "1400 Market Street, Suite 200",
    "security_deposit": "$12,500.00",
    "cam_charges": "$850.00",
    "rent_escalation": "Year 1: $6,000.00; Year 2: $6,180.00; Year 3: $6,365.00",
    "renewal_options": "2 option(s) of 5 year(s) each; 180 days notice; "
                       "renewal rent based on then-prevailing fair market rate",
    "permitted_use": "retail coffee shop",
    "exclusivity_clause": "no other coffee retailer in the building",
    "insurance_requirements": "$2,000,000 per occurrence",
    "default_cure_period": "10 days after written notice",
    "square_footage": "2,400 sq ft",
}

CLEAN_PORTFOLIO = {
    "avg_rent": 6300.0,
    "avg_rent_per_sqft": 2.60,
    "avg_cam": 900.0,
    "avg_security_deposit": 12000.0,
    "avg_notice_days": 180.0,
    "avg_escalation_pct": 3.0,
    "lease_count": 8,
}


def make_lease(**overrides):
    """
    A fully-populated, unremarkable lease, with any field overridden by
    keyword. Pass `field=None` to simulate a not-found field (value,
    source and confidence all None, as the extractor produces).
    """
    fields = {}
    for name in FIELD_NAMES:
        value = overrides[name] if name in overrides else CLEAN_VALUES[name]
        if value is None:
            fields[name] = {"value": None, "source": None, "confidence": None}
        else:
            fields[name] = {
                "value": value,
                "source": {"page": 1, "quote": f"...{value}..."},
                "confidence": "high",
            }
    return fields


def categories(flags):
    return [flag["category"] for flag in flags]


def find(flags, category):
    return [flag for flag in flags if flag["category"] == category]


def test_clean_lease_has_no_flags():
    """A complete, internally-consistent, at-market lease should raise nothing."""
    flags = analyze_lease_risks(make_lease(), CLEAN_PORTFOLIO)
    assert flags == [], f"Expected no flags on a clean lease, got: {categories(flags)}"
    print("✓ test_clean_lease_has_no_flags: PASS")


def test_no_portfolio_context_skips_benchmark_checks():
    """Without a portfolio, comparison checks are skipped, not guessed at."""
    flags = analyze_lease_risks(make_lease(), None)
    assert flags == [], f"Expected no flags without portfolio context, got: {categories(flags)}"

    # Missing/None keys inside the context must also be tolerated.
    sparse = {"avg_rent": None, "avg_rent_per_sqft": None, "avg_notice_days": None,
              "lease_count": 1}
    flags = analyze_lease_risks(make_lease(), sparse)
    assert flags == [], f"Expected no flags with all-None portfolio values, got: {categories(flags)}"
    print("✓ test_no_portfolio_context_skips_benchmark_checks: PASS")


def test_below_market_rent_medium():
    """15% below the portfolio average is a medium flag, not a high one."""
    portfolio = dict(CLEAN_PORTFOLIO, avg_rent_per_sqft=None, avg_rent=6000.0)
    flags = analyze_lease_risks(
        make_lease(rent_amount="$5,100.00", square_footage=None), portfolio
    )
    below = find(flags, "below_market_rent")
    assert len(below) == 1, f"Expected one below_market_rent flag, got {len(below)}"
    assert below[0]["severity"] == "medium", below[0]["severity"]
    assert "15%" in below[0]["message"], below[0]["message"]
    assert "$5,100/mo" in below[0]["message"] and "$6,000/mo" in below[0]["message"], below[0]["message"]
    print("✓ test_below_market_rent_medium: PASS")
    print(f"    → {below[0]['message']}")


def test_below_market_rent_high():
    """More than 25% below average escalates to high severity."""
    portfolio = dict(CLEAN_PORTFOLIO, avg_rent_per_sqft=None, avg_rent=5850.0)
    flags = analyze_lease_risks(
        make_lease(rent_amount="$4,200.00", square_footage=None), portfolio
    )
    below = find(flags, "below_market_rent")
    assert len(below) == 1
    assert below[0]["severity"] == "high", below[0]["severity"]
    assert "28%" in below[0]["message"], below[0]["message"]
    print("✓ test_below_market_rent_high: PASS")
    print(f"    → {below[0]['message']}")


def test_below_market_prefers_per_sqft_comparison():
    """
    With square footage on both sides, the comparison is per-square-foot:
    this lease's raw rent is BELOW the portfolio's raw average but its
    rent per sq ft is well ABOVE the per-sq-ft average, so no flag.
    """
    portfolio = dict(CLEAN_PORTFOLIO, avg_rent=9000.0, avg_rent_per_sqft=2.00)
    flags = analyze_lease_risks(
        make_lease(rent_amount="$6,000.00", square_footage="1,200 sq ft"), portfolio
    )
    assert find(flags, "below_market_rent") == [], \
        "Per-sq-ft comparison should have won over the raw-rent comparison"

    # Same lease, below average on a per-sq-ft basis, does flag.
    portfolio = dict(CLEAN_PORTFOLIO, avg_rent=4000.0, avg_rent_per_sqft=7.00)
    flags = analyze_lease_risks(
        make_lease(rent_amount="$6,000.00", square_footage="1,200 sq ft"), portfolio
    )
    below = find(flags, "below_market_rent")
    assert len(below) == 1 and below[0]["severity"] == "high"
    assert "sq ft" in below[0]["message"], below[0]["message"]
    print("✓ test_below_market_prefers_per_sqft_comparison: PASS")
    print(f"    → {below[0]['message']}")


def test_missing_insurance_clause():
    flags = analyze_lease_risks(make_lease(insurance_requirements=None))
    missing = find(flags, "missing_clause")
    assert len(missing) == 1, f"Expected one missing_clause flag, got {categories(flags)}"
    assert missing[0]["field"] == "insurance_requirements"
    assert missing[0]["severity"] == "medium"
    assert "coverage amount" in missing[0]["explanation"]
    print("✓ test_missing_insurance_clause: PASS")


def test_missing_cure_period_clause():
    flags = analyze_lease_risks(make_lease(default_cure_period=None))
    missing = find(flags, "missing_clause")
    assert len(missing) == 1 and missing[0]["field"] == "default_cure_period"
    assert missing[0]["severity"] == "medium"
    print("✓ test_missing_cure_period_clause: PASS")


def test_missing_security_deposit_clause():
    flags = analyze_lease_risks(make_lease(security_deposit=None))
    missing = find(flags, "missing_clause")
    assert len(missing) == 1 and missing[0]["field"] == "security_deposit"
    assert missing[0]["severity"] == "medium"
    print("✓ test_missing_security_deposit_clause: PASS")


def test_all_three_clauses_missing():
    flags = analyze_lease_risks(
        make_lease(insurance_requirements=None, default_cure_period=None, security_deposit=None)
    )
    missing = find(flags, "missing_clause")
    assert len(missing) == 3, f"Expected 3 missing_clause flags, got {len(missing)}"
    assert [flag["field"] for flag in missing] == [
        "insurance_requirements", "default_cure_period", "security_deposit"
    ]
    print("✓ test_all_three_clauses_missing: PASS")


def test_notice_period_too_short():
    lease = make_lease(renewal_options="1 option(s) of 3 year(s) each; 15 days notice")
    flags = analyze_lease_risks(lease)
    notice = find(flags, "notice_period_outlier")
    assert len(notice) == 1, f"Expected one notice flag, got {len(notice)}"
    assert notice[0]["severity"] == "medium", notice[0]["severity"]
    assert "15 days" in notice[0]["message"] and "short" in notice[0]["message"]
    print("✓ test_notice_period_too_short: PASS")
    print(f"    → {notice[0]['message']}")


def test_notice_period_too_long():
    lease = make_lease(renewal_options="1 option(s) of 5 year(s) each; 365 days notice")
    flags = analyze_lease_risks(lease)
    notice = find(flags, "notice_period_outlier")
    assert len(notice) == 1
    assert notice[0]["severity"] == "low", notice[0]["severity"]
    assert "365 days" in notice[0]["message"] and "long" in notice[0]["message"]
    print("✓ test_notice_period_too_long: PASS")
    print(f"    → {notice[0]['message']}")


def test_notice_period_deviates_from_portfolio_average():
    """
    A 60-day window is within absolute bounds, so it only flags against
    the portfolio average (180 days) — a 67% deviation.
    """
    lease = make_lease(renewal_options="1 option(s) of 5 year(s) each; 60 days notice")
    flags = analyze_lease_risks(lease, CLEAN_PORTFOLIO)
    notice = find(flags, "notice_period_outlier")
    assert len(notice) == 1, f"Expected only the portfolio-deviation flag, got {len(notice)}"
    assert notice[0]["severity"] == "low"
    assert "portfolio average" in notice[0]["message"], notice[0]["message"]
    assert "67%" in notice[0]["message"], notice[0]["message"]
    print("✓ test_notice_period_deviates_from_portfolio_average: PASS")
    print(f"    → {notice[0]['message']}")


def test_no_escalation_on_long_term_lease():
    """A 5-year lease with no escalation clause is a one-sided-terms flag."""
    lease = make_lease(rent_escalation=None)
    flags = analyze_lease_risks(lease)
    one_sided = find(flags, "one_sided_terms")
    assert len(one_sided) == 1, f"Expected one one_sided_terms flag, got {len(one_sided)}"
    assert one_sided[0]["severity"] == "medium"
    assert one_sided[0]["field"] == "rent_escalation"
    assert "5-year" in one_sided[0]["message"], one_sided[0]["message"]
    print("✓ test_no_escalation_on_long_term_lease: PASS")
    print(f"    → {one_sided[0]['message']}")


def test_no_escalation_on_short_term_lease_is_not_flagged():
    """A 1-year lease with a flat rent is entirely normal."""
    lease = make_lease(
        rent_escalation=None,
        lease_start_date="April 1, 2025",
        lease_end_date="March 31, 2026",
    )
    flags = analyze_lease_risks(lease)
    assert find(flags, "one_sided_terms") == [], categories(flags)
    print("✓ test_no_escalation_on_short_term_lease_is_not_flagged: PASS")


def test_long_cure_period():
    lease = make_lease(default_cure_period="45 days after written notice")
    flags = analyze_lease_risks(lease)
    one_sided = find(flags, "one_sided_terms")
    assert len(one_sided) == 1
    assert one_sided[0]["severity"] == "medium"
    assert one_sided[0]["field"] == "default_cure_period"
    assert "45 days" in one_sided[0]["message"]
    print("✓ test_long_cure_period: PASS")
    print(f"    → {one_sided[0]['message']}")


def test_inconsistent_escalation_schedule():
    """
    Year 1->2 jumps ~8.3% but Year 2->3 only ~0.77%: a spread of ~7.6
    points, well past the high threshold.
    """
    lease = make_lease(
        rent_escalation="Year 1: $6,000.00; Year 2: $6,500.00; Year 3: $6,550.00"
    )
    flags = analyze_lease_risks(lease)
    escalation = find(flags, "escalation_inconsistency")
    assert len(escalation) == 1, f"Expected an escalation flag, got {categories(flags)}"
    assert escalation[0]["severity"] == "high", escalation[0]["severity"]
    assert "8.33%" in escalation[0]["message"] and "0.77%" in escalation[0]["message"], \
        escalation[0]["message"]
    assert "0.77%, 8.33%" in escalation[0]["explanation"] or \
           "8.33%, 0.77%" in escalation[0]["explanation"], escalation[0]["explanation"]
    print("✓ test_inconsistent_escalation_schedule: PASS")
    print(f"    → {escalation[0]['message']}")


def test_mildly_inconsistent_escalation_is_medium():
    """A ~3-point spread is medium, not high."""
    lease = make_lease(
        rent_escalation="Year 1: $6,000.00; Year 2: $6,120.00; Year 3: $6,395.00"
    )
    flags = analyze_lease_risks(lease)
    escalation = find(flags, "escalation_inconsistency")
    assert len(escalation) == 1
    assert escalation[0]["severity"] == "medium", escalation[0]["severity"]
    print("✓ test_mildly_inconsistent_escalation_is_medium: PASS")
    print(f"    → {escalation[0]['message']}")


def test_percentage_escalation_is_not_checked_for_consistency():
    """A bare "3% annually" has no internal schedule to contradict itself."""
    flags = analyze_lease_risks(make_lease(rent_escalation="3% annually"))
    assert find(flags, "escalation_inconsistency") == [], categories(flags)
    print("✓ test_percentage_escalation_is_not_checked_for_consistency: PASS")


def test_invalid_date_range():
    lease = make_lease(lease_start_date="April 1, 2025", lease_end_date="March 31, 2025")
    flags = analyze_lease_risks(lease)
    dates = find(flags, "date_inconsistency")
    assert len(dates) == 1, f"Expected one date_inconsistency flag, got {len(dates)}"
    assert dates[0]["severity"] == "high"
    assert "March 31, 2025" in dates[0]["message"] and "April 1, 2025" in dates[0]["message"]
    print("✓ test_invalid_date_range: PASS")
    print(f"    → {dates[0]['message']}")


def test_equal_start_and_end_dates_flagged():
    """A zero-length term is as broken as a negative one."""
    lease = make_lease(lease_start_date="April 1, 2025", lease_end_date="April 1, 2025")
    flags = analyze_lease_risks(lease)
    assert len(find(flags, "date_inconsistency")) == 1
    print("✓ test_equal_start_and_end_dates_flagged: PASS")


def test_cross_section_start_date_conflict():
    candidates = {
        "start": [
            {"value": "April 1, 2025", "source": {"page": 1, "quote": "shall commence on April 1, 2025"}},
            {"value": "May 15, 2025", "source": {"page": 4, "quote": "Commencement Date: May 15, 2025"}},
        ],
        "end": [
            {"value": "March 31, 2030", "source": {"page": 1, "quote": "shall expire March 31, 2030"}},
        ],
    }
    flags = analyze_lease_risks(make_lease(), None, candidates)
    dates = find(flags, "date_inconsistency")
    assert len(dates) == 1, f"Expected one conflict flag, got {len(dates)}"
    assert dates[0]["severity"] == "high"
    assert dates[0]["field"] == "lease_start_date"
    assert "April 1, 2025" in dates[0]["message"] and "May 15, 2025" in dates[0]["message"]
    assert "page 1" in dates[0]["explanation"] and "page 4" in dates[0]["explanation"], \
        dates[0]["explanation"]
    print("✓ test_cross_section_start_date_conflict: PASS")
    print(f"    → {dates[0]['message']}")


def test_same_date_written_two_ways_is_not_a_conflict():
    """Deduplication is on the parsed date, so re-statements agree."""
    candidates = {
        "start": [
            {"value": "April 1, 2025", "source": {"page": 1, "quote": "..."}},
            {"value": "04/01/2025", "source": {"page": 3, "quote": "..."}},
            {"value": "not a date at all", "source": {"page": 5, "quote": "..."}},
        ],
        "end": [],
    }
    flags = analyze_lease_risks(make_lease(), None, candidates)
    assert find(flags, "date_inconsistency") == [], categories(flags)
    print("✓ test_same_date_written_two_ways_is_not_a_conflict: PASS")


def test_missing_date_candidates_skips_check():
    """No candidates supplied means the check is skipped, not errored."""
    flags = analyze_lease_risks(make_lease(), None, None)
    assert flags == []
    flags = analyze_lease_risks(make_lease(), None, {})
    assert flags == []
    print("✓ test_missing_date_candidates_skips_check: PASS")


def test_flags_sorted_severity_first():
    """
    A lease that trips checks across all three severities must come back
    high -> medium -> low, with check order preserved inside each tier.
    """
    lease = make_lease(
        rent_amount="$3,000.00",
        square_footage=None,
        insurance_requirements=None,
        renewal_options="1 option(s) of 5 year(s) each; 300 days notice",
        rent_escalation="Year 1: $6,000.00; Year 2: $6,500.00; Year 3: $6,550.00",
    )
    portfolio = dict(CLEAN_PORTFOLIO, avg_rent_per_sqft=None, avg_rent=6000.0)
    flags = analyze_lease_risks(lease, portfolio)

    severities = [flag["severity"] for flag in flags]
    ranks = {"high": 0, "medium": 1, "low": 2}
    assert severities == sorted(severities, key=lambda s: ranks[s]), severities
    assert severities[0] == "high" and severities[-1] == "low", severities
    assert categories(flags)[:2] == ["below_market_rent", "escalation_inconsistency"], \
        categories(flags)
    assert "missing_clause" in categories(flags)
    print("✓ test_flags_sorted_severity_first: PASS")
    for flag in flags:
        print(f"    [{flag['severity']:>6}] {flag['category']}: {flag['message']}")


def test_empty_lease_fields_do_not_crash():
    """An all-not-found lease should still analyze, flagging what's absent."""
    empty = {name: {"value": None, "source": None, "confidence": None} for name in FIELD_NAMES}
    flags = analyze_lease_risks(empty, CLEAN_PORTFOLIO)
    assert len(find(flags, "missing_clause")) == 3
    assert find(flags, "below_market_rent") == [], "No rent value means no rent comparison"

    # A dict missing keys entirely (not just with None values) must also work.
    flags = analyze_lease_risks({}, CLEAN_PORTFOLIO)
    assert len(find(flags, "missing_clause")) == 3
    print("✓ test_empty_lease_fields_do_not_crash: PASS")


def test_every_flag_has_the_full_contract_shape():
    """Downstream modules index these keys directly, so all five must exist."""
    lease = make_lease(
        rent_amount="$3,000.00", square_footage=None, insurance_requirements=None,
        default_cure_period="60 days after written notice",
        lease_start_date="April 1, 2025", lease_end_date="March 1, 2025",
    )
    portfolio = dict(CLEAN_PORTFOLIO, avg_rent_per_sqft=None, avg_rent=6000.0)
    flags = analyze_lease_risks(lease, portfolio)
    assert flags, "Expected this lease to raise flags"
    for flag in flags:
        assert set(flag) == {"severity", "category", "field", "message", "explanation"}, set(flag)
        assert flag["severity"] in ("high", "medium", "low")
        assert flag["message"] and "\n" not in flag["message"], flag["message"]
        assert len(flag["explanation"]) > len(flag["message"]), flag["category"]
    print(f"✓ test_every_flag_has_the_full_contract_shape: PASS ({len(flags)} flags checked)")


if __name__ == "__main__":
    test_clean_lease_has_no_flags()
    test_no_portfolio_context_skips_benchmark_checks()
    test_below_market_rent_medium()
    test_below_market_rent_high()
    test_below_market_prefers_per_sqft_comparison()
    test_missing_insurance_clause()
    test_missing_cure_period_clause()
    test_missing_security_deposit_clause()
    test_all_three_clauses_missing()
    test_notice_period_too_short()
    test_notice_period_too_long()
    test_notice_period_deviates_from_portfolio_average()
    test_no_escalation_on_long_term_lease()
    test_no_escalation_on_short_term_lease_is_not_flagged()
    test_long_cure_period()
    test_inconsistent_escalation_schedule()
    test_mildly_inconsistent_escalation_is_medium()
    test_percentage_escalation_is_not_checked_for_consistency()
    test_invalid_date_range()
    test_equal_start_and_end_dates_flagged()
    test_cross_section_start_date_conflict()
    test_same_date_written_two_ways_is_not_a_conflict()
    test_missing_date_candidates_skips_check()
    test_flags_sorted_severity_first()
    test_empty_lease_fields_do_not_crash()
    test_every_flag_has_the_full_contract_shape()
    print("\nAll risk analysis tests passed.")
