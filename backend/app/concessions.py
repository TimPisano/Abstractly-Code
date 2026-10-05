"""
Lease concessions: finding them in a lease's text, turning them into a
structured schedule, and computing the lease's EFFECTIVE rent from that
schedule -- the piece the Deal Mismatch Report's concession checks
(deal_mismatch.py's detect_concession_missing / detect_concession_mismatch
/ detect_concession_expiring) and its effective-rent-aware rent comparison
are built on.

Why this matters for a multifamily deal: a rent roll usually lists each
unit's GROSS contract rent ("$1,075.00"). If the lease actually gave the
resident a month free, or $100/month off for six months, the money the
property really collects is lower than the rent roll implies. A buyer
underwriting off the rent roll's gross number overpays for income that
was never there. Underwriters handle this with "net effective rent": the
average monthly rent over the lease term after every concession is
netted out. The gap between gross and net effective rent, annualized, is
the dollar figure the report shows.

Three kinds of concession are recognized, because they apply differently:

  - free_rent          -- N whole (or half) months of rent abated/waived,
                          e.g. "one (1) month of Base Rent ... is abated".
                          Its dollar value depends on the lease's base
                          rent, so it's computed at report time, not here.
  - recurring_discount -- a fixed $ (or %) off every month for some number
                          of months, or for the whole term, e.g. "Base Rent
                          is reduced by $100.00 per month for the first six
                          (6) months".
  - one_time_credit    -- a single dollar credit, e.g. "$500 move-in
                          credit", or "first month's rent reduced to $500".

Each one also records HOW and WHEN it applies: its trigger (move-in,
renewal, retention, military, employee), where in the term it falls
(first months, last months, or an explicit calendar range the lease
states), whether the lease says the concession is recaptured if the
resident defaults, and whether its duration had to be assumed because
the lease didn't state one.

Design notes, in the same "None means not enough data, never a guessed
zero" spirit portfolio.py and deal_mismatch.py follow:

  * The PARSER (parse_concessions) is pure text -> schedule. It never
    needs base rent or lease dates, so the same schedule can be stored
    at extraction time and re-priced later if an amendment changes the
    rent.
  * Every item keeps the verbatim sentence it came from plus its page,
    so every dollar figure the report shows has a source citation.
  * The PRICING (compute_effective_rent) is a separate pure function
    over (base rent, schedule, lease dates, as-of date). An item it
    can't price (e.g. a free month on a lease whose rent wasn't found)
    gets total_value None and makes the whole result "not quantified",
    rather than being silently priced at $0.
  * Both the regex engine (field_extractor.py) and the AI engine
    (ai_extraction.py) end up with the same {value, source, confidence,
    items} field entry, so the detectors don't care which engine ran.
    The AI engine's verbatim source_text is run back through this same
    deterministic parser -- the model finds the clause, this module does
    the arithmetic, so a dollar figure is never something the model
    "calculated".

This module deliberately imports nothing from portfolio.py or
deal_mismatch.py (both import it), only normalize.py.
"""
import calendar
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .normalize import parse_currency, parse_date

FIELD_NAME = "concessions"

# Same average month length portfolio.py uses (365.25 / 12) -- used only
# to turn a lease's start/end dates into a whole number of term months.
_DAYS_PER_MONTH = 30.4375

# When a lease's own term can't be read (a missing start or end date),
# annualizing a concession still needs SOME denominator. 12 months is the
# overwhelmingly common multifamily lease length; results computed this
# way carry term_assumed=True so callers can say so rather than present
# it as read off the lease.
_DEFAULT_TERM_MONTHS = 12

# How far ahead "expiring soon" looks for an active concession.
EXPIRING_WINDOW_DAYS = 90

# ----------------------------------------------------------------------
# Regex building blocks
# ----------------------------------------------------------------------

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "twenty-one": 21, "twenty-two": 22, "twenty-three": 23,
    "twenty-four": 24,
}

# A count of months as leases actually write it: "6", "six", "six (6)",
# "one-half (1/2)", "half a", "1.5". Longest words first so "twenty-four"
# isn't read as "twenty".
_NUM_WORD_ALT = "|".join(sorted((re.escape(w) for w in _NUMBER_WORDS), key=len, reverse=True))
_NUM_CORE = rf"(?:one[- ]half|half(?:\s+an?)?|\d+(?:\.\d+)?|{_NUM_WORD_ALT})"
_NUM_PAREN = r"(?:\s*\(\s*\d+(?:[./]\d+)?\s*\))?"


def _num(group: str) -> str:
    return rf"(?P<{group}>{_NUM_CORE}){_NUM_PAREN}"


_AMOUNT = r"(?P<amount>\$\s?[\d,]+(?:\.\d{1,2})?)"
_PER_MONTH = r"(?:per\s+month|a\s+month|each\s+month|every\s+month|monthly|/\s*mo(?:nth)?\b\.?)"
_POSITION_WORD = r"(?:first|initial|last|final)"
# Gap inside one clause: anything but a sentence break, while still
# allowing a decimal point inside a number like "$1,075.00".
_GAP = r"(?:[^.;]|(?<=\d)\.(?=\d))"
_MONTH_NAMES = (
    r"January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
)

