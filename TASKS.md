# TASKS — single source of truth for work in progress

Last verified against git: **2026-10-01, overnight pass** (`feature/team-isolation`
rebasing onto `origin/main` @ `28f2fb9`). "+a / −b" = commits ahead of /
behind `main`.

**`main` was pushed to `origin` at `74d3237`**, then advanced further to
`28f2fb9` by `fix/rent-roll-hardening`'s merge (Maple Ridge demo deal +
golden-file test) and a TASKS.md bookkeeping commit. `render.yaml` has
no `branch:` override, so every push to `main` redeploys prod, tester,
**and** demo from one push.

**Other sessions may still be active concurrently** — treat exact SHAs
here as a snapshot, re-run the `status` skill before relying on them
precisely.

## Done (merged into `main`, pushed to `origin`)

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `fix/tester-api-routing` | `~/dev/projects/abstractly-tester-routing` | Fixed the tester frontend calling production's API (CSP was blocking it); added a test that checks every frontend/API pair in `render.yaml` against `config.js` and the CSPs | Merged `b6a46e9`. Worktree still has the branch checked out — safe to remove once pushed. |
| `feature/t12-crosscheck` | `~/dev/projects/abstractly-t12crosscheck` | T-12 cross-check in the Deal Mismatch Report | Merged `0ee711c`. |
| `feature/usage-limits` | `~/dev/projects/abstractly-usage` | Anthropic-spend protection: adds the **`teams` table + `users.team_id`**, per-team file/rate limits and quotas, upload dedup. Billing/quota scope only — does not scope `leases`/`discrepancies`/`alerts`/`tasks`. | Merged `ab7fb6f`. This is the schema `feature/team-isolation` builds document-level scoping on top of — see Decisions log. |
| `feature/deal-mismatch-report` | none | Deal Mismatch Report: discrepancies with dollar impact, citations, export; analyst role required | Merged `e2c4848`. |
| `feature/landing-positioning` (round 1) | `~/dev/projects/abstractly-landing` | Multifamily-syndicator landing page + Book a Demo | Merged `d6ff92d`. Round 2 below is newer, separate work. |
| `feature/pricing-page` (round 1) | `~/dev/projects/abstractly-pricing` | Config-driven pricing page + marketing redesign | Merged `a794f0e`. Round 2 below is newer, separate work. |
| `worktree-agent-a3fcc0f…`, `-a640a39f…`, `-a671d27b…` | none (local only) | Old agent branches (sample lease onboarding, owner console tests, rent roll import fixes) | Fully merged. Safe to delete (`git worktree remove` / `git branch -d`). |
| `fix/rent-roll-hardening` | `~/dev/projects/abstractly-rentroll-qa` | QA/hardening of the rent roll pipeline: import edge cases, negative-rent sign loss, multifamily tenant extraction, route-role checks, **Maple Ridge demo deal + golden-file test** (`backend/benchmark_data/demo_deal/`: 15 real lease PDFs + 16-unit rent-roll CSV + T12, `test_demo_deal_golden.py` asserts exact planted findings through the real routes) | Merged `03cebb5`. Full suite 77/77 (post-fix for the two usage-limits integration gaps the golden test predated: team_id on its faked session, and the per-user extraction rate limit). **This unblocks `feature/team-isolation`'s deferred "Load sample deal" fixture — the real PDFs now exist on `main`.** |
| (docs) | — | `CLAUDE.md` + `TASKS.md` committed to main; `TEAM_AUDIT.md` (external, read-only audit of the tenancy question, lives at `~/dev/projects/TEAM_AUDIT.md` — not part of this repo) | `64af20a`, 2026-10-01. |

