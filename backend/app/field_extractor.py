"""
Field extraction module for lease documents.

This module contains logic to extract specific fields (tenant, rent, dates)
from lease PDFs using regex patterns and keyword matching.
"""

import re
from typing import Optional, Dict, Any, List
from datetime import datetime


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
            "tenant": self._extract_tenant(pages),
            "rent_amount": self._extract_rent(pages),
            "lease_start_date": self._extract_start_date(pages),
            "lease_end_date": self._extract_end_date(pages)
        }

        return result

    def _extract_tenant(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract tenant name from lease document.

        Strategy: Look for patterns like "Tenant:", "Lessee:", etc.
        Usually appears early in the document.

        Returns:
            {"value": "tenant name", "source": {"page": N, "quote": "..."}}
            or {"value": null, "source": null} if not found
        """
        # Keywords that typically precede tenant name
        # Use [^\n] to avoid capturing newlines in names
        tenant_keywords = [
            r"tenant[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"lessee[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"renter[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"tenant\s+name[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)",
            r"name\s+of\s+tenant[:\s]+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*)"
        ]

        # Search through pages (prioritize earlier pages)
        for page in pages:
            page_num = page["page"]
            text = page["text"]

            # Try each pattern
            for pattern in tenant_keywords:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    tenant_name = match.group(1).strip()

                    # Extract a quote showing context (50 chars before and after)
                    match_start = match.start()
                    match_end = match.end()
                    quote_start = max(0, match_start - 50)
                    quote_end = min(len(text), match_end + 50)
                    quote = text[quote_start:quote_end].strip()

                    return {
                        "value": tenant_name,
                        "source": {
                            "page": page_num,
                            "quote": quote
                        }
                    }

        # Not found
        return {"value": None, "source": None}

    def _extract_rent(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract rent amount from lease document.

        Strategy: Look for patterns like "$X,XXX", "rent: $X", etc.

        Returns:
            {"value": "rent amount", "source": {"page": N, "quote": "..."}}
            or {"value": null, "source": null} if not found
        """
        # Patterns for rent amount - look for dollar amounts with rent-related keywords
        rent_patterns = [
            r"(?:monthly\s+)?rent[:\s]+\$?([\d,]+(?:\.\d{2})?)",
            r"rental\s+amount[:\s]+\$?([\d,]+(?:\.\d{2})?)",
            r"base\s+rent[:\s]+\$?([\d,]+(?:\.\d{2})?)",
            r"monthly\s+payment[:\s]+\$?([\d,]+(?:\.\d{2})?)",
            r"rent\s+is\s+\$?([\d,]+(?:\.\d{2})?)"
        ]

        for page in pages:
            page_num = page["page"]
            text = page["text"]

            for pattern in rent_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    rent_amount = match.group(1).strip()

                    # Add dollar sign if not present
                    if not rent_amount.startswith("$"):
                        rent_amount = "$" + rent_amount

                    # Extract context quote
                    match_start = match.start()
                    match_end = match.end()
                    quote_start = max(0, match_start - 50)
                    quote_end = min(len(text), match_end + 50)
                    quote = text[quote_start:quote_end].strip()

                    return {
                        "value": rent_amount,
                        "source": {
                            "page": page_num,
                            "quote": quote
                        }
                    }

        return {"value": None, "source": None}

    def _extract_start_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract lease start date from lease document.

        Strategy: Look for "start date", "commencement date", "begin date", etc.

        Returns:
            {"value": "date", "source": {"page": N, "quote": "..."}}
            or {"value": null, "source": null} if not found
        """
        # Date pattern - matches formats like "01/15/2024", "January 15, 2024", etc.
        date_regex = r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})"

        start_patterns = [
            rf"(?:lease\s+)?start\s+date[:\s]+{date_regex}",
            rf"commencement\s+date[:\s]+{date_regex}",
            rf"begin(?:ning)?\s+date[:\s]+{date_regex}",
            rf"term\s+begins?[:\s]+{date_regex}",
            rf"effective\s+date[:\s]+{date_regex}"
        ]

        for page in pages:
            page_num = page["page"]
            text = page["text"]

            for pattern in start_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # The date is in the last capturing group
                    date_str = match.group(match.lastindex).strip()

                    # Extract context quote
                    match_start = match.start()
                    match_end = match.end()
                    quote_start = max(0, match_start - 50)
                    quote_end = min(len(text), match_end + 50)
                    quote = text[quote_start:quote_end].strip()

                    return {
                        "value": date_str,
                        "source": {
                            "page": page_num,
                            "quote": quote
                        }
                    }

        return {"value": None, "source": None}

    def _extract_end_date(self, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract lease end date from lease document.

        Strategy: Look for "end date", "expiration date", "termination date", etc.

        Returns:
            {"value": "date", "source": {"page": N, "quote": "..."}}
            or {"value": null, "source": null} if not found
        """
        # Date pattern
        date_regex = r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})"

        end_patterns = [
            rf"(?:lease\s+)?end\s+date[:\s]+{date_regex}",
            rf"expiration\s+date[:\s]+{date_regex}",
            rf"termination\s+date[:\s]+{date_regex}",
            rf"term\s+ends?[:\s]+{date_regex}",
            rf"expires?[:\s]+{date_regex}"
        ]

        for page in pages:
            page_num = page["page"]
            text = page["text"]

            for pattern in end_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # The date is in the last capturing group
                    date_str = match.group(match.lastindex).strip()

                    # Extract context quote
                    match_start = match.start()
                    match_end = match.end()
                    quote_start = max(0, match_start - 50)
                    quote_end = min(len(text), match_end + 50)
                    quote = text[quote_start:quote_end].strip()

                    return {
                        "value": date_str,
                        "source": {
                            "page": page_num,
                            "quote": quote
                        }
                    }

        return {"value": None, "source": None}
