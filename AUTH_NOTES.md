# AUTH_NOTES — auth-flow / auth-hardening log

## Summary (kept current — read this first)

**State:** `feature/auth-flow` merged to `main` as `77e25f0` and deployed (rounds 1–3).
Hardening continues on **`feature/auth-hardening`** (rounds 4+), pushed after each round and
never merged. Plan: `docs/plans/feature-auth-hardening.md`.

**Latest round:** 6. Links pasted with trailing junk (".", ")", a wrapped-line space,
tracking params) still work; the password-manager username field is visible to Safari; an
email scanner that opens a link can't use it up. The browser checks now live in the repo:
`.claude/tools/auth-e2e/` (README there). Reviewer on rounds 4–5: **MERGE**; its follow-ups
are done in round 6.

**Deploy state (2026-10-05):** the auth-flow merge reached prod `abstractly-api`, but **the
tester and demo APIs did not redeploy** while their static sites did. Tester's new
reset/finish pages call `POST /auth/link-status`, which the old tester API doesn't have, so
**password reset on tester is broken until a Manual Deploy of `abstractly-tester-api` (and
`abstractly-demo-api`) in Render.**

**What a person gets**
- **Get started** (`/app/signup.html`): name, work email, company. They get an email from
  Tim, "Finish setting up your Abstractly account" (72-hour, single-use link). The link
  opens **Choose a password**, which shows the rules live and has a show/hide toggle.
  Submitting creates their team and admin user, and they land in the dashboard signed in.
  No account exists until the link is used. Signing up again sends a fresh link and kills
  the old one. If the email already has an account, they get a "you already have an
  account" email instead, and the page looks identical either way.
- **Forgot password?** always says "If an account exists for that email, we just sent a
  reset link." The 1-hour link opens **Choose a new password**. Saving it signs them in and
  signs out every other session. A "your password was changed" notice follows.
- **Dead links** (expired, used, replaced by a newer one, or mangled) show a friendly page
  *before* any password is typed. It offers **Send me a new link**, which re-sends to the
  same address without retyping it.
- **Keep me signed in** (on login, finish-setup, reset; checked by default): 30 days if
  checked, otherwise the login ends when the browser closes (12-hour cap).
- **Sign out** in the app sidebar (there was none before). It signs out every open tab.
- **Admin and owner consoles now work in Safari** (they were cookie-only, and the admin
  dashboard was broken in every browser). See round 3.

**Switches:** `SELF_SERVE_SIGNUP_ENABLED` (default off; on for `abstractly-tester-api` in
`render.yaml`). With it off, the signup routes 404 and "Get started" is hidden.

**Verified (by me, this session)**
- `python backend/tests/run_all_tests.py`: **83/83 files** (after round 2). New
  `test_auth_flow.py`: 45 tests. Every bug-fix test was checked to FAIL on the code before
  its fix.
- Headless E2E (`scratchpad/e2e.mjs`, 41 checks each): Chromium desktop 1440, Chromium
  tablet 768, Chromium Android (Pixel 5), WebKit iPhone 13, WebKit desktop. All **41/41**.
  Round-2 script (`round2.mjs`, 6 checks): Chromium and WebKit, both **6/6**.
- Real email: 4 messages sent from the local API via Gmail SMTP to
  timmypisano24@gmail.com; Gmail accepted all 4 (`REAL SEND ... -> ok`).

**Not verified / needs you**
- How the 4 emails look *in Gmail*, and whether they hit spam. I can only see that SMTP
  accepted them. The links in them point at `localhost:8731` and won't open on your phone.
- Real iOS Safari / Android Chrome on a device. Tested with Playwright's WebKit and
  Chromium engines, which are close but not identical.
- Render: that `RENDER=true` is set and `X-Forwarded-For` has exactly one proxy hop (the
  per-IP rate-limit fix depends on it).
- **Tester needs `EMAIL_USER`/`EMAIL_APP_PASSWORD` set in the Render dashboard**, or signup
  and reset emails silently never send there.
