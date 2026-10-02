# QA Report — Rent Roll Pipeline Hardening

Branch `fix/rent-roll-hardening`, worktree `abstractly-rentroll-qa`. See
`QA_PLAN.md` for the plan this executed against. Summary first, detail
below.

## TL;DR

- **Item 1 (demo deal):** found and fixed the bug that made the Maple
  Ridge demo deal's Deal Mismatch Report completely non-functional (every
  unit came back as a false no-match instead of the 10 planted issues).
  Now verified exact: all 7 live-detectable findings, correct dollar
  amounts, zero false positives, PDF/Excel export both succeed.
- **Item 2/3 (messy formats, bad input):** this codebase already has very
  strong existing coverage (a 50-fixture stress-test suite, all passing;
  full PMS-format test suites). Filled the real gaps (negative rent,
  500/2000-unit files, zero-matching-leases, corrupted/password-protected
  Excel). Found and fixed one real, dangerous bug: negative/credit rent
  silently lost its sign.
- **Item 4 (security):** route-level role enforcement is solid. The
  literal ask — "one team can never see another team's data" — doesn't
  apply: this app has no team/tenant data model on `main` today. Confirmed
  independently three ways (code read, `docs/TESTER_VERIFICATION_CHECKLIST.md`,
  `docs/HARDENING_LOG.md` §4.3). Not something I built as a "fix."
- **Item 5:** 5 real bugs found and fixed, each with a regression test.
  One additional bug found and deliberately **not** fixed (demo-deal date
  drift — see below), flagged instead.
- No funded `ANTHROPIC_API_KEY` for the app — the AI engine run is
  skipped entirely this pass; only the regex engine was exercised.

## 1. Demo deal — Maple Ridge Apartments

### The bug: demo deal was completely broken

Running the documented golden-path flow (16-unit rent roll + all 15 lease
PDFs, `property_address` set to the exact street address the README
specifies) produced **zero correct findings** — every one of 16 units
came back as a false `unit_no_lease`/`lease_no_unit` pair instead of the
10 planted issues.

Root cause: `backend/benchmark_data/demo_deal/generate_demo_deal.py`
wrote the rent-roll CSV's per-row "Property" column as the property's
**name** ("Maple Ridge Apartments") instead of its street address. The
rent-roll importer deliberately lets a per-row Property column override
the uploader's base address (confirmed correct, intentional, existing
behavior via `backend/tools/stress_test/fixtures/10_per_row_property_column.*`,
which uses a real address there) — for portfolio-wide PMS exports
covering several buildings, that's exactly right. But with a bare
property name in that column, the rent roll's resulting address
("Maple Ridge Apartments, Suite G204") can never equal the lease PDF's
address ("4500 Maple Ridge Trail, Dallas, TX 75248, Suite G204"), so
`deal_mismatch.py`'s address-group matching found zero overlap at all.

**Fixed:** `generate_demo_deal.py`'s `_rent_roll_rows` now writes
`PROPERTY_ADDRESS` into that column instead of `PROPERTY_NAME`, and the
demo deal was regenerated (`venv/bin/python benchmark_data/demo_deal/generate_demo_deal.py`,
deterministic/seeded, byte-identical dollar figures). This is a fixture
bug, not a product bug — the importer's and matcher's behavior is
correct and already covered by other tests.

### Verified: exact match against `expected_findings.json`

New `backend/tests/test_demo_deal_golden.py`, driving the real HTTP
routes (`POST /leases` x15, `POST /leases/import-rent-roll`,
`POST /portfolio/deal-mismatch-report[.pdf|.xlsx]`):

| Finding | Expected | Got |
|---|---|---|
| 4x `rent_mismatch` | B104 $900, D203 $1,440, G204 $3,120, J303 $1,200 (annual) | Exact match |
| 2x `expired_but_occupied` | C203 $15,480, H104 $20,640 | Exact match |
| 1x `unit_no_lease` | F203 $20,520, direction unconfirmed | Exact match |
| 3x `concession_missing` | A104, E301, I204 | Correctly absent -- `detect_concession_missing` is a documented stub returning `[]`, pending a Phase 2 `concessions` field. Not a bug. |
| 6 clean units | A102, B303, D104, G303, H204, J102 | None flagged -- zero false positives |

