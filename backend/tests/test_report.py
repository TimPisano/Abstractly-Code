"""
Tests for the printable portfolio summary report.

The report is rendered from hand-built metrics/timeline/risk fixtures matching
the shapes portfolio.py and risk_analysis.py produce, so these assertions test
this module's rendering rather than those modules' math.

Assertions focus on what actually goes wrong with a report nobody can
interact with: a figure silently missing from the page, a lease absent from
the summary, a "None" or empty section where a finding should be, an external
asset reference that breaks once the file is emailed, and unescaped extracted
text (which is attacker-influenced — it comes out of an uploaded PDF).
"""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.report import generate_portfolio_report_html


def _field(value):
    if value is None:
        return {"value": None, "source": None, "confidence": None}
    return {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}


def _lease(lease_id, filename, **field_values):
    field_names = [
        "tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date",
        "property_address", "security_deposit", "cam_charges", "rent_escalation",
        "renewal_options", "permitted_use", "exclusivity_clause",
        "insurance_requirements", "default_cure_period", "square_footage",
    ]
    return {
        "id": lease_id,
        "filename": filename,
        "uploaded_at": "2026-08-01T10:00:00Z",
        "document_type": "lease",
        "base_lease_id": None,
        "amendment_count": 0,
        "extracted_fields": {name: _field(field_values.get(name)) for name in field_names},
    }


def make_leases():
    return [
        _lease(1, "blue_sky_coffee.pdf", tenant="Blue Sky Coffee Roasters, Inc.",
               rent_amount="$6,250.00", lease_start_date="April 1, 2025",
               lease_end_date="March 31, 2028", square_footage="2,400 sq ft"),
        _lease(2, "northgate_dental.pdf", tenant="Northgate Dental Group, P.C.",
               rent_amount="$4,100.00", lease_start_date="June 1, 2024",
               lease_end_date="November 30, 2026"),
        _lease(3, "vertex_consulting.pdf", tenant="Vertex Consulting LLC",
               rent_amount="$3,000.00"),
        _lease(4, "anchor_hardware.pdf", tenant="Anchor Hardware Supply Co.",
               rent_amount="$9,800.00", lease_end_date="January 5, 2027",
               square_footage="7,000 sq ft"),
    ]


def make_metrics():
    return {
        "lease_count": 4,
        "total_monthly_rent": 23150.0,
        "avg_monthly_rent": 5787.5,
        "avg_rent_per_sqft": 2.0,
        "total_cam_exposure": 1750.0,
        "avg_cam": 875.0,
        "avg_security_deposit": 16050.0,
        "avg_escalation_pct": 3.0,
        "avg_notice_days": 180.0,
        "total_square_footage": 9400.0,
        "fields_missing_count": {"cam_charges": 2, "square_footage": 2},
    }


def make_timeline():
    return {
        "expiring_0_6_months": [
            {"lease_id": 2, "filename": "northgate_dental.pdf",
             "tenant": "Northgate Dental Group, P.C.",
             "lease_end_date": "November 30, 2026", "months_remaining": 3.6},
        ],
        "expiring_6_12_months": [
            {"lease_id": 4, "filename": "anchor_hardware.pdf",
             "tenant": "Anchor Hardware Supply Co.",
             "lease_end_date": "January 5, 2027", "months_remaining": 4.8},
        ],
        "expiring_12_24_months": [],
        "expiring_24_plus_months": [
            {"lease_id": 1, "filename": "blue_sky_coffee.pdf",
             "tenant": "Blue Sky Coffee Roasters, Inc.",
             "lease_end_date": "March 31, 2028", "months_remaining": 19.6},
        ],
        "already_expired": [],
        "unknown_expiration": [
            {"lease_id": 3, "filename": "vertex_consulting.pdf",
             "tenant": "Vertex Consulting LLC",
             "lease_end_date": None, "months_remaining": 0.0},
        ],
    }


