"""
Deal Mismatch Report: cross-checks an uploaded rent roll against the
lease PDFs on file and produces one dollar-quantified discrepancy list,
plus a portfolio-level income-impact summary -- Abstractly's primary
sellable export, the document a buyer hands to a lender or LP (see
deal_mismatch_export.py for the PDF/Excel renderers this feeds).

Reuses this app's existing unit-matching convention (_normalize_address,
same-suite-included matching compute_rent_roll_reconciliation and
compute_cross_lease_mismatches already use in portfolio.py) and
discrepancies.py's _severity_for_monthly_impact severity scale, so a
Deal Mismatch Report severity means the same thing as every other
discrepancy severity already surfaced elsewhere in the app.

Each detector below is a pure function over get_all_effective_leases()'s
output, returning a list of row dicts shaped:
    {
        "discrepancy_type": one of the 7 categories below,
        "unit": display property address (rent roll's own value
            preferred, same fallback compute_rent_roll_reconciliation
            uses),
        "field": which extracted field disagreed, or a category name
            for presence-only checks (unit_no_lease/lease_no_unit/
            expired_but_occupied),
        "rent_roll_value": display string or None,
        "lease_value": display string or None,
        "source": {"page": int, "quote": str} or None -- pulled from
            whichever lease-PDF field established the finding; a
            unit_no_lease row has no lease PDF to cite, so this is
            always None there,
        "severity": "high" | "medium" | "low",
        "monthly_dollar_impact": float or None -- unsigned magnitude,
        "annual_dollar_impact": float or None -- unsigned magnitude,
        "income_direction": "overstate" | "understate" | None -- whether
            the rent roll's implied income is too high, too low, or (for
            findings with no defensible direction, e.g. a tenant-name or
            date disagreement) not assignable at all. Kept separate from
            the magnitude fields so a row can show "how big" without this
            module asserting a direction it can't actually support --
            same "None means not enough data, never a guessed zero"
            discipline portfolio.py's own docstrings insist on
            throughout.
        "rent_roll_lease_id": int or None,
        "lease_document_id": int or None,
    }

rent_mismatch reuses compute_rent_roll_reconciliation's own tolerance
constants so "is this even a mismatch worth reporting" stays defined in
exactly one place; every OTHER detector here is new (see PROGRESS.md/
the approved plan for why: the existing reconciliation functions only
ever look at matched pairs and never estimate a dollar amount).

concession_missing intentionally returns an empty list for now -- it
needs the lease's own concessions field, which doesn't exist until
Phase 2 (multifamily lease fields) lands. Left in place, not omitted
entirely, so build_deal_mismatch_report_data's discrepancy_type list
and the exporters don't need to change shape again when Phase 2 wires
it up for real.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from .database import get_all_effective_leases
from .discrepancies import _severity_for_monthly_impact
from .normalize import parse_currency, parse_date
from .portfolio import (
    _is_rent_roll_import,
    _normalize_address,
    _normalize_for_matching,
    _RENT_DISAGREEMENT_TOLERANCE_ABS,
    _RENT_DISAGREEMENT_TOLERANCE_PCT,
    field_value,
)

DISCREPANCY_TYPES = [
    "rent_mismatch",
    "expired_but_occupied",
    "unit_no_lease",
    "lease_no_unit",
    "concession_missing",
    "dates_mismatch",
    "tenant_mismatch",
]


def _field_source(lease: Dict[str, Any], field_name: str) -> Optional[Dict[str, Any]]:
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field_name) or {}
    return entry.get("source")


def _display_unit(rr_lease: Optional[Dict[str, Any]], doc_lease: Optional[Dict[str, Any]]) -> Optional[str]:
    """Same fallback order compute_rent_roll_reconciliation's _add_mismatch uses: rent roll's own address string first, then the lease PDF's."""
    if rr_lease is not None:
        value = field_value(rr_lease, "property_address")
        if value:
            return value
    if doc_lease is not None:
        return field_value(doc_lease, "property_address")
    return None


