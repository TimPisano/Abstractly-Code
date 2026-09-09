"""
Multi-format rent-roll import: every format reduces to the same
(headers, rows) table and flows through the one existing column-matching
/ row-parsing pipeline (parse_rent_roll_rows). These tests exercise the
new .xls / .docx / .pdf / image paths and the specific-error contract
for files that genuinely aren't tabular.

The OCR paths (scanned PDF, images) need a `tesseract` binary. Where it
isn't installed, the image test asserts the CLEAN failure message
instead, and the grid-reconstruction algorithm is tested directly with
synthetic word boxes (no tesseract needed).
"""
import io
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.rent_roll_import import parse_rent_roll_file, RentRollImportError
from app.rent_roll_table_extract import _ocr_words_to_rows, RentRollTableError

HEADER = ["Unit", "Tenant", "Unit SF", "Lease From", "Lease To", "Market Rent", "Monthly Rent", "Annual Rent"]
DATA = [
    ["101", "Blue Bottle Coffee", "1,450", "03/01/2023", "02/28/2028", "7,200", "6,180", "74,160"],
    ["102", "Meridian Dental Associates PLLC", "2,100", "06/15/2021", "06/14/2028", "9,900", "9,724", "116,688"],
    ["103", "VACANT", "980", "", "", "5,400", "0", "0"],
    ["104", "Sunrise Bagel Co.", "1,200", "September 1, 2021", "August 31, 2027", "6,000", "5,568", "66,816"],
    ["Total", "", "16,000", "", "", "62,400", "51,522", "618,264"],
]
ADDR = "1 Meridian Plaza, Portland, OR 97204"

_HAS_TESSERACT = shutil.which("tesseract") is not None


def _tenants(result):
    return {l["extracted_fields"]["tenant"]["value"] for l in result["leases"]}


def _rents(result):
    return {l["extracted_fields"]["tenant"]["value"]: l["extracted_fields"]["rent_amount"]["value"]
            for l in result["leases"]}


# ----------------------------------------------------------------------
# structured formats -- must all yield the identical parse
# ----------------------------------------------------------------------

def _expected_ok(result):
    assert result["column_mapping"].get("rent_amount") == 6, "must map Monthly Rent, not Market/Annual"
    assert result["column_mapping"].get("tenant") == 1
    assert len(result["leases"]) == 4  # VACANT + Total skipped
    assert _tenants(result) == {
        "Blue Bottle Coffee", "Meridian Dental Associates PLLC", "Sunrise Bagel Co.", "The Corner Bookshop LLC",
    } or _tenants(result) == {
        "Blue Bottle Coffee", "Meridian Dental Associates PLLC", "Sunrise Bagel Co.",
    }
    rents = _rents(result)
    assert rents["Blue Bottle Coffee"] == "$6,180.00"
    assert rents["Meridian Dental Associates PLLC"] == "$9,724.00"


DATA_5 = DATA[:2] + [DATA[2]] + [DATA[3]] + [
    ["105", "The Corner Bookshop LLC", "1,050", "05/01/2023", "04/30/2028", "4,100", "3,900", "46,800"],
    DATA[4],
]


def test_xlsx_baseline():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in [["Meridian Plaza"], []] + [HEADER] + DATA_5:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    result = parse_rent_roll_file(buf.getvalue(), "rr.xlsx", ADDR)
    assert result["source_kind"] == "excel"
    _expected_ok(result)
    assert result["warnings"] == []


def test_xls_legacy_via_xlrd():
    xlwt = pytest.importorskip("xlwt")
    book = xlwt.Workbook()
    sheet = book.add_sheet("Rent Roll")
    for ri, row in enumerate([["Meridian Plaza"], []] + [HEADER] + DATA_5):
        for ci, val in enumerate(row):
            sheet.write(ri, ci, val)
    buf = io.BytesIO()
    book.save(buf)
    result = parse_rent_roll_file(buf.getvalue(), "rr.xls", ADDR)
    assert result["source_kind"] == "excel_legacy"
    _expected_ok(result)


def test_docx_table():
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("Meridian Plaza Rent Roll")
    t = d.add_table(rows=0, cols=len(HEADER))
    for row in [HEADER] + DATA_5:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v)
    buf = io.BytesIO()
    d.save(buf)
    result = parse_rent_roll_file(buf.getvalue(), "rr.docx", ADDR)
    assert result["source_kind"] == "word"
    _expected_ok(result)


def test_tsv():
    body = "\n".join("\t".join(r) for r in [["Meridian Plaza"], []] + [HEADER] + DATA_5)
    result = parse_rent_roll_file(body.encode(), "rr.tsv", ADDR)
    assert result["source_kind"] == "delimited"
    _expected_ok(result)


