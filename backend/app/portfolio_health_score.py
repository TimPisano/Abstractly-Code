"""
Portfolio Health Score: a single, defensible 0-100 number (plus a
letter rating) summarizing how much a user can trust their portfolio's
data RIGHT NOW -- the number meant to make someone check the app
regularly, the same way a credit score or a uptime SLA number works:
one figure that's actually grounded in real, documented sub-measures,
not a vibe.

NOT the same thing as portfolio.py's existing compute_portfolio_health
(the dashboard's "morning glance" strip: verified-vs-needs-review
counts, renewal urgency, rent on the clock). That function answers "is
there anything urgent to look at today." This one answers a narrower,
different question: "how much can I trust the DATA itself, right now."
Different question, different formula, deliberately not merged into
one function -- see DECISIONS.md for the full reasoning.

There is no real multi-user account system in this app (see
DECISIONS.md's "Identity model" entry) -- there is exactly one shared
portfolio, so "per account" here means "over the whole current
portfolio," the same scope every other portfolio-wide computation in
this app already uses.

=====================================================================
THE FORMULA (documented here, not just in code, per explicit request)
=====================================================================

Overall score = weighted sum of four 0-100 sub-scores:

  30%  Confidence Distribution   -- how much of the extracted DATA itself
                                     is trustworthy
  25%  Source Verification       -- how much of each lease's core
                                     information was actually found, not
                                     silently missing
  25%  Unresolved Discrepancies  -- how many known, still-open problems
                                     are sitting in the portfolio
  20%  Data Freshness            -- how recently the data was last
                                     uploaded or amended

These weights (WEIGHTS below) are this module's own judgment call, not
a market-tested standard -- documented explicitly rather than
presented as more authoritative than it is (same honesty standard
compute_loss_to_lease and compute_tenant_concentration already hold
themselves to for their own thresholds). Confidence distribution and
source verification are weighted heaviest because they're about
whether the extracted DATA is even usable at all; discrepancies are
about known ACTIVE problems; freshness is a real but secondary signal
(a portfolio can have perfectly accurate three-month-old data).

--- 1. Confidence Distribution (30%) ---
Reuses portfolio.py's compute_portfolio_confidence_summary (the exact
same high/medium/low/not_found tally the dashboard and every export
already show -- never a second, parallel confidence calculation that
could disagree with it). Each extracted field contributes a weighted
credit: high=1.0, medium=0.6, low=0.3, not_found=0.0. Score =
(weighted credit sum / total fields) * 100. Medium and low get PARTIAL
credit rather than zero, because a low-confidence match is still a
real finding a human can verify against its citation -- it isn't as
worthless as a field that was never found at all.

--- 2. Source Verification (25%) ---
A lease counts as "fully verified" if BOTH: (a) every CORE_FIELDS_FOR_
COMPLETENESS field (tenant, landlord, rent_amount, lease_start_date,
lease_end_date -- the fields portfolio math depends on most) was
actually found, and (b) zero of its fields were flagged during
extraction validation (field_extractor.py's format/range/OCR-clarity
checks). Every field that DOES have a value already carries a real,
audit-trail-verifiable source citation by construction (see the "Full
audit trail" item's invariant, enforced and tested at extraction
time) -- so "fully verified" here means "the core facts are present
AND nothing about them looked questionable enough to flag," which is
the honest, checkable version of "source verification" this system
can actually claim. Score = 100 * (fully-verified lease count / total
lease count).

--- 3. Unresolved Discrepancies (25%) ---
Every currently-OPEN discrepancy (Item 2's discrepancies table, portfolio-
wide) counts against the score, normalized by portfolio size (an open
discrepancy in a 3-lease portfolio is a much bigger problem than the
same count in a 300-lease one) via a smooth diminishing-returns curve
rather than a hard cutoff: score = 100 / (1 + open_discrepancies_per_lease).
Zero open discrepancies per lease scores 100; 1 per lease scores 50; 4
per lease scores 20 -- it can approach zero but never go negative or
hit a cliff at an arbitrary count.

--- 4. Data Freshness (20%) ---
A lease's "last refreshed" timestamp is the later of its own upload
time and its most recent amendment's upload time (an amendment IS a
real refresh of that lease's data, same convention portfolio_
history.py uses). A lease is "stale" if that's more than
`staleness_threshold_months` (default 6) ago. Score = 100 * (fresh
lease count / total lease count).

--- Rating bands ---
90-100 Excellent | 75-89.9 Good | 60-74.9 Fair | 40-59.9 Poor | 0-39.9 Critical

--- Empty portfolio ---
Zero leases returns score=None, rating="No Data" -- an unscored
portfolio is not the same thing as a 0/100 portfolio, same "None means
unknown, not a known zero" convention every aggregate in portfolio.py
already follows.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import database
from .portfolio import (
    CORE_FIELDS_FOR_COMPLETENESS,
    _normalize_building_address,
    _normalize_tenant_name,
    compute_lease_confidence_summary,
    compute_portfolio_confidence_summary,
    field_value,
)

WEIGHTS = {
    "confidence_distribution": 0.30,
    "source_verification": 0.25,
    "unresolved_discrepancies": 0.25,
    "data_freshness": 0.20,
}

_CONFIDENCE_CREDIT = {"high": 1.0, "medium": 0.6, "low": 0.3}

DEFAULT_STALENESS_THRESHOLD_MONTHS = 6
_APPROX_DAYS_PER_MONTH = 30.4375

# Discrepancy types that, per app/discrepancies.py's own sync_lease_risk_flags,
# ALWAYS carry a real lease_id (or related_lease_id) when created correctly.
# A row of one of these types with neither set is a data anomaly, not a
# legitimate "this type has no lease" case -- see _current_open_discrepancies.
_LEASE_SCOPED_DISCREPANCY_TYPES = {"lease_risk_flag", "cross_lease_mismatch", "rent_roll_reconciliation"}

_RATING_BANDS = [
    (90.0, "Excellent"),
    (75.0, "Good"),
    (60.0, "Fair"),
    (40.0, "Poor"),
    (0.0, "Critical"),
]


def _rating_for(score: float) -> str:
    for threshold, label in _RATING_BANDS:
        if score >= threshold:
            return label
    return "Critical"


def _confidence_distribution_component(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = compute_portfolio_confidence_summary(leases)
    total_fields = summary["total_fields"]
    if total_fields == 0:
        return {"score": None, "weight": WEIGHTS["confidence_distribution"], **summary}

    weighted_credit = sum(_CONFIDENCE_CREDIT[tier] * summary[tier] for tier in _CONFIDENCE_CREDIT)
    score = round(weighted_credit / total_fields * 100, 1)
    return {"score": score, "weight": WEIGHTS["confidence_distribution"], **summary}


def _source_verification_component(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not leases:
        return {"score": None, "weight": WEIGHTS["source_verification"], "fully_verified_count": 0, "total_count": 0}

    fully_verified_count = 0
    for lease in leases:
        has_all_core_fields = all(field_value(lease, f) is not None for f in CORE_FIELDS_FOR_COMPLETENESS)
        flagged_for_review = compute_lease_confidence_summary(lease)["flagged_for_review"]
        if has_all_core_fields and flagged_for_review == 0:
            fully_verified_count += 1

    score = round(fully_verified_count / len(leases) * 100, 1)
    return {
        "score": score,
        "weight": WEIGHTS["source_verification"],
        "fully_verified_count": fully_verified_count,
        "total_count": len(leases),
    }


def _current_open_discrepancies(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Open discrepancies relevant to the portfolio AS IT EXISTS RIGHT NOW
    -- deliberately NOT database.list_discrepancies(status="open")
    unfiltered. Discrepancies are permanent records by design (Item 2)
    and are never cascade-deleted when their lease is deleted (a
    deliberate choice -- see that item's own entry), so an unscoped
    count keeps accumulating forever across a long-lived database's
    entire history. Confirmed this actually happens, not a
    hypothetical, and in TWO distinct ways -- both caught live against
    the real dev database, neither by a unit test (a fresh temp DB per
    test can't reproduce accumulation):

    1. Lease-scoped discrepancies (lease_risk_flag, cross_lease_
       mismatch, rent_roll_reconciliation) whose lease_id/
       related_lease_id no longer exists in the current portfolio at
       all -- filtered out by requiring the id to be in the current
       lease set.
    2. Portfolio-wide discrepancies with NO lease_id at all
       (tenant_concentration, t12_reconciliation -- facts about a
       TENANT or an ADDRESS, not one lease row) accumulated from every
       distinct tenant name / property address this database has ever
       been tested with across its whole history -- 351 of them found
       live, the first fix above didn't touch these at all since they
       were never lease-scoped to begin with. Filtered out by
       requiring the tenant_concentration's tenant (normalized) or the
       t12_reconciliation's property address (normalized, building-
       level) to still appear somewhere in the CURRENT portfolio.
    """
    current_lease_ids = {lease["id"] for lease in leases}
    current_tenant_names = {_normalize_tenant_name(field_value(l, "tenant")) for l in leases} - {None}
    current_addresses = {_normalize_building_address(field_value(l, "property_address")) for l in leases} - {None}

    relevant = []
    for disc in database.list_discrepancies(status="open"):
        lease_id, related_id = disc.get("lease_id"), disc.get("related_lease_id")
        if lease_id is not None or related_id is not None:
            if lease_id in current_lease_ids or related_id in current_lease_ids:
                relevant.append(disc)
            continue

        if disc["discrepancy_type"] == "tenant_concentration":
            if _normalize_tenant_name(disc["details"].get("tenant")) in current_tenant_names:
                relevant.append(disc)
        elif disc["discrepancy_type"] == "t12_reconciliation":
            if _normalize_building_address(disc["details"].get("property_address")) in current_addresses:
                relevant.append(disc)
        elif disc["discrepancy_type"] in _LEASE_SCOPED_DISCREPANCY_TYPES:
            # A type that's SUPPOSED to always carry a lease_id, but
            # doesn't here -- a data anomaly (this exact database had
            # 343 real rows like this, from a since-fixed schema bug
            # that let a deleted lease silently null out the
            # discrepancies that referenced it -- see
            # _migrate_discrepancies_table_drop_lease_fk in
            # database.py), not a legitimate "no lease" case. There's
            # no way to verify whether the lease it WAS about still
            # exists, so the honest, non-guessing choice is to exclude
            # it rather than assume it's still relevant.
            continue
        else:
            relevant.append(disc)  # a genuinely new, unrecognized no-lease-id type -- don't silently drop it

    return relevant


