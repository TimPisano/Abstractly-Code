# Lease Portfolio Intelligence

A full-stack application for extracting structured data from commercial
lease PDFs and analyzing them as a portfolio — not just one document at
a time.

## Overview

Upload one or many lease PDFs. The tool extracts 15 fields per lease
(with source page/quote and a confidence level on every field), then
goes beyond extraction into portfolio-level analysis:

- **Dashboard** — every lease in a sortable/filterable table, with portfolio metrics (total/average rent, CAM exposure, square footage) and an inline risk indicator
- **Risk detection** — a rule-based engine flags below-market rent, missing standard clauses, notice-period outliers, one-sided terms, and internal inconsistencies (bad escalation math, conflicting or reversed dates) — every flag explains itself with the actual numbers it fired on
- **Grounded Q&A** — ask plain-English questions ("which leases expire in the next year," "what's our total CAM exposure") and get answers assembled from real stored data with page-level citations; this is a deterministic rule engine, not an LLM, specifically so it can't hallucinate a number or a citation
- **Comparison & benchmarking** — side-by-side terms for 2+ leases, and single-lease-vs-portfolio-average benchmarking
- **Amendments** — link an amendment/addendum PDF to a base lease; its fields override the base lease's in an "effective" view used everywhere else
- **Exports** — CSV/Excel rent roll, and a one-page printable HTML portfolio summary report

**Extracted fields**: tenant, landlord, monthly rent, lease start/end
dates, property address, security deposit, CAM charges, rent
escalation, renewal options, permitted use, exclusivity clause,
insurance requirements, default/cure period, square footage.

## Project Structure

```
lease-abstraction/
├── backend/                    # Flask API + SQLite persistence
│   ├── app/
│   │   ├── api.py                  # Routes
│   │   ├── pdf_extractor.py         # PDF text extraction (+ OCR fallback)
│   │   ├── field_extractor.py        # 15-field regex extraction engine
│   │   ├── database.py                # SQLite persistence, amendments
│   │   ├── normalize.py                # Display-string -> real number/date parsing
│   │   ├── risk_analysis.py             # Rule-based risk/anomaly detection
│   │   ├── qa_engine.py                  # Deterministic grounded Q&A
│   │   ├── portfolio.py                   # Portfolio metrics + expiration timeline
│   │   ├── comparison.py                   # Side-by-side compare + benchmarking
│   │   ├── rent_roll_export.py              # CSV / Excel export
│   │   └── report.py                         # Printable HTML report
│   ├── tests/                  # Automated test suite + PDF fixtures
│   ├── run.py
│   └── README.md
│
└── frontend/                   # Multi-view vanilla JS app
    ├── index.html                  # App shell + sidebar nav
    ├── api.js / app.js              # API client / router + shared state
    ├── *-view.js                     # One file per view
    ├── styles.css
    └── README.md
```

## Quick Start

### 1. Start the Backend

```bash
cd backend
source venv/bin/activate   # or: python3 -m venv venv && pip install -r requirements.txt
python run.py
```
Runs on `http://localhost:5000`. Confirm: `curl http://localhost:5000/health`

### 2. Start the Frontend

```bash
cd frontend
python3 -m http.server 8080
```
Open `http://localhost:8080`

### 3. Use It

1. **Upload Leases** — drag in one or many PDFs; a batch reports per-file success/failure so one bad file doesn't block the rest
2. **Dashboard** — see the whole portfolio, sort/filter, spot risk flags at a glance
3. Click into a lease for the **Detail** view — grouped fields, inline editing, risk explanations, amendments, and a per-lease Q&A box
4. **Expirations** — renewal risk timeline
5. **Compare** — pick 2+ leases for a side-by-side + benchmark view
6. **Ask a Question** — portfolio-wide grounded Q&A
7. **Portfolio Report** — printable/downloadable one-page summary

## Technology Stack

**Backend:** Python 3.8+, Flask, PyPDF2 (+ pytesseract/pdf2image for OCR), SQLite (stdlib `sqlite3`), openpyxl (Excel export)
**Frontend:** Vanilla JavaScript, no framework/build step — CSS Grid/Flexbox, semantic HTML5

