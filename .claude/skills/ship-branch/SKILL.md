---
name: ship-branch
description: Run tests (and ui-checker if UI changed), commit, push the branch, invoke the reviewer subagent, and move the task to Ready for review in TASKS.md. Steps 5-9 of The Loop (CLAUDE.md).
---

# ship-branch

Steps 5–9 of The Loop, run after building (step 4) is actually done.

## 1. Tests green

```
python backend/tests/run_all_tests.py
```

Fix failures until green. Known pre-existing OCR failures
(`test_real_ocr.py`, `test_ocr_fallback.py` without `tesseract`/
`poppler` installed) are not new breakage — don't chase those, but
treat every other failure as real. Register any new test file in
`run_all_tests.py` (plain-script convention, not auto-discovered).

## 2. Visual check, only if UI changed

If the diff touches anything under `frontend/`, invoke the
`ui-checker` subagent against the running local app — headless
Playwright only, never the user's real browser (CLAUDE.md rule 1).
Fix anything it flags before moving on.

## 3. Commit and push

- Small, focused commits, one concern per branch (CLAUDE.md
  conventions). Write a clear message.
- Push the branch to `origin` — this is pushing a *feature branch*,
  not `main`, so it doesn't need the explicit merge-approval the Loop
  requires later; it's still worth a quick confirmation if you're
  unsure the user wants it pushed yet.

## 4. Hand off to the reviewer

Invoke the `reviewer` subagent with this branch name. Give it the
worktree path so it can run `git diff main...<branch>` itself.

## 5. Fix what it flags

- **MERGE**: nothing to do, proceed to step 6.
- **FIX FIRST**: make the listed fixes, re-run tests, and re-invoke
  `reviewer` if any fix was non-trivial (touched logic, not just a typo).
- **REJECT**: this needs rework, not a patch — go back to step 4 of
  The Loop (Build) with the reviewer's reasoning in hand; don't try to
  patch around a rejected design.

## 6. Update TASKS.md

Move the branch from **In progress** to **Ready for review**, with its
worktree path, what it does, commit count ahead/behind `main`, and the
reviewer's verdict. Note any overlap with other open branches the
reviewer flagged.
