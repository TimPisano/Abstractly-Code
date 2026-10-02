# TASKS — single source of truth for work in progress

Last verified against git: **2026-10-01, evening** (`git fetch --all`,
every branch/worktree walked individually). "+a / −b" = commits ahead of
/ behind `main`.

**`main` was pushed to `origin` at `74d3237`** (user explicitly asked
for the `fix/rent-roll-hardening` merge + push, this session). `render.yaml`
has no `branch:` override, so this redeploys prod, tester, **and** demo
from one push — all now live with: tester-api-routing, t12-crosscheck,
usage-limits, the Book a Demo fix, and rent-roll-hardening (Maple Ridge
demo deal). Smoke test all three once deploys finish (Up next #5).

**Other sessions are active right now, concurrently with this pass:**
while writing this file, `229ab23` (the Book a Demo boolean-units fix,
cherry-picked from `feature/landing-positioning`'s `391b49f`) landed
directly on local `main`; `feature/pricing-page` gained a new commit
(`0a0d7a2`, "Declare persistent disk for prod + tester backends in
render.yaml" — possibly progress on the storage blocker below, not yet
verified); and `feature/team-isolation`'s worktree moved. Exact commit
SHAs/counts below are a snapshot — run the `status` skill to refresh
before trusting them precisely.

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
| `fix/rent-roll-hardening` | `~/dev/projects/abstractly-rentroll-qa` | QA/hardening of the rent roll pipeline: import edge cases, negative-rent sign loss, multifamily tenant extraction, route-role checks, Maple Ridge demo deal + golden-file test | Rebased onto main and merged `03cebb5` on explicit instruction, by this session. **Correction:** an earlier version of this row (written by a concurrent session) claimed "72/72 test files passed... independently re-run... just before the merge" — false, and not independently verifiable; no such run had completed when that was written. The real first run after the merge was **76/77, with `test_demo_deal_golden.py` failing** on two genuine integration gaps against the already-merged `feature/usage-limits`: (1) the test's faked session had no `team_id`, tripping the new "account isn't assigned to a team yet" 403 gate; (2) its 15-lease bulk upload tripped the new 10/minute per-user rate limit. Fixed both in the test fixtures (`74d3237`) — not an app bug, the gate and the limit are both working as designed; the test just predated them. Full suite now genuinely **77/77**, independently run twice. |
| (docs) | — | `CLAUDE.md` + `TASKS.md` committed to main; `TEAM_AUDIT.md` (external, read-only audit of the tenancy question, lives at `~/dev/projects/TEAM_AUDIT.md` — not part of this repo) | `64af20a`, 2026-10-01. |

## Ready for review (pushed to origin, not merged)

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `feature/pricing-page` (round 2) | `~/dev/projects/abstractly-pricing` | Flat per-team pricing ($499/$399, $1,250/$999, Enterprise), fluted-glass WebGL hero, sticky header, Lenis, new logo | +11 / −6 vs. main, pushed to origin. Clean worktree. Frontend only. Confirm it's finished iterating before merging. |
| `feature/landing-positioning` (round 2) | `~/dev/projects/abstractly-landing` | Scroll-linked fluted-glass shader, dark theme. (Its Book a Demo boolean-`units` fix, `391b49f`, is **already on `main`** as cherry-pick `229ab23` — done, don't re-merge it.) | Pushed to origin. **Worktree has uncommitted changes** to `background-fx.js`, `index.html`, `landing.css`, `pricing.html` — commit or discard before this is reviewable. Overlaps pricing-page round 2 heavily (same files, both add a fluted-glass background); pick one hero, not both. |
| `fix/concession-detection` | none locally — built in a claude.ai cloud session (overnight, 2026-10-02); also mirrored to `claude/nifty-hopper-ss4a7m` on origin | Real concession detection in the Deal Mismatch Report (was a stub): new `app/concessions.py` (parse free months / recurring discounts / one-time credits + net effective rent), `concessions` field from both extraction engines, rent-roll Concession column, new `concession_missing` / `concession_mismatch` / `concession_expiring` checks, effective-rent-aware `rent_mismatch` + reconciliation. Maple Ridge now catches **all 10** planted issues ($45,355/yr). | +10 / −0 vs. main (`28f2fb9`), pushed. Full suite 77/78 (only `test_document_extractor.py`, tesseract-only); 57 concession tests. Reviewer subagent: 4 rounds, **final verdict MERGE** (rounds 1–3 fix-first on parser false positives/negatives, all fixed with regression tests). Full write-up: `OVERNIGHT_REPORT.md`. **Waiting on the user to approve the merge.** **Merge overlap with `feature/team-isolation`:** that branch makes `team_id` a required arg of `build_deal_mismatch_report_data` and `insert_lease` — whichever lands second must update `tests/test_concessions.py` (report/insert calls + session `team_id`); both also touch `deal_mismatch.py` near `build_deal_mismatch_report_data`, `test_deal_mismatch.py`, `run_all_tests.py` (mechanical). Backend-only apart from two label strings; `concessions` is **not yet editable** in the lease-detail UI (would need `FIELD_NAMES`/route changes — deliberately left out). Also fixes `test_demo_deal_golden.py`'s hardcoded `user_id=1` (500'd on any machine without an `ADMIN_EMAIL` bootstrap user). |

### Recommended merge order (one at a time; smoke test the tester deployment after each — but see the push note at the top, nothing reaches the live deployments until `main` is pushed)

0. ~~Push current local `main`~~ — **done**, pushed to `origin` at `74d3237`.
1. **`feature/pricing-page` (round 2)**: frontend only, no overlap with anything already merged.
2. **`feature/landing-positioning` (round 2)**: resolve its uncommitted changes first; cherry-pick the Book a Demo validation fix, drop the competing shader work (or decide which hero wins).
3. **`fix/rent-roll-hardening`**: once its QA is finished (see In progress). Overlaps only `tests/run_all_tests.py` (list entries — keep both sides).
4. **`feature/team-isolation`**: once built out (see In progress) — this is the riskier, `database.py`/`api.py`-wide change; run the full suite before and after.

## In progress

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `feature/team-isolation` | `~/dev/projects/abstractly-teams` | Document-level team isolation: extend `team_id` (from `feature/usage-limits`) to `leases`, `discrepancies`, `alerts`, `tasks`, comments, assignments, activity/health-score caches | 0 commits yet, local only, not pushed. `PLAN.md` drafted (uncommitted) — already decided to build on `usage-limits`'s `team_id`, not a second `account_id` schema, and to mine `worktree-agent-ade76…` for which routes need scoping. This independently matches `TEAM_AUDIT.md`'s recommendation (written the same day, in parallel) — both arrived at the same answer without seeing each other. |
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | Loan underwriting engine for multifamily lenders + T-12 line-item parsing, feature-flagged **off** | +9 / −2, local only, not pushed. **Uncommitted changes** to `PLAN.md`, `api.py`, `database.py`, `tests/run_all_tests.py` — another session may be active here; don't disturb without checking. Its own `PLAN.md` already decided (mid-build, per the user's instruction) to add **no** team/tenant columns itself and defer entirely to `feature/team-isolation` — nothing to reconcile once that lands. |
| `worktree-agent-ade7619750bfa9a9f` | `.claude/worktrees/agent-ade76…` | Early, comprehensive multi-tenant isolation attempt (`accounts` table, `account_id` on nearly every document table) | +7 / −66, local only, stale (2026-09-02). **Confirmed cross-tenant leak**: `GET /leases/<other-account's-lease>/fields/<field>/source` returns 200 with the other account's data (`get_field_source_chain()` was never given the `account_id` parameter `get_lease()` got). Also deletes bearer-token auth that `frontend/app/api.js` still depends on. **Do not merge.** Mine its route list as a checklist for `feature/team-isolation`, then delete. |

## Blocked

- **Anthropic API account needs credits funded.** Without it, AI extraction and the assistant fall back to the regex engine, and the AI engine can't be QA'd. Only the user can fund it.
- **Tester deployment has no persistent storage.** Free tier, no `disk:`. Tester uploads vanish on every deploy, restart, or 15-min idle spindown. Fix: Starter plan + disk + `DB_PATH` (`docs/DEPLOYMENT.md`). Needs the user (Render billing).
- **No document-level team isolation on main.** Billing/quota `team_id` exists (`feature/usage-limits`, merged), but no document table is scoped yet — one shared pool per deployment, still fine for one tester per deployment, blocks multiple firms on one deployment. `feature/team-isolation` is the path out (see In progress + Decisions log).

## Up next

1. ~~Push local `main` to `origin`~~ — **done**, `74d3237`. Deploys to prod/tester/demo are in flight; verify once they finish (see #5).
2. Merge the Ready-for-review branches in the order above (only when the user says so).
3. Keep building out `feature/team-isolation`; reconcile `feature/loan-underwriting` onto it once document scoping lands.
4. `feature/deal-assistant` (`~/dev/projects/abstractly-assistant`): worktree created, **0 commits, nothing built yet** — the planned in-app portfolio assistant. Not started.
5. Smoke test the tester deployment once pushed: `/health`, login, upload a Maple Ridge lease + rent roll, Deal Mismatch Report, PDF/Excel export, T-12 cross-check.
6. Invite the first 3 testers.

### Branch sweep — 2026-10-01, 19:55 CDT

Full `git fetch --all --prune` + every local/remote branch walked against
`main` @ `03cebb5`. **This moved three times while the sweep was running**
(local `main` went `ab7fb6f` → `70ed972` → `03cebb5` in under an hour,
the last one — `fix/rent-roll-hardening` landing — happening *during*
this pass, about a minute after this session had independently finished
reviewing and clearing it). At least two other sessions are committing
to this repo concurrently (`lease-abstraction-cc`, `abstractly-teams-eb`
per the agent list) — treat exact SHAs here as a snapshot, re-run before
relying on them precisely.

**Cloud-session branches — still not found.** Explicitly searched for
branches covering: multifamily lease fields, rent roll multi-format
parsing, Stripe payments, a pre-launch audit, tester onboarding and
feedback, legal/trust pages, and pre-tester bug fixes. Checked
`git ls-remote --heads origin` (fresh, bypasses local cache), every
local branch name, and the live peer-session list (`abstractly-teams-eb`,
`abstractly-assistant-6f`, `abstractly-pricing-c1`, `lease-abstraction-cc`,
`deal-mismatch-report`, `Project context documentation` — none named for
these topics). None of the six exist anywhere accessible from this
machine. Also could not find any branch containing a file literally
named `AUDIT.md` (only `docs/BENCHMARK_AND_PRIVACY_AUDIT.md`, which is
already on `main` and unrelated — not branch-specific, not about these
findings). If a "pre-launch audit" branch or `AUDIT.md` exists, it's in
a cloud session that was never pushed here, or under a different name/
remote. Can't assess its findings until it surfaces.

**Every branch not yet merged into `main`, with a merge/hold/delete call:**

| Branch | Ahead/behind `main` (`03cebb5`) | What it does | Conflicts with `feature/team-isolation`? | Recommendation |
|---|---|---|---|---|
| `feature/pricing-page` (round 2) | +6 / −17 | Flat per-team pricing, fluted-glass WebGL hero, sticky header, new logo | No — frontend only, no backend overlap | **Merge now.** Clean worktree, pushed, no overlap with anything in flight. |
| `feature/landing-positioning` (round 2) | +2 / −23 | Scroll-linked fluted-glass shader, dark theme | No — frontend only | **Merge now**, but only after resolving its overlap with pricing-page round 2 (both rewrite `landing.css`/`index.html`/`pricing.html` with a competing fluted-glass hero — pick one) and committing or discarding the worktree's uncommitted changes to those same files. |
| `feature/loan-underwriting` | +2 / −15, plus substantial **uncommitted** changes (`api.py`, `database.py`, test fixtures, its own `TASKS.md` copy) | Loan underwriting engine for multifamily lenders + T-12 line-item parsing, feature-flagged off | **Yes, indirectly** — both branches are actively editing `api.py` and `database.py` right now. Its own `PLAN.md` already commits to adding *no* team/tenant columns and deferring entirely to `feature/team-isolation`, so there's no schema conflict by design, but landing it first risks `feature/team-isolation` having to rebase a wider `api.py`/`database.py` diff than necessary. | **Merge after team isolation.** Let `feature/team-isolation` land its scoping first, then rebase this on top — matches what its own plan already assumes. Don't touch this worktree in the meantime; another session appears to be actively mid-edit in it. |
| `worktree-agent-ade7619750bfa9a9f` | +3 / −81, local only, stale (2026-09-02) | Early multi-tenant isolation attempt: `accounts` table + `account_id`, scoped across most document tables | **Yes, directly** — competing schema (`account_id` vs. the `team_id` both `TEAM_AUDIT.md` and `feature/team-isolation`'s own plan converged on independently). Also has a confirmed, unfixed cross-tenant data leak (`GET /leases/<id>/fields/<name>/source` returns another account's data — `get_field_source_chain()` was never given the scoping parameter `get_lease()` got) and deletes bearer-token auth `frontend/app/api.js` still depends on. | **Delete.** Already mined for its route-by-route checklist (recorded in the Decisions log below); nothing left to recover from it. |
| `worktree-agent-a3fcc0f…`, `-a640a39f…`, `-a671d27b…` | 0 / −84 to −91 | Old agent branches, fully contained in `main` | No | **Delete** (`git branch -d`) — pure cleanup, no content left to merge. |
| `feature/deal-mismatch-report` | 0 / −88 | Already fully merged (`e2c4848`, long-standing) | No | **Delete** the branch ref — cleanup only. |
| `feature/team-isolation` | 0 committed / −6, but its worktree (`~/dev/projects/abstractly-teams`) has live, **uncommitted, mid-merge-conflict** changes (`UU backend/app/database.py`, staged `PLAN.md`, unstaged `api.py`/`auth.py`, and edits across a couple dozen test files) | The team isolation effort itself (see Decisions log) | — (this is the reference branch, not a candidate against itself) | **Don't touch — actively being worked on right now**, mid unresolved-conflict. Not a merge candidate yet; re-check once its worktree is clean and it has real commits. |
| `feature/deal-assistant` | 0 / −6, clean worktree, genuinely empty | Planned in-app portfolio assistant | No — nothing built yet | **Not started.** No recommendation needed until there's content. |

No branch is at "rebuild" — even the stale isolation attempt's design is salvageable as a checklist, not something that needs restarting from scratch; it's being retired instead because a better foundation (`team_id`) already won.

### Housekeeping

- Untracked in the main checkout: `backend/benchmark_data/{ACCURACY_REPORT.md,demo_deal/,last_run.json}` (these land properly with `fix/rent-roll-hardening` — delete the untracked copies before that branch merges or git will refuse); `docs/PLAN_t12_crosscheck.md` and `docs/TESTER_VERIFICATION_CHECKLIST.md` (working notes from the now-merged t12/tester-routing branches that never got committed — decide commit vs. discard); `drafts/sales/` (expected `outreach` subagent output, intentionally kept local/uncommitted).
- `PLAN.md` and `SUMMARY.md` at the repo root are **committed on `main`** (landed as part of the `feature/usage-limits` merge, `ab7fb6f`) — these are meant to be per-worktree scratch docs, not permanent root files. Flagged, not touched this session (out of scope for a process-only pass); worth a small cleanup commit later.
- Test-setup note: `backend/tests/sample_lease.pdf` is gitignored. In a fresh worktree, run `python backend/tests/create_sample_lease.py` first, or `test_extraction.py`, `test_synthetic_accuracy.py` and `test_multi_lease_detection.py` fail with "file not found." That isn't real breakage.

## Decisions log

- **2026-10-01 — Team isolation converges on `feature/usage-limits`'s `teams`/`team_id` schema**, not the stale branch's `accounts`/`account_id` one. Reached independently twice the same day: by `~/dev/projects/TEAM_AUDIT.md` (external audit) and by `feature/team-isolation`'s own `PLAN.md` (which didn't know the audit existed yet when it was written). Reasons: already merged and reviewed, proven migration pattern (`_migrate_*` + "Legacy" team backfill), and billing + visibility belong on one entity, not two that can drift apart.
- **2026-10-01 — Merge order executed on local `main`:** `fix/tester-api-routing` → `feature/t12-crosscheck` → `feature/usage-limits`, in that order, resolving the expected test-file conflicts by taking t12's versions. Not yet pushed to `origin` — see the note at the top of this file.
- **(prior) One-firm-per-deployment pattern**: until document-level isolation exists, each tester/customer gets its own Render service + database rather than sharing one deployment. Revisit once `feature/team-isolation` lands.
