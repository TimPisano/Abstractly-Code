# T-12 Cross-Checking for the Deal Mismatch Report

Branch: `feature/t12-crosscheck`, based on `feature/deal-mismatch-report` (not `main` —
see note below).

## Branch base note

`main` only has the base `deal_mismatch.py` module (commit `50ca746`). The export
renderers (`deal_mismatch_export.py`) and analyst-role route enforcement (`fa189ee`)
exist only on the still-unmerged `feature/deal-mismatch-report` branch. Per your
answer, this branch is rooted there instead of `main`, so it has both. You'll want to
land `feature/deal-mismatch-report` into `main` at some point independent of this work.

## Three scope calls, flagged before writing any code

1. **"Team-level data isolation"** — this app has no `team_id` anywhere in the schema;
   it's single-tenant per deployment (one company, one `users` table, no tenant
   dimension to scope by). The existing isolation boundary is role-based
   (`@require_role('analyst')` on every report route). I'll apply that same gate to
   the new route and treat it as satisfying "team isolation," since there's nothing
   else in this codebase's data model to isolate against. Flag if you actually meant
   something else (e.g. a future multi-tenant model not yet built).

2. **Concessions can't be reconciled against the rent roll.** Neither lease-PDF
   extraction nor rent-roll import captures a concessions figure anywhere today —
   `deal_mismatch.py`'s existing `detect_concession_missing` is a stub for exactly
   this reason (waiting on a future "Phase 2" lease field that doesn't exist yet). So
   the new concessions check will report the T-12's concessions line and flag it as
   **"reported on T-12, not verifiable against rent roll (no rent-roll concessions
   field exists)"** rather than compute a fake dollar mismatch. If/when a rent-roll
   concessions field lands, this becomes a real number comparison with no shape
   change needed.

3. **Bad debt trend is building-level, not per-tenant.** Rent roll import only
   captures `tenant` and `rent_amount` — no balance/delinquency field — so there's no
   way to point at which specific "current" tenant isn't paying. The check flags a
   rising bad-debt trend across the T-12's trailing months at the building level,
   with a plain-English note that a rent roll showing full occupancy alongside rising
   bad debt is the pattern worth investigating manually.

## What already exists and will be reused, not rebuilt

- `t12_import.py` already parses CSV/XLSX T-12s for exactly one line item (actual
  rental income, annual total only) — header-row detection tolerant of decorative
  rows, month-column aliases, Total/Annual-column detection, tolerant currency
  parsing. Its column-matching and header-detection helpers (`_match_t12_columns`,
  `_find_t12_header_row`, `_parse_t12_currency`) get reused, not rewritten, for the
  new multi-line-item parser.
- `/portfolio/t12-reconciliation` and `investment_memo.py`'s existing T12 handling
  call `parse_csv_t12`/`parse_xlsx_t12` today — **left untouched** so nothing existing
  breaks. New functions are added alongside, not in place of, these.
- `compute_t12_reconciliation` (portfolio.py) already does building-level rent-roll
  vs. T12 annual-income comparison with its own fixed tolerance
  (`_T12_DISAGREEMENT_TOLERANCE_PCT = 5.0`, `_ABS = 3000.0`). The new "rent roll
  materially above actual collections" check in this feature is a *separate*,
  adjustable-materiality version scoped to the Deal Mismatch Report — it does not
  change that function or its route.
- `pdfplumber` and `pytesseract`/`pdf2image` are already dependencies (used by
  `pdf_extractor.py` for lease PDFs) — reused for T-12 PDF support rather than adding
  a new PDF library.
- Discrepancy persistence follows `sync_deal_mismatch_report`'s existing upsert/dedup
  convention (natural key per row, not per report run) — new T-12 rows get their own
  natural-key prefix following that same pattern.

## 1. Backend: multi-line-item, monthly T-12 parsing

New module `backend/app/t12_statement.py` (kept separate from `t12_import.py` rather
than piled into it, since that module's whole design is "extract exactly one number"
— its docstring says so explicitly):

- `parse_csv_t12_statement(file_bytes, filename)`, `parse_xlsx_t12_statement(...)`,
  and `parse_pdf_t12_statement(...)` (new PDF path).
- Reuses `_match_t12_columns`/`_find_t12_header_row`/`_parse_t12_currency` from
  `t12_import.py` (imported, not copied).
- Adds a `_row_monthly_values(row, column_mapping)` helper next to the existing
  `_row_annual_total` — same column mapping, returns `{month_id: float|None}` instead
  of a single sum, so a genuinely messy file (say, only 9 of 12 months present, or a
  Total column but no month columns) degrades to "annual only, monthly breakdown
  partially unavailable" instead of failing outright.