- **Tester has no disk.** A restart or the 15-min idle spindown wipes the DB, including
  pending signup links and new accounts.

## Known gaps (accepted for now)

- **Safari caps "keep me signed in" at 7 days of not visiting.** Safari deletes storage written
  by page scripts on sites you haven't used in 7 days (ITP), and the 30-day token lives in
  localStorage. Someone who signs in every few days stays signed in; after a week away they
  sign in again. The real fix is the same-site API (`api.getabstractly.com` + an HttpOnly
  cookie) described in the plan's question 1; it's a DNS + Render task, not done here.

- **Sign out can't revoke a copied 30-day token.** The token is stateless. Sign-out clears it
  from this browser and every open tab, and a password change or reset kills every token. But
  a token copied off the machine before sign-out keeps working until it expires. A per-device
  token list would fix this; it's not built.
- **Per-IP limits on Render depend on the proxy hop count** (`TRUSTED_PROXY_HOPS`, default 1
  when `RENDER=true`). If Render puts two proxies in front, everyone behind one edge shares a
  bucket (a nuisance, not an exploit; spoofing is blocked either way). To verify on the
  tester, log `request.remote_addr` from two networks.
- **Team farming / spend:** every confirmed inbox gets a team with default quotas. Bounded by
  per-IP/per-email limits and the flag (tester only). Add an approval step or a global daily
  cap before public launch.
- **Delayed email + "send it again":** if the first email is slow and they resend, the
  late-arriving email holds the *old* (now dead) link. Its page says "There's a newer link"
  and offers a resend. This follows the spec ("die once a newer one is sent").
