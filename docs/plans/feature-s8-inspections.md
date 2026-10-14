# Plan: feature/s8-inspections (T6)

## Goal

With `SECTION8_MODE` on, an operator can see, for every unit:
- **Inspections:** HQS or NSPIRE-V (voucher) and NSPIRE (multifamily), with each deficiency's severity, **cure deadline**, date corrected, and reinspection dates and results.
- **What's at risk:** overdue cures, a life-threatening item not fixed within 24 hours, a reinspection with no result, and the date HAP abatement is expected to start.

Inspections get in two ways:
- **Manual entry**, always available.
- **Uploading the PHA's inspection report.** The fields are read where the regex engine can; anything it can't read is left for the user to fill in.

Deadlines come from **per-PHA rules** with code defaults (your Q4 decision) and are always labelled "Verify with your PHA". Overdue items create tasks. T5 (HAP reconciliation) reads the expected abatement start, and T10 (This Month) shows the due list.

## Prior art (searched 2026-10-13)

The searches covered:
- TASKS.md: "inspection", "T6".
- `git log --all -i --grep` "inspection_items | s8-inspections".
- Branch names containing "inspection".

| Where | What | How this plan uses it |
|---|---|---|
| None found | No inspection tables, routes or parsing on any branch | — |
| `feature/s8-data-model` (T1, unmerged) | `phas.settings_json` (per-PHA rules), `phas.inspection_standard` (HQS / NSPIRE-V / NSPIRE), units/tenancies, `unit_documents` (`doc_kind` already includes `inspection_report`), `section8_records` validation, route patterns | **Stacked on it** (+ `main` merged, `992e3c6`, same reviewed `database.py` resolution as T4/T13). New tables follow T1's conventions. Uploaded reports are linked to the unit via T1's `unit_documents` (`inspection_report`). |
| `main` `tasks` + `assignments` + `action_items` | Team-scoped tasks with due dates, assignment, the "Today" view | **Overdue/at-risk items create ordinary tasks** linked to the unit, so they show up in the existing Tasks and Today screens with no new surface. |
| `main` `PDFExtractor` / `document_extractor` | Text + OCR from uploads | Reused to read uploaded inspection reports. |
| `backend/tests/fixtures/section8/inspections/` (P4, merged) | HQS (JR 104: fail → failed reinspection → abatement 09/01), NSPIRE-V (Bellmont PBV: LT cured late on 2B, moderate on 2C cured in time), NSPIRE (Bellmont PBRA: repair certification due 09/30 NOT RECEIVED) | **The test bed:** S8-14, S8-15 and S8-16 plus the traps must come out exactly as the answer key says. |
| T4 plan (`feature/s8-hap-payment-import`, unbuilt) | Stores `ABT` abatement lines | T6 provides the *expected* abatement (from inspections); T5 compares it with T4's *received* lines. No dependency between T4 and T6. |

## Approach

