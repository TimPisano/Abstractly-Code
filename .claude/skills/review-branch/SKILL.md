---
name: review-branch
description: Run the reviewer and security-auditor subagents on a named branch and combine their verdicts into one report.
---

# review-branch

Takes a branch name (from the user, or picked from TASKS.md's Ready
for review table). Use this for a deeper look than `ship-branch`'s
built-in review step — e.g. before a merge, or when a branch touches
auth/roles/cross-team data directly.

## Steps

1. Resolve the branch's worktree path (`git worktree list`, or
   `TASKS.md`).
2. Invoke `reviewer` on the branch: correctness, team isolation on
   every route/query, secrets, test quality, conflicts with other open
   branches. Get its MERGE / FIX FIRST / REJECT verdict.
3. Invoke `security-auditor` on the same branch: auth, sessions,
   roles, cross-team data access, file upload safety, secrets. Run it
   even if `reviewer` already said MERGE — they check different things
   and a clean correctness review can still miss an auth gap.
4. Combine both into one report:
   - If either says REJECT, the combined verdict is REJECT — lead with
     that agent's reasoning.
   - If either says FIX FIRST, the combined verdict is FIX FIRST — list
     every required fix from both, deduplicated.
   - Only MERGE if both are MERGE.
   - Note any place the two disagreed or one found something the other
     missed — that's a signal the next review pass should double-check it.
5. Report the combined verdict with the full fix list. Do not act on
   the findings yourself unless asked — this skill only reviews.
