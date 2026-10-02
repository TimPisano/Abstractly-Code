# TASKS — single source of truth

**The copy that counts is `~/dev/projects/lease-abstraction/TASKS.md`
(primary checkout, on `main`).** Never edit TASKS.md on a feature branch.
Commit changes with `git commit -m "TASKS: …" -- TASKS.md` (the hooks
allow TASKS.md-only commits on main). `/status` reconciles this file with
git; `/session-handoff` writes the handoff blocks; `/resume-task` reads them.

Last reconciled with git: **2026-10-01 20:15 CDT** (by `chore/agent-os`).
`+a/−b` = commits ahead/behind local `main` @ `74d3237`.

## ⚠️ Waiting on you

1. **Local `main` is 16 commits ahead of `origin/main` (unpushed).** It
   holds merges of `fix/tester-api-routing`, `feature/t12-crosscheck`,
   `feature/usage-limits`, and `fix/rent-roll-hardening`, plus a
   test-fixture fix (`74d3237`, suite 77/77 per that session). None of it
   is live. Pushing redeploys prod + tester + demo. Say `/merge-branch`
   (or "approve merge") in your merger session when you want it pushed.
2. **Review `chore/agent-os`** (this agent-system rebuild) and merge it
   from your merger session. Its PR-equivalent summary is in the commit.
3. **GateGuard decision** — recommendation in `docs/HOW_TO_RUN_AGENTS.md`
   ("GateGuard"): keep it, but turn off its per-file and routine-Bash
   prompts. Not changed without your OK.
4. **Pick one fluted-glass hero**: `feature/pricing-page` and
   `feature/landing-positioning` both rewrite the same marketing files.

## In progress

| Branch | Worktree | +/− main | State |
|---|---|---|---|
| `chore/agent-os` | `~/dev/projects/abstractly-agent-os` | +3 / 0 | Loop step 10 — pushed, reviewed (FIX FIRST, all fixed), waiting for your merge. Agent system rebuild (CLAUDE.md, TASKS.md, agents, skills, hooks, guide). No app code. |
| `feature/team-isolation` | `~/dev/projects/abstractly-teams` | 0 / −7 | **Active in another session.** ~47 uncommitted files incl. an unresolved merge conflict in `database.py`; no commits yet; not pushed. Extends `usage-limits`' `team_id` to document tables. Don't touch. |
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | +2 / −16 | ~19 uncommitted files (`api.py`, `database.py`, tests, plan); not pushed. Feature-flagged off. Merge **after** team isolation (its plan defers all tenancy to it). Another session may be active — don't touch. |
| `feature/deal-assistant` | `~/dev/projects/abstractly-assistant` | 0 / −7 | Worktree only, nothing built. Not started. |

### Handoff blocks
<!-- One block per In-progress task, written by /start-task and
     /session-handoff, read by /resume-task. Keep them current. -->

### chore/agent-os
- Worktree: ~/dev/projects/abstractly-agent-os
- Goal: make the agent system reliable (rules, skills, hooks, guide); no app code.
- Plan: the user's own session prompt (no separate plan file; user-specified scope).
- Loop step: 10 — waiting for the user's merge decision.
- Last update: 2026-10-01 by the agent-os session.
- Verified: `python3 .claude/hooks/test_guard.py` (59/59 cases pass); reviewer subagent FIX FIRST → all 5 findings fixed with regression tests; headless screenshot tool run against the local marketing site and PNGs opened; self-test of start-task / status / prompt-builder on a fake task.
- Not verified: hooks firing inside a live Claude session (they activate only once this branch is checked out / merged; first session after merge should run one blocked command to confirm).
- Next action: user reviews; merger session runs `/merge-branch chore/agent-os`. On merge, **TASKS.md will conflict** with the primary checkout's uncommitted edits: keep this file's structure, then run `/status` to fold back anything newer.
- Waiting on user: merge approval; GateGuard decision.

## Ready for review (pushed, not merged)

| Branch | Worktree | +/− main | Notes |
|---|---|---|---|
| `feature/pricing-page` (round 2) | `~/dev/projects/abstractly-pricing` | +6 / −18 | Flat per-team pricing, fluted-glass WebGL hero, sticky header, Lenis, new logo; also declares a persistent disk in `render.yaml` (`0a0d7a2`, unverified, would need a paid plan). Clean, pushed. Frontend + render.yaml. No reviewer verdict recorded yet → run `/review-branch`. |
| `feature/landing-positioning` (round 2) | `~/dev/projects/abstractly-landing` | +2 / −24 | Scroll-linked fluted-glass shader, dark theme. **5 uncommitted files** (`background-fx.js`, `index.html`, `landing.css`, `pricing.html`, +1) — commit or discard first. Overlaps pricing-page round 2 (same files, competing hero). Its Book-a-Demo fix is already on main (`229ab23`). |

Recommended order: pricing-page → (decide the hero) landing-positioning →
team-isolation (when built) → loan-underwriting.

## Blocked (needs you)

- **Anthropic API credits** — without them AI extraction/assistant fall
  back to regex and the AI path can't be QA'd.
- **No persistent storage on Render** (free tier). Tester uploads vanish on
  every deploy/restart/15-min spindown. Fix: Starter plan + disk + `DB_PATH`
  (`docs/DEPLOYMENT.md`). Render billing is yours.
- **No document-level team isolation on main** — fine while each firm has
  its own deployment; blocks multiple firms per deployment until
  `feature/team-isolation` lands.

## Up next

1. Push local `main` (your approval) → unblocks testers with routing fix,
   T-12 check, spend limits, rent roll hardening.
2. Merge `chore/agent-os`, then the Ready-for-review branches in order.
3. Smoke test the tester deployment: `/health`, login, Maple Ridge lease +
   rent roll upload, Deal Mismatch Report, PDF/Excel export, T-12.
4. Invite the first 3 testers.
5. Finish `feature/team-isolation`; then rebase `feature/loan-underwriting` on it.

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
| `fix/rent-roll-hardening` | `03cebb5` (+ test fix `74d3237`) | Rent roll edge cases, negative-rent sign loss, multifamily tenant extraction, route roles, Maple Ridge demo deal + golden test. Merged on the user's explicit instruction. An earlier "72/72 passed" claim in this file was false; real post-merge run was 76/77, fixed to 77/77. **Local only, not pushed.** |
| `feature/usage-limits` | `ab7fb6f` | `teams` table + `users.team_id`, per-team limits/quotas, upload dedup (billing scope only). Local only. |
| `feature/t12-crosscheck` | `0ee711c` | T-12 cross-check in the Deal Mismatch Report. Local only. |
| `fix/tester-api-routing` | `b6a46e9` | Tester frontend → tester API (CSP); render.yaml/config.js pairing test. Local only. |
| `feature/deal-mismatch-report` | `e2c4848` | Report with dollar impact, citations, export; analyst role. Pushed. |
| `feature/landing-positioning` r1 | `d6ff92d` | Multifamily landing + Book a Demo. Pushed. |
| `feature/pricing-page` r1 | `a794f0e` | Config-driven pricing page + redesign. Pushed. |
| (docs) | `64af20a`, `d55fef9`, `70ed972` | First CLAUDE.md / TASKS.md / agents / skills. |

## Decisions log

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
