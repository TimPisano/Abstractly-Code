"""
Deal Mismatch Report renderers: PDF and Excel, both reading from the one
data structure deal_mismatch.build_deal_mismatch_report_data returns, so
the two formats can never disagree about what they're reporting for the
same request -- same convention investment_memo.py's two renderers
already follow off build_investment_memo_data.

PDF: reportlab platypus (SimpleDocTemplate/Table/Paragraph), reusing
summary_memo.py's shared styles/footer/header machinery rather than
re-declaring fonts/colors/margins a third time in this codebase.

Excel: openpyxl, one sheet, styled the same way rent_roll_export.py's
workbook is (bold frozen header, currency number format on the impact
column) so a Deal Mismatch Report workbook looks like it came from the
same product as every other Abstractly export.
"""
import io
from datetime import date
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as _xml_escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

from .summary_memo import (
    _build_pdf,
    _header_flowables,
    _styles,
    _INK,
    _MUTED,
    _RULE,
    _SEVERITY_COLORS,
)

# One-paragraph plain-English definition per discrepancy type, used in
# both the per-finding detail pages (as a caption under the finding) and
# the methodology appendix -- a single place to keep this wording so the
# two can't drift apart from each other.
_METHODOLOGY_DESCRIPTIONS: Dict[str, str] = {
    "rent_mismatch": "The rent amount on the rent roll disagrees with the Base Rent stated in the signed lease, beyond a small rounding/timing tolerance. The signed lease controls; the rent roll's figure is treated as the error.",
    "expired_but_occupied": "The signed lease's stated end date has already passed, but the rent roll still lists the unit as occupied by a paying tenant, with no newer lease or renewal on file.",
    "unit_no_lease": "The rent roll lists an occupied, paying unit with no corresponding lease document on file. The rent roll's rent is unconfirmed, not asserted as wrong -- there is no lease to compare it against.",
    "lease_no_unit": "A lease document is on file for a unit that doesn't appear anywhere on the uploaded rent roll.",
    "concession_missing": "The lease grants a rent concession the rent roll doesn't note, making the rent roll's full stated rent an overstatement of effective rent.",
    "dates_mismatch": "The lease start and/or end date on the rent roll disagrees with the signed lease.",
    "tenant_mismatch": "The tenant name on the rent roll disagrees with the signed lease.",
    "t12_income_gap": "The property's trailing 12-month actual collections disagree materially with what the rent roll's in-place rent implies the property should be collecting.",
    "t12_occupancy_mismatch": "The T12's reported occupancy disagrees materially with the rent roll's own occupancy.",
    "t12_concession_gap": "The T12 reports concessions the rent roll doesn't reflect.",
    "t12_bad_debt_trend": "The T12 shows a bad debt / collection loss pattern material enough to flag for underwriting.",
}

# A portfolio-wide report could in principle have hundreds of findings;
# a dedicated page per finding beyond this count would make the PDF
# unreasonably large without adding much the summary table above it
# doesn't already say. Same "don't silently truncate, say what was cut"
# rule summary_memo.py's own _MAX_RISKS_SHOWN already follows.
_MAX_DETAIL_PAGES = 60

_HEADLINE_STYLE = ParagraphStyle(
    "DealMismatchHeadline", fontName="Helvetica-Bold", fontSize=30, leading=34, textColor=_INK, spaceAfter=2,
)

DISCREPANCY_TYPE_LABELS = {
    "rent_mismatch": "Rent Mismatch",
    "expired_but_occupied": "Expired but Occupied",
    "unit_no_lease": "Unit on Rent Roll, No Lease",
    "lease_no_unit": "Lease on File, Not on Rent Roll",
    "concession_missing": "Concession Missing from Rent Roll",
    "dates_mismatch": "Lease Dates Mismatch",
    "tenant_mismatch": "Tenant Name Mismatch",
    "t12_income_gap": "Rent Roll vs. T12 Income",
    "t12_occupancy_mismatch": "Rent Roll vs. T12 Occupancy",
    "t12_concession_gap": "T12 Concessions Reported",
    "t12_bad_debt_trend": "T12 Bad Debt Trend",
}

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _fmt_source(source: Optional[Dict[str, Any]]) -> str:
    if not source or not source.get("page"):
        return "—"
    return f"Page {source['page']}"


