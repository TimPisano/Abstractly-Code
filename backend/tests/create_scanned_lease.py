"""
Generates a genuinely image-based ("scanned") lease PDF for real OCR
testing: the page is a rendered picture of the lease text (via Pillow),
with NO embedded text layer at all, unlike every other fixture in this
project (which are digitally text-based PDFs from reportlab). PyPDF2
extracts 0 characters from this file — that's the point. It's what
forces pdf_extractor.py's OCR fallback to actually trigger, rather than
exercising the "sparse but nonzero" branch a lightly-populated digital
PDF might.
"""

import os
from PIL import Image, ImageDraw, ImageFont


def create_scanned_lease():
    output_path = os.path.join(os.path.dirname(__file__), "scanned_lease.pdf")

    img = Image.new("RGB", (1700, 2200), color="white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        font_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    except Exception:
        # Fall back to Pillow's built-in bitmap font if no system TTF is
        # found (e.g. non-macOS CI) — OCR accuracy will be worse with it,
        # but the test doesn't require perfection, just that the pipeline
        # runs and finds *something*.
        font = ImageFont.load_default()
        font_bold = font

    lines = [
        ("COMMERCIAL LEASE AGREEMENT", font_bold),
        ("", font),
        ("This Commercial Lease Agreement is made by and between", font),
        ("Riverfront Holdings LLC (\"Landlord\") and Pacific Crest", font),
        ("Trading Co. (\"Tenant\").", font),
        ("", font),
        ("1. PREMISES. The premises are located at 900 Harbor", font),
        ("View Road, Suite 220, Seattle, Washington 98101.", font),
        ("", font),
        ("2. TERM. This Lease shall commence on June 1, 2025,", font),
        ("and shall expire on May 31, 2030.", font),
        ("", font),
        ("3. RENT. Tenant shall pay Base Rent in the amount of", font),
        ("$7,400.00 per month, payable in advance on the first", font),
        ("day of each month.", font),
        ("", font),
        ("4. SECURITY DEPOSIT. Tenant shall deposit with Landlord", font),
        ("the sum of $7,400.00 as a security deposit.", font),
    ]

    y = 100
    for text, f in lines:
        draw.text((100, y), text, fill="black", font=f)
        y += 60

    img.save(output_path, "PDF", resolution=150.0)
    print(f"Created: {output_path}")
    return output_path


if __name__ == "__main__":
    create_scanned_lease()
