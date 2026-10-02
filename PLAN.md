# Plan: Real multi-tenant team isolation

## Build status (post-implementation)

**Built and tested (66/70 test files green — the other 4 are the
pre-existing tesseract-dependent failures noted in `CLAUDE.md`,
unrelated to this work):**
- Schema reconciled with the now-merged `feature/usage-limits` teams
  model (extended with `teams.status`), §2/§4.
- `team_id` threaded through `database.py`, `auth.py`, and every
  domain module that touches team-owned data (§4/§5) — leases,
  discrepancies, alerts, comments, tasks, assignments, lease tags/field
  edits, activity log, assistant conversations, messaging, linked email
  accounts.
- All ~155 `api.py` routes updated to resolve and pass `team_id`.
- §7/§8's owner-console **backend** routes: `POST /owner/teams`
  (team + first admin + 7-day setup link via `POST /auth/team-setup`),
  `GET /owner/teams` (usage view), deactivate/reactivate.
- §3's team-deactivation-blocks-login check in `verify_password`.
- `backend/tests/test_team_isolation.py` — 20 cross-team tests.
- **Found and fixed real, pre-existing cross-team vulnerabilities**
  while doing this (not introduced by this branch): `POST
  /team/members` accepted a client-supplied `team_id` (could create a
  user directly inside another team); `PATCH /team/members/<id>` and
  its `/reset-password` sibling didn't check the target's team at all;
  task/assignment/thread-participant routes let a caller point at a
  user on another team. All fixed, all covered by the new test file.

**Explicitly deferred (not built this pass):**
- §7/§8's **frontend**: the owner console's "Teams" UI, and
  `frontend/app/team-setup.html` (the page the setup-link email points
  at). The backend routes exist and are tested; nothing renders them
  yet.
- §9: the empty-workspace UI copy and the "Load sample deal" button,
  including the Maple Ridge precomputed-fixture generation work
  (blocked on `fix/rent-roll-hardening` committing/pushing the raw
  fixture — see `TASKS.md`).
- §10: `render.yaml`'s persistent-disk config was left untouched, per
  its own "not my call to flip this" reasoning — still blocking
  "survives a redeploy" in practice on the tester deployment.

## 0. About `TEAM_AUDIT.md`

You asked me to read `~/dev/projects/TEAM_AUDIT.md` first. **It doesn't
exist** — I checked that exact path, searched `~/dev/projects` and `~`
for any `*AUDIT*` or `*audit*` file, and grepped every worktree's docs
for "team." Nothing. So I did the audit myself, directly against the
candidate branches, before writing this plan:

- **`feature/usage-limits`** (`~/dev/projects/abstractly-usage`) adds a
  real `teams` table + `users.team_id`, with a clean migration that
  creates a `'Legacy'` team and backfills every existing user into it.
  This is the schema TASKS.md already says loan-underwriting and
  isolation work should converge on, and it's the only one of the three
  that matches your vocabulary ("every customer firm is a team"). But
  it only scopes `users` and its own new `usage_events` table —
  **no lease, discrepancy, alert, comment, task, etc. is scoped.**
- **`worktree-agent-ade7619750bfa9a9f`** (stale, local-only, branched
  2026-09-02 off an old `main`) did the opposite: a comprehensive
  `accounts` table + `account_id` added to `leases`, `discrepancies`,
  `alerts`, `comments`, `assignments`, `message_threads`, `tasks`,
  `lease_tags`, `lease_field_edits`, `activity_log`, with `account_id`
  threaded through nearly every `database.py` function and `api.py`
  route. This is the actually-comprehensive one, and the part worth
  reusing is its **shape of the work** (which tables, which call sites,
  the migration-with-backfill pattern). Two problems with reusing it
  directly: it uses `account_id` (not `team_id` — a second vocabulary
  TASKS.md already warned against), and **it deleted bearer-token auth**
  from `auth.py` (`issue_token` / `_user_from_bearer_token`), which
  `frontend/app/api.js` still depends on today — a real regression I
  won't reintroduce.
