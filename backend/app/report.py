"""
Printable one-page portfolio summary report.

This is the only output of the tool designed to be read by someone who will
never open the app: it gets saved to PDF, emailed, or printed and handed
across a desk. Three consequences shape the whole module:

  - The HTML is fully self-contained (one inline <style>, no external
    stylesheet, font, script, or image). A saved or emailed file has to render
    identically with no network, and an <img>/CDN reference is exactly what
    breaks first in that setting.
  - It is styled for ink: light background, restrained borders, severity
    conveyed by a small tinted badge rather than a full-bleed color block, and
    @media print rules that drop screen chrome and keep sections from being
    split across a page break.
  - Every section degrades to an explicit "none" message instead of vanishing.
    A blank section reads as a rendering bug to someone holding the printout;
    "No leases expiring in the next 6 months" reads as a finding.

Inputs are the plain dicts produced by the portfolio, timeline, and risk
modules; nothing here imports them, so this module can be rendered from
hand-built data (and is, in its tests).
"""

import html
from datetime import date
from typing import Any, Dict, List, Optional

from .normalize import (
    extracted_field_value as _field_value,
    format_currency as _format_currency,
    format_sqft as _format_sqft,
)


# Rendered in the header for a reader to recognize whose portfolio this is.
# A placeholder until the app models named portfolios.
PORTFOLIO_NAME_PLACEHOLDER = "Lease Portfolio"

# Only the near-term buckets are shown: a printed summary is a decision aid,
# and a lease expiring in three years isn't a decision this quarter.
_TIMELINE_SECTIONS = [
    ("expiring_0_6_months", "Expiring within 6 months", "urgent"),
    ("expiring_6_12_months", "Expiring in 6-12 months", "soon"),
    ("expiring_12_24_months", "Expiring in 12-24 months", "later"),
]

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_MAX_RISKS_SHOWN = 15


def generate_portfolio_report_html(
    leases: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    timeline: Dict[str, Any],
    all_risks: List[Dict[str, Any]],
) -> str:
    """
    Builds the complete report document as a single self-contained HTML string.

    all_risks is per-lease: [{"lease_id", "filename", "tenant", "flags": [...]}].
    Every argument is read defensively (`.get`, `or {}`) because this report is
    the last thing in the pipeline and should still print something honest if
    an upstream module hands it a partial result.
    """
    metrics = metrics or {}
    timeline = timeline or {}
    leases = leases or []
    all_risks = all_risks or []

    body = "\n".join([
        _render_header(),
        _render_summary(metrics, leases),
        _render_leases(leases),
        _render_timeline(timeline),
        _render_risks(all_risks),
        _render_footer(),
    ])

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Portfolio Summary Report</title>\n"
        f"<style>\n{_STYLES}\n</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def _render_header() -> str:
    return f"""<header class="report-header">
  <h1>Portfolio Summary Report</h1>
  <p class="portfolio-name">{html.escape(PORTFOLIO_NAME_PLACEHOLDER)}</p>
  <p class="generated">Generated {html.escape(_format_long_date(date.today()))}</p>
</header>"""


def _render_summary(metrics: Dict[str, Any], leases: List[Dict[str, Any]]) -> str:
    """
    The five figures a reader wants before anything else. lease_count falls
    back to the actual list length so the headline number can never contradict
    the lease table printed directly beneath it.
    """
    lease_count = metrics.get("lease_count")
    if lease_count is None:
        lease_count = len(leases)

    if lease_count == 0:
        return _section(
            "Portfolio Summary",
            '<p class="empty">No leases in this portfolio yet. Upload leases to '
            "populate this report.</p>",
        )

    tiles = [
        ("Leases", _format_count(lease_count)),
        ("Total Monthly Rent", _format_currency(metrics.get("total_monthly_rent"))),
        ("Average Monthly Rent", _format_currency(metrics.get("avg_monthly_rent"))),
        ("Total CAM Exposure", _format_currency(metrics.get("total_cam_exposure"))),
        ("Total Square Footage", _format_sqft(metrics.get("total_square_footage"))),
    ]
    cells = "\n".join(
        f'  <div class="tile"><span class="tile-label">{html.escape(label)}</span>'
        f'<span class="tile-value">{html.escape(value)}</span></div>'
        for label, value in tiles
    )
    return _section("Portfolio Summary", f'<div class="tiles">\n{cells}\n</div>')


