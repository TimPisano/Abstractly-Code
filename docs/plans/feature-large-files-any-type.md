# Plan: feature/large-files-any-type

Unattended overnight run (2026-10-19). The user's prompt is the spec; it
stands in for the usual `/start-task` approval step (noted in the report).
Branch only: no merge, no push, no deploy, no Render settings.

## What exists already (found while reading the code)

- `app/jobs.py` + `worker.py` + `start.sh`: an RQ queue on Redis, with the
  worker started inside the API container. Only the **AI field
  extraction** step is queued. Text extraction and OCR still run inside
  the web request.
- `app/document_extractor.py` already turns PDF/XLSX/XLS/CSV/TSV/DOCX/DOC/
  JPG/PNG/TIFF/TXT into one shared `pages` shape
  (`[{"page": N, "text": ..., "ocr_confidence"?}]`). HEIC is accepted only
  by the rent-roll importer. File type is chosen **by extension only**.

## Suspected failure points (to prove with tests first)

1. `MAX_CONTENT_LENGTH` = 16 MB (frontend also hardcodes 16 MB).
2. Upload is read into memory 3 times (`_validate_upload`, `upload_lease`,
   `_extract_leases_from_file_storage`).
3. OCR rasterizes **every page at once** (`convert_from_path(path)`):
   300 pages at 200 DPI is several GB of RAM. OCR also only triggers when
   the *whole document* has under 100 characters of text.
4. All of that runs inside the request; gunicorn `--timeout 120` kills it.
5. AI path truncates the document at 200k characters (about page 70 of a
   dense lease); later pages are silently dropped.
6. `usage_limits.check_file_limits` passes `temp_path=None` into
   `extract_pages` for PDFs, which raises inside `open(None)` and is
   swallowed, so the 150-page limit is never enforced.
7. Rent-roll import: one insert + one re-read + one commit per row, then a
   full reconciliation sweep, all inside the request.

## Approach

Everything new sits behind `LARGE_FILE_UPLOADS` (default off). With the
flag off, existing routes behave exactly as today, except true bug fixes
(item 6, and not reading the file into memory repeatedly).

- **New routes** (existing routes untouched, per CLAUDE.md):
  `POST /uploads` (multipart `file`, `kind` = `lease` | `rent_roll`,
  optional `property_address`) -> 202 with a job;
  `GET /uploads/<id>` -> status + progress (team-scoped);
  `GET /uploads/config` -> flag, max size, accepted types.
  All `@require_role(...)`, all queries scoped by `team_id`.
- **New table** `upload_jobs` (team_id NOT NULL): status, stage, progress
  current/total, message, result JSON, error, timestamps.
- **Streaming to disk**: `FileStorage.save()` to a server-named file in
  an upload dir (never the filename); SHA-256 and size computed by
  streaming; Werkzeug already spools large multipart bodies to disk.
- **Type check by content** (`app/file_types.py`): magic bytes + ZIP/OLE
  container inspection + text heuristics. Content decides how a file is
  processed; unsupported content is rejected with a friendly message.
- **Background job** (`jobs.run_upload_job(job_id)`): RQ when `REDIS_URL`
  is set (prod already has the worker), an in-process single-thread
  runner otherwise (local dev, zero install). Stale jobs (no heartbeat)
  are failed on read with a clear message.
- **OCR per page**: text layer first; OCR only pages without usable text,
  one page rasterized at a time; multi-page TIFF; HEIC via pillow-heif.
- **Chunked AI extraction**: split into page chunks within the limits
  from the official docs, extract each, merge per field with page
  citations; conflicting values across chunks are flagged and never
  silently picked as high confidence.
- **Rent roll**: same job runner; batched inserts.
- **UI**: upload view uses the new routes when the flag is on and shows a
  progress bar from `GET /uploads/<id>`.
- **Max file size**: decided after measuring the fixtures; reasoning in
  the report.

## Tests

- `tests/create_large_fixtures.py` generates `tests/fixtures/large/`
  (gitignored; too big to commit).
- Repro tests written first and run against the unfixed code; output
  saved to `docs/plans/large-files-repro.txt`.
- New test files registered in `run_all_tests.py`; Anthropic mocked.
- Full suite before every commit.

## Done

- Full suite passes (count quoted), headless screenshots of the upload UI,
  `docs/plans/large-files-REPORT.md` written.
