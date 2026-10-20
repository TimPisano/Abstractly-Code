"""
Fill a blank public form with sample values and write its answer key.

A spec (see specs/*.py) names a blank source PDF in sources/, the values to
place on it, and the answer key. Each placement puts one string on one page,
located one of three ways:

  {"acro": "FieldName"}                  inside an AcroForm widget's own box
  {"anchor": "Label text", "page": 1}    next to (or below) printed label text
  {"at": (x, top), "page": 1}            absolute, in pdfplumber coordinates
                                         (points from the page's top-left)

Optional keys: "occurrence" (nth match of the anchor, 1-based), "where"
("right" default, or "below"), "dx"/"dy" offsets, "size" (font points).

The output is flattened: values are drawn into the page content and the
form widgets are removed, like a filled form printed to PDF. That's the
shape owners actually upload, and it means the text layer is what our
extractor sees.
"""

import io
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
SAMPLES = HERE / "samples"

FONT = "Helvetica"
DEFAULT_SIZE = 9.0
VALUE_TYPES = {"text", "money", "date", "int", "pct", "checkbox"}


class SpecError(Exception):
    pass


def _widgets(reader: PdfReader) -> Dict[str, List[Tuple[int, List[float]]]]:
    """AcroForm field name -> [(page_index, [x0, y0, x1, y1])], PDF coordinates."""
    out: Dict[str, List[Tuple[int, List[float]]]] = defaultdict(list)
    for i, page in enumerate(reader.pages):
        for annot in page.get("/Annots") or []:
            a = annot.get_object()
            if a.get("/Subtype") != "/Widget":
                continue
            name = a.get("/T")
            if name is None and a.get("/Parent") is not None:
                name = a["/Parent"].get_object().get("/T")
            if name is None:
                continue
            out[str(name)].append((i, [float(v) for v in a["/Rect"]]))
    return out


def _anchor_box(page, phrase: str, occurrence: int) -> Dict[str, float]:
    matches = page.search(phrase, regex=False, case=True)
    if len(matches) < occurrence:
        matches = page.search(phrase, regex=False, case=False)
    if len(matches) < occurrence:
        raise SpecError(f"anchor {phrase!r} occurrence {occurrence} not found on page {page.page_number} "
                        f"({len(matches)} match(es))")
    return matches[occurrence - 1]


def _resolve(placement: Dict[str, Any], widgets, plumber_pdf, page_heights) -> Tuple[int, float, float, float]:
    """-> (page_index, x, baseline_y in PDF coordinates, font size)"""
    size = float(placement.get("size", DEFAULT_SIZE))
    dx, dy = float(placement.get("dx", 0)), float(placement.get("dy", 0))
    if "acro" in placement:
        hits = widgets.get(placement["acro"])
        if not hits:
            raise SpecError(f"AcroForm field {placement['acro']!r} not found")
        page_i, (x0, y0, x1, y1) = hits[placement.get("index", 0)]
        size = min(size, max(y1 - y0 - 2, 5))
        # Tall boxes carry their printed label inside the top of the box,
        # so write near the bottom; short ones get vertically centred.
        baseline = y0 + 4 if (y1 - y0) > 18 else y0 + (y1 - y0 - size) / 2 + 1.5
        return page_i, x0 + 2 + dx, baseline - dy, size
    page_i = int(placement["page"]) - 1
    height = page_heights[page_i]
    if "at" in placement:
        x, top = placement["at"]
        return page_i, x + dx, height - top - size - dy, size
    box = _anchor_box(plumber_pdf.pages[page_i], placement["anchor"], int(placement.get("occurrence", 1)))
    if placement.get("where", "right") == "below":
        x, top = box["x0"] + dx, box["bottom"] + 2 + dy
    else:
        x, top = box["x1"] + 4 + dx, box["top"] + dy
    return page_i, x, height - top - size, size


def _fits_text(value: str) -> str:
    return value.replace("\n", " ")


def build(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Write samples/<id>.pdf and samples/<id>.answer_key.json. Returns the answer key."""
    doc_id = spec["id"]
    src = SOURCES / spec["source"]
    _validate(spec)

    reader = PdfReader(str(src))
    widgets = _widgets(reader)
    page_heights = [float(p.mediabox.height) for p in reader.pages]
    for p in reader.pages:
        if float(p.mediabox.left) != 0 or float(p.mediabox.bottom) != 0:
            raise SpecError(f"{doc_id}: page mediabox not at origin; coordinates would be off")

    draws: Dict[int, List[Tuple[float, float, str, float]]] = defaultdict(list)
    with pdfplumber.open(str(src)) as plumber_pdf:
        for placement in spec["placements"]:
            page_i, x, y, size = _resolve(placement, widgets, plumber_pdf, page_heights)
            draws[page_i].append((x, y, _fits_text(placement["text"]), size))

    writer = PdfWriter(clone_from=reader)
    for page_i, items in draws.items():
        page = writer.pages[page_i]
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        for x, y, text, size in items:
            c.setFont(FONT, size)
            c.drawString(x, y, text)
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    _flatten(writer)
    writer.add_metadata({"/Title": f"SYNTHETIC SAMPLE - {spec['form']}",
                         "/Subject": "Fictional values for extraction evals. Not a real filing."})

    SAMPLES.mkdir(exist_ok=True)
    with open(SAMPLES / f"{doc_id}.pdf", "wb") as f:
        writer.write(f)

    key = {
        "id": doc_id,
        "form": spec["form"],
        "program": spec["program"],
        "doc_type": spec["doc_type"],
        "source_file": f"sources/{spec['source']}",
        "sample_file": f"samples/{doc_id}.pdf",
        "synthetic": True,
        "notes": spec.get("notes", ""),
        "lease_fields": spec["lease_fields"],
        "program_fields": spec["program_fields"],
    }
    with open(SAMPLES / f"{doc_id}.answer_key.json", "w") as f:
        json.dump(key, f, indent=2)
        f.write("\n")
    return key


def _flatten(writer: PdfWriter) -> None:
    """Drop form widgets and the AcroForm so only drawn content remains."""
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        keep = [a for a in annots if a.get_object().get("/Subtype") != "/Widget"]
        if keep:
            page[NameObject("/Annots")] = ArrayObject(keep)
        else:
            del page["/Annots"]
    if "/AcroForm" in writer._root_object:
        del writer._root_object["/AcroForm"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", s.lower())


def _validate(spec: Dict[str, Any]) -> None:
    """Every answer-key value must actually be written on the page somewhere."""
    for key in ("id", "source", "form", "program", "doc_type", "placements", "lease_fields", "program_fields"):
        if key not in spec:
            raise SpecError(f"spec missing {key!r}")
    placed = " ".join(_norm(p["text"]) for p in spec["placements"])
    for name, entry in spec["program_fields"].items():
        if entry.get("type") not in VALUE_TYPES:
            raise SpecError(f"{spec['id']}.{name}: bad type {entry.get('type')!r}")
        if entry["type"] == "checkbox":
            continue
        shown = entry.get("shown_as", entry["value"])
        if _norm(str(shown)) not in placed:
            raise SpecError(f"{spec['id']}.{name}: value {shown!r} is in the key but never placed")
    for name, value in spec["lease_fields"].items():
        if value is not None and _norm(str(value)) not in placed and name not in spec.get("lease_fields_unplaced_ok", ()):
            raise SpecError(f"{spec['id']}.lease_fields.{name}: {value!r} never placed")
