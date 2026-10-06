"""
Accuracy floors on the three synthetic multifamily / Section 8 lease
corpora (tools/lease_corpus/): regenerate each into a temp dir, run the
real upload extraction helper on every file (OCR included, regex engine,
LEASE_MULTIFAMILY_FIELDS on), and fail if accuracy drops.

  generate.py  -- the corpus the parser was developed against
  holdout.py   -- independently written; tuned against after its first run
  holdout2.py  -- independently written blind set; 87.6% before any tuning

The floors sit a little under the current scores so a real regression
fails loudly while an unrelated tweak doesn't flap. When a fix raises a
score, raise its floor with it (LEASE_EXTRACTION_REPORT.md tracks the
history). A confidently wrong value ("high" confidence, wrong answer) is
never allowed on any corpus.
"""

import json
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
import holdout  # noqa: E402
import holdout2  # noqa: E402
import run_corpus  # noqa: E402

# Fields a deal can't be checked without: any miss on the own corpus is a regression.
MUST_BE_PERFECT = ("lease_count", "processed", "tenant", "rent_amount", "lease_start_date", "lease_end_date")

CORPORA = [
    # (name, generator, overall floor, checks that must be 100%)
    ("own", lambda out: generate.generate(out), 99.0, MUST_BE_PERFECT),
    ("holdout", lambda out: holdout.generate(out), 98.0, ("lease_count", "processed", "tenant", "rent_amount")),
    ("holdout2", lambda out: holdout2.generate(out), 94.0, ("processed",)),
]


def _run(name, gen):
    has_ocr = shutil.which("tesseract") and shutil.which("pdftoppm")
    out = tempfile.mkdtemp(prefix=f"lease_corpus_{name}_")
    try:
        gen(out)
        if not has_ocr:
            # Scanned cases need tesseract/poppler (a known local-only
            # dependency, see CLAUDE.md rule 13) -- grade the rest.
            path = os.path.join(out, "manifest.json")
            with open(path) as fh:
                manifest = json.load(fh)
            manifest["cases"] = [c for c in manifest["cases"] if not c["scanned"]]
            with open(path, "w") as fh:
                json.dump(manifest, fh, default=str)
        return run_corpus.run(out)
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_corpus_accuracy_floors():
    for name, gen, floor, perfect in CORPORA:
        s = _run(name, gen)
        assert s["overall_pct"] >= floor, (name, s["overall_pct"], floor)
        for check in perfect:
            assert s["by_check"][check]["pct"] == 100.0, (name, check, s["by_check"][check])
        assert not s["high_confidence_wrong"], (name, s["high_confidence_wrong"])
        print(f"✓ Lease corpus '{name}': {s['overall_pct']}% of {s['checks_total']} checks (floor {floor}%), "
              f"no high-confidence wrong values: PASS")


if __name__ == "__main__":
    test_corpus_accuracy_floors()