## API Documentation

Two layers:

- **Stateless**: `POST /extract` — extract without persisting (unchanged since the tool's first version)
- **Persisted portfolio**: `POST /leases` (single), `POST /leases/batch` (multi, per-file error recovery), `GET /leases`, `GET /leases/<id>`, `DELETE /leases/<id>`, `POST`/`GET /leases/<id>/amendments`, `GET /portfolio/summary`, `GET /portfolio/timeline`, `GET /portfolio/risks`, `GET /leases/<id>/risks`, `POST /qa`, `GET /leases/compare?ids=1,2,3`, `GET /leases/<id>/benchmark`, `GET /portfolio/rent-roll.csv`, `GET /portfolio/rent-roll.xlsx`, `GET /portfolio/report`

Every extracted field is shaped:
```json
{
  "rent_amount": {
    "value": "$6,250.00",
    "source": { "page": 1, "quote": "...the sum of $6,250.00 per month, payable..." },
    "confidence": "high"
  }
}
```
Not-found fields have `value`, `source`, and `confidence` all `null`.

A risk flag:
```json
{
  "severity": "high",
  "category": "below_market_rent",
  "field": "rent_amount",
  "message": "Rent ($2,250/mo) is 34% below the portfolio average ($3,420/mo)",
  "explanation": "Comparing on rent per square foot, this lease is at $1.50/sq ft/mo against a portfolio average of $2.29/sq ft/mo — 34.5% below. ..."
}
```

A Q&A response:
```json
{
  "answer": "2 of 10 lease(s) expire within the next 12 month(s)...",
  "citations": [{"lease_id": 5, "filename": "casual_sublease.pdf", "field": "lease_end_date", "page": 1, "quote": "..."}],
  "confidence": "answered",
  "matched_intent": "list_expiring"
}
```

### GET /health
```json
{ "status": "healthy" }
```

## Testing

`backend/tests/` — run everything with `python run_all_tests.py` (unit tests) or `python run_all_tests.py --live` (also runs the live-API integration suites; backend must already be running):

- **Unit tests** (no server needed): `test_extraction.py`, `test_synthetic_accuracy.py` (field accuracy across all 10 PDF fixtures), `test_multipage_field.py`, `test_ocr_fallback.py`, `test_risk_analysis.py`, `test_qa_engine.py`, `test_portfolio.py`, `test_comparison.py`, `test_rent_roll_export.py`, `test_report.py`
- **Live API integration** (backend must be running): `test_live_api.py`, `test_live_portfolio_api.py` (48 checks against the real HTTP layer — batch upload error recovery, amendments, all analysis endpoints, exports, error paths; self-cleaning, safe to re-run)
- **Fixture generators**: `create_sample_lease.py`, `create_commercial_lease.py`, `create_synthetic_leases.py`, `create_red_flag_leases.py` (the last one builds 5 documents with deliberate risk-detection issues)

## Known Limitations

- Regex-based extraction, not ML/NLP — see `docs/PROGRESS.md` for measured accuracy and known weak spots
- Q&A only answers questions matching a known intent pattern (by design — see `docs/DECISIONS.md` for why this trades coverage for zero-hallucination guarantees)
- Risk thresholds are fixed constants, not yet tunable per portfolio
- OCR fallback logic verified with mocks only — no tesseract/poppler in this dev environment
- No authentication/multi-user support; SQLite is right-sized for single-user/local use, not a hosted multi-tenant deployment

## Future Enhancements

See the prioritized list in `docs/PROGRESS.md`.

## Troubleshooting

**Backend won't start** — check Python 3.8+, `pip install -r requirements.txt`, port 5000 free
**Frontend shows CORS/network errors** — confirm the backend is actually running (`curl http://localhost:5000/health`)
**Upload fails** — PDF only, 16MB max per file; check the per-file error message in a batch, don't assume the whole batch failed
**"I don't have a way to answer that yet"** — expected for questions outside the Q&A engine's supported intents, not a bug
**No text extracted** — PDF may be image-based (needs OCR) or corrupted/encrypted

## Contributing

This is a learning project. Feel free to fork and enhance!

## License

This is a learning project. Use freely.
