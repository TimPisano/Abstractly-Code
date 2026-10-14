# Plan: feature/auth-flow

## Goal

The simplest, smoothest account experience. A new syndicator types their name,
work email, and company on a clean **Get started** page and receives a short,
personal "Finish setting up your account" email from Tim. The link opens a page
where they choose a password, with live strength rules and a show/hide toggle.
On submit, their user and team are created and they land in the dashboard,
already logged in. **No account exists until the link is used.** "Forgot
password?" works the same way, and a successful reset signs out every other
session. Links are single-use and stored only as hashes. A newer link kills
the older one. Expired or used links show a friendly page with **Send me a new
link**. "Keep me signed in" decides whether you stay logged in for 30 days or
only until the browser closes.

## Prior art (searched before planning)

Searches: TASKS.md for `signup|forgot|reset|password|auth-flow|keep me
signed|rate limit`; `git log --all --grep` for the same words; `git grep` on
`password_reset_tokens`, `RateLimiter`, `forgot`; stash list; `ls
frontend/app`. Findings, all on `main`, all **to be extended, not
duplicated**:

| Exists on main | Where | What this branch does with it |
|---|---|---|
| `POST /auth/forgot-password`: generic 200, hashed token, per-IP + per-email limit, sends off the request path | `api.py:~2160` | Keep. Change the copy to the exact wording requested and add a `surface`-free single page. |
| `POST /auth/reset-password`: single-use 1h token via `consume_password_reset_token` | `api.py:~2230`, `database.py:2548` | Keep. Add: log in on success, sign out all other sessions, distinct "expired" vs "used" states for the friendly page. |
| `password_reset_tokens` table (sha256, `used_at`, a newer token deletes older unused ones) | `database.py:751, 2523` | Reuse for reset links. Signup gets its own table (see below), because no user row exists yet. |
| `RateLimiter` (in-process fixed window) + login limiter per IP/email | `security.py:143`, `api.py:1971` | Reuse for the signup and token-check routes. |
| `/auth/team-setup` + `team-setup.html` (owner-invited admin sets a password, 7-day link) | `api.py`, `frontend/app/` | Untouched. Different flow (owner invite); its page gets the shared password-strength component only if it's a free win. |
| `forgot-password.html`, `reset-password.html`, `login.html` in `frontend/app/` | | Restyled and extended in place. No second copies. |
| `email_service._personal_email_html`, `_send` (Reply-To tim@getabstractly.com already wired) | `email_service.py` | Reuse for all new emails (plain, personal, mobile, text part). |
| No self-serve signup anywhere (no branch, no stash) | — | New. |

Stale `worktree-agent-ade7619750bfa9a9f` has a competing `accounts` schema.
Ignored per CLAUDE.md. Signup creates rows in the existing `teams` + `users`.

## Approach

### Backend

1. **`signup_requests` table** (new, `database.py`): `token_hash` PK,
   `email`, `name`, `company`, `created_at`, `used_at`. Creating a request
   revokes (keeps, marked unusable) any unused request for the same email, so a
   newer link kills the older one and the page can say so. Consume is atomic (`UPDATE … WHERE used_at IS NULL`), like the
   existing reset tokens.
2. **`POST /auth/signup`** `{name, email, company}`. Public. Validates, then
   is rate-limited per IP and per email *before* any lookup, the same pattern
   as forgot-password. It always returns the same 200 "Check your email"
   response:
   - **No account yet:** creates or replaces the signup request and emails the
     72-hour "Finish setting up your account" link.
   - **Account already exists:** sends a "You already have an account. Sign
     in, or reset your password" email instead. The page never reveals that
     an account exists.
   - All mail goes out on a background thread
     (`_send_email_off_request_path`), so response time can't leak whether an
     account exists either.
3. **`POST /auth/link-status` `{kind, token}`** (POST so the token stays out of access logs) returns
   `valid | expired | used | invalid`. Pages call this on load, so an
   expired or used link shows the friendly page *before* the user types a
   password. Tampered and unknown tokens return `invalid` and show the same
   friendly page. Rate-limited per IP. Never reveals the email.
