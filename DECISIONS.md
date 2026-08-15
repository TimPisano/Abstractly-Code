# Implementation Decisions

## Production-Readiness Hardening (session 4)

A focused ~1-hour pass: real OCR verification, security/input-validation
review, performance testing. Full results in PROGRESS.md; this section
covers the decisions, not the test output.

### Debug mode: opt-in via FLASK_DEBUG, not hardcoded on
**Status: done.** Both `run.py` and `api.py`'s `__main__` block
previously hardcoded `app.run(debug=True, ...)`. Changed to read
`FLASK_DEBUG` from the environment, defaulting to off.
- **Reason**: confirmed live that Flask's interactive debugger (which
  `debug=True` enables) shows a full traceback, real filesystem paths,
  and an embedded Python console for any unhandled exception —
  triggered by nothing more exotic than an oversized integer in a URL
  path. That's fine for a developer debugging locally with the
  terminal in front of them; it's a serious information-disclosure
  risk for anything else. Making it opt-in (rather than removing it
  entirely) keeps the debugger available for local development without
  it being the default.

### Global error handlers return clean JSON regardless of debug mode
**Status: done.** Registered `@app.errorhandler` for 400/404/413/500
and a catch-all `Exception` handler in `api.py`, all returning a
generic `{"error": "..."}` body; the real exception is logged
server-side via `logger.exception(...)` in every case.
- **Reason**: Two problems needed one fix. First, several failure
  modes returned Flask/Werkzeug's *default* HTML error pages (a raw
  413 page for oversized uploads, a raw 404 page for unknown routes)
  instead of JSON, which the frontend's JSON-only error parsing
  couldn't use cleanly. Second, and more important: registering
  `@app.errorhandler(Exception)` turns out to intercept an exception
  *before* it reaches Werkzeug's interactive-debugger path, even with
  `debug=True` — verified this directly, not assumed from
  documentation. That means local `FLASK_DEBUG=1` debugging and
  "never leak a traceback to a client" aren't actually in tension:
  the handler catches it first either way, and only the terminal
  running the server sees the real exception.

### Oversized/out-of-range lease IDs are "not found," not a crash
**Status: done.** `database.get_lease()` catches `OverflowError` and
returns `None`.
- **Reason**: this is the actual root cause of the debugger-leak
  finding above (an id like `9` × 34 digits overflows SQLite's signed
  64-bit `INTEGER` column). Fixing it at the single lowest layer
  (`get_lease`, which `get_effective_lease` and therefore every route
  built on it calls first) means every route that checks "does this
  lease exist" before doing anything else — detail, delete, risks,
  benchmark, amendments, compare — automatically returns a proper 404
  instead of relying on the generic exception handler as a safety net.
  Fixing the specific cause is more correct than only fixing the
  generic symptom, even though the generic handler would have masked
  it either way.

### OCR binaries via conda-forge, not Homebrew
**Status: done.** Got real `tesseract`/`poppler` working via a
Miniforge (conda-forge) install to `~/.miniforge3`, after Homebrew —
even installed to a user-owned prefix specifically to avoid needing
sudo — failed.
- **Reason**: Homebrew bottles (precompiled binaries) are built for
  the *standard* prefix (`/opt/homebrew` on Apple Silicon); installing
  to a non-standard user-owned prefix to dodge the sudo requirement for
  creating `/opt/homebrew` meant Homebrew couldn't use those bottles
  for at least poppler/tesseract's build chain, and fell back to
  compiling from source — which then failed because this machine's
  Xcode Command Line Tools are older than the build requires, and
  updating them needs either sudo (`xcode-select --install`) or
  interactive System Settings, neither available in this session.
  Conda-forge packages are precompiled for a relocatable install
  location by design (conda environments are *meant* to live anywhere,
  unlike Homebrew's bottle system), so the same "can't use sudo, can't
  use the GUI" constraint didn't block it. This is genuinely a
  workaround for this specific machine's state (an outdated CLT
  version), not a general statement that Homebrew is the wrong choice
  — a machine with current Command Line Tools, or with sudo access,
  would likely succeed with plain Homebrew.
- **Consequence**: OCR now depends on `~/.miniforge3/bin` being on
  `PATH` when the backend starts. This lives outside the repo (home
  directory) and outside `requirements.txt` (it's system binaries, not
  Python packages) since it's a machine-level install. See PROGRESS.md
  for the exact restart commands and for how to reproduce this install
  from scratch if the environment is ever reset.

## Portfolio Intelligence Expansion (2026-08-12, session 3)

This section was updated live as work happened, not just at the end,
per explicit instruction — the per-decision "Status" lines below were
the running record during the session and are now all "done."

### Scope
Moving from single-lease extraction to portfolio-level intelligence:
multi-lease upload/storage, a portfolio dashboard, expiration timeline,
risk/anomaly detection, a grounded natural-language Q&A interface,
lease-vs-lease comparison and benchmarking, batch upload with per-file
error recovery, amendment linking, rent roll export, and a printable
portfolio summary report.

