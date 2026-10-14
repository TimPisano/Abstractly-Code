# Plan: Calendly popup on every Book a Demo CTA

> **Revision 2026-10-05 — read this first.** The user answered the open
> questions and widened the scope (see "Revision 2026-10-05" at the end).
> Where the two disagree, the revision wins.

## Goal

Every "Book a Demo" button on the marketing site (`index.html`,
`pricing.html`) opens the user's Calendly booking popup in place, instead
of scrolling down to the on-page demo-request form. A visitor can pick a
time without leaving the page. If Calendly is unavailable or blocked, the
button still falls back to the existing form — no CTA ever becomes a
dead click.

## Prior art

**None found** — this is greenfield. Searches run from the primary
checkout:

- `grep -n -i 'calendly\|booking\|calendar' TASKS.md` → nothing
- `git log --all --oneline -i --grep='calendly'` → nothing
- `git log --all --oneline -i --grep='booking'` → nothing
- `git grep -n -i 'calendly' <every local branch> -- frontend backend` → nothing
- `git stash list` → 2 stashes, both unrelated (t12 test WIP, agent-ade76 tenancy WIP)

What *does* already exist, and which this builds on rather than replaces:

- **A working demo-request flow.** `index.html:310-352` is a real form
  (`#demoForm`), handled in `landing.js:54-134`, posting to
  `POST /demo-request` (`backend/app/api.py:3422`), with inline validation,
  a success confirmation (`demoFormConfirm`), and a `demo_requested`
  analytics event. Tests: `backend/tests/test_demo_request.py`.
- **9 CTAs** pointing at `#book-demo`: 5 in `index.html` (announcement bar
  :33, nav :50, hero :76, sample-report note :171, footer :376) and 4 in
  `pricing.html` (:33, :50, :141, :157).
- Nav and hero **already have** Book a Demo buttons, so the task's step 3
  ("add one if missing") is a no-op.
- No "Get started" or "Contact sales" text exists on either page, so that
  part of the task's step 2 is also a no-op.

## Approach

1. Add the Calendly `<link>` + `<script async>` to the `<head>` of
   `frontend/index.html` and `frontend/pricing.html`. There is **no base
   template** (vanilla HTML, no build step), so this is two files.
2. Extend the Content-Security-Policy for all three frontend services in
   `render.yaml` to permit Calendly. Without this the popup is blocked and
   silently never opens — see **Why the CSP change is required** below.
3. Repoint the 9 CTAs to open the popup, keeping `href="#book-demo"`
   intact as a fallback:
   ```html
   <a href="#book-demo"
      onclick="Calendly.initPopupWidget({url: 'https://calendly.com/timmypisano24/abstractly-intro-call'}); return false;">Book a Demo</a>
   ```
   `return false` suppresses the anchor jump when Calendly loaded; if the
   script was blocked or failed, `Calendly` is undefined, the onclick
   throws, and the browser follows the href to the existing form. Graceful
   degradation for free.
4. **Do not touch the form's own submit button** (`index.html:352`,
   `id="demoSubmitBtn"`). Its label is also "Book a Demo", so the task's
   literal wording would catch it, but repointing it would break form
   submission entirely.
5. Headless screenshots at 1440/768/375 on both pages to confirm styling
   is untouched, plus a scripted check that the popup opens.

### Why the CSP change is required

All three frontends currently send (`render.yaml:124-128, 213-217, 316-320`):

```
default-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; font-src 'self';
```

There is no `script-src`, so scripts fall back to `default-src 'self'`.
Five separate directives would block Calendly:

| What Calendly needs | Blocked by | Fix |
|---|---|---|
| `widget.js` from `assets.calendly.com` | `default-src 'self'` | add `script-src 'self' https://assets.calendly.com` |
| `widget.css` from `assets.calendly.com` | `style-src` has no external host | add `https://assets.calendly.com` |
| the popup's `calendly.com` iframe | no `frame-src` → `default-src 'self'` | add `frame-src https://calendly.com` |
| host/avatar images | `img-src 'self' data:` | add `https://*.calendly.com` |
| its webfonts | `font-src 'self'` | add `https://assets.calendly.com` |

This is the one place the plan goes beyond "don't change anything else":
it is deployment config, not page content, and the feature does not
function without it.

## Files to change

- `frontend/index.html` — head snippet; 5 CTA onclicks
- `frontend/pricing.html` — head snippet; 4 CTA onclicks
- `render.yaml` — CSP for the 3 frontend services
- `docs/plans/feature-calendly-booking.md` — this file

## Files not to touch

- `frontend/landing.js`, the `#book-demo` form markup, `/demo-request`,
  `test_demo_request.py` — the fallback flow stays exactly as it is.
- `frontend/app/`, `frontend/admin/`, `frontend/owner/` — the customer app
  and staff consoles get no booking popup.
- `frontend/landing.css` — no styling changes (task requirement).
- Any backend code.

## Team isolation & roles

