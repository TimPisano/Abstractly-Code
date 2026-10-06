# Plan: feature/lease-intelligence

**Approval:** the user's task prompt (2026-10-05) said to "work autonomously
all night" on this branch, so that prompt is the approved scope (same
precedent as `qa/overnight-gauntlet`). This plan is the record for the
reviewer. Note: the prompt was cut off after "scanned"; it is read here as
"scanned leases" (image-only PDFs that need OCR).

## Goal

Make lease extraction as accurate and complete as possible for
**multifamily and Section 8** leases, and prove it with numbers: a graded,
synthetic lease corpus with a known right answer for every field, and a
per-field accuracy table before and after each fix
(`LEASE_EXTRACTION_REPORT.md`, rewritten each cycle).

## Prior art (searched TASKS.md, all branches, stashes, git log)

- **Commercial-only accuracy harness:** `benchmark_data/run_accuracy_benchmark.py`
  (12 real SEC commercial leases) plus `app/extraction_scoring.py` (value
  matching and grading). It is reused for scoring, not copied.
- **Synthetic generators are all commercial:** `tests/generate_synthetic_corpus.py`,
  `create_synthetic_leases.py` and `create_scanned_lease.py` (an image-only
  PDF, `test_real_ocr.py`). There is no multifamily or Section 8 lease
  fixture anywhere. The new corpus borrows their reportlab/PIL approach.
- **Concessions are already done:** `fix/concession-detection` (merged)
  built `app/concessions.py`, which both engines call. It is reused as is.
  Pet and parking rent are already excluded from concessions there.
- **Section 8 work elsewhere, none of it extraction:**
  - `feature/s8-demo-files`: the Oak Hollow tenant-file data
  - `feature/s8-hud-data`: HUD income-limit and FMR tables
  - `docs/research/section8.md`
- **No other branch touches lease extraction.** `qa/overnight-gauntlet`'s
  plan explicitly leaves `field_extractor.py` and `ai_extraction.py` to this
  branch and will log extraction misses for it.

Searches run: `extract|section 8|HAP|amendment|lease-intel` across TASKS.md
and `git log --all`, branch names, and `git stash list` (2 unrelated stashes).

## What's broken today (found during planning, reproduced in memory)

1. **False lease splits.** `detect_lease_boundaries` treats addendum text
   as new parties. In a HUD Tenancy Addendum, "Tenant Rent: $312" and "(To
   be attached to Tenant Lease)" become tenants called "Rent" and "Lease".
   In a renewal amendment, "This Renewal Amendment is between X" becomes a
   new landlord. One lease plus its addenda gets stored as 2–3 separate
   leases.
2. **Renewal and amendment rent loses.** Within one PDF, the first
   (original) rent always wins over a later renewal's new rent.
3. **There are no multifamily charge fields at all.** That covers unit
   number, pet rent/fee/deposit, parking, utility reimbursements (RUBS and
   flat fees), and the Section 8 split (contract rent vs. tenant portion vs.
   HAP, PHA, HAP contract term, utility allowance).
4. **The AI prompt is written for commercial leases.** It says
   "commercial", and its rent guidance ("initial-term rent") is wrong for
   renewals.
5. **One illegible page blocks everything.** If any page is under ~50
   characters, the whole document becomes "OCR needed" with no extraction.
   OCR only runs when the *entire* PDF has under 100 characters, so a
   lease with one scanned page gets nothing.

## Approach

### Phase A: measure first
- `backend/tools/lease_corpus/generate.py` is a seeded, deterministic
  generator of ~40+ synthetic lease PDFs plus `manifest.json` holding the
  expected value of every field. All names, addresses and PHAs are
  fictional. Families:
  - standard multifamily, in several templates (NAA-style labeled table,
    prose, state-form style)
  - Section 8: the lease plus the HUD Tenancy Addendum, plus a HAP contract
    excerpt
  - concessions
  - pet addendum
  - parking addendum
  - utility addendum (RUBS and flat fees)
  - renewal agreement
  - mid-term amendment
  - scanned versions (rasterized, skewed and noisy, so they need OCR)
  - odd formats (rent written out in words, MM/DD/YYYY dates, multiple
    residents)
- `backend/tools/lease_corpus/run_corpus.py` runs the real page extraction
  (including OCR) and the regex engine on every file, grades each field
  against the manifest with `extraction_scoring`, checks for lease splits,
  and writes `results/latest.json` plus a summary.
- The first run gives the baseline. `LEASE_EXTRACTION_REPORT.md` records
  it.

### Phase B: fix existing fields (always on; these are bug fixes)
- **Boundary detection:** ignore party "names" that are common nouns or
  heading words (Rent, Lease, Portion, ...). Treat a page that is an
  addendum, amendment, renewal or HAP/Tenancy Addendum as part of the
  preceding lease. Strip "is between" style lead-ins.
- **Rent for Section 8:** `rent_amount` is the contract rent (the total
  rent to owner). The tenant portion is never mistaken for it.
- **Multifamily phrasing gaps:**
  - "Resident(s)", "Owner/Agent", "Apartment No."
  - written-out amounts, "per month" variants, MM/DD/YYYY dates
  - all of these are found and fixed through the corpus
- **Per-page OCR:** OCR only the pages with no usable text layer, instead
  of all-or-nothing. A short signature page alone no longer blocks the
  whole lease.
