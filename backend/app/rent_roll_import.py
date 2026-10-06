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

from app.normalize import BinaryTextUploadError, decode_text_upload, normalize_header as _normalize_header, parse_currency, parse_date, parse_square_footage
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
    # "Bldg-Unit"/"Bldg/Unit" (Entrata, RealPage) normalize to "bldgunit"
    # once punctuation is stripped, so they need their own aliases.
    "unit": ["unit number", "unit #", "suite #", "unit", "suite", "space", "bldg-unit", "bldg/unit",
             "building/unit", "building unit", "bldg unit", "apt #", "apt", "apartment", "unit id"],
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
    # Affordable / Section 8 rent rolls: the resident's share and the
    # housing authority's Housing Assistance Payment. Contract rent (the
    # lease rent) is their sum -- see parse_rent_roll_rows. Listed before
    # "tenant" so "Tenant Portion"/"Tenant Rent" never become the tenant
    # NAME column (longest alias wins in Pass 2 anyway).
    "tenant_portion": ["tenant portion", "tenant rent", "resident rent", "resident portion", "tenant share",
                       "tenant paid", "tenant pays", "tenant payment"],
    "hap": ["hap", "hap amount", "hap payment", "subsidy", "subsidy amount", "housing assistance",
            "housing assistance payment", "assistance payment", "hud portion", "pha portion"],
    "rent_amount": [
        "contract rent", "gross rent", "total contract rent",
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
    # A monthly concession/discount column, when the PMS export has one
    # (Yardi/AppFolio "Concession" charge codes, RealPage "Concessions").
    # Lets the Deal Mismatch Report compare the concession the rent roll
    # SHOWS against the one the lease actually grants, instead of
    # assuming every rent roll omits concessions (see deal_mismatch.py's
    # detect_concession_mismatch). Never eligible for rent_amount, see
    # _is_concession_header.
    # Unit/lease status ("Current", "Vacant-Unrented", "Down", "Notice-
    # Rented"...). Not a lease field -- read only to tell an occupied unit
    # from a vacant/down one (see _unit_status_of_skipped_row).
    "status": ["unit/lease status", "unit lease status", "lease status", "unit status", "status"],
    "concessions": ["concession", "concessions", "rent concession", "monthly concession", "concession amount", "rent discount", "concession/month", "concession/mo", "concessions/month", "concessions/mo"],
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


_CONCESSION_WORDS = {"concession", "concessions", "discount", "discounts", "special", "specials"}


def _is_concession_header(normalized_header: str) -> bool:
    """
    "Rent Concession" / "Rent Discount" contain the word "rent" but hold a
    concession amount, not the tenant's rent -- reading one as rent_amount
    would replace every unit's rent with its discount.
    """
    return bool(set(normalized_header.split()) & _CONCESSION_WORDS)


# A concession column that ISN'T the dollar amount -- "Concession End
# Date", "Concession Months", "Concession Type". Reading one as dollars
# turned "2026-03-31" into a $2,026.00/mo concession (review finding,
# fix/concession-detection), so these are never eligible for `concessions`.
_CONCESSION_NON_AMOUNT_WORDS = {
    "date", "start", "end", "expires", "expiration", "thru", "through", "from", "to",
    "month", "months", "mos", "term", "type", "description", "desc", "code", "reason", "note", "notes",
}


def _is_concession_non_amount_header(normalized_header: str) -> bool:
    # "Concession Per Month" / "Concession a Month" IS the dollar amount --
    # only a bare "month(s)" means a count column.
    stripped = re.sub(r"\b(?:per|a|each|every)\s+month\b", " ", normalized_header)
    # "Concession/Month" normalizes to "concession month" -- singular,
    # right after "concession", it means per month (a count is "Months").
    stripped = re.sub(r"\b(concessions?)\s+month\b", r"\1", stripped)
    return bool(set(stripped.split()) & _CONCESSION_NON_AMOUNT_WORDS)


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


# rent_amount is a MONTHLY figure everywhere else this system uses it
# (dashboards, WALT, loss-to-lease, every other computation). "Annual
# Rent" is a real, common rent-roll column -- and its bare "rent" word
# would otherwise match the bare "rent" alias, silently mapping a
# once-a-year total into a field every downstream computation treats
# as monthly (roughly 12x too high). Found via stress-testing messy
# rent rolls, 2026-09. Same denylist pattern as _MARKET_RENT_WORDS/
# _RATE_NOT_AMOUNT_WORDS: the honest behavior is treating the file as
# if it has no recognizable rent column at all (an annual-to-monthly
# conversion isn't attempted -- guessing the header really does mean
# a clean /12 division is its own way to be silently wrong).
_ANNUAL_NOT_MONTHLY_WORDS = {"annual", "annualized", "yearly"}


def _is_annual_not_monthly_header(normalized_header: str) -> bool:
    words = set(normalized_header.split())
    return "rent" in words and bool(words & _ANNUAL_NOT_MONTHLY_WORDS)


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
_NON_TENANT_KEYWORDS = {"vacant", "vacancy", "total", "totals", "subtotal", "sub total", "grand total", "grand totals", "n a", "na", "0"}

# Matches a Unit/Suite cell that already spells out its own designator
# (e.g. "Suite 101", "Ste. 101", "Unit 5", "Apt 2", "#12"), as opposed to
# a bare identifier (e.g. "101", "A") that still needs "Suite " prepended
# to read naturally combined with a base property address.
_UNIT_DESIGNATOR_RE = re.compile(r"^\s*(?:suite|ste\.?|unit|apt\.?|#)\s*[\w-]+", re.IGNORECASE)


_TENANT_NAME_HEADERS = ["tenant name", "resident name", "lessee name", "tenant names", "resident names", "name"]


def _has_rent_column(mapping: Dict[str, int]) -> bool:
    """A rent column, or a Section 8 tenant-portion column the rent can be built from."""
    return "rent_amount" in mapping or "tenant_portion" in mapping


def _match_columns(headers: List[Any]) -> Dict[str, int]:
    """Maps canonical field name -> column index for whichever headers could be confidently matched. See module docstring."""
    normalized = [_normalize_header(h) for h in headers]
    mapping: Dict[str, int] = {}
    used_columns = set()

    # Pass 0: a column that is literally the tenant's NAME wins the tenant
    # field over a bare "Resident"/"Tenant" column. RealPage heads it just
    # "Name"; Yardi has "Resident" (an id like t0012345) next to "Name".
    # "Name" counts only as the whole header -- never "Property Name".
    for wanted in _TENANT_NAME_HEADERS:
        if "tenant" in mapping:
            break
        for i, h in enumerate(normalized):
            if h == wanted:
                mapping["tenant"] = i
                used_columns.add(i)
                break

    # Pass 1: exact match (most confident) -- "Rent" header equals the "rent" alias exactly.
    for field_name, aliases in _COLUMN_ALIASES.items():
        if field_name in mapping:
            continue
        alias_norms = {_normalize_header(a) for a in aliases}
        for i, h in enumerate(normalized):
            if i in used_columns:
                continue
            if field_name == "rent_amount" and (_is_market_rent_header(h) or _is_concession_header(h) or _is_rate_not_amount_header(h) or _is_annual_not_monthly_header(h)):
                continue  # see _MARKET_RENT_WORDS / _RATE_NOT_AMOUNT_WORDS -- never eligible for rent_amount, exact match or not
            if field_name == "property" and _is_non_address_property_header(h):
                continue  # see _NON_ADDRESS_PROPERTY_WORDS -- never eligible for property, exact match or not
            if field_name == "concessions" and _is_concession_non_amount_header(h):
                continue  # see _CONCESSION_NON_AMOUNT_WORDS -- a concession date/count/type column is not dollars
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
                if field_name == "rent_amount" and (_is_market_rent_header(h) or _is_concession_header(h) or _is_rate_not_amount_header(h) or _is_annual_not_monthly_header(h)):
                    continue  # see _MARKET_RENT_WORDS / _RATE_NOT_AMOUNT_WORDS -- e.g. "Market Rent"/"Rent PSF" must not fall through to the bare "rent" alias
                if field_name == "property" and _is_non_address_property_header(h):
                    continue  # see _NON_ADDRESS_PROPERTY_WORDS -- e.g. "Property Manager" must not fall through to the bare "property" alias
                if field_name == "concessions" and _is_concession_non_amount_header(h):
                    continue  # see _CONCESSION_NON_AMOUNT_WORDS -- e.g. "Concession End Date" must not be read as dollars
                if pattern.search(h):
                    candidates.append((len(alias_norm), field_name, i))

    candidates.sort(key=lambda c: c[0], reverse=True)  # longest/most-specific alias first
    for _, field_name, i in candidates:
        if field_name in mapping or i in used_columns:
            continue  # already claimed by an even more specific match
        mapping[field_name] = i
        used_columns.add(i)

    # Pass 3: one typo per long word ("Lease Strat", "Lease Expiraton",
    # "Tennant") for whatever is still unmapped. Same word count, every
    # word equal or (5+ letters) one edit/transposition away -- strict
    # enough that "Lease Status" never becomes a lease date.
    fuzzy = []
    for field_name, aliases in _COLUMN_ALIASES.items():
        if field_name in mapping:
            continue
        for alias in aliases:
            alias_words = _normalize_header(alias).split()
            for i, h in enumerate(normalized):
                if i in used_columns or not h:
                    continue
                if field_name == "rent_amount" and (_is_market_rent_header(h) or _is_concession_header(h) or _is_rate_not_amount_header(h) or _is_annual_not_monthly_header(h)):
                    continue
                if field_name == "property" and _is_non_address_property_header(h):
                    continue
                if field_name == "concessions" and _is_concession_non_amount_header(h):
                    continue
                header_words = h.split()
                if len(header_words) == len(alias_words) and header_words != alias_words and all(
                    hw == aw or (len(aw) >= 5 and len(hw) >= 5 and _one_typo_apart(hw, aw))
                    for hw, aw in zip(header_words, alias_words)
                ):
                    fuzzy.append((len(alias), field_name, i))
    fuzzy.sort(key=lambda c: c[0], reverse=True)
    for _, field_name, i in fuzzy:
        if field_name in mapping or i in used_columns:
            continue
        mapping[field_name] = i
        used_columns.add(i)

    return mapping


def _one_typo_apart(a: str, b: str) -> bool:
    """Damerau-Levenshtein distance <= 1: one insert, delete, substitute, or adjacent swap."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [k for k in range(len(a)) if a[k] != b[k]]
        if len(diffs) == 1:
            return True
        return len(diffs) == 2 and diffs[1] == diffs[0] + 1 and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    for k in range(len(long_)):
        if long_[:k] + long_[k + 1:] == short:
            return True
    return False


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
        if "tenant" in mapping and _has_rent_column(mapping):
            return i
    return 0


def _find_header(all_rows: List[List[Any]]):
    """
    (header cells, header row index, index of the first data row).

    A single header row is found exactly as _find_header_row always did.
    If none qualifies, a TWO-ROW header is tried: Yardi and other canned
    reports split each title over two rows ("Actual" / "Rent", "Lease" /
    "Expiration"), so neither row alone has a tenant AND a rent column.
    Each column's two parts are joined ("Actual Rent") and matched again.
    """
    idx = _find_header_row(all_rows)
    if "tenant" in _match_columns(all_rows[idx]) and _has_rent_column(_match_columns(all_rows[idx])):
        return list(all_rows[idx]), idx, idx + 1
    window = all_rows[:_HEADER_SCAN_WINDOW]

    def filled(row):
        return sum(1 for x in row if x is not None and str(x).strip())

    best = None  # (mapped field count, -i, combined, i)
    for i in range(len(window) - 1):
        top, bottom = list(window[i]), list(window[i + 1])
        if filled(top) < 2 or filled(bottom) < 2:
            continue  # a title line ("Rent Roll") is never half of a header
        width = max(len(top), len(bottom))
        top += [None] * (width - len(top))
        bottom += [None] * (width - len(bottom))
        combined = [" ".join(str(x).strip() for x in (a, b) if x is not None and str(x).strip()) or None
                    for a, b in zip(top, bottom)]
        mapping = _match_columns(combined)
        if "tenant" in mapping and _has_rent_column(mapping):
            candidate = (len(mapping), -i, combined, i)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best:
        return best[2], best[3], best[3] + 2
    return list(all_rows[idx]), idx, idx + 1


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
    strict = parse_currency(text)  # handles "$1,200.00" (and "-$1,200.00"/"($1,200.00)") using the existing, already-tested parser
    if strict is not None:
        return strict
    # Fall back to a bare number with no "$" -- same negative handling as
    # parse_currency (leading "-", or wrapping parens as accounting
    # notation for a credit/negative amount), see that function's
    # docstring for why silently dropping the sign is dangerous here.
    paren_match = re.search(r"\(\s*([\d,]+(?:\.\d+)?)\s*\)", text)
    if paren_match:
        if re.match(r"[A-Za-z]", text[paren_match.end():]):
            return None
        try:
            return -float(paren_match.group(1).replace(",", ""))
        except ValueError:
            return None
    match = re.search(r"(-\s?)?([\d,]+(?:\.\d+)?)", text)
    if not match:
        return None
    # Same OCR-truncation guard as normalize.parse_currency (see its own
    # docstring): a match immediately followed by a bare letter with no
    # separator ("1,2OO.00") is a corrupted/truncated number, not a real
    # one -- reject rather than silently return the truncated prefix.
    if re.match(r"[A-Za-z]", text[match.end():]):
        return None
    try:
        amount = float(match.group(2).replace(",", ""))
        return -amount if match.group(1) else amount
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


_VACANT_WORDS = {"vacant", "vacancy", "available", "unrented", "unoccupied", "empty"}
_DOWN_WORDS = {"down", "model", "offline", "renovation", "reno", "uninhabitable", "nonrevenue", "non revenue", "unavailable"}
# Whole-cell placeholders some exports put in the tenant column of an
# empty unit ("DOWN UNIT", "MODEL") -- whole-cell only, so a real tenant
# like "Model Unit Corp" is never mistaken for one. Sorted-word form.
_PLACEHOLDER_TENANT_CELLS = {"down", "down unit", "model", "model unit", "offline", "admin unit", "unavailable",
                             "renovation", "down renovation"}
_UNIT_ID_RE = re.compile(r"^[A-Za-z]{0,3}[\s#-]*\d[\w-]{0,8}$")


def _unit_status_of_skipped_row(row: List[Any], column_mapping: Dict[str, int], tenant_raw: Optional[str]) -> Optional[str]:
    """
    "vacant" or "down" when this row is a real unit with no current
    resident, else None (an occupied unit, or a total/subtotal/note row).

    A unit counts only if its Unit cell looks like a unit id ("101",
    "A-204", "#3B") -- a "Total"/"Floor 1" row never does. Vacant vs down:
    the status column (or, without one, the tenant cell) says vacant /
    down / model / offline. A status of vacant/down wins even when a name
    is present: "Vacant-Leased" is a future resident in an empty unit, not
    current rent. With no status column, a blank or "VACANT" tenant cell
    on a unit row is vacant.
    """
    def cell(field_name):
        idx = column_mapping.get(field_name)
        return _cell_to_str(row[idx]) if idx is not None and idx < len(row) else None

    unit = cell("unit")
    if not unit or not _UNIT_ID_RE.match(unit.strip()):
        return None

    def words(text):
        return set(re.sub(r"[^a-z\s]", " ", (text or "").lower()).split())

    status_words = words(cell("status"))
    whole_cell = " ".join(sorted(words(tenant_raw)))
    real_tenant = _is_real_tenant_name(tenant_raw) and whole_cell not in _PLACEHOLDER_TENANT_CELLS
    no_rent = _parse_import_currency(cell("rent_amount")) in (None, 0.0)
    if status_words & _VACANT_WORDS:
        return "vacant"
    if status_words & _DOWN_WORDS and (no_rent or not real_tenant):
        return "down"  # a model unit actually rented to a named tenant is still revenue
    if real_tenant:
        return None
    tenant_words = words(tenant_raw)
    if tenant_words & _DOWN_WORDS:
        return "down"
    if (tenant_words & _VACANT_WORDS or not tenant_raw) and no_rent:
        return "vacant"
    return None


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

    if "tenant" not in column_mapping or not _has_rent_column(column_mapping):
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
    # Per building (effective base address): occupied count + vacant/down
    # unit ids, so occupancy can be computed later -- vacant rows are not
    # imported as leases, which made every rent roll look 100% occupied.
    unit_summary: Dict[str, Dict[str, Any]] = {}

    def _summary_for(base):
        return unit_summary.setdefault(base, {"occupied_units": 0, "vacant_units": [], "down_units": []})

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
        non_occupied = _unit_status_of_skipped_row(row, column_mapping, tenant_raw)
        if non_occupied:
            unit_id = _cell_to_str(cell("unit"))
            base = _cell_to_str(cell("property")) or base_property_address
            if base:
                _summary_for(base)[f"{non_occupied}_units"].append(unit_id)
            skipped_rows.append({
                "row": row_num,
                "reason": f"{non_occupied} unit (no current resident) -- counted for occupancy, not imported as a lease",
            })
            continue
        if not _is_real_tenant_name(tenant_raw):
            skipped_rows.append({
                "row": row_num,
                "reason": "blank tenant, or looks like a vacancy/total/subtotal row, not a real tenant",
            })
            continue

        rent = _parse_import_currency(cell("rent_amount"))
        if "tenant_portion" in column_mapping and "hap" in column_mapping:
            # Section 8: with no contract-rent column, the lease rent is the
            # resident's portion plus the HAP. A "rent" column that is only
            # the resident's portion would understate every voucher unit.
            portion = _parse_import_currency(cell("tenant_portion"))
            hap = _parse_import_currency(cell("hap"))
            if "rent_amount" not in column_mapping or (rent is not None and portion is not None and abs(rent - portion) < 0.005):
                if portion is not None or hap is not None:
                    rent = round((portion or 0.0) + (hap or 0.0), 2)
        elif rent is None and "tenant_portion" in column_mapping:
            rent = _parse_import_currency(cell("tenant_portion"))
        landlord_str = _cell_to_str(cell("landlord"))
        unit_str = _cell_to_str(cell("unit"))
        sqft_str = _cell_to_str(cell("square_footage"))
        start_str = _cell_to_str(cell("lease_start_date"))
        end_str = _cell_to_str(cell("lease_end_date"))

        # A row with a "tenant" cell that isn't blank/a known non-tenant
        # keyword (so it passed the check above) but has NO rent and NO
        # parseable lease date at all is almost never a real lease row --
        # found via stress-testing messy rent rolls, 2026-09: a junk,
        # non-tabular line (a page-break/footer artifact from a PDF-to-
        # CSV conversion, e.g. "*** END OF PAGE 1 ***") has fewer real
        # columns than the header, so every OTHER field lands out of
        # range/blank, but its one text column still reads as a
        # syntactically valid "tenant name" -- _is_real_tenant_name has
        # no way to tell that apart from a real, if incomplete, tenant
        # row using text alone. Requiring at least one other real signal
        # is what catches it. A genuinely real tenant with every other
        # field missing is vanishingly rare in practice (a real lease
        # has SOME dollar figure or date attached); a row with a tenant
        # name and truly nothing else is far more often noise than data.
        if rent is None and parse_date(start_str) is None and parse_date(end_str) is None:
            skipped_rows.append({
                "row": row_num,
                "reason": "tenant name found but no rent or lease dates -- likely a non-data row (e.g. a page-break/footer artifact), not a real lease",
            })
            continue

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
        # Stored as the unsigned monthly amount: PMS exports show a
        # concession as either "-100.00" (a charge-code credit) or
        # "100.00", and both mean $100/month off. A $0.00 cell is kept
        # too -- "the rent roll explicitly shows no concession" is a
        # real, different fact from "this rent roll has no such column".
        concession = _parse_import_currency(cell("concessions"))
        if concession is not None:
            set_field("concessions", f"${abs(concession):,.2f}/mo", _cell_to_str(cell("concessions")))

        display_name = f"{tenant_raw} - {address}" if address else tenant_raw
        parsed_leases.append({"extracted_fields": fields, "display_name": display_name})
        if effective_base:
            _summary_for(effective_base)["occupied_units"] += 1

    return {
        "leases": parsed_leases,
        "skipped_rows": skipped_rows,
        "unit_summary": unit_summary,
        "column_mapping": column_mapping,
    }


def _parse_from_numbered_rows(
    numbered_rows: List[tuple],
    filename: str,
    base_property_address: Optional[str],
    empty_message: str,
) -> Dict[str, Any]:
    """
    Shared tail for every format: given ``(true_row_number, row)`` pairs
    (blank rows already dropped), auto-detect the header row and hand the
    rest to ``parse_rent_roll_rows``. Extracted so the CSV path and every
    non-spreadsheet format (PDF/Word/image, via
    ``rent_roll_table_extract``) run identical column-matching / row-
    parsing logic -- there is exactly one place that logic lives.
    """
    if not numbered_rows:
        raise RentRollImportError(empty_message)

    row_contents = [row for _, row in numbered_rows]
    headers, header_idx, data_start = _find_header(row_contents)
    data_entries = numbered_rows[data_start:]
    data_rows = [row for _, row in data_entries]
    data_row_numbers = [n for n, _ in data_entries]
    return parse_rent_roll_rows(
        headers, data_rows, filename, base_property_address,
        header_row_offset=header_idx, row_numbers=data_row_numbers,
    )


def parse_csv_rent_roll(
    file_bytes: bytes, filename: str, base_property_address: Optional[str] = None,
    delimiter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reads a CSV/TSV file's bytes and parses it via parse_rent_roll_rows.
    Raises RentRollImportError for a genuinely empty file. Auto-detects
    which row is the real header (see _find_header_row) rather than
    assuming row 1 always is -- a canned PMS export routinely has a few
    decorative rows (property name, report title, date range) above it.

    `delimiter` defaults to ',' -- pass '\\t' for a .tsv, or None to let
    the caller decide by extension. A .tsv whose rows still have no tab
    is retried as comma-separated before giving up.
    """
    try:
        text = decode_text_upload(file_bytes)  # UTF-8/BOM, UTF-16 (Excel "Unicode Text"), or Windows-1252
    except BinaryTextUploadError as exc:
        raise RentRollImportError(str(exc))

    def _rows_for(delim):
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        # (true 1-indexed file row number, row) pairs, blank rows dropped --
        # tracking the TRUE row number here (rather than just dropping blank
        # rows and recomputing a citation from position alone) matters once
        # a decorative PMS-report header block is in play: those routinely
        # have a blank spacer row in them, which would otherwise silently
        # shift every later row's citation off by one.
        return [(i, row) for i, row in enumerate(reader, start=1) if any(cell.strip() for cell in row)]

    if delimiter is None:
        # A .txt is usually Excel's tab-delimited "Text"/"Unicode Text"
        # save, but can be a comma CSV under another name: go by which
        # separator the first lines actually use.
        head = text[:4000]
        delimiter = "\t" if head.count("\t") > head.count(",") else ","
    numbered_rows = _rows_for(delimiter)
    # A .tsv that came through with no tabs at all (someone renamed a
    # .csv) collapses to one column -- retry as comma before failing.
    if delimiter == "\t" and numbered_rows and max(len(r) for _, r in numbered_rows) == 1:
        retried = _rows_for(",")
        if retried and max(len(r) for _, r in retried) > 1:
            numbered_rows = retried

    return _parse_from_numbered_rows(
        numbered_rows, filename, base_property_address,
        "This file is empty -- nothing to import.",
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
        headers, header_idx, data_start = _find_header(row_contents)
        if "tenant" not in _match_columns(headers) or not _has_rent_column(_match_columns(headers)):
            continue  # this sheet has no usable header row -- try the next one

        data_entries = numbered_rows[data_start:]
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


def _extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower() if filename and "." in filename else ""


def parse_rent_roll_file(
    file_bytes: bytes, filename: str, base_property_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Single entry point for a rent-roll upload in ANY supported format.

    Spreadsheets and delimited text are read here directly (csv/openpyxl,
    the long-standing well-tested paths). Every other format -- .xls,
    .docx, .pdf, and image files -- is reduced to a plain list of rows by
    ``rent_roll_table_extract.extract_rent_roll_table`` and then run
    through the EXACT same ``_parse_from_numbered_rows`` ->
    ``parse_rent_roll_rows`` pipeline: identical column-header matching,
    identical row parsing, identical output shape. No format gets its own
    downstream logic.

    Returns the same dict ``parse_rent_roll_rows`` returns, plus a
    ``source_kind`` string and a ``warnings`` list (empty for clean
    structured files; populated for OCR / heuristic reconstructions so
    the route can pass an honest caveat to the frontend).

    Raises ``RentRollImportError`` (the route already handles it as a
    400) with a specific message for every failure -- unsupported type,
    empty file, a document that genuinely isn't a table.
    """
    ext = _extension_of(filename)

    from app.t12_import import PASSWORD_PROTECTED_MESSAGE, is_password_protected_office_file
    if is_password_protected_office_file(file_bytes):
        raise RentRollImportError(PASSWORD_PROTECTED_MESSAGE)

    if ext in ("csv", "tsv", "txt"):
        result = parse_csv_rent_roll(
            file_bytes, filename, base_property_address,
            delimiter={"tsv": "\t", "csv": ","}.get(ext),
        )
        result.setdefault("source_kind", "delimited")
        result.setdefault("warnings", [])
        return result

    if ext in ("xlsx", "xlsm"):
        result = parse_xlsx_rent_roll(file_bytes, filename, base_property_address)
        result.setdefault("source_kind", "excel")
        result.setdefault("warnings", [])
        return result

    # .xls / .docx / .pdf / images -> reduce to rows, then shared pipeline.
    from app.rent_roll_table_extract import extract_rent_roll_table

    table = extract_rent_roll_table(file_bytes, filename)
    numbered_rows = [
        (i, [_cell_to_str(c) or "" for c in row])
        for i, row in enumerate(table.rows, start=1)
        if any((c or "").strip() for c in row)
    ]
    result = _parse_from_numbered_rows(
        numbered_rows, filename, base_property_address,
        "We opened this file but found no rows to import.",
    )

    # A reconstructed grid (OCR, or a borderless PDF rebuilt from word
    # positions) can pass the "looks like a table" gate yet still have
    # columns misaligned enough that not one row parses into a lease.
    # That's not a successful import of zero -- it's a failure to read
    # the structure, and the user should be told so plainly rather than
    # shown an empty "0 imported" result that looks like their file was
    # blank.
    _RECONSTRUCTED = {"pdf-text-reconstructed", "pdf-ocr", "image-ocr"}
    if table.source_kind in _RECONSTRUCTED and not result["leases"]:
        raise RentRollImportError(
            "We read this file but couldn't line its text up into a rent-roll table reliably "
            "-- the columns didn't come out cleanly enough to trust. This is common with "
            "photos, scans, and PDFs that aren't a ruled table. Export the rent roll to Excel "
            "or CSV from your property-management system and upload that instead."
        )

    result["source_kind"] = table.source_kind
    result["warnings"] = list(table.warnings)
    if table.ocr_confidence is not None:
        result["ocr_confidence"] = table.ocr_confidence
    return result
