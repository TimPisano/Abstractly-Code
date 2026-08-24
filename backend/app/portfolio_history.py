"""
Trend queries over a property's full upload history.

The underlying data was already permanent: `leases` is append-only --
nothing about a normal upload UPDATEs an existing row (a lease/rent-
roll upload always INSERTs a new one; the only UPDATE path is a
display_name rename via PATCH). So every rent roll re-import, and every
lease PDF re-upload, has always been silently accumulating a real
historical record -- this module is what actually makes that record
queryable as a timeline instead of just sitting there. See DECISIONS.md
for the one honest limitation this doesn't cover: DELETE is still a
real hard delete (`database.delete_lease`), so a deleted lease's
history goes with it -- deliberately not changed here, since altering
delete semantics would touch every existing "current portfolio state"
computation in portfolio.py, a much bigger and riskier change than
this feature asked for.

Building-level grouping (which records belong to "this property" at
all) uses `_normalize_building_address` (suite-insensitive, same as
compute_loss_to_lease/compute_t12_reconciliation). Unit-level grouping
(which records are the SAME unit's history over time, for rent growth
and tenant turnover) uses `_normalize_address` (suite-INCLUSIVE, same
as compute_rent_roll_reconciliation/compute_cross_lease_mismatches) --
using the building-level match for unit-level trends would blend
different units' independent rent/tenant histories into one nonsense
timeline.
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .normalize import parse_currency, parse_date
from .portfolio import _is_rent_roll_import, _normalize_address, _normalize_building_address, _normalize_tenant_name, field_value


def _history_entry(lease: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "lease_id": lease.get("id"),
        "uploaded_at": lease.get("uploaded_at"),
        "source": "rent_roll_import" if _is_rent_roll_import(lease) else "lease_document",
        "filename": lease.get("filename"),
        "display_name": lease.get("display_name"),
        "unit_key": _normalize_address(field_value(lease, "property_address")),
        "property_address": field_value(lease, "property_address"),
        "tenant": field_value(lease, "tenant"),
        "rent_amount": field_value(lease, "rent_amount"),
        "square_footage": field_value(lease, "square_footage"),
        "lease_start_date": field_value(lease, "lease_start_date"),
        "lease_end_date": field_value(lease, "lease_end_date"),
    }


def get_property_history(leases: List[Dict[str, Any]], property_address: str) -> List[Dict[str, Any]]:
    """
    Every historical record (lease PDF or rent-roll-imported row) ever
    uploaded at this building, building-level matched, oldest first.
    Includes amendments' base leases as a single entry each (amendment
    overrides aren't separately timelined here -- get_all_effective_
    leases already merges an amendment into its base lease's current
    values, which is what every entry below reflects; the amendment
    upload itself doesn't get its own historical data point distinct
    from the lease it amends).
    """
    normalized_target = _normalize_building_address(property_address)
    if not normalized_target:
        return []
    matched = [
        lease for lease in leases
        if _normalize_building_address(field_value(lease, "property_address")) == normalized_target
    ]
    entries = [_history_entry(lease) for lease in matched]
    return sorted(entries, key=lambda e: (e["uploaded_at"] or "", e["lease_id"] or 0))


def _group_by_unit(history: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in history:
        if entry["unit_key"]:
            groups[entry["unit_key"]].append(entry)
    return groups


def compute_rent_growth(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Per-unit rent-over-time: every consecutive pair of historical
    records for the SAME unit (exact address, suite included) where
    both sides have a parseable rent, with the % change between them
    and whether the tenant also changed at that same transition -- a
    rent reset alongside a new tenant tells a very different story
    (market repricing at turnover) than the same tenant's rent
    increasing (a scheduled escalation or renewal), so this is surfaced
    explicitly rather than collapsed into one undifferentiated number.

    Returns {"units": [{unit_address, data_points: [...],
    transitions: [{from_uploaded_at, to_uploaded_at, from_rent,
    to_rent, pct_change, tenant_changed}], total_pct_change}],
    "units_with_growth_data": N}. A unit with fewer than 2 parseable
    rent data points contributes no transitions (nothing to compare)
    but still appears if it has at least 1 data point, so a caller can
    see it's being tracked, just without a trend yet.
    """
    units = []
    for unit_key, entries in _group_by_unit(history).items():
        entries = sorted(entries, key=lambda e: e["uploaded_at"] or "")
        parsed = [(e, parse_currency(e["rent_amount"])) for e in entries]

        transitions = []
        for (prev_entry, prev_rent), (curr_entry, curr_rent) in zip(parsed, parsed[1:]):
            if prev_rent is None or curr_rent is None or prev_rent == 0:
                continue
            pct_change = round((curr_rent - prev_rent) / prev_rent * 100, 2)
            transitions.append({
                "from_uploaded_at": prev_entry["uploaded_at"],
                "to_uploaded_at": curr_entry["uploaded_at"],
                "from_lease_id": prev_entry["lease_id"],
                "to_lease_id": curr_entry["lease_id"],
                "from_rent": prev_entry["rent_amount"],
                "to_rent": curr_entry["rent_amount"],
                "pct_change": pct_change,
                "tenant_changed": _normalize_tenant_name(prev_entry["tenant"]) != _normalize_tenant_name(curr_entry["tenant"]),
            })

        priced = [r for _, r in parsed if r is not None]
        total_pct_change = (
            round((priced[-1] - priced[0]) / priced[0] * 100, 2)
            if len(priced) >= 2 and priced[0] != 0 else None
        )

        units.append({
            "unit_address": entries[0]["property_address"],
            "data_points": len(entries),
            "transitions": transitions,
            "total_pct_change": total_pct_change,
        })

    return {
        "units": sorted(units, key=lambda u: u["unit_address"] or ""),
        "units_with_growth_data": sum(1 for u in units if u["transitions"]),
    }