def _summary_flowables(data: Dict[str, Any]) -> List[Any]:
    scope = data.get("property_address") or "whole portfolio"
    overstatement = data.get("annual_income_overstatement")

    if overstatement is None:
        headline = "Not enough matched, dollar-quantified discrepancies to estimate a net income impact."
    elif overstatement > 0:
        headline = f"Rent roll <b>overstates</b> annual income by <b>{_fmt_money(overstatement)}</b>."
    elif overstatement < 0:
        headline = f"Rent roll <b>understates</b> annual income by <b>{_fmt_money(abs(overstatement))}</b>."
    else:
        headline = "Rent roll and lease-documented income agree overall (net impact: $0)."

    return [
        Paragraph(f"Scope: {scope}", _styles["body"]),
        Paragraph(f"Units checked: {data.get('total_units_checked', 0)}", _styles["body"]),
        Paragraph(f"Discrepancies found: {data.get('total_discrepancies', 0)}", _styles["body"]),
        Spacer(1, 4),
        Paragraph(headline, _styles["section"]),
    ]


def _dollar_impact_sort_key(row: Dict[str, Any]):
    """
    Descending by annual dollar impact -- the institutional-report
    convention (biggest exposure first), as opposed to severity, which
    only coarsely buckets into high/medium/low and loses the actual
    ranking within a bucket. A row with no quantifiable impact (None)
    sorts last, after every row that has a real number, rather than
    being treated as a $0 impact (which would misleadingly rank it
    above a small-but-real finding).
    """
    impact = row.get("annual_dollar_impact")
    return (impact is None, -(impact or 0.0))


def _discrepancies_table(rows: List[Dict[str, Any]]) -> Table:
    header = [
        Paragraph("<b>UNIT</b>", _styles["cell_label"]),
        Paragraph("<b>TYPE</b>", _styles["cell_label"]),
        Paragraph("<b>RENT ROLL</b>", _styles["cell_label"]),
        Paragraph("<b>LEASE</b>", _styles["cell_label"]),
        Paragraph("<b>SOURCE</b>", _styles["cell_label"]),
        Paragraph("<b>SEVERITY</b>", _styles["cell_label"]),
        Paragraph("<b>ANNUAL IMPACT</b>", _styles["cell_label"]),
    ]
    table_rows = [header]
    ordered = sorted(rows, key=_dollar_impact_sort_key)
    for row in ordered:
        severity = row.get("severity") or "low"
        color = _SEVERITY_COLORS.get(severity, _MUTED)
        table_rows.append([
            Paragraph(row.get("unit") or "—", _styles["cell_value"]),
            Paragraph(DISCREPANCY_TYPE_LABELS.get(row["discrepancy_type"], row["discrepancy_type"]), _styles["cell_value"]),
            Paragraph(str(row.get("rent_roll_value") or "—"), _styles["cell_value"]),
            Paragraph(str(row.get("lease_value") or "—"), _styles["cell_value"]),
            Paragraph(_fmt_source(row.get("source")), _styles["cell_value"]),
            Paragraph(f'<font color="{color.hexval()}"><b>{severity.upper()}</b></font>', _styles["cell_value"]),
            Paragraph(_fmt_money(row.get("annual_dollar_impact")), _styles["cell_value"]),
        ])

    table = Table(
        table_rows,
        colWidths=[1.2 * inch, 1.1 * inch, 0.9 * inch, 0.9 * inch, 0.7 * inch, 0.65 * inch, 0.85 * inch],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 1, _INK),
    ]))
    return table


