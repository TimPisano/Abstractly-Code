# Lease Portfolio Backend

A Python/Flask backend that extracts 15 structured fields from commercial
lease PDFs (with source page/quote and a confidence level on every
field), persists them in SQLite as a portfolio, and analyzes that
portfolio: risk/anomaly detection, grounded natural-language Q&A,
lease comparison and benchmarking, rent roll export, and a printable
summary report. See the repo root `README.md` for the full picture;
this file covers backend-specific setup and API detail.

## Features

- 15-field extraction (tenant, landlord, rent, dates, address, deposit, CAM, escalation, renewal, permitted use, exclusivity, insurance, default/cure, square footage) with per-field confidence and source page/quote
- Digital + scanned PDFs (OCR fallback via pytesseract/pdf2image)
- Persisted portfolio (SQLite): single or batch upload, amendments linked to a base lease
- Risk/anomaly detection: below-market rent, missing clauses, notice-period outliers, one-sided terms, internal inconsistencies — rule-based, every flag cites real numbers
- Deterministic (non-LLM) Q&A with citations grounded in real stored data
- Portfolio metrics, expiration timeline, side-by-side comparison, benchmarking
- CSV/Excel rent roll export, printable HTML portfolio report
- RESTful Flask API, CORS enabled, graceful error handling throughout

## Requirements

- Python 3.8+
- Tesseract OCR (for scanned PDFs)
- Poppler (for PDF to image conversion)

### System Dependencies

**macOS:**
```bash
brew install tesseract poppler
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr poppler-utils
```

**Windows:**
- Download Tesseract installer from: https://github.com/UB-Mannheim/tesseract/wiki
- Download Poppler from: https://github.com/oschwartz10612/poppler-windows/releases
- Add both to your PATH

## Installation

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Running the Server

Start the Flask development server:

```bash
python run.py
```

Or run the API module directly:

```bash
python -m app.api
```

The server will start at `http://localhost:5000`

## API Endpoints

Full request/response JSON examples (extraction, risk flags, Q&A) are
in the repo root `README.md`. Summary here:

### Stateless extraction (no persistence)

- `POST /extract` — multipart `file` field, PDF only. Returns 15 fields, each `{"value", "source": {"page", "quote"}, "confidence"}`; not-found fields have all three `null`.
  ```bash
  curl -X POST -F "file=@path/to/lease.pdf" http://localhost:5000/extract
  ```

### Persisted leases (portfolio)

- `POST /leases` — upload + persist one PDF as a base lease
- `POST /leases/batch` — multipart `files` field (repeat for each file); each processed independently, response includes a per-file success/error list
- `GET /leases` / `GET /leases/<id>` — list / detail (amendment-merged "effective" fields)
- `DELETE /leases/<id>` — also removes its amendments
- `POST /leases/<id>/amendments` — upload a PDF and link it as an amendment; its fields override the base lease's in the effective view
- `GET /leases/<id>/amendments` — list amendments for a lease

### Portfolio analysis

- `GET /portfolio/summary` — totals/averages (rent, CAM, deposit, escalation, notice period, sq ft), per-field missing counts
- `GET /portfolio/timeline` — leases bucketed by months-until-expiration
- `GET /portfolio/risks` / `GET /leases/<id>/risks` — risk flags (portfolio-wide / one lease)
- `POST /qa` — body `{"question": str, "lease_id": int (optional)}`; omit `lease_id` for a portfolio-wide question
- `GET /leases/compare?ids=1,2,3` — side-by-side field values for 2+ leases
- `GET /leases/<id>/benchmark` — one lease vs. every other lease in the portfolio
- `GET /portfolio/rent-roll.csv` / `GET /portfolio/rent-roll.xlsx` — rent roll export
- `GET /portfolio/report` — self-contained printable HTML portfolio summary

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

## Testing

Run everything at once:
```bash
cd tests
python run_all_tests.py          # 10 unit tests, no server needed
python run_all_tests.py --live   # + 2 live-API suites (backend must already be running)
```

