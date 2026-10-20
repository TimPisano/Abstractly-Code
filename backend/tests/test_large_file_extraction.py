"""
Tests for the large-file text extraction path:
PDFExtractor.extract_text_per_page and document_extractor.extract_pages_from_path.

Real tesseract + poppler run on small slices of the 300-page scanned
fixture (OCR-ing all 300 pages takes ~10 minutes, so the full-size run is
done by tests/run_large_file_scale_check.py and recorded in the report,
not here).
"""
import io
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pypdf  # noqa: E402

from create_large_fixtures import SCANNED_LEASE, TEXT_LEASE, ensure_large_fixtures, path_of  # noqa: E402
from app import document_extractor  # noqa: E402
from app.document_extractor import DocumentExtractionError, extract_pages_from_path  # noqa: E402
from app.pdf_extractor import PDFExtractor  # noqa: E402

TENANT = "Northwind Outfitters"


def _pdf_from(pages_by_source, dest):
    """pages_by_source: list of (fixture path, 0-based page index)."""
    writer = pypdf.PdfWriter()
    readers = {}
    for src, index in pages_by_source:
        readers.setdefault(src, pypdf.PdfReader(src))
        writer.add_page(readers[src].pages[index])
    with open(dest, "wb") as f:
        writer.write(f)
    return dest


def _text_image(text_lines, size=(1700, 2200)):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    except Exception:
        font = ImageFont.load_default()
    y = 150
    for line in text_lines:
        draw.text((150, y), line, fill=0, font=font)
        y += 70
    return image


def test_scanned_pages_are_rasterized_one_at_a_time_and_ocrd():
    ensure_large_fixtures(only=[SCANNED_LEASE])
    tmpdir = tempfile.mkdtemp()
    try:
        pdf = _pdf_from([(path_of(SCANNED_LEASE), i) for i in range(4)], os.path.join(tmpdir, "scan4.pdf"))
        import app.pdf_extractor as pe
        real = pe.convert_from_path
        calls = []

        def spy(path, **kwargs):
            calls.append(kwargs)
            return real(path, **kwargs)

        progress = []
        with mock.patch.object(pe, "convert_from_path", side_effect=spy):
            pages = PDFExtractor().extract_text_per_page(pdf, progress=lambda d, t: progress.append((d, t)))

        assert len(pages) == 4
        assert len(calls) == 4, f"expected one rasterization per page, got {len(calls)}"
        for n, kwargs in enumerate(calls, start=1):
            assert kwargs.get("first_page") == n and kwargs.get("last_page") == n, kwargs
            assert kwargs.get("grayscale") is True
        assert TENANT in pages[0]["text"], pages[0]["text"][:300]
        assert all("ocr_confidence" in p for p in pages), "every scanned page went through OCR"
        assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]
    finally:
        shutil.rmtree(tmpdir)
    print("✓ test_scanned_pages_are_rasterized_one_at_a_time_and_ocrd: PASS")


def test_mixed_pdf_only_ocrs_the_pages_without_text():
    """A long digital lease with a few scanned pages: the old whole-document rule (OCR only if the entire file has <100 chars) never OCR'd them."""
    ensure_large_fixtures(only=[SCANNED_LEASE, TEXT_LEASE])
    tmpdir = tempfile.mkdtemp()
    try:
        pdf = _pdf_from(
            [(path_of(TEXT_LEASE), 0), (path_of(TEXT_LEASE), 1), (path_of(SCANNED_LEASE), 0), (path_of(TEXT_LEASE), 2)],
            os.path.join(tmpdir, "mixed.pdf"),
        )
        # The old path: plenty of text overall, so the scanned page stays empty.
        with open(pdf, "rb") as f:
            old_pages = PDFExtractor().extract_text(f, pdf_path=pdf)
        assert len((old_pages[2]["text"] or "").strip()) == 0

        pages = PDFExtractor().extract_text_per_page(pdf)
        assert [("ocr_confidence" in p) for p in pages] == [False, False, True, False]
        assert TENANT in pages[2]["text"]
        assert pages[0]["text"] == old_pages[0]["text"], "text-layer pages are read exactly as before"
    finally:
        shutil.rmtree(tmpdir)
    print("✓ test_mixed_pdf_only_ocrs_the_pages_without_text: PASS")


def test_one_failing_page_does_not_sink_the_document():
    ensure_large_fixtures(only=[SCANNED_LEASE])
    tmpdir = tempfile.mkdtemp()
    try:
        pdf = _pdf_from([(path_of(SCANNED_LEASE), i) for i in range(3)], os.path.join(tmpdir, "scan3.pdf"))
        real = PDFExtractor._ocr_page_with_confidence
        seen = {"n": 0}

        def flaky(self, image, timeout_s=0):
            seen["n"] += 1
            if seen["n"] == 2:
                raise RuntimeError("Tesseract process timeout")
            return real(self, image, timeout_s=timeout_s)

        with mock.patch.object(PDFExtractor, "_ocr_page_with_confidence", flaky):
            pages = PDFExtractor().extract_text_per_page(pdf, ocr_timeout_s=5)
        assert len(pages) == 3
        assert TENANT in pages[0]["text"]
        assert pages[1]["text"] == "" and "ocr_confidence" not in pages[1]
        assert len(pages[2]["text"]) > 50
    finally:
        shutil.rmtree(tmpdir)
    print("✓ test_one_failing_page_does_not_sink_the_document: PASS")


