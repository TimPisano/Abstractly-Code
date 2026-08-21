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
    DAYS_PER_YEAR,
    FIELD_NAMES,
    ROLLOVER_YEAR_1_HIGH_RISK_PCT,
    ROLLOVER_YEAR_1_MODERATE_RISK_PCT,
    compute_cross_lease_mismatches,
    compute_expiration_alerts,
    compute_expiration_timeline,
    compute_lease_confidence_summary,
    compute_loss_to_lease,
    compute_portfolio_confidence_summary,
    compute_portfolio_metrics,
    compute_rent_roll_reconciliation,
    compute_rent_variance_outliers,
    compute_rollover_schedule,
    compute_t12_reconciliation,
    compute_tenant_concentration,
    compute_walt,
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


def test_lease_confidence_summary_counts_every_tier():
    import copy
    # LEASE_RETAIL has all 15 fields populated, confidence "high" throughout
    # (the _field() default) -- deep-copied and mutated so each tier,
    # not_found, and a validation_note can each be driven deliberately.
    lease = copy.deepcopy(LEASE_RETAIL)
    lease["extracted_fields"]["landlord"]["confidence"] = "medium"
    lease["extracted_fields"]["cam_charges"]["confidence"] = "low"
    lease["extracted_fields"]["rent_amount"]["validation_note"] = "Rent amount of $5,000.00 is outside the expected range."
    lease["extracted_fields"]["lease_start_date"] = {"value": None, "source": None, "confidence": None}

    summary = compute_lease_confidence_summary(lease)

    assert summary["total_fields"] == 15
    assert summary["medium"] == 1
    assert summary["low"] == 1
    assert summary["not_found"] == 1
    assert summary["high"] == 12
    assert summary["flagged_for_review"] == 1
    assert summary["flagged_fields"] == ["rent_amount"]
    print("✓ test_lease_confidence_summary_counts_every_tier: PASS")


def test_lease_confidence_summary_all_not_found():
    lease = _lease(61, "blank.pdf")  # no field values passed -- every field defaults to not-found
    summary = compute_lease_confidence_summary(lease)
    assert summary["not_found"] == 15
    assert summary["high"] == 0 and summary["medium"] == 0 and summary["low"] == 0
    assert summary["flagged_for_review"] == 0
    print("✓ test_lease_confidence_summary_all_not_found: PASS")


def test_portfolio_confidence_summary_aggregates_across_leases():
    import copy
    lease_a = copy.deepcopy(LEASE_RETAIL)
    lease_a["id"] = 62
    lease_a["extracted_fields"]["landlord"]["confidence"] = "medium"

    lease_b = copy.deepcopy(LEASE_RETAIL)
    lease_b["id"] = 63
    lease_b["extracted_fields"]["cam_charges"]["confidence"] = "low"
    lease_b["extracted_fields"]["rent_amount"]["validation_note"] = "outside expected range"

    summary = compute_portfolio_confidence_summary([lease_a, lease_b])

    assert summary["lease_count"] == 2
    assert summary["total_fields"] == 30
    assert summary["medium"] == 1
    assert summary["low"] == 1
    assert summary["high"] == 28
    assert summary["flagged_for_review"] == 1
    assert summary["extracted_fields"] == 30, "both fixtures have every field found -- none should be not_found"
    assert summary["high_confidence_pct"] == round(28 / 30 * 100, 1)
    print("✓ test_portfolio_confidence_summary_aggregates_across_leases: PASS")


def test_portfolio_confidence_summary_empty_portfolio_does_not_crash():
    summary = compute_portfolio_confidence_summary([])
    assert summary["lease_count"] == 0
    assert summary["total_fields"] == 0
    assert summary["high_confidence_pct"] is None, "0/0 must report unknown, not a fabricated 0% or 100%"
    print("✓ test_portfolio_confidence_summary_empty_portfolio_does_not_crash: PASS")


def test_rent_variance_outliers_flags_both_directions():
    # avg rent/sqft across these three: (2.00 + 2.10 + 5.00) / 3 = 3.03
    cheap = _lease(70, "cheap.pdf", tenant="Cheap Co.", rent_amount="$2,000.00", square_footage="1,000 sq ft")  # $2.00/sqft
    typical = _lease(71, "typical.pdf", tenant="Typical Co.", rent_amount="$2,100.00", square_footage="1,000 sq ft")  # $2.10/sqft
    expensive = _lease(72, "expensive.pdf", tenant="Expensive Co.", rent_amount="$5,000.00", square_footage="1,000 sq ft")  # $5.00/sqft

    outliers = compute_rent_variance_outliers([cheap, typical, expensive])
    by_id = {o["lease_id"]: o for o in outliers}

    assert 72 in by_id and by_id[72]["direction"] == "above"
    assert 70 in by_id and by_id[70]["direction"] == "below"
    # "typical" (only ~30% below avg... let's just confirm it's not the most extreme)
    assert outliers[0]["lease_id"] == 72, "most extreme deviation must sort first"
    print("✓ test_rent_variance_outliers_flags_both_directions: PASS")


def test_rent_variance_outliers_excludes_leases_within_normal_range():
    close_a = _lease(73, "a.pdf", rent_amount="$3,000.00", square_footage="1,000 sq ft")  # $3.00/sqft
    close_b = _lease(74, "b.pdf", rent_amount="$3,200.00", square_footage="1,000 sq ft")  # $3.20/sqft, ~6.5% above avg of $3.10
    outliers = compute_rent_variance_outliers([close_a, close_b])
    assert outliers == []
    print("✓ test_rent_variance_outliers_excludes_leases_within_normal_range: PASS")


def test_rent_variance_outliers_skips_leases_without_sqft():
    no_sqft = _lease(75, "no_sqft.pdf", rent_amount="$50,000.00")  # would be a huge outlier if raw rent were compared
    normal = _lease(76, "normal.pdf", rent_amount="$3,000.00", square_footage="1,000 sq ft")
    outliers = compute_rent_variance_outliers([no_sqft, normal])
    assert outliers == [], "a lease missing square footage can't contribute a rent/sqft outlier"
    print("✓ test_rent_variance_outliers_skips_leases_without_sqft: PASS")


def test_rent_variance_outliers_empty_portfolio_does_not_crash():
    assert compute_rent_variance_outliers([]) == []
    print("✓ test_rent_variance_outliers_empty_portfolio_does_not_crash: PASS")


def test_cross_lease_mismatch_flags_both_leases_at_same_address():
    lease_a = _lease(
        40, "unit_a.pdf", tenant="Alpha Retail LLC",
        property_address="100 Main Street, Suite 100",
        rent_amount="$5,000.00", square_footage="2,000 sq ft",  # $2.50/sqft
    )
    lease_b = _lease(
        41, "unit_b.pdf", tenant="Beta Goods Inc.",
        property_address="100 Main Street, Suite 100",
        rent_amount="$8,000.00", square_footage="2,000 sq ft",  # $4.00/sqft, 60% higher
    )
    mismatches = compute_cross_lease_mismatches([lease_a, lease_b])

    assert 40 in mismatches and 41 in mismatches
    flag_a = mismatches[40][0]
    flag_b = mismatches[41][0]
    assert flag_a["category"] == "cross_lease_mismatch"
    assert flag_a["severity"] == "high"
    assert flag_a["other_lease_id"] == 41
    assert "unit_b.pdf" in flag_a["message"]
    assert flag_b["other_lease_id"] == 40
    assert "unit_a.pdf" in flag_b["message"]
    print("✓ test_cross_lease_mismatch_flags_both_leases_at_same_address: PASS")


def test_cross_lease_mismatch_not_flagged_within_normal_variation():
    lease_a = _lease(
        42, "unit_c.pdf", property_address="200 Oak Avenue",
        rent_amount="$5,000.00", square_footage="2,000 sq ft",  # $2.50/sqft
    )
    lease_b = _lease(
        43, "unit_d.pdf", property_address="200 Oak Avenue",
        rent_amount="$5,150.00", square_footage="2,000 sq ft",  # $2.575/sqft, 3% higher
    )
    mismatches = compute_cross_lease_mismatches([lease_a, lease_b])
    assert mismatches == {}
    print("✓ test_cross_lease_mismatch_not_flagged_within_normal_variation: PASS")