## Ready for review (pushed to origin, not merged)

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `feature/team-isolation` | `~/dev/projects/abstractly-teams` | **Real multi-tenant team isolation** — every team-owned table scoped by `team_id` (leases, discrepancies, alerts, comments, tasks, assignments, messaging, lease tags/edits, activity log, linked email accounts); `teams.status` for deactivation (blocks login for every member); owner-console team provisioning (`POST /owner/teams` — creates team + first admin with an unusable password hash + 7-day single-use setup link via `POST /auth/team-setup`, `GET /owner/teams` usage view, deactivate/reactivate); `backend/tests/test_team_isolation.py` (20 cross-team tests). See `PLAN.md` in this worktree for the full design. | **In an overnight autonomous pass (user-authorized, no merge/push-to-main, no browser except headless Playwright) to finish it completely**: rebase onto the now-updated `origin/main` (this unblocks the Maple Ridge sample-deal fixture — see Done table), a full re-audit of every query/route/export/cache-key/background-job/admin-view for team scoping, the owner-console frontend + `team-setup.html` page, the empty-workspace + "Load sample deal" button, adversarial ID-guessing cross-team tests, and headless-Playwright verification. Decisions logged below as they're made; see `OVERNIGHT_REPORT.md` in this worktree when the pass finishes. **Fixed real pre-existing cross-team vulnerabilities found while building this** (not isolation gaps introduced by this branch — all predate it): `POST /team/members` accepted a client-supplied `team_id`, letting any admin create a user directly inside another team; `POST /team/members/<id>/reset-password` and `PATCH /team/members/<id>` didn't check the target user's team at all; task/assignment/thread-participant routes let a caller assign work to or message a user on another team. All now team-scoped and covered by the test file. |
| `feature/deal-assistant` | `~/dev/projects/abstractly-assistant` | **In-app deal assistant** — all 5 planned phases complete. Source page citations (`respond_to_user` takes `{lease_id, field?}`; `assistant._resolve_citations()` fills document name/page from the lease record, never from model text, and **drops any citation whose `lease_id` isn't in this question's own team-scoped grounding data** — that drop is the isolation boundary); per-team assistant credit (`teams.monthly_assistant_credit_usd` + migration, Haiku pricing in `usage_limits_config.py`, `check_assistant_credit`/`log_assistant_usage_event`/`get_assistant_usage_summary` reusing `usage_events` with `event_type='assistant_query'`, credit checked *before* the Claude call and tokens logged after, new `GET /assistant/usage` for the meter); suggested-question chips; rewired the existing floating FAB panel in `frontend/admin/assistant.js` from the old deterministic `/qa` engine to `/assistant/ask`; editable credit field in the owner console Teams modal. `backend/tests/test_deal_assistant_credit_and_citations.py` (19 tests, incl. 4 real cross-team leakage tests through the full `ask_assistant` pipeline *and* the HTTP route). **Also fixed a real pre-existing cross-tenant hole**: `POST`/`GET /teams` and `PATCH /teams/<id>` were `@require_role('admin')` (role-rank only), so any customer team's own admin could create or patch *any* team's quotas — now `@require_owner()`. | **Reviewed 2026-10-02 — `reviewer` verdict: MERGE, no blocking issues.** Pushed to origin @ `ddc8db3`, clean worktree. Full suite 75/79 (only the 4 pre-existing OCR/tesseract failures CLAUDE.md documents as expected). **This branch has `feature/team-isolation` merged into it** (merge commit `81dd96c`, 4 conflicts reconciled — reviewer verified both sides' intent survived in each), so it and team isolation land together; see merge order below. See `OVERNIGHT_REPORT.md` + `PLAN.md` in this worktree. Three open questions the reviewer left to the user, none blocking: (a) the per-lease "Ask About This Lease" panel (`qa-view.js`) is **untouched** and still on `/qa` — replace it too, or leave it? (b) no real-Anthropic end-to-end run yet (mocked only, per CLAUDE.md's ask-first rule) — worth one live smoke question once credits are funded; (c) two team-management route families now coexist (`/owner/teams/*` provisioning vs. `/teams/<id>` quota edits) — correct and tested, but a human API-design pass might consolidate. |
| `feature/pricing-page` (round 2) | `~/dev/projects/abstractly-pricing` | Flat per-team pricing ($499/$399, $1,250/$999, Enterprise), fluted-glass WebGL hero, sticky header, Lenis, new logo | +11 / −6 vs. main, pushed to origin. Clean worktree. Frontend only. Confirm it's finished iterating before merging. |
| `feature/landing-positioning` (round 2) | `~/dev/projects/abstractly-landing` | Scroll-linked fluted-glass shader, dark theme. (Its Book a Demo boolean-`units` fix, `391b49f`, is **already on `main`** as cherry-pick `229ab23` — done, don't re-merge it.) | Pushed to origin. **Worktree has uncommitted changes** to `background-fx.js`, `index.html`, `landing.css`, `pricing.html` — commit or discard before this is reviewable. Overlaps pricing-page round 2 heavily (same files, both add a fluted-glass background); pick one hero, not both. |

### Recommended merge order (one at a time; smoke test the tester deployment after each)

1. **`feature/deal-assistant`** — which **already contains `feature/team-isolation`** (merged in at `81dd96c`), so merging this one lands both at once and is the simplest path: one merge, one smoke test, no reconciling two copies of the same `database.py`/`api.py`-wide isolation change. Both are reviewed (team isolation on its own branch; deal assistant 2026-10-02, verdict MERGE). This is the riskiest merge in the queue — run the full suite before and after, and smoke test the tester deployment. *Alternative if you'd rather land the riskier change alone first:* merge `feature/team-isolation`, smoke test, then `feature/deal-assistant` reduces to a near-clean follow-up merge. Either order works; don't merge team isolation *after* deal assistant.
2. **`feature/pricing-page` (round 2)**: frontend only, no overlap with anything already merged.
3. **`feature/landing-positioning` (round 2)**: resolve its uncommitted changes first; cherry-pick the Book a Demo validation fix, drop the competing shader work (or decide which hero wins).

## In progress

| Branch | Worktree | What it does | Status |
|---|---|---|---|
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | Loan underwriting engine for multifamily lenders + T-12 line-item parsing, feature-flagged **off** | +9 / −2, local only, not pushed. **Uncommitted changes** to `PLAN.md`, `api.py`, `database.py`, `tests/run_all_tests.py` — another session may be active here; don't disturb without checking. Its own `PLAN.md` already decided (mid-build, per the user's instruction) to add **no** team/tenant columns itself and defer entirely to `feature/team-isolation` — nothing to reconcile once that lands; merge this one *after* team isolation per the recommended order above. |

