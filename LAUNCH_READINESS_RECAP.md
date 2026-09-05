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

## Task 3 — OCR diagnostics

**The diagnostic question first, since it determines everything else:**
Coastal Brew Coffee Co. and Northbridge Analytics' missing Landlord/date
fields were **neither a text-layer problem nor a parsing miss**. I
pulled every lease in the demo dataset directly from the live API and
found each property actually has **two separate lease records** sharing
the same display name: the real PDF-derived lease (fully populated,
high confidence on every field) and a **rent-roll-derived duplicate**
(`q1_2026_rent_roll.csv`) that never had those fields to begin with —
a real rent roll spreadsheet genuinely never states landlord name or
lease dates, only tenant/rent/address/sqft. The "missing data" was
someone looking at the rent-roll entry and mistaking it for the same
record as the fully-populated PDF one, because they share a display
name. Nothing to fix in extraction for these two specifically — I did
also find and fix a real, unrelated bug while investigating (both
records were further duplicated 2x each, 8 total instead of 4, from a
gunicorn multi-worker seeding race — see the housekeeping note at the
top of this file) and cleaned up the live duplicates.

**The actual pipeline feature** (separate from the above, and a real
gap in the general extraction pipeline, not specific to the demo data):
added a document-quality check that runs after text extraction and
before any field extraction, in `document_extractor.find_low_text_pages()`.
Flags any page under ~50 characters of text, or whose text is mostly
non-alphanumeric symbols (garbled OCR), as unusable.

This catches something the existing OCR fallback in `pdf_extractor.py`
can't: that fallback decides whether to run OCR at all based on the
**whole document's total** text length, so a hybrid PDF — several
genuinely digital pages plus one embedded scanned page (a photocopied
signature page, a scanned exhibit) — never triggers OCR at all if the
digital pages alone clear the threshold, silently leaving that one page
blank forever. Verified this exact scenario with a real generated PDF
(good page 1, blank page 2, total text comfortably over the
whole-document OCR threshold) — confirmed the page was previously
silently skipped, and is now correctly flagged.

When flagged, the whole document is persisted as one lease with
`processing_status: "ocr_needed"`, `processing_error` naming exactly
which page(s) and why, and every field left honestly null — no
per-field extraction runs at all, so it can never be confused with the
source genuinely not stating a field. Surfaced in both the upload
result screen and the lease detail page as a clear banner instead of
the previous "not a lease" framing (which would have been actively
misleading here — extraction never ran, so "no tenant/landlord/rent
found" isn't the right message).

**Verified:** end-to-end through the real upload API (a lease with a
blank page correctly comes back `ocr_needed` with the right page named,
placeholder fields, and `looks_like_lease: true` so it isn't
double-flagged as "not a lease" on top of "unreadable"); full test
suite still 63/64 (only the pre-existing, environment-only failure —
`tesseract` isn't installed on this dev machine, unrelated to this
change and confirmed by reading its actual traceback, not assumed).

**Not fixed / out of scope:** the deeper structural fix (running OCR
per-page instead of only on a whole-document total) would close the gap
at the source rather than just flagging it after the fact. Didn't build
that — it's a larger change to `pdf_extractor.py`'s core OCR-fallback
decision, and the detection layer above already gets you the visibility
this task asked for without changing the OCR strategy itself.

---

## Task 4 — Confidence transparency

This was already done earlier today, before this task list — restating
here for the record since it's exactly what this task asked for.

Every extracted field already stores `source.quote` (the exact
sentence/table cell it was pulled from, with page number or rent-roll
row+file), and now also `validation_note` — a one-line reason,
populated whenever confidence is medium or low, e.g. "Landlord name
inferred from a signature block -- appeared above a standalone
'LANDLORD' caption rather than an explicit label" or "Date found
further from the commencement keyword than a direct statement usually
appears." High-confidence fields don't get a note — nothing to
caveat.

Also added `document: {lease_id, filename}` on every field — which
document (base lease, or whichever amendment most recently overrode
it) actually produced that value, since a lease with amendments has
more than one document that could have stated a given field. Verified
live: uploaded a base lease + an amendment that only overrides
rent_amount, confirmed via the real API response that landlord still
attributes to the base document while rent_amount attributes to the
amendment.

All of this flows into the API response automatically (the lease
detail/list endpoints already pass `extracted_fields` through
verbatim) — no separate API change was needed. Frontend already
displays `validation_note` inline on each field's card (a pre-existing
mechanism I found was populated inconsistently, not one I had to
build), and now shows "(from filename.pdf)" next to a field's citation
when its value came from a different document than the one being
viewed.

---

## Task 5 — Test coverage check

**Pass rate:** 63/64 test files passing (backend, non-live suite —
`tests/run_all_tests.py`). The one failure (`test_document_extractor.py`)
is environment-only, not a real bug: `tesseract` isn't installed on
this dev machine, so its one OCR-image test fails on `TesseractNotFoundError`
before it ever reaches the code under test (confirmed by reading the
actual traceback, not assumed) — this would pass on the real deployed
container, which does have tesseract installed per the Dockerfile.
There's also a separate `--live` suite (18 more files) that requires an
actual running server on localhost and is skipped by default — not run
here since nothing was standing up a live local server during this
session.

**82 test files total** is a genuinely large backend suite covering
auth (`test_admin_auth`, `test_password_reset`, `test_route_authorization`,
`test_security_hardening`/`_middleware`), upload (`test_upload_validation`,
`test_document_extractor`, `test_multi_lease_detection`, `test_table_upload_extraction`),
extraction (`test_extraction`, `test_extraction_quality/scoring`,
`test_confidence_validation`, `test_ocr_fallback`, `test_synthetic_accuracy`,
`test_ai_extraction`), and dashboard-adjacent backend logic
(`test_dashboard_features`, `test_portfolio*`, `test_alerts`,
`test_discrepancies`). This part of the app is well tested.

**The gap — and it's a big one:** there is **zero automated test
coverage for any frontend JavaScript**, in any of the three bundles
(`app/`, `admin/`, `owner/`). No `package.json`, no test runner (Jest/
Vitest/anything), no `*.test.js`/`*.spec.js` files anywhere in the repo.
`test_access_gate.py` sounds like it covers `access-gate.js` but
actually only tests the *backend* endpoints that file happens to call
(`/config`, `/waitlist/check`) via Flask's test client — none of the
actual JavaScript (rendering logic, the session-redirect and
script-load-error handling I added in Task 2, the OCR-needed banner
from Task 3, any dashboard widget) is exercised by anything automated.
Every frontend fix in this session's work was verified by hand (live
API calls, a real uploaded PDF, manual DOM/logic reasoning) — real
verification, but not a regression test that protects it going
forward.

**Other specific gaps found:**
- `demo_seed.py` (seeding, the reset lock fix, `/demo/reset`) has zero
  test coverage — everything I verified there this session was a
  manual/live check, not an automated test. Given it only runs on the
  demo deployment, lower stakes than a production-path gap, but worth
  knowing.
- The two brand-new pieces from today — `find_low_text_pages()`
  (Task 3) and the `document`/`validation_note` field attribution
  (Task 4) — aren't in the automated suite yet either; both were
  verified live/manually in this session, same caveat as above.

**Not done (per your instructions — inventory only, not new tests):**
I didn't write any new tests. If you want to close the biggest gap
first, standing up even a minimal frontend test runner (Vitest is the
lowest-friction choice for plain `<script>`-tag JS like this) and
covering just the session-redirect/error-banner logic from Task 2 would
be the highest-leverage starting point, since that's the code with the
least existing safety net and the most user-facing blast radius if it
breaks.

---