**Not applicable, and verified rather than assumed:** this change adds no
routes and no queries. It touches two static HTML files and `render.yaml`.
The one endpoint in the vicinity, `POST /demo-request`, is unauthenticated
public marketing intake by design and is not modified.

## Feature flag

None. A booking link is not a gated feature, it is reversible in one
commit, and the fallback means the worst case is the previous behaviour.

## Verification

- `python backend/tests/run_all_tests.py` — expect **79/79** (baseline on
  `main` @ `7ac879b`, confirmed by me today). No backend change, so this
  is a regression check only.
- A CSP unit check asserting each of the 5 directives names the Calendly
  host it needs, for all 3 frontend services — mirroring the existing
  `render.yaml`↔`config.js` pairing test from `fix/tester-api-routing`, so
  a future CSP edit can't silently re-break the popup.
- Headless screenshots (`node .claude/tools/screenshots.mjs`) of
  `index.html` and `pricing.html` at **1440 / 768 / 375**, several scroll
  positions, opened and looked at — confirming no visual change.
- A headless click test: click the hero CTA, assert a Calendly iframe is
  inserted and no CSP violation appears in the console.

## Out of scope

- Removing or hiding the existing demo-request form (it stays as the
  fallback; deciding its long-term fate is a separate product call).
- Adding Calendly to the customer app, admin, or owner consoles.
- Replacing the `demo_requested` analytics event with a Calendly
  conversion event.
- Picking between the competing `feature/pricing-page` and
  `feature/landing-positioning` heroes.

## Open questions

1. **Does Calendly replace the form, or sit in front of it?** This plan
   keeps both: popup first, form as fallback. If you want the form gone,
   that is a follow-up (it also orphans `/demo-request` and its test).
2. **Merge-order collision.** `feature/pricing-page` and
   `feature/landing-positioning` both rewrite `index.html` and
   `pricing.html`, and the hero choice is still open. Whichever of the
   three merges last will have to re-apply the onclicks. Cheapest order is
   to land the hero decision first, then this; happy to do it either way.
3. **Confirm the booking URL** is exactly
   `https://calendly.com/timmypisano24/abstractly-intro-call` — I will not
   guess at a different event slug.

## Revision 2026-10-05

**Answers from the user:**

- **Booking URL:** `https://calendly.com/timpisano/abstractly-intro-call`
  (the user pasted it with `?back=1&month=2026-10`; those are browser-state
  params and `month=` would pin the calendar to Oct 2026, so they are
  dropped). This replaces the guessed `timmypisano24` slug above.
- **Form stays.** Calendly sits in front of it; the form is the fallback
  *and* gets its own Calendly hand-off on success (below).
- **Built here**, not on `chore/contact-email` (that branch keeps only the
  contact-detail changes and merges first).

**Added scope:**

1. **Every "Book a call" and "Book a Demo" CTA** opens the popup — now
   also the footer "Book a call" link and the two "How do I reach you?"
   FAQ links that `chore/contact-email` adds. Form's own submit button
   still excluded (it submits the form).
2. **Form success state:** the confirmation text says thanks and shows a
   **"Pick a time"** button that opens the popup with the visitor's name
   and email **prefilled** (`Calendly.initPopupWidget({url, prefill:
   {name, email}})`; if the widget is blocked, the button is a plain
   `target="_blank"` link to the URL with `?name=&email=` query params,
   which Calendly also honours). Touches `landing.js` — this reverses the
   "do not touch landing.js" line above.
3. **Emails:** `send_demo_request_confirmation` (to the visitor) and
   `send_demo_request_notification` (to the user) both include the
   booking link. URL lives in one constant/env var
   (`CALENDLY_URL`, default the URL above) so it is not hard-coded in 3
   places. Backend change → mocked-SMTP tests in `test_demo_request.py`
   asserting the link is in both bodies.
4. **CSP:** as in "Why the CSP change is required", for all 3 frontend
   services, plus a test pinning it. Verified with a **headless** click
   test that the iframe loads and the console has no CSP violation.
   Caveat: that proves the policy locally against the real `render.yaml`
   header values served by a local server; it is *not* the production
   deploy itself, which can only be checked after merge (merge-branch
   step 12 smoke test).

**Rebase first:** the plan's base `7ac879b` is 41 commits behind
`origin/main` (pricing page and team isolation merged since). Rebuild on
current `main` *after* `chore/contact-email` merges, so the new footer and
FAQ links exist to wire up. Baseline test count will be re-measured
(currently 81/82 on main; `test_demo_deal_regression.py` fails on `main`
itself with `401 Login required` — separate fix).

**Files (revised):** `frontend/index.html`, `frontend/pricing.html`,
`frontend/landing.js`, `render.yaml`, `backend/app/email_service.py`,
`backend/tests/test_demo_request.py` (+ a CSP test file, registered).

**Team isolation / roles:** still no new routes or queries;
`/demo-request` is public intake by design and only its email bodies
change.

## Revision 2 — 2026-10-05 (supersedes the popup approach above)

