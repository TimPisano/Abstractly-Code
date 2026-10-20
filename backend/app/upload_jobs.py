"""
Background processing for large uploads (behind LARGE_FILE_UPLOADS,
default off). Leases and rent rolls of any supported type are streamed to
disk by the web request, then read, OCR'd, extracted and saved here, off
the request, with progress the browser can poll (GET /uploads/<id>).

Why: before this, everything except the AI call ran inside the upload
request -- OCR of every page, regex extraction of 500 pages, per-row
inserts of a 5,000-row rent roll -- against gunicorn's 120 s worker
timeout and 512 MB of RAM (docs/plans/large-files-repro.txt has the
measurements).

Flow:
  POST /uploads (api.py)
    -> save_upload(): stream the body to a server-named file, hashing as
       it goes (never held in memory, never named after the user's file)
    -> file_types.detect_file_type(): what the file really is
    -> database.create_upload_job() + start_job()
  start_job() -> run_upload_job(job_id), on one of two runners:
    - "rq": the existing Redis queue and worker (app/jobs.py, worker.py,
      started next to gunicorn by start.sh). Default when REDIS_URL is set.
    - "thread": a single background thread in the web process. Default
      when REDIS_URL is unset, so local dev needs no Redis. One thread, so
      two big OCR jobs never run at once in one process.
    UPLOAD_JOB_RUNNER=rq|thread overrides either default.
  run_upload_job() -> _process_lease() / _process_rent_roll(), reporting
  progress into the upload_jobs row; the stored file is deleted at the end
  whatever happens.

A job that stops reporting progress (the process died mid-run) is marked
failed the next time anyone polls it (fail_stale_jobs), so nothing sits
"processing" forever.
"""
import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app import database, file_types

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}

