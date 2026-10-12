# Plan: feature/s8-sample-data (T13)

## Goal

With `SECTION8_MODE` on, a brand-new team clicks **Load Sample Deal** and gets a complete fictional Section 8 portfolio. No AI call is made and nothing is uploaded. The portfolio contains:

- Juniper Row (HCV) and Bellmont Terrace (PBV + PBRA), with their PHA.
- The 10 voucher leases, the 5 HAP contracts and both October rent rolls as documents.
- The matching Section 8 records: properties, units, tenancies, HAP contracts and document links.

The demo deployment (`DEMO_MODE`) seeds the same portfolio when the flag is on. With the flag **off**, nothing changes: Maple Ridge loads exactly as today, and the demo seeds the same coffee-shop/office leases.

## Prior art (searches run 2026-10-12)

The searches covered:
- TASKS.md: "sample", "T13", "DEMO_MODE".
- `git log --all -i --grep` "s8-sample | sample portfolio | section 8 sample".
- Branch names containing "sample".
- `git grep` for `sample_deal`, `demo_seed`, `/sample-deal`, `/leases/sample`, `DEMO_MODE` on main and T1.

| Where | What | How this plan uses it |
|---|---|---|
| `main` `app/sample_deal.py` + `POST /sample-deal/load` | Inserts precomputed Maple Ridge rows (`benchmark_data/demo_deal/precomputed_sample_deal.json`) into the caller's team. No extraction. | **Same pattern:** a precomputed JSON and plain `insert_lease` calls. The route branches on the flag; the Maple Ridge path is unchanged. |
| `main` `app/demo_seed.py` | `seed_demo_data()` (flock-guarded, idempotent) and `reset_demo_data()` (wipes `_CONTENT_TABLES`) | Seed branches on the flag. Reset also wipes the Section 8 tables, children before parents, so a reset never leaves orphaned rows. |
| `feature/s8-data-model` (T1, Ready, **unmerged**) | `section8_mode_enabled()`, team-scoped `phas/properties/units/tenancies/hap_contracts/unit_documents`, `database.create_section8_record` | **Built on directly:** this branch is cut from T1's tip `b6caf9a`. All Section 8 rows go through T1's own create functions and validation. No new tables. |
| `main` `backend/tests/fixtures/section8/` (P4, merged `e0341a6`) | Fictional fixture PDFs, rent rolls and generator data (`UNITS`, `PROPS`, `PHA`, contracts) | **The source documents.** A capture script reads them and writes the precomputed JSON, so the sample cannot drift from the graded answer key. |
| No T13 work found on any branch or stash | — | — |

## Approach

1. **Capture script:** `backend/benchmark_data/section8_sample/capture_section8_sample.py`. It writes `precomputed_section8_sample.json`, which is committed.
   - **Documents.** It runs the app's **regex** engine on the fixture files: the 10 lease PDFs, the 5 HAP contract PDFs, and the October AppFolio and RealPage rent rolls. The pipeline is the same one the real upload routes use (`PDFExtractor` + `FieldExtractor`, `rent_roll_import`). The script keeps each resulting row's `extracted_fields`, `document_type`, `display_name` and page range, the same shape as the Maple Ridge fixture. Anthropic is never called; the script forces the regex engine.
   - **Records.** It builds the Section 8 rows from the fixture generator's data, in plain dollars, which become cents at load time through T1's `dollars_to_cents`:
     - **PHA:** 1 (Harrow County HA). The PBRA contract administrator is noted on the contract, not added as a PHA.
     - **Properties:** 2.
     - **Units:** 32, with status occupied, vacant or unknown.
     - **Tenancies:** current ones carry contract rent, tenant share and HAP as the **October rent roll shows them**, i.e. what the seller's own system says, planted errors included. That way the T3/T5 checks have something real to find. Unit 112 becomes a **past** tenancy with move-out 2026-08-31.
     - **HAP contracts:** 3 HCV, one per tenancy. The PBV contract becomes one row per Exhibit A unit, sharing the contract number, so each unit's contract rent can be stored. The PBRA contract becomes one row per unit, `status: active` as the documents state it; its end date of 08/31/2026 is what a later check should catch.
     - **Document links:** `unit_documents` links each lease, HAP contract and rent-roll row to its unit and tenancy, with doc kinds `lease`, `hap_contract` and `rent_roll_row`.
   - **Hashes.** The JSON records the sha256 of every fixture file it read.
2. **`app/sample_deal.py`:** add `load_section8_sample(team_id)`.
   - It refuses with **409 "Sample portfolio already loaded"** if the team already has a property at a sample address. T1's tables are unique on `(team_id, normalized_address)`, so a second load could not succeed anyway; a clear 409 is better than a half-load.
   - It inserts the leases, then the records in dependency order, mapping fixture keys to the new ids.
   - Leases are tagged `Sample`, like `/leases/sample` does today.
   - It returns counts.