4. **`POST /auth/complete-signup`** `{token, password, remember}`. Consumes
   the token, enforces the password rules server-side, then in one
   transaction creates the team (company name; `"Acme (2)"` if the name is
   taken, because `teams.name` is UNIQUE) and the user as that team's
   **admin**. It logs them in and returns the same shape as `/auth/login`.
   If the email got an account by another path in the meantime, it fails
   cleanly and points to sign-in. A double-click is safe: the second request
   finds the token used and is sent to sign-in, or to the dashboard if
   already logged in.
5. **`POST /auth/reset-password`** (extend): accepts `remember`. On success:
   bumps `users.session_version`, logs the caller in, and returns the login
   shape.
6. **Sign out everywhere = `users.session_version`** (new integer column,
   migration default 0). It is embedded in the session cookie and bearer
   token at login. `auth._live_user` rejects a credential whose version
   doesn't match the row. The cost is one extra column read per request, on
   the row it already loads. This also makes `/auth/logout` able to really
   revoke.
7. **Keep me signed in.** See open question 1. The checkbox maps to a
   30-day credential when checked and a browser-session credential when
   unchecked. It applies to login, complete-signup, and reset.
8. **Password rules**, shared server and client: at least 10 characters,
   not the email or name, and not on a short list of common passwords
   (bundled, no network). The server is authoritative.
9. **Rate limits:** signup (per IP 10/hr, per email 3/hr), login (existing),
   forgot (existing 3/hr), reset/complete/link-status (per IP 15/15 min).
   429 copy is friendly.
10. **Usage limits:** new teams get the existing defaults from
    `usage_limits_config` (`DEFAULT_MONTHLY_*`) exactly as owner-created
    teams do. A test asserts a signed-up team hits the same quota check.
11. **Emails** (`email_service.py`, with `_personal_email_html` and text
    parts): finish-setup, already-have-an-account, reset (copy rewritten:
    short, first name, signed "Tim"). Subjects are plain. Links are
    full-width-tappable on mobile.

### Frontend (`frontend/app/`, matching landing tokens in `design-system.css`)

12. `signup.html` + `signup.js`: Get started (name, work email, company),
    then a "Check your inbox" state with a resend button (with a cooldown).
13. `finish-signup.html` + `.js`: link-status check, then password form
    (live rules checklist, show/hide, keep-me-signed-in), then the
    dashboard. Expired or used shows the friendly state with "Send me a new
    link".
14. `forgot-password.html`, `reset-password.html`: restyled to match, same
    friendly expired state, and log in on success.
15. `login.html`: "Forgot password?" link, "Keep me signed in" checkbox,
    "New here? Get started" link.
16. Buttons disable while in flight (double-click), and forms survive the
    back button (`pageshow` resets the in-flight state). Inputs use
    `autocomplete` and `inputmode` hints so iOS Safari autofill and the
    password manager work (`autocomplete="new-password"` + hidden
    `username`).

## Files to change

`backend/app/api.py` (auth section only), `backend/app/auth.py`,
`backend/app/database.py` (new table, `session_version` migration, team
create helper), `backend/app/email_service.py`, new
`backend/app/password_rules.py`. New `backend/tests/test_auth_flow.py`
(+ register in `run_all_tests.py`). Frontend: `app/login.*`,
`app/forgot-password.*`, `app/reset-password.*`, new `app/signup.*`,
`app/finish-signup.*`, `app/api.js` (token storage only), `app/styles.css`
(auth-card styles). `AUTH_NOTES.md` (hardening log, requested).

## Files not to touch

`render.yaml` (except possibly one flag value, see question 2),
`index.html`/`landing.*` (see out of scope), all document routes,
owner/admin consoles, `/auth/team-setup`.

## Team isolation & roles

- New routes `/auth/signup`, `/auth/complete-signup`, `/auth/link-status`
  are **public by necessity** (the caller has no session). They are marked
  with an explicit comment in place of `@require_role`, exactly like the
  existing `/auth/login` and `/auth/forgot-password`. They read and write
  only `signup_requests`, `users`, and `teams`. No document queries.
