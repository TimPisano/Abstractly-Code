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
    # "Resident" is Yardi/AppFolio's own term for a tenant even in
    # mixed/commercial portfolios (both platforms originated in
    # multifamily) -- added for PMS export support, alongside the
    # existing broker-spreadsheet terms.
    "tenant": ["tenant name", "tenant", "lessee", "occupant", "customer", "resident"],
    # Real broker rent rolls essentially never state a landlord (the
    # uploader IS the landlord); this exists mainly so re-importing
    # THIS APP'S OWN export -- which does have a Landlord column, since
    # a full lease abstraction states it -- doesn't silently drop it,
    # see api.py's _try_table_extraction for the round-trip this backs.
    "landlord": ["landlord", "owner", "lessor"],
    "unit": ["unit number", "unit #", "suite #", "unit", "suite", "space"],
    # "Unit SF" is Yardi/AppFolio's own compact form of "square feet".
    "square_footage": ["square footage", "square feet", "sq ft", "sqft", "sf", "rsf", "size", "area", "unit sf"],
    # "Scheduled Rent"/"Rent Charge" are Yardi/AppFolio's own terms for
    # the tenant's actual contracted rent (as opposed to "Market Rent",
    # which is the theoretical achievable rate at 100% occupancy --
    # explicitly denylisted below, see _MARKET_RENT_WORDS, since using
    # market rent as if it were actual rent would silently corrupt
    # every downstream computation that reads rent_amount). "Actual
    # Rent"/"Charged Rent" are RealPage's own equivalent terms, for the
    # exact same reason -- RealPage rent rolls commonly show both an
    # Actual Rent and a Market Rent column side by side.
    "rent_amount": [
        "monthly base rent", "monthly rent", "base rent", "current rent", "rent/mo", "rent",
        "scheduled rent", "rent charge", "scheduled charges", "actual rent", "charged rent",
    ],
    # "Rent Commencement"/"Rent Start" are real, standard commercial
    # lease terms distinct from "Lease Commencement" -- rent can start
    # later than the lease itself during a free-rent/build-out period.
    # This system doesn't track that distinction as its own field, so
    # a rent-commencement column is treated as equivalent to
    # lease_start_date -- deliberately listed here, not left to
    # accidentally collide with rent_amount's "rent" alias (a real bug
    # caught in testing: "Rent Commencement" was getting matched to
    # rent_amount via the bare "rent" substring before this was added).
    # "Lease From"/"Lease To" are Yardi/AppFolio's own terms.
    # Deliberately does NOT include "Move-in"/"Move-out" -- those are
    # occupancy dates (when a tenant physically took/vacated
    # possession), a different real-world fact from the lease's own
    # contractual start/end (a tenant can move in days after lease
    # start, or a lease can renew past an original move-in date), the
    # same "don't conflate two different things" care already applied
    # elsewhere in this module (see _normalize_building_address in
    # portfolio.py for the same principle applied to addresses).
    # Bare "Commence" (no "date"/"lease" suffix) is a real, common MRI-
    # style column header -- caught during research for this addition,
    # not found broken in production: the longer phrases above only
    # match when the HEADER contains the full alias phrase, so a header
    # that's just "Commence" wouldn't match "commence date" (the header
    # is shorter than that alias, can never contain it). A bare
    # "commence" alias fills that gap; the longer, more specific
    # phrases above still win when both are present, via the existing
    # longest-alias-first matching order.
    "lease_start_date": [
        "lease commencement", "commencement date", "commence date", "lease start", "start date", "lease from",
        "rent commencement", "rent commencement date", "rent start", "rent start date", "commence",
    ],
    "lease_end_date": [
        "lease expiration", "expiration date", "lease end", "end date", "expire", "lease to",
        "rent expiration", "rent expiration date", "rent end", "rent end date",
    ],
    # Per-row property identifier -- most rent rolls (broker-built or a
    # single-property PMS pull) state the building once, outside the
    # table, handled by the uploader-supplied base_property_address
    # parameter. A portfolio-wide PMS export can instead cover several
    # properties in one file, one row per unit; when a column like this
    # is present, its value overrides base_property_address for that
    # row specifically (see parse_rent_roll_rows). Deliberately doesn't
    # include a bare "building" alias -- some rent rolls have an
    # unrelated "Building Type" (construction type) column, and a bare
    # "building" substring match would risk grabbing that instead.
    "property": ["property", "property name", "property address", "community", "community name"],
}