def test_pdf_text_layer_gridded_table():
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    buf = io.BytesIO()
    tbl = Table([HEADER] + DATA_5, repeatRows=1)
    # A ruled table -- what every PMS PDF export actually looks like.
    # pdfplumber's table detection keys off the ruling lines.
    tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                             ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    SimpleDocTemplate(buf, pagesize=landscape(letter)).build([tbl])
    result = parse_rent_roll_file(buf.getvalue(), "rr.pdf", ADDR)
    assert result["source_kind"] == "pdf-text"
    _expected_ok(result)


# ----------------------------------------------------------------------
# specific errors for genuinely non-tabular input
# ----------------------------------------------------------------------

def test_unsupported_extension_is_specific():
    with pytest.raises(RentRollImportError) as exc:
        parse_rent_roll_file(b"whatever", "rentroll.pages", ADDR)
    assert ".pages" in str(exc.value)
    assert "Supported" in str(exc.value)


def test_pdf_prose_not_a_table():
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "To whom it may concern:")
    c.drawString(72, 700, "Attached please find our quarterly portfolio narrative.")
    c.save()
    with pytest.raises(RentRollImportError) as exc:
        parse_rent_roll_file(buf.getvalue(), "letter.pdf", ADDR)
    msg = str(exc.value).lower()
    assert "table" in msg and ("narrative" in msg or "rent" in msg)


def test_docx_no_table():
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("Hi, here is the rent roll you asked for.")
    buf = io.BytesIO()
    d.save(buf)
    with pytest.raises(RentRollImportError) as exc:
        parse_rent_roll_file(buf.getvalue(), "note.docx", ADDR)
    assert "no table" in str(exc.value).lower()


def test_empty_file():
    with pytest.raises(RentRollImportError):
        parse_rent_roll_file(b"", "rr.csv", ADDR)


# ----------------------------------------------------------------------
# images / OCR
# ----------------------------------------------------------------------

@pytest.mark.skipif(_HAS_TESSERACT, reason="tesseract installed -- OCR path runs for real, see test_image_ocr_when_available")
def test_image_without_tesseract_fails_cleanly():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buf, format="PNG")
    with pytest.raises(RentRollImportError) as exc:
        parse_rent_roll_file(buf.getvalue(), "rr.png", ADDR)
    m = str(exc.value).lower()
    assert "ocr" in m and ("excel" in m or "csv" in m)  # actionable fallback offered


@pytest.mark.skipif(not _HAS_TESSERACT, reason="needs a tesseract binary")
def test_image_ocr_when_available():
    from PIL import Image, ImageDraw
    rows = [HEADER] + DATA_5
    img = Image.new("RGB", (1400, 60 + 40 * len(rows)), "white")
    d = ImageDraw.Draw(img)
    xs = [20, 90, 430, 520, 700, 880, 1030, 1180]
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            d.text((xs[ci], 40 + ri * 40), str(val), fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(200, 200))
    result = parse_rent_roll_file(buf.getvalue(), "rr.png", ADDR)
    assert result["source_kind"] == "image-ocr"
    assert result["warnings"], "an OCR import must carry a spot-check warning"
    # OCR is imperfect -- assert it found SOMETHING sane, not an exact match.
    assert len(result["leases"]) >= 3
    assert any("Blue" in (t or "") for t in _tenants(result))


def test_ocr_grid_reconstruction_algorithm():
    """_ocr_words_to_rows on synthetic tesseract-style word boxes -- no tesseract needed."""
    def W(t, left, top, h=18):
        return {"text": t, "left": left, "top": top, "width": 9 * len(t), "height": h, "conf": 92.0}

    cols = [30, 250, 470, 600, 780, 940]  # Unit Tenant SF Start End Rent
    src = [
        ["Unit", "Tenant", "SF", "Start", "End", "Rent"],
        ["101", "Blue Bottle Coffee", "1450", "03/01/2023", "02/28/2028", "6,180"],
        ["102", "Acme Corp", "2100", "06/15/2021", "06/14/2028", "9,724"],
        ["103", "VACANT", "980", "", "", "0"],
    ]
    words = []
    for ri, row in enumerate(src):
        top = 20 + ri * 40
        for ci, val in enumerate(row):
            if not val:
                continue
            x = cols[ci]
            for tok in val.split():
                words.append(W(tok, x, top))
                x += 9 * len(tok) + 6

    grid = _ocr_words_to_rows(words)
    assert grid[0] == ["Unit", "Tenant", "SF", "Start", "End", "Rent"]
    assert grid[1][0] == "101"
    assert grid[1][1] == "Blue Bottle Coffee"        # multi-word cell stays intact
    assert grid[1][5] == "6,180"
    assert grid[2][1] == "Acme Corp"
    assert grid[3][1] == "VACANT"
