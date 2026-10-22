"""
Make a "scanned" copy of each synthetic sample: every page rendered to a
grayscale image with a slight skew and speckle, saved as an image-only PDF
(no text layer). That forces our pipeline down its OCR fallback, which is
how most real tenant files arrive.

  python -I tests/eval/affordable/make_scans.py            # all samples
  python -I tests/eval/affordable/make_scans.py tic_sc

Writes samples/<id>.scan.pdf next to samples/<id>.pdf. Deterministic
(seeded per document), so re-running gives the same files.
"""

import random
import sys
import zlib
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples"

DPI = 200          # a typical office scanner setting
SKEW_DEG = 0.6     # max rotation either way
SPECKLE = 0.0015   # fraction of pixels flipped to dark


def scan_page(page, rng: random.Random) -> Image.Image:
    img = page.render(scale=DPI / 72).to_pil().convert("L")
    img = img.rotate(rng.uniform(-SKEW_DEG, SKEW_DEG), resample=Image.BICUBIC, expand=False, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    px = img.load()
    w, h = img.size
    for _ in range(int(w * h * SPECKLE)):
        px[rng.randrange(w), rng.randrange(h)] = rng.randrange(40, 140)
    # scanners clip to near-black/near-white; this also drops the light gray fills
    return img.point(lambda v: 0 if v < 150 else 255).convert("L")


def make_scan(src: Path) -> Path:
    rng = random.Random(zlib.crc32(src.stem.encode()))
    pdf = pdfium.PdfDocument(str(src))
    images = [scan_page(pdf[i], rng) for i in range(len(pdf))]
    # <id>.pdf -> <id>.scan.pdf ; <id>.holdout.pdf -> <id>.holdout_scan.pdf
    base = src.name[: -len(".pdf")]
    name = f"{base[: -len('.holdout')]}.holdout_scan.pdf" if base.endswith(".holdout") else f"{base}.scan.pdf"
    out = src.with_name(name)
    images[0].save(out, "PDF", resolution=DPI, save_all=True, append_images=images[1:])
    return out


def main(argv):
    """Scans the clean samples and, when present, the holdout copies."""
    wanted = set(argv)
    sources = [p for p in sorted(SAMPLES.glob("*.pdf"))
               if p.name.count(".") == 1 or p.name.endswith(".holdout.pdf")]
    if wanted:
        sources = [p for p in sources if p.name.split(".")[0] in wanted]
    for src in sources:
        out = make_scan(src)
        print(f"{out.relative_to(HERE)}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
