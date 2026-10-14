# Plan: `feature/s8-demo-files` (Retroactive)

## What This Branch Is

Data-only branch: a **fictional PBRA (Project-Based Section 8) demo property** called "Oak Hollow Apartments" with 10 tenant-file PDFs, rent roll CSV/XLSX, and 10 planted compliance errors for demoing the product's lease-review and rent-roll-validation features.

**Branch is NOT to be merged yet** — it is a living fixture maintained by the generator script, used for QA, internal demos, and to-be-announced beta features.

## Contents

- **`backend/benchmark_data/s8_demo/`:**
  - `tenant_files/`: 10 PDF tenant files (each with intentional errors planted)
  - `rent_roll/`: Oak Hollow's 40-unit rent roll (CSV + XLSX)
  - `expected_findings.json`: machine-readable answer key (pages, dollars, rule citations)
  - `generate_s8_demo.py`: source of truth for all outputs; regenerating yields byte-identical results (except .xlsx save timestamp)
  - `README.md`: description of the property, the 10 errors (E1–E10), and rules applied

- **`backend/tests/test_s8_demo_files.py`:** regression test for the fixture (validates JSON totals, PDF pages, clean units)

- **`docs/plans/feature-s8-demo-files.md`:** this plan (retroactive documentation)

## Recent Fixes (2026-10-13)

Following user review, the following corrections were made to citations, rule claims, and dollar-impact descriptions:

1. **E1:** Marked HAP $ as "exposure" (not recovery); marked Ch. 7 cite as "chapter-level, paragraph unverified"
2. **E3:** Removed `docs/research/section8.md` citation; marked 120-day window start-point as unverified
3. **E4:** Removed "most common MOR finding" claim; marked Ch. 9 as "chapter-level, paragraph unverified"
4. **E5:** Added note that $480 dependent deduction is pre-HOTMA; post-HOTMA differs
5. **E6:** Softened "must send" to "Handbook directs (cadence unverified)"; marked HAP $ as "exposure, not recoverable in normal case"
6. **E7 & E10:** Clarified both use "current HAP for every month" so dollar methods are consistent
7. **E8:** Reordered citation to make household-composition rule the stated basis (Ch. 3, chapter-level, paragraph unverified); noted 24 CFR 5.216 is SSN disclosure (supporting). Fixed stray ")..  typo
8. **E9:** Relabeled "confirmed per rent roll" and noted no tenant ledger on file
9. **E10:** Changed "full-time student" to "enrolled at institution"; noted disability exception is narrower (as of 11/30/2005); marked rule "simplified; confirm"
10. **README:** Enhanced final caveat to explicitly state all rule statements are NOT practitioner-checked; added PII warning that these files contain full (fictional, 000-range) SSNs and must NOT be uploaded until `feature/s8-pii-guard` is merged

## Standing Rules Applicable

- PII: These files contain full (fictional) SSNs in 000-range and sensitive income/asset documents. **Do NOT upload to any deployment until the PII guard feature (`feature/s8-pii-guard`) is merged.** See README warning.

- Generator is source of truth: if you need to change any outputs, edit `generate_s8_demo.py` and regenerate; never hand-edit PDFs or JSON.

- Byte-for-byte reproducibility: regenerating with no code changes yields identical outputs (PDFs, CSV, JSON), except .xlsx which has an openpyxl timestamp.

## Out of Scope / Not Done

- Redacting the PDFs to remove SSNs (a user decision; mention as an option in handoff if needed).
- Merging the branch into `main` (will happen only after PII guard is live and user decision is made).

## Success Criteria

- [x] Citations/claims in README and JSON corrected per user review
- [x] PII warning added prominently to README
- [x] Test file `test_s8_demo_files.py` created, validates totals and PDF pages
- [x] Test registered in `run_all_tests.py`
- [x] All tests pass (including the new test with intentionally broken totals then reverted)
- [x] No secrets, real SSNs, or redacted PDFs in the diff
