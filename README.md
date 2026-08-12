# Lease Abstraction Tool

A full-stack web application for extracting structured data from lease PDF documents.

## Overview

This tool helps automate the extraction of key information from commercial lease agreements. Upload a PDF lease document, and the tool will automatically extract 14 fields:

**Parties**: tenant name, landlord name, property address
**Financial terms**: monthly rent, security deposit, CAM charges, rent escalation schedule, insurance requirements
**Dates & term**: lease start/end dates, renewal options, default/cure period
**Special clauses**: permitted use, exclusivity clause

Each extracted field includes source attribution (page number + exact quote) and a confidence level (high/medium/low) reflecting how directly the source text matched the expected pattern, so a human reviewer knows what to double-check.

## Project Structure

```
lease-abstraction/
├── backend/          # Flask API server
│   ├── app/          # Application code
│   │   ├── api.py              # API endpoints
│   │   ├── pdf_extractor.py    # PDF text extraction
│   │   └── field_extractor.py  # Field pattern matching
│   ├── tests/        # Test files and sample PDFs
│   ├── run.py        # Server entry point
│   └── README.md     # Backend documentation
│
└── frontend/         # Web UI
    ├── index.html    # Main page structure
    ├── app.js        # Application logic
    ├── styles.css    # Styling
    └── README.md     # Frontend documentation
```

## Quick Start

### 1. Start the Backend

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Start the server
python run.py
```

The backend API will run on `http://localhost:5000`

### 2. Start the Frontend

In a new terminal:

```bash
# Navigate to frontend directory
cd frontend

# Start a simple web server (Python 3)
python3 -m http.server 8080
```

Open your browser to `http://localhost:8080`

### 3. Use the Application

1. Drag and drop a lease PDF onto the upload area (or click to browse)
2. Wait for processing to complete
3. Review the extracted fields with their source citations
4. Export results as JSON if needed

## Features

### Backend
- RESTful API with `/extract` endpoint
- Text extraction from PDF documents, with OCR fallback (pytesseract + poppler) for scanned/image-based PDFs
- Regex-based pattern matching for 14 lease fields, tuned for both rigid "Label: Value" formatting and narrative legal prose
- Per-field confidence scoring (high/medium/low)
- Source attribution (page number + quote) for each field, correctly attributed even when a field's keyword and value are split across a page break
- CORS enabled for frontend integration

### Frontend
- Clean, modern UI with drag-and-drop upload
- Results grouped into Parties, Financial Terms, Dates & Term, and Special Clauses
- Color-coded confidence badge per field
- Click-to-edit inline correction of any extracted value before export
- JSON export includes value, source, confidence, and edited-flag for every field
- Session Stats panel (localStorage-backed) tracking fields-found and confidence breakdown across documents processed in the browser session
- Fully responsive design

## Technology Stack

**Backend:**
- Python 3.8+
- Flask - Web framework
- PyPDF2 - PDF text extraction
- flask-cors - CORS support

**Frontend:**
- Vanilla JavaScript - No frameworks
- Modern CSS (Grid, Flexbox)
- HTML5 - Semantic markup

## API Documentation

### POST /extract

Extract lease data from PDF file.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: `file` field containing PDF (max 16MB)

**Response:** one entry per field (`tenant`, `landlord`, `rent_amount`, `lease_start_date`, `lease_end_date`, `property_address`, `security_deposit`, `cam_charges`, `rent_escalation`, `renewal_options`, `permitted_use`, `exclusivity_clause`, `insurance_requirements`, `default_cure_period`), each shaped as:
```json
{
  "rent_amount": {
    "value": "$6,250.00",
    "source": {
      "page": 1,
      "quote": "...base rent for the Premises the sum of $6,250.00 per month, payable..."
    },
    "confidence": "high"
  }
}
```

Fields not found will have `"value": null`, `"source": null`, and `"confidence": null`.

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

## Development

### Adding New Fields

To extract additional fields:

1. Edit `backend/app/field_extractor.py`
2. Add a new extraction method following the existing pattern (label-style + prose-style + confidence tier per strategy — see the module docstring)
3. Add the field to the `extract_fields` method return dictionary
4. Add the field to `FIELD_LABELS` and the appropriate group in `FIELD_GROUPS` in `frontend/app.js`

### Extending the Frontend

The frontend is intentionally simple and modular:
- `index.html` - Markup structure
- `app.js` - All JavaScript logic
- `styles.css` - All styling with CSS variables for easy theming

To customize:
- Update CSS variables in `:root` for colors and spacing
- Modify `FIELD_LABELS` / `FIELD_GROUPS` in `app.js` for field display names and grouping
- Add new sections to `index.html` as needed

## Testing

`backend/tests/` contains the test suite and PDF fixtures:
- `test_extraction.py` — validates all 14 fields against the residential (`sample_lease.pdf`) and commercial (`sample_lease_commercial.pdf`) fixtures
- `test_synthetic_accuracy.py` — runs extraction against 5 documents (the 2 above plus 3 synthetic leases with deliberately different structure/phrasing/formatting/formality) and prints a field-by-field accuracy summary
- `test_multipage_field.py` — confirms a field split across a page break is still found
- `test_ocr_fallback.py` — confirms the OCR fallback trigger/success/failure logic (mocked, since this dev environment has no tesseract/poppler installed)
- `create_sample_lease.py`, `create_commercial_lease.py`, `create_synthetic_leases.py` — regenerate the PDF fixtures

Run any of them with `python <file>.py` from `backend/` (with the venv activated).

## Known Limitations

- Regex-based extraction, not ML/NLP — accuracy depends on the pattern library covering the phrasing a given lease uses. See `PROGRESS.md` for current measured accuracy and known weak spots.
- Returns the first (or best-scoring, for a few disambiguated fields) match only — doesn't handle a lease that legitimately has multiple values for the same field.
- No authentication or user management
- OCR fallback logic is verified with mocks, not a live run — this dev environment has no tesseract/poppler installed. Should be validated against a real scanned PDF in an environment with those binaries before relying on it in production.

## Future Enhancements

See the prioritized list in `PROGRESS.md`.

## Troubleshooting

**Backend won't start:**
- Ensure Python 3.8+ is installed
- Install dependencies: `pip install -r requirements.txt`
- Check port 5000 is not in use

**Frontend shows CORS errors:**
- Ensure backend is running
- flask-cors should be installed (included in requirements.txt)

**No text extracted:**
- PDF may be image-based (requires OCR)
- PDF may be corrupted or encrypted

**Fields not found:**
- Lease format may differ from expected patterns
- Check backend logs for pattern matching details
- Patterns can be adjusted in `field_extractor.py`

## Contributing

This is a learning project. Feel free to fork and enhance!

## License

This is a learning project. Use freely.
