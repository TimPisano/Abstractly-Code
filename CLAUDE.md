# Abstractly — project instructions for Claude

Read this and `TASKS.md` at the start of every session. **`TASKS.md` in the
primary checkout (`~/dev/projects/lease-abstraction/TASKS.md`) is the single
source of truth** for what's in flight and every task's handoff notes.
How the user runs agents day to day: `docs/HOW_TO_RUN_AGENTS.md`.

## Product

SaaS for **mid-size multifamily syndicators**. It reads the leases behind a
seller's rent roll and checks them unit by unit before a deal closes.

- **Lease abstraction** — AI extraction of lease terms, each with a source page citation.
- **Rent roll validation** — reconcile the rent roll against the actual leases (the core feature).
- **Deal Mismatch Report** — every discrepancy with its **dollar impact** and **page citations**; PDF + Excel export.
- **T-12 cross-check** — T-12 collections vs. rent roll / lease rent.

Competitor: **Prophia** (institutional *office*). We win on multifamily focus,
rent roll validation as the core, and dollar-impact reports. Pricing is a
flat monthly fee per team: Starter $499 ($399/mo annual), Growth $1,250
($999), Enterprise custom (live only on `feature/pricing-page`).
**Current goal: first outside beta testers on the tester deployment.**

## Architecture

- **Backend:** Python 3.11, Flask 3, gunicorn (`backend/start.sh`). Most
  routes in `backend/app/api.py`; domain modules beside it
  (`deal_mismatch*.py`, `rent_roll_import.py`, `t12_import.py`,
  `ai_extraction.py`, `pdf_extractor.py` with Tesseract OCR fallback,
  `auth.py`, `database.py`, `security.py`, `usage_limits.py`).
- **Frontend:** vanilla JS/HTML/CSS, no framework, no build step.
  `frontend/index.html` + `pricing.html` = marketing; `frontend/app/` =
  customer app; `frontend/admin/`, `frontend/owner/` = staff consoles;
  `frontend/config.js` picks the API URL from the hostname.
- **DB:** SQLite, fresh connection per call. **No Render service has a
  persistent disk** — every deploy/restart wipes prod, tester, and demo
  data (`docs/DEPLOYMENT.md` → "Adding persistent storage later").
- **Jobs:** RQ on Redis (Upstash); `backend/worker.py` runs in the same
  container; queue per deployment (`LEASE_EXTRACTION_QUEUE`).
- **Anthropic:** `ai_extraction.py` (`LEASE_EXTRACTION_MODEL`),
  `assistant.py`, `cre_qa.py`, `ai_rent_roll_validation.py`. No
  `ANTHROPIC_API_KEY` → rule-based regex fallback.
- **Auth/roles:** session cookie (admin) + bearer token (`app/` client).
  `viewer < analyst < admin` via `@require_role(...)`; `is_owner` /
  `@require_owner` is separate and never implied by admin.
- **Tenancy:** `main` has `teams` + `users.team_id`, but **only for
  billing/quota** (`usage_events`, `/teams`). Document tables (`leases`,
  `discrepancies`, `alerts`, `tasks`, …) are **not** scoped: any user on a
  deployment can see every lease on it. Firms are isolated per deployment
  for now. `feature/team-isolation` extends `team_id` to documents —
  build on that, never a second `accounts`/`account_id` schema.
- **Render** (`render.yaml`, free plan, no `branch:` → all deploy from
  `main`): `abstractly-api` + `abstractly` (prod),
  `abstractly-tester-api` + `abstractly-tester` (beta, own DB),
  `abstractly-demo-api` + `abstractly-demo` (`DEMO_MODE`, seeded).
  **One push to `main` redeploys all three.** Secrets only in the Render
  dashboard (`sync: false`). Runbook: `docs/DEPLOYMENT.md`.

```bash
cd backend && source venv/bin/activate && python run.py   # API :5000
cd frontend && python3 -m http.server 8080                 # site :8080
python backend/tests/run_all_tests.py [--live]             # tests (register new files here)
```

More: `docs/LOCAL_DEV.md`, `docs/DECISIONS.md`, `docs/OPERATIONS.md`.
(`docs/PROGRESS.md`, `WORK_LOG.md`, `LAUNCH_READINESS_RECAP.md` are history,
not instructions. Root `PLAN.md`/`SUMMARY.md` are leftovers from
`feature/usage-limits`; new plans go in `docs/plans/`.)

## Standing rules

Hooks in `.claude/settings.json` enforce the ones marked 🔒; the rest are
on you. A hook block is a signal to stop and reconsider, never something
to route around.