### Persistence: SQLite via Python's stdlib `sqlite3`, not a new dependency
**Status: done.**
Portfolio features (sort/filter across leases, aggregate averages, link
amendments to a base lease) genuinely require queryable persistence —
the previous session's browser-localStorage-only state can't support
this. Chose `sqlite3` (stdlib, zero new dependency) over a JSON-file
store or a heavier ORM/database.
- **Reason**: Keeps the "minimal dependencies" philosophy from session 1
  while giving real query capability (filtering, sorting, joins for
  amendments) that a flat JSON file would make painful to maintain
  correctly as the number of leases grows. A learning-project scale
  (dozens to low hundreds of leases) is exactly SQLite's sweet spot.
- **Schema**: single `leases` table — `id`, `filename`, `uploaded_at`,
  `extracted_fields` (JSON blob of the existing 14/15-field extraction
  result, unchanged shape), `document_type` ('lease' or 'amendment'),
  `base_lease_id` (NULL for base leases, FK to the base lease for an
  amendment). An "effective" lease view merges a base lease's fields
  with its most recent amendment's non-null fields (amendment overrides
  base per-field) — see `database.py: get_effective_lease()`.

### New field: square_footage (15th extracted field)
**Status: done.**
Added to support "average rent per square foot" portfolio metric, which
the brief explicitly conditions on square footage being extracted.
- **Reason**: Needed as an input to a specific requested metric; follows
  the same label-style/prose-style pattern-matching approach as every
  other field in `field_extractor.py`.

### Normalization layer for portfolio math
**Status: done.**
`app/normalize.py` — parses the extractor's *display strings* ("$6,250.00",
"April 1, 2025", "3% annually", "10 days after written notice") into
actual numbers/dates for aggregation, comparison, and risk-threshold
checks. Shared by every downstream module (risk analysis, portfolio
metrics, comparison, Q&A, rent roll export).
- **Reason**: The extraction engine's job is to produce human-readable,
  source-verifiable strings, not machine-typed values — that's the right
  design for the extraction layer, but portfolio math needs real numbers.
  Building this parsing once as a shared utility avoids every downstream
  module re-implementing (and subtly disagreeing on) currency/date
  parsing.

### Q&A engine: deterministic intent-matching, NOT an LLM call
**Status: done, independently verified.** `app/qa_engine.py`, built by a
parallel subagent. Re-ran its tests myself, confirmed no network/LLM
imports, then ran the brief's own example questions against real
extracted data from actual test PDFs — each answered correctly with
citations traced back to real stored source data.
The brief asks for "an accurate answer grounded in the actual extracted/
source data — not a hallucinated answer," with citations. Built as a
rule-based natural-language query engine: pattern-match the question
against a set of known intents (list-expiring, aggregate-field,
field-lookup-on-lease, has-clause, etc.), execute a real query against
the SQLite-stored extracted data, and construct the answer directly from
stored values with a citation (lease name + page + quote) pulled from
the actual stored source. Unsupported questions get an honest "I can't
answer that yet" rather than a guess.
- **Reason**: An LLM-generated answer — even a good one — can hallucinate
  a number or misattribute a citation, which is exactly what the brief
  says to avoid. A deterministic query engine cannot fabricate a value:
  it either finds a real stored fact and returns it with its real
  source, or it says it doesn't know. The tradeoff is coverage (only
  questions matching a known intent pattern are answerable) rather than
  open-ended chat — a deliberate choice given the "not hallucinated"
  requirement is explicit and non-negotiable in the brief. No API keys,
  no external LLM dependency, no per-query cost.

