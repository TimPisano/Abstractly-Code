# Multi-format rent-roll import — reliability report

_Tested 2026-09-08 against the generated Meridian_Plaza_Rent_Roll_HARD
fixture set (xlsx / pdf / png) plus the pytest suite in
`tests/test_rent_roll_multiformat.py`._

## What was built

Every accepted format is reduced to a plain list of rows and then run
through the **one existing** pipeline — `_find_header_row` →
`_match_columns` → `parse_rent_roll_rows`. No format has its own
column-matching or row-parsing logic; the messiness tolerance that was
already there (Market Rent / Annual Rent denylists, vacant/total-row
skipping, multiple date formats, decorative header blocks) applies
identically to a PDF or a photo once the table is extracted.

| Extension | Path | Library |
|---|---|---|
| `.csv` `.tsv` | delimited reader | stdlib `csv` |
| `.xlsx` `.xlsm` | existing multi-sheet reader | `openpyxl` |
| `.xls` | legacy workbook | `xlrd` |
| `.docx` | largest table in the document | `python-docx` |
| `.pdf` (ruled table) | table detection | `pdfplumber` |
| `.pdf` (borderless, has text) | grid rebuilt from word x/y positions | `pdfplumber` |
| `.pdf` (no text layer) | rasterise → OCR → grid from word boxes | `pdf2image` + `pytesseract` |
| `.jpg .jpeg .png .webp .tif .tiff .bmp` | OCR → grid from word boxes | `pytesseract` |
| `.heic .heif` | decode → OCR | `pillow-heif` + `pytesseract` |

New deps: `pdfplumber==0.11.8`, `pillow-heif==1.1.1` (added to
`requirements.txt`).

## Reliability — honest assessment

### Reliable — treat like the current .xlsx path

- **`.csv` / `.tsv` / `.xlsx` / `.xlsm`** — unchanged behaviour.
- **`.xls`** — `xlrd` reads the cell grid directly; date cells are
  converted the same way `openpyxl` ones are. No guesswork.
- **`.docx` with a real Word table** — `python-docx` gives exact cell
  text. On the Meridian fixture: **identical parse to the .xlsx** —
  same 10 rows, same column mapping, VACANT + Total skipped.
- **`.pdf` that is a ruled table** (what Yardi / AppFolio / RealPage /
  MRI actually export) — `pdfplumber.extract_tables()` keys off the
  ruling lines. On the Meridian fixture PDF: **identical parse to the
  .xlsx** — 10 rows, `Monthly Rent` correctly chosen over `Market
  Rent` and `Annual Rent`, both date formats parsed.

### Shakier — works, but warns, and can be wrong

- **`.pdf` borderless / not a clean grid** (a spreadsheet "Save as
  PDF" with no cell borders). The grid is rebuilt from each word's
  exact x/y position. On a borderless test PDF this recovered tenant +
  rent + start date for every row, but **merged the Unit column into
  Tenant and dropped the end-date column** because the header words
  weren't spaced like real gutters. The import still succeeds and
  carries a "columns were reconstructed from text positions —
  spot-check" warning. If nothing parses at all, it fails with a clear
  "export to Excel/CSV" message rather than a silent 0-row import.

- **OCR paths (`.pdf` with no text layer, and every image format).**
  Not verifiable on this machine — **there is no `tesseract` binary
  installed here and no package manager (brew/port/conda) to add
  one**, so the real end-to-end OCR accuracy was **not measured**. The
  code is written and the grid-reconstruction algorithm is unit-tested
  with synthetic word boxes (`test_ocr_grid_reconstruction_algorithm`),
  but treat OCR accuracy as unproven until it runs against a real
  scan on a box with tesseract.

  What OCR will realistically do, based on how `tesseract` +
  bounding-box table reconstruction actually behave:
  - **Digit confusion** — `0/O`, `1/l/I`, `5/S`, `8/B`, `6/G`. A
    misread rent or a misread year is the most likely and most
    damaging error, and OCR gives no signal that a specific digit was
    a guess.
  - **Column bleed** — a tenant name wider than its column merges into
    the next cell (`"Meridian Dental Associates" | "2100 PLLC"`).
    Long legal entity names are the usual trigger.
  - **Row drift on a skewed scan** — a photo taken at an angle breaks
    the vertical row clustering; rows interleave.
  - **Word mis-segmentation by tesseract itself** — `"MacArthur"` →
    `"Mac Arthur"`, or `"$1,200 3/1/24"` glued into one token — before
    this code sees anything.
  - Every OCR import carries a mandatory "read by OCR — spot-check
    every row" warning, plus a stronger one when mean word confidence
    is below 75%.

### Fails cleanly with a specific message (verified)

| Input | Message |
|---|---|
| `.pages`, `.numbers`, unknown ext | "Can't read a '.pages' file as a rent roll. Supported formats: …" |
| Empty file | "This file is empty — there's nothing to import." |
| PDF that's a letter/narrative, not a table | "This PDF has text in it, but nothing that looks like a rent-roll table … If it's a narrative document rather than a table, that's expected." |
| `.docx` with no table (just prose) | "This Word document has no table in it. Put the rent roll in an actual Word table (Insert > Table), or upload it as a spreadsheet, CSV, or PDF instead." |
| Image / scanned PDF, no `tesseract` on server | "OCR couldn't run on this file on this server. If this is a scanned or photographed rent roll, try exporting it to Excel or CSV …" |
| Image that OCRs but isn't a table (photo of a resume, blank scan) | "We read text from this file but it doesn't look like a rent-roll table … a clearer image or an exported spreadsheet will work much better." |
| HEIC when `pillow-heif` unavailable | "This is an iPhone HEIC image and HEIC support isn't available on this server. In Photos, use Share > Options and turn off 'HEIC' …" |
| Scanned PDF over 15 pages | "This looks like a scanned PDF with N pages. We only OCR up to 15 pages …" |

## Meridian_Plaza_Rent_Roll_HARD results (this machine)

```
.xlsx  -> source_kind=excel        10 leases, 2 skipped (VACANT, Total), rent_amount=col 6 (Monthly Rent) ✓
.pdf   -> source_kind=pdf-text     10 leases, 2 skipped, IDENTICAL parse to .xlsx ✓
.png   -> clean 400: "OCR couldn't run on this file on this server ..."  (no tesseract here)
```

## Before this goes live

1. **OCR runs in production, but is unverified.** `backend/Dockerfile`
   already installs `tesseract-ocr` + `poppler-utils` (lines 18–20),
   so the deployed container *can* OCR — unlike this dev machine. But
   nobody has run a real photographed/scanned rent roll through it
   yet. Before relying on it: deploy, upload one real scan, and check
   the output row-by-row. The local dev machine needs
   `brew install tesseract poppler` to test it here.
2. **Frontend** (held by the other session): widen the file `accept`
   list; render the new `warnings[]` array from the import response
   verbatim above the results; show `source_kind` so an OCR import is
   visually distinct from a spreadsheet import.
3. **Set expectations in the UI copy**: "Spreadsheet, CSV, or a
   PDF exported from your PMS work best. Photos and scans are read by
   OCR and need checking."
4. The `_MAX_OCR_PDF_PAGES = 15` cap and the existing 16 MB upload
   limit are the only guards on OCR cost/time — fine for an
   authenticated route, revisit if this ever becomes public.

## Reproduce

```
cd backend
python3 tools/rent_roll_formats/make_fixtures.py       # writes fixtures/
python3 tools/rent_roll_formats/run_formats_check.py   # runs each through the real parser
python3 -m pytest tests/test_rent_roll_multiformat.py
```