- **`feature/loan-underwriting`** deliberately adds **no** team/account
  column anywhere (its own `PLAN.md` says so explicitly) and defers to
  "a separate branch" for the team model. Nothing to reuse here except
  the confirmation that it's not a second schema to reconcile.

**Decision: build on `usage-limits`'s `teams`/`team_id` schema and
migration pattern, but give it the comprehensive table/route coverage
the stale `accounts` branch demonstrated — renamed to `team_id`, with
bearer-token auth preserved and extended to carry `team_id`.**

One more deliberate departure from both prior attempts: every reused
function in the stale branch took `account_id: Optional[int] = None`
— "pass it if you have it, defaults to unscoped." `usage-limits` hit
exactly this bug once already (its last commit, `4a4deca`, is titled
*"usage-limit bypass: ... no longer skip when team_id is missing"*).
So here, **`team_id` is a required parameter everywhere, with no
default** — a call site that forgets to pass it is a crash at
development time, not a silent cross-tenant leak in production.

---

## 1. Why this is a bigger change than "add a column"

I traced where lease/user data actually gets read, not just where
routes live. `get_all_effective_leases()` / `get_all_leases()` /
`get_lease()` / `list_users()` etc. (`database.py`) are called from
**`api.py` and 11 other modules**: `deal_mismatch.py`,
`investment_memo.py`, `portfolio_health_score.py`, `alerts.py`,
`assignments.py`, `tasks.py`, `qa_engine.py`, `assistant.py`,
`demo_seed.py`, plus the comparison/portfolio helpers those pull in.
`build_deal_mismatch_report_data()`, for instance, is called from 3
routes with zero arguments and reaches into `get_all_effective_leases()`
two layers down. If `team_id` only gets added to `api.py` and
`database.py`, every one of those 11 modules keeps quietly operating on
the whole deployment's data. So the real unit of work is: **thread a
required `team_id` through every function in that call graph**, not
just the `database.py` layer.

`api.py` is 5,087 lines with 151 routes; `database.py` is 4,042 lines.
This is the largest change this codebase has seen. I'm not going to
pretend it's small, and I'd rather size it honestly now than discover
the real scope three files in.

---

## 2. Schema

