# Lease Portfolio Intelligence - Frontend

A multi-view web interface for uploading, analyzing, and comparing a
portfolio of commercial leases — not just extracting one PDF at a time.

## Features

- **Dashboard**: every uploaded lease in a sortable/filterable table, with portfolio-wide metrics (total/average rent, CAM exposure, square footage) and an inline risk indicator per lease
- **Upload**: single or batch PDF upload (drag-and-drop or click-to-browse); a batch processes each file independently, so one corrupted file doesn't fail the rest
- **Lease Detail**: grouped field display (Parties / Financial Terms / Dates & Term / Special Clauses) with source citations, click-to-edit inline correction, a risk-flags panel, an amendments list/uploader, and a per-lease "ask about this lease" Q&A box
- **Expiration Timeline**: leases bucketed by how soon they expire (0-6/6-12/12-24/24+ months, already-expired, unknown), most-urgent first
- **Compare**: side-by-side terms for 2+ leases, each numeric term benchmarked against the portfolio average
- **Ask a Question**: portfolio-wide natural-language Q&A — every answer is grounded in real extracted data with page-level citations, never generated/guessed (see the backend's `qa_engine.py` — it's a rule-based query engine, not an LLM call)
- **Portfolio Report**: a one-page printable/downloadable HTML summary (total rent, upcoming expirations, top red flags)
- **Session Stats**: a running tally of extraction confidence across documents processed this browser session

## How to Run

### Prerequisites

1. **Backend must be running first**:
   ```bash
   cd ../backend
   source venv/bin/activate
   python run.py
   ```
   Runs on `http://localhost:5000`. Confirm with `curl http://localhost:5000/health`.

2. **A static file server for the frontend** — any of these work:
   ```bash
   cd frontend
   python3 -m http.server 8080
   ```
   Then open `http://localhost:8080`.

## File Structure

```
frontend/
├── index.html            # App shell: sidebar nav + all view containers
├── styles.css             # All styles (sidebar layout, tables, cards, Q&A, etc.)
├── api.js                  # Fetch wrappers for every backend endpoint
├── app.js                   # View router, shared state, toasts, session stats
├── upload-view.js            # Single/batch upload
├── dashboard-view.js          # Portfolio table + metrics
├── detail-view.js              # Lease detail, inline editing, risk panel, amendments, Q&A
├── timeline-view.js             # Expiration timeline
├── comparison-view.js            # Side-by-side comparison + benchmarking
├── qa-view.js                     # Portfolio-wide Q&A
├── report-view.js                  # Printable report preview
└── README.md                        # This file
```

Loaded as plain `<script src>` tags in dependency order (no build step,
no framework) — this is a deliberate architecture choice carried over
from earlier sessions; see the repo's `DECISIONS.md`. Note: classic
scripts loaded this way share one global scope for top-level
`let`/`const`, which is how e.g. `dashboard-view.js` can reference
`AppState` (declared in `app.js`) directly — this is standard browser
behavior for non-module scripts, not something specific to this app.

## API Integration

`api.js` wraps every endpoint the backend exposes: `/extract` (stateless
single-doc), `/leases` + `/leases/batch` + `/leases/<id>` (+ DELETE) +
`/leases/<id>/amendments` (persisted CRUD), and the portfolio analysis
endpoints — `/portfolio/summary`, `/portfolio/timeline`,
`/portfolio/risks`, `/leases/<id>/risks`, `/qa`, `/leases/compare`,
`/leases/<id>/benchmark`, `/portfolio/rent-roll.csv`,
`/portfolio/rent-roll.xlsx`, `/portfolio/report`. See the backend
README for full request/response shapes.

## Extracted Fields

15 fields per lease: tenant, landlord, rent amount, lease start/end
date, property address, security deposit, CAM charges, rent
escalation, renewal options, permitted use, exclusivity clause,
insurance requirements, default/cure period, square footage. Each
carries a value, a source (page + quote), and a confidence level
(high/medium/low), or nulls across the board if genuinely not found.

## Browser Compatibility

Modern evergreen browsers (Chrome/Edge, Firefox, Safari). Uses
`fetch`, `FormData`, CSS Grid/Flexbox, and template literals — no
transpilation, so very old browsers aren't supported.

## Troubleshooting

**Nothing loads / errors in console**
- Confirm the backend is running and reachable: `curl http://localhost:5000/health`
- Check the browser's Network tab for failed requests — CORS is enabled backend-side, so a failure usually means the backend isn't running, not a CORS issue

**Upload fails or hangs**
- PDF only, 16MB max per file (batch upload has no cap on file count)
- A single corrupted/unreadable file in a batch reports its own error and doesn't block the rest — check the per-file result list

**Q&A says "I don't have a way to answer that yet"**
- This is intentional, not a bug — the Q&A engine is deterministic and only answers questions matching a known pattern (field lookups, totals/averages, expiring-soon lists, counts) rather than guessing at unfamiliar phrasing

## Development Notes

- **Add a new field**: extend `field_extractor.py` on the backend first, then add it to `FIELD_LABELS` and the right group in `FIELD_GROUPS` (`app.js`)
- **Change styling**: CSS custom properties in `:root` in `styles.css`
- **Change API endpoint**: `API_BASE_URL` in `api.js`
- **Add a new view**: create `<view-name>-view.js` registering itself via `registerView('name', {...})`, add a `<section class="view" id="view-name">` to `index.html`, and a sidebar nav button with `data-view="name"`