def make_risks():
    return [
        {"lease_id": 3, "filename": "vertex_consulting.pdf", "tenant": "Vertex Consulting LLC",
         "flags": [
             {"severity": "high", "category": "missing_clause", "field": "lease_end_date",
              "message": "No lease end date found",
              "explanation": "Without an end date the lease term cannot be verified or tracked for expiration."},
             {"severity": "low", "category": "missing_clause", "field": "cam_charges",
              "message": "No CAM charges found",
              "explanation": "CAM may genuinely not apply, but confirm against the source lease."},
         ]},
        {"lease_id": 2, "filename": "northgate_dental.pdf", "tenant": "Northgate Dental Group, P.C.",
         "flags": [
             {"severity": "medium", "category": "below_market", "field": "rent_amount",
              "message": "Rent is 29% below the portfolio average",
              "explanation": "Monthly rent of $4,100.00 vs a portfolio average of $5,787.50."},
         ]},
        {"lease_id": 1, "filename": "blue_sky_coffee.pdf", "tenant": "Blue Sky Coffee Roasters, Inc.",
         "flags": []},
    ]


def _render_default():
    return generate_portfolio_report_html(
        make_leases(), make_metrics(), make_timeline(), make_risks()
    )


def test_report_is_self_contained_html():
    html_text = _render_default()

    assert html_text.startswith("<!DOCTYPE html>")
    assert "<style>" in html_text and "</html>" in html_text.strip()
    # No external asset can be referenced: the file has to render offline.
    for pattern in ("<link", "<script", "<img", "http://", "https://", "@import", "url("):
        assert pattern not in html_text, f"report references external asset: {pattern}"
    print("✓ test_report_is_self_contained_html: PASS")


def test_report_contains_summary_figures():
    html_text = _render_default()

    assert "$23,150.00" in html_text, "total monthly rent missing from report"
    assert "$5,787.50" in html_text, "average monthly rent missing from report"
    assert "$1,750.00" in html_text, "total CAM exposure missing from report"
    assert "9,400 sq ft" in html_text, "total square footage missing from report"
    assert ">4<" in html_text.replace(" ", ""), "lease count missing from report"
    assert "Portfolio Summary Report" in html_text
    print("✓ test_report_contains_summary_figures: PASS")


def test_report_lists_every_lease():
    html_text = _render_default()
    for lease in make_leases():
        assert lease["filename"] in html_text, f"{lease['filename']} missing from report"
        assert lease["extracted_fields"]["tenant"]["value"] in html_text
    print("✓ test_report_lists_every_lease: PASS")


def test_report_expiration_timeline_and_urgency():
    html_text = _render_default()

    assert "Expiring within 6 months" in html_text
    assert "Expiring in 6-12 months" in html_text
    assert "Expiring in 12-24 months" in html_text
    # The urgent bucket must be visually distinguished, not just listed.
    assert "bucket-urgent" in html_text
    urgent_block = html_text.split("Expiring within 6 months")[1].split("Expiring in 6-12")[0]
    assert "northgate_dental.pdf" in urgent_block, "0-6mo lease not in the urgent bucket"
    assert "November 30, 2026" in urgent_block
    # The empty 12-24 bucket says "None.", it doesn't just disappear.
    later_block = html_text.split("Expiring in 12-24 months")[1].split("</section>")[0]
    assert "None." in later_block
    # Unknown-expiration leases are surfaced rather than silently dropped.
    assert "no usable end date" in html_text
    print("✓ test_report_expiration_timeline_and_urgency: PASS")


def test_report_shows_risks_sorted_by_severity():
    html_text = _render_default()

    assert "No lease end date found" in html_text
    assert "Rent is 29% below the portfolio average" in html_text
    assert "No CAM charges found" in html_text
    # Explanations, not just messages — the reader can't click for detail.
    assert "cannot be verified or tracked for expiration" in html_text
    assert "badge-high" in html_text and "badge-medium" in html_text and "badge-low" in html_text

    severities = re.findall(r"badge badge-(high|medium|low)", html_text)
    assert severities == ["high", "medium", "low"], f"risks not severity-sorted: {severities}"
    print("✓ test_report_shows_risks_sorted_by_severity: PASS")


