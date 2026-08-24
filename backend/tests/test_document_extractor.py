"""
Tests for app/document_extractor.py: every supported upload format
(PDF, Excel .xlsx/.xls/.xlsm, CSV/TSV, Word .docx/.doc, images
.jpg/.png/.tiff, plain .txt) run through the REAL fixture files in
tests/multiformat_lease.* (see create_multiformat_fixtures.py -- real
files written by real libraries, and the .doc file is a genuine
macOS-`textutil`-converted binary .doc, not a hand-crafted blob),
confirming every format produces the SAME extracted field values --
the actual point of this feature: one consistent pipeline regardless
of input format. Also covers the specific failure modes requirement 4
asked for: corrupted files, empty files, and a genuinely unsupported
format, each with its own clear, specific error.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.document_extractor import extract_pages, DocumentExtractionError
from app.field_extractor import FieldExtractor

FIXTURES_DIR = os.path.dirname(__file__)

EXPECTED = {
    "tenant": "Cascade Outdoor Gear Co.",
    "landlord": "Timberline Properties LLC",
    "property_address": "500 Pioneer Square, Suite 300, Portland, Oregon 97204",
    "lease_start_date": "May 1, 2025",
    "lease_end_date": "April 30, 2032",
    "rent_amount": "$7,800.00",
    "security_deposit": "$7,800.00",
    "cam_charges": "$650.00",
    "square_footage": "2,900 sq ft",
}


def _read(filename):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "rb") as f:
        return f.read(), path


def _extract_and_check(filename, context, skip_fields=None):
    file_bytes, path = _read(filename)
    pages = extract_pages(file_bytes, filename, path)
    assert pages, f"{context}: no pages returned"
    result = FieldExtractor().extract_fields(pages)
    skip_fields = skip_fields or set()
    for field, expected_value in EXPECTED.items():
        if field in skip_fields:
            continue
        actual = result[field]["value"]
        assert actual == expected_value, f"{context}: field '{field}' expected {expected_value!r}, got {actual!r}"
        assert result[field]["source"] is not None, f"{context}: field '{field}' has a value but no source citation"
    return result


# ------------------------------------------------------------------
# Every supported format, individually, against the real fixture files
# ------------------------------------------------------------------

def test_pdf_still_works_unchanged():
    """PDF is the pre-existing format -- confirms this refactor didn't regress it, using an existing real project fixture, not a new one."""
    file_bytes, path = _read("sample_lease_commercial.pdf")
    pages = extract_pages(file_bytes, "sample_lease_commercial.pdf", path)
    result = FieldExtractor().extract_fields(pages)
    assert result["tenant"]["value"] == "Blue Sky Coffee Roasters, Inc."
    assert result["rent_amount"]["value"] == "$6,250.00"
    print("✓ test_pdf_still_works_unchanged: PASS")


def test_txt_extracts_correctly():
    _extract_and_check("multiformat_lease.txt", "txt")
    print("✓ test_txt_extracts_correctly: PASS")


def test_csv_extracts_correctly():
    _extract_and_check("multiformat_lease.csv", "csv")
    print("✓ test_csv_extracts_correctly: PASS")


def test_tsv_extracts_correctly():
    _extract_and_check("multiformat_lease.tsv", "tsv")
    print("✓ test_tsv_extracts_correctly: PASS")


def test_xlsx_extracts_correctly():
    result = _extract_and_check("multiformat_lease.xlsx", "xlsx")
    assert result["tenant"]["source"]["page"] == 1, "single-sheet workbook should cite page 1 (sheet 1)"
    print("✓ test_xlsx_extracts_correctly: PASS")


def test_xls_legacy_extracts_correctly():
    _extract_and_check("multiformat_lease.xls", "xls")
    print("✓ test_xls_legacy_extracts_correctly: PASS")


