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


def test_extraction():
    """Test the extraction pipeline with sample lease PDF."""

    # Path to sample lease
    sample_lease_path = os.path.join(os.path.dirname(__file__), "sample_lease.pdf")

    if not os.path.exists(sample_lease_path):
        print(f"Error: Sample lease not found at {sample_lease_path}")
        print("Please run create_sample_lease.py first to generate the sample PDF.")
        return

    print(f"Testing extraction with: {sample_lease_path}\n")

    # Step 1: Extract text from PDF
    print("Step 1: Extracting text from PDF...")
    pdf_extractor = PDFExtractor()

    with open(sample_lease_path, 'rb') as pdf_file:
        pages = pdf_extractor.extract_text(pdf_file, pdf_path=sample_lease_path)

    print(f"✓ Extracted {len(pages)} page(s)\n")

    # Print extracted text for debugging
    for page in pages:
        print(f"--- Page {page['page']} ---")
        print(page['text'][:500])  # Print first 500 chars
        if len(page['text']) > 500:
            print("...")
        print()

    # Step 2: Extract fields
    print("Step 2: Extracting fields...")
    field_extractor = FieldExtractor()
    extracted_fields = field_extractor.extract_fields(pages)

    print("✓ Field extraction complete\n")

    # Step 3: Display results
    print("=" * 60)
    print("EXTRACTION RESULTS")
    print("=" * 60)
    print(json.dumps(extracted_fields, indent=2))
    print()

    # Step 4: Validate results
    print("=" * 60)
    print("VALIDATION")
    print("=" * 60)

    expected = {
        "tenant": "John Smith",
        "rent_amount": "$2,500",
        "lease_start_date": "January 15, 2024",
        "lease_end_date": "January 14, 2025"
    }

    for field_name, expected_value in expected.items():
        actual_value = extracted_fields[field_name]["value"]

        if actual_value and expected_value.lower() in str(actual_value).lower():
            print(f"✓ {field_name}: PASS")
        else:
            print(f"✗ {field_name}: FAIL (expected '{expected_value}', got '{actual_value}')")

    print()


if __name__ == "__main__":
    test_extraction()
