"""
Field extraction module for lease documents.

This module contains logic to extract specific fields (parties, financial
terms, dates, and special clauses) from lease PDFs using regex patterns and
keyword matching.

Real leases express the same fact in very different sentence shapes:
  - "Tenant: John Smith"                                  (label style)
  - "...Blue Sky Coffee Roasters, Inc. ("Tenant")"         (defined-term style)
  - "Monthly Rent: $2,500.00"                              (label style)
  - "...the sum of $6,250.00 per month..."                 (prose/narrative style)

Each extractor tries several strategies, most-reliable first, and stops at
the first one that matches. A bounded, period-free "gap" is used between a
keyword and its value (instead of requiring immediate adjacency) so that
narrative sentences like "shall commence on April 1, 2025" are matched
without also running past the end of the sentence into unrelated text.

Every strategy is tagged with a confidence level ("high"/"medium"/"low"):
  - high:   an unambiguous, tightly-anchored match (explicit label, or a
            prose pattern with a strong disambiguating cue like "per month"
            or a defined-term marker)
  - medium: a looser prose match, a reversed-order match (value appears
            before its keyword), or a composite clause missing some of its
            expected sub-parts
  - low:    a generic fallback pattern with little context to confirm the
            match is actually the field in question
Fields that were not found have confidence None.
"""

import re
from typing import Optional, Dict, Any, List


MONTHS_FULL = (r"January|February|March|April|May|June|July|August|September"
               r"|October|November|December")
MONTHS_ABBR = r"Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sept\.?|Sep\.?|Oct\.?|Nov\.?|Dec\.?"
MONTHS = rf"{MONTHS_FULL}|{MONTHS_ABBR}"
ORDINAL_SUFFIX = r"(?:st|nd|rd|th)?"

# Matches "01/15/2024", "1-15-24", "January 15, 2024", "Sept 1 2025"
# (abbreviated months, optional ordinal suffixes, optional comma), and the
# legal-drafting style "1st day of April, 2025"
DATE_REGEX = (
    rf"(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}"
    rf"|(?:{MONTHS})\s+\d{{1,2}}{ORDINAL_SUFFIX},?\s+\d{{4}}"
    rf"|\d{{1,2}}{ORDINAL_SUFFIX}\s+day\s+of\s+(?:{MONTHS}),?\s+\d{{4}})"
)

# Matches "$2,500.00", "$2,500", "$ 2,500.00"
CURRENCY_REGEX = r"\$\s?([\d,]+(?:\.\d{2})?)"

# Bounded gap between a keyword and its value. Excludes "." and "$" so the
# match can't run past the end of a sentence or swallow an unrelated dollar
# amount, but newlines (from PDF line-wrapping) are allowed through.
GAP = r"[^.$]{0,100}?"

# Wider gap for clause-level extraction (renewal terms, cure periods, etc.)
# where the relevant detail may be a full sentence or two away.
WIDE_GAP = r"[^.]{0,150}?"

# Smart quotes vs straight quotes around defined terms like ("Tenant")
QUOTE_OPEN = r"[\"“]"
QUOTE_CLOSE = r"[\"”]"

CONFIDENCE_LEVELS = ("high", "medium", "low")


def _clean_value(value: str) -> str:
    """Collapse line-wrap whitespace/newlines in a captured value."""
    return re.sub(r"\s+", " ", value).strip()


def _make_quote(text: str, start: int, end: int, pad: int = 50) -> str:
    """Build a readable context snippet around a regex match span."""
    quote_start = max(0, start - pad)
    quote_end = min(len(text), end + pad)
    quote = text[quote_start:quote_end].strip()
    # Collapse line-wrap newlines into spaces for readability
    return re.sub(r"\s+", " ", quote)


def _not_found() -> Dict[str, Any]:
    return {"value": None, "source": None, "confidence": None}


