"""
Tests for field_extractor.py's confidence-validation layer: a second,
independent signal layered on top of the pattern-based confidence every
field already carries. Pattern confidence answers "how reliably was
this text located" -- validation answers "does the located value
actually look real, and was the page it came from even legible."

Field dicts are built directly (same {value, source, confidence} shape
FieldExtractor.extract_fields() produces), same convention
test_risk_analysis.py already uses, so each rule can be driven to both
sides of its threshold deliberately without needing a real PDF for
every boundary case.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.field_extractor import FieldExtractor


def _field(value, confidence="high", page=1):
    if value is None:
        return {"value": None, "source": None, "confidence": None}
    return {"value": value, "source": {"page": page, "quote": f"...{value}..."}, "confidence": confidence}


def test_rent_below_minimum_is_downgraded():
    fx = FieldExtractor()
    entry = _field("$5.00", "high")
    fx._validate_currency_range(entry, 50, 1_000_000, "Rent amount")
    assert entry["confidence"] == "medium"
    assert "validation_note" in entry
    assert "$5.00" in entry["validation_note"]
    print("✓ test_rent_below_minimum_is_downgraded: PASS")


def test_rent_above_maximum_is_downgraded():
    fx = FieldExtractor()
    entry = _field("$5,000,000.00", "high")
    fx._validate_currency_range(entry, 50, 1_000_000, "Rent amount")
    assert entry["confidence"] == "medium"
    assert "validation_note" in entry
    print("✓ test_rent_above_maximum_is_downgraded: PASS")


def test_rent_within_range_is_unaffected():
    fx = FieldExtractor()
    entry = _field("$6,250.00", "high")
    fx._validate_currency_range(entry, 50, 1_000_000, "Rent amount")
    assert entry["confidence"] == "high"
    assert "validation_note" not in entry
    print("✓ test_rent_within_range_is_unaffected: PASS")


def test_not_found_field_is_untouched_by_currency_validation():
    fx = FieldExtractor()
    entry = _field(None)
    fx._validate_currency_range(entry, 50, 1_000_000, "Rent amount")
    assert entry == {"value": None, "source": None, "confidence": None}
    print("✓ test_not_found_field_is_untouched_by_currency_validation: PASS")


def test_low_confidence_field_stays_low_on_downgrade():
    """Validation only ever downgrades -- "low" has nowhere lower to go."""
    fx = FieldExtractor()
    entry = _field("$5.00", "low")
    fx._validate_currency_range(entry, 50, 1_000_000, "Rent amount")
    assert entry["confidence"] == "low"
    assert "validation_note" in entry
    print("✓ test_low_confidence_field_stays_low_on_downgrade: PASS")


def test_square_footage_too_small_is_downgraded():
    fx = FieldExtractor()
    entry = _field("10 sq ft", "high")
    fx._validate_square_footage(entry)
    assert entry["confidence"] == "medium"
    assert "validation_note" in entry
    print("✓ test_square_footage_too_small_is_downgraded: PASS")


def test_square_footage_too_large_is_downgraded():
    fx = FieldExtractor()
    entry = _field("5,000,000 sq ft", "high")
    fx._validate_square_footage(entry)
    assert entry["confidence"] == "medium"
    print("✓ test_square_footage_too_large_is_downgraded: PASS")


def test_square_footage_within_range_is_unaffected():
    fx = FieldExtractor()
    entry = _field("2,400 sq ft", "high")
    fx._validate_square_footage(entry)
    assert entry["confidence"] == "high"
    assert "validation_note" not in entry
    print("✓ test_square_footage_within_range_is_unaffected: PASS")


def test_end_date_before_start_date_downgrades_end_date_only():
    fx = FieldExtractor()
    start = _field("April 1, 2025", "high")
    end = _field("January 1, 2024", "high")
    fx._validate_date_fields(start, end)
    assert start["confidence"] == "high" and "validation_note" not in start
    assert end["confidence"] == "medium"
    assert "April 1, 2025" in end["validation_note"] and "January 1, 2024" in end["validation_note"]
    print("✓ test_end_date_before_start_date_downgrades_end_date_only: PASS")


def test_implausible_year_is_downgraded():
    fx = FieldExtractor()
    start = _field("April 1, 1900", "high")
    end = _field("April 1, 1905", "high")
    fx._validate_date_fields(start, end)
    assert start["confidence"] == "medium"
    assert "1900" in start["validation_note"]
    print("✓ test_implausible_year_is_downgraded: PASS")


def test_sensible_date_pair_is_unaffected():
    fx = FieldExtractor()
    start = _field("April 1, 2025", "high")
    end = _field("March 31, 2030", "high")
    fx._validate_date_fields(start, end)
    assert start["confidence"] == "high" and "validation_note" not in start
    assert end["confidence"] == "high" and "validation_note" not in end
    print("✓ test_sensible_date_pair_is_unaffected: PASS")


def test_field_from_low_ocr_confidence_page_is_downgraded():
    fx = FieldExtractor()
    result = {
        "rent_amount": _field("$6,250.00", "high", page=1),
        "tenant": _field("Blue Sky Coffee Roasters, Inc.", "high", page=2),
    }
    pages = [
        {"page": 1, "text": "...", "ocr_confidence": 35.0},
        {"page": 2, "text": "...", "ocr_confidence": 91.0},
    ]
    fx._validate_ocr_page_clarity(result, pages)
    assert result["rent_amount"]["confidence"] == "medium"
    assert "35" in result["rent_amount"]["validation_note"]
    assert result["tenant"]["confidence"] == "high"
    assert "validation_note" not in result["tenant"]
    print("✓ test_field_from_low_ocr_confidence_page_is_downgraded: PASS")


def test_ocr_clarity_check_is_a_noop_for_digitally_extracted_pages():
    """No page carries ocr_confidence at all (a normal digital PDF) -- nothing should be touched."""
    fx = FieldExtractor()
    result = {"rent_amount": _field("$6,250.00", "high", page=1)}
    pages = [{"page": 1, "text": "..."}]
    fx._validate_ocr_page_clarity(result, pages)
    assert result["rent_amount"]["confidence"] == "high"
    assert "validation_note" not in result["rent_amount"]
    print("✓ test_ocr_clarity_check_is_a_noop_for_digitally_extracted_pages: PASS")


def test_two_validation_failures_compound_through_both_tiers():
    """A field that's both out-of-range AND from a low-clarity OCR page gets downgraded twice: high -> medium -> low."""
    fx = FieldExtractor()
    result = {"rent_amount": _field("$5.00", "high", page=1)}
    pages = [{"page": 1, "text": "...", "ocr_confidence": 20.0}]
    fx._validate_currency_range(result["rent_amount"], 50, 1_000_000, "Rent amount")
    assert result["rent_amount"]["confidence"] == "medium"
    fx._validate_ocr_page_clarity(result, pages)
    assert result["rent_amount"]["confidence"] == "low"
    print("✓ test_two_validation_failures_compound_through_both_tiers: PASS")


