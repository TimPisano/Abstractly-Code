"""
Words with positions, and reading-order page text.

document_extractor reads PDFs with pypdf, which returns text in
content-stream order. On a filled form, the filled values are usually drawn
after all the printed labels, so each value ends up at the end of the page
text, far from its label. This module keeps every word's position instead:

  - pages with a text layer: pdfplumber words;
  - pages without one (scans): Tesseract words with their boxes,
    converted to PDF points so both sources share one coordinate system.

From the words we rebuild text line by line, left to right, which puts a
value next to the label it sits beside on the page.
"""

import hashlib
import io
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import pdfplumber

from .pii import mask_ssns

logger = logging.getLogger(__name__)

Source = Union[bytes, str]

OCR_DPI = 200            # same as the app's OCR (pdf_extractor); typical scanner resolution, so no upsampling blur
MIN_TEXT_CHARS = 30         # below this a page is treated as a scan and OCR'd
LINE_TOLERANCE = 3.0        # points; words whose vertical centres are this close share a line
REGION_MIN_CONFIDENCE = 60.0   # Tesseract word confidence needed for a re-read box to count
COLUMN_GAP = 18.0          # points; a wider horizontal gap is written as two spaces in page text


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def mid_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def mid_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class PageLayout:
    page: int                       # 1-based
    width: float
    height: float
    words: List[Word] = field(default_factory=list)
    source: str = "text"            # "text" or "ocr"
    ocr_confidence: Optional[float] = None


_CACHE: Dict[str, List[PageLayout]] = {}
_IMAGES: Dict[Tuple[str, int], object] = {}   # (file hash, page) -> rendered page image, for OCR pages


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def ocr_region(source: Source, page_no: int, box: Tuple[float, float, float, float]) -> str:
    """
    Re-OCR one box (x0, top, x1, bottom in PDF points) of a scanned page as a
    single line. Whole-page OCR often drops short values that sit next to
    table rules (a lone "2" under "Number of Bedrooms"); a tight crop read
    on its own usually recovers them. Returns "" if the page wasn't OCR'd.
    """
    data = _bytes(source)
    image = _IMAGES.get((_hash(data), page_no))
    if image is None:
        return ""
    import pytesseract
    pages = _CACHE.get(_hash(data) + ":ocr") or []
    page = next((p for p in pages if p.page == page_no), None)
    if page is None:
        return ""
    sx, sy = image.width / page.width, image.height / page.height
    x0, top, x1, bottom = box
    left, upper = max(0, int(x0 * sx)), max(0, int(top * sy))
    right, lower = min(image.width, int(x1 * sx)), min(image.height, int(bottom * sy))
    if right - left < 8 or lower - upper < 8:   # box off the page or too small to read
        return ""
    crop = image.crop((left, upper, right, lower))
    try:
        info = pytesseract.image_to_data(crop, config="--psm 7", output_type=pytesseract.Output.DICT)
    except Exception as e:
        logger.warning("region OCR failed on page %d: %s", page_no, type(e).__name__)
        return ""
    words = []
    for text, conf in zip(info["text"], info["conf"]):
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            continue
        if (text or "").strip() and conf >= REGION_MIN_CONFIDENCE:
            words.append(text.strip())
    # An empty box's borders and specks OCR as low-confidence junk; only
    # confidently read words count.
    return " ".join(words)


def _bytes(source: Source) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    with open(source, "rb") as f:
        return f.read()


def read_layout(source: Source, *, ocr: bool = True) -> List[PageLayout]:
    """Positioned words for every page. Pages with almost no text layer are
    OCR'd (if `ocr`). Results are cached per file content for the process."""
    data = _bytes(source)
    key = _hash(data) + (":ocr" if ocr else "")
    if key in _CACHE:
        return _CACHE[key]
    _IMAGES.clear()   # page images are kept for the current document only

    from .acroform import appearance_words
    drawn = appearance_words(data)
    pages: List[PageLayout] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            # Values typed over "______" blanks, or over runs of space characters
            # some forms print under their fill areas, would otherwise be chopped
            # up by those glyphs ("_C_ed_a_r_", "1 ,1 6 6"). Neither carries text.
            page = page.filter(lambda o: not (o.get("object_type") == "char"
                                              and (o.get("text") == "_" or (o.get("text") or "").isspace())))
            words = [
                Word(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]), float(w["bottom"]))
                for w in page.extract_words(x_tolerance=2.0, y_tolerance=2.0, keep_blank_chars=False)
            ]
            # Filled boxes some form tools save as a drawing only (no field name or
            # value): place their text where the box is, like printed text.
            words += [Word(text, x0, x1, top, bottom) for text, (x0, top, x1, bottom) in drawn.get(i, [])]
            layout = PageLayout(page=i, width=float(page.width), height=float(page.height), words=words)
            if ocr and sum(len(w.text) for w in words) < MIN_TEXT_CHARS:
                ocr_layout = _ocr_page(data, i, float(page.width), float(page.height))
                if ocr_layout is not None:
                    layout = ocr_layout
            pages.append(layout)
    _CACHE[key] = pages
    return pages


