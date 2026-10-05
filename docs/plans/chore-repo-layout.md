# Plan: chore/repo-layout — make the repo read like a well-run project

## Goal

Someone opening the repo (an investor, a hire, a beta tester's tech lead)
should understand the project in 30 seconds: a short root, a README that
describes the real product and shows the layout, and a `docs/` folder
grouped by purpose instead of a pile of reports. Nothing about how the app
runs, deploys, or tests changes.

## Prior art

- `5c9bfd3` "Reorganize repo structure for public visibility" (2026-09-15)
  moved internal docs from the root into `docs/`. Since then, 5 new
  reports/plans have piled up at the root again. This task finishes and
  extends that pass; it doesn't redo it.
- TASKS.md → Up next → Housekeeping already lists "root `PLAN.md` /
  `SUMMARY.md` are `feature/usage-limits` leftovers; remove once no open
  branch edits them".
- Searches run: `grep -i "reorg|organi|cleanup|tidy|restructur"` in
  TASKS.md; `git log --all -i --grep` for reorg/organiz/tidy/restructur;
  `git stash list`. No other reorg branch or stash.
- Open branches that edit files this plan moves: `feature/loan-underwriting`
  (PLAN.md, SUMMARY.md, OVERNIGHT_REPORT.md), `docs/tester-pack` and
  `feature/deal-assistant` (OVERNIGHT_REPORT.md), `fix/demo-deal-relative-dates`
  (QA_REPORT.md). All use `git mv`, so git's rename detection carries their
  edits over at merge time; I'll verify with a dry-run merge of each.

## Approach

1. **Root: down to what belongs there.** Final root:
   `README.md`, `CLAUDE.md`, `TASKS.md`, `render.yaml`, `.gitignore`,
   `backend/`, `frontend/`, `docs/`, `drafts/`. (`CLAUDE.md`/`TASKS.md`
   have to stay at the root: the hooks and skills read them there.)
2. **Move root reports/plans into `docs/`** (`git mv`, history preserved):
   | From | To |
   |---|---|
   | `PLAN.md` | `docs/plans/feature-team-isolation-v1.md` |
   | `SUMMARY.md` | `docs/reports/feature-usage-limits-summary.md` |
   | `OVERNIGHT_REPORT.md` | `docs/reports/2026-10-04-demo-rent-roll-polish.md` |
   | `QA_PLAN.md` | `docs/reports/2026-10-01-rent-roll-hardening-qa-plan.md` |
   | `QA_REPORT.md` | `docs/reports/2026-10-04-rent-roll-hardening-qa-report.md` |
   | `docs/PLAN_t12_crosscheck.md` | `docs/plans/feature-t12-crosscheck.md` |
3. **Group `docs/` by purpose:**
   - `docs/` top level = live runbooks: `DEPLOYMENT`, `LOCAL_DEV`,
     `OPERATIONS`, `DECISIONS`, `HOW_TO_RUN_AGENTS`,
     `TESTER_VERIFICATION_CHECKLIST`.
   - `docs/history/` = the logs CLAUDE.md already calls history:
     `PROGRESS`, `WORK_LOG`, `LAUNCH_READINESS_RECAP`, `HARDENING_LOG`,
     `AI_PIPELINE_LOG`.
   - `docs/reports/` gains `BENCHMARK_AND_PRIVACY_AUDIT.md`.
   - `docs/plans/`, `docs/research/` unchanged otherwise.
   - New `docs/README.md`: one-line index of every doc, by folder.
4. **Fix every reference** to a moved path (8 hits found so far:
   CLAUDE.md, `reviewer.md` agent, comments in `api.py`,
   `run_all_tests.py`, `test_demo_deal_golden.py`, and cross-links inside
   the moved docs). Comments only — no code logic touched.
5. **`.gitignore`:** add root `.pytest_cache/` and `__pycache__/`
   (currently only covered under `backend/`).
6. **README:** add a "Repository layout" tree and a "Running tests"
   section (`python backend/tests/run_all_tests.py`); fix the link targets.
   Positioning text: see Open question 1.

## Files to change

Root `*.md` listed above (moved), `docs/**` (moved + new `docs/README.md`),
`README.md`, `CLAUDE.md` (path updates only), `.gitignore`,
`.claude/agents/reviewer.md` (one path), comments in
`backend/app/api.py`, `backend/tests/run_all_tests.py`,
`backend/tests/test_demo_deal_golden.py`.

## Files not to touch

All application code behavior; `render.yaml`; `backend/Dockerfile`,
`start.sh`; `frontend/**`; `backend/tests/` layout; `drafts/`;
`.claude/settings.json` and hooks; `TASKS.md` on this branch.

## Team isolation & roles

n/a — no routes or queries touched.

## Feature flag

n/a — no runtime behavior.

## Verification

- `python backend/tests/run_all_tests.py` before and after; same pass count.
- `git grep` for every old path returns nothing outside `docs/history/`
  (history logs keep their original text on purpose).
- Every relative link in README.md / docs/README.md / CLAUDE.md resolves
  (small script checks each `](path)` exists).
- Dry-run merge of each open branch listed under Prior art into this
  branch (`git merge --no-commit --no-ff`, then abort) — no new conflicts
  beyond what they already have with main.
- No UI change → no screenshots.

## Out of scope

- Moving the ~30 test fixture PDFs/CSVs out of `backend/tests/` into
  `backend/tests/fixtures/` (see Open question 2).
- Moving `backend/set_owner.py` & friends into `backend/scripts/`
  (Open question 2).
- Deleting stale branches/worktrees/stashes (already in Housekeeping,
  each needs its own yes).
- Any refactor of `api.py` (~5,600 lines) — real win, separate task.

## Open questions

1. **README positioning.** It currently says "commercial real estate" and
   ends with "*a portfolio project*". The product is a multifamily SaaS
   with paying-tier pricing. Should I rewrite the intro/features to match
   CLAUDE.md (multifamily syndicators, rent roll validation as the core,
   Deal Mismatch Report), and drop the "portfolio project" line?
2. **Go deeper into `backend/`?** Recommend **no, not now**: test fixtures
   and the 4 admin scripts are referenced by tests, `.env.example`, and
   docs, and ~20 open branches add files to `backend/tests/` — moving them
   now means merge conflicts on most of those branches. Better as a
   follow-up after the current branches land.
3. Is anyone expected to see this repo publicly? If yes, `drafts/` (sales
   outreach) and `TASKS.md` arguably shouldn't be in a public repo at all —
   that's a different decision from tidying.