def _render_leases(leases: List[Dict[str, Any]]) -> str:
    """
    A compact inventory so the reader can tie every figure above to a real
    document — the filename is what they'd go open to verify a number.
    """
    if not leases:
        return _section(
            "Leases",
            '<p class="empty">No leases to list.</p>',
        )

    rows = []
    for lease in leases:
        tenant = _field_value(lease, "tenant") or "Tenant not found"
        filename = lease.get("filename") or "(unnamed file)"
        rent = _field_value(lease, "rent_amount") or "—"
        start = _field_value(lease, "lease_start_date") or "—"
        end = _field_value(lease, "lease_end_date") or "—"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(tenant))}</td>"
            f'<td class="filename">{html.escape(str(filename))}</td>'
            f'<td class="num">{html.escape(str(rent))}</td>'
            f"<td>{html.escape(str(start))} &ndash; {html.escape(str(end))}</td>"
            "</tr>"
        )

    table = (
        '<table class="data">\n<thead><tr><th>Tenant</th><th>File</th>'
        '<th class="num">Monthly Rent</th><th>Term</th></tr></thead>\n<tbody>\n'
        + "\n".join(rows)
        + "\n</tbody>\n</table>"
    )
    return _section("Leases", table)


def _render_timeline(timeline: Dict[str, Any]) -> str:
    """
    Near-term expirations, most urgent first. The 0-6 month bucket is marked
    visually because it's the only one with an action deadline attached.
    """
    blocks = []
    for key, heading, tone in _TIMELINE_SECTIONS:
        entries = timeline.get(key) or []
        if entries:
            rows = "\n".join(_render_timeline_row(entry) for entry in entries)
            content = (
                '<table class="data">\n<thead><tr><th>Tenant</th><th>File</th>'
                '<th>Lease End</th><th class="num">Months Left</th></tr></thead>\n'
                f"<tbody>\n{rows}\n</tbody>\n</table>"
            )
        else:
            content = '<p class="empty">None.</p>'
        count = f'<span class="bucket-count">{len(entries)}</span>'
        blocks.append(
            f'<div class="bucket bucket-{tone}">\n'
            f"<h3>{html.escape(heading)} {count}</h3>\n{content}\n</div>"
        )

    expired = timeline.get("already_expired") or []
    unknown = timeline.get("unknown_expiration") or []
    notes = []
    if expired:
        notes.append(f"{len(expired)} lease(s) already past their end date")
    if unknown:
        notes.append(f"{len(unknown)} lease(s) with no usable end date")
    if notes:
        blocks.append(
            f'<p class="note">Also: {html.escape("; ".join(notes))}.</p>'
        )

    return _section("Expiration Timeline", "\n".join(blocks))


def _render_timeline_row(entry: Dict[str, Any]) -> str:
    tenant = entry.get("tenant") or "Tenant not found"
    filename = entry.get("filename") or "(unnamed file)"
    end_date = entry.get("lease_end_date") or "—"
    months = entry.get("months_remaining")
    months_text = "—" if months is None else f"{float(months):.1f}"
    return (
        "<tr>"
        f"<td>{html.escape(str(tenant))}</td>"
        f'<td class="filename">{html.escape(str(filename))}</td>'
        f"<td>{html.escape(str(end_date))}</td>"
        f'<td class="num">{html.escape(months_text)}</td>'
        "</tr>"
    )


def _render_risks(all_risks: List[Dict[str, Any]]) -> str:
    """
    One flat, severity-ranked list across the whole portfolio, capped at
    _MAX_RISKS_SHOWN. A printed report that lists every low-severity flag on
    every lease buries the two high-severity ones that actually matter; the
    cap is stated explicitly so the reader knows more exist.
    """
    flattened = []
    for lease_risks in all_risks:
        filename = lease_risks.get("filename") or "(unnamed file)"
        tenant = lease_risks.get("tenant")
        for flag in lease_risks.get("flags") or []:
            flattened.append((filename, tenant, flag))

    if not flattened:
        return _section(
            "Top Red Flags",
            '<p class="empty">No risk flags were raised across this portfolio.</p>',
        )

    flattened.sort(key=lambda item: _SEVERITY_ORDER.get(item[2].get("severity"), 3))
    shown = flattened[:_MAX_RISKS_SHOWN]

    rows = []
    for filename, tenant, flag in shown:
        severity = str(flag.get("severity") or "low").lower()
        badge_class = severity if severity in _SEVERITY_ORDER else "low"
        source = f"{tenant} — {filename}" if tenant else filename
        rows.append(
            '<li class="risk">\n'
            f'  <div class="risk-head"><span class="badge badge-{badge_class}">'
            f"{html.escape(severity.upper())}</span>"
            f'<span class="risk-source">{html.escape(str(source))}</span></div>\n'
            f'  <div class="risk-message">{html.escape(str(flag.get("message") or ""))}</div>\n'
            f'  <div class="risk-explanation">{html.escape(str(flag.get("explanation") or ""))}</div>\n'
            "</li>"
        )

    caption = (
        f'<p class="note">Showing the {len(shown)} most severe of '
        f"{len(flattened)} total flags.</p>"
        if len(flattened) > len(shown)
        else f'<p class="note">{len(flattened)} flag(s) raised.</p>'
    )
    return _section(
        "Top Red Flags",
        f'{caption}\n<ul class="risks">\n' + "\n".join(rows) + "\n</ul>",
    )