- A new user is always placed in a **brand-new** team created from the
  link's own stored data. `team_id` is never taken from the request, so
  signup can't join an existing firm. Joining a coworker stays the
  admin-only `/team/members` flow.
- `session_version` tightens every existing authenticated route
  (revocation), with no scoping change.

## Feature flag

`SELF_SERVE_SIGNUP_ENABLED`, default **off** (rule 14). Off means
`/auth/signup` and `/auth/complete-signup` return 404 and the "Get started"
link is hidden. Forgot-password, keep-me-signed-in, and session revocation
are improvements to existing flows and ship unflagged. See question 2.

## Verification

- `test_auth_flow.py`, Anthropic not involved, SMTP mocked: signup creates no
  account; signup twice resends and kills the old link; existing email gets
  the "already have an account" mail with an identical response; complete
  signup creates team + admin + logged-in session; team-name collision;
  expired (72h) / used / tampered / unknown / reset-token-used-as-signup
  links; double-submit race; password rules enforced server-side; forgot
  always-same message; reset expired (1h) / used / tampered; reset kills old
  cookie and old bearer token but not the new one; remember on/off cookie
  attributes; rate limits per IP and per email on signup, login, and reset;
  flag off returns 404; new team inherits default quotas.
- Full suite via `run_all_tests.py`.
- **Real email, local:** run the API locally with `backend/.env`'s existing
  `EMAIL_USER`/`EMAIL_APP_PASSWORD` and sign up and reset to the Gmail
  address in question 3. I can confirm the send succeeded, but **I can't
  open your inbox**, so rendering in Gmail stays "unverified" until you look.
  I'll also save each email's HTML and screenshot it headlessly.
- **Screenshots** (headless, `.claude/tools/screenshots.mjs` / `ui-checker`)
  at 1440 / 768 / 375 plus a 390 WebKit (Safari engine) pass: get-started,
  check-inbox, finish-setup (empty, rules partly met, error), link-expired,
  login, forgot, forgot-sent, reset, plus the emails. I'll open and look at
  each one.
- reviewer + security-auditor (auth routes).

## Out of scope

Landing-page nav/hero "Get started" button (a one-line follow-up once the
flag is on; the landing page is under other branches). Email verification
for existing users, 2FA, OAuth/Google sign-in, Redis-backed shared rate
limits (in-process like the rest of the app), invite-a-coworker by email,
change-password revoking sessions (easy follow-up; not asked).

## Open questions (need your answer before I build)

1. **The "SameSite=Lax cookie" won't work on our current setup.** The site
   and API live on different domains (`getabstractly.com` →
   `abstractly-api.onrender.com`; tester is `abstractly-tester.onrender.com`
   → `abstractly-tester-api.onrender.com`, and `onrender.com` counts as
   separate sites per subdomain). Browsers don't send a Lax cookie on those
   calls, and iPhone Safari blocks cross-site cookies entirely. That's why
   the app already uses a bearer token, not the cookie.
   **Recommendation:** keep the token. "Keep me signed in" checked = a
   30-day token in `localStorage`; unchecked = a short token in
   `sessionStorage` (gone when the tab or browser closes). Revocation via
   `session_version` makes reset sign-outs real. I'd still set the cookie
   to `Secure; HttpOnly` with 30-day vs session lifetime for the admin
   consoles. The fully-cookie version needs the API on
   `api.getabstractly.com` (a DNS + Render custom-domain change), which can
   be a later task.
2. **Signup flag on tester?** Self-serve signup lets anyone on the internet
   create a team (within default quotas: 200 docs / $50 a month). OK to
   ship it **off by default** and turn it **on for `abstractly-tester-api`
   only** (one `render.yaml` value, takes effect after merge)?
3. **Real-email test recipient:** the Gmail on your Claude account,
   `timmypisano24@gmail.com`? Sent from `EMAIL_USER` in your local
   `backend/.env`. It's about 6–10 test emails.

Once approved, I build, push, and then run the overnight hardening rounds
you described (double clicks, back button, expired sessions, WebKit/mobile,
slow SMTP, signing up twice). I'll push after each round and keep a log in
`AUTH_NOTES.md`. I never merge.
