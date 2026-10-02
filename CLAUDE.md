# Abstractly — project instructions for Claude

Read this file and `TASKS.md` at the start of every session. `TASKS.md` is
the single source of truth for what's in flight; this file is the standing
context and rules. (`docs/CLAUDE.md` is an outdated stub from the first
prototype; ignore it.)

## What Abstractly is

SaaS for **mid-size multifamily syndicators**. It reads the leases behind a
rent roll and checks them unit by unit before a deal closes.

Core features:
- **Lease abstraction**: AI extraction of lease terms, each with a source page citation.
- **Rent roll validation**: reconcile the seller's rent roll against the actual leases (the core feature).
- **Deal Mismatch Report**: every rent roll vs. lease discrepancy with its **dollar impact** and **source page citations**.
- **PDF and Excel export** of the report.
- **T-12 cross-check**: compare the T-12 operating statement's collections against rent roll / lease rent.

Positioning: the main competitor is **Prophia**, which serves institutional
*office* owners. We win on multifamily focus, rent roll validation as the
core feature, and dollar-impact reports.

Business model: customers sign contracts. Pricing is a flat monthly fee per
team:

| Plan | Monthly | Annual (per month) |
|---|---|---|
| Starter | $499 | $399 |
| Growth | $1,250 | $999 |
| Enterprise | custom | custom |

(That pricing is live only on `feature/pricing-page`. `main` still shows
the old per-property placeholder prices. See TASKS.md.)

**Current goal: get the first outside beta testers onto the tester deployment.**

## Tech stack and architecture (as found in the code)

- **Backend:** Python 3.11, Flask 3, single app in `backend/app/api.py`
  (large; most routes live there). Served by gunicorn (`backend/start.sh`).
  Domain modules sit beside it: `deal_mismatch.py`, `deal_mismatch_export.py`,
  `rent_roll_import.py`, `t12_import.py`, `ai_extraction.py`,
  `pdf_extractor.py` (pypdf/pdfplumber + Tesseract OCR fallback), `auth.py`,
  `database.py`, `security.py`.
- **Frontend:** vanilla JS/HTML/CSS, **no framework, no build step**.
  `frontend/index.html` + `pricing.html` = marketing site; `frontend/app/` =
  the customer app; `frontend/admin/`, `frontend/owner/` = staff consoles.
  `frontend/config.js` picks the API base URL from the page's hostname.
- **Database:** SQLite (`database.py`, a fresh short-lived connection per
  call). **No Render service has a persistent disk**, so every deploy or
  restart wipes the data on prod, tester, and demo alike. See
  `docs/DEPLOYMENT.md` → "Adding persistent storage later".
- **Background jobs:** RQ on Redis (Upstash). `backend/worker.py` runs in
  the **same container** as gunicorn (started by `start.sh`). Each
  deployment uses its own queue name (`LEASE_EXTRACTION_QUEUE`:
  default / `extraction-tester` / `extraction-demo`).
- **Anthropic API:** `anthropic` SDK. Lease extraction (`ai_extraction.py`,
  env `LEASE_EXTRACTION_MODEL`, default `claude-sonnet-5`), the portfolio
  assistant (`assistant.py`, `ASSISTANT_MODEL`, `claude-sonnet-5`), CRE Q&A
  (`cre_qa.py`, `CRE_QA_MODEL`, `claude-haiku-4-5`), and AI rent roll
  validation (`ai_rent_roll_validation.py`). Without `ANTHROPIC_API_KEY`
  the app falls back to the rule-based regex engine.
- **Auth and roles:** session cookie for admin and a bearer token for the
  `app/` client (`auth.py`). Roles rank `viewer < analyst < admin`
  (`ROLE_RANK`), enforced with `@require_role('analyst')` etc.;
  `is_owner` is a separate flag (`@require_owner`) and is never implied
  by `admin`.
