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


if __name__ == "__main__":
    test_field_split_across_page_boundary_is_found()
