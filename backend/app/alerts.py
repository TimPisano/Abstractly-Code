"""
Proactive alert generation: instead of waiting for someone to open the
app and look, this scans the current portfolio state for four
specific, high-value situations and persists a record of each one a
human can act on -- upcoming lease expirations, newly detected
discrepancies, rent significantly below this portfolio's own internal
market proxy, and tenant concentration crossing a risk threshold.

Deliberately reuses this project's EXISTING computations rather than
re-deriving any of the four -- `compute_expiration_alerts` (30/60/90-
day bucketing, already built for the dashboard widget),
`database.list_discrepancies` (the Item 2 discrepancy-resolution
system), `compute_loss_to_lease` (the portfolio's own internal
best-achieved-rent proxy -- see that function's own docstring for why
there's no external market-rate source to compare against instead),
and `compute_tenant_concentration`'s already-defined
TOP_TENANT_HIGH_RISK_PCT/TOP_TENANT_MODERATE_RISK_PCT thresholds
(25%/15% -- not reinvented here). An alert is a NOTIFICATION about a
condition already computed elsewhere, not a second, parallel
computation of the same thing that could silently disagree with it.

Generation is idempotent and safe to re-run on any schedule (a cron
job, a manual trigger, eventually a scheduled email digest -- see
DECISIONS.md, email delivery itself is explicitly out of scope for
this pass): every candidate is upserted by a deterministic natural
key (see database.upsert_alert), so re-running with unchanged data
produces zero new rows, and a condition that's cleared since the last
run gets its alert auto-resolved rather than left stale forever.
"""
from typing import Any, Dict, List

from . import database
from .portfolio import (
    TOP_TENANT_HIGH_RISK_PCT,
    compute_expiration_alerts,
    compute_loss_to_lease,
    compute_tenant_concentration,
)

# ----------------------------------------------------------------------
# 1. Lease expirations
# ----------------------------------------------------------------------

_EXPIRATION_SEVERITY_BY_BUCKET = {"30": "high", "60": "medium", "90": "low"}


def _detect_lease_expiration_alerts(leases: List[Dict[str, Any]], reference_date=None) -> List[Dict[str, Any]]:
    expiring = compute_expiration_alerts(leases, reference_date=reference_date)["expiring"]
    candidates = []
    for entry in expiring:
        bucket = entry["bucket"]
        severity = _EXPIRATION_SEVERITY_BY_BUCKET[bucket]
        tenant = entry.get("tenant") or "An unnamed tenant"
        days = entry["days_remaining"]
        when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
        candidates.append({
            "alert_type": "lease_expiration",
            "natural_key": f"lease_expiration:{entry['lease_id']}",
            "lease_id": entry["lease_id"],
            "severity": severity,
            "title": f"Lease expires {when}",
            "message": (
                f"{tenant}'s lease ({entry['display_name']}) expires {when} "
                f"({entry['lease_end_date']}), within the {bucket}-day window. "
                f"{'Immediate action needed to avoid an unplanned vacancy.' if severity == 'high' else 'Worth planning a renewal or re-leasing decision now, before it becomes urgent.'}"
            ),
            "details": entry,
        })
    return candidates


# ----------------------------------------------------------------------
# 2. Newly detected discrepancies
# ----------------------------------------------------------------------

def _detect_new_discrepancy_alerts() -> List[Dict[str, Any]]:
    """
    One alert per currently-OPEN discrepancy (Item 2's discrepancies
    table) -- a discrepancy that's already been resolved by the time
    this runs doesn't need proactive surfacing, and one that gets
    resolved after its alert was raised will naturally fall out of
    this candidate set on the next run, which is exactly what makes
    its alert auto-resolve (see generate_alerts).
    """
    candidates = []
    for disc in database.list_discrepancies(status="open"):
        severity = disc.get("severity") or "medium"
        candidates.append({
            "alert_type": "new_discrepancy",
            "natural_key": f"new_discrepancy:{disc['id']}",
            "lease_id": disc.get("lease_id"),
            "severity": severity,
            "title": f"New discrepancy: {disc['category'].replace('_', ' ')}",
            # No raw route/path reference here -- every place this message
            # actually renders (admin dashboard's Today's Priorities, the
            # app's own Alerts feed) already shows a real "View ->" link
            # right next to it; a literal internal path in the body text
            # was leftover from before that existed and just read as a
            # broken/unprofessional detail once it did.
            # disc['message'] never ends in its own punctuation (it's a
            # plain factual statement, e.g. "...below the portfolio
            # average ($7,750/mo)") -- a leading period here, not just a
            # space, so this doesn't read as one run-on sentence.
            "message": (
                f"{disc['message']}. This hasn't been reviewed yet -- "
                f"confirm which source is correct before resolving it."
            ),
            "details": {"discrepancy_id": disc["id"], "discrepancy_type": disc["discrepancy_type"], "category": disc["category"], "field": disc.get("field")},
        })
    return candidates


