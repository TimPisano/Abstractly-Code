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

import re
from datetime import date, timedelta
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


# Rent/sqft and square-footage disagreement thresholds between two leases
# that claim the same property address -- wider than the below-market-
# rent thresholds in risk_analysis.py, since this is comparing two
# specific figures directly rather than one figure against a portfolio
# mean, and ordinary unit-to-unit variation within one building is
# itself real and shouldn't be flagged.
_CROSS_LEASE_RENT_PSF_HIGH_PCT = 25.0
_CROSS_LEASE_RENT_PSF_MEDIUM_PCT = 10.0
_CROSS_LEASE_SQFT_HIGH_PCT = 15.0
_CROSS_LEASE_SQFT_MEDIUM_PCT = 5.0


def _normalize_address(address: Optional[str]) -> Optional[str]:
    """
    Loose matching for "same property" across independently-uploaded
    leases -- lowercased, punctuation stripped, whitespace collapsed.
    Not a real address-parsing/geocoding solution, just enough to catch
    the common case of the exact same address typed the same way in two
    lease documents. Deliberately conservative: this will miss a real
    match typed two different ways ("Suite 200" vs "Ste. 200"), but
    will not incorrectly match two genuinely different addresses -- a
    missed opportunity to flag something is a far smaller problem than
    an actively misleading false match.
    """
    if not address:
        return None
    normalized = re.sub(r"[^\w\s]", "", address.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def _lease_label(lease: Dict[str, Any]) -> str:
    return lease.get("display_name") or lease.get("filename") or f"lease #{lease.get('id')}"


def _cross_lease_flag_pair(
    lease_a: Dict[str, Any], lease_b: Dict[str, Any],
    field: str, basis: str, display_a: str, display_b: str,
    diff_pct: float, severity: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """One mismatch, phrased twice -- once from each lease's own perspective, naming the other lease it disagrees with. Same flag shape risk_analysis.py's other checks produce, so these merge directly into a lease's existing risk-flags list."""
    label_a, label_b = _lease_label(lease_a), _lease_label(lease_b)
    address = field_value(lease_a, "property_address")

    def _flag(this_label, other_label, this_display, other_display, other_id):
        return {
            "severity": severity,
            "category": "cross_lease_mismatch",
            "field": field,
            "message": f"{basis.capitalize()} ({this_display}) disagrees with \"{other_label}\" ({other_display}) at the same property by {diff_pct:.0f}%",
            "explanation": (
                f"Both this lease and \"{other_label}\" list the property address as "
                f"\"{address}\", but their {basis} figures disagree by {diff_pct:.0f}% "
                f"({this_display} vs {other_display}). This could mean one of the two "
                "figures was misextracted, or that these are actually different units "
                "within the same building -- worth confirming against both source "
                "documents before relying on either."
            ),
            "other_lease_id": other_id,
            "other_lease_name": other_label,
        }

    return (
        _flag(label_a, label_b, display_a, display_b, lease_b.get("id")),
        _flag(label_b, label_a, display_b, display_a, lease_a.get("id")),
    )


def _compare_lease_pair(lease_a: Dict[str, Any], lease_b: Dict[str, Any]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Every mismatch found between two leases that share a (normalized) property address."""
    pairs = []

    psf_a = rent_per_sqft(field_value(lease_a, "rent_amount"), field_value(lease_a, "square_footage"))
    psf_b = rent_per_sqft(field_value(lease_b, "rent_amount"), field_value(lease_b, "square_footage"))
    if psf_a and psf_b:
        diff_pct = abs(psf_a - psf_b) / max(psf_a, psf_b) * 100
        severity = (
            "high" if diff_pct >= _CROSS_LEASE_RENT_PSF_HIGH_PCT
            else "medium" if diff_pct >= _CROSS_LEASE_RENT_PSF_MEDIUM_PCT
            else None
        )
        if severity:
            pairs.append(_cross_lease_flag_pair(
                lease_a, lease_b, "rent_amount", "rent per square foot",
                f"${psf_a:,.2f}/sq ft/mo", f"${psf_b:,.2f}/sq ft/mo", diff_pct, severity,
            ))

    sqft_a = parse_square_footage(field_value(lease_a, "square_footage"))
    sqft_b = parse_square_footage(field_value(lease_b, "square_footage"))
    if sqft_a and sqft_b:
        diff_pct = abs(sqft_a - sqft_b) / max(sqft_a, sqft_b) * 100
        severity = (
            "high" if diff_pct >= _CROSS_LEASE_SQFT_HIGH_PCT
            else "medium" if diff_pct >= _CROSS_LEASE_SQFT_MEDIUM_PCT
            else None
        )
        if severity:
            pairs.append(_cross_lease_flag_pair(
                lease_a, lease_b, "square_footage", "square footage",
                f"{sqft_a:,.0f} sq ft", f"{sqft_b:,.0f} sq ft", diff_pct, severity,
            ))

    return pairs


def compute_cross_lease_mismatches(leases: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """
    Compares leases sharing the same (normalized) property address and
    flags when their rent-per-square-foot or square footage figures
    disagree more than ordinary unit-to-unit variation would explain --
    two independently-uploaded leases for the same address with wildly
    different numbers usually means one of them was misextracted, or
    that they're actually different units at a multi-tenant property.
    Either way, worth a human's second look before either number is
    trusted; this is the "flag mismatches between two already-uploaded
    sources" half of the confidence story, alongside the single-lease
    format/range validation in field_extractor.py.

    Returns {lease_id: [flag, ...]}, each flag already in risk_analysis.
    py's standard {severity, category, field, message, explanation}
    shape and phrased from that lease's own perspective -- ready to
    merge directly into that lease's own risk-flags list. A lease with
    no address, or no property-address match to any other lease, simply
    doesn't appear as a key.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for lease in leases:
        address = _normalize_address(field_value(lease, "property_address"))
        if address is None:
            continue
        groups.setdefault(address, []).append(lease)

    mismatches: Dict[int, List[Dict[str, Any]]] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                for flag_a, flag_b in _compare_lease_pair(group[i], group[j]):
                    mismatches.setdefault(group[i]["id"], []).append(flag_a)
                    mismatches.setdefault(group[j]["id"], []).append(flag_b)

    return mismatches


def compute_lease_confidence_summary(lease: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tallies this lease's 15 extracted fields by confidence tier, plus how
    many were flagged during validation (field_extractor.py's format/
    range/OCR-clarity checks -- see _apply_confidence_validation there).
    This is the trust mechanism a premium tier's pricing depends on: a
    real, computed count grounded in what was actually found and
    checked, not a decorative badge.

    "not_found" fields (confidence None, never extracted at all) are
    counted separately from "low" -- a field the extractor genuinely
    couldn't find is a different, more complete kind of gap than one it
    found but isn't sure about.
    """
    fields = lease.get("extracted_fields") or {}
    counts = {"high": 0, "medium": 0, "low": 0, "not_found": 0}
    flagged_fields: List[str] = []

    for name in FIELD_NAMES:
        entry = fields.get(name) or {}
        confidence = entry.get("confidence")
        if confidence in counts:
            counts[confidence] += 1
        else:
            counts["not_found"] += 1
        if entry.get("validation_note"):
            flagged_fields.append(name)

    return {
        "total_fields": len(FIELD_NAMES),
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "not_found": counts["not_found"],
        "flagged_for_review": len(flagged_fields),
        "flagged_fields": flagged_fields,
    }


def compute_portfolio_confidence_summary(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates compute_lease_confidence_summary across the whole
    portfolio -- the "47 of 50 fields high-confidence, 3 flagged for
    review" number a buyer actually sees, computed fresh from the same
    per-lease summaries the lease detail page shows, not a separate
    parallel calculation that could silently disagree with it.
    """
    totals = {"total_fields": 0, "high": 0, "medium": 0, "low": 0, "not_found": 0, "flagged_for_review": 0}
    for lease in leases:
        summary = compute_lease_confidence_summary(lease)
        for key in totals:
            totals[key] += summary[key]

    high_confidence_pct = (
        round((totals["high"] / totals["total_fields"]) * 100, 1) if totals["total_fields"] else None
    )

    return {
        "lease_count": len(leases),
        **totals,
        "extracted_fields": totals["high"] + totals["medium"] + totals["low"],
        "high_confidence_pct": high_confidence_pct,
    }


# How far a lease's rent/sqft has to sit from the portfolio average
# (in either direction) to count as a "variance outlier" for the
# monthly report -- deliberately its own threshold, not reused from
# risk_analysis.py's BELOW_MARKET_* constants, since this is a
# two-sided screen (both unusually cheap AND unusually expensive are
# worth a reviewer's attention in a monthly portfolio scan) rather
# than risk_analysis.py's one-sided "is this lease underpriced" check.
RENT_VARIANCE_OUTLIER_PCT = 20.0


def compute_rent_variance_outliers(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Leases whose rent-per-square-foot deviates significantly from the
    portfolio average, in either direction. Broader than risk_analysis.
    py's below-market-rent check (which only flags rent that's too
    LOW): a lease priced well ABOVE market is just as worth a reviewer's
    attention in a monthly scan -- it could mean genuine upside, a
    misextracted figure, or a lease approaching renewal that needs
    repricing scrutiny before the market moves further.

    Only leases with both a parseable rent and square footage are
    considered -- comparing raw monthly rent across differently-sized
    spaces would mostly measure size, not price, same reasoning the
    below-market check already uses.

    Returns entries sorted by |deviation| descending (most extreme
    first): {lease_id, display_name, tenant, rent_per_sqft,
    portfolio_avg_rent_per_sqft, diff_pct, direction: "above"|"below"}.
    """
    avg_psf = compute_portfolio_metrics(leases).get("avg_rent_per_sqft")
    if not avg_psf or avg_psf <= 0:
        return []

    outliers = []
    for lease in leases:
        lease_psf = rent_per_sqft(field_value(lease, "rent_amount"), field_value(lease, "square_footage"))
        if lease_psf is None or lease_psf <= 0:
            continue
        diff_pct = ((lease_psf - avg_psf) / avg_psf) * 100
        if abs(diff_pct) < RENT_VARIANCE_OUTLIER_PCT:
            continue
        outliers.append({
            "lease_id": lease.get("id"),
            "display_name": _lease_label(lease),
            "tenant": field_value(lease, "tenant"),
            "rent_per_sqft": round(lease_psf, 2),
            "portfolio_avg_rent_per_sqft": round(avg_psf, 2),
            "diff_pct": round(diff_pct, 1),
            "direction": "above" if diff_pct > 0 else "below",
        })

    outliers.sort(key=lambda entry: abs(entry["diff_pct"]), reverse=True)
    return outliers


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
    cross_lease_mismatches = compute_cross_lease_mismatches(leases)

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
        cross_lease_flags = cross_lease_mismatches.get(lease["id"], [])
        flags = analyze_lease_risks(fields, context, date_candidates, cross_lease_flags)
        notable_flags = [f for f in flags if f["severity"] in ("high", "medium")]
        if notable_flags:
            unusual_terms.append(_attention_entry(lease, flags=notable_flags))

    expiring_soon.sort(key=lambda entry: entry["days_remaining"])

    return {
        "expiring_soon": expiring_soon,
        "missing_data": missing_data,
        "unusual_terms": unusual_terms,
    }


# The three windows the expiration-alerts widget buckets into. 90 days
# is also compute_attention_items' outer window (ATTENTION_EXPIRING_DAYS)
# -- kept as the same constant so "expiring soon" can't mean two
# different horizons on the same dashboard.
EXPIRATION_ALERT_DAYS = ATTENTION_EXPIRING_DAYS


def _days_bucket(days_remaining: int) -> str:
    if days_remaining <= 30:
        return "30"
    if days_remaining <= 60:
        return "60"
    return "90"


def compute_expiration_alerts(
    leases: List[Dict[str, Any]],
    reference_date: Optional[date] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Two lists for the dashboard's expiration-alerts widget, each sorted
    soonest-first:

      - expiring: leases whose lease_end_date falls within the next
        EXPIRATION_ALERT_DAYS (90) days, bucketed "30"/"60"/"90" by how
        soon. Already-expired leases are a different, more urgent
        problem (handled by the "unusual terms"/risk machinery
        elsewhere) and are excluded here, same as compute_attention_
        items' expiring_soon.

      - renewal_deadlines: leases whose renewal *notice* deadline
        (lease_end_date minus the notice period parsed out of
        renewal_options) falls within the same window -- kept
        separate from straight expirations because the two dates are
        usually different, and the renewal deadline is the one that
        actually requires action first. A deadline that has already
        passed (negative days_remaining) is still included and
        bucketed "overdue" rather than dropped, since a missed
        renewal window is the single most actionable flag this
        function can surface -- silently hiding it once the date
        passes would be exactly the "produces a garbage/misleading
        picture instead of surfacing the problem" failure mode this
        project's quality bar exists to prevent. A lease that has
        already fully expired is excluded either way -- there's
        nothing left to renew.
    """
    if reference_date is None:
        reference_date = date.today()

    expiring = []
    renewal_deadlines = []

    for lease in leases:
        end_date = parse_date(field_value(lease, "lease_end_date"))
        if end_date is None:
            continue
        days_to_end = (end_date - reference_date).days
        if days_to_end < 0:
            continue

        if days_to_end <= EXPIRATION_ALERT_DAYS:
            expiring.append(_attention_entry(
                lease,
                lease_end_date=field_value(lease, "lease_end_date"),
                days_remaining=days_to_end,
                bucket=_days_bucket(days_to_end),
            ))

        notice_days = parse_renewal_options(field_value(lease, "renewal_options")).get("notice_days")
        if notice_days is None:
            continue
        deadline = end_date - timedelta(days=notice_days)
        days_to_deadline = (deadline - reference_date).days
        if days_to_deadline <= EXPIRATION_ALERT_DAYS:
            renewal_deadlines.append(_attention_entry(
                lease,
                lease_end_date=field_value(lease, "lease_end_date"),
                renewal_deadline=deadline.isoformat(),
                notice_days=notice_days,
                days_remaining=days_to_deadline,
                bucket="overdue" if days_to_deadline < 0 else _days_bucket(days_to_deadline),
            ))

    expiring.sort(key=lambda entry: entry["days_remaining"])
    renewal_deadlines.sort(key=lambda entry: entry["days_remaining"])

    return {
        "expiring": expiring,
        "renewal_deadlines": renewal_deadlines,
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
