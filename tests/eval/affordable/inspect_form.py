"""
Help write a spec: list a blank form's AcroForm fields with the printed
label nearest each one, or dump a page's text lines with coordinates.

  python -I inspect_form.py fields sources/hud_52517_rfta.pdf
  python -I inspect_form.py lines  sources/tic_sc.pdf 1

Coordinates are pdfplumber's: x from the left edge, top from the top edge.
"""

import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fill_lib import _widgets  # noqa: E402
from pypdf import PdfReader  # noqa: E402


def _label_for(words, x0, top, bottom):
    """Closest words on the same line to the left, else the line just above."""
    mid = (top + bottom) / 2
    left = [w for w in words if w["x1"] <= x0 + 2 and w["top"] - 3 <= mid <= w["bottom"] + 3]
    if left:
        left.sort(key=lambda w: w["x1"])
        return "L: " + " ".join(w["text"] for w in left[-6:])
    above = [w for w in words if w["bottom"] <= top + 1 and top - w["bottom"] < 14 and w["x0"] < x0 + 120 and w["x1"] > x0 - 40]
    if above:
        above.sort(key=lambda w: (w["top"], w["x0"]))
        return "A: " + " ".join(w["text"] for w in above[-8:])
    return "?"


def fields(path):
    reader = PdfReader(path)
    with pdfplumber.open(path) as pdf:
        for name, hits in sorted(_widgets(reader).items(), key=lambda kv: (kv[1][0][0], -kv[1][0][1][3], kv[1][0][1][0])):
            for page_i, (x0, y0, x1, y1) in hits:
                page = pdf.pages[page_i]
                h = float(page.height)
                top, bottom = h - y1, h - y0
                words = page.extract_words()
                print(f"p{page_i + 1} {name!r:42} x={x0:6.1f} top={top:6.1f} w={x1 - x0:5.1f} h={y1 - y0:4.1f}  {_label_for(words, x0, top, bottom)}")


def lines(path, page_no):
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[int(page_no) - 1]
        for line in page.extract_text_lines():
            print(f"x={line['x0']:6.1f} top={line['top']:6.1f} x1={line['x1']:6.1f}  {line['text']}")


def render(path, out_dir, *pages):
    """Write page PNGs for a visual check (put out_dir outside the repo)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    wanted = [int(p) for p in pages] or range(1, len(pdf) + 1)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for n in wanted:
        img = pdf[n - 1].render(scale=1.6).to_pil()
        target = out / f"{Path(path).stem}_p{n}.png"
        img.save(target)
        print(target)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"fields": fields, "lines": lines, "render": render}[cmd](*args)
