"""
Tests for portfolio-wide metrics and the expiration timeline.

Fixtures are hand-built lease records rather than PDFs run through the
extractor: the aggregation logic's job is to be correct given a known set
of field values, and decoupling it from extraction accuracy means a
regression here is unambiguously a math/bucketing bug rather than a
pattern-matching one.

The fixture set is deliberately uneven — one complete lease, one missing
a single clause, one with no end date at all, one very sparse sublease,
and one using a year-by-year escalation table instead of a flat
percentage — because the interesting behavior in this module is what it
does with the gaps, not with the happy path.

Every timeline test passes an explicit `reference_date` so the buckets
are reproducible; relying on today's date would make these tests start
failing on their own as fixtures aged past their expiration dates.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.portfolio import (
    FIELD_NAMES,
    compute_expiration_alerts,
    compute_expiration_timeline,
    compute_portfolio_metrics,
    portfolio_context_for_risk_analysis,
)


# The date every timeline assertion below is measured from.
REFERENCE_DATE = date(2026, 1, 15)


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
    """
    A lease record with all 15 fields present in the extracted_fields
    dict — any field not passed in is explicitly "not found" (None),
    mirroring what the extractor actually produces rather than omitting
    the key.
    """
    return {
        "id": lease_id,
        "filename": filename,
        "uploaded_at": "2026-01-10T09:00:00",
        "document_type": "lease",
        "base_lease_id": None,
        "amendment_count": 0,
        "extracted_fields": {name: _field(values.get(name)) for name in FIELD_NAMES},
    }


# Complete lease: every field found. Rent $6,000 over 2,400 sq ft = $2.50/sqft.
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

# Missing only the exclusivity clause. $9,000 over 3,000 sq ft = $3.00/sqft.
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

# No end date (unknown expiration), no square footage, no CAM, and a
# year-by-year escalation table instead of a flat percentage — the implied
# rate is a clean 4%/yr.
LEASE_WAREHOUSE = _lease(
    3, "warehouse_lease.pdf",
    tenant="Northgate Logistics Co.",
    landlord="Pinebrook Industrial Trust",
    rent_amount="$3,000.00",
    lease_start_date="July 1, 2023",
    property_address="88 Riverside Industrial Way, Westbrook, ME",
    security_deposit="$6,000.00",
    rent_escalation="Year 1: $3,000.00; Year 2: $3,120.00; Year 3: $3,244.80",
    permitted_use="warehousing and distribution",
    insurance_requirements="$3,000,000 per occurrence",
    default_cure_period="15 days after written notice",
)

# Sparse casual sublease: only the basics were found. Already expired
# relative to REFERENCE_DATE.
LEASE_SUBLEASE = _lease(
    4, "casual_sublease.pdf",
    tenant="Alex Chen",
    landlord="Jordan Blake",
    rent_amount="$2,000.00",
    lease_start_date="July 1, 2024",
    lease_end_date="June 30, 2025",
    property_address="17 Elm Street, Apt 2, Portland, ME",
)

# Complete lease, expiring far out. $12,000 over 4,000 sq ft = $3.00/sqft.
LEASE_MEDICAL = _lease(
    5, "medical_office_lease.pdf",
    tenant="Casco Bay Dental Partners, P.A.",
    landlord="Seaside Medical Holdings LLC",
    rent_amount="$12,000.00",
    lease_start_date="August 1, 2023",
    lease_end_date="August 1, 2028",
    property_address="9 Marginal Way, Suite 200, Portland, ME",
    security_deposit="$24,000.00",
    cam_charges="$1,600.00",
    rent_escalation="2% annually",
    renewal_options="2 option(s) of 5 year(s) each; 120 days notice; renewal rent based on then-prevailing fair market rate",
    permitted_use="dental practice and related medical office use",
    exclusivity_clause="No other dental practice in the building",
    insurance_requirements="$5,000,000 per occurrence",
    default_cure_period="20 days after written notice",
    square_footage="4,000 sq ft",
)

ALL_LEASES = [LEASE_RETAIL, LEASE_OFFICE, LEASE_WAREHOUSE, LEASE_SUBLEASE, LEASE_MEDICAL]


def test_portfolio_totals_and_averages():
    """
    Totals and averages against hand-computed values.

    Rents: 6000 + 9000 + 3000 + 2000 + 12000 = 32000 over 5 leases.
    CAM:   800 + 1200 + 1600 = 3600 over the 3 leases that have it —
           critically NOT over all 5, which would give 720.
    """
    metrics = compute_portfolio_metrics(ALL_LEASES)

    assert metrics["lease_count"] == 5
    assert metrics["total_monthly_rent"] == 32000.0
    assert metrics["avg_monthly_rent"] == 6400.0

    assert metrics["total_cam_exposure"] == 3600.0
    assert metrics["avg_cam"] == 1200.0, "CAM average must skip leases with no CAM clause"

    # Deposits: (12000 + 18000 + 6000 + 24000) / 4 leases that have one.
    assert metrics["avg_security_deposit"] == 15000.0

    # Square footage only on 3 leases: 2400 + 3000 + 4000.
    assert metrics["total_square_footage"] == 9400.0

    # Per-sqft only where BOTH rent and sqft exist: 2.50, 3.00, 3.00.
    assert metrics["avg_rent_per_sqft"] == 2.83

    # Escalation: 3% + 5% + 4% (derived from the year table) + 2%, over 4.
    assert metrics["avg_escalation_pct"] == 3.5

    # Notice days: (180 + 90 + 120) / 3 leases with renewal options.
    assert metrics["avg_notice_days"] == 130.0

    print("✓ test_portfolio_totals_and_averages: PASS")


def test_year_table_escalation_contributes_a_derived_rate():
    """
    A lease whose escalation is a year-by-year dollar table has no stated
    percentage, but still implies one (3000 -> 3120 -> 3244.80 = 4%/yr).
    It must contribute that derived rate rather than being skipped.
    """
    table_only = compute_portfolio_metrics([LEASE_WAREHOUSE])
    assert table_only["avg_escalation_pct"] == 4.0

    flat_only = compute_portfolio_metrics([LEASE_RETAIL])
    assert flat_only["avg_escalation_pct"] == 3.0

    print("✓ test_year_table_escalation_contributes_a_derived_rate: PASS")


def test_fields_missing_count_is_accurate():
    """
    Every one of the 15 fields must be reported, including fields no lease
    is missing (count 0), so the UI can show a complete coverage picture.
    """
    metrics = compute_portfolio_metrics(ALL_LEASES)
    missing = metrics["fields_missing_count"]

    assert set(missing.keys()) == set(FIELD_NAMES), "all 15 fields must be reported"

    expected = {
        "tenant": 0,
        "landlord": 0,
        "rent_amount": 0,
        "lease_start_date": 0,
        "lease_end_date": 1,            # warehouse
        "property_address": 0,
        "security_deposit": 1,          # sublease
        "cam_charges": 2,               # warehouse, sublease
        "rent_escalation": 1,           # sublease
        "renewal_options": 2,           # warehouse, sublease
        "permitted_use": 1,             # sublease
        "exclusivity_clause": 3,        # office, warehouse, sublease
        "insurance_requirements": 1,    # sublease
        "default_cure_period": 1,       # sublease
        "square_footage": 2,            # warehouse, sublease
    }
    assert missing == expected, f"got {missing}"

    print("✓ test_fields_missing_count_is_accurate: PASS")


def test_missing_fields_do_not_dilute_averages():
    """
    The core guarantee: a lease with no CAM clause must not be treated as
    $0 CAM. Adding a CAM-less lease to a portfolio must leave the CAM
    average untouched.
    """
    with_cam_only = compute_portfolio_metrics([LEASE_RETAIL])
    plus_cam_less = compute_portfolio_metrics([LEASE_RETAIL, LEASE_SUBLEASE])

    assert with_cam_only["avg_cam"] == 800.0
    assert plus_cam_less["avg_cam"] == 800.0, "a CAM-less lease must not drag the average toward zero"
    assert plus_cam_less["avg_monthly_rent"] == 4000.0, "rent average still counts both leases"

    print("✓ test_missing_fields_do_not_dilute_averages: PASS")


def test_empty_portfolio_does_not_crash():
    """An empty portfolio reports unknown (None), not a fabricated 0.0."""
    metrics = compute_portfolio_metrics([])

    assert metrics["lease_count"] == 0
    for key in ("total_monthly_rent", "avg_monthly_rent", "avg_rent_per_sqft",
                "total_cam_exposure", "avg_cam", "avg_security_deposit",
                "avg_escalation_pct", "avg_notice_days", "total_square_footage"):
        assert metrics[key] is None, f"{key} should be None for an empty portfolio"

    assert metrics["fields_missing_count"] == {name: 0 for name in FIELD_NAMES}

    timeline = compute_expiration_timeline([], reference_date=REFERENCE_DATE)
    assert all(bucket == [] for bucket in timeline.values())

    context = portfolio_context_for_risk_analysis([])
    assert context["lease_count"] == 0
    assert context["avg_rent"] is None

    print("✓ test_empty_portfolio_does_not_crash: PASS")


def test_lease_with_no_parseable_values_yields_none_not_zero():
    """
    A portfolio of one totally unextracted lease has an unknown average
    rent, not $0.00 — reporting 0.0 would read as a real finding.
    """
    blank = _lease(99, "unreadable.pdf")
    metrics = compute_portfolio_metrics([blank])

    assert metrics["lease_count"] == 1
    assert metrics["total_monthly_rent"] is None
    assert metrics["avg_monthly_rent"] is None
    assert metrics["fields_missing_count"]["tenant"] == 1

    print("✓ test_lease_with_no_parseable_values_yields_none_not_zero: PASS")


def test_risk_analysis_context_shape_and_values():
    """
    The risk-analysis contract is a renamed/trimmed view of the same
    numbers — it must not disagree with the dashboard's averages.
    """
    context = portfolio_context_for_risk_analysis(ALL_LEASES)
    metrics = compute_portfolio_metrics(ALL_LEASES)

    assert set(context.keys()) == {
        "avg_rent", "avg_rent_per_sqft", "avg_cam", "avg_security_deposit",
        "avg_notice_days", "avg_escalation_pct", "lease_count",
    }

    assert context["avg_rent"] == metrics["avg_monthly_rent"] == 6400.0
    assert context["avg_rent_per_sqft"] == metrics["avg_rent_per_sqft"] == 2.83
    assert context["avg_cam"] == metrics["avg_cam"] == 1200.0
    assert context["avg_security_deposit"] == metrics["avg_security_deposit"] == 15000.0
    assert context["avg_notice_days"] == metrics["avg_notice_days"] == 130.0
    assert context["avg_escalation_pct"] == metrics["avg_escalation_pct"] == 3.5
    assert context["lease_count"] == 5

    print("✓ test_risk_analysis_context_shape_and_values: PASS")


def test_expiration_timeline_buckets():
    """
    Buckets measured from a fixed 2026-01-15 reference date:
      retail   2026-03-31 ->  +2.5 months  -> 0-6
      office   2026-12-31 -> +11.5 months  -> 6-12
      flex     2027-06-30 -> +17.4 months  -> 12-24
      medical  2028-08-01 -> +30.5 months  -> 24+
      sublease 2025-06-30 ->  -6.5 months  -> already expired
      warehouse (no end date)              -> unknown
    """
    flex = _lease(6, "flex_space_lease.pdf",
                  tenant="Kestrel Design Studio",
                  rent_amount="$4,500.00",
                  lease_end_date="June 30, 2027")

    timeline = compute_expiration_timeline(ALL_LEASES + [flex], reference_date=REFERENCE_DATE)

    def ids(bucket):
        return [entry["lease_id"] for entry in timeline[bucket]]

    assert ids("expiring_0_6_months") == [1]
    assert ids("expiring_6_12_months") == [2]
    assert ids("expiring_12_24_months") == [6]
    assert ids("expiring_24_plus_months") == [5]
    assert ids("already_expired") == [4]
    assert ids("unknown_expiration") == [3]

    assert timeline["expiring_0_6_months"][0]["months_remaining"] == 2.5
    assert timeline["expiring_6_12_months"][0]["months_remaining"] == 11.5
    assert timeline["expiring_12_24_months"][0]["months_remaining"] == 17.4
    assert timeline["expiring_24_plus_months"][0]["months_remaining"] == 30.5
    assert timeline["already_expired"][0]["months_remaining"] == -6.5

    print("✓ test_expiration_timeline_buckets: PASS")


def test_unknown_expiration_entries_stay_useful():
    """
    A lease whose end date didn't parse is still listed with its filename
    and tenant so a human can go chase it down — months_remaining is None,
    and it is never silently dropped from the timeline.
    """
    unparseable = _lease(7, "aardvark_lease.pdf",
                         tenant="Aardvark Supply Co.",
                         lease_end_date="upon mutual agreement")

    timeline = compute_expiration_timeline(
        [LEASE_WAREHOUSE, unparseable], reference_date=REFERENCE_DATE
    )
    unknown = timeline["unknown_expiration"]

    assert len(unknown) == 2, "both a missing and an unparseable end date belong here"
    # Sorted by filename: "aardvark_lease.pdf" before "warehouse_lease.pdf".
    assert [entry["filename"] for entry in unknown] == ["aardvark_lease.pdf", "warehouse_lease.pdf"]
    assert unknown[0]["tenant"] == "Aardvark Supply Co."
    assert unknown[0]["lease_end_date"] == "upon mutual agreement"
    assert all(entry["months_remaining"] is None for entry in unknown)

    print("✓ test_unknown_expiration_entries_stay_useful: PASS")


def test_timeline_buckets_sorted_soonest_first():
    """Within a bucket, the most urgent lease must come first."""
    soon = _lease(10, "soon_lease.pdf", tenant="Soon Corp", lease_end_date="February 10, 2026")
    later = _lease(11, "later_lease.pdf", tenant="Later Corp", lease_end_date="May 1, 2026")

    timeline = compute_expiration_timeline(
        [LEASE_RETAIL, later, soon], reference_date=REFERENCE_DATE
    )
    bucket = timeline["expiring_0_6_months"]

    assert [entry["lease_id"] for entry in bucket] == [10, 1, 11]
    assert bucket[0]["months_remaining"] == 0.9
    assert bucket == sorted(bucket, key=lambda e: e["months_remaining"])

    print("✓ test_timeline_buckets_sorted_soonest_first: PASS")


def test_timeline_entry_shape():
    """Each entry carries enough to render a row without re-querying the DB."""
    timeline = compute_expiration_timeline(ALL_LEASES, reference_date=REFERENCE_DATE)
    entry = timeline["expiring_0_6_months"][0]

    assert set(entry.keys()) == {
        "lease_id", "filename", "display_name", "tenant", "lease_end_date", "months_remaining"
    }
    assert entry["lease_id"] == 1
    assert entry["filename"] == "retail_lease.pdf"
    # LEASE_RETAIL's fixture never sets display_name, so it must fall
    # back to the filename -- same rule _timeline_entry itself applies.
    assert entry["display_name"] == "retail_lease.pdf"
    assert entry["tenant"] == "Blue Sky Coffee Roasters, Inc."
    assert entry["lease_end_date"] == "March 31, 2026"

    print("✓ test_timeline_entry_shape: PASS")


def test_expiring_today_counts_as_active():
    """
    A lease ending exactly on the reference date has 0 months remaining
    and belongs in the most-urgent active bucket, not already-expired.
    """
    today_lease = _lease(12, "today_lease.pdf", lease_end_date="January 15, 2026")
    timeline = compute_expiration_timeline([today_lease], reference_date=REFERENCE_DATE)

    assert [e["lease_id"] for e in timeline["expiring_0_6_months"]] == [12]
    assert timeline["already_expired"] == []
    assert timeline["expiring_0_6_months"][0]["months_remaining"] == 0.0

    print("✓ test_expiring_today_counts_as_active: PASS")


def _days_from_reference(n):
    """MM/DD/YYYY string n days from REFERENCE_DATE -- parse_date-friendly, and avoids hand-picked calendar dates going stale or being miscounted."""
    return (REFERENCE_DATE + timedelta(days=n)).strftime("%m/%d/%Y")


def test_expiration_alerts_buckets_by_30_60_90():
    within_30 = _lease(20, "within_30.pdf", tenant="ThirtyCo", lease_end_date=_days_from_reference(20))
    within_60 = _lease(21, "within_60.pdf", tenant="SixtyCo", lease_end_date=_days_from_reference(45))
    within_90 = _lease(22, "within_90.pdf", tenant="NinetyCo", lease_end_date=_days_from_reference(85))
    outside_90 = _lease(23, "outside_90.pdf", tenant="TooFarCo", lease_end_date=_days_from_reference(120))
    already_expired = _lease(24, "expired.pdf", tenant="ExpiredCo", lease_end_date=_days_from_reference(-5))

    alerts = compute_expiration_alerts(
        [within_30, within_60, within_90, outside_90, already_expired],
        reference_date=REFERENCE_DATE,
    )
    by_id = {e["lease_id"]: e for e in alerts["expiring"]}

    assert set(by_id.keys()) == {20, 21, 22}, "only leases within 90 days, excluding already-expired, belong here"
    assert by_id[20]["bucket"] == "30"
    assert by_id[21]["bucket"] == "60"
    assert by_id[22]["bucket"] == "90"
    assert by_id[20]["days_remaining"] == 20
    print("✓ test_expiration_alerts_buckets_by_30_60_90: PASS")


def test_expiration_alerts_sorted_soonest_first():
    soon = _lease(25, "soon.pdf", tenant="SoonCo", lease_end_date=_days_from_reference(10))
    mid = _lease(26, "mid.pdf", tenant="MidCo", lease_end_date=_days_from_reference(50))
    later = _lease(27, "later.pdf", tenant="LaterCo", lease_end_date=_days_from_reference(80))

    alerts = compute_expiration_alerts([later, soon, mid], reference_date=REFERENCE_DATE)
    assert [e["lease_id"] for e in alerts["expiring"]] == [25, 26, 27]
    print("✓ test_expiration_alerts_sorted_soonest_first: PASS")


def test_renewal_deadline_kept_separate_from_expiration_and_can_land_in_different_bucket():
    """
    A lease ending in 100 days (outside the 90-day expiring window) with
    a 40-day notice period has its renewal deadline 60 days out -- inside
    the window. It must show up in renewal_deadlines but NOT expiring,
    proving the two lists are computed independently, not one derived
    from the other.
    """
    lease = _lease(
        30, "far_out_but_deadline_soon.pdf", tenant="DeadlineCo",
        lease_end_date=_days_from_reference(100),
        renewal_options="1 option(s) of 5 year(s) each; 40 days notice; renewal rent based on fair market rate",
    )
    alerts = compute_expiration_alerts([lease], reference_date=REFERENCE_DATE)

    assert alerts["expiring"] == []
    assert len(alerts["renewal_deadlines"]) == 1
    entry = alerts["renewal_deadlines"][0]
    assert entry["lease_id"] == 30
    assert entry["days_remaining"] == 60
    assert entry["bucket"] == "60"
    assert entry["notice_days"] == 40
    assert date.fromisoformat(entry["renewal_deadline"]) == REFERENCE_DATE + timedelta(days=60)
    print("✓ test_renewal_deadline_kept_separate_from_expiration_and_can_land_in_different_bucket: PASS")


def test_missed_renewal_deadline_flagged_as_overdue_not_dropped():
    """
    A lease whose renewal notice window has already closed (but whose
    lease term hasn't ended yet) is the single most actionable flag this
    function can raise -- it must still appear, bucketed "overdue" with
    a negative days_remaining, not silently disappear once the date
    passes.
    """
    lease = _lease(
        31, "missed_deadline.pdf", tenant="OverdueCo",
        lease_end_date=_days_from_reference(200),
        renewal_options="1 option(s) of 10 year(s) each; 210 days notice; renewal rent based on fair market rate",
    )
    alerts = compute_expiration_alerts([lease], reference_date=REFERENCE_DATE)

    assert len(alerts["renewal_deadlines"]) == 1
    entry = alerts["renewal_deadlines"][0]
    assert entry["bucket"] == "overdue"
    assert entry["days_remaining"] == -10
    print("✓ test_missed_renewal_deadline_flagged_as_overdue_not_dropped: PASS")


def test_expired_lease_excluded_from_renewal_deadlines_even_if_notice_unparsed_would_match():
    """Once the lease itself has fully expired, there's nothing left to renew -- excluded regardless of notice period math."""
    lease = _lease(
        32, "fully_expired.pdf", tenant="GoneCo",
        lease_end_date=_days_from_reference(-1),
        renewal_options="1 option(s) of 5 year(s) each; 30 days notice; renewal rent based on fair market rate",
    )
    alerts = compute_expiration_alerts([lease], reference_date=REFERENCE_DATE)
    assert alerts["renewal_deadlines"] == []
    assert alerts["expiring"] == []
    print("✓ test_expired_lease_excluded_from_renewal_deadlines_even_if_notice_unparsed_would_match: PASS")


def test_renewal_options_with_no_parseable_notice_days_excluded_silently():
    """A renewal_options string with no '<N> days notice' phrase can't produce a deadline -- excluded, not a crash or a bogus 0-day deadline."""
    lease = _lease(
        33, "no_notice_period.pdf", tenant="VagueCo",
        lease_end_date=_days_from_reference(20),
        renewal_options="Renewal terms to be negotiated at time of exercise",
    )
    alerts = compute_expiration_alerts([lease], reference_date=REFERENCE_DATE)
    assert alerts["renewal_deadlines"] == []
    assert [e["lease_id"] for e in alerts["expiring"]] == [33]
    print("✓ test_renewal_options_with_no_parseable_notice_days_excluded_silently: PASS")


def test_lease_can_appear_in_both_expiring_and_renewal_deadlines():
    lease = _lease(
        34, "both_lists.pdf", tenant="BothCo",
        lease_end_date=_days_from_reference(15),
        renewal_options="1 option(s) of 5 year(s) each; 10 days notice; renewal rent based on fair market rate",
    )
    alerts = compute_expiration_alerts([lease], reference_date=REFERENCE_DATE)
    assert [e["lease_id"] for e in alerts["expiring"]] == [34]
    assert [e["lease_id"] for e in alerts["renewal_deadlines"]] == [34]
    print("✓ test_lease_can_appear_in_both_expiring_and_renewal_deadlines: PASS")


if __name__ == "__main__":
    test_portfolio_totals_and_averages()
    test_year_table_escalation_contributes_a_derived_rate()
    test_fields_missing_count_is_accurate()
    test_missing_fields_do_not_dilute_averages()
    test_empty_portfolio_does_not_crash()
    test_lease_with_no_parseable_values_yields_none_not_zero()
    test_risk_analysis_context_shape_and_values()
    test_expiration_timeline_buckets()
    test_unknown_expiration_entries_stay_useful()
    test_timeline_buckets_sorted_soonest_first()
    test_timeline_entry_shape()
    test_expiring_today_counts_as_active()
    test_expiration_alerts_buckets_by_30_60_90()
    test_expiration_alerts_sorted_soonest_first()
    test_renewal_deadline_kept_separate_from_expiration_and_can_land_in_different_bucket()
    test_missed_renewal_deadline_flagged_as_overdue_not_dropped()
    test_expired_lease_excluded_from_renewal_deadlines_even_if_notice_unparsed_would_match()
    test_renewal_options_with_no_parseable_notice_days_excluded_silently()
    test_lease_can_appear_in_both_expiring_and_renewal_deadlines()
    print("\nAll portfolio tests passed.")
