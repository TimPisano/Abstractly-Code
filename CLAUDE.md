# Abstractly
Lease abstraction and rent roll validation for CRE firms. Live at getabstractly.com. Section 8 work is parked behind `SECTION8_MODE`.

## Commands
- Setup: `cd backend && python3.11 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Run API: `cd backend && source venv/bin/activate && python run.py` (:5000)
- Run site: `cd frontend && python3 -m http.server 8080`
- Test all: `source backend/venv/bin/activate && python backend/tests/run_all_tests.py` (`--live` hits real APIs: ask first)
- Test one: `python backend/tests/test_<name>.py` (plain scripts; register new files in `run_all_tests.py`)
- Build: none. Frontend is static; Render builds `backend/Dockerfile` on deploy.
- Tests need test env values: the real `backend/.env` (`ADMIN_EMAIL`) breaks 7 files. Unset `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` or run where `.env` is absent; never edit `.env`.
- Fresh worktree: run `python backend/tests/create_sample_lease.py` first (`sample_lease.pdf` is gitignored; 3 tests need it).
- OCR: tesseract is in `/opt/homebrew/bin`. If OCR tests fail, check PATH and `pytesseract` in the venv.

## Deploy
- Push to main = prod + tester + demo redeploy on Render (`render.yaml`, no `branch:`).
- Only prod API has a persistent disk; tester and demo data wipe on every deploy/restart.
- Secrets only in the Render dashboard (`sync: false`). Never commit `.env` or `*.db`.

## Git
- One task = one branch = one worktree under `~/dev/projects/`. Primary checkout stays on main; read-only except `TASKS.md` and `drafts/`.
- Branch off main: `feature/<topic>` or `fix/<topic>` (`chore/`, `docs/`, `qa/` also used). Small, one concern.
- No GitHub PRs (`gh` not installed). Push the feature branch; review with `/review-branch`.
- Merges need the user to type `/merge-branch <branch>` (guard hook). One merger at a time, use the merge lock.
- User pushes main with `! git push origin main`.
- Sync: `git pull --rebase=merges`.
- Never force-push, rewrite main, or delete unmerged branches.

## Product
- New features behind an env flag, default off.
- Section 8: code on main stays; `SECTION8_MODE` off in every environment. Don't merge S8 branches (`feature/s8-*`, `fix/section8-*`, `pivot/section8`, `research/section8`); leave them pushed.
- Don't touch pricing, legal pages, demo button, existing routes, signup.
- In Section 8 code: never invent HUD/PHA rules; cite the HUD source and label "Verify with your PHA".
- No PII in logs or fixtures. Use Maple Ridge (`backend/benchmark_data/demo_deal/`) and `backend/tests/` fixtures.
- Every route gets `@require_role(...)`; every document query is scoped to the authenticated caller's `team_id`. Never add an `accounts`/`account_id` schema.
- Mock the Anthropic API in tests.
- Every bug fix gets a regression test that fails before the fix.

## Workflow
- Read `TASKS.md` (primary checkout) first: task board + handoff notes.
- Non-trivial work: `/start-task` (plan in `docs/plans/<branch>.md`), wait for approval.
- Done = full test suite passes, count quoted. UI changes also need headless screenshots (`node .claude/tools/screenshots.mjs`); never open a visible browser.
- Parallel sessions: claim tasks and log handoffs in `TASKS.md`.
- Ambiguous: pick the conservative option, note the question, keep going.
- Before /clear or a break: `/session-handoff`; resume with `/resume-task <branch>`.
- After changes: explain the diff in plain English in 3 to 5 lines (I'm learning to read code).

## Lessons
(empty)