def _severity_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for row in rows:
        severity = row.get("severity") or "low"
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _cover_page_flowables(data: Dict[str, Any], scope: str, generated_date: date, rows: List[Dict[str, Any]]) -> List[Any]:
    overstatement = data.get("annual_income_overstatement")
    if overstatement is None:
        stat_text, stat_caption = "N/A", "Not enough matched, dollar-quantified discrepancies to estimate a net income impact."
    elif overstatement > 0:
        stat_text = _fmt_money(overstatement)
        stat_caption = "Estimated annual income the rent roll OVERSTATES versus the signed leases on file."
    elif overstatement < 0:
        stat_text = _fmt_money(abs(overstatement))
        stat_caption = "Estimated annual income the rent roll UNDERSTATES versus the signed leases on file."
    else:
        stat_text, stat_caption = "$0", "Rent roll and lease-documented income agree overall."

    flowables = _header_flowables(
        "Deal Mismatch Report",
        [f"Rent roll vs. lease documents &mdash; {_xml_escape(scope)}"],
        generated_date,
    )
    flowables.append(Spacer(1, 28))
    flowables.append(Paragraph(stat_text, _HEADLINE_STYLE))
    flowables.append(Paragraph(stat_caption, _styles["body"]))
    flowables.append(Spacer(1, 20))

    counts = _severity_counts(rows)
    stats_header = ["Units Checked", "Discrepancies Found", "High Severity", "Medium Severity", "Low Severity"]
    stats_values = [
        str(data.get("total_units_checked", 0)), str(data.get("total_discrepancies", 0)),
        str(counts["high"]), str(counts["medium"]), str(counts["low"]),
    ]
    stats_table = Table(
        [[Paragraph(f"<b>{h}</b>", _styles["cell_label"]) for h in stats_header],
         [Paragraph(v, _styles["cell_value"]) for v in stats_values]],
        colWidths=[1.25 * inch] * 5,
    )
    stats_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1, _INK),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    flowables.append(stats_table)
    flowables.append(PageBreak())
    return flowables


def _breakdown_by_type_table(rows: List[Dict[str, Any]]) -> Table:
    counts: Dict[str, int] = {}
    totals: Dict[str, float] = {}
    for row in rows:
        t = row["discrepancy_type"]
        counts[t] = counts.get(t, 0) + 1
        impact = row.get("annual_dollar_impact")
        if impact is not None:
            totals[t] = totals.get(t, 0.0) + impact
    ordered_types = sorted(counts.keys(), key=lambda t: -totals.get(t, 0.0))

    header = [
        Paragraph("<b>DISCREPANCY TYPE</b>", _styles["cell_label"]),
        Paragraph("<b>COUNT</b>", _styles["cell_label"]),
        Paragraph("<b>TOTAL ANNUAL IMPACT</b>", _styles["cell_label"]),
    ]
    table_rows = [header]
    for t in ordered_types:
        table_rows.append([
            Paragraph(DISCREPANCY_TYPE_LABELS.get(t, t), _styles["cell_value"]),
            Paragraph(str(counts[t]), _styles["cell_value"]),
            Paragraph(_fmt_money(totals.get(t)), _styles["cell_value"]),
        ])
    table = Table(table_rows, colWidths=[3.3 * inch, 1.1 * inch, 1.9 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 1, _INK),
    ]))
    return table


_INCOME_DIRECTION_VERB = {"overstate": "overstates", "understate": "understates"}


