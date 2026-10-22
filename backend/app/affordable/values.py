"""
Turn the raw text found in a form field into a typed value, or reject it.

Separate from normalize.parse_currency on purpose: that one only accepts
amounts with a "$", and HUD/IRS forms pre-print the "$" in the label and
leave it off the value ("1,325", "415,800"). Accepting bare numbers is only
safe here, where we already know the field holds money.
"""

import re
from datetime import date
from typing import Iterable, Optional

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

MONEY_TOKEN = re.compile(r"\$?\s?(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?(?![\d,])")
NUM_DATE = re.compile(r"(?<!\d)(\d{1,2})\s?[/\-.]\s?(\d{1,2})\s?[/\-.]\s?(\d{2,4})(?!\d)")
ISO_DATE = re.compile(r"(?<!\d)(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})(?!\d)")
WORD_DATE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")
INT_TOKEN = re.compile(r"(?<![\d.,])(\d{1,7})(?![\d.,]\d)")
PCT_TOKEN = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,4})?)\s?%?")

# Words that make up form labels and instructions. A "value" made only of
# these (plus punctuation) is a label the box caught, not something typed in.
LABEL_WORDS = {
    "name", "names", "address", "street", "city", "state", "zip", "code", "county", "date", "dates",
    "unit", "number", "no", "bedrooms", "bedroom", "of", "the", "and", "or", "for", "to", "in", "if", "any",
    "enter", "print", "type", "signature", "sign", "signed", "including", "apartment", "apt", "first",
    "last", "middle", "initial", "full", "tenant", "owner", "family", "head", "household", "member",
    "members", "income", "certification", "rent", "amount", "total", "monthly", "annual", "contract",
    "lease", "term", "effective", "move", "in", "phone", "telephone", "email", "title", "agency",
    "authority", "public", "housing", "program", "building", "property", "project", "development",
    "identification", "id", "bin", "pha", "hud", "form", "page", "part", "section", "line", "see",
    "instructions", "box", "check", "one", "yes", "n/a", "na", "other", "mm/dd/yyyy", "mmddyyyy",
    "town", "with", "by", "at", "on", "as", "is", "be", "this", "that", "your", "do", "not", "use",
    "p", "o", "po", "a", "an", "s", "applicable", "required", "optional",
}


def _clean_text(raw: str) -> str:
    text = raw.replace("_", " ")
    text = re.sub(r"\s*\|\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" :;,-–—.|#()[]")


def looks_like_label(text: str, extra_phrases: Iterable[str] = ()) -> bool:
    """True when `text` is form furniture: empty, underscores, all label words,
    or one of this form's own printed phrases."""
    norm = re.sub(r"[^a-z0-9/ ]+", " ", text.lower())
    tokens = [t for t in norm.split() if t]
    if not tokens:
        return True
    if all(t in LABEL_WORDS for t in tokens):
        return True
    squashed = "".join(tokens)
    for phrase in extra_phrases:
        p = re.sub(r"[^a-z0-9]+", "", phrase.lower())
        if p and squashed == p:
            return True
    return False


def parse_money(raw: str) -> Optional[float]:
    # OCR reads a printed "$" as "5" or "S" ("5 76,064"); in a money field a lone
    # 5/S followed by a space and digits is the dollar sign.
    raw = re.sub(r"(?<![\d,.])[5S]\s+(?=\d)", "$", raw)
    for m in MONEY_TOKEN.finditer(raw.replace("O", "0") if re.search(r"\d", raw) else raw):
        whole = m.group(1).replace(",", "")
        try:
            return float(whole + (m.group(2) or ""))
        except ValueError:
            continue
    return None


def _year(y: str) -> int:
    n = int(y)
    return n + 2000 if n < 100 else n


def parse_date(raw: str) -> Optional[date]:
    text = raw.replace("O", "0") if re.search(r"\d", raw) else raw
    for rx, order in ((ISO_DATE, "ymd"), (NUM_DATE, "mdy")):
        for m in rx.finditer(text):
            a, b, c = m.groups()
            try:
                if order == "ymd":
                    return date(int(a), int(b), int(c))
                return date(_year(c), int(a), int(b))
            except ValueError:
                continue
    for m in WORD_DATE.finditer(raw):
        month = MONTHS.get(m.group(1)[:3].lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                continue
    return None


def parse_int(raw: str) -> Optional[int]:
    m = INT_TOKEN.search(raw.replace(",", ""))
    return int(m.group(1)) if m else None


def parse_pct(raw: str) -> Optional[float]:
    m = PCT_TOKEN.search(raw)
    return float(m.group(1)) if m else None


def coerce(raw: str, vtype: str, label_phrases: Iterable[str] = (), *, label_guard: bool = True) -> Optional[str]:
    """The display string for a field of type `vtype`, or None if `raw`
    doesn't hold a usable value of that type."""
    text = _clean_text(raw or "")
    if not text:
        return None
    if vtype == "money":
        v = parse_money(text)
        return None if v is None else f"${v:,.2f}"
    if vtype == "date":
        d = parse_date(text)
        return None if d is None else d.strftime("%m/%d/%Y")
    if vtype == "int":
        v = parse_int(text)
        return None if v is None else str(v)
    if vtype == "pct":
        v = parse_pct(text)
        return None if v is None else f"{v:g}%"
    if vtype == "checkbox":
        return "X" if re.search(r"\b[xX✓✔]\b|^[xX]$", text) else None
    # text
    # OCR scatters ";" and ":" inside words and phrases ("Cedar Hollow: Housing LP")
    text = re.sub(r"(?<=[A-Za-z]);\s", ", ", text)
    text = re.sub(r"(?<=[A-Za-z]{2}):\s", " ", text)
    if label_guard and looks_like_label(text, label_phrases):
        return None
    if not re.search(r"[A-Za-z0-9]", text):
        return None
    # a value that is exactly a date is never a name, title or address
    # (IDs like "800091733" or "204" are digits but not dates, and stay valid)
    stripped = text.strip()
    if any(rx.fullmatch(stripped) for rx in (NUM_DATE, ISO_DATE, WORD_DATE)):
        return None
    return text
