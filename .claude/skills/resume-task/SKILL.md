---
name: resume-task
description: Pick up a task in a fresh session (after /clear, logout, crash, or sleep) from its TASKS.md handoff block — re-enters its worktree, verifies the notes against git, summarizes, and continues from the recorded next action.
argument-hint: "<branch or task name>"
---

# resume-task

> `$P` = the primary checkout (normally `~/dev/projects/lease-abstraction`, always on `main`). Each Bash call that uses it starts with
> `P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}`.
> Task worktrees live beside it: `${P%/*}/abstractly-<topic>`.

Resume: **$ARGUMENTS**

## 1. Find it

Read `$P/TASKS.md` (and CLAUDE.md if not
already loaded). Find the handoff block / row matching `$ARGUMENTS`
(branch name or a word from its goal). If there's no match or more than
one, list candidates and ask. If `$ARGUMENTS` is empty, list the
In progress handoff blocks and ask which.

## 2. Re-enter and verify

```bash
cd <worktree from the handoff>
git branch --show-current       # must equal the handoff's branch
git status --short
git log --oneline -8
git log --oneline main..HEAD | wc -l
```

- Worktree missing? If the branch exists, recreate it:
  `git -C $P worktree add <path> <branch>`
  and re-link the venv (`ln -s $P/backend/venv backend/venv`).
  Never check the branch out in the primary checkout.
- Read the plan file and the last few commits' diffs.
- Compare reality with the handoff (uncommitted files, last commit,
  Loop step). If they disagree, trust git and say what differs — another
  session may have worked on it since. If another session looks
  **active** on it right now (very recent commits/edits not described
  in the handoff), stop and ask before touching anything.

## 3. Summarize, then continue

Tell the user in ≤6 lines: goal, Loop step, what's verified, what's
not, the next action you're about to take.

- If the next action needs the user (plan approval at step 3, merge at
  step 10, an open question, placeholder values), ask and stop.
- Otherwise continue from **Next action**, following The Loop.

Update the handoff's `Last update` line (`resumed by new session`) and
commit `-- TASKS.md` in the primary checkout.
