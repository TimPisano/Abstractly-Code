---
name: status
description: Read TASKS.md and git, and give a short summary of what's done, what's waiting on the user, and what to do next.
---

# status

A quick read, not an investigation — don't re-derive what `TASKS.md`
already records, just verify it's still accurate and summarize.

## Steps

1. Read `TASKS.md`.
2. Spot-check it against git: `git status`, `git branch -a`,
   `git worktree list`, `git log origin/main..main --oneline` (is
   local `main` ahead of `origin` the way `TASKS.md` says?). If
   something's drifted (a branch merged/pushed that `TASKS.md` still
   shows as open, an uncommitted change in a worktree it calls clean),
   fix `TASKS.md` to match reality before reporting — don't repeat a
   stale status.
3. Summarize in three short parts:
   - **Done recently** — what landed since the last time this was
     checked.
   - **Waiting on you** — anything in Blocked, or a Ready-for-review
     branch that needs a merge decision, or an In-progress branch with
     uncommitted changes that look like someone needs to weigh in.
   - **Next** — the top 1–3 items from Up next, in the order TASKS.md
     recommends.

Keep it short. This is a status check, not a full report — point to
`TASKS.md` for the detail rather than repeating every row.
