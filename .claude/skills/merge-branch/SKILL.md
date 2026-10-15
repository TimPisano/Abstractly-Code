---
name: merge-branch
description: Merge one reviewed branch into main, run tests, update TASKS.md, remove the worktree, then stop and remind the user to push main themselves; smoke test after they push. User-only — the user types /merge-branch <branch> in the designated merger session; that typed command is the approval.
argument-hint: "<branch>"
disable-model-invocation: true
---

# merge-branch

> `$P` = the primary checkout (normally `~/dev/projects/lease-abstraction`, always on `main`). Each Bash call that uses it starts with
> `P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}`.
> Task worktrees live beside it: `${P%/*}/abstractly-<topic>`.

Branch to merge: **$ARGUMENTS**

The user typing `/merge-branch <branch>` in this session is the approval
(CLAUDE.md → Git). The project hooks recorded it for this session only,
for 2 hours, and they enforce a **single repo-wide merge lock**: if
another session is merging, every main-changing command here is blocked.
Don't work around a block — report it and wait.

If `$ARGUMENTS` is empty or ambiguous, ask which branch. Merge only that
branch. Approval for one branch never covers another.

All commands run in the **primary checkout**
`$P` (the only place `main` lives).

## 1. Preconditions — stop and report if any fails

```bash
P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}   # primary checkout
python3 $P/.claude/hooks/guard.py merge-lock status   # must be free or this session
git -C $P status --short                               # must be clean except TASKS.md / drafts/
git -C $P fetch -q origin
git -C $P log --oneline origin/main..main              # unpushed local commits on main?
git -C $P log --oneline main..origin/main              # remote ahead?
```

- If local `main` has unpushed commits that **aren't** TASKS.md
  bookkeeping or this merge, list them and ask the user whether they
  approved them — pushing would ship them too.
- TASKS.md must show the branch in **Ready for review** with a MERGE
  verdict. If not, ask whether to run `/review-branch` first.
- `git -C $P pull --ff-only` if remote is ahead.

## 2. Merge

```bash
P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}   # primary checkout
git -C $P merge --no-ff <branch> -m "Merge <branch> into main"
```

Any conflict outside what TASKS.md predicted → `git -C $P merge --abort`,
release the lock (step 6), and report. Don't resolve unplanned
conflicts by guessing.

## 3. Full test suite on merged main

```bash
P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}   # primary checkout
cd $P && backend/venv/bin/python backend/tests/run_all_tests.py
```

Any non-OCR failure → report it and stop; tell the user not to push.
Ask whether to revert the merge (`git -C $P reset --hard ORIG_HEAD`,
needs the user's yes).

## 4. Clean up and release (never push main)

The user pushes `main` themselves (CLAUDE.md → Git). This skill never
runs `git push origin main`.

- TASKS.md (primary): move the row to **Done** with the merge SHA,
  marked "merged locally, awaiting user push"; delete its handoff block;
  add a Decisions log line for any non-mechanical choice. Commit
  `-- TASKS.md` on main.
- `git -C $P worktree remove ${P%/*}/abstractly-<topic>` (only if
  clean — if dirty, ask) and `git -C $P branch -d <branch>`.
- **Always** release the lock, including after a failure:
  `python3 $P/.claude/hooks/guard.py merge-lock release ${CLAUDE_SESSION_ID}`

## 5. Stop and remind the user to push

Show `git -C $P log --oneline origin/main..main` (everything a push
would ship), then end with: "Pushing main redeploys prod, tester, and
demo on Render. When ready, run: `! git push origin main`". Stop here.

## 6. Smoke test (only after the user says they pushed; headless only)

After Render redeploys (poll `curl -s https://abstractly-tester-api.onrender.com/health`
every ~30s, up to 10 min), check the tester deployment with `curl` and
`node .claude/tools/screenshots.mjs https://abstractly-tester.onrender.com/`
(Read the PNGs). Cover: `/health`, login, Maple Ridge lease + rent roll
upload, Deal Mismatch Report, PDF/Excel export, T-12 cross-check — as
far as possible without real credentials; say which steps need the user.
Record the result in TASKS.md (TASKS.md-only commit; don't push).
