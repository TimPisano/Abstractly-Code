"""
Second-opinion OCR for scanned pages that carry their own OCR text layer.

A scanner's OCR layer is what every text reader (and the AI) sees, and it
can misread a table cell ("158" for a printed 156, "1 SIR" for "1 BR").
Nothing in the text says so. This compares that layer with a fresh
tesseract pass at 400 DPI, cell by cell on table rows, and reports where
the two disagree. It never picks one reading over the other: a value read
from a disputed cell keeps its value, drops to low confidence, and gets a
note naming both readings.

    found = second_ocr_disagreements(pdf_bytes, page_numbers)
    checks = flag_ocr_disagreements(program_fields, found)

Only pages that are an image with a text layer are compared; born-digital
pages and pages this module OCR'd itself are skipped.
"""

import io
import logging
import re
from typing import Dict, Iterable, List, Optional

import pdfplumber

from .layout import Word, group_lines
from .values import parse_money

logger = logging.getLogger(__name__)

SECOND_PASS_DPI = 400
MIN_IMAGE_SHARE = 0.6    # an image covering this share of the page = a scan
CELL_GAP = 10.0          # points; words closer than this belong to one cell ("1, 099", "1 BR")
ROW_TOLERANCE = 5.0      # points between the two readings' line centres
NOTE = "Verify against the document."


def _cells(line: List[Word]) -> List[Dict]:
    cells: List[Dict] = []
    for w in line:
        if cells and w.x0 - cells[-1]["x1"] < CELL_GAP:
            cells[-1]["text"] += " " + w.text
            cells[-1]["x1"] = w.x1
        else:
            cells.append({"text": w.text, "x0": w.x0, "x1": w.x1})
    return cells


def _norm(text: str) -> str:
    """Compare readings without the marks OCR layers drop or add: $ , . and spaces."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


NUMBER = re.compile(r"^\$?\s?\d[\d,. ]*$")     # "158", "$1,099", "1, 099"


def _is_number(text: str) -> bool:
    return bool(NUMBER.match(text.strip()))


def _is_table_row(cells: List[Dict]) -> bool:
    """A row of figures: at least two cells that are plain numbers (prose
    with a section number or a ZIP code is not a table row)."""
    return sum(1 for c in cells if _is_number(c["text"])) >= 2


def _competing(original: str, second: str) -> bool:
    """Two readings of one cell that both look like what the cell holds:
    numbers against numbers ("158" / "156"), or a label against a label
    ("1 SIR" / "1 BR"). A number the second pass turned into letters ("4g")
    is that pass failing, not another reading."""
    if _norm(original) == _norm(second):
        return False
    return _is_number(original) == _is_number(second)


def _second_pass(data: bytes, page_no: int, width: float, height: float) -> List[Word]:
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        image = convert_from_bytes(data, dpi=SECOND_PASS_DPI, first_page=page_no, last_page=page_no)[0]
        # one uniform block: keeps a table row on one line
        info = pytesseract.image_to_data(image, config="--psm 6", output_type=pytesseract.Output.DICT)
    except Exception as e:  # tesseract/poppler missing or failed: nothing to compare, not a crash
        logger.warning("Second OCR pass failed on page %d: %s", page_no, type(e).__name__)
        return []
    sx, sy = width / image.width, height / image.height
    return [Word(t.strip(), left * sx, (left + w) * sx, top * sy, (top + h) * sy)
            for t, left, top, w, h in zip(info["text"], info["left"], info["top"], info["width"], info["height"])
            if (t or "").strip()]


def second_ocr_disagreements(data: bytes, page_numbers: Iterable[int]) -> List[Dict]:
    """Table cells where a scanned page's own OCR layer and a 400 DPI pass
    read differently, as {"page", "original", "second", "row_original",
    "row_second"}. Cells only one reading has are skipped, not reported."""
    found: List[Dict] = []
    wanted = set(page_numbers)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            if page_no not in wanted:
                continue
            area = float(page.width) * float(page.height)
            image_area = max((float(i["x1"]) - float(i["x0"])) * (float(i["bottom"]) - float(i["top"]))
                             for i in page.images) if page.images else 0.0
            layer = [Word(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]), float(w["bottom"]))
                     for w in page.extract_words(x_tolerance=2.0, y_tolerance=2.0)]
            if not layer or image_area < MIN_IMAGE_SHARE * area:
                continue
            second_lines = [(sum(w.mid_y for w in ln) / len(ln), _cells(ln))
                            for ln in group_lines(_second_pass(data, page_no, float(page.width), float(page.height)))]
            for line in group_lines(layer):
                cells = _cells(line)
                if not _is_table_row(cells):
                    continue
                mid = sum(w.mid_y for w in line) / len(line)
                match = [c for y, c in second_lines if abs(y - mid) <= ROW_TOLERANCE]
                if len(match) != 1:
                    continue
                other = match[0]
                for cell in cells:
                    overlap = [o for o in other if o["x0"] < cell["x1"] and o["x1"] > cell["x0"]]
                    if len(overlap) == 1 and _competing(cell["text"], overlap[0]["text"]):
                        found.append({"page": page_no, "original": cell["text"], "second": overlap[0]["text"],
                                      "row_original": " ".join(c["text"] for c in cells),
                                      "row_second": " ".join(o["text"] for o in other)})
    return found


def _digits(value) -> Optional[str]:
    """A plain number or amount, normalised ("$1,099.00" -> "1099"); None for anything else."""
    if value is None or not _is_number(str(value)):
        return None
    amount = parse_money(str(value))
    if amount is None:
        return None
    return str(int(amount)) if amount == int(amount) else f"{amount:.2f}"


def flag_ocr_disagreements(fields: Dict[str, Dict], found: List[Dict]) -> List[Dict]:
    """Mark each number read from a disputed cell. Edits confidence and
    notes in place; never changes a value. Returns one check per field."""
    checks: List[Dict] = []
    for name, entry in fields.items():
        mine = _digits(entry.get("value"))
        if mine is None:
            continue
        for d in found:
            if mine not in (_digits(d["original"]), _digits(d["second"])):
                continue
            note = (f"The document's OCR text reads '{d['original']}' here (row: '{d['row_original']}'), "
                    f"but a second OCR pass reads '{d['second']}' (row: '{d['row_second']}'), p.{d['page']}. {NOTE}")
            if note in (entry.get("check_note") or ""):
                break
            entry["confidence"] = "low"
            entry["check_note"] = f"{entry.get('check_note', '')} {note}".strip()
            checks.append({"status": "ocr_disagreement", "fields": [name], "message": note,
                           "citation": "the document's own OCR layer vs a 400 DPI OCR pass"})
            break
    return checks


def pages_to_compare(data: bytes, fields: Dict[str, Dict], min_hits: int = 2) -> List[int]:
    """Pages whose text holds at least `min_hits` of the extracted numbers
    (two digits or more): the pages the table values came from."""
    wanted = {d for d in (_digits(e.get("value")) for e in fields.values()) if d and len(d) >= 2}
    out = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            tokens = {_digits(t) for t in re.findall(r"\$?\d[\d,]*(?:\.\d+)?", page.extract_text() or "")}
            if len(wanted & tokens) >= min_hits:
                out.append(page_no)
    return out