def test_report_caps_risk_list_and_says_so():
    """20 flags in, top 15 shown, and the reader is told the rest exist."""
    many = [{
        "lease_id": 1, "filename": "blue_sky_coffee.pdf", "tenant": "Blue Sky Coffee Roasters, Inc.",
        "flags": [
            {"severity": "low", "category": "test", "field": None,
             "message": f"Synthetic flag {i}", "explanation": "explanation"}
            for i in range(20)
        ],
    }]
    html_text = generate_portfolio_report_html(
        make_leases(), make_metrics(), make_timeline(), many
    )

    assert html_text.count("Synthetic flag") == 15, "risk list should be capped at 15"
    assert "Showing the 15 most severe of 20 total flags." in html_text
    print("✓ test_report_caps_risk_list_and_says_so: PASS")


def test_report_handles_empty_portfolio():
    html_text = generate_portfolio_report_html([], {}, {}, [])

    assert html_text.startswith("<!DOCTYPE html>")
    assert "No leases in this portfolio yet" in html_text
    assert "No risk flags were raised" in html_text
    # Timeline buckets still render with an explicit "None." rather than blank.
    assert html_text.count("None.") == 3
    assert "Portfolio Summary Report" in html_text
    print("✓ test_report_handles_empty_portfolio: PASS")


def test_report_handles_no_risks_and_no_upcoming_expirations():
    empty_timeline = {
        "expiring_0_6_months": [], "expiring_6_12_months": [], "expiring_12_24_months": [],
        "expiring_24_plus_months": [], "already_expired": [], "unknown_expiration": [],
    }
    html_text = generate_portfolio_report_html(
        make_leases(), make_metrics(), empty_timeline, []
    )

    assert "No risk flags were raised across this portfolio." in html_text
    assert html_text.count("None.") == 3, "each empty expiration bucket needs its own message"
    # The leases themselves are still listed even with nothing expiring.
    assert "blue_sky_coffee.pdf" in html_text
    print("✓ test_report_handles_no_risks_and_no_upcoming_expirations: PASS")


def test_report_handles_missing_metric_values():
    """A metric that couldn't be computed says so instead of printing $0.00."""
    sparse_metrics = {
        "lease_count": 2, "total_monthly_rent": None, "avg_monthly_rent": None,
        "total_cam_exposure": None, "total_square_footage": None,
    }
    html_text = generate_portfolio_report_html(
        make_leases()[:2], sparse_metrics, make_timeline(), []
    )

    assert "$0.00" not in html_text, "an uncomputable metric must not render as zero"
    assert html_text.count("Not available") >= 4
    print("✓ test_report_handles_missing_metric_values: PASS")


def test_report_escapes_extracted_text():
    """
    Extracted values originate in an uploaded PDF, so they are untrusted input
    to this template even though the report is 'just' an internal document.
    """
    lease = _lease(9, "weird<name>.pdf", tenant='Acme & Sons <script>alert(1)</script>',
                   rent_amount="$1,000.00")
    risks = [{"lease_id": 9, "filename": "weird<name>.pdf", "tenant": "Acme & Sons",
              "flags": [{"severity": "high", "category": "x", "field": None,
                         "message": "Odd clause <b>here</b>", "explanation": "5 > 3 & unusual"}]}]
    html_text = generate_portfolio_report_html([lease], make_metrics(), {}, risks)

    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
    assert "Acme &amp; Sons" in html_text
    assert "Odd clause &lt;b&gt;here&lt;/b&gt;" in html_text
    assert "5 &gt; 3 &amp; unusual" in html_text
    print("✓ test_report_escapes_extracted_text: PASS")


def test_report_has_print_rules():
    html_text = _render_default()
    assert "@media print" in html_text
    assert "@page" in html_text
    assert "page-break-inside: avoid" in html_text
    print("✓ test_report_has_print_rules: PASS")


if __name__ == "__main__":
    test_report_is_self_contained_html()
    test_report_contains_summary_figures()
    test_report_lists_every_lease()
    test_report_expiration_timeline_and_urgency()
    test_report_shows_risks_sorted_by_severity()
    test_report_caps_risk_list_and_says_so()
    test_report_handles_empty_portfolio()
    test_report_handles_no_risks_and_no_upcoming_expirations()
    test_report_handles_missing_metric_values()
    test_report_escapes_extracted_text()
    test_report_has_print_rules()
    print("\nAll portfolio report tests passed.")
