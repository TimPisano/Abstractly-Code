"""
Grounded natural-language Q&A over the lease portfolio.

This is a deterministic, rule-based intent matcher — deliberately NOT an
LLM call. The product requirement is "an accurate answer grounded in the
actual extracted/source data — not a hallucinated answer... Always cite
which lease and which page the answer came from." A generative model,
however good, can invent a number or attach a plausible-looking citation
to the wrong clause; a rule engine structurally cannot. It either finds a
real stored value and reports it with that field's real stored `source`,
or it says it doesn't know.

The design consequences of that choice, on purpose:
  - Every sentence in every answer is assembled from stored field values
    and counts computed over them. No inferred or paraphrased facts.
  - Every citation is read off a field's own `source` dict. If a field
    has no source, no citation is emitted for it — never a fabricated one.
  - A question that matches no known intent returns "unsupported" rather
    than a guess. Coverage is traded away for trustworthiness.
  - A field that is null on every candidate lease reports "no data on
    file" with confidence "partial" — never a fabricated $0 total, which
    would read as a real answer while meaning the opposite.

`leases` is a list of lease records (see database.get_all_effective_leases).
Passing a single-element list is how the caller scopes a question to one
lease, which is what the lease-detail "ask about this lease" UI does.
"""

import calendar
import re
from datetime import date
from typing import Optional, Dict, Any, List, Tuple

from app.normalize import (
    format_currency as _format_currency,
    format_sqft as _format_sqft,
    parse_currency,
    parse_square_footage,
    parse_date,
    rent_per_sqft,
)


# Question wording -> extracted_fields key. Ordered: the first pattern that
# matches wins, so more specific phrasings must precede the looser ones they
# contain ("security deposit" before "deposit", "rent escalation" before
# "rent"). Word boundaries keep "cam" from matching inside "came".
FIELD_SYNONYMS: List[Tuple[str, str]] = [
    (r"\bcommon area maintenance\b|\bcam charges?\b|\bcam\b", "cam_charges"),
    (r"\bsecurity deposits?\b|\bdeposits?\b", "security_deposit"),
    (r"\bexclusivity\b|\bexclusive use\b|\bexclusives?\b", "exclusivity_clause"),
    (r"\binsurance\b|\bliability coverage\b", "insurance_requirements"),
    (r"\bsquare (?:footage|feet|foot)\b|\bsq\.?\s?ft\b|\bsqft\b|\bsize\b", "square_footage"),
    (r"\bescalations?\b|\brent increases?\b|\bescalates?\b", "rent_escalation"),
    (r"\brenewals?\b|\boptions? to renew\b|\bextension options?\b", "renewal_options"),
    (r"\bpermitted use\b|\buse clause\b", "permitted_use"),
    (r"\bcure period\b|\bdefaults?\b", "default_cure_period"),
    (r"\bexpirations?\b|\bexpires?\b|\bexpiring\b|\bexpiry\b|\bend date\b|\bends\b", "lease_end_date"),
    (r"\bstart date\b|\bcommencement\b|\bcommences?\b|\bbegins?\b|\bstarts?\b", "lease_start_date"),
    (r"\bproperty address\b|\baddress\b|\blocation\b", "property_address"),
    (r"\blandlords?\b", "landlord"),
    (r"\btenants?\b", "tenant"),
    (r"\brent\b", "rent_amount"),
]

FIELD_LABELS: Dict[str, str] = {
    "tenant": "tenant",
    "landlord": "landlord",
    "rent_amount": "monthly rent",
    "lease_start_date": "lease start date",
    "lease_end_date": "lease expiration date",
    "property_address": "property address",
    "security_deposit": "security deposit",
    "cam_charges": "CAM charge",
    "rent_escalation": "rent escalation",
    "renewal_options": "renewal option",
    "permitted_use": "permitted use clause",
    "exclusivity_clause": "exclusivity clause",
    "insurance_requirements": "insurance requirement",
    "default_cure_period": "default cure period",
    "square_footage": "square footage",
}

# Only these fields can be summed or averaged, each with the parser that
# turns its display string into a number. A field absent from this map is
# not aggregatable, and an aggregate question about one is answered as
# unsupported rather than approximated.
NUMERIC_PARSERS = {
    "rent_amount": parse_currency,
    "cam_charges": parse_currency,
    "security_deposit": parse_currency,
    "insurance_requirements": parse_currency,
    "square_footage": parse_square_footage,
}

