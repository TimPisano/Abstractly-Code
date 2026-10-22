"""
Holdout copies of every sample, to keep form mappings honest.

The form mappings in backend/app/affordable/ are written by looking at the
same blank forms the samples were built on, so scoring them only on
samples/<id>.pdf would flatter them. The holdout uses the same answer keys
but draws every value differently:

  - shifted a few points in x and y,
  - in a different font (Helvetica, Times or Courier) and size,
  - with dates and money amounts reformatted ("December 1, 2026",
    "1325.00", ...).

  python -I tests/eval/affordable/make_holdout.py           # all specs
  python -I tests/eval/affordable/make_holdout.py tic_sc

Writes samples/<id>.holdout.pdf. Deterministic (seeded per document).
Mapping authors: don't tune against these files; they're for the final
measurement.
"""

import copy
import io
import random
import re
import sys
import zlib
from collections import defaultdict
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_samples import load_specs  # noqa: E402
from fill_lib import SAMPLES, SOURCES, _flatten, _resolve, _widgets  # noqa: E402

FONTS = ("Helvetica", "Times-Roman", "Courier")
JITTER = 2.5          # points, either way
SIZE_RANGE = (0.85, 1.12)
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
MONEY_RE = re.compile(r"^\$?(\d{1,3}(?:,\d{3})*|\d+)(\.\d{2})?$")


def reformat(text: str, rng: random.Random) -> str:
    m = DATE_RE.match(text.strip())
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), m.group(3)
        style = rng.randrange(4)
        if style == 0:
            return f"{MONTHS[mo - 1]} {d}, {y}"
        if style == 1:
            return f"{MONTHS[mo - 1][:3]}. {d}, {y}"
        if style == 2:
            return f"{mo}/{d}/{y}"
        return text
    m = MONEY_RE.match(text.strip())
    if m and ("," in text or "$" in text or "." in text):
        whole = int(m.group(1).replace(",", ""))
        cents = m.group(2) or ""
        style = rng.randrange(4)
        if style == 0:
            return f"{whole}{cents or '.00'}"
        if style == 1:
            return f"${whole:,}{cents}"
        if style == 2:
            return f"{whole:,}"
        return text
    return text


def build_holdout(spec) -> Path:
    rng = random.Random(zlib.crc32(("holdout:" + spec["id"]).encode()))
    src = SOURCES / spec["source"]
    reader = PdfReader(str(src))
    widgets = _widgets(reader)
    heights = [float(p.mediabox.height) for p in reader.pages]
    font = FONTS[rng.randrange(len(FONTS))]

    draws = defaultdict(list)
    with pdfplumber.open(str(src)) as plumber_pdf:
        for placement in spec["placements"]:
            p = copy.deepcopy(placement)
            p["size"] = float(p.get("size", 9.0)) * rng.uniform(*SIZE_RANGE)
            page_i, x, y, size = _resolve(p, widgets, plumber_pdf, heights)
            x += rng.uniform(-JITTER, JITTER)
            y += rng.uniform(-JITTER, JITTER)
            draws[page_i].append((x, y, reformat(p["text"], rng), size))

    writer = PdfWriter(clone_from=reader)
    for page_i, items in draws.items():
        page = writer.pages[page_i]
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
        for x, y, text, size in items:
            c.setFont(font, size)
            c.drawString(x, y, text)
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    _flatten(writer)
    writer.add_metadata({"/Title": f"SYNTHETIC HOLDOUT - {spec['form']}",
                         "/Subject": "Fictional values for extraction evals. Not a real filing."})
    out = SAMPLES / f"{spec['id']}.holdout.pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out


def main(argv):
    for spec in load_specs(set(argv) or None):
        out = build_holdout(spec)
        print(out.relative_to(HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