def compute_tenant_turnover(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Per-unit tenant changes over time: every consecutive pair of
    historical records for the SAME unit where the (normalized) tenant
    name differs is one turnover event. A missing tenant on either side
    of a pair is not treated as a turnover (nothing to compare, not
    evidence of a change) -- consistent with this project's "don't
    guess" standard.

    Returns {"events": [{unit_address, from_tenant, to_tenant,
    detected_at, old_lease_id, new_lease_id}], "turnover_count": N,
    "units_tracked": N}.
    """
    events = []
    units_tracked = 0
    for unit_key, entries in _group_by_unit(history).items():
        entries = sorted(entries, key=lambda e: e["uploaded_at"] or "")
        if len(entries) >= 2:
            units_tracked += 1
        for prev_entry, curr_entry in zip(entries, entries[1:]):
            prev_tenant = _normalize_tenant_name(prev_entry["tenant"])
            curr_tenant = _normalize_tenant_name(curr_entry["tenant"])
            if prev_tenant and curr_tenant and prev_tenant != curr_tenant:
                events.append({
                    "unit_address": curr_entry["property_address"],
                    "from_tenant": prev_entry["tenant"],
                    "to_tenant": curr_entry["tenant"],
                    "detected_at": curr_entry["uploaded_at"],
                    "old_lease_id": prev_entry["lease_id"],
                    "new_lease_id": curr_entry["lease_id"],
                })

    return {
        "events": sorted(events, key=lambda e: e["detected_at"] or ""),
        "turnover_count": len(events),
        "units_tracked": units_tracked,
    }


def compute_rollover_pattern(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Historical distribution of lease_end_dates across EVERY record this
    building has ever had (not deduped to "current" per unit) -- a
    building-level view of when rollovers have tended to cluster, e.g.
    disproportionately many expirations in one calendar month across
    years, or a particular year that saw a wave of them. This is
    intentionally NOT the same thing as compute_rollover_schedule
    (portfolio.py), which reports the CURRENT forward-looking schedule
    from today -- this reports the historical footprint, which is only
    visible at all because every upload is retained.

    Returns {"by_month": {"01".."12": count}, "by_year": {year: count},
    "total_expirations_tracked": N}. A record whose lease_end_date
    doesn't parse contributes to neither bucket -- not guessed at.
    """
    by_month: Dict[str, int] = {f"{m:02d}": 0 for m in range(1, 13)}
    by_year: Dict[str, int] = defaultdict(int)
    total = 0

    for entry in history:
        end_date = parse_date(entry["lease_end_date"])
        if end_date is None:
            continue
        by_month[f"{end_date.month:02d}"] += 1
        by_year[str(end_date.year)] += 1
        total += 1

    return {
        "by_month": by_month,
        "by_year": dict(sorted(by_year.items())),
        "total_expirations_tracked": total,
    }


def compute_property_trends(leases: List[Dict[str, Any]], property_address: str) -> Optional[Dict[str, Any]]:
    """
    Everything this module can say about one property in one call:
    the raw history timeline, rent growth, tenant turnover, and
    rollover pattern. Returns None only when property_address itself
    doesn't normalize to anything (blank/unusable input) -- an address
    that normalizes fine but matches zero historical records returns a
    real, honest all-empty result (0 history, not an error), since "no
    data yet" and "invalid input" are different situations.
    """
    normalized_target = _normalize_building_address(property_address)
    if not normalized_target:
        return None

    history = get_property_history(leases, property_address)
    return {
        "property_address": property_address,
        "history": history,
        "record_count": len(history),
        "rent_growth": compute_rent_growth(history),
        "tenant_turnover": compute_tenant_turnover(history),
        "rollover_pattern": compute_rollover_pattern(history),
    }
