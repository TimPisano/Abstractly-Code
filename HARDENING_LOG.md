# Security / Performance / Reliability Hardening — Running Log

Newest notes at the bottom of each phase. Written to be read cold.

---

## PHASE 1 — Security audit

### 1.0 Findings (ranked by real-world severity)

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **HIGH** | `/auth/login` has **no rate limiting**. Forgot-password, waitlist, and the assistant are all rate-limited; login itself is wide open to online password brute-force / credential stuffing. | fixing |
| 2 | **HIGH** | **CSRF on multipart uploads.** Session cookie is `SameSite=None` (required — frontend and API are cross-site on Render). CORS preflight protects JSON endpoints, but `multipart/form-data` is a CORS-"simple" content type → **no preflight** → a malicious page can POST a file to `/leases`, `/leases/batch`, `/leases/<id>/resubmit`, `/leases/<id>/amendments`, `/leases/import-rent-roll`, `/portfolio/t12-reconciliation` with the victim's cookie. Attacker can't read the response, but the side effects (lease created/replaced, AI spend) happen. | fixing |
| 3 | **MEDIUM** | **No security headers.** No `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`, `Cache-Control` on auth responses, or CSP. | fixing |
| 4 | **MEDIUM** | **Dependency vulns.** `Flask-Cors 4.0.0` (CVE-2024-6839/6844/6866/1681 — CORS matching & log-injection bugs; CORS is security-critical here), `Pillow 10.1.0` (CVE-2023-50447 RCE via `ImageMath`, CVE-2024-28219 buffer overflow — **Pillow parses uploaded images for OCR**). `setuptools 58.0.4` (CVE-2024-6345 RCE, CVE-2022-40897 ReDoS) and `pip 21.2.4` — not runtime attack surface but trivially old. | fixing |
| 5 | **MEDIUM** | **`PyPDF2 3.0.1` is deprecated** (renamed `pypdf`) and has known DoS/quadratic-parse behavior on crafted PDFs — and it parses every uploaded PDF. Migrating to `pypdf` is a larger change; flagged with a recommendation. | flagged |
| 6 | **LOW** | **Temp-file extension not sanitized.** `_extract_leases_from_file_storage` does `NamedTemporaryFile(suffix=f'.{ext}')` where `ext` is from the attacker-controlled filename. Currently *contained* — every caller runs `allowed_file()` first, which rejects anything but a known short extension — but there's no defense-in-depth if a future caller forgets. | fixing |
| 7 | **LOW** | `/auth/reset-password` has no rate limiting. Token is `secrets.token_urlsafe(32)` = 256-bit, so brute-force is infeasible; adding a limit anyway is cheap defense-in-depth. | fixing |
| 8 | **LOW** | Session lifetime is a fixed 12h with no idle timeout. Acceptable for this app; noted. | accepted |

### 1.1 Explicitly checked and found OK

