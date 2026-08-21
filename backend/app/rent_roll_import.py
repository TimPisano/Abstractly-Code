"""
Rent roll import: parses a broker-built Excel/CSV rent roll into the
same extracted_fields shape the PDF lease extractor produces, so every
existing portfolio computation (tenant concentration, WALT, rollover,
loss-to-lease, risk analysis, ...) works on imported rows with zero
special-casing anywhere else in the codebase.

There is deliberately no fixed expected format here -- unlike a PDF
lease (a legal document with fairly consistent structure this project
already knows how to parse), a broker's rent roll spreadsheet has no
standard: every broker builds their own, with their own column names,
their own column order, and their own extra decorative columns. This
module works by matching each column's HEADER TEXT against a list of
common aliases per field (see _COLUMN_ALIASES) rather than assuming
any fixed layout -- a header this module doesn't recognize (e.g.
"Parking Spaces", "Notes") is simply ignored, not an error.

Source citations for imported data use a different shape than the PDF
extractor's {page, quote} -- there is no PDF page for a spreadsheet
cell. Instead: {row, file, quote}, where `quote` is the raw cell text
actually read, same "here's exactly what we found" spirit as the PDF
citation, just located by row/file instead of page. See
frontend/app/detail-view.js for the matching display-side handling.
"""

import csv
import io
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from openpyxl import load_workbook

from app.normalize import parse_currency, parse_date, parse_square_footage
from app.portfolio import FIELD_NAMES


class RentRollImportError(Exception):
    """
    Raised when the file can't be imported AT ALL -- wrong file type,
    completely empty, or no recognizable tenant/rent columns in the
    header row. A single bad DATA row is a different, non-fatal thing
    (see `skipped_rows` in the return value) -- one malformed row
    should never block importing the rest of a real file.
    """


# Canonical field name -> header aliases that map to it, checked in a
# fixed field order (see _match_columns) so a header that could
# plausibly match more than one field resolves predictably. A header
# this module doesn't recognize at all is simply left unmapped --
# broker rent rolls routinely have extra columns (notes, parking,
# CAM, etc.) that aren't an error to skip.
_COLUMN_ALIASES: Dict[str, List[str]] = {
    "tenant": ["tenant name", "tenant", "lessee", "occupant", "customer"],
    "unit": ["unit number", "unit #", "suite #", "unit", "suite", "space"],
    "square_footage": ["square footage", "square feet", "sq ft", "sqft", "sf", "rsf", "size", "area"],
    "rent_amount": ["monthly base rent", "monthly rent", "base rent", "current rent", "rent/mo", "rent"],
    # "Rent Commencement"/"Rent Start" are real, standard commercial
    # lease terms distinct from "Lease Commencement" -- rent can start
    # later than the lease itself during a free-rent/build-out period.
    # This system doesn't track that distinction as its own field, so
    # a rent-commencement column is treated as equivalent to
    # lease_start_date -- deliberately listed here, not left to
    # accidentally collide with rent_amount's "rent" alias (a real bug
    # caught in testing: "Rent Commencement" was getting matched to
    # rent_amount via the bare "rent" substring before this was added).
    "lease_start_date": [
        "lease commencement", "commencement date", "commence date", "lease start", "start date",
        "rent commencement", "rent commencement date", "rent start", "rent start date",
    ],
    "lease_end_date": [
        "lease expiration", "expiration date", "lease end", "end date", "expire",
        "rent expiration", "rent expiration date", "rent end", "rent end date",
    ],
}

# A row is skipped (not imported as a tenant) if its tenant cell, once
# normalized, is blank or matches one of these. Broker rent rolls
# routinely include vacant-unit rows and a totals/subtotal row at the
# bottom -- neither is a real lease, and importing "Total" as if it
# were a tenant would fabricate a fake mega-tenant that doesn't exist
# (the exact failure mode compute_tenant_concentration's own docstring
# already worries about for a missing tenant name -- this is the same
# concern, applied at the import boundary instead).
_NON_TENANT_KEYWORDS = {"vacant", "vacancy", "total", "totals", "subtotal", "sub total", "n a", "na"}


def _normalize_header(header: Any) -> str:
    return re.sub(r"[^\w\s]", "", str(header).lower()).strip()