def test_xlsm_extracts_correctly():
    """.xlsm (macro-enabled) reuses the exact same openpyxl path as .xlsx -- confirmed with its own real file, not assumed identical."""
    import openpyxl
    path = os.path.join(FIXTURES_DIR, "multiformat_lease_temp.xlsm")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Tenant:", "Cascade Outdoor Gear Co."])
    ws.append(["Monthly Rent:", "$7,800.00"])
    wb.save(path)
    try:
        with open(path, "rb") as f:
            file_bytes = f.read()
        pages = extract_pages(file_bytes, "test.xlsm", path)
        result = FieldExtractor().extract_fields(pages)
        assert result["tenant"]["value"] == "Cascade Outdoor Gear Co."
        assert result["rent_amount"]["value"] == "$7,800.00"
    finally:
        os.unlink(path)
    print("✓ test_xlsm_extracts_correctly: PASS")


def test_docx_extracts_correctly():
    _extract_and_check("multiformat_lease.docx", "docx")
    print("✓ test_docx_extracts_correctly: PASS")


def test_doc_legacy_extracts_correctly():
    """A REAL binary .doc file, converted from the real .docx fixture by macOS's own textutil -- not a fake extension on different content."""
    _extract_and_check("multiformat_lease.doc", "doc")
    print("✓ test_doc_legacy_extracts_correctly: PASS")


def test_jpg_extracts_correctly_via_ocr():
    result = _extract_and_check("multiformat_lease.jpg", "jpg")
    assert "ocr_confidence" in result["tenant"]["source"] or result["tenant"]["source"].get("page") == 1
    print("✓ test_jpg_extracts_correctly_via_ocr: PASS")


def test_png_extracts_correctly_via_ocr():
    _extract_and_check("multiformat_lease.png", "png")
    print("✓ test_png_extracts_correctly_via_ocr: PASS")


def test_tiff_extracts_correctly_via_ocr():
    _extract_and_check("multiformat_lease.tiff", "tiff")
    print("✓ test_tiff_extracts_correctly_via_ocr: PASS")


def test_image_pages_carry_ocr_confidence():
    """Images must route through the same OCR machinery scanned PDFs use, including the per-page confidence signal field_extractor.py's validation step relies on."""
    file_bytes, path = _read("multiformat_lease.png")
    pages = extract_pages(file_bytes, "multiformat_lease.png", path)
    assert "ocr_confidence" in pages[0], "image pages must carry ocr_confidence, same as OCR'd PDF pages"
    assert isinstance(pages[0]["ocr_confidence"], (int, float))
    print("✓ test_image_pages_carry_ocr_confidence: PASS")


# ------------------------------------------------------------------
# Clear, specific failure modes (requirement 4) -- never silent, never hangs
# ------------------------------------------------------------------

def test_empty_file_fails_clearly():
    for filename in ("empty.pdf", "empty.xlsx", "empty.docx", "empty.txt", "empty.csv", "empty.jpg"):
        try:
            extract_pages(b"", filename, "/tmp/does-not-matter")
            assert False, f"{filename}: empty file must raise, not succeed"
        except DocumentExtractionError as e:
            assert "empty" in str(e).lower()
    print("✓ test_empty_file_fails_clearly: PASS")


def test_unsupported_extension_fails_clearly():
    try:
        extract_pages(b"some content", "lease.rtf", "/tmp/does-not-matter")
        assert False, "unsupported extension must raise"
    except DocumentExtractionError as e:
        assert "Unsupported file type" in str(e)
        assert ".rtf" in str(e)
    print("✓ test_unsupported_extension_fails_clearly: PASS")


def test_corrupted_docx_fails_clearly():
    try:
        extract_pages(b"this is not a real docx file", "fake.docx", "/tmp/does-not-matter")
        assert False, "corrupted docx must raise"
    except DocumentExtractionError as e:
        assert "corrupted" in str(e).lower() or "unsupported" in str(e).lower()
    print("✓ test_corrupted_docx_fails_clearly: PASS")


