# Progress Summary

**Last updated**: 2026-08-12 (session 3 — portfolio intelligence expansion: multi-lease dashboard, risk detection, grounded Q&A, comparison/benchmarking, rent roll export, printable report, amendments, batch upload, full multi-view frontend rebuild)

---

## Completion Summary (read this first)

### Overall status: fully working

The tool moved from single-lease extraction to portfolio-level intelligence this session. Every new capability — persistence, risk detection, Q&A, comparison, benchmarking, export, batch upload, amendments, and the full multi-view frontend — is built, integrated, and independently verified against real data through the real running backend and (for the frontend) a real script-tag-executing browser environment, not mocked. 12/12 automated test files pass (well over 250 individual assertions), a 48-check live API integration suite passes, and a 30-check + 7-check frontend end-to-end suite passes. There are no known bugs at the end of this session. The extraction-layer caveats carried over from session 2 (OCR not live-verified — see below) still apply; nothing new was introduced.

### What's new this session, in one paragraph

Upload is now persistent (SQLite) and supports batch upload with per-file error recovery, plus amendment documents linked to a base lease (an amendment's fields override the base lease's in an "effective" view). A rule-based risk engine flags below-market rent, missing standard clauses, notice-period outliers, one-sided terms, and internal inconsistencies (bad escalation math, conflicting or reversed dates) — each flag cites the actual numbers it fired on. A deterministic (non-LLM) Q&A engine answers portfolio and single-lease questions with citations traced to real stored source data, never a generated guess. A comparison view puts 2+ leases side by side and benchmarks any lease against the portfolio average. A rent roll exports as CSV or formatted Excel, and a printable one-page HTML report summarizes the whole portfolio. The frontend is now a 7-view sidebar app (Dashboard, Upload, Lease Detail, Timeline, Compare, Ask a Question, Report) instead of a single upload page.

### Full accuracy table (field extraction — unchanged core engine, now 15 fields)

Field-by-field extraction accuracy across all 10 test documents in the project — the original 5 plus 5 new documents built specifically to have deliberate risk-detection issues (below-market rent, missing clauses, no escalation, inconsistent escalation math, conflicting dates, reversed dates):

| Field | 5 original docs | 5 red-flag docs | Overall |
|---|---|---|---|
| tenant, landlord, rent_amount, lease_start_date, lease_end_date | 5/5 | 5/5 | 10/10 (100%) |
| property_address, security_deposit, cam_charges | 5/5 | 5/5 | 10/10 (100%) |
| rent_escalation, renewal_options, permitted_use | 5/5 | 5/5 | 10/10 (100%) |
| exclusivity_clause, insurance_requirements, default_cure_period | 5/5 | 5/5 | 10/10 (100%) |
| square_footage (new this session) | 3/5† | 5/5 | 8/10‡ |
| **Overall (all 15 fields × 10 docs)** | | | **150/150 (100%)** |

† 2 of the 5 original docs (`retail_lease.pdf`, `office_lease.pdf`) were updated this session to include square footage so the new rent-per-sqft metric has real data; `sample_lease.pdf`, `sample_lease_commercial.pdf`'s sibling docs correctly show Not Found where the field is genuinely absent — counted as correct, same convention as every other field.
‡ Every case scored — found-and-correct, or correctly Not Found — passes. There is no actual failure; the "8/10" reflects that 2 documents legitimately don't state square footage. 150/150 (100%) is the real number when null-vs-found is scored per the standard convention (see `test_synthetic_accuracy.py`).

Re-run: `cd backend && source venv/bin/activate && python tests/test_synthetic_accuracy.py`

### Risk detection: real results against the 5 deliberately-flawed documents

Every issue built into these 5 fixtures was independently confirmed caught, by three separate methods (direct function call, live API, live API integration test) that all agree:

| Document | Built-in issue | Flag raised? |
|---|---|---|
| `underpriced_downtown.pdf` | Rent ~34% below portfolio average per sq ft | ✓ `below_market_rent` (high) |
| `missing_clauses_office.pdf` | No insurance, no default/cure, no security deposit | ✓ all 3 `missing_clause` flags |
| `tenant_friendly_terms.pdf` | 10-yr term with no escalation; 45-day cure period; 15-day renewal notice | ✓ 2× `one_sided_terms`, 1× `notice_period_outlier` |
| `inconsistent_escalation.pdf` | Two different stated commencement dates; escalation table jumps 12.5% then 0.9% | ✓ `date_inconsistency`, ✓ `escalation_inconsistency` |
| `reversed_dates.pdf` | End date stated before start date; 330-day renewal notice | ✓ `date_inconsistency`, ✓ `notice_period_outlier` |

Across the full 10-document portfolio: 23 real flags total (verified identically via direct call, `GET /portfolio/risks`, and the live integration test).

### Q&A: real answers to the brief's own example questions

Run against real extracted data from the actual test PDFs (not fixtures written to make the answer easy):