1. **Schema** (additive, T6's own migration block; all `team_id NOT NULL`, archive not delete).
   - **`inspections`:**
     - Identity and scope: `id, team_id, unit_id → units` (nullable for site/common-area inspections), `property_id → properties, pha_id → phas`.
     - The inspection: `standard (HQS|NSPIRE-V|NSPIRE), inspection_type (initial|annual|biennial|special|complaint|reinspection|quality_control), inspection_date, result (pass|fail|inconclusive|pending), score` (NSPIRE).
     - Source: `parent_inspection_id` (a reinspection points at the original), `source_lease_id` (the uploaded report's `leases.id`, if any).
     - `notes`, timestamps, `archived_at`.
   - **`inspection_items`:**
     - What: `id, team_id, inspection_id → inspections, unit_id, location, deficiency, severity (life_threatening|severe|moderate|low|24_hour|30_day)`.
     - Dates: `cure_deadline` (stored as computed at entry, with `deadline_rule` recording which rule produced it, e.g. "PHA setting: life_threatening=1 day" or "default"), `corrected_date, verified_date`.
     - `status (open|corrected|verified|waived)`, timestamps, `archived_at`.
2. **Rules** (`app/section8_inspection_rules.py`, Q4):
   - Cure days per severity come from `phas.settings_json.inspection_cure_days`, falling back to code defaults:
     - life-threatening and 24-hour: 1 day;
     - severe: 1 day for NSPIRE multifamily, 30 days for HCV/PBV;
     - moderate and 30-day: 30 days;
     - low: 60 days.
   - Abatement start: the first of the month after a failed reinspection, or after an uncured deadline, from `settings_json.abatement_start` (default "first of next month").
   - Every computed date in the API carries `rule_source` and `verify_with_pha: true`.
   - The defaults are paraphrased and **not practitioner-checked**. Your Q4 launch gate (your Section 8 contacts check them before launch) stands.
3. **Status and risk** (computed on read, not stored, so rule changes apply immediately), as of a date (default today):
   - `overdue` (open item past its deadline), `lt_cured_late` (life-threatening corrected after its deadline), `reinspection_overdue` (a fail with a deadline passed and no later reinspection or certification), `expected_abatement_start` and `abatement_active` per unit.
   - Exposed via `GET /section8/inspections/at-risk?as_of=` and on each inspection's detail.
4. **Tasks:** when an inspection or item is saved, or the at-risk view is computed, every open item with a deadline gets **one** linked task:
   - Due on the deadline, title "Cure: <deficiency> — Unit X", assigned to nobody.
   - It's idempotent (keyed by item id) and closed automatically when the item is marked corrected.
   - This uses `main`'s existing task functions and team scoping.
5. **Report import** (`POST /section8/inspections/import`, analyst; multipart file + `unit_id` or `property_id` + `pha_id`):
   - Reads text with `PDFExtractor` (text + OCR) and parses the common layouts: header fields (type, date, result, score, inspector) and deficiency tables (location, deficiency, severity, correct-by, corrected).
   - Returns a **draft** (`dry_run` default on) for the user to confirm. Only on confirm (`dry_run=0`, or a POST of the edited draft to the create route) are records written.
   - The report is stored like any upload: extracted fields only, the file unlinked. It is linked to the unit via `unit_documents (inspection_report)`.
   - No AI. A layout the regex can't read returns an empty draft with "enter manually", never a guess.
6. **Routes**, `@require_section8_mode` outermost, then `@require_role`:
   - viewer: `GET /section8/inspections` (filters unit/property/pha/result/date range), `GET /section8/inspections/<id>` (with items and computed deadlines), `GET /section8/inspections/at-risk`.
   - analyst: `POST /section8/inspections` (with items), `PATCH /section8/inspections/<id>`, `POST /section8/inspections/<id>/items`, `PATCH /section8/inspection-items/<id>` (correct, verify, waive with note, archive), `POST /section8/inspections/import`.
   - No DELETE routes.
7. **UI: one view, "Inspections"**, at `frontend/app/inspections.html` (same app shell, tokens and components; brand files untouched):
   - The at-risk list first: overdue, life-threatening, abatement.
   - Then all inspections, with a detail drawer to mark items corrected, a manual-entry form, and the import with a draft review.
   - Every rule date shows "Verify with your PHA".
   - **No nav item:** T12 owns nav. The page is reachable at its URL and from T9's unit page when both are in. Hidden and 404-backed with the flag off.

## Files to change

- New: `backend/app/section8_inspections.py` (CRUD orchestration, import parser), `backend/app/section8_inspection_rules.py`, `frontend/app/inspections.html` + `inspections.js` (+ component CSS using existing tokens only), `backend/tests/test_section8_inspections.py`.
- Edit:
  - `backend/app/database.py`: the two tables in T6's own block, scoped CRUD, `reset_db` order.
  - `backend/app/api.py`: routes.
  - `backend/tests/test_team_isolation.py`: new cases.
  - `backend/tests/run_all_tests.py`.

## Files not to touch

- Nav and app chrome (T12).
- T1's tables and routes.
- `design-system.css`, the token blocks and other brand files (pivot constraint 1).
- `render.yaml`.
- The fixtures.
- T4's area.

## Team isolation & roles

- Every query uses `team_id = current_team_id()`.
- `unit_id`, `property_id`, `pha_id` and `parent_inspection_id` go through `require_own`. Another team's id gives 404.
- Auto-tasks are created in the caller's team only.
- The at-risk view reads only the caller's rows.
- **New `test_team_isolation.py` cases:** team B can't list, fetch or patch team A's inspections or items; can't attach an inspection to team A's unit or PHA; can't see A's at-risk items; and A's auto-tasks never appear in B's task list.

## Feature flag

`SECTION8_MODE` (T1). Flag off: every new route and the page are 404, with nothing in nav. The tables are created regardless.

## Verification

`test_section8_inspections.py`, with no Anthropic and no network. **Fixture reports:** importing each of the 3 fixture PDFs gives drafts whose fields equal the generator's data, and confirming them yields exactly the answer-key outcomes as of 2026-10-01:

| ID | Unit | Expected outcome |
|---|---|---|
| S8-14 | JR 104 | `abatement_active` from 2026-09-01 |
| S8-16 | BT 2B | `lt_cured_late` |
| S8-15 | BT PBRA (1B / site) | `reinspection_overdue` |

**Traps that must NOT flag:**
- JR 104's smoke detector, cured within 24 hours.
- BT 3B's life-threatening item, corrected the same day.
- BT 2C's moderate item, cured within 30 days.
- BT 1D's severe item, corrected on its deadline.

Further tests:
- **Rules:** a per-PHA `inspection_cure_days` override changes the computed deadline and `rule_source`; removing it falls back to the default.
- **Tasks:** one task per open item; no duplicate on re-save; auto-closed when corrected.
- **Manual entry** round trip; reinspection chaining; waive with note.
- **Roles, flag and validation:** cure date before inspection date gives 400; unknown severity gives 400; viewer 403 on writes; flag off 404.
- **UI:** headless screenshots of `inspections.html` (at-risk list, detail, import draft) at 1440/768/375 and several scroll positions, flag on, against the fixture data. Opened and looked at.
- Full suite in the worktree.

## Out of scope

- Feeding abatement into reconciliation findings (T5 reads `expected_abatement_start`).
- Nav entries (T12).
- The This-Month panel (T10).
- PHA portal integrations.
- AI extraction of reports.
- Loading the fixture inspections into the T13 sample (follow-up once both are on `main`).

## Open questions

1. **Default cure periods.** The plan's code defaults are paraphrased (see Approach 2). They'll be checked by your Section 8 contacts per Q4. Any you already know should differ, for example HCV "severe"?
2. **Auto-tasks:** create them for **every** open deficiency (my default), or only for life-threatening, severe and overdue items, to avoid flooding the task list after a big NSPIRE inspection?
3. **Site/common-area inspections** (unit_id empty, property-level, like the PBRA sidewalk item). OK to support them now? They come with NSPIRE multifamily inspections.