def test_cross_lease_mismatch_ignores_different_addresses():
    lease_a = _lease(
        44, "unit_e.pdf", property_address="1 First Street",
        rent_amount="$5,000.00", square_footage="1,000 sq ft",  # $5.00/sqft
    )
    lease_b = _lease(
        45, "unit_f.pdf", property_address="2 Second Street",
        rent_amount="$50,000.00", square_footage="1,000 sq ft",  # $50.00/sqft -- wildly different, different building
    )
    mismatches = compute_cross_lease_mismatches([lease_a, lease_b])
    assert mismatches == {}, "different addresses must never be compared, no matter how different the numbers"
    print("✓ test_cross_lease_mismatch_ignores_different_addresses: PASS")


def test_cross_lease_mismatch_address_normalization_matches_formatting_variants():
    lease_a = _lease(46, "unit_g.pdf", property_address="100 MAIN STREET, Suite 100.", rent_amount="$5,000.00", square_footage="2,000 sq ft")
    lease_b = _lease(47, "unit_h.pdf", property_address="100 main street suite 100", rent_amount="$9,000.00", square_footage="2,000 sq ft")
    mismatches = compute_cross_lease_mismatches([lease_a, lease_b])
    assert 46 in mismatches and 47 in mismatches
    print("✓ test_cross_lease_mismatch_address_normalization_matches_formatting_variants: PASS")


def test_cross_lease_mismatch_lease_with_no_address_excluded_without_crashing():
    lease_a = _lease(48, "unit_i.pdf", property_address=None, rent_amount="$5,000.00", square_footage="1,000 sq ft")
    lease_b = _lease(49, "unit_j.pdf", property_address="300 Elm Street", rent_amount="$5,000.00", square_footage="1,000 sq ft")
    mismatches = compute_cross_lease_mismatches([lease_a, lease_b])
    assert mismatches == {}
    print("✓ test_cross_lease_mismatch_lease_with_no_address_excluded_without_crashing: PASS")


def test_cross_lease_mismatch_three_leases_same_address_pairwise():
    """3 leases at the same address: only the pair that actually disagrees should produce flags."""
    matched = _lease(50, "unit_k.pdf", property_address="400 Pine Street", rent_amount="$5,000.00", square_footage="2,000 sq ft")
    also_matched = _lease(51, "unit_l.pdf", property_address="400 Pine Street", rent_amount="$5,100.00", square_footage="2,000 sq ft")
    outlier = _lease(52, "unit_m.pdf", property_address="400 Pine Street", rent_amount="$20,000.00", square_footage="2,000 sq ft")

    mismatches = compute_cross_lease_mismatches([matched, also_matched, outlier])

    assert 52 in mismatches, "the outlier must be flagged against both other leases"
    assert len(mismatches[52]) == 2
    assert 50 in mismatches and 51 in mismatches
    print("✓ test_cross_lease_mismatch_three_leases_same_address_pairwise: PASS")


