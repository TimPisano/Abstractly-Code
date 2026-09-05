"""
Decision-ready PDF output: a one-page summary memo, per lease or for
the whole portfolio, meant to be forwarded to someone who will never
open the app -- an investment committee, a lender, a broker. Key
terms, flagged discrepancies, and the confidence summary, laid out as
a real document rather than a data dump.

This module only lays out data that's already been extracted and
computed elsewhere -- field values/confidence from field_extractor.py,
risk flags from risk_analysis.py (including the cross-lease mismatch
flags portfolio.py merges in), confidence tallies from portfolio.py.
Every function here takes that data as a parameter rather than
recomputing it, the same convention report.py's HTML report already
uses, so this can never quietly disagree with what the app itself
shows for the same lease.

Built with reportlab's platypus layer (SimpleDocTemplate/Paragraph/
Table), not the raw Canvas positioning this project's test fixtures
use to build throwaway sample PDFs -- a real document meant to be read
and forwarded needs actual text wrapping and table layout, not
hand-positioned coordinates. reportlab was already a project
dependency (used only for those test fixtures until now); no new
library was added for this.
"""

import io
from datetime import date
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .normalize import extracted_field_value as _field_value
from .portfolio import compute_lease_confidence_summary

# Same labels the frontend's FIELD_LABELS (app.js) uses, so a field is
# never called two different things depending on whether a human is
# looking at the app or a forwarded PDF.
FIELD_LABELS: Dict[str, str] = {
    "tenant": "Tenant Name",
    "landlord": "Landlord Name",
    "property_address": "Property Address",
    "rent_amount": "Monthly Rent",
    "security_deposit": "Security Deposit",
    "cam_charges": "CAM Charges",
    "rent_escalation": "Rent Escalation",
    "insurance_requirements": "Insurance Requirements",
    "square_footage": "Square Footage",
    "lease_start_date": "Lease Start Date",
    "lease_end_date": "Lease End Date",
    "renewal_options": "Renewal Options",
    "default_cure_period": "Default / Cure Period",
    "permitted_use": "Permitted Use",
    "exclusivity_clause": "Exclusivity Clause",
}

# The fields shown in the Key Terms grid, in display order -- deliberately
# fewer than all 15 (permitted use / exclusivity / cure period are long
# prose, not memo-grid material) so the grid stays scannable at a glance.
_KEY_TERMS_FIELDS = [
    "rent_amount", "lease_start_date",
    "security_deposit", "lease_end_date",
    "cam_charges", "square_footage",
    "rent_escalation", "renewal_options",
]

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_SEVERITY_COLORS = {
    "high": colors.HexColor("#9a3b3b"),
    "medium": colors.HexColor("#a6741f"),
    "low": colors.HexColor("#6b6f76"),
}

# A memo is meant to fit on one page; a portfolio or lease with more
# findings than this still gets every one of them counted in the
# section heading, just not all listed line by line -- same "don't
# silently truncate, say what was cut" rule report.py's HTML report
# already follows for its own risk list.
_MAX_RISKS_SHOWN = 8

_INK = colors.HexColor("#161512")
_MUTED = colors.HexColor("#5b5851")
_ACCENT = colors.HexColor("#b68a4e")
_RULE = colors.HexColor("#e6e0d2")

_styles = {
    # reportlab's ParagraphStyle defaults `leading` to a flat 12pt
    # regardless of fontSize when not given explicitly -- every style
    # below sets it explicitly (~1.3x fontSize) to avoid lines
    # overlapping the next flowable, which a fontSize=18 title with the
    # default leading=12 does visibly.
    "title": ParagraphStyle("MemoTitle", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=_INK, spaceAfter=4),
    "subtitle": ParagraphStyle("MemoSubtitle", fontName="Helvetica", fontSize=10.5, leading=14, textColor=_MUTED, spaceAfter=12),
    "section": ParagraphStyle("MemoSection", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=_INK, spaceBefore=14, spaceAfter=6),
    "body": ParagraphStyle("MemoBody", fontName="Helvetica", fontSize=9.5, textColor=_INK, leading=13),
    "muted": ParagraphStyle("MemoMuted", fontName="Helvetica", fontSize=9.5, textColor=_MUTED, leading=13),
    "cell_label": ParagraphStyle("MemoCellLabel", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=_MUTED),
    "cell_value": ParagraphStyle("MemoCellValue", fontName="Helvetica", fontSize=9.5, textColor=_INK, leading=12),
    "flag": ParagraphStyle("MemoFlag", fontName="Helvetica", fontSize=9, textColor=_INK, leading=12.5),
}


