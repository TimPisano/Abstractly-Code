# Plan: qa/overnight-gauntlet

**Approval:** the user's task prompt (2026-10-05) *is* the approved scope and
explicitly said "work autonomously all night … without asking me questions".
So this plan is written for the record and the reviewer, and work does not
stop for a separate approval step.

## Goal

An overnight reliability gauntlet for the core diligence pipeline (upload →
parse → lease extraction → rent roll validation → T-12 cross-check → Deal
Mismatch Report + PDF/Excel export), run locally against synthetic messy
files with a manifest of the correct answer for every file. Every crash, hang,
wrong number, missed mismatch, false alarm or unclear error gets a root-cause
fix and a regression test, one commit per fix. `QA_REPORT.md` is rewritten
after every cycle.

## Prior art (searched TASKS.md, all branches, stashes)

- `backend/tools/stress_test/`: 50 rent-roll parse fixtures with truth JSON
  (parse-level only, no leases/T-12/report). Kept as is; the gauntlet is
  end-to-end, so it is a new harness beside it, not a copy.
- `backend/benchmark_data/demo_deal/` (Maple Ridge): the lease PDF template
  and report-level golden tests. Gauntlet leases reuse its layout ideas.
- `fix/rent-roll-hardening` (merged): the previous QA pass. Its
  `QA_REPORT.md` on `main` is replaced by this run's report. The old one
  stays in git history (`03cebb5`).
- `docs/tester-pack:OVERNIGHT_REPORT.md` lists unfixed pipeline bugs, among
  them #2 (T-12 income gap compares monthly vs annual), #3 (rent-roll
  detection by file extension), #4 (vacant rows never imported, so
  occupancy is always 100%) and #7 (.xls T-12). The gauntlet should
  reproduce these, and they get fixed here if it does.
- No `qa/` or gauntlet branch exists, and no stash is related.

## Approach

1. `backend/tools/gauntlet/generate.py`: seeded, deterministic generator.
   It builds ~14 fictional properties, each with its ground truth (units,
   tenants, rents, dates, concessions, Section 8 splits, vacant/down units).
   It writes:
   - 60+ rent rolls across AppFolio / Yardi / RealPage / Entrata / broker
     Excel styles. The messy features are merged cells, multi-row
     headers, subtotals, blank rows, footnotes, duplicate units,
     vacant/down units, concessions, HAP vs. tenant portion, mixed dates,
     `$`/commas/parentheses, misspelled headers, extra sheets, cp1252/
     UTF-16 CSVs, text and scanned/rotated PDFs, password-protected
     xlsx, empty files and wrong file types.
   - 30+ T-12s (csv/xlsx/pdf, month-header variants, section headers,
     negative signs, extra sheets).
   - Lease PDFs per property with planted mismatches (rent, expired,
     missing lease, missing unit, concession not on rent roll, tenant
     name, dates) plus clean controls.
   - `manifest.json`, which holds the expected answer for every file.
2. `backend/tools/gauntlet/run_gauntlet.py`: for every case, a fresh temp
   SQLite DB and a real Flask test client with an analyst session on a real
   team. It uploads leases (`POST /leases`), imports the rent roll, runs
   `POST /portfolio/deal-mismatch-report` (+ `.pdf`, `.xlsx`) with the T-12,
   and `POST /portfolio/t12-reconciliation`. It grades against the manifest
   with a per-case timeout, then writes `results/latest.json` and a summary.
3. Cycle: run, triage failures to their root cause, fix, add a regression
   test (fails before, passes after), commit, re-run everything. Then add
   nastier fixtures aimed at the weak spots. Push every few cycles.
4. `QA_REPORT.md` is rewritten each cycle: summary, pass rates by file type,
   fixes with hashes, what is not fixed, top 5 recommendations.

## Files

- New: `backend/tools/gauntlet/**`, `backend/tests/test_gauntlet_*.py`
  (registered in `run_all_tests.py`), `QA_REPORT.md` (rewritten).
- Changed as fixes require: `rent_roll_import.py`, `rent_roll_table_extract.py`,
  `t12_import.py`, `t12_statement.py`, `deal_mismatch.py`, `portfolio.py`,
  `field_extractor.py`, `api.py` (upload/report routes only).
- Not touched: `render.yaml`, any deploy config, `frontend/`, prod/tester DBs,
  the Maple Ridge fixtures' expected answers.

## Team isolation & roles

- The harness runs every case as a real analyst on a real team through the
  real routes, so `@require_role` and `team_id` scoping are exercised, not
  bypassed.
- Any route or query touched by a fix keeps its existing `@require_role`
  and passes the caller's `team_id`.
- One gauntlet case uploads a second team's documents into the same DB and
  asserts they never appear in the first team's report.

## Feature flag

None planned: these are correctness fixes to existing behavior. Any new
user-visible behavior that is not a pure fix goes behind an env flag that
defaults to off.

## Verification

- `python backend/tests/run_all_tests.py` after every fix.
- Gauntlet pass rate per cycle, recorded in `QA_REPORT.md`.

## Constraints

- **Anthropic API:** there is no funded key (TASKS.md "Blocked"), and rule 8
  says to ask before any real-API run. Extraction therefore runs on the
  regex engine. The AI path is not exercised with real calls, and the
  report says so.
- Never weaken or delete tests. Never merge or deploy. Never touch Render.

## Out of scope

- UI changes.
- New detectors beyond fixing the existing ones.
- Persisting T-12s.
- The AI extraction path with real calls.
