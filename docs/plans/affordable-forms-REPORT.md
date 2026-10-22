# Report: `feature/affordable-forms`, the non-AI extraction fixes

**Date:** 2026-10-19 (overnight, unattended) · **Branch:** `feature/affordable-forms`, not pushed · **Plan:** [affordable-extraction-plan.md](./affordable-extraction-plan.md) · **Scores:** [eval-baseline.md](../research/eval-baseline.md), last section

## Headline

Today's extractor reads **0%** of the lease fields on filled HUD and LIHTC forms. The new module reads:

- **94%** on flattened forms, both the dev copies and a holdout set it was never tuned on;
- **92%** on fillable forms saved without flattening;
- **88%** on scans of the dev copies, and **56–58%** on scans of the holdout copies (the weak spot).

It also reads the affordable-specific fields today's engine has no place for: HAP, TTP, tenant rent, AMI limits, household, contract and BIN numbers. Those score **89–95%** on digital copies.

When the module is wrong it says "medium" confidence, never "high". It invented nothing in 73 runs. Today's engine produced 46 wrong or invented values, all marked "high".

## What was built

All new code is in **`backend/app/affordable/`**: 16 files, about 2,000 lines. **No existing app file was changed.** That includes `ai_extraction.py`, `api.py`, `document_extractor.py` and the rest of the upload pipeline. `git diff --name-status main...HEAD -- backend` shows only added files. Nothing calls the module yet. It's behind `AFFORDABLE_FORMS_MODE` (default off) for whoever wires it in.

| File | What it does | Plan step |
|---|---|---|
| `acroform.py` | Reads values typed into a PDF's fillable fields, which today's text extraction never sees. Skips SSN fields; masks SSN-shaped values, except bare 9-digit numbers in ID fields (REMS, contract) | Step 2 |
| `layout.py` | Words with positions from the text layer, or from Tesseract on scanned pages. Rebuilds reading-order page text. Ignores underscore and space glyphs that split typed-in values. Re-OCRs a single box when whole-page OCR drops a short value | Layout-aware text |
| `values.py` | Typed parsing: money with or without `$` (fixes the `parse_currency` gap), the common date formats, integers, percents. Rejects form labels, headings and lone dates as values | Steps 1 and 6 |
| `forms/*.py` | **13 form mappings**, written from the blank forms: RFTA 52517; HAP contract 52641 (two PHA re-saves); PBV 52530A and 52530B; 50059; 52670; 52697; the SC/LA/NJ TIC template; the Illinois TIC; IRS 8609, 8823 and 8586; CHFA LURA (partial) | Step 5, template route |
| `extract.py` | Recognises the form, reads it as **one** document (no splitting, no rent-roll gate), and returns program fields plus the 15 lease fields in the shape the app already uses | Steps 4–5 |
| `pii.py`, `config.py` | Tenant-data guards; the feature flag | |

Labels are found by phrase, tolerant of squashed spacing, OCR typos and scan skew. Each value is read from a box positioned relative to its label, or straight from the fillable field when the PDF still has one.

## Before and after, by fix

Lease-field recall / program-field accuracy, 16 forms per variant. Measured with `tests/eval/affordable/run_eval.py`, one engine per fix:

| Engine | clean | unflattened | scan | holdout | holdout scan |
|---|---|---|---|---|---|
| Today (`regex`) | 0% / 0% | 0% / 0% | 10% / 0% | 0% / 0% | 6% / 0% |
| + read fillable fields | 0% / 0% | 8% / 0% | 10% / 0% | 0% / 0% | 6% / 0% |
| + layout-aware text | 10% / 0% | 8% / 0% | 13% / 0% | 10% / 0% | 6% / 0% |
| **+ per-form mapping (new module)** | **94% / 92%** | **92% / 95%** | **88% / 85%** | **94% / 89%** | **56% / 58%** |

**Reading the table:**
- **Read fillable fields:** on unflattened forms, the values the extractor can see go from 21% to 98–100%. The regex extractor still can't use them, because it doesn't read forms.
- **Layout-aware text:** puts each value next to its label, but the regex extractor only reaches 10%. That confirms the baseline finding: the regex patterns, not text order, were the main problem.
- **Per-form mapping:** the change that moves the score. It holds up on the holdout copies (94% vs 94%), so the mappings aren't fitted to where our samples happened to put values.
- **Program fields:** 13 of the 339 program values are dates of birth, which the module refuses to read. So the most it can score is 96%, and the clean 92% is 95% of that.

## How the measurement was kept honest