Both `worktree-agent-ade7619750bfa9a9f` (early `accounts`/`account_id` isolation attempt) and the old agent branches are now **fully superseded and safe to delete** — mined for ideas by `feature/team-isolation`, nothing left to recover.

## Blocked

- **Anthropic API account needs credits funded.** Without it, AI extraction and the assistant fall back to the regex engine, and the AI engine can't be QA'd. Only the user can fund it.
- **Tester deployment has no persistent storage.** Free tier, no `disk:`. Tester uploads vanish on every deploy, restart, or 15-min idle spindown. Same for prod. Fix: Starter plan + disk + `DB_PATH` (`docs/DEPLOYMENT.md`). **This is also why "logins survive restarts" can't be fully true yet** — every redeploy wipes the *entire* database (teams, users, leases — not just the admin password), so real customer teams lose everything on every deploy until this is fixed. Needs the user's call on the Starter-plan cost; `feature/team-isolation`'s overnight pass leaves `render.yaml` untouched per its own plan (not this session's call to make).
- **Tester frontend points at the production API (found 2026-10-01).** `frontend/config.js` maps only localhost and `abstractly-demo.onrender.com`. `abstractly-tester.onrender.com` falls through to `abstractly-api`, and the tester site's CSP only allows `abstractly-tester-api`, so the tester app's API calls will fail. No branch fixes this. Needs a small fix branch (with a test) **before inviting testers**.

## Up next

1. ~~Finish `feature/team-isolation`'s overnight pass; review in the morning.~~ **Done** — the pass finished, and `feature/deal-assistant` (which merged team isolation into itself) was reviewed 2026-10-02 with a **MERGE** verdict. Both are now waiting only on the user's go-ahead.
2. Merge the Ready-for-review branches in the order above (only when the user says so).
3. Reconcile `feature/loan-underwriting` onto `main` once team isolation lands.
4. Smoke test the tester deployment: `/health`, login, upload a Maple Ridge lease + rent roll, Deal Mismatch Report, PDF/Excel export, T-12 cross-check.
5. Invite the first 3 testers.

### Branch sweep — 2026-10-01, 19:55 CDT

Full `git fetch --all --prune` + every local/remote branch walked against
`main` @ `03cebb5` (since advanced to `28f2fb9` — see header). At least
two other sessions were committing to this repo concurrently with this
sweep — treat exact SHAs as a snapshot, re-run before relying on them
precisely.

**Cloud-session branches — still not found.** Explicitly searched for
branches covering: multifamily lease fields, rent roll multi-format
parsing, Stripe payments, a pre-launch audit, tester onboarding and
feedback, legal/trust pages, and pre-tester bug fixes. Checked
`git ls-remote --heads origin` (fresh, bypasses local cache), every
local branch name, and the live peer-session list. None of the six
exist anywhere accessible from this machine. If a "pre-launch audit"
branch or `AUDIT.md` exists, it's in a cloud session that was never
pushed here, or under a different name/remote.

