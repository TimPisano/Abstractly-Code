"""
Normalization utilities: turn the extraction engine's human-readable
display strings ("$6,250.00", "April 1, 2025", "3% annually", "10 days
after written notice", "2,400 sq ft") into real numbers/dates that
portfolio math, risk thresholds, comparison, and the Q&A engine can
actually compute with.

The extraction engine's job is to produce source-verifiable display
strings, not typed values — keeping that separate from this parsing
layer means every downstream module shares one (tested) implementation
of "what does this string actually mean" instead of subtly disagreeing.

Every function here is deliberately forgiving: given a string it can't
parse, it returns None rather than raising, since "field not found" and
"field found but unparseable" should both just mean "skip this in the
aggregate," not crash a portfolio-wide computation over one bad value.
"""

import re
from datetime import date
from typing import Optional, Dict, Any


MONTHS_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def format_currency(value: Optional[float]) -> str:
    """None (or anything unparseable) becomes an explicit phrase, never a blank or a zero. Was duplicated (less defensively) in qa_engine.py."""
    if value is None:
        return "Not available"
    try:
        return "${:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return "Not available"


def format_sqft(value: Optional[float]) -> str:
    """Same None/unparseable handling as format_currency. Was duplicated (less defensively) in qa_engine.py."""
    if value is None:
        return "Not available"
    try:
        return "{:,.0f} sq ft".format(float(value))
    except (TypeError, ValueError):
        return "Not available"


