# AUTH_NOTES — feature/auth-flow hardening log

## Summary (kept current — read this first)

**State:** built, tested, pushed. Not merged (never merge from this branch's session).
Plan: `docs/plans/feature-auth-flow.md`.

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

**Switches:** `SELF_SERVE_SIGNUP_ENABLED` (default off; on for `abstractly-tester-api` in
`render.yaml`). With it off, the signup routes 404 and "Get started" is hidden.

**Verified (by me, this session)**
- `python backend/tests/run_all_tests.py`: **83/83 files** (round 1). New
  `test_auth_flow.py`: 34 tests.
- Headless E2E (`scratchpad/e2e.mjs`, 41 checks each): Chromium desktop 1440, Chromium
  tablet 768, Chromium Android (Pixel 5), WebKit iPhone 13. All **41/41**.
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

## Design decisions worth knowing

| Decision | Why |
|---|---|
| Bearer token, not a SameSite=Lax cookie, for "keep me signed in" | Site and API are different sites (`getabstractly.com` → `abstractly-api.onrender.com`; `*.onrender.com` subdomains are separate sites). Browsers don't send Lax cookies there, and Safari blocks them outright. Approved by user 2026-10-05. The cookie is still set (HttpOnly, Secure; 30-day vs browser-session) for admin/owner. |
| `users.session_version` | Tokens and cookies are stateless, so there was no way to "sign out everywhere". Bumping the version kills every older credential on its next request. |
| Superseded links are *revoked*, not deleted | So the page can say "there's a newer link" instead of "invalid". |
| `GET /auth/link-status` (read-only pre-check) | An earlier comment rejected it as a guessing oracle. It isn't one: 256-bit tokens, and anyone holding a live link can just use it. It returns the email **only for a still-valid link** (so password managers save the right username). |
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
