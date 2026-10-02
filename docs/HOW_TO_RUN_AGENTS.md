# How to run your agents (one page)

The short version: **one task per session, one session per worktree,
at most two building at once, one merger.** Type the skills below;
don't write long recap prompts.

## Your sessions

| Session | Where it runs | What you type in it |
|---|---|---|
| **Builder A** | the task's worktree (`~/dev/projects/abstractly-<topic>`) | `/start-task …` or `/resume-task …`, then approve the plan |
| **Builder B** (optional) | a *different* task's worktree | same |
| **Merger** (one, long-lived) | the primary checkout `~/dev/projects/lease-abstraction` | `/status`, `/review-branch x`, `/merge-branch x` |

Only the merger session ever gets `/merge-branch`. Typing it there is
your approval. The hooks enforce it: nobody else can commit to, merge
into, or push `main`, and only one session can hold the merge lock.

## How many at once (Pro limits)

- **Two builder sessions max.** Every session, and every subagent it
  launches, draws from the same 5-hour usage window. Three parallel
  builders plus their reviewers is what's been running you out.
- Subagents aren't free. A `/review-branch` is two extra agents. Run
  reviews when a branch is actually done, not after every edit.
- Use **Sonnet for building** (model picker). Save Opus for hard design
  or debugging. The reviewer, security-auditor, ui-checker and qa-tester
  agents are pinned to Sonnet. Your global setting runs every other
  subagent on Haiku.
- The ECC plugin adds a few hundred skill descriptions and ~20 hooks to
  every session. That's a constant tax on context and speed. Consider
  turning ECC off for this project (`"enabledPlugins": {"ecc@ecc": false}`
  in `.claude/settings.local.json`) and keeping only what you use.
- When you hit ~80% of your window, `/session-handoff` everything and stop.

## Which skill when

| You want to… | Type |
|---|---|
| Turn a rough idea into a solid prompt | `/prompt-builder <idea>` |
| Start new work | `/start-task <task>` (stops for your plan approval) |
| Finish a branch: tests, screenshots, push, review | `/ship-branch` |
| A second opinion with a security focus | `/review-branch <branch>` |
| Merge (merger session only) | `/merge-branch <branch>` |
| See where everything stands | `/status` |
| Stop for now / before `/clear` / before closing the laptop | `/session-handoff` |
| Continue in a fresh session | `/resume-task <branch>` |

## Handing off between sessions

1. In the old session: `/session-handoff`. It commits and pushes WIP and
   writes a handoff block in TASKS.md (Loop step, what's verified, next action).
2. `/clear` (or quit, or log out).
3. New session: `/resume-task <branch>`. That's the whole recap prompt.

A hook also reminds every new or cleared session to read TASKS.md, so
nothing depends on chat history.

## Keeping the Mac awake

A hook starts `caffeinate` for the life of each Claude session, which
stops *idle* sleep. **Closing the lid still sleeps the Mac** unless it's
on power with an external display. For long runs, leave the lid open
and plugged in, and turn on *Keep awake* in the Claude desktop app's
Code settings. If it does sleep, nothing is lost past the last
`/session-handoff`.

## The safety hooks (`.claude/settings.json` → `.claude/hooks/guard.py`)

| Hook | Stops | Why |
|---|---|---|
| Main guard | merge/commit/reset/push on `main` without your typed `/merge-branch`; a second session merging at the same time; subagents touching main | agents merged into main without approval; two merged at once |
| Primary checkout guard | edits to anything but TASKS.md/`drafts/` in `lease-abstraction/`, and branch switching there | agents worked in the shared folder and switched branches under each other |
| Browser guard | `open <url>`, headed Playwright, Chrome MCP tools (also denied in permissions) | agents opened your browser; an automated Chrome hijacked a login page |
| Read-only agents | reviewer/security-auditor/ui-checker writing in the repo | reviewers should report, not "fix" |
| Prompt check | flags placeholder text like `(the real email)` so the agent asks you | placeholders were used literally |
| Session start | reminds the agent of TASKS.md and `/resume-task`, warns if it's in the primary checkout, keeps the Mac awake | context lost after `/clear` |

Each check takes about 0.2s. Test them with `python3 .claude/hooks/test_guard.py`.
If one blocks something you really want, do that step yourself in a terminal.

## GateGuard (ECC's "Fact-Forcing Gate"): recommendation

It makes agents restate facts **before the first Bash command, and before
the first edit to *every* file**, with its state resetting after 30
idle minutes. The session that built this system hit it 18+ times while
writing ~20 files. Its useful part is the **destructive-command check**
(`rm -rf`, `git reset --hard`, force-push), which our hooks don't duplicate.

**Recommend: tune, don't remove.** Turn off the low-value gates and keep
the destructive one by adding this to `~/.claude/settings.json` → `"env"`:

```json
"GATEGUARD_BASH_ROUTINE_DISABLED": "1",
"GATEGUARD_EXEMPT_GLOBS": "/Users/timmypisano24/dev/projects/**"
```

Not applied. Say the word and an agent will add it.

## Writing better prompts

1. **Say what "done" looks like**, something you could check yourself.
2. **Name what not to touch.** Agents expand scope to fill silence.
3. **Point at prior work.** "Build on X branch" prevents duplicates.
4. **Ask for evidence**, not assurances: test output, screenshots.
5. **No placeholders.** If you don't have a value yet, write "ASK ME
   for the email". Or run `/prompt-builder`, which flags them.

**Example 1: the shader background (took 4 attempts).** Reconstructed
from the commits on `feature/pricing-page`, not your exact words.

> *Before:* "The hero background is cut off, fix it."

> *After:* "On `feature/pricing-page`, the fluted-glass WebGL hero stops
> partway down at 1440px (the section below shows a hard edge). Goal:
> the glow fills the whole hero at 1440/768/375 at the top and while
> scrolling. Don't change copy, header, or pricing. Verify with
> headless before/after screenshots (`ui-checker`) and show me the
> 1440px top and 50%-scroll shots. Not done until I can see it in them."

**Example 2: the teams table (duplicated work).**

> *Before:* "Add team accounts so firms can't see each other's leases."

> *After:* "`/start-task feature/team-isolation`: scope `leases`,
> `discrepancies`, `alerts`, and `tasks` by team. `main` already has a
> `teams` table and `users.team_id` from `feature/usage-limits`. Build on
> that; don't create an `accounts` table. The stale
> `worktree-agent-ade76…` branch has a route checklist and a known leak
> in `get_field_source_chain()`. Use it as a checklist only. Plan first,
> including every route you'll scope. `security-auditor` must show team
> A gets a 404 on team B's lease."