def test_multi_page_tiff_becomes_one_page_per_frame():
    tmpdir = tempfile.mkdtemp()
    try:
        frames = [_text_image([f"COMMERCIAL LEASE PAGE {n}", "Tenant: Northwind Outfitters, Inc."]) for n in (1, 2, 3)]
        path = os.path.join(tmpdir, "fax.tiff")
        frames[0].save(path, save_all=True, append_images=frames[1:], compression="tiff_lzw")

        # The old path reads only the first frame.
        with open(path, "rb") as f:
            assert len(document_extractor.extract_pages(f.read(), "fax.tiff", path)) == 1

        progress = []
        pages = extract_pages_from_path(path, "tiff", progress=lambda d, t: progress.append((d, t)))
        assert [p["page"] for p in pages] == [1, 2, 3]
        for n, page in enumerate(pages, start=1):
            assert f"PAGE {n}" in page["text"].upper() and TENANT in page["text"], page["text"]
        assert progress[-1] == (3, 3)
    finally:
        shutil.rmtree(tmpdir)
    print("✓ test_multi_page_tiff_becomes_one_page_per_frame: PASS")


def test_heic_photo_is_decoded_and_ocrd():
    import pillow_heif
    pillow_heif.register_heif_opener()
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "IMG_0042.heic")
        _text_image(["COMMERCIAL LEASE", "Tenant: Northwind Outfitters, Inc.", "Base Rent: $18,750.00 per month"]).convert("RGB").save(path, "HEIF")
        pages = extract_pages_from_path(path, "heic")
        assert len(pages) == 1 and TENANT in pages[0]["text"] and "ocr_confidence" in pages[0], pages
    finally:
        shutil.rmtree(tmpdir)
    print("✓ test_heic_photo_is_decoded_and_ocrd: PASS")


def test_oversized_photo_is_scaled_down_before_ocr():
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "huge.png")
        _text_image(["Tenant: Northwind Outfitters, Inc."], size=(9000, 3000)).save(path)
        sizes = []
        real = PDFExtractor._ocr_page_with_confidence

        def spy(self, image, timeout_s=0):
            sizes.append(image.size)
            return real(self, image, timeout_s=timeout_s)

        with mock.patch.object(PDFExtractor, "_ocr_page_with_confidence", spy):
            extract_pages_from_path(path, "png")
        assert max(sizes[0]) <= document_extractor._MAX_OCR_IMAGE_SIDE, sizes
    finally:
        shutil.rmtree(tmpdir)
    print("✓ test_oversized_photo_is_scaled_down_before_ocr: PASS")


def test_unreadable_inputs_raise_friendly_errors():
    tmpdir = tempfile.mkdtemp()
    try:
        writer = pypdf.PdfWriter()
        writer.add_blank_page(612, 792)
        writer.encrypt(user_password="secret", owner_password="owner")
        locked = os.path.join(tmpdir, "locked.pdf")
        with open(locked, "wb") as f:
            writer.write(f)
        cases = [
            (locked, "pdf", "password-protected"),
            (os.path.join(tmpdir, "empty.pdf"), "pdf", "empty"),
            (os.path.join(tmpdir, "broken.pdf"), "pdf", "couldn't be opened"),
            (os.path.join(tmpdir, "blank.png"), "png", "No readable text"),
        ]
        open(cases[1][0], "wb").close()
        with open(cases[2][0], "wb") as f:
            f.write(b"%PDF-1.7\n" + os.urandom(300))
        from PIL import Image
        Image.new("L", (800, 800), 255).save(cases[3][0])
        for path, ext, needle in cases:
            try:
                extract_pages_from_path(path, ext)
            except DocumentExtractionError as e:
                assert needle.lower() in str(e).lower(), f"{os.path.basename(path)}: {e}"
            else:
                raise AssertionError(f"{os.path.basename(path)} should have failed")
    finally:
        shutil.rmtree(tmpdir)
    print("✓ test_unreadable_inputs_raise_friendly_errors: PASS")


def test_500_page_text_lease_keeps_every_page():
    ensure_large_fixtures(only=[TEXT_LEASE])
    import app.pdf_extractor as pe
    with mock.patch.object(pe, "convert_from_path", side_effect=AssertionError("a text PDF must never be rasterized")):
        pages = extract_pages_from_path(path_of(TEXT_LEASE), "pdf")
    assert len(pages) == 500
    assert "56,250.00" in pages[261]["text"], "page 262's security deposit survives"
    assert "EXCLUSIVE USE" in pages[477]["text"]
    print("✓ test_500_page_text_lease_keeps_every_page: PASS")


if __name__ == "__main__":
    test_scanned_pages_are_rasterized_one_at_a_time_and_ocrd()
    test_mixed_pdf_only_ocrs_the_pages_without_text()
    test_one_failing_page_does_not_sink_the_document()
    test_multi_page_tiff_becomes_one_page_per_frame()
    test_heic_photo_is_decoded_and_ocrd()
    test_oversized_photo_is_scaled_down_before_ocr()
    test_unreadable_inputs_raise_friendly_errors()
    test_500_page_text_lease_keeps_every_page()
    print("\nAll large-file extraction tests passed!")