- **Small timing difference** on signup/forgot for existing accounts (a DB write happens
  before the response; the email send doesn't). Rate limits make it hard to measure.
- **Signing in without "Keep me signed in" replaces a remembered login in other tabs of the
  same browser**, even for the same person: those tabs go to "You're signed out". Intended
  (one browser holds one login), but it can surprise.
- Admin-created members' passwords (typed by an admin) still use the old 8-character
  minimum. Self-chosen passwords (signup, reset, change, team-setup) use the full rules.

## Design decisions worth knowing

| Decision | Why |
|---|---|
| Bearer token, not a SameSite=Lax cookie, for "keep me signed in" | Site and API are different sites (`getabstractly.com` → `abstractly-api.onrender.com`; `*.onrender.com` subdomains are separate sites). Browsers don't send Lax cookies there, and Safari blocks them outright. Approved by user 2026-10-05. The cookie is still set (HttpOnly, Secure; 30-day vs browser-session) for admin/owner. |
| `users.session_version` | Tokens and cookies are stateless, so there was no way to "sign out everywhere". Bumping the version kills every older credential on its next request. |
| Superseded links are *revoked*, not deleted | So the page can say "there's a newer link" instead of "invalid". |
| `POST /auth/link-status` (read-only pre-check) | An earlier comment rejected it as a guessing oracle. It isn't one: 256-bit tokens, and anyone holding a live link can just use it. POST, so the token stays out of access logs. It returns the email **only for a still-valid link** (so password managers save the right username). |
| Every password change signs out everywhere | `update_user_password` bumps `session_version`. The person changing their own password gets fresh credentials in the same response. |
| NIST-style password rules | At least 10 chars, not common, not your email/name, at most 72 bytes. No "must contain a symbol". The server is authoritative; JS mirrors it and a test keeps the lists identical. |
| Company name taken → "Acme (2)" | `teams.name` is UNIQUE. "Legacy" is reserved (code looks that team up by name). |
| Untrusted signup name in email | Whoever fills the form picks the name, and the email comes from Tim. Anything that isn't plainly a first name becomes "Hi there". Company never appears in the email. |

## Round log

### Round 1 — 2026-10-05 (build + first hardening pass)

Built backend, pages, emails, tests. Then ran the E2E across 4 browser/size combos.

Bugs found and fixed (each has a test):
1. **Per-IP rate limits were one global bucket on Render.** `request.remote_addr` was the
   proxy's IP, so 20 failed logins from anyone locked out everyone. Fix: `ProxyFix(x_for=1)`
   when `RENDER=true` (`TRUSTED_PROXY_HOPS` override). Test:
   `test_proxy_fix_uses_the_real_client_ip_and_cannot_be_spoofed`.
2. **Passwords over 72 bytes caused a 500** on change-password, team-member create/reset,
   owner reset, team-setup (bcrypt raises). Fix: a 400 with a clear message; login treats an
   overlong password as simply wrong (same timing). Test: `test_overlong_passwords_are_400_not_500`.
3. **No way to revoke a session.** A reset used to leave the old password-holder logged in
   for up to 12 hours. Fix: `session_version`. Test:
   `test_reset_logs_in_and_signs_out_every_other_session`.
4. **Old reset email could undo a newer password.** Any password change now revokes
   outstanding reset links. Test: `test_any_password_change_kills_outstanding_reset_links`.
5. **Second tab without "keep me signed in" bounced to login** (found by E2E). The token was
   per-tab and the cross-site cookie is blocked. Fix: new tabs ask open tabs over a
   same-origin `BroadcastChannel`; sign-out is broadcast too. E2E check:
   "unchecked remember: second tab stays signed in".
6. **iOS zoom on login.** The old inputs were 14px, so Safari zoomed in on focus. All auth
   inputs are now 16px (E2E checks it on every page).
7. **The app had no sign-out at all.** That matters once logins can last 30 days. Added to
   the sidebar.

Checked and fine: double-clicks (exactly one email / one account / one reset), two tabs on
the same link (the second gets "You're already set up" + "Go to your dashboard"), the back
button after signup (doesn't return to the password form), reopening a used link,
tampered link, expired link + one-click resend, superseded link, logging in during a pending
reset (the reset still works afterwards and signs that login out), the other device signed
out after a reset with a "session ended" notice, no horizontal scroll at 375/390/768/1440.

Observed, not this branch: on phones the dashboard has inner panels (lease filter row,
recent activity) that scroll sideways inside their cards. It's identical on `main`; the page
itself is 390px wide on both.

### Round 2 — 2026-10-05 (review findings + more edge cases)

Sources: the `reviewer` (FIX FIRST) and `security-auditor` (no critical/high) on `1ae353b`,
plus new headless checks (`round2.mjs`). Each fix has a regression test, verified to fail on
the old code.

1. **A stale token signed you in as a different person** after a DB wipe. User ids restart
   (tester has no disk), so an old 30-day token for user #1 became the *new* user #1, possibly
   another firm's admin. Fix: credentials carry the email they were issued for, and
   `_live_user` rejects a mismatch (cookie and token). Test:
   `test_stale_credential_from_a_wiped_database_is_rejected` (old code: "old token signed in as
   bob@second.test").
2. **Link tokens ended up in the access log** (auditor, medium): link-status was a GET with
   `?token=`. Now a POST with the token in the body. Test:
   `test_link_tokens_never_travel_in_a_url_to_the_api`.
3. **A forgot-password link worked at `/auth/team-setup` for 7 days** (auditor, medium;
   pre-existing on main). `password_reset_tokens.purpose` ('reset' / 'setup'); each route
   accepts only its own. Test: `test_reset_and_setup_tokens_are_not_interchangeable`.
4. **Only the emailed reset signed other sessions out** (both reviewers, medium).
   Change-password, admin reset and owner reset left a stolen token alive. Now any password
   change bumps `session_version`; change-password re-issues the caller's own credentials and
   keeps their "keep me signed in" choice. Test:
   `test_change_password_signs_out_other_sessions_but_keeps_the_caller`.
5. **+tag aliases multiplied the per-email limits** (auditor, low). Limiter keys ignore `+tag`
   (and dots at Gmail). Test: `test_plus_and_dot_aliases_share_one_email_budget`.
6. **Old 12-hour cookies would have slid to 30 days** (reviewer, low). A permanent cookie
   with no `exp` (issued before this deploy) now has to sign in once more. Test:
   `test_pre_deploy_permanent_cookie_without_exp_must_sign_in_again`.
7. **Every wrong-method request was a 500** (found while fixing 2; app-wide, pre-existing):
   the catch-all `Exception` handler swallowed Flask's own 405. HTTP errors now keep their
   status. Test: `test_wrong_http_method_is_405_not_500`.
8. **Back button after signing out showed the dashboard** from the back/forward cache. A
   restored app page now hides itself and re-checks the session. E2E: "back after sign out
   does not show the dashboard" (Chromium + WebKit).
9. **"Forgot password?" before finishing signup sent nothing** (there's no account yet). It
   now re-sends the setup link; the response is identical either way. Test:
   `test_forgot_password_before_finishing_signup_resends_the_setup_link`.
10. Change-password and team-setup now use the same password rules as signup/reset;
    `TRUSTED_PROXY_HOPS` with a junk value no longer crashes startup.

Checked and fine: slow email (server delaying each send by 10s) leaves the signup page instant
(66ms Chromium, 851ms WebKit) because mail goes out in the background; a session revoked
mid-use (reset elsewhere) lands on login with "Your session ended"; a rate-limited login says
"Too many sign-in attempts"; with the server unreachable, every page says "Couldn't reach the
server" and the button works again (no endless spinner).

### Round 3 — 2026-10-05 (staff consoles, review notes)

1. **The admin dashboard was broken in every browser** (pre-existing on `main`, reproduced
   against `origin/main`'s frontend). `admin/dashboard.html` reuses the app's `api.js`, which
   authenticates with a bearer token, but admin sign-in only set a cookie. Every call
   returned 401, and `api.js` then sent people to `admin/login.html`, which doesn't exist (a 404).
   Fix: admin sign-in keeps the token (per tab); `api.js` sends admin pages to `admin/index.html`.
2. **Admin and owner consoles never worked in Safari.** They were cookie-only, and the
   cookie is cross-site, which Safari blocks. Both now also send the bearer token; sign-out
   clears it.
   Checked headless: admin → dashboard and owner → Teams load in Chromium **and** WebKit
   (before: WebKit stayed on the login page for both, Chromium admin hit the 404).
   Test: `test_staff_consoles_send_a_bearer_token`.
3. Review note: the catch-all error handler returns redirects (3xx) as-is, keeping `Location`.
   Test: `test_catch_all_handler_keeps_redirects_as_redirects`.
4. Review note: a password change no longer counts as a "login" for the daily briefing.
   Test: `test_change_password_is_not_counted_as_a_login`.

After the round: suite 83/83; E2E 41/41 (Chromium desktop, WebKit iPhone); round-2 checks 6/6.

### Round 4 — 2026-10-05 (feature/auth-hardening)

New headless script `round4.mjs` (16 checks): Chromium **16/16**, WebKit **15/16** (the one
miss is noise from the app dashboard, not auth; see below). Suite **83/83**. Round-1 E2E still
**41/41** (Chromium desktop, WebKit iPhone).

Fixed:
1. **Two people, one browser.** With "Keep me signed in", every tab shares one token. When
   B signed in, A's open tab silently made requests *as B* while still showing A's name and
   data. Now an app tab watches the shared token: if it changes hands, the tab reloads into
   the new person; if it's cleared, the tab goes to "You're signed out". And sign-in now
   overwrites the token in one step instead of clear-then-set (the momentary "empty" made
   other tabs think they'd been signed out). Tests:
   `test_signing_in_never_momentarily_empties_the_shared_token` + E2E "two people, one
   browser".
2. **Signup while already signed in** says "You're signed in as … Go to your dashboard"
   (signing up for another firm is still allowed).
3. **Phone keyboards**: every auth input has `enterkeyhint` (Next / Go / Send / Done). Test:
   `test_auth_inputs_tell_phone_keyboards_what_enter_does`.

Checked and fine (no change needed): a link that expires while the form is open → "This
link has expired" on submit; a link superseded from another tab while open → "There's a
newer link"; Back from "Check your inbox" → a usable login form; Forward → the forgot page
is not frozen; Back after a successful reset never shows the password form; double-click
"send it again" and "Send me a new link" each send one email; Enter pressed 3× on login →
one sign-in; two signups at once for the same email → exactly one live link; 200% text in
landscape and portrait → no sideways scroll.

Observed, not auth: after signing in, leaving the dashboard immediately makes WebKit log its
in-flight background requests (`/alerts/summary`, `/today`, `/activity`) as "access control
checks" errors when they're cancelled. Harmless, existing app code.

### Round 5 — 2026-10-05 (feature/auth-hardening)

New headless script `round5.mjs` (7 checks): Chromium **7/7**, WebKit **7/7**. Suite **83/83**.
Round-1 E2E still **41/41** (Chromium desktop, WebKit iPhone).

1. **Return to where you were.** A session that ends mid-use (expired, or signed out by a
   reset elsewhere) used to land you on the dashboard after signing back in. Now `api.js`
   passes the current screen's name (`?next=tasks`), and sign-in returns there. Only a plain
   `[a-z0-9-]` view name is accepted (checked on both ends), so it can't be turned into an
   off-site redirect. E2E: back on `#alerts` after re-login, and `?next=https://evil.example/x`
   ignored. Test: `test_return_to_screen_only_accepts_a_plain_view_name`.
2. **Logging in during a reset, two devices, UI only** (no change needed): phone opens the
   reset link; the laptop signs in with the old password (works); the phone saves the new
   password (works, signed in); the laptop's next click lands on "Your session ended".

Test upkeep: round 4's static finishLogin test now finds the function body without relying
on its exact signature (still verified to catch the original clear-then-set bug).

### Round 6 — 2026-10-05 (feature/auth-hardening)

`round6.mjs` (7 checks): WebKit iPhone **7/7**, Chromium **7/7**. Suite **83/83**.

1. **Links pasted with trailing junk.** Copying a link out of a sentence often adds "." or ")",
   a `%20` from a wrapped line, or a tracking `&utm_…`. These read as "This link doesn't
   work". The page now keeps the leading token-shaped run (tokens are 43 chars of
   `[A-Za-z0-9_-]`). E2E: all four variants open the form.
2. **Password managers on iPhone.** The username field that tells Keychain which account the
   new password belongs to used `hidden` (display:none), which Safari may skip. It's now
   present but visually hidden. Test:
   `test_password_pages_keep_a_username_field_password_managers_can_see`.
3. Checked and fine: **an email security scanner that pre-opens a link does not burn it.**
   Opening a link only *checks* it; only submitting the form uses it.

Review follow-ups (rounds 4–5 reviewer, verdict MERGE):
- Return-to-screen skips screens that need a lease or deal already picked (`detail`,
  `report`, `timeline`, `comparison`); those return to the dashboard instead of an empty
  screen.
- **The headless browser scripts are now in the repo**: `.claude/tools/auth-e2e/`
  (`run-local.sh`, `flows.mjs` 41 checks, `round2/4/5/6.mjs`, README). All rerun from there:
  flows 41/41 (Chromium desktop, WebKit iPhone), round2 6/6, round4 16/16 both engines,
  round5 7/7, round6 7/7. Round 4's error check now explicitly ignores WebKit's
  cancelled-dashboard-fetch noise.
- Commented the tiny boot window in which the two-tab listener isn't active yet.
- Screenshots looked at for this branch: signup "You're signed in as…" notice and 200% text
  (landscape/portrait), WebKit + Chromium, in `$AUTH_E2E_DIR/shots/r4-*`.