def _unresolved_discrepancies_component(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    lease_count = len(leases)
    open_count = len(_current_open_discrepancies(leases))
    if lease_count == 0:
        return {"score": None, "weight": WEIGHTS["unresolved_discrepancies"], "open_count": open_count, "discrepancies_per_lease": None}

    discrepancies_per_lease = open_count / lease_count
    score = round(100 / (1 + discrepancies_per_lease), 1)
    return {
        "score": score,
        "weight": WEIGHTS["unresolved_discrepancies"],
        "open_count": open_count,
        "discrepancies_per_lease": round(discrepancies_per_lease, 2),
    }


def _last_refreshed_at(lease: Dict[str, Any]) -> str:
    """The later of this lease's own upload time and its most recent amendment's -- an amendment IS a real data refresh, same convention portfolio_history.py uses."""
    latest = lease["uploaded_at"]
    if lease.get("amendment_count", 0) > 0:
        for amendment in database.get_amendments(lease["id"]):
            if amendment["uploaded_at"] > latest:
                latest = amendment["uploaded_at"]
    return latest


def _data_freshness_component(
    leases: List[Dict[str, Any]], reference_date: date, staleness_threshold_months: float
) -> Dict[str, Any]:
    if not leases:
        return {
            "score": None, "weight": WEIGHTS["data_freshness"],
            "fresh_count": 0, "stale_count": 0, "total_count": 0,
            "threshold_months": staleness_threshold_months,
        }

    threshold = timedelta(days=staleness_threshold_months * _APPROX_DAYS_PER_MONTH)
    now = datetime.combine(reference_date, datetime.min.time(), tzinfo=timezone.utc)

    fresh_count = 0
    for lease in leases:
        last_refreshed = datetime.fromisoformat(_last_refreshed_at(lease))
        if now - last_refreshed <= threshold:
            fresh_count += 1

    score = round(fresh_count / len(leases) * 100, 1)
    return {
        "score": score,
        "weight": WEIGHTS["data_freshness"],
        "fresh_count": fresh_count,
        "stale_count": len(leases) - fresh_count,
        "total_count": len(leases),
        "threshold_months": staleness_threshold_months,
    }


def compute_portfolio_health_score(
    reference_date: Optional[date] = None,
    staleness_threshold_months: float = DEFAULT_STALENESS_THRESHOLD_MONTHS,
) -> Dict[str, Any]:
    """
    See the module docstring for the full formula. Returns
    {"score", "rating", "lease_count", "computed_at", "components": {
    "confidence_distribution", "source_verification",
    "unresolved_discrepancies", "data_freshness"}}, each component
    carrying its own "score"/"weight" plus the raw numbers behind it.

    score/rating are None/"No Data" for an empty portfolio -- an
    unscored portfolio is not the same thing as a known-bad one.
    """
    reference_date = reference_date or date.today()
    leases = database.get_all_effective_leases()

    components = {
        "confidence_distribution": _confidence_distribution_component(leases),
        "source_verification": _source_verification_component(leases),
        "unresolved_discrepancies": _unresolved_discrepancies_component(leases),
        "data_freshness": _data_freshness_component(leases, reference_date, staleness_threshold_months),
    }

    if not leases:
        return {
            "score": None,
            "rating": "No Data",
            "lease_count": 0,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "components": components,
        }

    overall = sum(components[name]["score"] * weight for name, weight in WEIGHTS.items())
    overall = round(overall, 1)

    return {
        "score": overall,
        "rating": _rating_for(overall),
        "lease_count": len(leases),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
