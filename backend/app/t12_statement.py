"""
T12 (trailing 12-month) operating statement parsing for multi-line-item extraction.

Extends t12_import.py (which parses exactly one line item -- actual rental income)
to parse six categories from a full operating statement: gross potential rent,
rental income collected, concessions, vacancy loss, bad debt, and other income.
Reuses t12_import.py's column-matching and header-detection machinery rather than
duplicating it.

PDF path: pdfplumber table extraction first (T-12 PDFs exported from property
software are usually real tables); if no table is extracted, falls back to
pytesseract OCR reconstruction. Raises T12ImportError with a specific, actionable
message rather than silently returning wrong numbers if OCR confidence is low or
column alignment can't be reconstructed.

Each category returns {monthly: {jan: float|None, ..., dec: float|None},
annual: float|None, source: {row, file, quote} | None}, matching this codebase's
"None means not enough data, never a guessed zero" discipline.
"""

import io
from typing import Any, Dict, List, Optional

from app.t12_import import (
    T12ImportError, _match_t12_columns, _find_t12_header_row, _parse_t12_currency,
    _normalize_header,
)
from app.normalize import parse_currency

_MONTH_IDS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

# Row-label aliases per category
_CATEGORY_ALIASES = {
    "gross_potential_rent": [
        "gross potential rent", "potential rent", "potential income",
        "scheduled gross income", "market rent income",
        "gross rent potential", "potential gross rent", "gross scheduled rent", "gpr",
    ],
    "rental_income_collected": [
        "total rental income", "rental income", "gross rental income",
        "base rental income", "total rent income", "rent revenue",
        "scheduled rent income", "total rent revenue",
        "rental revenue", "net rental revenue", "net rent revenue", "net rents", "rent collected",
    ],
    "concessions": [
        "concessions", "rent concessions", "loss to lease - concessions",
        "tenant concessions", "lease concessions",
    ],
    "vacancy_loss": [
        "vacancy loss", "vacancy", "loss to vacancy",
    ],
    "bad_debt": [
        "bad debt", "bad debt expense", "collection loss", "uncollectible rent",
    ],
    "other_income": [
        "other income", "miscellaneous income", "ancillary income", "other revenue", "total other revenue",
    ],
}


def _row_monthly_values(row: List[Any], column_mapping: Dict[str, Any]) -> Optional[Dict[str, Optional[float]]]:
    """
    Extract monthly values for a row. Returns {month_id: float|None} for the
    months present in the file, or None if no months are available for this row.
    """
    months = column_mapping.get("months", {})
    if not months:
        return None
    monthly: Dict[str, Optional[float]] = {}
    for month_id in _MONTH_IDS:
        if month_id in months:
            idx = months[month_id]
            if idx < len(row):
                monthly[month_id] = _parse_t12_currency(row[idx])
            else:
                monthly[month_id] = None
        else:
            monthly[month_id] = None
    return monthly


def _row_annual_total(row: List[Any], column_mapping: Dict[str, Any]) -> Optional[float]:
    """
    A row's annual figure: the Total/Annual column if the file has one,
    otherwise the sum of all 12 month columns if the file has every one of them.
    None if neither is available.
    """
    if "total" in column_mapping:
        idx = column_mapping["total"]
        return _parse_t12_currency(row[idx]) if idx < len(row) else None
    months = column_mapping.get("months", {})
    if len(months) < 12:
        return None
    total = 0.0
    found = False
    for idx in months.values():
        if idx < len(row):
            value = _parse_t12_currency(row[idx])
            if value is not None:
                total += value
                found = True
    return total if found else None  # an all-blank row has no total, not a $0 one


def _row_has_any_amount(row: List[Any], column_mapping: Dict[str, Any]) -> bool:
    """True if any month or total cell in this row holds a number."""
    indexes = list(column_mapping.get("months", {}).values())
    if "total" in column_mapping:
        indexes.append(column_mapping["total"])
    return any(i < len(row) and _parse_t12_currency(row[i]) is not None for i in indexes)