3. **`POST /sample-deal/load`:** flag on → Section 8 loader, flag off → Maple Ridge, unchanged.
   - The JSON response gains `sample_name`. This is additive; existing keys are unchanged.
   - The activity text names the portfolio actually loaded.
   - Role stays `@require_role('analyst')` and all writes use the caller's `team_id`.
4. **`app/demo_seed.py`:**
   - Seed: flag on → seed the Section 8 portfolio into the Legacy team, flag off → today's leases. The flock and the "already seeded" check are kept. The check also counts Section 8 properties, so a restart doesn't double-seed.
   - Reset: wipe the six Section 8 tables, children first, before the existing content tables.
5. **Frontend (one line):** the success toast says `"<sample_name> loaded."` from the response, falling back to today's text, instead of hard-coding "Maple Ridge sample deal loaded." The button label and nav stay unchanged; renames belong to T12.

## Files to change

- New: `backend/benchmark_data/section8_sample/capture_section8_sample.py`, `precomputed_section8_sample.json`, `README.md`.
- Edit: `backend/app/sample_deal.py`, `backend/app/api.py` (only the `/sample-deal/load` handler), `backend/app/demo_seed.py`, `frontend/app/dashboard-view.js` (toast text only).
- New: `backend/tests/test_section8_sample_data.py`.
- Edit: `backend/tests/test_team_isolation.py` (new case).
- Edit: `backend/tests/run_all_tests.py` (register the new test).

## Files not to touch

- `database.py` schema: T1 owns it, and no new tables or columns are needed.
- Brand files (pivot constraint 1).
- `render.yaml` and Render env vars.
- `/leases/sample` (see the open question).
- The fixture set itself.
- Maple Ridge files.
- Every other route.

## Team isolation & roles

- `POST /sample-deal/load` keeps `@require_role('analyst')`. Every insert passes the authenticated caller's `current_team_id()`. Cross-row references (unit→property, tenancy→unit, …) only ever point at ids created in the same call for the same team, and still go through T1's `require_own` checks via its create path.
- `demo_seed` writes only to the demo deployment's Legacy team, as today.
- **New `test_team_isolation.py` case:** team A loads the Section 8 sample, then team B sees zero rows in every `/section8/*` list and zero sample leases, and can't fetch A's ids (404).

## Feature flag

`SECTION8_MODE` (T1's helper, default **off**). No new flag. With it off, behaviour is byte-for-byte today's.

## Verification

`test_section8_sample_data.py` covers the following, with Anthropic never called (asserted by patching the client to raise):
- **Flag off:** `/sample-deal/load` loads Maple Ridge with the same lease count as today, and creates no Section 8 rows.
- **Flag on:** expected counts of leases, PHAs, properties, units, tenancies (current and past) and HAP contracts.
- **Planted values survive into the records** (cross-checked against `answer_key.json`):
  - JR 104 tenancy contract rent is $1,295 against HAP contract rent of $1,250 (S8-06).
  - JR 206 tenancy HAP is $1,050 (S8-03).
  - JR 112 tenancy is `past` with move-out 2026-08-31 (S8-17).
  - The PBRA contract end date is 2026-08-31 (S8-08).
- **Second load:** returns 409 and inserts nothing new.
- **Viewer role:** gets 403.
- **Demo seed:** `seed_demo_data()` with `DEMO_MODE` + `SECTION8_MODE` seeds the portfolio, and running it twice is a no-op. `reset_demo_data()` empties the Section 8 tables and reseeds.
- **Precomputed JSON is in sync:** its recorded sha256s match the current fixture files, so regenerating the fixtures forces a recapture.

Full suite run in this worktree. UI: headless screenshots of the dashboard empty state and the toast after loading, flag on and off, at 1440/768/375.

## Out of scope

- Detectors and reconciliation (T3/T5).
- Importing PHA registers or inspections into tables. Those tables don't exist yet; T4 and T6 extend this loader when they land, and the README will say so.
- Button and nav renames (T12).
- Marketing copy (T11).
- Re-capturing Maple Ridge.

## Open questions

1. **Base branch.** This branch sits on T1 (`feature/s8-data-model`, unmerged) with `main` merged in, so it can only merge **after** T1. If T1 changes in review, I'll merge its new tip in. OK?
2. **`/leases/sample`** (the single "try a sample lease" button) still returns the commercial sample lease with the flag on. Switch it to one voucher lease (Juniper Row 214, the clean control) in this task, or leave it for T12? I'd do it here: it's about 10 lines, and the same pattern.
3. **Rent-roll capture uses `main`'s importer.** The Section 8 tenant-share/HAP column support lives on unmerged `qa/overnight-gauntlet` (P2), so the captured rent-roll rows read "Rent"/"Contract Rent" only. That's fine for loading; the capture script can be re-run after P2 merges. OK?
