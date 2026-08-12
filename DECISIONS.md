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

## Extraction Engine Rework (2026-08-12, session 2)

The original 4-field extractor only matched rigid "Label: Value" phrasing
(e.g. "Monthly Rent: $2,500.00"). It silently returned "Not Found" for the
narrative sentence structure real commercial leases actually use ("...the
sum of $6,250.00 per month...", "Blue Sky Coffee Roasters, Inc. (\"Tenant\")").
This session reworked the extraction engine and expanded it from 4 to 14
fields, added confidence scoring, and hardened it against messier input.

### Pattern strategy: ordered fallback, most-reliable-first
Every field tries several regex strategies in priority order (label style →
prose style → loose fallback), stopping at the first match. Each strategy is
tagged with a confidence tier (high/medium/low) reported alongside the
value, so a human reviewer knows how much to trust a given extraction
without having to inspect the source quote themselves.
- **Reason**: A single rigid pattern per field can't cover both "Field:
  Value" documents and narrative legal prose. Trying multiple strategies
  and keeping the most specific one lets the tool handle both without
  guessing silently — a field found via a loose fallback is visibly lower
  confidence than one found via an explicit label.

### Bounded "gap" instead of requiring keyword/value adjacency
A keyword and its value are matched with a bounded, period-excluding gap
between them (`[^.$]{0,100}?`) rather than requiring immediate adjacency.
This lets patterns match "shall commence on April 1, 2025" or "base rent
... the sum of $6,250.00 per month" without also running past the end of
the sentence into unrelated text.
- **Reason**: This is the core fix for the Part 1 bug. Requiring immediate
  adjacency is what caused rent/date extraction to fail on prose lease
  text in the first place.

### Whole-document search, not page-by-page
All extractors search the full document text (pages joined, with an
offset-to-page-number map for source attribution) rather than looping
page by page.
- **Reason**: Two problems with page-by-page search: (1) a keyword and its
  value can legitimately be split across a page break in a real multi-page
  lease, and neither page's text alone contains the full clause; (2) it
  made pattern priority page-dependent — a low-confidence match on page 1
  would win over a high-confidence match on page 2 just because it was
  checked first. Searching the whole document fixes both.

### Case-sensitivity is scoped per-pattern, not global
`_search_ordered` defaults to `re.IGNORECASE`, but party-name extraction
(tenant/landlord) explicitly passes `flags=0` and scopes case-insensitive
keywords locally with `(?i:...)`.
- **Reason**: Found during Part 4 robustness testing — a blanket
  `re.IGNORECASE` flag makes `[A-Z]`/`[a-z]` character classes stop
  meaning "a capitalized word," since both classes then match either
  case. That silently defeats the capitalization heuristic used to bound
  where a proper name ends, causing catastrophic over-capture on casual
  phrasing (captured "Jordan Blake and the tenant is Alex Chen" instead of
  "Jordan Blake"). Any future pattern whose capture group relies on
  `[A-Z]`/`[a-z]` to detect real capitalization must follow the same
  scoping approach.

### Confidence tiers reflect match directness, not just field type
Confidence is assigned per matching *strategy*, not per field: an explicit
label always scores high regardless of which field it's on; a reversed-
order match (value before its keyword, e.g. "...the sum of $12,500.00 as a
security deposit") scores medium; a generic fallback with little
disambiguating context scores low. Composite fields (renewal options)
grade confidence by how many of their expected sub-parts (notice period,
renewal basis) were actually corroborated in the text.
- **Reason**: This is what the Part 3 requirement ("confidence based on how
  directly the source text matches expected patterns") actually calls for
  — a fixed per-field confidence wouldn't distinguish an unambiguous label
  match from a loose proximity-based guess on the same field.

### Ambiguous keyword matches are disambiguated by proximity, not document order
Default/cure period extraction scans every "(N) days ... written notice"
candidate in the document and prefers the one with "default"/"cure" nearby,
rather than taking the first match found.
- **Reason**: Found during Part 4 testing — a lease can have several
  unrelated "(N) days ... written notice" clauses (renewal notice, cure
  notice), and blindly taking the first one in document order picked up
  the wrong clause when the renewal section happened to come first.

### Synthetic test documents as the primary robustness signal
Rather than relying only on real leases (sensitive, hard to source safely)
or a single stylized sample, this session built 3 additional synthetic
lease PDFs (`retail_lease.pdf`, `office_lease.pdf`, `casual_sublease.pdf`)
each with deliberately different section structure, sentence phrasing,
currency/date formatting, and drafting formality, plus a field-by-field
accuracy report (`test_synthetic_accuracy.py`) across all 5 fixtures.
- **Reason**: A single "does it pass" test document can't reveal phrasing-
  specific gaps. Testing against meaningfully different documents is what
  actually surfaced the case-sensitivity bug, the heading-period bug, and
  the ambiguous-keyword bug above — all three were invisible against the
  original two fixtures.

### OCR fallback verified with mocks, not a live run
This dev environment has no tesseract/poppler installed and no package
manager available to install them. The OCR trigger condition, success
path, and failure-degrades-gracefully path are verified with
`unittest.mock` against the real `pdf_extractor.py` code (not rewritten
test doubles), rather than skipped entirely.
- **Reason**: Verifying the logic is still valuable even without live OCR
  — it confirms the fallback actually triggers on sparse text, that OCR
  output flows into field extraction normally, and that an OCR failure
  degrades to an empty page list instead of raising and crashing the
  request. A live end-to-end run against a real scanned PDF should still
  happen in an environment with those binaries before relying on this path
  in production — see `PROGRESS.md` known limitations.

### Frontend: grouped display + inline editing + confidence badges
Results are grouped into Parties / Financial Terms / Dates & Term /
Special Clauses (`FIELD_GROUPS` in `app.js`) instead of one flat grid.
Confidence renders as a color-coded badge per field. Clicking a value
turns it into an inline text input; committing a correction sets an
`edited: true` flag on that field, which is included in the JSON export.
- **Reason**: Matches the Part 6 requirements directly. The `edited` flag
  (rather than silently overwriting) preserves the distinction between
  "the tool found this" and "a human corrected this" through to export,
  which matters for an abstraction tool whose whole premise is
  human-verifiable extraction.

### Frontend verified via jsdom against real backend output, not just read
No browser automation tool was available in this environment. Instead of
relying on static code review alone, a scratch jsdom harness loads the
actual unmodified `index.html`/`app.js`, mocks `fetch` to return real
`/extract` responses (captured from the live backend against real test
PDFs), and drives the exact `processFile()` entry point the browser uses
on upload — then asserts on the resulting DOM and on the actual JSON blob
captured from `exportJSON()`.
- **Reason**: This is a meaningfully stronger check than reading the
  source, since it executes the real code through the real entry point
  and catches issues static review would miss (e.g. an early version of
  this harness itself revealed a scoping mistake in test setup, not the
  app — but the point of running it was to catch exactly that class of
  false confidence). It is still not a substitute for a literal browser
  click-through; that should be done manually — see `PROGRESS.md` for
  what to check.
