"""
Tests for the OCR fallback path in pdf_extractor.py.

This environment has no system tesseract/poppler binaries installed (and
no package manager available to install them), so pytesseract.image_to_data
and pdf2image.convert_from_path are mocked here to verify the *logic*
end-to-end: that the fallback actually triggers when digital text
extraction yields too little text, that its output flows through to field
extraction correctly, and that OCR failure degrades gracefully instead of
raising. This does not substitute for a real end-to-end OCR run against
an actual scanned PDF, which should be done in an environment with
tesseract/poppler installed before relying on this path in production.

_extract_with_ocr calls pytesseract.image_to_data (not image_to_string) so
one OCR pass yields both the recognized text and tesseract's own per-word
confidence -- _fake_image_to_data() below builds a mock return value in
that same {text, conf, block_num, par_num, line_num, ...} DICT shape.
"""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor


def _make_blank_pdf(path):
    """A PDF with no text layer at all, so PyPDF2 extracts ~0 characters."""
    c = canvas.Canvas(path, pagesize=letter)
    c.showPage()
    c.save()


def _fake_image_to_data(text: str, confidence: float = 92.0) -> dict:
    """
    Builds a pytesseract.image_to_data(output_type=Output.DICT)-shaped
    mock: one word per entry, grouped into lines by "\n" in `text`, each
    word tagged with the given confidence (tesseract's real 0-100 scale).
    Good enough to exercise _ocr_page_with_confidence's line-reconstruction
    and mean-confidence math without a real image or tesseract binary.
    """
    data = {"text": [], "conf": [], "block_num": [], "par_num": [], "line_num": []}
    for line_num, line in enumerate(text.split("\n")):
        for word in line.split(" "):
            if not word:
                continue
            data["text"].append(word)
            data["conf"].append(str(confidence))
            data["block_num"].append(1)
            data["par_num"].append(1)
            data["line_num"].append(line_num)
    return data


def test_ocr_triggers_on_sparse_text():
    """
    A digitally-blank PDF should yield < min_text_length characters from
    PyPDF2, causing extract_text() to fall back to _extract_with_ocr().
    """
    blank_path = os.path.join(os.path.dirname(__file__), "_blank_for_ocr_test.pdf")
    _make_blank_pdf(blank_path)

    fake_image = MagicMock()
    ocr_text = (
        "Tenant: Jamie Rivera\nMonthly Rent: $3,100.00\n"
        "Lease Start Date: June 1, 2025\nLease End Date: May 31, 2026\n"
    )

    try:
        with patch("app.pdf_extractor.convert_from_path", return_value=[fake_image]) as mock_convert, \
             patch("app.pdf_extractor.pytesseract.image_to_data", return_value=_fake_image_to_data(ocr_text)) as mock_ocr:

            extractor = PDFExtractor()
            with open(blank_path, "rb") as f:
                pages = extractor.extract_text(f, pdf_path=blank_path)

            assert mock_convert.called, "OCR fallback did not trigger for sparse-text PDF"
            assert mock_ocr.called, "pytesseract.image_to_data was never invoked"
            assert len(pages) == 1
            assert "Jamie Rivera" in pages[0]["text"]
            assert pages[0]["ocr_confidence"] == 92.0, pages[0].get("ocr_confidence")
            print("✓ test_ocr_triggers_on_sparse_text: PASS")

            # OCR output should flow through field extraction normally
            fields = FieldExtractor().extract_fields(pages)
            assert fields["tenant"]["value"] == "Jamie Rivera"
            assert fields["rent_amount"]["value"] == "$3,100.00"
            print("✓ OCR output feeds field extraction correctly: PASS")
    finally:
        os.remove(blank_path)


def test_ocr_failure_degrades_gracefully():
    """
    If poppler/tesseract are missing or OCR otherwise raises, extract_text()
    must return an empty list rather than propagating the exception, so the
    API layer can turn it into a clean error response instead of a 500
    stack trace.
    """
    blank_path = os.path.join(os.path.dirname(__file__), "_blank_for_ocr_fail_test.pdf")
    _make_blank_pdf(blank_path)

    try:
        with patch("app.pdf_extractor.convert_from_path", side_effect=Exception("poppler not installed")):
            extractor = PDFExtractor()
            with open(blank_path, "rb") as f:
                pages = extractor.extract_text(f, pdf_path=blank_path)

            assert pages == [], "OCR failure should yield an empty page list, not raise"
            print("✓ test_ocr_failure_degrades_gracefully: PASS")
    finally:
        os.remove(blank_path)


def test_no_pdf_path_skips_ocr_without_crashing():
    """Without a pdf_path, OCR can't run — should just return the sparse pages, not crash."""
    blank_path = os.path.join(os.path.dirname(__file__), "_blank_for_ocr_nopath_test.pdf")
    _make_blank_pdf(blank_path)

    try:
        extractor = PDFExtractor()
        with open(blank_path, "rb") as f:
            pages = extractor.extract_text(f, pdf_path=None)

        assert isinstance(pages, list)
        print("✓ test_no_pdf_path_skips_ocr_without_crashing: PASS")
    finally:
        os.remove(blank_path)


if __name__ == "__main__":
    test_ocr_triggers_on_sparse_text()
    test_ocr_failure_degrades_gracefully()
    test_no_pdf_path_skips_ocr_without_crashing()
    print("\nAll OCR fallback tests passed.")
