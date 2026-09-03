# Operations & Architecture — internal reference

For future-me: what the env vars do, how the pieces fit, and how to
deploy / roll back. Deploy *walkthrough* (account setup, first deploy)
is in `DEPLOYMENT.md`; *why* decisions were made is in `DECISIONS.md`.

---

## 1. The shape of the thing

```
 ┌─────────────────┐        HTTPS + cookie          ┌──────────────────────┐
 │  Static frontend │  ──────────────────────────▶  │   Flask API           │
 │  (Render static) │  ◀──────────────────────────  │   (Render Docker web) │
 │  frontend/*      │        JSON / files            │   backend/app/*       │
 └─────────────────┘                                 └──────────┬───────────┘
   plain HTML/JS/CSS, no build step                             │  file: SQLite
   config.js picks the API origin by hostname                   ▼
                                                       lease_portfolio.db
                                                    (ephemeral on free tier;
                                                     on a Render disk if DB_PATH set)
```

- **One process, one SQLite file.** No Redis, no queue, no separate DB
  server. `backend/app/database.py` opens a fresh short-lived
  connection per call (`get_connection`), so 2 gunicorn workers are
  fine.
- **The frontend is dumb.** All logic is server-side; the frontend is
  fetch + render. `frontend/config.js` is the only environment-aware
  bit (localhost → `http://localhost:5000`, else the Render API URL).

### Request lifecycle (backend)

`backend/app/api.py` on import:
1. `load_dotenv()` — `backend/.env` → `os.environ` (no-op in prod).
2. `configure_logging()` — one stdout handler, `LOG_LEVEL`/`LOG_FORMAT`.
3. `CORS(...)` with the `ADMIN_ALLOWED_ORIGINS` allow-list.
4. `install_security(app, ...)` — CSRF origin check on state-changing
   requests, HSTS, response security headers (`app/security.py`).
5. `install_request_logging(app)` — one log line + `X-Request-Id` per
   request.
6. `database.init_db()` — idempotent schema create + migrate.
7. `database.fail_orphaned_processing_leases()` — reset any lease left
   mid-extraction by a dead process.

---

## 2. Environment variables

Set these on Render at `abstractly-api` → **Environment**. `sync: false`
in `render.yaml` means "enter the value in the dashboard, never commit
it". Nothing here is required for the app to *boot* — every missing
piece degrades to a clear error or a disabled feature.

### Core

| Var | What it does | Notes |
|---|---|---|
| `FLASK_SECRET_KEY` | Signs the session cookie. | If unset, a random one is generated per process → every login drops on restart. Set a stable 64-hex value in prod. |
| `ADMIN_ALLOWED_ORIGINS` | Comma-separated origins allowed to send credentialed requests. **Also the CSRF allow-list.** | Must exactly match the deployed frontend origin(s). Default: the two localhost dev origins. |
| `ADMIN_EMAIL` | (a) seeds the first admin row on a brand-new DB, (b) waitlist-notification recipient, (c) error-alert recipient. | After the first `users` row exists it's only (b)/(c). |
| `ADMIN_PASSWORD_HASH` | bcrypt hash of the first admin's password. | One-time seed only. Generate: `venv/bin/python set_admin_password.py`. |
| `DB_PATH` | Where the SQLite file lives. | Unset → `backend/lease_portfolio.db` (ephemeral). Set to `/app/data/lease_portfolio.db` once a Render disk is attached (see DEPLOYMENT.md). |
| `LOCAL_DEV_MODE` | `true` skips the `/app` waitlist access gate. | **Local only.** Never `true` in prod. Read once at boot, never from a request. |
| `PORT` | Bind port. | Render sets this itself. |
| `FLASK_DEBUG` | `1` enables Werkzeug's interactive debugger. | **Local only** — leaks tracebacks/source. |
| `FORCE_HTTPS` | `true` → app-level HTTP→HTTPS 301. | Leave unset on Render (its edge already redirects). HSTS is sent regardless on HTTPS. |

### AI (lease extraction + the portfolio assistant)

