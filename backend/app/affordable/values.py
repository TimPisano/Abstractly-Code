"""
Turn the raw text found in a form field into a typed value, or reject it.

Separate from normalize.parse_currency on purpose: that one only accepts
amounts with a "$", and HUD/IRS forms pre-print the "$" in the label and
leave it off the value ("1,325", "415,800"). Accepting bare numbers is only
safe here, where we already know the field holds money.
"""

import re
from datetime import date
from typing import Iterable, List, Optional

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


# ---------------------------------------------------------------------------
# cleanup of read values (form reader and AI alike)
# ---------------------------------------------------------------------------

FRACTIONS = {"¼": "1/4", "½": "1/2", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8"}
# OCR reads a Roman numeral's capital I as lowercase l: "Cottonwood ll" (II), "Phase lll".
# Lowercase only: "ll" and "lll" are never words, but "Ill" is (Illinois).
OCR_ROMAN = re.compile(r"(?<=[A-Za-z] )l{2,3}(?=$|[\s,.;:)])")
# HUD Section 8 contract numbers: state, 2 digits, a letter, 6 digits ("TX24E000008");
# documents print them with hyphens or spaces ("TX24-E000-008").
HUD_CONTRACT = re.compile(r"([A-Z]{2})\s?-?\s?(\d{2})\s?-?\s?([A-Z])\s?-?\s?(\d{3})\s?-?\s?(\d{3})")


ENTITY_DESCRIPTOR = re.compile(
    r",?\s+an?\s+(?:[A-Z][A-Za-z]+\s+){0,3}(?:limited partnership|limited liability company|"
    r"general partnership|corporation|nonprofit corporation|non-profit corporation|public body|"
    r"public agency|municipal corporation)\.?$", re.I)


_ONES = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
NUMBER_WORDS = {w: i + 1 for i, w in enumerate(_ONES)}
NUMBER_WORD = re.compile(r"\b(?:(twenty|thirty|forty|fifty)(?:[\s-]+(one|two|three|four|five|six|seven|eight|nine))?"
                         r"|(" + "|".join(_ONES) + r"))\b", re.I)


def _number_word(m: re.Match) -> str:
    if m.group(3):
        return str(NUMBER_WORDS[m.group(3).lower()])
    return str(_TENS[m.group(1).lower()] + (NUMBER_WORDS[m.group(2).lower()] if m.group(2) else 0))


def tidy(name: str, value):
    """Clean OCR and typing noise out of a read value. Only rewrites shapes
    that can't be anything else; never turns one number into another."""
    if not isinstance(value, str):
        return value
    text = value
    for sym, frac in FRACTIONS.items():
        text = re.sub(rf"(?<=\d){sym}", f" {frac}", text).replace(sym, frac)
    text = OCR_ROMAN.sub(lambda m: "I" * len(m.group(0)), text)
    if name.endswith(("owner_name", "assignee_name", "landlord")) or name in ("landlord",):
        # "NCRC Example LP, a California limited partnership": the descriptor isn't part of the name
        text = ENTITY_DESCRIPTOR.sub("", text)
    if name.endswith(("_term", "term_years")) and not re.search(r"\d", text):
        # a contract term, asked for as "20 years": "Twenty years" is the same term
        # ("Fifteen (15) years" already gives the digits and is left as written)
        text = NUMBER_WORD.sub(_number_word, text)
    if name.startswith("contract_number"):
        m = HUD_CONTRACT.fullmatch(text.strip())
        if m:
            text = "".join(m.groups())
    return text


# ---------------------------------------------------------------------------
# addresses
# ---------------------------------------------------------------------------

STATES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
          "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
          "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
          "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
          "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
          "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
          "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
          "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
          "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
          "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC", "puerto rico": "PR"}
_STATE = r"(?P<state>[A-Z]{2}|" + "|".join(sorted((s.title() for s in STATES), key=len, reverse=True)) + r")"
ADDRESS = re.compile(rf"^(?P<street>.+?),\s*(?P<city>[A-Za-z][A-Za-z .'\-]*?),?\s+{_STATE}\.?,?\s+(?P<zip>\d{{5}}(?:-\d{{4}})?)$")
STREET_NO = re.compile(r"^\s*\d+[A-Za-z]?\b")


def split_address(text: str) -> Optional[dict]:
    """"926 and 932 W. 5th Street, Corona, CA 92882" -> street, city, state, zip.
    Only for a one-line address that ends in state and ZIP; else None. The
    state is returned as written ("Utah" stays "Utah")."""
    m = ADDRESS.match(re.sub(r"\s+", " ", (text or "").strip()).rstrip("."))
    if not m:
        return None
    return {k: m.group(k).strip().rstrip(",") for k in ("street", "city", "state", "zip")}


def expand_address_list(text: str) -> List[str]:
    """"57, 81, 101 and 119 Kane Creek Blvd" -> ["57 Kane Creek Blvd", ..., "119 Kane Creek Blvd"].
    Also splits "; "-separated lists. A single address comes back as a
    one-item list. Only the street part is expanded; anything after the
    first comma that follows the street name is dropped."""
    out: List[str] = []
    for chunk in re.split(r"\s*;\s*", text or ""):
        m = re.match(r"^\s*((?:\d+[A-Za-z]?\s*(?:,|&|and)\s*)+(?:and\s+|&\s*)?)(\d+[A-Za-z]?)\s+([A-Za-z].*?)(?:,|$)", chunk)
        if m:
            numbers = re.findall(r"\d+[A-Za-z]?", m.group(1)) + [m.group(2)]
            out += [f"{n} {m.group(3).strip()}" for n in numbers]
        elif chunk.strip():
            out.append(chunk.strip())
    return out


def fill_address_parts(fields: dict) -> None:
    """Fill street_address / city / state / zip from property_address when the
    reader didn't return them, and list every building address
    (building_address_1, _2, ...) when the document lists several. Values are
    split out of what the document states, never looked up; method "split"."""
    full = fields.get("property_address")
    parts = split_address(str(full["value"])) if full and full.get("value") else None
    if parts:
        for name, key in (("street_address", "street"), ("city", "city"), ("state", "state"), ("zip", "zip")):
            if not (fields.get(name) or {}).get("value"):
                fields[name] = {**full, "value": parts[key], "method": "split"}
    listed = fields.get("building_addresses") or fields.get("street_address")
    if listed and listed.get("value") and not any(n.startswith("building_address_") for n in fields):
        addresses = expand_address_list(str(listed["value"]))
        if len(addresses) > 1:
            for i, a in enumerate(addresses, start=1):
                fields[f"building_address_{i}"] = {**listed, "value": a, "method": "split"}
