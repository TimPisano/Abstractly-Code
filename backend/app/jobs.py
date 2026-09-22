"""
RQ job definitions for background AI lease extraction -- replaces the
old `threading.Thread(daemon=True)` in api.py's _start_deferred_
extraction. That approach silently lost in-flight jobs whenever
gunicorn recycled a worker process (the Dockerfile runs --workers 2,
and each is its own process with its own threads), with no retry and
no record beyond the lease sitting in 'processing' forever until
fail_orphaned_processing_leases() cleaned it up at next boot. A queue
backed by Redis survives a worker restart because the job description
lives in Redis, not in one process's memory.

RQ enqueues a job by import path (module + function name), so a
separate worker process (see worker.py) can re-import and run it later
without ever importing Flask/api.py's app object at all. This module is
the one place BOTH api.py (to enqueue) and worker.py (to run) need to
import, and it deliberately does NOT import api.py at module load time:
api.py imports this module to get `extraction_queue`, so importing it
back here would be circular. run_deferred_extraction instead imports
api.py lazily, inside the function body -- safe because by the time a
job actually runs, api.py has already finished loading in every process
that touches this queue (the web process that enqueued it, and this
worker running it now).
"""
import logging
import os

import redis
from rq import Queue

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EXTRACTION_QUEUE_NAME = os.environ.get("LEASE_EXTRACTION_QUEUE", "extraction")
# Generous relative to a single request's gunicorn timeout (120s) since
# a multi-lease upload extracts every split lease in this one job.
EXTRACTION_JOB_TIMEOUT_SECONDS = int(os.environ.get("LEASE_EXTRACTION_JOB_TIMEOUT_SECONDS", "600"))

_redis_conn = redis.from_url(REDIS_URL)
extraction_queue = Queue(EXTRACTION_QUEUE_NAME, connection=_redis_conn)


def run_deferred_extraction(filename, items):
    """
    Extract each pending lease's fields and persist the result. `items`
    is a list of plain dicts (lease_id, sub_pages, date_candidates,
    index, total) built by api.py's _start_deferred_extraction --
    unchanged in shape and behavior from the old background-thread
    closure of the same name: an AI extraction error marks the lease
    'failed' with a plain reason; an unexpected bug marks it 'failed'
    generically rather than leaving it stuck 'processing' forever; a
    success writes the real fields and links telemetry.
    """
    from app import api, database, ai_extraction

    field_extractor = api.FieldExtractor()
    completed = failed = 0
    for item in items:
        try:
            fields, run_id = api._extract_one_range(item["sub_pages"], field_extractor, engine="ai")
        except ai_extraction.AIExtractionError as e:
            api._record_ai_run(None, status="error", error_message=str(e))
            database.finalize_lease_processing(item["lease_id"], status="failed", error=str(e))
            failed += 1
            continue
        except Exception:
            logger.exception("Unexpected error extracting lease %s in background job", item["lease_id"])
            database.finalize_lease_processing(
                item["lease_id"], status="failed",
                error="Something went wrong while extracting this document. Delete it and try again.",
            )
            failed += 1
            continue
        fields.pop("_ai_meta", None)
        display_name = api._default_lease_name(fields, filename, item["index"], item["total"])
        database.finalize_lease_processing(
            item["lease_id"], status="complete", extracted_fields=fields,
            date_candidates=item["date_candidates"], display_name=display_name,
        )
        if run_id:
            database.link_ai_extraction_run_to_lease(run_id, item["lease_id"])
        completed += 1

    api._invalidate_lease_derived_caches()
    try:
        if completed:
            database.insert_activity(
                "lease_uploaded",
                f"Finished processing {filename}" + (f" ({completed} lease(s))" if completed > 1 else ""),
                lease_id=items[0]["lease_id"],
            )
        if failed:
            database.insert_activity("lease_processing_failed", f"Extraction failed for {failed} lease(s) from {filename}")
    except Exception:
        logger.exception("Post-extraction activity log failed (non-fatal)")
