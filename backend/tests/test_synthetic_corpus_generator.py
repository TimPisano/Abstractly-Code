"""
Tests that tests/generate_synthetic_corpus.py produces a usable,
ground-truthed corpus: the manifest is well-formed, every listed file
exists, generation is deterministic for a fixed seed, and the
documents it produces actually flow through the real extraction /
rent-roll-import pipeline (not just "a file was written").
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from generate_synthetic_corpus import generate_corpus
from app import document_extractor
from app.field_extractor import FieldExtractor
from app.rent_roll_import import parse_csv_rent_roll, parse_xlsx_rent_roll


def _gen(tmp, **kw):
    return generate_corpus(tmp, n_leases=kw.get("n_leases", 8), n_garbage=kw.get("n_garbage", 5),
                           n_rent_rolls=kw.get("n_rent_rolls", 5), seed=kw.get("seed", 7))


def test_manifest_well_formed_and_every_file_exists():
    with tempfile.TemporaryDirectory() as tmp:
        m = _gen(tmp)
        assert os.path.exists(os.path.join(tmp, "manifest.json"))
        assert len(m["leases"]) == 8 and len(m["garbage"]) == 5 and len(m["rent_rolls"]) == 5
        for group in ("leases", "rent_rolls", "garbage"):
            for entry in m[group]:
                assert os.path.exists(os.path.join(tmp, entry["file"])), entry["file"]
        for L in m["leases"]:
            gt = L["ground_truth"]
            assert set(gt) >= {"tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date"}
            assert gt["tenant"] and gt["rent_amount"].startswith("$")
    print("✓ test_manifest_well_formed_and_every_file_exists: PASS")


def test_generation_is_deterministic_for_a_seed():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        ma = _gen(a, seed=42)
        mb = _gen(b, seed=42)
        assert [l["ground_truth"] for l in ma["leases"]] == [l["ground_truth"] for l in mb["leases"]]
        mc = _gen(b, seed=43)
        assert [l["ground_truth"] for l in ma["leases"]] != [l["ground_truth"] for l in mc["leases"]]
    print("✓ test_generation_is_deterministic_for_a_seed: PASS")


def test_generated_leases_flow_through_the_real_extraction_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        m = _gen(tmp, n_leases=12)
        fe = FieldExtractor()
        extracted_any_tenant = 0
        for L in m["leases"]:
            path = os.path.join(tmp, L["file"])
            with open(path, "rb") as f:
                pages = document_extractor.extract_pages(f.read(), L["file"], path)
            assert pages and pages[0]["text"].strip()
            fields = fe.extract_fields(pages)
            # ground truth tenant core (before the entity suffix) should appear in the doc text
            core = L["ground_truth"]["tenant"].split(",")[0]
            assert core in " ".join(p["text"] for p in pages), f"{L['file']} missing its own tenant in body"
            if fields["tenant"]["value"]:
                extracted_any_tenant += 1
        assert extracted_any_tenant >= 6, "the regex engine should still get tenant on most clean synthetic leases"
    print("✓ test_generated_leases_flow_through_the_real_extraction_pipeline: PASS")


def test_generated_rent_rolls_import_and_carry_ground_truth_links():
    with tempfile.TemporaryDirectory() as tmp:
        m = _gen(tmp)
        imported_any = False
        for rr in m["rent_rolls"]:
            path = os.path.join(tmp, rr["file"])
            with open(path, "rb") as f:
                data = f.read()
            parsed = parse_xlsx_rent_roll(data, rr["file"]) if rr["file"].endswith(".xlsx") else parse_csv_rent_roll(data, rr["file"])
            if parsed["leases"]:
                imported_any = True
            for row_gt in rr["ground_truth"]["rows"]:
                assert row_gt["lease_id"].startswith("lease_")
                assert row_gt["rent_roll_rent_monthly"] > 0
                # an injected disagreement, when present, is a real field name
                if row_gt["injected_disagreement"]:
                    assert row_gt["injected_disagreement"]["field"] in ("rent_amount", "lease_end_date", "tenant")
        assert imported_any, "at least one synthetic rent roll must import cleanly"
    print("✓ test_generated_rent_rolls_import_and_carry_ground_truth_links: PASS")


def test_garbage_files_are_rejected_by_the_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        m = _gen(tmp)
        rejected = 0
        for g in m["garbage"]:
            path = os.path.join(tmp, g["file"])
            with open(path, "rb") as f:
                data = f.read()
            try:
                pages = document_extractor.extract_pages(data, g["file"], path)
                # a memo/invoice extracts text fine but must not look like a lease
                fe = FieldExtractor()
                fields = fe.extract_fields(pages)
                identity = [fields[k]["value"] for k in ("tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date")]
                if not any(identity):
                    rejected += 1
            except document_extractor.DocumentExtractionError:
                rejected += 1
        assert rejected >= 3, f"most garbage files should be rejected or read as non-leases, got {rejected}/5"
    print("✓ test_garbage_files_are_rejected_by_the_pipeline: PASS")


if __name__ == "__main__":
    test_manifest_well_formed_and_every_file_exists()
    test_generation_is_deterministic_for_a_seed()
    test_generated_leases_flow_through_the_real_extraction_pipeline()
    test_generated_rent_rolls_import_and_carry_ground_truth_links()
    test_garbage_files_are_rejected_by_the_pipeline()
    print("\nAll synthetic corpus generator tests passed.")
