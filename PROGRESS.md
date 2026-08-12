# Progress Summary

**Last updated**: 2026-08-12 (session 2 — extraction engine rework, 4→14 fields, confidence scoring, frontend rebuild, final verification pass)

---

## Completion Summary (read this first)

### Overall status: fully working

Every field extracts correctly on every test document in the project, verified three independent ways (direct function call, live HTTP API, and simulated frontend), and the app degrades cleanly on every edge case tested (empty file, corrupted file, valid PDF with no lease terms). There are no known extraction or UI bugs at the end of this session. The one thing that is **not** fully verified is live OCR against a real scanned PDF — see "Known issue: OCR not live-verified" below.

### Full accuracy table

Field-by-field extraction accuracy across all 5 test documents in the project (`sample_lease.pdf`, `sample_lease_commercial.pdf`, `retail_lease.pdf`, `office_lease.pdf`, `casual_sublease.pdf`), each with deliberately different structure, phrasing, currency/date formatting, and drafting formality:

| Field | residential | commercial | retail | office | casual | Accuracy |
|---|---|---|---|---|---|---|
| tenant | ✓ | ✓ | ✓ | ✓ | ✓ | 5/5 (100%) |
| landlord | ✓ | ✓ | ✓ | ✓ | ✓ | 5/5 (100%) |
| rent_amount | ✓ | ✓ | ✓ | ✓ | ✓ | 5/5 (100%) |
| lease_start_date | ✓ | ✓ | ✓ | ✓ | ✓ | 5/5 (100%) |
| lease_end_date | ✓ | ✓ | ✓ | ✓ | ✓ | 5/5 (100%) |
| property_address | ✓ | ✓ | ✓ | ✓ | N/A* | 5/5 (100%) |
| security_deposit | ✓ | ✓ | ✓ | N/A* | ✓ | 5/5 (100%) |
| cam_charges | N/A* | ✓ | ✓ | N/A* | N/A* | 5/5 (100%) |
| rent_escalation | N/A* | ✓ | ✓ | ✓ | N/A* | 5/5 (100%) |
| renewal_options | N/A* | ✓ | ✓ | ✓ | N/A* | 5/5 (100%) |
| permitted_use | N/A* | ✓ | ✓ | ✓ | N/A* | 5/5 (100%) |
| exclusivity_clause | N/A* | ✓ | N/A* | ✓ | N/A* | 5/5 (100%) |
| insurance_requirements | N/A* | ✓ | ✓ | ✓ | N/A* | 5/5 (100%) |
| default_cure_period | N/A* | ✓ | ✓ | ✓ | N/A* | 5/5 (100%) |
| **Overall** | | | | | | **70/70 (100%)** |

`✓` = field is present in that document and was extracted correctly (verified against a known ground-truth value, not just "returned something").
`N/A*` = the field is genuinely absent from that document by design (e.g. the casual sublease has no CAM clause), and the extractor correctly returned "Not Found" (null) rather than guessing or erroring — this counts as correct in the accuracy total.

Re-run this table yourself at any time: `cd backend && source venv/bin/activate && python tests/test_synthetic_accuracy.py`

### Bugs found and fixed this session

All found via testing against the synthetic documents (structural/phrasing diversity is what surfaced these — the original 2 fixtures never exercised them) and fixed before this session ended:

1. **Core bug (Part 1)**: rent/date/tenant extraction only matched rigid "Label: Value" phrasing and silently failed on narrative lease prose ("...the sum of $6,250.00 per month...", "shall commence on April 1, 2025"). Fixed with a bounded keyword-to-value "gap" pattern instead of requiring immediate adjacency.
2. **`re.IGNORECASE` defeated capitalization bounding**: a blanket case-insensitive flag made `[A-Z]`/`[a-z]` stop meaning "capitalized," causing catastrophic over-capture of party names in casual phrasing (captured "Jordan Blake and the tenant is Alex Chen" instead of "Jordan Blake"). Fixed by running party-name patterns case-sensitive with keywords scoped case-insensitive via `(?i:...)`.
3. **Section-heading periods blocked matches**: "7. INSURANCE. Tenant shall maintain..." — the heading's own period sat directly after the keyword, and the period-excluding gap could never cross it to reach the amount, when the body text didn't repeat the word "insurance." Fixed by absorbing an optional heading period right after the keyword.
4. **Ambiguous "(N) days ... written notice" clauses**: a lease can have several unrelated ones (renewal notice, cure notice); default/cure extraction was taking the first match in document order, which was sometimes the wrong clause. Fixed by scanning all candidates and preferring the one with "default"/"cure" nearby.
5. **Multi-page field spans**: extraction searched each page independently, so a keyword at the bottom of one page and its value at the top of the next could never match. Fixed by searching the whole document (pages joined with a page-offset map for source attribution) instead of page-by-page — this also fixed a related bug where a low-confidence match on an early page could incorrectly win over a high-confidence match on a later page.
6. Narrower issues: CAM/renewal/permitted-use keyword coverage too narrow for common alternate phrasings, entity-suffix names (LLC/LP) getting truncated by the personal-name pattern, trailing sentence periods leaking into captured names, PDF fixture timestamps causing spurious git diffs on every test run.

