# TASKS — single source of truth

**The copy that counts is `~/dev/projects/lease-abstraction/TASKS.md`
(primary checkout, on `main`).** Never edit TASKS.md on a feature branch.
Commit changes with `git commit -m "TASKS: …" -- TASKS.md` (the hooks
allow TASKS.md-only commits on main). `/status` reconciles this file with
git; `/session-handoff` writes the handoff blocks; `/resume-task` reads them.

Last reconciled with git: **2026-10-04** (`chore/agent-os` merged + pushed).
`main` @ `c6c873d` == `origin/main`. `+a/−b` = commits ahead/behind `main`;
the per-branch numbers below predate the agent-os merge. **Every open branch
now also conflicts in `TASKS.md`** (they each edited it before that rule
existed) — resolve those by taking **main's** TASKS.md, not the branch's.

## ⚠️ Waiting on you

1. **Type `/merge-branch <branch>` for each branch you want merged.** The
   guard ties approval to the branch the user names, and the regex only
   matches `/merge-branch …`, `approve merge`, or `merge approved` — prose
   like "merge these one at a time" does **not** arm it (`guard.py:427-440`,
   `APPROVE_RE`). A 2026-10-04 request to merge five branches in one pass
   was therefore not actionable; see #2–#4 for what each one actually needs.
2. **`feature/team-isolation` is NOT reviewer-approved — do not merge.**
   Its tip `b75b947` is the exact commit the 2026-10-02 review ran on:
   reviewer **FIX FIRST**, security-auditor **BLOCK**, with 4 unfixed
   cross-team data-leak findings (listed in its In-progress row). Merging
   it would ship cross-team read/write access.
3. **`feature/pricing-page` r2 would ship the Render billing change you
   asked to hold.** Its tip commit *is* `0a0d7a2` — the persistent disk +
   `plan: free → starter` on `abstractly-api` and `abstractly-tester-api`,
   the same change as `chore/render-persistent-disk`. The TASKS.md note
   claiming that part was "split out" is wrong: it was *copied* out, not
   removed from pricing-page. To merge pricing-page frontend-only, drop or
   revert `0a0d7a2` on the branch first. Also still conflicts in
   `frontend/config.js`, and has no reviewer verdict.
4. **`fix/concession-detection` is ready but was missing from this file.**
   7 commits, +2493/−65 (`concessions.py`, deal-mismatch integration,
   `test_concessions.py`), two reviewer rounds fixed. See its row below.
   Note: "update its tests for `team_id`" is a no-op on current `main` —
   `team_id` exists on `users` only (billing), not on documents, so the
   one `team_id` reference in `test_concessions.py:407` is already correct.
   That instruction only becomes real once team-isolation lands.
5. ~~GateGuard decision~~ — **done**: tuned in `~/.claude/settings.json`
   (routine-Bash and per-file prompts off; destructive-command check kept).
6. **Pick one fluted-glass hero**: `feature/pricing-page` and
   `feature/landing-positioning` both rewrite the same marketing files.
