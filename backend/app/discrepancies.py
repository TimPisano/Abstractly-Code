"""
Gives a stable, persisted identity to discrepancies that are otherwise
computed fresh on every request -- single-lease risk flags, cross-lease
mismatches, rent-roll-vs-lease-PDF reconciliation disagreements, and
rent-roll-vs-T12 reconciliation disagreements -- and merges resolution
status back into them, so a human resolving one, once, means it stops
needing a manual re-read on every future request.

Natural keys are deterministic strings derived from each flag's own
IDENTIFYING fields (lease id(s), category, field) -- never from its
rendered message or the dollar amounts in it, which change with the
underlying data even when the underlying disagreement itself is the
same one a human already looked at. That's what makes a discrepancy
"the same one" across repeated computations, which is the whole point:
without it, resolving something today would have no way to still be
recognized as resolved tomorrow once the numbers shift slightly.

See database.py's discrepancies/discrepancy_resolutions tables for the
persistence layer this sits on top of.
"""
from typing import Any, Dict, List

from app import database
from app.portfolio import _normalize_building_address


def _annotate(flag_like: Dict[str, Any], discrepancy_id: int) -> None:
    """Mutates flag_like in place, adding discrepancy_id/resolution_status/resolution."""
    discrepancy = database.get_discrepancy(discrepancy_id)
    flag_like["discrepancy_id"] = discrepancy_id
    flag_like["resolution_status"] = discrepancy["status"]
    flag_like["resolution"] = None
    if discrepancy["status"] == "resolved":
        history = database.get_discrepancy_resolutions(discrepancy_id)
        for entry in reversed(history):
            if entry["action"] == "resolved":
                flag_like["resolution"] = entry
                break


