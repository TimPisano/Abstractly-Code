# Implementation Decisions

## Backend Structure (2026-08-12)

Built Python backend for lease PDF extraction with the following design choices:

### Architecture
- **Modular design**: Separated PDF extraction (`pdf_extractor.py`) from field extraction (`field_extractor.py`) for better maintainability
- **API layer**: Flask API (`api.py`) handles HTTP concerns separately from business logic
- **Reason**: This separation makes it easier to swap out components (e.g., add ML-based extraction later) without touching API code

### PDF Text Extraction Strategy
- **Primary method**: PyPDF2 for digital PDFs (fast, no external dependencies)
- **Fallback**: OCR using pytesseract + pdf2image when text extraction yields < 100 chars
- **Reason**: Most modern leases are digital PDFs, so PyPDF2 handles 90% of cases efficiently. OCR is slower but handles scanned documents when needed

### Field Extraction Approach
- **Method**: Regex patterns with keyword matching
- **Not using**: Machine learning or NLP models
- **Reason**:
  - Simpler to debug and maintain for a solo learning project
  - Sufficient for standardized lease formats
  - Can add ML layer later if needed without changing API contract
  - Lower deployment complexity (no model files to manage)

### JSON Response Format
Each field returns:
```json
{
  "value": "extracted value or null",
  "source": {
    "page": page_number,
    "quote": "context snippet"
  } or null
}
```
- **Reason**: Source information helps users verify extractions and debug issues. Null values are explicit about what wasn't found.

### File Organization
- `backend/app/`: Core application modules
- `backend/tests/`: Test utilities and sample data
- **Reason**: Standard Python project layout, familiar to most developers

### Dependencies
- Flask + flask-cors: Lightweight web framework
- PyPDF2: Pure Python PDF reader
- pdf2image + pytesseract: OCR fallback
- reportlab: Test PDF generation
- **Reason**: Minimal dependencies, all well-maintained libraries

### Testing Approach
- Created sample PDF generator to ensure reproducible tests
- Included validation script that checks extraction against known values
- **Reason**: Real lease PDFs contain sensitive data; generated test data is safer to commit

### Pre-existing Files
Found `app/extract.py` and `app/main.py` already in the codebase. These appear to be an earlier implementation attempt. Left them in place but built a new, more complete system with better separation of concerns.

### Future Improvements (not implemented)
- Machine learning models for more flexible extraction
- Support for more date formats
- Additional fields (property address, landlord, etc.)
- Confidence scores
- Batch processing

## Frontend Structure (2026-08-12)

Built minimal web UI for uploading PDFs and viewing extraction results.

### Technology Choice
- **Method**: Vanilla JavaScript, HTML5, and CSS3
- **Not using**: React, Vue, or other frameworks
- **Reason**:
  - Zero build tools or compilation steps required
  - Just serve static files - extremely simple deployment
  - Easy to understand and modify for a solo learning project
  - No framework overhead or dependency management
  - Perfect for learning fundamentals

### File Structure
- `frontend/index.html`: Single-page app structure
- `frontend/app.js`: Upload handling, API integration, result rendering
- `frontend/styles.css`: Modern CSS with Grid and Flexbox
- **Reason**: Simple three-file structure - easy to navigate and understand

### Key Features Implemented
1. **Drag-and-drop upload**: Visual feedback and click fallback
2. **File validation**: Type and size checks before upload
3. **Loading states**: Spinner and status messages
4. **Result display**: Card-based layout showing value, status, page, and quote
5. **Error handling**: Clear user-friendly error messages
6. **JSON export**: Download full extraction results
- **Reason**: These features meet the MVP requirement of "simple web UI to upload and view results"

### Design Choices
- **CSS variables**: Easy theming and color management
- **Status badges**: Green for "Found", gray for "Not Found" - clear visual distinction
- **Quote display**: Shows context snippet so users can verify extraction accuracy
- **Responsive layout**: Works on desktop and mobile using CSS Grid
- **Reason**: Aligns with quality bar of "show source so humans can verify"

### Integration Approach
- Backend API: `http://localhost:5000/extract`
- CORS already enabled in Flask backend
- Field mapping: Backend keys → user-friendly labels
- **Reason**: Clean separation - frontend and backend can be developed/deployed independently

### Server Options
Documented three ways to serve static files:
1. Python's http.server
2. Node's http-server
3. VS Code Live Server
- **Reason**: Solo developer might not have Node installed; Python is guaranteed since backend uses it