def _finding_detail_flowables(index: int, row: Dict[str, Any]) -> List[Any]:
    label = DISCREPANCY_TYPE_LABELS.get(row["discrepancy_type"], row["discrepancy_type"])
    severity = row.get("severity") or "low"
    color = _SEVERITY_COLORS.get(severity, _MUTED)

    flowables: List[Any] = [
        Paragraph(f"Finding {index} &mdash; {_xml_escape(label)}", _styles["section"]),
        Paragraph(
            f'Unit: <b>{_xml_escape(str(row.get("unit") or "—"))}</b> &nbsp;&nbsp;|&nbsp;&nbsp; '
            f'Severity: <font color="{color.hexval()}"><b>{severity.upper()}</b></font>',
            _styles["body"],
        ),
        Spacer(1, 8),
    ]

    compare_table = Table(
        [
            [Paragraph("<b>RENT ROLL</b>", _styles["cell_label"]), Paragraph("<b>LEASE DOCUMENT</b>", _styles["cell_label"])],
            [
                Paragraph(_xml_escape(str(row.get("rent_roll_value") or "—")), _styles["cell_value"]),
                Paragraph(_xml_escape(str(row.get("lease_value") or "—")), _styles["cell_value"]),
            ],
        ],
        colWidths=[3 * inch, 3 * inch],
    )
    compare_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, _RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(compare_table)
    flowables.append(Spacer(1, 10))

    annual = row.get("annual_dollar_impact")
    direction = row.get("income_direction")
    if annual is not None and direction in _INCOME_DIRECTION_VERB:
        monthly = _fmt_money(row.get("monthly_dollar_impact"))
        flowables.append(Paragraph(
            f"This finding <b>{_INCOME_DIRECTION_VERB[direction]}</b> income by <b>{monthly}/month</b> "
            f"(<b>{_fmt_money(annual)}/year</b>).",
            _styles["body"],
        ))
    elif annual is not None:
        flowables.append(Paragraph(
            f"Unconfirmed exposure: <b>{_fmt_money(row.get('monthly_dollar_impact'))}/month</b> "
            f"(<b>{_fmt_money(annual)}/year</b>) &mdash; no signed lease on file to confirm a direction.",
            _styles["body"],
        ))
    else:
        flowables.append(Paragraph("No dollar amount could be quantified for this finding.", _styles["muted"]))
    flowables.append(Spacer(1, 10))

    source = row.get("source")
    if source and source.get("page"):
        quote = _xml_escape(source.get("quote") or "")
        flowables.append(Paragraph(f"<b>Source citation</b> &mdash; Page {source['page']} of the lease document:", _styles["body"]))
        flowables.append(Paragraph(f"&ldquo;{quote}&rdquo;", _styles["muted"]))
    else:
        flowables.append(Paragraph("<b>Source citation</b> &mdash; no lease document on file to cite for this unit.", _styles["muted"]))

    description = _METHODOLOGY_DESCRIPTIONS.get(row["discrepancy_type"])
    if description:
        flowables.append(Spacer(1, 8))
        flowables.append(Paragraph(f"<i>{description}</i>", _styles["muted"]))

    flowables.append(PageBreak())
    return flowables


def _methodology_flowables() -> List[Any]:
    flowables = [
        Paragraph("Methodology", _styles["section"]),
        Paragraph(
            "This report reconciles an uploaded rent roll against the signed lease documents on file for the "
            "same units, unit by unit, and -- when a T12 operating statement is also on file -- cross-checks the "
            "rent roll against actual trailing-12-month collections. Every dollar figure above is computed "
            "directly from the rent roll and lease data as uploaded; nothing is estimated or inferred beyond "
            "what those documents state.",
            _styles["body"],
        ),
        Spacer(1, 6),
        Paragraph(
            "Severity (High/Medium/Low) is this product's standard discrepancy severity scale, the same scale "
            "used everywhere else a discrepancy is surfaced in the app -- it is not specific to this report.",
            _styles["body"],
        ),
        Spacer(1, 10),
        Paragraph("Discrepancy types", _styles["section"]),
    ]
    for discrepancy_type in DISCREPANCY_TYPES_ORDER:
        label = DISCREPANCY_TYPE_LABELS.get(discrepancy_type, discrepancy_type)
        description = _METHODOLOGY_DESCRIPTIONS.get(discrepancy_type)
        if not description:
            continue
        flowables.append(Paragraph(f"<b>{label}.</b> {description}", _styles["body"]))
        flowables.append(Spacer(1, 4))
    flowables.append(Spacer(1, 6))
    flowables.append(Paragraph(
        "Limitations: concession_missing is planted-ready in this product's own demo fixtures but not yet live "
        "in production detection, pending a dedicated lease concessions field (see release notes). The T12 "
        "cross-check only ever compares against the rent roll's in-place rent; it does not itself reconcile "
        "against individual leases the way the findings above do.",
        _styles["muted"],
    ))
    return flowables