### Risk detection: rule-based thresholds + cross-field consistency checks
**Status: done.** `app/risk_analysis.py`. Flags below-market rent (vs.
portfolio average, preferring a per-sqft comparison when available),
notice-period outliers (absolute bounds + portfolio-relative
deviation), missing standard clauses (insurance, default/cure,
security deposit), one-sided terms (no escalation on a long-term
lease, unusually long cure period), and internal inconsistencies
within a single lease (escalation-schedule rate spread, invalid/
reversed date range, conflicting dates across sections). Each flag
carries a severity and a plain-English explanation citing the actual
numbers it fired on. Built by a parallel subagent per the shared
contract, independently re-verified afterward (re-ran its 26 tests,
then ran it against all 5 real red-flag fixture PDFs with a portfolio
context computed from actual data) — every deliberately-built issue
was caught correctly.
- **Reason**: This is explicitly "the differentiator" per the brief — go
  beyond extraction into analysis. Rule-based (not ML-based) for the
  same reason as the Q&A engine: explainability. Every flag needs to say
  *why* it fired, which a rule threshold can state directly ("rent is
  22% below the portfolio average of $X") in a way an opaque model
  score couldn't.

### Portfolio metrics, timeline, comparison, and benchmarking
**Status: done.** `app/portfolio.py` (totals/averages computed only
over leases whose value actually parsed — a missing field is skipped,
never counted as zero, so an average can't be silently diluted;
expiration timeline bucketed 0-6/6-12/12-24/24+ months plus already-
expired/unknown) and `app/comparison.py` (side-by-side N-lease compare
keeping the extractor's original display strings verbatim — a compare
view is exactly where a human checks the tool's work against the
source, so normalizing the numbers there would work against the
point; single-lease-vs-portfolio benchmarking with a signed % diff and
above/below/in-line assessment). Built by a parallel subagent,
independently re-verified: re-ran its 24 tests, then ran both modules
against all 10 real test PDFs — the benchmark for the deliberately
underpriced lease (64.8% below average rent) is consistent with the
below_market_rent flag risk_analysis raised for the same lease
independently.

### Rent roll export and printable portfolio report
**Status: done.** `app/rent_roll_export.py` (CSV via stdlib, Excel via
the one new dependency this session — `openpyxl==3.1.5` — with real
numeric typing applied conservatively so a qualified value like "$4.50
per sq ft annually" never gets misrepresented as a bare number) and
`app/report.py` (self-contained, print-oriented HTML one-pager: no
external assets, so it renders identically saved or emailed). Built by
a parallel subagent, independently re-verified: re-ran its 22 tests,
then generated real CSV/Excel/HTML from all 10 actual test PDFs and
read the Excel file back with openpyxl and the HTML report by eye —
professional-looking output, correctly surfacing all 23 real risk
flags from this session's portfolio.

### Frontend: stays vanilla JS, no build step, restructured as a multi-view app
**Status: done.** The single-lease-upload page is now a sidebar-
navigated multi-view app: Dashboard, Upload, Lease Detail (inline
editing, risk panel, amendments, per-lease Q&A), Expiration Timeline,
Compare, Ask a Question, and Portfolio Report — plain `<script>`
includes, no framework/bundler.
- **Reason**: Session 1 explicitly chose vanilla JS for zero build
  tooling and stayed consistent through session 2's larger single-page
  rebuild; introducing a framework now would be a bigger, tangential
  architectural change the brief didn't ask for. Vanilla JS can still
  organize multiple views cleanly with careful state management — it
  just takes more discipline than a framework would.
- **Verification note**: found and fixed two test-harness-only issues
  while verifying this (neither was a real app bug): a jsdom
  `window.eval()`-per-file harness doesn't reproduce how real
  `<script>` tags share one global scope for top-level `let`/`const`
  across a page, and jsdom's `FormData`/`File` aren't recognized by
  Node's native `fetch` (a cross-realm mismatch that doesn't exist in
  an actual browser). Fixed by having jsdom execute the real
  `<script src>` tags (`JSDOM.fromFile` + `runScripts: "dangerously"`)
  and bridging FormData across realms in the harness — see the
  frontend rebuild commit for detail. All 30 end-to-end checks passed
  against the real backend with real file uploads afterward.

### Backend module ownership during parallel work
Foundation (`database.py`, `normalize.py`, the `square_footage` field,
and the new lease/batch/amendment API routes) was built first and
sequentially, since every other module depends on its contract. The
independent analysis modules (`risk_analysis.py`, `qa_engine.py`,
`portfolio.py`/`comparison.py`, `rent_roll_export.py`/`report.py`) were
then built in parallel by separate agents, each producing a new
self-contained file plus its own tests and NOT touching `api.py` or each
other's files — wiring those modules into Flask routes was done
afterward by the orchestrating session alone, specifically to avoid
multiple agents editing the same shared file concurrently.

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

## Session 5: Visual redesign — landing page, waitlist, and app restyle

### Routes via real directory structure, not client-side routing
The frontend is still served by plain `python3 -m http.server`, with no
server-side routing logic and no build step. To get real, bookmarkable
URLs for `/`, `/app/`, and `/admin/waitlist/`, each is its own directory
with its own `index.html` — `http.server`'s built-in behavior (serve a
directory's `index.html`, 301-redirect a bare path to its trailing-slash
form) does the rest. The old flat `frontend/*.js`/`styles.css` files
moved into `frontend/app/` unchanged (only their CSS's token block was
replaced with an `@import`), so nothing about how the app itself loads
or runs changed — only where it lives.
- **Reason**: Keeps the "no build step, no framework" decision from
  session 1 intact rather than reaching for a JS router or a second dev
  server just to get distinct URLs.

