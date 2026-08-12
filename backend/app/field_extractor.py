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
        }

        return result

    def _search_ordered(
        self,
        pages: List[Dict[str, Any]],
        patterns: List[str],
        confidences: List[str],
        group: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Try each pattern (in priority order) against each page (in document
        order), returning the first match found. `confidences` must be the
        same length as `patterns` and gives the confidence tier to report
        for a match on that pattern.
        """
        assert len(patterns) == len(confidences)

        for page in pages:
            page_num = page["page"]
            text = page["text"]

            for pattern, confidence in zip(patterns, confidences):
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = _clean_value(match.group(group))
                    quote = _make_quote(text, match.start(), match.end())
                    return {
                        "value": value,
                        "source": {"page": page_num, "quote": quote},
                        "confidence": confidence
                    }

        return None

    # ------------------------------------------------------------------
    # Party name extraction (tenant / landlord)
    # ------------------------------------------------------------------

    def _party_label_patterns(self, *keywords: str) -> List[str]:
        keyword_group = "|".join(keywords)
        return [
            # Capitalized personal name, e.g. "Tenant: John Smith"
            rf"(?:{keyword_group})[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            # Company/entity name (allows acronyms like LLC), to end of line,
            # e.g. "Landlord: Property Management LLC"
            rf"(?:{keyword_group})[:\s]+([A-Z][\w&,\.\'\-\s]+?)(?:\n|$)",
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
        """
        defined_term_pattern = (
            rf"([A-Z][A-Za-z0-9&,\.\'\-\s]{{2,80}}?)\s*\(\s*{QUOTE_OPEN}{role}{QUOTE_CLOSE}\s*\)"
        )

        result = self._search_ordered(pages, [defined_term_pattern], ["high"])
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

        result = self._search_ordered(pages, label_patterns, ["high", "high"])
        if result:
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
        patterns = [
            rf"{keyword}[:\s]+{CURRENCY_REGEX}",
            rf"{keyword}{GAP}{CURRENCY_REGEX}",
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
        cam_keyword = r"(?:common\s+area\s+maintenance(?:\s*\(\s*cam\s*\))?|cam\s+charges)"
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
            rf"rent\s+is\s+{CURRENCY_REGEX}",
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

    def _extract_start_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract lease start date. Tries, in order:
          1. Label style: "Lease Start Date: January 15, 2024" (high)
          2. Prose style: "term shall commence on April 1, 2025" (high)
          3. Loose "begin..." fallback, e.g. could latch onto unrelated
             text like "beginning of the fiscal year" (medium)
        """
        patterns = [
            rf"(?:lease\s+)?start\s+date[:\s]+{DATE_REGEX}",
            rf"commencement\s+date[:\s]+{DATE_REGEX}",
            rf"begin(?:ning)?\s+date[:\s]+{DATE_REGEX}",
            rf"term\s+begins?[:\s]+{DATE_REGEX}",
            rf"effective\s+date[:\s]+{DATE_REGEX}",
            rf"(?:shall\s+)?commenc\w*{GAP}{DATE_REGEX}",
            rf"begin\w*{GAP}{DATE_REGEX}",
        ]
        confidences = ["high", "high", "high", "high", "high", "high", "medium"]

        result = self._search_ordered(pages, patterns, confidences)
        return result if result else _not_found()

    def _extract_end_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract lease end date. Tries, in order:
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
            rf"(?:shall\s+)?expir\w*{GAP}{DATE_REGEX}",
            rf"(?:shall\s+)?terminat\w*{GAP}{DATE_REGEX}",
            rf"ending{GAP}{DATE_REGEX}",
        ]
        confidences = ["high", "high", "high", "high", "high", "high", "high", "medium"]

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

        for page in pages:
            page_num = page["page"]
            text = page["text"]

            year_matches = list(re.finditer(year_line, text, re.IGNORECASE))
            if len(year_matches) >= 2:
                parts = [f"Year {m.group(1)}: ${m.group(2)}" for m in year_matches]
                start = year_matches[0].start()
                end = year_matches[-1].end()
                return {
                    "value": "; ".join(parts),
                    "source": {"page": page_num, "quote": _make_quote(text, start, end, pad=20)},
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
        options_pattern = rf"\(\s*(\d+)\s*\)\s+options?\s+to\s+renew{WIDE_GAP}\(\s*(\d+)\s*\)\s+years?"
        notice_pattern = rf"(?:not\s+less\s+than\s*)?\(\s*(\d+)\s*\)\s+days\b[^.]{{0,30}}?(?:notice|prior)"
        basis_pattern = r"(fair\s+market\s+(?:rate|value)|then[- ]prevailing\s+(?:fair\s+)?market\s+rate|consumer\s+price\s+index|CPI|fixed\s+(?:rate|amount|increase))"

        for page in pages:
            page_num = page["page"]
            text = page["text"]

            match = re.search(options_pattern, text, re.IGNORECASE)
            if not match:
                continue

            num_options = match.group(1)
            term_years = match.group(2)

            parts = [f"{num_options} option(s) of {term_years} year(s) each"]

            notice_match = re.search(notice_pattern, text, re.IGNORECASE)
            if notice_match:
                parts.append(f"{notice_match.group(1)} days notice")

            basis_match = re.search(basis_pattern, text, re.IGNORECASE)
            if basis_match:
                parts.append(f"renewal rent based on {_clean_value(basis_match.group(1)).lower()}")

            sub_parts_found = sum([bool(notice_match), bool(basis_match)])
            confidence = "high" if sub_parts_found == 2 else ("medium" if sub_parts_found == 1 else "low")

            quote = _make_quote(text, match.start(), match.end(), pad=80)
            return {
                "value": "; ".join(parts),
                "source": {"page": page_num, "quote": quote},
                "confidence": confidence
            }

        # Fallback: label-style single-line summary (medium — raw, unparsed content)
        result = self._search_ordered(pages, [r"renewal\s+option[s]?[:\s]+([^\n]+)"], ["medium"])
        return result if result else _not_found()

    def _extract_default_cure_period(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns = [
            r"\(\s*(\d+)\s*\)\s+(?:business\s+|calendar\s+)?days\b[^.]{0,40}?written\s+notice",
            r"(\d+)\s+(?:business\s+|calendar\s+)?days\b[^.]{0,40}?written\s+notice",
            r"cure\s+period[:\s]+(\d+)\s+days",
        ]
        confidences = ["high", "medium", "high"]

        result = self._search_ordered(pages, patterns, confidences)
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

    def _extract_permitted_use(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns = [
            r"used\s+solely\s+for(?:\s+the\s+(?:operation|purpose)\s+of)?\s+([^.]{5,150}?)(?:,?\s+and\s+for\s+no\s+other\s+purpose|\.)",
            r"permitted\s+use[:\s]+([^\n]+)",
            r"use\s+clause[:\s]+([^\n]+)",
        ]
        confidences = ["high", "high", "high"]

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