New `teams` table (from `usage-limits`, extended with a `status`
column for requirement 3's deactivation):
```sql
CREATE TABLE teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'deactivated'
    created_at TEXT NOT NULL
)
```
(I'll leave out `usage-limits`'s quota/budget columns — that's
`feature/usage-limits`' own concern to add when it merges; this branch
only owns the isolation + status columns.)

`team_id INTEGER NOT NULL REFERENCES teams(id)` added to every
team-owned table, via a generic migration helper (same idea as the
stale branch's `_add_account_id_column`, adapted to add it as
`NOT NULL DEFAULT <legacy_team_id>` in one step rather than nullable
+ backfill, since SQLite allows a `DEFAULT` on `ALTER TABLE ADD
COLUMN`):

- `users` (every user belongs to exactly one team)
- `leases` (covers lease docs *and* rent rolls — `document_type`
  distinguishes them on the same table today)
- `discrepancies`, `discrepancy_resolutions`, `alerts`
- `comments`, `lease_tags`, `lease_field_edits`
- `tasks`, `assignments`
- `activity_log`
- `assistant_conversations`, `message_threads`,
  `message_thread_participants`, `messages`
- `revenue_entries`, `expense_entries` (owner-console financials — see
  open question below on whether these stay global-to-Abstractly or
  become per-team)
- `ai_extraction_runs`, `training_rounds`
- `linked_email_accounts`

**Not team-scoped, by design** (staff-only or pre-account data, no
customer team ever reads these):
- `waitlist_signups`, `demo_requests`, `pageviews` — marketing-site
  leads/analytics, submitted before any login exists.
- `oauth_states` — short-lived OAuth artifacts, already scoped by their
  own state token.
- `password_reset_tokens` — reused as-is for requirement 1's setup
  links (see §7); scoped by `user_id`, which already implies a team.

**Open question on `demo_requests`:** your instruction says "every...
demo request is owned by a team." I think this refers to the marketing
`/demo-request` form (`name`/`work_email`/`company`/`units`, no login),
which is a sales lead with no team yet — there's nothing to scope it
*to*. If you meant something else (an in-app "request a demo of a
feature" flow), I don't see one in the code — tell me and I'll adjust.
Otherwise I'll leave it admin/owner-visible only, as today.

**Open question on `revenue_entries`/`expense_entries`:** these back
the **owner console's** (`/owner/revenue`, `/owner/expenses`) view of
*Abstractly's own* business financials (what Abstractly bills/spends
per customer), not a customer-facing feature. They're `@require_owner`
already. I'd lean toward leaving them as Abstractly-staff-global data
(not per-customer-team), since "team" here means the customer, and
these rows already exist to be viewed across all customers at once.
Flag if you want them scoped instead.

---

## 3. Auth (`auth.py`)

- `current_user()` gains `"team_id"` in both the session-cookie and
  bearer-token paths (so the `app/` client, which uses the Bearer
  header, keeps working — this is the regression I'm specifically
  avoiding from the stale branch).
- New `current_team_id()` helper (mirrors `current_account_id()` from
  the stale branch, renamed): returns the logged-in user's `team_id`,
  or raises if called with no session, rather than returning `None`
  silently.
- `issue_token()` and the session-set-on-login code both start
  including `team_id`.
- `require_role` / `require_owner` are untouched — role and
  team are orthogonal. `is_owner` stays a global, cross-team flag
  exactly as today (owner-console routes intentionally see every
  team's data — that's Abstractly staff, not a customer).
- `verify_password()` extends its existing "deactivated user fails
  exactly like a wrong password" check to also fail when the user's
  **team** is deactivated (`teams.status != 'active'`) — same
  timing-safe dummy-bcrypt-check path, so a deactivated team's login
  page gives no signal beyond "wrong email or password."
- **Known limitation I'm carrying forward, not introducing:** sessions
  and bearer tokens are stateless (`auth.py`'s own docstring: "logout
  can't force early invalidation of an already-issued token any more
  than... cookie"). That means deactivating a user or a team blocks
  *new* logins immediately, but an already-issued session/token stays
  valid until it expires (bearer tokens: 12h) — exactly how user
  deactivation already behaves today. I'm matching existing behavior,
  not inventing a weaker guarantee for teams specifically. If you want
  immediate revocation, that's a separate, larger change to the auth
  model (a server-side session/token blocklist) — tell me if you want
  that scoped in too.

---

## 4. `database.py`: every team-owned read/write takes `team_id`

Pattern, applied to every function touching a table from §2 — e.g.:

```python
def get_all_leases(team_id: int, document_type: Optional[str] = "lease",
                    include_superseded: bool = False) -> List[Dict[str, Any]]:
    ...
    WHERE team_id = ?
```

`insert_*` functions gain a required `team_id` parameter and write it
on insert. `get_*`/`list_*` functions add `AND team_id = ?` (or
`WHERE team_id = ?`) to their query and take `team_id` as a required
(not keyword-defaulted) argument. `get_lease(lease_id, team_id)` and
similar single-row lookups return `None` — not another team's row —
when the id exists but belongs to a different team, so a 404 is
indistinguishable from "doesn't exist," never leaking existence.

Migration functions (new, modeled on `usage-limits`'s
`_migrate_teams_table` / `_migrate_teams_create_legacy_team` /
`_migrate_users_add_team_id`):
1. Create `teams`.
2. Create the `'Legacy'` team.
3. For each table in §2's list, add `team_id NOT NULL DEFAULT
   <legacy_team_id>` + an index, idempotently (`PRAGMA table_info`
   check first, like every other migration in this file already does).

This is the step that satisfies "existing data migrates into a single
default team" — it happens automatically on next boot, no manual step.

---

## 5. The 11 call-graph modules (§1)

Each function in `deal_mismatch.py`, `investment_memo.py`,
`portfolio_health_score.py`, `alerts.py`, `assignments.py`, `tasks.py`,
`qa_engine.py`, `assistant.py`, `demo_seed.py` that currently calls a
now-team_id-requiring `database.py` function gains its own required
`team_id` parameter and passes it straight down. No module gets a
"current team" global/thread-local — same explicit-parameter
convention as `database.py`, so a missing `team_id` is a `TypeError` at
the call site, caught the first time that code path runs, not a silent
cross-team read.

---

## 6. `api.py`: 151 routes

Every route handler that currently calls one of the now-scoped
functions resolves `team_id = auth.current_team_id()` once (already
implicitly available via the session/token `current_user()` reads) and
passes it down the chain. Existing `@require_role`/`@require_owner`
decorators are untouched — this adds a dimension, it doesn't replace
the existing one.

`@require_owner` routes (`/owner/...`) stay deliberately cross-team —
that's the one place "see every team's data" is correct, by design,
for Abstractly staff. Everything else gets scoped.

---

## 7. Admin console: create a team, invite its first user (requirement 1)

New owner-only route, `POST /owner/teams`, body
`{"firm_name", "admin_name", "admin_email"}` — **no password field**,
per your requirement that you never see or set it:

1. Creates the `teams` row (`name = firm_name`).
2. Creates the first `users` row for that team: `role='admin'`,
   `team_id` = the new team, and a **password_hash nobody can match**
   — a fresh random 32-byte value run through `hash_password()`, same
   as a real password hash in shape but with no corresponding
   plaintext anyone (including Abstractly staff) knows. This is
   deliberately not a `NULL`/empty column — the login path's bcrypt
   check already fails closed on any non-matching hash, so this needs
   no new "pending" status or special-cased login logic; it just can't
   be logged into until step 3 replaces it.
3. Creates a row in the **existing** `password_reset_tokens` table
   (reused as-is — it already stores exactly `token_hash`, `user_id`,
   `created_at`, `used_at`) with a **7-day** TTL, following the
   existing `/auth/reset-password`-request code path
   (`database.create_password_reset_token`, raw token only ever
   returned once, hash stored). The 1-hour forgot-password flow and
   this 7-day setup flow share the table and the `consume` function;
   only the TTL passed at consume-time differs, same as today's single
   `_PASSWORD_RESET_TOKEN_TTL_SECONDS` constant pattern — I'll add a
   second constant, `_TEAM_SETUP_TOKEN_TTL_SECONDS = 7 * 24 * 3600`,
   and a distinct consuming route so a forgot-password link can never
   accidentally be used as a first-time setup link or vice versa.
4. Tries to email the link
   (new `email_service.send_team_setup_email(to_email, name,
   firm_name, setup_url)`, modeled directly on the existing
   `send_password_reset_email`). **If sending fails or
   `RESEND_API_KEY`/mail isn't configured** (already a possibility
   today — `email_service.py` logs and returns `False` rather than
   raising), the route still returns `201` with the raw setup URL in
   the JSON response body, so you can copy it from the admin page and
   send it yourself — this satisfies "or shows me a one-time link I
   can copy" as the fallback, not a separate mode you have to pick.
5. New route `GET/POST /auth/team-setup` (token in the query string for
   GET to render the "set your password" page, POST with
   `{"token","new_password"}` to consume it) — same shape as
   `/auth/reset-password`, separate endpoint so it can enforce "token
   not yet used, team not deactivated" without touching the existing
   forgot-password route at all.

New frontend: a page under `frontend/app/` (e.g. `team-setup.html`),
same pattern as the existing `reset-password.html` pages, where the
invited person sets their own password — the one point in the whole
flow where a plaintext password exists, and it's typed by them, into
their own browser, straight to `/auth/team-setup`, never through you.

---

## 8. Admin console: teams/users/usage view + deactivation (requirement 3)

Extends the **existing owner console** (`frontend/owner/`,
`@require_owner` routes) — this is clearly staff-level, cross-team
visibility, i.e. the owner console, not a per-team admin screen. New
routes alongside the existing `/owner/accounts` family:

- `GET /owner/teams` — one row per team: name, status, user count,
  lease count (leases + rent rolls together, `document_type` both
  counted), and last activity (`MAX(activity_log.created_at)` for that
  team). I'm defining "usage" this concretely because nothing richer
  (page counts, AI spend) exists on this branch — that's
  `feature/usage-limits`' `usage_events` table, which isn't merged
  here; tell me if you want me to pull that table in too, but it's a
  separate concern from isolation.
- `GET /owner/teams/<id>` — that team's user list (reusing
  `_user_public`, same password_hash-stripping as `/owner/accounts`).
- `POST /owner/teams/<id>/deactivate` — sets `teams.status =
  'deactivated'`; blocks new logins for every user in it (§3).
- `POST /owner/teams/<id>/reactivate` — the inverse, mirroring
  `/owner/accounts/<id>/reactivate`'s existing pattern.
- Per-user deactivate/reactivate: **already exists**
  (`/owner/accounts/<user_id>/suspend` /`/reactivate`) — unchanged,
  just now additionally shown grouped under its team in the UI.

Frontend: a new "Teams" section in `frontend/owner/owner-app.js` +
`index.html`, listing teams with the usage columns above, a "Create
team" button opening the firm/name/email form from §7, and
deactivate/reactivate buttons at both the team row and the user row
inside it — same confirmation-before-destructive-action pattern the
existing suspend button already uses.

---

## 9. Empty workspace + sample deal (requirement 2)

**Empty by construction, not by a new check.** Once `get_all_leases`
etc. are scoped by `team_id` (§4), a brand-new team's queries simply
return nothing — there's no separate "is this a new team" flag to add
or get wrong. I'll update the `app/` dashboard's existing empty-state
rendering (shown today when a query returns zero leases) to the
onboarding copy you want: upload your own leases and rent roll, plus
the new "Load sample deal" button.

**"Load sample deal" — precomputed, zero API calls, team-scoped:**

New route `POST /sample-deal/load`, `@require_role('analyst')`,
team-scoped like everything else. It must *insert already-extracted
lease/rent-roll rows directly via `database.insert_lease(...)` etc.*,
never call `ai_extraction.py` or any Anthropic-backed path — same
"pure fixture insert" convention `demo_seed.py` already uses for its
own two sample leases (`_sample_pdf_leases()`), just with Maple Ridge's
16 leases instead of 2, and written into the *calling team's*
`team_id` instead of a standalone demo database.

The catch, and I want to flag it rather than quietly solve it: **no
precomputed, already-extracted field data for Maple Ridge exists
anywhere in this codebase today.** I checked every candidate:
- `backend/benchmark_data/demo_deal/` (the Maple Ridge fixture itself)
  only exists uncommitted in the `fix/rent-roll-hardening` worktree —
  it's **16 real lease PDFs + 2 rent-roll CSVs + 1 T12 xlsx**, i.e. raw
  source documents that still need extracting, not precomputed output.
- `expected_findings.json` in that same folder is a benchmark *answer
  key* (10 planted discrepancies: unit id, rent-roll value, lease
  value, dollar impact) — useful for verifying correctness, but it's
  missing most fields a lease record needs (landlord, dates, deposit,
  source-page citations, etc.) and isn't in the `FieldExtractor` shape
  `insert_lease` expects.
- `backend/benchmark_data/last_run.json` (cached AI output) is a
  *different*, unrelated 12-lease accuracy-benchmark corpus — not
  Maple Ridge.

So building the fixture is real, one-time work. My plan: copy the raw
Maple Ridge files (already-fictional, safe per `CLAUDE.md`'s synthetic-
data rule) from the `fix/rent-roll-hardening` worktree into this
branch, use the **16-unit demo-subset rent roll**
(`maple_ridge_rent_roll_demo_subset_16unit_appfolio.csv`) rather than
the full 120-unit roll (which would otherwise show 104 "no lease on
file" units with no story behind them), run the 16 lease PDFs through
the codebase's existing **non-AI regex/pdfplumber fallback extractor**
once, locally (the same deterministic engine `ai_extraction.py` already
falls back to with no `ANTHROPIC_API_KEY` — zero cost, no Anthropic
call, ever, including at generation time), hand-correct the output
where needed so the 10 planted discrepancies in `expected_findings.json`
actually surface when the real Deal Mismatch Report detectors run over
it, and commit the result as a static JSON fixture (same shape as
`demo_seed.py`'s `_sample_pdf_leases()`). "Load sample deal" then only
ever reads that static file.

This is more work than a one-line button, and I want your sign-off on
the approach (not the alternative: run the real Anthropic extraction
once against the real PDFs, which needs `ANTHROPIC_API_KEY` funded per
TASKS.md's Blocked list and your explicit go-ahead for a real-API run
per `CLAUDE.md` rule 5 — I'm defaulting to the zero-cost local-engine
route specifically so this doesn't need that).

The T12 file: a basic `t12_import.py` already exists on this branch
independent of the unmerged T-12-cross-check feature, so I'll seed the
Maple Ridge T12 too — it exercises a real, already-shipped import path.

---

## 10. Login durability across restarts/redeploys (requirement 4)

Checked the current behavior in `database.py`'s
`_seed_first_admin_user()` closely, because its own docstring makes
the real risk explicit: *"the users table gets wiped and this function
re-seeds a fresh admin+owner row from the same env vars **every
time**."* Two separate things are going on here, and only one is
something my code change controls:

**What's already correct, and what I'll keep true:** the function's
*logic* already matches your requirement exactly as written — it only
seeds from `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` when the `users` table
is completely empty ("no-op if any user already exists"), which is
indistinguishable from "a brand-new database" from inside the
function. I'm not changing this function, and — more importantly —
**no code I add anywhere will set or reset any other user's or team's
password from an environment variable.** Every password after the
first admin comes from the setup-link flow in §7 (set once, by the
person themselves) or the existing in-app change-password /
owner-console reset-password routes (admin-triggered, in-database, no
env var involved). I'll say this explicitly in the code comments next
to §7's token logic so a future change doesn't quietly reintroduce an
env-var password path.

**What this change can't fix, and I want to be upfront about now
rather than let you discover it after beta testers are on the
platform:** `_seed_first_admin_user`'s docstring is explicit that
"every time" is expected to mean *every redeploy*, because — per
`CLAUDE.md` and `TASKS.md`'s existing Blocked item — **no Render
service has a persistent disk**, so a redeploy or restart wipes the
*entire* SQLite file, not just the admin password: every team, every
user, every lease. The password-seeding logic being correct doesn't
help if the whole database it's seeding into disappears. `render.yaml`
already has the disk config written and commented out, with your own
note next to it ("free tier, per your choice"), so this was a known,
deliberate tradeoff before today — but it's now in direct conflict with
"logins must survive restarts and redeploys" once there are real teams
with real data on this deployment. **I can't fix this from the
backend-isolation branch**: it needs a paid Render plan + uncommenting
the `disk:` block + setting `DB_PATH`, which is your call (cost +
dashboard action), the same way the unfunded Anthropic API key is
already flagged as something only you can act on. Tell me if you want
me to go ahead and uncomment the `render.yaml` disk config now (so it's
ready the moment you upgrade the plan), or leave it as-is until you're
ready to make that change.

---

## 11. Tests

New `backend/tests/test_team_isolation.py`, registered in
`run_all_tests.py`. Fixture: two teams (`Team A`, `Team B`), one
`admin` user in each, each with its own lease, discrepancy, alert,
comment, task, assistant conversation. For every route category —
list, get-by-id, update, delete, PDF export, Excel export, the
assistant/Q&A endpoints — assert Team B's session can never read, list,
export, or modify Team A's data: a direct-by-id request 404s (not
403 — doesn't confirm the id exists), a list endpoint never includes
the other team's rows, and an export (PDF/Excel) built under Team B's
session never contains Team A's figures. I'll also keep/extend
`test_route_authorization.py`'s existing role checks — team scoping and
role checks are independent and both need covering on the same routes.

Additional cases for this update's new requirements:
- `POST /owner/teams` creates an unusable password hash + a 7-day
  setup token; the team's admin cannot log in until the token is
  consumed; a consumed/expired/wrong-team token is rejected by
  `/auth/team-setup`.
- A deactivated team blocks login for *every* user in it, even one
  whose own `status` is still `'active'`; reactivating restores it.
- `POST /sample-deal/load` under Team A's session never touches Team
  B's `leases` rows (same isolation guarantee as everything else), and
  — mocking/monkeypatching `ai_extraction`'s Anthropic client to raise
  if called — asserting it's never invoked by this route proves the
  "never calls the API" requirement rather than just asserting on the
  output.
- A brand-new team's lease list is empty immediately after
  `POST /owner/teams`, before any upload.

I'll run the full suite (`run_all_tests.py`) before and after, and call
out any pre-existing failure separately from anything this change
causes (per the OCR-tests exception already noted in `CLAUDE.md`).

---

## 12. What I'm explicitly not doing

- Not merging `feature/usage-limits` or `feature/loan-underwriting`
  into this branch — I'm reusing their *schema/pattern*, not their
  commits (usage-limits' diff also carries an old marketing-site
  revert and the T12 feature, neither of which belongs here).
- Not deleting the stale `worktree-agent-ade7619750bfa9a9f` — it's
  mined for ideas per TASKS.md, not merged; I'll leave it for you to
  delete once this ships.
- Not adding team-level billing/quotas (`usage-limits`'s concern, not
  isolation's), and not pulling in its `usage_events` table unless you
  want "usage" in §8 to include spend/page counts.
- Not building self-serve signup — provisioning stays an owner/staff
  action (§7), consistent with how accounts are created today.
- Not adding server-side session/token revocation (§3's noted
  limitation) unless you want that scoped in too.
- Not upgrading the Render plan or touching `render.yaml`'s disk config
  myself (§10) — that's your dashboard action; I'll prep the YAML if
  you say so.
- Not running real Anthropic extraction against the Maple Ridge PDFs
  (§9) — using the existing zero-cost local fallback engine instead,
  specifically so this doesn't need API credits or a real-API-run
  approval.

---

## Open questions (blocking — need your call before I start)

1. **`demo_requests`** — leave unscoped (pre-account marketing lead), or
   did you mean a different, in-app demo-request flow I haven't found?
2. **`revenue_entries`/`expense_entries`** — leave as Abstractly-global
   owner-console data, or scope per customer team?
3. **"Usage" in the admin teams view (§8)** — user count + lease count
   + last activity (what's achievable on this branch alone), or do you
   want `usage-limits`' spend/page-count tracking pulled in too?
4. **Maple Ridge sample-deal fixture (§9)** — OK with the local
   regex/pdfplumber-engine-plus-hand-correction approach (zero cost, no
   API credits needed), rather than a real Anthropic extraction run?
5. **`render.yaml` disk config (§10)** — want me to uncomment it now
   (inert until you upgrade the plan), or leave it alone until you're
   ready to pay for persistent storage?

If you'd rather I just make the calls above and keep moving, say so and
I'll go with my stated leans (unscoped demo_requests, global financials,
branch-local usage metrics, local-engine fixture, leave render.yaml
untouched) and note it in the commit instead of waiting.
