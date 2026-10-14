# Plan: feature/s8-hap-payment-import (T4)

## Goal

With `SECTION8_MODE` on, an analyst uploads a housing authority's HAP payment register and gets one stored row per unit payment line. Formats: the CSV/XLSX export or the PDF statement. Each row carries:
- period, PHA, unit, tenant name;
- contract rent, HAP amount, adjustment and net paid;
- a payment type: regular, adjustment, abatement, proration, termination, hold or unknown.

Each row is matched to the team's Section 8 unit and current tenancy where possible. Unmatched lines are listed for the user to assign. This is the "what the PHA actually paid" half of HAP reconciliation; T5 compares it to what was expected. **Data only, no UI** beyond the API, which T5/T10 present.

## Prior art (searched 2026-10-13)

The searches covered:
- TASKS.md: "hap_payments", "payment register", "T4".
- `git log --all -i --grep` "hap_payments | payment register".
- Branch names containing "payment".

| Where | What | How this plan uses it |
|---|---|---|
| None found | No register parsing or `hap_payments` table on any branch | — |
| `feature/s8-data-model` (T1, unmerged) | Team-scoped `phas`/`units`/`tenancies` + `section8_records` validation, `/section8/*` route patterns, `SECTION8_MODE` helper | **Built on directly.** The branch is stacked on T1 with `main` merged in (`0da9450`). New table and routes follow T1's conventions: `team_id NOT NULL`, money in integer cents, archive not delete, `require_own` refs, `@require_section8_mode` outermost. |
| `main` `normalize.py` | `normalize_header`, `parse_currency` (incl. comma-decimal and negatives), `parse_date`, `decode_text_upload` | Reused as-is. |
| `main` `rent_roll_table_extract.extract_rent_roll_table` | PDF (text + OCR), XLS and DOCX tables → rows | Reused for the PDF/XLS/DOCX register formats. |
| `main` `rent_roll_import` (gauntlet merged `b63927d`) | Header-row detection, column aliasing, totals/vacant-row skipping | Same *approach* in a new module. Its internals are rent-roll specific and private, so they're not modified. **Known bug to avoid repeating:** it reads a "Total … occupied / … units" row as a tenant (TASKS Up next). The register parser skips totals rows by rule and has a test for it. |
| `main` `portfolio._normalize_address` | Unit-level address match key | Used to match register lines to `units.normalized_address`. |
| `backend/tests/fixtures/section8/hap_registers/` (P4, merged) | Aug/Sep/Oct 2026 registers, CSV + PDF, with shortfall, missing payment, `ABT`/`TRM`/`HLD`/`RTA`/`INT` codes | **The test bed.** Tests assert every row, type and planted absence against the generator's data. |

## Approach

1. **Schema** (additive, in T4's own migration block per the pivot's collision rule).
   - **`hap_payment_imports`:** one row per uploaded register.
     - Columns: `id, team_id NOT NULL, pha_id → phas, filename, file_sha256, period (YYYY-MM), payment_date, row_count, matched_count, unmatched_count, skipped_count, status (active|superseded), superseded_by, created_by, created_at, archived_at`.
     - The file itself is **not** kept, as with every upload today.
   - **`hap_payments`:** one row per payment line.
     - Columns: `id, team_id NOT NULL, import_id → hap_payment_imports, pha_id, period, payment_date, unit_id → units (nullable), tenancy_id → tenancies (nullable), match_status (matched|unmatched|manual), head_of_household, unit_label_raw, unit_address_raw, contract_number, program, contract_rent_cents, hap_cents, adjustment_cents, net_paid_cents, adjustment_code, payment_type, memo, created_at, updated_at, archived_at`.
   - **Not stored**, per Q5 data minimization: the PHA client/case ID and payee vendor ID. They are used in memory only, for matching and for the duplicate check, then dropped.
2. **Parser** (`app/section8_hap_payments.py`):
   - **Input:** CSV/TSV via `decode_text_upload`; XLSX via openpyxl (first sheet with a recognisable header); PDF/XLS/DOCX via `extract_rent_roll_table`.
   - **Header detection:** the first row that has a unit or address column *and* a HAP or net-paid column.
   - **Column aliases** for common PHA exports: unit / unit address / address; tenant / head of household / participant; HAP / HAP amount / housing assistance payment / subsidy; adj / adjustment; net / net payment / amount paid / check amount; and code, memo, contract, program, period, payment date.
   - **Skipped with a reason:** totals/subtotals ("Total", "Payee total", "Grand total"), blank rows, and repeated header rows on later PDF pages.
   - **Period** comes from the payment-date column, the filename (`2026-09`), or an explicit form field, in that order. One import has one period; mixed periods are a 400 with a clear message.
3. **Payment type:**
   - Mapped from the adjustment code through **per-PHA settings** (`phas.settings_json.payment_codes`, Q4 decision) with code defaults: `ABT`→abatement, `RTA`→adjustment, `TRM`→termination, `HLD`→hold, `PRO`→proration, `INT`→regular (memo only).
   - A blank code with no adjustment gives regular. Anything else gives `unknown`; it's stored, and flagged in the import summary.
