# Lease Abstraction Tool

A full-stack web application for extracting structured data from lease PDF documents.

## Overview

This tool helps automate the extraction of key information from lease agreements. Upload a PDF lease document, and the tool will automatically extract:

- Tenant name
- Monthly rent amount
- Lease start date
- Lease end date

Each extracted field includes source attribution showing the page number and exact quote from the PDF where the information was found.

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
- Text extraction from PDF documents
- Regex-based pattern matching for common lease fields
- Source attribution (page number + quote) for each field
- CORS enabled for frontend integration

### Frontend
- Clean, modern UI with drag-and-drop upload
- Real-time extraction results display
- Source attribution for transparency
- Clear indication of found vs. not-found fields
- JSON export functionality
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

**Response:**
```json
{
  "tenant": {
    "value": "John Smith",
    "source": {
      "page": 1,
      "quote": "Tenant: John Smith hereby agrees..."
    }
  },
  "rent_amount": {
    "value": "$2,500.00",
    "source": {
      "page": 1,
      "quote": "Monthly Rent: $2,500.00 due on..."
    }
  },
  "lease_start_date": {
    "value": "January 1, 2024",
    "source": {
      "page": 1,
      "quote": "Lease Start Date: January 1, 2024"
    }
  },
  "lease_end_date": {
    "value": "December 31, 2024",
    "source": {
      "page": 1,
      "quote": "Lease End Date: December 31, 2024"
    }
  }
}
```

Fields not found will have `"value": null` and `"source": null`.

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
2. Add a new extraction method (e.g., `_extract_landlord`)
3. Add the field to the `extract_fields` method return dictionary
4. Update frontend field labels in `frontend/app.js`

### Extending the Frontend

The frontend is intentionally simple and modular:
- `index.html` - Markup structure
- `app.js` - All JavaScript logic
- `styles.css` - All styling with CSS variables for easy theming

To customize:
- Update CSS variables in `:root` for colors and spacing
- Modify `fieldLabels` object in `app.js` for field display names
- Add new sections to `index.html` as needed

## Known Limitations

- Text-based PDFs only (scanned images require OCR - not yet implemented)
- Pattern matching may need tuning for specific lease formats
- Returns first match only (doesn't handle duplicate fields)
- No authentication or user management

## Future Enhancements

- OCR support for scanned PDFs (backend has pytesseract available)
- Machine learning models for more robust extraction
- Additional fields (landlord, property address, security deposit, etc.)
- Batch processing of multiple PDFs
- User accounts and saved extractions
- Confidence scores for extracted values
- Custom field definitions

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
