# feature/tester-ready: overnight report (2026-10-19)

Branch `feature/tester-ready`, worktree `~/dev/projects/abstractly-tester-ready`,
branched off `main` at `71889b4`. **Not pushed, not merged, nothing deployed,
Render untouched** (as instructed). 8 commits of its own plus the merged
auth-hardening commits; 45 files changed vs `main`.

**Bottom line:** testers can now be put on production as teams. You create
their firm in the owner console, its admin invites teammates by email, and
everyone on a team sees the same leases. Another team sees none of them
(proven by an automated test and a headless click-through). Uploads stop at
a monthly page limit before any AI work. Turn invites on with
`TEAM_INVITES_ENABLED=true` (see "Render environment variables").

Steps 7 and 9 were **not done**: they aren't defined anywhere I could find
(see "Decisions I need from you", item 1). Step 8 was skipped as you asked.

---

## What each step did

| Step | Commit | Suite before commit | What it did |
|---|---|---|---|
| 1 | `8125f04` | 85/85 | Merged `feature/auth-hardening` (no conflicts): two people in one browser, return to the same screen after a session ends, pasted links with junk, Safari password manager, phone keyboard hints, browser test scripts. |
| 2 | `10c3ef1` | 85/85 | Confirmed prod's database lives on the persistent disk (below). Fixed the outdated "no per-account isolation" text in `render.yaml`, `docs/DEPLOYMENT.md`, `docs/TESTER_VERIFICATION_CHECKLIST.md`. Comments and docs only. |
| 3 | `92ae950` | 86/86 | Team invites by email, behind `TEAM_INVITES_ENABLED` (off by default). Removing a member signs them out everywhere, for good. |
| fix | `495717e` | 87/87 | Team-setup page bug: a 9-character password showed "this link is dead" and hid the form. |
| 4 | `8f6c45e` | 88/88 | Monthly page limit, default 1,000 a month, enforced before any AI work. Editable per team in the owner console. |
| 5 | `fb11c30` | 89/89 | The two-account check as an automated test. |
| 6 | `28d8e2d` | 89/89 | Headless click-through of the whole tester flow; fixed the three things it found. |
| 7 | — | — | **Not done: not defined.** |
| 8 | — | — | Skipped, per your instruction (you'll create the Google and Microsoft credentials). |
| 9 | — | — | **Not done: not defined.** |
| report | (this file) | 89/89 | |

Every bug fix has a regression test that I ran against the code before the
fix and watched fail.

### Step 2: does prod's data survive a redeploy?

Yes, as far as the repo can show:

- `render.yaml` gives `abstractly-api` a 1 GB disk at `/app/data` (paid
  `starter` plan) and sets `DB_PATH=/app/data/lease_portfolio.db`.
- `backend/app/api.py` applies `DB_PATH` at startup. The background
  extraction worker applies it too, because each job imports `api.py`
  (`backend/app/jobs.py:53`).
- Nothing deletes data at startup. `database.reset_db()` is only ever called
  by tests.
- The Docker image contains no `/app/data` folder and excludes `*.db`
  (`backend/.dockerignore`). If the disk weren't mounted, SQLite couldn't
  open the file and the app wouldn't start. Prod has stayed healthy since the
  disk was added on Oct 4.
- **Still yours to check:** the Disks tab on `abstractly-api` in the Render
  dashboard. That's the only way to be certain.
- **Logins don't survive a redeploy unless `FLASK_SECRET_KEY` is set on
  Render.** If it's missing, the app makes a new key on each start
  (`api.py:214-224`) and everyone is signed out on every push. Their data
  stays.

### Step 3: invites (how it works)

- A team **admin** (the team's top role; "owner" in this code means you)
  types an email and a role on the Team page. The name is optional.
- The app creates a pending member on the admin's own team and emails a
  single-use link that lasts 72 hours. The database stores only the link's
  SHA-256 hash, so a database leak exposes no usable links (a test reads the
  whole database file to prove it).
- The link opens `team-setup.html`, which says "Join Harbor Capital". The
  invitee picks their own password and lands in the app, signed in.
- **Pending Invites** list:
  - Shows when each link expires.
  - **Resend:** sends a new link; the old one stops working.
  - **Revoke:** the link stops working and the email can be invited again.
- If email isn't configured, the admin gets the link to copy, same as team
  creation.
- **Removing a member** is the existing Deactivate button. Two problems
  were fixed:
  - Deactivation already blocked a member on their next request, but
    reactivating them brought every old cookie and token back to life.
  - Now deactivation bumps `session_version`, so old sessions stay dead.
- Pending invitees can't sign in, be assigned tasks, be added to message
  threads, or be edited through the member routes.
- **New routes:**
  - Admin only, caller's own team: `GET`/`POST /team/invites`,
    `POST /team/invites/<id>/resend`, `POST /team/invites/<id>/revoke`.
  - Public, rate-limited, flag-gated: `POST /auth/invite-status`,
    `POST /auth/accept-invite`.
- No database schema change. The invite uses a new `users.status` value
  (`invited`) and a new token purpose (`invite`) in the existing table.

### Step 4: monthly page limit (and two bugs that made it do nothing)

What was wrong on `main`:

- **Uploads never recorded their page count** (`usage_events.pages` was
  always empty), so the page limit could never be reached.
- The check only blocked a team **already** at its limit. One 150-page file
  at 990/1,000 got through.
- `POST /leases/batch` skipped the quota checks entirely.
- The per-file cap (`MAX_PAGES_PER_FILE = 150`) never ran for PDFs. The code
  that should count pages crashed on a missing file path, and the error was
  silently ignored.

What it does now:

- `DEFAULT_MONTHLY_PAGE_QUOTA` is 2000 → **1000**. This was the only change
  in `usage_limits_config.py`.
- `check_team_quota(team_id, incoming_pages)` blocks any upload that *would*
  go over the limit, with a message like:
  > "This file has 6 pages, but your team has 5 of its 1,000 monthly pages
  > left. Nothing was processed. Try a smaller file, or contact Abstractly to
  > raise your team's limit."
- **PDFs:** the page count is read from the file itself (no OCR), so an
  oversized PDF is refused before any text extraction.
- **Every format, every upload route** (single, batch, resubmit, amendment,
  `/extract`): the limit is checked again once the pages are known, before
  any AI call. That same point records the pages, so batch uploads now count
  too.
- **Owner console:** a team's detail shows "X of Y pages used this month"
  with an editable limit and a "Use default" button. `PATCH /teams/<id>` now
  rejects bad values (text, negatives, fractions, more than 1,000,000).

### Step 5: the two-account test (`backend/tests/test_two_team_access.py`)

- **Team A:** you create it in the owner console, its admin sets a password
  from the setup email, invites a teammate, and the teammate accepts.
- **Sharing:** each uploads a lease; each sees both.
- **Team B, created separately, gets 404** on every route that puts a team A
  lease id in its path. That's all 21 route/method pairs: view, edit,
  delete, comments, tags, fields, versions, risks, `export.xlsx`,
  `summary.pdf`, Google Sheets, resubmit and amendments.
  - Routes are read from Flask's own route list, so a new lease route that
    forgets team scoping fails this test automatically.
- **Team B's own exports** (Excel, CSV, PDF reports) contain nothing of team
  A's. The test opens the PDFs and spreadsheets and reads their contents.
- Team A's leases are unchanged afterwards.
- **Proof the test works:** I made lease lookups ignore the team (in memory
  only) and the test failed immediately. Team B could replace team A's lease.

### Step 6: headless click-through (`.claude/tools/auth-e2e/tester-ready.mjs`)

- **Run it with:** `.claude/tools/auth-e2e/run-tester-ready.sh`, then the
  node command it prints. It uses ports 5741/8741, and emails are captured
  to a folder, never sent.
- **The flow it covers:**
  1. Owner creates a team.
  2. Admin tries a 9-character password, then a common one, then a good one.
  3. Admin invites a teammate.
  4. Teammate joins.
  5. Admin uploads a lease and the teammate sees it.
  6. Admin removes the teammate, who is signed out on their next page load.
- **Result:** 16/16 checks on desktop Chrome, phone Chrome, and iPhone
  Safari (WebKit). I looked at the screenshots.

**What it found and I fixed:**

1. On the invite page the fields and the short "Join team" button wrapped
   onto shared lines. Now one per line.
2. On phones, the member and invite tables pushed Resend/Revoke/Deactivate
   off the screen. They now scroll sideways inside their card, and the page
   itself no longer scrolls sideways (checked by the script).
3. The pending list repeated "riley" under "riley@…" when no name was given.

**Confusing things it found that I did NOT change (your call):**

- **On phones, Resend and Revoke need a sideways swipe** inside the table. It
  works, but it isn't obvious. A stacked phone layout would be better.
- **A sidebar click in the first second after signing in does nothing.** The
  sidebar shows before the app finishes loading, and clicks before then are
  silently ignored. The app then lands on the Dashboard. This was already on
  `main`; it's what made my early click-through runs flaky. The script now
  retries.
- **The chat button covers the end of tables on phones.** Also already on
  `main`.
- **Not tested:** real email delivery (emails were captured, not sent), and
  anything on Render itself.

---

## Decisions I need from you

1. **Steps 7 and 9 aren't defined anywhere I can see.** Our plan had steps
   1–6. I searched TASKS.md, `docs/plans/`, `drafts/` and every worktree's
   plans and reports. Nothing lists a step 7, 8 or 9. Your note about Google
   and Microsoft credentials suggests a list from another session (maybe
   Gmail/Outlook account linking, `backend/app/email_accounts.py`). Send me
   the list and I'll do them.
2. **The per-file page cap now actually works at 150 pages.** Testers' PDFs
   over 150 pages will now be refused with a clear message. (Before, they
   were accepted, but AI extraction silently read only about the first 70
   pages.) If you want more, change `MAX_PAGES_PER_FILE` in
   `backend/app/usage_limits_config.py`; I left it alone as you asked. My
   suggestion is **1000**, the same as the monthly default, together with
   the large-file work.
3. **When pages count.** Pages count when a file is accepted for
   extraction, even if extraction then fails. That matches how the
   document quota already counts. A spreadsheet of lease rows counts as 1
   page. OK?
4. **The quota message says "contact Abstractly"** but gives no address.
   Should it name tim@getabstractly.com?
5. **Inviting an email that already has an account on another team**
   returns "That email already has an Abstractly account". That tells a team
   admin the address is registered somewhere. The alternative was an invite
   that silently goes nowhere. Keep it?
6. **Five list filters return 200 and an empty list, not 404,** when given
   another team's lease id: `/discrepancies?lease_id=`, `/alerts?lease_id=`,
   their CSV exports, and `/tasks?lease_id=`. They leak nothing (the test
   checks that). Making them 404 would change existing routes. Leave them?
7. **Reset links survive deactivation.** A removed member can still finish
   a password reset they started before removal, but can't sign in. An
   existing test protects this, so I left it. Change it?
8. **Admins can deactivate themselves** and are now signed out immediately.
   That's existing behavior, but sharper now. Add a guard?
9. **Self-serve signup on prod:** `SELF_SERVE_SIGNUP_ENABLED` is off on prod
   (only the tester server has it). With invites, testers don't need it.
   Keep it off?
10. **Python versions:** see below.
11. **The R2 / 2 GB uploads follow-up** is recorded in TASKS.md. It belongs
    on a new branch stacked on `feature/large-files-any-type`, which another
    session is building. That session should call this branch's page check
    (I updated the shared memory note to say how).
12. **Next for this branch:** run `/review-branch feature/tester-ready`
    (reviewer + security auditor), then `/merge-branch` when you're happy.
    Nothing here is pushed yet.

---

## Read-only review: feature/deal-assistant

Done by the reviewer agent; nothing changed or run.

- **State:** 8 commits ahead of `main`, 272 behind. The worktree is clean.
  All 5 planned phases are built: the chat panel uses the real LLM route,
  answers carry citations (lease and page), there's a per-team monthly
  assistant credit with a meter, suggested questions, and an owner-console
  credit field. `main`'s TASKS.md row ("nothing built") is stale.
- **Security:** looks right.
  - New routes have `@require_role` (or `@require_owner`).
  - All queries are scoped to the caller's `team_id`.
  - Citation lease ids are checked against the team's own leases.
  - No secrets in the diff.
- **Tests:** 19 new ones, with Anthropic mocked. **But they would fail on
  today's `main`:** they fake sessions the old way, without
  `sync_session_user`, so every route test would get 401.
- **Cost bug (medium):**
  - The assistant defaults to `claude-sonnet-5` (`assistant.py:46`), but
    the cost meter uses Haiku prices (`usage_limits_config.py` ~line 43).
  - So real spend is about 3× what's metered: the $15 default credit is
    really about $45.
- **No feature flag:** it goes live for every team on merge, which breaks
  the "new features default off" rule.
- **Conflicts:** five files, the same against `main` and against this
  branch. `TASKS.md`, `OVERNIGHT_REPORT.md`, `test_assistant.py` and
  `owner-app.js` look easy; `api.py`'s 3 hunks are identical lines.
- **Overlap with this branch:** it adds functions to `usage_limits.py`,
  which this branch owns. Rebase it after tester-ready merges.
- **Verdict: FINISH FIRST.**
  1. Rebase onto `main` (after tester-ready) and fix its test helper.
  2. Fix the price/model mismatch.
  3. Put it behind an env flag, off by default.

---

## Python 3.9 vs 3.11

- **Render runs Python 3.11.** `backend/Dockerfile` starts `FROM
  python:3.11-slim`.
- **Your Mac runs the tests on Python 3.9.6.** The shared venv
  (`~/dev/projects/lease-abstraction/backend/venv`) was built from Apple's
  Command Line Tools Python (`pyvenv.cfg`: `version = 3.9.6`).
- **Python 3.11 isn't installed on this Mac at all.** `python3.11` isn't on
  the PATH and Homebrew has no python3. So the CLAUDE.md setup line
  (`python3.11 -m venv venv`) can't work here as written.
- **Risk:** low today, since the suite passes on 3.9 and nothing on this
  branch uses 3.10+ features. But code that works on 3.11 (Render) could
  fail locally on 3.9, and the reverse for small library differences. Python
  3.9 is also past end-of-life; Google's libraries already print warnings.
- **Fix (your decision, it installs software):**
  1. `brew install python@3.11`
  2. Rebuild the shared venv with `python3.11 -m venv` and
     `pip install -r backend/requirements.txt`.
  3. Re-run the suite.

---

## Render environment variables to set yourself

All on **`abstractly-api`** (prod), in the dashboard's Environment tab. I
didn't change `render.yaml`'s variable list or anything on Render.

| Variable | Value | Why |
|---|---|---|
| `TEAM_INVITES_ENABLED` | `true` | **New.** Turns on invite-by-email. Off (unset) means the Team page keeps the old "add with a password" form. |
| `FLASK_SECRET_KEY` | (check it's set) | Without it, every tester is signed out on every deploy. |
| `EMAIL_USER`, `EMAIL_APP_PASSWORD` | (check they're set) | Setup, invite and password-reset emails. Without them, setup and invite links fall back to copy-and-send-yourself, but **password reset emails don't go out at all.** |
| `TOKEN_ENCRYPTION_KEY` | (check it's set) | Already required; listed for completeness. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` | (already set) | Only used to create your owner account on a brand-new database. Nothing to change. |
| `ADMIN_ALLOWED_ORIGINS` | already `https://getabstractly.com,https://www.getabstractly.com,https://abstractly-n0id.onrender.com` | Also sets the address used inside setup and invite links. Nothing to change. |
| `ANTHROPIC_API_KEY` + `LEASE_AI_EXTRACTION=true` | only if testers should get AI extraction | Commented out in `render.yaml` today; without them uploads use the regex engine. Your call (and your Anthropic billing). |
| `LEASE_EXTRACTION_JOB_TIMEOUT_SECONDS` | leave at the default (600) for now | Only matters once large-file uploads land. Then about 3600, measured on Render first. |

Nothing needs setting on `abstractly-tester-api` for this branch. Testers
won't use it.

---

## Where things are

- **Plan context and decisions:** TASKS.md (`feature/tester-ready` handoff
  block on `main`).
- **New tests:** `backend/tests/test_team_invites.py` (15),
  `test_team_setup_link.py` (3), `test_monthly_page_limit.py` (8),
  `test_two_team_access.py` (1 end-to-end).
- **Click-through:** `.claude/tools/auth-e2e/tester-ready.mjs` and
  `run-tester-ready.sh`.