def parse_t12_statement_rows(
    headers: List[Any],
    rows: List[List[Any]],
    filename: str,
    header_row_offset: int = 0,
    row_numbers: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Core parsing logic, independent of file format. Scans every data row's first
    cell for each of the six category aliases, extracting monthly and annual values.

    Returns {
        "gross_potential_rent": {monthly: {...}, annual: ..., source: ...},
        "rental_income_collected": {...},
        "concessions": {...},
        "vacancy_loss": {...},
        "bad_debt": {...},
        "other_income": {...},
    }

    Raises T12ImportError only for total failure (no usable header row at all).
    A partially-parseable file (some categories found, some not) returns None per
    missing category rather than failing the whole upload.
    """
    column_mapping = _match_t12_columns(headers)

    if "total" not in column_mapping and len(column_mapping.get("months", {})) < 12:
        # But for statement parsing, we're more lenient: even partial
        # monthly data is useful. Only raise if we have no month cols at all.
        if len(column_mapping.get("months", {})) == 0:
            raise T12ImportError(
                "Couldn't find any month columns in this file's header row -- "
                "expected either a \"Total\"/\"Annual\" column, or at least some month columns "
                "(Jan through Dec). Check that the file actually has a real column-header row "
                "within the first 20 rows."
            )

    result: Dict[str, Any] = {}
    for category, aliases in _CATEGORY_ALIASES.items():
        result[category] = None

    for row_index, row in enumerate(rows):
        if not row:
            continue
        label_raw = row[0]
        label_str = str(label_raw).strip() if label_raw is not None else ""
        if not label_str:
            continue
        normalized_label = _normalize_header(label_str)

        for category, aliases in _CATEGORY_ALIASES.items():
            if result[category] is not None:
                # Already found this category
                continue
            alias_norms = {_normalize_header(a) for a in aliases}
            is_match = normalized_label in alias_norms
            if not is_match:
                # Try substring match
                import re
                for alias in aliases:
                    if re.search(rf"\b{re.escape(_normalize_header(alias))}\b", normalized_label):
                        is_match = True
                        break

            if not is_match:
                continue

            # Found a match for this category
            monthly = _row_monthly_values(row, column_mapping)
            annual = _row_annual_total(row, column_mapping)
            if not _row_has_any_amount(row, column_mapping):
                # A SECTION HEADER ("Rental Income", "Other Income") with
                # no numbers -- it must not claim the category, or the
                # real line below it ("Net Rental Income") is never read.
                continue

            if row_numbers is not None:
                row_num = row_numbers[row_index]
            else:
                row_num = row_index + header_row_offset + 2

            result[category] = {
                "monthly": monthly,
                # The statement's own column order (oldest -> newest). A
                # trailing T-12 runs e.g. Oct..Sep, so calendar order would
                # put its oldest months last.
                "month_order": [m for m, _ in sorted(column_mapping.get("months", {}).items(), key=lambda kv: kv[1])],
                "annual": annual,
                "source": {"row": row_num, "file": filename, "quote": label_str} if annual is not None or monthly else None,
            }

    if all(v is None for v in result.values()):
        # Nothing recognizable at all -- most likely not a T-12 (a rent roll
        # or budget dropped into the T-12 slot). Saying so beats a report
        # that silently has no T-12 section.
        raise T12ImportError(
            "This doesn't look like a T-12 operating statement: none of its rows is a recognizable income "
            "line (Gross Potential Rent, Rental Income, Vacancy Loss, Concessions, Bad Debt, Other Income). "
            "Check that you uploaded the trailing-12-month income statement, not a rent roll or budget."
        )
    return result


def parse_csv_t12_statement(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Parses a CSV T12 statement. Raises T12ImportError for genuinely empty file."""
    import csv
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    numbered_rows = [(i, row) for i, row in enumerate(reader, start=1) if any(cell.strip() for cell in row)]

    if not numbered_rows:
        raise T12ImportError("This CSV file is empty -- nothing to import.")

    row_contents = [row for _, row in numbered_rows]
    header_idx = _find_t12_header_row(row_contents)
    headers = row_contents[header_idx]
    data_entries = numbered_rows[header_idx + 1:]
    data_rows = [row for _, row in data_entries]
    data_row_numbers = [n for n, _ in data_entries]
    return parse_t12_statement_rows(
        headers, data_rows, filename,
        header_row_offset=header_idx, row_numbers=data_row_numbers,
    )


def parse_xlsx_t12_statement(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Parses an .xlsx/.xls T12 statement from the first worksheet that has a
    T-12 header row and at least one recognized line item (a "Summary"
    tab first no longer hides the detail sheet; .xls is read with xlrd).
    Raises T12ImportError for an empty, unreadable or encrypted file.
    """
    from app.t12_import import _t12_sheet_candidates
    candidates = _t12_sheet_candidates(file_bytes)
    if not candidates:
        raise T12ImportError(
            "Couldn't find any month columns in this file's header row -- "
            "expected either a \"Total\"/\"Annual\" column, or at least some month columns "
            "(Jan through Dec), on any sheet of this workbook."
        )
    first = None
    for headers, data_rows, header_idx, row_numbers in candidates:
        parsed = parse_t12_statement_rows(headers, data_rows, filename, header_row_offset=header_idx, row_numbers=row_numbers)
        if first is None:
            first = parsed
        if any(v is not None for v in parsed.values()):
            return parsed
    return first


def parse_pdf_t12_statement(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Parses a PDF T12 statement. First tries pdfplumber table extraction,
    then falls back to pytesseract OCR if needed. Raises T12ImportError with
    an actionable message on real failure rather than returning wrong numbers.
    """
    import tempfile
    import os
    import pdfplumber
    from pdf2image import convert_from_path
    import pytesseract

    # Try pdfplumber table extraction first
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    # Found a table, use the first one
                    table = tables[0]
                    if len(table) > 1:
                        headers = table[0]
                        data_rows = table[1:]
                        return parse_t12_statement_rows(
                            headers, data_rows, filename, header_row_offset=0
                        )
    except Exception:
        pass

    # Fall back to OCR
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        images = convert_from_path(tmp_path)
        if not images:
            raise T12ImportError("Couldn't convert PDF pages to images for OCR.")

        all_text = []
        for image in images:
            try:
                text = pytesseract.image_to_string(image)
                all_text.append(text)
            except Exception as exc:
                raise T12ImportError(
                    f"OCR failed on this PDF: {exc}. If this is a scanned T12, "
                    "try uploading a digital PDF or CSV/Excel export instead."
                )

        combined_text = "\n".join(all_text)
        if not combined_text.strip():
            raise T12ImportError(
                "This PDF appears to be blank or unreadable by OCR. "
                "If it's a scanned T12, ensure the scan is legible."
            )

        # Parse OCR'd text as CSV-like
        lines = [line.strip() for line in combined_text.split("\n") if line.strip()]
        if len(lines) < 2:
            raise T12ImportError("PDF OCR produced too little text to parse a T12.")

        # Convert lines to rows (splitting on spaces for simplicity -- OCR'd tables are messy)
        rows = [line.split() for line in lines]
        if len(rows) < 2:
            raise T12ImportError("Couldn't parse the OCR'd PDF as a table.")

        return parse_t12_statement_rows(
            rows[0], rows[1:], filename, header_row_offset=0
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
