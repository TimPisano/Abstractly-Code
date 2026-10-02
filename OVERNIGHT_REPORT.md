# Overnight report — `docs/tester-pack` (2026-10-01)

Branch `docs/tester-pack`, worktree `~/dev/projects/abstractly-tester-pack`,
pushed to origin. **Not merged; `main` not touched.** No backend code changed.

## ⚠️ Read first

1. **The shared folder is still mid-merge from yesterday's `chore/agent-os` merge.**
   `~/dev/projects/lease-abstraction` has an unfinished merge (staged, no
   commit, nothing pushed). I left it alone: finishing it is a merge, and
   the new guard also blocks `git merge --abort` on main. To finish it,
   type `/merge-branch chore/agent-os` in a session there. To back out,
   run `git merge --abort` yourself in a terminal.
2. **The report page's T-12 upload is broken** (reproduced against a
   local server). The help articles route testers around it, but it's
   the first thing a tester would try. Details under "Bugs found".
3. **Before sending invites:** give each tester the **Analyst** role and
   a **team**. Viewers can't open the Deal Mismatch Report, and users
   without a team can't upload.

## What was built

| Phase | Commit | What |
|---|---|---|
| 1 | `71b344d` | **Help & Guides** view in the app (sidebar: Help → Help & Guides): searchable article list + reader. **Getting started** walks through upload leases → import rent roll → read the Deal Mismatch Report → export. **What each discrepancy type means** explains every type, dollar math and severity. |
| 2 | `4c168c8` | 15 more articles, 17 in total: uploading leases, importing a rent roll, reading the report, T-12, exports, lease fields/citations/corrections, amendments, dashboard/alerts, discrepancies/tasks, rent roll/compare/trends, Q&A, roles. **Troubleshooting:** every upload error message mapped to a fix, plus "when the report looks wrong" and beta known issues. `docs/tester-pack/HELP_FACTS.md` gives the code source for every number and message. |
| 3 | `3252243` | `docs/tester-pack/emails/`: invite, day-3 check-in, feedback request. Fill-ins are marked `[[FILL: …]]` (search for `[[FILL` before sending). |
| 4 | `18c9af8` | `docs/tester-pack/feedback-questionnaire.md`: 10 questions on time saved (Q2 vs Q3) and real errors caught (Q5, Q6), with a guide to reading the answers. |
| 5 | `6413914` | Updated `drafts/sales/` (local only, originals saved as `*.bak-2026-10-01`). Change log: `docs/tester-pack/SALES_DRAFTS_CHANGES.md`. Fixed false claims (concession extraction; "$150/mo = high severity", which is actually Low; exports "with their name at the top") and added T-12 and per-team pricing. |

## How it was verified

- **Facts:** every limit, threshold and error string in the help came
  from the code, gathered by an exploration agent and spot-checked by me.
  The T-12 bug was reproduced live: `POST /portfolio/deal-mismatch-report`
  gives 200 without a T-12 and `400 "t12_file requires property_address"`
  with one sent the way the UI sends it.
- **Visual:** headless Playwright against a throwaway local server
  (temp DB, fictional demo login, no API key). 24 screenshots at
  1440/768/375px, covering several scroll positions, search, no-results,
  a long table and the sidebar entry. **I opened every one.** That review
  found and fixed three layout problems: the article list became a
  cramped inner scroll box, the stacked list was too long on narrow
  screens, and tables were clipped on phones (they now stack into
  labelled cards). In-article links and jump-to-screen links are
  confirmed working at all three widths, with zero console errors.
- **Tests:** `run_all_tests.py` gives **76/77** in this worktree.
  `test_demo_deal_golden.py` fails, and it's **not this branch**: the test
  fakes `user_id = 1` without creating that user, so it only passes where
  `backend/.env` seeds an admin. With a fictional admin passed through
  env vars it passes. It's a pre-existing test bug from `74d3237`, and
  it will fail in CI or any fresh worktree.
- **Reviewer:** _see below_

## Bugs found (not fixed, out of scope for a docs branch)

Ordered by how much they'd hurt a tester. Each is worth a small `fix/` branch.

1. **Report-page T-12 upload always fails.** `deal-mismatch-view.js:42-44`
   never sends `property_address`, and `api.py` requires it whenever a T-12
   is attached. The working path is the Upload page's T-12 cross-check.
2. **Rent Roll vs. T12 Income check can never fire** (`deal_mismatch.py:409-414`).
   It compares the rent roll's *monthly* rent sum against the T-12's *annual*
   income, with no ×12.
3. **Only .csv/.xlsx rent rolls feed the Deal Mismatch Report**
   (`portfolio.py:1383-1388` decides by file extension). PDF, Word, .xls and
   photo rent rolls import fine but are treated as *leases*. Leases
   uploaded as .xlsx/.csv are treated as rent-roll rows.
4. **Vacant rows are never imported**, so the T-12 occupancy check always
   sees 100% occupancy and the bad-debt check's "no vacancies" condition is always true.
5. **Duplicate upload notice is never shown.** The backend reuses the
   existing lease, but the UI ignores the message and shows "Tenant not
   found". The duplicate lookup isn't team-scoped either (`usage_limits.py:123-126`),
   which matters once multiple firms share a deployment.
6. **The 25 MB upload limit is unreachable.** Flask caps requests at 16 MB (`api.py:213`).
7. **.xls T-12 is accepted but can't be parsed** (openpyxl doesn't read .xls).
8. **Deal Mismatch rows show as raw "deal_mismatch" in Discrepancies**, with no label or filter.
9. **The app's sidebar scrolls off-screen on long pages.** It's
   `position: sticky`, but sticky doesn't take effect here; confirmed on the
   Dashboard. On phones the floating chat button covers article text.
10. **Plan limits aren't enforced.** Pricing says 50/250 documents a month;
    the backend applies a flat 200 to every team.
11. **The demo site's seed data is commercial** (a coffee shop, "Suite 200"),
    not multifamily. Use Maple Ridge for demos.
12. **`test_demo_deal_golden.py` depends on a local `.env`** (see Tests above).

## Agent-system notes from tonight

- **The new hooks went live mid-session** when the `chore/agent-os` merge
  started in the shared folder. They worked as designed:
  - The main guard blocked my unapproved merge commit.
  - The browser rules held.
  - Read-only reviewers stayed read-only.
- **The placeholder flag misfired once.** It flagged "(the last three
  calendar columns)" in a subagent's report, because the pattern
  `(the …)` catches ordinary prose. Consider tightening it to
  `(the real …)`, `(your …)` and `(insert …)`.
- **The app's login rate limit (429) tripped** after repeated headless
  logins, which is correct behavior. The screenshot script now logs in
  once and reuses the token.

## Housekeeping I left for you

- The local test servers I started (API :5011, site :4173) are stopped.
  The throwaway DB and screenshots stay in the session scratchpad, not the repo.
- TASKS.md row for `docs/tester-pack` added to the shared TASKS.md
  (uncommitted, because the folder is mid-merge).