# ---- free rent --------------------------------------------------------
_FREE_RENT_PATTERNS = [
    # "One (1) month of Base Rent (the first full calendar month, October 2025) is abated"
    re.compile(
        rf"\b{_num('n')}\s+(?:full\s+)?(?:calendar\s+)?months?(?:'s|’s)?\s+(?:of\s+)?(?:free\s+)?"
        rf"(?:base\s+|monthly\s+)?rent\b{_GAP}{{0,120}}?\b(?:abated|abate|free|waived|forgiven|at\s+no\s+charge)\b",
        re.IGNORECASE,
    ),
    # "two months free", "1 month free rent", "one month rent-free"
    re.compile(rf"\b{_num('n')}\s+(?:full\s+)?(?:calendar\s+)?months?\s+(?:of\s+)?(?:free|rent[- ]free)\b", re.IGNORECASE),
    # "free rent for the first two (2) months", "rent abatement of one month"
    re.compile(
        rf"\b(?:free\s+rent|rent[- ]free|rent\s+abatement|abated\s+rent)\s+(?:period\s+)?(?:for|of)\s+(?:the\s+)?"
        rf"(?:{_POSITION_WORD}\s+)?{_num('n')}\s+(?:full\s+)?(?:calendar\s+)?months?\b",
        re.IGNORECASE,
    ),
    # "Base Rent shall be abated for the first three (3) months"
    re.compile(
        rf"\b(?:base\s+|monthly\s+)?rent\s+(?:shall|will|is\s+to)?\s*be\s+(?:fully\s+)?(?:abated|waived|free)\s+"
        rf"(?:for|during)\s+(?:the\s+)?(?:{_POSITION_WORD}\s+)?{_num('n')}\s+(?:full\s+)?(?:calendar\s+)?months?\b",
        re.IGNORECASE,
    ),
    # "the first month's rent is free" (no explicit count -> 1)
    re.compile(
        rf"\b(?P<pos>first|last|final)\s+(?:full\s+)?(?:calendar\s+)?month(?:'s|’s)?\s+(?:base\s+)?rent\s+"
        rf"(?:is\s+|shall\s+be\s+|will\s+be\s+)?(?:fully\s+)?(?:abated|free|waived|forgiven)\b",
        re.IGNORECASE,
    ),
]

# ---- recurring discounts ---------------------------------------------
_RECURRING_PATTERNS = [
    # "Base Rent is reduced by $100.00 per month"
    re.compile(rf"\b(?:reduced|discounted|lowered|decreased)\s+by\s+{_AMOUNT}\s*{_PER_MONTH}", re.IGNORECASE),
    # "$75/mo off", "$50 per month discount", "$100 monthly concession"
    re.compile(rf"{_AMOUNT}\s*{_PER_MONTH}\s+(?:[a-z\-]+\s+){{0,2}}?(?:discount|concession|reduction|credit(?!\s+card)|off)\b", re.IGNORECASE),
    # "$50 off rent each month"
    re.compile(rf"{_AMOUNT}\s+off\s+(?:the\s+)?(?:monthly\s+)?(?:base\s+)?rent\s+(?:per|each|every)\s+month\b", re.IGNORECASE),
    # "a discount of $50 per month", "concession of $100 monthly"
    re.compile(rf"\b(?:discount|concession|credit(?!\s+card)|reduction)\s+of\s+{_AMOUNT}\s*{_PER_MONTH}", re.IGNORECASE),
    # "monthly concession of $100" -- the leading "monthly" makes it recurring
    re.compile(rf"\bmonthly\s+(?:rent\s+)?(?:discount|concession|credit|reduction)\s+of\s+{_AMOUNT}", re.IGNORECASE),
    # "5% off", "a 10% discount on monthly rent", "reduced by 5%"
    re.compile(r"\b(?P<pct>\d{1,2}(?:\.\d+)?)\s*%\s+(?:[a-z\-]+\s+){0,2}?(?:off|discount|reduction|concession)\b", re.IGNORECASE),
    re.compile(r"\b(?:reduced|discounted)\s+by\s+(?P<pct>\d{1,2}(?:\.\d+)?)\s*%", re.IGNORECASE),
]

# ---- one-time credits -------------------------------------------------
_ONE_TIME_PATTERNS = [
    # "first month's rent is reduced to $500" (credit = base - 500, priced later)
    re.compile(
        rf"\b(?:first|1st)\s+(?:full\s+)?month(?:'s|’s)?\s+(?:base\s+)?rent\s+(?:is\s+|shall\s+be\s+|will\s+be\s+)?"
        rf"(?:reduced|discounted)\s+to\s+{_AMOUNT}",
        re.IGNORECASE,
    ),
    # "$300 off the first month's rent"
    re.compile(rf"{_AMOUNT}\s+off\s+(?:the\s+)?(?:first|1st)\s+(?:full\s+)?month(?:'s|’s)?(?:\s+(?:base\s+)?rent)?", re.IGNORECASE),
    # "a one-time move-in credit of $500", "concession of $750"
    re.compile(
        rf"\b(?:(?:move[- ]in|leasing|look[- ]and[- ]lease)\s+special|"
        rf"(?:one[- ]time\s+)?(?:(?:rent|move[- ]in|leasing|renewal|retention|signing)\s+)?(?:credit(?!\s+card)|concession|discount|rebate))"
        rf"\s+(?:in\s+the\s+amount\s+)?of\s+{_AMOUNT}",
        re.IGNORECASE,
    ),
    # "$500 move-in credit", "$250 one-time concession"
    re.compile(
        rf"{_AMOUNT}\s+(?:one[- ]time\s+)?(?:(?:move[- ]in|rent|leasing|renewal|retention|signing)\s+)?"
        rf"(?:credit(?!\s+card)|concession|discount|rebate|special)\b",
        re.IGNORECASE,
    ),
]

