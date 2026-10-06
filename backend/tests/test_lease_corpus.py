"""
Accuracy floor on the synthetic multifamily / Section 8 lease corpus
(tools/lease_corpus/): regenerate it into a temp dir, run the real
upload extraction helper on every file (OCR included, regex engine,
LEASE_MULTIFAMILY_FIELDS on), and fail if accuracy drops.

The floors sit a little under the current score so a real regression
fails loudly while an unrelated tweak doesn't flap. When a fix raises
the score, raise the floor with it (LEASE_EXTRACTION_REPORT.md tracks
the history).
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(BACKEND, "tools", "lease_corpus"))
sys.path.insert(0, BACKEND)
os.environ["LEASE_EXTRACTION_ENGINE"] = "regex"
os.environ["LEASE_MULTIFAMILY_FIELDS"] = "1"

import generate  # noqa: E402
import run_corpus  # noqa: E402

OVERALL_FLOOR = 97.0
# Fields a deal can't be checked without: any miss here is a regression.
MUST_BE_PERFECT = ("lease_count", "processed", "tenant", "rent_amount", "lease_start_date", "lease_end_date")


def test_corpus_accuracy_floor():
    has_ocr = shutil.which("tesseract") and shutil.which("pdftoppm")
    out = tempfile.mkdtemp(prefix="lease_corpus_test_")
    try:
        manifest = generate.generate(out)
        if not has_ocr:
            # Scanned cases need tesseract/poppler (a known local-only
            # dependency, see CLAUDE.md rule 13) -- grade the rest.
            manifest["cases"] = [c for c in manifest["cases"] if not c["scanned"]]
            import json
            with open(os.path.join(out, "manifest.json"), "w") as fh:
                json.dump(manifest, fh, default=str)
        s = run_corpus.run(out)
    finally:
        shutil.rmtree(out, ignore_errors=True)
    run_corpus.print_summary({**s, "high_confidence_wrong": s["high_confidence_wrong"][:10]})
    assert s["overall_pct"] >= OVERALL_FLOOR, s["overall_pct"]
    for check in MUST_BE_PERFECT:
        assert s["by_check"][check]["pct"] == 100.0, (check, s["by_check"][check])
    assert not s["high_confidence_wrong"], s["high_confidence_wrong"]
    print(f"✓ Lease corpus: {s['overall_pct']}% of {s['checks_total']} checks (floor {OVERALL_FLOOR}%), "
          f"core fields 100%, no high-confidence wrong values: PASS")


if __name__ == "__main__":
    test_corpus_accuracy_floor()