### Known issue: OCR not live-verified

This development environment has no `tesseract` or `poppler` binaries installed, and no package manager (`brew`, `apt`, etc.) available to install them. The OCR fallback code path (`pdf_extractor.py`'s `_extract_with_ocr`) was verified with `unittest.mock` against the real code — confirmed the fallback triggers correctly when digital text extraction yields sparse text, that OCR output flows into field extraction normally, and that an OCR failure returns an empty page list instead of crashing the request. **What was not verified**: an actual scanned/image-based PDF run through real tesseract OCR end-to-end. To close this gap: `brew install tesseract poppler` (macOS) in an environment with Homebrew, then run `backend/tests/test_ocr_fallback.py` against a real scanned PDF, or simply upload one through the UI and confirm text comes back.

### Frontend verification caveat

No browser automation tool (Playwright/Puppeteer/etc.) was available in this environment, so a literal mouse-and-keyboard browser session could not be driven directly. Instead, a jsdom-based harness (in the session's scratch directory, not part of the repo) loaded the **actual, unmodified** `index.html`/`app.js`, mocked `fetch` to return real `/extract` responses captured from the live backend, and drove the exact `processFile()` entry point the browser uses on file upload/drop — then asserted on the resulting DOM and on the actual JSON blob captured from `exportJSON()`. This ran successfully against all 5 test documents (grouping, confidence badges, inline editing, edited-flag, JSON export) plus the error path (corrupted-PDF response and raw network failure). This is a strong signal but is not identical to a real browser session (no visual rendering, no real click/drag events, no real File System Access API). **Recommended**: do one manual click-through when you're back — see "What to test first" below.

### How to start both servers

```bash
# Terminal 1 — backend
cd backend
source venv/bin/activate   # venv already exists and has all dependencies installed
python run.py
# Runs on http://localhost:5000 — confirm with: curl http://localhost:5000/health

# Terminal 2 — frontend
cd frontend
python3 -m http.server 8080
# Open http://localhost:8080 in a browser
```

If a previous session's servers are still running and you get "port already in use": `lsof -ti:5000 -ti:8080 | xargs kill -9`, then start again.

### What to test first when you're back

1. Open `http://localhost:8080`, drag `backend/tests/sample_lease_commercial.pdf` onto the upload area.
2. Confirm results appear grouped into **Parties / Financial Terms / Dates & Term / Special Clauses**.
3. Confirm each field shows a colored confidence badge (green=high, amber=medium, red=low, gray=not found).
4. Click any extracted value (e.g. Monthly Rent) — it should become an editable text box. Change it and click elsewhere; it should show an "Manually Edited" badge.
5. Click **Export JSON** and open the downloaded file — confirm it includes `confidence` and `edited` alongside `value`/`source` for every field.
6. Click **Session Stats** in the header — confirm it shows 1 document processed with a fields-found count.
7. If you have real (anonymized) lease PDFs, that's the most valuable next test — see "High Priority" below.

---

## What's Built

### Backend (`backend/`)
- Flask API (`app/api.py`) — `POST /extract`, `GET /health`
- PDF text extraction with OCR fallback (`app/pdf_extractor.py`) — PyPDF2 for digital PDFs, pytesseract+pdf2image fallback for scanned ones (see OCR caveat above)
- Field extraction engine (`app/field_extractor.py`) — 14 fields, each via an ordered list of regex strategies (label-style → prose-style → loose fallback) tagged with a confidence tier; whole-document search (not page-by-page) with page-offset mapping for source attribution
- Extracted fields: `tenant`, `landlord`, `rent_amount`, `lease_start_date`, `lease_end_date`, `property_address`, `security_deposit`, `cam_charges`, `rent_escalation`, `renewal_options`, `permitted_use`, `exclusivity_clause`, `insurance_requirements`, `default_cure_period`
- Every field returns `{"value": ..., "source": {"page": N, "quote": "..."} | null, "confidence": "high"|"medium"|"low"|null}`

### Frontend (`frontend/`)
- Vanilla JS/HTML/CSS, no build step
- Drag-and-drop upload with validation
- Results grouped into 4 logical sections with color-coded confidence badges
- Click-to-edit inline correction, tracked with an `edited` flag through to export
- JSON export (value + source + confidence + edited-flag per field)
- Session Stats panel (localStorage) tracking fields-found/confidence-tier counts across documents processed in the browser session

### Tests (`backend/tests/`)
- `test_extraction.py` — validates all 14 fields against the residential and commercial fixtures
- `test_synthetic_accuracy.py` — field-by-field accuracy report across all 5 documents (the table above)
- `test_multipage_field.py` — confirms cross-page-boundary field extraction
- `test_ocr_fallback.py` — mocked OCR trigger/success/failure logic
- `test_live_api.py` — same accuracy check as `test_synthetic_accuracy.py` but through the actual running HTTP server, not a direct function call
- `create_sample_lease.py`, `create_commercial_lease.py`, `create_synthetic_leases.py` — deterministic PDF fixture generators (`invariant=1`, so re-running them doesn't produce spurious git diffs)

## Current Limitations

- **Regex-based, not ML/NLP** — accuracy depends on the pattern library covering the phrasing a given lease actually uses. All 5 test documents hit 100%, but real leases will inevitably use phrasing not yet covered.
- **OCR not live-verified** — see above.
- **No literal browser click-through this session** — see above; do one manually when convenient.
- **Single-value fields only** — if a lease legitimately states two different rent amounts (e.g. an early-termination scenario), the extractor returns one.
- **No residential-lease-specific field set** — the tool now assumes commercial lease concepts (CAM, exclusivity, permitted use); a pure residential lease will correctly show many of these as Not Found, which is appropriate, but there's no separate "residential mode."
- **No batch processing** — one PDF per upload.

## Next Steps (prioritized)

### High Priority
1. **Install tesseract+poppler and run a real OCR test** against an actual scanned PDF — closes the one verification gap from this session.
2. **Test against real (anonymized) commercial leases** — the synthetic documents were designed to be structurally diverse, but real leases will surface phrasing gaps synthetic documents can't anticipate. This is the highest-value next step for accuracy.
3. **Do a manual browser click-through** — confirm the jsdom-verified behavior holds in an actual browser (drag-drop visuals, real click/focus behavior, actual file picker).

### Medium Priority
4. **Residential lease variant** — either a distinct field set for residential leases or clearer UI messaging that "Not Found" for commercial-only fields (CAM, exclusivity) is expected on a residential document, not a failure.
5. **Batch processing** — upload and process multiple PDFs in one session, useful now that the Session Stats panel exists to aggregate results.
6. **CSV export** alongside JSON.
7. **Multi-value field support** — for leases with legitimately multiple rent figures, escalation tables beyond simple year-by-year, etc.

### Low Priority / Nice to Have
8. Deployment setup (Docker, production WSGI server — `run.py` currently uses Flask's dev server).
9. Persisted extraction sessions (currently everything is in-memory/localStorage, lost on backend restart or browser data clear).
10. User accounts / multi-user support.

## Dependencies

**System**: Python 3.7+, Tesseract OCR + Poppler (for the OCR fallback path — not installed in this dev environment, see above)
**Python packages**: see `backend/requirements.txt`
**Frontend**: none — pure HTML/CSS/JS
**Test-only** (not part of the app): Node.js + jsdom were used in this session's scratch directory to simulate a browser for frontend verification; not a project dependency.

## Project Structure

```
lease-abstraction/
├── backend/
│   ├── app/
│   │   ├── api.py
│   │   ├── pdf_extractor.py
│   │   └── field_extractor.py
│   ├── tests/
│   │   ├── create_sample_lease.py
│   │   ├── create_commercial_lease.py
│   │   ├── create_synthetic_leases.py
│   │   ├── test_extraction.py
│   │   ├── test_synthetic_accuracy.py
│   │   ├── test_multipage_field.py
│   │   ├── test_ocr_fallback.py
│   │   ├── test_live_api.py
│   │   └── *.pdf (5 fixtures)
│   ├── venv/
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── CLAUDE.md
├── DECISIONS.md
├── PROGRESS.md
└── README.md
```
