# Plan: feature/s8-data-model (T1 of the Section 8 pivot)

## Goal

Give Abstractly the records a Section 8 operator thinks in, so every later Section 8 feature has somewhere to put its data:
- properties
- units
- housing authorities (PHAs)
- tenancies (who lives in a unit, under which PHA, at what contract rent / tenant share / HAP)
- HAP contracts
- the link from each uploaded document to the unit it belongs to

Today a "unit" exists only as an address string inside a lease's JSON.

The branch adds those tables (team-scoped), a small set of create/read/update API routes and a helper that groups a team's existing uploads into properties and units. All of it sits behind a new `SECTION8_MODE` flag that defaults to **off**: with the flag off, nothing a user or tester sees changes. There is no UI on this branch; later tasks (T4–T10, T12) build on it.

Source: `PIVOT_PLAN.md` Step 4, T1 (branch `pivot/section8`, approved 2026-10-11).

## Prior art (searches run 2026-10-11)

- `git log --all -S` for `hap_contracts`, `CREATE TABLE units`, `CREATE TABLE properties`, `CREATE TABLE phas`, `tenancies`, `SECTION8_MODE`, `unit_documents`. The only hits are the pivot plan / TASKS and the `qa/section8-fixtures` file names (PDF fixtures named `hap_contract_*`). **No existing schema anywhere.**
- `TASKS.md`: T1 is queued under "Section 8 pivot"; nobody else holds it.
- Stashes: nothing relevant.
- **Builds on:**
  - `main`'s team-isolation pattern: `team_id` on every document table, `current_team_id()`, by-id lookups that return 404 across teams, and the `tests/test_team_isolation.py` two-team harness.
  - `portfolio._normalize_address` (unit-level) and `_normalize_building_address` (building-level) for the backfill grouping. No new normalizer is written.
- **Coexists with, no overlap:**
  - `fix/section8-tenant-share` (other session) adds `leases.source_kind` and a `rent_roll_unit_summaries` table in `database.py`, in different places. Expect a mechanical merge in `database.py`'s `init_db`. Once it lands, backfill should prefer `source_kind` over the filename-extension rule (noted as a follow-up, not done here).
  - `feature/s8-hud-data` creates the package `app/section8/`. To avoid an add/add conflict on `app/section8/__init__.py`, this branch uses **flat modules** (`app/section8_mode.py`, `app/section8_records.py`) rather than putting files in that package.
  - `qa/section8-fixtures` (data only) is used as the reference for real field shapes: HCV per-unit HAP contracts, a PBV contract and a PBRA contract covering several units, 3 PHAs' worth of registers. Not imported by tests here.

## Approach

