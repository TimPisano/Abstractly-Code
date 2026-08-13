"""
Real (non-mocked) OCR pipeline test — runs an actual image-based PDF
through PDFExtractor + FieldExtractor exactly as the live API does,
using the real tesseract/poppler binaries if they're on PATH.

This complements test_ocr_fallback.py, which mocks pytesseract/
pdf2image to verify the *logic* (trigger condition, success/failure
handling) without needing real binaries — appropriate for environments
that don't have them. This test verifies the real thing actually
works, when it can.

Skips cleanly (not a failure) if tesseract or poppler (pdftoppm) aren't
found on PATH, since not every environment running this suite will
have them installed — see DECISIONS.md/PROGRESS.md for how they were
obtained in this project's dev environment (conda-forge, after
Homebrew's build-from-source path hit an outdated Command Line Tools
wall) and what a fresh environment needs to run this for real.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor
from create_scanned_lease import create_scanned_lease


EXPECTED = {
    "tenant": "Pacific Crest Trading Co.",
    "landlord": "Riverfront Holdings LLC",
    "property_address": "900 Harbor View Road",
    "lease_start_date": "June 1, 2025",
    "lease_end_date": "May 31, 2030",
    "rent_amount": "$7,400.00",
    "security_deposit": "$7,400.00",
}


def test_real_ocr_pipeline():
    if shutil.which("tesseract") is None or shutil.which("pdftoppm") is None:
        print(
            "SKIPPED: tesseract and/or poppler (pdftoppm) not found on PATH. "
            "This test needs real OCR binaries — see PROGRESS.md for how "
            "this project's dev environment got them and what a fresh one "
            "needs. test_ocr_fallback.py still covers the fallback *logic* "
            "with mocks regardless of whether real binaries are available."
        )
        return True

    pdf_path = create_scanned_lease()

    try:
        pdf_extractor = PDFExtractor()
        with open(pdf_path, "rb") as f:
            pages = pdf_extractor.extract_text(f, pdf_path=pdf_path)

        assert len(pages) == 1, f"expected 1 page, got {len(pages)}"
        assert len(pages[0]["text"].strip()) > 50, (
            "OCR produced little to no text — tesseract may not be "
            f"working correctly. Got: {pages[0]['text']!r}"
        )
        print(f"✓ OCR extracted {len(pages[0]['text'])} characters of text from the image-only PDF")

        field_extractor = FieldExtractor()
        extracted = field_extractor.extract_fields(pages)

        correct = 0
        for field, expected_value in EXPECTED.items():
            actual_value = extracted[field]["value"]
            ok = bool(actual_value) and expected_value.lower() in str(actual_value).lower()
            mark = "✓" if ok else "✗"
            print(f"{mark} {field}: expected={expected_value!r} actual={actual_value!r}")
            if ok:
                correct += 1

        accuracy = correct / len(EXPECTED)
        print(f"\nReal OCR field accuracy: {correct}/{len(EXPECTED)} ({accuracy:.0%})")

        # OCR text has some noise even when working correctly (font
        # rendering artifacts, tesseract misreads), so this asserts "OCR
        # is genuinely working" (most fields recovered) rather than
        # demanding the 100% a digital-text PDF gets — that would make
        # the test flaky against normal OCR imperfection.
        assert accuracy >= 0.7, f"OCR accuracy too low ({accuracy:.0%}) — tesseract may be misconfigured"
        print("✓ test_real_ocr_pipeline: PASS")
        return True

    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)


if __name__ == "__main__":
    success = test_real_ocr_pipeline()
    sys.exit(0 if success else 1)
