"""
Tests for app/affordable/ocr_check.py: a scanned PDF's own OCR text layer is
compared with a second OCR pass at 400 DPI, and a table value read from a
cell where the two disagree is marked low confidence. Neither reading is
picked over the other, and no value is changed. The fixture is a page image
of a fictional rent table under a hidden text layer that misreads two cells,
the way a scanner's OCR layer does. Needs tesseract (see CLAUDE.md).

Run: python backend/tests/test_affordable_ocr_check.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import copy
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pdf2image import convert_from_bytes
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.affordable.ocr_check import flag_ocr_disagreements, second_ocr_disagreements

# (x, cells as printed, cells as the scanner's text layer read them)
COLUMNS = (72, 180, 280, 380, 480)
PRINTED = [("156", "1 BR", "$767", "$75", "$842"), ("102", "2 BR", "$979", "$120", "$1,099")]
LAYER = [("158", "1 SIR", "767", "75", "842"), ("102", "2 BR", "979", "120", "1, 099")]
ROW_Y = (600, 580)


def _scanned_pdf():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 640, "Number of Contract Units   Bedrooms   Contract Rent   Utility Allowance   Gross Rent")
    for y, row in zip(ROW_Y, PRINTED):
        for x, cell in zip(COLUMNS, row):
            c.drawString(x, y, cell)
    c.save()
    image = convert_from_bytes(buf.getvalue(), dpi=200)[0]

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(612, 792))
    c.drawImage(ImageReader(image), 0, 0, width=612, height=792)
    text = c.beginText()
    text.setTextRenderMode(3)             # invisible, like a scanner's OCR layer
    text.setFont("Helvetica", 12)
    for y, row in zip(ROW_Y, LAYER):
        for x, cell in zip(COLUMNS, row):
            text.setTextOrigin(x, y)
            text.textOut(cell)
    c.drawText(text)
    c.save()
    return out.getvalue()


def _f(value):
    return {"value": value, "source": {"page": 1, "quote": value}, "confidence": "medium", "method": "ai"}


def test_cells_where_the_two_ocr_readings_disagree_are_found():
    found = second_ocr_disagreements(_scanned_pdf(), [1])
    pairs = {(d["original"], d["second"]) for d in found}
    assert ("158", "156") in pairs, found
    assert ("1 SIR", "1 BR") in pairs, found
    assert not any(d["original"] in ("767", "102", "1, 099") for d in found), found


def test_a_value_from_a_disputed_cell_is_flagged_and_kept():
    fields = {"contract_units_0br": _f("158"), "contract_rent_0br": _f("$767"), "contract_units_2br": _f("102")}
    before = {k: v["value"] for k, v in fields.items()}
    checks = flag_ocr_disagreements(fields, second_ocr_disagreements(_scanned_pdf(), [1]))
    assert {k: v["value"] for k, v in fields.items()} == before          # values never change
    units = fields["contract_units_0br"]
    assert units["confidence"] == "low"
    assert "158" in units["check_note"] and "156" in units["check_note"]
    assert "Verify against the document" in units["check_note"]
    assert fields["contract_rent_0br"]["confidence"] == "medium"
    assert fields["contract_units_2br"]["confidence"] == "medium"
    assert [c["fields"] for c in checks] == [["contract_units_0br"]]


def test_a_page_without_an_image_is_not_compared():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.drawString(72, 600, "158   1 BR   $767")
    c.save()
    assert second_ocr_disagreements(buf.getvalue(), [1]) == []


def test_flagging_twice_adds_the_note_once():
    fields = {"contract_units_0br": _f("158")}
    found = [{"page": 1, "original": "158", "second": "156", "row_original": "158 1 SIR", "row_second": "156 1 BR"}]
    flag_ocr_disagreements(fields, found)
    once = copy.deepcopy(fields)
    flag_ocr_disagreements(fields, found)
    assert fields == once



def test_prose_ids_and_failed_readings_are_not_disputes():
    """Regression: on real scans a contract number matched '24' in a prose
    line about 24 CFR, and a second pass that read '49' as '4g' counted as a
    competing value."""
    fields = {"contract_number": _f("ZZ24E000008"), "contract_units_2br": _f("49"), "initial_term": _f("20 years")}
    found = [{"page": 1, "original": "or 24 CFR, Part 24.", "second": "or 24 CFR Part 24", "row_original": "x",
              "row_second": "y"},
             {"page": 1, "original": "20", "second": "26", "row_original": "x", "row_second": "y"}]
    assert flag_ocr_disagreements(fields, found) == []
    assert all(v["confidence"] == "medium" for v in fields.values())
    from app.affordable.ocr_check import _competing, _is_table_row
    assert not _competing("49", "4g") and _competing("158", "156") and _competing("1 SIR", "1 BR")
    assert not _is_table_row([{"text": "debarment as provided in 29 CFR, section 5."}, {"text": "6,"}])
    assert not _is_table_row([{"text": "Address: 24550 & 24570 Cottonwood"}, {"text": "Moreno Vallev 92553"}])


if __name__ == "__main__":
    test_cells_where_the_two_ocr_readings_disagree_are_found()
    test_a_value_from_a_disputed_cell_is_flagged_and_kept()
    test_a_page_without_an_image_is_not_compared()
    test_flagging_twice_adds_the_note_once()
    test_prose_ids_and_failed_readings_are_not_disputes()
    print("\nAll second-OCR comparison tests passed.")