def test_tenant_concentration_happy_path_multiple_distinct_tenants():
    """4 tenants at $10k/$6k/$3k/$1k (total $20k) -> 50%/30%/15%/5%. HHI = 2500+900+225+25 = 3650 (high)."""
    leases = [
        _lease(70, "a.pdf", tenant="Tenant A", rent_amount="$10,000.00"),
        _lease(71, "b.pdf", tenant="Tenant B", rent_amount="$6,000.00"),
        _lease(72, "c.pdf", tenant="Tenant C", rent_amount="$3,000.00"),
        _lease(73, "d.pdf", tenant="Tenant D", rent_amount="$1,000.00"),
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 4
    assert result["lease_count"] == 4
    assert result["excluded_lease_count"] == 0
    assert result["total_rent"] == 20000.0
    assert [t["tenant"] for t in result["tenants"]] == ["Tenant A", "Tenant B", "Tenant C", "Tenant D"]
    assert [t["pct_of_total"] for t in result["tenants"]] == [50.0, 30.0, 15.0, 5.0]
    assert result["top_1_pct"] == 50.0
    assert result["top_3_pct"] == 95.0
    assert result["top_5_pct"] == 100.0  # fewer than 5 tenants exist -- takes however many there are
    assert result["hhi"] == 3650.0
    assert result["concentration_level"] == "high"
    print("✓ test_tenant_concentration_happy_path_multiple_distinct_tenants: PASS")


def test_tenant_concentration_merges_same_tenant_across_multiple_leases():
    """A chain tenant with 3 separate lease uploads must count as ONE tenant, not three."""
    leases = [
        _lease(74, "chain1.pdf", tenant="Big Chain Co", rent_amount="$2,000.00"),
        _lease(75, "chain2.pdf", tenant="Big Chain Co", rent_amount="$3,000.00"),
        _lease(76, "chain3.pdf", tenant="Big Chain Co", rent_amount="$1,000.00"),
        _lease(77, "solo.pdf", tenant="Solo Shop", rent_amount="$4,000.00"),
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 2  # not 4 -- Big Chain Co's 3 leases merged into one
    assert result["lease_count"] == 4
    big_chain = next(t for t in result["tenants"] if t["tenant"] == "Big Chain Co")
    assert big_chain["rent"] == 6000.0
    assert big_chain["pct_of_total"] == 60.0
    print("✓ test_tenant_concentration_merges_same_tenant_across_multiple_leases: PASS")


def test_tenant_concentration_name_normalization_merges_formatting_variants():
    """Same tenant typed with different case/punctuation/whitespace must still merge into one group."""
    leases = [
        _lease(78, "v1.pdf", tenant="Acme Corp", rent_amount="$1,000.00"),
        _lease(79, "v2.pdf", tenant="ACME CORP.", rent_amount="$1,000.00"),
        _lease(80, "v3.pdf", tenant="acme   corp", rent_amount="$1,000.00"),
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 1
    assert result["tenants"][0]["rent"] == 3000.0
    assert result["tenants"][0]["tenant"] == "Acme Corp"  # first-seen display spelling is kept
    print("✓ test_tenant_concentration_name_normalization_merges_formatting_variants: PASS")


def test_tenant_concentration_does_not_merge_genuinely_different_tenants():
    """"Acme Corp" and "Acme Corp West" are different tenants -- must never be fuzzy-merged."""
    leases = [
        _lease(81, "a.pdf", tenant="Acme Corp", rent_amount="$5,000.00"),
        _lease(82, "b.pdf", tenant="Acme Corp West", rent_amount="$5,000.00"),
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 2
    assert result["top_1_pct"] == 50.0  # not 100 -- confirms they were NOT merged into one
    print("✓ test_tenant_concentration_does_not_merge_genuinely_different_tenants: PASS")


def test_tenant_concentration_excludes_lease_with_missing_tenant_name():
    """A lease with no extracted tenant name must be excluded, never bucketed as a fake 'Unknown' tenant."""
    leases = [
        _lease(83, "known1.pdf", tenant="Known Tenant A", rent_amount="$5,000.00"),
        _lease(84, "known2.pdf", tenant="Known Tenant B", rent_amount="$5,000.00"),
        _lease(85, "unknown.pdf", rent_amount="$50,000.00"),  # no tenant= passed -> defaults to not-found
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 2  # the $50k lease with no tenant must not appear as a 3rd "tenant"
    assert result["excluded_lease_count"] == 1
    assert result["total_rent"] == 10000.0  # the $50k unattributed lease is excluded from the total too
    assert all(t["tenant"] not in (None, "Unknown", "unknown") for t in result["tenants"])
    print("✓ test_tenant_concentration_excludes_lease_with_missing_tenant_name: PASS")


def test_tenant_concentration_excludes_lease_with_unparseable_rent():
    leases = [
        _lease(86, "known.pdf", tenant="Known Tenant", rent_amount="$5,000.00"),
        _lease(87, "no_rent.pdf", tenant="No Rent Tenant"),  # no rent_amount= passed
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 1
    assert result["excluded_lease_count"] == 1
    assert result["top_1_pct"] == 100.0
    print("✓ test_tenant_concentration_excludes_lease_with_unparseable_rent: PASS")


def test_tenant_concentration_empty_portfolio_does_not_crash():
    result = compute_tenant_concentration([])
    assert result["tenant_count"] == 0
    assert result["lease_count"] == 0
    assert result["excluded_lease_count"] == 0
    assert result["total_rent"] is None  # unknown, not a misleading 0
    assert result["tenants"] == []
    assert result["top_1_pct"] is None
    assert result["hhi"] is None
    assert result["concentration_level"] is None
    print("✓ test_tenant_concentration_empty_portfolio_does_not_crash: PASS")


def test_tenant_concentration_no_analyzable_leases_does_not_crash():
    """Every lease is missing tenant, rent, or both -- must degrade to the same 'not enough data' shape as an empty portfolio, not crash on a division by zero."""
    leases = [
        _lease(88, "a.pdf", rent_amount="$5,000.00"),  # no tenant
        _lease(89, "b.pdf", tenant="Some Tenant"),  # no rent
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 0
    assert result["excluded_lease_count"] == 2
    assert result["total_rent"] is None
    assert result["concentration_level"] is None
    print("✓ test_tenant_concentration_no_analyzable_leases_does_not_crash: PASS")


def test_tenant_concentration_single_tenant_is_maximum_concentration():
    result = compute_tenant_concentration([
        _lease(90, "only.pdf", tenant="Only Tenant", rent_amount="$8,000.00"),
    ])
    assert result["tenant_count"] == 1
    assert result["top_1_pct"] == 100.0
    assert result["hhi"] == 10000.0
    assert result["concentration_level"] == "high"
    print("✓ test_tenant_concentration_single_tenant_is_maximum_concentration: PASS")


def test_tenant_concentration_evenly_split_is_low():
    """10 tenants at 10% each -> HHI = 10*(10^2) = 1000, well under the 1500 'moderate' floor."""
    leases = [
        _lease(100 + i, f"t{i}.pdf", tenant=f"Tenant {i}", rent_amount="$1,000.00")
        for i in range(10)
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 10
    assert result["top_1_pct"] == 10.0
    assert result["hhi"] == 1000.0
    assert result["concentration_level"] == "low"
    print("✓ test_tenant_concentration_evenly_split_is_low: PASS")


def test_tenant_concentration_high_via_dominant_tenant_even_with_low_hhi():
    """
    1 tenant at exactly 25% (the top-tenant "high" threshold) plus 75 tiny
    tenants at 1% each: HHI = 625 + 75*(1) = 700, which is "low" by HHI
    alone. Must still classify as "high" because of the single dominant
    tenant -- this is exactly the case HHI alone can under-flag (see the
    docstring), and the whole reason the top-tenant threshold exists as
    an independent trigger.
    """
    leases = [_lease(200, "dominant.pdf", tenant="Dominant Tenant", rent_amount="$2,500.00")]
    leases += [
        _lease(201 + i, f"tiny{i}.pdf", tenant=f"Tiny Tenant {i}", rent_amount="$100.00")
        for i in range(75)
    ]
    result = compute_tenant_concentration(leases)

    assert result["total_rent"] == 10000.0
    assert result["top_1_pct"] == 25.0
    assert result["hhi"] == 700.0  # confirms HHI alone would NOT flag this as high
    assert result["concentration_level"] == "high"
    print("✓ test_tenant_concentration_high_via_dominant_tenant_even_with_low_hhi: PASS")


def test_tenant_concentration_moderate_via_top_tenant_threshold():
    """1 tenant at exactly 15% (the top-tenant 'moderate' threshold) plus 17 tenants at 5% each. HHI = 225 + 17*25 = 650 (low by HHI alone) -- moderate must still trigger off the top-tenant share."""
    leases = [_lease(300, "midsize.pdf", tenant="Midsize Tenant", rent_amount="$1,500.00")]
    leases += [
        _lease(301 + i, f"small{i}.pdf", tenant=f"Small Tenant {i}", rent_amount="$500.00")
        for i in range(17)
    ]
    result = compute_tenant_concentration(leases)

    assert result["total_rent"] == 10000.0
    assert result["top_1_pct"] == 15.0
    assert result["hhi"] == 650.0
    assert result["concentration_level"] == "moderate"
    print("✓ test_tenant_concentration_moderate_via_top_tenant_threshold: PASS")


def test_tenant_concentration_high_at_exact_threshold_boundary():
    """
    4 equal tenants at exactly 25% each: HHI = 4*(25^2) = 2500, exactly
    at HHI_HIGH_THRESHOLD, and top_1_pct = 25.0, exactly at
    TOP_TENANT_HIGH_RISK_PCT. Confirms both thresholds are inclusive
    (>=, not >) -- a portfolio sitting exactly on the line is "high",
    not "moderate". (It's mathematically not possible to exceed the HHI
    high threshold while keeping every individual tenant strictly under
    25% -- verified separately -- so this exact-equal-split case is the
    boundary itself, not an arbitrary example.)
    """
    leases = [
        _lease(400 + i, f"t{i}.pdf", tenant=f"Tenant {i}", rent_amount="$2,500.00")
        for i in range(4)
    ]
    result = compute_tenant_concentration(leases)

    assert result["total_rent"] == 10000.0
    assert result["top_1_pct"] == 25.0
    assert result["hhi"] == 2500.0
    assert result["concentration_level"] == "high"
    print("✓ test_tenant_concentration_high_at_exact_threshold_boundary: PASS")


def test_tenant_concentration_includes_legitimate_zero_rent_tenant():
    """
    A genuine $0 base rent (e.g. a percentage-only retail lease) is a
    real value, not a data-quality problem -- must be included at 0%,
    not silently excluded the way a missing/unparseable rent is.
    """
    leases = [
        _lease(500, "normal.pdf", tenant="Normal Tenant", rent_amount="$5,000.00"),
        _lease(501, "pct_only.pdf", tenant="Percentage-Rent Kiosk", rent_amount="$0.00"),
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 2  # the $0 tenant counts as a real tenant...
    assert result["lease_count"] == 2
    assert result["excluded_lease_count"] == 0  # ...not excluded like a missing/unparseable rent would be
    zero_rent_tenant = next(t for t in result["tenants"] if t["tenant"] == "Percentage-Rent Kiosk")
    assert zero_rent_tenant["rent"] == 0.0
    assert zero_rent_tenant["pct_of_total"] == 0.0
    assert result["total_rent"] == 5000.0  # unaffected by the $0 tenant
    print("✓ test_tenant_concentration_includes_legitimate_zero_rent_tenant: PASS")


def test_tenant_concentration_all_zero_rent_does_not_crash():
    """
    Every lease has a legitimate $0 rent -- total_rent is exactly 0, so
    no percentage can be computed. Must degrade to the same 'not enough
    data' shape as an empty portfolio, not raise ZeroDivisionError.
    """
    leases = [
        _lease(502, "a.pdf", tenant="Tenant A", rent_amount="$0.00"),
        _lease(503, "b.pdf", tenant="Tenant B", rent_amount="$0.00"),
    ]
    result = compute_tenant_concentration(leases)

    assert result["tenant_count"] == 0
    assert result["total_rent"] is None
    assert result["concentration_level"] is None
    print("✓ test_tenant_concentration_all_zero_rent_does_not_crash: PASS")


def test_tenant_concentration_rounding_does_not_compound_across_tenants():
    """
    6 tenants whose true percentages don't round cleanly (e.g. thirds)
    must still have top_5_pct/hhi computed from the RAW fractions, not
    from already-rounded per-tenant percentages -- summing rounded
    values first would drift the total away from what the raw math
    actually says.
    """
    # $10,000 split as 5900/1100/1000/900/700/400 -- deliberately messy
    # percentages (59.0/11.0/10.0/9.0/7.0/4.0, chosen to be clean here so
    # the assertion below is exact) that still exercises the "compute
    # cumulative/hhi from raw shares, round once" code path identically
    # to a real messy split would.
    leases = [
        _lease(510, "a.pdf", tenant="A", rent_amount="$5,900.00"),
        _lease(511, "b.pdf", tenant="B", rent_amount="$1,100.00"),
        _lease(512, "c.pdf", tenant="C", rent_amount="$1,000.00"),
        _lease(513, "d.pdf", tenant="D", rent_amount="$900.00"),
        _lease(514, "e.pdf", tenant="E", rent_amount="$700.00"),
        _lease(515, "f.pdf", tenant="F", rent_amount="$400.00"),
    ]
    result = compute_tenant_concentration(leases)
    all_pcts = [t["pct_of_total"] for t in result["tenants"]]
    assert sum(all_pcts) == 100.0  # every tenant's share, summed, must equal exactly 100
    assert result["top_5_pct"] == 96.0  # 59+11+10+9+7
    print("✓ test_tenant_concentration_rounding_does_not_compound_across_tenants: PASS")


def _date_str(days_from_reference):
    """A lease_end_date string `days_from_reference` days after REFERENCE_DATE, in the extractor's usual display format."""
    return (REFERENCE_DATE + timedelta(days=days_from_reference)).strftime("%B %d, %Y")


def test_walt_happy_path_weighted_by_rent():
    """
    2 leases: $8,000 rent with 365 days left, $2,000 rent with 1095 days
    left. WALT must be pulled toward the $8,000 lease's shorter term,
    not a plain unweighted average of the two remaining terms.
    """
    leases = [
        _lease(600, "a.pdf", rent_amount="$8,000.00", lease_end_date=_date_str(365)),
        _lease(601, "b.pdf", rent_amount="$2,000.00", lease_end_date=_date_str(1095)),
    ]
    result = compute_walt(leases, reference_date=REFERENCE_DATE)

    expected_years_a = 365 / DAYS_PER_YEAR
    expected_years_b = 1095 / DAYS_PER_YEAR
    expected_walt = round((expected_years_a * 8000 + expected_years_b * 2000) / 10000, 2)
    unweighted_avg = round((expected_years_a + expected_years_b) / 2, 2)

    assert result["lease_count"] == 2
    assert result["excluded_lease_count"] == 0
    assert result["walt_years"] == expected_walt
    assert result["walt_years"] != unweighted_avg  # confirms it's actually weighted, not a plain average
    print("✓ test_walt_happy_path_weighted_by_rent: PASS")


def test_walt_excludes_lease_missing_end_date():
    leases = [
        _lease(602, "a.pdf", rent_amount="$5,000.00", lease_end_date=_date_str(730)),
        _lease(603, "b.pdf", rent_amount="$5,000.00"),  # no end date
    ]
    result = compute_walt(leases, reference_date=REFERENCE_DATE)
    assert result["lease_count"] == 1
    assert result["excluded_lease_count"] == 1
    print("✓ test_walt_excludes_lease_missing_end_date: PASS")


def test_walt_excludes_lease_missing_rent():
    leases = [
        _lease(604, "a.pdf", rent_amount="$5,000.00", lease_end_date=_date_str(730)),
        _lease(605, "b.pdf", lease_end_date=_date_str(730)),  # no rent
    ]
    result = compute_walt(leases, reference_date=REFERENCE_DATE)
    assert result["lease_count"] == 1
    assert result["excluded_lease_count"] == 1
    print("✓ test_walt_excludes_lease_missing_rent: PASS")


def test_walt_excludes_already_expired_lease():
    leases = [
        _lease(606, "active.pdf", rent_amount="$5,000.00", lease_end_date=_date_str(365)),
        _lease(607, "expired.pdf", rent_amount="$5,000.00", lease_end_date=_date_str(-30)),  # expired 30 days ago
    ]
    result = compute_walt(leases, reference_date=REFERENCE_DATE)
    assert result["lease_count"] == 1
    assert result["excluded_lease_count"] == 1
    print("✓ test_walt_excludes_already_expired_lease: PASS")


def test_walt_includes_lease_expiring_exactly_today_at_zero_years():
    """A lease ending exactly on reference_date is 0 years remaining -- a real data point, not excluded like an already-expired lease."""
    leases = [_lease(608, "today.pdf", rent_amount="$5,000.00", lease_end_date=_date_str(0))]
    result = compute_walt(leases, reference_date=REFERENCE_DATE)
    assert result["lease_count"] == 1
    assert result["excluded_lease_count"] == 0
    assert result["walt_years"] == 0.0
    print("✓ test_walt_includes_lease_expiring_exactly_today_at_zero_years: PASS")


def test_walt_empty_portfolio_does_not_crash():
    result = compute_walt([], reference_date=REFERENCE_DATE)
    assert result["walt_years"] is None
    assert result["lease_count"] == 0
    print("✓ test_walt_empty_portfolio_does_not_crash: PASS")


def test_walt_no_analyzable_leases_does_not_crash():
    leases = [_lease(609, "a.pdf", rent_amount="$5,000.00")]  # no end date
    result = compute_walt(leases, reference_date=REFERENCE_DATE)
    assert result["walt_years"] is None
    assert result["excluded_lease_count"] == 1
    print("✓ test_walt_no_analyzable_leases_does_not_crash: PASS")


def test_rollover_schedule_happy_path_buckets_by_year():
    leases = [
        _lease(700, "y1.pdf", rent_amount="$1,000.00", lease_end_date=_date_str(100)),   # year_1
        _lease(701, "y2.pdf", rent_amount="$1,000.00", lease_end_date=_date_str(400)),   # year_2
        _lease(702, "y6.pdf", rent_amount="$1,000.00", lease_end_date=_date_str(2600)),  # year_6_plus (>5 years out)
    ]
    result = compute_rollover_schedule(leases, reference_date=REFERENCE_DATE)

    assert result["lease_count"] == 3
    assert result["total_rent"] == 3000.0
    assert result["buckets"]["year_1"]["lease_count"] == 1
    assert result["buckets"]["year_2"]["lease_count"] == 1
    assert result["buckets"]["year_6_plus"]["lease_count"] == 1
    assert result["buckets"]["year_3"]["lease_count"] == 0
    assert result["buckets"]["year_1"]["pct_of_total_rent"] == round(1000 / 3000 * 100, 2)
    print("✓ test_rollover_schedule_happy_path_buckets_by_year: PASS")


def test_rollover_schedule_already_expired_kept_separate_not_folded_into_year_1():
    leases = [
        _lease(703, "active.pdf", rent_amount="$4,000.00", lease_end_date=_date_str(100)),
        _lease(704, "expired.pdf", rent_amount="$1,000.00", lease_end_date=_date_str(-10)),
    ]
    result = compute_rollover_schedule(leases, reference_date=REFERENCE_DATE)

    assert result["already_expired"]["rent"] == 1000.0
    assert result["already_expired"]["lease_count"] == 1
    # The forward-looking total must exclude the expired lease's rent entirely --
    # year_1 gets 100% of the (forward-looking-only) total, not diluted by it.
    assert result["total_rent"] == 4000.0
    assert result["buckets"]["year_1"]["pct_of_total_rent"] == 100.0
    print("✓ test_rollover_schedule_already_expired_kept_separate_not_folded_into_year_1: PASS")


def test_rollover_schedule_lease_expiring_today_lands_in_year_1():
    leases = [_lease(705, "today.pdf", rent_amount="$1,000.00", lease_end_date=_date_str(0))]
    result = compute_rollover_schedule(leases, reference_date=REFERENCE_DATE)
    assert result["buckets"]["year_1"]["lease_count"] == 1
    assert result["already_expired"]["lease_count"] == 0
    print("✓ test_rollover_schedule_lease_expiring_today_lands_in_year_1: PASS")


def test_rollover_schedule_percentages_sum_to_100_across_buckets():
    leases = [
        _lease(706 + i, f"l{i}.pdf", rent_amount="$1,000.00", lease_end_date=_date_str(100 + i * 200))
        for i in range(7)
    ]
    result = compute_rollover_schedule(leases, reference_date=REFERENCE_DATE)
    total_pct = sum(b["pct_of_total_rent"] for b in result["buckets"].values())
    assert abs(total_pct - 100.0) < 0.1  # small rounding tolerance, not a large drift
    total_lease_pct = sum(b["pct_of_total_leases"] for b in result["buckets"].values())
    assert abs(total_lease_pct - 100.0) < 0.1
    print("✓ test_rollover_schedule_percentages_sum_to_100_across_buckets: PASS")


def test_rollover_schedule_high_risk_when_year_1_concentrated():
    """80% of rent rolling over in year_1 alone -- well over the high-risk threshold."""
    leases = [
        _lease(720, "big.pdf", rent_amount="$8,000.00", lease_end_date=_date_str(100)),
        _lease(721, "small.pdf", rent_amount="$2,000.00", lease_end_date=_date_str(800)),
    ]
    result = compute_rollover_schedule(leases, reference_date=REFERENCE_DATE)
    assert result["buckets"]["year_1"]["pct_of_total_rent"] == 80.0
    assert result["rollover_risk_level"] == "high"
    assert ROLLOVER_YEAR_1_HIGH_RISK_PCT <= 80.0
    print("✓ test_rollover_schedule_high_risk_when_year_1_concentrated: PASS")


def test_rollover_schedule_low_risk_when_evenly_laddered():
    """10 equal leases, only 1 landing in year_1 (10% of total rent) -- clearly under the 15% moderate threshold."""
    offsets = [100, 500, 500, 900, 900, 1300, 1300, 1700, 1700, 2100]  # 1 in year_1, 2 each in years 2-5, 2 in year_6_plus
    leases = [
        _lease(730 + i, f"l{i}.pdf", rent_amount="$1,000.00", lease_end_date=_date_str(offset))
        for i, offset in enumerate(offsets)
    ]
    result = compute_rollover_schedule(leases, reference_date=REFERENCE_DATE)
    assert result["buckets"]["year_1"]["pct_of_total_rent"] == 10.0
    assert result["buckets"]["year_1"]["pct_of_total_rent"] < ROLLOVER_YEAR_1_MODERATE_RISK_PCT
    assert result["rollover_risk_level"] == "low"
    print("✓ test_rollover_schedule_low_risk_when_evenly_laddered: PASS")


def test_rollover_schedule_empty_portfolio_does_not_crash():
    result = compute_rollover_schedule([], reference_date=REFERENCE_DATE)
    assert result["buckets"] is None
    assert result["already_expired"] is None
    assert result["rollover_risk_level"] is None
    print("✓ test_rollover_schedule_empty_portfolio_does_not_crash: PASS")


def test_rollover_schedule_all_leases_already_expired_reports_real_data_not_none():
    """
    Every analyzable lease has already expired -- this is real, important
    data (100% rollover already happened) and must NOT collapse to the
    same null result as an empty/unusable portfolio.
    """
    leases = [
        _lease(740, "a.pdf", rent_amount="$3,000.00", lease_end_date=_date_str(-10)),
        _lease(741, "b.pdf", rent_amount="$2,000.00", lease_end_date=_date_str(-5)),
    ]
    result = compute_rollover_schedule(leases, reference_date=REFERENCE_DATE)

    assert result["buckets"] is not None  # NOT the null "not enough data" shape
    assert all(b["rent"] == 0.0 for b in result["buckets"].values())
    assert result["already_expired"]["rent"] == 5000.0
    assert result["already_expired"]["lease_count"] == 2
    assert result["rollover_risk_level"] == "high"
    print("✓ test_rollover_schedule_all_leases_already_expired_reports_real_data_not_none: PASS")


def test_loss_to_lease_happy_path_top_rent_becomes_the_proxy():
    """
    3 leases at the same property: $2.00/sqft, $3.00/sqft, $5.00/sqft
    (the top). The $5.00 lease has 0% loss; the others show a real gap
    against that property's own best-achieved rate.
    """
    leases = [
        _lease(800, "unit_a.pdf", property_address="100 Main St", rent_amount="$2,000.00", square_footage="1,000 sq ft"),  # $2.00/sqft
        _lease(801, "unit_b.pdf", property_address="100 Main St", rent_amount="$3,000.00", square_footage="1,000 sq ft"),  # $3.00/sqft
        _lease(802, "unit_c.pdf", property_address="100 Main St", rent_amount="$5,000.00", square_footage="1,000 sq ft"),  # $5.00/sqft -- the top
    ]
    result = compute_loss_to_lease(leases)

    assert result["lease_count"] == 3
    assert result["excluded_lease_count"] == 0
    by_id = {r["lease_id"]: r for r in result["leases"]}
    assert by_id[802]["loss_pct"] == 0.0
    assert by_id[802]["monthly_upside"] == 0.0
    assert by_id[801]["loss_pct"] == 40.0  # (5-3)/5 * 100
    assert by_id[801]["monthly_upside"] == 2000.0  # (5-3) * 1000 sqft
    assert by_id[800]["loss_pct"] == 60.0  # (5-2)/5 * 100
    assert by_id[800]["monthly_upside"] == 3000.0  # (5-2) * 1000 sqft
    assert result["total_monthly_upside"] == 5000.0  # 2000 + 3000 + 0
    print("✓ test_loss_to_lease_happy_path_top_rent_becomes_the_proxy: PASS")


def test_loss_to_lease_excludes_property_with_only_one_lease():
    """A single lease at a property has no internal comp -- must be excluded, not compared against unrelated properties."""
    leases = [
        _lease(803, "solo.pdf", property_address="200 Solo Ave", rent_amount="$4,000.00", square_footage="1,000 sq ft"),
    ]
    result = compute_loss_to_lease(leases)
    assert result["lease_count"] == 0
    assert result["excluded_lease_count"] == 1
    assert result["leases"] == []
    assert result["total_monthly_upside"] is None
    print("✓ test_loss_to_lease_excludes_property_with_only_one_lease: PASS")


def test_loss_to_lease_different_properties_not_compared_against_each_other():
    """Two separate 2-lease properties -- each property's comp is its own, not blended across properties."""
    leases = [
        _lease(804, "prop1_a.pdf", property_address="100 Main St", rent_amount="$1,000.00", square_footage="1,000 sq ft"),  # $1/sqft
        _lease(805, "prop1_b.pdf", property_address="100 Main St", rent_amount="$2,000.00", square_footage="1,000 sq ft"),  # $2/sqft (prop 1's top)
        _lease(806, "prop2_a.pdf", property_address="999 Other Rd", rent_amount="$8,000.00", square_footage="1,000 sq ft"),  # $8/sqft
        _lease(807, "prop2_b.pdf", property_address="999 Other Rd", rent_amount="$10,000.00", square_footage="1,000 sq ft"),  # $10/sqft (prop 2's top)
    ]
    result = compute_loss_to_lease(leases)
    by_id = {r["lease_id"]: r for r in result["leases"]}

    # Lease 804 must be compared against prop 1's $2/sqft top, NOT prop 2's $10/sqft
    assert by_id[804]["property_top_rent_per_sqft"] == 2.0
    assert by_id[806]["property_top_rent_per_sqft"] == 10.0
    print("✓ test_loss_to_lease_different_properties_not_compared_against_each_other: PASS")


def test_loss_to_lease_excludes_lease_missing_address():
    leases = [
        _lease(808, "a.pdf", property_address="100 Main St", rent_amount="$2,000.00", square_footage="1,000 sq ft"),
        _lease(809, "b.pdf", property_address="100 Main St", rent_amount="$4,000.00", square_footage="1,000 sq ft"),
        _lease(810, "c.pdf", rent_amount="$3,000.00", square_footage="1,000 sq ft"),  # no address
    ]
    result = compute_loss_to_lease(leases)
    assert result["lease_count"] == 2
    assert result["excluded_lease_count"] == 1
    assert 810 not in {r["lease_id"] for r in result["leases"]}
    print("✓ test_loss_to_lease_excludes_lease_missing_address: PASS")


def test_loss_to_lease_excludes_lease_missing_sqft():
    leases = [
        _lease(811, "a.pdf", property_address="100 Main St", rent_amount="$2,000.00", square_footage="1,000 sq ft"),
        _lease(812, "b.pdf", property_address="100 Main St", rent_amount="$4,000.00", square_footage="1,000 sq ft"),
        _lease(813, "c.pdf", property_address="100 Main St", rent_amount="$3,000.00"),  # no sqft -- can't compute psf
    ]
    result = compute_loss_to_lease(leases)
    assert result["lease_count"] == 2
    assert result["excluded_lease_count"] == 1
    print("✓ test_loss_to_lease_excludes_lease_missing_sqft: PASS")


def test_loss_to_lease_address_normalization_matches_formatting_variants():
    """Same exact unit typed with different case/whitespace must still be recognized as one group."""
    leases = [
        _lease(814, "a.pdf", property_address="100 Main Street, Suite 1", rent_amount="$2,000.00", square_footage="1,000 sq ft"),
        _lease(815, "b.pdf", property_address="100 MAIN STREET, SUITE 1", rent_amount="$4,000.00", square_footage="1,000 sq ft"),
    ]
    result = compute_loss_to_lease(leases)
    assert result["lease_count"] == 2  # recognized as the same property, not two comp-less singletons
    print("✓ test_loss_to_lease_address_normalization_matches_formatting_variants: PASS")


def test_loss_to_lease_groups_different_suites_in_same_building():
    """
    Regression test for a real bug: DIFFERENT suites in the SAME
    building must be grouped as comparable units (that's the entire
    point of an internal rent comp), not treated as separate,
    comp-less single-lease "properties" just because their suite
    numbers differ. Caught originally by testing against a realistic
    multi-suite building, not by the (too-uniform) fixtures above.
    """
    leases = [
        _lease(821, "a.pdf", property_address="500 Commerce Blvd, Suite 100", rent_amount="$2,000.00", square_footage="1,000 sq ft"),  # $2/sqft
        _lease(822, "b.pdf", property_address="500 Commerce Blvd, Suite 200", rent_amount="$3,500.00", square_footage="1,000 sq ft"),  # $3.50/sqft -- top
        _lease(823, "c.pdf", property_address="500 Commerce Blvd, Suite 300", rent_amount="$3,000.00", square_footage="1,000 sq ft"),  # $3/sqft
    ]
    result = compute_loss_to_lease(leases)

    assert result["lease_count"] == 3  # NOT 0 -- all three recognized as the same building
    assert result["excluded_lease_count"] == 0
    by_id = {r["lease_id"]: r for r in result["leases"]}
    assert by_id[822]["loss_pct"] == 0.0  # Suite 200 is this building's top rent
    assert by_id[821]["property_top_rent_per_sqft"] == 3.5
    print("✓ test_loss_to_lease_groups_different_suites_in_same_building: PASS")


def test_loss_to_lease_does_not_merge_genuinely_different_buildings_with_similar_names():
    """Two different street addresses must never be merged just because both happen to have a suite number stripped."""
    leases = [
        _lease(824, "a.pdf", property_address="500 Commerce Blvd, Suite 100", rent_amount="$2,000.00", square_footage="1,000 sq ft"),
        _lease(825, "b.pdf", property_address="700 Commerce Blvd, Suite 100", rent_amount="$9,000.00", square_footage="1,000 sq ft"),
    ]
    result = compute_loss_to_lease(leases)
    assert result["lease_count"] == 0  # each is alone at its own (different) building -- both comp-less
    assert result["excluded_lease_count"] == 2
    print("✓ test_loss_to_lease_does_not_merge_genuinely_different_buildings_with_similar_names: PASS")


def test_loss_to_lease_all_equal_rent_shows_zero_gap_not_excluded():
    """Every lease at a property has the identical rent/sqft -- 0% loss for all, correctly computed, not excluded."""
    leases = [
        _lease(816, "a.pdf", property_address="100 Main St", rent_amount="$3,000.00", square_footage="1,000 sq ft"),
        _lease(817, "b.pdf", property_address="100 Main St", rent_amount="$3,000.00", square_footage="1,000 sq ft"),
    ]
    result = compute_loss_to_lease(leases)
    assert result["lease_count"] == 2
    assert all(r["loss_pct"] == 0.0 for r in result["leases"])
    assert result["total_monthly_upside"] == 0.0
    print("✓ test_loss_to_lease_all_equal_rent_shows_zero_gap_not_excluded: PASS")


def test_loss_to_lease_sorted_by_monthly_upside_descending():
    leases = [
        _lease(818, "small_gap.pdf", property_address="100 Main St", rent_amount="$4,500.00", square_footage="1,000 sq ft"),
        _lease(819, "big_gap.pdf", property_address="100 Main St", rent_amount="$1,000.00", square_footage="1,000 sq ft"),
        _lease(820, "top.pdf", property_address="100 Main St", rent_amount="$5,000.00", square_footage="1,000 sq ft"),
    ]
    result = compute_loss_to_lease(leases)
    upsides = [r["monthly_upside"] for r in result["leases"]]
    assert upsides == sorted(upsides, reverse=True)
    assert result["leases"][0]["lease_id"] == 819  # the biggest dollar gap first
    print("✓ test_loss_to_lease_sorted_by_monthly_upside_descending: PASS")


def test_loss_to_lease_empty_portfolio_does_not_crash():
    result = compute_loss_to_lease([])
    assert result["leases"] == []
    assert result["lease_count"] == 0
    assert result["total_monthly_upside"] is None
    print("✓ test_loss_to_lease_empty_portfolio_does_not_crash: PASS")


def test_rent_roll_reconciliation_agreement_produces_no_mismatches():
    """Rent roll row and lease PDF for the same unit, everything agrees -- real reconciliation happened, zero mismatches is the correct (good news) answer."""
    leases = [
        _lease(900, "rentroll.csv", tenant="Acme Corp", property_address="500 Main St, Suite 100",
               rent_amount="$4,500.00", lease_end_date="December 31, 2028"),
        _lease(901, "lease.pdf", tenant="Acme Corp", property_address="500 Main St, Suite 100",
               rent_amount="$4,500.00", lease_end_date="December 31, 2028"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert result["rent_roll_lease_count"] == 1
    assert result["lease_document_count"] == 1
    assert result["compared_pair_count"] == 1
    assert result["mismatches"] == []
    print("✓ test_rent_roll_reconciliation_agreement_produces_no_mismatches: PASS")


def test_rent_roll_reconciliation_flags_tenant_mismatch():
    leases = [
        _lease(902, "rentroll.csv", tenant="Old Tenant LLC", property_address="500 Main St, Suite 100", rent_amount="$4,500.00"),
        _lease(903, "lease.pdf", tenant="New Tenant Inc", property_address="500 Main St, Suite 100", rent_amount="$4,500.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert len(result["mismatches"]) == 1
    m = result["mismatches"][0]
    assert m["field"] == "tenant"
    assert m["rent_roll_value"] == "Old Tenant LLC"
    assert m["lease_document_value"] == "New Tenant Inc"
    print("✓ test_rent_roll_reconciliation_flags_tenant_mismatch: PASS")


def test_rent_roll_reconciliation_flags_stale_rent():
    """The realistic case this feature exists for: PM system never got updated after a rent increase."""
    leases = [
        _lease(904, "rentroll.csv", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,000.00"),
        _lease(905, "lease.pdf", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,800.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    rent_mismatches = [m for m in result["mismatches"] if m["field"] == "rent_amount"]
    assert len(rent_mismatches) == 1
    assert rent_mismatches[0]["rent_roll_value"] == "$4,000.00"
    assert rent_mismatches[0]["lease_document_value"] == "$4,800.00"
    print("✓ test_rent_roll_reconciliation_flags_stale_rent: PASS")


def test_rent_roll_reconciliation_flags_stale_end_date():
    """The other realistic case: rent roll still shows the pre-renewal expiration."""
    leases = [
        _lease(906, "rentroll.csv", tenant="Acme Corp", property_address="500 Main St, Suite 100", lease_end_date="December 31, 2025"),
        _lease(907, "lease.pdf", tenant="Acme Corp", property_address="500 Main St, Suite 100", lease_end_date="December 31, 2030"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    date_mismatches = [m for m in result["mismatches"] if m["field"] == "lease_end_date"]
    assert len(date_mismatches) == 1
    print("✓ test_rent_roll_reconciliation_flags_stale_end_date: PASS")


def test_rent_roll_reconciliation_rent_tolerance_absorbs_rounding_noise():
    """A trivial $0.50 gap on a $4,500 rent must NOT be flagged -- well under both the % and $ tolerance."""
    leases = [
        _lease(908, "rentroll.csv", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,500.00"),
        _lease(909, "lease.pdf", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,500.50"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert result["mismatches"] == []
    print("✓ test_rent_roll_reconciliation_rent_tolerance_absorbs_rounding_noise: PASS")


def test_rent_roll_reconciliation_small_dollar_gap_on_tiny_unit_not_flagged_by_pct_alone():
    """A $2 gap on a $100/mo unit is 2% (over the pct tolerance) but under the $5 absolute floor -- must NOT be flagged; both tolerances are required together."""
    leases = [
        _lease(910, "rentroll.csv", tenant="Tiny Kiosk", property_address="500 Main St, Suite 200", rent_amount="$100.00"),
        _lease(911, "lease.pdf", tenant="Tiny Kiosk", property_address="500 Main St, Suite 200", rent_amount="$102.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert result["mismatches"] == []
    print("✓ test_rent_roll_reconciliation_small_dollar_gap_on_tiny_unit_not_flagged_by_pct_alone: PASS")


def test_rent_roll_reconciliation_large_dollar_gap_on_huge_unit_still_flagged():
    """A $500 gap on a $60,000/mo anchor tenant is under 1% but a real dollar discrepancy -- wait, must confirm this IS flagged since $500 clears the $5 floor and needs >1% too; use a gap that clears both."""
    leases = [
        _lease(912, "rentroll.csv", tenant="Anchor Co", property_address="500 Main St, Suite 300", rent_amount="$60,000.00"),
        _lease(913, "lease.pdf", tenant="Anchor Co", property_address="500 Main St, Suite 300", rent_amount="$61,000.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    rent_mismatches = [m for m in result["mismatches"] if m["field"] == "rent_amount"]
    assert len(rent_mismatches) == 1
    print("✓ test_rent_roll_reconciliation_large_dollar_gap_on_huge_unit_still_flagged: PASS")


def test_rent_roll_reconciliation_row_with_no_matching_lease_document_not_compared():
    """Most rent roll rows won't have an uploaded lease PDF yet -- must not crash, and must not appear in compared_pair_count."""
    leases = [
        _lease(914, "rentroll.csv", tenant="No PDF Yet Co", property_address="999 Nowhere St", rent_amount="$1,000.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert result["rent_roll_lease_count"] == 1
    assert result["lease_document_count"] == 0
    assert result["compared_pair_count"] == 0
    assert result["mismatches"] == []
    print("✓ test_rent_roll_reconciliation_row_with_no_matching_lease_document_not_compared: PASS")


def test_rent_roll_reconciliation_lease_document_with_no_rent_roll_row_excluded():
    """A lease PDF at an address with no imported rent roll row -- correctly excluded, not compared against anything."""
    leases = [
        _lease(915, "lease.pdf", tenant="Standalone Co", property_address="123 Solo Ave", rent_amount="$2,000.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert result["lease_document_count"] == 1
    assert result["compared_pair_count"] == 0
    print("✓ test_rent_roll_reconciliation_lease_document_with_no_rent_roll_row_excluded: PASS")


def test_rent_roll_reconciliation_missing_field_on_one_side_skips_only_that_field():
    leases = [
        _lease(916, "rentroll.csv", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,000.00"),  # no lease_end_date
        _lease(917, "lease.pdf", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,800.00", lease_end_date="December 31, 2028"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    fields_flagged = {m["field"] for m in result["mismatches"]}
    assert fields_flagged == {"rent_amount"}  # date comparison skipped (missing on one side), not a crash or a false mismatch
    print("✓ test_rent_roll_reconciliation_missing_field_on_one_side_skips_only_that_field: PASS")


def test_rent_roll_reconciliation_empty_portfolio_does_not_crash():
    result = compute_rent_roll_reconciliation([])
    assert result["mismatches"] == []
    assert result["rent_roll_lease_count"] == 0
    assert result["lease_document_count"] == 0
    assert result["compared_pair_count"] == 0
    print("✓ test_rent_roll_reconciliation_empty_portfolio_does_not_crash: PASS")


def test_rent_roll_reconciliation_extension_matching_is_case_insensitive():
    leases = [
        _lease(918, "RENTROLL.CSV", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,000.00"),
        _lease(919, "LEASE.PDF", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,800.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert result["rent_roll_lease_count"] == 1
    assert result["lease_document_count"] == 1
    assert len(result["mismatches"]) == 1
    print("✓ test_rent_roll_reconciliation_extension_matching_is_case_insensitive: PASS")


def test_rent_roll_reconciliation_multiple_leases_at_same_address_pairwise():
    """2 rent roll rows and 2 lease PDFs at one address (e.g. a mis-imported duplicate) -- every pair compared, count reflects it."""
    leases = [
        _lease(920, "rentroll.csv", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,000.00"),
        _lease(921, "rentroll2.csv", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,000.00"),
        _lease(922, "lease.pdf", tenant="Acme Corp", property_address="500 Main St, Suite 100", rent_amount="$4,800.00"),
    ]
    result = compute_rent_roll_reconciliation(leases)
    assert result["compared_pair_count"] == 2  # 2 rent-roll rows x 1 lease doc
    rent_mismatches = [m for m in result["mismatches"] if m["field"] == "rent_amount"]
    assert len(rent_mismatches) == 2
    print("✓ test_rent_roll_reconciliation_multiple_leases_at_same_address_pairwise: PASS")


def test_t12_reconciliation_agreement():
    leases = [
        _lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$10,000.00"),
        _lease(2, "b.pdf", tenant="Beta LLC", property_address="100 Main St, Suite 102", rent_amount="$8,000.00"),
    ]
    result = compute_t12_reconciliation(leases, "100 Main St", 216000.0)  # (10000+8000)*12
    assert result["rent_roll_annual_rent"] == 216000.0
    assert result["difference"] == 0.0
    assert result["direction"] == "agree"
    assert result["flagged"] is False
    print("✓ test_t12_reconciliation_agreement: PASS")


def test_t12_reconciliation_flags_real_discrepancy_rent_roll_higher():
    leases = [_lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$10,000.00")]
    # rent roll annual = 120000, T12 says only 90000 -- a real, large gap
    result = compute_t12_reconciliation(leases, "100 Main St", 90000.0)
    assert result["direction"] == "rent_roll_higher"
    assert result["flagged"] is True
    print("✓ test_t12_reconciliation_flags_real_discrepancy_rent_roll_higher: PASS")


def test_t12_reconciliation_flags_real_discrepancy_t12_higher():
    leases = [_lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$5,000.00")]
    # rent roll annual = 60000, T12 says 100000 -- T12 higher this time
    result = compute_t12_reconciliation(leases, "100 Main St", 100000.0)
    assert result["direction"] == "t12_higher"
    assert result["flagged"] is True
    print("✓ test_t12_reconciliation_flags_real_discrepancy_t12_higher: PASS")


def test_t12_reconciliation_small_gap_not_flagged():
    """A trivial gap (well under both tolerance bars) must not be flagged -- rounding/timing noise, not a real discrepancy."""
    leases = [_lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$10,000.00")]
    result = compute_t12_reconciliation(leases, "100 Main St", 119500.0)  # 120000 vs 119500 -- $500 gap, 0.4%
    assert result["flagged"] is False
    print("✓ test_t12_reconciliation_small_gap_not_flagged: PASS")


def test_t12_reconciliation_dual_tolerance_absolute_alone_not_enough():
    """A gap that clears the absolute-dollar bar but not the percentage bar (a huge property) must not be flagged -- both thresholds required, same principle as compute_rent_roll_reconciliation's rent tolerance."""
    leases = [_lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$500,000.00")]
    rent_roll_annual = 500000.0 * 12  # 6,000,000
    t12 = rent_roll_annual - 4000.0  # clears the $3,000 absolute bar, but nowhere near 5%
    result = compute_t12_reconciliation(leases, "100 Main St", t12)
    assert result["flagged"] is False, result
    print("✓ test_t12_reconciliation_dual_tolerance_absolute_alone_not_enough: PASS")


def test_t12_reconciliation_dual_tolerance_percentage_alone_not_enough():
    """A gap that clears the percentage bar but not the absolute-dollar bar (a tiny property) must not be flagged."""
    leases = [_lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$500.00")]
    rent_roll_annual = 500.0 * 12  # 6,000
    t12 = rent_roll_annual - 500.0  # 8.3% gap, comfortably clears 5% -- but only a $500 absolute gap
    result = compute_t12_reconciliation(leases, "100 Main St", t12)
    assert result["flagged"] is False, result
    print("✓ test_t12_reconciliation_dual_tolerance_percentage_alone_not_enough: PASS")


def test_t12_reconciliation_building_level_not_unit_level():
    """Different suites in the same building must all count toward the same T12 comparison -- building-level grouping, not exact-unit matching (same convention as compute_loss_to_lease, for the same reason)."""
    leases = [
        _lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$5,000.00"),
        _lease(2, "b.pdf", tenant="Beta LLC", property_address="100 Main St, Suite 202", rent_amount="$5,000.00"),
    ]
    result = compute_t12_reconciliation(leases, "100 Main St", 120000.0)
    assert result["matched_lease_count"] == 2
    assert result["rent_roll_annual_rent"] == 120000.0  # (5000+5000)*12
    print("✓ test_t12_reconciliation_building_level_not_unit_level: PASS")


def test_t12_reconciliation_different_building_not_included():
    leases = [
        _lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$5,000.00"),
        _lease(2, "b.pdf", tenant="Unrelated Co", property_address="999 Other Ave, Suite 1", rent_amount="$9,999.00"),
    ]
    result = compute_t12_reconciliation(leases, "100 Main St", 60000.0)
    assert result["matched_lease_count"] == 1
    assert result["rent_roll_annual_rent"] == 60000.0  # only the 100 Main St lease
    print("✓ test_t12_reconciliation_different_building_not_included: PASS")


def test_t12_reconciliation_no_matching_leases_returns_honest_not_found():
    """No lease at all matches the T12's property -- honest 'not enough data on the rent roll side,' distinct from a real comparison that happens to agree."""
    leases = [_lease(1, "a.pdf", tenant="Acme Corp", property_address="999 Other Ave, Suite 1", rent_amount="$5,000.00")]
    result = compute_t12_reconciliation(leases, "100 Main St", 120000.0)
    assert result["matched_lease_count"] == 0
    assert result["rent_roll_annual_rent"] is None
    assert result["difference"] is None
    assert result["flagged"] is None
    assert result["t12_annual_rental_income"] == 120000.0  # the T12 side is still real and reported
    print("✓ test_t12_reconciliation_no_matching_leases_returns_honest_not_found: PASS")


def test_t12_reconciliation_lease_missing_rent_excluded_not_zero():
    """A matching-building lease with no parseable rent must be excluded from the sum, not silently treated as $0 (which would understate the rent roll side)."""
    leases = [
        _lease(1, "a.pdf", tenant="Acme Corp", property_address="100 Main St, Suite 101", rent_amount="$5,000.00"),
        _lease(2, "b.pdf", tenant="Beta LLC", property_address="100 Main St, Suite 102", rent_amount=None),
    ]
    result = compute_t12_reconciliation(leases, "100 Main St", 60000.0)
    assert result["matched_lease_count"] == 1
    assert result["excluded_lease_count"] == 1
    assert result["rent_roll_annual_rent"] == 60000.0  # just the one usable lease, not counting the missing one as $0
    print("✓ test_t12_reconciliation_lease_missing_rent_excluded_not_zero: PASS")


def test_t12_reconciliation_empty_portfolio_does_not_crash():
    result = compute_t12_reconciliation([], "100 Main St", 120000.0)
    assert result["rent_roll_annual_rent"] is None
    assert result["flagged"] is None
    print("✓ test_t12_reconciliation_empty_portfolio_does_not_crash: PASS")


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
    test_cross_lease_mismatch_flags_both_leases_at_same_address()
    test_cross_lease_mismatch_not_flagged_within_normal_variation()
    test_cross_lease_mismatch_ignores_different_addresses()
    test_cross_lease_mismatch_address_normalization_matches_formatting_variants()
    test_cross_lease_mismatch_lease_with_no_address_excluded_without_crashing()
    test_cross_lease_mismatch_three_leases_same_address_pairwise()
    test_lease_confidence_summary_counts_every_tier()
    test_lease_confidence_summary_all_not_found()
    test_portfolio_confidence_summary_aggregates_across_leases()
    test_portfolio_confidence_summary_empty_portfolio_does_not_crash()
    test_rent_variance_outliers_flags_both_directions()
    test_rent_variance_outliers_excludes_leases_within_normal_range()
    test_rent_variance_outliers_skips_leases_without_sqft()
    test_rent_variance_outliers_empty_portfolio_does_not_crash()
    test_tenant_concentration_happy_path_multiple_distinct_tenants()
    test_tenant_concentration_merges_same_tenant_across_multiple_leases()
    test_tenant_concentration_name_normalization_merges_formatting_variants()
    test_tenant_concentration_does_not_merge_genuinely_different_tenants()
    test_tenant_concentration_excludes_lease_with_missing_tenant_name()
    test_tenant_concentration_excludes_lease_with_unparseable_rent()
    test_tenant_concentration_empty_portfolio_does_not_crash()
    test_tenant_concentration_no_analyzable_leases_does_not_crash()
    test_tenant_concentration_single_tenant_is_maximum_concentration()
    test_tenant_concentration_evenly_split_is_low()
    test_tenant_concentration_high_via_dominant_tenant_even_with_low_hhi()
    test_tenant_concentration_moderate_via_top_tenant_threshold()
    test_tenant_concentration_high_at_exact_threshold_boundary()
    test_tenant_concentration_includes_legitimate_zero_rent_tenant()
    test_tenant_concentration_all_zero_rent_does_not_crash()
    test_tenant_concentration_rounding_does_not_compound_across_tenants()
    test_walt_happy_path_weighted_by_rent()
    test_walt_excludes_lease_missing_end_date()
    test_walt_excludes_lease_missing_rent()
    test_walt_excludes_already_expired_lease()
    test_walt_includes_lease_expiring_exactly_today_at_zero_years()
    test_walt_empty_portfolio_does_not_crash()
    test_walt_no_analyzable_leases_does_not_crash()
    test_rollover_schedule_happy_path_buckets_by_year()
    test_rollover_schedule_already_expired_kept_separate_not_folded_into_year_1()
    test_rollover_schedule_lease_expiring_today_lands_in_year_1()
    test_rollover_schedule_percentages_sum_to_100_across_buckets()
    test_rollover_schedule_high_risk_when_year_1_concentrated()
    test_rollover_schedule_low_risk_when_evenly_laddered()
    test_rollover_schedule_empty_portfolio_does_not_crash()
    test_rollover_schedule_all_leases_already_expired_reports_real_data_not_none()
    test_loss_to_lease_happy_path_top_rent_becomes_the_proxy()
    test_loss_to_lease_excludes_property_with_only_one_lease()
    test_loss_to_lease_different_properties_not_compared_against_each_other()
    test_loss_to_lease_excludes_lease_missing_address()
    test_loss_to_lease_excludes_lease_missing_sqft()
    test_loss_to_lease_address_normalization_matches_formatting_variants()
    test_loss_to_lease_groups_different_suites_in_same_building()
    test_loss_to_lease_does_not_merge_genuinely_different_buildings_with_similar_names()
    test_loss_to_lease_all_equal_rent_shows_zero_gap_not_excluded()
    test_loss_to_lease_sorted_by_monthly_upside_descending()
    test_loss_to_lease_empty_portfolio_does_not_crash()
    test_rent_roll_reconciliation_agreement_produces_no_mismatches()
    test_rent_roll_reconciliation_flags_tenant_mismatch()
    test_rent_roll_reconciliation_flags_stale_rent()
    test_rent_roll_reconciliation_flags_stale_end_date()
    test_rent_roll_reconciliation_rent_tolerance_absorbs_rounding_noise()
    test_rent_roll_reconciliation_small_dollar_gap_on_tiny_unit_not_flagged_by_pct_alone()
    test_rent_roll_reconciliation_large_dollar_gap_on_huge_unit_still_flagged()
    test_rent_roll_reconciliation_row_with_no_matching_lease_document_not_compared()
    test_rent_roll_reconciliation_lease_document_with_no_rent_roll_row_excluded()
    test_rent_roll_reconciliation_missing_field_on_one_side_skips_only_that_field()
    test_rent_roll_reconciliation_empty_portfolio_does_not_crash()
    test_rent_roll_reconciliation_extension_matching_is_case_insensitive()
    test_rent_roll_reconciliation_multiple_leases_at_same_address_pairwise()
    test_t12_reconciliation_agreement()
    test_t12_reconciliation_flags_real_discrepancy_rent_roll_higher()
    test_t12_reconciliation_flags_real_discrepancy_t12_higher()
    test_t12_reconciliation_small_gap_not_flagged()
    test_t12_reconciliation_dual_tolerance_absolute_alone_not_enough()
    test_t12_reconciliation_dual_tolerance_percentage_alone_not_enough()
    test_t12_reconciliation_building_level_not_unit_level()
    test_t12_reconciliation_different_building_not_included()
    test_t12_reconciliation_no_matching_leases_returns_honest_not_found()
    test_t12_reconciliation_lease_missing_rent_excluded_not_zero()
    test_t12_reconciliation_empty_portfolio_does_not_crash()
    print("\nAll portfolio tests passed.")