# ---- Limits (see docs/plans/large-files-REPORT.md, "Maximum file size") ----
# 150 MB: the 300-page scanned fixture (200 DPI grayscale, a typical office
# scanner setting) is 120 MB, so a long scanned lease fits with headroom.
# The cost of a file is in its PAGES (OCR + extraction time), which
# MAX_PAGES bounds separately; the byte cap only bounds disk use and
# upload time. Nothing here holds the file in memory, so RAM is not what
# limits it. The Claude API's 32 MB request limit doesn't apply to the
# upload: the model is sent extracted text in chunks, never the file.
MAX_UPLOAD_MB = int(os.environ.get("LARGE_FILE_MAX_UPLOAD_MB", "150"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
# Multipart framing + the small form fields ride on top of the file.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
# Spreadsheets, Word and text files are parsed fully in memory by their
# libraries (openpyxl, python-docx, xlrd, csv), so they get a lower cap.
# Real ones are a few MB at most; the 5,000-row rent roll fixture is 0.4 MB.
MAX_IN_MEMORY_DOCUMENT_MB = int(os.environ.get("LARGE_FILE_MAX_DOCUMENT_MB", "50"))
IN_MEMORY_EXTENSIONS = {"docx", "doc", "xlsx", "xlsm", "xls", "csv", "tsv", "txt"}
# 1,000 pages: twice the 500-page lease this was built for. A scanned page
# OCRs in ~2-3 s, so this caps one file at under an hour of OCR.
MAX_PAGES = int(os.environ.get("LARGE_FILE_MAX_PAGES", "1000"))

JOB_TIMEOUT_SECONDS = int(os.environ.get("LARGE_FILE_JOB_TIMEOUT_SECONDS", str(3 * 3600)))
# Each accepted upload is up to MAX_UPLOAD_MB on disk until its job ends,
# and jobs run one at a time per worker; this keeps one team (or one
# script) from filling the disk or the queue (security review of this branch).
MAX_ACTIVE_JOBS_PER_TEAM = int(os.environ.get("LARGE_FILE_MAX_ACTIVE_JOBS_PER_TEAM", "3"))
# A running job heartbeats on every page / chunk; the longest silent step is
# one AI call with its retries (~7 min worst case), so 20 min of silence
# means the process is gone. A queued job may wait behind another file's
# long OCR run on the single worker, so it gets longer.
PROCESSING_STALE_AFTER = timedelta(minutes=20)
QUEUED_STALE_AFTER = timedelta(hours=3)
STALE_MESSAGE = ("Processing stopped unexpectedly (the server restarted while working on this file). "
                 "Please upload it again.")
GENERIC_FAILURE = ("Something went wrong while processing this file. Please try again; "
                   "if it keeps happening, contact support.")

_COPY_CHUNK_BYTES = 1024 * 1024


class UploadJobError(Exception):
    """A user-facing reason this job can't finish. str(e) is shown as-is."""


class UploadTooLarge(Exception):
    pass


class _JobNoLongerActive(Exception):
    """The job row was failed (as stale) while this runner was still working on it: stop, don't overwrite."""


def enabled() -> bool:
    return os.environ.get("LARGE_FILE_UPLOADS", "").strip().lower() in _TRUTHY


def public_config() -> Dict[str, Any]:
    """What the upload page needs to know (GET /uploads/config). No secrets, nothing env-sensitive beyond the flag."""
    return {
        "large_file_uploads": enabled(),
        "max_upload_mb": MAX_UPLOAD_MB,
        "max_document_mb": MAX_IN_MEMORY_DOCUMENT_MB,
        "max_pages": MAX_PAGES,
        "accepted": {kind: {"extensions": file_types.PICKER_EXTENSIONS[kind], "label": file_types.ACCEPTED_LABEL[kind]}
                     for kind in ("lease", "rent_roll")},
    }


def upload_dir() -> str:
    path = os.environ.get("LARGE_FILE_UPLOAD_DIR") or os.path.join(tempfile.gettempdir(), "abstractly-uploads")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def has_room_for_an_upload() -> bool:
    """Enough free disk in upload_dir() for one more maximum-size upload (twice: Werkzeug's spool + our copy)."""
    return shutil.disk_usage(upload_dir()).free > 2 * MAX_REQUEST_BYTES


# Older than this, a stored upload can't belong to a live job: a job waits
# at most QUEUED_STALE_AFTER and runs at most JOB_TIMEOUT_SECONDS.
ORPHAN_AFTER_SECONDS = int(QUEUED_STALE_AFTER.total_seconds()) + JOB_TIMEOUT_SECONDS + 3600


def sweep_orphaned_files() -> int:
    """Deletes stored uploads left behind by a process that died mid-job. Returns how many."""
    cutoff = time.time() - ORPHAN_AFTER_SECONDS
    removed = 0
    directory = upload_dir()
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if name.endswith(".upload") and os.path.getmtime(path) < cutoff:
            remove_file(path)
            removed += 1
    return removed


def save_upload(file_storage) -> Tuple[str, int, str]:
    """
    Streams an uploaded werkzeug FileStorage to a new file under
    upload_dir(), 1 MB at a time, computing its size and SHA-256 on the
    way. Werkzeug has already spooled a large multipart body to its own
    temp file, so this is a disk-to-disk copy; the file is never held in
    memory. The stored name is random, never derived from the user's
    filename. Returns (path, size_bytes, sha256_hex). Raises
    UploadTooLarge (and leaves nothing behind) past MAX_UPLOAD_BYTES --
    Flask's MAX_CONTENT_LENGTH normally stops it sooner.
    """
    try:
        sweep_orphaned_files()
    except OSError:
        logger.warning("Orphaned-upload sweep failed", exc_info=True)
    path = os.path.join(upload_dir(), f"{uuid.uuid4().hex}.upload")
    digest, size = hashlib.sha256(), 0
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            stream = file_storage.stream
            while True:
                chunk = stream.read(_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise UploadTooLarge()
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        remove_file(path)
        raise
    return path, size, digest.hexdigest()


def remove_file(path: Optional[str]) -> None:
    if path:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Could not delete a stored upload", exc_info=True)


def too_large_message(size_bytes: Optional[int], limit_mb: Optional[int] = None, applies_to: str = "per file") -> str:
    limit_mb = limit_mb or MAX_UPLOAD_MB
    size = f"This file is {size_bytes / (1024 * 1024):,.0f} MB. " if size_bytes else "This file is too large. "
    return (f"{size}The limit is {limit_mb} MB {applies_to}. If it's a scan, rescanning at 200-300 DPI in "
            "black-and-white or grayscale usually makes it much smaller; or split it into parts and upload each.")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def runner_name() -> str:
    explicit = os.environ.get("UPLOAD_JOB_RUNNER", "").strip().lower()
    if explicit in ("rq", "thread"):
        return explicit
    return "rq" if os.environ.get("REDIS_URL") else "thread"


def _thread_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="upload-job")
        return _executor


def start_job(job_id: int) -> None:
    """Hands the job to the configured runner. Raises if it can't be queued (e.g. Redis unreachable); the caller fails the job."""
    if runner_name() == "rq":
        from app import jobs
        jobs.extraction_queue.enqueue(jobs.run_upload_job, job_id, job_timeout=JOB_TIMEOUT_SECONDS)
    else:
        _thread_executor().submit(run_upload_job, job_id)


def fail_stale_jobs(team_id: int) -> int:
    """Housekeeping on poll. Never fails the poll itself: if the write lock is busy, the next poll tries again."""
    now = datetime.now(timezone.utc)
    try:
        paths = database.fail_stale_upload_jobs(
            team_id, (now - PROCESSING_STALE_AFTER).isoformat(), (now - QUEUED_STALE_AFTER).isoformat(), STALE_MESSAGE,
        )
    except sqlite3.OperationalError:
        logger.info("Skipped the stale upload-job check: database busy")
        return 0
    for path in paths:
        remove_file(path)  # the runner that would have deleted it is gone
    return len(paths)


def _retry_when_locked(fn, *args, attempts: int = 4, wait_s: float = 2.0, **kwargs):
    """
    Calls fn, retrying while SQLite reports "database is locked". For the
    existing helpers this job reuses (usage log, activity feed, unit
    summaries, AI-run link), which open connections with Python's default
    5 s lock wait -- shorter than one POST /alerts/generate on a big
    portfolio holds the lock.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) or attempt == attempts:
                raise
            time.sleep(wait_s)


class _Progress:
    """Writes stage/progress into the job row -- at most twice a second, except stage changes and the final step of a stage."""

    def __init__(self, job_id: int):
        self.job_id = job_id
        self._last_write = 0.0
        self._last_stage = None

    def __call__(self, stage: str, message: str, current: Optional[int] = None, total: Optional[int] = None):
        now = time.monotonic()
        stage_changed = stage != self._last_stage
        final = current is not None and total is not None and current >= total
        if not (stage_changed or final) and now - self._last_write < 0.5:
            return
        try:
            # A heartbeat is best-effort: if the database is busy, skip it --
            # the next page or chunk reports again.
            changed = database.update_upload_job(self.job_id, busy_timeout_ms=2000, only_if_active=True,
                                                 status="processing", stage=stage, message=message,
                                                 progress_current=current, progress_total=total)
        except sqlite3.OperationalError:
            logger.info("Skipped a progress update for upload job %s: database busy", self.job_id)
            return
        if not changed:
            raise _JobNoLongerActive()
        self._last_write, self._last_stage = now, stage


def _fail(job_id: int, message: str) -> None:
    _retry_when_locked(database.update_upload_job, job_id, only_if_active=True, status="failed", stage="failed",
                       message=message, error=message, finished_at=datetime.now(timezone.utc).isoformat())


def run_upload_job(job_id: int) -> None:
    """
    The job body (RQ and thread runners both call this). Never raises: every
    outcome ends with the row 'complete' or 'failed' and the stored file
    deleted. Log lines carry only the job id -- never filenames or document
    text (CLAUDE.md: no PII in logs).
    """
    from app import ai_extraction
    from app.document_extractor import DocumentExtractionError
    from app.rent_roll_import import RentRollImportError

    job = database.get_upload_job_for_worker(job_id)
    if job is None:
        logger.warning("Upload job %s no longer exists; skipping", job_id)
        return
    if job["status"] != "queued":
        logger.warning("Upload job %s is %s, not queued; skipping", job_id, job["status"])
        return

    progress = _Progress(job_id)
    started = time.monotonic()
    try:
        progress("starting", "Starting")
        if job["kind"] == "lease":
            result = _process_lease(job, progress)
        elif job["kind"] == "rent_roll":
            result = _process_rent_roll(job, progress)
        else:
            raise UploadJobError("Unknown upload type.")
        result["elapsed_seconds"] = round(time.monotonic() - started, 1)
        changed = _retry_when_locked(database.update_upload_job, job_id, only_if_active=True, status="complete",
                                     stage="complete", message="Done", result=result,
                                     finished_at=datetime.now(timezone.utc).isoformat())
        if changed:
            logger.info("Upload job %s complete in %.1fs", job_id, result["elapsed_seconds"])
        else:
            # Its leases are saved, but the row had already been failed as
            # stale; a re-upload is answered by the duplicate check.
            logger.warning("Upload job %s finished after it was marked failed as stale", job_id)
    except _JobNoLongerActive:
        logger.warning("Upload job %s was marked failed while still running; stopped", job_id)
    except (UploadJobError, DocumentExtractionError, RentRollImportError) as e:
        _fail(job_id, str(e))
    except ai_extraction.AIExtractionError as e:
        from app import api
        api._record_ai_run(None, status="error", error_message=str(e))
        _fail(job_id, str(e))
    except Exception:
        logger.exception("Upload job %s failed unexpectedly", job_id)
        _fail(job_id, GENERIC_FAILURE)
    finally:
        remove_file(job.get("stored_path"))
        try:
            database.update_upload_job(job_id, stored_path=None)
        except Exception:
            logger.exception("Could not clear stored_path on upload job %s", job_id)


# ---------------------------------------------------------------------------
# Leases
# ---------------------------------------------------------------------------

def _pdf_page_count(path: str) -> Optional[int]:
    import pypdf
    try:
        reader = pypdf.PdfReader(path)
        if reader.is_encrypted:
            reader.decrypt("")
        return len(reader.pages)
    except Exception:
        return None  # extraction reports the real problem with a specific message


def _too_many_pages(count: int) -> UploadJobError:
    return UploadJobError(
        f"This document has {count:,} pages. The limit is {MAX_PAGES:,} pages per file. Split it into "
        "smaller files (for example, the lease and its exhibits separately) and upload each one."
    )


def _process_lease(job: Dict[str, Any], progress) -> Dict[str, Any]:
    from app import ai_extraction, api, document_extractor, usage_limits

    team_id, path, extension = job["team_id"], job["stored_path"], job["detected_type"]
    options = job.get("options") or {}
    filename = job["filename"]
    warnings: List[str] = []
    if options.get("renamed_from"):
        warnings.append(options["renamed_from"])

    if extension == "pdf":
        count = _pdf_page_count(path)
        if count is not None and count > MAX_PAGES:
            raise _too_many_pages(count)

    # Table-shaped .csv/.xlsx (e.g. this app's own exports) first, same as POST /leases.
    if extension in ("csv", "xlsx"):
        with open(path, "rb") as f:
            table_leases, _ = api._try_table_extraction(f.read(), options.get("canonical_filename") or filename, extension)
        if table_leases:
            return _store_leases(job, table_leases, warnings, page_count=None, ocr_page_count=0)

    progress("reading", "Reading the document")

    def on_page(done, total):
        progress("reading", f"Reading page {done:,} of {total:,}", done, total)

    pages = document_extractor.extract_pages_from_path(path, extension, progress=on_page, max_pages=MAX_PAGES)
    if len(pages) > MAX_PAGES:
        raise _too_many_pages(len(pages))
    ocr_page_count = sum(1 for p in pages if "ocr_confidence" in p)

    # Pages still unreadable AFTER per-page OCR are almost always blank
    # separator pages or a ruined scan of one page. The old all-or-nothing
    # rule (any one such page skips extraction for the whole document) would
    # make nearly every 500-page lease "needs OCR"; here only a document that
    # is mostly unreadable is.
    low = document_extractor.find_low_text_pages(pages)
    if low and len(low) * 2 >= len(pages):
        placeholder = api._placeholder_fields()
        return _store_leases(job, [{
            "fields": placeholder,
            "date_candidates": {"start": [], "end": []},
            "source_page_start": pages[0]["page"],
            "source_page_end": pages[-1]["page"],
            "display_name": api._default_lease_name(placeholder, filename, 0, 1),
            "processing_status": "ocr_needed",
            "processing_error": (
                f"{len(low)} of {len(pages)} page(s) had no readable text even after OCR, so extraction was "
                "skipped rather than guessing. Rescan the document (200-300 DPI, straight, good contrast) "
                "or upload a text-based version."
            ),
        }], warnings, page_count=len(pages), ocr_page_count=ocr_page_count)
    if low:
        listed = ", ".join(str(p["page"]) for p in low[:20]) + (" ..." if len(low) > 20 else "")
        warnings.append(f"{len(low)} page(s) had no readable text and were skipped (usually blank pages or a "
                        f"poor scan of that page): {listed}.")

    if api.looks_like_rent_roll_table(pages):
        raise UploadJobError(
            "This looks like a rent roll or portfolio report, not a lease -- it has far more dollar amounts "
            "and dates than a lease would. Upload it in the Rent Roll section instead, which reads each "
            "unit's own row."
        )

    # Checked here, right before extraction (the user's instruction for this
    # branch), as well as when the upload was accepted: the quota can be
    # used up by other uploads while this one waits in the queue.
    quota_message = usage_limits.check_team_quota(team_id)
    if quota_message:
        raise UploadJobError(quota_message)

    engine = ai_extraction.resolve_engine()
    field_extractor = api.FieldExtractor()
    boundaries = field_extractor.detect_lease_boundaries(pages)
    total = len(boundaries)
    results = []
    for index, (start_page, end_page) in enumerate(boundaries):
        sub_pages = [p for p in pages if start_page <= p["page"] <= end_page]
        which = f" (lease {index + 1} of {total})" if total > 1 else ""
        if engine == "ai":
            progress("extracting", f"Extracting fields with AI{which}", 0, None)

            def on_chunk(done, chunks, which=which):
                progress("extracting", f"Extracting fields with AI{which}: part {done} of {chunks}", done, chunks)

            fields = ai_extraction.extract_lease_fields_chunked(sub_pages, progress=on_chunk)
            ai_run_id = api._record_ai_run(fields, status="ok")
            fields.pop("_ai_meta", None)
        else:
            progress("extracting", f"Extracting fields{which}", index, total)
            fields, ai_run_id = field_extractor.extract_fields(sub_pages), None
        results.append({
            "fields": fields,
            "date_candidates": api._regex_date_candidates(field_extractor, sub_pages),
            "source_page_start": start_page,
            "source_page_end": end_page,
            "ai_run_id": ai_run_id,
            "display_name": api._default_lease_name(fields, filename, index, total),
        })
    return _store_leases(job, results, warnings, page_count=len(pages), ocr_page_count=ocr_page_count)


def _best_effort(what: str, fn, *args, **kwargs) -> None:
    try:
        _retry_when_locked(fn, *args, **kwargs)
    except Exception:
        logger.exception("Upload job bookkeeping failed (%s); the upload itself was saved", what)


def _store_leases(job, leases, warnings, page_count, ocr_page_count) -> Dict[str, Any]:
    from app import api, usage_limits

    team_id, filename = job["team_id"], job["filename"]
    ids = database.insert_leases_bulk([{
        "filename": filename,
        "extracted_fields": lease["fields"],
        "document_type": "lease",
        "date_candidates": lease.get("date_candidates"),
        "display_name": lease["display_name"],
        "source_page_start": lease.get("source_page_start"),
        "source_page_end": lease.get("source_page_end"),
        "processing_status": lease.get("processing_status", "complete"),
        "processing_error": lease.get("processing_error"),
        "source_kind": "document",
    } for lease in leases], team_id)
    database.set_lease_content_hash(ids, job["content_hash"], team_id)
    # The leases are saved; from here on, bookkeeping. Each step retries on a
    # busy database, and none of them may turn a saved upload into "failed".
    for lease, lease_id in zip(leases, ids):
        if lease.get("ai_run_id"):
            _best_effort("link AI telemetry", database.link_ai_extraction_run_to_lease, lease["ai_run_id"], lease_id)
    if job.get("user_id"):
        _best_effort("log usage", usage_limits.log_usage_event, team_id, job["user_id"], ids[0] if ids else None,
                     None, None, event_type="extraction")
    if len(ids) == 1:
        _best_effort("log activity", database.insert_activity, "lease_uploaded", f"Uploaded {filename}", team_id,
                     lease_id=ids[0])
    elif ids:
        _best_effort("log activity", database.insert_activity, "lease_split",
                     f"Split {filename} into {len(ids)} separate leases", team_id)
    api._invalidate_lease_derived_caches()

    resubmission = {}
    all_leases = database.get_all_effective_leases(team_id=team_id)
    for lease, lease_id in zip(leases, ids):
        if lease.get("processing_status", "complete") == "complete":
            match = api._find_possible_resubmission_target(lease["fields"], all_leases, exclude_lease_id=lease_id)
            if match:
                resubmission[str(lease_id)] = match
    return {
        "lease_ids": ids,
        "split_count": len(ids),
        "page_count": page_count,
        "ocr_page_count": ocr_page_count,
        "warnings": warnings,
        "possible_resubmission_of": resubmission,
    }


# ---------------------------------------------------------------------------
# Rent rolls
# ---------------------------------------------------------------------------

def _process_rent_roll(job: Dict[str, Any], progress) -> Dict[str, Any]:
    """
    Same parsing and the same stored result as POST /leases/import-rent-roll
    (api.import_rent_roll), with the rows written in one transaction instead
    of one connection + commit + re-read per row. The supersede and unit-
    summary steps mirror that route line for line; it is left untouched
    (CLAUDE.md: don't change existing routes), so keep the two in step.
    """
    from app import api
    from app.rent_roll_import import parse_rent_roll_file

    team_id, filename = job["team_id"], job["filename"]
    options = job.get("options") or {}
    progress("reading", "Reading the rent roll")
    with open(job["stored_path"], "rb") as f:
        file_bytes = f.read()
    parsed = parse_rent_roll_file(file_bytes, options.get("canonical_filename") or filename,
                                  options.get("property_address"))
    del file_bytes

    progress("saving", f"Saving {len(parsed['leases']):,} units")
    new_ids = database.insert_leases_bulk([{
        "filename": filename,
        "extracted_fields": lease["extracted_fields"],
        "document_type": "lease",
        "display_name": lease["display_name"],
        "source_kind": "rent_roll",
    } for lease in parsed["leases"]], team_id)

    new_buildings = {
        api._normalize_building_address(lease["extracted_fields"]["property_address"]["value"])
        for lease in parsed["leases"] if lease["extracted_fields"]["property_address"]["value"]
    } - {None}
    replaced = 0
    if new_buildings:
        new_units = {api._normalize_address(lease["extracted_fields"]["property_address"]["value"]) for lease in parsed["leases"]}
        new_id_set = set(new_ids)
        old_by_file = {}
        for old_row in database.get_all_effective_leases(team_id=team_id):
            if old_row["id"] not in new_id_set and api._is_rent_roll_import(old_row) and api._normalize_building_address(
                    api.field_value(old_row, "property_address")) in new_buildings:
                old_by_file.setdefault(old_row.get("filename"), []).append(old_row)
        to_supersede = []
        for old_rows in old_by_file.values():
            old_units = {api._normalize_address(api.field_value(r, "property_address")) for r in old_rows}
            if old_units and len(old_units & new_units) * 2 >= len(old_units):
                to_supersede.extend(old_row["id"] for old_row in old_rows)
        # One transaction instead of the route's one commit per old row.
        replaced = database.supersede_leases_bulk(to_supersede, team_id)

    for building, counts in (parsed.get("unit_summary") or {}).items():
        _retry_when_locked(database.insert_rent_roll_unit_summary, team_id, filename, building,
                           counts["occupied_units"], counts["vacant_units"], counts["down_units"])

    if new_ids:
        api._invalidate_lease_derived_caches()
        progress("reconciling", "Checking the rent roll against your leases")
        try:
            api._run_reconciliation_sweep_for_team(team_id)
        except Exception:
            logger.exception("Auto-reconciliation after a background rent roll import failed (import itself succeeded)")

    skipped_note = f" ({len(parsed['skipped_rows'])} row(s) skipped)" if parsed["skipped_rows"] else ""
    _best_effort("log activity", database.insert_activity, "rent_roll_imported",
                 f"Imported {len(new_ids)} lease(s) from {filename}{skipped_note}", team_id)

    warnings = list(parsed.get("warnings", []))
    if options.get("renamed_from"):
        warnings.insert(0, options["renamed_from"])
    result = {
        "lease_ids": new_ids,
        "imported_count": len(new_ids),
        "skipped_rows": parsed["skipped_rows"],
        "column_mapping": parsed["column_mapping"],
        "unit_summary": parsed.get("unit_summary", {}),
        "replaced_previous_rows": replaced,
        "source_kind": parsed.get("source_kind", "delimited"),
        "warnings": warnings,
    }
    if "ocr_confidence" in parsed:
        result["ocr_confidence"] = parsed["ocr_confidence"]
    return result
