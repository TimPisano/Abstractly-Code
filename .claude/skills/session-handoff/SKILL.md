---
name: session-handoff
description: Before a session ends or is cleared, write the current state of its task into TASKS.md so a fresh session can resume cold.
---

# session-handoff

Run this proactively near the end of a session that leaves work
mid-task — don't wait to be asked if context is about to run out or
the user signals they're wrapping up.

## Steps

1. Identify the task(s) this session touched that aren't finished
   (not yet at the end of its Loop step).
2. For each, update its row in `TASKS.md`'s **In progress** (or
   wherever it currently sits) with:
   - The exact Loop step it's at (1–13, per CLAUDE.md's "The Loop").
   - What's been done so far in concrete terms (files changed, tests
     passing/failing, what the plan decided) — not "made progress,"
     specifics a cold session can act on immediately.
   - What's uncommitted, if anything, and where (worktree path).
   - The single next action a fresh session should take first.
3. If a decision got made mid-session that isn't obvious from the code
   (a scope cut, a design choice between two options, a deliberate
   deferral), add it to the **Decisions log** — this is exactly the
   kind of thing that's lost if it only lives in chat history.
4. Don't pad this with anything derivable from git (commit history,
   file contents) — only what a fresh session couldn't reconstruct on
   its own by reading the repo.
