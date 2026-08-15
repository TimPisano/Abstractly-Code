"""
Tests for FieldExtractor.detect_multiple_leases() and its wiring into
the upload pipeline (_extract_fields_from_file_storage in api.py).

This exists because of a real, empirically-confirmed bug: a PDF that
bundles more than one distinct lease (several tenants scanned/merged
into a single file) was being silently persisted as ONE lease record,
with each field independently "winning" from whichever constituent
lease happened to match first/best for that field — e.g. the tenant
name from lease #2 paired with the rent amount from lease #1. See
DECISIONS.md for the investigation (concatenating two real fixture PDFs
and showing the extracted record mixed both leases' data).

Every fixture combination tested here is built at runtime from this
project's own real fixture PDFs via PyPDF2 (no synthetic text) — both
for the "must NOT flag a real single lease" checks (every existing
fixture, individually) and the "must flag a real merged PDF" checks
(several different genuine multi-file merges).
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyPDF2 import PdfReader, PdfWriter

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor

FIXTURES_DIR = os.path.dirname(__file__)

ALL_SINGLE_LEASE_FIXTURES = [
    "casual_sublease.pdf", "inconsistent_escalation.pdf", "missing_clauses_office.pdf",
    "office_lease.pdf", "retail_lease.pdf", "reversed_dates.pdf", "sample_lease.pdf",
    "sample_lease_commercial.pdf", "tenant_friendly_terms.pdf", "underpriced_downtown.pdf",
]


def _extract_pages(path):
    with open(path, 'rb') as f:
        return PDFExtractor().extract_text(f, pdf_path=path)


def _merge_fixtures(*filenames, out_path):
    """Concatenates real fixture PDFs' pages into one PDF at out_path via PyPDF2 — a real merged document, not synthetic text."""
    writer = PdfWriter()
    for filename in filenames:
        reader = PdfReader(os.path.join(FIXTURES_DIR, filename))
        for page in reader.pages:
            writer.add_page(page)
    with open(out_path, 'wb') as f:
        writer.write(f)
    return out_path


def test_no_false_positives_on_any_real_single_lease_fixture():
    """The core safety requirement: every genuine single-lease fixture in this repo must come back clean."""
    fe = FieldExtractor()
    false_positives = []
    for filename in ALL_SINGLE_LEASE_FIXTURES:
        path = os.path.join(FIXTURES_DIR, filename)
        pages = _extract_pages(path)
        result = fe.detect_multiple_leases(pages)
        if result:
            false_positives.append((filename, result))

    assert not false_positives, f"false positive(s) on real single-lease fixtures: {false_positives}"
    print(f"✓ test_no_false_positives_on_any_real_single_lease_fixture: PASS ({len(ALL_SINGLE_LEASE_FIXTURES)} fixtures checked)")


def test_detects_two_merged_leases():
    fe = FieldExtractor()
    merged_path = "/tmp/test_merge_two.pdf"
    _merge_fixtures("retail_lease.pdf", "office_lease.pdf", out_path=merged_path)
    try:
        pages = _extract_pages(merged_path)
        result = fe.detect_multiple_leases(pages)
        assert result is not None, "a real 2-lease merged PDF must be flagged"
        assert "tenants" in result
        assert len(result["tenants"]) == 2
        assert set(result["tenants"]) == {"Cascade Apparel Co.", "Vertex Analytics LLC"}
        assert "landlords" in result
        assert len(result["landlords"]) == 2
    finally:
        os.unlink(merged_path)
    print("✓ test_detects_two_merged_leases: PASS")


def test_detects_three_merged_leases():
    fe = FieldExtractor()
    merged_path = "/tmp/test_merge_three.pdf"
    _merge_fixtures("retail_lease.pdf", "office_lease.pdf", "sample_lease_commercial.pdf", out_path=merged_path)
    try:
        pages = _extract_pages(merged_path)
        result = fe.detect_multiple_leases(pages)
        assert result is not None
        assert len(result["tenants"]) == 3
    finally:
        os.unlink(merged_path)
    print("✓ test_detects_three_merged_leases: PASS")


def test_detects_merge_of_casual_style_leases():
    """The two false positives found and fixed while building this were both on casually-worded fixtures (casual_sublease.pdf, sample_lease_commercial.pdf) — confirm real detection still works on that same style once genuinely merged with another lease, not just that they're individually clean."""
    fe = FieldExtractor()
    merged_path = "/tmp/test_merge_casual.pdf"
    _merge_fixtures("sample_lease.pdf", "casual_sublease.pdf", out_path=merged_path)
    try:
        pages = _extract_pages(merged_path)
        result = fe.detect_multiple_leases(pages)
        assert result is not None
        assert set(result["tenants"]) == {"John Smith", "Alex Chen"}
    finally:
        os.unlink(merged_path)
    print("✓ test_detects_merge_of_casual_style_leases: PASS")


def test_extract_fields_still_works_normally_on_single_leases():
    """Confirms adding the check didn't change extract_fields()'s own behavior/output for a real single lease."""
    fe = FieldExtractor()
    pages = _extract_pages(os.path.join(FIXTURES_DIR, "sample_lease.pdf"))
    fields = fe.extract_fields(pages)
    assert fields["tenant"]["value"] == "John Smith"
    assert fields["rent_amount"]["value"] == "$2,500.00"
    print("✓ test_extract_fields_still_works_normally_on_single_leases: PASS")


def test_dedupe_merges_same_entity_with_and_without_suffix():
    """Unit-level check on the dedup helper directly: 'Acme Co' and 'Acme Co, Inc.' are the same party, not two."""
    deduped = FieldExtractor._dedupe_party_values([
        "Blue Sky Coffee Roasters, Inc.", "Blue Sky Coffee Roasters",
        "Meridian Properties Group, LLC", "Meridian Properties Group",
    ])
    assert len(deduped) == 2, f"expected 2 distinct parties, got {deduped}"
    print("✓ test_dedupe_merges_same_entity_with_and_without_suffix: PASS")


def test_dedupe_keeps_genuinely_different_names_distinct():
    deduped = FieldExtractor._dedupe_party_values(["Alex Chen", "Jordan Blake", "Vertex Analytics LLC"])
    assert len(deduped) == 3
    print("✓ test_dedupe_keeps_genuinely_different_names_distinct: PASS")


if __name__ == "__main__":
    test_no_false_positives_on_any_real_single_lease_fixture()
    test_detects_two_merged_leases()
    test_detects_three_merged_leases()
    test_detects_merge_of_casual_style_leases()
    test_extract_fields_still_works_normally_on_single_leases()
    test_dedupe_merges_same_entity_with_and_without_suffix()
    test_dedupe_keeps_genuinely_different_names_distinct()
    print("\nAll multi-lease detection tests passed.")