**Every branch not yet merged into `main`, with a merge/hold/delete call:**

| Branch | What it does | Recommendation |
|---|---|---|
| `feature/pricing-page` (round 2) | Flat per-team pricing, fluted-glass WebGL hero, sticky header, new logo | **Merge after team isolation.** Clean worktree, pushed, no backend overlap. |
| `feature/landing-positioning` (round 2) | Scroll-linked fluted-glass shader, dark theme | **Merge after team isolation**, but only after resolving its overlap with pricing-page round 2 (both rewrite `landing.css`/`index.html`/`pricing.html` with a competing fluted-glass hero — pick one) and committing or discarding the worktree's uncommitted changes. |
| `feature/loan-underwriting` | Loan underwriting engine + T-12 line-item parsing, feature-flagged off | **Merge after team isolation.** Its own `PLAN.md` already commits to adding no team/tenant columns and deferring entirely to `feature/team-isolation`. Don't touch this worktree meanwhile; another session appears mid-edit in it. |
| `worktree-agent-ade7619750bfa9a9f` | Early multi-tenant isolation attempt: `accounts`/`account_id`, confirmed cross-tenant leak, deletes bearer-token auth | **Delete.** Fully mined for its route-by-route checklist; nothing left to recover. |
| `worktree-agent-a3fcc0f…`, `-a640a39f…`, `-a671d27b…` | Old agent branches, fully contained in `main` | **Delete** (`git branch -d`) — pure cleanup. |
| `feature/deal-mismatch-report` | Already fully merged (`e2c4848`) | **Delete** the branch ref — cleanup only. |
| `feature/team-isolation` | The team isolation effort itself | Overnight pass in progress this session — see Ready for review. |
| `feature/deal-assistant` | Planned in-app portfolio assistant | **Not started.** No recommendation needed until there's content. |

No branch is at "rebuild" — even the stale isolation attempt's design was salvaged as a checklist, not restarted from scratch; it's being retired because a better foundation (`team_id`) already won.

### Housekeeping

- Untracked in the main checkout: `docs/PLAN_t12_crosscheck.md` and `docs/TESTER_VERIFICATION_CHECKLIST.md` (working notes from the now-merged t12/tester-routing branches that never got committed — decide commit vs. discard); `drafts/sales/` (expected `outreach` subagent output, intentionally kept local/uncommitted).
- `PLAN.md` and `SUMMARY.md` at the repo root are **committed on `main`** (landed as part of the `feature/usage-limits` merge, `ab7fb6f`) — these are meant to be per-worktree scratch docs, not permanent root files. Flagged, not touched this session (out of scope for a process-only pass); worth a small cleanup commit later.
- Test-setup note: `backend/tests/sample_lease.pdf` is gitignored. In a fresh worktree, run `python backend/tests/create_sample_lease.py` first, or `test_extraction.py`, `test_synthetic_accuracy.py` and `test_multi_lease_detection.py` fail with "file not found." That isn't real breakage.

## Decisions log

- **2026-10-01 — Team isolation converges on `feature/usage-limits`'s `teams`/`team_id` schema**, not the stale branch's `accounts`/`account_id` one. Reached independently twice the same day: by `~/dev/projects/TEAM_AUDIT.md` (external audit, since found not to actually exist as a repo file — see `feature/team-isolation`'s `PLAN.md` §0) and by `feature/team-isolation`'s own `PLAN.md`. Reasons: already merged and reviewed, proven migration pattern (`_migrate_*` + "Legacy" team backfill), and billing + visibility belong on one entity, not two that can drift apart.
- **2026-10-01 — Merge order executed on local `main`:** `fix/tester-api-routing` → `feature/t12-crosscheck` → `feature/usage-limits` → `fix/rent-roll-hardening`, in that order, resolving the expected test-file conflicts by taking the later branch's versions.
- **(prior) One-firm-per-deployment pattern**: until document-level isolation exists, each tester/customer gets its own Render service + database rather than sharing one deployment. Retired once `feature/team-isolation` merges.
- **2026-10-01, overnight — found and fixed real pre-existing cross-team vulnerabilities** while building team isolation (predate this branch, not introduced by it): `POST /team/members` took a client-supplied `team_id` (could create a user directly inside another team); `PATCH /team/members/<id>` and its `/reset-password` sibling never checked the target user's team; task/assignment/thread-participant routes let a caller point at a user on another team. All fixed, all covered by `test_team_isolation.py`.
