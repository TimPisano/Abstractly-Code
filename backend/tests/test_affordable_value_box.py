"""
Tests for the second reading of a scanned form's typed values: on an OCR'd
page, each money / number / date box is read again on its own at 400 DPI.
Where the two readings disagree, the page reading stays, at low confidence,
with both readings named. Where the page found nothing, the box reading
fills the gap at low confidence. Fixtures are rendered in-test (reportlab ->
image-only PDF); fictional values only. Needs tesseract (see CLAUDE.md).

Run: python backend/tests/test_affordable_value_box.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import io
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pdf2image import convert_from_bytes
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.affordable import extract
from app.affordable.forms.base import Anchor, FormSpec, Rule
from app.affordable.layout import ocr_value_box

SPEC = FormSpec(id="zz_rent", name="test rent form", doc_kind="tic", program="LIHTC",
                detect=(("EXAMPLE RENT CERTIFICATION", 2.0),),
                rules=(Rule("tenant_rent", "money", anchors=(Anchor("Tenant Rent:", (-2, -6, 110, 9)),)),))


def _scan(value="$1,166", speckles=0):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 720, "EXAMPLE RENT CERTIFICATION")
    c.setFont("Courier", 11)
    c.drawString(72, 600, "Tenant Rent:")
    if value:
        c.drawString(160, 600, value)
    for i in range(14):    # body text, so the page reads like a form
        c.drawString(72, 560 - 14 * i, "The household certifies the information on this form is true.")
    c.save()
    image = convert_from_bytes(buf.getvalue(), dpi=200, grayscale=True)[0]
    rnd = random.Random(7)
    px = image.load()
    for _ in range(speckles):             # scanner dust
        x, y = rnd.randrange(image.width), rnd.randrange(image.height)
        px[x, y] = 0
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(612, 792))
    c.drawImage(ImageReader(image), 0, 0, width=612, height=792)
    c.save()
    return out.getvalue()


def test_a_speckled_value_box_is_read():
    """Regression: on a dusty scan a box read on its own came back empty ('')
    until the specks were filtered out."""
    data = _scan(speckles=20000)   # unfiltered, this reads as ""
    # box around "$1,166": x 160..214, baseline 600 from the bottom -> top ~181
    assert ocr_value_box(data, 1, (150, 178, 230, 196), "money").replace(" ", "") == "$1,166"


def test_two_readings_that_disagree_keep_the_page_value_and_flag_it():
    data = _scan()
    real = extract.ocr_value_box
    extract.ocr_value_box = lambda *a, **k: "$4,166"
    try:
        f = extract.extract_document(data, forms=[SPEC])["program_fields"]["tenant_rent"]
    finally:
        extract.ocr_value_box = real
    assert f["value"] == "$1,166.00"
    assert f["confidence"] == "low"
    assert "$1,166" in f["check_note"] and "$4,166" in f["check_note"]
    assert "Verify against the document" in f["check_note"]


def test_two_readings_that_agree_change_nothing():
    data = _scan()
    f = extract.extract_document(data, forms=[SPEC])["program_fields"]["tenant_rent"]
    assert f["value"] == "$1,166.00" and f["confidence"] == "medium" and "check_note" not in f


def test_the_box_reading_fills_a_value_the_page_missed():
    data = _scan(value="")
    real_box, real_region = extract.ocr_value_box, extract.ocr_region
    extract.ocr_value_box = lambda *a, **k: "$1,166"
    extract.ocr_region = lambda *a, **k: ""
    try:
        f = extract.extract_document(data, forms=[SPEC])["program_fields"]["tenant_rent"]
    finally:
        extract.ocr_value_box, extract.ocr_region = real_box, real_region
    assert f["value"] == "$1,166.00"
    assert f["confidence"] == "low" and "Verify against the document" in f["check_note"]


if __name__ == "__main__":
    test_a_speckled_value_box_is_read()
    test_two_readings_that_disagree_keep_the_page_value_and_flag_it()
    test_two_readings_that_agree_change_nothing()
    test_the_box_reading_fills_a_value_the_page_missed()
    print("\nAll value-box second-reading tests passed.")
