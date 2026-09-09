"""
Turn any supported rent-roll file into a plain list of rows
(``List[List[str]]``) -- the ONE shape ``rent_roll_import.parse_rent_
roll_rows`` already consumes. Every format below reduces to that shape
and then flows through the exact same, already-existing, messiness-
tolerant column-header matching and row parsing; nothing here re-
implements any of that.

Formats
-------
============  =====================================================
.csv .tsv     handled directly in rent_roll_import (csv module)
.xlsx .xlsm   handled directly in rent_roll_import (openpyxl)
.xls          this module -- xlrd
.docx         this module -- python-docx, largest table in the doc
.pdf          this module -- pdfplumber tables, then pdfplumber text
              lines, then (no text layer at all) rasterise + OCR
.jpg .jpeg    this module -- OCR, table reconstructed from tesseract
.png .webp        word bounding boxes
.tif .tiff
.bmp
.heic .heif   this module -- decoded via pillow-heif, then OCR
============  =====================================================

Reliability, honestly
---------------------
Structured files (.xls/.docx/.pdf-with-a-real-table) reduce to a table
with essentially no guesswork. The OCR paths (.pdf with no text layer,
and every image format) are genuinely less reliable: tesseract does
not understand table structure, so this module rebuilds the grid from
word pixel positions -- and column alignment, merged cells, and digit
confusion (0/O, 1/l, 5/S, 8/B) are all real, common failure modes on a
photographed or low-DPI-scanned rent roll. See ``report`` in the tests
directory and this module's ``_ocr_words_to_rows`` docstring.

Errors
------
Raises ``RentRollTableError`` (a ``RentRollImportError`` subclass, so
the import route's existing handler catches it) with a specific,
user-facing message whenever a file cannot be reduced to a table --
never a generic failure. Callers should surface ``str(exc)`` directly.
"""
from __future__ import annotations

import io
import logging
from typing import List, Optional

from app.rent_roll_import import RentRollImportError

logger = logging.getLogger(__name__)


class RentRollTableError(RentRollImportError):
    """A specific, user-facing reason this file couldn't be read as a rent-roll table."""


# Extension -> which extractor in this module. .csv/.tsv/.xlsx/.xlsm are
# deliberately NOT here -- rent_roll_import handles those on its own,
# well-tested paths and only delegates the rest here.
EXTRA_TABLE_EXTENSIONS = {
    "xls": "excel_legacy",
    "docx": "word",
    "pdf": "pdf",
    "jpg": "image", "jpeg": "image", "png": "image", "webp": "image",
    "tif": "image", "tiff": "image", "bmp": "image",
    "heic": "image", "heif": "image",
}

# Every extension the rent-roll importer accepts, for the route + the
# frontend accept="" attribute. csv/tsv/xlsx/xlsm + everything above.
ALL_RENT_ROLL_EXTENSIONS = (
    {"csv", "tsv", "xlsx", "xlsm"} | set(EXTRA_TABLE_EXTENSIONS)
)

# A rasterised PDF page beyond this count is refused rather than run
# through OCR -- a 60-page scanned "rent roll" is almost always the
# wrong file, and OCR is slow and expensive per page.
_MAX_OCR_PDF_PAGES = 15


class ExtractedTable:
    """
    rows           every non-empty row, cells already coerced to str
    source_kind    "excel_legacy" | "word" | "pdf-text" | "pdf-ocr" | "image-ocr"
    ocr_confidence tesseract mean word confidence 0-100, or None (non-OCR / nothing read)
    warnings       user-facing caveats to attach to a successful import
    """

    def __init__(self, rows: List[List[str]], source_kind: str,
                 ocr_confidence: Optional[float] = None, warnings: Optional[List[str]] = None):
        self.rows = rows
        self.source_kind = source_kind
        self.ocr_confidence = ocr_confidence
        self.warnings = warnings or []


def _extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower() if filename and "." in filename else ""


def extract_rent_roll_table(file_bytes: bytes, filename: str) -> ExtractedTable:
    """Dispatch on extension. Raises RentRollTableError for anything that can't become a table."""
    if not file_bytes:
        raise RentRollTableError("This file is empty -- there's nothing to import.")

    ext = _extension_of(filename)
    kind = EXTRA_TABLE_EXTENSIONS.get(ext)
    if kind is None:
        raise RentRollTableError(
            f"Can't read a '.{ext or '?'}' file as a rent roll. Supported formats: "
            "CSV, Excel (.xlsx/.xls), Word (.docx), PDF, or an image (.jpg/.png/.heic) of a rent-roll table."
        )

    if kind == "excel_legacy":
        return _extract_xls(file_bytes)
    if kind == "word":
        return _extract_docx(file_bytes)
    if kind == "pdf":
        return _extract_pdf(file_bytes)
    if kind == "image":
        return _extract_image(file_bytes, ext)
    raise RentRollTableError("This file type isn't supported for rent-roll import.")  # unreachable


