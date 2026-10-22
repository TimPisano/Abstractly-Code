#!/bin/sh
# Runs the RQ worker (background lease extraction) and gunicorn (the
# API) as two processes in this one container. Deliberately not two
# separate Render services: SQLite is a plain file on this container's
# own disk (see database.py), so the worker MUST share this exact
# filesystem to see the same leases the API just inserted -- a second
# Render service would get its own empty database.
#
# The worker runs in the background; gunicorn execs as PID 1 in the
# foreground so Render's health checks and log stream still see it as
# the main process. Known tradeoff at this scale: if the worker process
# dies, nothing here restarts it until the whole container next
# restarts/redeploys -- acceptable for now given the free-tier SQLite
# setup already resets on every restart anyway.
#
# GUNICORN_TIMEOUT (default 120, unchanged): a sync worker is killed if one
# request takes longer, and receiving the upload body counts. With
# LARGE_FILE_UPLOADS on, processing happens in the background, but a
# 150 MB file over a slow connection can take more than 120 s just to
# arrive -- set GUNICORN_TIMEOUT=300 when turning that flag on (see
# docs/DEPLOYMENT.md, "Large-file uploads").
set -e

python worker.py &

exec gunicorn app.api:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - --error-logfile -
