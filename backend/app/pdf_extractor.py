"""
PDF text extraction module with fallback to OCR.

This module handles extracting text from lease PDFs using PyPDF2 for digital PDFs
and falling back to OCR (pytesseract + pdf2image) for scanned PDFs.
"""

import logging
import re
from typing import Optional, Dict, Any, List
import PyPDF2
from pdf2image import convert_from_path
import pytesseract
from io import BytesIO

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Handles PDF text extraction with OCR fallback."""

    def __init__(self):
        # Minimum text length to consider PyPDF2 extraction successful
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
        # First try PyPDF2 for digital PDF extraction
        pages = self._extract_with_pypdf2(pdf_file)

        # Calculate total text length across all pages
        total_text = "".join(page["text"] for page in pages)

        # If extraction yielded poor results, fall back to OCR
        if len(total_text.strip()) < self.min_text_length:
            logger.info("PyPDF2 extraction yielded poor results, falling back to OCR...")
            if pdf_path:
                pages = self._extract_with_ocr(pdf_path)
            else:
                logger.warning("OCR fallback requires pdf_path parameter, but none was given")

        return pages

    def _extract_with_pypdf2(self, pdf_file) -> List[Dict[str, Any]]:
        """
        Extract text using PyPDF2 (for digital PDFs).

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
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            # Extract text from each page
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                text = page.extract_text()
                pages.append({
                    "page": page_num,
                    "text": text
                })

        except Exception:
            logger.exception("Error during PyPDF2 extraction")
            # Return empty list on error, will trigger OCR fallback
            return []

        return pages

    def _extract_with_ocr(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract text using OCR (for scanned PDFs).

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

            # Run OCR on each page
            for page_num, image in enumerate(images, start=1):
                text = pytesseract.image_to_string(image)
                pages.append({
                    "page": page_num,
                    "text": text
                })

        except Exception:
            logger.exception("Error during OCR extraction")
            # Return empty result if OCR also fails
            return []

        return pages