# Header words that mean a rent-like column is a THEORETICAL/aspirational
# figure -- the achievable rate at 100% occupancy or asking price -- not
# what a tenant is actually, contractually paying. A column whose header
# contains "rent" together with any of these is never matched to
# rent_amount, even if no better rent column exists in the file:
# comparing a rent roll's real dollars against an unrelated aspirational
# figure (as if they were the same thing) would be systematically wrong
# in one direction, and silently so -- the honest behavior is to treat
# the file as if it has no recognizable rent column at all, same as if
# the column were simply named something this module doesn't recognize.
_MARKET_RENT_WORDS = {"market", "potential", "asking", "projected", "proforma"}


def _is_market_rent_header(normalized_header: str) -> bool:
    words = set(normalized_header.split())
    return "rent" in words and bool(words & _MARKET_RENT_WORDS)


# "Rent PSF" (rent per square foot) is a genuinely common commercial
# rent-roll column, especially on RealPage/MRI-style exports -- a RATE,
# not the tenant's total dollar rent (e.g. "2.75" meaning $2.75/sqft/
# month, not $2.75/month total). Found during self-review while
# researching RealPage/MRI terminology, not found broken in production:
# with no better rent column present, the bare "rent" alias would
# otherwise match "Rent PSF" and silently treat a per-square-foot rate
# as if it were the tenant's actual total rent -- wrong by roughly the
# unit's entire square footage, and silently so. Same denylist pattern
# as _MARKET_RENT_WORDS.
_RATE_NOT_AMOUNT_WORDS = {"psf"}


def _is_rate_not_amount_header(normalized_header: str) -> bool:
    words = set(normalized_header.split())
    return "rent" in words and bool(words & _RATE_NOT_AMOUNT_WORDS)


# "Property" alone is a genuinely common, useful column header (see the
# "property" alias above, and this module's own synthetic AppFolio
# fixture) -- but it's also a common WORD inside several other, very
# different real rent-roll columns that have nothing to do with a
# building's address: "Property Manager" (a person's name), "Property
# Type" (Retail/Office/Industrial), "Property Tax", "Property ID" (an
# internal PMS record id). Pass 2's substring matching would otherwise
# grab any of these via the bare "property" alias -- caught during
# self-review, not found broken in production. Denylisted the same way
# as _MARKET_RENT_WORDS, rather than removing the bare "property" alias
# entirely (which would break the common, legitimate bare-"Property"
# case this feature exists for in the first place).
_NON_ADDRESS_PROPERTY_WORDS = {"manager", "management", "type", "tax", "id", "code"}


def _is_non_address_property_header(normalized_header: str) -> bool:
    words = set(normalized_header.split())
    return "property" in words and bool(words & _NON_ADDRESS_PROPERTY_WORDS)

# A row is skipped (not imported as a tenant) if its tenant cell, once
# normalized, is blank, exactly matches one of these, OR starts with one
# of these as its own word/phrase (e.g. "Subtotal Floor 1", "Total (12
# units)") -- a real subtotal/total row's tenant-column text is often not
# the bare keyword alone. Checked as a leading-word/phrase match, not a
# substring, so a real tenant whose name merely CONTAINS one of these
# words elsewhere (e.g. "Totally Awesome Tenant") is never caught by
# this -- "totally" doesn't start with "total " (with the trailing
# space), only an actual "Total ..." row does. Broker rent rolls
# routinely include vacant-unit rows and a totals/subtotal row -- neither
# is a real lease, and importing one as if it were a tenant would
# fabricate a fake mega-tenant that doesn't exist (the exact failure mode
# compute_tenant_concentration's own docstring already worries about for
# a missing tenant name -- this is the same concern, applied at the
# import boundary instead). "0" is included for the same reason: a rent
# roll that marks a vacant unit's tenant cell with a literal "0" (instead
# of blank/VACANT/Vacant) should not import a fake tenant literally named
# "0".
_NON_TENANT_KEYWORDS = {"vacant", "vacancy", "total", "totals", "subtotal", "sub total", "n a", "na", "0"}

