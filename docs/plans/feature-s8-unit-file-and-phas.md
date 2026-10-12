# Plan: feature/s8-unit-file-and-phas (T9 of the Section 8 pivot)

## Goal

A Section 8 operator signs in with `SECTION8_MODE` on and finds a new **Section 8** group in the app sidebar with two pages:

- **Units.** Every unit, grouped by property. Each row shows:
  - the current household
  - the housing authority (PHA)
  - program, voucher size
  - contract rent / tenant share / HAP

  Clicking a unit opens its **unit file**:
  - the current tenancy (editable)
  - past tenancies
  - its HAP contracts
  - every document linked to it (lease, addendum, HAP contract, PHA notice, rent-roll row), each opening the existing lease-detail page with its page citations

  From here a user can add properties and units, record a new tenancy, add a HAP contract, link an uploaded document, and (admins) run the address backfill with a preview first.
- **Housing Authorities.** The team's PHA directory: name, jurisdiction, inspection standard, HAP payment day, rent-increase notice days, portal link and caseworker contact. These are the per-PHA settings later deadline features read.

With the flag off, the group and pages are absent and nothing changes for anyone. Same brand, tokens, fonts and components as the rest of the app.

Source: `PIVOT_PLAN.md` Step 4, T9; feature F7.

## Base branch

**Stacked on `feature/s8-data-model` (`b6caf9a`, Ready for review, unmerged).** T9 needs T1's `/section8/*` API. This branch **cannot merge before T1**. Once T1 merges, rebase onto `main` (expected clean: T9 touches the frontend and one line of `/config`).

## Prior art (searches run 2026-10-12)

- `git log --all` for "unit page/file", "PHA settings/directory", and `-S` for `section8/units`, `unit-file`, `phas-view`. **Hits:** only T1's own commits (the API this builds on) and the pivot plan. **No UI exists anywhere.**
- `TASKS.md`: T9 queued under "Section 8 pivot", unclaimed. No in-progress row touches the customer app's nav or `index.html`. T12 (app reframe, nav renames) is not started; T9 adds a *new* nav group only and renames nothing, leaving T12 its whole scope.
- `docs/tester-pack` (unmerged) has a Help framework; not needed here.
- **Reused as-is:**
  - The view router: `registerView` / `showView(name, params)` in `app.js`.
  - The `apiRequest` / `Api` helper in `api.js`.
  - The nav-group/nav-item markup.
  - The `.view`, `.view-header`, `.panel`, `.text-input`, `.btn-primary` and `team-members-table`-style classes from `styles.css`.
  - The `escapeHtml` helper.
  - The `showView('detail', { leaseId })` navigation to lease detail.
  - The role check used by `team-view.js` (`Api.authSession()`, UX only; the backend `@require_role` is the real gate).

## Approach