SUM_CUES = r"\btotal\b|\bsum\b|\bcombined\b|\baggregate\b|\bexposure\b|\ball in\b|\baltogether\b"
AVG_CUES = r"\baverage\b|\bavg\b|\bmean\b|\btypical\b"
COUNT_CUES = r"\bhow many\b|\bnumber of\b|\bhow much of the portfolio\b"
EXPIRY_CUES = r"\bexpir\w*\b|\broll(?:ing)? off\b|\bcoming up for renewal\b"
YESNO_START = r"^(?:does|do|is|are|has|have|did|was|were|can|will)\b"

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "eighteen": 18, "twenty-four": 24, "twentyfour": 24,
}

# Corporate suffixes stripped when matching a tenant name mentioned in a
# question ("the Blue Sky lease") against the stored name ("Blue Sky
# Coffee Roasters, Inc.").
ENTITY_SUFFIXES = r"\b(?:inc|incorporated|llc|l\.l\.c|llp|lp|ltd|corp|corporation|co|company)\b\.?"

DEFAULT_EXPIRY_MONTHS = 12


def answer_question(question: str, leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Answers a natural-language question against a list of lease records.

    Returns {"answer", "citations", "confidence", "matched_intent"} where
    confidence is "answered" (real data found and reported), "partial"
    (intent understood, but the underlying data is missing or the question
    was too ambiguous to scope), or "unsupported" (no intent matched).
    """
    if not isinstance(question, str) or not question.strip():
        return _unsupported()

    normalized = question.lower().strip()
    leases = [lease for lease in (leases or []) if isinstance(lease, dict)]

    # Order matters: "how many leases expire this year" is a count question
    # that reuses the expiry filter, so counting is tried before listing;
    # both are tried before the single-field lookup, which is the most
    # permissive matcher and would otherwise swallow portfolio questions.
    for handler in (_try_count, _try_list_expiring, _try_aggregate, _try_field_lookup):
        result = handler(normalized, leases)
        if result is not None:
            return result

    return _unsupported()


# --------------------------------------------------------------------------
# Intent handlers. Each returns None if the question isn't its intent, so
# answer_question can fall through to the next one.
# --------------------------------------------------------------------------


def _try_count(question: str, leases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """"how many leases do we have" / "how many leases expire this year"."""
    if not re.search(COUNT_CUES, question):
        return None

    if re.search(EXPIRY_CUES, question):
        cutoff, timeframe_label = _parse_timeframe(question)
        matches, no_date = _expiring_leases(leases, cutoff)
        citations = _citations_for(matches, "lease_end_date")
        answer = (
            f"{len(matches)} of {len(leases)} lease(s) expire {timeframe_label} "
            f"(on or before {_format_date(cutoff)})."
        )
        if no_date:
            answer += f" {len(no_date)} lease(s) have no expiration date on file and were not counted."
        confidence = "partial" if (not matches and no_date and len(no_date) == len(leases)) else "answered"
        return _result(answer, citations, confidence, "count")

    # "how many leases have CAM charges" — count leases where a field is present.
    field = _detect_field(question)
    if field and re.search(r"\bhave\b|\bwith\b|\bhas\b|\binclude\b", question):
        present = [lease for lease in leases if _field_value(lease, field) is not None]
        label = FIELD_LABELS[field]
        answer = (
            f"{len(present)} of {len(leases)} lease(s) have {_article(label)} {label} on file."
        )
        return _result(
            answer,
            _citations_for(present, field),
            "answered" if present else "partial",
            "count",
        )

    answer = f"There are {len(leases)} lease(s) in this set."
    # Cite each lease's tenant clause where one exists — that is the stored
    # evidence tying a record to a real document, and it is the only
    # citation a bare count can honestly carry.
    return _result(answer, _citations_for(leases, "tenant"), "answered", "count")


def _try_list_expiring(question: str, leases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """"which leases expire in the next year" / "list leases expiring in 6 months"."""
    if not re.search(EXPIRY_CUES, question):
        return None
    if "this lease" in question:
        # Detail-page phrasing ("when does this lease expire") is a
        # single-field lookup, not a portfolio scan.
        return None

    portfolio_phrasing = re.search(r"\bwhich\b|\blist\b|\bshow\b|\bleases\b|\bwhat leases\b", question)
    if not portfolio_phrasing:
        return None

    cutoff, timeframe_label = _parse_timeframe(question)
    matches, no_date = _expiring_leases(leases, cutoff)

    if not matches:
        answer = (
            f"No leases in this set expire {timeframe_label} "
            f"(on or before {_format_date(cutoff)})."
        )
        if no_date:
            answer += f" Note: {len(no_date)} of {len(leases)} lease(s) have no expiration date on file."
        confidence = "partial" if no_date and len(no_date) == len(leases) else "answered"
        return _result(answer, [], confidence, "list_expiring")

    lines = [
        f"{len(matches)} of {len(leases)} lease(s) expire {timeframe_label} "
        f"(on or before {_format_date(cutoff)}):"
    ]
    for lease in matches:
        tenant = _field_value(lease, "tenant") or "tenant not found"
        end_value = _field_value(lease, "lease_end_date")
        lines.append(f"- {lease.get('filename')} — {tenant} — expires {end_value}")
    if no_date:
        lines.append(
            f"({len(no_date)} lease(s) excluded: no expiration date on file.)"
        )

    return _result(
        "\n".join(lines),
        _citations_for(matches, "lease_end_date"),
        "answered",
        "list_expiring",
    )


def _try_aggregate(question: str, leases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """"total CAM exposure" / "average rent" / "average rent per square foot"."""
    wants_avg = bool(re.search(AVG_CUES, question))
    wants_sum = bool(re.search(SUM_CUES, question))
    if not (wants_avg or wants_sum):
        return None

    # Rent per square foot is a derived per-lease ratio, checked before the
    # generic field detector because "rent per square foot" contains both a
    # rent and a square-footage synonym. Only ever averaged: summing a set
    # of $/sqft rates across leases produces a meaningless number.
    if re.search(r"per (?:square (?:foot|feet)|sq\.?\s?ft)|\bpsf\b", question) and re.search(r"\brent\b", question):
        return _aggregate_rent_per_sqft(leases)

    field = _detect_field(question)
    if not field:
        return None
    if field not in NUMERIC_PARSERS:
        # Intent understood but the field isn't numeric (e.g. "average
        # permitted use") — say so rather than inventing a statistic.
        label = FIELD_LABELS[field]
        return _result(
            f"I can't compute a total or average for {label} — it isn't a numeric field.",
            [],
            "unsupported",
            None,
        )

    parser = NUMERIC_PARSERS[field]
    contributors: List[Tuple[Dict[str, Any], float]] = []
    missing: List[Dict[str, Any]] = []
    for lease in leases:
        parsed = parser(_field_value(lease, field))
        if parsed is None:
            missing.append(lease)
        else:
            contributors.append((lease, parsed))

    label = FIELD_LABELS[field]
    intent = "aggregate_avg" if wants_avg else "aggregate_sum"

    if not contributors:
        answer = (
            f"No lease in this set has a {label} on file, so I can't compute a "
            f"{'average' if wants_avg else 'total'} (0 of {len(leases)} lease(s) have that field). "
            "This is missing data, not a value of zero."
        )
        return _result(answer, [], "partial", intent)

    values = [value for _, value in contributors]
    formatter = _format_sqft if field == "square_footage" else _format_currency
    if wants_avg:
        stat = sum(values) / len(values)
        answer = f"Average {label} across the portfolio: {formatter(stat)}."
    else:
        stat = sum(values)
        answer = f"Total {label} across the portfolio: {formatter(stat)}."
    answer += (
        f" Based on {len(contributors)} of {len(leases)} lease(s); "
        f"{len(missing)} lease(s) have no {label} on file"
    )
    answer += f" ({_filename_list(missing)})." if missing else "."

    return _result(
        answer,
        _citations_for([lease for lease, _ in contributors], field),
        "answered",
        intent,
    )


def _aggregate_rent_per_sqft(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Average monthly rent per square foot: computed per lease, then averaged."""
    contributors: List[Dict[str, Any]] = []
    rates: List[float] = []
    for lease in leases:
        rate = rent_per_sqft(
            _field_value(lease, "rent_amount"), _field_value(lease, "square_footage")
        )
        if rate is not None:
            contributors.append(lease)
            rates.append(rate)

    if not rates:
        return _result(
            "No lease in this set has both a monthly rent and a square footage on "
            f"file, so rent per square foot can't be computed (0 of {len(leases)} lease(s)).",
            [],
            "partial",
            "aggregate_avg",
        )

    average = sum(rates) / len(rates)
    missing = len(leases) - len(contributors)
    answer = (
        f"Average monthly rent per square foot: ${average:,.2f}/sq ft. "
        f"Based on {len(contributors)} of {len(leases)} lease(s); {missing} lease(s) "
        "were excluded for missing rent or square footage."
    )
    # Both inputs are cited, since the ratio is only verifiable against both.
    citations = _citations_for(contributors, "rent_amount") + _citations_for(
        contributors, "square_footage"
    )
    return _result(answer, citations, "answered", "aggregate_avg")


def _try_field_lookup(question: str, leases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """"does this lease have an exclusivity clause" / "what is the rent for X"."""
    field = _detect_field(question)
    if not field:
        return None

    lease = _scope_to_lease(question, leases)
    if lease is None:
        if not leases:
            return _result(
                "There are no leases in this set to look that up in.",
                [],
                "partial",
                "field_lookup",
            )
        # Intent is clear but the target lease isn't. Asking is honest;
        # picking one arbitrarily would produce a confidently wrong answer.
        return _result(
            f"I understood this as a {FIELD_LABELS[field]} lookup, but I couldn't tell "
            f"which of the {len(leases)} leases you mean. Name the tenant or the file "
            "(e.g. \"what is the rent for Blue Sky Coffee\").",
            [],
            "partial",
            "field_lookup",
        )

    value = _field_value(lease, field)
    label = FIELD_LABELS[field]
    filename = lease.get("filename") or f"lease {lease.get('id')}"
    is_yes_no = bool(re.search(YESNO_START, question)) or "is there" in question or "are there" in question

    if value is None:
        if is_yes_no:
            answer = (
                f"No — {filename} does not have {_article(label)} {label} on file; "
                "the extractor did not find one."
            )
        else:
            answer = f"Not found: no {label} was extracted from {filename}."
        return _result(answer, [], "partial", "field_lookup")

    confidence_note = _confidence_note(lease, field)
    if is_yes_no:
        answer = f"Yes — {filename} has {_article(label)} {label}: {value}.{confidence_note}"
    else:
        tenant = _field_value(lease, "tenant")
        who = f" ({tenant})" if tenant and field != "tenant" else ""
        answer = f"The {label} for {filename}{who} is {value}.{confidence_note}"

    citation = _citation(lease, field)
    return _result(answer, [citation] if citation else [], "answered", "field_lookup")


# --------------------------------------------------------------------------
# Grounding helpers — the only places a value or citation is ever produced.
# --------------------------------------------------------------------------


def _field_value(lease: Dict[str, Any], field: str) -> Optional[str]:
    """The stored display value for a field, or None. Never a default."""
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field) or {}
    if not isinstance(entry, dict):
        return None
    return entry.get("value")


def _citation(lease: Dict[str, Any], field: str) -> Optional[Dict[str, Any]]:
    """
    Builds a citation strictly from a field's own stored `source`. Returns
    None when there is no source to cite — a missing citation is correct,
    a synthesized one would defeat the entire point of this module.
    """
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field) or {}
    if not isinstance(entry, dict):
        return None
    source = entry.get("source")
    if not isinstance(source, dict):
        return None
    return {
        "lease_id": lease.get("id"),
        "filename": lease.get("filename"),
        "field": field,
        "page": source.get("page"),
        "quote": source.get("quote"),
    }


