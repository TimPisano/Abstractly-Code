---
name: start-task
description: Start a new task the disciplined way — check for duplicate/prior work on other branches, claim it in TASKS.md, create its own branch + worktree, write a plan, then STOP for the user's approval before touching code. Loop steps 1-3. Use whenever beginning any new piece of work.
argument-hint: "<task description or TASKS.md item> [--type feature|fix|chore]"
---

# start-task

> `$P` = the primary checkout (normally `~/dev/projects/lease-abstraction`, always on `main`). Each Bash call that uses it starts with
> `P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}`.
> Task worktrees live beside it: `${P%/*}/abstractly-<topic>`.

Task: **$ARGUMENTS**

Loop steps 1–3 (CLAUDE.md). Write no application code in this skill.

Current worktrees (other sessions may be using any of these — never touch
a worktree you didn't create, never switch its branch):
!`git worktree list`

## 0. Sanity-check the request

- If the task text contains placeholder-looking text (`(the real …)`,
  `<your …>`, `[insert …]`, `TBD`, `@example.com`) or is ambiguous
  about what "done" means, **ask before going further**. Don't guess.
- If it's a rough one-liner, suggest `/prompt-builder` first.

## 1. Prior-art check (prevents duplicated work and scope creep)

Before designing anything, find out whether it already exists anywhere:

```bash
P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}   # primary checkout
git -C $P fetch -q --all
grep -n -i "<keyword>" $P/TASKS.md
git -C $P log --all --oneline -i --grep="<keyword>" | head -20
git -C $P log --all --oneline -S"<identifier, e.g. CREATE TABLE teams>" | head -20
git -C $P grep -n -i "<identifier>" $(git -C $P for-each-ref --format='%(refname:short)' refs/heads) -- backend frontend | head -40
git -C $P stash list
```

Use 2–4 keywords/identifiers that a previous attempt would have used
(table names, route paths, function names). Record what you found in
the plan's **Prior art** section, including "none found" and the
searches you ran. If another branch already does part of this, the plan
must build on it (or explain why not) — never create a parallel version
(e.g. a second teams/accounts schema). If the task overlaps an
**In progress** row owned by another session, stop and ask the user.

## 2. Claim it in TASKS.md

Edit **`$P/TASKS.md`** (the primary
checkout; this is the only copy that counts — never edit TASKS.md on a
feature branch). Add a row to **In progress** and a handoff block:

```markdown
### <type>/<topic>
- Worktree: ${P%/*}/abstractly-<topic>
- Goal: <one sentence>
- Loop step: 3 — plan written, waiting for user approval
- Last update: <YYYY-MM-DD HH:MM> by start-task
- Next action: user reviews docs/plans/<type>-<topic>.md
```

Commit only that file on main (the hooks allow TASKS.md-only commits):
`git -C $P commit -m "TASKS: claim <type>/<topic>" -- TASKS.md`

## 3. Branch + worktree

```bash
P=$(git rev-parse --path-format=absolute --git-common-dir); P=${P%/.git}   # primary checkout
git -C $P worktree add ${P%/*}/abstractly-<topic> -b <type>/<topic> main
cd ${P%/*}/abstractly-<topic>
ln -s $P/backend/venv backend/venv   # share the venv
python backend/tests/create_sample_lease.py                         # gitignored fixture
```

`<type>` is `feature`, `fix`, or `chore`. From here on, work **only**
in this worktree. The primary checkout stays on `main`.

## 4. Write the plan, then stop

Write `docs/plans/<type>-<topic>.md` in the worktree (committed with the
branch, so the reviewer sees it):

- **Goal** — one paragraph, user-visible outcome.
- **Prior art** — what step 1 found, and the searches run.
- **Approach** — numbered steps.
- **Files to change** / **Files not to touch**.
- **Team isolation & roles** — which routes/queries are touched and how
  each is scoped (rule 3). If it needs document-level isolation that
  `main` lacks, say so and build on `feature/team-isolation`'s `team_id`.
- **Feature flag** — if not tester-ready, the env var (default off).
- **Verification** — the tests to add, and for UI work the pages and
  widths for headless screenshots.
- **Out of scope** — tempting extras you will *not* do.
- **Open questions** — anything the user must decide.

Commit it (`git add docs/plans/... && git commit -m "Plan: <topic>"`).

**STOP.** Show the user the plan path and a 5-line summary. Do not
start building until the user explicitly approves in chat. When they
do, update the TASKS.md handoff (`Loop step: 4 — building`).
