# Overnight report — `feature/team-isolation`

Autonomous overnight pass finishing multi-tenant team isolation. No merge
or push to `main` was done. Branch pushed to `origin/feature/team-isolation`
after every phase (final commit before this report: `ba7251b`; this
report plus a Phase 6 UI fix are committed on top).

## TL;DR — what to review first

1. **The two real cross-team vulnerabilities Phase 5 found and fixed**
   (`DELETE /tasks/<id>` and `DELETE /assignments/<id>` — any team could
   delete any other team's task/assignment by guessing the numeric id).
   These existed on `main`'s predecessor branches before this work and
   are fixed here. See "Decisions and findings" below and
   `backend/tests/test_team_isolation.py::test_sequential_id_guessing_finds_nothing_across_every_resource_type`.
2. **The owner console's new "Teams" tab** (`frontend/owner/index.html`,
   `frontend/owner/owner-app.js`) — create-team flow, setup-link
   fallback, team detail/deactivate. This is net-new UI surface you
   haven't seen yet.
3. **`backend/app/sample_deal.py`** and
   `backend/benchmark_data/demo_deal/precomputed_sample_deal.json` — the
   "Load sample deal" button's zero-cost fixture. Worth a skim to confirm
   you're comfortable with what gets copied into a team's workspace.
4. **`TASKS.md`** — rewritten during Phase 1's rebase; it's now the
   canonical status doc with a branch-sweep recommendation section.

Everything else below is detail in case something looks wrong.

## Phase-by-phase

