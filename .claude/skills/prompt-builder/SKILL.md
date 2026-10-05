---
name: prompt-builder
description: Turn the user's rough request into a well-structured task prompt (goal, context, constraints, likely files, what not to touch, verification, definition of done), flag ambiguities and placeholder text, save it, and show it for approval. Never runs the task itself. Use when the user gives a rough idea, says "build a prompt", or before starting a vague task.
argument-hint: "<rough request>"
---

# prompt-builder

> `$P` = the primary checkout (normally `~/dev/projects/lease-abstraction`, always on `main`). Each Bash call that uses it starts with
> `P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}`.
> Task worktrees live beside it: `${P%/*}/abstractly-<topic>`.

Rough request: **$ARGUMENTS**

You produce a prompt. You do **not** execute it, create branches, or
edit code. The user approves (or edits) it first.

## 1. Gather just enough context (read-only, quick)

- CLAUDE.md and TASKS.md: is this already done, in progress, blocked,
  or overlapping another branch? Name the branch if so.
- Locate likely files: `git grep -n -i "<keyword>" -- backend frontend | head -30`
  and the route/table names involved.
- Prior art on other branches:
  `git log --all --oneline -i --grep="<keyword>" | head` and
  `git log --all --oneline -S"<identifier>" | head`.

Spend a few minutes, not an investigation. Uncertain → it's a question.

## 2. Flag problems before writing

List, at the top of your reply:
- **Placeholders** — any text like `(the real email)`, `<your key>`,
  `[insert …]`, `TBD`, `XXX`, `{{…}}`, `@example.com`, "the usual". Quote
  each; ask for the real value. Never fill one in with a guess.
- **Ambiguities** — anything with two reasonable readings; give the
  readings and recommend one.
- **Risks** — touches auth/roles/team data, money math, prod data,
  pushing main, real-API cost, or another session's branch.
- **Size** — if it's more than one branch's worth of work, propose a split.

## 3. Write the prompt

Use exactly this structure:

```markdown
/start-task <type>/<topic>: <one-line goal>

## Goal
<What should be true for the user when this is done. 2-4 sentences.>

## Context
<Why now; current behavior; related branches/TASKS.md items; prior art found.>

## Constraints
- Follow The Loop in CLAUDE.md; stop after the plan for my approval.
- <rule-3 team scoping / roles if routes or queries are touched>
- <feature flag default off, if not tester-ready>
- <data: Maple Ridge / synthetic fixtures only; mock Anthropic>

## Files likely involved
- <path> — <why>

## Do not touch
- <files/areas/branches out of scope, incl. other sessions' worktrees>

## Verification
- <specific tests to add/run, with expected result>
- <for UI: pages + widths for headless screenshots, what must be visible>

## Definition of done
- <task-specific acceptance checks>
- Plus CLAUDE.md's Definition of Done checklist.

## Open questions (answer before starting)
- <only if any remain>
```

## 4. Save and show

Save to `$P/drafts/prompts/<YYYY-MM-DD>-<topic>.md`
(gitignored, local only). Show the full prompt in chat plus the flags
from step 2, and ask: **"Approve, edit, or answer the open questions?"**
Stop. Don't run it — the user pastes it into a session (usually a fresh
one) when ready.
