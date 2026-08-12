# Lease PDF Extraction Backend

A Python backend service for extracting key information from lease PDF documents using PyPDF2 and OCR fallback.

## Features

- Extracts tenant name, rent amount, lease start date, and lease end date
- Supports both digital and scanned PDFs (with OCR fallback)
- Returns source information (page number and quote) for each extracted field
- RESTful API built with Flask
- Handles "not found" cases gracefully

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

### POST /extract

Extracts lease information from an uploaded PDF file.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: Form data with a 'file' field containing the PDF

**Example using curl:**
```bash
curl -X POST -F "file=@path/to/lease.pdf" http://localhost:5000/extract
```

**Response:**
```json
{
  "tenant": {
    "value": "John Smith",
    "source": {
      "page": 1,
      "quote": "Landlord: Property Management LLC\nTenant: John Smith\n\nPROPERTY:"
    }
  },
  "rent_amount": {
    "value": "$2,500.00",
    "source": {
      "page": 1,
      "quote": "RENT:\nMonthly Rent: $2,500.00\nPayment Due: 1st of each month"
    }
  },
  "lease_start_date": {
    "value": "January 15, 2024",
    "source": {
      "page": 1,
      "quote": "LEASE TERMS:\nLease Start Date: January 15, 2024\nLease End Date: January 14, 2025"
    }
  },
  "lease_end_date": {
    "value": "January 14, 2025",
    "source": {
      "page": 1,
      "quote": "Lease Start Date: January 15, 2024\nLease End Date: January 14, 2025\nTerm: 12 months"
    }
  }
}
```

**For fields not found:**
```json
{
  "tenant": {
    "value": null,
    "source": null
  }
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

## Testing

### Create Sample Lease PDF

Generate a sample lease PDF for testing:

```bash
cd tests
python create_sample_lease.py
```

This creates `tests/sample_lease.pdf` with sample lease data.

### Run Extraction Test

Test the extraction pipeline:

```bash
cd tests
python test_extraction.py
```

This will:
1. Extract text from the sample PDF
2. Extract all fields
3. Display results in JSON format
4. Validate extracted values against expected values

## Project Structure

```
backend/
├── app/
│   ├── __init__.py          # Package initialization
│   ├── api.py               # Flask API endpoints
│   ├── pdf_extractor.py     # PDF text extraction (with OCR fallback)
│   └── field_extractor.py   # Field extraction logic
├── tests/
│   ├── create_sample_lease.py  # Generate sample PDF
│   ├── test_extraction.py      # Test extraction pipeline
│   └── sample_lease.pdf        # Generated sample PDF (after running create script)
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## How It Works

### PDF Text Extraction

1. **PyPDF2 (Digital PDFs):** First attempts to extract text using PyPDF2, which works for digitally-created PDFs
2. **OCR Fallback (Scanned PDFs):** If PyPDF2 extraction yields poor results (< 100 characters), automatically falls back to OCR using pytesseract + pdf2image

### Field Extraction

Uses regex patterns and keyword matching to find:

- **Tenant Name:** Looks for patterns like "Tenant:", "Lessee:", "Tenant Name:"
- **Rent Amount:** Looks for patterns like "Monthly Rent:", "Rent:", "Rental Amount:" followed by dollar amounts
- **Start Date:** Looks for "Start Date:", "Commencement Date:", "Beginning Date:"
- **End Date:** Looks for "End Date:", "Expiration Date:", "Termination Date:"

Each extraction includes:
- The extracted value
- Source page number
- A quote showing the context (50 characters before and after the match)

## Limitations & Future Improvements

**Current Limitations:**
- Uses simple regex patterns (no ML/NLP)
- May struggle with non-standard lease formats
- Date formats must match common patterns (MM/DD/YYYY or "Month DD, YYYY")

**Potential Improvements:**
- Add machine learning models for more robust extraction
- Support more date formats
- Extract additional fields (property address, landlord, etc.)
- Add confidence scores for extractions
- Implement caching for repeated extractions
- Add batch processing for multiple PDFs

## Error Handling

- **Invalid file type:** Returns 400 error
- **No file uploaded:** Returns 400 error
- **PDF processing error:** Returns 500 error with details
- **Field not found:** Returns null value with null source

## Configuration

- **Max file size:** 16 MB (configurable in `app/api.py`)
- **Allowed file types:** PDF only
- **Server port:** 5000 (configurable in `app/api.py`)
- **OCR threshold:** 100 characters (configurable in `app/pdf_extractor.py`)

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