| Var | What it does | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Auth for every model call. | — (features disabled / regex fallback if unset) |
| `LEASE_AI_EXTRACTION` | `true` → uploaded leases are abstracted by the model instead of the regex `FieldExtractor`. | off |
| `LEASE_EXTRACTION_ENGINE` | `ai` \| `regex` — explicit override, wins over the flag. | — |
| `LEASE_EXTRACTION_MODEL` | Model id for extraction. | `claude-sonnet-5` |
| `LEASE_EXTRACTION_TIMEOUT` | Per-request seconds before a hung call fails. | `90` |
| `LEASE_ASYNC_EXTRACTION` | `false` → model uploads block the request instead of returning 202 + finishing on a background thread. | `true` |
| `ASSISTANT_MODEL` | Model id for the in-app Q&A assistant. | `claude-sonnet-5` |

If `LEASE_AI_EXTRACTION` is on but no key is configured → regex
fallback + a logged warning (never a failed upload). A model call that
genuinely fails → clean 502 (sync) or `processing_status='failed'`
(async), never a partial write, never a silent regex substitution.

### Email (waitlist + error alerts)

| Var | What it does |
|---|---|
| `EMAIL_USER` | Gmail address emails are sent *from*. |
| `EMAIL_APP_PASSWORD` | Gmail **App Password** (not the account password). |
| `ERROR_ALERT_EMAILS` | `true` → an `ERROR`/`CRITICAL` log line also emails `ADMIN_EMAIL` (rate-limited per call-site). Needs the two above + `ADMIN_EMAIL`. **Opt-in** (past email-storm incident — see DECISIONS.md). |

If `EMAIL_USER`/`EMAIL_APP_PASSWORD` are missing, every send is a
logged no-op — the waitlist flow still works, nobody just gets the
email.

### Other integrations

| Var | What it does |
|---|---|
| `TOKEN_ENCRYPTION_KEY` | Fernet key encrypting stored OAuth tokens for the "send from my email" feature (`app/token_encryption.py`, `app/email_accounts.py`). Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to a Google service-account JSON for "Export to Google Sheets". Unset → that button shows a clear error, nothing else affected. |

### Logging