**Phase 1 — rebase.** Rebased onto `origin/main` @ `28f2fb9`, kept the
single `teams` table from the merged `usage-limits` work as the schema
foundation. One real merge conflict (`TASKS.md`); resolved by hand,
combining both branches' status content. Two pre-existing test-fixture
gaps surfaced post-rebase (missing `team_id` in a faked test session;
a faked `user_id` in another test with no real backing `users` row,
which only became a problem once team isolation started actually
exercising `usage_events`' foreign key) — both fixed, neither is an
application bug. Pushed with `--force-with-lease` (expected after a
rebase of an already-pushed branch; `--with-lease` protects against
clobbering a concurrent push — nothing else was touched).

**Phase 2 — scoping audit.** Walked every route in `api.py` (~155) and
every query-shaped function in `database.py` (~170) and threaded a
required `team_id` through all of them — deliberately required, not
`Optional[...] = None`, because the `usage-limits` branch had already
been bitten once by an optional team filter silently defaulting to
"unscoped." Added `_migrate_add_team_id_column`, a generic
migration helper, and ran it for every team-owned table discovered
during the audit: leases, activity_log, lease_tags, discrepancies,
discrepancy_resolutions, alerts, comments, assignments,
assistant_conversations, message_threads/participants, messages,
linked_email_accounts, tasks, lease_field_edits. Left
`ai_extraction_runs` and `training_rounds` deliberately global —
they're owner-only telemetry about the AI pipeline itself, not
customer data. Cache keys that were previously bare
(`effective_leases`, `health_score:<threshold>`, portfolio/property
trend keys) are now namespaced by `team_id` — this was a real
cross-team cache-pollution risk under the old deployment-per-tenant
model, since a shared Redis would otherwise let one team's cached
numbers leak into another's view once isolation moved to a single
deployment.

**Phase 3 — admin page.** Built the owner console's "Teams" tab:
create a team + its first admin login in one call
(`POST /owner/teams`), list teams with per-team user/lease counts and
last-activity (`list_teams_with_usage`), a detail modal with the
member roster, and deactivate/reactivate for both teams and individual
users. The first admin's password hash is `hash_password(secrets.token_urlsafe(32))`
— a real bcrypt hash of a value nobody (not even you) knows — so the
row exists but is unusable until the person consumes their setup link.
Decision: reused the existing `password_reset_tokens` table and
`create_password_reset_token`/`consume_password_reset_token` functions
for the 7-day team-setup link rather than building a parallel table,
differentiated only by TTL (`_TEAM_SETUP_TOKEN_TTL_SECONDS`) and route
(`/auth/team-setup`). If email isn't configured (or the send fails),
the API response carries the raw `setup_url` and the UI shows it as a
copyable field — this is the fallback you asked for, and it's what the
local verification exercised since this machine has no mail
configured.

**Phase 4 — empty workspace + sample deal.** New teams start with zero
rows in every team-owned table — nothing to build here beyond what
Phase 2's scoping already guaranteed. Added the "Load sample deal"
button: `sample_deal.py`'s `load_sample_deal(team_id)` reads a
precomputed JSON fixture (31 lease rows, captured once by running the
*real* upload pipeline against the real 15 Maple Ridge PDFs + rent
roll, since no `ANTHROPIC_API_KEY` is configured locally so the
rule-based engine did the extraction for free) and inserts those rows
directly via `database.insert_lease(...)` — it never touches
`ai_extraction.py` or any network call. A test
(`test_sample_deal_load_never_calls_extraction_pipeline`) monkeypatches
the real extraction function to raise, to make that guarantee durable
rather than just true today.

**Phase 5 — adversarial tests.** `backend/tests/test_team_isolation.py`,
26 tests. Beyond the straightforward "team B can't read/list/export
team A's X" tests, the one that mattered most was
`test_sequential_id_guessing_finds_nothing_across_every_resource_type`:
it probes ids 1–50 against every single-resource route as a team that
owns none of them, then repeats against ids it knows are real (owned
by the other team), then does the same against six mutating routes
(update/delete/status-transition). **This caught two real,
pre-existing vulnerabilities**: `DELETE /tasks/<id>` and
`DELETE /assignments/<id>` deleted the row without ever checking it
belonged to the caller's team — any team could delete any other team's
task or assignment by guessing or knowing its id. Both fixed with the
same boundary-check pattern used everywhere else
(`database.get_task(id, team_id=current_team_id())` before the
delete). I then manually re-audited every other delete/update/status
route (~15) for the same shape of bug and found none.

**Phase 6 — Playwright verification.** Installed Playwright + chromium
into the shared venv, ran the full admin + new-team walkthrough
headless, and looked at the screenshots. Two environment problems
surfaced along the way (not application bugs, noted here so you're not
surprised if you re-run this yourself):
- The frontend static server on port 8080 turned out to be a stray
  process left running from a *different* worktree
  (`abstractly-landing`), so the first several runs were silently
  testing the wrong checkout and showing a stale "Accounts"-only owner
  console with no Teams tab. Didn't kill someone else's process — just
  started this worktree's frontend on 8181 instead.
- `ADMIN_ALLOWED_ORIGINS` needed to include whatever port the frontend
  actually serves on or the owner console's login fetch is blocked by
  CORS — set via env var for the local run, no code change needed.
- A `full_page=True` Playwright screenshot of the customer-app
  dashboard intermittently rendered the content pane blank below the
  sidebar — a headless-Chromium full-page-screenshot/sticky-sidebar
  interaction, not a real rendering bug. Confirmed by capturing a
  plain (non-full-page) viewport screenshot instead, which showed the
  dashboard — including the empty-state copy and "Load Sample Deal"
  button for a genuinely brand-new team — rendering correctly.

One real, minor bug *was* found this way: the team-detail modal's
member table (`frontend/owner/owner-app.js`, `Teams.renderDetail`)
could overflow the 480px modal width and clip the Status column with
no way to reach it, since the modal only allowed vertical scroll. Fixed
by wrapping the table in an `overflow-x:auto` div (same "wide content
scrolls in its own container" pattern used elsewhere). Verified after
the fix that the wrapper is actually scrollable
(`scrollWidth 492 > clientWidth 416`).

Full screenshot set reviewed (not committed — they're walkthrough
artifacts, not test fixtures): owner console Teams tab, create-team
form, create-team result with the setup-link fallback, team detail
modal (before and after the clipping fix), the team-setup password
page, the post-setup login redirect, and — using a second,
independently created team — the genuinely-empty first dashboard load
with its empty-state copy and "Load Sample Deal" button, then the
dashboard again after clicking that button, showing the Maple Ridge
data loaded and isolated to that team only.

## Test status

74/78 backend test files pass. The 4 failures
(`test_extraction.py`, `test_synthetic_accuracy.py`,
`test_multi_lease_detection.py`, `test_document_extractor.py`) are all
`TesseractNotFoundError` — this machine has no local `tesseract`/
`poppler` install. Confirmed via direct run that the failure is purely
the missing binary, not an assertion failure; this matches the known,
pre-existing baseline noted in `CLAUDE.md` (different filenames than
the two examples named there, but the same root cause and category).
`backend/tests/test_team_isolation.py`: 26/26 pass.

## What's broken or deferred

- **Nothing in-scope is broken.** The one real bug found (modal table
  clipping) is fixed and verified.
- **Already-issued sessions survive deactivation.** Deactivating a user
  or a team blocks new logins but doesn't revoke tokens/cookies already
  issued — this matches the pre-existing behavior for user
  deactivation before this work, so it wasn't treated as a new gap, but
  it's worth knowing if "deactivate" is meant to be instant and total.
- **Email sending is untested end-to-end** beyond the code path itself
  — local verification exercised the no-email-configured fallback
  (copyable link) because that's what's actually configured here.
  `email_service.send_team_setup_email` mirrors the existing
  `send_password_reset_email` exactly, so it should behave the same way
  in whatever environment email *is* configured, but nobody's watched
  a real email land in an inbox for this flow.
- **`PLAN.md`'s "Build status" section is now stale** — it was written
  after the original (pre-overnight) "Build it" pass and predates
  Phases 3–4's frontend UI and the sample-deal fixture. This report
  supersedes it as the status source; `PLAN.md` itself wasn't re-edited
  tonight to avoid two documents drifting out of sync with each other
  — if you want it reconciled, say so and I'll fold this report's
  content back into it.

## Local dev artifacts left behind (not committed)

- Backend process running on `:5000` (seeded `ADMIN_EMAIL=owner@abstractly.app`,
  password `ownerpass123`, `FLASK_SECRET_KEY=testsecretkeyfordevonly`,
  `ADMIN_ALLOWED_ORIGINS=http://localhost:8181`) — local-only, fine to
  kill.
- Frontend static server on `:8181` — same, fine to kill.
- `backend/lease_portfolio.db` — fresh local SQLite created for this
  verification pass, contains only the fictional Legacy/Maple Ridge
  Capital/Riverside Holdings teams created tonight. Not committed
  (`.gitignore`'d like every other local DB file); delete freely.
- Playwright + chromium are now installed in the shared
  `~/dev/projects/lease-abstraction/backend/venv` (used because this
  worktree's own `backend/venv` wasn't set up) — harmless to leave, or
  `pip uninstall playwright` if you'd rather not keep it there.

## Branch state

`feature/team-isolation` is rebased on `origin/main` @ `28f2fb9`,
3 commits ahead (`35c395d`, `e6cc3bb`, `ba7251b`) plus this report and
the modal fix on top, all pushed to `origin/feature/team-isolation`.
Not merged, per instructions.
