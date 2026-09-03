"""
Tests for the decision-ready PDF summary memo (summary_memo.py) --
the "add a new export option... pull from data already extracted"
output format built on top of field_extractor/risk_analysis/
portfolio.py's existing data, not a reimplementation of any of them.

Fixtures build lease field dicts directly (same convention
test_risk_analysis.py and test_rent_roll_export.py already use) rather
than going through a real PDF upload -- the point here is whether the
memo *layout* correctly reflects given data, which a real extraction
run can only exercise incidentally.

Content is verified by extracting the generated PDF's own text back
out via PyPDF2 (already a project dependency) rather than just
checking "it produced some bytes" -- a memo whose layout silently
dropped the tenant name or a risk flag would still "successfully"
produce a well-formed PDF file.
"""

import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pypdf

from app.portfolio import FIELD_NAMES, compute_lease_confidence_summary, compute_portfolio_confidence_summary
from app.summary_memo import (
    generate_lease_summary_pdf, generate_portfolio_summary_pdf,
    monthly_report_extra_sections, _MAX_RISKS_SHOWN,
)


def _field(value, page=1, confidence="high"):
    if value is None:
        return {"value": None, "source": None, "confidence": None}
    return {"value": value, "source": {"page": page, "quote": f"...{value}..."}, "confidence": confidence}


def _lease(lease_id, filename, **field_values):
    return {
        "id": lease_id,
        "filename": filename,
        "display_name": field_values.pop("display_name", None),
        "uploaded_at": "2026-08-01T10:00:00Z",
        "document_type": "lease",
        "base_lease_id": None,
        "amendment_count": 0,
        "extracted_fields": {name: _field(field_values.get(name)) for name in FIELD_NAMES},
    }


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


FULL_LEASE = _lease(
    1, "blue_sky.pdf",
    display_name="Blue Sky Coffee Roasters, Inc. - 4200 Commerce Pkwy",
    tenant="Blue Sky Coffee Roasters, Inc.",
    landlord="Meridian Properties Group, LLC",
    property_address="4200 Commerce Parkway, Suite 110, Austin, Texas 78701",
    rent_amount="$6,250.00",
    lease_start_date="April 1, 2025",
    lease_end_date="March 31, 2030",
    square_footage="2,400 sq ft",
    security_deposit="$12,500.00",
    cam_charges="$875.00",
    rent_escalation="3% annually",
    renewal_options="2 option(s) of 5 year(s) each",
)

RISK_FLAGS = [
    {"severity": "high", "category": "below_market_rent", "field": "rent_amount",
     "message": "Rent ($4.34/sq ft/mo) is 30% below the portfolio average ($6.20/sq ft/mo)", "explanation": "x"},
    {"severity": "medium", "category": "missing_clause", "field": "insurance_requirements",
     "message": "No insurance requirements clause found in this lease", "explanation": "x"},
]


def test_lease_memo_is_a_real_single_page_pdf():
    pdf_bytes = generate_lease_summary_pdf(FULL_LEASE, RISK_FLAGS)
    assert pdf_bytes[:4] == b"%PDF", "must be a real PDF, not just bytes"
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1, f"a normal lease's memo should fit on one page, got {len(reader.pages)}"
    print("✓ test_lease_memo_is_a_real_single_page_pdf: PASS")


def test_lease_memo_contains_key_terms():
    text = _pdf_text(generate_lease_summary_pdf(FULL_LEASE, RISK_FLAGS))
    assert "Blue Sky Coffee Roasters, Inc." in text
    assert "Meridian Properties Group, LLC" in text
    assert "4200 Commerce Parkway" in text
    assert "$6,250.00" in text
    assert "April 1, 2025" in text
    assert "March 31, 2030" in text
    assert "2,400 sq ft" in text
    print("✓ test_lease_memo_contains_key_terms: PASS")


def test_lease_memo_contains_risk_flags():
    text = _pdf_text(generate_lease_summary_pdf(FULL_LEASE, RISK_FLAGS))
    assert "HIGH" in text
    assert "30% below the portfolio average" in text
    assert "MEDIUM" in text
    assert "No insurance requirements clause found" in text
    print("✓ test_lease_memo_contains_risk_flags: PASS")