# ----------------------------------------------------------------------
# .xls  (legacy Excel -- openpyxl can't read these; xlrd 2.x only reads these)
# ----------------------------------------------------------------------

def _extract_xls(file_bytes: bytes) -> ExtractedTable:
    try:
        import xlrd
    except ImportError:  # pragma: no cover - dependency is pinned
        raise RentRollTableError("Legacy .xls files can't be read on this server. Re-save it as .xlsx and upload that.")

    try:
        book = xlrd.open_workbook(file_contents=file_bytes)
    except Exception as exc:
        raise RentRollTableError(
            "This doesn't look like a valid .xls workbook -- it may be corrupted, or it's actually "
            "a different format with an .xls name. Try opening it in Excel and re-saving as .xlsx."
        ) from exc

    best: List[List[str]] = []
    for sheet in book.sheets():
        rows: List[List[str]] = []
        for r in range(sheet.nrows):
            cells = [_xls_cell_to_str(sheet.cell(r, c), book.datemode) for c in range(sheet.ncols)]
            if any(cell.strip() for cell in cells):
                rows.append(cells)
        if len(rows) > len(best):
            best = rows

    if not best:
        raise RentRollTableError("This .xls workbook has no data in any sheet.")
    return ExtractedTable(best, "excel_legacy")


def _xls_cell_to_str(cell, datemode) -> str:
    import xlrd
    if cell.ctype == xlrd.XL_CELL_EMPTY or cell.value is None:
        return ""
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            y, m, d, hh, mm, ss = xlrd.xldate_as_tuple(cell.value, datemode)
            import datetime as _dt
            return _dt.date(y, m, d).strftime("%B %d, %Y")
        except Exception:
            return str(cell.value)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        # 1234.0 -> "1234"; keep real decimals
        return str(int(cell.value)) if float(cell.value).is_integer() else str(cell.value)
    return str(cell.value).strip()


# ----------------------------------------------------------------------
# .docx  (Word) -- the largest real table in the document
# ----------------------------------------------------------------------

def _extract_docx(file_bytes: bytes) -> ExtractedTable:
    try:
        import docx  # python-docx
    except ImportError:  # pragma: no cover
        raise RentRollTableError("Word (.docx) files can't be read on this server right now.")

    try:
        document = docx.Document(io.BytesIO(file_bytes))
    except Exception as exc:
        raise RentRollTableError(
            "This doesn't look like a valid Word document. If it's an old .doc file, open it in Word "
            "and re-save as .docx; otherwise paste the rent roll into a spreadsheet and upload that."
        ) from exc

    tables = document.tables
    if not tables:
        # Maybe someone pasted the rent roll as tab/space-separated text
        # into the body instead of a real Word table.
        body_rows = _text_block_to_rows("\n".join(p.text for p in document.paragraphs))
        if len(body_rows) >= 2 and max(len(r) for r in body_rows) >= 2:
            return ExtractedTable(body_rows, "word",
                                  warnings=["This Word file had no real table -- we read it as "
                                            "tab/space-separated text, which is less reliable. A proper "
                                            "Word table or a spreadsheet imports more cleanly."])
        raise RentRollTableError(
            "This Word document has no table in it. Put the rent roll in an actual Word table "
            "(Insert > Table), or upload it as a spreadsheet, CSV, or PDF instead."
        )

    # Pick the table with the most cells -- a rent roll's data table is
    # essentially always the biggest thing in the doc.
    def _table_rows(t) -> List[List[str]]:
        out = []
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                out.append(cells)
        return out

    candidates = [_table_rows(t) for t in tables]
    best = max(candidates, key=lambda rows: sum(len(r) for r in rows))
    if len(best) < 2:
        raise RentRollTableError(
            "The table in this Word document has no data rows -- just a header, or it's empty."
        )
    return ExtractedTable(best, "word")


# ----------------------------------------------------------------------
# .pdf  -- three tiers: real tables -> text lines -> rasterise + OCR
# ----------------------------------------------------------------------

