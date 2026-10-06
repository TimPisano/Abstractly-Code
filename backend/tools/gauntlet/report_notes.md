<!-- SUMMARY -->
**Cycle 7: 173 of 188 cases pass (92%). It was 22 of 132 (17%) at the start.** The gauntlet now runs 92 messy rent rolls (plus a two-property portfolio file), 49 T-12s and 214 lease documents (including duplicate copies and rent amendments) through the full local pipeline, graded against a manifest of correct answers.

- **Planted mismatches caught: 1,971 of 1,971, every one with the right dollar amount.**
- **False alarms: 19, down from 337.** All are lease-extraction misreads of accented names (owned by `feature/lease-intelligence`) or character-level OCR misreads on scanned rent rolls.
- **Scanned rent rolls now import.** Columns are rebuilt from the data rows, sideways and tilted pages are turned upright, and impossible OCR rents are blanked with a warning. Remaining scan failures are character misreads (a lost space, "4201" for 1201) that grid logic can't fix. The heavily degraded sideways fixture still fails with a clear 400.
- **No crashes and no hangs.**
- **Fixes:** 59, each its own commit with a regression test. All 83 test files pass.
- **Reviews:** the `security-auditor` said MERGE (no cross-team leak). Its three follow-ups are fixed: image-size cap, tesseract timeouts, insert-before-supersede. The `reviewer` said FIX FIRST with four items, all fixed (`b888ef9`, `c0b4403`, `99920ec`, `4e5d765`). A re-review is pending.

**AUDIT.md top priority: "the Deal Mismatch Report gets dollar figures wrong on ordinary lease files" (§6.11, §6.1).** It is reproduced with golden fixtures (property `p18` + a re-import case) and fixed at the root:

| Audit finding | Before (on the pre-fix code, same fixtures) | Fix |
|---|---|---|
| Original lease + renewal on file | Each renewed unit got a phantom rent_mismatch + expired_but_occupied + dates_mismatch (the audit's $3,600 + $25,200 = $28,800/yr reproduced exactly in a unit test) | Each unit is compared only against its **operative** lease (term covering the as-of date, else the newest). This applies in both the report and the reconciliation view. |
| Scheduled rent step-up | A correct year-2 rent roll was flagged as an overstatement | Rent in effect on the as-of date, from the escalation schedule. An escalation that can't be priced is flagged but **not** counted in dollars. |
| "First month 50% off" | Priced as a full-term discount: **$10,950 instead of $912.50** (12×) | A singular "first/last month" means one month |
| Re-import of an updated rent roll | Every unit doubled (9 stale rows stayed active) | A new import for a building supersedes that building's previous rows (kept, not deleted; team-scoped) |
| "Unit"/"Apt"/"#", "St"/"Street", "Building A, Apt 101", leading property name | Real gaps became unpriced "no lease"/"no unit" pairs | One canonical unit/building key |
| Same lease uploaded twice (signed + unsigned copy) | A real gap was counted twice in dollars | Identical copies collapse to one |
| Rent amendment uploaded as its own document | The correct amended rent was flagged against the original | Same tenant + same term = versions of one lease; matching any version is fine |
| Scanned T-12 (§6.13) | OCR numbers trusted as-is; one test scan read $10.81 of annual rent | Real OCR table rebuild; a line is trusted only if its months add up to its total, otherwise a clear error |
| T-12 from the report page | Always 400 (no property address sent) | Scoped to the rent roll's building when there is exactly one; otherwise a clear error naming the buildings |
| T-12 income gap / occupancy / bad-debt months | Never fired / false alarm / wrong months | Fixed in cycles 1–2 (see the fixes table) |

Still open from the audit's §6.11 list, all owned by lease extraction: everyday rent phrasings the regex misses (§6.16), and a "rent not found" finding. Those are for the `feature/lease-intelligence` session.

**What was broken, in plain terms:**

- The **report could not pair a lease with its rent-roll row** whenever the wording differed: "Apt 101" vs "Suite 101", "Drive" vs "Dr", or "Building A, Apartment 101" vs "A-101". Every unit then showed up as two false findings.
- **Rent rolls from PDF, Word, .xls or .txt were treated as leases**, so they were never checked.
- **The T-12 cross-check could essentially never work.** The causes:
  - it compared monthly rent to annual collections;
  - vacancy came out as 110% occupancy;
  - vacant units were never counted;
  - section headers hid the real income line;
  - month headers like "Oct 2025" and "Oct 2025 Actual" weren't recognized;
  - "last 3 months" was read as Oct–Dec;
  - negative amounts lost their sign;
  - lease PDFs were double-counted in the rent total.
- **Most real PMS layouts were rejected or misread:**
  - Yardi two-row headers, merged group titles and its charge-code layout;
  - RealPage's "Name" column;
  - Entrata's "Bldg-Unit" column;
  - Section 8 HAP splits;
  - future-resident rows;
  - semicolon CSVs and cp1252/UTF-16 encodings;
  - ISO, Excel-serial and European dates, plus comma-decimal amounts;
  - T-24 statements, which were read from the older year;
  - headers below row 20;
  - "Grand Total" rows and duplicate rows.

All of these are fixed and covered by tests. **Three decisions are yours, before merge:**

- **Unit-wording matching (Suite = Apt = Unit, Building A + Apt 101 = A-101).** This reverses a stance a previous QA pass wrote into a test docstring. The reasoning is in `docs/DECISIONS.md`.
- **A new table, `rent_roll_unit_summaries`.** It is team-scoped and stores the vacant/down unit counts.
- **Re-import replaces an earlier rent-roll file only when it covers the same units.** See `docs/DECISIONS.md`; the upload screen doesn't show "replaced N rows" yet.
<!-- OPEN -->
1. **Lease extraction misreads (not mine to fix; owned by `feature/lease-intelligence`).** These cause 10 of the 13 remaining failures.
   - For tenants with accented names, the regex extractor returns the *owner entity* ("Bluebonnet Commons Owner LLC", "Copper Canyon Owner LLC") or only the surname ("Delacroix" for "François Delacroix"). The result is a high-severity false tenant_mismatch on that unit.
   - Repro: `backend/tools/gauntlet/fixtures/leases/p04/1301.pdf`, `p04/1303.pdf`, `p08/202.pdf`.
   - The runner tags these `[extraction-caused]`. Overall, tenant extraction is 560/585 correct; rent, dates and unit are 585/585.
2. **Scanned rent-roll PDFs (OCR): 3 cases still fail.** The reasons are character-level misreads, not structure: "EzraQuintero" (lost space; tenant matching now tolerates it), "4201" for unit 1201, and "$1.00" for $1,475.00 (now blanked with a warning, not priced). The worst fixture (sideways, tilted, speckled, 57% OCR confidence) still fails with a clear 400. Better results would need a better OCR engine or a cleaner scan, not more grid logic.
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