**The user's instruction:** when someone submits the Book a Demo form, save
the request and email them a short note with the link from the
`CALENDLY_URL` env var, Reply-To `tim@getabstractly.com`, sent with
`EMAIL_USER` / `EMAIL_APP_PASSWORD` (all three now set on `abstractly-api`
in Render). If any are missing, log a clear error instead of failing
silently. Point every **Book a call** button on the site at `CALENDLY_URL`.

**Already on `main`** (via `chore/contact-email`): the request is saved,
the visitor gets a confirmation email containing a booking link, and
Reply-To is `tim@getabstractly.com`. What's missing, and what this round
builds:

1. **`CALENDLY_URL` is the only source of the link.** Drop the hard-coded
   fallback in `email_service._calendly_url()`. If it's unset, log an
   ERROR that names the variable and still send the confirmation, minus
   the link ("reply to this email and we'll set up a time"), so the visitor
   is never left with nothing.
2. **Missing `EMAIL_USER` / `EMAIL_APP_PASSWORD`:** `_send()` logs an
   ERROR (was a WARNING) that names exactly which variable is missing.
3. **Honest success message:** `/demo-request` says "we've emailed you a
   link to pick a time" only when the confirmation actually went out with
   a link; otherwise it keeps today's "we'll be in touch" text. The form
   shows the server's message instead of a hard-coded one.
4. **"Book a call" links → `CALENDLY_URL`.** The frontend is static and the
   variable lives on the API, so a new public, read-only
   `GET /public-config` returns `{"calendly_url": ... | null}`. `landing.js`
   rewrites every `a[data-book-call]` to that URL (new tab). Until the
   fetch returns, or if the URL is unset, the link keeps its current
   `#book-demo` fallback to the form, so it's never a dead click. Four
   links get the attribute: footer + FAQ on `index.html` and `pricing.html`.
   The FAQ text "book a call below" drops "below".
5. **No popup, so no CSP change.** A plain link to calendly.com is a
   navigation, which the frontend CSP doesn't restrict. The widget script,
   the 5 CSP directives, and the `render.yaml` edit above are dropped.

**"Book a Demo" buttons stay pointed at the form** (the form is what now
sends the link). Only links labeled "Book a call" go straight to Calendly,
per the instruction's wording.

**Team isolation / roles:** `GET /public-config` is public by design (the
marketing site calls it before anyone logs in), like `/health` and
`/demo-request`. It returns one non-secret config value, reads no
documents or user data, and so has no `@require_role` and no team scope.
`/demo-request` stays public intake.

**Files:** `backend/app/email_service.py`, `backend/app/api.py`,
`backend/tests/test_demo_request.py`, `frontend/index.html`,
`frontend/pricing.html`, `frontend/landing.js`.

**Overlap:** `feature/landing-interactive` adds a calculator "Book a call"
button; whichever branch merges second adds `data-book-call` to it.

**Bug found during local testing (fixed here, with a regression test):**
every outgoing email's `From:` header was encoded whole, address
included, because the display name "Tim Pisano — Abstractly" contains an
em dash and `_send()` built the header as one f-string. Mail parsers found
no sender address in it. Present since `2a7e344` (2026-08-13), so it
affected all app email, not just this flow. Fix: `email.utils.formataddr`.

**Added 2026-10-05 (user, mid-build):**

- **Admin notification → `ADMIN_EMAIL`.** It went to
  `tim@getabstractly.com`, which forwards into the same Gmail that sends
  it, so Gmail hid it. `DEMO_REQUEST_NOTIFY_EMAIL` is removed; unset
  `ADMIN_EMAIL` logs an ERROR and skips only the notification. Requester
  emails keep Reply-To `tim@getabstractly.com`.
- **Requester email didn't arrive in a live test** (Yahoo address; the
  admin notification did arrive). Production runs `main`, which has the
  broken `From:` header above, which is a likely cause (Yahoo rejects
  malformed From headers after Gmail has accepted the send). Not
  confirmable from here: such a bounce lands in the sending Gmail inbox,
  not the app logs. This branch now logs every send's outcome: INFO
  "Email sent to …" on success, ERROR "Email FAILED to …" with the exact
  exception or the server's refusal, plus tests for each.
- **Full suite green:** `test_demo_deal_regression.py` (TASKS "Waiting on
  you" #10) gets a real users row and the now-required `team_id`, the
  same fix `test_demo_deal_golden.py` already has. Test-only change.

- **Requester email rewritten as a personal note** (user's exact copy):
  subject "Thanks for reaching out, {first_name}", first name from the
  form's name field ("there" if blank; all-lowercase gets a capital),
  company sentence falls back to "your team", link text "Grab a time that
  works for you →", signed Tim Pisano, Founder. Its own plain HTML layout
  (white, no card or heading, fluid to 560px) plus a plain-text part; the
  branded template other emails use is untouched.

**Out of scope:** the Calendly popup widget, CSP changes, a startup-time
config check, Book a Demo buttons going straight to Calendly.
