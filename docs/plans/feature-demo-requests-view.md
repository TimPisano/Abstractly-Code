# Plan: feature/demo-requests-view

## Goal

A **Demo Requests** tab in the owner console that lists every Book a Demo
submission (name, email, company, units, message, date), newest first,
with a CSV export. Optionally, each new submission is also forwarded to
a Google Sheet through a Google Apps Script webhook whose URL comes from
an environment variable. Unset means off. Setup steps for the Apps
Script live in `docs/DEMO_REQUESTS_SHEET.md`.

The user's task prompt (2026-10-05) asked to build and push in one
pass, so it is treated as the plan approval.

## Prior art

- **Storage already exists on main.** `demo_requests` table,
  `database.insert_demo_request`, `database.get_all_demo_requests`
  (newest first). `POST /demo-request` already validates, rate-limits,
  honeypots, saves, and emails. Nothing lists the rows yet. This
  branch builds on all of that and adds no new table.
- Searches run: TASKS.md (`demo request|book a demo|sheet|webhook|apps
  script`), commit messages on all branches, stashes, and a grep of
  `backend/app` and `frontend`. No other branch lists demo requests or
  posts to a webhook.
- `feature/calendly-booking` (plan only, unbuilt) touches the same
  Book a Demo CTAs on the marketing pages, not the owner console or
  `/demo-request`. No overlap.

## Approach

1. `database.get_all_demo_requests`: add `id DESC` as a tie-breaker so
   two submissions in the same instant still list newest first.
2. New routes in `api.py`, both `@require_owner()`:
   - `GET /owner/demo-requests` returns JSON.
   - `GET /owner/demo-requests/export.csv` returns a CSV attachment.
     Every cell that starts with `= + - @`, a tab, or a carriage
     return gets a leading `'`. The text comes from a public form, and
     a cell like `=HYPERLINK(...)` would otherwise run as a formula
     when the owner opens it in Excel or Sheets.
3. New `backend/app/demo_request_sheet.py`:
   - `forward(record)` is best-effort and never raises. It POSTs JSON
     to `DEMO_REQUEST_SHEET_WEBHOOK_URL`. That must be
     `https://script.google.com/macros/s/…/exec`; any other URL is
     logged and skipped.
   - The request uses a 10s timeout and no redirects. Apps Script
     answers a POST with a 302 after the script has already run, so a
     302 counts as delivered.
   - It sends an optional shared secret, `DEMO_REQUEST_SHEET_SECRET`,
     in the body. An Apps Script web app can't read request headers,
     and the deployed URL is reachable by anyone who has it.
   - `forward_in_background(record)` runs it in a daemon thread so the
     public form never waits on Google.
4. `POST /demo-request` calls `forward_in_background` after the insert,
   only for real (non-honeypot) submissions. The insert now uses the
   returned id and timestamp.
5. Owner console: a Demo Requests tab with a table and an Export CSV
   button. The button uses `fetch` with credentials and saves a blob,
   because the console is cross-origin with a cookie session.
6. Docs: `docs/DEMO_REQUESTS_SHEET.md` (the Apps Script plus
   step-by-step setup) and the two env vars in `backend/.env.example`.

## Files to change

`backend/app/api.py`, `backend/app/database.py` (ORDER BY only), new
`backend/app/demo_request_sheet.py`, `frontend/owner/index.html`,
`frontend/owner/owner-app.js`, `frontend/owner/owner.css` (if needed),
`backend/.env.example`, new `docs/DEMO_REQUESTS_SHEET.md`, tests.

## Files not to touch

`render.yaml` (the env vars are set in the Render dashboard, which
makes secrets `sync: false` anyway), the marketing pages,
`email_service.py`, and the other CSV exports.

## Team isolation & roles

"Admin-only" maps to `@require_owner()`, following `GET /waitlist`'s
precedent. Demo requests are Abstractly's own sales leads, with no
`team_id`. `@require_role("admin")` would show them to every customer
firm's admin, which is a cross-firm leak. Non-owners get a 404 and
logged-out users a 401, like every `/owner/*` route. No document
tables are touched.

## Feature flag

The listing is owner-only and ready. Forwarding is off unless
`DEMO_REQUEST_SHEET_WEBHOOK_URL` is set.

## Verification

Backend tests in a new `test_demo_requests_view.py`, registered in
`run_all_tests.py`. All network calls go through a mocked
`requests.post`.

- Routes: owner gets 200, admin non-owner gets 404, logged out gets
  401.
- Ordering, CSV columns and content, and the formula-injection guard.
- Forwarding: off when unset, a non-Apps-Script URL is refused, the
  secret is included, network errors and HTTP 500 are swallowed, 302
  counts as delivered.
- The route forwards a real submission, skips a honeypot one, and
  still returns 201 when forwarding blows up.
- The new routes are added to `test_owner_console.py`'s owner-route
  list.

UI: headless screenshots of the owner console's Demo Requests tab at
1440, 768 and 375.

## Found while building

- The owner console's tab bar had no overflow handling. Five tabs
  already crowded a phone, and a sixth pushed the page wider than the
  screen. The bar now scrolls sideways (`owner.css`), and the demo table
  scrolls inside its own box. This is a shared-CSS change, but tiny,
  and the new tab is unreachable on a phone without it.

## Out of scope

- Statuses, notes, or "contacted" tracking per request.
- Backfilling existing rows into the Sheet.
- Retries or a queue for failed forwards. A failure is logged, and the
  row is always in the DB and the CSV.
- Hardening the other CSV exports against formula injection. Their
  data isn't from a public form, but it's worth a follow-up.
