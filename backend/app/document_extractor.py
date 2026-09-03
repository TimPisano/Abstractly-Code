"""
Multi-format document text extraction: given ANY of this project's
supported upload formats (PDF, Excel .xlsx/.xls/.xlsm, CSV/TSV, Word
.docx/.doc, images .jpg/.png/.tiff, plain .txt), produces the SAME
`pages` shape PDFExtractor already produces for PDFs --
`List[{"page": N, "text": "...", ["ocr_confidence": N]}]` -- so
FieldExtractor.extract_fields()/extract_multiple_leases() (and
everything downstream of it: confidence scoring, source citations, the
audit trail, risk analysis) runs completely unchanged regardless of
which format the document arrived in. There is exactly ONE extraction/
validation pipeline; this module's only job is getting any input
format into the one shape that pipeline already understands. No
format-specific special-casing exists anywhere past `extract_pages()`.

Every function here either succeeds with a real, non-empty pages list,
or raises DocumentExtractionError with a specific, user-facing message
naming what actually went wrong (corrupted file, empty file, wrong
format content, no readable text) -- never returns an empty/partial
result silently, and never hangs (every call here is a bounded,
synchronous parse of an already-fully-read-into-memory file; no
network calls, no unbounded loops).
"""
import csv
import io
import logging
import re
from typing import Any, Dict, List

import olefile
import openpyxl
import xlrd
from docx import Document as DocxDocument
from PIL import Image, UnidentifiedImageError
import pypdf

from .pdf_extractor import PDFExtractor

logger = logging.getLogger(__name__)


class DocumentExtractionError(Exception):
    """Raised with a clear, specific, user-facing message when a file genuinely can't be processed."""


# Extension -> format family. The single source of truth for "what does
# this project accept" -- api.py's ALLOWED_EXTENSIONS and the frontend's
# accept="" attributes should always list exactly these extensions.
SUPPORTED_EXTENSIONS = {
    "pdf": "pdf",
    "xlsx": "excel", "xlsm": "excel",
    "xls": "excel_legacy",
    "csv": "delimited", "tsv": "delimited",
    "docx": "word",
    "doc": "word_legacy",
    "jpg": "image", "jpeg": "image", "png": "image", "tif": "image", "tiff": "image",
    "txt": "text",
}

_MIN_LEGACY_DOC_TEXT_LENGTH = 50


def _extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower() if filename and "." in filename else ""


def extract_pages(file_bytes: bytes, filename: str, temp_path: str) -> List[Dict[str, Any]]:
    """
    Dispatches on the file's extension. `temp_path` is a path to the
    same bytes already saved to disk -- only the PDF path actually
    needs it (pdf2image's OCR fallback requires a real file path, not
    bytes); every other format works directly from `file_bytes`.

    Raises DocumentExtractionError (never returns an empty pages list)
    if the file can't be processed. Callers should catch that
    specifically and surface str(error) directly to the user -- it's
    already written to be a clear, actionable message, not an internal
    detail.
    """
    if not file_bytes:
        raise DocumentExtractionError("This file is empty.")

    extension = _extension_of(filename)
    kind = SUPPORTED_EXTENSIONS.get(extension)
    if kind is None:
        supported = "PDF, Excel (.xlsx/.xls/.xlsm), CSV/TSV, Word (.docx/.doc), images (.jpg/.png/.tiff), and plain text (.txt)"
        raise DocumentExtractionError(f"Unsupported file type '.{extension or '?'}'. Supported formats: {supported}.")

    if kind == "pdf":
        pages = _extract_pdf(file_bytes, temp_path)
    elif kind == "excel":
        pages = _extract_excel_xlsx(file_bytes)
    elif kind == "excel_legacy":
        pages = _extract_excel_xls(file_bytes)
    elif kind == "delimited":
        pages = _extract_delimited(file_bytes, extension)
    elif kind == "word":
        pages = _extract_docx(file_bytes)
    elif kind == "word_legacy":
        pages = _extract_doc_legacy(file_bytes)
    elif kind == "image":
        pages = _extract_image(file_bytes)
    else:
        pages = _extract_plain_text(file_bytes)

    if not pages:
        raise DocumentExtractionError("This file has no readable content.")
    return pages


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------