def _address_groups(leases: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Same grouping compute_rent_roll_reconciliation builds internally
    (portfolio.py), rebuilt here rather than imported since that
    function doesn't expose its intermediate grouping -- every detector
    below needs the full groups (including addresses with rent-roll rows
    but no lease PDF, and vice versa), not just the matched-pair subset
    compute_rent_roll_reconciliation itself iterates.
    """
    rent_roll_leases = [l for l in leases if _is_rent_roll_import(l)]
    lease_documents = [l for l in leases if not _is_rent_roll_import(l)]

    groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for lease in rent_roll_leases:
        address = _normalize_address(field_value(lease, "property_address"))
        if address is None:
            continue
        groups.setdefault(address, {"rent_roll": [], "lease_document": []})["rent_roll"].append(lease)
    for lease in lease_documents:
        address = _normalize_address(field_value(lease, "property_address"))
        if address is None:
            continue
        groups.setdefault(address, {"rent_roll": [], "lease_document": []})["lease_document"].append(lease)
    return groups


def detect_rent_mismatch(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for rr_lease in group["rent_roll"]:
            for doc_lease in group["lease_document"]:
                rr_rent = parse_currency(field_value(rr_lease, "rent_amount"))
                doc_rent = parse_currency(field_value(doc_lease, "rent_amount"))
                if rr_rent is None or doc_rent is None or rr_rent == doc_rent:
                    continue
                diff_abs = abs(rr_rent - doc_rent)
                larger = max(rr_rent, doc_rent)
                diff_pct = (diff_abs / larger * 100) if larger > 0 else 0.0
                if not (diff_abs > _RENT_DISAGREEMENT_TOLERANCE_ABS and diff_pct > _RENT_DISAGREEMENT_TOLERANCE_PCT):
                    continue

                monthly_impact = diff_abs
                rows.append({
                    "discrepancy_type": "rent_mismatch",
                    "unit": _display_unit(rr_lease, doc_lease),
                    "field": "rent_amount",
                    "rent_roll_value": field_value(rr_lease, "rent_amount"),
                    "lease_value": field_value(doc_lease, "rent_amount"),
                    "source": _field_source(doc_lease, "rent_amount"),
                    "severity": _severity_for_monthly_impact(monthly_impact),
                    "monthly_dollar_impact": round(monthly_impact, 2),
                    "annual_dollar_impact": round(monthly_impact * 12, 2),
                    "income_direction": "overstate" if rr_rent > doc_rent else "understate",
                    "rent_roll_lease_id": rr_lease.get("id"),
                    "lease_document_id": doc_lease.get("id"),
                })
    return rows


def detect_expired_but_occupied(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    A lease PDF whose lease_end_date is in the past, for a unit the rent
    roll still lists a real tenant against -- the rent roll is counting
    income for a unit the lease itself says should no longer be earning
    rent. "Still occupied" is read off the rent roll row's own tenant
    field being present: rent_roll_import.py already refuses to import a
    row with a vacancy/blank tenant name in the first place (see its
    _is_real_tenant_name), so a rent-roll-derived lease record reaching
    this function is, by construction, one that claimed a real tenant.
    """
    today = today or date.today()
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for doc_lease in group["lease_document"]:
            doc_end = parse_date(field_value(doc_lease, "lease_end_date"))
            if doc_end is None or doc_end >= today:
                continue
            for rr_lease in group["rent_roll"]:
                if not field_value(rr_lease, "tenant"):
                    continue
                rr_rent = parse_currency(field_value(rr_lease, "rent_amount"))
                monthly_impact = rr_rent
                rows.append({
                    "discrepancy_type": "expired_but_occupied",
                    "unit": _display_unit(rr_lease, doc_lease),
                    "field": "lease_end_date",
                    "rent_roll_value": f"Occupied ({field_value(rr_lease, 'tenant')})",
                    "lease_value": f"Expired {field_value(doc_lease, 'lease_end_date')}",
                    "source": _field_source(doc_lease, "lease_end_date"),
                    "severity": _severity_for_monthly_impact(monthly_impact),
                    "monthly_dollar_impact": round(monthly_impact, 2) if monthly_impact is not None else None,
                    "annual_dollar_impact": round(monthly_impact * 12, 2) if monthly_impact is not None else None,
                    "income_direction": "overstate",
                    "rent_roll_lease_id": rr_lease.get("id"),
                    "lease_document_id": doc_lease.get("id"),
                })
    return rows


def detect_unit_no_lease(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    A rent-roll row with no lease PDF on file at all for its unit --
    compute_rent_roll_reconciliation (portfolio.py) explicitly skips
    this case ("nothing to reconcile against"); here it's the finding
    itself, since the rent roll's own claimed rent for that unit is
    entirely unverified against a real signed lease. No lease PDF exists
    to cite, so `source` is always None and `income_direction` is
    deliberately None too -- there's no signed document to say the rent
    roll's number is too HIGH or too LOW, only that it's unconfirmed.
    """
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases).values():
        if group["lease_document"]:
            continue
        for rr_lease in group["rent_roll"]:
            rr_rent = parse_currency(field_value(rr_lease, "rent_amount"))
            rows.append({
                "discrepancy_type": "unit_no_lease",
                "unit": _display_unit(rr_lease, None),
                "field": "presence",
                "rent_roll_value": field_value(rr_lease, "tenant") or "(unit on rent roll)",
                "lease_value": None,
                "source": None,
                "severity": _severity_for_monthly_impact(rr_rent),
                "monthly_dollar_impact": round(rr_rent, 2) if rr_rent is not None else None,
                "annual_dollar_impact": round(rr_rent * 12, 2) if rr_rent is not None else None,
                "income_direction": None,
                "rent_roll_lease_id": rr_lease.get("id"),
                "lease_document_id": None,
            })
    return rows


def detect_lease_no_unit(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    A lease PDF whose unit never appears on the rent roll at all -- the
    mirror image of unit_no_lease. Unlike that case, this one DOES have
    a defensible direction: a signed lease documents real rent the rent
    roll simply isn't counting, so the rent roll understates income by
    that lease's rent.
    """
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases).values():
        if group["rent_roll"]:
            continue
        for doc_lease in group["lease_document"]:
            doc_rent = parse_currency(field_value(doc_lease, "rent_amount"))
            rows.append({
                "discrepancy_type": "lease_no_unit",
                "unit": _display_unit(None, doc_lease),
                "field": "presence",
                "rent_roll_value": None,
                "lease_value": field_value(doc_lease, "tenant") or "(lease on file)",
                "source": _field_source(doc_lease, "property_address"),
                "severity": _severity_for_monthly_impact(doc_rent),
                "monthly_dollar_impact": round(doc_rent, 2) if doc_rent is not None else None,
                "annual_dollar_impact": round(doc_rent * 12, 2) if doc_rent is not None else None,
                "income_direction": "understate" if doc_rent is not None else None,
                "rent_roll_lease_id": None,
                "lease_document_id": doc_lease.get("id"),
            })
    return rows


def detect_concession_missing(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Stub until Phase 2 (multifamily lease fields) adds a `concessions`
    extracted field to compare against -- always returns an empty list
    for now. Kept as its own function (rather than omitted) so
    DISCREPANCY_TYPES / build_deal_mismatch_report_data's shape doesn't
    change again once Phase 2 wires this up for real.
    """
    return []


def detect_dates_mismatch(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    lease_start_date and lease_end_date, zero tolerance on both -- same
    "no meaningful close enough for a date" stance
    compute_rent_roll_reconciliation already takes for lease_end_date;
    extended here to lease_start_date too, which that function doesn't
    check. Severity is "medium" for either field, matching
    discrepancies.py's own existing precedent for a date disagreement
    (_rent_roll_mismatch_severity_and_impact's lease_end_date case) --
    no dollar amount is assignable to a date disagreement on its own, so
    monthly/annual impact and income_direction all stay None here
    rather than a fabricated number.
    """
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for rr_lease in group["rent_roll"]:
            for doc_lease in group["lease_document"]:
                for field_name in ("lease_start_date", "lease_end_date"):
                    rr_date = parse_date(field_value(rr_lease, field_name))
                    doc_date = parse_date(field_value(doc_lease, field_name))
                    if rr_date is None or doc_date is None or rr_date == doc_date:
                        continue
                    rows.append({
                        "discrepancy_type": "dates_mismatch",
                        "unit": _display_unit(rr_lease, doc_lease),
                        "field": field_name,
                        "rent_roll_value": field_value(rr_lease, field_name),
                        "lease_value": field_value(doc_lease, field_name),
                        "source": _field_source(doc_lease, field_name),
                        "severity": "medium",
                        "monthly_dollar_impact": None,
                        "annual_dollar_impact": None,
                        "income_direction": None,
                        "rent_roll_lease_id": rr_lease.get("id"),
                        "lease_document_id": doc_lease.get("id"),
                    })
    return rows


def detect_tenant_mismatch(leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Any tenant-name disagreement at all is flagged -- same "no close
    enough for whether it's the same tenant" stance
    compute_rent_roll_reconciliation and discrepancies.py's own
    _rent_roll_mismatch_severity_and_impact already take (always "high").
    No dollar amount is assignable to a naming disagreement on its own.
    """
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for rr_lease in group["rent_roll"]:
            for doc_lease in group["lease_document"]:
                rr_tenant = field_value(rr_lease, "tenant")
                doc_tenant = field_value(doc_lease, "tenant")
                rr_norm = _normalize_for_matching(rr_tenant)
                doc_norm = _normalize_for_matching(doc_tenant)
                if not rr_norm or not doc_norm or rr_norm == doc_norm:
                    continue
                rows.append({
                    "discrepancy_type": "tenant_mismatch",
                    "unit": _display_unit(rr_lease, doc_lease),
                    "field": "tenant",
                    "rent_roll_value": rr_tenant,
                    "lease_value": doc_tenant,
                    "source": _field_source(doc_lease, "tenant"),
                    "severity": "high",
                    "monthly_dollar_impact": None,
                    "annual_dollar_impact": None,
                    "income_direction": None,
                    "rent_roll_lease_id": rr_lease.get("id"),
                    "lease_document_id": doc_lease.get("id"),
                })
    return rows


_DETECTORS = [
    detect_rent_mismatch,
    detect_expired_but_occupied,
    detect_unit_no_lease,
    detect_lease_no_unit,
    detect_concession_missing,
    detect_dates_mismatch,
    detect_tenant_mismatch,
]


def _total_units_checked(leases: List[Dict[str, Any]]) -> int:
    """Distinct normalized unit addresses across every rent-roll row and lease PDF on file -- the universe this report actually checked, not just the ones with a discrepancy."""
    return len(_address_groups(leases))


def build_deal_mismatch_report_data(
    property_address: Optional[str] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Runs every detector once and assembles the single data structure
    both the PDF and Excel renderers in deal_mismatch_export.py read
    from (same "one shared computation, multiple export formats"
    convention investment_memo.py's build_investment_memo_data already
    follows), so the two formats can never disagree about what they're
    reporting for the same request.

    `property_address` optionally scopes to one building (same
    _normalize_building_address-based filter investment_memo.py's
    _scoped_leases uses) -- omitted means the whole portfolio.
    """
    from .investment_memo import _scoped_leases  # local import: avoids a module-level cycle, investment_memo.py doesn't import this module

    all_leases = get_all_effective_leases()
    leases = _scoped_leases(all_leases, property_address)

    discrepancies: List[Dict[str, Any]] = []
    for detector in _DETECTORS:
        if detector is detect_expired_but_occupied:
            discrepancies.extend(detector(leases, today))
        else:
            discrepancies.extend(detector(leases))

    signed_annual_impacts = [
        row["annual_dollar_impact"] if row["income_direction"] == "overstate" else -row["annual_dollar_impact"]
        for row in discrepancies
        if row["income_direction"] is not None and row["annual_dollar_impact"] is not None
    ]
    annual_income_overstatement = round(sum(signed_annual_impacts), 2) if signed_annual_impacts else None

    return {
        "property_address": property_address,
        "generated_date": (today or date.today()).isoformat(),
        "total_units_checked": _total_units_checked(leases),
        "total_discrepancies": len(discrepancies),
        "annual_income_overstatement": annual_income_overstatement,
        "discrepancies": discrepancies,
    }