def _match_columns(headers: List[Any]) -> Dict[str, int]:
    """Maps canonical field name -> column index for whichever headers could be confidently matched. See module docstring."""
    normalized = [_normalize_header(h) for h in headers]
    mapping: Dict[str, int] = {}
    used_columns = set()

    # Pass 1: exact match (most confident) -- "Rent" header equals the "rent" alias exactly.
    for field_name, aliases in _COLUMN_ALIASES.items():
        alias_norms = {_normalize_header(a) for a in aliases}
        for i, h in enumerate(normalized):
            if i in used_columns:
                continue
            if h in alias_norms:
                mapping[field_name] = i
                used_columns.add(i)
                break

    # Pass 2: whole-phrase containment for anything not yet matched.
    # Deliberately NOT "first field in dict order wins" -- that order
    # dependency was a real bug: "Rent Commencement" would get grabbed
    # by rent_amount's bare "rent" alias before lease_start_date's more
    # specific "commencement"-family aliases ever got a look, purely
    # because rent_amount happens to be declared earlier above. Instead:
    # collect every (field, header, alias) match that exists at all,
    # then assign them longest-alias-first -- a longer alias is a more
    # specific, more confident signal ("rent commencement" pinning down
    # exactly what a column means beats the bare word "rent" matching
    # almost anything with "rent" in it), so it should win regardless of
    # which field happens to be declared first.
    candidates = []  # (alias_length, field_name, header_index)
    for field_name, aliases in _COLUMN_ALIASES.items():
        if field_name in mapping:
            continue
        for alias in aliases:
            alias_norm = _normalize_header(alias)
            pattern = re.compile(rf"\b{re.escape(alias_norm)}\b")
            for i, h in enumerate(normalized):
                if i in used_columns:
                    continue
                if pattern.search(h):
                    candidates.append((len(alias_norm), field_name, i))

    candidates.sort(key=lambda c: c[0], reverse=True)  # longest/most-specific alias first
    for _, field_name, i in candidates:
        if field_name in mapping or i in used_columns:
            continue  # already claimed by an even more specific match
        mapping[field_name] = i
        used_columns.add(i)

    return mapping


def _cell_to_str(value: Any) -> Optional[str]:
    """
    Normalizes a raw cell value to a string suitable for normalize.py's
    parsers, or None for a genuinely empty cell. openpyxl hands back
    str/int/float/date/datetime/None depending on how the cell is
    formatted; csv.DictReader always hands back str (or None for a
    missing trailing column). Both are normalized to the same shape
    here so the rest of this module doesn't need to care which format
    the file came in.
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (datetime, date)):
        return value.strftime("%B %d, %Y")  # matches parse_date's supported month-name format
    return str(value)


def _parse_import_currency(value: Any) -> Optional[float]:
    """
    Like normalize.parse_currency, but tolerant of a bare number with
    no "$" -- imported spreadsheet rent columns very often store a raw
    number (an actual numeric cell type in xlsx, or a "1200.00"-style
    string with no currency symbol in csv), unlike PDF-extracted text,
    which always has a real "$" attached in this codebase's existing
    parser's expected input.
    """
    if isinstance(value, (int, float)):
        return float(value)
    text = _cell_to_str(value)
    if text is None:
        return None
    strict = parse_currency(text)  # handles "$1,200.00" using the existing, already-tested parser
    if strict is not None:
        return strict
    match = re.search(r"[\d,]+(?:\.\d+)?", text)  # fall back to a bare number with no "$"
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _is_real_tenant_name(tenant_raw: Optional[str]) -> bool:
    if not tenant_raw:
        return False
    normalized = re.sub(r"[^\w\s]", " ", tenant_raw.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized not in _NON_TENANT_KEYWORDS


def parse_rent_roll_rows(
    headers: List[Any],
    rows: List[List[Any]],
    filename: str,
    base_property_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Core parsing logic, independent of file format -- both the CSV and
    xlsx readers below reduce their own file to this same
    (headers, rows) shape before handing off here, so the actual
    column-matching/row-parsing logic exists exactly once.

    `base_property_address` is the property this rent roll is for,
    supplied by the uploader at import time (most rent rolls state the
    building once, in a title/header area, not per row) -- combined
    with a per-row "Unit"/"Suite" column (if the file has one) to
    produce a full per-lease property_address, e.g. "123 Main St,
    Suite 200". This is also what makes compute_loss_to_lease's
    same-building comp grouping work correctly for imported leases:
    every row from one import shares the same base address, so they
    group together as one building automatically. If no base address
    is given and the file has no unit/suite column either,
    property_address is left unset for every row (honest "not found",
    not a guess).

    Returns `{leases: [...], skipped_rows: [{row, reason}, ...],
    column_mapping: {field_name: column_index, ...}}`. `leases` entries
    are `{extracted_fields, display_name}`, ready to hand to
    database.insert_lease() exactly like a PDF-extracted result.

    Raises RentRollImportError (fatal, nothing imported) only if the
    header row has no recognizable tenant name column AND no
    recognizable rent column -- without at least those two, there's
    nothing to import. Everything else (a missing square footage
    column, an unparseable date in one row, a vacant-unit row) is
    handled per-row: either that one field is "not found" for that
    row, or that one row is skipped and reported, never a reason to
    fail the whole file.
    """
    column_mapping = _match_columns(headers)

    if "tenant" not in column_mapping or "rent_amount" not in column_mapping:
        raise RentRollImportError(
            "Couldn't find a recognizable tenant name column and rent column in this "
            "file's header row. Recognized headers include things like \"Tenant\", "
            "\"Tenant Name\", \"Rent\", \"Monthly Rent\", \"Base Rent\" -- check that "
            "the first row of the file actually contains column headers, not a blank "
            "or decorative row."
        )

    parsed_leases = []
    skipped_rows = []

    for row_index, row in enumerate(rows):
        row_num = row_index + 2  # +1 for 1-indexing, +1 because row 1 is the header

        def cell(field_name: str) -> Any:
            idx = column_mapping.get(field_name)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        tenant_raw = _cell_to_str(cell("tenant"))
        if not _is_real_tenant_name(tenant_raw):
            skipped_rows.append({
                "row": row_num,
                "reason": "blank tenant, or looks like a vacancy/total/subtotal row, not a real tenant",
            })
            continue

        rent = _parse_import_currency(cell("rent_amount"))
        unit_str = _cell_to_str(cell("unit"))
        sqft_str = _cell_to_str(cell("square_footage"))
        start_str = _cell_to_str(cell("lease_start_date"))
        end_str = _cell_to_str(cell("lease_end_date"))

        if base_property_address and unit_str:
            address = f"{base_property_address}, Suite {unit_str}"
        elif base_property_address:
            address = base_property_address
        else:
            address = unit_str  # better than nothing if no base address was given at all

        fields = {name: {"value": None, "source": None, "confidence": None} for name in FIELD_NAMES}

        def set_field(name: str, value: Optional[str], raw_quote: Optional[str]):
            if value is None:
                return
            fields[name] = {
                "value": value,
                "source": {"row": row_num, "file": filename, "quote": raw_quote if raw_quote is not None else str(value)},
                "confidence": "high",  # not a guess -- read directly out of an uploaded spreadsheet cell
            }

        set_field("tenant", tenant_raw, tenant_raw)
        set_field("property_address", address, unit_str if unit_str else base_property_address)
        if rent is not None:
            set_field("rent_amount", f"${rent:,.2f}", _cell_to_str(cell("rent_amount")))
        if sqft_str is not None and parse_square_footage(sqft_str) is not None:
            set_field("square_footage", f"{parse_square_footage(sqft_str):,.0f} sq ft", sqft_str)
        if start_str is not None and parse_date(start_str) is not None:
            set_field("lease_start_date", start_str, start_str)
        if end_str is not None and parse_date(end_str) is not None:
            set_field("lease_end_date", end_str, end_str)

        display_name = f"{tenant_raw} - {address}" if address else tenant_raw
        parsed_leases.append({"extracted_fields": fields, "display_name": display_name})

    return {
        "leases": parsed_leases,
        "skipped_rows": skipped_rows,
        "column_mapping": column_mapping,
    }