# Matches a Unit/Suite cell that already spells out its own designator
# (e.g. "Suite 101", "Ste. 101", "Unit 5", "Apt 2", "#12"), as opposed to
# a bare identifier (e.g. "101", "A") that still needs "Suite " prepended
# to read naturally combined with a base property address.
_UNIT_DESIGNATOR_RE = re.compile(r"^\s*(?:suite|ste\.?|unit|apt\.?|#)\s*[\w-]+", re.IGNORECASE)


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
            if field_name == "rent_amount" and (_is_market_rent_header(h) or _is_rate_not_amount_header(h)):
                continue  # see _MARKET_RENT_WORDS / _RATE_NOT_AMOUNT_WORDS -- never eligible for rent_amount, exact match or not
            if field_name == "property" and _is_non_address_property_header(h):
                continue  # see _NON_ADDRESS_PROPERTY_WORDS -- never eligible for property, exact match or not
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
                if field_name == "rent_amount" and (_is_market_rent_header(h) or _is_rate_not_amount_header(h)):
                    continue  # see _MARKET_RENT_WORDS / _RATE_NOT_AMOUNT_WORDS -- e.g. "Market Rent"/"Rent PSF" must not fall through to the bare "rent" alias
                if field_name == "property" and _is_non_address_property_header(h):
                    continue  # see _NON_ADDRESS_PROPERTY_WORDS -- e.g. "Property Manager" must not fall through to the bare "property" alias
                if pattern.search(h):
                    candidates.append((len(alias_norm), field_name, i))

    candidates.sort(key=lambda c: c[0], reverse=True)  # longest/most-specific alias first
    for _, field_name, i in candidates:
        if field_name in mapping or i in used_columns:
            continue  # already claimed by an even more specific match
        mapping[field_name] = i
        used_columns.add(i)

    return mapping


_HEADER_SCAN_WINDOW = 20  # generous bound for decorative title/date rows before the real header


def _find_header_row(all_rows: List[List[Any]]) -> int:
    """
    Returns the index (into all_rows) of the row that looks like the
    real column-header row -- the first one, scanning from the top
    within a bounded window, that _match_columns can find BOTH a
    tenant and a rent column in.

    A hand-built broker spreadsheet's row 0 is almost always already
    the real header. A canned PMS report (Yardi, AppFolio, ...) is
    different: it routinely opens with several decorative rows --
    property name, report title, "As of" date -- before the actual
    column-header row. Requiring BOTH a tenant AND a rent match (not
    just one) is what keeps this from false-matching a decorative row
    that happens to contain a stray recognizable word on its own (e.g.
    a title like "Rent Roll Report" contains "Rent" but has no tenant
    column, so it correctly isn't mistaken for the real header).

    Bounded to the first _HEADER_SCAN_WINDOW rows so a file with no
    real header at all (or one buried implausibly deep -- almost
    certainly not actually a rent roll) fails fast by falling back to
    row 0, which then produces parse_rent_roll_rows' existing, clear
    "no recognizable columns" error -- not a silent misinterpretation
    of what's actually a data row as if it were a header.
    """
    for i, row in enumerate(all_rows[:_HEADER_SCAN_WINDOW]):
        mapping = _match_columns(row)
        if "tenant" in mapping and "rent_amount" in mapping:
            return i
    return 0


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
    if normalized in _NON_TENANT_KEYWORDS:
        return False
    # Leading-phrase match too, not just a whole-cell exact match -- see
    # _NON_TENANT_KEYWORDS' own comment for why ("Subtotal Floor 1" needs
    # to be caught, not just a bare "Subtotal"). The trailing space in
    # the startswith check is what keeps this a real word/phrase boundary
    # rather than a substring match, so "Totally Awesome Tenant" is never
    # mistaken for a "Total ..." row.
    return not any(normalized.startswith(keyword + " ") for keyword in _NON_TENANT_KEYWORDS)