def test_lease_memo_with_no_risks_says_so_explicitly():
    text = _pdf_text(generate_lease_summary_pdf(FULL_LEASE, []))
    assert "No risk flags on this lease." in text
    print("✓ test_lease_memo_with_no_risks_says_so_explicitly: PASS")


def test_lease_memo_contains_confidence_summary_matching_computed_values():
    summary = compute_lease_confidence_summary(FULL_LEASE)
    text = _pdf_text(generate_lease_summary_pdf(FULL_LEASE, []))
    assert f"{summary['high']} of {summary['total_fields']}" in text
    print("✓ test_lease_memo_contains_confidence_summary_matching_computed_values: PASS")


def test_lease_memo_truncates_long_risk_list_with_a_count():
    many_flags = [
        {"severity": "low", "category": "x", "field": "x", "message": f"Finding number {i}", "explanation": "x"}
        for i in range(_MAX_RISKS_SHOWN + 3)
    ]
    text = _pdf_text(generate_lease_summary_pdf(FULL_LEASE, many_flags))
    assert "Finding number 0" in text, "the first (shown) finding must be present"
    assert f"...and 3 more" in text
    assert f"Finding number {_MAX_RISKS_SHOWN}" not in text, "a finding past the cap must not be listed"
    print("✓ test_lease_memo_truncates_long_risk_list_with_a_count: PASS")


def test_lease_memo_missing_fields_render_as_not_found_not_blank():
    sparse = _lease(2, "sparse.pdf", tenant="Sparse Tenant LLC")
    text = _pdf_text(generate_lease_summary_pdf(sparse, []))
    assert "Not found" in text
    print("✓ test_lease_memo_missing_fields_render_as_not_found_not_blank: PASS")


PORTFOLIO_LEASES = [
    FULL_LEASE,
    _lease(2, "vertex.pdf", display_name="Vertex Analytics LLC", tenant="Vertex Analytics LLC",
           rent_amount="$9,500.00", square_footage="6,200 sq ft", lease_end_date="December 31, 2035"),
]

PORTFOLIO_RISKS_BY_LEASE = {1: RISK_FLAGS, 2: []}


def test_portfolio_memo_is_a_real_pdf_and_lists_every_lease():
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    pdf_bytes = generate_portfolio_summary_pdf(PORTFOLIO_LEASES, summary, PORTFOLIO_RISKS_BY_LEASE)
    assert pdf_bytes[:4] == b"%PDF"
    text = _pdf_text(pdf_bytes)
    assert "Blue Sky Coffee Roasters, Inc." in text
    assert "Vertex Analytics LLC" in text
    assert "2 leases in this portfolio" in text
    print("✓ test_portfolio_memo_is_a_real_pdf_and_lists_every_lease: PASS")


def test_portfolio_memo_risk_flags_name_which_lease():
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    text = _pdf_text(generate_portfolio_summary_pdf(PORTFOLIO_LEASES, summary, PORTFOLIO_RISKS_BY_LEASE))
    assert "Blue Sky Coffee Roasters, Inc." in text and "30% below the portfolio average" in text
    print("✓ test_portfolio_memo_risk_flags_name_which_lease: PASS")


def test_portfolio_memo_confidence_summary_matches_computed_totals():
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    text = _pdf_text(generate_portfolio_summary_pdf(PORTFOLIO_LEASES, summary, PORTFOLIO_RISKS_BY_LEASE))
    assert f"{summary['high']} of {summary['total_fields']}" in text
    print("✓ test_portfolio_memo_confidence_summary_matches_computed_totals: PASS")


def test_portfolio_memo_empty_portfolio_does_not_crash():
    summary = compute_portfolio_confidence_summary([])
    pdf_bytes = generate_portfolio_summary_pdf([], summary, {})
    assert pdf_bytes[:4] == b"%PDF"
    text = _pdf_text(pdf_bytes)
    assert "No leases in this portfolio yet." in text
    assert "No fields to summarize." in text
    print("✓ test_portfolio_memo_empty_portfolio_does_not_crash: PASS")


def test_portfolio_memo_no_risks_anywhere_says_so_explicitly():
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    text = _pdf_text(generate_portfolio_summary_pdf(PORTFOLIO_LEASES, summary, {1: [], 2: []}))
    assert "No risk flags across the portfolio." in text
    print("✓ test_portfolio_memo_no_risks_anywhere_says_so_explicitly: PASS")


