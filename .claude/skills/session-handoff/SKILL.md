---
name: session-handoff
description: Save this session's task state into TASKS.md (and push a WIP commit) so the user can /clear, log out, or close the laptop and a fresh session can resume with /resume-task. Use before /clear, when context is getting long, when the user is wrapping up, or before anything that might kill the session.
argument-hint: "[task/branch — defaults to the current worktree's branch]"
---

# session-handoff

> `$P` = the primary checkout (normally `~/dev/projects/lease-abstraction`, always on `main`). Each Bash call that uses it starts with
> `P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}`.
> Task worktrees live beside it: `${P%/*}/abstractly-<topic>`.

Goal: a brand-new session with zero memory of this chat can run
`/resume-task <branch>` and continue correctly. Write what it can't
reconstruct from the repo; skip what git already records.

## 1. Make the work durable

In the task's worktree:
- If there are uncommitted changes worth keeping:
  `git add -A && git commit -m "WIP: <what state it's in>"` (check
  `git status` first: no `*.db`, `.env`, screenshots, scratch files).
- `git push -u origin <branch>` (feature branch only), so a dead laptop
  doesn't lose it.
- If it's a half-edit you'd rather not commit, say so in the handoff
  and leave it uncommitted — but say exactly which files.

## 2. Write the handoff block

In **`$P/TASKS.md`** (primary checkout,
never the branch copy), replace this task's handoff block:

```markdown
### <branch>
- Worktree: ${P%/*}/abstractly-<topic>
- Goal: <one sentence>
- Plan: docs/plans/<slug>.md (approved by user? yes/no, when)
- Loop step: <1-13 + name, e.g. "6 — visual check">
- Last update: <YYYY-MM-DD HH:MM> by session-handoff
- Done so far: <concrete: files changed, tests added, what works>
- Verified: <test result with counts; screenshot dir + what they show>
- Not working / unknown: <failing tests, unverified claims, suspicions>
- Uncommitted: <files, or "none">
- Decisions this session: <scope cuts, design choices, user answers>
- Next action: <the ONE first thing the next session should do>
- Waiting on user: <question/approval, or "nothing">
```

Be honest in **Verified** vs **Not working**: a fix that wasn't seen in
a screenshot or a test is "unverified", not "done".

Also add durable decisions to the **Decisions log** at the bottom.

## 3. Commit TASKS.md and tell the user

```bash
P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}   # primary checkout
git -C $P commit -m "TASKS: handoff <branch>" -- TASKS.md
```

Then tell the user, in two lines: it's safe to /clear (or quit), and the
exact command for the next session: `/resume-task <branch>`.
