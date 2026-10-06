<!-- SUMMARY -->
**Cycle 2: 119 of 132 cases pass (90%), up from 22 of 132 (17%) at the start.** The gauntlet ran 70 messy rent rolls, 33 T-12s and 117 leases through the full local pipeline, graded against a manifest of correct answers.

- **Planted mismatches caught: 257 of 257, every one with the right dollar amount.** At baseline it was 108 of 193, and that denominator was smaller because many files never got past import.
- **False alarms: 15, down from 337.** All 15 come from the *lease extraction* misreading three accented tenant names (for example, it reads "Søren Ågård"'s lease as tenant "Bluebonnet Commons Owner LLC"). Lease extraction belongs to the `feature/lease-intelligence` session, so I logged these and did not fix them.
- **No crashes and no hangs**, down from 1 crash at baseline.
- **Fixes:** 28 so far, each its own commit with a regression test. All 83 test files pass.

**What was broken, in plain terms:**

- The **report could not pair a lease with its rent-roll row** whenever the wording differed: "Apt 101" vs "Suite 101", "Drive" vs "Dr". Every unit then showed up as two false findings.
- **Rent rolls from PDF, Word, .xls or .txt were treated as leases**, so they were never checked at all.
- **The T-12 cross-check could essentially never work.** The causes:
  - it compared monthly rent to annual collections;
  - vacancy came out as 110% occupancy;
  - vacant units were never counted, so every rent roll looked 100% occupied;
  - section headers hid the real income line;
  - month headers like "Oct 2025" weren't recognized;
  - the "last 3 months" of a trailing T-12 were read as Oct–Dec.
- **Most real PMS layouts were rejected or misread:**
  - Yardi two-row headers and its charge-code layout;
  - RealPage's "Name" column;
  - Entrata's "Bldg-Unit" column;
  - Section 8 tenant-portion/HAP splits;
  - ISO dates;
  - cp1252/UTF-16 CSVs.

All of these are fixed and covered by tests. **Two decisions are yours, before merge:**

- **Unit-wording matching (Suite = Apt = Unit).** This reverses a stance a previous QA pass wrote into a test docstring. The reasoning is in `docs/DECISIONS.md`.
- **A new table, `rent_roll_unit_summaries`.** It is team-scoped and stores the vacant/down unit counts.
<!-- OPEN -->
1. **Lease extraction misreads (not mine to fix; owned by `feature/lease-intelligence`).** These cause 10 of the 13 remaining failures.
   - For tenants with accented names, the regex extractor returns the *owner entity* ("Bluebonnet Commons Owner LLC", "Copper Canyon Owner LLC") or only the surname ("Delacroix" for "François Delacroix"). The result is a high-severity false tenant_mismatch on that unit.
   - Repro: `backend/tools/gauntlet/fixtures/leases/p04/1301.pdf`, `p04/1303.pdf`, `p08/202.pdf`.
   - The runner tags these `[extraction-caused]`. Overall, tenant extraction is 560/585 correct; rent, dates and unit are 585/585.
2. **Scanned rent-roll PDFs (OCR): 3 failing cases.**
   - A 200 dpi scan with speckle noise either reconstructs no table or loses the header.
   - A sideways (rotated 90°) scan is never re-oriented.
   - Both fail with a clear 400 rather than wrong numbers, which is the safe failure. Fixing them properly means orientation detection (tesseract OSD) and a sturdier grid rebuild in `rent_roll_table_extract.py`. Not attempted yet.
3. **AI extraction path not exercised.** No funded `ANTHROPIC_API_KEY` exists, and CLAUDE.md rule 8 requires asking before any real-API run. Every run used the regex engine; the runner strips the key from its own environment.
4. **File types still narrower than the parsers.**
   - The rent-roll picker's `accept` list doesn't include `.txt`, though the backend now takes it. This is a frontend change, out of scope here.
   - The Upload page's standalone T-12 cross-check (`/portfolio/t12-reconciliation`) still accepts only `.csv/.xlsx`, though the T-12 parsers now read `.xls` (and the Deal Mismatch Report route takes `.xls/.pdf`). Widening that route is a one-line follow-up.
5. **T-12 income gap on a multi-building scope.** `detect_t12_income_gap` still compares only the *first* building's rent when a report is run without a property address. The route requires `property_address` whenever a T-12 is attached, so this can't trigger through the API today.
<!-- RECS -->
1. **Merge this branch before the first outside testers.** Without it, any tester whose leases say "Apt" (that is, nearly every multifamily lease) gets a report where every unit is a false unit_no_lease/lease_no_unit pair. Any tester with a T-12 gets either no T-12 findings or a wrong occupancy number.
2. **Hand the three extraction repros above to the `feature/lease-intelligence` session.** Accented names make the extractor fall back to the owner entity; that false tenant_mismatch is the main remaining error class.
3. **Make the gauntlet a standing check.** `run_gauntlet.py` takes about 30 s, needs no network or API key, and gives a per-format pass rate. Run it before every merge that touches `rent_roll_import`, `t12_*`, `deal_mismatch` or `portfolio`.
4. **Show testers what the importer did.** The import response now includes `unit_summary` (occupied / vacant / down units) and `skipped_rows` reasons such as "exact duplicate of row N" or "vacant unit". The upload screen should display them, so a tester can see "18 occupied, 2 vacant, 1 down; skipped: Grand Total" before trusting the report.
5. **Get one real export from each PMS from a friendly operator, with names scrubbed.** The fixtures here are modelled on public descriptions of AppFolio, Yardi, RealPage and Entrata reports, not on real files. One real file each would confirm the header and charge-code handling.
<!-- ABOUT -->
`backend/tools/gauntlet/` holds the harness:

- `truth.py` defines 14 fictional properties (8–12 units each) with planted issues and traps:
  - planted issues: rent over/under, expired lease, missing lease, missing unit, concession not on the rent roll, tenant mismatch, stale end date;
  - traps that must *not* be flagged: concessions shown correctly, "LAST, FIRST" names, co-residents, accented names, Section 8 splits, vacant/down units.
- `generate.py` renders those properties deterministically into:
  - **rent rolls:** AppFolio / Yardi / RealPage / Entrata / broker / Section 8 layouts as csv, xlsx, xls, docx, txt (UTF-16), text PDF, scanned and rotated PDF, plus 14 bad files (empty, header-only, all-vacant, password-protected, binary renamed .csv, truncated, wrong type, a lease in the rent-roll slot);
  - **T-12s:** 33, in five month-header styles, with and without a Total column, with a Summary tab first, as .xls and PDF, plus bad files;
  - **leases:** one PDF per leased unit.
- `manifest.json` stores the correct answer for every file, computed from first principles in `truth.py` and never from app output.
- `run_gauntlet.py` drives the real Flask routes with a fresh temp DB per case and an analyst on a real team. It covers lease upload, rent-roll import, the Deal Mismatch Report (+ PDF and Excel exports) and the T-12 cross-check route, plus a team-isolation case.