| Var | What it does | Default |
|---|---|---|
| `LOG_LEVEL` | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR` | `INFO` |
| `LOG_FORMAT` | `json` → one JSON object per line | plain |

---

## 3. How the subsystems fit

### Auth (`app/auth.py`, `app/api.py` `/auth/*`, `app/security.py`)

- **Team accounts** in the `users` table: email, name, bcrypt hash,
  `role` (`viewer` < `analyst` < `admin`), `status`, `is_owner`.
- Session = Flask **signed cookie** (`SameSite=None; Secure; HttpOnly`,
  12h). No server-side session store.
- `@require_role('analyst')` on a route → 401 if no session, 403 if the
  session's role rank is too low. `@require_owner()` → 404 (not 403) to
  non-owners, so `/owner/*` is undiscoverable.
- `is_owner` is **not** implied by `role='admin'` and there is **no**
  API path that grants it — only `backend/set_owner.py` (local script)
  or the env-var reseed.
- CSRF: the cookie is `SameSite=None` (frontend/API are cross-site on
  Render), so `app/security.py` rejects any `POST/PUT/PATCH/DELETE`
  whose browser `Origin`/`Referer` isn't in `ADMIN_ALLOWED_ORIGINS`.
- Rate limits (all in-process, per-worker): `/auth/login` (20/5min per
  IP, 7/15min per email), `/auth/forgot-password`, `/auth/reset-password`,
  `/waitlist`, `/assistant/ask`.

### Plans / usage limits

**There are none.** No billing, no per-account quotas, no plan tiers in
the schema or code. Every logged-in user shares one portfolio. The
`ai_extraction_runs` telemetry table is the count source a future
per-account cap *would* read from, but nothing enforces one today. (If
you see "plan" in older notes, it was aspirational.)

### Multi-tenant data isolation

**Not on `main`.** All portfolio data (leases, discrepancies, alerts,
tasks) is shared across every login. Real `account_id` scoping exists
only in the unmerged branch `worktree-agent-ade7619750bfa9a9f`.

### AI lease extraction (`app/ai_extraction.py`, `app/api.py` upload routes)

- Engine chosen by `resolve_engine()`: `LEASE_EXTRACTION_ENGINE`
  override → else `LEASE_AI_EXTRACTION` + key → else `regex`.
- Upload → `document_extractor.extract_pages()` (any format → uniform
  page text) → regex boundary detection (multi-lease split) → per-range
  extraction.
- **Regex engine**: synchronous, returns 201 with fields.
- **AI engine**: inserts placeholder leases `processing_status='processing'`,
  returns **202** `{processing: true}`, a daemon thread runs the model
  calls and `finalize_lease_processing()`s each row to `complete` (or
  `failed` with a plain reason, row kept). Frontend polls
  `GET /leases/<id>`.
- Every model call → one `ai_extraction_runs` row (latency, tokens,
  per-confidence-tier field counts, ok/error), surfaced in the owner
  console's **Extraction Quality** tab.
- Same call discipline everywhere (`call_forced_tool`): forced
  single-tool JSON, own retry/backoff, hard timeout, `AIExtractionError`
  on every failure path.

### Rent-roll AI validation (`app/ai_rent_roll_validation.py`, `POST /portfolio/rent-roll-ai-validation`)

- For each unit where an imported rent-roll row **and** an abstracted
  lease document both exist (exact address match), the model
  cross-checks the two and emits discrepancies with its own
  high/medium/low severity.
- Guardrail: only runs against a lease that's actually been abstracted
  (`is_abstracted()`); a not-yet-abstracted unit is skipped, no error.
- Persists as discrepancy type `rent_roll_ai_validation` — shows up in
  the normal Discrepancies view. One pair's API failure doesn't abort
  the sweep.

### Observability

- **Logs** → stdout, captured by Render. One line per request with a
  request id (also `X-Request-Id`). 5xx at ERROR, 4xx at WARNING.
- **`GET /health`** runs `SELECT 1` — 503 on a DB problem so Render's
  health check is meaningful.
- **Alerts**: `ERROR_ALERT_EMAILS=true` emails on errors; Render's own
  Notifications cover deploy failure + unhealthy service.
- Owner console → **Extraction Quality** tab: training-round accuracy
  trend + live production volume/errors/latency/confidence mix.

---

## 4. Deploy and roll back on Render

### Deploy

Render auto-deploys `abstractly-api` and `abstractly` on every push to
`main` (Blueprint from `render.yaml`). To watch it: Render dashboard →
the service → **"Events"** / **"Logs"**.

Manual deploy (e.g. to redeploy without a code change after an env-var
edit): service → **"Manual Deploy"** → "Deploy latest commit".

A `render.yaml` change (new env var key, header, plan) needs a deploy
to take effect, and **an env var's _value_ set to `sync: false` must
also be entered in the dashboard** — `render.yaml` only declares the
key.

### Roll back

**Fastest — Render's built-in rollback (no git):**
service → **"Events"** → find the last-known-good deploy → **"Rollback
to this deploy"**. Redeploys that exact image/commit in ~1–2 min. Use
this for "the deploy that just went out is broken".

**Git rollback (makes `main` match):**
```
git revert <bad-commit>        # or: git revert <oldest>..<newest>
git push origin main           # Render auto-deploys the revert
```
Prefer `revert` over `reset --hard` + force-push — non-destructive,
and force-pushing `main` fights Render's deploy tracking.

**Database considerations on rollback:**
- The schema migration (`init_db`) is **additive only** — it adds
  columns/tables, never drops. So rolling the *code* back while the DB
  is on a newer schema is safe: the old code just ignores the extra
  columns.
- If a bad migration ever *did* need undoing, restore the DB from a
  backup (DEPLOYMENT.md → "Database backups and restore") rather than
  writing a down-migration.
- On the **free tier** there's no persistent DB, so a rollback that
  restarts the dyno also wipes all data — expected, documented.

### If the site is down

1. `curl https://abstractly-api.onrender.com/health` — `{"status":"healthy"}`?
   - `503 degraded` → DB problem (disk full / bad `DB_PATH` / locked).
   - connection refused / 502 → the dyno is down or crash-looping →
     check **Logs** for the traceback.
2. Render **Events** — did the last deploy fail to build, or build fine
   and then crash on boot?
3. Roll back (above) while you diagnose.