def _lease_label(lease: Dict[str, Any]) -> str:
    return lease.get("display_name") or lease.get("filename") or f"Lease #{lease.get('id')}"


def _footer(canvas_obj, doc) -> None:
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColor(_MUTED)
    canvas_obj.drawString(0.75 * inch, 0.55 * inch, "Generated by Abstractly — every value traceable to its source document")
    canvas_obj.drawRightString(letter[0] - 0.75 * inch, 0.55 * inch, f"Page {doc.page}")
    canvas_obj.restoreState()


def _header_flowables(title: str, subtitle_lines: List[str], generated_date: date) -> List[Any]:
    flowables = [
        Paragraph(title, _styles["title"]),
        Paragraph(f"Generated {generated_date.strftime('%B %-d, %Y')}", _styles["subtitle"]),
    ]
    for line in subtitle_lines:
        flowables.append(Paragraph(line, _styles["body"]))
    flowables.append(Spacer(1, 6))
    flowables.append(HRFlowable(width="100%", thickness=1, color=_RULE, spaceAfter=6))
    return flowables


def _key_terms_table(lease: Dict[str, Any]) -> Table:
    rows = []
    for i in range(0, len(_KEY_TERMS_FIELDS), 2):
        left_field = _KEY_TERMS_FIELDS[i]
        right_field = _KEY_TERMS_FIELDS[i + 1] if i + 1 < len(_KEY_TERMS_FIELDS) else None

        left_value = _field_value(lease, left_field) or "Not found"
        row = [
            Paragraph(FIELD_LABELS[left_field].upper(), _styles["cell_label"]),
            Paragraph(left_value, _styles["cell_value"]),
        ]
        if right_field:
            right_value = _field_value(lease, right_field) or "Not found"
            row += [
                Paragraph(FIELD_LABELS[right_field].upper(), _styles["cell_label"]),
                Paragraph(right_value, _styles["cell_value"]),
            ]
        else:
            row += ["", ""]
        rows.append(row)

    table = Table(rows, colWidths=[1.15 * inch, 2.35 * inch, 1.15 * inch, 2.35 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, _RULE),
    ]))
    return table


def _confidence_summary_flowables(summary: Dict[str, Any]) -> List[Any]:
    if summary["total_fields"] == 0:
        return [Paragraph("No fields to summarize.", _styles["muted"])]

    headline = f"<b>{summary['high']} of {summary['total_fields']}</b> fields high-confidence"
    if summary["flagged_for_review"] > 0:
        headline += f" &mdash; <b>{summary['flagged_for_review']} flagged for review</b>"
    else:
        headline += " &mdash; nothing flagged for review"

    breakdown = (
        f"High: {summary['high']} &nbsp;&nbsp; Medium: {summary['medium']} &nbsp;&nbsp; "
        f"Low: {summary['low']} &nbsp;&nbsp; Not Found: {summary['not_found']}"
    )

    flowables = [
        Paragraph(headline, _styles["body"]),
        Paragraph(breakdown, _styles["muted"]),
    ]

    flagged_labels = summary.get("flagged_fields") or []
    if flagged_labels:
        names = ", ".join(FIELD_LABELS.get(f, f) for f in flagged_labels)
        flowables.append(Paragraph(f"Flagged: {names}", _styles["muted"]))

    return flowables