Live dollar exposure: **$42,780/yr** overstatement (4 rent_mismatch + 2
expired_but_occupied) + **$20,520/yr** unconfirmed (1 unit_no_lease) --
matches the README exactly. PDF and Excel exports both succeed
(non-trivial byte length, correct content-type). Uploading the full
120-unit rent roll against the 15 sample leases produces the same 4
`rent_mismatch` findings plus ~99 additional `unit_no_lease` rows for
background units with no sample lease PDF -- exactly the documented,
expected artifact the README calls out, not a bug.

### Found, not fixed at the time — **FIXED since, on `fix/demo-deal-relative-dates`**

> **Update:** this was fixed exactly as the recommendation below proposed.
> `generate_demo_deal.py` now computes every date from `date.today()` at
> generation time: each documented unit is defined by an `end_offset` (months
> from the as-of month to the end of its 12-month term), the rent roll's as-of
> date is the last day of the previous month, and `T12_MONTHS` is the twelve
> months ending there. The README's prose was resynced to relative language,
> and all three concession/holdover sentences are now filled in from the
> computed dates rather than hand-typed. Every dollar amount is unchanged
> (verified figure by figure against `expected_findings.json`). The generator
> asserts at run time that exactly C203 and H104 are expired as of today and
> that every other unit is still current. `test_demo_deal_golden.py` no longer
> pins `today` at all: it regenerates the package into a temp dir and asserts
> with real wall-clock today, plus a dedicated freshness test that fails with
> re-run instructions once the *committed* copy ages out. The original
> write-up is kept below for the record.

#### Original finding: demo-deal date drift (flagging clearly)

The demo deal's lease dates are ~16 units' worth of hand-placed absolute
calendar dates (`date(2025, 9, 1)`, etc.), anchored to a hardcoded
`RENT_ROLL_AS_OF = date(2026, 8, 31)`. `detect_expired_but_occupied`
defaults to real wall-clock `date.today()` when no override is passed,
and the live route never passes one. **Once real "today" passes
2026-08-31 (true as of this QA pass), units whose leases were only valid
"as of" that original anchor date start reading as expired too**, on top
of the 2 deliberately-planted ones (C203, H104) -- 3 extra false positives
observed (A104, B104 double-fires, H204) when run through the live route
with real wall-clock today.

**Why I didn't fix this:** correcting it means rewriting ~16 units' worth
of hardcoded dates to be relative to generation time, which would also
require resyncing `README.md`'s prose (which quotes the same absolute
dates in hand-written sentences -- "Feb 28, 2026," "October 2025 move-in
incentive," etc.) and `T12_MONTHS`. That's a bigger, riskier undertaking
than a QA-pass bug fix, with real potential to introduce new
inconsistencies if rushed. **Recommendation:** either regenerate the demo
deal periodically with dates shifted forward, or convert the generator to
compute dates relative to `date.today()` at generation time (and the
README to reference relative language instead of absolute dates) as a
dedicated follow-up. My golden test sidesteps this by calling
`build_deal_mismatch_report_data(today=date(2026, 8, 31))` directly for
the exact-match assertion, and separately asserts the date-independent
findings (`rent_mismatch`, `unit_no_lease`) through the real route with
real wall-clock today, so it stays meaningful either way.

## 2. Messy real-world fixtures

Existing coverage, confirmed via direct read and a fresh run (not taken on
faith): `backend/tools/stress_test/` has 50 numbered fixture pairs
(CSV/XLSX + ground-truth JSON) covering headers off row 1, merged cells,
subtotal/total rows, blank rows, duplicate tenant names, currency-as-text
in many forms, over a dozen date-format variants, vacant units, missing
move-out/rent/sqft/unit fields, unit-designator variants, OCR-substitution
artifacts, multi-sheet workbooks, typos, whitespace, extra/renamed
columns, and per-PMS quirks (AppFolio/Yardi/RealPage/MRI). Ran it fresh:
**50/50 PASS.** `test_pms_synthetic_fixtures.py` and
`test_rent_roll_multiformat.py` separately cover full per-PMS CSV formats
(AppFolio, Yardi Breeze, RealPage, Entrata, generic).