def _render_footer() -> str:
    return (
        '<footer class="report-footer">Generated by the lease abstraction tool. '
        "Every figure traces to an extracted field with a page-level source quote "
        "in the application — verify against the source lease before relying on "
        "this summary.</footer>"
    )


def _section(title: str, content: str) -> str:
    return (
        f'<section>\n<h2>{html.escape(title)}</h2>\n{content}\n</section>'
    )


def _format_count(value: Any) -> str:
    try:
        return "{:,}".format(int(value))
    except (TypeError, ValueError):
        return "Not available"


def _format_long_date(value: date) -> str:
    """"August 12, 2026" — %-d/%e are not portable, so the day is formatted manually."""
    return "{} {}, {}".format(value.strftime("%B"), value.day, value.year)


_STYLES = """
* { box-sizing: border-box; }
body {
  margin: 0 auto;
  padding: 32px 28px 40px;
  max-width: 8.5in;
  background: #ffffff;
  color: #161512;
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 12px;
  line-height: 1.45;
}
h1 { font-size: 22px; margin: 0 0 2px; letter-spacing: -0.01em; }
h2 {
  font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em;
  margin: 22px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #e6e0d2;
  color: #58554d;
}
h3 { font-size: 12px; margin: 0 0 6px; color: #58554d; }
.report-header { border-bottom: 2px solid #161512; padding-bottom: 10px; }
.portfolio-name { margin: 0; font-size: 14px; font-weight: 600; color: #58554d; }
.generated { margin: 2px 0 0; font-size: 11px; color: #8b8779; }
section { page-break-inside: avoid; }
.tiles { display: flex; flex-wrap: wrap; gap: 8px; }
.tile {
  flex: 1 1 130px; border: 1px solid #e6e0d2; border-radius: 4px;
  padding: 8px 10px; display: flex; flex-direction: column; gap: 2px;
}
.tile-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: #8b8779; }
.tile-value { font-size: 15px; font-weight: 600; }
table.data { width: 100%; border-collapse: collapse; margin: 0 0 4px; }
table.data th, table.data td {
  text-align: left; padding: 4px 6px; border-bottom: 1px solid #efeade;
  vertical-align: top;
}
table.data th { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: #8b8779; }
table.data td.num, table.data th.num { text-align: right; white-space: nowrap; }
td.filename { color: #58554d; word-break: break-word; }
.bucket { margin-bottom: 12px; padding-left: 10px; border-left: 3px solid #e6e0d2; }
.bucket-urgent { border-left-color: #9a3b3b; }
.bucket-urgent h3 { color: #9a3b3b; font-weight: 700; }
.bucket-soon { border-left-color: #a6741f; }
.bucket-later { border-left-color: #b3ada0; }
.bucket-count {
  display: inline-block; min-width: 18px; padding: 0 5px; margin-left: 4px;
  border-radius: 9px; background: #efeade; color: #58554d;
  font-size: 10px; font-weight: 700; text-align: center;
}
.bucket-urgent .bucket-count { background: #f3e3e1; color: #9a3b3b; }
ul.risks { list-style: none; margin: 0; padding: 0; }
li.risk { padding: 6px 0; border-bottom: 1px solid #efeade; page-break-inside: avoid; }
.risk-head { display: flex; align-items: center; gap: 6px; }
.risk-source { font-weight: 600; }
.risk-message { margin-top: 2px; }
.risk-explanation { color: #6f6c62; font-size: 11px; margin-top: 1px; }
.badge {
  display: inline-block; padding: 1px 6px; border-radius: 3px;
  font-size: 9px; font-weight: 700; letter-spacing: 0.06em;
  border: 1px solid currentColor;
}
.badge-high { color: #9a3b3b; background: #f3e3e1; }
.badge-medium { color: #a6741f; background: #f3e7d2; }
.badge-low { color: #6f6c62; background: #efeade; }
.empty { color: #8b8779; font-style: italic; margin: 4px 0; }
.note { color: #8b8779; font-size: 11px; margin: 4px 0; }
.report-footer {
  margin-top: 24px; padding-top: 8px; border-top: 1px solid #e6e0d2;
  font-size: 10px; color: #8b8779;
}
@media print {
  body { padding: 0; max-width: none; font-size: 11px; }
  h2 { margin-top: 16px; }
  .tile { break-inside: avoid; }
}
@page { margin: 0.6in; }
"""