def _extract_pdf(file_bytes: bytes, temp_path: str) -> List[Dict[str, Any]]:
    # Checked before extraction, not left to surface as a generic
    # "corrupted or unsupported" failure: a password-protected PDF is
    # structurally fine and has a specific, actionable fix (open it,
    # remove the password, re-upload) that a vague corruption message
    # would hide. pypdf.is_encrypted is true even for a PDF with only
    # an OWNER password (no password needed to open/read it) --
    # decrypt("") succeeds for those; only genuinely
    # unreadable-without-a-real-password files fail here.
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise DocumentExtractionError(
                "This PDF is password-protected. Remove the password (or save an "
                "unprotected copy) and upload it again."
            )
    except DocumentExtractionError:
        raise
    except Exception:
        # Not our concern here -- extract_text() below runs its own
        # extraction attempt and OCR fallback, and reports its own
        # failure if the file turns out to be unreadable for some
        # other reason.
        pass

    with open(temp_path, "rb") as f:
        pages = PDFExtractor().extract_text(f, pdf_path=temp_path)

    if not pages:
        raise DocumentExtractionError("Failed to extract text from this PDF. The file may be corrupted or unsupported.")
    return pages


# ----------------------------------------------------------------------
# Excel (.xlsx / .xlsm via openpyxl, .xls via xlrd -- openpyxl dropped
# legacy .xls support entirely; xlrd 2.x dropped .xlsx support entirely
# in the other direction, so both libraries are needed, one per format)
# ----------------------------------------------------------------------

def _rows_to_lines(rows) -> List[str]:
    """
    Shared by both Excel readers (and CSV/TSV): one text line per
    non-empty row, cells joined with a single space -- rendering a
    two-cell ["Tenant:", "Acme Corp"] row as "Tenant: Acme Corp",
    genuine label-style prose FieldExtractor's label/value patterns
    can match directly.

    Deliberately NOT joined with a visual separator like " | " --
    tried that first, and it broke exactly this: FieldExtractor's
    label-style patterns (tenant, landlord, both dates) require the
    value to sit immediately after the label with only whitespace in
    between, so "Tenant: | Acme Corp" failed to match at all where
    "Tenant: Acme Corp" does, and one field (property_address, matched
    by a looser pattern) picked up a literal stray "| " into its
    captured value. Confirmed both problems by actually running a real
    fixture through this before fixing it, not assumed.
    """
    lines = []
    for row in rows:
        cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
        if cells:
            lines.append(" ".join(cells))
    return lines


def _extract_excel_xlsx(file_bytes: bytes) -> List[Dict[str, Any]]:
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as e:
        raise DocumentExtractionError("This Excel file appears to be corrupted or in an unsupported format.") from e

    pages = []
    try:
        for sheet_index, sheet in enumerate(workbook.worksheets, start=1):
            lines = _rows_to_lines(sheet.iter_rows(values_only=True))
            if lines:
                pages.append({"page": sheet_index, "text": "\n".join(lines)})
    finally:
        workbook.close()

    if not pages:
        raise DocumentExtractionError("This Excel file has no readable content in any sheet.")
    return pages


def _extract_excel_xls(file_bytes: bytes) -> List[Dict[str, Any]]:
    try:
        workbook = xlrd.open_workbook(file_contents=file_bytes)
    except Exception as e:
        raise DocumentExtractionError("This .xls file appears to be corrupted or in an unsupported format.") from e

    pages = []
    for sheet_index in range(workbook.nsheets):
        sheet = workbook.sheet_by_index(sheet_index)
        rows = (sheet.row_values(r) for r in range(sheet.nrows))
        lines = _rows_to_lines(rows)
        if lines:
            pages.append({"page": sheet_index + 1, "text": "\n".join(lines)})

    if not pages:
        raise DocumentExtractionError("This .xls file has no readable content in any sheet.")
    return pages


# ----------------------------------------------------------------------
# CSV / TSV
# ----------------------------------------------------------------------

def _decode_text(file_bytes: bytes, what: str) -> str:
    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return file_bytes.decode("latin-1")
        except Exception as e:
            raise DocumentExtractionError(f"This {what}'s text encoding could not be read.") from e


def _extract_delimited(file_bytes: bytes, extension: str) -> List[Dict[str, Any]]:
    text_content = _decode_text(file_bytes, "CSV/TSV file")
    delimiter = "\t" if extension == "tsv" else ","

    try:
        rows = list(csv.reader(io.StringIO(text_content), delimiter=delimiter))
    except csv.Error as e:
        raise DocumentExtractionError("This file could not be parsed as CSV/TSV -- check it's a valid delimited file.") from e

    lines = _rows_to_lines(rows)
    if not lines:
        raise DocumentExtractionError("This file has no readable rows.")
    return [{"page": 1, "text": "\n".join(lines)}]


# ----------------------------------------------------------------------
# Word: .docx via python-docx (real, full-fidelity XML parsing), .doc
# via a documented best-effort fallback -- see _extract_doc_legacy.
# ----------------------------------------------------------------------