- **Tenancy today:** there is **no `team_id` / teams table on `main`**.
  Isolation is currently *per deployment* (that is why tester and demo are
  separate Render services). A `teams` table + `team_id` arrives with
  `feature/usage-limits` — that is the **one** teams model; don't add a
  second. (`feature/loan-underwriting` originally planned its own; that
  was reverted on 2026-10-01 on explicit instruction. It now creates no
  users/teams/tenant schema at all, and documents where its own two
  tables gain a `team_id` once the usage-limits model merges — see that
  branch's `SUMMARY.md` → "Where team isolation plugs in".)

### Render services (`render.yaml`, Blueprint)

| Service | Kind | URL | Purpose |
|---|---|---|---|
| `abstractly-api` | Docker web | abstractly-api.onrender.com | Production API |
| `abstractly` | static | abstractly-n0id.onrender.com | Production site/app |
| `abstractly-tester-api` | Docker web | abstractly-tester-api.onrender.com | Beta tester API, own empty DB |
| `abstractly-tester` | static | abstractly-tester.onrender.com | Beta tester frontend |
| `abstractly-demo-api` | Docker web | abstractly-demo-api.onrender.com | Demo, `DEMO_MODE`, seeded, `/demo/reset` |
| `abstractly-demo` | static | abstractly-demo.onrender.com | Demo frontend |

All six are on the free plan. `render.yaml` sets **no `branch:`**, so every
service auto-deploys from the Blueprint's linked branch, **`main`**. Any
push to main redeploys prod, tester, and demo at once. (Verify in the
Render dashboard if that ever matters; it can be overridden there.)
Secrets live only in the Render dashboard (`sync: false`). Full runbook:
`docs/DEPLOYMENT.md`.

### Running locally

```bash
cd backend && source venv/bin/activate && python run.py      # API on :5000
cd frontend && python3 -m http.server 8080                    # site on :8080
python backend/tests/run_all_tests.py                         # unit tests (plain-script convention)
python backend/tests/run_all_tests.py --live                  # + live API tests (needs run.py up)
```

New test files must be registered in `backend/tests/run_all_tests.py`.
pytest is also installed in the venv. More detail: `docs/LOCAL_DEV.md`.

### Other docs worth knowing

`docs/DECISIONS.md` (architecture decisions), `docs/DEPLOYMENT.md`,
`docs/OPERATIONS.md`, `docs/HARDENING_LOG.md`,
`docs/TESTER_VERIFICATION_CHECKLIST.md`, `PLAN.md` (the active branch's
plan; each worktree may have its own).
Subagents in `.claude/agents/`: `engineer`, `reviewer`, `accuracy-tester`,
`product-strategist`, `outreach` (drafts only, never sends).

## Standing rules for every session

1. **Never open the user's browser.** Run servers in the background and
   give the URL. Use **headless Playwright** for any visual check.
2. **Never merge into `main` or push `main`** unless the user explicitly
   says so *in that session*. Do all work on a feature branch in **its own
   git worktree under `~/dev/projects/`** (e.g. `~/dev/projects/abstractly-<topic>`).
   Don't switch branches in someone else's worktree, and check
   `git worktree list` first.
3. **Enforce team-level data isolation and correct roles on every route
   and query** you add or touch: scope every query by the caller's team and
   put an explicit `@require_role(...)` on every route. Because `main` has
   no team model yet, if a change needs isolation that doesn't exist on
   your branch, say so and build on the agreed teams model. Never silently
   ship an unscoped route.
4. **Never commit secrets, `.env` files, `*.db` files, or real customer
   data.** Use fictional data such as the **Maple Ridge** demo deal
   (`backend/benchmark_data/demo_deal/`, not yet committed; it lands with
   `fix/rent-roll-hardening`) and the synthetic fixtures in `backend/tests/`.
5. **Mock the Anthropic API in tests.** Do not run real AI benchmarks
   repeatedly; they cost money. Ask before any real-API run.
6. **Write a test for every bug fix**: a regression test that fails
   before the fix and passes after.
7. **Explain changes in plain English when done.** The user is still
   learning backend development, so briefly teach the important pattern
   behind the change (e.g. why a query is scoped, why a decorator is there).
8. **Keep `TASKS.md` updated at the end of every task**: move items
   between sections, and record branch, worktree, and status.
9. **Known pre-existing failures:** OCR tests that need `tesseract` /
   `poppler` installed locally (e.g. `test_real_ocr.py`, `test_ocr_fallback.py`)
   fail on machines without them. Don't treat those as new breakage, but do
   report any *other* failure.

## Conventions

- Match the surrounding code: long explanatory comments on *why*, plain
  Python, no new frameworks.
- New features that aren't ready for testers go behind an env-var feature
  flag that defaults **off**.
- Small, focused commits with clear messages; one concern per branch.
