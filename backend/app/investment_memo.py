"""
Investment memo export: a clean, professional PDF or Excel document per
property or per portfolio, meant to be attached to a real investment
committee memo or forwarded to a lender/partner who will never open
this app -- key lease terms, flagged discrepancies AND their
resolutions, a T12 cross-check summary, and a rollover risk summary.

Two things distinguish this from the existing summary_memo.py (a
one-lease or whole-portfolio "everything, briefly" memo) and
report.py (a self-contained HTML report):
  1. Property-level scope. Neither existing export can produce "just
     this one building" -- summary_memo.py is per-lease or whole-
     portfolio only.
  2. Discrepancy RESOLUTIONS, not just risk flags. summary_memo.py's
     "Top Risk Flags" section shows risk_analysis's live-computed
     flags with no resolution status -- this document instead reads
     from the Item-2 discrepancies table, so an outside reader sees
     not just "here's a red flag" but "here's what we found, and
     here's how we resolved it and why" -- the actual point of
     bringing something to an IC: showing the diligence was done, not
     just that a problem exists.

Everything here composes a single canonical data structure
(build_investment_memo_data) that BOTH the PDF and Excel renderers
read from -- the same "one shared computation, multiple export
formats" convention rent_roll_export.py/sheets_export.py already
follow, so the two formats can never disagree about what they're
reporting for the same request.
"""
import io
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from . import database
from .normalize import parse_currency
from .portfolio import (
    FIELD_NAMES,
    _is_rent_roll_import,
    _normalize_address,
    _normalize_building_address,
    compute_portfolio_confidence_summary,
    compute_portfolio_metrics,
    compute_rollover_schedule,
    compute_t12_reconciliation,
    compute_walt,
    field_value,
)
from .summary_memo import (
    FIELD_LABELS,
    _build_pdf,
    _confidence_summary_flowables,
    _field_value,
    _header_flowables,
    _key_terms_table,
    _lease_label,
    _styles,
    _INK,
    _MUTED,
    _RULE,
    _SEVERITY_COLORS,
)


# ----------------------------------------------------------------------
# Data structure -- built once, read by both renderers
# ----------------------------------------------------------------------

def _scoped_leases(all_leases: List[Dict[str, Any]], property_address: Optional[str]) -> List[Dict[str, Any]]:
    if property_address is None:
        return all_leases
    normalized_target = _normalize_building_address(property_address)
    return [
        lease for lease in all_leases
        if _normalize_building_address(field_value(lease, "property_address")) == normalized_target
    ]


