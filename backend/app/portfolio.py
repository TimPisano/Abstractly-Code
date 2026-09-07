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
    "termination_options",
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


def _normalize_for_matching(text: Optional[str]) -> Optional[str]:
    """
    Loose text matching for "is this the same real-world thing" across
    independently-uploaded leases -- lowercased, punctuation stripped,
    whitespace collapsed. Not real entity resolution, just enough to
    catch the common case of the exact same name/address typed the same
    way in two lease documents. Deliberately conservative: this will
    miss a real match typed two different ways ("Suite 200" vs
    "Ste. 200", "Acme Corp" vs "Acme Corporation"), but will not
    incorrectly match two genuinely different things -- a missed
    opportunity to flag/group something is a far smaller problem than
    an actively misleading false match (e.g. merging "Acme Corp" and
    "Acme Corp West" into one tenant would understate concentration
    risk, which is the opposite of what this kind of check is for).
    """
    if not text:
        return None
    normalized = re.sub(r"[^\w\s]", "", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def _normalize_address(address: Optional[str]) -> Optional[str]:
    """
    Loose matching for "same UNIT" (exact address, suite included)
    across independently-uploaded leases -- see _normalize_for_matching.
    Used by cross-lease mismatch detection, where the whole point is
    catching the SAME unit uploaded twice with conflicting numbers, so
    two different suites in the same building must NOT match here (see
    _normalize_building_address for the opposite, building-level need).
    """
    return _normalize_for_matching(address)


# Strips a recognizable suite/unit designator (", Suite 200", " Ste. 4",
# " Unit 12B", " #301") wherever it appears, case-insensitively, before
# the usual lowercase/punctuation/whitespace normalization runs. Applied
# in _normalize_building_address only -- _normalize_address (used for
# cross-lease mismatch detection) deliberately does NOT do this, since
# that check exists specifically to catch the same unit's numbers
# disagreeing across two uploads, which requires the suite to still be
# part of the match key there.
_SUITE_DESIGNATOR_RE = re.compile(r",?\s*(?:suite|ste\.?|unit|apt\.?|#)\s*[\w-]+", re.IGNORECASE)


def _normalize_building_address(address: Optional[str]) -> Optional[str]:
    """
    Loose matching for "same BUILDING" (suite/unit number ignored)
    across independently-uploaded leases -- for grouping DIFFERENT
    units that share a property, e.g. for an internal rent comp. "123
    Main St, Suite 100" and "123 Main St, Suite 200" must match here
    (same building, different units) even though they must NOT match
    under _normalize_address (which exists for the opposite purpose --
    catching the same unit disagreeing with itself). Same conservative
    posture as _normalize_for_matching otherwise: this will miss a
    building match typed inconsistently in other ways (a different
    street abbreviation, a missing city), but won't merge two
    genuinely different buildings just because both happen to remove a
    suite number.
    """
    if not address:
        return None
    stripped = _SUITE_DESIGNATOR_RE.sub("", address)
    return _normalize_for_matching(stripped)


def _normalize_tenant_name(tenant: Optional[str]) -> Optional[str]:
    """Loose matching for "same tenant" across independently-uploaded leases (e.g. a chain with several units) -- see _normalize_for_matching."""
    return _normalize_for_matching(tenant)


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


# Herfindahl-Hirschman Index thresholds, on the standard 0-10,000 scale
# (sum of each tenant's percent-of-total-rent, squared). These are the
# exact thresholds DOJ/FTC merger guidelines use for market
# concentration -- borrowed rather than invented, since "how concentrated
# is too concentrated" needs a defensible reference point, not an
# arbitrary number. A portfolio is also independently flagged "high" if
# any single tenant exceeds TOP_TENANT_HIGH_RISK_PCT of total rent, since
# a single dominant tenant is an intuitive cash-flow risk regardless of
# how the HHI shape reads -- HHI alone can under-flag a portfolio with
# one big tenant plus many small ones if the small ones pull the index
# down.
HHI_HIGH_THRESHOLD = 2500.0
HHI_MODERATE_THRESHOLD = 1500.0
TOP_TENANT_HIGH_RISK_PCT = 25.0
TOP_TENANT_MODERATE_RISK_PCT = 15.0


def compute_tenant_concentration(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    How much of the portfolio's total rent depends on a small number of
    tenants -- a real due-diligence concern independent of any single
    lease's own terms: a portfolio where one tenant is 40% of total rent
    takes a much bigger hit if that one tenant leaves than a portfolio
    where no tenant exceeds 5%, even if every individual lease looks
    fine on its own.

    Leases are grouped by tenant name (conservatively normalized --
    case/punctuation/whitespace only, see _normalize_tenant_name) so a
    chain tenant with several separate lease uploads (e.g. three
    locations of the same retailer) is correctly counted as one tenant,
    not three. Deliberately does NOT do fuzzy/substring matching: two
    similarly-named but genuinely different tenants ("Acme Corp" and
    "Acme Corp West") must never be merged, since that would understate
    concentration risk -- the exact failure mode this check exists to
    catch. A missed merge (same tenant counted twice under slightly
    different spellings) is a smaller, more honest failure than a false
    merge.

    A lease only counts toward this analysis if it has BOTH a tenant
    name and a parseable, positive rent amount -- one without the other
    can't be attributed to anyone's total. Leases missing either are
    excluded and counted in `excluded_lease_count` rather than silently
    dropped, so the result is honest about how much of the portfolio it
    could actually analyze. A lease with a missing tenant name is never
    bucketed into a generic "Unknown" tenant -- that would fabricate a
    single large "tenant" out of unrelated leases and could itself look
    like a concentration risk that doesn't really exist.

    Returns `{tenant_count, lease_count, excluded_lease_count,
    total_rent, tenants: [{tenant, rent, pct_of_total}, ...] sorted by
    rent descending, top_1_pct, top_3_pct, top_5_pct, hhi,
    concentration_level}`. `concentration_level` is "high" / "moderate"
    / "low", based on HHI and the largest single tenant's share (see
    the threshold constants above). When there isn't enough data to
    analyze (no leases, or none with both a tenant and a rent), every
    numeric field is None and concentration_level is None rather than a
    misleading 0 -- an unknown concentration is not the same thing as a
    known-zero one.
    """
    groups: Dict[str, Dict[str, Any]] = {}  # normalized name -> {"tenant": display name, "rent": total}
    lease_count = 0
    excluded_lease_count = 0

    for lease in leases:
        tenant_display = field_value(lease, "tenant")
        rent = parse_currency(field_value(lease, "rent_amount"))
        normalized = _normalize_tenant_name(tenant_display)

        # rent == 0.0 is deliberately NOT excluded here: parse_currency
        # distinguishes "no dollar figure found" (None) from "found, and
        # it's genuinely zero" (0.0) -- a percentage-only retail lease
        # with no base rent is a real, if uncommon, lease structure, not
        # a data-quality problem. (rent < 0 can't actually happen given
        # parse_currency's regex has no sign handling, but the guard
        # costs nothing and documents the assumption.) A portfolio where
        # EVERY included lease has $0 rent -- so total_rent ends up 0 --
        # is handled below, not here: that's a "can't compute a
        # percentage of zero" case, not a "this one lease is bad" case.
        if normalized is None or rent is None or rent < 0:
            excluded_lease_count += 1
            continue

        lease_count += 1
        if normalized not in groups:
            groups[normalized] = {"tenant": tenant_display, "rent": 0.0}
        groups[normalized]["rent"] += rent

    total_rent = sum(g["rent"] for g in groups.values())

    if not groups or total_rent <= 0:
        return {
            "tenant_count": 0,
            "lease_count": 0,
            "excluded_lease_count": excluded_lease_count if not groups else len(leases),
            "total_rent": None,
            "tenants": [],
            "top_1_pct": None,
            "top_3_pct": None,
            "top_5_pct": None,
            "hhi": None,
            "concentration_level": None,
        }

    # Computed from the raw (unrounded) rent/total_rent fractions, not
    # from already-rounded per-tenant percentages -- rounding each
    # tenant's share first and then summing those rounded values for
    # top_N_pct/hhi compounds rounding error across tenants (visible as
    # e.g. a portfolio's per-tenant percentages summing to 100.01, not
    # 100.00, in a real test against a 6-tenant scenario). Rounding
    # happens exactly once, on the final reported numbers.
    raw_shares = [(g["tenant"], g["rent"], g["rent"] / total_rent * 100) for g in groups.values()]
    raw_shares.sort(key=lambda entry: entry[1], reverse=True)

    tenants = [
        {"tenant": name, "rent": round(rent, 2), "pct_of_total": round(pct, 2)}
        for name, rent, pct in raw_shares
    ]

    def _cumulative_pct(n: int) -> float:
        return round(sum(pct for _, _, pct in raw_shares[:n]), 2)

    hhi = round(sum(pct ** 2 for _, _, pct in raw_shares), 1)
    top_1_pct = _cumulative_pct(1)

    if hhi >= HHI_HIGH_THRESHOLD or top_1_pct >= TOP_TENANT_HIGH_RISK_PCT:
        concentration_level = "high"
    elif hhi >= HHI_MODERATE_THRESHOLD or top_1_pct >= TOP_TENANT_MODERATE_RISK_PCT:
        concentration_level = "moderate"
    else:
        concentration_level = "low"

    return {
        "tenant_count": len(tenants),
        "lease_count": lease_count,
        "excluded_lease_count": excluded_lease_count,
        "total_rent": round(total_rent, 2),
        "tenants": tenants,
        "top_1_pct": _cumulative_pct(1),
        "top_3_pct": _cumulative_pct(3),
        "top_5_pct": _cumulative_pct(5),
        "hhi": hhi,
        "concentration_level": concentration_level,
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
    "What needs attention today" — the four reasons a lease would be
    worth a human's time right now, computed fresh from the same data
    every other view uses (no separate flag stored on the lease):

      - expiring_soon: lease_end_date within ATTENTION_EXPIRING_DAYS days
        (including already-due-today, excluding leases already expired —
        those are a different problem, not a thing to plan for)
      - missing_data: missing one or more of CORE_FIELDS_FOR_COMPLETENESS
        entirely (nothing extracted for that field at all)
      - needs_verification: has one or more CORE_FIELDS_FOR_COMPLETENESS
        that WAS found but is only medium-confidence -- a different
        problem from missing_data (there's a value, a human just needs
        to glance at it and confirm it's right, via
        POST .../fields/<name>/verify, rather than type a replacement)
      - unusual_terms: has at least one medium/high severity risk flag
        from the existing risk_analysis engine (below-market rent,
        missing standard clauses, notice-period outliers, inconsistent
        escalation schedules, date conflicts) — reused rather than
        reimplemented, so "unusual" means the same thing here as it does
        on the lease detail page's risk panel.

    Both missing_data and needs_verification are grouped one entry PER
    LEASE (see _attention_entry), each carrying the full list of that
    lease's own gaps -- never one entry per (lease, field) pair, which
    would scatter the same lease across several rows and defeat the
    point of a "here's everything wrong with this one lease" view.

    A lease can appear in more than one list; each list is independently
    useful ("show me every incomplete lease" vs "show me every lease
    expiring soon"), so no dedup is done across lists.
    """
    if reference_date is None:
        reference_date = date.today()

    expiring_soon = []
    missing_data = []
    needs_verification = []
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

        medium_confidence_fields = [
            {"field": f, "value": field_value(lease, f)}
            for f in CORE_FIELDS_FOR_COMPLETENESS
            if field_value(lease, f) is not None and (fields.get(f) or {}).get("confidence") == "medium"
        ]
        if medium_confidence_fields:
            needs_verification.append(_attention_entry(lease, needs_verification_fields=medium_confidence_fields))

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
        "needs_verification": needs_verification,
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


# Average calendar year length (accounts for leap years), same
# averaging approach as DAYS_PER_MONTH above -- used to convert a day
# delta into "years remaining" for WALT and the rollover schedule.
DAYS_PER_YEAR = 365.25


def compute_walt(leases: List[Dict[str, Any]], reference_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Weighted Average Lease Term (WALT): the average remaining lease term
    across the portfolio, weighted by rent -- each lease pulls the
    average toward its own remaining term in proportion to how much
    rent it represents, not just counted equally per lease. This is the
    standard industry convention (not an arbitrary choice): WALT exists
    to answer "how much of my REVENUE is locked in, and for how long,"
    not "how many leases do I have left." A portfolio can have plenty of
    leases remaining and still have a short, risky WALT if the big
    anchor tenants are the ones expiring soonest.

    A lease only contributes if it has BOTH a parseable lease_end_date
    and a parseable, positive rent -- one without the other can't be
    placed in the weighted average. Leases already expired as of
    `reference_date` (negative days remaining) are excluded entirely,
    same precedent compute_portfolio_health already established for
    "time remaining" math -- an expired lease doesn't have a remaining
    term to average in, it has none. A lease expiring exactly on
    `reference_date` (0 days remaining) IS included, at 0 years -- that
    is a real, meaningful data point (a lease with no time left is
    correctly pulling the average toward zero), not an error state,
    same "expiring today counts as still-active-today" rule
    compute_expiration_timeline already uses.

    Returns `{walt_years, lease_count, excluded_lease_count,
    total_weighted_rent}`. When there's nothing to average (no leases,
    or none with both a usable end date and rent, or the only usable
    leases all have $0 rent so there's no weight to average by),
    `walt_years` is None -- an unknown WALT is not the same thing as a
    zero one.
    """
    if reference_date is None:
        reference_date = date.today()

    lease_count = 0
    excluded_lease_count = 0
    weighted_years_sum = 0.0
    rent_sum = 0.0

    for lease in leases:
        end_date = parse_date(field_value(lease, "lease_end_date"))
        rent = parse_currency(field_value(lease, "rent_amount"))

        if end_date is None or rent is None or rent <= 0:
            excluded_lease_count += 1
            continue

        days_remaining = (end_date - reference_date).days
        if days_remaining < 0:
            excluded_lease_count += 1
            continue

        years_remaining = days_remaining / DAYS_PER_YEAR
        weighted_years_sum += years_remaining * rent
        rent_sum += rent
        lease_count += 1

    if lease_count == 0 or rent_sum <= 0:
        return {
            "walt_years": None,
            "lease_count": 0,
            "excluded_lease_count": len(leases),
            "total_weighted_rent": None,
        }

    return {
        "walt_years": round(weighted_years_sum / rent_sum, 2),
        "lease_count": lease_count,
        "excluded_lease_count": excluded_lease_count,
        "total_weighted_rent": round(rent_sum, 2),
    }


# Rollover-risk read: how much of total rent rolling over in Year 1 (the
# nearest, most urgent window) counts as concerning. There's no external
# standard for this the way HHI is a real DOJ/FTC benchmark for tenant
# concentration -- this is a stated, reasonable rule of thumb (a
# portfolio with a well-laddered lease schedule keeps any single year's
# rollover well under a fifth of total rent; above a quarter in the very
# next year is a real near-term releasing/re-tenanting risk), not a
# market-tested threshold. Deliberately conservative and named as such
# in the docstring below, same posture as the pricing page's own
# "recommended, not market-tested" framing for numbers without an
# external reference point.
ROLLOVER_YEAR_1_HIGH_RISK_PCT = 25.0
ROLLOVER_YEAR_1_MODERATE_RISK_PCT = 15.0

_ROLLOVER_BUCKET_NAMES = ["year_1", "year_2", "year_3", "year_4", "year_5", "year_6_plus"]


def compute_rollover_schedule(leases: List[Dict[str, Any]], reference_date: Optional[date] = None) -> Dict[str, Any]:
    """
    The lease rollover schedule: what share of total portfolio rent (and
    of total lease count) expires in each of the next five years, plus a
    catch-all "6+ years" bucket -- the standard exhibit for seeing how
    much revenue is "at risk" of needing to be re-leased, and when,
    rather than just a single blended average (that's what compute_walt
    is for). Complements compute_expiration_timeline (which buckets by
    month, per-lease, for "what needs attention soon") with a coarser,
    percentage-of-total view organized the way an underwriting exhibit
    actually gets built: by year, by share of rent.

    Same inclusion rule as compute_walt: a lease needs both a parseable
    end date and a parseable, positive rent to be placed in a bucket.
    Leases already expired as of `reference_date` go in their own
    `already_expired` bucket -- not dropped, and deliberately NOT folded
    into year_1, since "will expire soon" and "has already expired" are
    materially different risks (an already-expired lease still on the
    books usually means a holdover tenant or a data problem, either way
    worth its own visibility rather than blending into the forward-
    looking schedule). A lease expiring exactly on `reference_date`
    lands in year_1 (0-12 months forward), matching the
    "expiring today counts as still-active-today" rule used elsewhere.

    Returns `{buckets: {bucket_name: {rent, pct_of_total_rent,
    lease_count, pct_of_total_leases}, ...}, already_expired: {rent,
    lease_count}, total_rent, lease_count, excluded_lease_count,
    rollover_risk_level}`. `total_rent` and `lease_count` are scoped to
    the forward-looking (bucketed) leases only, deliberately excluding
    already-expired ones -- every bucket's percentages are relative to
    that same forward-looking total, so they sum to (approximately) 100%
    across the six buckets. `already_expired` reports raw rent/lease
    count only, with no percentage of its own: a percentage of "total
    rent" that itself excludes the expired leases would be misleading,
    and there's no single obviously-correct larger denominator to use
    instead. `rollover_risk_level` ("high"/"moderate"/"low") is driven
    by year_1's share of total rent -- see the threshold constants above
    for why, and their explicitly non-market-tested status.

    Two distinct empty cases, handled differently on purpose: no usable
    data at all (no leases, or none with both a date and rent) returns
    a fully None-shaped "not enough data" result, same posture as
    compute_walt. But a portfolio where every analyzable lease has
    ALREADY expired is NOT "not enough data" -- it's real data showing
    the worst possible rollover picture (100% already rolled over,
    nothing scheduled in any future year) -- so that case returns real
    zero-filled buckets, a real (non-null) `already_expired` count, and
    `rollover_risk_level` forced to "high", rather than silently
    discarding the finding by returning None.
    """
    if reference_date is None:
        reference_date = date.today()

    buckets = {name: {"rent": 0.0, "lease_count": 0} for name in _ROLLOVER_BUCKET_NAMES}
    already_expired = {"rent": 0.0, "lease_count": 0}
    lease_count = 0  # forward-looking (bucketed) leases only -- see docstring
    excluded_lease_count = 0
    total_rent = 0.0  # forward-looking rent only, same scope as lease_count

    for lease in leases:
        end_date = parse_date(field_value(lease, "lease_end_date"))
        rent = parse_currency(field_value(lease, "rent_amount"))

        if end_date is None or rent is None or rent <= 0:
            excluded_lease_count += 1
            continue

        days_remaining = (end_date - reference_date).days

        if days_remaining < 0:
            already_expired["rent"] += rent
            already_expired["lease_count"] += 1
            continue

        lease_count += 1
        total_rent += rent
        years_remaining = days_remaining / DAYS_PER_YEAR
        bucket_index = min(int(years_remaining), 5)  # 0-4 -> year_1..year_5 ; 5+ -> year_6_plus
        bucket_name = _ROLLOVER_BUCKET_NAMES[bucket_index]
        buckets[bucket_name]["rent"] += rent
        buckets[bucket_name]["lease_count"] += 1

    # Nothing at all to work with -- neither a forward-looking schedule
    # nor any already-expired data. Genuinely "not enough data."
    if lease_count == 0 and already_expired["lease_count"] == 0:
        return {
            "buckets": None,
            "already_expired": None,
            "total_rent": None,
            "lease_count": 0,
            "excluded_lease_count": len(leases),
            "rollover_risk_level": None,
        }

    # There IS real data, but none of it is forward-looking -- every
    # analyzable lease has already expired. This is not "not enough
    # data": it's the single worst possible rollover picture (100% of
    # whatever's left has already rolled over), and reporting it as a
    # null result would hide the most important finding this function
    # can surface. Buckets are all real zeros (there's genuinely nothing
    # scheduled to expire in any future year), not a placeholder.
    if lease_count == 0:
        bucket_results = {
            name: {"rent": 0.0, "pct_of_total_rent": 0.0, "lease_count": 0, "pct_of_total_leases": 0.0}
            for name in _ROLLOVER_BUCKET_NAMES
        }
        return {
            "buckets": bucket_results,
            "already_expired": {"rent": round(already_expired["rent"], 2), "lease_count": already_expired["lease_count"]},
            "total_rent": 0.0,
            "lease_count": 0,
            "excluded_lease_count": excluded_lease_count,
            "rollover_risk_level": "high",
        }

    bucket_results = {}
    for name, data in buckets.items():
        bucket_results[name] = {
            "rent": round(data["rent"], 2),
            "pct_of_total_rent": round(data["rent"] / total_rent * 100, 2),
            "lease_count": data["lease_count"],
            "pct_of_total_leases": round(data["lease_count"] / lease_count * 100, 2),
        }

    year_1_pct = bucket_results["year_1"]["pct_of_total_rent"]
    if year_1_pct >= ROLLOVER_YEAR_1_HIGH_RISK_PCT:
        rollover_risk_level = "high"
    elif year_1_pct >= ROLLOVER_YEAR_1_MODERATE_RISK_PCT:
        rollover_risk_level = "moderate"
    else:
        rollover_risk_level = "low"

    return {
        "buckets": bucket_results,
        "already_expired": {"rent": round(already_expired["rent"], 2), "lease_count": already_expired["lease_count"]},
        "total_rent": round(total_rent, 2),
        "lease_count": lease_count,
        "excluded_lease_count": excluded_lease_count,
        "rollover_risk_level": rollover_risk_level,
    }


def compute_loss_to_lease(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    "Loss to lease": how much upside exists if a unit were re-leased at
    the strongest rent this portfolio has actually proven a comparable
    unit can command, rather than what it's leased at today.

    This is deliberately NOT compared against true external market
    rent -- this system has no market-rent data source (no comps feed,
    no survey integration), and inventing a market-rate number would be
    fabricating data. Instead, the "market" proxy used here is
    internal: the highest rent-per-square-foot already achieved among
    OTHER leases at the same BUILDING -- grouped via
    _normalize_building_address, which strips the suite/unit number
    before matching (deliberately NOT the same _normalize_address used
    for cross-lease mismatch detection elsewhere in this module, which
    needs the exact opposite: matching the same UNIT, suite included,
    to catch that unit's own numbers disagreeing across two uploads --
    using it here would have made every differently-suited unit in a
    building look comp-less, which was a real bug caught only by
    testing against a multi-suite building, not by clean single-suite
    test fixtures). A lease is only included if at least one OTHER
    lease shares its building -- a property with only one lease on
    file has no internal comp to measure against, and is honestly
    excluded rather than compared against unrelated space elsewhere in
    the portfolio (this system has no property-type field, so a
    portfolio-wide comp would risk comparing, say, a downtown office
    suite against a suburban
    retail kiosk -- same-property grouping is the only comp basis
    available that doesn't risk that).

    Deliberately does NOT classify a "high/moderate/low" risk level the
    way compute_tenant_concentration and compute_rollover_schedule do:
    those have a defensible reference point (an external standard, or a
    stated rule of thumb) to hang a threshold on. An internal-proxy
    "market rate" has neither, and attaching a risk label would lend it
    more authority than it honestly has. This function reports the raw
    numbers; the reader judges them.

    A lease at exactly its property's top rent has 0% loss (correctly
    included at zero, not excluded -- it has a real, computed answer,
    it's just zero) -- only a lease with strictly lower rent/sqft than
    its property's max shows a positive gap.

    Returns `{leases: [{lease_id, display_name, tenant, rent_per_sqft,
    property_top_rent_per_sqft, loss_pct, monthly_upside}, ...] sorted
    by monthly_upside descending, total_monthly_upside, lease_count,
    excluded_lease_count}`. `monthly_upside` is
    (property_top_psf - this_lease_psf) * this_lease_sqft -- the
    dollar gap, not just the percentage, since a small percentage gap
    on a huge unit can matter more than a large percentage gap on a
    tiny one. `excluded_lease_count` covers both "missing rent/sqft/
    address" and "no other lease at the same property to compare
    against" -- both are real, honest reasons a lease can't get a
    computed answer, not the same failure, but reported as one count
    for simplicity (matching this module's existing per-metric,
    single-excluded-count convention elsewhere).
    """
    # Group by normalized address first, keeping every lease that at
    # least has enough to be grouped -- the "needs 2+ leases at this
    # address" filter happens after grouping, not before, since we
    # don't know a lease is comp-less until we see its whole group.
    groups: Dict[str, List[Dict[str, Any]]] = {}
    ungroupable_count = 0

    for lease in leases:
        address = _normalize_building_address(field_value(lease, "property_address"))
        psf = rent_per_sqft(field_value(lease, "rent_amount"), field_value(lease, "square_footage"))
        if address is None or psf is None or psf <= 0:
            ungroupable_count += 1
            continue
        groups.setdefault(address, []).append(lease)

    results = []
    comp_less_count = 0

    for group in groups.values():
        if len(group) < 2:
            comp_less_count += len(group)
            continue

        group_psf = [
            (lease, rent_per_sqft(field_value(lease, "rent_amount"), field_value(lease, "square_footage")))
            for lease in group
        ]
        top_psf = max(psf for _, psf in group_psf)

        for lease, psf in group_psf:
            sqft = parse_square_footage(field_value(lease, "square_footage"))
            loss_pct = round((top_psf - psf) / top_psf * 100, 2)
            monthly_upside = round((top_psf - psf) * sqft, 2)
            results.append({
                "lease_id": lease.get("id"),
                "display_name": _lease_label(lease),
                "tenant": field_value(lease, "tenant"),
                "rent_per_sqft": round(psf, 2),
                "property_top_rent_per_sqft": round(top_psf, 2),
                "loss_pct": loss_pct,
                "monthly_upside": monthly_upside,
            })

    results.sort(key=lambda entry: entry["monthly_upside"], reverse=True)

    return {
        "leases": results,
        "total_monthly_upside": round(sum(r["monthly_upside"] for r in results), 2) if results else None,
        "lease_count": len(results),
        "excluded_lease_count": ungroupable_count + comp_less_count,
    }


# The only way a non-PDF file enters the leases table is through the
# rent roll import route (see rent_roll_import.py) -- so the uploaded
# filename's extension is a reliable signal for "is this record a rent
# roll row or an actual lease document," without needing a dedicated
# schema column just for this one check.
_RENT_ROLL_IMPORT_EXTENSIONS = {"csv", "xlsx"}


def _is_rent_roll_import(lease: Dict[str, Any]) -> bool:
    filename = (lease.get("filename") or "").lower()
    return "." in filename and filename.rsplit(".", 1)[1] in _RENT_ROLL_IMPORT_EXTENSIONS


# A rent-figure "disagreement" must clear BOTH a percentage and an
# absolute-dollar bar before being flagged -- either alone is too easy
# to over- or under-trigger. A 1%-only rule would flag a $0.01 rounding
# artifact on a $2 line item; a $5-only rule would flag noise on a
# $50,000/mo anchor tenant's rent. Both together catch a real
# discrepancy at any unit size without flagging rounding noise at either
# extreme.
_RENT_DISAGREEMENT_TOLERANCE_PCT = 1.0
_RENT_DISAGREEMENT_TOLERANCE_ABS = 5.0


def compute_rent_roll_reconciliation(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Cross-checks an imported rent roll against the actual lease PDF
    documents on file for the same units, and flags where they
    disagree -- the real due-diligence problem this exists for: a
    property manager's system saying one thing (often stale after a
    renewal or rent increase that never made it back into that system)
    while the signed lease itself says another.

    "Same unit" is exact address match (same normalized
    property_address, suite included -- reusing _normalize_address,
    the same conservative same-UNIT matching compute_cross_lease_
    mismatches already uses, NOT the same-BUILDING matching
    compute_loss_to_lease uses -- this check is about one unit's two
    records disagreeing with each other, not about comparing different
    units). A rent roll row with no matching lease PDF on file --
    the common case, since a rent roll typically covers far more units
    than have an uploaded lease PDF -- is simply not compared against
    anything. That's not an error; there's nothing to reconcile it
    with yet.

    Compares three fields, each with its own honest tolerance:
      - tenant name: any disagreement at all (after the same
        conservative case/punctuation-insensitive normalization used
        throughout this module) is flagged -- there's no "close
        enough" for whether it's the same tenant.
      - rent_amount: flagged only past BOTH tolerance constants above
        -- see their own comment for why both are needed together.
      - lease_end_date: any disagreement at all -- a rent roll showing
        the pre-renewal expiration while the lease was actually
        extended is exactly the stale-data problem this function
        exists to catch, and there's no meaningful "close enough" for
        a date either.
    A field missing on either side of a given pair is simply not
    compared for that field on that pair -- not a mismatch, nothing to
    compare.

    Returns `{mismatches: [{rent_roll_lease_id, lease_document_id,
    address, field, rent_roll_value, lease_document_value}, ...],
    rent_roll_lease_count, lease_document_count, compared_pair_count}`.
    An empty `mismatches` list alongside real (non-zero) counts means
    real reconciliation happened and everything agreed -- genuinely
    good news, not an absence of an answer. That's different from all
    counts being 0 (most commonly: no rent roll has ever been
    imported), which means there's nothing to reconcile yet. Both are
    valid, distinguishable by the counts themselves -- this function
    deliberately does NOT use the rest of this module's "None means
    not enough data" convention, since an empty list here is a real,
    positive result, not an unknown one.
    """
    rent_roll_leases = [l for l in leases if _is_rent_roll_import(l)]
    lease_documents = [l for l in leases if not _is_rent_roll_import(l)]

    address_groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for lease in rent_roll_leases:
        address = _normalize_address(field_value(lease, "property_address"))
        if address is None:
            continue
        address_groups.setdefault(address, {"rent_roll": [], "lease_document": []})["rent_roll"].append(lease)
    for lease in lease_documents:
        address = _normalize_address(field_value(lease, "property_address"))
        if address is None or address not in address_groups:
            continue  # no rent roll row at this exact address -- nothing to reconcile against
        address_groups[address]["lease_document"].append(lease)

    def _add_mismatch(mismatches, rr_lease, doc_lease, address, field, rr_value, doc_value):
        mismatches.append({
            "rent_roll_lease_id": rr_lease.get("id"),
            "lease_document_id": doc_lease.get("id"),
            "address": address,
            "field": field,
            "rent_roll_value": rr_value,
            "lease_document_value": doc_value,
        })

    mismatches: List[Dict[str, Any]] = []
    compared_pair_count = 0

    for group in address_groups.values():
        if not group["lease_document"]:
            continue  # rent roll rows here, but no lease PDF to compare any of them against
        for rr_lease in group["rent_roll"]:
            for doc_lease in group["lease_document"]:
                compared_pair_count += 1
                address = field_value(rr_lease, "property_address") or field_value(doc_lease, "property_address")

                rr_tenant_norm = _normalize_for_matching(field_value(rr_lease, "tenant"))
                doc_tenant_norm = _normalize_for_matching(field_value(doc_lease, "tenant"))
                if rr_tenant_norm and doc_tenant_norm and rr_tenant_norm != doc_tenant_norm:
                    _add_mismatch(
                        mismatches, rr_lease, doc_lease, address, "tenant",
                        field_value(rr_lease, "tenant"), field_value(doc_lease, "tenant"),
                    )

                rr_rent = parse_currency(field_value(rr_lease, "rent_amount"))
                doc_rent = parse_currency(field_value(doc_lease, "rent_amount"))
                if rr_rent is not None and doc_rent is not None and rr_rent != doc_rent:
                    diff_abs = abs(rr_rent - doc_rent)
                    larger = max(rr_rent, doc_rent)
                    diff_pct = (diff_abs / larger * 100) if larger > 0 else 0.0
                    if diff_abs > _RENT_DISAGREEMENT_TOLERANCE_ABS and diff_pct > _RENT_DISAGREEMENT_TOLERANCE_PCT:
                        _add_mismatch(
                            mismatches, rr_lease, doc_lease, address, "rent_amount",
                            field_value(rr_lease, "rent_amount"), field_value(doc_lease, "rent_amount"),
                        )

                rr_end = parse_date(field_value(rr_lease, "lease_end_date"))
                doc_end = parse_date(field_value(doc_lease, "lease_end_date"))
                if rr_end is not None and doc_end is not None and rr_end != doc_end:
                    _add_mismatch(
                        mismatches, rr_lease, doc_lease, address, "lease_end_date",
                        field_value(rr_lease, "lease_end_date"), field_value(doc_lease, "lease_end_date"),
                    )

    return {
        "mismatches": mismatches,
        "rent_roll_lease_count": len(rent_roll_leases),
        "lease_document_count": len(lease_documents),
        "compared_pair_count": compared_pair_count,
    }


# A T12 discrepancy must clear BOTH a percentage and an absolute-dollar
# bar before being flagged -- same dual-tolerance reasoning as
# _RENT_DISAGREEMENT_TOLERANCE_* above, just recalibrated for this
# comparison's very different scale: an ANNUAL, BUILDING-WIDE dollar
# figure (tens of thousands to millions), not one lease's monthly rent.
# A percentage-only rule would flag ordinary rounding/timing noise on a
# large property; a dollar-only rule would flag routine noise on a
# small one. 5% keeps a large property from over-triggering on a minor
# timing difference (e.g. a mid-period rent step); $3,000/year keeps a
# small property from over-triggering on the kind of rounding that's
# unavoidable when a T12 covers a slightly different trailing-12 window
# than "right now."
_T12_DISAGREEMENT_TOLERANCE_PCT = 5.0
_T12_DISAGREEMENT_TOLERANCE_ABS = 3000.0


def compute_t12_reconciliation(
    leases: List[Dict[str, Any]],
    property_address: str,
    t12_annual_rental_income: float,
) -> Dict[str, Any]:
    """
    Cross-checks the rent roll's own annualized rent for one property
    against that property's T12 (trailing 12-month operating
    statement) actual rental income line -- the real due-diligence
    question this exists for: does what the rent roll claims the
    building collects match what the operating statement says it
    actually collected. `t12_annual_rental_income` is the number
    t12_import.py already extracted (see that module for how it's
    chosen -- always the ACTUAL collected income line, never "Gross
    Potential Rent" or another theoretical figure, which would make
    this comparison wrong in one direction by definition rather than
    catching a real discrepancy).

    Unlike compute_rent_roll_reconciliation (same UNIT, exact address,
    one rent roll row vs. one lease PDF), this is a whole-BUILDING
    comparison -- a T12 covers an entire property, not one unit, so
    grouping uses _normalize_building_address (suite/unit stripped),
    the same convention compute_loss_to_lease uses for the same reason.
    Every lease at that building counts toward the rent roll side,
    regardless of source (PDF or imported rent roll) -- get_all_
    effective_leases already handles amendment overrides upstream, same
    as every other function in this module.

    A T12 is NOT persisted anywhere (unlike a rent roll import, it
    doesn't represent a lease or tenant -- inserting it into the leases
    table would corrupt tenant concentration, WALT, and every other
    per-lease computation with a fake non-lease row). It's parsed fresh
    from the uploaded file and compared in the same request; nothing
    about the T12 itself survives past this one response.

    Returns `{property_address, matched_lease_count,
    excluded_lease_count, rent_roll_annual_rent,
    t12_annual_rental_income, difference, difference_pct, direction,
    flagged}`. `rent_roll_annual_rent` (and everything derived from it)
    is None if NO lease at this building has a usable rent_amount --
    an honest "not enough data on the rent roll side to compare,"
    distinct from a real comparison that happens to agree (difference
    of 0, flagged False). `direction` is "rent_roll_higher",
    "t12_higher", or "agree" -- which side is bigger matters for how a
    human reads the result (a rent roll UNDER-stating collected income
    is a very different story, e.g. a stale export, than a rent roll
    OVER-stating it, e.g. leases signed after the T12's own trailing
    window closed -- this function reports the fact, not a guess at
    which explanation applies).
    """
    normalized_target = _normalize_building_address(property_address)

    matched_leases = [
        lease for lease in leases
        if _normalize_building_address(field_value(lease, "property_address")) == normalized_target
    ] if normalized_target else []

    matched_rents = []
    excluded_lease_count = 0
    for lease in matched_leases:
        rent = parse_currency(field_value(lease, "rent_amount"))
        if rent is None:
            excluded_lease_count += 1
            continue
        matched_rents.append(rent)

    if not matched_rents:
        return {
            "property_address": property_address,
            "matched_lease_count": 0,
            "excluded_lease_count": excluded_lease_count,
            "rent_roll_annual_rent": None,
            "t12_annual_rental_income": round(t12_annual_rental_income, 2),
            "difference": None,
            "difference_pct": None,
            "direction": None,
            "flagged": None,
        }

    rent_roll_annual_rent = round(sum(matched_rents) * 12, 2)
    t12_value = round(t12_annual_rental_income, 2)
    difference = round(rent_roll_annual_rent - t12_value, 2)
    larger = max(abs(rent_roll_annual_rent), abs(t12_value))
    difference_pct = round(abs(difference) / larger * 100, 2) if larger > 0 else 0.0

    if difference > 0:
        direction = "rent_roll_higher"
    elif difference < 0:
        direction = "t12_higher"
    else:
        direction = "agree"

    flagged = abs(difference) > _T12_DISAGREEMENT_TOLERANCE_ABS and difference_pct > _T12_DISAGREEMENT_TOLERANCE_PCT

    return {
        "property_address": property_address,
        "matched_lease_count": len(matched_rents),
        "excluded_lease_count": excluded_lease_count,
        "rent_roll_annual_rent": rent_roll_annual_rent,
        "t12_annual_rental_income": t12_value,
        "difference": difference,
        "difference_pct": difference_pct,
        "direction": direction,
        "flagged": flagged,
    }