def _extract_pdf(file_bytes: bytes) -> ExtractedTable:
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        raise RentRollTableError("PDF rent rolls can't be read on this server right now.")

    try:
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception as exc:
        raise RentRollTableError(
            "This file couldn't be opened as a PDF -- it may be corrupted or password-protected."
        ) from exc

    with pdf:
        pages = pdf.pages
        if not pages:
            raise RentRollTableError("This PDF has no pages.")

        # Tier 1: pdfplumber's own table detection (ruled or whitespace-aligned).
        table_rows: List[List[str]] = []
        for page in pages:
            for tbl in (page.extract_tables() or []):
                for row in tbl:
                    cells = [(c or "").strip().replace("\n", " ") for c in row]
                    if any(cells):
                        table_rows.append(cells)
        if _looks_like_a_table(table_rows):
            return ExtractedTable(table_rows, "pdf-text")

        # Tier 2: no ruled table, but there IS a text layer. Reconstruct
        # the grid from each word's real x/y position (same routine the
        # OCR path uses -- here fed EXACT coordinates, not OCR estimates,
        # so it's far more reliable). Handles borderless tables and
        # single-space-separated columns that a naive text split misses.
        word_rows: List[List[str]] = []
        for page in pages:
            words = [
                {"text": w["text"], "left": int(w["x0"]), "top": int(w["top"]),
                 "width": max(1, int(w["x1"] - w["x0"])), "height": max(1, int(w["bottom"] - w["top"]))}
                for w in page.extract_words(use_text_flow=False, keep_blank_chars=False)
            ]
            if words:
                word_rows.extend(_ocr_words_to_rows(words))
        if _looks_like_a_table(word_rows):
            return ExtractedTable(
                word_rows, "pdf-text-reconstructed",
                warnings=["This PDF had no ruled table -- columns were reconstructed from text "
                          "positions. That's usually reliable for an exported table, but a wide "
                          "value can bleed into the next column; spot-check the imported rows."],
            )

        if any((page.extract_text() or "").strip() for page in pages):
            raise RentRollTableError(
                "This PDF has text in it, but nothing that looks like a rent-roll table "
                "(no rows with a tenant name and a rent figure lined up in columns). "
                "If it's a narrative document rather than a table, that's expected."
            )

        # Tier 3: no text layer at all -> scanned/photographed PDF -> OCR.
        if len(pages) > _MAX_OCR_PDF_PAGES:
            raise RentRollTableError(
                f"This looks like a scanned PDF with {len(pages)} pages. We only OCR up to "
                f"{_MAX_OCR_PDF_PAGES} pages of a scanned rent roll -- if this really is one rent roll, "
                "export it to Excel/CSV or split it down to the rent-roll pages."
            )
        return _ocr_pdf_pages(file_bytes, len(pages))


def _ocr_pdf_pages(file_bytes: bytes, page_count: int) -> ExtractedTable:
    try:
        from pdf2image import convert_from_bytes
    except ImportError:  # pragma: no cover
        raise RentRollTableError("This is a scanned PDF, and image conversion isn't available on this server.")

    try:
        images = convert_from_bytes(file_bytes, dpi=300)
    except Exception as exc:
        # Almost always: poppler (pdftoppm) not installed.
        logger.warning("pdf2image failed on a scanned rent roll: %s", exc)
        raise RentRollTableError(
            "This is a scanned PDF (no text layer), and it couldn't be converted to images for OCR "
            "on this server. Export the rent roll to Excel or CSV, or upload the pages as images."
        ) from exc

    all_rows: List[List[str]] = []
    confidences: List[float] = []
    for img in images:
        rows, conf = _ocr_image_to_rows(img)
        all_rows.extend(rows)
        if conf is not None:
            confidences.append(conf)

    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    return _finish_ocr_table(all_rows, mean_conf, "pdf-ocr")


# ----------------------------------------------------------------------
# images -- OCR, table reconstructed from tesseract word bounding boxes
# ----------------------------------------------------------------------

def _extract_image(file_bytes: bytes, ext: str) -> ExtractedTable:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:  # pragma: no cover
        raise RentRollTableError("Image files can't be read on this server right now.")

    if ext in ("heic", "heif"):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception as exc:
            raise RentRollTableError(
                "This is an iPhone HEIC image and HEIC support isn't available on this server. "
                "In Photos, use Share > Options and turn off 'HEIC', or export it as JPG."
            ) from exc

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise RentRollTableError(
            "This image couldn't be read -- it may be corrupted or an unsupported format."
        ) from exc

    rows, conf = _ocr_image_to_rows(image)
    return _finish_ocr_table(rows, conf, "image-ocr")