def _risk_flags_flowables(flags: List[Dict[str, Any]]) -> List[Any]:
    if not flags:
        return [Paragraph("No risk flags on this lease.", _styles["muted"])]

    ordered = sorted(flags, key=lambda f: _SEVERITY_ORDER.get(f["severity"], 99))
    shown = ordered[:_MAX_RISKS_SHOWN]

    flowables = []
    for flag in shown:
        color = _SEVERITY_COLORS.get(flag["severity"], _MUTED)
        severity_label = flag["severity"].upper()
        flowables.append(Paragraph(
            f'<font color="{color.hexval()}"><b>[{severity_label}]</b></font> {flag["message"]}',
            _styles["flag"],
        ))
    if len(ordered) > _MAX_RISKS_SHOWN:
        flowables.append(Paragraph(
            f"...and {len(ordered) - _MAX_RISKS_SHOWN} more (see the full lease detail page).",
            _styles["muted"],
        ))
    return flowables


def _build_pdf(flowables: List[Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    )
    doc.build(flowables, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def generate_lease_summary_pdf(
    lease: Dict[str, Any],
    risk_flags: List[Dict[str, Any]],
    generated_date: Optional[date] = None,
) -> bytes:
    """
    A one-page memo for a single lease: key terms, the confidence
    summary, and flagged risks (including any cross-lease mismatches
    already merged into risk_flags by the caller) -- everything a
    reviewer needs to sanity-check the lease without opening the app.
    """
    generated_date = generated_date or date.today()
    lease_name = _lease_label(lease)
    tenant = _field_value(lease, "tenant") or "Tenant not found"
    landlord = _field_value(lease, "landlord") or "Landlord not found"
    address = _field_value(lease, "property_address")

    subtitle_lines = [f"{tenant} &mdash; {landlord}"]
    if address:
        subtitle_lines.append(address)

    flowables = _header_flowables("Lease Summary Memo", [], generated_date)
    flowables.append(Paragraph(lease_name, _styles["section"]))
    for line in subtitle_lines:
        flowables.append(Paragraph(line, _styles["body"]))
    flowables.append(Spacer(1, 4))

    flowables.append(Paragraph("Key Terms", _styles["section"]))
    flowables.append(_key_terms_table(lease))

    flowables.append(Paragraph("Confidence Summary", _styles["section"]))
    flowables.extend(_confidence_summary_flowables(compute_lease_confidence_summary(lease)))

    flowables.append(Paragraph("Risk Flags", _styles["section"]))
    flowables.extend(_risk_flags_flowables(risk_flags))

    return _build_pdf(flowables)


def generate_portfolio_summary_pdf(
    leases: List[Dict[str, Any]],
    portfolio_confidence_summary: Dict[str, Any],
    risks_by_lease: Dict[int, List[Dict[str, Any]]],
    generated_date: Optional[date] = None,
    extra_sections: Optional[List[Any]] = None,
    title: str = "Portfolio Summary Memo",
) -> bytes:
    """
    A one-page memo for the whole portfolio: a rollup table (one row
    per lease), the portfolio-wide confidence summary, and the
    highest-severity risk flags across every lease.

    `risks_by_lease` is {lease_id: [flag, ...]}, the same per-lease
    flag lists /portfolio/risks already returns (each already carrying
    any cross-lease mismatch flags merged in) -- passed in rather than
    recomputed, so this can never disagree with what /portfolio/risks
    shows for the same portfolio.

    `extra_sections` lets a caller (e.g. the monthly report route)
    append additional flowables -- expirations, rent variance outliers,
    and so on -- after the standard sections, reusing this function's
    header/footer/build machinery instead of duplicating it.
    """
    generated_date = generated_date or date.today()

    flowables = _header_flowables(
        title,
        [f"{len(leases)} lease{'' if len(leases) == 1 else 's'} in this portfolio"],
        generated_date,
    )

    flowables.append(Paragraph("Portfolio Overview", _styles["section"]))
    if leases:
        rows = [[
            Paragraph("<b>LEASE</b>", _styles["cell_label"]),
            Paragraph("<b>RENT</b>", _styles["cell_label"]),
            Paragraph("<b>SQ FT</b>", _styles["cell_label"]),
            Paragraph("<b>EXPIRES</b>", _styles["cell_label"]),
        ]]
        for lease in leases:
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
    else:
        flowables.append(Paragraph("No leases in this portfolio yet.", _styles["muted"]))

    flowables.append(Paragraph("Confidence Summary", _styles["section"]))
    flowables.extend(_confidence_summary_flowables(portfolio_confidence_summary))

    flowables.append(Paragraph("Top Risk Flags", _styles["section"]))
    all_flags = []
    for lease in leases:
        for flag in risks_by_lease.get(lease["id"], []):
            all_flags.append({**flag, "_lease_name": _lease_label(lease)})
    all_flags.sort(key=lambda f: _SEVERITY_ORDER.get(f["severity"], 99))

    if not all_flags:
        flowables.append(Paragraph("No risk flags across the portfolio.", _styles["muted"]))
    else:
        shown = all_flags[:_MAX_RISKS_SHOWN]
        for flag in shown:
            color = _SEVERITY_COLORS.get(flag["severity"], _MUTED)
            flowables.append(Paragraph(
                f'<font color="{color.hexval()}"><b>[{flag["severity"].upper()}]</b></font> '
                f'{flag["_lease_name"]}: {flag["message"]}',
                _styles["flag"],
            ))
        if len(all_flags) > _MAX_RISKS_SHOWN:
            flowables.append(Paragraph(
                f"...and {len(all_flags) - _MAX_RISKS_SHOWN} more across the portfolio (see the full risk view).",
                _styles["muted"],
            ))

    if extra_sections:
        flowables.extend(extra_sections)

    return _build_pdf(flowables)


def monthly_report_extra_sections(
    expiring_90_days: List[Dict[str, Any]],
    rent_variance_outliers: List[Dict[str, Any]],
) -> List[Any]:
    """
    The sections specific to the monthly portfolio report (beyond the
    standard portfolio memo's overview/confidence/risk sections above),
    built to be passed as generate_portfolio_summary_pdf's
    extra_sections -- reuses that function's header/footer/build
    machinery rather than duplicating it.

    `expiring_90_days` is portfolio.py's compute_expiration_alerts()
    ["expiring"] list; `rent_variance_outliers` is
    compute_rent_variance_outliers()'s output. Both are computed by the
    caller (the /portfolio/monthly-report.pdf route) and passed in, the
    same "never recompute what a caller already has" convention every
    other function in this module follows.

    Loss-to-lease is deliberately NOT computed here: it would require
    an asking/market-rent figure this tool has no way to capture from a
    lease document itself (a lease states the *actual* contracted rent,
    never what the landlord could have gotten), so a real number here
    would have to be fabricated. Reported as explicitly unavailable
    instead, with the reason stated -- the same "explicit none message,
    never a silently blank or fabricated section" rule report.py's
    HTML report already follows.
    """
    flowables = [Paragraph("Upcoming Expirations (Next 90 Days)", _styles["section"])]
    if not expiring_90_days:
        flowables.append(Paragraph("No leases expiring in the next 90 days.", _styles["muted"]))
    else:
        for entry in expiring_90_days:
            name = entry.get("display_name") or entry.get("filename") or f"Lease #{entry.get('lease_id')}"
            flowables.append(Paragraph(
                f"{name} &mdash; expires {entry.get('lease_end_date')} ({entry.get('days_remaining')} days)",
                _styles["flag"],
            ))

    flowables.append(Paragraph("Rent Variance Outliers", _styles["section"]))
    if not rent_variance_outliers:
        flowables.append(Paragraph("No leases significantly above or below the portfolio's average rent/sqft.", _styles["muted"]))
    else:
        for entry in rent_variance_outliers:
            direction = "above" if entry["direction"] == "above" else "below"
            flowables.append(Paragraph(
                f'{entry["display_name"]} &mdash; ${entry["rent_per_sqft"]:.2f}/sq ft/mo is '
                f'{abs(entry["diff_pct"]):.0f}% {direction} the portfolio average '
                f'(${entry["portfolio_avg_rent_per_sqft"]:.2f}/sq ft/mo)',
                _styles["flag"],
            ))

    flowables.append(Paragraph("Loss to Lease", _styles["section"]))
    flowables.append(Paragraph(
        "Not available. Loss-to-lease compares actual contracted rent against current asking/market "
        "rent, and this tool has no way to capture an asking-rent figure from a lease document itself "
        "(a lease states what was actually agreed to, never what the landlord could get today). This "
        "section will populate once a market-rent input is added.",
        _styles["muted"],
    ))

    return flowables