# Duration of a recurring discount, searched near the match.
_DURATION_MONTHS = re.compile(
    rf"\b(?:for|during)\s+(?:the\s+)?(?:(?P<pos>{_POSITION_WORD})\s+)?{_num('n')}\s*(?:full\s+)?(?:calendar\s+)?months?\b"
    rf"|\b(?P<pos2>{_POSITION_WORD})\s+{_num('n2')}\s*(?:full\s+)?(?:calendar\s+)?months?\b",
    re.IGNORECASE,
)
_DURATION_TERM = re.compile(
    r"\b(?:full|entire|whole|remaining|initial)\b[^.;]{0,40}?\b(?:lease\s+)?term\b"
    r"|\blife\s+of\s+(?:the|this)\s+lease\b|\bfor\s+the\s+(?:lease\s+)?term\b|\beach\s+month\s+of\s+the\s+(?:lease\s+)?term\b",
    re.IGNORECASE,
)

_MONTH_RANGE = re.compile(
    rf"\b(?P<m1>{_MONTH_NAMES})\.?\s+(?P<y1>\d{{4}})\s*(?:through|thru|to|until|-|–|—)\s*(?P<m2>{_MONTH_NAMES})\.?\s+(?P<y2>\d{{4}})\b",
    re.IGNORECASE,
)
_MONTH_SINGLE = re.compile(rf"\b(?P<m1>{_MONTH_NAMES})\.?\s+(?P<y1>\d{{4}})\b", re.IGNORECASE)

# A sentence about casualty/condemnation rent abatement ("Rent shall abate
# while the Premises are untenantable") describes a contingency, not a
# concession the resident was given -- never treated as one.
_CONTINGENCY_WORDS = re.compile(
    r"\b(?:casualty|condemn\w*|eminent\s+domain|untenantable|destroyed|destruction|fire|damage[ds]?|interruption)\b",
    re.IGNORECASE,
)
# Rent INCREASES phrased with the same verbs ("increase by $50 per month")
# are escalations, not concessions.
_ESCALATION_WORDS = re.compile(r"\b(?:increase[sd]?|escalat\w*)\b", re.IGNORECASE)
# A deposit or prepaid month APPLIED to a later month ("one month's rent
# as a security deposit, credited toward the last month's rent") is the
# resident's own money, not a concession -- a free-rent reading of it
# would invent a full month of overstated income AND hide a real rent gap
# behind a fake net effective rent (review finding, fix/concession-
# detection). Requires a deposit/prepaid word: "rent is payable in
# advance" boilerplate and "a $1,000 concession credited against the last
# month" are NOT this. Skipped entirely when the sentence itself names a
# concession, credit, special or incentive.
_PREPAID_APPLIED = re.compile(
    r"\b(?:deposit|prepaid|pre-paid|prepay\w*|prepayment)\b[^.;]{0,160}?\b(?:credited|applied)\s+(?:toward|towards|against|to)\b",
    re.IGNORECASE,
)
# "interest-free" / "free of interest" describe how a deposit is held,
# not a concession -- removed before looking for concession words.
_INTEREST_FREE = re.compile(r"\binterest[- ]free\b|\bfree\s+of\s+interest\b|\bwithout\s+interest\b", re.IGNORECASE)
_CONCESSION_NAMED = re.compile(
    r"\b(?:concessions?|credit|special|incentive|discount|abate\w*|free)\b", re.IGNORECASE,
)
# Negated grants ("Resident shall not receive any free rent") -- checked in
# the words just before a match.
_NEGATION_BEFORE = re.compile(
    r"\b(?:shall|will|does|do|is|are|was|were)\s+not\b|\bnot\s+(?:entitled|eligible)\b"
    r"|\bno\s+(?:concessions?|free\s+rent|discounts?|credits?)\b|\bnever\b",
    re.IGNORECASE,
)
# ...unless that "not" is itself about the tenant's default ("Provided
# Tenant is not then in default / does not default / shall not have
# breached, rent shall be abated") -- a condition on a real grant. Judged
# by what directly FOLLOWS the "not", so a forfeiture clause ("If Tenant
# defaults, Tenant shall not be entitled to one month free") still reads
# as a negation of the grant.
_NOT_ABOUT_DEFAULT = re.compile(
    r"^\W*(?:[a-z\-]+\W+){0,6}?(?:default\w*|breach\w*|delinquen\w*|late\b|past\s+due)", re.IGNORECASE,
)
# Discounts and credits on something other than rent (parking, utilities,
# the deposit, pet rent, an early-payment discount). Judged from the words
# right around the match -- the clause it's in -- not the whole sentence,
# so a real special that also mentions a waived application fee still
# counts, while "parking is $50 per month, discounted by $10" doesn't.
_NON_RENT_WORDS = re.compile(
    r"\b(?:parking|garage|carport|storage|utilit\w*|water|electric\w*|cable|internet|pet|deposit|amenity|"
    r"early\s+payment|prompt\s+payment|paid\s+(?:early|on\s+time|by|on\s+or\s+before|before)|processing|convenience|fee)\b",
    re.IGNORECASE,
)
# "rent" the noun meaning the unit's rent -- not the verb ("may rent a
# parking space") and not "pet rent" / "parking rent" / "storage rent".
_RENT_WORD = re.compile(
    r"\b(?<!may )(?<!to )(?<!can )(?<!pet )(?<!parking )(?<!storage )(?<!garage )rent\b"
    r"(?!\s+(?:a|an|the|one|two|additional|another)\b)",
    re.IGNORECASE,
)
_APPLIED_TO_DEPOSIT = re.compile(
    r"\b(?:applied|credited)\s+(?:toward|towards|against|to)\s+(?:the\s+|resident's\s+|tenant's\s+)?(?:security\s+)?deposit\b",
    re.IGNORECASE,
)
# Words in the match itself that make it unmistakably a leasing concession.
_TRIGGER_IN_MATCH = re.compile(
    r"\b(?:move[- ]in|look[- ]and[- ]lease|special|leasing|renewal|retention|signing|concessions?)\b", re.IGNORECASE,
)