DISCREPANCY_TYPES_ORDER = list(DISCREPANCY_TYPE_LABELS.keys())


def generate_deal_mismatch_report_pdf(data: Dict[str, Any]) -> bytes:
    scope = data.get("property_address") or "Whole Portfolio"
    generated_date = date.fromisoformat(data["generated_date"]) if data.get("generated_date") else date.today()
    rows = data.get("discrepancies") or []

    flowables = _cover_page_flowables(data, scope, generated_date, rows)

    flowables.append(Paragraph("Executive Summary", _styles["section"]))
    flowables.extend(_summary_flowables(data))
    if rows:
        flowables.append(Spacer(1, 10))
        flowables.append(Paragraph("Impact by discrepancy type", _styles["body"]))
        flowables.append(Spacer(1, 4))
        flowables.append(_breakdown_by_type_table(rows))

    flowables.append(Paragraph("Findings (sorted by annual dollar impact)", _styles["section"]))
    if not rows:
        flowables.append(Paragraph("No discrepancies found.", _styles["muted"]))
    else:
        flowables.append(_discrepancies_table(rows))

    # T12 section
    t12_rows = data.get("rent_roll_vs_actual_collections")
    if t12_rows:
        flowables.append(Spacer(1, 12))
        flowables.append(Paragraph("Rent Roll vs. Actual Collections (T12 Cross-Check)", _styles["section"]))
        t12_overstatement = data.get("estimated_income_overstatement_from_t12")
        if t12_overstatement is not None:
            if t12_overstatement > 0:
                headline = f"Rent roll <b>overstates</b> actual collections by <b>{_fmt_money(t12_overstatement)}</b>."
            else:
                headline = f"Rent roll <b>understates</b> actual collections by <b>{_fmt_money(abs(t12_overstatement))}</b>."
        else:
            headline = "No dollar-quantified T12 findings."
        flowables.append(Paragraph(headline, _styles["body"]))
        flowables.append(Spacer(1, 8))
        flowables.append(_discrepancies_table(t12_rows))

    if rows:
        flowables.append(PageBreak())
        ordered = sorted(rows, key=_dollar_impact_sort_key)
        shown, omitted = ordered[:_MAX_DETAIL_PAGES], ordered[_MAX_DETAIL_PAGES:]
        for index, row in enumerate(shown, start=1):
            flowables.extend(_finding_detail_flowables(index, row))
        if omitted:
            flowables.append(Paragraph(
                f"{len(omitted)} additional finding(s) are included in the Findings table above but omitted "
                "from individual detail pages to keep this report a reasonable length.",
                _styles["muted"],
            ))
            flowables.append(Spacer(1, 10))

    flowables.extend(_methodology_flowables())

    return _build_pdf(flowables)


_EXCEL_HEADER = [
    "Unit", "Discrepancy Type", "Field", "Rent Roll Value", "Lease Value",
    "Source Page", "Severity", "Monthly Impact", "Annual Impact", "Income Direction",
]
_EXCEL_COLUMN_WIDTHS = [26, 26, 16, 22, 22, 12, 10, 16, 16, 16]
_CURRENCY_FORMAT = "$#,##0.00"


