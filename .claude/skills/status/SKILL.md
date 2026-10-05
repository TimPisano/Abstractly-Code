---
name: status
description: Quick read of where everything stands — reconciles TASKS.md with git (branches, worktrees, uncommitted work, unpushed main, merge lock) and summarizes what's done, what's waiting on the user, and what's next.
---

# status

> `$P` = the primary checkout (normally `~/dev/projects/lease-abstraction`, always on `main`). Each Bash call that uses it starts with
> `P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}`.
> Task worktrees live beside it: `${P%/*}/abstractly-<topic>`.

A quick check, not an investigation. Snapshot of git right now:

!`P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}; git -C $P fetch -q --all 2>/dev/null; echo "main: $(git -C $P rev-list --count origin/main..main) unpushed, $(git -C $P rev-list --count main..origin/main) behind origin"; python3 $P/.claude/hooks/guard.py merge-lock status 2>/dev/null; git -C $P worktree list --porcelain | awk '/^worktree/{print $2}' | while read w; do b=$(git -C "$w" branch --show-current); printf '%-34s %-28s ahead %-3s behind %-3s dirty %-3s pushed:%s\n' "$b" "${w/#$HOME/~}" "$(git -C $P rev-list --count main..$b 2>/dev/null)" "$(git -C $P rev-list --count $b..main 2>/dev/null)" "$(git -C "$w" status --porcelain | wc -l | tr -d ' ')" "$(git -C "$w" rev-parse -q --verify @{u} >/dev/null && echo yes || echo no)"; done`

## Steps

1. Read `$P/TASKS.md`.
2. Compare it with the snapshot above. Where they disagree (a branch
   TASKS.md calls open that's merged, a "clean" worktree that's dirty,
   unpushed commits on main nobody mentioned, a worktree with no TASKS
   row), fix TASKS.md to match reality in the primary checkout and
   commit `-- TASKS.md`. Note anything suspicious (e.g. merges on main
   the user may not have approved) instead of fixing it.
3. Reply in three short parts:
   - **Done recently**
   - **Waiting on you** — Blocked items, branches ready for a merge
     decision, plans waiting for approval, anything suspicious.
   - **Next** — the top 1–3 items from Up next.
   Plus one line on capacity: how many tasks are mid-build right now
   (keep to ≤2 at once on Pro; see docs/HOW_TO_RUN_AGENTS.md).

Keep it under ~20 lines; point to TASKS.md for detail.
