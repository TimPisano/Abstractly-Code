"""
Tests for FieldExtractor.detect_multiple_leases(), detect_lease_
boundaries(), and extract_multiple_leases() — and, further down, the
per-lease field/date-candidate accuracy those boundaries actually
produce.

This exists because of a real, empirically-confirmed bug: a PDF that
bundles more than one distinct lease (several tenants scanned/merged
into a single file) was being silently persisted as ONE lease record,
with each field independently "winning" from whichever constituent
lease happened to match first/best for that field — e.g. the tenant
name from lease #2 paired with the rent amount from lease #1, and a
risk-analysis date-conflict flag listing every date in the WHOLE
document as though they all belonged to one lease. See DECISIONS.md for
the investigation (concatenating real fixture PDFs and showing the
extracted record mixed leases' data).

An earlier version of this fix refused to persist a detected multi-
lease PDF at all (see the git history / DECISIONS.md for that
iteration) — this file's newer tests cover the current behavior:
splitting the document into correctly-attributed per-lease records
instead of refusing the upload.

Every fixture combination tested here is built at runtime from this
project's own real fixture PDFs via PyPDF2 (no synthetic text) — both
for the "must NOT flag/split a real single lease" checks (every
existing fixture, individually) and the "must correctly split a real
merged PDF" checks (several different genuine multi-file merges).
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pypdf import PdfReader, PdfWriter

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


# ------------------------------------------------------------------
# detect_lease_boundaries() — page-range computation
# ------------------------------------------------------------------

def test_boundaries_single_range_for_every_real_single_lease_fixture():
    """Same safety requirement as the detection tests above, at the boundary level: every genuine single-lease fixture must yield exactly one page range covering the whole document."""
    fe = FieldExtractor()
    wrong = []
    for filename in ALL_SINGLE_LEASE_FIXTURES:
        pages = _extract_pages(os.path.join(FIXTURES_DIR, filename))
        boundaries = fe.detect_lease_boundaries(pages)
        expected = (pages[0]["page"], pages[-1]["page"])
        if boundaries != [expected]:
            wrong.append((filename, boundaries, expected))
    assert not wrong, f"wrong boundaries on real single-lease fixtures: {wrong}"
    print(f"✓ test_boundaries_single_range_for_every_real_single_lease_fixture: PASS ({len(ALL_SINGLE_LEASE_FIXTURES)} fixtures checked)")


def test_boundaries_cover_whole_document_with_no_gaps_or_overlaps():
    fe = FieldExtractor()
    merged_path = "/tmp/test_boundaries_coverage.pdf"
    _merge_fixtures("retail_lease.pdf", "office_lease.pdf", "sample_lease_commercial.pdf", "casual_sublease.pdf", out_path=merged_path)
    try:
        pages = _extract_pages(merged_path)
        boundaries = fe.detect_lease_boundaries(pages)
        assert len(boundaries) == 4, boundaries

        assert boundaries[0][0] == pages[0]["page"], "first range must start at the document's actual first page"
        assert boundaries[-1][1] == pages[-1]["page"], "last range must end at the document's actual last page"
        for i in range(len(boundaries) - 1):
            assert boundaries[i][1] + 1 == boundaries[i + 1][0], f"gap or overlap between {boundaries[i]} and {boundaries[i+1]}"
        for start, end in boundaries:
            assert start <= end
    finally:
        os.unlink(merged_path)
    print("✓ test_boundaries_cover_whole_document_with_no_gaps_or_overlaps: PASS")


def test_boundaries_empty_document_returns_empty_list():
    fe = FieldExtractor()
    assert fe.detect_lease_boundaries([]) == []
    print("✓ test_boundaries_empty_document_returns_empty_list: PASS")


# ------------------------------------------------------------------
# extract_multiple_leases() — the actual per-lease field/date accuracy
# ------------------------------------------------------------------

def _ground_truth_fields(filename):
    pages = _extract_pages(os.path.join(FIXTURES_DIR, filename))
    return FieldExtractor().extract_fields(pages)


def test_split_leases_have_field_accuracy_matching_standalone_extraction():
    """
    The core correctness requirement: every field of every split-out
    lease must EXACTLY match what extracting that same fixture on its
    own (never merged with anything) produces — not approximately, not
    "close enough". This is what "not mixed with any other lease in the
    file" concretely means. Checked across four different real merge
    combinations, including a 4-way merge.
    """
    fe = FieldExtractor()
    combos = [
        ("retail_lease.pdf", "office_lease.pdf"),
        ("sample_lease.pdf", "casual_sublease.pdf"),
        ("retail_lease.pdf", "office_lease.pdf", "sample_lease_commercial.pdf"),
        ("tenant_friendly_terms.pdf", "underpriced_downtown.pdf", "reversed_dates.pdf", "inconsistent_escalation.pdf"),
    ]
    check_fields = ["tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date", "property_address"]

    for combo in combos:
        merged_path = f"/tmp/test_split_accuracy_{len(combo)}.pdf"
        _merge_fixtures(*combo, out_path=merged_path)
        try:
            pages = _extract_pages(merged_path)
            results = fe.extract_multiple_leases(pages)
            assert len(results) == len(combo), f"{combo}: expected {len(combo)} leases, got {len(results)}"

            for filename, result in zip(combo, results):
                truth = _ground_truth_fields(filename)
                for key in check_fields:
                    got = result["fields"][key]["value"]
                    expected = truth[key]["value"]
                    assert got == expected, f"{'+'.join(combo)} / {filename} / {key}: got {got!r}, expected {expected!r}"
        finally:
            os.unlink(merged_path)

    print(f"✓ test_split_leases_have_field_accuracy_matching_standalone_extraction: PASS ({len(combos)} merge combinations)")


def test_split_leases_have_their_own_date_candidates_not_the_whole_documents():
    """
    Directly reproduces and confirms the fix for the reported symptom:
    a merged PDF's risk analysis showed a "high risk" flag listing 30+
    different start dates, because date_candidates were being collected
    from the WHOLE merged document instead of kept separate per lease.
    Each split lease's date_candidates must contain only dates from its
    own page range.
    """
    fe = FieldExtractor()
    combo = ("tenant_friendly_terms.pdf", "underpriced_downtown.pdf", "reversed_dates.pdf", "inconsistent_escalation.pdf", "retail_lease.pdf")
    merged_path = "/tmp/test_split_date_candidates.pdf"
    _merge_fixtures(*combo, out_path=merged_path)
    try:
        pages = _extract_pages(merged_path)

        whole_doc_start_dates = {c["value"] for c in fe.find_all_date_candidates(pages, "start")}
        assert len(whole_doc_start_dates) >= 5, "sanity check: the merged doc really does have several different start dates smeared across it"

        results = fe.extract_multiple_leases(pages)
        assert len(results) == 5

        for filename, result in zip(combo, results):
            own_starts = {c["value"] for c in result["date_candidates"]["start"]}
            # This lease's split-out date_candidates must be a subset of
            # what extracting it standalone (never merged with anything)
            # finds — anything beyond that would mean a date leaked in
            # from a different constituent lease's pages.
            standalone_pages = _extract_pages(os.path.join(FIXTURES_DIR, filename))
            standalone_starts = {c["value"] for c in fe.find_all_date_candidates(standalone_pages, "start")}
            assert own_starts <= standalone_starts, (
                f"{filename}: split date_candidates {own_starts} contains a date not found when "
                f"extracting {filename} standalone ({standalone_starts}) — dates bled in from another lease"
            )

    finally:
        os.unlink(merged_path)
    print("✓ test_split_leases_have_their_own_date_candidates_not_the_whole_documents: PASS")


if __name__ == "__main__":
    test_no_false_positives_on_any_real_single_lease_fixture()
    test_detects_two_merged_leases()
    test_detects_three_merged_leases()
    test_detects_merge_of_casual_style_leases()
    test_extract_fields_still_works_normally_on_single_leases()
    test_dedupe_merges_same_entity_with_and_without_suffix()
    test_dedupe_keeps_genuinely_different_names_distinct()
    test_boundaries_single_range_for_every_real_single_lease_fixture()
    test_boundaries_cover_whole_document_with_no_gaps_or_overlaps()
    test_boundaries_empty_document_returns_empty_list()
    test_split_leases_have_field_accuracy_matching_standalone_extraction()
    test_split_leases_have_their_own_date_candidates_not_the_whole_documents()
    print("\nAll multi-lease detection tests passed.")