### One shared token file, not three separate palettes
`frontend/design-system.css` holds every color/typography/shadow/radius
CSS custom property, plus a few truly shared components (buttons,
loading spinner). The landing page and admin view link it directly;
`frontend/app/styles.css` `@import`s it instead of redeclaring its own
`:root` block. All existing component class names and CSS variable
*names* in the app were preserved exactly — only their values changed —
so `app.js` and every view module needed zero changes to pick up the
new look.
- **Reason**: A single source of truth was the only way to guarantee the
  landing page and the app actually look like the same product, per the
  explicit "one cohesive palette, used everywhere" requirement. Keeping
  variable/class names stable avoided touching any JS (the task was
  scoped to a visual pass, not a behavior change) and made every existing
  jsdom-based test/verification pattern keep working unmodified.

### Waitlist has no real auth yet — deliberate, and flagged loudly
`GET /waitlist` and `POST /waitlist/<id>/approve` are open endpoints, and
`/admin/waitlist/` has no login. This was an explicit instruction
("no auth needed yet ... build the real auth gate later, don't block on
it now"), not an oversight. It's called out in three places so it can't
be missed later: a comment block directly above the routes in `api.py`,
a comment block in the admin `index.html`, and here.
- **Reason**: Matches the requested scope exactly — the task was to get
  a working waitlist gate and admin approval flow shipped now, with real
  authentication as explicitly deferred follow-up work, not something to
  half-build or skip documenting.

### Inter font via Google Fonts CDN, despite the "minimal dependencies" precedent
`design-system.css` pulls Inter from `fonts.googleapis.com`. Earlier
sessions' dependency choices (stdlib `sqlite3` over an ORM, no JS
framework) favored minimal/offline-friendly dependencies. This is a
narrow, deliberate exception: a system-font stack reads as a prototype,
and "premium SaaS typography" was an explicit requirement Inter serves
directly. If offline use becomes a requirement later, this is a single
`@import` line to swap for a self-hosted font file — noted here so that
tradeoff is visible, not buried.
  what to check.

## Session 6: /app access gate + local dev bypass (2026-08-15)

### Access gate uses self-reported email, not real auth
`/app` previously had zero enforcement — anyone with the URL landed
straight in the dashboard (see Session 5's "no auth yet" note above,
which was specifically about the admin waitlist endpoints but was true
of `/app` too). It's now gated: a visitor must enter an email with
`status = 'approved'` in `waitlist_signups`, checked via the new
`POST /waitlist/check` endpoint (`frontend/app/access-gate.js`).

This is explicitly **not** real authentication. There's no password, no
session token tied to a verified identity, and nothing stopping someone
from typing in an email they don't own if they can guess or find an
approved one. What it does do: stops a stranger who just has the URL
(the actual problem this session was scoped to solve) from reaching the
dashboard, while staying consistent with the project's "no accounts /
no login system" architecture so far — adding real password/session
auth would be a materially bigger scope (user table, password hashing,
session or token management, login UI) than what was asked for here.
- **Reason**: Matches the requested scope — "build the real auth gate"
  in context meant "stop unapproved visitors from reaching /app," not
  "build a full accounts system." The gap between this and real auth is
  called out here and in `api.py` directly above the route so it isn't
  mistaken for more than it is. Real auth (accounts, passwords/OAuth,
  sessions) remains a Next Steps item, now split out from the admin-panel
  auth gap tracked in the Session 5 entry above — the two are separate
  problems (who can reach `/app` vs. who can approve signups /
  see everyone's email) and don't need to ship together.

### LOCAL_DEV_MODE: a server-side, env-only bypass — not a client-side one
The gate can be skipped locally via `LOCAL_DEV_MODE=true` in
`backend/.env`. The frontend never decides this for itself — it asks the
backend via `GET /config`, and the backend only reports what's already
in its own environment at process start (`os.environ`, loaded once
before any request is handled). A client can't set or influence this
value through any request path.
- **Reason**: The alternative — a client-side flag (URL param, hardcoded
  `true` in JS, a build-time toggle) — would ship the same bypass to
  production by accident the moment that code path is reachable there,
  since there's no build step to strip it out (Session 1's "no build
  tooling" decision, still in effect). Routing it through an
  environment variable the *server* controls means the real/default
  gate is what ships everywhere by default, and the bypass only exists
  on whichever machine's `.env` explicitly turns it on — which is also
  why `backend/.env` (gitignored, per Session 1) is the only place this
  is ever set to `true`; `.env.example` documents the variable but
  defaults it to `false`.

### App scripts now load dynamically, after the gate — not statically in the HTML
`frontend/app/index.html` no longer lists `api.js`/`app.js`/the view
modules as static `<script>` tags. `access-gate.js` is the only
statically-loaded script; it injects the rest only after access is
confirmed (`script.async = false` on each, to preserve load order
without blocking).
- **Reason**: Without this, every view module's API calls (dashboard
  metrics, lease list, etc.) would fire immediately on page load
  regardless of whether the visitor is allowed in — the gate would only
  be hiding the DOM, not actually stopping the underlying requests. This
  also surfaced a latent bug worth noting: `app.js` and all six view
  modules bootstrap via `document.addEventListener('DOMContentLoaded',
  ...)`, which never fires for a script injected after that event
  already happened (true even on the `LOCAL_DEV_MODE` bypass path, since
  the `/config` fetch that decides that is itself async). Each of those
  seven files now checks `document.readyState` first and calls its init
  function directly if the page has already finished loading — a small,
  general fix that also makes each file correct if loaded late for any
  other reason in the future, not just this one.