# ----------------------------------------------------------------------
# OCR core -- word boxes -> rows -> cells
# ----------------------------------------------------------------------

def _ocr_image_to_rows(image):
    """
    Returns (rows, mean_confidence). rows is List[List[str]] reconstructed
    from tesseract's per-word bounding boxes; mean_confidence is the mean
    of tesseract's own 0-100 per-word scores (None if nothing recognised).
    """
    try:
        import pytesseract
    except ImportError:  # pragma: no cover
        raise RentRollTableError("OCR isn't available on this server.")

    # Upscale small images -- tesseract is much worse below ~300 DPI
    # equivalent, and a phone screenshot of a rent roll is often smaller.
    try:
        from PIL import Image
        if max(image.size) < 1800:
            scale = 1800 / max(image.size)
            image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
        if image.mode not in ("L", "RGB"):
            image = image.convert("RGB")
    except Exception:
        pass

    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        # pytesseract.TesseractNotFoundError, or a crash mid-page.
        logger.warning("tesseract failed during rent-roll OCR: %s", exc)
        raise RentRollTableError(
            "OCR couldn't run on this file on this server. If this is a scanned or photographed rent "
            "roll, try exporting it to Excel or CSV from the property-management system instead."
        ) from exc

    words = []
    confidences = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        words.append({
            "text": text.strip(),
            "left": int(data["left"][i]), "top": int(data["top"][i]),
            "width": int(data["width"][i]), "height": int(data["height"][i]),
            "conf": conf,
        })
        if conf >= 0:
            confidences.append(conf)

    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    if not words:
        return [], mean_conf
    return _ocr_words_to_rows(words), mean_conf