1. **Flag.** `app/section8_mode.py`: `section8_mode_enabled()` reads `SECTION8_MODE` on every call (truthy `1/true/yes/on`, default off), the same as `SELF_SERVE_SIGNUP_ENABLED`. A `require_section8_mode` decorator returns **404** when the flag is off, so routes look like they don't exist.
2. **Schema** (`database.init_db`, `CREATE TABLE IF NOT EXISTS`, additive only, no change to existing tables).
   - Tables are always created; the flag gates routes only, so empty tables are harmless.
   - Every table has `team_id INTEGER NOT NULL REFERENCES teams(id)`, `created_at`, `updated_at` and `archived_at` (NULL = live).
   - Money is stored as **integer cents** (`*_cents`) to avoid float drift. Dates are ISO `YYYY-MM-DD` text.

   | Table | Columns (beyond the common ones) | Uniqueness |
   |---|---|---|
   | `phas` | name, short_name, jurisdiction, inspection_standard (`HQS`/`NSPIRE-V`/`NSPIRE`/NULL), payment_day (1–31), rent_increase_notice_days, settings_json (future per-PHA deadline defaults), portal_url, contact_name, contact_email, contact_phone, notes | (team_id, name) |
   | `properties` | name, address, normalized_address (building-level), program (`HCV`/`PBV`/`PBRA`/`mixed`/`market`), default_pha_id → phas, notes | (team_id, normalized_address) |
   | `units` | property_id → properties, unit_label, normalized_address (unit-level, same key as `_normalize_address`), bedrooms, status (`occupied`/`vacant`/`down`/`unknown`) | (team_id, normalized_address) |
   | `tenancies` | unit_id → units, head_of_household, household_size, pha_id → phas, program (`HCV`/`PBV`/`PBRA`/`market`), voucher_bedrooms, move_in_date, move_out_date, contract_rent_cents, tenant_rent_cents, hap_cents, utility_allowance_cents, amounts_effective_date, source_lease_id (→ leases.id, deliberately **not** FK'd, same reasoning as `tasks.lease_id`), status (`current`/`past`) | at most one `current` tenancy per unit (enforced in code + partial unique index) |
   | `hap_contracts` | pha_id → phas, contract_type (`HCV`/`PBV`/`PBRA`), contract_number, form (free text, e.g. `HUD-52641`), property_id → properties (PBV/PBRA), unit_id → units (HCV), tenancy_id → tenancies (HCV), start_date, end_date, contract_rent_cents (HCV), initial_hap_cents, source_lease_id (not FK'd), status (`active`/`expired`/`terminated`) | none (numbers repeat across PHAs) |
   | `unit_documents` | lease_id (→ leases.id, not FK'd), unit_id → units, tenancy_id, pha_id, hap_contract_id (all nullable except unit_id), doc_kind (`lease`/`tenancy_addendum`/`hap_contract`/`pha_notice`/`inspection_report`/`payment_register`/`rent_roll_row`/`other`), linked_by (`backfill`/`user`) | (team_id, lease_id, unit_id) |

   Indexes on `team_id` and every foreign-key column.
3. **Cross-team reference guard.** SQLite FKs prove a referenced row *exists*, not that it's the *same team's*. Every create/update validates each referenced id (pha_id, property_id, unit_id, tenancy_id, hap_contract_id, lease_id) with a team-scoped lookup first. A foreign id gets **404**, matching how `POST /tasks` treats a foreign `lease_id`. One helper, `_require_own(kind, id, team_id)`, so no route can skip it.
4. **Data access** (`database.py`, house style, `team_id` a required argument everywhere). *Built as one shared set rather than per-table functions:* `create_section8_record(table, team_id, values)`, `get_section8_record(table, id, team_id)`, `list_section8_records(table, team_id, filters, include_archived)` and `update_section8_record(table, id, team_id, values, archived)`. `SECTION8_COLUMNS` / `SECTION8_LIST_FILTERS` are fixed allow-lists, so a table or column name never comes from a request. Updates use that column allow-list, never `**body`. No hard deletes: archiving sets `archived_at` and un-archiving clears it.
5. **Domain helpers** (`app/section8_records.py`):
   - Input validation: enums, ISO dates, dollars to cents (rejects negatives, NaN and more than 2 decimals), payment_day range.
   - JSON shaping for API responses: cents → dollars as strings `"1400.00"`.
   - "Single current tenancy" rule: creating a second current tenancy for a unit returns 409 unless the request also ends the old one.
   - Backfill (step 7).
6. **Routes** (`api.py`, all under `/section8/`, all `@require_role(...)` + `@require_section8_mode`, all team-scoped via `current_team_id()`):

   | Method | Path | Role | Notes |
   |---|---|---|---|
   | GET / POST | `/section8/phas` | viewer / analyst | List / create |
   | GET / PATCH | `/section8/phas/<id>` | viewer / analyst | PATCH includes `archived: true/false` |
   | GET / POST | `/section8/properties` | viewer / analyst | |
   | GET / PATCH | `/section8/properties/<id>` | viewer / analyst | GET includes unit count |
   | GET / POST | `/section8/units` | viewer / analyst | `?property_id=` filter |
   | GET / PATCH | `/section8/units/<id>` | viewer / analyst | GET includes current tenancy, HAP contracts, linked documents (id, filename, doc_kind) |
   | GET / POST | `/section8/tenancies` | viewer / analyst | `?unit_id=`, `?pha_id=`, `?status=` |
   | GET / PATCH | `/section8/tenancies/<id>` | viewer / analyst | |
   | GET / POST | `/section8/hap-contracts` | viewer / analyst | `?pha_id=`, `?property_id=`, `?unit_id=` |
   | GET / PATCH | `/section8/hap-contracts/<id>` | viewer / analyst | |
   | POST | `/section8/units/<id>/documents` | analyst | Link an existing upload (`lease_id`, `doc_kind`) to the unit |
   | PATCH | `/section8/unit-documents/<id>` | analyst | Change doc_kind / tenancy / HAP contract, or archive the link |
   | POST | `/section8/backfill` | **admin** | Body `{"apply": false}` (default = dry run) |

   **No DELETE routes** (pivot constraint: deprecate, don't delete).
7. **Backfill** (`POST /section8/backfill`) reads the caller's team's live, non-amendment `leases` rows.
   - **Grouping:** building key = `_normalize_building_address`, unit key = `_normalize_address`.
   - **Unit label:** the `unit_number` field (lease-intelligence, once merged), else the suite/unit designator matched in the address, else the full address.
   - **Rent roll vs lease:** decided by `portfolio._is_rent_roll_import` (doc_kind `rent_roll_row` vs `lease`).
   - **Dry run** returns `{properties: [...], units: [...], links: N, skipped: [{lease_id, reason}]}` and writes nothing.
   - **Unit status:** every backfilled unit is created with status **`unknown`**, never `occupied`. main's importer skips vacant rows, so a rent-roll row isn't proof of occupancy. This holds until `fix/section8-tenant-share` (which records vacant/down units) merges. *(User decision 2026-10-11.)*
   - **`apply: true`** creates only what's missing (idempotent: a second run creates nothing), links documents with `linked_by='backfill'`, and **never modifies `leases` rows**. It creates no PHAs, tenancies or HAP contracts; those need extraction (T2/T3).
   - Rows with no address are skipped with a reason.
   - Logged to `activity_log` under the caller's team.
8. **Tests** (see Verification). Register new files in `run_all_tests.py`.

## Files to change

- `backend/app/section8_mode.py` (new): flag + decorator
- `backend/app/section8_records.py` (new): validation, shaping, backfill
- `backend/app/database.py`: 6 `CREATE TABLE`s + indexes in `init_db`, CRUD functions in a new `# Section 8 records` section at the end
- `backend/app/api.py`: the routes above, in one new block
- `backend/tests/test_section8_data_model.py` (new)
- `backend/tests/test_team_isolation.py`: add Section 8 cases to the two-team harness
- `backend/tests/run_all_tests.py`: register the new file
- `backend/.env.example`: document `SECTION8_MODE=` (commented, off)
- `docs/plans/feature-s8-data-model.md` (this file)

## Files not to touch

- Any frontend file. This branch has no UI.
- `render.yaml` and Render env vars. The user flips `SECTION8_MODE` in the dashboard.
- Existing tables' columns, existing queries, `rent_roll_import.py`, `deal_mismatch*.py`, `portfolio.py` (imported from, not edited), and the brand files.
- `app/section8/` (owned by `feature/s8-hud-data`).

## Team isolation & roles

- **Every table:** `team_id NOT NULL`.
- **Every query:** includes `AND team_id = ?` with `current_team_id()`. By-id reads and updates return **404** across teams, never 403.
- **Every referenced id in a request body:** checked against the caller's team before use (step 3).
- **Lists:** filter by team before any other filter.
- **Backfill:** reads only `list_leases(team_id=…)`.
- **Roles:**
  - viewer: read
  - analyst: create/update/link
  - admin: backfill
  - `require_owner` is not involved.
- **New `test_team_isolation.py` cases**, run with the flag on:
  - Team B can't GET, PATCH or list Team A's phas/properties/units/tenancies/hap-contracts/unit-documents.
  - Team B can't create a unit under Team A's property, a tenancy under Team A's unit or PHA, or a HAP contract under Team A's PHA. It also can't link Team A's `lease_id` to its own unit.
  - Team B's backfill never creates rows from Team A's leases.

## Feature flag

`SECTION8_MODE` (env var, default **off**). With it off:
- every `/section8/*` route returns 404;
- the tables exist but stay empty;
- no existing behavior changes.

Later tasks reuse the same helper. The flag is not added to `render.yaml`. The user turns it on for the tester service in the Render dashboard when there's something to see.

## Verification

- `test_section8_data_model.py` (temp SQLite, Flask test client, no network, no Anthropic):
  - **Flag:** off → each route 404s; on → it works.
  - **Roles:** viewer → 403 on POST/PATCH; analyst → 403 on backfill.
  - **CRUD round trip** for each table. Money in dollars → stored cents → returned `"1400.00"`. Rejects negative, NaN and 3-decimal amounts, bad dates, bad enums, payment_day 0/32.
  - **Uniqueness:** duplicate PHA name / property address / unit address → 409; second current tenancy → 409.
  - **Archive** hides from lists, `?include_archived=1` shows it, un-archive restores it. No DELETE route exists (405).
  - **Backfill:**
    - dry run writes nothing;
    - apply creates the expected properties/units from a seeded mix (2 buildings, 5 units, lease PDFs + rent-roll rows, one address-less row skipped);
    - re-run is a no-op;
    - `leases` rows are byte-identical before and after.
  - **Unit GET** shows the current tenancy, contracts and linked documents.
- `test_team_isolation.py` additions as listed above.
- **Full suite in a clean worktree:** `python backend/tests/run_all_tests.py`, quoted count. Expected baseline: main's current count + 1 new file, with only the known OCR failures (if tesseract/poppler are absent).
- No UI, so no screenshots (DoD line n/a).

## Out of scope

- **Any UI:** unit page, PHA settings, nav (T9/T12).
- **Filling tenancies, PHAs or HAP contracts from extracted fields** (T2/T3). Backfill makes only properties, units and links.
- **PBV/PBRA per-unit contract schedules** (a `hap_contract_units` table). Expected HAP per unit comes from `tenancies.hap_cents`. Add the table when T5/T8 needs it.
- **HAP payments, inspections, recerts, rent-increase tables** (T4, T6, T7, T8 add their own).
- **Using `leases.source_kind`** for backfill. A follow-up once `fix/section8-tenant-share` merges.
- **Hard delete, team export of these tables** (AUDIT.md §5.2 item, separate task).
- **Changing CLAUDE.md** (`docs/claude-md-tenancy` owns that).

## Open questions

1. **Route prefix** `/section8/…`: fine, or prefer something shorter? (Doesn't affect anything user-visible yet.)
2. **Backfill role:** admin-only (proposed, since it creates many rows at once), or analyst too?
3. ~~Unit status from rent-roll vacancy~~ **Decided 2026-10-11:** backfilled units are always `unknown` until the tenant-share fix lands.

Q1 (prefix `/section8/`) and Q2 (backfill admin-only) were approved as proposed.
