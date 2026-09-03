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