- Adds one label-alias list per category, same alias-list style as
  `_RENTAL_INCOME_LABEL_ALIASES`:
  - `gross_potential_rent`: reuses the *allow* side of the existing
    `_POTENTIAL_INCOME_WORDS` vocabulary ("gross potential rent", "potential rent",
    "scheduled gross income", "market rent income")
  - `rental_income_collected`: same alias list `t12_import.py` already has
  - `concessions`: "concessions", "rent concessions", "loss to lease - concessions"
  - `vacancy_loss`: "vacancy loss", "vacancy", "loss to vacancy" (kept distinct from
    "loss to lease" — not a vacancy synonym)
  - `bad_debt`: "bad debt", "bad debt expense", "collection loss", "uncollectible rent"
  - `other_income`: "other income", "miscellaneous income", "ancillary income"
- Each row match also tries a **subtotal-tolerant** scan: if a category's exact label
  isn't found but the file has e.g. "Total Income" as a subtotal directly below a
  block of income sub-lines, the parser does NOT try to guess-sum sub-lines (too
  fragile across arbitrary layouts) — a category with no matching row simply comes
  back `None` for that category, surfaced honestly in the report ("not found on this
  T-12") rather than guessed.
- Returns one dict per category:
  `{monthly: {jan: float|None, ..., dec: float|None}, annual: float|None,
  source: {row, file, quote} | None}`.
- Raises the existing `T12ImportError` only for total failure (no usable header row
  at all) — a partially-parseable file (some categories found, some not) returns
  `None` per missing category rather than failing the whole upload, matching this
  codebase's "None means not enough data, never a guessed zero" rule.
- **PDF path**: `pdfplumber` table extraction first (T-12 PDFs exported from property
  software are usually real tables); if no table is extracted, falls back to
  `pytesseract` OCR reconstruction the same way `pdf_extractor.py` does for scanned
  lease PDFs. This is genuinely the hardest input format for a T-12 (no fixed
  layout, and OCR'd numbers in a grid are the easiest thing to misread) — the plan is
  to raise `T12ImportError` with a specific, actionable message rather than silently
  returning wrong numbers if OCR confidence is low or column alignment can't be
  reconstructed. I'd rather ship "PDF sometimes says 'couldn't parse this reliably,
  try CSV/XLSX'" than a plausible-looking wrong number in a document a lender sees.

## 2. Backend: new detectors in `deal_mismatch.py`

Four new detector functions, following the existing `detect_*(leases) -> List[Dict]`
shape but taking `(leases, t12_data, property_address, materiality_pct)` — they
return `[]` immediately if no T-12 was uploaded, so the whole section is silently
absent from a report with no T-12 file, exactly like `concession_missing` returns
`[]` today when its precondition isn't met.

New constant: `_T12_MATERIALITY_THRESHOLD_PCT_DEFAULT = 3.0` (separate from
`portfolio.py`'s existing fixed `_T12_DISAGREEMENT_TOLERANCE_PCT` — not shared,
since that one is a different check with its own established behavior I'm not
touching).

- `detect_t12_income_gap`: rent roll's building-level annualized rent (same
  `_normalize_building_address` grouping `compute_t12_reconciliation` already uses)
  vs. T-12 `rental_income_collected.annual`. Flagged when the rent roll is above T-12
  collections by more than `materiality_pct` (default 3%). `income_direction` is
  always `"overstate"` when flagged (rent roll claims more than was actually
  collected) — this is the check that drives the headline number.
- `detect_t12_occupancy_mismatch`: rent-roll-implied occupancy (occupied units with a
  real tenant / total rent-roll units at that building) vs. T-12-implied occupancy
  (`1 - vacancy_loss.annual / gross_potential_rent.annual`, only computed when both
  are present — `None` otherwise, never a guessed ratio). Flagged past
  `materiality_pct` on the percentage-point gap.
- `detect_t12_concession_gap`: reports the T-12's `concessions.annual` figure with
  `rent_roll_value: None` and an explanatory note that it's unverifiable against the
  rent roll (see scope call #2 above) — always `income_direction: None`, since there's
  no defensible direction without a rent-roll-side number.
- `detect_t12_bad_debt_trend`: building-level, from `bad_debt.monthly` alone — flags a
  sustained upward trend (e.g. last 3 months' average bad debt notably higher than
  the trailing-12 average) alongside the rent roll showing no vacant/non-current
  units at that building, with the plain-English note described in scope call #3.

All four get added to `DISCREPANCY_TYPES` and `_DETECTORS`, called from
`build_deal_mismatch_report_data` only when a T-12 was supplied. New top-level
fields on the returned dict:

- `"t12_source"`: filename + which categories were found vs. missing, so the report
  is explicit about what it could and couldn't read off the file.
- `"rent_roll_vs_actual_collections"`: the section itself — the four checks' rows
  plus their own subtotal.
- `"estimated_income_overstatement_from_t12"`: the headline number — annual dollar
  amount by which in-place income is overstated based on *actual T-12 collections*
  specifically (kept separate from the existing `annual_income_overstatement` field,
  which is rent roll vs. lease PDFs — a different comparison, deliberately not
  merged into one number that would conflate two different sources of truth).

## 3. Backend: routes (`api.py`)

Extends the three existing routes exactly the way their own docstrings already
say they will ("Phase 3 (T12 cross-check) extends this same route to optionally
accept a t12_file"):

- `POST /portfolio/deal-mismatch-report`, `.pdf`, `.xlsx` all gain two optional
  fields: `t12_file` (csv/xlsx/pdf, only meaningful alongside `property_address` —
  same "T-12 covers one building" rule `investment_memo.py`'s t12 handling already
  enforces) and `materiality_threshold_pct` (float, default 3.0).
- Same `@require_role('analyst')` already on all three — unchanged.
- File validation follows the existing `portfolio_t12_reconciliation` pattern: key
  `request.files['t12_file']`, extension allowlist extended to include `pdf`, 400 on
  wrong type, 400 if `t12_file` given without `property_address`, existing global
  16MB `MAX_CONTENT_LENGTH` applies (no new limit needed).
- Parse errors (`T12ImportError`) return 400 with the parser's own message — not
  swallowed, not silently degraded to "no T-12 section."

## 4. Backend: exports (`deal_mismatch_export.py`)

New "Rent Roll vs Actual Collections" section, rendered only when
`rent_roll_vs_actual_collections` is present in the data:

- **PDF**: new flowables block after the existing Discrepancies table, same
  `_styles`/`_SEVERITY_COLORS` conventions, headline number in bold at the top of
  this section (separate from — not replacing — the existing top summary).
- **Excel**: new rows appended below the existing sheet content (not a second sheet
  — keeps the "one document a buyer/lender opens" framing this whole feature exists
  for), headline as its own bold row, then a small table for the four checks.

## 5. Frontend (`frontend/app/deal-mismatch-view.js`)

No T-12 upload UI currently exists anywhere in the frontend for this report (checked
— the standalone `/portfolio/t12-reconciliation` endpoint doesn't have a frontend
view either). To make this reachable at all without shelling out to curl:

- Add an optional file input (`t12_file`) and materiality-threshold number input to
  the existing report-generation form, and render the new section (headline number +
  four-row breakdown) when the API response includes it.
- I will build and verify this against the API responses/fixtures directly — per your
  instruction, I will **not** open localhost in a browser. I'll ask you to click
  through it once it's live if you want visual confirmation beyond what I can verify
  from code and tests.

## 6. Tests

New `backend/tests/test_t12_statement.py` (parser-level, mirrors
`test_t12_import.py`'s `_csv_bytes()`/`_xlsx_bytes()` in-memory fixture pattern):

- Clean file: all 6 categories, all 12 months present, Total column.
- Months-only file: no Total column, all 12 months (sum path).
- Partial file: some categories present, some missing → `None` per missing category,
  not a hard failure.
- Renamed line items: alternate real-world labels per category (e.g. "Loss to
  Lease-Vacancy" instead of "Vacancy Loss", "Uncollectible Rent" instead of "Bad
  Debt") to prove the alias matching, not just the happy-path label.
- Subtotal noise: extra subtotal/blank rows interspersed, proving they're ignored
  rather than mismatched.
- Decorative header block before the real header row (reuses the existing
  `_find_t12_header_row` tolerance — proves it still works with 6 categories instead
  of 1).
- PDF: a simple reportlab-generated table-based T-12 PDF (reportlab's already a
  dependency via `deal_mismatch_export.py`) as the "clean PDF" case, plus a test
  asserting a garbled/unreadable PDF raises `T12ImportError` with a useful message
  rather than returning wrong numbers.

New `backend/tests/test_deal_mismatch_t12.py` (detector + report-assembly level,
mirrors `test_deal_mismatch.py`'s fixture-building helpers):

- Each of the 4 detectors independently, with realistic rent-roll + T-12 fixture
  pairs (materially-over case, within-tolerance case, missing-data case per detector).
- `materiality_threshold_pct` adjustability: same fixture flagged at 3% default,
  not flagged at 10%.
- Headline number computation, and that it stays `None` (not 0) when there isn't
  enough matched data, consistent with the rest of this module's convention.
- No-T-12-uploaded case: report generates normally, new section entirely absent.
- Route-level test extending `test_t12_reconciliation_api.py`'s
  `_authed_client()`/role-check pattern: a non-analyst role gets 403 on the extended
  routes, same as every other analyst-gated route already covered there.

## Order of work

1. `t12_statement.py` parser + its tests (self-contained, no route/detector
   dependencies yet).
2. Four detectors in `deal_mismatch.py` + headline number + their tests.
3. Route changes in `api.py` + route-level tests.
4. Export sections (PDF + Excel).
5. Frontend upload control + section rendering.
6. Full test suite run; plain-English summary of what changed for you.

Waiting for your go-ahead (or corrections, especially on the three flagged scope
calls) before writing any code.