def normalize_header(header: Any) -> str:
    """
    Lowercases, strips punctuation, collapses internal whitespace, and
    trims a spreadsheet column header for matching. Was duplicated
    identically in rent_roll_import.py and t12_import.py.

    Whitespace collapse (found via stress-testing messy rent rolls,
    2026-09): a header like "Tenant   Name" (multiple internal spaces --
    a real artifact of hand-built broker spreadsheets and some PDF-to-
    CSV conversions) previously normalized to "tenant   name", which
    matched neither the exact alias "tenant name" (Pass 1) nor its
    word-boundary substring search (Pass 2, since re.escape'd a single
    space) in rent_roll_import._match_columns -- the column silently
    went unmapped instead of matching the obviously-intended alias.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(header).lower())).strip()


def extracted_field_value(lease: Dict[str, Any], field_name: str) -> Optional[str]:
    """
    Reads one extracted field's value, tolerating every shape a partially
    populated or amendment-merged record can take (missing extracted_fields,
    missing field, field present but null). Was duplicated identically
    across report.py/rent_roll_export.py/sheets_export.py/summary_memo.py --
    consolidated here since all four bodies were byte-for-byte the same.
    """
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field_name)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    return value if value not in (None, "") else None


def parse_currency(value: Optional[str]) -> Optional[float]:
    """
    "$6,250.00" -> 6250.0 ; "$1,000,000 per occurrence" -> 1000000.0
    Returns None if no dollar amount is found.

    Rejects a match immediately followed by a letter with no separator
    (found via stress-testing OCR-garbled rent rolls, 2026-09): OCR
    routinely confuses a digit for a letter mid-number ("$1,2OO.00" for
    "$1,200.00") -- [\\d,]+ then stops at the "O", silently returning a
    truncated 12.0 instead of failing. A real amount is never directly
    followed by a bare letter (currency, whitespace, punctuation, or
    end-of-string are the only legitimate next characters), so treating
    that shape as corrupted and returning None -- an honest "couldn't
    read this" -- is safer than confidently reporting a truncated wrong
    number.
    """
    if not value:
        return None
    match = re.search(r"\$\s?([\d,]+(?:\.\d+)?)", value)
    if match and re.match(r"[A-Za-z]", value[match.end():]):
        return None
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_percent(value: Optional[str]) -> Optional[float]:
    """"3% annually" -> 3.0 ; "4.5% increase" -> 4.5"""
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_days(value: Optional[str]) -> Optional[int]:
    """"10 days after written notice" -> 10"""
    if not value:
        return None
    match = re.search(r"(\d+)\s*days?", value, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_square_footage(value: Optional[str]) -> Optional[float]:
    """"2,400 sq ft" -> 2400.0"""
    if not value:
        return None
    match = re.search(r"([\d,]+(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_date(value: Optional[str]) -> Optional[date]:
    """
    Parses the date formats field_extractor.py's DATE_REGEX can produce:
      - "04/01/2025" or "4-1-25"
      - "April 1, 2025" / "Sept 1 2025" / "Apr. 1, 2025"
      - "1st day of January, 2026"
    Returns None if the string doesn't match a recognized shape.
    """
    if not value:
        return None
    value = value.strip()

    # MM/DD/YYYY or M-D-YY etc. -- this app's existing, documented
    # convention (US-style, month first) for the genuinely ambiguous
    # case where both readings would be valid (e.g. "03/04/2024").
    #
    # DD/MM fallback (found via stress-testing messy rent rolls,
    # 2026-09): a value like "25/03/2023" is UNAMBIGUOUSLY day-then-
    # month -- no calendar has a 25th month -- so treating the first
    # component as MM/DD-first below made date(year, 25, 3) raise and
    # this function return None, silently dropping a perfectly
    # well-formed date rather than reading it correctly. Only swaps
    # when doing so turns an invalid date into a valid one; the
    # genuinely ambiguous case (both components <= 12) is deliberately
    # left exactly as before -- there is no universally correct answer
    # for "03/04/2024" without an explicit source-locale signal this
    # string doesn't carry, so this keeps resolving it MM/DD-first
    # rather than silently flipping an existing, working convention.
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", value)
    if match:
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        mm_dd = _safe_date(year, first, second)
        if mm_dd is not None:
            return mm_dd
        return _safe_date(year, second, first)  # DD/MM fallback -- only reached when MM/DD was invalid

    # "1st day of January, 2026" (legal style)
    match = re.match(
        r"^(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+([A-Za-z]+\.?),?\s+(\d{4})$",
        value, re.IGNORECASE
    )
    if match:
        day = int(match.group(1))
        month = MONTHS_MAP.get(match.group(2).lower().rstrip("."))
        year = int(match.group(3))
        if month:
            return _safe_date(year, month, day)
        return None

    # "April 1, 2025" / "Sept 1 2025" / "Apr. 1st, 2025"
    match = re.match(
        r"^([A-Za-z]+\.?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$",
        value, re.IGNORECASE
    )
    if match:
        month = MONTHS_MAP.get(match.group(1).lower().rstrip("."))
        day = int(match.group(2))
        year = int(match.group(3))
        if month:
            return _safe_date(year, month, day)
        return None

    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_renewal_options(value: Optional[str]) -> Dict[str, Any]:
    """
    Parses the composite renewal_options display string back into
    structured pieces, e.g.
      "2 option(s) of 5 year(s) each; 180 days notice; renewal rent
      based on then-prevailing fair market rate"
    ->
      {"num_options": 2, "term_years": 5, "notice_days": 180,
       "basis": "then-prevailing fair market rate"}
    Any piece that can't be found is None.
    """
    result = {"num_options": None, "term_years": None, "notice_days": None, "basis": None}
    if not value:
        return result

    match = re.search(r"(\d+)\s*option\(s\)\s*of\s*(\d+)\s*year\(s\)", value, re.IGNORECASE)
    if match:
        result["num_options"] = int(match.group(1))
        result["term_years"] = int(match.group(2))

    match = re.search(r"(\d+)\s*days\s*notice", value, re.IGNORECASE)
    if match:
        result["notice_days"] = int(match.group(1))

    match = re.search(r"renewal rent based on (.+?)(?:;|$)", value, re.IGNORECASE)
    if match:
        result["basis"] = match.group(1).strip()

    return result


def parse_termination_options(value: Optional[str]) -> Dict[str, Any]:
    """
    Parses the composite termination_options display string (see
    field_extractor._extract_termination_options) back into structured
    pieces, e.g. "terminable after year 3 of the term; 180 days notice"
    -> {"years_into_term": 3, "notice_days": 180}. Any piece that can't
    be found is None -- same "don't guess a missing sub-part" contract
    as parse_renewal_options.
    """
    result = {"years_into_term": None, "notice_days": None}
    if not value:
        return result

    match = re.search(r"year\s+(\d+)\s+of\s+the\s+term", value, re.IGNORECASE)
    if match:
        result["years_into_term"] = int(match.group(1))

    match = re.search(r"(\d+)\s*days\s*notice", value, re.IGNORECASE)
    if match:
        result["notice_days"] = int(match.group(1))

    return result


def rent_per_sqft(rent_value: Optional[str], sqft_value: Optional[str]) -> Optional[float]:
    """Monthly rent per square foot, or None if either input is missing/unparseable."""
    rent = parse_currency(rent_value)
    sqft = parse_square_footage(sqft_value)
    if rent is None or sqft is None or sqft == 0:
        return None
    return rent / sqft


def parse_escalation_schedule(value: Optional[str]):
    """
    Parses a year-by-year rent_escalation display string, e.g.
      "Year 1: $6,000.00; Year 2: $6,180.00; Year 3: $6,365.00"
    into [(1, 6000.0), (2, 6180.0), (3, 6365.0)], sorted by year.
    Returns [] if the value isn't a year-by-year table (e.g. it's a bare
    "3% annually" string instead — use parse_percent for that shape).
    """
    if not value:
        return []
    matches = re.findall(r"Year\s+(\d+)\s*:\s*\$?([\d,]+(?:\.\d+)?)", value, re.IGNORECASE)
    if not matches:
        return []
    try:
        pairs = [(int(year), float(amount.replace(",", ""))) for year, amount in matches]
    except ValueError:
        return []
    return sorted(pairs, key=lambda p: p[0])


def escalation_rate_consistency(value: Optional[str]):
    """
    For a year-by-year escalation table, computes the year-over-year
    percentage increase between each consecutive pair and reports how
    consistent they are. Returns None if there aren't at least 2
    consecutive years to compare (including a bare percentage string,
    which has nothing to check internal consistency against).

    Returns a dict: {"rates": [pct, ...], "min_rate": float,
    "max_rate": float, "spread": float} where spread = max_rate -
    min_rate (0 for a perfectly consistent schedule).
    """
    pairs = parse_escalation_schedule(value)
    if len(pairs) < 3:
        # Need at least 2 consecutive increases (3 years) to judge
        # "consistency" — a single increase has nothing to compare against.
        return None

    rates = []
    for (_, amt1), (_, amt2) in zip(pairs, pairs[1:]):
        if amt1 == 0:
            continue
        rates.append(((amt2 - amt1) / amt1) * 100)

    if len(rates) < 2:
        return None

    return {
        "rates": rates,
        "min_rate": min(rates),
        "max_rate": max(rates),
        "spread": max(rates) - min(rates),
    }
