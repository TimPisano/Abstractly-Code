---
name: review-branch
description: Run the reviewer and security-auditor subagents in parallel on a named branch and combine their verdicts into one report. Review only — changes nothing.
argument-hint: "<branch>"
---

# review-branch

Branch: **$ARGUMENTS** (if empty, ask, or pick from TASKS.md's Ready for
review table and confirm with the user).

1. Find its worktree: `git worktree list | grep "\[$ARGUMENTS\]"`. If it
   has no worktree, review it from the primary checkout with
   `git diff main...<branch>` — do not check it out there.
2. Launch **both** subagents in one message (parallel):
   - `reviewer` — correctness, isolation/roles, scope vs. plan, secrets,
     tests (it runs the suite), DoD evidence, overlap.
   - `security-auditor` — cross-team data access first, then auth,
     roles, uploads, secrets.
   Give each the branch, the worktree path, and the plan file path.
3. Combine:
   - Either says REJECT → **REJECT**, lead with that reasoning.
   - Either says FIX FIRST, or the auditor reports any critical/high →
     **FIX FIRST**, one deduplicated numbered fix list.
   - Otherwise **MERGE**.
   - Note disagreements or things only one of them caught.
4. Report the combined verdict and fix list. Record the verdict in the
   branch's TASKS.md row (primary checkout, TASKS.md-only commit). Don't
   fix anything unless the user asks.