def _dedupe_for_financial_computation(scoped_leases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Only for the numbers that get SUMMED (total rent, WALT, rollover
    schedule, confidence tally) -- "Key Lease Terms" still lists every
    record on file, unfiltered.

    When a unit has BOTH a real PDF lease and a rent-roll-imported
    snapshot on file -- exactly the scenario rent-roll reconciliation
    exists to catch, and exactly what generating this memo against a
    real reviewed property surfaced -- counting both toward totals
    double-counts that one unit's rent. A $6,250 PDF lease plus a
    $6,000 rent-roll row for the SAME suite isn't $12,250 of real rent;
    it's one unit with two records of it, one of them a cross-check
    input. That's a materially wrong number to hand a lender or IC, not
    a cosmetic one, so it's fixed here rather than left as a caveat.

    Prefers the PDF lease over the rent-roll row when both exist for
    the same exact unit (suite-inclusive match, _normalize_address --
    the real underlying source document, not a reconciliation input).
    Among multiple leases of the SAME source type for one unit, keeps
    whichever was uploaded most recently. A lease with no parseable
    address at all can't be deduped against anything, so it's kept
    as-is rather than silently dropped.
    """
    by_unit: Dict[str, Dict[str, Any]] = {}
    unmatched: List[Dict[str, Any]] = []

    for lease in scoped_leases:
        unit_key = _normalize_address(field_value(lease, "property_address"))
        if unit_key is None:
            unmatched.append(lease)
            continue

        existing = by_unit.get(unit_key)
        if existing is None:
            by_unit[unit_key] = lease
            continue

        existing_is_rr = _is_rent_roll_import(existing)
        candidate_is_rr = _is_rent_roll_import(lease)
        if existing_is_rr and not candidate_is_rr:
            by_unit[unit_key] = lease
        elif existing_is_rr == candidate_is_rr and lease["uploaded_at"] > existing["uploaded_at"]:
            by_unit[unit_key] = lease

    return list(by_unit.values()) + unmatched


def _relevant_discrepancies(scoped_lease_ids: set, normalized_target: Optional[str], portfolio_wide: bool) -> List[Dict[str, Any]]:
    """
    Which persisted discrepancies (Item 2) belong in this document.
    Portfolio scope: everything. Property scope: anything tied to one
    of this property's leases (lease_id or related_lease_id), PLUS any
    t12_reconciliation discrepancy whose own address normalizes to the
    same building (that discrepancy type carries no lease_id at all --
    see app/discrepancies.py's sync_t12_reconciliation -- so it can
    only be matched by address). tenant_concentration discrepancies are
    inherently portfolio-wide facts about a tenant, not about one
    property, so they're excluded from a property-scoped memo.
    """
    all_discrepancies = database.list_discrepancies()
    if portfolio_wide:
        return all_discrepancies

    relevant = []
    for disc in all_discrepancies:
        if disc["lease_id"] in scoped_lease_ids or disc.get("related_lease_id") in scoped_lease_ids:
            relevant.append(disc)
        elif disc["discrepancy_type"] == "t12_reconciliation":
            disc_address = _normalize_building_address(disc["details"].get("property_address"))
            if disc_address and disc_address == normalized_target:
                relevant.append(disc)
    return relevant


def _t12_cross_check_section(
    scoped_leases: List[Dict[str, Any]],
    property_address: Optional[str],
    t12_parsed: Optional[Dict[str, Any]],
    relevant_discrepancies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Prefers a FRESH cross-check if the caller supplied a just-parsed
    T12 file (same shape t12_import.py's parse_csv_t12/parse_xlsx_t12
    return) -- the natural case when someone is generating a memo today
    and has this quarter's T12 in hand. Falls back to the most
    recently-seen PERSISTED t12_reconciliation discrepancy for this
    property (Item 2 / the alerting system both already populate this
    when a real mismatch was found), so a memo generated without a
    fresh upload still shows the last known cross-check rather than
    nothing. Reports honestly when neither exists -- never fabricates
    a number.
    """
    if t12_parsed is not None and property_address:
        result = compute_t12_reconciliation(scoped_leases, property_address, t12_parsed["annual_rental_income"])
        result["t12_source"] = t12_parsed["source"]
        return {"available": True, "basis": "fresh_upload", **result}

    t12_discrepancies = [d for d in relevant_discrepancies if d["discrepancy_type"] == "t12_reconciliation"]
    if t12_discrepancies:
        most_recent = max(t12_discrepancies, key=lambda d: d["last_seen_at"])
        return {"available": True, "basis": "persisted", "discrepancy_id": most_recent["id"], **most_recent["details"]}

    return {
        "available": False,
        "reason": (
            "No T12 on file for this property, and no T12 cross-check has been "
            "run for it yet. Upload one via POST /portfolio/t12-reconciliation, "
            "or pass a T12 file when generating this memo."
            if property_address else
            "T12 cross-check is only available when generating a memo for a single property."
        ),
    }


def build_investment_memo_data(
    property_address: Optional[str] = None,
    t12_parsed: Optional[Dict[str, Any]] = None,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    The single data structure both generate_investment_memo_pdf and
    generate_investment_memo_excel render from. See the module
    docstring for why this is scoped the way it is.
    """
    reference_date = reference_date or date.today()
    all_leases = database.get_all_effective_leases()
    scoped = _scoped_leases(all_leases, property_address)
    scoped_ids = {lease["id"] for lease in scoped}
    normalized_target = _normalize_building_address(property_address) if property_address else None
    financial_leases = _dedupe_for_financial_computation(scoped)

    discrepancies = _relevant_discrepancies(scoped_ids, normalized_target, portfolio_wide=property_address is None)
    discrepancies_with_resolutions = []
    open_count = 0
    for disc in discrepancies:
        entry = dict(disc)
        entry["resolutions"] = database.get_discrepancy_resolutions(disc["id"])
        discrepancies_with_resolutions.append(entry)
        if disc["status"] == "open":
            open_count += 1
    discrepancies_with_resolutions.sort(
        key=lambda d: ({"high": 0, "medium": 1, "low": 2}.get(d.get("severity"), 3), d["status"] != "open")
    )

    return {
        "scope": "property" if property_address else "portfolio",
        "property_address": property_address,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lease_count": len(financial_leases),
        "record_count": len(scoped),
        "leases": scoped,
        "portfolio_metrics": compute_portfolio_metrics(financial_leases),
        "confidence_summary": compute_portfolio_confidence_summary(financial_leases),
        "discrepancies": discrepancies_with_resolutions,
        "discrepancy_summary": {
            "total": len(discrepancies_with_resolutions),
            "open": open_count,
            "resolved": len(discrepancies_with_resolutions) - open_count,
        },
        "t12_cross_check": _t12_cross_check_section(financial_leases, property_address, t12_parsed, discrepancies_with_resolutions),
        "rollover": {
            "walt": compute_walt(financial_leases, reference_date=reference_date),
            "rollover_schedule": compute_rollover_schedule(financial_leases, reference_date=reference_date),
        },
    }


# ----------------------------------------------------------------------
# PDF renderer
# ----------------------------------------------------------------------

_ROLLOVER_BUCKET_LABELS = {
    "year_1": "Year 1", "year_2": "Year 2", "year_3": "Year 3",
    "year_4": "Year 4", "year_5": "Year 5", "year_6_plus": "Year 6+",
}

_MAX_LEASES_DETAILED = 25   # property scope: full key-terms table per lease
_MAX_LEASES_ROLLUP = 30     # portfolio scope: compact rollup table rows shown
_MAX_DISCREPANCIES_SHOWN = 15


def _overview_flowables(data: Dict[str, Any]) -> List[Any]:
    metrics = data["portfolio_metrics"]
    scope_label = data["property_address"] if data["scope"] == "property" else "Full Portfolio"

    def _money(v):
        return f"${v:,.2f}" if v is not None else "Not available"

    lines = [
        f"<b>{data['lease_count']}</b> lease{'s' if data['lease_count'] != 1 else ''} covered in this memo",
        f"Total monthly rent: <b>{_money(metrics.get('total_monthly_rent'))}</b>",
    ]
    if metrics.get("avg_rent_per_sqft") is not None:
        lines.append(f"Average rent per square foot: <b>${metrics['avg_rent_per_sqft']:.2f}</b>")

    flowables = [
        Paragraph("Overview", _styles["section"]),
        Paragraph(scope_label, _styles["body"]),
        *[Paragraph(line, _styles["body"]) for line in lines],
    ]
    if data["record_count"] > data["lease_count"]:
        flowables.append(Paragraph(
            f"({data['record_count'] - data['lease_count']} additional rent-roll cross-check "
            "record(s) on file for units already covered above are listed in Key Lease Terms "
            "below but excluded from these totals to avoid double-counting.)",
            _styles["muted"],
        ))
    return flowables


def _key_terms_flowables(data: Dict[str, Any]) -> List[Any]:
    """
    Property scope: a full key-terms grid per lease (a property usually
    has few enough units for this to be tractable and genuinely useful
    to an outside reader). Portfolio scope: a compact rollup table
    instead -- a portfolio can have hundreds of leases, where a full
    grid per lease would produce an unusable document, not a memo.
    """
    flowables = [Paragraph("Key Lease Terms", _styles["section"])]
    leases = data["leases"]

    if not leases:
        flowables.append(Paragraph("No leases in scope.", _styles["muted"]))
        return flowables

    if data["scope"] == "property":
        shown = leases[:_MAX_LEASES_DETAILED]
        for lease in shown:
            tenant = _field_value(lease, "tenant") or "Tenant not found"
            source_label = "Rent Roll Import — cross-check record, not counted in totals above" if _is_rent_roll_import(lease) else "Lease Document"
            flowables.append(Paragraph(f"{_lease_label(lease)} &mdash; {tenant}", _styles["body"]))
            flowables.append(Paragraph(source_label, _styles["muted"]))
            flowables.append(_key_terms_table(lease))
            flowables.append(Spacer(1, 4))
        if len(leases) > _MAX_LEASES_DETAILED:
            flowables.append(Paragraph(
                f"...and {len(leases) - _MAX_LEASES_DETAILED} more lease(s) not shown in detail (see the full rent roll export).",
                _styles["muted"],
            ))
    else:
        rows = [[
            Paragraph("<b>LEASE</b>", _styles["cell_label"]),
            Paragraph("<b>RENT</b>", _styles["cell_label"]),
            Paragraph("<b>SQ FT</b>", _styles["cell_label"]),
            Paragraph("<b>EXPIRES</b>", _styles["cell_label"]),
        ]]
        for lease in leases[:_MAX_LEASES_ROLLUP]:
            rows.append([
                Paragraph(_lease_label(lease), _styles["cell_value"]),
                Paragraph(_field_value(lease, "rent_amount") or "—", _styles["cell_value"]),
                Paragraph(_field_value(lease, "square_footage") or "—", _styles["cell_value"]),
                Paragraph(_field_value(lease, "lease_end_date") or "—", _styles["cell_value"]),
            ])
        table = Table(rows, colWidths=[2.7 * inch, 1.35 * inch, 1.1 * inch, 1.75 * inch], repeatRows=1)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
            ("LINEBELOW", (0, 0), (-1, 0), 1, _INK),
        ]))
        flowables.append(table)
        if len(leases) > _MAX_LEASES_ROLLUP:
            flowables.append(Paragraph(f"...and {len(leases) - _MAX_LEASES_ROLLUP} more (see the full rent roll export).", _styles["muted"]))

    return flowables


def _discrepancies_flowables(data: Dict[str, Any]) -> List[Any]:
    summary = data["discrepancy_summary"]
    flowables = [Paragraph("Flagged Discrepancies & Resolutions", _styles["section"])]

    if summary["total"] == 0:
        flowables.append(Paragraph("No discrepancies have been flagged in this scope.", _styles["muted"]))
        return flowables

    flowables.append(Paragraph(
        f"<b>{summary['total']}</b> flagged &mdash; <b>{summary['open']} open</b>, <b>{summary['resolved']} resolved</b>",
        _styles["body"],
    ))

    shown = data["discrepancies"][:_MAX_DISCREPANCIES_SHOWN]
    for disc in shown:
        color = _SEVERITY_COLORS.get(disc.get("severity"), _MUTED)
        severity_label = (disc.get("severity") or "unknown").upper()
        category_label = disc["category"].replace("_", " ").title()
        flowables.append(Paragraph(
            f'<font color="{color.hexval()}"><b>[{severity_label}]</b></font> <b>{category_label}:</b> {disc["message"]}',
            _styles["flag"],
        ))
        if disc["status"] == "open":
            flowables.append(Paragraph("Status: Open &mdash; not yet resolved.", _styles["muted"]))
        else:
            latest_resolution = next((r for r in reversed(disc["resolutions"]) if r["action"] == "resolved"), None)
            if latest_resolution:
                resolved_date = latest_resolution["created_at"][:10]
                flowables.append(Paragraph(
                    f'Status: Resolved &mdash; <b>{latest_resolution["correct_source"]}</b> confirmed correct by '
                    f'{latest_resolution["resolved_by"]} on {resolved_date}: "{latest_resolution["note"]}"',
                    _styles["muted"],
                ))
        flowables.append(Spacer(1, 3))

    if len(data["discrepancies"]) > _MAX_DISCREPANCIES_SHOWN:
        flowables.append(Paragraph(
            f"...and {len(data['discrepancies']) - _MAX_DISCREPANCIES_SHOWN} more (see the full discrepancy log).",
            _styles["muted"],
        ))

    return flowables


def _t12_flowables(data: Dict[str, Any]) -> List[Any]:
    t12 = data["t12_cross_check"]
    flowables = [Paragraph("T12 Cross-Check Summary", _styles["section"])]

    if not t12["available"]:
        flowables.append(Paragraph(t12["reason"], _styles["muted"]))
        return flowables

    basis_label = "just uploaded for this memo" if t12["basis"] == "fresh_upload" else "from the last cross-check on file"
    flowables.append(Paragraph(f"Basis: T12 {basis_label}.", _styles["muted"]))

    if t12.get("rent_roll_annual_rent") is None:
        flowables.append(Paragraph(
            "Not enough rent-roll data at this property to compute an annual rent total to compare against.",
            _styles["muted"],
        ))
        return flowables

    direction_label = {
        "rent_roll_higher": "Rent roll is HIGHER than the T12's actual rental income",
        "t12_higher": "T12's actual rental income is HIGHER than the rent roll",
        "agree": "Rent roll and T12 agree",
    }.get(t12.get("direction"), "")

    flag_color = _SEVERITY_COLORS["high"] if t12.get("flagged") else colors.HexColor("#2f6b4f")
    flag_label = "FLAGGED — MATERIAL DISCREPANCY" if t12.get("flagged") else "WITHIN NORMAL RANGE"

    rows = [
        [Paragraph("<b>RENT ROLL ANNUAL RENT</b>", _styles["cell_label"]), Paragraph(f"${t12['rent_roll_annual_rent']:,.2f}", _styles["cell_value"])],
        [Paragraph("<b>T12 ANNUAL RENTAL INCOME</b>", _styles["cell_label"]), Paragraph(f"${t12['t12_annual_rental_income']:,.2f}", _styles["cell_value"])],
        [Paragraph("<b>DIFFERENCE</b>", _styles["cell_label"]), Paragraph(f"${t12['difference']:,.2f} ({t12['difference_pct']:.1f}%)", _styles["cell_value"])],
        [Paragraph("<b>RESULT</b>", _styles["cell_label"]), Paragraph(f'<font color="{flag_color.hexval()}"><b>{flag_label}</b></font>', _styles["cell_value"])],
    ]
    table = Table(rows, colWidths=[2.2 * inch, 4.3 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, _RULE),
    ]))
    flowables.append(table)
    if direction_label:
        flowables.append(Paragraph(direction_label, _styles["muted"]))
    return flowables


def _rollover_flowables(data: Dict[str, Any]) -> List[Any]:
    rollover = data["rollover"]["rollover_schedule"]
    walt = data["rollover"]["walt"]
    flowables = [Paragraph("Rollover Risk Summary", _styles["section"])]

    if rollover.get("total_rent") is None:
        flowables.append(Paragraph("Not enough lease-end-date/rent data in this scope to compute a rollover schedule.", _styles["muted"]))
        return flowables

    walt_years = walt.get("walt_years")
    walt_line = f"Weighted Average Lease Term (WALT): <b>{walt_years:.1f} years</b>" if walt_years is not None else "WALT: not available"
    risk_level = (rollover.get("rollover_risk_level") or "unknown").upper()
    flowables.append(Paragraph(f"{walt_line} &mdash; Rollover risk level: <b>{risk_level}</b>", _styles["body"]))

    rows = [[
        Paragraph("<b>PERIOD</b>", _styles["cell_label"]),
        Paragraph("<b>RENT EXPIRING</b>", _styles["cell_label"]),
        Paragraph("<b>% OF RENT</b>", _styles["cell_label"]),
        Paragraph("<b>LEASES</b>", _styles["cell_label"]),
    ]]
    for bucket_name in _ROLLOVER_BUCKET_LABELS:
        bucket = rollover["buckets"][bucket_name]
        rows.append([
            Paragraph(_ROLLOVER_BUCKET_LABELS[bucket_name], _styles["cell_value"]),
            Paragraph(f"${bucket['rent']:,.0f}", _styles["cell_value"]),
            Paragraph(f"{bucket['pct_of_total_rent']:.1f}%", _styles["cell_value"]),
            Paragraph(str(bucket["lease_count"]), _styles["cell_value"]),
        ])
    already_expired = rollover["already_expired"]
    if already_expired["lease_count"] > 0:
        rows.append([
            Paragraph("Already Expired", _styles["cell_value"]),
            Paragraph(f"${already_expired['rent']:,.0f}", _styles["cell_value"]),
            Paragraph("—", _styles["cell_value"]),
            Paragraph(str(already_expired["lease_count"]), _styles["cell_value"]),
        ])

    table = Table(rows, colWidths=[1.6 * inch, 1.6 * inch, 1.3 * inch, 1.0 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 1, _INK),
    ]))
    flowables.append(table)
    return flowables


def generate_investment_memo_pdf(data: Dict[str, Any]) -> bytes:
    """Renders build_investment_memo_data's output as a multi-page PDF, reusing summary_memo.py's header/footer/style machinery for visual consistency with every other document this app produces."""
    generated_date = datetime.fromisoformat(data["generated_at"]).date()
    title = f"Investment Memo — {data['property_address']}" if data["scope"] == "property" else "Investment Memo — Full Portfolio"

    flowables = _header_flowables(title, [], generated_date)
    flowables.extend(_overview_flowables(data))
    flowables.extend(_key_terms_flowables(data))
    flowables.extend(_discrepancies_flowables(data))
    flowables.extend(_t12_flowables(data))
    flowables.extend(_rollover_flowables(data))
    flowables.append(Paragraph("Data Confidence Summary", _styles["section"]))
    flowables.extend(_confidence_summary_flowables(data["confidence_summary"]))

    return _build_pdf(flowables)


# ----------------------------------------------------------------------
# Excel renderer -- one sheet per section, all from the same data dict
# ----------------------------------------------------------------------

_HEADER_FILL = PatternFill(start_color="2B2A27", end_color="2B2A27", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_TITLE_FONT = Font(bold=True, size=14)
_SUBTITLE_FONT = Font(italic=True, color="5B5851")


def _write_header_row(sheet, row: int, labels: List[str]) -> None:
    for col, label in enumerate(labels, start=1):
        cell = sheet.cell(row=row, column=col, value=label)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _autosize(sheet, widths: List[int]) -> None:
    for i, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(i)].width = width


def _add_overview_sheet(workbook: Workbook, data: Dict[str, Any]) -> None:
    sheet = workbook.active
    sheet.title = "Overview"
    scope_label = data["property_address"] if data["scope"] == "property" else "Full Portfolio"

    sheet["A1"] = "Investment Memo"
    sheet["A1"].font = _TITLE_FONT
    sheet["A2"] = scope_label
    sheet["A2"].font = _SUBTITLE_FONT
    sheet["A3"] = f"Generated {data['generated_at'][:10]}"
    sheet["A3"].font = _SUBTITLE_FONT

    metrics = data["portfolio_metrics"]
    leases_covered_label = "Leases Covered"
    leases_covered_value = data["lease_count"]
    if data["record_count"] > data["lease_count"]:
        leases_covered_label = "Leases Covered (excl. rent-roll cross-check duplicates)"

    rows = [
        (leases_covered_label, leases_covered_value),
        ("Total Monthly Rent", metrics.get("total_monthly_rent")),
        ("Average Rent / Sq Ft", metrics.get("avg_rent_per_sqft")),
        ("Total Square Footage", metrics.get("total_square_footage")),
        ("Discrepancies Flagged", data["discrepancy_summary"]["total"]),
        ("Discrepancies Open", data["discrepancy_summary"]["open"]),
        ("Discrepancies Resolved", data["discrepancy_summary"]["resolved"]),
        ("WALT (years)", data["rollover"]["walt"].get("walt_years")),
        ("Data Confidence: High-Confidence Fields", f"{data['confidence_summary'].get('high_confidence_pct')}%" if data["confidence_summary"].get("high_confidence_pct") is not None else "N/A"),
    ]
    for i, (label, value) in enumerate(rows, start=5):
        sheet.cell(row=i, column=1, value=label).font = Font(bold=True)
        sheet.cell(row=i, column=2, value=value if value is not None else "N/A")
    _autosize(sheet, [32, 24])


def _add_key_terms_sheet(workbook: Workbook, data: Dict[str, Any]) -> None:
    """Lists every record on file (including rent-roll cross-check rows for a unit that also has a PDF lease) -- the "Source" column, not omission, is how a reader tells them apart. Totals on the Overview sheet exclude the duplicate side; see build_investment_memo_data's _dedupe_for_financial_computation."""
    sheet = workbook.create_sheet("Key Lease Terms")
    columns = ["Lease", "Source"] + [FIELD_LABELS.get(name, name) for name in FIELD_NAMES]
    _write_header_row(sheet, 1, columns)

    for row_idx, lease in enumerate(data["leases"], start=2):
        sheet.cell(row=row_idx, column=1, value=_lease_label(lease))
        sheet.cell(row=row_idx, column=2, value="Rent Roll Import" if _is_rent_roll_import(lease) else "Lease Document")
        for col_idx, field_name in enumerate(FIELD_NAMES, start=3):
            value = field_value(lease, field_name)
            sheet.cell(row=row_idx, column=col_idx, value=value if value is not None else "")

    _autosize(sheet, [28, 16] + [20] * len(FIELD_NAMES))
    sheet.freeze_panes = "C2"


def _add_discrepancies_sheet(workbook: Workbook, data: Dict[str, Any]) -> None:
    sheet = workbook.create_sheet("Discrepancies & Resolutions")
    _write_header_row(sheet, 1, ["Severity", "Category", "Field", "Message", "Status", "Resolved By", "Resolved At", "Correct Source", "Resolution Note"])

    row_idx = 2
    for disc in data["discrepancies"]:
        latest_resolution = next((r for r in reversed(disc["resolutions"]) if r["action"] == "resolved"), None)
        sheet.cell(row=row_idx, column=1, value=(disc.get("severity") or "").upper())
        sheet.cell(row=row_idx, column=2, value=disc["category"].replace("_", " ").title())
        sheet.cell(row=row_idx, column=3, value=disc.get("field") or "")
        sheet.cell(row=row_idx, column=4, value=disc["message"])
        sheet.cell(row=row_idx, column=5, value=disc["status"].title())
        if latest_resolution:
            sheet.cell(row=row_idx, column=6, value=latest_resolution["resolved_by"])
            sheet.cell(row=row_idx, column=7, value=latest_resolution["created_at"][:10])
            sheet.cell(row=row_idx, column=8, value=latest_resolution["correct_source"])
            sheet.cell(row=row_idx, column=9, value=latest_resolution["note"])
        row_idx += 1

    if not data["discrepancies"]:
        sheet.cell(row=2, column=1, value="No discrepancies flagged in this scope.")

    _autosize(sheet, [10, 20, 16, 50, 12, 18, 14, 16, 45])
    sheet.freeze_panes = "A2"


def _add_t12_sheet(workbook: Workbook, data: Dict[str, Any]) -> None:
    sheet = workbook.create_sheet("T12 Cross-Check")
    t12 = data["t12_cross_check"]

    if not t12["available"]:
        sheet["A1"] = "T12 Cross-Check Summary"
        sheet["A1"].font = _TITLE_FONT
        sheet["A2"] = t12["reason"]
        _autosize(sheet, [90])
        return

    rows = [
        ("Basis", "Fresh upload" if t12["basis"] == "fresh_upload" else "Last cross-check on file"),
        ("Property Address", t12.get("property_address")),
        ("Rent Roll Annual Rent", t12.get("rent_roll_annual_rent")),
        ("T12 Annual Rental Income", t12.get("t12_annual_rental_income")),
        ("Difference", t12.get("difference")),
        ("Difference %", t12.get("difference_pct")),
        ("Direction", t12.get("direction")),
        ("Flagged", "Yes — material discrepancy" if t12.get("flagged") else "No — within normal range"),
    ]
    sheet["A1"] = "T12 Cross-Check Summary"
    sheet["A1"].font = _TITLE_FONT
    for i, (label, value) in enumerate(rows, start=3):
        sheet.cell(row=i, column=1, value=label).font = Font(bold=True)
        sheet.cell(row=i, column=2, value=value if value is not None else "N/A")
    _autosize(sheet, [26, 34])


def _add_rollover_sheet(workbook: Workbook, data: Dict[str, Any]) -> None:
    sheet = workbook.create_sheet("Rollover Schedule")
    rollover = data["rollover"]["rollover_schedule"]
    walt = data["rollover"]["walt"]

    sheet["A1"] = "Rollover Risk Summary"
    sheet["A1"].font = _TITLE_FONT
    if walt.get("walt_years") is not None:
        sheet["A2"] = f"WALT: {walt['walt_years']:.1f} years"
    if rollover.get("rollover_risk_level"):
        sheet["A3"] = f"Rollover risk level: {rollover['rollover_risk_level'].upper()}"

    if rollover.get("total_rent") is None:
        sheet["A5"] = "Not enough lease-end-date/rent data in this scope to compute a rollover schedule."
        _autosize(sheet, [70])
        return

    _write_header_row(sheet, 5, ["Period", "Rent Expiring", "% of Rent", "Leases"])
    row_idx = 6
    for bucket_name in _ROLLOVER_BUCKET_LABELS:
        bucket = rollover["buckets"][bucket_name]
        sheet.cell(row=row_idx, column=1, value=_ROLLOVER_BUCKET_LABELS[bucket_name])
        sheet.cell(row=row_idx, column=2, value=bucket["rent"])
        sheet.cell(row=row_idx, column=3, value=f"{bucket['pct_of_total_rent']:.1f}%")
        sheet.cell(row=row_idx, column=4, value=bucket["lease_count"])
        row_idx += 1

    already_expired = rollover["already_expired"]
    if already_expired["lease_count"] > 0:
        sheet.cell(row=row_idx, column=1, value="Already Expired")
        sheet.cell(row=row_idx, column=2, value=already_expired["rent"])
        sheet.cell(row=row_idx, column=3, value="—")
        sheet.cell(row=row_idx, column=4, value=already_expired["lease_count"])

    _autosize(sheet, [18, 18, 12, 10])


def generate_investment_memo_excel(data: Dict[str, Any]) -> bytes:
    """Renders build_investment_memo_data's output as a multi-sheet workbook: Overview, Key Lease Terms, Discrepancies & Resolutions, T12 Cross-Check, Rollover Schedule."""
    workbook = Workbook()
    _add_overview_sheet(workbook, data)
    _add_key_terms_sheet(workbook, data)
    _add_discrepancies_sheet(workbook, data)
    _add_t12_sheet(workbook, data)
    _add_rollover_sheet(workbook, data)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
