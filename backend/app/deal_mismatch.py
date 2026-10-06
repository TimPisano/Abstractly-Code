"""
Deal Mismatch Report: cross-checks an uploaded rent roll against the
lease PDFs on file and optionally against a T12 (trailing 12-month)
operating statement, producing one dollar-quantified discrepancy list,
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
        "discrepancy_type": one of the 11 categories below,
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

Concession checks (detect_concession_missing, detect_concession_mismatch,
detect_concession_expiring) read the lease PDF's `concessions` field --
a structured schedule of free months, recurring discounts and one-time
credits, see concessions.py -- and price it into the lease's net
effective rent. Their dollar impact is the ANNUALIZED concession value:
(gross rent - net effective rent) x 12, i.e. how much more income per
year the rent roll's gross rent implies than the lease actually yields.
rent_mismatch is effective-rent aware too: a rent roll that already
shows the lease's discounted current rent, or its net effective rent, is
reflecting the concession correctly and isn't reported as a mismatch.

All three concession checks skip a lease whose term has already ended
-- detect_expired_but_occupied already counts that unit's ENTIRE rent
as overstated, so also counting its concession would double count it.

T12 detectors (detect_t12_income_gap, detect_t12_occupancy_mismatch,
detect_t12_concession_gap, detect_t12_bad_debt_trend) take optional
t12_data and materiality_pct and return [] immediately if no T-12 was
uploaded, so the whole section is silently absent from a report with no
T-12 file.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from .concessions import (
    add_months,
    describe_item,
    effective_rent_for_lease,
    has_unreadable_concession,
    rent_reflects_concession,
    timing_note,
)
from .database import get_all_effective_leases
from .discrepancies import _severity_for_monthly_impact
import re

from .normalize import parse_currency, parse_date, parse_escalation_schedule, parse_percent
from .portfolio import (
    _is_rent_roll_import,
    _normalize_address,
    _normalize_for_matching,
    _operative_documents,
    _same_tenant,
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
    "concession_mismatch",
    "concession_expiring",
    "dates_mismatch",
    "tenant_mismatch",
    "t12_income_gap",
    "t12_occupancy_mismatch",
    "t12_concession_gap",
    "t12_bad_debt_trend",
]

_T12_MATERIALITY_THRESHOLD_PCT_DEFAULT = 3.0


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


def _address_groups(leases: List[Dict[str, Any]], today: Optional[date] = None) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
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
    today = today or date.today()
    for group in groups.values():
        group["lease_document"] = _operative_documents(group["lease_document"], today)
    return groups


def _same_amount(a: float, b: float) -> bool:
    """Not a disagreement under compute_rent_roll_reconciliation's own two tolerance constants -- the one definition of "close enough" for money here."""
    diff_abs = abs(a - b)
    larger = max(abs(a), abs(b))
    diff_pct = (diff_abs / larger * 100) if larger > 0 else 0.0
    return not (diff_abs > _RENT_DISAGREEMENT_TOLERANCE_ABS and diff_pct > _RENT_DISAGREEMENT_TOLERANCE_PCT)


