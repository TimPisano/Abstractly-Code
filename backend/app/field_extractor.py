"""
Field extraction module for lease documents.

This module contains logic to extract specific fields (tenant, rent, dates)
from lease PDFs using regex patterns and keyword matching.

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
"""

import re
from typing import Optional, Dict, Any, List, Tuple


MONTHS = (r"January|February|March|April|May|June|July|August|September"
          r"|October|November|December")

# Matches "01/15/2024", "1-15-24", or "January 15, 2024"
DATE_REGEX = rf"(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|(?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})"

# Matches "$2,500.00", "$2,500", "$ 2,500.00"
CURRENCY_REGEX = r"\$\s?([\d,]+(?:\.\d{2})?)"

# Bounded gap between a keyword and its value. Excludes "." and "$" so the
# match can't run past the end of a sentence or swallow an unrelated dollar
# amount, but newlines (from PDF line-wrapping) are allowed through.
GAP = r"[^.$]{0,100}?"

# Smart quotes vs straight quotes around defined terms like ("Tenant")
QUOTE_OPEN = r"[\"“]"
QUOTE_CLOSE = r"[\"”]"


def _make_quote(text: str, start: int, end: int, pad: int = 50) -> str:
    """Build a readable context snippet around a regex match span."""
    quote_start = max(0, start - pad)
    quote_end = min(len(text), end + pad)
    quote = text[quote_start:quote_end].strip()
    # Collapse line-wrap newlines into spaces for readability
    return re.sub(r"\s+", " ", quote)


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
            Dictionary with extracted fields in the required format
        """
        result = {
            "tenant": self._extract_defined_party(pages, "Tenant", self._tenant_label_patterns()),
            "rent_amount": self._extract_rent(pages),
            "lease_start_date": self._extract_start_date(pages),
            "lease_end_date": self._extract_end_date(pages)
        }

        return result

    def _search_ordered(
        self,
        pages: List[Dict[str, Any]],
        patterns: List[str],
        group: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Try each pattern (in priority order) against each page (in document
        order), returning the first match found.
        """
        for page in pages:
            page_num = page["page"]
            text = page["text"]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(group).strip()
                    quote = _make_quote(text, match.start(), match.end())
                    return {
                        "value": value,
                        "source": {"page": page_num, "quote": quote}
                    }

        return None

    # ------------------------------------------------------------------
    # Party name extraction (tenant / landlord)
    # ------------------------------------------------------------------

    def _tenant_label_patterns(self) -> List[str]:
        return [
            r"tenant[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"lessee[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"renter[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"tenant\s+name[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"name\s+of\s+tenant[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
        ]

    def _extract_defined_party(
        self,
        pages: List[Dict[str, Any]],
        role: str,
        label_patterns: List[str]
    ) -> Dict[str, Any]:
        """
        Extract a party name (Tenant/Landlord). Tries, in order:
          1. Defined-term prose style: '...Some Company, LLC ("Tenant")'
          2. Label style: 'Tenant: John Smith'
        """
        defined_term_pattern = (
            rf"([A-Z][A-Za-z0-9&,\.\'\-\s]{{2,80}}?)\s*\(\s*{QUOTE_OPEN}{role}{QUOTE_CLOSE}\s*\)"
        )

        result = self._search_ordered(pages, [defined_term_pattern])
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

        result = self._search_ordered(pages, label_patterns)
        if result:
            return result

        return {"value": None, "source": None}

    # ------------------------------------------------------------------
    # Rent amount
    # ------------------------------------------------------------------

    def _extract_rent(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract monthly rent amount. Tries, in order:
          1. Label style: "Monthly Rent: $2,500.00"
          2. Prose style: "base rent ... the sum of $6,250.00 per month"
          3. Loose fallback: any rent-labeled dollar amount, even without
             an explicit "per month" suffix
        """
        rent_keyword = r"(?:base\s+rent|monthly\s+rent|rental\s+amount|monthly\s+payment)"

        patterns = [
            # Label style: keyword immediately followed by amount
            rf"{rent_keyword}[:\s]+{CURRENCY_REGEX}",
            # Prose style: keyword ... "sum of" ... amount ... "per month"
            rf"{rent_keyword}{GAP}{CURRENCY_REGEX}\s*(?:per\s+month|/\s*mo\.?|monthly)",
            # Prose style without the trailing "per month" cue
            rf"{rent_keyword}{GAP}{CURRENCY_REGEX}",
            # Generic "rent is $X" phrasing
            rf"rent\s+is\s+{CURRENCY_REGEX}",
        ]

        result = self._search_ordered(pages, patterns)
        if result:
            value = result["value"]
            if not value.startswith("$"):
                value = "$" + value
            result["value"] = value
            return result

        return {"value": None, "source": None}

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------

    def _extract_start_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract lease start date. Tries, in order:
          1. Label style: "Lease Start Date: January 15, 2024"
          2. Prose style: "term shall commence on April 1, 2025"
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

        result = self._search_ordered(pages, patterns)
        return result if result else {"value": None, "source": None}

    def _extract_end_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract lease end date. Tries, in order:
          1. Label style: "Lease End Date: January 14, 2025"
          2. Prose style: "shall expire on March 31, 2030"
        """
        patterns = [
            rf"(?:lease\s+)?end\s+date[:\s]+{DATE_REGEX}",
            rf"expiration\s+date[:\s]+{DATE_REGEX}",
            rf"termination\s+date[:\s]+{DATE_REGEX}",
            rf"term\s+ends?[:\s]+{DATE_REGEX}",
            rf"expires?[:\s]+{DATE_REGEX}",
            rf"(?:shall\s+)?expir\w*{GAP}{DATE_REGEX}",
            rf"(?:shall\s+)?terminat\w*{GAP}{DATE_REGEX}",
        ]

        result = self._search_ordered(pages, patterns)
        return result if result else {"value": None, "source": None}
