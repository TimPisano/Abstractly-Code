# feature/affordable-accuracy-2

## Goal

Read Section 8, LIHTC and Section 811 documents as close to 100% right as
the documents allow, starting with the scanned copies, which are where the
reader is weakest. The reader stays behind `AFFORDABLE_FORMS_MODE` (off
everywhere) and is not wired into uploads. Done = every scanned-copy fix
lands with a regression test, the scores are re-measured on every variant
after each fix, and the measurement copies were never used to tune.

## Base

Stacked on `feature/affordable-real-accuracy` `61119ce` (reviewed MERGE,
not merged yet), because that branch holds all the current reader work.
Merge order: affordable-real-accuracy, then the reorganization
(`feature/product-mode` / `refactor/organize`), then this branch after
updating it from main.

## Prior art

Searched TASKS.md and every branch's log for `affordable-accuracy`,
`holdout_scan` and "scanned holdout". Only the two earlier affordable
branches touch this work (`feature/affordable-forms`, merged as
`f715a25`; `feature/affordable-real-accuracy`, which this branch builds
on). No parallel version exists.

`feature/product-mode` plans to move `ai_extraction` into `app/shared/ai/`,
the only app module the reader imports (`ai_fields.py`). Its plan lists
every `feature/affordable-*` branch as "don't touch", so the two shouldn't
collide beyond that one import line.

## Where the points are lost (synthetic set, latest run `affordable_totalflag.json`)

| Variant | Program fields right |
|---|---|
| holdout (typed, moved, other fonts) | 303 / 339 (89.4%) |
| holdout_scan (same, then scanned) | 243 / 339 (71.7%) |

Of the 96 scanned misses:

- **13 are dates of birth.** The reader skips DOB and SSN fields on purpose
  (`pii.py`), so they miss on the typed copies too. That's a scoring
  question, not a reading problem (open question 1).
- **73 are values the typed holdout gets right and the scan loses.** In 60
  of those 73, the value is in the scanned page's OCR text, so the reader
  fails to find or parse it. In the other 13, OCR lost it.
- **By document**, the scan losses are: HUD-50059 15, the Louisiana TIC 10, the
  Illinois TIC 9, HUD-52530A 6, the South Carolina TIC 6, HUD-52641 6,
  HUD-52697 4, the NJ TIC 4, IRS 8609 4, IRS 8823 4, the Colorado LURA 3,
  and others 2 or fewer.

The 11 real documents are at 163 / 165. The two misses are cells the
document's own OCR misread. They're flagged and left as read, by Tim's
rule. That set has no free headroom.

## Approach

1. **Dev copies to tune on (free).** `make_holdout.py` itself says not to
   tune against the holdout. So I'll generate a third copy of each sample
   with a new seed (`dev`): values moved, other fonts and formats, then
   scanned the same way. Diagnosis and tuning use `scan` and `dev_scan`.
   `holdout` and `holdout_scan` are only measured, never looked at
   document by document. At the end I'll generate one more fresh seed and
   measure it, to check the fixes generalise rather than fit.
2. **Weakest first, by the 60 "OCR has it, reader misses it" losses.**
   One commit per cause, each with a regression test that fails without
   it. Likely causes, to be confirmed on the dev copies:
   - OCR-garbled labels that anchors don't match. Tolerant matching for
     anchors only (normalised text, a small edit distance, unique best
     match) on OCR pages.
   - Value boxes that miss on skewed or shifted text. Measure the offset
     between where a label's words are and where the form says they are,
     then shift that label's boxes.
   - OCR character swaps inside number and date fields only (`O`→`0`,
     `l`/`I`→`1`, `S`→`5`), with the field marked low confidence when a
     swap was needed.
   - HUD-50059 first (15 losses), then the TICs, then HUD-52530A and
     HUD-52641.
3. **The 13 values OCR lost.** Try the existing 400 DPI value-box read on
   these boxes, and a box-only re-read when an anchor is found but its box
   is empty. Stop if it doesn't help, as with fix 3 last time.
4. **Section 811 coverage (free).** The synthetic set has no 811 document.
   Add a synthetic sample for HUD-92236-PRA, the 811 PRA lease (a public
   blank HUD form), with fictional values and its clean, holdout and scan
   copies, so the 811 reader is measured at all.
5. **Paid work only if a free fix can't reach it.** The Colorado LURA is
   the weakest typed document (5 / 14 on the scan) and goes to the AI
   reader. Any call gets a cost estimate first. Total spend over $1 needs
   Tim's OK; the response cache stays on.
6. **After each fix:** run the full suite, then rescore clean, acroform,
   scan, holdout, holdout_scan, dev, dev_scan and the 11 real documents
   (from the cache, $0). Report a before/after table.

## Files to change

- `backend/app/affordable/**` (the reader: `extract.py`, `layout.py`,
  `values.py`, `forms/*.py`, `checks.py`, `ocr_check.py`).
- Tests: existing `backend/tests/test_affordable_*.py` files. New test cases
  go into these files rather than new files, so `run_all_tests.py` (a
  shared file the reorganization edits) isn't touched.
- Eval harness: `tests/eval/affordable/**` (`make_holdout.py` seed option,
  `make_scans.py`, `run_eval.py` variants, a new 811 spec, samples and
  results) and `tests/eval/real/**` results.
- `docs/research/eval-baseline.md`, this plan.

## Files not to touch

- `api.py`, routes, `app/config.py`, `app/__init__.py`, `field_extractor.py`,
  `ai_extraction.py`, `document_extractor.py` and anything else outside
  `backend/app/affordable/`. The reorganization is moving them.
- The `ai_extraction` import line in `ai_fields.py`. The reorganization
  changes it.
- `backend/tests/run_all_tests.py`, `_test_env.py`, `render.yaml`,
  `.env.example`, Dockerfiles, frontend.
- `tests/eval/holdout_public/`. Never opened, listed or read.

## Team isolation & roles

No route, query, table or cache key is added or changed. Nothing is wired
into uploads.

## Feature flag

`AFFORDABLE_FORMS_MODE` stays unset everywhere (default off). Not added
to any config.

## Verification

- One regression test per fix, failing without it, in the existing
  `test_affordable_*.py` files.
- Full suite passes, with the count quoted, after each fix.
- Before/after table per fix: clean, acroform, scan, holdout, holdout_scan,
  dev, dev_scan, 11 real documents.
- Final fresh-seed holdout score next to holdout_scan.

## Out of scope

- Wiring the reader into uploads, and the pre-wiring hardening from the
  reviews (page and size limits, SSN masking in AI prompts, cache limits).
  They belong with the wiring.
- Changing answer keys, except by a decision Tim makes.
- Picking between two OCR readings, or changing a value to make checks
  pass.

## Open questions

1. **DOB fields (13 misses, about 3.8 points on every variant).** The
   reader skips dates of birth on purpose. Should the eval score them as
   "not read by design" (left out of the total and listed separately, like
   the null fields), or keep counting them as misses? The default keeps
   counting them. That's conservative, but caps the program score near
   96%.
2. **Dev copies.** Is it OK to tune on a new `dev` seed and keep `holdout` /
   `holdout_scan` for measurement only? The default is yes.
3. **811 synthetic sample.** OK to add one? The default is yes, with
   fictional values only.