def parse_rent_roll_rows(
    headers: List[Any],
    rows: List[List[Any]],
    filename: str,
    base_property_address: Optional[str] = None,
    header_row_offset: int = 0,
    row_numbers: Optional[List[int]] = None,
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

    A portfolio-wide PMS export can instead cover several DIFFERENT
    properties in one file -- if the file has its own per-row Property/
    Community column, that row's own value overrides
    base_property_address for that row specifically (falling back to
    base_property_address only for rows where the per-row cell is
    blank), so those rows correctly group by their own actual building
    rather than all being incorrectly merged into whatever the uploader
    happened to type.

    `header_row_offset` is how many rows were skipped BEFORE `headers`
    itself -- 0 for a file whose row 1 already is the header (the
    common broker-spreadsheet case), or however many decorative rows
    _find_header_row skipped over for a PMS-style canned report. Used
    (via simple arithmetic: row_index + header_row_offset + 2) only
    when `row_numbers` isn't given, so each row's `source.row` citation
    still reflects roughly its real position in the original file.

    `row_numbers`, when given, is the TRUE 1-indexed original file row
    number for each entry in `rows`, positionally matched -- more
    precise than header_row_offset's arithmetic, which silently drifts
    wrong by however many fully-blank rows got dropped before parsing
    (both callers below drop blank rows anywhere in the file, and a
    real PMS report's decorative header block routinely has one between
    the title and the actual column-header row). Preferred whenever the
    caller can provide it; header_row_offset alone remains supported so
    existing direct callers/tests that don't pass row_numbers keep
    working unchanged.

    Returns `{leases: [...], skipped_rows: [{row, reason}, ...],
    column_mapping: {field_name: column_index, ...}}`. `leases` entries
    are `{extracted_fields, display_name}`, ready to hand to
    database.insert_lease() exactly like a PDF-extracted result.

    Raises RentRollImportError (fatal, nothing imported) only if NO row
    within the header-detection scan window has a recognizable tenant
    name column AND a recognizable rent column -- without at least
    those two, there's nothing to import. Everything else (a missing
    square footage column, an unparseable date in one row, a vacant-
    unit row) is handled per-row: either that one field is "not found"
    for that row, or that one row is skipped and reported, never a
    reason to fail the whole file.
    """
    column_mapping = _match_columns(headers)

    if "tenant" not in column_mapping or "rent_amount" not in column_mapping:
        raise RentRollImportError(
            "Couldn't find a row with a recognizable tenant name column and rent "
            "column anywhere in the first rows of this file. Recognized headers "
            "include things like \"Tenant\", \"Tenant Name\", \"Rent\", \"Monthly "
            "Rent\", \"Base Rent\" -- check that the file actually has a real column-"
            "header row (a title/date block before it is fine and is skipped "
            "automatically, but the header row itself must be within the first "
            f"{_HEADER_SCAN_WINDOW} rows)."
        )

    parsed_leases = []
    skipped_rows = []

    for row_index, row in enumerate(rows):
        if row_numbers is not None:
            row_num = row_numbers[row_index]
        else:
            row_num = row_index + header_row_offset + 2  # +1 for 1-indexing, +1 because the header row itself precedes the data

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
        landlord_str = _cell_to_str(cell("landlord"))
        unit_str = _cell_to_str(cell("unit"))
        sqft_str = _cell_to_str(cell("square_footage"))
        start_str = _cell_to_str(cell("lease_start_date"))
        end_str = _cell_to_str(cell("lease_end_date"))

        # A per-row Property column (portfolio-wide PMS exports covering
        # several buildings in one file) takes priority over the single
        # uploader-typed base_property_address for THIS row specifically
        # -- it's the more specific, row-level source of truth. Falls
        # back to base_property_address when the file has no property
        # column, or this particular row's cell is blank, so a mostly-
        # complete property column doesn't lose the uploader-supplied
        # fallback for the rows it's actually missing on.
        property_str = _cell_to_str(cell("property"))
        effective_base = property_str or base_property_address

        if effective_base and unit_str:
            # Many rent rolls' Unit/Suite column already spells out the
            # designator itself (e.g. "Suite 101", "Unit 5", "#12"), not
            # just a bare number -- unconditionally prepending "Suite "
            # in that case produced "Suite Suite 101", which then fails
            # to match the same unit's address on a lease PDF (e.g. via
            # compute_rent_roll_reconciliation's exact-address matching).
            # Only prepend "Suite" when the cell is a bare identifier.
            if _UNIT_DESIGNATOR_RE.match(unit_str):
                address = f"{effective_base}, {unit_str}"
            else:
                address = f"{effective_base}, Suite {unit_str}"
        elif effective_base:
            address = effective_base
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
        if landlord_str:
            set_field("landlord", landlord_str, landlord_str)
        set_field("property_address", address, unit_str if unit_str else (property_str or base_property_address))
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
    """
    Reads a CSV file's bytes and parses it via parse_rent_roll_rows.
    Raises RentRollImportError for a genuinely empty file. Auto-detects
    which row is the real header (see _find_header_row) rather than
    assuming row 1 always is -- a canned PMS export routinely has a few
    decorative rows (property name, report title, date range) above it.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")  # utf-8-sig strips a leading BOM, common from Excel's own CSV export
    reader = csv.reader(io.StringIO(text))
    # (true 1-indexed file row number, row) pairs, blank rows dropped --
    # tracking the TRUE row number here (rather than just dropping blank
    # rows and recomputing a citation from position alone) matters once
    # a decorative PMS-report header block is in play: those routinely
    # have a blank spacer row in them, which would otherwise silently
    # shift every later row's citation off by one.
    numbered_rows = [(i, row) for i, row in enumerate(reader, start=1) if any(cell.strip() for cell in row)]

    if not numbered_rows:
        raise RentRollImportError("This CSV file is empty -- nothing to import.")

    row_contents = [row for _, row in numbered_rows]
    header_idx = _find_header_row(row_contents)
    headers = row_contents[header_idx]
    data_entries = numbered_rows[header_idx + 1:]
    data_rows = [row for _, row in data_entries]
    data_row_numbers = [n for n, _ in data_entries]
    return parse_rent_roll_rows(
        headers, data_rows, filename, base_property_address,
        header_row_offset=header_idx, row_numbers=data_row_numbers,
    )