def _ocr_words_to_rows(words):
    """
    Rebuild a grid from a flat list of positioned words.

    Rows: cluster words by vertical position -- a word starts a new row
    when its vertical centre is more than ~0.7x the median word height
    below the current row's centre.

    Columns: use the FIRST clustered row (the header, in every real rent
    roll) as the column anchors -- each header word's left edge marks a
    column start. Every later word is assigned to the last anchor at or
    before its own left edge (with a small tolerance), space-joining
    within a cell left-to-right. This is far more stable than a pure
    whitespace-projection method, which wobbles whenever a data value is
    long enough to close a gutter on some rows but not others. If the
    first row has fewer than two words, fall back to projecting word
    spans onto the x-axis and cutting at the widest never-covered gaps.

    This is heuristic and this is where OCR rent rolls get shaky:
      * a data value wider than its column runs into the next cell and
        the two merge
      * a column that's blank for the header (rare) or whose header
        wraps to two lines throws the anchor set off
      * tesseract itself mis-segments ("MacArthur" -> "Mac Arthur",
        "$1,200 3/1/24" glued together) before this code ever sees it
      * a rotated/skewed scan breaks the row clustering outright
    """
    heights = sorted(w["height"] for w in words)
    med_h = heights[len(heights) // 2] or 10
    row_gap = med_h * 0.7

    words.sort(key=lambda w: (w["top"], w["left"]))
    rows_words = []
    current = [words[0]]
    current_center = words[0]["top"] + words[0]["height"] / 2
    for w in words[1:]:
        c = w["top"] + w["height"] / 2
        if abs(c - current_center) > row_gap:
            rows_words.append(current)
            current = [w]
            current_center = c
        else:
            current.append(w)
            current_center = sum(x["top"] + x["height"] / 2 for x in current) / len(current)
    rows_words.append(current)

    # Column anchors from the header row: walk its words left-to-right and
    # start a new column only where the gap from the previous word's END
    # to this word's START exceeds a real gutter (~3 char widths). This
    # keeps multi-word headers ("Lease From", "Monthly Rent") as ONE
    # column instead of splitting on the internal space.
    header = sorted(rows_words[0], key=lambda w: w["left"])
    char_w = max(4.0, med_h * 0.5)
    gutter = char_w * 3.0
    anchors = [header[0]["left"]]
    prev_end = header[0]["left"] + header[0]["width"]
    for w in header[1:]:
        if w["left"] - prev_end > gutter:
            anchors.append(w["left"])
        prev_end = w["left"] + w["width"]

    if len(anchors) < 2:
        return _ocr_words_to_rows_by_projection(rows_words, words, med_h)

    tol = char_w * 2.0  # a data word starting a little left of its header anchor still belongs to it

    def _col_index(word):
        cx = word["left"]
        best = 0
        for j, a in enumerate(anchors):
            if cx >= a - tol:
                best = j
            else:
                break
        return best

    grid = []
    for rw in rows_words:
        cells = [""] * len(anchors)
        for w in sorted(rw, key=lambda x: x["left"]):
            j = _col_index(w)
            cells[j] = (cells[j] + " " + w["text"]).strip() if cells[j] else w["text"]
        if any(cells):
            grid.append(cells)
    return grid


def _ocr_words_to_rows_by_projection(rows_words, words, med_h):
    """Fallback column detection: cut at the widest x-ranges no word ever covers."""
    x_min = int(min(w["left"] for w in words))
    x_max = int(max(w["left"] + w["width"] for w in words))
    covered = bytearray(x_max - x_min + 1)
    for w in words:
        for x in range(w["left"] - x_min, w["left"] + w["width"] - x_min):
            covered[x] = 1
    min_gutter = max(8, int(med_h * 1.2))
    boundaries = [x_min]
    run = 0
    for x in range(len(covered)):
        if covered[x] == 0:
            run += 1
        else:
            if run >= min_gutter:
                boundaries.append(x_min + x - run // 2)
            run = 0
    boundaries.append(x_max + 1)

    def _col_index(word):
        for j in range(len(boundaries) - 1):
            if boundaries[j] <= word["left"] < boundaries[j + 1]:
                return j
        return len(boundaries) - 2

    grid = []
    for rw in rows_words:
        cells = [""] * (len(boundaries) - 1)
        for w in sorted(rw, key=lambda x: x["left"]):
            j = _col_index(w)
            cells[j] = (cells[j] + " " + w["text"]).strip() if cells[j] else w["text"]
        if any(cells):
            grid.append(cells)
    return grid


def _finish_ocr_table(rows: List[List[str]], mean_conf: Optional[float], source_kind: str) -> ExtractedTable:
    if not rows:
        raise RentRollTableError(
            "OCR ran but found no readable text in this file. Make sure it's a clear, straight, "
            "well-lit photo or scan of the actual rent roll -- not blurry, rotated, or cropped."
        )
    if not _looks_like_a_table(rows):
        detail = f" (average text confidence {mean_conf}%)" if mean_conf is not None else ""
        raise RentRollTableError(
            "We read text from this file but it doesn't look like a rent-roll table -- we couldn't find "
            f"rows that line up into columns with a tenant name and a rent figure{detail}. "
            "If this is a photo of something else, that's why. If it really is a rent roll, a clearer "
            "image or an exported spreadsheet will work much better."
        )

    warnings = [
        "This was read by OCR from a scan/photo. OCR misreads digits (0/O, 1/l, 5/S) and can merge or "
        "split columns -- every imported row should be spot-checked against the original before you rely on it."
    ]
    if mean_conf is not None and mean_conf < 75:
        warnings.append(
            f"OCR text confidence was low ({mean_conf}%). Expect several wrong values -- a clearer "
            "image or an exported spreadsheet is strongly recommended."
        )
    return ExtractedTable(rows, source_kind, ocr_confidence=mean_conf, warnings=warnings)


# ----------------------------------------------------------------------
# shared helpers
# ----------------------------------------------------------------------

def _text_block_to_rows(text: str) -> List[List[str]]:
    """Split a block of text into rows: one row per line, cells split on runs of 2+ spaces or a tab."""
    import re
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cells = [c.strip() for c in re.split(r"\t|\s{2,}", line.strip())]
        rows.append([c for c in cells if c != ""] or [line.strip()])
    return rows


def _looks_like_a_table(rows: List[List[str]]) -> bool:
    """
    A cheap sanity gate before handing off: at least 2 rows, a modal row
    width of 2+ columns, and at least one row that has both something
    word-like and something digit-like (a tenant + a number). Real
    column-matching still happens downstream in rent_roll_import; this
    only rejects obvious non-tables (a photo of a resume, a blank scan,
    a prose paragraph) with a clear message instead of a confusing
    "no recognizable columns" further down.
    """
    import re
    non_trivial = [r for r in rows if len([c for c in r if c.strip()]) >= 2]
    if len(non_trivial) < 2:
        return False
    has_wordy_and_numeric_row = any(
        any(re.search(r"[A-Za-z]{3,}", c) for c in r) and any(re.search(r"\d", c) for c in r)
        for r in non_trivial
    )
    return has_wordy_and_numeric_row
