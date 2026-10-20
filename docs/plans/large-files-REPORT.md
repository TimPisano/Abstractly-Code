# Large files + any file type: report

Branch `feature/large-files-any-type`, overnight run 2026-10-19/20. Local
commits only: nothing merged, pushed or deployed, no Render settings
touched. Everything new is behind `LARGE_FILE_UPLOADS` (default **off**);
with it off, every existing route behaves as on `main`.

## In plain English (start here)

- **What was broken.** A big scanned lease could never work: the site
  refused anything over 16 MB, and even a smaller scan was OCR'd inside the
  web request, all pages at once (about 3 GB of memory for 300 pages, on a
  512 MB server, against a 2-minute cutoff). With AI turned on, a long
  lease was silently cut off after about page 71, so terms later in the
  document were never read. And the site judged files by their name: a
  photo renamed `.pdf` got a confusing "corrupted PDF" error, and a PDF
  renamed `.txt` was saved as a garbage lease.
- **What I changed.** With the new switch on, the upload page sends the
  file to a new endpoint that saves it straight to disk and answers at
  once; a background job then reads it page by page (OCR only where a
  page has no text), runs AI in page chunks and merges the answers (every
  value keeps its page number), and saves the result, while the page shows
  "Reading page 120 of 300". File type is checked from the file's
  contents. PDF, DOCX, DOC, XLSX, XLS, CSV, TXT, JPG, PNG, HEIC and TIFF
  are accepted; anything else gets a message saying what the file looks
  like and what to upload instead.
- **Result.** The 120 MB, 300-page scanned lease now uploads in half a
  second and is fully OCR'd in the background in about 5 minutes. The
  500-page lease's late terms (page 262, 333, 431, 478) all reach the AI.
  The 5,000-row messy rent roll imports in seconds instead of 10+.
- **Before you turn it on:** set three things on Render (below), try it
  on the tester deployment first, and consider a bigger instance if
  testers will import 5,000-row rent rolls.

## 1. What was broken (measured before changing anything)