def test_portfolio_memo_extra_sections_are_appended():
    """The monthly-report route reuses this function's header/footer/build machinery via extra_sections -- confirm a caller-supplied flowable actually lands in the output."""
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    marker_style = ParagraphStyle("Marker", fontName="Helvetica", fontSize=9)
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    pdf_bytes = generate_portfolio_summary_pdf(
        PORTFOLIO_LEASES, summary, PORTFOLIO_RISKS_BY_LEASE,
        extra_sections=[Paragraph("UNIQUE_MARKER_TEXT_FOR_TEST", marker_style)],
    )
    text = _pdf_text(pdf_bytes)
    assert "UNIQUE_MARKER_TEXT_FOR_TEST" in text
    print("✓ test_portfolio_memo_extra_sections_are_appended: PASS")


def test_monthly_report_title_and_sections_render_correctly():
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    expiring = [{"lease_id": 1, "display_name": "Blue Sky Coffee Roasters, Inc.", "lease_end_date": "March 31, 2030", "days_remaining": 45}]
    outliers = [{"lease_id": 2, "display_name": "Vertex Analytics LLC", "rent_per_sqft": 1.53, "portfolio_avg_rent_per_sqft": 2.49, "diff_pct": -38.6, "direction": "below"}]
    extra = monthly_report_extra_sections(expiring, outliers)

    pdf_bytes = generate_portfolio_summary_pdf(
        PORTFOLIO_LEASES, summary, PORTFOLIO_RISKS_BY_LEASE,
        extra_sections=extra, title="Portfolio Monthly Report",
    )
    text = _pdf_text(pdf_bytes)

    assert "Portfolio Monthly Report" in text
    assert "Upcoming Expirations" in text
    assert "45 days" in text
    assert "Rent Variance Outliers" in text
    assert "39% below the portfolio average" in text, "abs(-38.6) formatted to 0 decimals rounds to 39"
    assert "Loss to Lease" in text
    assert "Not available" in text
    print("✓ test_monthly_report_title_and_sections_render_correctly: PASS")


def test_monthly_report_empty_expirations_and_outliers_say_so_explicitly():
    text_flowables = monthly_report_extra_sections([], [])
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    pdf_bytes = generate_portfolio_summary_pdf(PORTFOLIO_LEASES, summary, PORTFOLIO_RISKS_BY_LEASE, extra_sections=text_flowables)
    text = _pdf_text(pdf_bytes)
    assert "No leases expiring in the next 90 days." in text
    assert "No leases significantly above or below the portfolio's average rent/sqft." in text
    print("✓ test_monthly_report_empty_expirations_and_outliers_say_so_explicitly: PASS")


def test_default_portfolio_memo_title_unchanged_when_not_overridden():
    summary = compute_portfolio_confidence_summary(PORTFOLIO_LEASES)
    text = _pdf_text(generate_portfolio_summary_pdf(PORTFOLIO_LEASES, summary, PORTFOLIO_RISKS_BY_LEASE))
    assert "Portfolio Summary Memo" in text
    print("✓ test_default_portfolio_memo_title_unchanged_when_not_overridden: PASS")


if __name__ == "__main__":
    test_lease_memo_is_a_real_single_page_pdf()
    test_lease_memo_contains_key_terms()
    test_lease_memo_contains_risk_flags()
    test_lease_memo_with_no_risks_says_so_explicitly()
    test_lease_memo_contains_confidence_summary_matching_computed_values()
    test_lease_memo_truncates_long_risk_list_with_a_count()
    test_lease_memo_missing_fields_render_as_not_found_not_blank()
    test_portfolio_memo_is_a_real_pdf_and_lists_every_lease()
    test_portfolio_memo_risk_flags_name_which_lease()
    test_portfolio_memo_confidence_summary_matches_computed_totals()
    test_portfolio_memo_empty_portfolio_does_not_crash()
    test_portfolio_memo_no_risks_anywhere_says_so_explicitly()
    test_portfolio_memo_extra_sections_are_appended()
    test_monthly_report_title_and_sections_render_correctly()
    test_monthly_report_empty_expirations_and_outliers_say_so_explicitly()
    test_default_portfolio_memo_title_unchanged_when_not_overridden()
    print("\nAll summary memo tests passed.")