def parse_csv_rent_roll(file_bytes: bytes, filename: str, base_property_address: Optional[str] = None) -> Dict[str, Any]:
    """Reads a CSV file's bytes and parses it via parse_rent_roll_rows. Raises RentRollImportError for a genuinely empty file."""
    text = file_bytes.decode("utf-8-sig", errors="replace")  # utf-8-sig strips a leading BOM, common from Excel's own CSV export
    reader = csv.reader(io.StringIO(text))
    all_rows = [row for row in reader if any(cell.strip() for cell in row)]  # drop fully-blank rows anywhere in the file

    if not all_rows:
        raise RentRollImportError("This CSV file is empty -- nothing to import.")

    headers, data_rows = all_rows[0], all_rows[1:]
    return parse_rent_roll_rows(headers, data_rows, filename, base_property_address)


def parse_xlsx_rent_roll(file_bytes: bytes, filename: str, base_property_address: Optional[str] = None) -> Dict[str, Any]:
    """Reads an .xlsx file's bytes and parses it via parse_rent_roll_rows. Uses the first (active) worksheet. Raises RentRollImportError for a genuinely empty or unreadable file."""
    try:
        workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise RentRollImportError(f"Couldn't read this file as an Excel workbook: {exc}")

    sheet = workbook.active
    all_rows = [
        list(row) for row in sheet.iter_rows(values_only=True)
        if any(cell is not None and str(cell).strip() for cell in row)
    ]

    if not all_rows:
        raise RentRollImportError("This Excel file is empty -- nothing to import.")

    headers, data_rows = all_rows[0], all_rows[1:]
    return parse_rent_roll_rows(list(headers), data_rows, filename, base_property_address)
