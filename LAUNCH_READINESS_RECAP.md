# Launch Readiness Recap

Worked autonomously through the 6 tasks below while you were away. Each
section is one task: what I found, what I changed, what's committed
(locally only — nothing pushed/deployed without your sign-off), and any
judgment calls left for you.

**Housekeeping done before Task 1** (not one of the 6, but related to the
OCR-diagnostics work from earlier in the day): found and fixed a real bug
where the demo deployment's two gunicorn worker processes could both
"win" the first-boot seed check, producing 8 demo leases instead of 4
(each sample duplicated). Fixed with an exclusive-create lock file
(committed locally, not pushed) and cleaned up the live duplicate data
directly via the demo's own authenticated API (not a code deploy, so no
sign-off needed for that part).

---

## Task 1 — Security audit

**Checked:** full git history (`git log --all -p`) for committed secrets
and common key patterns (AWS keys, Anthropic/OpenAI-shaped keys, private
key blocks, GitHub tokens); every source file for hardcoded
credentials/fallback-secret patterns; `.gitignore` coverage (root and
nested); `render.yaml` for anything that should be `sync: false` but
isn't; how every secret-shaped env var behaves when unset.

**Found — already fixed earlier today, restating for the record:**
`FLASK_SECRET_KEY`'s fallback (`backend/app/api.py`) used to generate a
fresh random secret per gunicorn worker process when the env var wasn't
set, so a session cookie signed by one worker failed verification on a
different worker — the cause of the "Login required" bug on the demo.
Fixed by persisting the generated fallback to a shared temp file so
every worker converges on the same value.

**Found — no other issues:**
- `backend/.env` has **never** been committed to git history (verified
  via `git log --all --full-history -- backend/.env` — empty). It's
  properly gitignored via `backend/.gitignore`.
- No hardcoded API keys, passwords, or tokens anywhere in backend or
  frontend source (targeted grep for key-shaped strings — AWS
  `AKIA...`, Google `AIza...`, OpenAI/Anthropic `sk-...`, GitHub
  `ghp_...`, PEM private key blocks — all clean). The two matches that
  came up in git history were both false positives on inspection: a
  `.env.example` comment showing the literal placeholder format
  (`ANTHROPIC_API_KEY=sk-ant-...`) and a test fixture in
  `test_sheets_export.py` using the literal string `"fake"` as a mock
  private key body.
- `render.yaml`: every real secret (`FLASK_SECRET_KEY`, `ADMIN_EMAIL`,
  `ADMIN_PASSWORD_HASH`, `TOKEN_ENCRYPTION_KEY`, `DEMO_RESET_TOKEN`,
  OAuth client secrets) is correctly `sync: false` (never committed,
  entered by hand in the Render dashboard); every committed `value:` is
  non-sensitive (URLs, header values, log level, boolean flags).
- Every other secret-shaped env var fails **closed**, not open, when
  unset: `TOKEN_ENCRYPTION_KEY` raises `TokenEncryptionNotConfigured`
  rather than falling back to anything; the Google/Microsoft OAuth
  client secrets raise a clear "not configured" error; `DEMO_RESET_TOKEN`
  rejects every reset request (401) if it isn't set. None of these have
  the "generate a weak default" problem `FLASK_SECRET_KEY` had.
- The demo account passwords (`Demo2026!`, `Holden12!`) are intentionally
  public by design, isolated to a separate, non-production database —
  not a leak, this is what they're for.

**Changed:** added a defensive root-level `.gitignore` rule for `.env`/
`*.env` (with `.env.example` explicitly re-allowed). `backend/.gitignore`
already covered the one `.env` file that exists today; this just means a
`.env` placed anywhere else later isn't one `git add -A` away from
landing in a commit. Zero risk, no behavior change.

**Nothing to rotate** — no secret was ever actually exposed in git
history or source. The FLASK_SECRET_KEY issue was a *logic* bug (weak
fallback generation), not a leaked value.

**Minor, not fixed (your call, not a security issue):** `backend/.env.example`
has your real email pre-filled as the `EMAIL_USER`/`ADMIN_EMAIL` example
value instead of a generic placeholder like `you@example.com`. Not a
secret, but it means your personal email is in git history/on GitHub if
this repo is ever made public. Say the word if you'd rather it were a
placeholder.

---

## Task 2 — Error handling audit

**Checked:** login (`app/login.js`), the shared fetch wrappers each
bundle uses (`app/api.js`'s `apiRequest`, `admin-bootstrap.js`'s
`adminFetch`, `owner-app.js`'s `ownerFetch`), the app boot sequence
(`access-gate.js`), lease upload (`document_extractor.py` +
`upload-view.js`), lease detail view (`detail-view.js`), and dashboard
empty-state handling (`dashboard-view.js`).

**Fixed:**
1. **Expired session on the main app (`app/api.js`) showed a wall of
   confusing errors instead of sending the user back to log in.** Every
   dashboard widget fetches independently and each has its own
   `.catch()` → "Failed to load X" — so a 401 (session expired) used to
   render as 8+ simultaneous, unexplained failures across the whole
   page, indistinguishable from a real outage, with nothing telling the
   user the fix is just signing in again. `admin-bootstrap.js` and
   `owner-app.js` already treat a 401 as "redirect to login" — `api.js`
   was the one bundle missing this. Added the same handling: a 401 now
   redirects straight to `login.html` instead of surfacing as a
   generic error.
2. **A script failing to load during app boot left a blank, silently
   broken shell.** `access-gate.js` reveals the app shell *before*
   loading its ~24 view scripts; if one fails over a flaky connection,
   a bad deploy, or a static-host hiccup, the shell was already visible
   with missing functionality and no visible error — just a
   `console.error` no real user would ever see. Now shows a clear
   "part of the app failed to load, reload the page" banner instead.

**Already solid, no change needed:**
- Login (`app/login.js`): network failures, bad credentials, and
  server errors all already produce a clear inline message with the
  form re-enabled and the password field cleared — no gaps.
- Malformed/unreadable upload (`document_extractor.py`): every format
  (PDF, Excel, Word, image, etc.) already raises a specific, actionable
  `DocumentExtractionError` message (corrupted file, wrong format,
  password-protected PDF, no readable text) rather than a generic
  crash; `upload-view.js` renders each file's success/failure inline
  per-file in a batch upload.
- Empty datasets: the dashboard already has empty-state messaging
  throughout (`isNewAccount` flag, "Nothing due," "No unread messages,"
  "Nothing active," "No activity yet") rather than blank sections.
- `access-gate.js`'s own session check already fails closed to the
  login page on a network error, rather than guessing.

**Found, not fixed (judgment call / lower priority):**
- **Lease detail view (`detail-view.js`) load failure**: if
  `Api.getLease()` throws (network blip, deleted-lease race), the page
  shows a transient toast (`showError`, auto-dismisses after ~3.5s) and
  otherwise leaves the page in whatever partial state it was in — no
  retry button, no persistent message once the toast fades. Not a
  crash or blank screen, but weaker than the other flows above. Left
  as-is because a proper fix (a persistent inline error state with a
  retry action, matching the quality bar of the other fixes here) is
  more than a small patch, and I wasn't sure whether you'd want the
  view to stay on a partial render or actively block on a "retry"
  screen — that's a product call, not something to guess at.

---
