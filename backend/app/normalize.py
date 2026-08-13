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


def parse_currency(value: Optional[str]) -> Optional[float]:
    """
    "$6,250.00" -> 6250.0 ; "$1,000,000 per occurrence" -> 1000000.0
    Returns None if no dollar amount is found.
    """
    if not value:
        return None
    match = re.search(r"\$\s?([\d,]+(?:\.\d+)?)", value)
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

    # MM/DD/YYYY or M-D-YY etc.
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", value)
    if match:
        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        return _safe_date(year, month, day)

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


def rent_per_sqft(rent_value: Optional[str], sqft_value: Optional[str]) -> Optional[float]:
    """Monthly rent per square foot, or None if either input is missing/unparseable."""
    rent = parse_currency(rent_value)
    sqft = parse_square_footage(sqft_value)
    if rent is None or sqft is None or sqft == 0:
        return None
    return rent / sqft