1. **Flag to the frontend.** `GET /config` adds `"section8_mode": <bool>` (from T1's `section8_mode_enabled()`). It is public and read-only, next to `local_dev_mode`, which the docstring already allows ("flags that are safe for anyone to read"). It reveals only on/off.
2. **Nav.** A new `nav-group` "Section 8" in `app/index.html`, with nav items **Units** and **Housing Authorities**. Hidden by default (`hidden` attribute), and revealed by `section8-view.js` after `/config` says the flag is on. A hidden nav item can't be clicked, and the backend still 404s with the flag off, so the hiding is cosmetic, not the security boundary.
3. **API client.** `api.js` gains `Api.s8.*` thin wrappers for T1's routes. No new endpoints beyond step 1. Wrapped routes:
   - list/get/create/update for phas, properties, units, tenancies, hap-contracts
   - `linkUnitDocument`, `updateUnitDocument`
   - `backfill(apply)`
4. **`frontend/app/section8-view.js`** (new, one file; registered in `access-gate.js` `APP_SCRIPTS`). Three registered views:
   - **`s8units`.** Property filter + table:

     | Column | Source |
     |---|---|
     | Unit | `unit_label` |
     | Property | joined client-side from `properties` |
     | Beds | `bedrooms` |
     | Status | pill; `unknown` shown as "Unknown" |
     | Household | current tenancy |
     | PHA | joined from `phas` |
     | Program | current tenancy |
     | Contract / Tenant / HAP | formatted dollars |

     - Joins are done client-side from one call each to units, current tenancies, properties and PHAs. No N+1 calls.
     - Actions (hidden for viewers): **Add property**, **Add unit**. For admins only: **Group uploads into units**, the backfill. It runs a dry-run preview modal first ("Will create 2 properties, 5 units, link 6 documents; 1 skipped: no address") with Apply / Cancel.
     - Empty state explains the two ways in: add by hand, or group existing uploads.
   - **`s8unit`** (the unit file; opened with `showView('s8unit', { unitId })`):
     - **Header:** unit label, property name, status, bedrooms. Analysts can edit status and bedrooms.
     - **Current tenancy panel:** household, size, PHA, program, voucher bedrooms, move-in, contract / tenant / HAP / UA, amounts effective date. **Edit** opens an inline form. **Record new tenancy** sends `end_current: true` after a confirm step ("This marks {name}'s tenancy as past"). A quiet note appears when tenant + HAP ≠ contract rent: "Tenant share + HAP doesn't equal contract rent". It is shown, not blocking.
     - **HAP contracts panel:** type, number, form, PHA, term, contract rent, initial HAP, status; **Add HAP contract** form.
     - **Documents panel:** filename or display name, kind badge, linked by (you/backfill), with click → lease detail. **Link a document** uses a select of the team's uploads (`Api.listLeases`), a doc kind and an optional tenancy. Changing the kind and **Unlink** use `PATCH {archived: true}`, since T1 has no delete.
     - **Past tenancies panel** (collapsed by default).
   - **`s8phas`.** Table of PHAs (name, short name, jurisdiction, inspection standard, payment day, notice days, contact) plus an add/edit form with the same fields, portal URL and notes. Analysts can **Archive**, and can see archived PHAs with a "Show archived" toggle. `settings` (JSON) is not exposed in the UI.
5. **Formatting and input.**
   - Money fields accept "1,400" or "1400.00"; the backend validates, and its 400 message is shown inline next to the form.
   - Dates use `<input type="date">`.
   - All user text goes through `escapeHtml`.
   - Enum selects mirror T1's allowed values.
6. **Styling.** Existing classes only. A few layout rules go in `styles.css` under a `/* Section 8 */` block, using **existing tokens only**, no new colours/fonts/tokens:
   - the unit-file panel grid
   - a money column `font-variant-numeric: tabular-nums`
   - the kind badge reusing the existing pill style

   Tables scroll horizontally inside their panel at 375px (same pattern as the rent-roll table) rather than widening the page.
7. **Admin console:** untouched (it reuses app views but has its own nav). Out of scope.

## Files to change

- `backend/app/api.py`: `/config` adds `section8_mode` (one line + docstring)
- `backend/tests/test_section8_data_model.py`: `/config` reflects the flag (off/on)
- `frontend/app/index.html`: Section 8 nav group + three `<section class="view">` shells
- `frontend/app/section8-view.js` (new)
- `frontend/app/api.js`: `Api.s8` wrappers
- `frontend/app/access-gate.js`: add `section8-view.js` to `APP_SCRIPTS`
- `frontend/app/styles.css`: small `/* Section 8 */` block, existing tokens only

## Files not to touch

- Brand/design files: `design-system.css`, the `landing.css` tokens, `auth.css`, fonts, logo, favicon, og.
- Marketing pages.
- `frontend/admin/*`, `frontend/owner/*`.
- Existing nav items and labels (T12 owns renames).
- T1's backend logic (bugs found there get fixed on T1's branch, not here).
- `render.yaml` and Render env vars.

## Team isolation & roles

- **New backend surface:** only `/config`'s boolean. It is not team data, so no scoping is needed. Every data call goes through T1's routes, which are already team-scoped, role-gated, and covered by `test_team_isolation.py`'s three Section 8 cases. No new queries.
- **Roles in the UI (UX only; the backend is the boundary):**
  - viewers see read-only pages (no add/edit/link/archive buttons);
  - analysts get the editing;
  - only admins see "Group uploads into units".
- A 403 from the backend still shows its message if the UI is out of date.

## Feature flag

`SECTION8_MODE` (T1's, default **off**). Off: the nav group stays hidden, the views are never reachable from the UI, and every `/section8/*` call 404s.

## Verification

- **Backend test:** `/config` returns `section8_mode: false` by default and `true` with the env var.
- **Suite:** full suite in this clean worktree, result quoted.
- **Headless screenshots** (`.claude/tools/screenshots.mjs` / `ui-checker`).
  - **Setup:** local API with `SECTION8_MODE=true` and a seeded team containing 2 properties, 5 units (one with no tenancy), 2 PHAs, current + past tenancies, 1 HAP contract and linked documents. Seeded from the Juniper Row / Bellmont Terrace names in `qa/section8-fixtures` (merged on main; values typed into the seed script, not imported), plus one flag-off run.
  - **Pages:** Units list, Unit file, Housing Authorities, the backfill preview modal, the viewer read-only state, and the flag-off sidebar (no Section 8 group).
  - **Widths:** 1440 / 768 / 375 at several scroll positions. I open and look at every key screenshot; the ui-checker opens all of them.
- **Manual click-through in the headless run:**
  - add a PHA
  - add a unit
  - record a tenancy, then record a new one (old moves to past)
  - link a document → lease detail opens
  - backfill preview → apply

## Out of scope

- **Open findings and tasks on the unit file.** No Section 8 findings exist yet. Added when T3/T5 produce them; T10 also aggregates them.
- **Editing PHA `settings` JSON / deadline defaults** (T6–T8 define what goes in it).
- **The admin console view, nav renames, hiding CRE views** (T12).
- **Uploading a document straight into a unit** (today: upload as usual, then link).
- **Merging duplicate units, moving a tenancy between units** (T1 makes those immutable on purpose).
- **Bulk edit, CSV export of units.**

## Open questions

1. **Sidebar placement:** the new "Section 8" group sits **above** the existing groups (proposed: these become the primary pages once the pivot lands) or **below** them (less disruptive while CRE pages still exist)?
2. **Backfill button wording:** "Group uploads into units" (proposed), or something else?
