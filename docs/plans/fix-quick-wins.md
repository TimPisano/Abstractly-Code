# Plan: fix/quick-wins

## Goal

1. Lease detail cards no longer get cut off on the right at a 375px phone width, and no other
   page has the same problem.
2. Every backend dependency with a known security advisory is upgraded to a fixed version, and
   the full test suite still passes.

## Prior art

Searched TASKS.md (`375`, `pillow`, `advisor`, `dependenc`, `pip-audit`, `cut off`),
`git branch -a`, and `git log --all --grep`. **No branch or task covers either item.**

- The read-only audit (`~/dev/projects/abstractly-audit/AUDIT.md` §2.4, uncommitted) lists the
  same advisories. It is the source of the version targets below, re-checked today.
- `frontend/app/styles.css` ~2850–2885 already has several 375px fixes (`.main-content
  width:100%`, one-column `.results-grid` and `.today-briefing-grid`). The detail-card fix goes
  in the same media block, in the same style.
- Yesterday's auth work found that on phones the dashboard has inner panels (lease filter row,
  recent activity) that scroll sideways inside their cards. Same family of bug; in scope for
  item 1's sweep.

## 1. 375px cut-off

1. Reproduce headless (Chromium + WebKit iPhone, 375 wide). Sign in locally, load the Maple
   Ridge sample deal, open a lease's detail view, and measure which elements are wider than
   the viewport or than their card (`scrollWidth > clientWidth`).
2. Fix the cause in `styles.css`'s phone media block: wrapping, `min-width: 0`, one-column
   grids, `overflow-wrap: anywhere` for long values. No horizontal-scroll band-aid on the page.
3. **Sweep every page at 375:** marketing (`index`, `pricing`, `404`), every app view
   registered in `app.js` (dashboard, upload, action items, tasks, alerts, discrepancies, deal
   mismatch, team notes, detail, timeline, rent roll, compare, QA, report, trends, team), the
   auth pages, and the admin and owner consoles. Use an automated check that flags any element
   sticking out past the viewport or its own card, plus screenshots I open and look at. Fix
   what it finds the same way.
4. Regression guard: the overflow sweep is committed as a re-runnable headless script, plus
   screenshots at 375 (and 390/768/1440 so nothing regresses on larger screens).

## 2. Dependency advisories

`uvx pip-audit -r backend/requirements.txt` today: **32 advisories in 8 packages.**

| Package | Now | → | Advisories |
|---|---|---|---|
| Pillow | 11.3.0 | **12.3.0** | 18 (out-of-bounds writes, heap overflows; reachable through image uploads) |
| pypdf | 6.16.2 | **6.19.0** | 8 |
| pdfminer.six (via pdfplumber) | 20251107 | 20260107 by bumping **pdfplumber 0.11.8 → 0.11.10** (0.11.8 pins the old one exactly) | 1 |
| pillow-heif | 1.1.1 | **1.3.0** | 1 |
| Flask | 3.0.0 | **3.1.3** | 1 |
| Werkzeug | 3.1.8 | **3.1.9** | 1 |
| requests | 2.32.5 | **2.33.0** | 1 |
| python-dotenv | 1.2.1 | **1.2.2** | 1 |

I'll take the lowest fixed version (smallest change), then re-run pip-audit and expect zero.

**Python version catch:** Pillow 12 needs Python ≥ 3.10. Production runs 3.11
(`backend/Dockerfile`: `python:3.11-slim`), but the **shared local venv every worktree uses is
3.9**. So:
- This branch gets its **own Python 3.11 venv** (via `uv`), which also matches production
  better. The shared venv is not touched, since other sessions are using it.
- The full suite runs in that 3.11 venv, against exactly the upgraded `requirements.txt`.
- I'll also build the production Docker image locally if Docker is available. If it isn't,
  I'll say so, since that's the real install test.

## Files

- `frontend/app/styles.css`, and other CSS only where the sweep finds problems
  (`landing.css`, `admin/admin.css`, `owner/owner.css`, `app/auth.css`)
- `backend/requirements.txt`
- Code only if an upgrade breaks something (e.g. a Flask 3.1 behavior change), each with a
  test
- New `.claude/tools/overflow-sweep.mjs`
- `docs/plans/fix-quick-wins.md`

Not touched: `render.yaml`, the shared venv, any feature behavior.

## Team isolation & roles

No routes or queries change. If an upgrade forces a code change in a route, it keeps its
`@require_role` and team scoping.

## Verification

- `run_all_tests.py` in the 3.11 venv: all green, or only the known OCR failures.
- `pip-audit`: 0 advisories.
- 375px sweep: 0 overflowing elements, with screenshots looked at.
- reviewer agent; security-auditor too if any route code changes.

## Out of scope

Frontend JS dependencies (none are installed; vendor files are static), the Docker non-root
user and `Image.open(formats=…)` hardening from the audit (separate task), and redesigning any
page.

## Open question (doesn't block)

After this merges, the shared local 3.9 venv can't install the new requirements
(Pillow 12 needs ≥ 3.10). Local test runs in other worktrees would keep the old Pillow until
the shared venv is rebuilt on 3.11. Rebuilding it is a one-time step that affects every
session, so it's yours to OK; I won't do it in this branch.
