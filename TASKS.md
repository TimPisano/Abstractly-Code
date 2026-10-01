# TASKS — single source of truth for work in progress

Last verified against git: **2026-10-01, evening** (`git fetch --all`,
every branch/worktree walked individually). "+a / −b" = commits ahead of
/ behind `main`.

**Local `main` is 9 commits ahead of `origin/main`** (the three merges
below happened locally but were never pushed). `render.yaml` deploys
every service from `origin`'s `main`, so **none of this is live yet** —
prod/tester/demo are still running old code. Push only when the user
explicitly says so in that session (CLAUDE.md rule 2).

## Done (merged into local main)

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `fix/tester-api-routing` | `~/dev/projects/abstractly-tester-routing` | Fixed the tester frontend calling production's API (CSP was blocking it); added a test that checks every frontend/API pair in `render.yaml` against `config.js` and the CSPs | Merged `b6a46e9`. Worktree still has the branch checked out — safe to remove once pushed. |
| `feature/t12-crosscheck` | `~/dev/projects/abstractly-t12crosscheck` | T-12 cross-check in the Deal Mismatch Report | Merged `0ee711c`. |
| `feature/usage-limits` | `~/dev/projects/abstractly-usage` | Anthropic-spend protection: adds the **`teams` table + `users.team_id`**, per-team file/rate limits and quotas, upload dedup. Billing/quota scope only — does not scope `leases`/`discrepancies`/`alerts`/`tasks`. | Merged `ab7fb6f`. This is the schema `feature/team-isolation` builds document-level scoping on top of — see Decisions log. |
| `feature/deal-mismatch-report` | none | Deal Mismatch Report: discrepancies with dollar impact, citations, export; analyst role required | Merged `e2c4848`. |
| `feature/landing-positioning` (round 1) | `~/dev/projects/abstractly-landing` | Multifamily-syndicator landing page + Book a Demo | Merged `d6ff92d`. Round 2 below is newer, separate work. |
| `feature/pricing-page` (round 1) | `~/dev/projects/abstractly-pricing` | Config-driven pricing page + marketing redesign | Merged `a794f0e`. Round 2 below is newer, separate work. |
| `worktree-agent-a3fcc0f…`, `-a640a39f…`, `-a671d27b…` | none (local only) | Old agent branches (sample lease onboarding, owner console tests, rent roll import fixes) | Fully merged. Safe to delete (`git worktree remove` / `git branch -d`). |
| (docs) | — | `CLAUDE.md` + `TASKS.md` committed to main; `TEAM_AUDIT.md` (external, read-only audit of the tenancy question, lives at `~/dev/projects/TEAM_AUDIT.md` — not part of this repo) | `64af20a`, 2026-10-01. |

## Ready for review (pushed to origin, not merged)

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `feature/pricing-page` (round 2) | `~/dev/projects/abstractly-pricing` | Flat per-team pricing ($499/$399, $1,250/$999, Enterprise), fluted-glass WebGL hero, sticky header, Lenis, new logo | +11 / −6 vs. main, pushed to origin. Clean worktree. Frontend only. Confirm it's finished iterating before merging. |
| `feature/landing-positioning` (round 2) | `~/dev/projects/abstractly-landing` | Reject boolean `units` in Book a Demo (backend + test); scroll-linked fluted-glass shader, dark theme | +17 / −2 vs. main, pushed to origin. **Worktree has uncommitted changes** to `background-fx.js`, `index.html`, `landing.css`, `pricing.html` — commit or discard before this is actually reviewable. Overlaps pricing-page round 2 heavily (same files, both add a fluted-glass background); recommend cherry-picking only the Book a Demo fix and dropping the shader work in favor of pricing-page's hero. |

### Recommended merge order (one at a time; smoke test the tester deployment after each — but see the push note at the top, nothing reaches the live deployments until `main` is pushed)

0. **Push current local `main`** (9 commits: tester-routing → t12-crosscheck → usage-limits), once the user says so — this alone unblocks testers and ships the T-12 check + spend limits.
1. **`feature/pricing-page` (round 2)**: frontend only, no overlap with anything already merged.
2. **`feature/landing-positioning` (round 2)**: resolve its uncommitted changes first; cherry-pick the Book a Demo validation fix, drop the competing shader work (or decide which hero wins).
3. **`fix/rent-roll-hardening`**: once its QA is finished (see In progress). Overlaps only `tests/run_all_tests.py` (list entries — keep both sides).
4. **`feature/team-isolation`**: once built out (see In progress) — this is the riskier, `database.py`/`api.py`-wide change; run the full suite before and after.

