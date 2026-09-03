# Deploying Abstractly

How to get Abstractly live at a real public URL, and what to do
whenever you're ready to add a custom domain or make data persistent.

## Why Render

Render was chosen over Vercel/Railway for this stack specifically
because:

- **The backend needs real system binaries, not just Python
  packages.** OCR fallback for scanned leases (`pytesseract` +
  `pdf2image`) needs the `tesseract-ocr` and `poppler-utils` OS
  packages installed alongside Python — not something a
  Node-oriented host like Vercel's serverless functions can do at
  all, and not something most "just point at a `requirements.txt`"
  buildpacks support either. Render's Docker-based Web Services do,
  cleanly (see `backend/Dockerfile`).
- **One platform, one dashboard, one bill** for both halves of this
  app — the Flask API as a Docker Web Service, the static
  landing/app/admin frontend as a Static Site — instead of splitting
  billing/monitoring/env-vars across two different companies (e.g.
  Vercel for frontend + Railway for backend).
- **Free tier to start, painless upgrade later.** Both services can
  run on Render's free plan today; moving the backend to a paid plan
  later (for persistent storage — see below) is a dashboard toggle,
  not a re-deploy or a code change.
- **render.yaml Blueprint**: this repo already includes one
  (`/render.yaml`) that describes both services declaratively — you
  click "New Blueprint," point it at this repo, and Render creates
  both services with the right settings in one step, instead of two
  separate manual "New Web Service" / "New Static Site" flows.

Railway is a reasonable alternative if you ever want to switch (same
Docker-based approach would work there too); Vercel is genuinely not
a fit for the backend specifically, for the OCR-binary reason above.

## What you need to do (only you can do these)

### 1. Push this repo's deployment files to GitHub

I've added the deployment files (`render.yaml`, `backend/Dockerfile`,
`backend/.dockerignore`) and made two small code changes needed for
production (both covered in DECISIONS.md). These need to be pushed to
your GitHub repo (`TimPisano/Abstractly-Code`) before Render can see
them — I'll do the actual `git push` once you confirm you're ready, since
that's a real, visible change to your shared repo.

### 2. Create a Render account

