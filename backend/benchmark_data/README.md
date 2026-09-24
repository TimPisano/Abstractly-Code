# benchmark_data/

Corpus and tooling for the homepage accuracy / speed claim review and the
customer demo. See `../../BENCHMARK_AND_PRIVACY_AUDIT.md` for the full
write-up.

## Contents

| Path | What |
|---|---|
| `leases/*.pdf` | **12 real commercial leases** filed publicly with the SEC (EDGAR). Provenance + selection criteria in `SOURCES.md`. |
| `leases_txt/*.txt` | Plain-text extraction of each lease, for reference. |
| `raw/*` | Original EDGAR bytes + intermediate render HTML. |
| `ground_truth.json` / `.csv` | 15-field answer key per lease, recorded **by hand from the source documents** (nothing guessed). See the file's `_meta`. |
| `SOURCES.md` | Where each lease came from (filer, CIK, EDGAR URL) and why it was selected. |
| `run_accuracy_benchmark.py` | Runs the 12 leases through the real pipeline, scores vs. ground truth, prints a full expected-vs-extracted table + per-field/overall accuracy + timing. |
| `load_demo_and_verify.py` | End-to-end check against an isolated temp DB: extract -> import rent rolls -> reconcile. |
| `archive/` | The earlier synthetic-lease attempt (10 machine-authored fictional leases + its ground truth + a homepage-changes draft). **Retired** -- superseded by the real EDGAR corpus. Kept for reference, not used by any current script. |

## Status

- **Corpus + ground truth: complete** (2026-09-09). 12 real leases, all
  clean single unamended documents, all 15 fields human-verified. n=12,
  180 (lease, field) pairs.
- **Accuracy benchmark: NOT YET RUN.** It is gated on a funded
  `ANTHROPIC_API_KEY` -- per the decision on file, the number must be
  measured on the **AI engine** (the engine real testers/customers use
  this week), not the regex fallback. Do not publish a regex number.
- **Speed benchmark: not yet run** (same gate + a manual timed pass).
- **Privacy audit: complete** -- see `../../BENCHMARK_AND_PRIVACY_AUDIT.md`.

## Reproduce (once the key is funded)

```
cd backend
LEASE_AI_EXTRACTION=true PYTHONPATH=. venv/bin/python benchmark_data/run_accuracy_benchmark.py --dump
```

Then review `last_run.json` / the printed expected-vs-extracted table and
record BOTH the raw auto-score and the human-reviewed accuracy in
`BENCHMARK_AND_PRIVACY_AUDIT.md`. The auto-scorer substring-matches the
free-text fields, so a correct answer phrased differently can score WRONG
-- the reviewed number is the one that can be quoted.

The scripts never touch the dev DB (`load_demo_and_verify.py` uses a
throwaway temp file via `database.configure()`).