def test_corrupted_xlsx_fails_clearly():
    try:
        extract_pages(b"this is not a real xlsx file", "fake.xlsx", "/tmp/does-not-matter")
        assert False, "corrupted xlsx must raise"
    except DocumentExtractionError as e:
        assert "corrupted" in str(e).lower() or "unsupported" in str(e).lower()
    print("✓ test_corrupted_xlsx_fails_clearly: PASS")


def test_corrupted_xls_fails_clearly():
    try:
        extract_pages(b"this is not a real xls file", "fake.xls", "/tmp/does-not-matter")
        assert False, "corrupted xls must raise"
    except DocumentExtractionError as e:
        assert "corrupted" in str(e).lower() or "unsupported" in str(e).lower()
    print("✓ test_corrupted_xls_fails_clearly: PASS")


def test_corrupted_image_fails_clearly():
    try:
        extract_pages(b"\xff\xd8\xff garbage not a real jpeg at all", "fake.jpg", "/tmp/does-not-matter")
        assert False, "corrupted image must raise"
    except DocumentExtractionError as e:
        assert "corrupted" in str(e).lower() or "unsupported" in str(e).lower()
    print("✓ test_corrupted_image_fails_clearly: PASS")


def test_blank_looking_but_valid_csv_fails_clearly():
    try:
        extract_pages(b"\n\n\n,,,\n\n", "blank.csv", "/tmp/does-not-matter")
        assert False, "a CSV with only blank rows must raise, not silently produce zero fields"
    except DocumentExtractionError as e:
        assert "no readable" in str(e).lower()
    print("✓ test_blank_looking_but_valid_csv_fails_clearly: PASS")


def test_corrupted_pdf_fails_clearly_with_real_temp_file():
    """Uses a real temp file (not a fake path) so both PyPDF2 AND the OCR fallback genuinely attempt and genuinely fail -- confirms the failure path doesn't hang or crash uncaught even when every extraction strategy fails."""
    garbage = b"not a real pdf at all, just plain text pretending to be one"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(garbage)
        path = f.name
    try:
        extract_pages(garbage, "fake.pdf", path)
        assert False, "corrupted pdf must raise"
    except DocumentExtractionError as e:
        assert "Failed to extract text" in str(e)
    finally:
        os.unlink(path)
    print("✓ test_corrupted_pdf_fails_clearly_with_real_temp_file: PASS")


def test_no_extension_fails_clearly():
    try:
        extract_pages(b"some content", "no_extension_at_all", "/tmp/does-not-matter")
        assert False, "a file with no extension must raise, not crash or guess"
    except DocumentExtractionError as e:
        assert "Unsupported file type" in str(e)
    print("✓ test_no_extension_fails_clearly: PASS")


if __name__ == "__main__":
    test_pdf_still_works_unchanged()
    test_txt_extracts_correctly()
    test_csv_extracts_correctly()
    test_tsv_extracts_correctly()
    test_xlsx_extracts_correctly()
    test_xls_legacy_extracts_correctly()
    test_xlsm_extracts_correctly()
    test_docx_extracts_correctly()
    test_doc_legacy_extracts_correctly()
    test_jpg_extracts_correctly_via_ocr()
    test_png_extracts_correctly_via_ocr()
    test_tiff_extracts_correctly_via_ocr()
    test_image_pages_carry_ocr_confidence()
    test_empty_file_fails_clearly()
    test_unsupported_extension_fails_clearly()
    test_corrupted_docx_fails_clearly()
    test_corrupted_xlsx_fails_clearly()
    test_corrupted_xls_fails_clearly()
    test_corrupted_image_fails_clearly()
    test_blank_looking_but_valid_csv_fails_clearly()
    test_corrupted_pdf_fails_clearly_with_real_temp_file()
    test_no_extension_fails_clearly()
    print("\nAll document extractor tests passed.")
