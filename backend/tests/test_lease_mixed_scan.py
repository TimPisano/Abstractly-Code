"""
Regression test: a typed lease with scanned attachment pages.

Before: OCR ran only when the WHOLE PDF had almost no text, and any
near-empty page then blocked the entire upload as "OCR needed" -- so a
typed lease with a faxed-back, signed HUD Tenancy Addendum got no
extraction at all. Now the near-empty pages are OCR'd on their own.

The mocked test runs everywhere; the real-OCR test needs tesseract and
poppler (skipped without them, the known local-only dependency).
"""

import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import pdf_extractor
from app.pdf_extractor import PDFExtractor


def test_only_sparse_pages_are_ocred_and_longer_text_wins():
    pages = [
        {"page": 1, "text": "APARTMENT LEASE CONTRACT " * 10},
        {"page": 2, "text": ""},
        {"page": 3, "text": "  x "},
    ]
    ocr_calls = []

    def fake_convert(path, first_page, last_page):
        ocr_calls.append(first_page)
        return [f"image-{first_page}"]

    def fake_ocr(self, image):
        return ("TENANCY ADDENDUM Tenant Rent: $312.00 per month" if image == "image-2" else "", 88.0)

    with mock.patch.object(pdf_extractor, "convert_from_path", fake_convert), \
            mock.patch.object(PDFExtractor, "_ocr_page_with_confidence", fake_ocr), \
            mock.patch.object(PDFExtractor, "_ocr_tools_available", return_value=True):
        out = PDFExtractor()._ocr_sparse_pages(pages, "/tmp/unused.pdf")
    assert ocr_calls == [2, 3], ocr_calls
    assert out[1]["text"].startswith("TENANCY ADDENDUM") and out[1]["ocr_confidence"] == 88.0
    assert out[2]["text"] == "  x " and "ocr_confidence" not in out[2]  # OCR found less: keep the original
    assert "ocr_confidence" not in out[0]
    print("✓ Only near-empty pages are OCR'd; OCR text kept only when longer: PASS")


def test_ocr_failure_on_one_page_keeps_the_rest():
    pages = [{"page": 1, "text": "x" * 200}, {"page": 2, "text": ""}]
    with mock.patch.object(pdf_extractor, "convert_from_path", side_effect=RuntimeError("poppler missing")), \
            mock.patch.object(PDFExtractor, "_ocr_tools_available", return_value=True):
        out = PDFExtractor()._ocr_sparse_pages(pages, "/tmp/unused.pdf")
    assert out == pages
    print("✓ A page whose OCR fails keeps its text layer, nothing raises: PASS")


def test_sparse_ocr_is_bounded_by_pages_and_time():
    """It runs inside the upload request: never more than 10 pages or ~60s."""
    pages = [{"page": n, "text": ""} for n in range(1, 41)]
    calls = []

    def fake_convert(path, first_page, last_page):
        calls.append(first_page)
        return ["img"]

    with mock.patch.object(pdf_extractor, "convert_from_path", fake_convert), \
            mock.patch.object(PDFExtractor, "_ocr_page_with_confidence", return_value=("", None)), \
            mock.patch.object(PDFExtractor, "_ocr_tools_available", return_value=True):
        PDFExtractor()._ocr_sparse_pages(pages, "/tmp/unused.pdf")
    assert len(calls) == PDFExtractor.MAX_SPARSE_PAGES_TO_OCR == 10, calls

    calls.clear()
    clock = iter([0.0, 0.0, 30.0, 61.0, 90.0, 120.0])  # start, then one reading per page
    with mock.patch.object(pdf_extractor, "convert_from_path", fake_convert), \
            mock.patch.object(PDFExtractor, "_ocr_page_with_confidence", return_value=("", None)), \
            mock.patch.object(PDFExtractor, "_ocr_tools_available", return_value=True), \
            mock.patch.object(pdf_extractor.time, "monotonic", lambda: next(clock)):
        PDFExtractor()._ocr_sparse_pages(pages, "/tmp/unused.pdf")
    assert calls == [1, 2], calls  # the 60s budget stops it before page 3
    print("✓ Sparse-page OCR stops at 10 pages or 60 seconds: PASS")


def test_no_ocr_attempt_without_tesseract():
    pages = [{"page": 1, "text": ""}]
    with mock.patch.object(PDFExtractor, "_ocr_tools_available", return_value=False), \
            mock.patch.object(pdf_extractor, "convert_from_path", side_effect=AssertionError("must not be called")):
        assert PDFExtractor()._ocr_sparse_pages(pages, "/tmp/unused.pdf") == pages
    print("✓ No OCR attempt when tesseract/poppler aren't installed: PASS")


def test_real_mixed_pdf_extracts_from_the_scanned_addendum():
    if not (shutil.which("tesseract") and shutil.which("pdftoppm")):
        print("- SKIP real OCR (tesseract/poppler not installed)")
        return
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools", "lease_corpus")))
    import generate
    from app import document_extractor
    from app.field_extractor import FieldExtractor

    out = tempfile.mkdtemp(prefix="mixed_scan_")
    try:
        manifest = generate.generate(out, only="mixed_scan_section8")
        case = manifest["cases"][0]
        path = os.path.join(out, case["file"])
        with open(path, "rb") as fh:
            pages = document_extractor.extract_pages(fh.read(), case["file"], path)
        assert not document_extractor.find_low_text_pages(pages), document_extractor.find_low_text_pages(pages)
        assert any("ocr_confidence" in p for p in pages), "no page went through OCR"
        with mock.patch.dict(os.environ, {"LEASE_MULTIFAMILY_FIELDS": "1"}):
            fields = FieldExtractor().extract_fields(pages)
        s8 = fields["section_8"]["details"]
        assert s8["tenant_rent"] == case["section_8"]["tenant_rent"], (s8, case["section_8"])
        assert s8["hap_amount"] == case["section_8"]["hap_amount"], (s8, case["section_8"])
    finally:
        shutil.rmtree(out, ignore_errors=True)
    print("✓ Typed lease + scanned HUD addendum/HAP contract: the scanned pages are read: PASS")


if __name__ == "__main__":
    test_only_sparse_pages_are_ocred_and_longer_text_wins()
    test_ocr_failure_on_one_page_keeps_the_rest()
    test_sparse_ocr_is_bounded_by_pages_and_time()
    test_no_ocr_attempt_without_tesseract()
    test_real_mixed_pdf_extracts_from_the_scanned_addendum()
    print("\nAll mixed-scan tests passed.")
