# chore/render-persistent-disk

## Goal

Give `abstractly-api` (production) persistent storage for the SQLite
database, so a deploy or restart stops wiping customer data. Config and
documentation only — no application code, and no changes made on Render
itself.

**Scope narrowed 2026-10-04 on the user's instruction:** this branch
originally also put a disk and `plan: starter` on
`abstractly-tester-api`. That was trimmed out — the tester service
stays on `plan: free` with no disk, so only one service incurs a paid
instance type. Tester data therefore still vanishes on restart and on
the free tier's idle spindown, which remains an open risk for the beta
(see TASKS.md "Blocked").

## Why this is its own branch

The identical `render.yaml` change already exists on
`feature/pricing-page` (`0a0d7a2`), bundled with a marketing-site
redesign. That bundling is the problem: `render.yaml` has no `branch:`
override, so merging pricing-page pushes a **billing** change
(two services from `plan: free` to `plan: starter`) along with a CSS
refresh, and the two need separate decisions at different times.

This branch carries only the hosting change, so pricing-page can merge
frontend-only. The `render.yaml` content is taken from pricing-page
rather than rewritten, to avoid a parallel second version — verified
structurally identical to it (`diff` ignoring comments shows only the
ordering of one `DB_PATH` entry within `envVars`, which is semantically
irrelevant).

## Findings that shaped the change

- **`DB_PATH` already works; no code change is needed.** `app/api.py:241-243`
  reads it and calls `database.configure()`. `main`'s `render.yaml`
  comment claiming it needs "a one-line code change" was stale and is
  removed here.
- **There are no uploads to persist.** Uploaded files are written to a
  temp file, parsed, and `os.unlink`'d in a `finally` (`app/api.py:545`).
  There are no BLOB columns and no route that serves an original
  document back. Only extracted fields and page numbers are stored, in
  SQLite — so the database disk covers everything durable the app has.
- **Render requires a paid instance type for disks**, confirmed from
  Render's own docs. The `plan: starter` change is mandatory, not
  optional tuning.
- **A disk costs two things beyond money:** deploys are no longer
  zero-downtime, and the service can never scale past one instance.
  Neither is new — SQLite is single-writer and could not be shared
  across instances regardless.
- **`FLASK_SECRET_KEY` is a separate failure mode.** Unset, the app
  writes a random key into the system temp directory per boot
  (`app/api.py:178-190`), invalidating admin sessions on every restart
  no matter what the disk does. Documented as a step to confirm.

## Scope

- `render.yaml`: `plan: starter` + 1 GB disk + `DB_PATH` on
  `abstractly-api` only.
- `docs/DEPLOYMENT.md`: rewrite "Adding persistent storage" for that one
  service, the no-data-migration warning, the two Render tradeoffs, and
  a verification procedure with a negative control.

## Out of scope

- `abstractly-tester-api` stays `plan: free` with no disk (user's
  decision, to avoid a second paid instance). Its data keeps vanishing
  on restart and idle spindown.
- `abstractly-demo-api` stays `plan: free` with no disk. Losing its
  database on restart is the mechanism that resets the demo for free;
  `DEMO_MODE`'s startup seed repopulates it.
- Making the app retain original uploaded documents (needed to
  re-render a page citation against its source PDF) — a product change.
- Fixing `test_demo_deal_golden.py`'s fixture bug (see below).
- Touching anything on Render. Every dashboard action is left to the
  user by instruction.

## Verification

- `backend/tests/test_frontend_api_routing.py`: 4 passed. This is the
  test that parses `render.yaml`; the new `disk:` block does not
  disturb its per-service `name:` extraction.
- Full suite in this worktree: **76/77 files passed**, failing only
  `test_demo_deal_golden.py`.

### That failure is pre-existing and environment-dependent

It is **not** caused by this branch, which touches no Python. Proof: the
same test passes in the primary checkout and fails here, with identical
application code.

Root cause: `_authed_client()` hardcodes `sess["user_id"] = 1` without
inserting a `users` row, so `usage_limits.log_usage_event()` trips
`FOREIGN KEY constraint failed`. It passes in the primary checkout only
because that checkout has a gitignored `backend/.env` with `ADMIN_EMAIL`
/ `ADMIN_PASSWORD_HASH`, which makes `init_db()` seed a user with id 1.

Consequence worth noting separately: `main`'s recorded "77/77" holds
only on a machine with that `.env`. On a clean clone, a fresh worktree,
or CI, `main` is 76/77. This is the same fixture bug `REVIEWS/MERGE_PLAN.md`
attributes to `chore/demo-rent-roll-polish`; the fix belongs there or in
its own branch, not bundled here.
