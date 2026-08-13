"""
Rent roll export: the portfolio as a CSV or formatted Excel workbook.

A rent roll is the artifact a property manager actually hands to a lender,
broker, or accountant, so this module optimizes for *their* reading of the
data rather than the tool's internal representation:

  - Text columns carry the extraction engine's display strings verbatim
    ("$6,250.00", "April 1, 2025", "3% annually"). Reformatting them here
    would quietly diverge from what the UI shows and what the source quote
    supports, which defeats the human-verifiability premise of the tool.
  - Two columns are genuinely derived rather than extracted — Rent/SqFt and
    Months Until Expiration — and are computed through app.normalize so they
    agree with every other module's parsing of the same strings.
  - A field that wasn't found renders as an empty cell, never the string
    "None": a blank cell reads as "no data" to a spreadsheet user and to
    every downstream tool, whereas "None" reads as a value.

The Excel variant additionally types the unambiguous numeric columns as real
numbers with a currency/number format, because the whole point of the .xlsx
over the .csv is that the recipient can sort, sum, and pivot it. See
_numeric_or_text() for why that typing is applied conservatively.
"""

import csv
import io
import re
from datetime import date
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from app.normalize import parse_currency, parse_date, parse_square_footage, rent_per_sqft


COLUMNS = [
    "Filename",
    "Tenant",
    "Landlord",
    "Property Address",
    "Square Footage",
    "Monthly Rent",
    "Rent/SqFt",
    "Security Deposit",
    "CAM Charges",
    "Rent Escalation",
    "Lease Start",
    "Lease End",
    "Renewal Options",
    "Months Until Expiration",
]

# Column -> extracted_fields key, for the columns that are a straight
# pass-through of an extracted display string.
_FIELD_FOR_COLUMN = {
    "Tenant": "tenant",
    "Landlord": "landlord",
    "Property Address": "property_address",
    "Square Footage": "square_footage",
    "Monthly Rent": "rent_amount",
    "Security Deposit": "security_deposit",
    "CAM Charges": "cam_charges",
    "Rent Escalation": "rent_escalation",
    "Lease Start": "lease_start_date",
    "Lease End": "lease_end_date",
    "Renewal Options": "renewal_options",
}

# openpyxl has no auto-fit, so widths are set explicitly. These are tuned for
# the shape of real values (long clause text vs. short dates) rather than for
# the header lengths.
_COLUMN_WIDTHS = {
    "Filename": 26,
    "Tenant": 30,
    "Landlord": 30,
    "Property Address": 34,
    "Square Footage": 14,
    "Monthly Rent": 14,
    "Rent/SqFt": 11,
    "Security Deposit": 16,
    "CAM Charges": 22,
    "Rent Escalation": 34,
    "Lease Start": 16,
    "Lease End": 16,
    "Renewal Options": 46,
    "Months Until Expiration": 14,
}

_CURRENCY_FORMAT = "$#,##0.00"
_CURRENCY_COLUMNS = {"Monthly Rent", "Rent/SqFt", "Security Deposit", "CAM Charges"}
_INTEGER_COLUMNS = {"Square Footage", "Months Until Expiration"}
_INTEGER_FORMAT = "#,##0"

# A display string that is *only* a dollar amount ("$6,250.00") can safely be
# retyped as a number. One carrying a qualifier ("$4.50 per sq ft annually")
# cannot, since the bare number would misstate it.
_PURE_CURRENCY = re.compile(r"^\s*\$\s?[\d,]+(?:\.\d+)?\s*$")


def generate_rent_roll_csv(leases: List[Dict[str, Any]], today: Optional[date] = None) -> str:
    """
    Renders the portfolio as CSV text (a str, not bytes — the caller owns the
    encoding decision, since a browser download and an email attachment want
    different things). One row per lease, in the order given.

    `today` is injectable purely so the Months Until Expiration column is
    testable without the assertions rotting as the calendar advances.
    """
    today = today or date.today()

    buffer = io.StringIO()
    # "\n" rather than the csv module's default "\r\n": this is returned as a
    # string for a caller to encode, not written to a binary file handle, and
    # every consumer (Excel included) accepts LF.
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for lease in leases:
        writer.writerow([_cell_text(lease, column, today) for column in COLUMNS])
    return buffer.getvalue()