def test_extract_fields_applies_validation_end_to_end():
    """Full extract_fields() pipeline: a synthetic page with an implausible rent figure should come back downgraded, not just pattern-matched."""
    fx = FieldExtractor()
    pages = [{
        "page": 1,
        "text": (
            'This Lease is between Example Landlord LLC ("Landlord") and '
            'Example Tenant Inc. ("Tenant"). Monthly Rent: $3.00. '
            "Lease Start Date: April 1, 2025. Lease End Date: March 31, 2030."
        ),
    }]
    fields = fx.extract_fields(pages)
    assert fields["rent_amount"]["value"] == "$3.00"
    assert fields["rent_amount"]["confidence"] == "medium", fields["rent_amount"]
    assert "validation_note" in fields["rent_amount"]
    # An unaffected field on the same page must come back completely untouched.
    assert fields["tenant"]["value"] == "Example Tenant Inc."
    assert fields["tenant"]["confidence"] == "high"
    assert "validation_note" not in fields["tenant"]
    print("✓ test_extract_fields_applies_validation_end_to_end: PASS")


if __name__ == "__main__":
    test_rent_below_minimum_is_downgraded()
    test_rent_above_maximum_is_downgraded()
    test_rent_within_range_is_unaffected()
    test_not_found_field_is_untouched_by_currency_validation()
    test_low_confidence_field_stays_low_on_downgrade()
    test_square_footage_too_small_is_downgraded()
    test_square_footage_too_large_is_downgraded()
    test_square_footage_within_range_is_unaffected()
    test_end_date_before_start_date_downgrades_end_date_only()
    test_implausible_year_is_downgraded()
    test_sensible_date_pair_is_unaffected()
    test_field_from_low_ocr_confidence_page_is_downgraded()
    test_ocr_clarity_check_is_a_noop_for_digitally_extracted_pages()
    test_two_validation_failures_compound_through_both_tiers()
    test_extract_fields_applies_validation_end_to_end()
    print("\nAll confidence validation tests passed.")