def sync_lease_risk_flags(lease_id: int, flags: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Upserts every flag in this lease's risk-flag list (single-lease
    categories AND cross_lease_mismatch flags -- both share this one
    list, see risk_analysis.analyze_lease_risks) as a discrepancy, and
    annotates each flag dict in place. Returns the same list.

    Cross-lease flags are keyed by the sorted (lease_id, other_lease_id)
    pair, not by whichever lease's list happens to be rendered first --
    so viewing the SAME mismatch from either lease's own risk list
    resolves to the SAME discrepancy row, not two independent ones.

    Non-cross-lease flags are keyed by (lease_id, category, field) plus
    an occurrence index, since a lease can legitimately raise more than
    one flag with the same category+field (e.g. two different date-
    inconsistency checks can both land on lease_end_date) -- the index
    disambiguates them deterministically as long as analyze_lease_risks
    keeps producing them in the same order for the same input, which it
    does (a fixed sequence of checks, then a stable sort by severity).
    """
    occurrence_seen: Dict[str, int] = {}
    for flag in flags:
        category = flag.get("category")
        field = flag.get("field")

        if category == "cross_lease_mismatch":
            other_id = flag.get("other_lease_id")
            if other_id is not None:
                lo, hi = sorted((lease_id, other_id))
                natural_key = f"cross_lease:{lo}:{hi}:{field}"
                row_lease_id, row_related_id = lo, hi
            else:
                natural_key = f"cross_lease:{lease_id}:none:{field}"
                row_lease_id, row_related_id = lease_id, None
            discrepancy_id = database.upsert_discrepancy(
                discrepancy_type="cross_lease_mismatch",
                natural_key=natural_key,
                category=category,
                field=field,
                severity=flag.get("severity"),
                message=flag.get("message", ""),
                details=flag,
                lease_id=row_lease_id,
                related_lease_id=row_related_id,
            )
        else:
            slot = f"{lease_id}:{category}:{field}"
            occurrence_seen[slot] = occurrence_seen.get(slot, -1) + 1
            natural_key = f"lease_risk:{slot}:{occurrence_seen[slot]}"
            discrepancy_id = database.upsert_discrepancy(
                discrepancy_type="lease_risk_flag",
                natural_key=natural_key,
                category=category,
                field=field,
                severity=flag.get("severity"),
                message=flag.get("message", ""),
                details=flag,
                lease_id=lease_id,
            )

        _annotate(flag, discrepancy_id)

    return flags


def sync_all_lease_risk_flags_bulk(per_lease_flags: List[tuple]) -> None:
    """
    Bulk sibling of sync_lease_risk_flags for syncing EVERY lease's risk
    flags in one pass (GET /portfolio/risks) instead of one lease at a
    time. `per_lease_flags` is [(lease_id, flags), ...]; every flag
    dict is annotated in place with discrepancy_id/resolution_status/
    resolution, exactly like sync_lease_risk_flags does -- this must
    stay behaviorally identical to calling sync_lease_risk_flags once
    per lease, just batched. See database.upsert_discrepancies_bulk's
    docstring for why this exists: thousands of individual upsert/read
    calls (one connect()+commit() each) dominate this endpoint's time
    at real portfolio scale, purely from per-call overhead.

    The natural-key derivation below is a deliberate copy of
    sync_lease_risk_flags' logic, not a shared helper -- occurrence_seen
    here must be keyed per (lease_id, category, field) same as before,
    but is accumulated across ALL leases in one dict rather than reset
    per call, so keeping the derivation inline and explicit here (
    matching the single-lease version line for line) is easier to
    verify stays in sync than threading a shared helper through both.
    """
    occurrence_seen: Dict[str, int] = {}
    payloads = []
    flag_to_natural_key = []  # parallel list: (flag_dict, natural_key)

    for lease_id, flags in per_lease_flags:
        for flag in flags:
            category = flag.get("category")
            field = flag.get("field")

            if category == "cross_lease_mismatch":
                other_id = flag.get("other_lease_id")
                if other_id is not None:
                    lo, hi = sorted((lease_id, other_id))
                    natural_key = f"cross_lease:{lo}:{hi}:{field}"
                    row_lease_id, row_related_id = lo, hi
                else:
                    natural_key = f"cross_lease:{lease_id}:none:{field}"
                    row_lease_id, row_related_id = lease_id, None
                payloads.append({
                    "discrepancy_type": "cross_lease_mismatch",
                    "natural_key": natural_key,
                    "category": category,
                    "field": field,
                    "severity": flag.get("severity"),
                    "message": flag.get("message", ""),
                    "details": flag,
                    "lease_id": row_lease_id,
                    "related_lease_id": row_related_id,
                })
            else:
                slot = f"{lease_id}:{category}:{field}"
                occurrence_seen[slot] = occurrence_seen.get(slot, -1) + 1
                natural_key = f"lease_risk:{slot}:{occurrence_seen[slot]}"
                payloads.append({
                    "discrepancy_type": "lease_risk_flag",
                    "natural_key": natural_key,
                    "category": category,
                    "field": field,
                    "severity": flag.get("severity"),
                    "message": flag.get("message", ""),
                    "details": flag,
                    "lease_id": lease_id,
                })

            flag_to_natural_key.append((flag, natural_key))

    if not payloads:
        return

    ids_by_natural_key = database.upsert_discrepancies_bulk(payloads)
    all_ids = list(ids_by_natural_key.values())
    discrepancies_by_id = database.get_discrepancies_by_ids(all_ids)
    resolved_ids = [d["id"] for d in discrepancies_by_id.values() if d["status"] == "resolved"]
    resolutions_by_id = database.get_discrepancy_resolutions_bulk(resolved_ids)

    for flag, natural_key in flag_to_natural_key:
        discrepancy_id = ids_by_natural_key[natural_key]
        discrepancy = discrepancies_by_id[discrepancy_id]
        flag["discrepancy_id"] = discrepancy_id
        flag["resolution_status"] = discrepancy["status"]
        flag["resolution"] = None
        if discrepancy["status"] == "resolved":
            for entry in reversed(resolutions_by_id.get(discrepancy_id, [])):
                if entry["action"] == "resolved":
                    flag["resolution"] = entry
                    break


def sync_rent_roll_reconciliation(mismatches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Upserts every rent-roll-vs-lease-PDF mismatch and annotates each dict in place. Returns the same list."""
    for mismatch in mismatches:
        rr_id = mismatch.get("rent_roll_lease_id")
        doc_id = mismatch.get("lease_document_id")
        field = mismatch.get("field")
        natural_key = f"rent_roll_recon:{rr_id}:{doc_id}:{field}"
        message = (
            f"Rent roll and lease document disagree on {field} at {mismatch.get('address')}: "
            f"rent roll says {mismatch.get('rent_roll_value')!r}, lease document says {mismatch.get('lease_document_value')!r}"
        )
        discrepancy_id = database.upsert_discrepancy(
            discrepancy_type="rent_roll_reconciliation",
            natural_key=natural_key,
            category="rent_roll_reconciliation",
            field=field,
            severity="medium",
            message=message,
            details=mismatch,
            lease_id=rr_id,
            related_lease_id=doc_id,
        )
        _annotate(mismatch, discrepancy_id)
    return mismatches


def sync_t12_reconciliation(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upserts (and annotates in place) the one T12-vs-rent-roll
    discrepancy for this property, IF it's currently flagged or a
    discrepancy already exists for it from an earlier check -- an
    unflagged result with no prior history has nothing to attach a
    resolution to, so nothing is persisted for it (a T12 upload itself
    is never persisted either, per compute_t12_reconciliation's own
    docstring -- this natural key is address-only, so it's honestly a
    coarser identity than the per-field discrepancies above: a
    DIFFERENT T12 file for the same building later would collide onto
    the same discrepancy row, since there's no persisted T12 upload to
    key against instead. Documented limitation, not silently assumed
    away -- see DECISIONS.md.
    """
    normalized = _normalize_building_address(result.get("property_address"))
    if not normalized:
        return result
    natural_key = f"t12_recon:{normalized}"

    existing = database.get_discrepancy_by_natural_key(natural_key)
    if not result.get("flagged") and not existing:
        return result

    message = (
        f"Rent roll and T12 disagree on annual rental income at {result.get('property_address')}: "
        f"rent roll implies ${result.get('rent_roll_annual_rent')}, T12 states ${result.get('t12_annual_rental_income')}"
    )
    discrepancy_id = database.upsert_discrepancy(
        discrepancy_type="t12_reconciliation",
        natural_key=natural_key,
        category="t12_reconciliation",
        field="rent_amount",
        severity="medium" if result.get("flagged") else None,
        message=message,
        details=result,
    )
    _annotate(result, discrepancy_id)
    return result