def _citations_for(leases: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    """One citation per lease that actually has a source for the field."""
    citations = []
    for lease in leases:
        citation = _citation(lease, field)
        if citation:
            citations.append(citation)
    return citations


def _confidence_note(lease: Dict[str, Any], field: str) -> str:
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field) or {}
    confidence = entry.get("confidence") if isinstance(entry, dict) else None
    return f" (extraction confidence: {confidence})" if confidence else ""


# --------------------------------------------------------------------------
# Question parsing helpers.
# --------------------------------------------------------------------------


def _detect_field(question: str) -> Optional[str]:
    for pattern, field in FIELD_SYNONYMS:
        if re.search(pattern, question):
            return field
    return None


def _scope_to_lease(question: str, leases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Resolves which lease a single-lease question is about: the only one, if
    the caller scoped the list to one; otherwise the lease whose filename or
    tenant name is named in the question. Returns None when ambiguous.
    """
    if len(leases) == 1:
        return leases[0]

    for lease in leases:
        filename = (lease.get("filename") or "").lower()
        if filename and filename in question:
            return lease
        stem = re.sub(r"\.pdf$", "", filename)
        stem_words = re.sub(r"[_\-]+", " ", stem).strip()
        if stem_words and stem_words in question:
            return lease

    for lease in leases:
        for alias in _tenant_aliases(_field_value(lease, "tenant")):
            if alias in question:
                return lease

    return None


def _tenant_aliases(tenant: Optional[str]) -> List[str]:
    """
    Progressively shorter forms of a tenant name, so "the Blue Sky lease"
    resolves to "Blue Sky Coffee Roasters, Inc.". Kept to >= 6 characters
    so a short fragment can't collide with unrelated question wording.
    """
    if not tenant:
        return []
    lowered = tenant.lower().strip()
    aliases = [lowered]

    without_suffix = re.sub(ENTITY_SUFFIXES, "", lowered)
    without_suffix = re.sub(r"[,\s]+$", "", without_suffix).strip()
    if without_suffix:
        aliases.append(without_suffix)

    words = without_suffix.split()
    if len(words) >= 2:
        aliases.append(" ".join(words[:2]))

    seen = set()
    unique = []
    for alias in aliases:
        if len(alias) >= 6 and alias not in seen:
            seen.add(alias)
            unique.append(alias)
    return unique


def _parse_timeframe(question: str) -> Tuple[date, str]:
    """
    Extracts the expiry window from the question, returning (cutoff_date,
    human label). Defaults to 12 months when no timeframe is stated, which
    covers "which leases are expiring soon".
    """
    today = date.today()

    if re.search(r"\bthis (?:calendar )?year\b", question):
        return date(today.year, 12, 31), f"before the end of {today.year}"

    match = re.search(r"\b(\d+)\s*(month|year)s?\b", question)
    if not match:
        match = re.search(
            r"\b(" + "|".join(NUMBER_WORDS) + r")\s*(month|year)s?\b", question
        )
    if match:
        raw = match.group(1)
        count = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]
        unit = match.group(2)
        months = count * 12 if unit == "year" else count
        return _add_months(today, months), f"within the next {months} month(s)"

    # "in the next year" / "next month" with no number word in between.
    if re.search(r"\bnext year\b", question):
        return _add_months(today, 12), "within the next 12 month(s)"
    if re.search(r"\bnext month\b", question):
        return _add_months(today, 1), "within the next 1 month(s)"

    return (
        _add_months(today, DEFAULT_EXPIRY_MONTHS),
        f"within the next {DEFAULT_EXPIRY_MONTHS} month(s)",
    )


def _expiring_leases(
    leases: List[Dict[str, Any]], cutoff: date
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Splits leases into (expiring on or before cutoff, no parseable end date).
    Already-expired leases are excluded: the question is forward-looking, and
    a lease that ended last year is a different problem than one rolling off.
    """
    today = date.today()
    expiring = []
    no_date = []
    for lease in leases:
        end = parse_date(_field_value(lease, "lease_end_date"))
        if end is None:
            no_date.append(lease)
        elif today <= end <= cutoff:
            expiring.append(lease)
    expiring.sort(key=lambda lease: parse_date(_field_value(lease, "lease_end_date")))
    return expiring, no_date


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# --------------------------------------------------------------------------
# Formatting.
# --------------------------------------------------------------------------


def _article(label: str) -> str:
    """"an exclusivity clause" vs "a monthly rent" — keeps answers readable."""
    return "an" if label[:1].lower() in "aeiou" else "a"


def _format_date(value: date) -> str:
    """Avoids platform-specific strftime padding flags (%-d / %#d)."""
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _filename_list(leases: List[Dict[str, Any]]) -> str:
    return ", ".join(lease.get("filename") or f"lease {lease.get('id')}" for lease in leases)


def _result(
    answer: str,
    citations: List[Dict[str, Any]],
    confidence: str,
    matched_intent: Optional[str],
) -> Dict[str, Any]:
    return {
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "matched_intent": matched_intent,
    }


def _unsupported() -> Dict[str, Any]:
    return _result(
        "I don't have a way to answer that question yet.", [], "unsupported", None
    )
