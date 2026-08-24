"""
Generates real, on-disk test fixtures for every new upload format this
project now supports (Excel .xlsx/.xls, CSV/TSV, Word .docx/.doc,
images .jpg/.png/.tiff, plain .txt) -- all carrying the EXACT SAME
lease content, so extraction results are directly comparable across
formats: if the pipeline is genuinely format-agnostic, every one of
these files should produce the same 13 field values.

Each file is a REAL file written by a REAL library for that format
(openpyxl, xlwt, python-docx, PIL, csv, macOS's own `textutil` for the
legacy .doc conversion) -- never a fake file with the right extension
but wrong internal structure, since that would test nothing real.
"""
import csv
import os
import subprocess

from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
import xlwt

FIXTURES_DIR = os.path.dirname(__file__)

# The single source of truth for this fixture's content -- every format
# below renders exactly these label/value pairs, nothing more.
LEASE_FIELDS = [
    ("Tenant", "Cascade Outdoor Gear Co."),
    ("Landlord", "Timberline Properties LLC"),
    ("Property Address", "500 Pioneer Square, Suite 300, Portland, Oregon 97204"),
    ("Lease Start Date", "May 1, 2025"),
    ("Lease End Date", "April 30, 2032"),
    ("Monthly Rent", "$7,800.00"),
    ("Security Deposit", "$7,800.00"),
    ("CAM Charges", "$650.00"),
    ("Square Footage", "2,900 sq ft"),
    ("Rent Escalation", "3% annually"),
    ("Renewal Options", "1 option of 5 years; 120 days notice"),
    ("Permitted Use", "a retail outdoor equipment store"),
    ("Default Cure Period", "15 days after written notice"),
    ("Insurance Requirements", "$1,500,000 per occurrence"),
]

# Expected extracted values, keyed by FieldExtractor's own field names --
# used by the test suite to assert against, not just eyeballed.
EXPECTED_VALUES = {
    "tenant": "Cascade Outdoor Gear Co.",
    "landlord": "Timberline Properties LLC",
    "property_address": "500 Pioneer Square, Suite 300, Portland, Oregon 97204",
    "lease_start_date": "May 1, 2025",
    "lease_end_date": "April 30, 2032",
    "rent_amount": "$7,800.00",
    "security_deposit": "$7,800.00",
    "cam_charges": "$650.00",
    "square_footage": "2,900 sq ft",
}


def _lines():
    return [f"{label}: {value}" for label, value in LEASE_FIELDS]


def create_txt():
    path = os.path.join(FIXTURES_DIR, "multiformat_lease.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("COMMERCIAL LEASE AGREEMENT\n\n")
        f.write("\n".join(_lines()))
    print(f"Created: {path}")
    return path


def create_csv():
    path = os.path.join(FIXTURES_DIR, "multiformat_lease.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Field", "Value"])
        for label, value in LEASE_FIELDS:
            writer.writerow([label, value])
    print(f"Created: {path}")
    return path


def create_tsv():
    path = os.path.join(FIXTURES_DIR, "multiformat_lease.tsv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["Field", "Value"])
        for label, value in LEASE_FIELDS:
            writer.writerow([label, value])
    print(f"Created: {path}")
    return path


def create_xlsx():
    path = os.path.join(FIXTURES_DIR, "multiformat_lease.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Lease"
    ws.append(["COMMERCIAL LEASE AGREEMENT"])
    ws.append([])
    for label, value in LEASE_FIELDS:
        ws.append([f"{label}:", value])
    wb.save(path)
    print(f"Created: {path}")
    return path


def create_xls():
    path = os.path.join(FIXTURES_DIR, "multiformat_lease.xls")
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Lease")
    ws.write(0, 0, "COMMERCIAL LEASE AGREEMENT")
    for i, (label, value) in enumerate(LEASE_FIELDS, start=2):
        ws.write(i, 0, f"{label}:")
        ws.write(i, 1, value)
    wb.save(path)
    print(f"Created: {path}")
    return path


def create_docx():
    path = os.path.join(FIXTURES_DIR, "multiformat_lease.docx")
    doc = Document()
    doc.add_paragraph("COMMERCIAL LEASE AGREEMENT")
    doc.add_paragraph("")
    for line in _lines():
        doc.add_paragraph(line)
    doc.save(path)
    print(f"Created: {path}")
    return path


def create_doc_from_docx(docx_path):
    """A REAL legacy .doc file, converted from the real .docx above by macOS's own textutil (built-in, no extra install) -- not a hand-crafted binary blob."""
    path = os.path.join(FIXTURES_DIR, "multiformat_lease.doc")
    subprocess.run(
        ["textutil", "-convert", "doc", "-output", path, docx_path],
        check=True, capture_output=True,
    )
    print(f"Created: {path}")
    return path


def _draw_image(output_path, fmt):
    img = Image.new("RGB", (1700, 1400), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        font_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    except Exception:
        font = ImageFont.load_default()
        font_bold = font

    y = 80
    draw.text((80, y), "COMMERCIAL LEASE AGREEMENT", fill="black", font=font_bold)
    y += 80
    for line in _lines():
        draw.text((80, y), line, fill="black", font=font)
        y += 60

    save_kwargs = {}
    if fmt == "JPEG":
        save_kwargs["quality"] = 95
    elif fmt == "TIFF":
        # Uncompressed TIFF at this resolution is ~7MB -- far too big
        # for a committed test fixture. tiff_deflate is lossless (OCR
        # accuracy is identical either way) and shrinks this to under
        # 100KB.
        save_kwargs["compression"] = "tiff_deflate"
    img.save(output_path, fmt, **save_kwargs)
    print(f"Created: {output_path}")


def create_jpg():
    _draw_image(os.path.join(FIXTURES_DIR, "multiformat_lease.jpg"), "JPEG")


def create_png():
    _draw_image(os.path.join(FIXTURES_DIR, "multiformat_lease.png"), "PNG")


def create_tiff():
    _draw_image(os.path.join(FIXTURES_DIR, "multiformat_lease.tiff"), "TIFF")


if __name__ == "__main__":
    create_txt()
    create_csv()
    create_tsv()
    create_xlsx()
    create_xls()
    docx_path = create_docx()
    create_doc_from_docx(docx_path)
    create_jpg()
    create_png()
    create_tiff()
    print("\nAll multi-format fixtures created.")