1. 🔒 **Never open the user's browser** or any visible browser (no `open
   <url>`, no headed Playwright, no Chrome MCP). Visual checks: headless
   via `node .claude/tools/screenshots.mjs` / the `ui-checker` agent. To
   show the user a page, run the server in the background and give the URL.
2. 🔒 **Never merge into `main`, commit on `main`, or push `main`** unless
   the user typed `/merge-branch <branch>` (or "approve merge") in *this*
   session. Only one session merges at a time (merge lock). Subagents
   never touch `main`. TASKS.md-only commits on `main` are allowed.
3. 🔒 **One task = one branch = one worktree** under `~/dev/projects/`.
   The primary checkout `~/dev/projects/lease-abstraction` stays on `main`
   and is read-only except `TASKS.md` and `drafts/`. Never switch branches
   in a worktree you didn't create; check `git worktree list` first.
4. **Team isolation and roles on every route and query you add or touch:**
   explicit `@require_role(...)` on every route; scope document queries by
   the *authenticated* caller's `team_id`. If the needed scoping doesn't
   exist on your base yet, say so in the plan — never silently ship an
   unscoped route.
5. **Check for prior art before building.** Search `TASKS.md`, all
   branches, and stashes (start-task step 1). Build on existing work;
   never create a parallel version. Stay inside the approved plan — new
   ideas go in the plan's "Out of scope" or TASKS.md "Up next".
6. **Placeholders are questions, not values.** Text like `(the real
   email)`, `<your key>`, `[insert …]`, `TBD`, `@example.com` means ask
   the user. 🔒 The prompt hook flags these.
7. **Never commit secrets, `.env`, `*.db`, or real customer data.** Use
   Maple Ridge (`backend/benchmark_data/demo_deal/`) and
   `backend/tests/` fixtures.
8. **Mock the Anthropic API in tests.** Ask before any real-API run.
9. **Every bug fix gets a regression test** that fails before the fix.
10. **Claim only what you verified.** "Fixed" means you saw it: a test
    you ran (quote the result) or a screenshot you opened. Otherwise
    say "changed, unverified".
11. **Before /clear, logout, or a long break: run `/session-handoff`.**
    A fresh session resumes with `/resume-task <branch>`.
12. **Explain changes in plain English when done** — the user is
    learning backend development; teach the one pattern that matters.
13. Known pre-existing failures: OCR tests needing `tesseract`/`poppler`
    (`test_real_ocr.py`, `test_ocr_fallback.py`). Report any other failure.
14. New features not ready for testers go behind an env-var flag,
    default **off**. Small focused commits; one concern per branch.

## The Loop

Each step has a skill; use it instead of improvising.

| # | Step | Skill |
|---|---|---|
| 1 | Prior-art check, claim the task in TASKS.md | `/start-task` |
| 2 | Create branch + worktree under `~/dev/projects/` | `/start-task` |
| 3 | Write `docs/plans/<branch>.md`, **stop for user approval** | `/start-task` |
| 4 | Build (only what the plan says) | — |
| 5 | Run tests, fix until green | `/ship-branch` |
| 6 | UI changed → headless screenshots, *look at them* | `/ship-branch` → `ui-checker` |
| 7 | Commit, push the **feature branch** | `/ship-branch` |
| 8 | `reviewer` subagent (+ `security-auditor` for routes/auth) | `/ship-branch`, `/review-branch` |
| 9 | Fix what it flags; re-review if non-trivial | `/ship-branch` |
| 10 | **User approves the merge** by typing `/merge-branch <branch>` | user only |
| 11 | Designated merger session merges + pushes `main` | `/merge-branch` |
| 12 | Smoke test the tester deployment (headless) | `/merge-branch` |
| 13 | Update TASKS.md, remove the worktree | `/merge-branch` |

Anytime: `/status` (where things stand), `/session-handoff` (save state),
`/resume-task` (pick up), `/prompt-builder` (rough idea → task prompt).

## Definition of Done

A task is not done, and you may not say it is, until every line is ✅ or
explicitly n/a. Paste this checklist with evidence in your final message.

- [ ] Work is on its own branch in its own worktree; plan was approved.
- [ ] Diff matches the plan — nothing out of scope, no parallel duplicate of existing work.
- [ ] `python backend/tests/run_all_tests.py` run **by you, now**; result quoted (pass count; only known OCR failures).
- [ ] Every bug fix has a regression test; new test files registered; Anthropic mocked.
- [ ] Every touched route has `@require_role`; every touched document query is team-scoped (or the gap is written in the plan).
- [ ] UI changed → headless screenshots at 1440/768/375 and several scroll positions, **opened and looked at**; the goal is visible in them; paths recorded.
- [ ] No secrets, `.env`, `*.db`, real customer data, or placeholder text in the diff.
- [ ] Unready features behind an env flag defaulting off.
- [ ] Branch committed and pushed; `reviewer` verdict MERGE (or every FIX FIRST item fixed).
- [ ] TASKS.md (primary checkout) updated: row moved, handoff block current.
- [ ] Plain-English explanation given to the user, including what was *not* verified.
