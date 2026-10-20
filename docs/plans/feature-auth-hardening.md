# Plan: feature/auth-hardening

## Goal

Keep hardening the account flows that shipped in `feature/auth-flow` (merged `77e25f0`).
The focus is the cases the user named: double clicks, the back button, expired and reused
links, two tabs at once, mobile Safari, slow email, signing up twice, and logging in during a
reset. Each round: find, fix with a new test (failing first), push. Never merge.

## Prior art

`feature/auth-flow` already did three hardening rounds, logged in `AUTH_NOTES.md` (on
`main`), with headless E2E scripts in that session's scratchpad (`e2e.mjs`, 41 checks;
`round2.mjs`). This branch **continues that same `AUTH_NOTES.md`**: a new summary at the top
and rounds 4+. It doesn't start a parallel log or a second set of auth code. Searched
TASKS.md and `git branch -a` for `auth-hardening`: none.

## Approach: what each round probes (beyond rounds 1–3)

1. **Two tabs, two people.** Sign in as A in one tab and B in another with "Keep me signed
   in". The shared localStorage token is silently replaced, so tab A *looks* like A but acts
   as B. Expect: tab A notices and reloads or signs out.
2. **Links that die while the page is open.** Valid on load, expired or used by submit, so
   the friendly dead-link screen must come up mid-form. Also: superseded by a resend from
   another tab while the page is open.
3. **Back button everywhere.** Forgot → sent → back; reset success → back; dead link →
   back; login with the expired notice → back. Nothing should resurrect a form that can only
   fail, or a used token.
4. **Double clicks / Enter-key repeats** on every button, including the "send it again" and
   "Send me a new link" links, Sign out, and the show/hide toggle.
5. **Mobile Safari** (Playwright WebKit iPhone): landscape, 200% text zoom, the keyboard
   covering the submit button, the "Go" key submitting, autofill attributes, safe-area insets.
6. **Slow and failed email.** SMTP delay; SMTP failure (`_send` returns False). Responses
   stay generic, but the failure must be loud in the logs.
7. **Signing up twice**, in parallel tabs with different company names; signup while
   already signed in.
8. **Logging in during a reset**, from the UI side across two browsers.
9. **Return to where you were** after a session expires mid-use (smoothness), if cheap.

## Files

Only auth surfaces: `frontend/app/{auth-common,access-gate,api,login,signup,finish-signup,
forgot-password,reset-password}.js`, `frontend/app/auth.css`, the auth HTML pages,
`backend/app/{api,auth,database,email_service,password_rules}.py` auth sections,
`backend/tests/test_auth_flow.py` (+ new test files registered in `run_all_tests.py`),
`AUTH_NOTES.md`.

**Not touched:** document routes, the landing page, `render.yaml`, owner and admin beyond
auth.

## Team isolation & roles

No document routes or queries are touched. The auth routes stay public by necessity and
rate-limited. Any new route gets `@require_role` or is documented as public.

## Feature flag

None new. Signup stays behind `SELF_SERVE_SIGNUP_ENABLED` (default off).

## Verification

Each fix gets a unit test (verified failing on the old code) or an E2E check. Each round runs
`run_all_tests.py`, plus headless E2E on Chromium (desktop, tablet, Android) and WebKit
(iPhone, desktop). Screenshots of anything visual are opened and looked at. Push after each
round.

## Out of scope

The same-site API move (`api.getabstractly.com`), per-device token revocation, CAPTCHA, an
admin approval step for signups, and the primary checkout's `.env` vs `_session_users.py` test
collision (a separate task in TASKS "Up next").

## Open questions

None. Same defaults as `feature/auth-flow`.
