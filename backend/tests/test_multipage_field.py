"""
Tests that a field whose keyword and value are split across a PDF page
break is still extracted correctly, and that its reported source page
number is sensible.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor


def _make_split_field_pdf(path):
    """
    Page 1 ends right after the "Base Rent:" label with nothing else on
    the page; page 2 opens with the dollar amount. A page-by-page search
    would never see "Base Rent:" and "$4,500.00" in the same string.
    """
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica", 12)
    c.drawString(1 * inch, height - 1 * inch, "LEASE AGREEMENT")
    c.drawString(1 * inch, height - 1.5 * inch, "This Lease Agreement sets forth the terms and conditions")
    c.drawString(1 * inch, height - 1.75 * inch, "under which the Premises are leased to Tenant by Landlord.")
    c.drawString(1 * inch, height - 2.25 * inch, "3. RENT.")
    c.drawString(1 * inch, height - 2.5 * inch, "Base Rent:")
    c.showPage()

    c.setFont("Helvetica", 12)
    c.drawString(1 * inch, height - 1 * inch, "$4,500.00 per month, payable in advance on the first")
    c.drawString(1 * inch, height - 1.25 * inch, "day of each calendar month during the term of this Lease.")
    c.showPage()
    c.save()


def test_field_split_across_page_boundary_is_found():
    path = os.path.join(os.path.dirname(__file__), "_split_field_test.pdf")
    _make_split_field_pdf(path)

    try:
        pdf_extractor = PDFExtractor()
        with open(path, "rb") as f:
            pages = pdf_extractor.extract_text(f, pdf_path=path)

        assert len(pages) == 2, f"expected 2 pages, got {len(pages)}"

        fields = FieldExtractor().extract_fields(pages)
        rent = fields["rent_amount"]

        assert rent["value"] == "$4,500.00", f"expected rent to be found across the page break, got {rent}"
        assert rent["source"]["page"] in (1, 2), f"unexpected source page: {rent['source']}"
        print(f"✓ test_field_split_across_page_boundary_is_found: PASS (value={rent['value']!r}, page={rent['source']['page']})")
    finally:
        os.remove(path)


def _make_large_single_lease_pdf(path, exhibit_pages=34):
    """
    A ~35-page single lease: real terms on page 1, followed by many
    pages of realistic exhibit/boilerplate text, each forced onto its
    own page via an explicit showPage() (not relying on natural text
    wrap to reach that many pages). Exercises two things a single small
    fixture can't: that extraction doesn't degrade or time out on a
    much longer real-world-sized document, and that
    detect_lease_boundaries() doesn't mistake a document that's merely
    long (lots of repeated boilerplate-ish text) for a multi-lease
    file and incorrectly split it.

    This is the permanent version of a scale check that was previously
    only ever run from an ad-hoc scratch script during a prior session
    — found during the pre-sale test-coverage audit that "a large PDF
    works" had been verified by hand but never locked in as a real,
    re-runnable regression test.
    """
    width, height = letter
    c = canvas.Canvas(path, pagesize=letter)

    c.setFont("Helvetica", 10.5)
    y = height - 1 * inch
    for line in [
        "COMMERCIAL LEASE AGREEMENT",
        "This Lease Agreement is entered into by and between Ashford Properties LLC",
        '("Landlord") and Fairwind Aviation Services ("Tenant").',
        "PREMISES: The Landlord leases to Tenant the premises located at 500 Aviation",
        "Way, Suite 210, Denver, CO, consisting of approximately 3,200 square feet.",
        "TERM: Lease Start Date: April 1, 2024. Lease End Date: March 31, 2031.",
        "RENT: Monthly Rent: $8,250.00.",
    ]:
        c.drawString(1 * inch, y, line)
        y -= 0.22 * inch
    c.showPage()

    for i in range(exhibit_pages):
        c.setFont("Helvetica", 10.5)
        y = height - 1 * inch
        c.drawString(1 * inch, y, f"EXHIBIT {i + 1} - RULES AND REGULATIONS")
        y -= 0.3 * inch
        c.drawString(1 * inch, y, "Tenant and Tenant's agents, employees, and invitees shall comply with all")
        y -= 0.22 * inch
        c.drawString(1 * inch, y, "rules and regulations as may be amended from time to time by Landlord.")
        c.showPage()

    c.save()


def test_large_document_extracts_correctly_and_stays_one_lease():
    path = os.path.join(os.path.dirname(__file__), "_large_document_test.pdf")
    _make_large_single_lease_pdf(path)

    try:
        pdf_extractor = PDFExtractor()
        with open(path, "rb") as f:
            pages = pdf_extractor.extract_text(f, pdf_path=path)

        assert len(pages) == 35, f"expected 35 pages, got {len(pages)}"

        field_extractor = FieldExtractor()
        fields = field_extractor.extract_fields(pages)

        assert fields["tenant"]["value"] == "Fairwind Aviation Services", fields["tenant"]
        assert fields["landlord"]["value"] == "Ashford Properties LLC", fields["landlord"]
        assert fields["rent_amount"]["value"] == "$8,250.00", fields["rent_amount"]
        assert fields["square_footage"]["value"] == "3,200 sq ft" or "3,200" in (fields["square_footage"]["value"] or ""), fields["square_footage"]
        assert fields["tenant"]["source"]["page"] == 1, fields["tenant"]["source"]

        boundaries = field_extractor.detect_lease_boundaries(pages)
        assert boundaries == [(1, 35)], \
            f"a long single-lease document with lots of boilerplate must stay one lease, not split — got {boundaries}"

        print(f"✓ test_large_document_extracts_correctly_and_stays_one_lease: PASS (35 pages, boundaries={boundaries})")
    finally:
        os.remove(path)


if __name__ == "__main__":
    test_field_split_across_page_boundary_is_found()
    test_large_document_extracts_correctly_and_stays_one_lease()