# ----------------------------------------------------------------------
# 3. Rent significantly below this portfolio's internal market proxy
# ----------------------------------------------------------------------

# This module's own judgment call about what counts as "significant"
# loss-to-lease for alerting purposes -- compute_loss_to_lease itself
# deliberately reports raw numbers with no severity label (see its
# docstring: an internal-proxy "market rate" doesn't have a defensible
# enough reference point to attach a risk level to on its own). An
# alert is a stronger claim than a raw metric ("this needs your
# attention," not just "here's a number"), so a threshold has to live
# somewhere -- it lives here, in the layer that's making that claim,
# not retrofitted into the metric itself.
BELOW_MARKET_ALERT_HIGH_PCT = 20.0
BELOW_MARKET_ALERT_MEDIUM_PCT = 10.0


def _detect_below_market_rent_alerts(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = compute_loss_to_lease(leases)
    candidates = []
    for entry in result["leases"]:
        loss_pct = entry["loss_pct"]
        if loss_pct >= BELOW_MARKET_ALERT_HIGH_PCT:
            severity = "high"
        elif loss_pct >= BELOW_MARKET_ALERT_MEDIUM_PCT:
            severity = "medium"
        else:
            continue

        tenant = entry.get("tenant") or "This tenant"
        candidates.append({
            "alert_type": "below_market_rent",
            "natural_key": f"below_market_rent:{entry['lease_id']}",
            "lease_id": entry["lease_id"],
            "severity": severity,
            "title": f"Rent {loss_pct:.0f}% below this property's best-achieved rate",
            "message": (
                f"{tenant} pays ${entry['rent_per_sqft']:.2f}/sq ft, {loss_pct:.0f}% below the "
                f"${entry['property_top_rent_per_sqft']:.2f}/sq ft another unit at the same building "
                f"has already achieved -- a potential ${entry['monthly_upside']:,.0f}/month of upside "
                f"if re-leased at that rate. Worth reviewing at renewal, or investigating why the gap exists."
            ),
            "details": entry,
        })
    return candidates


# ----------------------------------------------------------------------
# 4. Tenant concentration crossing a risk threshold
# ----------------------------------------------------------------------

def _normalize_tenant_key(tenant: str) -> str:
    return (tenant or "").strip().lower()


def _detect_tenant_concentration_alerts(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Alerts only at TOP_TENANT_HIGH_RISK_PCT (25%, not the 15% "moderate"
    threshold too) -- deliberately a single, higher bar. Using the 15%
    moderate threshold here would flag every tenant in a healthy,
    evenly-diversified portfolio (e.g. 5 tenants at 20% each is a LOW-
    risk shape by any reasonable read, not five separate things to
    alert on) -- confirmed this would actually happen and fixed it
    before shipping, see test_tenant_concentration_evenly_split_stays_
    quiet. 25% is the threshold the request itself named as the
    concrete "crossing a risk threshold" example, and it's also this
    project's own existing bar for a portfolio being independently
    flagged "high" concentration regardless of HHI shape (see
    TOP_TENANT_HIGH_RISK_PCT's own comment in portfolio.py) -- an alert
    should be at least that decisive, not a lower, noisier bar invented
    fresh for this feature.
    """
    result = compute_tenant_concentration(leases)
    candidates = []
    for entry in result["tenants"]:
        pct = entry["pct_of_total"]
        if pct < TOP_TENANT_HIGH_RISK_PCT:
            continue

        candidates.append({
            "alert_type": "tenant_concentration",
            "natural_key": f"tenant_concentration:{_normalize_tenant_key(entry['tenant'])}",
            "lease_id": None,  # concentration is a portfolio-wide fact about a tenant, not one specific lease
            "severity": "high",
            "title": f"{entry['tenant']} is {pct:.0f}% of portfolio rent",
            "message": (
                f"{entry['tenant']} now accounts for {pct:.0f}% of total portfolio rent "
                f"(${entry['rent']:,.0f}/mo of ${result['total_rent']:,.0f}/mo), exceeding the "
                f"{TOP_TENANT_HIGH_RISK_PCT:.0f}% single-tenant concentration threshold -- losing this "
                "tenant would have an outsized impact on portfolio cash flow relative to the rest of the book."
            ),
            "details": entry,
        })
    return candidates


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------

# Which alert_types a generation pass is authoritative for -- used to
# scope auto-resolution correctly. Without this, auto-resolving "every
# active alert not in this run's candidate set" would be wrong the
# moment a 5th alert type is ever added by different code, since a
# generation pass that doesn't compute that 5th type at all would
# incorrectly auto-resolve every one of its alerts as "condition
# cleared" just because it was never asked about.
_MANAGED_ALERT_TYPES = ("lease_expiration", "new_discrepancy", "below_market_rent", "tenant_concentration")


def detect_all_candidates(leases: List[Dict[str, Any]], reference_date=None) -> List[Dict[str, Any]]:
    """Every alert condition currently detected across all four categories, unfiltered by severity threshold beyond what each detector itself applies."""
    return (
        _detect_lease_expiration_alerts(leases, reference_date=reference_date)
        + _detect_new_discrepancy_alerts()
        + _detect_below_market_rent_alerts(leases)
        + _detect_tenant_concentration_alerts(leases)
    )


def generate_alerts(reference_date=None) -> Dict[str, Any]:
    """
    Runs all four detectors against the current portfolio state,
    upserts each candidate (see database.upsert_alert for exactly what
    "upsert" does to an already-dismissed or already-auto_resolved
    alert), and auto-resolves any previously-active, currently-managed
    alert whose natural key no longer appears in this run's candidates
    -- i.e. its underlying condition genuinely cleared.

    Safe to call as often as needed (a cron job, a manual trigger, a
    button in an admin panel) -- re-running against unchanged data
    produces zero new rows and zero status changes.

    Returns {"created": N, "refreshed": N, "auto_resolved": N,
    "active_count": N, "by_severity": {...}}.
    """
    leases = database.get_all_effective_leases()
    candidates = detect_all_candidates(leases, reference_date=reference_date)

    # Bulk path: one batched existence check, one batched upsert, one
    # batched auto-resolve UPDATE, instead of 2-3 connect()+commit()
    # round trips per candidate. At real portfolio scale (hundreds of
    # leases, each capable of raising several alert candidates) that
    # per-call overhead was the dominant cost of this endpoint -- same
    # root cause as GET /portfolio/risks, see
    # database.upsert_discrepancies_bulk's docstring for the full
    # profiling writeup of the identical pattern.
    seen_keys = {c["natural_key"] for c in candidates}
    existing_keys = database.get_alerts_existing_natural_keys(list(seen_keys))
    created = sum(1 for c in candidates if c["natural_key"] not in existing_keys)
    refreshed = len(candidates) - created

    database.upsert_alerts_bulk([
        {
            "alert_type": c["alert_type"],
            "natural_key": c["natural_key"],
            "severity": c["severity"],
            "title": c["title"],
            "message": c["message"],
            "details": c["details"],
            "lease_id": c.get("lease_id"),
        }
        for c in candidates
    ])

    to_auto_resolve = [
        alert["id"] for alert in database.list_alerts(status="active")
        if alert["alert_type"] in _MANAGED_ALERT_TYPES and alert["natural_key"] not in seen_keys
    ]
    auto_resolved = database.auto_resolve_alerts_bulk(to_auto_resolve)

    active_alerts = database.list_alerts(status="active")
    by_severity: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for alert in active_alerts:
        by_severity[alert["severity"]] = by_severity.get(alert["severity"], 0) + 1

    return {
        "created": created,
        "refreshed": refreshed,
        "auto_resolved": auto_resolved,
        "active_count": len(active_alerts),
        "by_severity": by_severity,
    }


def get_alert_digest() -> Dict[str, Any]:
    """A summary suitable for a notification-feed header or a future email digest: counts of currently-active alerts by severity and by type. Does NOT run generation -- callers should generate_alerts() first if they want this to reflect the latest data."""
    active_alerts = database.list_alerts(status="active")
    by_severity: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    by_type: Dict[str, int] = {t: 0 for t in _MANAGED_ALERT_TYPES}
    for alert in active_alerts:
        by_severity[alert["severity"]] = by_severity.get(alert["severity"], 0) + 1
        by_type[alert["alert_type"]] = by_type.get(alert["alert_type"], 0) + 1
    return {
        "active_count": len(active_alerts),
        "by_severity": by_severity,
        "by_type": by_type,
    }