def _ocr_page(data: bytes, page_no: int, width: float, height: float) -> Optional[PageLayout]:
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:  # pragma: no cover - both are app dependencies
        return None
    try:
        images = convert_from_bytes(data, dpi=OCR_DPI, first_page=page_no, last_page=page_no)
        if not images:
            return None
        image = images[0]
        info = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception as e:  # tesseract/poppler missing or failed: no words, not a crash
        logger.warning("OCR failed on page %d: %s", page_no, type(e).__name__)
        return None

    _IMAGES[(_hash(data), page_no)] = image.convert("L")
    sx = width / image.width
    sy = height / image.height
    words, confs = [], []
    for text, conf, left, top, w, h in zip(info["text"], info["conf"], info["left"], info["top"],
                                            info["width"], info["height"]):
        text = (text or "").strip()
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = -1.0
        if not text or conf < 0:
            continue
        words.append(Word(text, left * sx, (left + w) * sx, top * sy, (top + h) * sy))
        confs.append(conf)
    return PageLayout(page=page_no, width=width, height=height, words=words, source="ocr",
                      ocr_confidence=round(sum(confs) / len(confs), 1) if confs else None)


def group_lines(words: List[Word]) -> List[List[Word]]:
    """Words grouped into visual lines, top to bottom, each left to right.
    A word joins the current line when its centre is within tolerance of
    the line's running average centre."""
    lines: List[List[Word]] = []
    centres: List[float] = []
    for w in sorted(words, key=lambda w: (w.mid_y, w.x0)):
        if lines and abs(centres[-1] - w.mid_y) <= LINE_TOLERANCE:
            lines[-1].append(w)
            centres[-1] = sum(x.mid_y for x in lines[-1]) / len(lines[-1])
        else:
            lines.append([w])
            centres.append(w.mid_y)
    for line in lines:
        line.sort(key=lambda w: w.x0)
    return lines


CHAIN_GAP = 14.0   # points; max gap between neighbouring words of one phrase


def chains(words: List[Word]) -> List[List[Word]]:
    """Runs of words that read left to right as one phrase: each next word
    starts just after the previous one ends and overlaps it vertically.
    Unlike fixed horizontal lines, a chain follows a skewed scan's tilt,
    so a label stays in one piece."""
    def overlap(a: Word, b: Word) -> float:
        inter = min(a.bottom, b.bottom) - max(a.top, b.top)
        return inter / max(min(a.bottom - a.top, b.bottom - b.top), 0.1)

    nxt = {}
    for i, a in enumerate(words):
        best = None
        for j, b in enumerate(words):
            if i == j:
                continue
            gap = b.x0 - a.x1
            if -2.0 <= gap <= CHAIN_GAP and overlap(a, b) >= 0.4:
                if best is None or gap < best[0]:
                    best = (gap, j)
        if best is not None:
            nxt[i] = best[1]
    # keep only one predecessor per word (the closest), so chains don't merge
    pred = {}
    for i, j in nxt.items():
        if j not in pred or (words[i].x1 > words[pred[j]].x1):
            pred[j] = i
    nxt = {i: j for j, i in pred.items()}
    out = []
    for start in range(len(words)):
        if start in pred:
            continue
        chain, cur, seen = [], start, set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            chain.append(words[cur])
            cur = nxt.get(cur)
        out.append(chain)
    return out


def line_text(line: List[Word]) -> str:
    parts = []
    prev = None
    for w in line:
        if prev is not None:
            parts.append("  " if w.x0 - prev.x1 > COLUMN_GAP else " ")
        parts.append(w.text)
        prev = w
    return "".join(parts)


def layout_pages(source: Source, *, ocr: bool = True, include_acroform: bool = True) -> List[Dict]:
    """
    Pages in the shape document_extractor.extract_pages returns
    ({"page": n, "text": str, ...}), but with text rebuilt in reading order,
    and (if `include_acroform`) each page's filled form-field values
    appended as "label: value" lines. Drop-in input for FieldExtractor.
    """
    from .acroform import acroform_page_text, read_acroform

    data = _bytes(source)
    acro_text = acroform_page_text(read_acroform(data)) if include_acroform else {}
    out = []
    for p in read_layout(data, ocr=ocr):
        text = "\n".join(line_text(line) for line in group_lines(p.words))
        if acro_text.get(p.page):
            text = (text + "\n" + acro_text[p.page]).strip()
        entry = {"page": p.page, "text": mask_ssns(text)}
        if p.source == "ocr":
            entry["ocr_confidence"] = p.ocr_confidence
        out.append(entry)
    return out