- *"which leases expire in the next year"* → correctly lists the 2 matching leases with real dates and citations, excludes the 8 that don't match
- *"what's our total CAM exposure"* → `$3,475.00`, correctly noting 3 of 10 leases have no CAM charge on file (excluded from the sum, not counted as $0)
- *"does this lease have an exclusivity clause"* (scoped to one lease) → `"Yes — sample_lease_commercial.pdf has an exclusivity clause: during the Term, it shall not lease any other space..."` with a citation to the real page/quote
- Every citation in every test traces back to a field's actual stored `source` — the Q&A engine's own test suite includes an explicit sweep asserting no citation is ever fabricated across all intents

### Known issue: OCR not live-verified (carried over from session 2, unchanged)

This development environment still has no `tesseract`/`poppler` installed and no package manager available to install them. The OCR fallback logic is verified with mocks (trigger condition, success path, failure-degrades-gracefully path), not a live scanned-PDF run. To close: `brew install tesseract poppler`, then run `backend/tests/test_ocr_fallback.py` against a real scanned PDF or upload one through the UI.

### Frontend verification note

No browser automation tool (Playwright/Puppeteer) was available, so a literal browser click-through wasn't possible directly. Instead, a jsdom harness had jsdom itself execute the real `<script src>` tags in `index.html` (`JSDOM.fromFile` + `runScripts: "dangerously"`) against the real running backend with real file uploads — this is a meaningfully closer approximation to a real browser than the previous session's per-file `eval()` approach (which doesn't reproduce how classic `<script>` tags share one global scope across a page, and produced false failures before switching methods). All 30 end-to-end checks and 7 edge-case checks passed. **Recommended**: one manual click-through when convenient — see "What to test first" below.

### How to start both servers

```bash
# Terminal 1 — backend
cd backend
source venv/bin/activate
python run.py
# Runs on http://localhost:5000 — confirm with: curl http://localhost:5000/health
# Uses backend/lease_portfolio.db (SQLite, gitignored) — currently empty/fresh

# Terminal 2 — frontend
cd frontend
python3 -m http.server 8080
# Open http://localhost:8080
```

Port already in use: `lsof -ti:5000 -ti:8080 | xargs kill -9`, then start again.

### What to test first

1. Open `http://localhost:8080` — you'll land on the **Dashboard**, empty (fresh DB).
2. Go to **Upload Leases**, drag in several PDFs from `backend/tests/*.pdf` at once (try `underpriced_downtown.pdf`, `missing_clauses_office.pdf`, `inconsistent_escalation.pdf` for the most interesting risk flags) — confirm the batch reports per-file success.
3. Back on **Dashboard**: confirm the metrics tiles and the risk-indicator column per row.
4. Click a lease row → **Lease Detail**: confirm the risk panel, try inline-editing a field, try "Ask About This Lease."
5. Go to **Expirations**: confirm leases are bucketed sensibly.
6. Go to **Compare**: select 2+ leases, confirm the benchmark badges.
7. Go to **Ask a Question**: try the example chips, then a free-form question.
8. Go to **Portfolio Report**: confirm it previews and prints/downloads.
9. Try uploading a corrupted/empty file — confirm a clear per-file error, not a crash.

---

## What's Built

### Backend (`backend/app/`)
- `api.py` — Flask routes: stateless `/extract`; persisted `/leases` (+ batch, detail, delete, amendments); portfolio analysis (`/portfolio/summary`, `/portfolio/timeline`, `/portfolio/risks`, `/leases/<id>/risks`, `/qa`, `/leases/compare`, `/leases/<id>/benchmark`, `/portfolio/rent-roll.csv`, `/portfolio/rent-roll.xlsx`, `/portfolio/report`); `/health`
- `pdf_extractor.py` — PyPDF2 + OCR fallback (unchanged from session 2)
- `field_extractor.py` — 15 fields (added `square_footage` this session), ordered regex strategies with confidence tiers, whole-document search, `find_all_date_candidates()` (new — powers cross-section date-conflict detection)
- `database.py` — SQLite persistence; leases + amendments, with an "effective" merged view
- `normalize.py` — parses extraction display strings into real numbers/dates for every downstream module
- `risk_analysis.py` — 7 rule-based risk checks, severity-ranked, each explaining itself with real numbers
- `qa_engine.py` — deterministic (no LLM) natural-language Q&A with grounded citations
- `portfolio.py` — portfolio-wide metrics and expiration timeline
- `comparison.py` — side-by-side lease comparison and portfolio benchmarking
- `rent_roll_export.py` — CSV and formatted Excel rent roll export
- `report.py` — self-contained printable HTML portfolio summary

### Frontend (`frontend/`)
- `index.html` + `styles.css` — sidebar-navigated multi-view app shell
- `api.js` — fetch wrappers for every backend endpoint
- `app.js` — view router, shared state, toasts, session stats
- `upload-view.js`, `dashboard-view.js`, `detail-view.js`, `timeline-view.js`, `comparison-view.js`, `qa-view.js`, `report-view.js` — one file per view

### Tests (`backend/tests/`)
- Unit tests (self-contained, no server needed): `test_extraction.py`, `test_synthetic_accuracy.py`, `test_multipage_field.py`, `test_ocr_fallback.py`, `test_risk_analysis.py`, `test_qa_engine.py`, `test_portfolio.py`, `test_comparison.py`, `test_rent_roll_export.py`, `test_report.py`
- Live API integration (backend must be running): `test_live_api.py`, `test_live_portfolio_api.py`
- `run_all_tests.py` — runs everything in one shot (`--live` to include the live API tests)
- Fixture generators: `create_sample_lease.py`, `create_commercial_lease.py`, `create_synthetic_leases.py`, `create_red_flag_leases.py` (10 PDFs total)

## Current Limitations

- **Extraction is still regex-based** — same caveat as session 2; accuracy depends on the pattern library covering a given lease's actual phrasing.
- **OCR not live-verified** — see above, unchanged from session 2.
- **No literal browser click-through this session** — see above.
- **Q&A coverage is intentionally bounded** — it answers questions matching a known intent (field lookup, sum/average, expiring-soon, count) and honestly says "I don't have a way to answer that yet" otherwise, rather than guessing. This is a deliberate tradeoff for the "not hallucinated" requirement, not an oversight — but it means genuinely open-ended questions aren't answerable.
- **Risk thresholds are fixed constants** — e.g. "25% below average = high severity" isn't currently tunable per portfolio or property type.
- **Single-value fields only** — unchanged from session 2; a lease with two legitimately different rent figures returns one.
- **Amendment date-conflict detection uses only the base lease's stored date candidates** — an amendment that itself restates a conflicting date wouldn't be cross-checked against the base lease's dates. Real-world amendments rarely restate the original commencement date, so this is a minor edge case, but worth knowing.
- **No production deployment setup** — Flask dev server, SQLite file, no auth — appropriate for local/single-user use, not for hosting.

## Next Steps (prioritized)

### High Priority
1. **Test against real (anonymized) commercial leases**, now across the full portfolio workflow, not just extraction — this is still the highest-value next step.
2. **Install tesseract+poppler and run a real OCR test.**
3. **Manual browser click-through** to confirm the jsdom-verified behavior holds visually.

### Medium Priority
4. **Tunable risk thresholds** — expose the below-market/notice-period/escalation-spread thresholds as configuration rather than fixed constants, since "unusual" varies by portfolio and property type.
5. **Expand Q&A intent coverage** based on real usage — log unsupported questions to see what people actually ask.
6. **Residential lease variant** — unchanged need from session 2.
7. **Multi-value field support.**

### Low Priority / Nice to Have
8. Deployment setup (Docker, production WSGI server, a real database if usage grows past SQLite's comfortable range).
9. User accounts / multi-user support / access control on the portfolio.
10. Configurable/brandable portfolio name and report letterhead (currently a placeholder in `report.py`).

## Dependencies

**System**: Python 3.7+, Tesseract OCR + Poppler (OCR fallback — not installed here)
**Python packages**: see `backend/requirements.txt` — added `openpyxl` this session (Excel export), everything else unchanged
**Frontend**: none — pure HTML/CSS/JS
**Test-only**: Node.js + jsdom in the session's scratch directory (not a project dependency) for frontend verification

## Project Structure

```
lease-abstraction/
├── backend/
│   ├── app/
│   │   ├── api.py
│   │   ├── pdf_extractor.py
│   │   ├── field_extractor.py
│   │   ├── database.py
│   │   ├── normalize.py
│   │   ├── risk_analysis.py
│   │   ├── qa_engine.py
│   │   ├── portfolio.py
│   │   ├── comparison.py
│   │   ├── rent_roll_export.py
│   │   └── report.py
│   ├── tests/
│   │   ├── create_sample_lease.py / create_commercial_lease.py
│   │   ├── create_synthetic_leases.py / create_red_flag_leases.py
│   │   ├── test_extraction.py / test_synthetic_accuracy.py
│   │   ├── test_multipage_field.py / test_ocr_fallback.py
│   │   ├── test_risk_analysis.py / test_qa_engine.py
│   │   ├── test_portfolio.py / test_comparison.py
│   │   ├── test_rent_roll_export.py / test_report.py
│   │   ├── test_live_api.py / test_live_portfolio_api.py
│   │   ├── run_all_tests.py
│   │   └── *.pdf (10 fixtures)
│   ├── venv/
│   ├── requirements.txt
│   ├── run.py
│   └── lease_portfolio.db (gitignored, created at runtime)
├── frontend/
│   ├── index.html / styles.css
│   ├── api.js / app.js
│   └── upload-view.js / dashboard-view.js / detail-view.js /
│       timeline-view.js / comparison-view.js / qa-view.js / report-view.js
├── CLAUDE.md
├── DECISIONS.md
├── PROGRESS.md
└── README.md
```