def _extract_docx(file_bytes: bytes) -> List[Dict[str, Any]]:
    try:
        document = DocxDocument(io.BytesIO(file_bytes))
    except Exception as e:
        raise DocumentExtractionError("This Word document appears to be corrupted or in an unsupported format.") from e

    lines = [p.text.strip() for p in document.paragraphs if p.text and p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if cells:
                lines.append(" | ".join(cells))

    text = "\n".join(lines)
    if not text.strip():
        raise DocumentExtractionError("This Word document has no readable text.")
    return [{"page": 1, "text": text}]


_PRINTABLE_RUN_RE = re.compile(r"[ -~\n]{4,}")


def _extract_printable_text_runs(stream: bytes) -> str:
    """A well-known, deliberately best-effort technique for legacy .doc text: decode the WordDocument stream as UTF-16LE (how Word 97+ stores most text runs) and keep only printable-ASCII runs of 4+ characters, discarding the surrounding binary formatting/structure noise. Not a real FIB/piece-table parser -- see _extract_doc_legacy for why, and for the honest quality gate this feeds into."""
    try:
        decoded = stream.decode("utf-16-le", errors="ignore")
    except Exception:
        decoded = stream.decode("latin-1", errors="ignore")
    runs = _PRINTABLE_RUN_RE.findall(decoded)
    return "\n".join(run.strip() for run in runs if run.strip())


def _extract_doc_legacy(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Best-effort extraction for the legacy binary .doc format (Word
    97-2003). No full parser for this format is available in this
    environment -- there's no antiword/LibreOffice system binary
    installed (this project has already hit real sudo/install
    constraints on this machine before, see DECISIONS.md's OCR-via-
    conda-forge entry), and no pure-Python library implements the full
    binary Word format (FIB header + piece table) either.

    Uses olefile (pure Python, already a real, maintained library for
    reading OLE2 compound documents -- which a .doc file structurally
    is) to pull the raw `WordDocument` stream, then a printable-text-
    run heuristic to recover readable text from it. This is
    meaningfully lower-fidelity than the real .docx path: it can miss
    some text and occasionally include a short run of coincidental
    binary noise that happens to decode as printable characters.
    Genuinely tested against a real macOS-generated .doc file (via
    `textutil -convert doc`, not a hand-crafted fixture) -- see
    DECISIONS.md for the actual measured result.

    If too little real text comes back to be useful, fails clearly
    with a real, actionable fix (re-save as .docx) rather than
    silently feeding noise into field extraction -- consistent with
    this project's "never guess silently" standard.
    """
    try:
        ole = olefile.OleFileIO(io.BytesIO(file_bytes))
    except Exception as e:
        raise DocumentExtractionError("This .doc file could not be read -- it may be corrupted or in an unsupported format.") from e

    try:
        if not ole.exists("WordDocument"):
            raise DocumentExtractionError("This .doc file doesn't look like a Word document (no WordDocument stream found).")
        stream = ole.openstream("WordDocument").read()
    finally:
        ole.close()

    text = _extract_printable_text_runs(stream)
    if len(text.strip()) < _MIN_LEGACY_DOC_TEXT_LENGTH:
        raise DocumentExtractionError(
            "Couldn't reliably extract text from this legacy .doc file. Please save it "
            "as .docx (File > Save As > Word Document) and upload that instead."
        )
    return [{"page": 1, "text": text}]


# ----------------------------------------------------------------------
# Images -- routed through the exact same OCR machinery scanned PDFs
# already use (PDFExtractor._ocr_page_with_confidence), not a separate
# OCR implementation.
# ----------------------------------------------------------------------

def _extract_image(file_bytes: bytes) -> List[Dict[str, Any]]:
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.load()  # forces full decode now, so a truncated/corrupt file fails here with a clear cause, not later mid-OCR
    except (UnidentifiedImageError, OSError) as e:
        raise DocumentExtractionError("This image file could not be read -- it may be corrupted or in an unsupported format.") from e

    try:
        text, confidence = PDFExtractor()._ocr_page_with_confidence(image)
    except Exception as e:
        logger.exception("OCR failed on an uploaded image")
        raise DocumentExtractionError(
            "OCR failed on this image. Make sure it's a clear, readable photo or scan of a document."
        ) from e

    if not text.strip():
        raise DocumentExtractionError(
            "No readable text was found in this image. Make sure it's a clear photo or "
            "scan of the actual document, not blank or too low-resolution to read."
        )

    page = {"page": 1, "text": text}
    if confidence is not None:
        page["ocr_confidence"] = confidence
    return [page]


# ----------------------------------------------------------------------
# Plain text
# ----------------------------------------------------------------------

def _extract_plain_text(file_bytes: bytes) -> List[Dict[str, Any]]:
    text = _decode_text(file_bytes, "text file")
    if not text.strip():
        raise DocumentExtractionError("This text file is empty.")
    return [{"page": 1, "text": text}]
