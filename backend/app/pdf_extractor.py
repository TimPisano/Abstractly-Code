"""
PDF text extraction module with fallback to OCR.

This module handles extracting text from lease PDFs using pypdf for digital PDFs
and falling back to OCR (pytesseract + pdf2image) for scanned PDFs.
"""

import logging
import shutil
import time
from typing import Dict, Any, List
import pypdf
from pdf2image import convert_from_path
import pytesseract

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Handles PDF text extraction with OCR fallback."""

    def __init__(self):
        # Minimum text length to consider pypdf extraction successful
        # If extracted text is shorter, we assume it's a scanned PDF
        self.min_text_length = 100

    def extract_text(self, pdf_file, pdf_path=None) -> List[Dict[str, Any]]:
        """
        Extract text from PDF file, using OCR if needed.

        Args:
            pdf_file: File-like object containing PDF data
            pdf_path: Optional file path (required for OCR fallback)

        Returns:
            List of dicts with page numbers and text content:
            [{"page": 1, "text": "..."}, {"page": 2, "text": "..."}, ...]
        """
        # First try pypdf for digital PDF extraction
        pages = self._extract_with_pypdf2(pdf_file)

        # Calculate total text length across all pages
        total_text = "".join(page["text"] for page in pages)

        # If extraction yielded poor results, fall back to OCR
        if len(total_text.strip()) < self.min_text_length:
            logger.info("pypdf extraction yielded poor results, falling back to OCR...")
            if pdf_path:
                pages = self._extract_with_ocr(pdf_path)
            else:
                logger.warning("OCR fallback requires pdf_path parameter, but none was given")
        elif pdf_path:
            # A mostly-typed PDF can still carry scanned pages -- a signed
            # HUD Tenancy Addendum, HAP contract, or renewal faxed back and
            # appended to the typed lease. Those pages used to block the
            # whole document ("OCR needed") even though OCR was available.
            pages = self._ocr_sparse_pages(pages, pdf_path)

        return pages

    # A page with less text than this gets an OCR attempt of its own
    # (same bar document_extractor.find_low_text_pages uses to call a page
    # unusable). This runs inside the upload request, so it's bounded by
    # both a page count and a total time budget, well inside gunicorn's
    # 120s worker timeout. Pages left over keep their (empty) text layer
    # and get the old "OCR needed" handling -- the same as before this
    # existed, never worse.
    MIN_PAGE_CHARS = 50
    MAX_SPARSE_PAGES_TO_OCR = 10
    SPARSE_OCR_BUDGET_SECONDS = 60.0

    @staticmethod
    def _ocr_tools_available() -> bool:
        return bool(shutil.which("tesseract") and shutil.which("pdftoppm"))

    def _ocr_sparse_pages(self, pages: List[Dict[str, Any]], pdf_path: str) -> List[Dict[str, Any]]:
        """OCR only the near-empty pages of an otherwise-digital PDF; keep OCR text only if it's longer."""
        sparse = [p for p in pages if len((p.get("text") or "").strip()) < self.MIN_PAGE_CHARS]
        if not sparse or not self._ocr_tools_available():
            return pages
        started = time.monotonic()
        for index, page in enumerate(sparse[:self.MAX_SPARSE_PAGES_TO_OCR]):
            if time.monotonic() - started > self.SPARSE_OCR_BUDGET_SECONDS:
                logger.warning("Sparse-page OCR budget (%.0fs) used up after %d of %d page(s); the rest stay unread",
                               self.SPARSE_OCR_BUDGET_SECONDS, index, len(sparse))
                break
            try:
                images = convert_from_path(pdf_path, first_page=page["page"], last_page=page["page"])
                if not images:
                    continue
                text, confidence = self._ocr_page_with_confidence(images[0])
            except Exception:
                logger.exception("OCR of sparse page %s failed; keeping its text layer", page["page"])
                continue
            if len(text.strip()) > len((page.get("text") or "").strip()):
                page["text"] = text
                if confidence is not None:
                    page["ocr_confidence"] = confidence
        return pages

    def _extract_with_pypdf2(self, pdf_file) -> List[Dict[str, Any]]:
        """
        Extract text using pypdf (for digital PDFs).

        Args:
            pdf_file: File-like object containing PDF data

        Returns:
            List of page dictionaries
        """
        pages = []

        try:
            # Reset file pointer to beginning
            pdf_file.seek(0)

            # Read PDF
            pdf_reader = pypdf.PdfReader(pdf_file)

            # An owner-password-only PDF (no password needed to read
            # it, just to edit/print) still reports is_encrypted, and
            # pypdf refuses to read .pages on it until decrypt() has
            # been called -- even with the correct effective (empty)
            # password. A real user-password PDF also reaches this
            # point (the caller's own upfront check only short-circuits
            # the ones it can detect this way; direct callers of this
            # method skip that check entirely) -- decrypt("") simply
            # fails for those, .pages then raises, and this method
            # returns [] same as any other unreadable PDF.
            if pdf_reader.is_encrypted:
                pdf_reader.decrypt("")

            # Extract text from each page
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                text = page.extract_text()
                pages.append({
                    "page": page_num,
                    "text": text
                })

        except Exception:
            logger.exception("Error during pypdf extraction")
            # Return empty list on error, will trigger OCR fallback
            return []

        return pages

    def _extract_with_ocr(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract text using OCR (for scanned PDFs).

        Each page also carries an "ocr_confidence" (0-100, tesseract's own
        mean word-confidence for that page's recognized text, or None if
        nothing was recognized at all) -- a real, per-page signal of how
        legible the scan actually was, not a guess. field_extractor.py's
        confidence-validation step uses this to downgrade a field whose
        source page came back barely legible, even if the field's own
        pattern match looked clean. Digitally-extracted pages (pypdf,
        no OCR involved) never carry this key at all, which is the
        signal field_extractor.py uses to know OCR wasn't involved for
        that page's fields.

        Args:
            pdf_path: File path to PDF

        Returns:
            List of page dictionaries
        """
        pages = []

        try:
            # Convert PDF pages to images
            # Note: This requires poppler to be installed on the system
            images = convert_from_path(pdf_path)

            # Run OCR on each page. image_to_data (not image_to_string) is
            # used so the same OCR pass yields both the recognized text
            # AND tesseract's own per-word confidence -- calling both
            # would OCR every page twice for no reason.
            for page_num, image in enumerate(images, start=1):
                text, confidence = self._ocr_page_with_confidence(image)
                page_entry = {"page": page_num, "text": text}
                if confidence is not None:
                    page_entry["ocr_confidence"] = confidence
                pages.append(page_entry)

        except Exception:
            logger.exception("Error during OCR extraction")
            # Return empty result if OCR also fails
            return []

        return pages

    def _ocr_page_with_confidence(self, image):
        """
        Runs tesseract once via image_to_data and returns (text, mean_
        confidence). Text is reconstructed from the word-level data
        (joined with spaces within a line, newlines between lines) rather
        than calling image_to_string separately, so this is a single OCR
        pass, not two.

        mean_confidence is the average of tesseract's own per-word
        confidence scores (0-100), counting only words it actually
        recognized -- tesseract reports -1 for regions with no
        recognized text (whitespace/layout boxes), which are excluded
        rather than dragging the average down for reasons that have
        nothing to do with legibility. Returns (text, None) if nothing
        was recognized at all, so a caller can tell "OCR ran but found
        nothing" apart from "OCR ran and was confident."
        """
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        lines: Dict[Any, List[str]] = {}
        confidences: List[float] = []
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(line_key, []).append(word)
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1
            if conf >= 0:
                confidences.append(conf)

        text = "\n".join(" ".join(words) for words in lines.values())
        mean_confidence = round(sum(confidences) / len(confidences), 1) if confidences else None
        return text, mean_confidence
