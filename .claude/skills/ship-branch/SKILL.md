---
name: ship-branch
description: Finish a built branch — run tests, headless visual check if UI changed, check the Definition of Done, commit, push the feature branch, run the reviewer subagent, fix what it flags, and mark it Ready for review in TASKS.md. Loop steps 5-9. Never merges.
argument-hint: "[branch — defaults to the current worktree's branch]"
---

# ship-branch

> `$P` = the primary checkout (normally `~/dev/projects/lease-abstraction`, always on `main`). Each Bash call that uses it starts with
> `P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}`.
> Task worktrees live beside it: `${P%/*}/abstractly-<topic>`.

Loop steps 5–9. Run inside the task's worktree, after building.
Never merges and never pushes `main` (that's `/merge-branch`, user-only).

Branch: `$ARGUMENTS` (or `git branch --show-current`).

## 1. Tests green (step 5)

```bash
backend/venv/bin/python backend/tests/run_all_tests.py
```

Fix until green. Only known OCR failures (`test_real_ocr.py`,
`test_ocr_fallback.py` without tesseract/poppler) may remain; list them
by name. Any other failure blocks shipping. New test files must be
registered in `run_all_tests.py`. If you touched `.claude/hooks/`, also
run `python3 .claude/hooks/test_guard.py`.

## 2. Visual check if anything under `frontend/` changed (step 6)

Invoke the `ui-checker` subagent with the worktree path, the changed
pages, and what the change is supposed to look like. It shoots before
(main) and after (this branch) headlessly at 1440/768/375 and five
scroll positions, and must Read every PNG.

You then **Read at least the key "after" screenshots yourself** for the
thing you changed. If the goal isn't visibly met, it isn't fixed; go
back and build. Never claim a visual fix from code reasoning alone.
Record the screenshot directory in the TASKS.md handoff.

## 3. Definition of Done (CLAUDE.md)

Walk the checklist line by line and write the result (✅ / ❌ / n/a +
one phrase of evidence) into your final message. Any ❌ → fix first.

## 4. Commit and push the branch (step 7)

Small commits, clear messages, one concern per branch. Check
`git status` for stray files (`*.db`, `.env`, screenshots, scratch).

```bash
git push -u origin <branch>
```

Pushing a feature branch is fine. Pushing `main` is not (hook-blocked).

## 5. Reviewer (steps 8–9)

Invoke the `reviewer` subagent with the branch name and worktree path.
For anything touching auth, roles, routes, or queries, also run
`/review-branch` (adds `security-auditor`).

- **MERGE** → step 6.
- **FIX FIRST** → fix, re-test, re-push, and re-run the reviewer if a
  fix changed logic (not just a typo).
- **REJECT** → back to building with its reasoning; tell the user.

## 6. Update TASKS.md (primary checkout)

Move the row to **Ready for review** with: worktree, what it does,
`+ahead/−behind` vs main, test result, reviewer verdict, screenshot dir
(if UI), overlap with other branches. Update the handoff block
(`Loop step: 10 — waiting for user to approve merge`). Commit with
`git -C $P commit -m "TASKS: <branch> ready for review" -- TASKS.md`.

Tell the user it's ready and that merging needs `/merge-branch <branch>`
typed in the designated merger session.
