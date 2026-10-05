# Plan: feature/s8-hud-data

## Goal

A self-contained backend module, `backend/app/section8/hud_data/`, that
holds HUD's published reference numbers — **Section 8 income limits**,
**Fair Market Rents**, and **LIHTC (MTSP) income limits** — by year and
area, versioned by effective year. It exposes a lookup function and a
refresh command. It is the data foundation for any later Section 8 /
LIHTC compliance check (`docs/research/section8.md` §6); nothing in the
app calls it yet. Behind `SECTION8_HUD_DATA_ENABLED`, default **off**.

Scope came directly from the user's task prompt (2026-10-05), which
asked for build → commit → push → reviewer in one pass; that prompt is
treated as the plan approval.

## Prior art

None. Searched TASKS.md (`section8|s8|hud|lihtc|fmr|income limit`), all
branches' commit messages (`s8|section8|hud|lihtc`), and stashes. The
only hit is the research briefing itself (`docs/research/section8.md`,
merged `2fbb542`, docs only).

## Approach

1. `section8/__init__.py` (empty package marker) and
   `section8/hud_data/` with:
   - `config.py` — flag (`SECTION8_HUD_DATA_ENABLED`, default off) and
     DB path (`HUD_DATA_DB_PATH`; else `hud_data.db` beside `DB_PATH`
     so it lands on the persistent disk where one exists; else
     `backend/hud_data.db`, gitignored by `*.db`).
   - `models.py` — frozen dataclasses for the three record types.
   - `parsers.py` — parse HUD's bulk CSV/XLSX files (the full-year files
     HUD publishes) into records. Header matching is case-insensitive
     with the column patterns HUD uses (`l50_1`, `ELI_1`, `l80_1`,
     `fmr_0..4`, `lim50_25p1`, `lim60_25p1`, `median2025`, `fips`,
     `hud_area_code`, …). Bad numbers fail loudly with the row number.
   - `store.py` — its own SQLite file: `hud_data_rows`
     (dataset, effective_year, area_code → JSON payload) and an
     append-only `hud_data_versions` log (year, effective date, source,
     sha256, row count, loaded_at). Loading a year replaces that year's
     rows in one transaction; other years are untouched.
   - `lookup.py` — `lookup_income_limits`, `lookup_fmr`,
     `lookup_lihtc_limits` (by explicit `year`, by `as_of` date, or
     latest), plus derived LIHTC helpers: income limit at any 20–80%
     AMI level and the §42 monthly rent cap (30% of the limit at the
     imputed household size of 1.5 persons/bedroom, 1 for a studio).
   - `loader.py` + `cli.py` + `__main__.py` — CLI:
     `python -m app.section8.hud_data refresh --dataset il|fmr|mtsp --year 2025 (--file PATH | --url URL) [--effective-date YYYY-MM-DD]`
     and `status`. `--url` only accepts `https://www.huduser.gov/…`.
2. Default effective dates when not given: income limits and MTSP →
   April 1 of the year; FMR fiscal year N → October 1 of N−1.
3. Tests in `backend/tests/test_section8_hud_data.py` against small
   fixture files in `backend/tests/fixtures/hud_data/` (illustrative
   numbers, not real HUD values); registered in `run_all_tests.py`.

## Files to change

- New: `backend/app/section8/**`, `backend/tests/test_section8_hud_data.py`,
  `backend/tests/fixtures/hud_data/*`, this plan.
- Edit: `backend/tests/run_all_tests.py` (one line, test registration —
  required by CLAUDE.md).

## Files not to touch

Everything else: `api.py`, `database.py`, `render.yaml`, the frontend,
`requirements.txt` (uses only `openpyxl` and `requests`, already pinned).

## Team isolation & roles

No routes are added. HUD limits are public reference data, identical for
every team, so the store is deliberately **not** team-scoped and never
touches document tables. When a later branch exposes this over HTTP, the
route needs `@require_role("viewer")` at minimum; refresh must be
owner/admin-only.

## Feature flag

`SECTION8_HUD_DATA_ENABLED` (default off). Lookups, `refresh()` and the
CLI raise `HudDataDisabled` while it's off; the `lihtc_*` helpers are pure
math on an already-looked-up record and are not gated. Not added to `render.yaml`.

## Verification

Unit tests (no network; the `--url` path is tested with a mocked
fetcher): parsing each dataset from CSV and XLSX, header variants, bad
numbers, versioning (two years coexist; reload replaces one year only;
version log appends), lookup by year / as-of date / latest, 5-digit
county FIPS normalization, lookup by HUD area code, not-found and
flag-off errors, derived LIHTC income/rent limits, CLI end-to-end, URL
allow-list. Full suite via `run_all_tests.py`.

## Out of scope

- Any HTTP route, UI, or call from existing app code.
- Per-entity HUD User API fetching (`/il/data/{id}`, `/fmr/data/{id}`):
  needs a bearer token and thousands of calls for a full year; bulk
  files are the canonical full-year source. Possible follow-up.
- Small Area FMRs, HERA special limits, state-agency charts, utility
  allowances, payment standards, scheduled/automatic refresh.

## Review follow-ups (reviewer verdict MERGE, applied anyway)

- Files whose headers carry no year (FMR; IL `l50_`/`ELI_`/`l80_`) are
  now year-checked by file name (`FY25`, `fy2026`); a name with no year
  is still accepted unchecked.
- Zero / `inf` / `nan` values rejected; limits must not fall as
  household size grows.
- Where a deploy sets `DB_PATH` without a persistent disk (tester, demo),
  the HUD store is wiped on every deploy like everything else there.

## Open questions

- **Real-file compatibility is unverified.** Header patterns follow
  HUD's published files from memory; no real FY2025/26 file was
  downloaded here. Run `refresh --url` against the live files before
  depending on it.
- Rounding of derived LIHTC rent limits varies by state agency; this
  floors to the dollar. Confirm against the target state's chart.
