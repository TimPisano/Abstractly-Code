---
name: start-task
description: Claim a task from TASKS.md, create its branch and worktree, write PLAN.md, and stop for the user's approval before touching code. Step 1-3 of The Loop (CLAUDE.md).
---

# start-task

Steps 1–3 of The Loop. Do all three before writing a single line of
application code.

## 1. Claim the task in TASKS.md

- Read `TASKS.md` and `CLAUDE.md` first (every session should have, but
  confirm you're not duplicating something already In progress or
  Ready for review).
- Pick (or confirm with the user) which task you're claiming.
- Edit `TASKS.md`: move the task into **In progress**, with a branch
  name you're about to create and a one-line purpose. If it's a brand
  new task not yet in the file, add the row.

## 2. Create the branch and worktree

- Run `git worktree list` first — never assume no one else is using a
  worktree, and never switch branches inside someone else's worktree.
- Create the branch and its own worktree **under `~/dev/projects/`**,
  named after the topic, e.g.:
  ```
  git worktree add ~/dev/projects/abstractly-<topic> -b <type>/<topic>
  ```
  (`<type>` is `feature/` or `fix/`, matching this repo's existing
  branch names in `TASKS.md`.)
- `cd` into the new worktree for everything that follows.

## 3. Write PLAN.md and stop

- In the new worktree, write `PLAN.md`: what you read first, what you
  found that constrains the approach (existing patterns, the current
  tenancy/team-isolation state from `CLAUDE.md`, any overlap with
  other branches in `TASKS.md`), and the concrete steps you intend to
  take.
- If the task needs team-level data isolation that doesn't exist yet
  on `main`, say so explicitly in the plan and build on
  `feature/team-isolation`'s model rather than inventing a new one
  (CLAUDE.md rule 3).
- **Stop here.** Do not start building. Present the plan and wait for
  the user's explicit approval before step 4 (Build) of The Loop.