- **Mapping rules:** written from the *blank* forms only. A scan for hard-coded sample values found none outside comments.
- **Holdout set:** `make_holdout.py` redraws every value shifted ±2.5 pt, in a different font and size, with dates and amounts reformatted. Mappings were debugged only on the clean, unflattened and scan copies; nobody opened a holdout file while writing them.
- **One change after the holdout run:** I lowered OCR from 300 to 200 dpi, the app's own setting, because the dev scans improved (program 81% → 85%). On the holdout scans it went the other way: lease 58% → 56%, program 63% → 58%, and two TIC scans stopped being recognised. Both numbers are in eval-baseline.md. I didn't tune further against the holdout.
- **Bugs fixed in the eval set itself, both disclosed:**
  - A helper mis-mapped the PBV signature fields.
  - The "Indiana" TIC is Illinois (fixed last pass).

## Tests

- **New:** 5 test files, 33 tests: `backend/tests/test_affordable_forms.py` (core, 14) and `test_affordable_forms_{hap,pbra,irs,tic}.py` (per-family, 19). They cover unsigned money, date formats, the label guard, the SSN/DOB guards and the ID exception, unflattened values (including that pypdf's text really lacks them), reading order, skew-tolerant label chains, underscore blanks, unrecognised documents, and end-to-end reads of each form family.
- **Every commit:** the full suite ran first, **85/85 test files**, plus all 33 new tests.
- **Not registered in `backend/tests/run_all_tests.py`.** That list is shared, and you asked me not to edit existing files tonight. **Follow-up: add the 5 file names to `UNIT_TESTS`** (one line each).

## Engine problems found and fixed along the way

The four helpers that wrote form mappings reported engine limits. Each was fixed in the module and has a regression test where it could:

- Values typed over `____` blanks or space runs came out split ("C ed a r", "1 ,1 6 6"). Those glyphs are now dropped before grouping words.
- A REMS property ID was masked as an SSN. Bare 9-digit numbers in ID fields are now kept; dashed SSN shapes are always masked.
- Labels on skewed scans broke across "lines". Labels are now matched along chains of adjacent words.
- A near-match label beat the exact one. Only the best-scoring matches are kept.
- Short labels matched inside values ("TC" in "TC-26-118"). Short labels now require whole-word matches.
- A date was accepted as a person's name. Text fields now reject a lone date.
- Re-OCR of an empty box returned junk. It now needs Tesseract confidence of 60 or more.
- OCR read "$" as "5". In money fields, "5 76,064" now reads as $76,064.
- Re-OCR crashed on boxes off the page. It now returns nothing.
- Strip rules didn't apply to fillable-field values. They now do, and multi-line fields can take one line.

## What's left, in order

1. **Wire it in** (needs files another session was editing): in the upload path, when `AFFORDABLE_FORMS_MODE` is on and `extract_document()` recognises a form, use its result instead of the lease extractor. Store program fields with the T1 Section 8 data model.
2. **Scans of unfamiliar typing (holdout scans, 56–58%):** fuzzy form detection on OCR pages, and OCR at the scan's native image resolution instead of a fixed dpi.
3. **OCR punctuation noise** in names and addresses ("1450. Maple Ridge Drive"). This causes most of the 11 wrong values.
4. **Register the 5 test files** in `run_all_tests.py`.
5. **AI comparison** once credits are added: `run_eval.py --engine ai`. The module is weakest on the LURA (prose, 7/14) and holdout scans, and that's where AI should be compared.
6. **Real documents.** Everything here is synthetic and typed. Before trusting these numbers, test 3–5 real, anonymized forms from a design partner, and only after `feature/s8-pii-guard` (T0) merges.

**Out of scope for this module, as designed:**
- PBV contract number and project address: no printed field on Part 1.
- Dates of birth: refused until PII masking lands.
- LURA prose fields: the AI route's job.

## Merge notes

- **Base:** this branch is cut from `research/affordable-housing` (`c1517d1`), not `main`, because the eval harness lives there. Merging it brings the research docs and `tests/eval/affordable/` along.
- **Divergence:** `main` has 3 newer commits, all `TASKS.md` updates, which don't overlap with anything here.
- **Commits:** `c3b2df5` (module, tests, harness) and the final commit (OCR resolution, results, eval-baseline, this report).
- **Not pushed.** TASKS.md not edited.

## How to run

```
PY=backend/venv/bin/python     # or the primary checkout's venv
$PY backend/tests/test_affordable_forms.py                       # + _hap, _pbra, _irs, _tic
$PY -I tests/eval/affordable/run_eval.py --engine affordable --variants clean acroform holdout   # ~1 min
$PY -I tests/eval/affordable/make_scans.py && $PY -I tests/eval/affordable/run_eval.py --engine affordable   # with scans, ~15 min
```

```python
from app.affordable import extract_document
res = extract_document(open("tic.pdf", "rb").read())
res["form_id"], res["lease_fields"]["rent_amount"], res["program_fields"]["income_limit"]
```