7. **Render plan upgrade** — you asked (2026-10-04) to hold
   `chore/render-persistent-disk` until you confirm the plan is upgraded.
   Held. Nothing on Render was changed. Same hold applies to pricing-page's
   `0a0d7a2` (#3): `plan: starter` on a non-upgraded account risks a
   failed deploy.
8. **`main` is 76/77 on a clean checkout, not 77/77.**
   `test_demo_deal_golden.py`'s `_authed_client()` sets
   `sess["user_id"] = 1` without inserting a `users` row, so
   `usage_limits.log_usage_event()` raises `FOREIGN KEY constraint
   failed`. It only passes where a gitignored `backend/.env` supplies
   `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH`, which makes `init_db()` seed a
   user with id 1 — i.e. on your machine but not in a fresh worktree or
   CI. Pre-existing, unrelated to any open branch's code; same fixture
   bug `REVIEWS/MERGE_PLAN.md` pins on `chore/demo-rent-roll-polish`.
   Needs a one-line fixture fix in its own branch.

## In progress

| Branch | Worktree | +/− main | State |
|---|---|---|---|
| `feature/team-isolation` | `~/dev/projects/abstractly-teams` | +4 / 0 | Pushed (`b75b947`). **Reviewed 2026-10-02: reviewer FIX FIRST, security-auditor BLOCK.** Must fix before merge: (1) undo-field-edit route has no team check — team A can revert team B's lease edits (`api.py:3019-3074`); (2) legacy `/teams` GET/POST/PATCH are admin-only, not owner — any team admin can read/zero other teams' quotas (`api.py:2486-2549`); (3) globally-unique `natural_key` on alerts/discrepancies (`tenant_concentration:`, `t12_recon:`) collides across teams → cross-team overwrite/leak (`database.py:613,3443,3501,3959,4012`); (4) assignments UNIQUE(target_type,target_key) collides for `property` targets (`database.py:735,2536`). Also: sessions don't re-check deactivation/role (12h), `/waitlist` admin routes should be owner-only, move root OVERNIGHT_REPORT.md. Each needs a two-team regression test. |
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | +2 / −16 | ~19 uncommitted files (`api.py`, `database.py`, tests, plan); not pushed. Feature-flagged off. Merge **after** team isolation (its plan defers all tenancy to it). Another session may be active — don't touch. |
| `feature/deal-assistant` | `~/dev/projects/abstractly-assistant` | 0 / −7 | Worktree only, nothing built. Not started. |

### Handoff blocks
<!-- One block per In-progress task, written by /start-task and
     /session-handoff, read by /resume-task. Keep them current. -->

## Ready for review (pushed, not merged)

| Branch | Worktree | +/− main | Notes |
|---|---|---|---|
| `fix/concession-detection` | (no worktree) | +7 | Pushed (`1380198`). Lease concession extraction into a structured schedule (both engines), missing/mismatched/expiring concession detection, effective-rent-aware rent checks; `concessions.py` (967 lines) + `test_concessions.py` (890 lines, AI mocked), Maple Ridge demo docs + golden-test updates. Two reviewer rounds fixed (`7b67ea2`, `1380198` — concession false positives, then guards dropping real concessions). Conflicts with `main` in `TASKS.md` only. Overlaps `fix/demo-deal-relative-dates` and `chore/demo-rent-roll-polish` on the demo deal + `test_demo_deal_golden.py` — merge this one first, then re-run the suite before the other two. |
| `fix/demo-deal-relative-dates` | `~/dev/projects/abstractly-demo-dates` | — | Pushed (`8e1084f`). Makes the Maple Ridge demo deal's dates relative to generation day. Conflicts with `main` in `TASKS.md` only. Touches the same demo-deal generator as the two branches above. |
| `chore/demo-rent-roll-polish` | `~/dev/projects/abstractly-demo-polish` | — | Pushed (`8bc76ca`). Overnight demo rent-roll pass. Conflicts with `main` in `TASKS.md` only. `REVIEWS/MERGE_PLAN.md` pins the `test_demo_deal_golden.py` fixture bug (#8) on this branch. |
| `docs/tester-pack` | `~/dev/projects/abstractly-tester-pack` | +7 / 0 | Overnight run, 2026-10-01: in-app Help & Guides (17 articles incl. Getting Started + troubleshooting), tester emails, 10-Q questionnaire, sales drafts updated (local). Frontend + docs only. Headless-verified at 3 widths. **Read `OVERNIGHT_REPORT.md` on the branch**: 12 product bugs found (report-page T-12 upload broken, T-12 income check never fires, only .csv/.xlsx rent rolls feed the report…). |
| `feature/pricing-page` (round 2) | `~/dev/projects/abstractly-pricing` | +6 / −18 | Flat per-team pricing, fluted-glass WebGL hero, sticky header, Lenis, new logo. Clean, pushed. **Blocked twice over (see #3):** its tip commit `0a0d7a2` is the held Render disk + `plan: starter` billing change, and it conflicts with `main` in `frontend/config.js`. No reviewer verdict → run `/review-branch`. |
| `chore/render-persistent-disk` | `~/dev/projects/abstractly-render-disk` | +1 / 0 | Pushed (`22db0ea`). 1 GB Render disk + `DB_PATH` on `abstractly-api` and `abstractly-tester-api`, both to `plan: starter`; demo stays free by design. Config + docs only, no app code. Extracted from `feature/pricing-page` so that branch can merge frontend-only (billing change shouldn't ride on a CSS refresh). **Needs your Render dashboard actions + billing decision — nothing was changed on Render.** Verified: routing test 4/4; suite 76/77 (see the golden-test note below). Plan: `docs/plans/chore-render-persistent-disk.md`. |
| `feature/landing-positioning` (round 2) | `~/dev/projects/abstractly-landing` | +2 / −24 | Scroll-linked fluted-glass shader, dark theme. **5 uncommitted files** (`background-fx.js`, `index.html`, `landing.css`, `pricing.html`, +1) — commit or discard first. Overlaps pricing-page round 2 (same files, competing hero). Its Book-a-Demo fix is already on main (`229ab23`). |

Recommended order: pricing-page → (decide the hero) landing-positioning →
team-isolation (when built) → loan-underwriting.

## Blocked (needs you)

- **Anthropic API credits** — without them AI extraction/assistant fall
  back to regex and the AI path can't be QA'd.
- **No persistent storage on Render** (free tier). Tester *data* vanishes on
  every deploy/restart/15-min spindown. The `render.yaml` side is now
  prepared on `chore/render-persistent-disk` (disk + `DB_PATH` + `plan:
  starter` on prod and tester); what's left is yours: the billing decision
  and the dashboard steps in `docs/DEPLOYMENT.md` → "Adding persistent
  storage". Render requires a paid instance type for disks, confirmed from
  Render's docs. Note: attaching the disk does **not** migrate the existing
  database, and uploaded *files* are never persisted by design
  (`app/api.py:545` unlinks them; only extracted fields + page numbers are
  stored), so the DB disk covers everything durable.
- **No document-level team isolation on main** — fine while each firm has
  its own deployment; blocks multiple firms per deployment until
  `feature/team-isolation` lands.

## Up next

1. ~~Push local `main`~~ — done (`c6c873d`, agent-os merged).
2. **Merge train, in this order** — each needs you to type
   `/merge-branch <branch>`, and the suite re-run after each:
   `fix/concession-detection` → `fix/demo-deal-relative-dates` →
   `chore/demo-rent-roll-polish` (the last three all touch the demo deal /
   `test_demo_deal_golden.py`, so order matters). Then `docs/tester-pack`.
   `feature/pricing-page` only after `0a0d7a2` is dropped from it (#3);
   `feature/team-isolation` only after its 4 BLOCK findings are fixed (#2);
   `chore/render-persistent-disk` only after you confirm the Render upgrade (#7).
3. Smoke test the tester deployment **beyond `/health`**: login, Maple Ridge
   lease + rent roll upload, Deal Mismatch Report, PDF/Excel export, T-12.
   Only `/health` was checked on 2026-10-04 (all three healthy); the rest
   needs real tester credentials.
4. Invite the first 3 testers.
5. Finish `feature/team-isolation`; then rebase `feature/loan-underwriting` on it.
6. `research/section8` (`2050414`, pushed) — Section 8 / LIHTC market
   research by another session, docs only. Decide whether it's a product
   direction or shelf it.

### Housekeeping (safe, low priority — each needs a yes)

- Delete merged/stale branches: `worktree-agent-a3fcc0f…`, `-a640a39f…`,
  `-a671d27b…`, `feature/deal-mismatch-report` (all 0 ahead of main).
- Delete `worktree-agent-ade7619750bfa9a9f` (+3/−82, stale 2026-09-02,
  competing `accounts` schema with a confirmed cross-tenant leak; already
  mined for team-isolation's route checklist) and its worktree under
  `.claude/worktrees/`.
- Remove merged worktrees: `abstractly-tester-routing`,
  `abstractly-t12crosscheck`, `abstractly-usage`, `abstractly-rentroll-qa`
  (all 0 ahead; `abstractly-usage` has 1 untracked file — check it first).
- 3 stashes (`git stash list`): team-isolation schema start, t12 test WIP,
  agent-ade76 WIP. Check before dropping.
- Root `PLAN.md`/`SUMMARY.md` on main are `feature/usage-limits` leftovers;
  remove once no open branch edits them (new plans live in `docs/plans/`).
- `backend/tests/sample_lease.pdf` is gitignored: new worktrees run
  `python backend/tests/create_sample_lease.py` (start-task does this).

## Done

| Branch | Merged as | Notes |
|---|---|---|
| `chore/agent-os` | `c6c873d` | Agent OS v2: CLAUDE.md + Definition of Done, TASKS.md handoff blocks, reviewer/security-auditor/qa-tester/ui-checker, 8 skills incl. resume-task + prompt-builder, safety hooks, `docs/HOW_TO_RUN_AGENTS.md`. Merged 2026-10-04 by finishing the half-done merge left in the primary checkout (21 staged files already matched the branch tip byte-for-byte; only `TASKS.md` needed resolving — taken as a union of main's rent-roll-hardening facts and the branch's new structure). Suite **77/77 on merged main**, run post-merge. Pushed; prod + tester + demo all returned `{"status":"healthy"}`. Tooling/docs only — no app code, so the redeploy was functionally a no-op. |
| `fix/rent-roll-hardening` | `03cebb5` (+ test fix `74d3237`) | Rent roll edge cases, negative-rent sign loss, multifamily tenant extraction, route roles, Maple Ridge demo deal + golden test. Merged on the user's explicit instruction. An earlier "72/72 passed" claim in this file was false; real post-merge run was 76/77, fixed to 77/77. Pushed. |
| `feature/usage-limits` | `ab7fb6f` | `teams` table + `users.team_id`, per-team limits/quotas, upload dedup (billing scope only). Pushed. |
| `feature/t12-crosscheck` | `0ee711c` | T-12 cross-check in the Deal Mismatch Report. Pushed. |
| `fix/tester-api-routing` | `b6a46e9` | Tester frontend → tester API (CSP); render.yaml/config.js pairing test. Pushed. |
| `feature/deal-mismatch-report` | `e2c4848` | Report with dollar impact, citations, export; analyst role. Pushed. |
| `feature/landing-positioning` r1 | `d6ff92d` | Multifamily landing + Book a Demo. Pushed. |
| `feature/pricing-page` r1 | `a794f0e` | Config-driven pricing page + redesign. Pushed. |
| (docs) | `64af20a`, `d55fef9`, `70ed972` | First CLAUDE.md / TASKS.md / agents / skills. |

## Decisions log

- **2026-10-04 — Merge approval is per-branch and must be typed.** A prose
  request to merge five branches in one pass didn't arm the guard (only
  `/merge-branch <branch>` / `approve merge` / `merge approved` match
  `APPROVE_RE`, and `git merge` is then checked against the named branch).
  Kept as-is rather than loosened: one typed approval per branch is the
  point of the gate, and the batch included a branch under a security BLOCK.
- **2026-10-04 — Another session switched the primary checkout off `main`**
  (to `research/section8`) mid-merge, against rule 3. Harmless this time —
  `main` and the merge commit were intact, and the branch work is safe —
  but a `git log` run inside that window reported the wrong branch's
  history. If the primary checkout's HEAD looks wrong, check
  `git reflog` before concluding `main` was rewound.
- **2026-10-01 — Agent operating system v2** (`chore/agent-os`): hooks now
  enforce no-browser, no-main-changes-without-typed-approval, a single
  merge lock, and a read-only primary checkout. TASKS.md lives only in
  the primary checkout. Plans move to `docs/plans/<branch>.md`.
- **2026-10-01 — Team isolation converges on `usage-limits`' `teams`/`team_id`**,
  not the stale branch's `accounts`/`account_id`. Reached independently by
  `~/dev/projects/TEAM_AUDIT.md` and `feature/team-isolation`'s plan.
  Reason: already merged and reviewed; billing and visibility on one entity.
- **2026-10-01 — Merge order on local main:** tester-api-routing →
  t12-crosscheck → usage-limits → rent-roll-hardening (test conflicts
  resolved by taking t12's versions).
- **(prior) One firm per deployment** until document-level isolation lands.