_RECAPTURE_WORDS = re.compile(
    r"\b(?:repay|reimburse|recaptur\w*|become[s]?\s+(?:immediately\s+)?due|forfeit\w*|charged\s+back|clawback|claw\s+back)\b",
    re.IGNORECASE,
)

_TRIGGERS = [
    ("renewal", re.compile(r"\brenew(?:al|ing)?\b", re.IGNORECASE)),
    ("retention", re.compile(r"\bretention\b", re.IGNORECASE)),
    ("military", re.compile(r"\bmilitary\b", re.IGNORECASE)),
    ("employee", re.compile(r"\b(?:employee|preferred\s+employer|courtesy\s+officer)\b", re.IGNORECASE)),
    ("move_in", re.compile(r"\b(?:move[- ]in|look[- ]and[- ]lease|new\s+resident|leasing\s+(?:incentive|special)|signing)\b", re.IGNORECASE)),
]

_TRIGGER_LABELS = {
    "move_in": "move-in",
    "renewal": "renewal",
    "retention": "retention",
    "military": "military",
    "employee": "employee",
}


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------

def _word_to_number(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    token = raw.strip().lower().replace("’", "'")
    if token.startswith("one-half") or token.startswith("one half") or token.startswith("half"):
        return 0.5
    if token in _NUMBER_WORDS:
        return float(_NUMBER_WORDS[token])
    try:
        return float(token)
    except ValueError:
        return None


def _month_number(name: str) -> int:
    key = name.strip().lower().rstrip(".")[:3]
    return ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(key) + 1


def _ym(month_name: str, year: str) -> str:
    return f"{int(year):04d}-{_month_number(month_name):02d}"


def _ym_to_date(ym: Optional[str]) -> Optional[date]:
    if not ym:
        return None
    y, m = ym.split("-")
    return date(int(y), int(m), 1)


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def _fmt_count(n: float) -> str:
    return f"{int(n)}" if float(n).is_integer() else f"{n:g}"


def _fmt_ym(ym: str) -> str:
    d = _ym_to_date(ym)
    return d.strftime("%b %Y")


def _sentences(text: str) -> List[Tuple[int, int]]:
    """
    (start, end) offsets of each sentence-ish clause in `text`. Splits on
    "." / ";" / newline-blank-line, but never on a decimal point inside a
    number ("$1,075.00") or a common abbreviation ("No.", "Sec.", "Inc.").
    Good enough for lease prose; it's a clause finder, not a grammar.
    """
    spans = []
    start = 0
    for m in re.finditer(r"[.;](?=\s|$)|\n\s*\n", text):
        end = m.end()
        prev = text[max(start, m.start() - 4):m.start()].lower()
        if m.group(0) == "." and re.search(r"\b(?:no|sec|inc|co|st|ste|apt|approx|mo|u\.s)$", prev):
            continue
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _position_for(sentence: str, match_start: int, explicit_pos: Optional[str]) -> str:
    word = (explicit_pos or "").lower()
    if not word:
        before = sentence[max(0, match_start - 25):match_start].lower()
        found = re.findall(r"\b(first|initial|last|final)\b", before)
        word = found[-1] if found else ""
    return "end" if word in ("last", "final") else "start"


def _trigger_for(sentence: str) -> Optional[str]:
    for name, pattern in _TRIGGERS:
        if pattern.search(sentence):
            return name
    return None


def _dates_in(segment: str) -> Tuple[Optional[str], Optional[str]]:
    rng = _MONTH_RANGE.search(segment)
    if rng:
        return _ym(rng.group("m1"), rng.group("y1")), _ym(rng.group("m2"), rng.group("y2"))
    single = _MONTH_SINGLE.search(segment)
    if single:
        return _ym(single.group("m1"), single.group("y1")), None
    return None, None


def _recurring_duration(sentence: str, after_offset: int) -> Dict[str, Any]:
    """How long a recurring discount runs -- searched after the match first (where leases put it), then the whole sentence."""
    for segment in (sentence[after_offset:], sentence):
        dm = _DURATION_MONTHS.search(segment)
        if dm:
            n = _word_to_number(dm.group("n") or dm.group("n2"))
            if n:
                pos = (dm.group("pos") or dm.group("pos2") or "").lower()
                return {"months": n, "full_term": False, "duration_assumed": False,
                        "position": "end" if pos in ("last", "final") else "start"}
        if _DURATION_TERM.search(segment):
            return {"months": None, "full_term": True, "duration_assumed": False, "position": "start"}
    # No end stated: a "$50 off per month" with no duration applies every
    # month of the lease. Recorded as an assumption, not hidden.
    return {"months": None, "full_term": True, "duration_assumed": True, "position": "start"}


def _overlaps(span: Tuple[int, int], taken: List[Tuple[int, int]]) -> bool:
    return any(span[0] < t[1] and t[0] < span[1] for t in taken)


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def _negated(sentence: str, start: int) -> bool:
    window = sentence[max(0, start - 60):start]
    for m in _NEGATION_BEFORE.finditer(window):
        if "not" in m.group(0).lower() and _NOT_ABOUT_DEFAULT.match(window[m.end():]):
            continue  # "is not then in default" -- a condition, not a negation
        return True
    return False


def _about_something_else(sentence: str, start: int, end: int) -> bool:
    """
    True when a $/% discount or credit match is about a non-rent charge.
    Looks at the match itself, up to 60 characters before it, and the rest
    of its own clause after it (to the next comma/semicolon): a non-rent
    word there wins unless "rent" (the noun) sits closer to the match.
    """
    matched = sentence[start:end]
    # "$200 move-in credit, applied toward the security deposit" reduces
    # the deposit, not rent -- never priced into effective rent.
    # Its own clause: up to a ";" or an "and" (a later, unrelated "..., and
    # any overpayment will be credited to the deposit" isn't about this
    # credit), but across a bare comma ("$200 credit, applied toward the
    # security deposit" is).
    own_clause = re.split(r";|\band\b", sentence[end:], maxsplit=1)[0]
    if _APPLIED_TO_DEPOSIT.search(own_clause):
        return True
    if _TRIGGER_IN_MATCH.search(matched) or _RENT_WORD.search(matched):
        return False
    after = re.split(r"[,;]", sentence[end:], maxsplit=1)[0]
    if _NON_RENT_WORDS.search(after):
        return True
    before = sentence[max(0, start - 60):start]
    # A non-rent word in an earlier "... and ..." clause belongs to that
    # clause ("the application fee is waived and residents receive $50 per
    # month off"); commas don't cut it ("parking is $50 per month,
    # discounted by $10" is still about parking).
    # An "and" followed by an auxiliary ("Parking is $50 and is discounted
    # by $10", "... and will be discounted") continues the same subject, so
    # it doesn't split; any other "and" ("... fee is waived and residents
    # receive", "... deposit of $200 and receives") starts a new clause.
    before = re.split(r"\band\s+(?!(?:is|are|was|were|will|shall|would|can|may|be|been|has|have)\b)", before, flags=re.IGNORECASE)[-1]
    non_rent = [m.end() for m in _NON_RENT_WORDS.finditer(before)]
    rent = [m.end() for m in _RENT_WORD.finditer(before)]
    return bool(non_rent) and (not rent or non_rent[-1] > rent[-1])


def _parse_sentence(sentence: str) -> List[Dict[str, Any]]:
    if _CONTINGENCY_WORDS.search(sentence):
        return []
    if _PREPAID_APPLIED.search(sentence) and not _CONCESSION_NAMED.search(_INTEREST_FREE.sub(" ", sentence)):
        return []

    found: List[Tuple[int, int, Dict[str, Any]]] = []  # (start, end, item)
    taken: List[Tuple[int, int]] = []

    for pattern in _FREE_RENT_PATTERNS:
        for m in pattern.finditer(sentence):
            if _overlaps(m.span(), taken) or _negated(sentence, m.start()):
                continue
            n = _word_to_number(m.groupdict().get("n")) if m.groupdict().get("n") else 1.0
            if not n or n > 24:
                continue
            item = {
                "kind": "free_rent",
                "free_months": n,
                "months": n,
                "position": _position_for(sentence, m.start(), m.groupdict().get("pos")),
                "full_term": False,
                "duration_assumed": False,
            }
            found.append((m.start(), m.end(), item))
            taken.append(m.span())

    if not _ESCALATION_WORDS.search(sentence):
        for pattern in _RECURRING_PATTERNS:
            for m in pattern.finditer(sentence):
                if _overlaps(m.span(), taken) or _negated(sentence, m.start()) or _about_something_else(sentence, m.start(), m.end()):
                    continue
                gd = m.groupdict()
                amount = parse_currency(gd.get("amount")) if gd.get("amount") else None
                pct = float(gd["pct"]) if gd.get("pct") else None
                if (amount is None or amount <= 0) and not pct:
                    continue
                item = {
                    "kind": "recurring_discount",
                    "monthly_amount": abs(amount) if amount is not None else None,
                    "percent": pct,
                    **_recurring_duration(sentence, m.end()),
                }
                found.append((m.start(), m.end(), item))
                taken.append(m.span())

    for idx, pattern in enumerate(_ONE_TIME_PATTERNS):
        for m in pattern.finditer(sentence):
            if _overlaps(m.span(), taken) or _negated(sentence, m.start()) or _about_something_else(sentence, m.start(), m.end()):
                continue
            # "$X credit ... per month" is a recurring discount the patterns
            # above didn't recognize the exact wording of -- don't misread
            # it as a single credit.
            if re.match(rf"\s*{_PER_MONTH}", sentence[m.end():m.end() + 20], re.IGNORECASE):
                continue
            amount = parse_currency(m.group("amount"))
            if amount is None or amount <= 0:
                continue
            item = {"kind": "one_time_credit", "months": 1, "position": "start",
                    "full_term": False, "duration_assumed": False}
            if idx == 0:
                item["reduced_to"] = abs(amount)
                item["one_time_amount"] = None
            else:
                item["one_time_amount"] = abs(amount)
            found.append((m.start(), m.end(), item))
            taken.append(m.span())

    if not found:
        return []

    found.sort(key=lambda f: f[0])
    trigger = _trigger_for(sentence)
    recapture = bool(_RECAPTURE_WORDS.search(sentence))
    items = []
    for i, (start, end, item) in enumerate(found):
        # Calendar months stated for THIS item: look between its own match
        # and the next item's, so "1 month free (Oct 2025) and $50/mo off
        # (Nov 2025 through Apr 2026)" assigns each range to its own item.
        next_start = found[i + 1][0] if i + 1 < len(found) else len(sentence)
        start_ym, end_ym = _dates_in(sentence[start:next_start])
        if start_ym is None and len(found) == 1:
            start_ym, end_ym = _dates_in(sentence)
        item.setdefault("free_months", None)
        item.setdefault("monthly_amount", None)
        item.setdefault("percent", None)
        item.setdefault("one_time_amount", None)
        item.setdefault("reduced_to", None)
        item["start_month"] = start_ym
        item["end_month"] = end_ym
        if end_ym and start_ym and item["kind"] == "recurring_discount" and item.get("months") is None:
            s, e = _ym_to_date(start_ym), _ym_to_date(end_ym)
            item["months"] = float((e.year - s.year) * 12 + e.month - s.month + 1)
            item["full_term"] = False
            item["duration_assumed"] = False
        if start_ym:
            item["position"] = "explicit"
        item["trigger"] = trigger
        item["recapture"] = recapture
        items.append(item)
    return items


def dedupe_key(item: Dict[str, Any]) -> Tuple:
    return (
        item["kind"], item.get("free_months"), item.get("monthly_amount"), item.get("percent"),
        item.get("one_time_amount"), item.get("reduced_to"), item.get("months"), item.get("full_term"),
        item.get("start_month"), item.get("trigger"),
    )


def parse_concessions(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find every concession stated in `pages` (the uniform [{page, text}]
    shape every extractor in this app produces) and return its structured
    schedule, one item per concession, in document order:

        {"kind": "free_rent" | "recurring_discount" | "one_time_credit",
         "free_months": float | None,       # free_rent only
         "monthly_amount": float | None,    # recurring $ off per month
         "percent": float | None,           # recurring % off per month
         "one_time_amount": float | None,   # one_time_credit $ amount
         "reduced_to": float | None,        # "first month reduced to $X"
         "months": float | None,            # how many months it applies; None + full_term = every month of the term
         "full_term": bool,
         "duration_assumed": bool,          # lease stated no duration; full term assumed
         "position": "start" | "end" | "explicit",
         "start_month": "YYYY-MM" | None,   # only when the lease states a calendar month
         "end_month": "YYYY-MM" | None,
         "trigger": "move_in" | "renewal" | "retention" | "military" | "employee" | None,
         "recapture": bool,                 # lease says it's repaid on default
         "page": int, "quote": str}         # the verbatim sentence, for citation

    Stacked concessions (a free month AND a monthly discount, in one
    sentence or several) each get their own item. The SAME concession
    restated word-for-word elsewhere (a summary box repeating section 3A)
    is kept once -- two genuinely identical concessions on one lease is
    far less likely than a lease repeating itself, and double counting
    would overstate the finding.
    """
    items: List[Dict[str, Any]] = []
    seen = set()
    for page in pages or []:
        raw = page.get("text") or ""
        # Line breaks inside a sentence are layout, not structure.
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", raw)
        for start, end in _sentences(text):
            sentence = re.sub(r"\s+", " ", text[start:end]).strip()
            for item in _parse_sentence(sentence):
                key = dedupe_key(item)
                if key in seen:
                    continue
                seen.add(key)
                item["page"] = page.get("page")
                item["quote"] = sentence
                items.append(item)
    return items


def parse_concession_text(text: Optional[str], page: Optional[int] = None) -> List[Dict[str, Any]]:
    """parse_concessions over one free-text string -- an AI source quote, a human-edited value, or this module's own summary string."""
    if not text or not text.strip():
        return []
    return parse_concessions([{"page": page, "text": text}])


def describe_item(item: Dict[str, Any]) -> str:
    """
    One-line, human-readable summary of a concession item. Written so it
    round-trips: parse_concession_text(describe_item(x)) yields the same
    schedule, which keeps a stored summary value re-parseable after an
    amendment merge or a manual edit drops the structured items.
    """
    kind = item["kind"]
    if kind == "free_rent":
        n = item.get("free_months") or 1
        core = f"{_fmt_count(n)} month{'s' if n != 1 else ''} free"
        if item.get("position") == "end":
            core = f"last {core}"
    elif kind == "recurring_discount":
        if item.get("monthly_amount") is not None:
            core = f"{_fmt_money(item['monthly_amount'])}/mo off"
        else:
            core = f"{_fmt_count(item.get('percent') or 0)}% off"
        if item.get("full_term"):
            core += " for the full lease term"
        elif item.get("months"):
            word = "last" if item.get("position") == "end" else "first"
            core += f" for the {word} {_fmt_count(item['months'])} months"
    else:
        if item.get("reduced_to") is not None:
            core = f"first month's rent reduced to {_fmt_money(item['reduced_to'])}"
        else:
            core = f"{_fmt_money(item.get('one_time_amount') or 0)} one-time credit"

    notes = []
    if item.get("trigger"):
        notes.append(_TRIGGER_LABELS.get(item["trigger"], item["trigger"]))
    if item.get("start_month") and item.get("end_month"):
        notes.append(f"{_fmt_ym(item['start_month'])} through {_fmt_ym(item['end_month'])}")
    elif item.get("start_month"):
        notes.append(_fmt_ym(item["start_month"]))
    if item.get("recapture"):
        notes.append("repayable on default")
    if item.get("duration_assumed"):
        notes.append("no end date stated")
    return f"{core} ({', '.join(notes)})" if notes else core


def summarize(items: List[Dict[str, Any]]) -> Optional[str]:
    return "; ".join(describe_item(i) for i in items) if items else None


def build_field_entry(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The stored extracted-field entry for `concessions`, same
    {value, source, confidence} shape every other field uses plus the
    structured `items`. `source` cites the first concession; every item
    carries its own page/quote for the report rows.

    Confidence: "high" when every item's amount, duration and position
    were stated outright; "medium" when any had to be assumed (no stated
    duration) -- a human should glance at it before relying on the
    dollar figure.
    """
    if not items:
        return {"value": None, "source": None, "confidence": None}
    first = items[0]
    confidence = "medium" if any(i.get("duration_assumed") for i in items) else "high"
    return {
        "value": summarize(items),
        "source": {"page": first.get("page") or 1, "quote": first.get("quote")},
        "confidence": confidence,
        "items": items,
    }


def concession_items_for_entry(entry: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    The structured schedule behind a stored `concessions` field entry.
    Prefers the stored items; falls back to re-parsing the display value
    (a manual edit or an amendment replaces the entry without items),
    then the cited quote (an AI entry whose value is free prose).
    """
    if not entry or not entry.get("value"):
        return []
    items = entry.get("items")
    if isinstance(items, list) and items:
        return items
    source = entry.get("source") or {}
    page = source.get("page") if isinstance(source, dict) else None
    parsed = parse_concession_text(entry.get("value"), page)
    if not parsed:
        quote = source.get("quote") if isinstance(source, dict) else None
        parsed = parse_concession_text(quote or entry.get("source_text"), page)
    return parsed


def has_unreadable_concession(entry: Optional[Dict[str, Any]]) -> bool:
    """
    The lease's `concessions` field says a concession exists, but no
    schedule can be read out of it (e.g. an AI entry the parser couldn't
    quantify). Detectors must report this as "concession found, amount
    unreadable" -- never treat it as "no concession in the lease".
    """
    return bool(entry and entry.get("value")) and not concession_items_for_entry(entry)


# ----------------------------------------------------------------------
# Pricing / effective rent
# ----------------------------------------------------------------------

def lease_term_months(start: Optional[date], end: Optional[date]) -> Optional[int]:
    """Whole months between a lease's start and end dates (Oct 1 2025 - Sep 30 2026 -> 12)."""
    if start is None or end is None or end < start:
        return None
    return max(1, int(round(((end - start).days + 1) / _DAYS_PER_MONTH)))


def _item_window(item: Dict[str, Any], lease_start: Optional[date], lease_end: Optional[date],
                 term_months: int) -> Tuple[Optional[date], Optional[date], Optional[float]]:
    """(first day, last day, months) this concession applies, or Nones where the lease doesn't say enough to place it."""
    explicit_start = _ym_to_date(item.get("start_month"))
    explicit_end = _ym_to_date(item.get("end_month"))

    if item.get("full_term"):
        months = float(term_months)
        # "$50/mo off starting Nov 2025" with no end: runs from its own
        # start month to the end of the lease, not the whole term.
        if explicit_start and lease_end:
            months = float(max(0, min(term_months, (lease_end.year - explicit_start.year) * 12 + lease_end.month - explicit_start.month + 1)))
    else:
        months = item.get("months")
        if months is not None:
            months = min(float(months), float(term_months))
    span = int(-(-(months or 1) // 1))  # ceil: a half free month still lands in one calendar month

    if explicit_start:
        start = explicit_start
    elif item.get("full_term"):
        start = date(lease_start.year, lease_start.month, 1) if lease_start else None
    elif item.get("position") == "end" and lease_end:
        start = add_months(date(lease_end.year, lease_end.month, 1), -(span - 1))
    elif lease_start:
        start = date(lease_start.year, lease_start.month, 1)
    else:
        start = None

    if explicit_end:
        end = _month_end(explicit_end)
    elif start is not None:
        end = _month_end(add_months(start, span - 1))
    else:
        end = None
    if item.get("full_term") and lease_end:
        end = lease_end
    return start, end, months


def price_item(item: Dict[str, Any], base_rent: Optional[float], lease_start: Optional[date],
               lease_end: Optional[date], term_months: int, as_of: Optional[date] = None) -> Dict[str, Any]:
    """One concession item plus its dollar value and timing as of `as_of`."""
    start, end, months = _item_window(item, lease_start, lease_end, term_months)
    kind = item["kind"]
    monthly_value: Optional[float] = None
    total: Optional[float] = None

    if kind == "free_rent":
        if base_rent is not None:
            monthly_value = base_rent
            total = base_rent * (item.get("free_months") or 0)
    elif kind == "recurring_discount":
        if item.get("monthly_amount") is not None:
            monthly_value = item["monthly_amount"]
        elif item.get("percent") is not None and base_rent is not None:
            monthly_value = base_rent * item["percent"] / 100.0
        if monthly_value is not None and months is not None:
            total = monthly_value * months
    else:
        if item.get("one_time_amount") is not None:
            total = item["one_time_amount"]
        elif item.get("reduced_to") is not None and base_rent is not None:
            total = max(0.0, base_rent - item["reduced_to"])
        monthly_value = total

    status = None
    if as_of is not None and start is not None and end is not None:
        status = "upcoming" if as_of < start else ("expired" if as_of > end else "active")

    return {
        **item,
        "monthly_value": round(monthly_value, 2) if monthly_value is not None else None,
        "applies_months": months,
        "total_value": round(total, 2) if total is not None else None,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "status": status,
    }


def compute_effective_rent(
    base_rent: Optional[float],
    items: List[Dict[str, Any]],
    lease_start: Optional[date] = None,
    lease_end: Optional[date] = None,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Price a lease's concession schedule and derive its effective rent:

      net_effective_rent           = base - total concessions / term months
      monthly_concession_equivalent = base - net_effective_rent
      annualized_concession_value   = monthly_concession_equivalent x 12
                                      (the number the report calls the
                                      concession's annual dollar impact)
      current_rent                  = what the resident actually owes in
                                      as_of's month: base, minus any
                                      recurring discount active then, or
                                      $0 in a free month
      remaining_concession_value    = concession dollars still to come after
                                      as_of's month (that month's rent is
                                      already billed)

    Every money figure is None when it can't be computed honestly (no
    base rent, or an item that can't be priced) -- `quantified` is False
    in that case so callers can say "concession found, amount unknown"
    instead of reporting $0.
    """
    term = lease_term_months(lease_start, lease_end)
    term_assumed = term is None
    term_months = term or _DEFAULT_TERM_MONTHS

    priced = [price_item(i, base_rent, lease_start, lease_end, term_months, as_of) for i in items]
    quantified = bool(priced) and all(p["total_value"] is not None for p in priced) and base_rent is not None
    total = round(sum(p["total_value"] for p in priced), 2) if quantified else None

    net_effective = monthly_equiv = annualized = None
    if quantified:
        monthly_equiv = round(total / term_months, 2)
        net_effective = round(base_rent - total / term_months, 2)
        annualized = round(total * 12 / term_months, 2)

    current_rent = None
    remaining = None
    if as_of is not None and base_rent is not None:
        current = base_rent
        for p in priced:
            if p["status"] != "active":
                continue
            if p["kind"] == "free_rent":
                # Half a month free means half the rent is still owed that month.
                free = p.get("free_months") or 1
                current = base_rent * (1 - free) if free < 1 else 0.0
            elif p["kind"] == "recurring_discount" and p["monthly_value"] is not None:
                current -= p["monthly_value"]
        current_rent = round(max(0.0, current), 2)
    if as_of is not None and quantified:
        rem = 0.0
        for p in priced:
            if p["status"] == "upcoming":
                rem += p["total_value"]
            elif p["status"] == "active" and p["end_date"]:
                if p["kind"] == "recurring_discount" and p["monthly_value"] is not None:
                    end = date.fromisoformat(p["end_date"])
                    # Months after as_of's own month -- rent for the
                    # current month is already billed, discount included.
                    months_left = (end.year - as_of.year) * 12 + end.month - as_of.month
                    rem += p["monthly_value"] * max(0, months_left)
                else:
                    rem += p["total_value"]
        remaining = round(rem, 2)

    return {
        "base_rent": base_rent,
        "term_months": term_months,
        "term_assumed": term_assumed,
        "items": priced,
        "quantified": quantified,
        "total_concession_value": total,
        "net_effective_rent": net_effective,
        "monthly_concession_equivalent": monthly_equiv,
        "annualized_concession_value": annualized,
        "current_rent": current_rent,
        "remaining_concession_value": remaining,
        "as_of": as_of.isoformat() if as_of else None,
    }


def effective_rent_for_lease(lease: Dict[str, Any], as_of: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """
    compute_effective_rent for one stored lease record (the
    get_all_effective_leases() shape), or None if the lease has no
    concessions. Reads rent_amount / lease_start_date / lease_end_date /
    concessions straight off extracted_fields.
    """
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(FIELD_NAME) or {}
    items = concession_items_for_entry(entry)
    if not items:
        return None

    def _value(name):
        return (fields.get(name) or {}).get("value")

    return compute_effective_rent(
        parse_currency(_value("rent_amount")),
        items,
        parse_date(_value("lease_start_date")),
        parse_date(_value("lease_end_date")),
        as_of,
    )


def rent_reflects_concession(rr_rent: Optional[float], effective: Optional[Dict[str, Any]],
                             tolerance_abs: float, tolerance_pct: float) -> bool:
    """
    True when a rent roll's rent figure is the lease's concession-adjusted
    rent -- the discounted rent actually owed this month, or the net
    effective rent -- rather than its gross base rent. A rent roll showing
    either one is reflecting the concession, not misstating rent. Same
    "both tolerances must be exceeded to disagree" rule as portfolio.py's
    rent reconciliation; the caller passes its constants in (this module
    can't import portfolio.py without a cycle).
    """
    if rr_rent is None or not effective or effective.get("base_rent") is None:
        return False

    def same(a: float, b: float) -> bool:
        diff = abs(a - b)
        larger = max(abs(a), abs(b))
        return not (diff > tolerance_abs and (diff / larger * 100 if larger else 0.0) > tolerance_pct)

    base = effective["base_rent"]
    for candidate in (effective.get("current_rent"), effective.get("net_effective_rent")):
        if candidate is not None and not same(candidate, base) and same(rr_rent, candidate):
            return True
    return False


def timing_note(effective: Dict[str, Any], as_of: Optional[date]) -> Optional[str]:
    """Plain-English "when does this apply" line for a report row."""
    if as_of is None:
        return None
    parts = []
    for p in effective["items"]:
        label = describe_item(p).split(" (")[0]
        if p["status"] == "expired":
            parts.append(f"{label}: already used (ended {p['end_date']})")
        elif p["status"] == "active":
            soon = p["end_date"] and date.fromisoformat(p["end_date"]) <= as_of + timedelta(days=EXPIRING_WINDOW_DAYS)
            parts.append(f"{label}: active, ends {p['end_date']}" + (" (expiring soon)" if soon else ""))
        elif p["status"] == "upcoming":
            parts.append(f"{label}: starts {p['start_date']}")
        else:
            parts.append(f"{label}: timing not stated in lease")
    return "; ".join(parts) if parts else None