- Each fix gets a regression test that fails before the fix.

### Phase C: new multifamily fields (behind `LEASE_MULTIFAMILY_FIELDS`, default off)
Both engines emit the same keys in the existing `{value, source{page,quote},
confidence}` shape, with structured `items` where useful (as `concessions`
does):
- `unit_number`
- `pet_charges`: monthly pet rent, one-time pet fee, pet deposit
- `parking_charges`: monthly parking or garage fee, with space details
- `utility_charges`: RUBS (yes/no plus which utilities), flat monthly
  fees, valet trash, and so on
- `section_8`: whether the lease is subsidized, PHA name, contract rent,
  tenant rent, HAP amount, HAP contract start/end, utility allowance
- `lease_changes`: renewals and amendments found inside the document, each
  with its effective date, new rent and new end date. Also
  `current_rent_amount` and `current_lease_end_date`, which resolve to the
  latest change.

`rent_amount` and the lease dates keep their current meaning (the base
lease), so the Deal Mismatch Report is not silently changed. Feeding the
`current_*` values and the Section 8 split into the report is a follow-up
(see Out of scope).

### Phase D: AI engine
- Residential-aware system prompt; guidance for the new fields and Section
  8; correct handling of renewals.
- `PROMPT_VERSION` moves to v3. The new fields only enter the tool schema
  when the flag is on.
- `termination_options` is added, so both engines return the same keys.
- Tested with a **mocked** Anthropic client only. There is no funded key,
  so AI accuracy is not measured (stated in the report).

### Phase E: lease detail UI
- `frontend/app/app.js` and `detail-view.js` get labels and a "Multifamily
  charges" group for the new fields.
- They render only when present, so nothing changes with the flag off.
- Headless screenshots at 1440/768/375.

### Cycle
Run the corpus, triage misses to their root cause, fix, add a regression
test, commit, run the suite, then add harder fixtures. Push every few
cycles. Update the report each cycle.

## Files to change
- `backend/app/field_extractor.py`
- `backend/app/ai_extraction.py`
- `backend/app/pdf_extractor.py` and `backend/app/document_extractor.py`
  (OCR fallback, lease path only)
- new `backend/app/multifamily_charges.py` (charge, Section 8 and
  lease-change parsing, mirroring how `concessions.py` is split out)
- `backend/app/api.py`: only the lease-extraction helpers
  (`_extract_leases_from_file_storage` OCR gate), only if needed
- `frontend/app/app.js` and `frontend/app/detail-view.js`: labels and group
- new `backend/tools/lease_corpus/**`, new `backend/tests/test_lease_*.py`
  (registered in `run_all_tests.py`), `LEASE_EXTRACTION_REPORT.md`

## Files not to touch
- Rent roll and T-12 (owned by `qa/overnight-gauntlet`):
  - `rent_roll_import.py`
  - `rent_roll_table_extract.py`
  - `t12_import.py`
  - `t12_statement.py`
  - `deal_mismatch*.py`
  - `portfolio.py`
- `concessions.py`: called, not changed, unless a lease-extraction bug is
  found in its parser. That would be a small fix, noted in TASKS.md so the
  gauntlet knows.
- Accounts (owned by `feature/auth-flow`): `auth.py`, `security.py`,
  auth/team routes.
- `render.yaml` and all deploy config.
- The Maple Ridge fixtures' expected answers.

## Team isolation & roles
No new routes. No route or document query is added or changed: extraction
is a pure function of page text. The one possible `api.py` touch, the OCR
gate inside `_extract_leases_from_file_storage`, sits behind the existing
`@require_role("analyst")` upload routes, and team scoping happens at
insert, unchanged.

## Feature flag
`LEASE_MULTIFAMILY_FIELDS` (default off) gates the new fields in both
engines and in the UI. Phase B fixes to existing fields are always on.

## Verification
- `python backend/tests/run_all_tests.py` after each fix, with only the
  known failures expected (#10 `test_demo_deal_regression.py` and the
  OCR-tool tests).
- New tests:
  - boundary regression with HUD addendum, renewal and pet addendum
  - Section 8 rent split
  - per-charge parsers
  - per-page OCR
  - flag on and off for both engines (AI mocked)
  - a corpus smoke test on a small subset
- Corpus per-field accuracy, before and after, in `LEASE_EXTRACTION_REPORT.md`.
- Screenshots of a lease detail page with the flag on, at three widths.

## Out of scope (handed off, not done here)
- Deal Mismatch Report using `current_rent_amount`, the Section 8
  tenant-vs-HAP split, or other charges. That is a `deal_mismatch.py` change
  (gauntlet's file); proposed as a follow-up task.
- **Lease-to-rent-roll matching on "Apt 204" vs "Suite 204"** (it currently
  matches the address string exactly in `portfolio._normalize_address`). This
  is a real multifamily gap, flagged for the gauntlet/follow-up, not fixed
  here. `unit_number` makes the later fix easy.
- Making the new fields editable/verifiable (needs `portfolio.FIELD_NAMES`),
  and adding them to exports.
- Any real Anthropic API run.

## Open questions (for the morning, none block the night)
1. Turn `LEASE_MULTIFAMILY_FIELDS` on for the tester deployment?
2. Should the report reconcile against the *current* (post-renewal) rent?
   (Proposed follow-up.)
