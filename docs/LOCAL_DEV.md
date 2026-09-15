# Running the whole thing locally

End-to-end on your own machine: local backend + local frontend, no
deployed services involved, nothing that can affect production.

## 1. Backend (`http://localhost:5000`)

```bash
cd backend
python -m venv venv && source venv/bin/activate      # first time only
pip install -r requirements.txt                       # first time only
python run.py
```

Confirm it's up: `curl http://localhost:5000/health` → `{"status":"healthy"}`.

**macOS note:** Monterey and later bind port 5000 to the AirPlay
Receiver. If `run.py` fails to bind (or `/health` returns something
that isn't ours), either turn off *System Settings → General →
AirDrop & Handoff → AirPlay Receiver*, or run the backend on another
port and tell the frontend about it:

```bash
PORT=5001 python run.py
```
then once, in the browser devtools console on the local frontend:
```js
localStorage.setItem('abstractly.apiBaseOverride', 'http://localhost:5001')
```
(undo with `localStorage.removeItem('abstractly.apiBaseOverride')`).

## 2. Frontend (`http://localhost:8000`)

Any static file server, rooted at `frontend/`:

```bash
cd frontend
python3 -m http.server 8000
```

- App: <http://localhost:8000/app/>
- Landing page: <http://localhost:8000/>
- Admin: <http://localhost:8000/admin/>
- Owner console: <http://localhost:8000/owner/>

`frontend/config.js` auto-detects `localhost` and points every API call
at `http://localhost:5000` (or your override from step 1). Nothing to
edit. Ports 8000, 8080, 5173, 4173, and 3000 (and their `127.0.0.1`
forms) are pre-allowed by the backend's CORS default; any other port
needs `ADMIN_ALLOWED_ORIGINS` set in `backend/.env`.

## 3. Logging in

`backend/.env` already has `LOCAL_DEV_MODE=true`, which skips the `/app`
access gate. You still need a login:

- Your local `backend/lease_portfolio.db` already has an admin user
  (`ADMIN_EMAIL` in `.env`). If you don't know the password:
  ```bash
  cd backend && venv/bin/python3 reset_admin_password.py
  ```
- A brand-new empty DB seeds one admin row from `ADMIN_EMAIL` +
  `ADMIN_PASSWORD_HASH` in `.env` on first boot.

## 4. Lease extraction without Anthropic credits

The Anthropic balance is currently empty, and `backend/.env` has
`LEASE_AI_EXTRACTION=true`, so uploading a lease (or clicking **Try a
Sample Lease**) will fail at the extraction step.

To test the full flow anyway, force the deterministic regex extractor —
add to `backend/.env`:

```
LEASE_EXTRACTION_ENGINE=regex
```

This wins over `LEASE_AI_EXTRACTION` and needs no API key. Extraction
quality is lower than the model path, but every downstream step (portfolio,
rent-roll import, **reconciliation**, discrepancies, obligations, action
items, exports) runs exactly as it does in production. Remove the line
to switch back to the model once credits are topped up.

## What works locally vs. what needs credits / extra setup

| Works now | Needs something |
|---|---|
| Rent-roll import + **lease↔rent-roll reconciliation** | Model-quality lease extraction → Anthropic credits (or `LEASE_EXTRACTION_ENGINE=regex`) |
| Discrepancies, patterns, dollar-impact | AI rent-roll validation → credits |
| Obligations engine, Action Items | Portfolio assistant / Q&A (AI) → credits |
| Portfolio metrics, health score, exports, reports | Scanned-PDF OCR → `brew install tesseract poppler` |
| Team accounts, tasks, comments, owner console | Waitlist / error-alert emails → SMTP env vars |

## Isolation

Local runs use `backend/lease_portfolio.db` (gitignored, your machine
only). It is never the deployed database — and the deployed one is on
Render's free tier with no persistent disk, so it resets on every deploy
regardless. Nothing you do here reaches production.