## In progress

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `fix/rent-roll-hardening` | `~/dev/projects/abstractly-rentroll-qa` | QA/hardening of the rent roll pipeline: import edge cases, negative-rent sign loss, multifamily tenant extraction, route-role checks, **Maple Ridge demo deal** + golden-file test | +10 / −2, pushed (`d168b0f`). Clean worktree. QA still in progress; move to Ready for review when finished. |
| `feature/team-isolation` | `~/dev/projects/abstractly-teams` | Document-level team isolation: extend `team_id` (from `feature/usage-limits`) to `leases`, `discrepancies`, `alerts`, `tasks`, comments, assignments, activity/health-score caches | 0 commits yet, local only, not pushed. `PLAN.md` drafted (uncommitted) — already decided to build on `usage-limits`'s `team_id`, not a second `account_id` schema, and to mine `worktree-agent-ade76…` for which routes need scoping. This independently matches `TEAM_AUDIT.md`'s recommendation (written the same day, in parallel) — both arrived at the same answer without seeing each other. |
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | Loan underwriting engine for multifamily lenders + T-12 line-item parsing, feature-flagged **off** | +9 / −2, local only, not pushed. **Uncommitted changes** to `PLAN.md`, `api.py`, `database.py`, `tests/run_all_tests.py` — another session may be active here; don't disturb without checking. Its own `PLAN.md` already decided (mid-build, per the user's instruction) to add **no** team/tenant columns itself and defer entirely to `feature/team-isolation` — nothing to reconcile once that lands. |
| `worktree-agent-ade7619750bfa9a9f` | `.claude/worktrees/agent-ade76…` | Early, comprehensive multi-tenant isolation attempt (`accounts` table, `account_id` on nearly every document table) | +7 / −66, local only, stale (2026-09-02). **Confirmed cross-tenant leak**: `GET /leases/<other-account's-lease>/fields/<field>/source` returns 200 with the other account's data (`get_field_source_chain()` was never given the `account_id` parameter `get_lease()` got). Also deletes bearer-token auth that `frontend/app/api.js` still depends on. **Do not merge.** Mine its route list as a checklist for `feature/team-isolation`, then delete. |

## Blocked

- **Anthropic API account needs credits funded.** Without it, AI extraction and the assistant fall back to the regex engine, and the AI engine can't be QA'd. Only the user can fund it.
- **Tester deployment has no persistent storage.** Free tier, no `disk:`. Tester uploads vanish on every deploy, restart, or 15-min idle spindown. Fix: Starter plan + disk + `DB_PATH` (`docs/DEPLOYMENT.md`). Needs the user (Render billing).
- **No document-level team isolation on main.** Billing/quota `team_id` exists (`feature/usage-limits`, merged), but no document table is scoped yet — one shared pool per deployment, still fine for one tester per deployment, blocks multiple firms on one deployment. `feature/team-isolation` is the path out (see In progress + Decisions log).

## Up next

1. Push local `main` to `origin` (only when the user says so) — unblocks the tester deployment with the already-merged routing fix, T-12 check, and spend limits.
2. Merge the Ready-for-review branches in the order above (only when the user says so).
3. Keep building out `feature/team-isolation`; reconcile `feature/loan-underwriting` onto it once document scoping lands.
4. `feature/deal-assistant` (`~/dev/projects/abstractly-assistant`): worktree created, **0 commits, nothing built yet** — the planned in-app portfolio assistant. Not started.
5. Smoke test the tester deployment once pushed: `/health`, login, upload a Maple Ridge lease + rent roll, Deal Mismatch Report, PDF/Excel export, T-12 cross-check.
6. Invite the first 3 testers.

### Housekeeping

- Untracked in the main checkout: `backend/benchmark_data/{ACCURACY_REPORT.md,demo_deal/,last_run.json}` (these land properly with `fix/rent-roll-hardening` — delete the untracked copies before that branch merges or git will refuse); `docs/PLAN_t12_crosscheck.md` and `docs/TESTER_VERIFICATION_CHECKLIST.md` (working notes from the now-merged t12/tester-routing branches that never got committed — decide commit vs. discard); `drafts/sales/` (expected `outreach` subagent output, intentionally kept local/uncommitted).
- `PLAN.md` and `SUMMARY.md` at the repo root are **committed on `main`** (landed as part of the `feature/usage-limits` merge, `ab7fb6f`) — these are meant to be per-worktree scratch docs, not permanent root files. Flagged, not touched this session (out of scope for a process-only pass); worth a small cleanup commit later.
- Test-setup note: `backend/tests/sample_lease.pdf` is gitignored. In a fresh worktree, run `python backend/tests/create_sample_lease.py` first, or `test_extraction.py`, `test_synthetic_accuracy.py` and `test_multi_lease_detection.py` fail with "file not found." That isn't real breakage.

## Decisions log

- **2026-10-01 — Team isolation converges on `feature/usage-limits`'s `teams`/`team_id` schema**, not the stale branch's `accounts`/`account_id` one. Reached independently twice the same day: by `~/dev/projects/TEAM_AUDIT.md` (external audit) and by `feature/team-isolation`'s own `PLAN.md` (which didn't know the audit existed yet when it was written). Reasons: already merged and reviewed, proven migration pattern (`_migrate_*` + "Legacy" team backfill), and billing + visibility belong on one entity, not two that can drift apart.
- **2026-10-01 — Merge order executed on local `main`:** `fix/tester-api-routing` → `feature/t12-crosscheck` → `feature/usage-limits`, in that order, resolving the expected test-file conflicts by taking t12's versions. Not yet pushed to `origin` — see the note at the top of this file.
- **(prior) One-firm-per-deployment pattern**: until document-level isolation exists, each tester/customer gets its own Render service + database rather than sharing one deployment. Revisit once `feature/team-isolation` lands.
