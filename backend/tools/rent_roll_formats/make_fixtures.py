"""
Generate the "same rent roll, three formats" fixture set used to test
multi-format rent-roll import:

  Meridian_Plaza_Rent_Roll_HARD.xlsx   structured spreadsheet
  Meridian_Plaza_Rent_Roll_HARD.pdf    text-layer PDF, gridded table
  Meridian_Plaza_Rent_Roll_HARD.png    rendered table image (screenshot-like)

All three carry the SAME underlying data -- a deliberately messy
("HARD") Yardi-style rent roll: decorative header block, a Market Rent
and an Annual Rent trap column, a vacant unit, a totals row, DBA vs
legal tenant names, two date formats.

Usage:  python3 tools/rent_roll_formats/make_fixtures.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures")
os.makedirs(OUT, exist_ok=True)

BASE = "Meridian_Plaza_Rent_Roll_HARD"

# Decorative rows a canned PMS report opens with, then the header, then data.
PREAMBLE = [
    ["Meridian Plaza", "", "", "", "", "", "", ""],
    ["Rent Roll - Commercial     As Of: 09/01/2026", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
]
HEADER = ["Unit", "Tenant", "Unit SF", "Lease From", "Lease To", "Market Rent", "Monthly Rent", "Annual Rent"]
DATA = [
    ["101", "Blue Bottle Coffee", "1,450", "03/01/2023", "02/28/2028", "7,200", "6,180", "74,160"],
    ["102", "Meridian Dental Associates PLLC", "2,100", "06/15/2021", "06/14/2028", "9,900", "9,724", "116,688"],
    ["103", "VACANT", "980", "", "", "5,400", "0", "0"],
    ["104", "Sunrise Bagel Co.", "1,200", "September 1, 2021", "August 31, 2027", "6,000", "5,568", "66,816"],
    ["105", "The Corner Bookshop LLC", "1,050", "05/01/2023", "04/30/2028", "4,100", "3,900", "46,800"],
    ["106", "Pacific Tide Surf Shop Inc", "1,320", "02/01/2022", "01/31/2030", "4,400", "4,120", "49,440"],
    ["107", "Verde Juice Bar", "760", "08/01/2024", "07/31/2029", "3,700", "3,600", "43,200"],
    ["108", "Old Town Barbers", "540", "07/01/2022", "06/30/2027", "2,500", "2,400", "28,800"],
    ["109", "Meridian Fitness Studio LLC", "3,400", "01/01/2024", "12/31/2031", "8,600", "8,100", "97,200"],
    ["110", "Loomis & Park Stationers", "900", "10/01/2020", "09/30/2028", "3,300", "3,180", "38,160"],
    ["111", "Cascade Pet Supply", "1,150", "03/15/2023", "03/14/2028", "4,900", "4,750", "57,000"],
    ["Total", "", "16,000", "", "", "62,400", "51,522", "618,264"],
]
ALL_ROWS = PREAMBLE + [HEADER] + DATA


def make_xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Rent Roll"
    for row in ALL_ROWS:
        ws.append(row)
    path = os.path.join(OUT, BASE + ".xlsx")
    wb.save(path)
    return path


def make_pdf():
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    path = os.path.join(OUT, BASE + ".pdf")
    doc = SimpleDocTemplate(path, pagesize=landscape(letter),
                            leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Meridian Plaza", styles["Title"]),
        Paragraph("Rent Roll - Commercial &nbsp;&nbsp; As Of: 09/01/2026", styles["Normal"]),
        Spacer(1, 0.2 * inch),
    ]
    table = Table([HEADER] + DATA, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    doc.build(story)
    return path


def make_png():
    from PIL import Image, ImageDraw, ImageFont

    rows = [HEADER] + DATA
    ncols = len(HEADER)
    col_w = [70, 260, 70, 130, 130, 100, 110, 110]
    row_h = 34
    pad = 24
    W = sum(col_w) + pad * 2
    H = row_h * (len(rows) + 2) + pad * 2

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
        bold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
        bold = font

    d.text((pad, pad), "Meridian Plaza  -  Rent Roll - Commercial  -  As Of: 09/01/2026", fill="black", font=bold)
    y0 = pad + row_h
    for r, row in enumerate(rows):
        y = y0 + r * row_h
        x = pad
        for c in range(ncols):
            cell = str(row[c]) if c < len(row) else ""
            d.text((x + 4, y + 8), cell, fill="black", font=(bold if r == 0 else font))
            x += col_w[c]
        d.line([(pad, y + row_h), (W - pad, y + row_h)], fill="#cccccc")
    x = pad
    for c in range(ncols):
        d.line([(x, y0), (x, y0 + len(rows) * row_h)], fill="#cccccc")
        x += col_w[c]
    d.line([(x, y0), (x, y0 + len(rows) * row_h)], fill="#cccccc")

    path = os.path.join(OUT, BASE + ".png")
    img.save(path, dpi=(150, 150))
    return path


if __name__ == "__main__":
    for fn in (make_xlsx, make_pdf, make_png):
        try:
            print("wrote", os.path.relpath(fn(), HERE))
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {fn.__name__}: {type(exc).__name__}: {exc}")