Or individually — `test_extraction.py` / `test_synthetic_accuracy.py` (extraction accuracy across all 10 fixture PDFs), `test_multipage_field.py`, `test_ocr_fallback.py`, `test_risk_analysis.py`, `test_qa_engine.py`, `test_portfolio.py`, `test_comparison.py`, `test_rent_roll_export.py`, `test_report.py`, `test_live_api.py`, `test_live_portfolio_api.py` (self-cleaning — safe to re-run against the dev DB).

Regenerate PDF fixtures: `python create_sample_lease.py`, `create_commercial_lease.py`, `create_synthetic_leases.py`, `create_red_flag_leases.py` (the last one builds 5 documents with deliberate risk-detection issues, for exercising `risk_analysis.py`).

## Project Structure

```
backend/
├── app/
│   ├── api.py                  # Flask routes (extraction, leases, portfolio analysis)
│   ├── pdf_extractor.py        # PDF text extraction (+ OCR fallback)
│   ├── field_extractor.py      # 15-field regex extraction engine
│   ├── database.py             # SQLite persistence, amendments
│   ├── normalize.py            # Display-string -> real number/date parsing
│   ├── risk_analysis.py        # Rule-based risk/anomaly detection
│   ├── qa_engine.py            # Deterministic grounded Q&A
│   ├── portfolio.py            # Portfolio metrics + expiration timeline
│   ├── comparison.py           # Side-by-side compare + benchmarking
│   ├── rent_roll_export.py     # CSV / Excel export
│   └── report.py               # Printable HTML report
├── tests/                      # Automated suite + PDF fixture generators (see Testing)
├── requirements.txt
├── run.py
├── lease_portfolio.db          # SQLite (gitignored, created at runtime)
└── README.md
```

## How It Works

### PDF Text Extraction
1. **PyPDF2** first, for digitally-created PDFs
2. **OCR fallback** (pytesseract + pdf2image) if PyPDF2 yields under 100 characters — see `PROGRESS.md` for the "not live-verified in this dev environment" caveat

### Field Extraction
Each of the 15 fields tries several regex strategies in priority order (explicit label → narrative prose → loose fallback), stopping at the first match, tagged with a confidence tier (high/medium/low) reflecting how directly the match was found. See `field_extractor.py`'s module docstring and `DECISIONS.md` for the full design rationale — this is the most load-bearing file in the project and worth reading before modifying.

### Portfolio Analysis
`risk_analysis.py`, `qa_engine.py`, `portfolio.py`, and `comparison.py` all consume the same `extracted_fields` shape (via `normalize.py` for anything needing real numbers) and operate on lease records from `database.py`'s "effective" (amendment-merged) view — see `DECISIONS.md` for why each is rule-based rather than ML/LLM-based.

## Limitations

- Regex-based extraction, not ML/NLP — see `PROGRESS.md` for current measured accuracy
- Q&A only answers questions matching a known intent (deliberate — see `DECISIONS.md`)
- Risk thresholds are fixed constants, not yet configurable
- OCR fallback verified with mocks only, not a live scanned-PDF run
- No authentication/multi-user support

## Error Handling

- **Invalid file type / no file uploaded:** 400
- **Lease/amendment not found:** 404
- **PDF processing error:** 500 with a clear message
- **Field not found:** `value`/`source`/`confidence` all `null`, not an error
- **Batch upload:** each file's success/failure is independent — one bad file doesn't fail the rest

## Configuration

- **Max file size:** 16 MB per file (`app/api.py`)
- **Allowed file types:** PDF only
- **Server port:** 5000 (`app/api.py`)
- **OCR threshold:** 100 characters (`app/pdf_extractor.py`)
- **DB path:** `backend/lease_portfolio.db` (override via `database.configure()`, used by tests to isolate a temp DB)

## Troubleshooting

**"Tesseract not found" error:**
- Ensure tesseract is installed and in your PATH
- Try: `tesseract --version` to verify installation

**"Poppler not found" error:**
- Ensure poppler-utils is installed
- On macOS, check with: `which pdfinfo`

**OCR not working:**
- Verify tesseract installation
- Check that pdf2image can find poppler utilities

## License

This is a learning project. Use freely.
