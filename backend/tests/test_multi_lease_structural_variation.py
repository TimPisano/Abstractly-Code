"""
Multi-lease splitting, stress-tested against structural variation —
not just the single kind of merged document this project's other
multi-lease tests build (one page per lease, parties defined in the
first paragraph, consistent formatting throughout).

Written during the pre-sale audit specifically because "the splitting
logic has been tested against real variation, not just one sample PDF"
was named as something to confirm, not assume. Three genuinely
different document shapes:

  - test_multi_lease_with_each_lease_spanning_multiple_pages:
    each of 3 leases in the merged document is itself 2 pages, not 1
    — boundary detection has to place the split at the right page
    even though "one lease" no longer means "one page."
  - test_multi_lease_with_reversed_clause_order:
    financial terms and the lease term come BEFORE the parties are
    named, not after (a plausible real-world variation — not every
    lease opens with "by and between X and Y"). Boundary detection
    depends on finding the parties, so this checks it still finds them
    when they're not the first thing on the page.
  - test_multi_lease_with_different_terminology_and_article_headers:
    "Lessor"/"Lessee" instead of "Landlord"/"Tenant", numbered
    "ARTICLE" headers instead of plain prose, different phrasing
    throughout — exercises the alternate-terminology patterns
    field_extractor.py already supports, at the multi-lease boundary
    level specifically (not just single-document extraction, which
    create_synthetic_leases.py's fixtures already cover).

Each document is built directly with one reportlab canvas and explicit
showPage() calls between leases — not by merging separately-generated
PDFs with PyPDF2, which a prior session found could silently duplicate
or lose page content when temp files were reused across a loop (see
DECISIONS.md). Generating directly avoids that failure mode entirely.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor


def _draw_page(c, lines):
    width, height = letter
    c.setFont("Helvetica", 10.5)
    y = height - 1 * inch
    for line in lines:
        c.drawString(1 * inch, y, line)
        y -= 0.22 * inch
    c.showPage()


def _make_multipage_lease_pdf(path):
    """3 leases, each spanning 2 pages (parties defined on each lease's
    own first page; page 2 of each carries the rest of the terms)."""
    c = canvas.Canvas(path, pagesize=letter)

    leases = [
        ("Northgate Fitness LLC", "Summit Retail Partners", "$5,200.00", "1800 sq ft"),
        ("Blue Harbor Consulting", "Coastal Property Group", "$3,900.00", "1200 sq ft"),
        ("Redline Auto Parts, Inc.", "Meridian Industrial LP", "$7,600.00", "3400 sq ft"),
    ]
    for tenant, landlord, rent, sqft in leases:
        _draw_page(c, [
            "COMMERCIAL LEASE AGREEMENT",
            f'This Lease is entered into by and between {landlord} ("Landlord")',
            f'and {tenant} ("Tenant").',
            "PREMISES: See Exhibit A for a full description of the premises.",
        ])
        _draw_page(c, [
            f"TERM: Lease Start Date: January 1, 2025. Lease End Date: December 31, 2029.",
            f"RENT: Monthly Rent: {rent}.",
            f"The premises consist of approximately {sqft}.",
        ])
    c.save()
    return leases


def _make_reversed_clause_order_pdf(path):
    """2 leases where financial terms and the lease term come BEFORE
    the parties are named, not after."""
    c = canvas.Canvas(path, pagesize=letter)

    leases = [
        ("Ironwood Design Studio", "Parkside Commercial Trust", "$4,450.00"),
        ("Golden Valley Imports", "Bayline Property Holdings", "$6,100.00"),
    ]
    for tenant, landlord, rent in leases:
        _draw_page(c, [
            "COMMERCIAL LEASE AGREEMENT",
            f"RENT: Monthly Rent: {rent}.",
            "TERM: Lease Start Date: March 1, 2024. Lease End Date: February 28, 2029.",
            "PREMISES: The leased premises are described in Exhibit A attached hereto.",
            f'This Lease is entered into by and between {landlord} ("Landlord")',
            f'and {tenant} ("Tenant"), effective as of the date first written above.',
        ])
    c.save()
    return leases


def _make_alternate_terminology_pdf(path):
    """2 leases using Lessor/Lessee terminology and numbered ARTICLE
    headers instead of Landlord/Tenant and plain prose."""
    c = canvas.Canvas(path, pagesize=letter)

    leases = [
        ("Cascade Outdoor Supply Co.", "Highland Estates Group", "$8,300.00"),
        ("Pinehill Veterinary Clinic", "Roseview Holdings LLC", "$5,750.00"),
    ]
    for tenant, landlord, rent in leases:
        _draw_page(c, [
            "COMMERCIAL LEASE",
            "ARTICLE 1: PARTIES",
            f'This Lease is made by and between {landlord} ("Lessor") and',
            f'{tenant} ("Lessee").',
            "ARTICLE 2: TERM",
            "Lease Start Date: June 1, 2025. Lease End Date: May 31, 2030.",
            "ARTICLE 3: RENT",
            f"Monthly Rent: {rent}.",
        ])
    c.save()
    return leases


def test_multi_lease_with_each_lease_spanning_multiple_pages():
    path = os.path.join(os.path.dirname(__file__), "_structural_multipage.pdf")
    ground_truth = _make_multipage_lease_pdf(path)
    try:
        pdf_extractor = PDFExtractor()
        with open(path, "rb") as f:
            pages = pdf_extractor.extract_text(f, pdf_path=path)
        assert len(pages) == 6, f"expected 6 pages (3 leases x 2 pages), got {len(pages)}"

        field_extractor = FieldExtractor()
        boundaries = field_extractor.detect_lease_boundaries(pages)
        assert boundaries == [(1, 2), (3, 4), (5, 6)], \
            f"each 2-page lease should be its own range, got {boundaries}"

        leases = field_extractor.extract_multiple_leases(pages)
        assert len(leases) == 3, f"expected 3 leases, got {len(leases)}"
        for lease, (tenant, landlord, rent, sqft) in zip(leases, ground_truth):
            fields = lease["fields"]
            assert fields["tenant"]["value"] == tenant, (fields["tenant"], tenant)
            assert fields["landlord"]["value"] == landlord, (fields["landlord"], landlord)
            assert fields["rent_amount"]["value"] == rent, (fields["rent_amount"], rent)
            assert sqft.split()[0] in (fields["square_footage"]["value"] or ""), fields["square_footage"]
        print("✓ test_multi_lease_with_each_lease_spanning_multiple_pages: PASS")
    finally:
        os.remove(path)


def test_multi_lease_with_reversed_clause_order():
    path = os.path.join(os.path.dirname(__file__), "_structural_reversed_order.pdf")
    ground_truth = _make_reversed_clause_order_pdf(path)
    try:
        pdf_extractor = PDFExtractor()
        with open(path, "rb") as f:
            pages = pdf_extractor.extract_text(f, pdf_path=path)
        assert len(pages) == 2, f"expected 2 pages, got {len(pages)}"

        field_extractor = FieldExtractor()
        boundaries = field_extractor.detect_lease_boundaries(pages)
        assert boundaries == [(1, 1), (2, 2)], f"expected one lease per page, got {boundaries}"

        leases = field_extractor.extract_multiple_leases(pages)
        assert len(leases) == 2, f"expected 2 leases, got {len(leases)}"
        for lease, (tenant, landlord, rent) in zip(leases, ground_truth):
            fields = lease["fields"]
            assert fields["tenant"]["value"] == tenant, (fields["tenant"], tenant)
            assert fields["landlord"]["value"] == landlord, (fields["landlord"], landlord)
            assert fields["rent_amount"]["value"] == rent, (fields["rent_amount"], rent)
        print("✓ test_multi_lease_with_reversed_clause_order: PASS")
    finally:
        os.remove(path)


def test_multi_lease_with_different_terminology_and_article_headers():
    path = os.path.join(os.path.dirname(__file__), "_structural_alt_terminology.pdf")
    ground_truth = _make_alternate_terminology_pdf(path)
    try:
        pdf_extractor = PDFExtractor()
        with open(path, "rb") as f:
            pages = pdf_extractor.extract_text(f, pdf_path=path)
        assert len(pages) == 2, f"expected 2 pages, got {len(pages)}"

        field_extractor = FieldExtractor()
        boundaries = field_extractor.detect_lease_boundaries(pages)
        assert boundaries == [(1, 1), (2, 2)], f"expected one lease per page, got {boundaries}"

        leases = field_extractor.extract_multiple_leases(pages)
        assert len(leases) == 2, f"expected 2 leases, got {len(leases)}"
        for lease, (tenant, landlord, rent) in zip(leases, ground_truth):
            fields = lease["fields"]
            assert fields["tenant"]["value"] == tenant, (fields["tenant"], tenant)
            assert fields["landlord"]["value"] == landlord, (fields["landlord"], landlord)
            assert fields["rent_amount"]["value"] == rent, (fields["rent_amount"], rent)
        print("✓ test_multi_lease_with_different_terminology_and_article_headers: PASS")
    finally:
        os.remove(path)


if __name__ == "__main__":
    test_multi_lease_with_each_lease_spanning_multiple_pages()
    test_multi_lease_with_reversed_clause_order()
    test_multi_lease_with_different_terminology_and_article_headers()
    print("\nAll structural-variation multi-lease tests passed.")
