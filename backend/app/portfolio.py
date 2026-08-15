"""
Portfolio-wide aggregation over stored leases: headline metrics
(averages/totals across the whole book) and a lease-expiration timeline.

Everything here works off the *display strings* the extraction engine
produces, run through `normalize.py` to get real numbers. That means a
lease can always contribute to some metrics and not others: a lease with
rent but no square footage still counts toward average rent, it just
can't count toward rent-per-square-foot.

That partial-participation rule is the central design point of this
module. A portfolio average must never be diluted by leases where the
field simply wasn't found — averaging $6,000 and "not found" as if the
second were $0 produces a confidently wrong number, which is exactly the
failure mode this project's quality bar exists to prevent. So every
aggregate here is computed only over the leases whose value actually
parsed, and a metric with no parseable inputs at all reports None ("we
don't know") rather than 0.0 ("we know it's zero").
"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .normalize import (
    escalation_rate_consistency,
    parse_currency,
    parse_date,
    parse_percent,
    parse_renewal_options,
    parse_square_footage,
    rent_per_sqft,
)
from .risk_analysis import analyze_lease_risks


# The full extracted-field set, in the extractor's own order. Kept as an
# explicit list so `fields_missing_count` reports every field every time —
# including fields that no lease in the portfolio happens to have, which
# are precisely the ones a user most needs to see flagged.
FIELD_NAMES = [
    "tenant",
    "landlord",
    "rent_amount",
    "lease_start_date",
    "lease_end_date",
    "property_address",
    "security_deposit",
    "cam_charges",
    "rent_escalation",
    "renewal_options",
    "permitted_use",
    "exclusivity_clause",
    "insurance_requirements",
    "default_cure_period",
    "square_footage",
]

# Average calendar month length (365.25 / 12). Used to convert a day delta
# into "months remaining" for expiration bucketing — see
# compute_expiration_timeline for why an approximation is the right call.
DAYS_PER_MONTH = 30.4375

# "Needs attention today" window: a lease expiring within this many days
# is surfaced on the dashboard, not just somewhere in the full timeline.
ATTENTION_EXPIRING_DAYS = 90

# A lease missing any of these is flagged as incomplete/needing review —
# these are the fields portfolio math and the dashboard depend on most;
# a missing special clause is a smaller gap than a missing rent amount.
CORE_FIELDS_FOR_COMPLETENESS = [
    "tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date",
]


def field_value(lease: Dict[str, Any], field_name: str) -> Optional[str]:
    """
    Safely pull one field's display value out of a lease record.

    Tolerates a missing `extracted_fields`, a missing field key, and a
    None field entry, because callers aggregate across a whole portfolio
    and one malformed record shouldn't take down the entire computation.
    A blank/whitespace-only string is normalized to None so it counts as
    "not found" rather than as a real value.
    """
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field_name) or {}
    value = entry.get("value")
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _mean(values: List[float], digits: int = 2) -> Optional[float]:
    """Average of the values that made it this far, or None if there are none."""
    if not values:
        return None
    return round(sum(values) / len(values), digits)


def _total(values: List[float], digits: int = 2) -> Optional[float]:
    """
    Sum, or None when nothing parsed.

    None rather than 0.0 on purpose: an empty portfolio (or one where no
    lease had a parseable rent) has an *unknown* total, not a zero total.
    """
    if not values:
        return None
    return round(sum(values), digits)


def escalation_pct(value: Optional[str]) -> Optional[float]:
    """
    A single annual escalation rate for one lease, from either shape the
    extractor can produce.

    A flat "3% annually" string has the rate stated outright. A
    year-by-year table ("Year 1: $6,000.00; Year 2: $6,180.00; ...")
    doesn't state a rate at all, so the implied rate is recovered from the
    year-over-year increases and averaged. Returns None when the value is
    neither shape (e.g. a two-year table, which has too few consecutive
    increases for a meaningful rate), so the lease is skipped rather than
    contributing a guess.
    """
    flat = parse_percent(value)
    if flat is not None:
        return flat

    consistency = escalation_rate_consistency(value)
    if consistency and consistency["rates"]:
        rates = consistency["rates"]
        # Rounded because the rate is *derived* from dollar amounts: a
        # clean 4% schedule comes back as 4.000000000000001 otherwise,
        # which would surface verbatim in benchmark output.
        return round(sum(rates) / len(rates), 2)

    return None


def compute_portfolio_metrics(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Headline metrics across every lease in the portfolio.

    Each aggregate is built from only the leases whose relevant field
    parsed; a lease missing that field is skipped, not counted as zero.
    `avg_rent_per_sqft` is stricter still — it requires both rent and
    square footage on the same lease, since a per-unit figure computed
    from mismatched populations would be meaningless.
    """
    rents: List[float] = []
    cams: List[float] = []
    deposits: List[float] = []
    sqfts: List[float] = []
    per_sqft: List[float] = []
    escalations: List[float] = []
    notice_days: List[float] = []
    missing = {name: 0 for name in FIELD_NAMES}

    for lease in leases:
        for name in FIELD_NAMES:
            if field_value(lease, name) is None:
                missing[name] += 1

        rent = parse_currency(field_value(lease, "rent_amount"))
        if rent is not None:
            rents.append(rent)

        cam = parse_currency(field_value(lease, "cam_charges"))
        if cam is not None:
            cams.append(cam)

        deposit = parse_currency(field_value(lease, "security_deposit"))
        if deposit is not None:
            deposits.append(deposit)

        sqft = parse_square_footage(field_value(lease, "square_footage"))
        if sqft is not None:
            sqfts.append(sqft)

        unit_rent = rent_per_sqft(
            field_value(lease, "rent_amount"),
            field_value(lease, "square_footage"),
        )
        if unit_rent is not None:
            per_sqft.append(unit_rent)

        escalation = escalation_pct(field_value(lease, "rent_escalation"))
        if escalation is not None:
            escalations.append(escalation)

        notice = parse_renewal_options(field_value(lease, "renewal_options"))["notice_days"]
        if notice is not None:
            notice_days.append(float(notice))

    return {
        "lease_count": len(leases),
        "total_monthly_rent": _total(rents),
        "avg_monthly_rent": _mean(rents),
        "avg_rent_per_sqft": _mean(per_sqft),
        "total_cam_exposure": _total(cams),
        "avg_cam": _mean(cams),
        "avg_security_deposit": _mean(deposits),
        "avg_escalation_pct": _mean(escalations),
        "avg_notice_days": _mean(notice_days),
        "total_square_footage": _total(sqfts),
        "fields_missing_count": missing,
    }