- **SQL injection**: none. Every query in `database.py` (and all modules) uses `?` placeholders; the only f-strings in SQL interpolate hardcoded clause fragments (`"lease_id = ?"`) and `IN (...)` placeholder lists — never a user value. `ALTER TABLE … {column} {type}` in migrations uses a hardcoded dict.
- **Secrets in git history**: none. `.env` was never tracked. The real Gmail App Password, `FLASK_SECRET_KEY`, and any bcrypt hash do **not** appear in any commit (`git log --all -S` / -p scans clean). `render.yaml` uses `sync: false` for every secret. `credentials/*.json` is gitignored.
- **Password storage**: bcrypt with per-hash salt, timing-safe dummy-hash check on unknown/deactivated accounts (blocks user enumeration by timing).
- **Reset tokens**: `secrets.token_urlsafe(32)`, only the SHA-256 hash is stored, single-use, 1-hour TTL, generic 200 response regardless of account existence, email sent off the request path so response time isn't an existence oracle.
- **Forgot-password**: rate-limited per-IP and per-email, counters advance before the account lookup (so 429-vs-200 isn't an oracle).
- **`require_owner`**: returns 404 (not 403) to non-owners so `/owner/*` routes are undiscoverable.
- **Error handlers**: generic JSON, no stack traces or paths to the client; real exception logged server-side.
- **Server-side upload size limit**: `MAX_CONTENT_LENGTH = 16 MB` → 413.
- **Upload extension checks**: enforced server-side on every path (`allowed_file()` or an explicit `in ('csv','xlsx')`), not just the UI `accept=`.

### 1.2 Fixes applied

**`backend/app/security.py`** (new) — `install_security(app, allowed_origins)`, wired in `api.py` right after `CORS(...)`:
- **CSRF** (finding #2): `before_request` rejects any `POST/PUT/PATCH/DELETE` whose browser-set `Origin` (or, if absent, `Referer`) is not in the CORS allow-list → `403`. A request with neither header is a non-browser client (no ambient cookie) and is allowed — the standard header-verification approach (Django-style). Closes the multipart-upload CSRF hole that CORS preflight didn't cover. `/health` exempt.
- **Transport** (finding #3 part): HSTS (`max-age=31536000; includeSubDomains`) on every HTTPS response (detected via `request.is_secure` or `X-Forwarded-Proto`). Optional app-level HTTP→HTTPS 301 via `FORCE_HTTPS=true` (off by default — Render already redirects at its edge; on for any non-Render host).
- **Response headers** (finding #3): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cross-Origin-Opener-Policy: same-origin` on all responses. CSP: `default-src 'none'; frame-ancestors 'none'; base-uri 'none'` for JSON/file responses; a `style-src 'unsafe-inline'`-permitting variant for the one HTML route (`/portfolio/report` — self-contained, no scripts/external refs, verified). `Cache-Control: no-store` on `/auth/*` and `/owner/*`.
- **`RateLimiter`** class — in-process fixed-window, multi-key (`check(["ip:…","email:…"])` → limited if any key saturated), self-pruning. Same per-worker caveat as the existing limiters.

**`backend/app/api.py`**:
- **Login rate limiting** (finding #1): `/auth/login` now limited **20 / 5 min per IP** and **7 / 15 min per email** (email counted even for nonexistent accounts, so 429-vs-401 isn't an existence oracle) → `429`.
- **Reset-password rate limiting** (finding #7): `/auth/reset-password` limited **15 / 15 min per IP** → `429`.
- **Temp-file extension sanitized** (finding #6): `_extract_leases_from_file_storage` now strips the upload extension to `[a-z0-9]{0,10}` before using it as a `NamedTemporaryFile` suffix — a path separator or null byte in a crafted filename can never reach the temp path, regardless of caller.

**Tests** — `backend/tests/test_security_middleware.py` (14 cases, all green, test-client unit tests): CSRF blocks disallowed Origin/Referer (incl. the multipart case), allows good Origin / no-Origin / GET; all security headers present; HSTS only on HTTPS; auth responses `no-store`; login throttled per-IP and per-email with identical behavior for unknown accounts; reset-password throttled; `RateLimiter` window + multi-key + pruning.

### 1.3 Dependency upgrades (findings #4, #5)

| Package | Was | Now | Why |
|---|---|---|---|
| `flask-cors` | 4.0.0 | **6.0.5** | CVE-2024-6839 / -6844 / -6866 (CORS path-matching bugs — regex, case, trailing-slash), CVE-2024-1681 (log injection). CORS is a security boundary in this app. |
| `Pillow` | 10.1.0 | **11.3.0** | CVE-2023-50447 (arbitrary code exec via `ImageMath.eval`), CVE-2024-28219 (`_imagingcms` buffer overflow). Pillow parses every uploaded image for OCR. |
| `PyPDF2` | 3.0.1 | **`pypdf` 6.16.2** | PyPDF2 is abandoned (renamed to `pypdf`, last release 2022) and has known quadratic-parse / DoS behavior on crafted PDFs — and it parses every uploaded PDF. Migrated `app/pdf_extractor.py`, `app/document_extractor.py`, and 10 test files (drop-in: `PdfReader`/`PdfWriter`/`.pages`/`.extract_text()`/`.is_encrypted`/`.decrypt()` are identical). `PyPDF2` uninstalled. |
| `Werkzeug` | 3.1.8 (transitive) | **3.1.8 (now pinned)** | Was unpinned; pinned to the tested, current, secure version so a resolver can't silently pull an older one. |
| `pip` / `setuptools` (build) | image default | **upgraded in Dockerfile** | setuptools CVE-2024-6345 (RCE via `package_index`), CVE-2022-40897 (ReDoS). Not runtime attack surface, but the build image's bundled versions lag — `pip install --upgrade pip setuptools` added before `pip install -r requirements.txt`. |

`requirements.txt` header now documents each security-motivated pin. `pip check` clean.

### 1.4 Frontend security headers (`render.yaml`)

The API sets its own headers in `app/security.py`; the static site (HTML/JS/CSS Render serves directly) now gets a matching set via `render.yaml` `headers`: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, HSTS, and a **CSP** (`default-src 'self'; connect-src 'self' https://abstractly-api.onrender.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`). CSP derived from a full frontend audit — every script/style/font is same-origin, no inline `<script>`, no inline event handlers, no `eval`, no CDN. `style-src` keeps `'unsafe-inline'` only for the `style="display:none"` attributes in the HTML. **Needs one browser check after the next Render deploy** (the deployed frontend can't be exercised from here); if the app breaks, the `connect-src` host is the most likely culprit (must exactly match the live API origin).

### 1.5 HTTPS

Render terminates TLS at its edge and 301-redirects HTTP→HTTPS automatically for both services — HTTPS **is** enforced in production. Added: HSTS on every HTTPS response (API + static site) so browsers refuse HTTP even before hitting the redirect, and an opt-in `FORCE_HTTPS=true` app-level redirect for any non-Render deployment. Nothing to change for the current setup.

### 1.6 Not fixed this pass (flagged)

- **`.env` has `LEASE_AI_EXTRACTION=true` but the `ANTHROPIC_API_KEY` is unfunded** → every upload currently returns a clean 502 ("credit balance too low"). Not a security bug and it *does* degrade gracefully (no crash, no partial write), but it means the running app can't process any document. Recommend: fund the key, or set `LEASE_AI_EXTRACTION=false` until then. Phase 3 improves this (fall back to regex on a config/billing failure rather than hard-failing).
- **Session lifetime** is a fixed 12h, no idle timeout. Acceptable for this app's threat model; noted, not changed.

### 1.7 Verification

Full unit suite **59/60** after all Phase 1 changes (the 1 failure is the pre-existing `tesseract`-not-installed OCR test — unrelated, fails identically on the baseline). New `test_security_middleware.py` (14 cases) green. `pip check` clean. `pypdf` migration verified against every PDF-touching test.

---

## PHASE 2 — Performance

### 2.0 Findings

| Area | Finding |
|---|---|
| **Owner account list** | Real N+1: `get_user_usage_stats` opened a **new DB connection + 6 `COUNT` queries per user**. N users → N connections + 6N queries. |
| **`get_user_by_email`** (every login) | `WHERE lower(email) = lower(?)` → full scan; can't use the `UNIQUE` index. |
| **Missing indexes** | `tasks(created_by_user_id)`, `lease_field_edits(edited_by_email)`, `discrepancy_resolutions(discrepancy_id)` and `(resolved_by_email)`, `comments(author_email)` and `(lease_id)`, `discrepancies(lease_id/related_lease_id/status)`, `alerts(lease_id/status)`, `activity_log(created_at/lease_id)`, `lease_tags(tag)` — all full-scanning. |
| **AI extraction blocks the request** | `POST /leases` runs `ai_extraction.extract_lease_fields` **synchronously** — 5–15s per lease. A multi-lease PDF (N×15s) hangs the UI and can blow gunicorn's 120s `--timeout` → worker killed mid-run → **partial writes** (some leases persisted, some not). |
| **`get_all_effective_leases`, `GET /leases`, risk/alert sync** | Already optimized in a prior pass (single query + in-memory merge; `upsert_*_bulk`). No change needed. |
| **Caching for "account/plan lookups"** | **N/A** — there is no plan/usage-limit system, and account status is read from the signed session cookie (no per-request DB hit). The expensive *derived* computations (portfolio trends, health score) are already cached in `cache.py` with proper invalidation. Adding raw-list caching would risk exactly the staleness bugs the ask warns against, for negligible benefit at this app's scale — deliberately not done. |

### 2.1 Fixes applied

**Indexes** (`database.py` `init_db`, `CREATE INDEX IF NOT EXISTS` — safe on existing DBs): the 15 indexes above. The email-keyed ones are `COLLATE NOCASE` and the matching queries were changed from `lower(col) = lower(?)` to `col = ? COLLATE NOCASE` / `GROUP BY col COLLATE NOCASE` so the index is actually used.

**`get_user_by_email`**: `users.email` is always stored lower-cased, so this now normalizes the input and matches with a plain `=` → uses the `UNIQUE` index. Runs on every login.

**Owner account list — N+1 removed**: new `database.get_usage_stats_for_users(users)` — **6 grouped aggregate queries on one connection**, total, regardless of user count. `owner_list_accounts` calls it once instead of per-user. `get_user_usage_stats` kept as a thin single-user wrapper.

**AI extraction moved off the request path** (`api.py` + `database.py`):
- New `leases.processing_status` (`processing`/`complete`/`failed`) + `processing_error` columns. Default `'complete'` → every existing row and every fast regex-path insert is born done, zero behavior change.
- `POST /leases` and `/leases/batch` with the AI engine: do only the **cheap synchronous work** (validate, extract page text, rent-roll-shape check, regex boundary detection), insert placeholder lease rows in `processing` state, spawn a **daemon thread** for the model calls, and return **`202` with `processing: true`** immediately. The thread writes the real fields (or marks the row `failed` with a plain reason — never a half-written field set), links telemetry, invalidates caches, logs one activity entry. It touches only `database` + pure helpers, never `request`/`session`.
- `GET /leases` / `GET /leases/<id>` expose `processing_status` / `processing_error`. A still-processing lease isn't pre-flagged "doesn't look like a lease".
- Startup: `database.fail_orphaned_processing_leases()` marks any lease left mid-extraction by a dead process as `failed` with "interrupted by a server restart" (a thread doesn't survive a redeploy).
- `LEASE_ASYNC_EXTRACTION=false` forces the old synchronous behavior (operator escape hatch + used by the sync-contract tests). The regex path is always synchronous (it's fast). `resubmit`/`amendment`/`sample` stay synchronous (single-doc, infrequent, heavy post-processing) — flagged as a possible follow-up.
- **Frontend** (`upload-view.js`): a `202` response triggers `waitForProcessing()` — polls `GET /leases/<id>` every 2s (5-min cap) until every lease is `complete`/`failed`, surfacing a `failed` lease's `processing_error` as the file's error. The upload UI already shows a spinner + escalating "still working" copy, so this slots in cleanly.

**Tests**: `test_async_extraction.py` (6 cases): 202 + processing state; background thread fills fields + links telemetry; AI failure → row marked `failed` and **kept** (so the user sees why); multi-lease document processes every split; orphan recovery; `LEASE_ASYNC_EXTRACTION=false` → sync 201. `test_ai_extraction.py`'s two upload tests updated to pin the sync path.

### 2.2 Verification

Full unit suite **60/61** (the 1 failure is the same pre-existing `tesseract` OCR test). New `test_async_extraction.py` (6 cases) green; `test_ai_extraction.py` updated and green.

### 2.3 Follow-ups
- `resubmit` / `amendment` / `sample` uploads still extract synchronously (single-doc, infrequent, heavy post-processing that's awkward to defer). If AI resubmit of a very large lease becomes a real problem, the same `_start_deferred_extraction` machinery can be extended to them.
- The frontend `waitForProcessing` polling needs a browser check on the next deploy (can't exercise the deployed frontend from here). Contract: 202 response has `processing: true`; poll `GET /leases/<id>` until `processing_status` is `complete`/`failed`.
