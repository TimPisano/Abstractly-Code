---
name: merge-branch
description: Merge a branch into main and push main — only when the user explicitly says to merge in this session. Pulls main, merges, runs the full test suite, pushes, smoke tests, updates TASKS.md, removes the worktree. Steps 10-13 of The Loop (CLAUDE.md).
---

# merge-branch

Steps 10–13 of The Loop. **Never run this skill speculatively.**
CLAUDE.md rule 2 is absolute: never merge into `main` or push `main`
unless the user explicitly says so *in that session*. If you weren't
just told to merge this specific branch, stop and ask — don't infer
approval from an earlier "looks good" on the diff.

## 1. Confirm approval, then prep

- Confirm the branch name and that the user approved merging it now.
- `git status` on the main checkout — stash or commit anything already
  there before switching/pulling (never discard uncommitted work).
- `git pull` to get local `main` current with `origin` first, so you're
  not merging onto a stale base.

## 2. Merge

- Check `TASKS.md`'s recommended merge order and any noted file
  overlaps with other open branches before merging — merge in that
  order, and expect the specific conflicts already flagged there.
- `git merge <branch>` (no `--squash` unless the user asked for one;
  this repo's convention is small real commits, not squashed history).
- Resolve conflicts per `TASKS.md`'s guidance (e.g. "take t12's
  version" style notes). If a conflict shows up that TASKS.md didn't
  anticipate, stop and flag it rather than guessing.

## 3. Full test suite

```
python backend/tests/run_all_tests.py
python backend/tests/run_all_tests.py --live   # needs run.py up locally
```

Every failure here blocks the push — this is the last gate before
`main` moves. Known pre-existing OCR failures are the only exception
(CLAUDE.md rule 9).

## 4. Push main

Only now, with tests green and the user's approval already confirmed
in step 1: `git push origin main`. Remember `render.yaml` auto-deploys
prod, tester, and demo from this one push — say so out loud before
pushing if it isn't already obvious to the user in this session.

## 5. Smoke test

Hit the tester deployment (or whichever this push affects):
`/health`, login, upload a sample lease + rent roll, Deal Mismatch
Report, PDF/Excel export, T-12 cross-check. Use headless Playwright or
`curl`/API calls — never the user's browser (CLAUDE.md rule 1).

## 6. Update TASKS.md and clean up

- Move the branch to **Done**, with its merge commit SHA.
- Remove the merged branch's entry from any "Ready for review" /
  "In progress" table it was in.
- `git worktree remove <path>` for its worktree, then
  `git branch -d <branch>` once you've confirmed nothing else needs it.
- Log anything non-obvious in the Decisions log (e.g. a conflict
  resolution choice that wasn't purely mechanical).