def parse_xlsx_rent_roll(file_bytes: bytes, filename: str, base_property_address: Optional[str] = None) -> Dict[str, Any]:
    """
    Reads an .xlsx file's bytes and parses it via parse_rent_roll_rows.
    Raises RentRollImportError for a genuinely empty or unreadable file.
    Auto-detects which row is the real header (see _find_header_row) --
    same reasoning as parse_csv_rent_roll.

    Checks every worksheet in the workbook, not just the first (active)
    one, using the first sheet where a header row with BOTH a
    recognizable tenant and rent column can be found -- a portfolio-wide
    PMS export routinely has a "Summary"/cover sheet before the actual
    per-unit data tab, and openpyxl's own `workbook.active` is just
    whichever sheet was selected when the file was last saved, which is
    no guarantee that's the one with real data (a real bug found via
    stress-testing: a workbook with a blank "Summary" sheet first and the
    real rent roll on a second "Detail" sheet was silently treated as
    having no usable data at all, because only the active sheet was ever
    read).
    """
    try:
        workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise RentRollImportError(f"Couldn't read this file as an Excel workbook: {exc}")

    if not workbook.sheetnames:
        raise RentRollImportError("This Excel file is empty -- nothing to import.")

    any_sheet_had_rows = False
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        # Same true-row-number tracking as parse_csv_rent_roll, and for
        # the same reason -- see the comment there.
        numbered_rows = [
            (i, list(row)) for i, row in enumerate(sheet.iter_rows(values_only=True), start=1)
            if any(cell is not None and str(cell).strip() for cell in row)
        ]
        if not numbered_rows:
            continue
        any_sheet_had_rows = True

        row_contents = [row for _, row in numbered_rows]
        header_idx = _find_header_row(row_contents)
        headers = row_contents[header_idx]
        if "tenant" not in _match_columns(headers) or "rent_amount" not in _match_columns(headers):
            continue  # this sheet has no usable header row -- try the next one

        data_entries = numbered_rows[header_idx + 1:]
        data_rows = [row for _, row in data_entries]
        data_row_numbers = [n for n, _ in data_entries]
        return parse_rent_roll_rows(
            list(headers), data_rows, filename, base_property_address,
            header_row_offset=header_idx, row_numbers=data_row_numbers,
        )

    if not any_sheet_had_rows:
        raise RentRollImportError("This Excel file is empty -- nothing to import.")

    # No sheet had a usable header -- delegate to parse_rent_roll_rows'
    # own clear error by calling it on the first non-empty sheet's rows,
    # so the message stays in exactly one place rather than being
    # duplicated here.
    return parse_rent_roll_rows([], [], filename, base_property_address)