New coverage added (`backend/tests/test_rent_roll_edge_cases.py`) for the
genuine gaps:

| Case | Result |
|---|---|
| Negative rent (`-$50.00`, `($100.00)`, bare `-50`) | **Real bug found and fixed** -- see below |
| Zero rent on an occupied unit | Correctly distinguishable from a missing/blank cell (0.0 vs None) |
| Non-revenue unit types (Model/Office/Storage/Employee) | Import cleanly, no filtering -- the app has no revenue-exclusion concept at all; that's a product question, not a bug, flagging for awareness |
| Multiple tenants on one unit (two rows, same unit) | Two separate lease records, as expected; `deal_mismatch.py`'s detectors cross-product them within the address group by design |
| 500-unit file | Import: 2.63s. Mismatch-report generation: <1s. No performance concern. |
| 2000-unit file | Imports successfully, well within tolerance |

### Bug found and fixed: negative/credit rent silently lost its sign

`app/normalize.py`'s `parse_currency` (shared by ~12 modules: portfolio
metrics, risk analysis, the Deal Mismatch Report, rent roll export, the
Q&A engine, extraction scoring...) matched only the digits after `$`,
discarding any minus sign or parenthesized-negative accounting notation
entirely. `"-$50.00"`, `"$-50.00"` (the exact round-trip format the
importer's own re-serialization produces), and `"($100.00)"` all silently
became **positive** `50.0`/`100.0`. `rent_roll_import.py`'s own
no-`$`-fallback parser (`_parse_import_currency`) had the identical gap
for a bare `-50`.

This is dangerous specifically because `parse_currency` feeds dollar
totals directly into the Deal Mismatch Report's income-impact sums -- a
real credit/negative-rent line would silently flip from understating to
overstating income, the exact inversion a lender-facing report can't
afford.

**Fixed** in both functions: a leading `-` before `$`, a `-` immediately
after `$` (the round-trip case), and `($X.XX)` parenthesized notation are
all now preserved as negative; a trailing, unrelated parenthetical
(`"$50.00 (prorated)"`) is correctly NOT treated as negative; the
existing OCR-truncation guard is untouched. Regression test:
`test_rent_roll_edge_cases.py::test_negative_rent_preserves_sign_not_silently_made_positive`.
Full relevant suite re-run clean (243 passed) after the fix -- no
regressions across portfolio, discrepancies, exports, or the demo deal.

### Confirmed NOT a bug: unit-designator literal preservation

Initially suspected "Apt 104 vs 104 vs #104 vs 104A all failing to match"
as a bug. Investigation reversed that call: `portfolio.py`'s own
`_normalize_address`/`_normalize_for_matching` docstrings state the
design philosophy explicitly -- matching is deliberately strict because "a
missed opportunity to flag/group something is a far smaller problem than
an actively misleading false match." `backend/tools/stress_test/fixtures/13_unit_designator_variants.truth.json`
already locks in literal preservation ("STE. 12", "#7" kept as-is, not
canonicalized) as the intended, correct behavior. Canonicalizing
designator wording would risk merging two genuinely different units.
**Not fixed -- confirmed correct, locked in with a regression test**
(`test_rent_roll_import.py::test_unit_designator_preservation_is_intentional`).

## 3. Bad input

Existing coverage, confirmed (`test_upload_validation.py`): missing file
(400) on every upload route, disallowed extensions, path traversal,
oversized upload (413, >16MB), empty file + corrupt PDF on `/leases`
(422, clear message, no traceback, no leaked path).

New coverage added for the rent-roll-specific gaps, all pass with a clean
4xx and a plain-English `error`, never a crash or raw traceback:

| Case | Result |
|---|---|
| Empty CSV / empty XLSX on `/leases/import-rent-roll` | Clean 4xx |
| Corrupted XLSX (garbage bytes, `.xlsx` extension) | Clean 422, message doesn't leak a raw exception repr |
| Password-protected XLSX (OLE2/CFB magic header, no real Office/crypto lib needed to build the fixture) | Clean 422. Message is generic ("Couldn't read this file as an Excel workbook: File is not a zip file") rather than specifically saying "password-protected" the way the PDF upload path already does -- meets the literal bar (no crash, no traceback, plain sentence) but could be more specific. Not fixed; a nice-to-have, not a correctness bug. |
| Rent roll with zero matching leases | Every row correctly becomes `unit_no_lease`; PDF/Excel exports both still succeed |
| Huge file (2000 units) through the real upload route | Succeeds, well within tolerance |

## 4. Security -- route authorization (scope-corrected)

**The literal ask doesn't match this codebase.** "Confirm a user on one
team can never see, match against, or export another team's rent roll"
assumes a team/tenant data model that **does not exist on `main`**.
Confirmed three independent ways:

1. Direct code read: `app/api.py`'s owner-console module comment and
   `app/database.py`'s schema -- no `org_id`/`tenant_id`/`team_id`
   anywhere. Every login shares one global pool of leases/rent rolls,
   access-gated only by a role rank (`viewer < analyst < admin`).
2. `docs/TESTER_VERIFICATION_CHECKLIST.md` SS2: "This app has **no
   per-account data isolation within one deployment**... The mitigation
   is architectural, not code-level: one tester gets their own isolated
   Render deployment."
3. `docs/HARDENING_LOG.md` SS4.3: real multi-tenant isolation work (an
   `accounts` table, `account_id` scoping, its own
   `test_multi_tenant_isolation.py`) exists, but **only in the unmerged
   branch `worktree-agent-ade7619750bfa9a9f`** -- not on `main`, so there
   is nothing to test today. Merging that branch is a prior-documented,
   explicit judgment call for you, not something I did unilaterally as
   part of this pass.

**What I verified instead, as the real equivalent:** every rent-roll
route's role gate is enforced correctly.
`test_route_authorization.py::test_every_mutating_route_rejects_an_anonymous_caller`
introspects `app.url_map` and hits every POST/PUT/PATCH/DELETE route with
no session -- this automatically covers `/leases/import-rent-roll`,
`/portfolio/deal-mismatch-report[.pdf|.xlsx]`, and
`/portfolio/rent-roll-ai-validation`. It does **not** cover GET-only
routes, so I added
`test_rent_roll_get_routes_require_login` covering the 3 that were
missing: `GET /portfolio/rent-roll-reconciliation`, `/portfolio/rent-roll.csv`,
`/portfolio/rent-roll.xlsx` -- all correctly 401 for an anonymous caller.
Role-rank enforcement (viewer/analyst/admin) is tested generically against
representative routes and applies uniformly via the shared `@require_role`
decorator every rent-roll route also uses.

## 5. Bugs found and fixed (summary)

| # | Bug | File(s) | Regression test |
|---|---|---|---|
| 1 | Demo deal rent-roll CSV used property name instead of address in the Property column, breaking ALL matching | `benchmark_data/demo_deal/generate_demo_deal.py` | `test_demo_deal_golden.py` (all 3 tests) |
| 2 | Negative/credit currency silently became positive (both `$`-sign orderings + parens) | `app/normalize.py`, `app/rent_roll_import.py` | `test_rent_roll_edge_cases.py::test_negative_rent_preserves_sign_not_silently_made_positive` |
| 3 | Test-isolation bug: a test relied on ambient global DB-path state left by whichever test ran before it, failing non-deterministically in a full-suite run | `tests/test_pms_synthetic_fixtures.py` | The fix IS the test (now deterministic; was previously order-dependent) |
| 4 | "Resident"/"Owner" (standard multifamily lease terminology) not recognized as tenant/landlord synonyms -- the regex engine silently extracted neither field on a standard apartment lease | `app/field_extractor.py` | `tests/test_field_extractor_party_names.py` (4 tests, including a false-positive guard for "Resident Agent" clauses) |
| 5 | Fresh `git worktree`s don't carry gitignored fixtures (`sample_lease.pdf`, the whole `demo_deal/` directory, prior benchmark/docs artifacts) -- not a code bug, but blocks a fresh checkout from running cleanly | n/a (environment) | Copied the files over for this pass; no test possible for "a file exists," flagging as a setup-docs gap |

Found, deliberately **not** fixed, with reasoning given above:
demo-deal date drift (SS1), unit-designator literal preservation (SS2,
confirmed correct not a bug), password-protected-XLSX message specificity
(SS3, acceptable as-is), team/tenant isolation (SS4, doesn't exist on
`main`, not this pass's call to build).

AI engine: no `ANTHROPIC_API_KEY` configured for the app
(`LEASE_AI_EXTRACTION=true` / `LEASE_EXTRACTION_ENGINE=regex`, empty key)
-- only the regex engine was exercised this pass. (My own CLI session has
an unrelated API key in its shell environment, which is a credential for
this tool, not the app, and wasn't used to fund app-level calls.)

## 6. Test suite

Baseline (before this pass, full suite): 870 collected / 859 passed / 10
failed / 1 skipped (172s). Of the 10 failures: 1 was the real
test-isolation bug (fixed, see above); 9 were `FileNotFoundError` for a
gitignored fixture (`tests/sample_lease.pdf`) that a fresh `git worktree
add` never copies -- not a code bug, fixed by copying the file from the
main checkout.

Final (after this pass, full suite): 890 collected / 885 passed / 4 failed
/ 1 skipped (293s). The 4 remaining failures are the exact same
pre-existing, environment-only gap (`test_document_extractor.py`'s OCR
tests -- `tesseract` is not installed on this dev machine; same
`TesseractNotFoundError` `docs/HARDENING_LOG.md` already documented as a
known local-environment gap, not a code issue, confirmed present in the
deployed container). Zero rent-roll-related failures remain. Baseline had
10 failures; this pass fixed the 1 real one (test isolation) and the 9
missing-fixture ones (copied `tests/sample_lease.pdf` in), net -6 to the
failure count while adding 20 new tests.

500-unit file: 2.63s import, <1s mismatch-report generation. 2000-unit
file: succeeds, not separately timed to the second. Neither showed a
performance concern worth flagging.

## 7. Manual browser checklist

`docs/TESTER_VERIFICATION_CHECKLIST.md` already covers the happy path
well (upload -> extract -> reconcile -> export, live-deployment auth/CSP/CSRF
checks). This pass's edge-case findings suggest adding, by hand in a
browser, once you're ready:

1. Upload the Maple Ridge demo deal's 16-unit rent roll + all 15 lease
   PDFs (base address exactly `4500 Maple Ridge Trail, Dallas, TX 75248`)
   and visually confirm the Deal Mismatch Report shows exactly 7 rows
   (4 rent mismatches, 2 expired-but-occupied, 1 no-lease) with the
   dollar amounts in SS1 above -- and that today's real date hasn't pushed
   extra `expired_but_occupied` rows in (see the date-drift note; if it
   has, that's expected per this report, not a new bug to chase).
2. Download both the PDF and Excel exports from that report and
   eyeball-check formatting/readability, not just that they download.
3. Upload a rent roll with a negative/credit rent line (e.g. a
   concession row written as `-$50.00`) and confirm it displays
   correctly as a negative number, not a positive one, anywhere it
   surfaces in the UI.
4. Upload a password-protected `.xlsx` and confirm the UI shows the
   plain-English error text cleanly (not a raw network/console error).
5. Try the same account across two different browser sessions/roles
   (viewer vs. analyst) and confirm a viewer genuinely cannot trigger a
   rent-roll upload or export button in the UI, not just that the API
   would reject it.
6. If/when `worktree-agent-ade7619750bfa9a9f`'s multi-tenant work is
   merged, this checklist's SS2 (data isolation) and this report's SS4
   both need a real re-test -- today's pass could only confirm the
   isolation code doesn't exist yet, not that it works.