def generate_rent_roll_excel(leases: List[Dict[str, Any]], today: Optional[date] = None) -> bytes:
    """
    Renders the same rows and columns as the CSV into a formatted .xlsx
    workbook, returned as raw bytes ready to hand to a file-download response.

    Formatting beyond the raw data: bold frozen header row, explicit column
    widths, and real numeric typing with a currency/count number format on the
    columns where that's unambiguous.
    """
    today = today or date.today()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rent Roll"

    header_font = Font(bold=True)
    for index, column in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index, value=column)
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(index)].width = _COLUMN_WIDTHS[column]

    for row_index, lease in enumerate(leases, start=2):
        for column_index, column in enumerate(COLUMNS, start=1):
            value, number_format = _cell_typed(lease, column, today)
            cell = sheet.cell(row=row_index, column=column_index, value=value)
            if number_format:
                cell.number_format = number_format

    # Keeps the header visible while scrolling a long portfolio.
    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _cell_text(lease: Dict[str, Any], column: str, today: date) -> str:
    """The CSV rendering of one cell: always a string, empty when unavailable."""
    value = _cell_value(lease, column, today)
    if value is None:
        return ""
    if column == "Rent/SqFt":
        return "${:,.2f}".format(value)
    if column == "Months Until Expiration":
        return str(value)
    return str(value)


def _cell_typed(lease: Dict[str, Any], column: str, today: date):
    """
    The Excel rendering of one cell, as (value, number_format).

    Returns None for an unavailable value so openpyxl leaves the cell truly
    empty rather than writing an empty string, which Excel treats differently
    in formulas like COUNTBLANK.
    """
    value = _cell_value(lease, column, today)
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return value, _CURRENCY_FORMAT if column in _CURRENCY_COLUMNS else _INTEGER_FORMAT
    return _numeric_or_text(value, column)


def _cell_value(lease: Dict[str, Any], column: str, today: date):
    """
    The underlying value for a column: the extracted display string, a derived
    number, or None when the field is missing or unparseable.
    """
    if column == "Filename":
        return lease.get("filename") or None
    if column == "Rent/SqFt":
        return rent_per_sqft(
            _field_value(lease, "rent_amount"), _field_value(lease, "square_footage")
        )
    if column == "Months Until Expiration":
        return _months_until(_field_value(lease, "lease_end_date"), today)
    return _field_value(lease, _FIELD_FOR_COLUMN[column])


def _field_value(lease: Dict[str, Any], field_name: str) -> Optional[str]:
    """
    Reads one extracted field's value, tolerating every shape a partially
    populated or amendment-merged record can take (missing extracted_fields,
    missing field, field present but null).
    """
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field_name)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    return value if value not in (None, "") else None


def _numeric_or_text(value: str, column: str):
    """
    Decides whether a display string may be retyped as a number for Excel.

    Conservative on purpose: a number is written only when the string carries
    no qualifier the number would drop. "$6,250.00" becomes 6250.0; "$4.50 per
    sq ft annually" stays text, because a cell reading "$4.50" would tell the
    reader something false. Square footage is the one exception — its "sq ft"
    suffix is restated by the column header, so nothing is lost.
    """
    text = str(value)
    if column in _CURRENCY_COLUMNS and _PURE_CURRENCY.match(text):
        parsed = parse_currency(text)
        if parsed is not None:
            return parsed, _CURRENCY_FORMAT
    if column == "Square Footage":
        parsed = parse_square_footage(text)
        if parsed is not None:
            return parsed, _INTEGER_FORMAT
    return text, None


def _months_until(end_date_value: Optional[str], today: date) -> Optional[int]:
    """
    Whole calendar months from today until the lease end date, negative if the
    lease has already expired, None if the end date is missing or unparseable.

    Counted in calendar months (not days/30) because that's how a lease term is
    actually written and how a reader will sanity-check the number against the
    Lease End column.
    """
    end_date = parse_date(end_date_value)
    if end_date is None:
        return None
    months = (end_date.year - today.year) * 12 + (end_date.month - today.month)
    if end_date.day < today.day:
        months -= 1
    return months
