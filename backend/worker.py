#!/usr/bin/env python3
"""
Runs the RQ worker that executes background lease-extraction jobs
enqueued by app.jobs (see api.py's _start_deferred_extraction). Started
as a second process alongside gunicorn in the same container (see
start.sh) rather than a separate Render service, since this app's
SQLite database is a plain file on the API container's own disk --
a separate Render service has its own container and filesystem, and
could never see that file.

Usage:
    python worker.py
"""
import logging

from app.logging_config import configure_logging
configure_logging()

from rq import Worker

from app.jobs import EXTRACTION_QUEUE_NAME, extraction_queue

logger = logging.getLogger("app.worker")

if __name__ == "__main__":
    logger.info("Starting RQ worker for queue %r", EXTRACTION_QUEUE_NAME)
    Worker([extraction_queue], connection=extraction_queue.connection).work()
