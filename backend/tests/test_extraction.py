"""
Test script for lease PDF extraction.

This script tests the extraction pipeline with a sample lease PDF.
"""

import os
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor
import json


DOCS = [
    {
        "name": "residential (label-style)",
        "path": "sample_lease.pdf",
        "expected": {
            "tenant": "John Smith",
            "rent_amount": "$2,500",
            "lease_start_date": "January 15, 2024",
            "lease_end_date": "January 14, 2025",
        },
    },
    {
        "name": "commercial (prose-style)",
        "path": "sample_lease_commercial.pdf",
        "expected": {
            "tenant": "Blue Sky Coffee Roasters, Inc.",
            "rent_amount": "$6,250.00",
            "lease_start_date": "April 1, 2025",
            "lease_end_date": "March 31, 2030",
        },
    },
]


def test_extraction():
    """Test the extraction pipeline against all sample lease PDFs."""

    overall_pass = True

    for doc in DOCS:
        sample_lease_path = os.path.join(os.path.dirname(__file__), doc["path"])

        print("=" * 60)
        print(f"DOCUMENT: {doc['name']} ({doc['path']})")
        print("=" * 60)

        if not os.path.exists(sample_lease_path):
            print(f"Error: Sample lease not found at {sample_lease_path}")
            overall_pass = False
            continue

        pdf_extractor = PDFExtractor()
        with open(sample_lease_path, 'rb') as pdf_file:
            pages = pdf_extractor.extract_text(pdf_file, pdf_path=sample_lease_path)

        field_extractor = FieldExtractor()
        extracted_fields = field_extractor.extract_fields(pages)

        print(json.dumps(extracted_fields, indent=2))
        print()

        for field_name, expected_value in doc["expected"].items():
            actual_value = extracted_fields[field_name]["value"]

            if actual_value and expected_value.lower() in str(actual_value).lower():
                print(f"✓ {field_name}: PASS")
            else:
                print(f"✗ {field_name}: FAIL (expected '{expected_value}', got '{actual_value}')")
                overall_pass = False

        print()

    print("=" * 60)
    print("PASS" if overall_pass else "FAIL", "- overall result")
    print("=" * 60)

    return overall_pass


if __name__ == "__main__":
    success = test_extraction()
    sys.exit(0 if success else 1)