Fixtures (all fictional; built by `backend/tests/create_large_fixtures.py`
into `backend/tests/fixtures/large/`, gitignored because they're 120 MB+):
a 500-page text lease with key terms planted late (security deposit
p.262, square footage p.333, renewal p.431, exclusivity p.478); a
300-page image-only scan (200 DPI grayscale, 120 MB, no text layer); a
5,000-row rent roll as XLSX (cover sheet first, two-row header with merged
cells, a heading row, subtotal row and blank row per building, a grand
total, mixed cell types) and the same data as CSV.

`backend/tests/repro_large_files.py` drove the unchanged code; its output
is in `docs/plans/large-files-repro.txt`.

| # | Problem | Evidence | Why |
|---|---|---|---|
| A | Anything over 16 MB refused | 120 MB scan -> HTTP 413; the upload page also drops >16 MB files before sending | `MAX_CONTENT_LENGTH = 16 MB`; `upload-view.js` hardcodes 16 MB |
| B | OCR runs inside the request, every page at once | 12 scanned pages: 33 s in-request, RSS 176 -> 356 MB. Projected for 300 pages: ~14 min and ~3.1 GB of bitmaps | `convert_from_path(path)` renders the whole PDF; gunicorn kills a request at 120 s; Render Starter has 512 MB |
| C | A scanned page inside a digital PDF is never OCR'd | mixed PDF: the scanned page comes back empty | OCR only runs when the *whole* file has <100 characters |
| D | AI sees only the first ~71 pages | 500-page lease: prompt cut at 200,476 chars, last page sent = 71; all 4 planted terms never sent | `MAX_DOCUMENT_CHARS = 200_000` truncation |
| E | Rent roll import entirely in-request | 5,000 rows: 9.7 s (XLSX) / 10.4 s (CSV) on an idle laptop; 266-385 MB of Python allocations | one connection + commit + two re-read queries per row, then a full reconciliation sweep |
| F | Type decided by extension | PNG named `.pdf` -> "corrupted PDF"; program named `.pdf` -> same; PDF named `.txt` -> **201, garbage lease saved**; `.heic` lease -> rejected | `allowed_file()` + extension dispatch |
| G | Upload copied into memory 3 times | 14.4 MB upload -> 43 MB just to receive it | `file.read()` in `_validate_upload`, `upload_lease`, and again from the temp file |
| H | Per-file page limit never enforced | 500-page PDF accepted under a 150-page limit | `usage_limits.check_file_limits` calls `extract_pages(..., None)`, which raises inside `open(None)` and is swallowed. **Not fixed here**: `feature/tester-ready` owns usage limits (your instruction mid-run). Reported for that branch. |

A note on timings: the repro recorded 31-43 s for the 500-page text lease
and 56-72 s for the rent rolls, but those runs overlapped with full test
runs. Re-measured alone, the old route took **4.5 s** (text lease) and
**9.7 s / 10.4 s** (rent rolls). So with the regex engine the text lease
never timed out; its real failures were D and H. The table uses the
uncontended numbers.

## 2. What I changed

| Commit | What |
|---|---|
| `5580c7d` | Plan, fixture generator, repro script |
| `785ed25` | `app/file_types.py`: type from content (magic bytes, inside ZIP/OLE2 containers, text heuristic) |
| `132c6a6` | Per-page OCR, one page rasterized at a time; multi-page TIFF; HEIC; `extract_pages_from_path` |
| `c79e3d3` | Chunked AI extraction + merge with page citations |
| `89d9654` | Background upload jobs: `POST /uploads`, `GET /uploads/<id>`, `GET /uploads/config`, `upload_jobs` table, bulk inserts |
| `8fbcfce` | Fix my own regression (below) + survive a busy database |
| `9e5329f` | Upload page: real progress bar and limits |
| (final) | Security/review fixes, docs, this report |

**One shared internal format.** It already existed: `document_extractor`
turns every format into `[{"page": N, "text": ..., "ocr_confidence"?}]`,
and everything downstream (regex or AI extraction, citations, risk
analysis) reads only that. The new path keeps it and adds per-page OCR,
every TIFF frame, HEIC, and progress callbacks.

**Background jobs.** The web request only streams the file to disk
(server-generated name, SHA-256 computed on the way), checks the type and
limits, records a job and returns 202. The job runs on the **existing**
Redis queue and `worker.py` when `REDIS_URL` is set (production already
has both), or on one background thread inside the API process when it
isn't (local dev, no Redis to install). Progress is written to the job
row; the page polls it. A job that stops reporting progress (the process
died) is marked failed on the next poll and its file deleted; a runner
that outlives that stops instead of reviving the job.

**Chunking, within limits checked in the official docs** (2026-10-19):
Messages API requests max **32 MB** (413 above that); current Sonnet
models have a **1M-token** context (about 2.5M characters); PDF input is
limited to **600 pages per request, 100 when the context is under 1M**,
at 1,500-3,000 tokens per page. Abstractly sends extracted *text*, not
PDFs, so tokens are what bind. Each chunk is at most **100 pages and
180,000 characters** (about 72k tokens). That's under the existing 200k
truncation, so a chunk is never cut; it's valid even on a 200k-context
model or if this ever switches to native PDF input; and one call stays
well inside the 90 s request timeout. The 500-page lease becomes 9
chunks. **Merging:** the highest-confidence value wins (earlier page on a
tie); the same value in several parts lists every page; **different
values in different parts drop the field to "low" and keep every
candidate with its own page citation**, so a reviewer decides (the
prompt's own "never guess between candidates" rule). Concessions are
combined. If one chunk fails, the whole document fails rather than
silently returning "not found" for that part.

**OCR.** Per page: text layer first, OCR only pages under 50 characters,
one page rasterized at a time (grayscale), 120 s tesseract timeout per
page, pages with absurd dimensions rasterized at a lower DPI (40 MP
budget) or skipped. Pages still unreadable after OCR: if they're under
half the document, extraction proceeds with a warning listing them
(usually blank separator pages); if half or more, the lease is saved as
"needs OCR", as before, rather than guessing.

**Rent rolls.** Same parser and same stored result as the existing
import; rows are written in one transaction, superseded rows in one
transaction, then the same reconciliation sweep, all in the background.

**Existing routes untouched.** `POST /leases` and
`POST /leases/import-rent-roll` are unchanged and keep their 16 MB limit,
now enforced per request so a chunked body can't get around it (see 4).
The only edits to existing code are additive or behavior-preserving:
`_run_reconciliation_sweep` delegates to a team-explicit helper, and
`_ocr_page_with_confidence` takes an optional timeout (default unchanged).

## 3. Test results

**Full suite: 90/90 test files pass** (`python backend/tests/run_all_tests.py`,
`ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` unset). Baseline on this branch
before any change: 85/85. It first showed 81/85, because this machine's
Homebrew was missing `libpng`, `nss` and `pcre2`, which broke
`tesseract` and `poppler` (3 OCR test files); the 4th failure was
`pytest` missing from the fresh venv. I installed those three Homebrew
libraries (no upgrades) and `pytest` into this worktree's venv only.

New test files (57 tests, all registered in `run_all_tests.py`, Anthropic
always mocked):

| File | Tests | Covers |
|---|---|---|
| `test_file_types.py` | 7 | every format from real bytes; mislabeled files; programs/archives/presentations/RTF/HTML/GIF; empty/damaged; password-protected; text that starts like BMP/MZ/%PDF; zip bombs |
| `test_large_file_extraction.py` | 9 | one-page-at-a-time rasterization (real tesseract on 4 scanned pages); mixed PDF; one failing page; multi-page TIFF; HEIC; oversized photo; locked/broken/blank files; 500-page lease keeps every page; frame/pixel/page-size caps |
| `test_ai_chunked_extraction.py` | 8 | chunk caps; every one of 500 pages reaches the model, late terms come back with the right page; conflicts flagged; same value not flagged; formatting-only differences not flagged; concessions combined; one failed chunk fails all; short documents unchanged |
| `test_upload_jobs.py` | 29 | end to end with the flag on: auth/roles; flag off = 404 and old limits; 500-page lease (regex and mocked AI, quota checked before any AI call, over-quota = no AI call); the 120 MB scan streamed (request allocates <20 MB); size/page/type limits; every format through one pipeline; 5,000-row rent rolls + re-import supersedes; bulk insert = `insert_lease`; **team isolation**; stale jobs; crash cleanup; dedup; queue down = 503; thread and RQ runners; busy database; chunked-body bypass; per-team job cap; orphan sweep; no resurrection; bulk-delete/bulk-tag regression; no duplicate function names |
| `test_large_upload_frontend.py` | 4 | every `/uploads` call the page makes is a real route; every field it reads is in a real response; flag-off page unchanged; JS parses |

**Regression tests fail before their fix** (CLAUDE.md rule). Each was
run against the commit before its fix in a throwaway worktree. Chunked
bypass: 422 with all 17,825,801 bytes read by the old route.
Bulk-delete/bulk-tag: every lease "not found". Busy database: poll
returned 500. Stale cleanup: file left behind. Resurrection: job
re-touched. BMP misread; formatting-only conflict flagged. The cap, sweep
and zip/raster limits failed on the old code because they didn't exist
yet; that's expected for new safeguards.

**Full-size runs with real OCR and no mocks**
(`backend/tests/run_large_file_scale_check.py`, not in the suite because
the scan alone takes ~5 min). Upload and job run in separate processes,
so the memory numbers are the job's own. On a shared laptop with other
sessions running (load average ~3), so treat times as ranges:

| File | Upload request | Job | Job peak memory | Found |
|---|---|---|---|---|
| 500-page text lease (0.7 MB) | <0.1 s | 4-9 s | ~100 MB | tenant, landlord, rent (p.1), deposit (p.262), renewal (p.431) |
| 300-page scan (120 MB) | 0.5 s | 319-321 s (two runs) | ~250 MB (~140 MB above the process baseline) | all 300 pages OCR'd; tenant, landlord, deposit (p.262, read by OCR) |
| 5,000-row rent roll XLSX | <0.1 s | 2-6 s | ~300 MB | 4,816 imported, 285 skipped (blank/vacant/subtotal/total) |
| 5,000-row rent roll CSV | <0.1 s | 2-9 s | ~280 MB | same |

The scan is 300 pages, so the terms planted on pages 333, 431 and 478 aren't
in it; only page 262's deposit is. Monthly rent isn't found on the scanned lease **because of my fixture,
not OCR**: the scan generator draws only the first four paragraphs of
each page, and base rent is page 1's fifth. OCR confidence on that page
is 94%. Square footage isn't found by the **regex** engine on either
lease ("approximately 12,500 rentable square feet" isn't a phrasing it
knows); the chunked AI test finds it on p.333.

**UI**, checked headlessly (never a visible browser) at 1440/768/375 px
against a local server: progress bar ("Reading page 306 of 500 (61%)"),
results, a rejected file with its full message, the 5,000-row rent roll
(first 200 rows + "…and 4,616 more"). No horizontal page overflow. A
second full run on an already-loaded database found the
database-locking problem in section 4.

**Live smoke test on the final code** (real local server, flag on, curl):
120 MB scan to `POST /uploads` -> 202 in 0.33 s, then `GET /uploads/1`
reported "Reading page 7 of 300"; a 17 MB body to the old `POST /leases`
-> 413 both chunked and with Content-Length; a program named `tool.pdf`
-> 415 with the friendly message.

## 4. Things I found along the way

1. **I broke two existing routes and fixed it** (`89d9654` -> `8fbcfce`).
   I added a `database.get_leases_by_ids` without noticing one already
   existed; mine replaced it and broke `POST /leases/bulk-delete` (500)
   and `POST /leases/bulk-tag` (everything "not found"). The full suite
   didn't catch it: those routes only had live tests. Fixed, with
   offline tests, plus a guard that fails if any module defines the same
   function twice. It was never pushed.
2. **`POST /alerts/generate` holds SQLite's write lock for 5-19 s** once a
   team has ~5,000 leases (pre-existing route; the dashboard calls it on
   load). Any other write waiting longer than Python's default 5 s fails
   with "database is locked". Upload jobs now wait up to 30 s, retry, and
   skip progress updates when busy. **Not fixed for the rest of the app**:
   it's a pre-existing problem worth its own task (batch or move alert
   generation, or turn on SQLite WAL mode).
3. **Security review (`security-auditor` + `reviewer` agents), all fixed
   before the last commit:**
   - With the flag on, a chunked request (no Content-Length) could push
     ~151 MB into the old routes, which read files into memory. Fixed:
     the body limit is decided per request, so Werkzeug enforces it either
     way.
   - Zip bombs: Office files over 64 MB uncompressed or 20,000 entries
     are refused before any parser runs (250 MB until the memory fix
     below).
   - Raster bombs: TIFF frame count checked before OCR, 60 MP per image,
     40 MP per rasterized PDF page.
   - At most 3 uploads in flight per team, plus a free-disk check.
   - Stale jobs' files are deleted, and old orphaned files swept.
   - A heartbeat can no longer revive a job already marked failed.
   - Text that starts with "BM" or "MZ" or mentions "%PDF-" is no longer
     misread as an image, program or PDF.
4. **AI errors (fixed after review, 2026-10-20):** a background upload
   whose AI step fails now shows "We couldn't finish reading this file
   with AI..." and logs the AI error and its cause with the job and team
   id. Before, the AI error's own text (e.g. the API credit balance) was
   the job's error. `POST /leases`, the deferred AI job and rent-roll
   validation on `main` still pass that text through; not changed here.
5. **Pre-existing UI:** at 375 px, long lease names in the upload results
   run past the card edge (unchanged row markup).
6. **Dashboard caches** are per-process with a 60 s TTL, so after a
   background job finishes, dashboards in other gunicorn processes catch
   up within 60 s. Same as the existing AI background job.

## 5. Recommended per-file limits

All are environment variables with these defaults; they only apply with
`LARGE_FILE_UPLOADS` on.

| Limit | Value | Why |
|---|---|---|
| Any one file | **150 MB** (`LARGE_FILE_MAX_UPLOAD_MB`) | The 300-page office-scanner fixture (200 DPI grayscale) is 120 MB, so long scans fit with headroom. The file is never held in memory, so RAM isn't what limits this; disk and upload time are. The Claude API's 32 MB limit doesn't apply: the model gets extracted text in chunks, never the file. Over the limit, the message suggests rescanning in black-and-white/grayscale or splitting. |
| Pages per file | **1,000** (`LARGE_FILE_MAX_PAGES`) | Twice the 500-page lease this was built for. OCR runs ~1 s/page on a laptop (Render will be slower), so this bounds one file at under an hour. Checked from the PDF's page tree / TIFF frame count before any OCR. |
| Word / Excel | **50 MB** (`LARGE_FILE_MAX_DOCUMENT_MB`); ≤64 MB uncompressed / 20,000 parts; XML ≤10 MB (Word) / 40 MB (Excel); Word ≤500,000 XML elements | Section 6. Images inside don't count toward the XML cap. Checked at upload from the ZIP alone. |
| CSV / TSV / TXT / .xls | **10 MB** (`LARGE_FILE_MAX_FLAT_DOCUMENT_MB`) | Read whole: a 50 MB .txt took 135 MB just to read. 10 MB is 25 times a 5,000-row rent roll and 3 times the text of a 1,000-page lease. |
| Rows per rent roll / spreadsheet | **10,000** (`LARGE_FILE_MAX_TABLE_ROWS`) | Section 6. Counted before parsing, without building the table. |
| Images | 60 MP per frame | A 48 MP phone photo fits; anything larger is scaled down or refused. |
| AI chunk | 100 pages / 180,000 chars | Section 2. |
| Uploads in flight | 3 per team (`LARGE_FILE_MAX_ACTIVE_JOBS_PER_TEAM`) | One worker runs one job at a time. |
| Old routes | 16 MB, unchanged | Not touched. |

## 6. What you'd set up on Render (and R2)

**No new Render service, no new add-on, no R2.** The job runs on the queue
(`REDIS_URL`, Upstash) and worker (`worker.py`, started by `start.sh`)
production already has, in the same container as the API, so the uploaded
file just waits on the container's own disk.

On **`abstractly-tester-api` first**, then `abstractly-api`
(Environment tab; full steps in `docs/DEPLOYMENT.md`, "Large-file
uploads"):

1. Confirm `REDIS_URL` is set (same value the AI queue uses). Without it,
   jobs run on a thread in the web process: it works, but a restart loses
   in-progress jobs, which then show "please upload it again".
2. `LARGE_FILE_UPLOADS` = `true`
3. `GUNICORN_TIMEOUT` = `300` (new variable read by `start.sh`; the
   default stays 120). Without it, a 150 MB upload over a slow connection
   is cut off at 2 minutes while it's still arriving.
4. Leave `LARGE_FILE_UPLOAD_DIR` unset (the default temp directory is
   right; don't point it at the database disk `/app/data`).

**Sizing:** the Starter instance has 512 MB. Two gunicorn workers plus the
worker idle at roughly 300 MB, and a 5,000-row rent roll job adds about
200 MB at its peak (the old in-request import already did the same
work), so a large rent roll on Starter is tight. Before testers import
big rent rolls, either move to the next instance size, or drop gunicorn
to one worker (`--workers 2` in `start.sh`). I haven't measured on
Render itself.

**When R2 (or any object storage) would become necessary**, none of
which applies today: (a) running the worker as a separate Render
Background Worker service (it couldn't see the API container's disk, nor
the SQLite file, which `worker.py` already explains); (b) more than one
API instance; (c) keeping original files so citations can be re-rendered
against the source PDF (today files are deleted after processing, by
design); (d) letting browsers upload straight to storage (presigned
URLs) to go past ~150 MB without tying up a gunicorn worker. I didn't set
up or guess at any R2 configuration.

**What I couldn't verify (blocked or out of reach tonight):**

- **Render's request size limit.** Not in Render's docs; a Render staff
  forum answer says there is none, and the docs say responses can take
  up to 100 minutes. Upload the 120 MB fixture to tester to confirm.
- **Speed and memory on Render's CPU.** All numbers here are from a
  laptop; expect slower OCR on Starter.
- **Real Anthropic calls on a 500-page lease.** All AI tests are mocked
  (CLAUDE.md); cost per 500-page lease at ~9 chunks of ~72k tokens is
  roughly 650k input tokens per extraction.
- **Python 3.11.** Prod runs 3.11; this machine only has 3.9, so the
  suite ran on 3.9 (as the other worktrees do). Nothing 3.10+ is used.

## 7. Open questions for you

1. Approve turning it on in tester (the three variables above), then try
   the fixtures?
2. Should `feature/tester-ready` pick up the page-limit bug (1H)?
3. Worth a separate task for the `POST /alerts/generate` lock (4.2)?
4. TASKS.md wasn't updated: you said this branch only, and the task
   board lives on `main`. Suggested entry: `feature/large-files-any-type`,
   `~/dev/projects/abstractly-large-files`, built, not pushed, flag off by
   default, report at `docs/plans/large-files-REPORT.md`, needs
   `/review-branch` after push.

## 6. Memory of Office conversion (review follow-up, 2026-10-20)

The server has 512 MB for everything (2 gunicorn workers + `worker.py`).
Measured peak memory above the process's starting point, each file in a
fresh process (macOS; scratch scripts, numbers below):

| What | Before | After |
|---|---|---|
| .docx with 50 MB of XML (0.2 MB on disk; old cap was 250 MB) | 352 MB | refused at upload (XML > 10 MB) |
| .docx at 10 MB of XML, 1.6 M empty paragraphs | 348 MB | refused at upload (> 500,000 elements) |
| Densest .docx lease accepted (~480,000 elements) | -- | **+110 MB** |
| Largest .docx rent roll accepted (9,999 rows) | -- | **+110 MB** |
| Rent roll parse, 9,990 rows: CSV / .xls / .xlsx | -- | +106 / +65 / +33 MB |
| 50,000-row rent roll (3 MB CSV) | 290 MB | refused before parsing (rows) |
| 50 MB .txt lease | 135 MB to read | refused at upload (> 10 MB) |

Why each limit: python-docx keeps ~200 bytes per XML element (so bytes
alone don't bound it); openpyxl streams sheets and shared strings
(~3 MB per MB); every parsed rent-roll row costs ~5.5-11 KB whatever the
format. `test_the_largest_office_files_accepted_convert_well_under_512mb`
re-measures the two worst cases on every run and fails above 200 MB.

**Not fixed, and bigger than conversion: what runs after a rent roll is
parsed.** The job then loads every lease the team has
(`get_all_effective_leases`, twice) and runs the reconciliation sweep
over all of them. A 5,000-row rent roll job peaked at ~320 MB absolute
(parse ~35 MB of it); 9,990 rows ~480 MB; 19,900 rows 724 MB. That grows
with the team's whole portfolio, not the file, and `POST
/leases/import-rent-roll` on `main` runs the same steps. Worth its own
task before teams hold ~10,000 leases. Related: a spreadsheet uploaded
as a *lease* becomes one lease per row, and the resubmission check
compares each against all the others: 1,000 rows took 7 s, 10,000 rows
didn't finish in 10 minutes (the worker is busy all that time).