def portfolio_context_for_risk_analysis(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The subset of portfolio metrics that risk analysis compares an
    individual lease against ("this rent is 22% below the portfolio
    average").

    Derived from compute_portfolio_metrics rather than recomputed, so
    there is exactly one definition of "the portfolio average" in the
    codebase — a risk flag citing a number the dashboard disagrees with
    would undermine the whole point of showing the comparison.
    """
    metrics = compute_portfolio_metrics(leases)
    return {
        "avg_rent": metrics["avg_monthly_rent"],
        "avg_rent_per_sqft": metrics["avg_rent_per_sqft"],
        "avg_cam": metrics["avg_cam"],
        "avg_security_deposit": metrics["avg_security_deposit"],
        "avg_notice_days": metrics["avg_notice_days"],
        "avg_escalation_pct": metrics["avg_escalation_pct"],
        "lease_count": metrics["lease_count"],
    }


def _timeline_entry(
    lease: Dict[str, Any],
    months_remaining: Optional[float],
) -> Dict[str, Any]:
    """One row of the expiration timeline, enough to render without a re-query."""
    return {
        "lease_id": lease.get("id"),
        "filename": lease.get("filename"),
        "display_name": lease.get("display_name") or lease.get("filename"),
        "tenant": field_value(lease, "tenant"),
        "lease_end_date": field_value(lease, "lease_end_date"),
        "months_remaining": months_remaining,
    }


def compute_expiration_timeline(
    leases: List[Dict[str, Any]],
    reference_date: Optional[date] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Buckets leases by how long until they expire, relative to
    `reference_date` (defaulting to today — pass an explicit date to make
    results reproducible).

    Months remaining is a day-delta converted at an average month length
    rather than true calendar-month arithmetic. The buckets are 6 months
    wide, so sub-day precision changes nothing about which bucket a lease
    lands in, and the approximation avoids the end-of-month edge cases
    ("one month after Jan 31") that exact calendar math would force us to
    take an arbitrary position on.

    A lease whose end date is missing or unparseable goes to
    `unknown_expiration` instead of being dropped — an unknown expiration
    is a thing the user needs to act on, not a thing to hide.
    """
    if reference_date is None:
        reference_date = date.today()

    buckets: Dict[str, List[Dict[str, Any]]] = {
        "expiring_0_6_months": [],
        "expiring_6_12_months": [],
        "expiring_12_24_months": [],
        "expiring_24_plus_months": [],
        "already_expired": [],
        "unknown_expiration": [],
    }

    for lease in leases:
        end_date = parse_date(field_value(lease, "lease_end_date"))
        if end_date is None:
            buckets["unknown_expiration"].append(_timeline_entry(lease, None))
            continue

        months = round((end_date - reference_date).days / DAYS_PER_MONTH, 1)
        entry = _timeline_entry(lease, months)

        if months < 0:
            # A lease ending exactly on the reference date is treated as
            # still-active-today (0 months remaining), not expired.
            buckets["already_expired"].append(entry)
        elif months < 6:
            buckets["expiring_0_6_months"].append(entry)
        elif months < 12:
            buckets["expiring_6_12_months"].append(entry)
        elif months < 24:
            buckets["expiring_12_24_months"].append(entry)
        else:
            buckets["expiring_24_plus_months"].append(entry)

    def _sort_key(entry: Dict[str, Any]) -> Tuple[float, str]:
        # Filename breaks ties so the ordering is stable and testable.
        return (entry["months_remaining"], entry["filename"] or "")

    for name, entries in buckets.items():
        if name == "unknown_expiration":
            entries.sort(key=lambda entry: entry["filename"] or "")
        else:
            entries.sort(key=_sort_key)

    return buckets


def _attention_entry(lease: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    """Common shape for an item in any of the three attention lists."""
    return {
        "lease_id": lease.get("id"),
        "filename": lease.get("filename"),
        "display_name": lease.get("display_name") or lease.get("filename"),
        "tenant": field_value(lease, "tenant"),
        **extra,
    }


def compute_attention_items(
    leases: List[Dict[str, Any]],
    reference_date: Optional[date] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    "What needs attention today" — the three reasons a lease would be
    worth a human's time right now, computed fresh from the same data
    every other view uses (no separate flag stored on the lease):

      - expiring_soon: lease_end_date within ATTENTION_EXPIRING_DAYS days
        (including already-due-today, excluding leases already expired —
        those are a different problem, not a thing to plan for)
      - missing_data: missing one or more of CORE_FIELDS_FOR_COMPLETENESS
      - unusual_terms: has at least one medium/high severity risk flag
        from the existing risk_analysis engine (below-market rent,
        missing standard clauses, notice-period outliers, inconsistent
        escalation schedules, date conflicts) — reused rather than
        reimplemented, so "unusual" means the same thing here as it does
        on the lease detail page's risk panel.

    A lease can appear in more than one list; each list is independently
    useful ("show me every incomplete lease" vs "show me every lease
    expiring soon"), so no dedup is done across lists.
    """
    if reference_date is None:
        reference_date = date.today()

    expiring_soon = []
    missing_data = []
    unusual_terms = []

    context = portfolio_context_for_risk_analysis(leases)

    for lease in leases:
        fields = lease.get("extracted_fields") or {}

        end_date = parse_date(field_value(lease, "lease_end_date"))
        if end_date is not None:
            days_remaining = (end_date - reference_date).days
            if 0 <= days_remaining <= ATTENTION_EXPIRING_DAYS:
                expiring_soon.append(_attention_entry(
                    lease,
                    lease_end_date=field_value(lease, "lease_end_date"),
                    days_remaining=days_remaining,
                ))

        missing_fields = [f for f in CORE_FIELDS_FOR_COMPLETENESS if field_value(lease, f) is None]
        if missing_fields:
            missing_data.append(_attention_entry(lease, missing_fields=missing_fields))

        date_candidates = lease.get("date_candidates")
        flags = analyze_lease_risks(fields, context, date_candidates)
        notable_flags = [f for f in flags if f["severity"] in ("high", "medium")]
        if notable_flags:
            unusual_terms.append(_attention_entry(lease, flags=notable_flags))

    expiring_soon.sort(key=lambda entry: entry["days_remaining"])

    return {
        "expiring_soon": expiring_soon,
        "missing_data": missing_data,
        "unusual_terms": unusual_terms,
    }


def compute_portfolio_health(
    leases: List[Dict[str, Any]],
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    A morning-glance health strip: how much of the portfolio is in good
    shape, how urgent the renewal picture is, and how much rent is on
    the clock over the next two windows.

    "Verified" here means a lease appears in neither compute_attention_
    items' missing_data nor unusual_terms list — i.e. nothing about it
    currently needs a human look. That is deliberately the same
    computation as the attention panel, not a separate heuristic, so the
    two can never disagree about which leases are fine.
    """
    if reference_date is None:
        reference_date = date.today()

    total = len(leases)
    attention = compute_attention_items(leases, reference_date)
    needs_review_ids = {item["lease_id"] for item in attention["missing_data"]}
    needs_review_ids |= {item["lease_id"] for item in attention["unusual_terms"]}
    needs_review = len(needs_review_ids)
    fully_verified = total - needs_review

    days_to_expiration: List[int] = []
    rent_expiring_6mo: List[float] = []
    rent_expiring_12mo: List[float] = []

    for lease in leases:
        end_date = parse_date(field_value(lease, "lease_end_date"))
        if end_date is None:
            continue
        days = (end_date - reference_date).days
        if days < 0:
            continue  # already expired — not part of "time remaining"

        days_to_expiration.append(days)

        rent = parse_currency(field_value(lease, "rent_amount"))
        if rent is None:
            continue
        if days <= 182:  # ~6 months
            rent_expiring_6mo.append(rent)
        if days <= 365:  # ~12 months
            rent_expiring_12mo.append(rent)

    return {
        "total_leases": total,
        "fully_verified_count": fully_verified,
        "needs_review_count": needs_review,
        "fully_verified_pct": round(fully_verified / total * 100, 1) if total else None,
        "avg_days_to_expiration": _mean([float(d) for d in days_to_expiration], digits=0),
        "monthly_rent_expiring_6mo": _total(rent_expiring_6mo),
        "monthly_rent_expiring_12mo": _total(rent_expiring_12mo),
    }