def generate_deal_mismatch_report_excel(data: Dict[str, Any]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Deal Mismatch Report"

    scope = data.get("property_address") or "Whole Portfolio"
    header_font = Font(bold=True)
    title_font = Font(bold=True, size=14)

    sheet.cell(row=1, column=1, value="Deal Mismatch Report").font = title_font
    sheet.cell(row=2, column=1, value=f"Scope: {scope}")
    sheet.cell(row=3, column=1, value=f"Units checked: {data.get('total_units_checked', 0)}")
    sheet.cell(row=4, column=1, value=f"Discrepancies found: {data.get('total_discrepancies', 0)}")

    overstatement = data.get("annual_income_overstatement")
    if overstatement is None:
        summary_text = "Not enough matched, dollar-quantified discrepancies to estimate a net income impact."
    elif overstatement > 0:
        summary_text = f"Rent roll overstates annual income by {_fmt_money(overstatement)}."
    elif overstatement < 0:
        summary_text = f"Rent roll understates annual income by {_fmt_money(abs(overstatement))}."
    else:
        summary_text = "Rent roll and lease-documented income agree overall (net impact: $0)."
    sheet.cell(row=5, column=1, value=summary_text).font = Font(bold=True)

    header_row = 7
    for index, column in enumerate(_EXCEL_HEADER, start=1):
        cell = sheet.cell(row=header_row, column=index, value=column)
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.fill = PatternFill(start_color="F0EDE5", end_color="F0EDE5", fill_type="solid")
        sheet.column_dimensions[get_column_letter(index)].width = _EXCEL_COLUMN_WIDTHS[index - 1]

    rows = data.get("discrepancies") or []
    ordered = sorted(rows, key=lambda r: (_SEVERITY_ORDER.get(r.get("severity"), 99), r.get("unit") or ""))
    current_row = header_row + 1
    for row in ordered:
        source = row.get("source") or {}
        values = [
            row.get("unit"),
            DISCREPANCY_TYPE_LABELS.get(row["discrepancy_type"], row["discrepancy_type"]),
            row.get("field"),
            row.get("rent_roll_value"),
            row.get("lease_value"),
            source.get("page"),
            (row.get("severity") or "").upper(),
            row.get("monthly_dollar_impact"),
            row.get("annual_dollar_impact"),
            row.get("income_direction"),
        ]
        for col_offset, value in enumerate(values, start=1):
            cell = sheet.cell(row=current_row, column=col_offset, value=value)
            if col_offset in (8, 9) and value is not None:
                cell.number_format = _CURRENCY_FORMAT
        current_row += 1

    # T12 section
    t12_rows = data.get("rent_roll_vs_actual_collections")
    if t12_rows:
        # Add blank row for spacing
        current_row += 1

        # Add T12 header
        t12_header_row = current_row
        sheet.cell(row=t12_header_row, column=1, value="Rent Roll vs. Actual Collections (T12)").font = Font(bold=True)
        current_row += 1

        # T12 overstatement summary
        t12_overstatement = data.get("estimated_income_overstatement_from_t12")
        if t12_overstatement is not None:
            if t12_overstatement > 0:
                summary_text = f"Rent roll overstates actual collections by {_fmt_money(t12_overstatement)}."
            else:
                summary_text = f"Rent roll understates actual collections by {_fmt_money(abs(t12_overstatement))}."
        else:
            summary_text = "No dollar-quantified T12 findings."
        sheet.cell(row=current_row, column=1, value=summary_text)
        current_row += 1

        # T12 header row
        t12_header_start = current_row
        for index, column in enumerate(_EXCEL_HEADER, start=1):
            cell = sheet.cell(row=current_row, column=index, value=column)
            cell.font = header_font
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.fill = PatternFill(start_color="E8F4F8", end_color="E8F4F8", fill_type="solid")
        current_row += 1

        # T12 data rows
        t12_ordered = sorted(t12_rows, key=lambda r: (_SEVERITY_ORDER.get(r.get("severity"), 99), r.get("unit") or ""))
        for row in t12_ordered:
            source = row.get("source") or {}
            values = [
                row.get("unit"),
                DISCREPANCY_TYPE_LABELS.get(row["discrepancy_type"], row["discrepancy_type"]),
                row.get("field"),
                row.get("rent_roll_value"),
                row.get("lease_value"),
                source.get("page"),
                (row.get("severity") or "").upper(),
                row.get("monthly_dollar_impact"),
                row.get("annual_dollar_impact"),
                row.get("income_direction"),
            ]
            for col_offset, value in enumerate(values, start=1):
                cell = sheet.cell(row=current_row, column=col_offset, value=value)
                if col_offset in (8, 9) and value is not None:
                    cell.number_format = _CURRENCY_FORMAT
            current_row += 1

    sheet.freeze_panes = f"A{header_row + 1}"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