def _effective_rent_summary(effective: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The compact effective-rent block attached to concession-related rows (the full priced schedule stays out of the row -- the row's own lease_value/source already describe it)."""
    if not effective:
        return None
    return {
        "base_rent": effective["base_rent"],
        "net_effective_rent": effective["net_effective_rent"],
        "current_rent": effective["current_rent"],
        "total_concession_value": effective["total_concession_value"],
        "annualized_concession_value": effective["annualized_concession_value"],
        "term_months": effective["term_months"],
        "term_assumed": effective["term_assumed"],
    }


def _is_expired(doc_lease: Dict[str, Any], today: date) -> bool:
    doc_end = parse_date(field_value(doc_lease, "lease_end_date"))
    return doc_end is not None and doc_end < today


def _concession_sources(effective: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One {page, quote} citation per distinct concession clause -- a stacked concession can span several sections or pages."""
    sources, seen = [], set()
    for item in effective["items"]:
        key = (item.get("page"), item.get("quote"))
        if item.get("quote") and key not in seen:
            seen.add(key)
            sources.append({"page": item.get("page") or 1, "quote": item["quote"]})
    return sources


def _unreadable_concession_value(doc_lease: Dict[str, Any]) -> Optional[str]:
    """The lease's concession text when one was found but couldn't be priced into a schedule, else None."""
    entry = (doc_lease.get("extracted_fields") or {}).get("concessions")
    return entry.get("value") if has_unreadable_concession(entry) else None


def _rr_concession_monthly(rr_lease: Dict[str, Any]) -> Optional[float]:
    """The monthly concession the rent roll itself shows, if it has a concession column (rent_roll_import.py's `concessions`); None if it doesn't."""
    amount = parse_currency(field_value(rr_lease, "concessions"))
    return abs(amount) if amount is not None else None


def _rent_in_effect(doc_lease: Dict[str, Any], base_rent: float, today: date):
    """
    (monthly rent in effect on `today`, escalation_unpriced) for a lease
    document. Reads the extracted rent_escalation: a year table ("Year 1:
    $1,500.00; Year 2: $1,545.00") or a percentage ("3% annually"),
    counted in lease years from lease_start_date. No escalation -> the
    base rent. An escalation that's stated but can't be priced (no start
    date, unrecognized wording) -> the base rent, with escalation_unpriced
    True so the caller doesn't present a step-up as an overstatement.
    """
    text = field_value(doc_lease, "rent_escalation")
    if not text:
        return base_rent, False
    start = parse_date(field_value(doc_lease, "lease_start_date"))
    if start is None:
        return base_rent, True
    if today < start:
        return base_rent, False  # not started yet: still the first-year rent
    lease_year = (today.year - start.year) - ((today.month, today.day) < (start.month, start.day)) + 1
    schedule = parse_escalation_schedule(text)
    if schedule:
        in_effect = [amount for year, amount in schedule if year <= lease_year]
        return (in_effect[-1] if in_effect else base_rent), False
    pct = parse_percent(text)
    if pct is not None and re.search(r"annual|anniversar|each year|per year|yearly", text, re.I):
        return round(base_rent * (1 + pct / 100.0) ** (lease_year - 1), 2), False
    return base_rent, True


def detect_rent_mismatch(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Rent roll rent vs. the lease's rent, effective-rent aware: when the
    lease grants a concession and the rent roll's figure matches the
    lease's discounted CURRENT rent (as of `today`) or its NET EFFECTIVE
    rent, the rent roll is reflecting that concession -- not misstating
    rent -- so no rent_mismatch is reported (detect_concession_expiring
    separately flags a discounted rent that's about to step back up).
    Any other disagreement is measured against the lease's gross base
    rent exactly as before; the concession itself is then reported on
    its own by detect_concession_missing, so the two rows add up to the
    full gap between the rent roll and the lease's effective rent.
    """
    today = today or date.today()
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases, today).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for rr_lease in group["rent_roll"]:
            for doc_lease in group["lease_document"]:
                rr_rent = parse_currency(field_value(rr_lease, "rent_amount"))
                base_rent = parse_currency(field_value(doc_lease, "rent_amount"))
                if rr_rent is None or base_rent is None:
                    continue
                # Compare against the rent IN EFFECT on the as-of date: a
                # scheduled step-up ("Year 2: $1,545") makes a correct rent
                # roll differ from the year-1 rent (AUDIT.md §6.11).
                in_effect, escalation_unpriced = _rent_in_effect(doc_lease, base_rent, today)
                doc_rent = in_effect
                if rr_rent == doc_rent or _same_amount(rr_rent, doc_rent):
                    continue
                effective = effective_rent_for_lease(doc_lease, today)
                if effective and rent_reflects_concession(
                    rr_rent, effective, _RENT_DISAGREEMENT_TOLERANCE_ABS, _RENT_DISAGREEMENT_TOLERANCE_PCT
                ):
                    continue
                diff_abs = abs(rr_rent - doc_rent)

                monthly_impact = diff_abs
                row = {
                    "discrepancy_type": "rent_mismatch",
                    "unit": _display_unit(rr_lease, doc_lease),
                    "field": "rent_amount",
                    "rent_roll_value": field_value(rr_lease, "rent_amount"),
                    "lease_value": field_value(doc_lease, "rent_amount") if doc_rent == base_rent
                    else f"${doc_rent:,.2f} (scheduled step-up from {field_value(doc_lease, 'rent_amount')})",
                    "source": _field_source(doc_lease, "rent_amount") if doc_rent == base_rent
                    else (_field_source(doc_lease, "rent_escalation") or _field_source(doc_lease, "rent_amount")),
                    "severity": _severity_for_monthly_impact(monthly_impact),
                    "monthly_dollar_impact": round(monthly_impact, 2),
                    "annual_dollar_impact": round(monthly_impact * 12, 2),
                    "income_direction": "overstate" if rr_rent > doc_rent else "understate",
                    "rent_roll_lease_id": rr_lease.get("id"),
                    "lease_document_id": doc_lease.get("id"),
                    "effective_rent": _effective_rent_summary(effective),
                }
                if escalation_unpriced and rr_rent > doc_rent:
                    # The lease states an increase we couldn't price: the
                    # rent roll may simply show the stepped-up rent. Flag
                    # it, but don't count it as an overstatement.
                    row.update(monthly_dollar_impact=None, annual_dollar_impact=None, income_direction=None,
                               severity="medium",
                               note="The lease states a rent escalation that couldn't be priced -- the rent roll "
                                    "may reflect a scheduled increase. Check the escalation clause.")
                rows.append(row)
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
    for group in _address_groups(leases, today).values():
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


def detect_unit_no_lease(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
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
    for group in _address_groups(leases, today).values():
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


def detect_lease_no_unit(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    A lease PDF whose unit never appears on the rent roll at all -- the
    mirror image of unit_no_lease. Unlike that case, this one DOES have
    a defensible direction: a signed lease documents real rent the rent
    roll simply isn't counting, so the rent roll understates income by
    that lease's rent.
    """
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases, today).values():
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


def detect_concession_missing(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    The lease grants a concession (free month, move-in special, recurring
    discount, one-time credit) and the rent roll shows the full gross
    rent with no concession -- so the rent roll implies more income than
    the lease actually yields. Dollar impact is the concession's
    annualized value, (gross rent - net effective rent) x 12; for a
    typical 12-month lease that's simply the concession's total value
    ($100/mo off for 6 months -> $600/yr; one month free on $1,075 ->
    $1,075/yr).

    Fires whether or not the concession has already been used up by
    `today`: net effective rent is measured over the whole lease term,
    which is how an underwriter prices a unit that needed a concession to
    lease. The row's `note` says plainly whether each concession is
    already used, active, or upcoming, so a reader can tell "rent roll is
    right going forward but the lease's real yield is lower" apart from
    "the resident is paying less than the rent roll says right now".

    Not reported here (handled elsewhere instead):
      - rent roll has its own concession column with a non-zero amount
        -> detect_concession_mismatch compares the two amounts.
      - rent roll already shows the discounted current rent or the net
        effective rent -> the concession IS reflected.
      - rent roll rent is below the lease's base rent by an unexplained
        amount -> detect_rent_mismatch's row; adding a concession row on
        top would guess at which number the rent roll meant.
      - lease term already ended -> detect_expired_but_occupied.

    A concession the parser found but couldn't price (e.g. a free month
    on a lease whose rent wasn't extracted) is still reported, with
    dollar impact None -- "found, amount unknown", never a guessed $0.
    """
    today = today or date.today()
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases, today).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for doc_lease in group["lease_document"]:
            if _is_expired(doc_lease, today):
                continue
            effective = effective_rent_for_lease(doc_lease, today)
            if not effective:
                unreadable = _unreadable_concession_value(doc_lease)
                if unreadable:
                    rows.extend(_unreadable_concession_missing_rows(group["rent_roll"], doc_lease, unreadable))
                continue
            for rr_lease in group["rent_roll"]:
                rr_concession = _rr_concession_monthly(rr_lease)
                if rr_concession is not None and rr_concession > 0:
                    continue
                rr_rent = parse_currency(field_value(rr_lease, "rent_amount"))
                base = effective["base_rent"]
                if rr_rent is not None and base is not None:
                    if rent_reflects_concession(rr_rent, effective, _RENT_DISAGREEMENT_TOLERANCE_ABS, _RENT_DISAGREEMENT_TOLERANCE_PCT):
                        continue
                    if rr_rent < base and not _same_amount(rr_rent, base):
                        continue

                monthly = effective["monthly_concession_equivalent"]
                annual = effective["annualized_concession_value"]
                rr_display = field_value(rr_lease, "rent_amount") or "(no rent shown)"
                rr_note = " (concession column shows $0.00)" if rr_concession == 0 else " (no concession shown)"
                sources = _concession_sources(effective)
                rows.append({
                    "discrepancy_type": "concession_missing",
                    "unit": _display_unit(rr_lease, doc_lease),
                    "field": "concessions",
                    "rent_roll_value": rr_display + rr_note,
                    "lease_value": "; ".join(describe_item(i) for i in effective["items"]),
                    "source": sources[0] if sources else _field_source(doc_lease, "concessions"),
                    "sources": sources,
                    "severity": _severity_for_monthly_impact(monthly),
                    "monthly_dollar_impact": monthly,
                    "annual_dollar_impact": annual,
                    "income_direction": "overstate",
                    "rent_roll_lease_id": rr_lease.get("id"),
                    "lease_document_id": doc_lease.get("id"),
                    "effective_rent": _effective_rent_summary(effective),
                    "note": timing_note(effective, today),
                })
    return rows


def _unreadable_concession_missing_rows(rent_roll_rows, doc_lease, lease_text):
    """
    The lease states a concession nobody could price (see
    concessions.has_unreadable_concession) and the rent roll shows none:
    still a concession_missing finding, but with no dollar figure -- the
    "found, amount unknown" case, never a silent pass and never a guess.
    """
    rows = []
    for rr_lease in rent_roll_rows:
        rr_concession = _rr_concession_monthly(rr_lease)
        if rr_concession is not None and rr_concession > 0:
            continue
        rows.append({
            "discrepancy_type": "concession_missing",
            "unit": _display_unit(rr_lease, doc_lease),
            "field": "concessions",
            "rent_roll_value": (field_value(rr_lease, "rent_amount") or "(no rent shown)") + " (no concession shown)",
            "lease_value": f"{lease_text} (amount couldn't be read automatically -- review the lease)",
            "source": _field_source(doc_lease, "concessions"),
            "sources": [],
            "severity": "medium",
            "monthly_dollar_impact": None,
            "annual_dollar_impact": None,
            "income_direction": "overstate",
            "rent_roll_lease_id": rr_lease.get("id"),
            "lease_document_id": doc_lease.get("id"),
            "effective_rent": None,
            "note": None,
        })
    return rows


def detect_concession_mismatch(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    The rent roll HAS a concession column showing a non-zero monthly
    concession, and it disagrees with what the lease grants -- including
    the lease granting none at all. Compared against both ways a PMS
    commonly books a concession: the lease's amortized monthly
    equivalent (total concession / term months) and the discount
    actually active in `today`'s month; matching either one is
    agreement. Otherwise the gap, measured against the amortized
    equivalent and annualized, is the dollar impact: a rent roll showing
    a smaller concession than the lease grants overstates income, a
    larger one (or one the lease doesn't support) understates it.
    """
    today = today or date.today()
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases, today).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for doc_lease in group["lease_document"]:
            if _is_expired(doc_lease, today):
                continue
            effective = effective_rent_for_lease(doc_lease, today)
            for rr_lease in group["rent_roll"]:
                rr_concession = _rr_concession_monthly(rr_lease)
                if rr_concession is None or rr_concession == 0:
                    continue

                unreadable = _unreadable_concession_value(doc_lease) if effective is None else None
                if unreadable:
                    # The lease DOES grant something -- just not readably.
                    # Comparing against "no concession" would be a
                    # confident wrong answer; report it unpriced instead.
                    lease_equiv, lease_current = None, None
                    lease_value = f"{unreadable} (amount couldn't be read automatically -- review the lease)"
                    sources = []
                    source = _field_source(doc_lease, "concessions")
                elif effective is None:
                    lease_equiv, lease_current, lease_value = 0.0, None, "No concession in lease"
                    sources: List[Dict[str, Any]] = []
                    source = _field_source(doc_lease, "rent_amount")
                else:
                    lease_equiv = effective["monthly_concession_equivalent"]
                    lease_current = None
                    if effective["current_rent"] is not None and effective["base_rent"] is not None:
                        lease_current = round(effective["base_rent"] - effective["current_rent"], 2)
                    lease_value = "; ".join(describe_item(i) for i in effective["items"])
                    sources = _concession_sources(effective)
                    source = sources[0] if sources else _field_source(doc_lease, "concessions")

                if lease_equiv is not None and _same_amount(rr_concession, lease_equiv):
                    continue
                if lease_current and _same_amount(rr_concession, lease_current):
                    continue

                if lease_equiv is None:
                    monthly = annual = direction = None
                else:
                    gap = lease_equiv - rr_concession
                    monthly = round(abs(gap), 2)
                    annual = round(abs(gap) * 12, 2)
                    direction = "overstate" if gap > 0 else "understate"
                rows.append({
                    "discrepancy_type": "concession_mismatch",
                    "unit": _display_unit(rr_lease, doc_lease),
                    "field": "concessions",
                    "rent_roll_value": f"${rr_concession:,.2f}/mo concession",
                    "lease_value": lease_value,
                    "source": source,
                    "sources": sources,
                    "severity": _severity_for_monthly_impact(monthly),
                    "monthly_dollar_impact": monthly,
                    "annual_dollar_impact": annual,
                    "income_direction": direction,
                    "rent_roll_lease_id": rr_lease.get("id"),
                    "lease_document_id": doc_lease.get("id"),
                    "effective_rent": _effective_rent_summary(effective),
                    "note": timing_note(effective, today) if effective else None,
                })
    return rows


def detect_concession_expiring(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    The rent roll shows the lease's DISCOUNTED current rent as the unit's
    in-place rent, but that discount burns off before the lease ends --
    after which the resident owes the full base rent. Underwriting off
    the rent roll would then understate income for the rest of the term.

    Only recurring discounts that are active as of `today` and end before
    the lease does count (a discount that runs to the end of the term
    never steps up within this lease, and what a renewal would charge
    isn't knowable from the lease). Monthly impact is the step-up; annual
    impact is the step-up times the months of lease term remaining after
    the burn-off, within the 12 months after `today` -- the income the
    rent roll's in-place figure leaves out over the next year.
    """
    today = today or date.today()
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases, today).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for doc_lease in group["lease_document"]:
            if _is_expired(doc_lease, today):
                continue
            effective = effective_rent_for_lease(doc_lease, today)
            if not effective or effective["current_rent"] is None or effective["base_rent"] is None:
                continue
            if effective["current_rent"] >= effective["base_rent"]:
                continue
            lease_end = parse_date(field_value(doc_lease, "lease_end_date"))
            burning = [
                i for i in effective["items"]
                if i["kind"] == "recurring_discount" and i["status"] == "active" and i["end_date"]
                and i["monthly_value"] and (lease_end is None or date.fromisoformat(i["end_date"]) < lease_end)
            ]
            if not burning:
                continue
            for rr_lease in group["rent_roll"]:
                rr_rent = parse_currency(field_value(rr_lease, "rent_amount"))
                if rr_rent is None or not _same_amount(rr_rent, effective["current_rent"]):
                    continue
                step_up = round(sum(i["monthly_value"] for i in burning), 2)
                # Months at full rent after each burn-off, still inside
                # the lease term and inside the next 12 months.
                last_month = add_months(date(today.year, today.month, 1), 11)
                if lease_end is not None:
                    last_month = min(last_month, date(lease_end.year, lease_end.month, 1))
                annual = 0.0
                for item in burning:
                    burn_off = date.fromisoformat(item["end_date"])
                    first_full = add_months(date(burn_off.year, burn_off.month, 1), 1)
                    months_after = (last_month.year - first_full.year) * 12 + last_month.month - first_full.month + 1
                    annual += item["monthly_value"] * max(0, min(12, months_after))
                annual = round(annual, 2)
                if annual <= 0:
                    continue
                ends = ", ".join(sorted({i["end_date"] for i in burning}))
                sources = _concession_sources(effective)
                rows.append({
                    "discrepancy_type": "concession_expiring",
                    "unit": _display_unit(rr_lease, doc_lease),
                    "field": "concessions",
                    "rent_roll_value": f"{field_value(rr_lease, 'rent_amount')} (discounted rent shown as in-place rent)",
                    "lease_value": (
                        "; ".join(describe_item(i) for i in burning)
                        + f" -- ends {ends}; rent then steps up to ${effective['base_rent']:,.2f}"
                    ),
                    "source": sources[0] if sources else _field_source(doc_lease, "concessions"),
                    "sources": sources,
                    "severity": _severity_for_monthly_impact(step_up),
                    "monthly_dollar_impact": step_up,
                    "annual_dollar_impact": annual,
                    "income_direction": "understate",
                    "rent_roll_lease_id": rr_lease.get("id"),
                    "lease_document_id": doc_lease.get("id"),
                    "effective_rent": _effective_rent_summary(effective),
                    "note": timing_note(effective, today),
                })
    return rows


def detect_dates_mismatch(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
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
    for group in _address_groups(leases, today).values():
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


def detect_tenant_mismatch(leases: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Any tenant-name disagreement at all is flagged -- same "no close
    enough for whether it's the same tenant" stance
    compute_rent_roll_reconciliation and discrepancies.py's own
    _rent_roll_mismatch_severity_and_impact already take (always "high").
    No dollar amount is assignable to a naming disagreement on its own.
    """
    rows: List[Dict[str, Any]] = []
    for group in _address_groups(leases, today).values():
        if not group["rent_roll"] or not group["lease_document"]:
            continue
        for rr_lease in group["rent_roll"]:
            for doc_lease in group["lease_document"]:
                rr_tenant = field_value(rr_lease, "tenant")
                doc_tenant = field_value(doc_lease, "tenant")
                rr_norm = _normalize_for_matching(rr_tenant)
                doc_norm = _normalize_for_matching(doc_tenant)
                if not rr_norm or not doc_norm or _same_tenant(rr_tenant, doc_tenant):
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


def _occupied_and_total(leases: List[Dict[str, Any]], unit_counts: Optional[Dict[str, int]]):
    """
    (occupied units, total units) on the rent roll. Prefers the import's
    own unit counts (which include the vacant and down units the importer
    skips as leases -- see _rent_roll_unit_counts); without them every
    imported row is occupied by construction, so this degrades to the old
    "N of N" count.
    """
    if unit_counts and unit_counts.get("total"):
        return unit_counts["occupied"], unit_counts["total"]
    occupied = sum(1 for l in leases if _is_rent_roll_import(l) and field_value(l, "tenant"))
    total = sum(1 for l in leases if _is_rent_roll_import(l))
    return occupied, total


def _rent_roll_unit_counts(team_id: int, leases: List[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    """
    Occupied/total units for the rent-roll rows in scope, from the team's
    stored import summaries (database.get_rent_roll_unit_summaries -- team-
    scoped). For each building in scope, the newest summary whose file is
    one of the rent-roll files actually on file for that building; None if
    there is none (e.g. rows imported before summaries existed).
    """
    from .database import get_rent_roll_unit_summaries
    from .portfolio import _normalize_building_address

    files_by_building: Dict[str, set] = {}
    for lease in leases:
        if _is_rent_roll_import(lease):
            key = _normalize_building_address(field_value(lease, "property_address"))
            if key:
                files_by_building.setdefault(key, set()).add(lease.get("filename"))
    if not files_by_building:
        return None
    occupied = total = 0
    used = set()
    for summary in get_rent_roll_unit_summaries(team_id):
        key = _normalize_building_address(summary["property_address"])
        if key in files_by_building and key not in used and summary["filename"] in files_by_building[key]:
            used.add(key)
            occupied += summary["occupied_units"]
            total += summary["occupied_units"] + len(summary["vacant_units"]) + len(summary["down_units"])
    if not used:
        return None
    return {"occupied": occupied, "total": total}


def detect_t12_income_gap(
    leases: List[Dict[str, Any]], t12_data: Optional[Dict[str, Any]] = None,
    materiality_pct: float = _T12_MATERIALITY_THRESHOLD_PCT_DEFAULT
) -> List[Dict[str, Any]]:
    """
    Rent roll's building-level annualized rent vs. T-12 rental_income_collected.annual.
    Flagged when rent roll is above T-12 collections by more than materiality_pct.
    income_direction is always "overstate" when flagged.
    """
    if not t12_data or t12_data.get("rental_income_collected") is None:
        return []

    from .portfolio import _normalize_building_address

    rows: List[Dict[str, Any]] = []
    rental_income = t12_data["rental_income_collected"]
    t12_annual = rental_income.get("annual")

    if t12_annual is None:
        return []

    # Build building-level rent totals from rent roll
    building_rents: Dict[str, List[float]] = {}
    for lease in leases:
        if _is_rent_roll_import(lease):
            addr = _normalize_building_address(field_value(lease, "property_address"))
            if addr is None:
                continue
            rr_rent = parse_currency(field_value(lease, "rent_amount"))
            if rr_rent is not None:
                building_rents.setdefault(addr, []).append(rr_rent)

    if not building_rents:
        return []

    # For simplicity, compare against the first (and typically only) building in the scope
    first_building_key = list(building_rents.keys())[0]
    # Rent roll rents are MONTHLY; the T-12 figure is ANNUAL. Comparing the
    # raw monthly sum meant the check could never fire (overnight
    # gauntlet / tester-pack bug #2).
    first_building_rent = round(sum(building_rents[first_building_key]) * 12, 2)

    diff_abs = first_building_rent - t12_annual
    if diff_abs <= 0:
        return []

    larger = max(first_building_rent, t12_annual)
    diff_pct = (diff_abs / larger * 100) if larger > 0 else 0.0

    if diff_pct <= materiality_pct:
        return []

    rows.append({
        "discrepancy_type": "t12_income_gap",
        "unit": "Building (T12-based)",
        "field": "rental_income_collected",
        "rent_roll_value": f"${first_building_rent:,.2f}/yr (rent roll x 12)",
        "lease_value": f"${t12_annual:,.2f}/yr (T12)",
        "source": rental_income.get("source"),
        "severity": _severity_for_monthly_impact(diff_abs / 12),
        "monthly_dollar_impact": round(diff_abs / 12, 2),
        "annual_dollar_impact": round(diff_abs, 2),
        "income_direction": "overstate",
        "rent_roll_lease_id": None,
        "lease_document_id": None,
    })
    return rows


def detect_t12_occupancy_mismatch(
    leases: List[Dict[str, Any]], t12_data: Optional[Dict[str, Any]] = None,
    materiality_pct: float = _T12_MATERIALITY_THRESHOLD_PCT_DEFAULT,
    unit_counts: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """
    Rent-roll-implied occupancy vs. T-12-implied occupancy.
    (1 - vacancy_loss.annual / gross_potential_rent.annual), only when both present.
    Flagged past materiality_pct percentage-point gap.
    """
    if not t12_data:
        return []

    gpr = t12_data.get("gross_potential_rent")
    vl = t12_data.get("vacancy_loss")

    if gpr is None or vl is None or gpr.get("annual") is None or vl.get("annual") is None:
        return []

    # Loss lines are printed NEGATIVE on most T-12s ("(17,100.00)"); the
    # math needs magnitudes, or occupancy comes out above 100%.
    gpr_annual = abs(gpr["annual"])
    vl_annual = abs(vl["annual"])

    if gpr_annual <= 0:
        return []

    t12_occupancy = (1.0 - vl_annual / gpr_annual) * 100

    occupied, total = _occupied_and_total(leases, unit_counts)

    if total == 0:
        return []

    rr_occupancy = (occupied / total) * 100

    gap = abs(rr_occupancy - t12_occupancy)

    if gap <= materiality_pct:
        return []

    rows: List[Dict[str, Any]] = []
    rows.append({
        "discrepancy_type": "t12_occupancy_mismatch",
        "unit": "Building (occupancy)",
        "field": "occupancy_rate",
        "rent_roll_value": f"{rr_occupancy:.1f}%",
        "lease_value": f"{t12_occupancy:.1f}% (T12)",
        "source": vl.get("source"),
        "severity": "medium",
        "monthly_dollar_impact": None,
        "annual_dollar_impact": None,
        "income_direction": None,
        "rent_roll_lease_id": None,
        "lease_document_id": None,
    })
    return rows


def detect_t12_concession_gap(
    leases: List[Dict[str, Any]], t12_data: Optional[Dict[str, Any]] = None,
    materiality_pct: float = _T12_MATERIALITY_THRESHOLD_PCT_DEFAULT
) -> List[Dict[str, Any]]:
    """
    Reports the T-12's concessions.annual figure with rent_roll_value: None
    and an explanatory note that it's unverifiable (rent roll has no concessions field).
    income_direction is None since there's no rent-roll-side number.
    """
    if not t12_data or t12_data.get("concessions") is None:
        return []

    concessions = t12_data["concessions"]
    annual = concessions.get("annual")

    if annual is None or round(abs(annual), 2) == 0:
        return []  # no concessions on the T-12 -> nothing to point out
    annual = abs(annual)  # printed negative on most T-12s

    rows: List[Dict[str, Any]] = []
    rows.append({
        "discrepancy_type": "t12_concession_gap",
        "unit": "Building (concessions)",
        "field": "concessions",
        "rent_roll_value": None,
        "lease_value": f"${annual:,.2f} (T12)",
        "source": concessions.get("source"),
        "severity": "low",
        "monthly_dollar_impact": None,
        "annual_dollar_impact": None,
        "income_direction": None,
        "rent_roll_lease_id": None,
        "lease_document_id": None,
    })
    return rows


def detect_t12_bad_debt_trend(
    leases: List[Dict[str, Any]], t12_data: Optional[Dict[str, Any]] = None,
    materiality_pct: float = _T12_MATERIALITY_THRESHOLD_PCT_DEFAULT,
    unit_counts: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """
    Building-level bad debt trend: flags sustained upward trend
    (last 3 months avg notably higher than trailing-12 avg) alongside
    rent roll showing no vacant/non-current units, with plain-English note
    explaining the pattern worth investigating.
    """
    if not t12_data or t12_data.get("bad_debt") is None:
        return []

    bad_debt = t12_data["bad_debt"]
    monthly = bad_debt.get("monthly")

    if monthly is None or len(monthly) < 12:
        return []

    # Compute trailing-12 average and last-3 average
    _MONTH_IDS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    # Oldest -> newest in the statement's own column order: a trailing T-12
    # (Oct..Sep) is not in calendar order, and "last 3 months" must mean
    # the most recent three, not Oct/Nov/Dec by name.
    order = bad_debt.get("month_order") or _MONTH_IDS
    monthly_values = [abs(monthly.get(m)) for m in order if monthly.get(m) is not None]  # magnitudes: bad debt is often printed negative

    if len(monthly_values) < 12:
        return []

    avg_all = sum(monthly_values) / len(monthly_values)
    avg_last_3 = sum(monthly_values[-3:]) / 3

    if avg_all <= 0 or avg_last_3 <= avg_all:
        return []

    pct_increase = ((avg_last_3 - avg_all) / avg_all) * 100

    if pct_increase <= 25:
        return []

    # Check rent roll for vacancies/non-current units
    occupied, total = _occupied_and_total(leases, unit_counts)

    if total == 0 or occupied < total:
        return []  # There are actual vacancies, so the pattern is less anomalous

    rows: List[Dict[str, Any]] = []
    rows.append({
        "discrepancy_type": "t12_bad_debt_trend",
        "unit": "Building (bad debt trend)",
        "field": "bad_debt_trend",
        "rent_roll_value": f"Full occupancy ({occupied}/{total} units)",
        "lease_value": f"Rising bad debt: {avg_last_3:.0f}/mo vs. {avg_all:.0f}/mo avg",
        "source": bad_debt.get("source"),
        "severity": "medium",
        "monthly_dollar_impact": None,
        "annual_dollar_impact": None,
        "income_direction": None,
        "rent_roll_lease_id": None,
        "lease_document_id": None,
    })
    return rows


_DETECTORS = [
    detect_rent_mismatch,
    detect_expired_but_occupied,
    detect_unit_no_lease,
    detect_lease_no_unit,
    detect_concession_missing,
    detect_concession_mismatch,
    detect_concession_expiring,
    detect_dates_mismatch,
    detect_tenant_mismatch,
]

# Detectors whose answer depends on what day it is (an expiry, or which
# concession months are active) -- they take build_deal_mismatch_report_data's
# `today` so a report run with an explicit as-of date is consistent across
# every row.
_DATE_AWARE_DETECTORS = {
    # Every detector that pairs rent-roll rows with lease documents is
    # date-aware: which lease is operative depends on the as-of date.
    detect_unit_no_lease,
    detect_lease_no_unit,
    detect_dates_mismatch,
    detect_tenant_mismatch,
    detect_rent_mismatch,
    detect_expired_but_occupied,
    detect_concession_missing,
    detect_concession_mismatch,
    detect_concession_expiring,
}

_T12_DETECTORS = [
    detect_t12_income_gap,
    detect_t12_occupancy_mismatch,
    detect_t12_concession_gap,
    detect_t12_bad_debt_trend,
]


def _concession_summary(leases: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    """
    Portfolio-level view of every lease PDF in scope that grants a
    concession (whether or not the rent roll reflects it): how many, and
    their combined annualized value -- the "how much of this deal's rent
    is really concession" number. Expired leases are left out for the
    same double-counting reason the detectors skip them. Value is None if
    any concession couldn't be priced, rather than a silently low total.
    """
    priced = []
    unreadable = 0
    for lease in leases:
        if _is_rent_roll_import(lease) or _is_expired(lease, today):
            continue
        effective = effective_rent_for_lease(lease, today)
        if effective:
            priced.append(effective)
        elif _unreadable_concession_value(lease):
            unreadable += 1
    if not priced and not unreadable:
        return {"leases_with_concessions": 0, "annualized_concession_value": 0.0}
    values = [e["annualized_concession_value"] for e in priced]
    complete = not unreadable and all(v is not None for v in values)
    return {
        "leases_with_concessions": len(priced) + unreadable,
        "annualized_concession_value": round(sum(values), 2) if complete else None,
    }


def _total_units_checked(leases: List[Dict[str, Any]]) -> int:
    """Distinct normalized unit addresses across every rent-roll row and lease PDF on file -- the universe this report actually checked, not just the ones with a discrepancy."""
    return len(_address_groups(leases))


def build_deal_mismatch_report_data(
    team_id: int,
    property_address: Optional[str] = None,
    today: Optional[date] = None,
    t12_data: Optional[Dict[str, Any]] = None,
    materiality_threshold_pct: float = _T12_MATERIALITY_THRESHOLD_PCT_DEFAULT,
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

    `t12_data` and `materiality_threshold_pct` are optional, supplied
    when a T-12 was uploaded. T-12 detectors return [] if no t12_data.
    """
    from .investment_memo import _scoped_leases  # local import: avoids a module-level cycle, investment_memo.py doesn't import this module

    all_leases = get_all_effective_leases(team_id)
    leases = _scoped_leases(all_leases, property_address)

    discrepancies: List[Dict[str, Any]] = []
    for detector in _DETECTORS:
        if detector in _DATE_AWARE_DETECTORS:
            discrepancies.extend(detector(leases, today))
        else:
            discrepancies.extend(detector(leases))

    # T12 detectors
    t12_rows: List[Dict[str, Any]] = []
    if t12_data:
        unit_counts = _rent_roll_unit_counts(team_id, leases)
        for detector in _T12_DETECTORS:
            if detector in (detect_t12_occupancy_mismatch, detect_t12_bad_debt_trend):
                t12_rows.extend(detector(leases, t12_data, materiality_threshold_pct, unit_counts=unit_counts))
            else:
                t12_rows.extend(detector(leases, t12_data, materiality_threshold_pct))

    signed_annual_impacts = [
        row["annual_dollar_impact"] if row["income_direction"] == "overstate" else -row["annual_dollar_impact"]
        for row in (discrepancies + t12_rows)
        if row["income_direction"] is not None and row["annual_dollar_impact"] is not None
    ]
    annual_income_overstatement = round(sum(signed_annual_impacts), 2) if signed_annual_impacts else None

    # T12-specific income gap estimation (separate from rent-roll-vs-lease-PDF overstatement)
    t12_income_gap_rows = [r for r in t12_rows if r["discrepancy_type"] == "t12_income_gap"]
    estimated_income_overstatement_from_t12 = None
    if t12_income_gap_rows and t12_income_gap_rows[0]["annual_dollar_impact"] is not None:
        estimated_income_overstatement_from_t12 = t12_income_gap_rows[0]["annual_dollar_impact"]

    # T12 source summary
    t12_source = None
    if t12_data:
        found_categories = [k for k, v in t12_data.items() if v is not None]
        missing_categories = [k for k, v in t12_data.items() if v is None]
        t12_source = {
            "filename": t12_data.get("filename", "unknown"),
            "found_categories": found_categories,
            "missing_categories": missing_categories,
        }

    result = {
        "property_address": property_address,
        "generated_date": (today or date.today()).isoformat(),
        "total_units_checked": _total_units_checked(leases),
        "total_discrepancies": len(discrepancies) + len(t12_rows),
        "annual_income_overstatement": annual_income_overstatement,
        "discrepancies": discrepancies,
        "concession_summary": _concession_summary(leases, today or date.today()),
    }

    if t12_data:
        result["t12_source"] = t12_source
        result["rent_roll_vs_actual_collections"] = t12_rows
        result["estimated_income_overstatement_from_t12"] = estimated_income_overstatement_from_t12

    return result