4. **Matching:** unit address normalized and compared with `units.normalized_address` for the team, among units of properties whose default PHA is this PHA or which have a tenancy with this PHA. The fallback is unit label within a single-property match. If exactly one current tenancy exists on the matched unit, its id is attached. Ambiguous or missing gives `unmatched`. **Never guessed.**
5. **Re-import rule:**
   - Same `file_sha256` for the same team returns **409** "already imported".
   - A different file for the same PHA and period creates a new import and marks the prior one `superseded`. Its rows stay stored but are hidden from default lists. The user is told, in the response, how many rows were replaced.
   - This mirrors the re-import supersede approach the gauntlet decision recorded for rent rolls. If your QA_REPORT decision went the other way, this follows it.
6. **Routes**, all with `@require_section8_mode` outermost then `@require_role`:
   - `POST /section8/hap-payments/import` (analyst): multipart `file`, `pha_id` (required, own team), optional `period`, and `dry_run=1` to preview without writing. Returns the summary, column mapping, skipped rows with reasons and unmatched lines.
   - `GET /section8/hap-payments` (viewer): filters `pha_id`, `unit_id`, `period`, `import_id`, `match_status`, `payment_type`; superseded hidden unless `include_superseded=1`.
   - `GET /section8/hap-payment-imports` (viewer).
   - `PATCH /section8/hap-payments/<id>` (analyst): assign `unit_id`/`tenancy_id` to an unmatched line (own-team refs only; `match_status` becomes manual), or `archived`.
   - `PATCH /section8/hap-payment-imports/<id>` (analyst): `archived` only.
   - **No DELETE routes** (pivot constraint 3).
7. **T13 hook:** none in this branch, since T13 is unmerged. The T13 README already says T4 extends the sample capture to load the three registers. That's a follow-up once both are on `main`.

## Files to change

- New: `backend/app/section8_hap_payments.py`, `backend/tests/test_section8_hap_payments.py`.
- Edit:
  - `backend/app/database.py`: new tables in their own block, CRUD and list functions, `reset_db` drop order.
  - `backend/app/api.py`: the 5 routes.
  - `backend/tests/test_team_isolation.py`: new cases.
  - `backend/tests/run_all_tests.py`.

## Files not to touch

- `rent_roll_import.py`. Its totals-row bug is its own task.
- T1's existing tables and routes.
- Frontend.
- Brand files.
- `render.yaml`.
- The fixture set.

## Team isolation & roles

- Every query includes `team_id = current_team_id()`.
- `pha_id`, `unit_id` and `tenancy_id` go through `section8_records.require_own`. Another team's id is a 404, identical to a missing id.
- Matching only reads the caller's units and tenancies.
- The duplicate-file check is per team: team B can import the same file as team A.
- **New `test_team_isolation.py` cases:**
  - Team B can't list, fetch or patch team A's payments or imports.
  - Team B can't import against team A's PHA (404).
  - Team B can't assign team A's unit to its own payment line (404).
  - Team A's import never matches team B's units.

## Feature flag

`SECTION8_MODE` (T1). Flag off: every new route 404s, logged in or not. The tables are created regardless, empty and harmless (same as T1).

## Verification

`test_section8_hap_payments.py`, with no Anthropic and no network:
- **Fixture registers, CSV *and* PDF**, for all three months. Every line is stored with the generator's exact cents, code and type:
  - Aug: unit 101 `RTA` +$45; **3D absent** (S8-13).
  - Sep: 104 `ABT` −$940 net $0 (S8-14); **108 HAP $873 with no code** (S8-12); 112 paid after move-out (S8-17); 206 `INT` memo.
  - Oct: 210 `TRM` (S8-11); 2A `HLD` (S8-10).
- **Payee-total rows are skipped, not imported.** This is the regression guard against the rent-roll totals-row bug.
- **Matching** against seeded team units: all 14 lines matched. A unit missing from the team gives `unmatched` plus a manual assign via PATCH. An ambiguous address stays unmatched.
- **Re-import:** same file gives 409; a corrected file for the same period supersedes, and default lists show only the new rows. `dry_run` writes nothing.
- **Validation:** mixed periods give 400; a file with no HAP column gives 400 naming what's missing; a bad `pha_id` gives 404.
- **Roles and flag:** viewer can list but gets 403 on import/patch; flag off gives 404 on every route.
- Full suite in the worktree.

## Out of scope

- Expected-vs-received reconciliation and findings (T5).
- Any UI (T5/T10).
- Remittance emails and PHA portal scraping.
- Loading registers into the T13 sample.
- Fixing the rent-roll totals-row bug.
- Masking the `memo` text (T0 adds that at its choke point when both are merged; noted for whichever lands second).

## Open questions

1. **Re-import rule:** supersede the earlier import for the same PHA and period (my default), or refuse and make the user archive the old one first?
2. **Client/case IDs:** I don't store them (Q5 minimization). They'd make matching more robust when a unit address is written oddly. OK to drop them, or store them as an allowed matching key?