Go to **[render.com](https://render.com)** → "Get Started" → sign up
(GitHub sign-in is the fastest — it also handles the repo-access step
below automatically). No credit card is required to sign up or to use
the free tier.

### 3. Connect your GitHub repo

During signup (or from the Render dashboard → "New +" → "Blueprint"),
Render will ask to install the **Render GitHub App** and pick which
repos it can see. Grant it access to `Abstractly-Code` (either "All
repositories" or just that one — your choice).

### 4. Deploy the Blueprint

Dashboard → "New +" → **"Blueprint"** → select the `Abstractly-Code`
repo → Render reads `render.yaml` and shows you both services it's
about to create (`abstractly-api`, `abstractly`) → click **"Apply"**.

This kicks off the first build. The backend build (installing
tesseract/poppler + Python packages via Docker) takes a few minutes
the first time; the frontend (a plain static-file copy) is fast.

### 5. Set the backend's required secrets

Once the Blueprint is applied, go to the **`abstractly-api`** service
→ **"Environment"** tab. Four values need to be entered by hand (they
were deliberately left blank in `render.yaml` — never put a real
secret in a file that's committed to git):

| Variable | How to get the value |
|---|---|
| `FLASK_SECRET_KEY` | Run locally: `cd backend && source venv/bin/activate && python3 -c "import secrets; print(secrets.token_hex(32))"` — paste the output. |
| `ADMIN_EMAIL` | The email you'll log in with as the first admin. |
| `ADMIN_PASSWORD_HASH` | Run locally: `cd backend && source venv/bin/activate && python3 set_admin_password.py` — it prompts for a password (hidden input) and prints the exact hash to paste here. |
| `TOKEN_ENCRYPTION_KEY` | Run locally: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — paste the output. (Powers encrypted-at-rest storage for the OAuth "link your email" feature; the app runs fine without ever using that feature, but this key must still be set or that one feature's routes will error.) |

Use **fresh, new values for production** — don't reuse your local
`.env` file's `FLASK_SECRET_KEY`/`TOKEN_ENCRYPTION_KEY` verbatim (a
leaked local dev secret shouldn't also compromise the real deployment).
`ADMIN_PASSWORD_HASH` should be a real password only you know, not
whatever you've been using locally for testing.

Click **"Save Changes"** — this triggers an automatic redeploy with
the new values.

### 6. (Optional, skip for now) Email notifications, AI assistant, Google Sheets export

These features degrade gracefully without their env vars set (a clear
error or a silent skip — never a crash), so there's no rush. When
you're ready for any of them:

- **Waitlist confirmation/notification emails** (`EMAIL_USER`,
  `EMAIL_APP_PASSWORD`) — see `backend/.env.example` for exactly how
  to generate a Gmail App Password.
- **AI portfolio assistant** (`ANTHROPIC_API_KEY`) — from
  [console.anthropic.com](https://console.anthropic.com). You
  mentioned funding this key later — same instruction applies here,
  just add it to Render's Environment tab whenever you do.
- **"Export to Google Sheets"** (`GOOGLE_APPLICATION_CREDENTIALS`) —
  see `backend/.env.example`'s step-by-step for creating a Google
  Cloud service account; the resulting JSON key file gets uploaded as
  a **Secret File** in Render (Environment tab → "Secret Files," not
  a plain env var, since it's a whole file) at the path
  `/app/credentials/google-service-account.json`, matching the
  commented-out line already in `render.yaml`.

## Your live URLs

Once both services finish deploying (Render shows "Live"/"Deployed"
with a green status):

- **Public site (landing page, homepage)**: `https://abstractly-n0id.onrender.com`
  ("abstractly" was already taken by someone else on Render — names
  are global — so Render auto-suffixed ours. Check your own service's
  actual URL in the Render dashboard rather than assuming it matches
  this exactly, in case it gets recreated later and picks a different
  suffix.)
- **Backend API** (not meant to be visited directly, but useful to
  sanity-check): `https://abstractly-api.onrender.com/health` should
  return `{"status":"healthy"}` ("abstractly-api" was available, no
  suffix needed.)

If a name is taken (Render tells you at Blueprint-apply time, or you
can just check the dashboard afterward), the two places that need to
match the *frontend's* real URL are `render.yaml`'s
`ADMIN_ALLOWED_ORIGINS` value (CORS) and the same variable's live
value in the `abstractly-api` service's Environment tab in the Render
dashboard (a `render.yaml` edit alone doesn't necessarily take effect
on an already-running service immediately). If the *backend's* name is
taken instead, update `frontend/config.js`'s production
`API_BASE_URL` to match its real URL.

## Known issue: sign-in on Safari (and, eventually, Chrome)

**On the default `*.onrender.com` URLs, signing in does not work in
Safari.** You log in, land back on the login page, and nothing seems to
happen. This is not a bug in the app's code — it's a browser cookie
policy interacting with the split-domain setup:

- The frontend is served from `abstractly-n0id.onrender.com` and the
  API from `abstractly-api.onrender.com`. Render puts `onrender.com` on
  the Public Suffix List, so browsers treat those two subdomains as
  **different sites**, not just different URLs.
- The session cookie the API sets after login is therefore a
  "third-party cookie" from the frontend's point of view. Safari blocks
  those outright (has since 2020). Firefox keeps it (partitioned per
  site). Chrome allows it *today* but that's on a deprecation timeline
  and an enterprise policy or a user setting can already break it.
- **Local development is unaffected** — `localhost:8000` and
  `localhost:5000` count as the same site, so the cookie is
  first-party there. That's why this isn't visible until it's deployed.

**The fix is to make the two services same-site.** In order of
preference:

1. **Custom domain with matching subdomains** (recommended — you were
   already planning to buy a domain). Put the frontend on
   `app.yourdomain.com` and the backend on `api.yourdomain.com`. Both
   are subdomains of one registrable domain, so `SameSite=Lax` cookies
   flow between them and every browser is happy. Follow "Adding a
   custom domain later" below, doing step 4 (backend subdomain) as well
   as the frontend, then change `SESSION_COOKIE_SAMESITE` from `'None'`
   to `'Lax'` in `backend/app/api.py`.
2. **Reverse-proxy the API under the frontend's origin** so the browser
   only ever sees one origin (`/api/...` on the frontend domain). This
   needs a Render `routes` rewrite or a small proxy and is more
   fiddly — ask me to set it up if you don't want to buy a domain yet.
3. **Token auth instead of a cookie** (`Authorization: Bearer`, token
   in `localStorage`). Larger code change; avoids the cookie problem
   entirely but has its own security tradeoffs.

Until one of those is done, **demo on Chrome or Firefox, not Safari**,
and don't send a prospect the link expecting them to open it on an
iPhone.

## Free-tier behavior you should know about

You chose the free tier for now, which means two things worth knowing
before a real call with a prospect:

1. **The backend spins down after 15 minutes of no traffic**, and takes
   ~30-60 seconds to wake back up on the next request. If you haven't
   used the live site recently, open it 1-2 minutes before a call so
   it's already warm — otherwise the first page load during the call
   will hang briefly.
2. **Uploaded lease data does not persist** across a restart or
   redeploy (see "Adding persistent storage later" below for the
   fix). Treat the live site as a demo environment for now: re-upload
   your demo lease fresh before an important call rather than relying
   on data uploaded days ago still being there.

Neither of these requires any action now — just know they're the
tradeoff of "free."

## Adding persistent storage later

When you're ready to stop losing data on restart (recommended before
using this with a real prospect's real data, not just a demo):

1. Render dashboard → `abstractly-api` service → "Settings" → change
   the plan from "Free" to "Starter" (currently ~$7/month).
2. Same service → "Disks" → "Add Disk" → name it `abstractly-data`,
   mount path `/app/data`, size 1 GB (currently ~$0.25/month).
3. Environment tab → add `DB_PATH` = `/app/data/lease_portfolio.db`.
4. Save — Render redeploys automatically. That's the entire upgrade;
   no code change is needed (the app already reads `DB_PATH` at
   startup — see `app/api.py`).

## Logging and monitoring

The backend logs to **stdout** in a consistent format
(`app/logging_config.py`). Render captures stdout — see it under the
`abstractly-api` service → **"Logs"** tab (live tail), or via
`render logs` in Render's CLI.

- Every request logs one line: `GET /leases -> 200 34ms`, prefixed with
  a short **request id** that's also on the `X-Request-Id` response
  header — so if a user reports an error at a certain time, you can
  find every log line for that exact request.
- 5xx responses log at `ERROR`; 4xx at `WARNING`.
- `/health` hits are not logged (Render probes it constantly).
- Env knobs (set on the `abstractly-api` service's Environment tab):
  `LOG_LEVEL` (default `INFO`), `LOG_FORMAT=json` for machine parsing.

**Health check.** `GET /health` (Render's configured health check path)
now runs a `SELECT 1` against the database — a broken/locked/misconfigured
DB returns `503 {"status":"degraded"}` so Render stops routing to a dyno
that can't actually serve requests. `curl https://abstractly-api.onrender.com/health`
should return `{"status":"healthy"}`.

### Getting alerted when something breaks

Two independent options — use either or both:

1. **Email on error (built in).** Set `ERROR_ALERT_EMAILS=true` on the
   `abstractly-api` service (needs `EMAIL_USER` / `EMAIL_APP_PASSWORD` /
   `ADMIN_EMAIL` also set — the same Gmail App Password the waitlist
   emails use). Any `ERROR`/`CRITICAL` log line then emails `ADMIN_EMAIL`,
   rate-limited to one per unique error site per 5 minutes so a loop
   can't mailbomb you. Off by default (opt-in — this app has a past
   accidental-email-storm incident; see `DECISIONS.md`).
2. **Render's own alerts.** `abstractly-api` → "Settings" → "Notifications"
   — Render can email/Slack you on deploy failure and on the service
   going unhealthy (which the new `/health` DB check now makes
   meaningful). Free, no code.
3. *(Optional, not wired up)* A hosted error tracker like **Sentry** —
   `pip install sentry-sdk[flask]` + `sentry_sdk.init(dsn=...)` early in
   `app/api.py`, DSN via a `SENTRY_DSN` env var. Gives grouped stack
   traces and trends. Left out to keep the dependency list minimal;
   the email handler covers "tell me when it breaks".

## Database backups and restore

**Free tier (current):** there is **no persistent disk**, so the SQLite
database is wiped on every restart/redeploy. There is nothing to back
up because there is no durable data — this is fine for a demo, not for
real prospect data. (This is the same tradeoff described under
"Free-tier behavior" above.)

**After you add persistent storage** (the section above):

- **Render disk snapshots.** A Starter+ service with an attached disk
  gets **automatic daily snapshots**, retained ~7 days, at
  `abstractly-api` → "Disks" → your disk → "Snapshots". To restore:
  create a new disk *from* a snapshot and re-point the service at it
  (Render support can also roll a disk back). This recovers the whole
  disk to a point in time — good enough for "the file got corrupted"
  or "a bad deploy trashed data", not for "undo one accidental delete
  from 20 minutes ago".

- **Better: your own SQLite copy.** SQLite is a single file, so a real
  backup is just copying `${DB_PATH}` somewhere safe on a schedule.
  Simplest options:
  - A **Render Cron Job** service (separate, ~$1/mo) running, daily:
    `sqlite3 /app/data/lease_portfolio.db ".backup /tmp/backup.db" && <upload /tmp/backup.db to S3/Backblaze/Dropbox>`.
    `.backup` is safe to run against a live database (it's a proper
    online backup, not a raw `cp`).
  - Or, once volume justifies it, migrate off SQLite to **Render
    Postgres**, which has managed daily backups + point-in-time
    recovery built in. The app's data layer is small and centralized
    (`app/database.py`); this is a real but bounded change.

**To restore a `.backup` copy** onto a running service: put the file at
`${DB_PATH}` (stop the service or do it during a maintenance window so
nothing is mid-write), then restart. On next boot the app runs its
idempotent schema migration (`init_db`) over whatever schema the backup
had, so a slightly older backup still comes up cleanly.

## Adding a custom domain later

Whenever you buy a domain (Namecheap, Google Domains, etc. all work
the same way here):

1. Render dashboard → `abstractly` (the frontend static site) →
   "Settings" → "Custom Domains" → "Add Custom Domain" → enter e.g.
   `app.yourdomain.com` or the bare `yourdomain.com`.
2. Render shows you a DNS record to add (a `CNAME` for a subdomain, or
   an `A`/`ALIAS` record for a bare domain) — add that record at
   wherever the domain is registered. Render auto-provisions a free
   SSL certificate once that DNS record is live (usually within
   minutes, sometimes up to a few hours for DNS to propagate).
3. Update `frontend/config.js`'s production branch and
   `render.yaml`'s `ADMIN_ALLOWED_ORIGINS` to your new domain instead
   of `abstractly.onrender.com`, then redeploy the backend.
4. If you also want the backend on a subdomain of your own domain
   (e.g. `api.yourdomain.com` instead of `abstractly-api.onrender.com`),
   repeat step 1-2 on the `abstractly-api` service, then update
   `frontend/config.js` to point at that instead.

I can walk through any of this with you live once you've made the
purchase — just point me at the domain and registrar.