### Multi-lease PDFs are rejected at upload, not silently merged into one record

A merged/bundled PDF — several distinct leases scanned or concatenated
into a single file — was silently persisted as ONE lease record.
`extract_fields()` treats the whole document as one continuous text
block and returns each field's single best match anywhere in it, so
across a genuinely multi-lease PDF, different fields independently
"win" from different constituent leases: the tenant name from lease #2
paired with the rent amount from lease #1, with nothing to indicate the
record is a mix.

**This was verified empirically, not assumed**: concatenating two real
fixture PDFs (`retail_lease.pdf` + `office_lease.pdf`) via PyPDF2 and
running the real extraction pipeline against the result produced tenant
`"Vertex Analytics LLC"` (from page 2 / office_lease) paired with rent
`"$6,000.00"` and dates from page 1 / retail_lease — a real Frankenstein
record. The same investigation also found a live example already in
this project's dev database: a pre-existing `Sample_500_Page_Lease_
Portfolio.pdf` upload (from before this fix existed) had been persisted
as a single lease with an implausible `$262,131.87` monthly rent and no
end date found — consistent with the same bleed, at much larger scale.

**Fix**: `FieldExtractor.detect_multiple_leases()` scans the whole
document for every match of the tenant/landlord party-name patterns
(reusing the same patterns `extract_fields()` itself uses, via a new
`_find_all_party_values()`, rather than inventing separate detection
logic) and checks whether more than one *distinct* tenant or landlord
is defined. A genuine single lease defines exactly one of each, even
when that name is repeated verbatim many times through the document —
2+ different names is a strong, low-false-positive signal that more
than one lease is present. `_extract_fields_from_file_storage()` in
`api.py` calls this before trusting `extract_fields()`'s result and
returns a 400 (not a 500 — this is a client-actionable "wrong kind of
file" situation, not a server error) with a message naming the
conflicting parties found, telling the uploader to split the PDF and
upload each lease separately. Applies uniformly to `/extract`,
`POST /leases`, `POST /leases/batch` (per-file, without failing the
rest of the batch), and amendment uploads, since they all share this
one pipeline function.

This does NOT attempt to automatically split a multi-lease PDF into its
constituent leases — that would need real per-lease boundary detection
(which page ranges belong to which lease) and is a substantially larger
feature with its own accuracy risks. Refusing and telling the human
what's wrong was the deliberately smaller, safer scope, consistent with
this project's existing "flag clearly, never guess silently" standard
(see the original quality-bar requirement in the root CLAUDE.md).

**False positives found and fixed before shipping this**: an early
version flagged 2 of the 10 existing single-lease fixtures incorrectly.
Both were the same root cause — the same real party mentioned twice
surfaces as two slightly different strings (once via the tight
word-boundary label pattern, once via the looser to-end-of-line one, or
once with a corporate suffix like ", Inc." and once without it in a
later reference) — not two different parties. Fixed with
`_dedupe_party_values()`, which merges values where one is a
case-insensitive prefix of the other before counting distinct parties.
Verified against all 10 real single-lease fixtures individually (zero
false positives) and 4 different real multi-file merges, including one
combining the two fixtures that had triggered the false positives (to
confirm the fix didn't just suppress detection entirely) — see
`test_multi_lease_detection.py`.

### Google Sheets export: service account, not OAuth; new sheet every time

`sheets_export.py` uses a Google **service account** key
(`GOOGLE_APPLICATION_CREDENTIALS`, a JSON file path — the standard env
var name Google's own libraries look for) rather than per-user OAuth.
- **Reason**: this is a backend-triggered export action (click a
  button, get a sheet), not a "sign in with Google" login flow — there
  is no per-user Google identity anywhere else in this app to hang
  OAuth off of, and a service account is the credential type meant for
  exactly this shape of server-to-server access.

Every export **creates a brand-new Sheet** (never updates one persistent
sheet), named `"Lease Portfolio Export - <date>"`.
- **Reason**: asked directly rather than assumed — see the
  AskUserQuestion exchange in this session. A fresh sheet per export
  also has no "which format does the existing sheet expect" compatibility
  concern to maintain over time, unlike updating a fixed sheet would.

The created sheet is shared **"anyone with the link can view"** (via
the Drive API, since Sheets API alone can't set sharing) rather than
shared with a specific person's email.
- **Reason**: a service-account-created file isn't visible to anyone
  else by default, and there's no single "current user" account
  anywhere in this app (no real per-user auth exists yet — see the
  access-gate entry above) to share it with individually instead.
  Link-shareable is the only option that guarantees the URL handed back
  actually opens for whoever clicked the button. This does mean anyone
  who obtains that exact (unguessable, but not access-controlled) link
  could view that export's data — documented explicitly in
  `backend/.env.example` as the same tradeoff the existing CSV/report
  exports already have, not a new regression introduced by this
  feature.

Column formatting (which fields become real numbers vs. stay as
extracted display strings, blank-not-"Not Found" for missing fields)
deliberately mirrors `rent_roll_export.py`'s existing philosophy rather
than inventing a third convention for a third export format — see that
module's docstring and `sheets_export.py`'s docstring for the shared
reasoning. Annual Rent and Rent per Square Foot are computed via
`app.normalize`, the same module every other aggregate in this project
uses, so a number in the exported sheet can't quietly disagree with the
same figure shown on the dashboard.

Verified as far as possible without real Google credentials (none are
configured in this environment, by design — nothing was invented or
guessed): every failure path (unset env var, missing file, invalid key
file, a mocked Google API 403/401/other error) raises a clean,
actionable `SheetsExportError`, confirmed live against the running
server with `curl`. The full happy path — creating a sheet, writing the
correct rows, setting sharing — is verified with `googleapiclient.
discovery.build` and `service_account.Credentials.from_service_account_
file` mocked out (`test_sheets_export.py`), asserting on the actual
data passed to the mocked Sheets API calls (header row, per-lease rows
in order, the sharing permission body), not just that no exception was
raised. What is NOT verified: an actual real Google Sheet being
created via a real API call, since no real credentials exist to test
with — that step is on whoever sets up
`GOOGLE_APPLICATION_CREDENTIALS`.

### Multi-lease PDFs are now SPLIT, not rejected — supersedes the earlier "reject" decision

The previous session's fix for multi-lease PDF field-bleed (see the
"Multi-lease PDFs are rejected instead of silently merged" entry above)
deliberately chose the smaller, safer scope: detect the situation and
refuse the upload, rather than attempt real per-lease boundary
detection, which that entry called "a substantially larger and riskier
feature on its own." This session built that larger feature, on
explicit request, after the smaller fix turned out not to be enough in
practice — a real merged portfolio PDF a user actually tried to upload
produced a risk-analysis flag listing 30+ "conflicting" start dates,
because `date_candidates` were being collected from the whole 500-page
document instead of kept separate per lease (the same underlying
bleed the reject-based fix prevented at the *field* level, but not at
the *risk-analysis* level, since risk analysis reads `date_candidates`
independently of `extract_fields()`'s own single-best-match fields).

**How boundary detection works**: `FieldExtractor.detect_lease_
boundaries()` places a page boundary at the first page each distinct
tenant OR distinct landlord is introduced on — the UNION of both
signals (not just one, and not just whichever found more distinct
parties, which was this feature's first, more conservative
implementation before it was strengthened — see below). Verified safe
against all 10 real single-lease fixtures before switching to the union
approach: in every one, the lease's tenant and landlord are introduced
on the *same* page (a lease's "parties" section names both together),
so the union never adds a spurious mid-lease boundary. `extract_
multiple_leases()` then runs the existing single-lease `extract_
fields()` + `find_all_date_candidates()` independently on each
boundary's own page range — never on the whole document — which is
what actually fixes the 30-dates symptom: each split lease's
`date_candidates` now only ever contains dates from its own 1-2 pages.

**Verified, concretely, not just reasoned about**: every field of every
split-out lease exactly matches what extracting that same source
fixture completely standalone produces (not "close" — byte-for-byte
equal), across 4 different real multi-file merges including a 4-way
merge, plus a 10-fixture merge (all 10 real fixtures concatenated into
one document) that correctly produced exactly 10 leases in 0.05
seconds. The reported symptom itself was directly reproduced and
confirmed fixed: a 5-fixture merge that showed 6 smeared "conflicting"
start dates under the old whole-document approach now shows 1-2 dates
per lease, with only the two fixtures that are genuinely internally
inconsistent (by design, as test fixtures) still flagging.

**Known, real, honestly-documented limitation**: if two genuinely
different, non-adjacent leases in the same merged PDF happen to share
BOTH the exact same tenant name AND the exact same landlord name, this
heuristic (or any purely name-based one) cannot tell them apart, and
they will incorrectly merge into one record — confirmed directly: a
test merging `retail_lease.pdf` + `office_lease.pdf` + `retail_lease.
pdf` again (so the same tenant AND landlord reappear on the third page)
produces 2 detected leases, not the true 3, with the second result's
fields bleeding between the office lease and the second copy of the
retail lease. This is not fixed and was not silently assumed away. It
was NOT possible to test against the user's actual real-world 500-page/
250-lease PDF that originally surfaced this bug — the file itself
wasn't recoverable (upload-time processing only ever kept a temporary
copy, already deleted; it wasn't found in common locations on this
machine either) — so this feature's accuracy against that *specific*
document is unverified; everything above is verified against this
project's own real fixture PDFs and real merges of them instead. This
should be spot-checked against the real file when available.

Not implemented, and deliberately out of scope: page-break heuristics
and repeated "COMMERCIAL LEASE AGREEMENT"/"ARTICLE 1: PARTIES"-style
structural title detection (both suggested as alternative signals).
The tenant/landlord-identity signal was preferred because it was
already built, already validated with zero false positives across
every real fixture in this project, and is what the fields themselves
are extracted from — a structural-title signal would need its own
separate validation pass against real documents to avoid new false
positives (e.g. a document that mentions "lease agreement" in a table
of contents or definitions section without that being a real
boundary), which there wasn't a real corpus available to validate
against here.

### Organization: tags, not folders

Chose a simple flat tag system (a lease can carry any number of tags;
a new `lease_tags` table, `id, lease_id, tag`, `UNIQUE(lease_id, tag)`,
`ON DELETE CASCADE` so deleting a lease can't leave orphaned tag rows)
over a folder hierarchy.
- **Reason**: a folder model forces a choice this project's own users
  explicitly don't have to make up front — "by property, portfolio, or
  however I want to organize them" was the actual request, and a real
  lease often belongs to more than one useful grouping at once (e.g.
  both "Downtown Portfolio" and "Expiring 2026" simultaneously) — a
  strict one-parent-folder model can't represent that without either
  duplicating the lease or picking one grouping arbitrarily over the
  other. Tags don't have that limitation, and they're a smaller,
  simpler addition to the existing relational schema (one small table,
  no tree/parent-child logic, no move/reparent operations to build).
- **Trade-off, stated plainly**: a folder view gives a stronger sense
  of "this lease lives in exactly one place," which some users may
  prefer conceptually. If that turns out to matter later, it's still
  buildable on top of this — a "primary folder" could just be
  "the first tag," or a genuine parent-child folder table added
  alongside tags without displacing them. Not built now because
  nothing in the request required it and it would have been guessing
  at a UI model rather than building the one actually asked for.

## Session 7 (continued): Part 2 — accuracy verified at scale (2026-08-15)

### Tested small/medium/large sizes; found zero app bugs, one test-tooling bug

Requirement: confirm extraction accuracy holds at small (1-5pg),
medium (30-50pg), and large (500pg, multi-lease) PDF sizes, not just
small ones — and fix any accuracy issues found, not just report them.

The real user-uploaded ~500-page/250-lease PDF that originally
surfaced the multi-lease bleed issue could not be recovered (it was
never persisted past the delete-after-processing temp file; Downloads/
Desktop/Documents were searched again this session, still not found —
this is unchanged from the prior session's finding, restated here for
honesty rather than silently re-asserted). In its place:
- **Small**: the existing 10 real fixture PDFs (1-2 pages each,
  `backend/tests/*.pdf`) — already covered by `test_live_api.py` and
  `test_multi_lease_detection.py`, both passing (22/22 test files,
  including live-API tests against a running server).
- **Medium**: a new 35-page synthetic single lease (real terms on
  page 1, 34 pages of realistic exhibit/boilerplate after, generated
  with explicit `showPage()` calls). Verified 100% field accuracy and
  confirmed `detect_lease_boundaries()` correctly returns one
  unsplit range for the whole document — a long document full of
  boilerplate doesn't fool the boundary detector into over-splitting.
- **Large**: a new 60-page synthetic multi-lease document, 60
  genuinely distinct tenants/landlords/terms (no real 500-page file
  was available, so this is explicitly a scale proxy, not the same
  as the original file). Uploaded through the live running API (not
  just the extraction pipeline directly), confirmed: 60/60 leases
  split into 60 separate DB records (no stacking/merging), 0/60
  field-value mismatches against ground truth, 0 anomalies in
  source-page citation or confidence across all ~900 found-field
  checks (15 fields × 60 leases).

**A real bug was found and fixed, but it was in the throwaway test
generator script, not the application**: the first attempt at the
60-lease fixture wrote each single-lease PDF to a reused temp filename
(`_tmp_lease_{i}.pdf`), read it with `PyPDF2.PdfReader`, then deleted
the file immediately before the next loop iteration. `PdfReader` reads
page content lazily rather than eagerly, so by the time
`PdfWriter.write()` actually serialized the merged document (once, at
the very end, after all 60 "adds"), several of the per-lease source
files had already been deleted and their filename reused by a later
iteration — silently corrupting the merged PDF (page 5 ended up a
byte-for-byte duplicate of page 2's content) with no error raised
anywhere. `detect_lease_boundaries()` was directly verified to behave
correctly given that corrupted input (deduping the duplicated page 5
into page 2's boundary was the right call given what was actually on
the page) — confirming the fault was upstream, in the generator, not
in `field_extractor.py`. Fixed by giving every temp file a unique name
and keeping every `PdfReader` reference alive until after the final
`write()`. This fixture-generation script is scratch tooling only,
not part of the repo, so there's no application diff for this fix —
it's recorded here because the debugging process (and the discipline
of checking raw page text before assuming the app was at fault) is
exactly the kind of thing this file exists to capture.

**Also directly re-confirmed** (not just assumed from the prior
session): merging two real fixture PDFs and uploading via the live
API still produces zero field bleed between the resulting leases —
the specific regression this project has previously flagged as
"a known issue" remains fixed.

No application code changes were needed for Part 2 — extraction
accuracy, boundary detection, confidence levels, and source citations
all held correctly at every size tested, including under live-API
upload (not just direct pipeline calls). All 22 test files (17
non-live + 5 live-API) pass with the backend/frontend dev servers
running.

## Session 7 (continued): Part 3 — Excel/Google Sheets export, wired to both views

### Found and fixed a real accuracy gap: the Excel/CSV export was missing 4 of 15 fields

`rent_roll_export.py`'s `COLUMNS` (used by both the CSV and Excel
exporters) only ever covered 11 of the 15 extracted fields — Permitted
Use, Exclusivity Clause, Insurance Requirements, and Default/Cure
Period were silently absent from every rent-roll export, even though
`sheets_export.py`'s Google Sheets export already included all 15.
This was caught by directly comparing the two exporters' `COLUMNS`
lists against each other and against `field_extractor.py`'s actual
15-field output, not by assuming either exporter was complete because
it had tests. Fixed by adding all 4 to `COLUMNS`/`_FIELD_FOR_COLUMN`/
`_COLUMN_WIDTHS`; `_cell_value`'s existing pass-through logic needed no
changes since it was already generic over the field-key mapping. CSV
and Excel now carry all 15 extracted fields (18 columns total, with
the 3 derived: Rent/SqFt, Months Until Expiration, and the Filename
identifier). `test_rent_roll_export.py` updated to assert 18 columns
and to give one fixture lease real values for all 4 previously-missing
fields, so blank-cell-vs-value behavior is actually exercised for them
too, not just implied by symmetry with the other 11.

### Single-lease export: new routes, not a special-cased exporter

Added `GET /leases/<id>/export.xlsx` and
`POST /leases/<id>/export/google-sheets` rather than writing a
separate single-lease rendering path. Both just call the existing
`generate_rent_roll_excel([lease])` / `export_to_google_sheets([lease])`
with a one-item list — the portfolio exporters were already written to
take a list of leases with no assumption about its length, so scoping
to one lease needed zero changes to either exporter module, only two
thin routes in `api.py`. The Excel route names the downloaded file
after the lease's own display name (sanitized to safe filename
characters) rather than the generic `rent_roll.xlsx`, since a
single-lease download landing in a Downloads folder named
`rent_roll.xlsx` next to five other identically-named files would be
useless.

### Export controls added to the Dashboard (list view) and Lease Detail view specifically

The Report view already had portfolio-wide CSV + Google Sheets export
(built in an earlier session) — that was left as-is. This part's ask
was specifically an Export option on the Lease Library (Dashboard) and
the individual Lease Detail view, so two new UI locations were wired,
matching the "choice between Google Sheets or .xlsx" framing exactly
(a Download Excel link plus an Export to Google Sheets button, not a
CSV option, in both new locations) rather than duplicating the Report
view's CSV-inclusive pattern.

### Verified end-to-end, including the exact standard requested: exported data matches the app

For the single-lease Excel route: uploaded a real fixture via the live
API, downloaded the resulting `.xlsx` via the live route, then
compared every one of its 18 cells against that same lease's
`extracted_fields` as returned by `GET /leases/<id>` — zero
mismatches. For the portfolio-wide route: same check at the header
level, confirming all 18 columns are present in a real download, not
just in a unit test with hand-built fixtures. For both Google Sheets
routes (portfolio and single-lease): confirmed the failure path is
clean and actionable — `GOOGLE_APPLICATION_CREDENTIALS` is not
configured in this environment's `backend/.env` (consistent with the
prior session's explicit instruction not to invent or guess
credentials), and both routes correctly return the same
already-existing, safe-to-display "Google Sheets export isn't set up
yet... see backend/.env.example" message rather than a stack trace or
a silent failure — verified both via direct `curl` against the live
API and via the actual rendered UI (jsdom against the real running
app: clicking each Export to Google Sheets button surfaces that exact
message in the page, with zero JS errors). The success path for
Google Sheets itself (a real spreadsheet actually getting created) is
still only verified via `test_sheets_export.py`'s mocks, same as the
prior session — this remains the one piece of Part 3 that needs the
user's own Google Cloud service account credentials to verify for
real; instructions are already in `backend/.env.example`.

22/22 backend test files pass. All test leases created during this
verification were deleted afterward; the dev DB is empty again.