def _concat_pages(pages: List[Dict[str, Any]]):
    """
    Join all pages into one continuous string (so a keyword/value pair
    split across a page break — e.g. "Base Rent: " at the bottom of page 1
    and "$6,250.00" at the top of page 2 — can still be matched by a single
    regex search) along with a function mapping a character offset in that
    joined string back to the page number it came from.
    """
    parts = []
    boundaries = []  # (start_offset, end_offset, page_num)
    offset = 0
    for page in pages:
        text = page["text"] or ""
        start = offset
        parts.append(text)
        offset += len(text)
        boundaries.append((start, offset, page["page"]))
        parts.append("\n")
        offset += 1

    full_text = "".join(parts)

    def page_for_offset(pos: int) -> int:
        for start, end, page_num in boundaries:
            if start <= pos < end:
                return page_num
        return boundaries[-1][2] if boundaries else 1

    return full_text, page_for_offset


class FieldExtractor:
    """Extracts specific fields from lease text using pattern matching."""

    def __init__(self):
        pass

    def extract_fields(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract all lease fields from page data.

        Args:
            pages: List of page dictionaries with "page" and "text" keys

        Returns:
            Dictionary with extracted fields in the required format:
            {"value": ..., "source": {"page": N, "quote": "..."} or None,
             "confidence": "high"/"medium"/"low" or None}
        """
        result = {
            "tenant": self._extract_defined_party(pages, "Tenant", self._party_label_patterns("tenant", "lessee", "renter")),
            "landlord": self._extract_defined_party(pages, "Landlord", self._party_label_patterns("landlord", "lessor")),
            "rent_amount": self._extract_rent(pages),
            "lease_start_date": self._extract_start_date(pages),
            "lease_end_date": self._extract_end_date(pages),
            "property_address": self._extract_property_address(pages),
            "security_deposit": self._extract_security_deposit(pages),
            "cam_charges": self._extract_cam_charges(pages),
            "rent_escalation": self._extract_rent_escalation(pages),
            "renewal_options": self._extract_renewal_options(pages),
            "permitted_use": self._extract_permitted_use(pages),
            "exclusivity_clause": self._extract_exclusivity_clause(pages),
            "insurance_requirements": self._extract_insurance_requirements(pages),
            "default_cure_period": self._extract_default_cure_period(pages),
            "square_footage": self._extract_square_footage(pages),
        }

        return result

    def _search_ordered(
        self,
        pages: List[Dict[str, Any]],
        patterns: List[str],
        confidences: List[str],
        group: int = 1,
        flags: int = re.IGNORECASE
    ) -> Optional[Dict[str, Any]]:
        """
        Try each pattern (in priority order) against each page (in document
        order), returning the first match found. `confidences` must be the
        same length as `patterns` and gives the confidence tier to report
        for a match on that pattern.

        `flags` defaults to case-insensitive, which is fine for keyword
        anchors and dates/currency. Patterns whose capture group relies on
        [A-Z]/[a-z] to detect real capitalization (e.g. bounding a proper
        name) must pass flags=0 and scope any case-insensitive keyword
        parts locally with (?i:...) — otherwise IGNORECASE makes [A-Z] and
        [a-z] equivalent and the capitalization heuristic silently stops
        bounding anything.

        Patterns are tried against the whole document (all pages joined),
        not page-by-page, for two reasons: it lets a keyword/value pair
        split across a page break still match, and it means pattern
        priority (most-reliable-first) always wins over "whichever page
        happens to come first" — a low-confidence match on page 1 should
        not beat a high-confidence match on page 2.
        """
        assert len(patterns) == len(confidences)

        full_text, page_for_offset = _concat_pages(pages)

        for pattern, confidence in zip(patterns, confidences):
            match = re.search(pattern, full_text, flags)
            if match:
                value = _clean_value(match.group(group))
                quote = _make_quote(full_text, match.start(), match.end())
                return {
                    "value": value,
                    "source": {"page": page_for_offset(match.start()), "quote": quote},
                    "confidence": confidence
                }

        return None

    # ------------------------------------------------------------------
    # Party name extraction (tenant / landlord)
    # ------------------------------------------------------------------

    def _party_label_patterns(self, *keywords: str) -> List[str]:
        # Keyword and connector are scoped case-insensitive with (?i:...)
        # rather than relying on a global IGNORECASE flag, because these
        # patterns are run case-sensitive overall (see _extract_defined_party)
        # so that [A-Z]/[a-z] in the capture group genuinely require real
        # capitalization to bound the name — under a blanket IGNORECASE
        # flag, [A-Z][a-z]+ stops meaning "a capitalized word" and starts
        # matching any word at all, letting the match run on indefinitely
        # (e.g. "Landlord is Jordan Blake and the tenant is Alex Chen").
        keyword_group = "|".join(keywords)
        # Optional "is"/"was" filler covers casual phrasing like
        # "the tenant is Alex Chen" alongside formal "Tenant: Alex Chen"
        connector = rf"[:\s]+(?:(?i:is|was)\s+)?"
        # A repeated word may be a normal capitalized word ("Apparel") or an
        # ALL-CAPS acronym suffix ("LLC", "LP"), each with an optional
        # trailing period, so entity suffixes aren't truncated.
        word = r"(?:[A-Z][a-z]+\.?|[A-Z]{2,}\.?)"
        return [
            # Capitalized personal/company name, e.g. "Tenant: John Smith"
            # or "Landlord: Property Management LLC"
            rf"(?i:{keyword_group}){connector}([A-Z][a-z]+(?:[ \t]+{word})*)",
            # Company/entity name (allows acronyms like LLC), to end of line,
            # e.g. "Landlord: Property Management LLC"
            rf"(?i:{keyword_group}){connector}([A-Z][\w&,\.\'\-\s]+?)(?:\n|$)",
        ]

    def _extract_defined_party(
        self,
        pages: List[Dict[str, Any]],
        role: str,
        label_patterns: List[str]
    ) -> Dict[str, Any]:
        """
        Extract a party name (Tenant/Landlord). Tries, in order:
          1. Defined-term prose style: '...Some Company, LLC ("Tenant")' (high)
          2. Label style: 'Tenant: John Smith' (high)

        Both run case-sensitive (flags=0) with keywords scoped
        case-insensitive via (?i:...) — see _party_label_patterns.
        """
        defined_term_pattern = (
            rf"([A-Z][A-Za-z0-9&,\.\'\-\s]{{2,80}}?)\s*\(\s*{QUOTE_OPEN}(?i:{role}){QUOTE_CLOSE}\s*\)"
        )

        result = self._search_ordered(pages, [defined_term_pattern], ["high"], flags=0)
        if result:
            value = result["value"]
            # Strip leading connector words swept in by the broad name charclass
            value = re.sub(
                r"^(?:.*\bby\s+and\s+between\s+|.*\band\s+)", "", value, flags=re.IGNORECASE
            )
            # Strip trailing entity-type boilerplate, e.g. ", a Delaware corporation"
            value = re.sub(
                r",?\s+an?\s+[A-Za-z\s]+?"
                r"(?:corporation|company|partnership|LLC|L\.L\.C\.|LLP|L\.L\.P\.|entity)\.?$",
                "", value, flags=re.IGNORECASE
            )
            result["value"] = value.strip().rstrip(",")
            return result

        result = self._search_ordered(pages, label_patterns, ["high", "high"], flags=0)
        if result:
            # A trailing period is only meaningful if it's a real
            # abbreviation ("Co.", "Inc."); otherwise it's just the
            # sentence's own end punctuation swept in by the optional
            # per-word period in the pattern, so strip it.
            value = result["value"]
            if value.endswith("."):
                last_word = value[:-1].rsplit(" ", 1)[-1].lower()
                if last_word not in ("co", "inc", "corp", "ltd", "llp", "lp", "llc"):
                    value = value[:-1]
            result["value"] = value
            return result

        return _not_found()

    # ------------------------------------------------------------------
    # Financial terms
    # ------------------------------------------------------------------

    def _extract_amount(
        self,
        pages: List[Dict[str, Any]],
        keyword: str,
        amount_before_keyword: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Generic dollar-amount extractor for a labeled or prose-described
        charge (deposit, CAM, insurance coverage, etc). Tries label style
        (high), then keyword-before-amount prose (high), then (optionally)
        amount-before-keyword prose (medium) since some clauses state the
        figure before naming it (e.g. "...the sum of $12,500.00 as a
        security deposit") and the association is a little less direct.
        """
        # The optional ".?\s*" right after the keyword absorbs a heading's
        # own period (e.g. "7. INSURANCE. Tenant shall maintain...") before
        # the exclusion-based GAP starts — otherwise a heading period sits
        # directly after the keyword and GAP (which excludes ".") can never
        # cross it to reach the amount later in the same clause.
        patterns = [
            rf"{keyword}[:\s]+{CURRENCY_REGEX}",
            rf"{keyword}\.?\s*{GAP}{CURRENCY_REGEX}",
        ]
        confidences = ["high", "high"]
        if amount_before_keyword:
            patterns.append(rf"{CURRENCY_REGEX}{GAP}{keyword}")
            confidences.append("medium")

        result = self._search_ordered(pages, patterns, confidences)
        if result:
            value = result["value"]
            if not value.startswith("$"):
                value = "$" + value
            result["value"] = value
        return result

    def _extract_security_deposit(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = self._extract_amount(pages, r"security\s+deposit", amount_before_keyword=True)
        return result if result else _not_found()

    def _extract_cam_charges(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        cam_keyword = r"(?:common\s+area\s+maintenance(?:\s*\(\s*cam\s*\))?|cam\s+(?:charges|contribution|fees?))"
        result = self._extract_amount(pages, cam_keyword)
        return result if result else _not_found()

    def _extract_insurance_requirements(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = self._extract_amount(pages, r"insurance")
        if not result:
            return _not_found()

        # Look just past the match for a "per occurrence" / "aggregate" qualifier
        value = result["value"]
        quote = result["source"]["quote"].lower()
        if "per occurrence" in quote:
            value += " per occurrence"
        elif "aggregate" in quote:
            value += " aggregate"
        result["value"] = value
        return result

    def _extract_rent(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract monthly rent amount. Tries, in order:
          1. Label style: "Monthly Rent: $2,500.00" (high)
          2. Annual-rent-with-monthly-parenthetical: "$72,000.00 per annum
             ($6,000.00 per month)" — common in formal leases that state
             rent as an annual figure first (high)
          3. Prose style with "per month" cue: "...the sum of $6,250.00
             per month" (high)
          4. Prose style without the trailing "per month" cue (medium)
          5. Generic "rent is $X" fallback (low)
        """
        rent_keyword = r"(?:base\s+rent|monthly\s+rent|rental\s+amount|monthly\s+payment)"

        patterns = [
            rf"{rent_keyword}[:\s]+{CURRENCY_REGEX}",
            rf"{rent_keyword}{GAP}\$[\d,.]+\s*per\s+annum\s*\(\s*{CURRENCY_REGEX}\s*per\s+month\s*\)",
            rf"{rent_keyword}{GAP}{CURRENCY_REGEX}\s*(?:per\s+month|/\s*mo\.?|monthly)",
            rf"{rent_keyword}{GAP}{CURRENCY_REGEX}",
            rf"rent\s+(?:is|will\s+be|shall\s+be)[:\s]*{CURRENCY_REGEX}",
        ]
        confidences = ["high", "high", "high", "medium", "low"]

        result = self._search_ordered(pages, patterns, confidences)
        if result:
            value = result["value"]
            if not value.startswith("$"):
                value = "$" + value
            result["value"] = value
            return result

        return _not_found()

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------

    def _start_date_patterns(self):
        """
        Shared pattern list for start-date matching. Tries, in order:
          1. Label style: "Lease Start Date: January 15, 2024" (high)
          2. Prose style: "term shall commence on April 1, 2025" (high)
          3. Loose "begin..." fallback, e.g. could latch onto unrelated
             text like "beginning of the fiscal year" (medium)
        Module-level so both single-match extraction (_extract_start_date)
        and multi-match scanning (find_all_date_candidates, used for
        cross-section consistency checking) stay in sync.
        """
        patterns = [
            rf"(?:lease\s+)?start\s+date[:\s]+{DATE_REGEX}",
            rf"commencement\s+date[:\s]+{DATE_REGEX}",
            rf"begin(?:ning)?\s+date[:\s]+{DATE_REGEX}",
            rf"term\s+begins?[:\s]+{DATE_REGEX}",
            rf"effective\s+date[:\s]+{DATE_REGEX}",
            # \b(?!\s+Date) excludes the noun form in a defined-term aside
            # like '(the "Commencement Date")'. The \b matters: without it,
            # \w* backtracks one character short of the full word (e.g.
            # matching "Commencemen" instead of "Commencement"), which
            # sidesteps the lookahead entirely since it's no longer
            # checking right before " Date" — and the gap then reaches
            # past that whole clause to grab an unrelated later date
            # (e.g. the lease's END date). \b forces \w* to only stop at
            # an actual word boundary, so the lookahead can't be dodged
            # by a partial-word backtrack.
            rf"(?:shall\s+)?commenc\w*\b(?!\s+Date){GAP}{DATE_REGEX}",
            rf"begin\w*\b(?!\s+Date){GAP}{DATE_REGEX}",
            rf"starting{GAP}{DATE_REGEX}",
        ]
        confidences = ["high", "high", "high", "high", "high", "high", "medium", "medium"]
        return patterns, confidences

    def _extract_start_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns, confidences = self._start_date_patterns()
        result = self._search_ordered(pages, patterns, confidences)
        return result if result else _not_found()

    def _end_date_patterns(self):
        """
        Shared pattern list for end-date matching. Tries, in order:
          1. Label style: "Lease End Date: January 14, 2025" (high)
          2. Prose style: "shall expire on March 31, 2030" (high)
          3. "...and ending March 31, 2030" cue (medium — broader verb,
             slightly more room for a false positive)
        """
        patterns = [
            rf"(?:lease\s+)?end\s+date[:\s]+{DATE_REGEX}",
            rf"expiration\s+date[:\s]+{DATE_REGEX}",
            rf"termination\s+date[:\s]+{DATE_REGEX}",
            rf"term\s+ends?[:\s]+{DATE_REGEX}",
            rf"expires?[:\s]+{DATE_REGEX}",
            rf"(?:shall\s+)?expir\w*\b(?!\s+Date){GAP}{DATE_REGEX}",
            rf"(?:shall\s+)?terminat\w*\b(?!\s+Date){GAP}{DATE_REGEX}",
            rf"ending{GAP}{DATE_REGEX}",
            rf"running\s+through{GAP}{DATE_REGEX}",
        ]
        confidences = ["high", "high", "high", "high", "high", "high", "high", "medium", "medium"]
        return patterns, confidences

    def find_all_date_candidates(self, pages: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
        """
        Scans the whole document for EVERY match of the start-date or
        end-date pattern list (role="start"|"end"), not just the first —
        used for internal-consistency checking (e.g. does a date stated
        in one section conflict with a date stated elsewhere?), which
        the single-best-match extractors above can't support since they
        stop at the first hit. Deduplicates by the raw matched text, not
        by parsed date, so a genuine conflict (two different-but-both-
        well-formed dates) is preserved for the caller to compare.

        Returns a list of {"value": ..., "source": {"page": N, "quote": ...}}.
        """
        patterns, _confidences = self._start_date_patterns() if role == "start" else self._end_date_patterns()
        full_text, page_for_offset = _concat_pages(pages)

        seen_values = set()
        candidates = []
        for pattern in patterns:
            for match in re.finditer(pattern, full_text, re.IGNORECASE):
                value = _clean_value(match.group(1))
                if value in seen_values:
                    continue
                seen_values.add(value)
                candidates.append({
                    "value": value,
                    "source": {"page": page_for_offset(match.start()), "quote": _make_quote(full_text, match.start(), match.end())}
                })
        return candidates

    def _extract_end_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns, confidences = self._end_date_patterns()

        result = self._search_ordered(pages, patterns, confidences)
        return result if result else _not_found()

    def _extract_rent_escalation(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract rent escalation schedule. Tries, in order:
          1. Full year-by-year breakdown, e.g. "Year 1: $6,250; Year 2:
             $6,438" (high — explicit structured data)
          2. Percentage increase stated in parens right after "increase
             by" (high — unambiguous)
          3. Percentage tied to an annual/anniversary cadence keyword
             found nearby (medium)
          4. Any percentage loosely near an "escalat..." keyword (low)
        """
        year_line = r"year\s+(\d+)[:\s]+\$?([\d,]+(?:\.\d{2})?)"

        full_text, page_for_offset = _concat_pages(pages)
        year_matches = list(re.finditer(year_line, full_text, re.IGNORECASE))
        if len(year_matches) >= 2:
            parts = [f"Year {m.group(1)}: ${m.group(2)}" for m in year_matches]
            start = year_matches[0].start()
            end = year_matches[-1].end()
            return {
                "value": "; ".join(parts),
                "source": {"page": page_for_offset(start), "quote": _make_quote(full_text, start, end, pad=20)},
                "confidence": "high"
            }

        patterns = [
            rf"increas\w*\s+by[^.$]{{0,60}}?\(\s*(\d{{1,2}}(?:\.\d+)?)\s*%\s*\)",
            rf"(\d{{1,2}}(?:\.\d+)?)\s*%[^.]{{0,60}}?(?:annual\w*|anniversary|per\s+year|each\s+year)",
            rf"escalat\w*{GAP}(\d{{1,2}}(?:\.\d+)?)\s*%",
        ]
        confidences = ["high", "medium", "low"]

        result = self._search_ordered(pages, patterns, confidences)
        if result:
            quote = result["source"]["quote"].lower()
            suffix = " annually" if ("annual" in quote or "anniversary" in quote or "each year" in quote or "per year" in quote) else " increase"
            result["value"] = f"{result['value']}%{suffix}"
            return result

        return _not_found()

    def _extract_renewal_options(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract renewal option terms: number of options, term length, notice
        period, and basis for renewal rent. Assembled into one summary value
        since these details are usually spread across a single clause.
        Confidence reflects how many of the expected sub-parts were
        corroborated: high if notice AND basis were both found alongside
        the option count/term, medium if only one was found, low if
        neither was found.
        """
        # Two common phrasings: "(N) options to renew ... (M) years" and
        # "extend this Lease for (N) additional period(s) of (M) years".
        # Both often write the number as a spelled-out word immediately
        # before the parenthetical digit ("for one (1) additional
        # period..."), so an optional word is allowed there too.
        spelled_number = r"(?:[a-z\-]+\s+)?"
        options_pattern = (
            rf"\(\s*(\d+)\s*\)\s+options?\s+to\s+renew{WIDE_GAP}\(\s*(\d+)\s*\)\s+years?"
            rf"|extend\w*(?:\s+this\s+lease)?\s+for\s+{spelled_number}\(?\s*(\d+)\s*\)?\s+additional\s+periods?"
            rf"\s+of\s+{spelled_number}\(?\s*(\d+)\s*\)?\s+years?"
        )
        notice_pattern = rf"(?:not\s+less\s+than\s*)?\(?\s*(\d+)\s*\)?\s+days\b[^.]{{0,30}}?(?:notice|prior)"
        basis_pattern = r"(fair\s+market\s+(?:rate|value)|then[- ]prevailing\s+(?:fair\s+)?market\s+rate|consumer\s+price\s+index|CPI|fixed\s+(?:rate|amount|increase))"

        full_text, page_for_offset = _concat_pages(pages)

        match = re.search(options_pattern, full_text, re.IGNORECASE)
        if match:
            num_options = match.group(1) or match.group(3)
            term_years = match.group(2) or match.group(4)

            parts = [f"{num_options} option(s) of {term_years} year(s) each"]

            notice_match = re.search(notice_pattern, full_text, re.IGNORECASE)
            if notice_match:
                parts.append(f"{notice_match.group(1)} days notice")

            basis_match = re.search(basis_pattern, full_text, re.IGNORECASE)
            if basis_match:
                parts.append(f"renewal rent based on {_clean_value(basis_match.group(1)).lower()}")

            sub_parts_found = sum([bool(notice_match), bool(basis_match)])
            confidence = "high" if sub_parts_found == 2 else ("medium" if sub_parts_found == 1 else "low")

            quote = _make_quote(full_text, match.start(), match.end(), pad=80)
            return {
                "value": "; ".join(parts),
                "source": {"page": page_for_offset(match.start()), "quote": quote},
                "confidence": confidence
            }

        # Fallback: label-style single-line summary (medium — raw, unparsed content)
        result = self._search_ordered(pages, [r"renewal\s+option[s]?[:\s]+([^\n]+)"], ["medium"])
        return result if result else _not_found()

    def _extract_default_cure_period(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract the default/cure notice period. A lease can contain several
        unrelated "(N) days ... written notice" clauses (renewal notice,
        cure notice, etc), so this scans every candidate on the page and
        prefers the one with "default"/"cure" nearby, rather than blindly
        taking the first match in document order.
        """
        day_notice_pattern = r"\(?\s*(\d+)\s*\)?\s+(?:business\s+|calendar\s+)?days\b[^.]{0,40}?written\s+notice"
        context_pattern = re.compile(r"\b(?:default|cure)\w*\b", re.IGNORECASE)
        context_window = 150

        full_text, page_for_offset = _concat_pages(pages)

        candidates = list(re.finditer(day_notice_pattern, full_text, re.IGNORECASE))
        if candidates:
            anchored_match = None
            for m in candidates:
                window = full_text[max(0, m.start() - context_window):min(len(full_text), m.end() + context_window)]
                if context_pattern.search(window):
                    anchored_match = m
                    break

            match = anchored_match or candidates[0]
            confidence = "high" if anchored_match else "low"

            return {
                "value": f"{match.group(1)} days after written notice",
                "source": {"page": page_for_offset(match.start()), "quote": _make_quote(full_text, match.start(), match.end())},
                "confidence": confidence
            }

        # Fallback: explicit label style
        result = self._search_ordered(pages, [r"cure\s+period[:\s]+(\d+)\s+days"], ["high"])
        if result:
            result["value"] = f"{result['value']} days after written notice"
            return result

        return _not_found()

    # ------------------------------------------------------------------
    # Property / use clauses
    # ------------------------------------------------------------------

    def _extract_property_address(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns = [
            rf"located\s+at\s+([^.(]{{5,120}}?)(?:\s*\(\s*the\s*{QUOTE_OPEN}Premises{QUOTE_CLOSE}\s*\)|,?\s+consisting|\.)",
            r"(?:property\s+)?address[:\s]+([^\n]+)",
        ]
        confidences = ["high", "high"]

        result = self._search_ordered(pages, patterns, confidences)
        return result if result else _not_found()

    def _extract_square_footage(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract the premises' square footage. Tries, in order:
          1. Label style: "Square Footage: 2,400" / "Rentable Area: 2,400 sq ft" (high)
          2. Prose style with an explicit cue: "approximately 2,400 square
             feet" / "consisting of 2,400 square feet" (high)
          3. Any bare "N square feet" mention (medium — could in principle
             refer to something other than the premises itself)
        """
        sqft_unit = r"(?:square\s+feet|sq\.?\s*ft\.?)"
        patterns = [
            rf"(?:square\s+footage|rentable\s+area|leasable\s+area)[:\s]+([\d,]+)",
            rf"(?:approximately|consisting\s+of)\s+([\d,]+)\s*{sqft_unit}",
            rf"([\d,]+)\s*{sqft_unit}",
        ]
        confidences = ["high", "high", "medium"]

        result = self._search_ordered(pages, patterns, confidences)
        if result:
            result["value"] = f"{result['value']} sq ft"
            return result

        return _not_found()

    def _extract_permitted_use(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns = [
            r"used\s+solely\s+for(?:\s+the\s+(?:operation|purpose)\s+of)?\s+([^.]{5,150}?)(?:,?\s+and\s+for\s+no\s+other\s+purpose|\.)",
            r"use\s+the\s+premises\s+exclusively\s+as\s+([^.]{5,150}?)(?:,?\s+and\s+shall\s+not|\.)",
            r"permitted\s+use[:\s]+([^\n]+)",
            r"use\s+clause[:\s]+([^\n]+)",
        ]
        confidences = ["high", "high", "high", "high"]

        result = self._search_ordered(pages, patterns, confidences)
        return result if result else _not_found()

    def _extract_exclusivity_clause(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns = [
            rf"exclusiv\w*[.\s]{{0,5}}Landlord\s+(?:agrees|covenants)\s+that,?\s+([\s\S]{{5,300}}?)\.",
            r"exclusivity[:\s]+([^\n]+)",
        ]
        confidences = ["high", "medium"]

        result = self._search_ordered(pages, patterns, confidences)
        if result:
            result["value"] = re.sub(r"\s+", " ", result["value"]).strip()
            return result

        return _not_found()
