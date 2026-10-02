# TASKS — single source of truth for work in progress

Last verified against git: **2026-10-01** (`main` = `origin/main` = `a794f0e`).
Update this file at the end of every task. "Ahead/behind" = commits relative to `main`.

## Done (merged into main)

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `feature/deal-mismatch-report` | none | Deal Mismatch Report: rent roll vs. lease discrepancies with dollar impact, citations, export; analyst role required on its routes | Fully merged (`e2c4848`). Branch can be deleted. |
| `feature/landing-positioning` (first round) | `~/dev/projects/abstractly-landing` | Multifamily-syndicator landing page + Book a Demo | Merged `d6ff92d`. **2 newer commits not merged** → see Ready for review |
| `feature/pricing-page` (first round) | `~/dev/projects/abstractly-pricing` | Config-driven pricing page + marketing redesign | Merged `a794f0e`. **3 newer commits not merged** → see Ready for review |
| `worktree-agent-a3fcc0f…`, `-a640a39f…`, `-a671d27b…` | none (local only) | Old agent branches (sample lease onboarding, owner console tests, rent roll import fixes) | Fully merged. Safe to delete. |

## Ready for review (pushed, not merged)

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `feature/t12-crosscheck` | `~/dev/projects/abstractly-t12crosscheck` | T-12 cross-check in the Deal Mismatch Report (`t12_statement.py`, API, export, UI) | +2 / −6. Clean worktree. Reviewed in a prior session (record the verdict here). |
| `feature/usage-limits` | `~/dev/projects/abstractly-usage` | Anthropic-spend protection: per-team file/rate limits and quotas. **Adds a `teams` table + `team_id` on users** | +4 / −6. **Built on t12's first commit `b397b40`** (not its test fix `9e1445c`). Last commit `4a4deca` fixes the reviewer-flagged bypass (limits skipped when `team_id` missing). Confirm with the reviewer that it's the complete fix, and settle whether its 4 failing tests are pre-existing. Untracked `PLAN.md` in the worktree. |
| `feature/pricing-page` (round 2) | `~/dev/projects/abstractly-pricing` | Flat per-team pricing ($499/$399, $1,250/$999, Enterprise), fluted-glass WebGL hero, sticky header, Lenis, new logo | +3 / −1. Clean worktree. Frontend only. |
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | Loan underwriting module for multifamily lenders, feature-flagged **off** by default (`LOAN_UNDERWRITING_ENABLED`, and the frontend nav item is hidden too via `GET /config`'s new `loan_underwriting_enabled`). Pure-Python engine (underwritten NOI, debt service with interest-only, DSCR/LTV/debt yield/breakeven, max loan by each constraint, 5 stress tests, a DSCR rate x occupancy sensitivity grid), full T-12 line-item parsing, a professional Word credit memo (cover summary table, consistent styling, every number source-cited) from a swappable template, a full UI matching the app's existing style, and 8 flag-gated routes. See `PLAN.md`, `SUMMARY.md`, and `OVERNIGHT_REPORT.md` for the full write-up. | **69/70 suite files pass** (same pre-existing `test_document_extractor.py`/tesseract failure as main). **117 new tests** across 6 files, all registered in `run_all_tests.py`; every Anthropic call in the suite is mocked. **Creates NO users/teams/tenant schema** — only `loan_requests` + `t12_snapshots`. **Not team-isolated** by explicit instruction; retrofit documented in `SUMMARY.md` → "Where team isolation plugs in". Verified end-to-end with headless Playwright (found and fixed a real ~120ms CSS layout bug in the process — see `OVERNIGHT_REPORT.md`). End-to-end run on the Maple Ridge demo deal saved to `demo_output/` (committed). Pushed, not merged. **`main` has since merged both `feature/usage-limits` (real teams table) and `fix/rent-roll-hardening` (real Maple Ridge fixture package) — this branch has not been rebased/merged against that yet; see `OVERNIGHT_REPORT.md`'s "What you should review first".** |
| `feature/landing-positioning` (round 2) | `~/dev/projects/abstractly-landing` | `391b49f` reject boolean `units` in Book a Demo (backend + test); `cd91ed0` scroll-linked fluted-glass shader, dark theme | +2 / −7. **Worktree has staged, uncommitted changes** to `background-fx.js`, `index.html`, `landing.css`, `pricing.html`. Commit or discard them before merging. |

### Recommended merge order (one at a time; smoke test the tester deployment after each, since every main push redeploys prod, tester, and demo)

1. **`feature/t12-crosscheck`**: self-contained backend feature, and `usage-limits` is built on it. Merging it first turns usage-limits' diff into just its own changes.
2. **`feature/usage-limits`**: rebase/merge onto main *after* step 1. Expect conflicts in `tests/test_t12_statement.py`, `tests/test_deal_mismatch_t12.py`, `tests/run_all_tests.py` (its copies predate t12's test fix `9e1445c`), so **take t12's versions**. Highest-risk merge: it touches `api.py`, `auth.py`, `database.py` (schema migration into a Legacy team) and 10 test files. Run the full suite before and after. It also establishes the **teams model** that loan-underwriting and isolation work should build on.
3. **`feature/pricing-page`**: frontend only, no overlap with steps 1–2. Merge before landing because it's the newer, larger redesign and it carries the real pricing.
4. **`feature/landing-positioning`**: overlaps pricing-page heavily (`landing.css`, `index.html`, `pricing.html`, `vendor/lenis.min.js`, and both add a fluted-glass background). Recommended: **cherry-pick only `391b49f`** (the Book a Demo validation fix + test) onto main, and drop `cd91ed0` plus the uncommitted shader edits unless you prefer that look over pricing-page's hero.

Steps 1–2 (backend) and 3–4 (marketing frontend) don't touch the same files, so the two pairs can go in either order. Backend first gets testers the T-12 check and spend limits sooner.

## In progress

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `fix/rent-roll-hardening` | `~/dev/projects/abstractly-rentroll-qa` | QA/hardening of the rent roll pipeline: import edge cases, route-role checks, Maple Ridge golden-file test, stress test report (`QA_PLAN.md`) | **0 commits**; all work is uncommitted (7 modified files plus new tests, `benchmark_data/demo_deal/`, `ACCURACY_REPORT.md`, docs). Not pushed. Commit and push before anything else happens to that worktree. |
| Cloud session branches (**not found**) | — | Multifamily lease fields; rent roll multi-format parsing; Stripe payments; pre-launch audit; tester onboarding and feedback; legal and trust pages; pre-tester bug fixes | **None of these exist locally or on `origin`** (checked `git branch -a` + `git ls-remote` on 2026-10-01). Either still running in cloud sessions or never pushed. A stash references `fix/pre-tester-bugs`, which also doesn't exist. Add each one here with its real branch name once pushed. |
| `worktree-agent-ade7619750bfa9a9f` | `.claude/worktrees/agent-ade76…` | Early multi-tenant isolation attempt (`accounts` table, `account_id`) | +3 / −65, local only, from 2026-09-02; untracked `test_multi_tenant_isolation.py`. **Stale, and conflicts with usage-limits' `teams` model.** Mine it for ideas, then delete. |

## Blocked

- **Anthropic API account needs credits funded.** Without it, AI extraction and the assistant fall back to the regex engine, and the AI engine can't be QA'd. Only the user can fund it.
- **Tester deployment has no persistent storage.** Free tier, no `disk:`. Tester uploads vanish on every deploy, restart, or 15-min idle spindown. Same for prod. Fix: Starter plan + disk + `DB_PATH` (`docs/DEPLOYMENT.md`).
- **Tester frontend points at the production API (found 2026-10-01).** `frontend/config.js` maps only localhost and `abstractly-demo.onrender.com`. `abstractly-tester.onrender.com` falls through to `abstractly-api`, and the tester site's CSP only allows `abstractly-tester-api`, so the tester app's API calls will fail. No branch fixes this. Needs a small fix branch (with a test) **before inviting testers**.
- **No team isolation on main.** One shared data pool per deployment. Fine for one tester per deployment; blocks multiple testers on one deployment.

## Up next

1. Merge the Ready-for-review branches one at a time, in the order above (only when the user says so).
2. Fix the tester `config.js` routing (blocker above).
3. Smoke test the tester deployment: `/health`, login, upload a Maple Ridge lease + rent roll, Deal Mismatch Report, PDF/Excel export, T-12 cross-check.
4. Invite the first 3 testers.
