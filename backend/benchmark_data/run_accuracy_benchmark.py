"""
Accuracy benchmark: the 12 real EDGAR sample leases (benchmark_data/leases/)
run through the REAL extraction pipeline -- the same document_extractor
front door an upload uses, then whichever engine resolve_engine() picks:

  - AI engine   when LEASE_AI_EXTRACTION=true AND a funded ANTHROPIC_API_KEY
                is set (this is the engine the homepage claim is about)
  - regex       otherwise (fallback; NOT the product claim -- do not
                publish a number from this path)

Scored field-by-field against benchmark_data/ground_truth.json using
app/extraction_scoring.py.

IMPORTANT -- read before quoting any number:
  extraction_scoring.values_match() uses substring/parse matching for the
  free-text fields (property_address, permitted_use, exclusivity_clause,
  insurance_requirements, default_cure_period). The ground-truth values in
  ground_truth.json are full, human-verified descriptions, so a
  semantically-correct extraction phrased differently can auto-score as
  WRONG. This script therefore prints the full expected-vs-extracted text
  for EVERY field. The headline accuracy number is the one you get AFTER
  reviewing that table and correcting auto-scoring artifacts -- record
  both (raw auto-score and reviewed) in BENCHMARK_AND_PRIVACY_AUDIT.md.

Run (AI engine):
  LEASE_AI_EXTRACTION=true PYTHONPATH=. venv/bin/python benchmark_data/run_accuracy_benchmark.py
Run (regex, offline sanity only):
  LEASE_EXTRACTION_ENGINE=regex PYTHONPATH=. venv/bin/python benchmark_data/run_accuracy_benchmark.py

Add --dump to also write benchmark_data/last_run.json (full extracted
fields + per-field scores) for the manual review pass.
"""

import json
import os
import sys
import time

from app import document_extractor, extraction_scoring, ai_extraction
from app.ai_extraction import resolve_engine
from app.field_extractor import FieldExtractor

HERE = os.path.dirname(os.path.abspath(__file__))

LEASE_FIELDS = [
    "tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date",
    "property_address", "security_deposit", "cam_charges", "rent_escalation",
    "renewal_options", "permitted_use", "exclusivity_clause",
    "insurance_requirements", "default_cure_period", "square_footage",
]


def extract_one(path, filename, engine):
    pages = document_extractor.extract_pages(open(path, "rb").read(), filename, path)
    t0 = time.perf_counter()
    if engine == "ai":
        fields = ai_extraction.extract_lease_fields(pages)
        fields.pop("_ai_meta", None)
    else:
        fields = FieldExtractor().extract_fields(pages, source_label=filename)
    elapsed = time.perf_counter() - t0
    return fields, elapsed, len(pages)


def main():
    dump = "--dump" in sys.argv
    manifest = json.load(open(os.path.join(HERE, "ground_truth.json")))["leases"]
    engine = resolve_engine()
    n = len(manifest)
    print(f"engine = {engine}   n = {n} leases")
    if engine != "ai":
        print("WARNING: not the AI engine -- this number must NOT go on the site.\n")
    else:
        print()

    doc_scores, timings, dump_rows = [], [], []
    for entry in manifest:
        path = os.path.join(HERE, "leases", entry["file"])
        try:
            fields, elapsed, npages = extract_one(path, entry["file"], engine)
        except ai_extraction.AIExtractionError as e:
            print(f"  !! {entry['id']}: AI extraction failed: {e}")
            continue
        timings.append((entry["id"], npages, elapsed))
        ds = extraction_scoring.score_document(
            fields, entry["ground_truth"], doc_meta={"id": entry["id"], "format": "pdf"})
        doc_scores.append(ds)
        dump_rows.append({"id": entry["id"], "extracted": fields, "scores": ds["field_scores"]})

    agg = extraction_scoring.aggregate(doc_scores)
    fa = {r["field"]: r for r in agg["field_accuracy"]}

    print("=== FULL EXPECTED vs EXTRACTED (review before quoting a number) ===")
    for row in dump_rows:
        print(f"\n--- {row['id']} ---")
        for s in row["scores"]:
            mark = {"correct_found": "OK", "correct_absent": "OK/absent", "wrong": "WRONG",
                    "missed": "MISS", "spurious": "SPURIOUS"}[s["kind"]]
            print(f"  [{mark:9}] {s['field']}")
            print(f"      expected : {s['expected']}")
            print(f"      extracted: {s['extracted']}  (conf={s['confidence']})")

    print("\n=== PER-FIELD ACCURACY (auto-score, n=%d each) ===" % n)
    for field in LEASE_FIELDS:
        acc = fa.get(field, {}).get("accuracy")
        print(f"  {field:24s} {acc*100:5.1f}%" if acc is not None else f"  {field:24s}   n/a")

    print("\n=== OVERALL (auto-score) ===")
    print(f"  overall field accuracy: {agg['overall_accuracy']*100:.1f}%  "
          f"over {agg['fields_evaluated']} (lease, field) pairs, n={n} leases")
    print(f"  asserted values wrong:  {agg['asserted_wrong']} / {agg['asserted_values']}")
    print(f"  high-confidence AND wrong: {agg['high_conf_wrong_count']}")
    for it in agg["high_conf_wrong"]:
        print(f"    - {it['doc']} {it['field']}: got {it['extracted']!r} vs {it['expected']!r}")
    cal = agg["calibration"]
    print(f"  calibration: P(correct|high)={cal['p_correct_given_high']} (n={cal['n_high']}), "
          f"P(correct|low)={cal['p_correct_given_low']} (n={cal['n_low']})")

    print(f"\n=== TIMING (extraction call only, {engine} engine) ===")
    if timings:
        total = sum(t[2] for t in timings)
        for lid, npages, el in timings:
            print(f"  {lid:36s} {npages:3d}pp  {el*1000:8.1f} ms")
        print(f"  mean {total/len(timings)*1000:.1f} ms/lease over {len(timings)} leases "
              f"(end-to-end upload timing is measured separately)")

    if dump:
        json.dump(dump_rows, open(os.path.join(HERE, "last_run.json"), "w"), indent=2, default=str)
        print("\nwrote benchmark_data/last_run.json")


if __name__ == "__main__":
    main()
