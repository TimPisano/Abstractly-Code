"""
Flask API for the lease abstraction / portfolio intelligence tool.

Three layers of endpoints:
  - Stateless single-document extraction (/extract) — unchanged from
    earlier sessions, for quick one-off use that doesn't need to persist
    anything.
  - Persisted leases (/leases, /leases/batch, amendments) — upload a
    lease document in any supported format (PDF, Excel, CSV/TSV, Word,
    image, or plain text -- see document_extractor.py), store their
    extraction results (and amendments) in SQLite.
  - Portfolio analysis (/portfolio/*, /leases/<id>/risks, /qa,
    /leases/compare, /leases/<id>/benchmark) — everything downstream of
    persisted leases: metrics, timeline, risk flags, grounded Q&A,
    comparison/benchmarking, rent roll export, and the printable report.
    These are thin wiring around the analysis modules (risk_analysis.py,
    qa_engine.py, portfolio.py, comparison.py, rent_roll_export.py,
    report.py) — the actual logic lives there, not here.
"""

from flask import Flask, request, jsonify, Response, session, redirect
from werkzeug.datastructures import FileStorage
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
import io
import logging
import os
import re
import secrets
import tempfile
import threading
import time

# Loads backend/.env (if present) into os.environ before anything below
# reads an env var from it — real deployments can just set real
# environment variables instead, load_dotenv() is a silent no-op if
# there's no .env file to find. Must run before email_service is used
# (it reads EMAIL_USER/EMAIL_APP_PASSWORD from os.environ), so this
# happens before that import.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Configure logging for the whole process before anything else logs --
# a single stdout handler + consistent format + optional email-on-error.
from app.logging_config import configure_logging
configure_logging()

from app.field_extractor import FieldExtractor, looks_like_rent_roll_table
from app import ai_extraction
from app import ai_rent_roll_validation
from app import extraction_quality
from app import document_extractor
from app.document_extractor import DocumentExtractionError
from app import database
from app import email_service
from app.risk_analysis import analyze_lease_risks
from app.qa_engine import answer_question
from app.rent_roll_import import RentRollImportError, parse_csv_rent_roll, parse_xlsx_rent_roll
from app.t12_import import T12ImportError, parse_csv_t12, parse_xlsx_t12
from app.portfolio import (
    FIELD_NAMES,
    field_value,
    _normalize_building_address,
    compute_portfolio_metrics,
    compute_expiration_timeline,
    compute_attention_items,
    compute_expiration_alerts,
    compute_portfolio_health,
    compute_cross_lease_mismatches,
    compute_lease_confidence_summary,
    compute_portfolio_confidence_summary,
    compute_loss_to_lease,
    compute_rent_roll_reconciliation,
    compute_rent_variance_outliers,
    compute_rollover_schedule,
    compute_t12_reconciliation,
    compute_tenant_concentration,
    compute_walt,
    portfolio_context_for_risk_analysis,
)
from app.comparison import compare_leases, benchmark_lease
from app.discrepancies import (
    sync_lease_risk_flags, sync_all_lease_risk_flags_bulk, sync_rent_roll_reconciliation, sync_t12_reconciliation,
    detect_discrepancy_patterns, DEFAULT_PATTERN_MIN_LEASE_COUNT,
)
from app import assignments as assignments_module
from app import obligations as obligations_module
from app import tasks as tasks_module
from app.action_items import compute_action_items
from app import assistant
from app import messaging
from app import email_accounts
from app.portfolio_history import compute_property_trends, compute_portfolio_trends
from app import cache
from app.alerts import generate_alerts, get_alert_digest
from app.investment_memo import build_investment_memo_data, generate_investment_memo_pdf, generate_investment_memo_excel
from app.portfolio_health_score import compute_portfolio_health_score, DEFAULT_STALENESS_THRESHOLD_MONTHS
from app.rent_roll_export import generate_rent_roll_csv, generate_rent_roll_excel
from app.report import generate_portfolio_report_html
from app.summary_memo import generate_lease_summary_pdf, generate_portfolio_summary_pdf, monthly_report_extra_sections
from app.sheets_export import export_to_google_sheets, SheetsExportError
from app.auth import verify_password, require_role, require_owner, current_user, hash_password


app = Flask(__name__)

# Origins allowed to send credentialed (cookie-bearing) cross-origin
# requests -- required for the admin login session cookie to work at
# all, since the frontend (served on its own port via `python3 -m
# http.server`) and the backend API are different origins in this
# project's dev setup. flask-cors requires an explicit origin list
# here (not "*") whenever supports_credentials=True; the browser itself
# also refuses a wildcard-plus-credentials combination. Extend
# ADMIN_ALLOWED_ORIGINS (comma-separated) in .env for a real deployed
# frontend origin -- nothing else about this needs to change.
_default_allowed_origins = "http://localhost:8000,http://127.0.0.1:8000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ADMIN_ALLOWED_ORIGINS", _default_allowed_origins).split(",")
    if origin.strip()
]
CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)

# CSRF (origin check on state-changing requests), HSTS + optional
# HTTPS enforcement, and standard response security headers. See
# app/security.py -- installed here so it wraps every route below.
from app.security import install_security, RateLimiter
install_security(app, ALLOWED_ORIGINS)

# One structured log line per request + a per-request id (X-Request-Id).
from app.logging_config import install_request_logging
install_request_logging(app)

# Signs the admin session cookie -- if FLASK_SECRET_KEY isn't set, a
# random key is generated, logged as a warning (every admin session is
# invalidated on the next restart, but nothing about this is silently
# insecure; a fresh random key each start is strictly safer than any
# hardcoded fallback would be). Set a real, stable FLASK_SECRET_KEY in
# backend/.env to keep admin sessions alive across restarts -- see
# .env.example for how to generate one.
#
# The generated fallback is written to a file under the OS temp dir
# (shared by every process in the same container) and re-read by any
# process that finds it already there, rather than each process just
# calling secrets.token_hex() independently -- gunicorn runs multiple
# WORKER PROCESSES for one deployment (see Dockerfile's --workers),
# each importing this module separately, so independent per-process
# secrets would sign a login's session cookie with one worker's key
# and then fail to verify it on a later request load-balanced to a
# different worker -- an intermittent, worker-dependent "Login
# required" on otherwise-valid sessions, not just a restart-boundary
# issue. Exclusive-create (O_CREAT|O_EXCL) makes whichever process
# gets there first the one whose value every other process converges
# on, even if several start at nearly the same moment.
_flask_secret_key = os.environ.get("FLASK_SECRET_KEY", "").strip()
if not _flask_secret_key:
    _fallback_secret_path = os.path.join(tempfile.gettempdir(), "abstractly_flask_secret_key")
    try:
        fd = os.open(_fallback_secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        _flask_secret_key = secrets.token_hex(32)
        os.write(fd, _flask_secret_key.encode())
        os.close(fd)
    except FileExistsError:
        with open(_fallback_secret_path, "r") as f:
            _flask_secret_key = f.read().strip()
    logging.getLogger(__name__).warning(
        "FLASK_SECRET_KEY is not set -- generated a random one, shared across this "
        "deployment's worker processes via %s. Admin login sessions will not survive "
        "a backend restart until you set a real, stable value in backend/.env (see "
        ".env.example).",
        _fallback_secret_path,
    )
app.secret_key = _flask_secret_key

# SameSite=None + Secure is what a cross-origin (different-port, and
# later different-domain) fetch with credentials actually requires --
# browsers refuse to send a SameSite=Lax/Strict cookie on a cross-site
# fetch() at all, credentials:'include' or not. Secure normally means
# "HTTPS only," but Chrome/Firefox/Safari all treat http://localhost
# (and http://127.0.0.1) as a secure context specifically for local
# development, which is what makes this work over plain HTTP here. A
# real deployment needs real HTTPS on both the frontend and backend for
# this same cookie to keep working.
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.permanent_session_lifetime = timedelta(hours=12)

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max file size
# The single source of truth for "what can be uploaded as a lease
# document" is document_extractor.SUPPORTED_EXTENSIONS -- this is just
# its key set, kept as its own name here since ALLOWED_EXTENSIONS is
# the established name every existing caller (allowed_file, error
# messages) already uses.
ALLOWED_EXTENSIONS = set(document_extractor.SUPPORTED_EXTENSIONS.keys())

# Local-only bypass for the /app access gate (see frontend/app/access-gate.js).
# Read once at process start from backend/.env (or a real env var in any
# other environment) — never from a request, so a client can't set this
# itself. Defaults to False/off, so any environment that doesn't
# explicitly set it (including a real deployment) gets the real gate.
LOCAL_DEV_MODE = os.environ.get('LOCAL_DEV_MODE', '').strip().lower() in ('1', 'true', 'yes')

logger = logging.getLogger(__name__)

# DB_PATH: points the SQLite file somewhere other than database.py's
# own default location (backend/lease_portfolio.db) -- unset almost
# everywhere (including plain local dev), so this is a no-op there.
# What it's actually for: a hosting platform's persistent disk is
# mounted at a specific path (e.g. Render's /app/data), and the
# database file needs to live ON that disk, not on the container's
# own ephemeral filesystem, to survive a restart or redeploy. Setting
# this one env var and attaching the disk is the entire upgrade -- no
# other code change, since every read/write already goes through
# database.get_connection(), which always uses whatever path was last
# configured here.
_db_path_override = os.environ.get('DB_PATH', '').strip()
if _db_path_override:
    database.configure(_db_path_override)

database.init_db()

# Demo deployment only (see demo_seed.py for why this is a separate
# database rather than a user inside the production one). Idempotent --
# no-op once the demo database already has leases.
if os.environ.get('DEMO_MODE', '').strip().lower() == 'true':
    from app.demo_seed import seed_demo_data
    seed_demo_data()

# Any lease left mid-extraction by a previous process (a background
# thread doesn't survive a restart) gets marked 'failed' with a clear
# reason, so it doesn't sit "processing" forever. See the async upload
# path (_start_deferred_extraction).
_orphaned = database.fail_orphaned_processing_leases()
if _orphaned:
    logger.warning("Marked %d lease(s) left mid-extraction by a previous process as failed", _orphaned)


# ----------------------------------------------------------------------
# Global error handlers
#
# Flask's interactive debugger (enabled by DEBUG=True) shows the full
# traceback, source code, and file paths for any unhandled exception —
# invaluable for local development, but exactly the "stack traces /
# internal file paths exposed to the frontend" this hardening pass
# checks for. These handlers return a clean, generic JSON error in
# every case; the real exception is still logged server-side (visible
# in the terminal running the server) so nothing is lost for debugging,
# it just doesn't reach the client. They're registered unconditionally
# — even with DEBUG on, a route-level 4xx (like our own 404/400 jsonify
# calls) should look the same as the framework's, and any exception we
# didn't anticipate should degrade the same way a handled one does.
# ----------------------------------------------------------------------

@app.errorhandler(400)
def handle_bad_request(e):
    return jsonify({"error": "Bad request"}), 400


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(413)
def handle_too_large(e):
    max_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    return jsonify({"error": f"File too large. Maximum size is {max_mb}MB."}), 413


@app.errorhandler(500)
def handle_server_error(e):
    logger.exception("Unhandled 500 error")
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # Catches anything not already turned into a proper HTTP error by
    # Werkzeug/Flask (e.g. an OverflowError from a route converter, a
    # database error) — without this, such an exception propagates past
    # our own try/except blocks and, in debug mode, straight into the
    # interactive debugger.
    logger.exception("Unhandled exception")
    return jsonify({"error": "Internal server error"}), 500


def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _default_lease_name(fields, filename, index, total):
    """
    Auto-generated display name for a newly-created lease: "[Tenant] -
    [Property Address]" when both were actually found, since that's
    what someone scanning a list of leases wants to see at a glance.
    Falls back to the source filename (with " - Lease N" appended only
    when this lease was one of several split out of the same PDF — a
    lone upload doesn't need a redundant "Lease 1" suffix) when tenant
    or address extraction came up empty, so the name is never blank or
    literally "None - None".
    """
    tenant = (fields.get("tenant") or {}).get("value")
    address = (fields.get("property_address") or {}).get("value")
    if tenant and address:
        return f"{tenant} - {address}"

    base_filename = filename.rsplit(".", 1)[0] if filename and "." in filename else (filename or "Untitled")
    if total > 1:
        return f"{base_filename} - Lease {index + 1}"
    return base_filename


def _try_table_extraction(file_bytes, filename, extension):
    """
    Attempts to parse a .csv/.xlsx as a headers+data-rows TABLE --
    reusing the exact same column-alias matching the dedicated rent-
    roll importer already uses (rent_roll_import.py's parse_csv_
    rent_roll/parse_xlsx_rent_roll) -- before falling back to treating
    the file as label:value prose the way document_extractor.py's
    _rows_to_lines does.

    Why this exists: this app's own exports (single-lease
    /leases/<id>/export.xlsx AND the portfolio-wide rent-roll export)
    are ALWAYS table-shaped -- one header row, one or more data rows.
    Without this, re-uploading one of them through the general upload
    or resubmit path fell through to _rows_to_lines, which joins each
    row's cells into ONE space-separated line (documented there as
    deliberately built for a label:value spreadsheet, e.g. a "Tenant:"
    cell next to an "Acme Corp" cell on the same row) -- collapsing a
    header row into "Filename Tenant Landlord Property Address..." and
    a data row into "sample_lease.pdf John Smith Property Management
    LLC...", which FieldExtractor's label:value regex then matches
    against essentially at random, producing confidently wrong values
    (a header word as a "value", a landlord name as a "tenant") rather
    than an honest failure. Found live, reproduced exactly by
    re-uploading this app's own single-lease export through the
    general upload endpoint.

    Returns (leases, None) if table parsing found at least one row
    with at least one recognizable core field (tenant, rent_amount, or
    property_address) -- same list-of-dicts shape
    _extract_leases_from_file_storage's caller expects, ready to hand
    straight to database.insert_lease. Returns (None, None) if table
    parsing found nothing usable at all (most likely a genuine
    label:value spreadsheet, not a table, or an unrecognized column
    layout) -- the caller falls back to prose extraction in that case,
    so a real label:value spreadsheet lease keeps working exactly as
    before. Never raises; a malformed file just falls back too.
    """
    try:
        if extension == "csv":
            parsed = parse_csv_rent_roll(file_bytes, filename)
        else:
            parsed = parse_xlsx_rent_roll(file_bytes, filename)
    except RentRollImportError:
        return None, None

    leases = []
    for lease_data in parsed["leases"]:
        fields = lease_data["extracted_fields"]
        if not any((fields.get(name) or {}).get("value") for name in ("tenant", "rent_amount", "property_address")):
            continue
        leases.append({
            "fields": fields,
            "date_candidates": None,
            "source_page_start": None,
            "source_page_end": None,
            "display_name": lease_data["display_name"],
        })
    return (leases, None) if leases else (None, None)


def _confidence_counts(fields):
    """Tally the 15 extracted-field entries by confidence tier -- shared by AI-run telemetry and nothing else."""
    counts = {"high": 0, "medium": 0, "low": 0, "not_found": 0}
    for name in FIELD_NAMES:
        entry = fields.get(name) or {}
        tier = entry.get("confidence")
        counts[tier if tier in ("high", "medium", "low") else "not_found"] += 1
    return counts


def _record_ai_run(fields, status="ok", error_message=None):
    """
    Write one ai_extraction_runs telemetry row for a completed (or
    failed) model extraction. Never raises -- telemetry must not be
    able to fail an upload. Returns the run id, or None.
    """
    try:
        meta = (fields or {}).get("_ai_meta") or {}
        counts = _confidence_counts(fields or {})
        return database.record_ai_extraction_run(
            engine="ai",
            status=status,
            model=meta.get("model") or ai_extraction.DEFAULT_MODEL,
            kind="lease_abstraction",
            field_count=len(FIELD_NAMES),
            found_count=meta.get("found_count"),
            high_count=counts["high"],
            medium_count=counts["medium"],
            low_count=counts["low"],
            not_found_count=counts["not_found"],
            latency_ms=meta.get("latency_ms"),
            input_tokens=meta.get("input_tokens"),
            output_tokens=meta.get("output_tokens"),
            error_message=error_message,
        )
    except Exception:
        logger.exception("Failed to record AI extraction telemetry (non-fatal)")
        return None


def _placeholder_fields():
    """A full not-found field set for a lease whose real extraction is still running in the background."""
    return {name: {"value": None, "source": None, "confidence": None} for name in FIELD_NAMES}


def _regex_date_candidates(field_extractor, sub_pages):
    return {
        "start": field_extractor.find_all_date_candidates(sub_pages, "start"),
        "end": field_extractor.find_all_date_candidates(sub_pages, "end"),
    }


def _extract_one_range(sub_pages, field_extractor, engine):
    """
    Extract one lease's fields from its own page range with `engine`
    ('ai' or 'regex'). Returns (fields, ai_run_id). On the AI path,
    `fields` still carries its private `_ai_meta` key (the caller pops
    it) and a telemetry row has been written. Raises
    ai_extraction.AIExtractionError straight through on an AI failure.
    """
    if engine == "ai":
        fields = ai_extraction.extract_lease_fields(sub_pages)
        ai_run_id = _record_ai_run(fields, status="ok")
        return fields, ai_run_id
    return field_extractor.extract_fields(sub_pages), None


def _async_extraction_enabled():
    """
    Whether an AI-engine upload should return immediately and finish
    extraction on a background thread. Default on (a 5-15s-per-lease
    model call otherwise blocks the request and risks a gunicorn
    worker timeout + partial write on a large multi-lease document).
    LEASE_ASYNC_EXTRACTION=false forces the old synchronous behavior --
    used by the test suite and available as an operator escape hatch.
    """
    return (os.environ.get("LEASE_ASYNC_EXTRACTION", "true").strip().lower() not in ("0", "false", "no", "off"))


def _split_and_extract(pages, field_extractor):
    """
    Synchronous split + extract: boundary-detect (regex, cheap) then
    extract each lease's fields with the configured engine. Returns a
    list of {"fields", "date_candidates", "source_page_start",
    "source_page_end", "ai_run_id"}. Used by the regex path and by any
    caller that opts out of async (resubmit, amendment, /extract).

    date_candidates stays regex-derived regardless of engine -- it's a
    cross-section date-consistency signal risk_analysis consumes, not a
    user-facing value. Raises ai_extraction.AIExtractionError straight
    through if a model call fails.
    """
    engine = ai_extraction.resolve_engine()
    boundaries = field_extractor.detect_lease_boundaries(pages)
    results = []
    for start_page, end_page in boundaries:
        sub_pages = [p for p in pages if start_page <= p["page"] <= end_page]
        fields, ai_run_id = _extract_one_range(sub_pages, field_extractor, engine)
        fields.pop("_ai_meta", None)
        results.append({
            "fields": fields,
            "date_candidates": _regex_date_candidates(field_extractor, sub_pages),
            "source_page_start": start_page,
            "source_page_end": end_page,
            "ai_run_id": ai_run_id,
        })
    return results


def _extract_leases_from_file_storage(file_storage, defer_ai=False):
    """
    Shared pipeline: save an uploaded werkzeug FileStorage to a temp
    path, then either parse it as a table (.csv/.xlsx -- see
    _try_table_extraction) or run document_extractor.extract_pages()
    to get this file's text into the one shape every prose format
    shares (see that module's docstring), then
    FieldExtractor.extract_multiple_leases() to split it into one or
    more per-lease results — a genuine single-lease document always
    comes back as exactly one result (same fields/confidence/
    citations extract_fields() alone would have produced). A real
    multi-lease document instead comes back as N independent results,
    each extracted only from its own page range — see DECISIONS.md
    for why that matters (fields and risk-relevant date candidates
    used to bleed across the constituent leases).

    Every supported file format (PDF, Excel, CSV/TSV, Word, images,
    plain text) goes through this same function; a .csv/.xlsx tries
    table extraction first and only falls through to the prose path
    (shared with every other format) if that finds nothing usable.

    Returns (leases, None) on success, where `leases` is a non-empty
    list of dicts: {"fields": {...}, "date_candidates": {...},
    "source_page_start": N, "source_page_end": M, "display_name": "..."}
    — or (None, (error_message, http_status)) on failure. Callers turn
    the error into a JSON response themselves, since batch endpoints
    need to report a per-file error without aborting the whole request.
    """
    temp_path = None
    try:
        raw_extension = file_storage.filename.rsplit('.', 1)[1].lower() if '.' in (file_storage.filename or '') else ''
        # The filename comes from the upload's Content-Disposition and is
        # fully attacker-controlled. Every caller runs allowed_file()
        # first (which only permits a known short extension), but sanitize
        # here too so a temp-file suffix can never carry a path separator
        # or other junk regardless of how this is reached.
        extension = re.sub(r'[^a-z0-9]', '', raw_extension)[:10]
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}' if extension else '') as temp_file:
            temp_path = temp_file.name
            file_storage.save(temp_path)

        with open(temp_path, 'rb') as f:
            file_bytes = f.read()

        if extension in ('csv', 'xlsx'):
            table_leases, _ = _try_table_extraction(file_bytes, file_storage.filename, extension)
            if table_leases is not None:
                return table_leases, None
            # Table parsing found nothing usable -- fall through to the
            # shared prose path below, same as every other format.

        try:
            pages = document_extractor.extract_pages(file_bytes, file_storage.filename, temp_path)
        except DocumentExtractionError as e:
            return None, (str(e), 422)

        # Checked before ANY extraction runs, including boundary
        # detection -- both are regex-driven and equally unreliable
        # against a page that isn't real recognized text in the first
        # place. Rather than silently returning "Not Found" for
        # whatever fields would have come from an unreadable page
        # (indistinguishable from the source genuinely not stating
        # them), the whole document is persisted as one lease in
        # 'ocr_needed' status with placeholder (all-null) fields and a
        # message naming exactly which pages triggered it. See
        # document_extractor.find_low_text_pages.
        low_text_pages = document_extractor.find_low_text_pages(pages)
        if low_text_pages:
            page_list = ", ".join(
                f"page {p['page']} ({p['reason'][0].lower()}{p['reason'][1:-1]})" for p in low_text_pages
            )
            placeholder_fields = _placeholder_fields()
            return [{
                "fields": placeholder_fields,
                "date_candidates": {"start": [], "end": []},
                "source_page_start": pages[0]["page"],
                "source_page_end": pages[-1]["page"],
                "display_name": _default_lease_name(placeholder_fields, file_storage.filename, 0, 1),
                "looks_like_lease": True,  # unknown until OCR'd -- don't pre-flag as "not a lease" on top of "unreadable"
                "processing_status": "ocr_needed",
                "processing_error": (
                    f"{len(low_text_pages)} of {len(pages)} page(s) appear to be scanned images with no "
                    f"usable text layer, so extraction was skipped rather than guessing: {page_list}. "
                    "Re-scan with OCR, or upload a text-based version of this document."
                ),
            }], None

        if looks_like_rent_roll_table(pages):
            # Running the single-lease extractor against a portfolio
            # rent roll doesn't fail cleanly -- it confidently returns
            # WRONG values (one unit's rent presented as "the" lease's
            # rent, a column header word as the tenant name, a
            # portfolio-wide aggregate as a per-lease figure), which is
            # worse than an honest error. Caught here, before
            # extraction ever runs, rather than after -- see
            # looks_like_rent_roll_table's docstring and DECISIONS.md
            # for the real example that prompted this.
            return None, (
                "This looks like a rent roll or portfolio report, not a single lease document -- "
                "it has far more dollar amounts and dates than a lease would state. Upload it to "
                "POST /leases/import-rent-roll instead, which is built to read each unit's own row.",
                422,
            )

        field_extractor = FieldExtractor()

        # Async path: the model engine is active, the caller allows
        # deferral, and async is enabled. Do only the cheap synchronous
        # work here (boundary detection) and hand each lease's page
        # range back as "pending" -- the caller persists placeholder
        # rows and a background thread fills in the fields. Keeps the
        # upload request fast and off gunicorn's worker timeout.
        if defer_ai and _async_extraction_enabled() and ai_extraction.resolve_engine() == "ai":
            boundaries = field_extractor.detect_lease_boundaries(pages)
            total = len(boundaries)
            leases = []
            for index, (start_page, end_page) in enumerate(boundaries):
                sub_pages = [p for p in pages if start_page <= p["page"] <= end_page]
                leases.append({
                    "pending": True,
                    "sub_pages": sub_pages,
                    "fields": _placeholder_fields(),
                    "date_candidates": _regex_date_candidates(field_extractor, sub_pages),
                    "source_page_start": start_page,
                    "source_page_end": end_page,
                    "display_name": _default_lease_name(_placeholder_fields(), file_storage.filename, index, total),
                    "looks_like_lease": True,  # unknown until extraction finishes; don't pre-flag as non-lease
                    "index": index,
                    "total": total,
                })
            return leases, None

        split_results = _split_and_extract(pages, field_extractor)

        total = len(split_results)
        leases = []
        for index, result in enumerate(split_results):
            leases.append({
                "fields": result["fields"],
                "date_candidates": result["date_candidates"],
                "source_page_start": result["source_page_start"],
                "source_page_end": result["source_page_end"],
                "ai_run_id": result.get("ai_run_id"),
                "display_name": _default_lease_name(result["fields"], file_storage.filename, index, total),
                "looks_like_lease": _looks_like_lease(result["fields"]),
            })
        return leases, None

    except ai_extraction.AIExtractionError as e:
        # A model-backed extraction that failed or came back unusable.
        # Surface the plain-language reason and a 502 -- never fall back
        # to regex silently (a confident wrong answer is worse than an
        # honest "couldn't process this"), and never a 500 traceback.
        logger.warning("AI extraction failed for uploaded document: %s", e)
        return None, (str(e), 502)

    except Exception:
        # The real exception (which can include the temp file's path,
        # e.g. a FileNotFoundError) is logged server-side only — the
        # client gets a generic message, never str(e) verbatim.
        logger.exception("Error processing uploaded document")
        return None, ("Error processing this file. It may be corrupted or unsupported.", 500)

    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _validate_upload():
    """Common validation for a single-file upload request. Returns (file_storage, error_response_or_none)."""
    if 'file' not in request.files:
        return None, (jsonify({"error": "No file uploaded"}), 400)

    file = request.files['file']

    if file.filename == '':
        return None, (jsonify({"error": "No file selected"}), 400)

    if not allowed_file(file.filename):
        supported = "PDF, Excel (.xlsx/.xls/.xlsm), CSV/TSV, Word (.docx/.doc), images (.jpg/.png/.tiff), or plain text (.txt)"
        return None, (jsonify({"error": f"Unsupported file type. Please upload one of: {supported}."}), 400)

    return file, None


# ----------------------------------------------------------------------
# Stateless single-document extraction (no persistence)
# ----------------------------------------------------------------------

@app.route('/extract', methods=['POST'])
@require_role()
def extract_lease_data():
    """
    Extract lease data from an uploaded document without persisting it.
    Login required -- this runs the full (potentially model-backed,
    billable) extraction pipeline, so it must not be anonymous.

    Expects: multipart form data with a 'file' field containing a
    lease document in any supported format -- PDF, Excel (.xlsx/.xls/
    .xlsm), CSV/TSV, Word (.docx/.doc), an image (.jpg/.png/.tiff, run
    through OCR), or plain text (.txt). See document_extractor.py:
    every format is converted to the same page-text shape before
    extraction, so the response below looks identical regardless of
    which format was uploaded.
    Returns: {"leases": [{"display_name":..., "source_page_start":...,
    "source_page_end":..., "fields": {one entry per extracted field,
    each shaped as {"value":..., "source": {"page":N, "quote":"..."} |
    null, "confidence": "high"|"medium"|"low"|null}}}, ...]} — always a
    list, even for a single-lease document (a list of one), so a
    caller never needs two different response shapes depending on
    whether the file turned out to contain more than one lease.
    Error responses: 400 (no/invalid file), 422 (a real, specific
    reason this exact file can't be processed -- password-protected,
    corrupted, no readable text/content, etc.), 500 (unexpected
    extraction failure).
    """
    file, error = _validate_upload()
    if error:
        return error

    leases, error = _extract_leases_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    return jsonify({"leases": leases}), 200


# ----------------------------------------------------------------------
# Persisted leases (portfolio)
# ----------------------------------------------------------------------

# The fields that identify a document as an actual lease -- if every
# one of these came back not-found, extraction technically "succeeded"
# (real text was pulled from a real PDF) but the document almost
# certainly isn't a lease at all: a cover letter, an unrelated report,
# a blank/near-blank scan. Same field set as portfolio.py's
# CORE_FIELDS_FOR_COMPLETENESS -- not imported from there directly
# since that module's meaning ("missing some fields, needs review") is
# a different, narrower question than this one ("might not be a lease
# at all"), even though the underlying fields happen to coincide.
_LEASE_IDENTITY_FIELDS = ["tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date"]


def _looks_like_lease(extracted_fields) -> bool:
    return any((extracted_fields.get(name) or {}).get("value") for name in _LEASE_IDENTITY_FIELDS)


def _lease_summary(lease):
    """Trim a DB lease record down to what list views need, keeping full extracted_fields (the dashboard needs most columns anyway)."""
    processing_status = lease.get("processing_status") or "complete"
    return {
        "id": lease["id"],
        "filename": lease["filename"],
        "display_name": lease.get("display_name") or lease["filename"],
        "uploaded_at": lease["uploaded_at"],
        "document_type": lease["document_type"],
        "base_lease_id": lease["base_lease_id"],
        "amendment_count": lease.get("amendment_count", 0),
        "extracted_fields": lease["extracted_fields"],
        # A lease still being extracted has all-null fields -- don't
        # pre-flag it as "doesn't look like a lease" until it's done.
        "looks_like_lease": True if processing_status in ("processing", "ocr_needed") else _looks_like_lease(lease["extracted_fields"]),
        "confidence_summary": compute_lease_confidence_summary(lease),
        "source_page_start": lease.get("source_page_start"),
        "source_page_end": lease.get("source_page_end"),
        "tags": lease.get("tags", []),
        "status": lease.get("status") or "active",
        "version_number": lease.get("version_number") or 1,
        "supersedes_lease_id": lease.get("supersedes_lease_id"),
        "processing_status": processing_status,
        "processing_error": lease.get("processing_error"),
    }


def _invalidate_lease_derived_caches():
    """
    Called after anything that changes which leases exist or what
    their extracted fields say (upload, batch upload, rent-roll
    import, amendment, delete, bulk-delete) -- clears the cached
    portfolio trends (both the portfolio-wide and every per-property
    entry, since "trends" is a shared prefix) and the cached health
    score, both of which walk the full lease list and would otherwise
    keep returning a now-stale answer for up to the cache's TTL. See
    app/cache.py's module docstring for the full invalidation strategy.

    Also clears "effective_leases" -- the raw get_all_effective_leases()
    result itself is cached (see the portfolio-wide GET routes below),
    since several of them were independently re-running that same
    full-portfolio scan on every dashboard load.
    """
    cache.invalidate("trends")
    cache.invalidate("health_score")
    cache.invalidate("effective_leases")


def _invalidate_discrepancy_derived_caches():
    """
    Called after a discrepancy is resolved or reopened -- the health
    score's "unresolved discrepancies" component depends on exactly
    this, so a cached score would otherwise keep reporting the old
    open/resolved count for up to the cache's TTL. Trends don't depend
    on discrepancies at all, so only the health-score cache needs
    clearing here, not "trends".
    """
    cache.invalidate("health_score")


def _run_reconciliation_sweep():
    """
    Re-runs the two reconciliation checks that a static "upload once,
    read once" tool can't offer: rent-roll-vs-lease-PDF (compute_rent_
    roll_reconciliation) and lease risk flags / cross-lease mismatches
    (the same computation GET /portfolio/risks does, reused verbatim so
    this can never disagree with what that route reports) -- against
    whatever leases exist RIGHT NOW, not just at initial upload time.

    T12-vs-rent-roll reconciliation is deliberately NOT re-run here: a
    T12 file is never persisted (see sync_t12_reconciliation's own
    docstring), so there is nothing to recompute against without a
    fresh upload -- that discrepancy already syncs at upload time, in
    portfolio_t12_reconciliation() itself.

    Ends with generate_alerts() so a fresh discrepancy is reflected in
    the alerts feed (new_discrepancy alerts) immediately, not only the
    next time something else happens to call it.

    Called both from import_rent_roll() (automatic, fire-and-forget --
    a new rent roll should re-check itself without a separate manual
    step) and from POST /portfolio/reconciliation/run (the explicit
    "Run reconciliation" trigger for everything else, including a
    lease PDF re-upload or amendment that this sweep alone wouldn't
    have a reason to fire from). Returns counts for the caller to log/
    return; safe to call as often as needed -- every step here is
    upsert-by-natural-key, so re-running against unchanged data
    produces zero new rows.
    """
    leases = database.get_all_effective_leases()

    rent_roll_result = compute_rent_roll_reconciliation(leases)
    sync_rent_roll_reconciliation(rent_roll_result["mismatches"])

    context = portfolio_context_for_risk_analysis(leases)
    cross_lease_mismatches = compute_cross_lease_mismatches(leases)
    per_lease_flags = []
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        cross_lease_flags = cross_lease_mismatches.get(lease["id"], [])
        flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates, cross_lease_flags)
        per_lease_flags.append((lease["id"], flags))
    sync_all_lease_risk_flags_bulk(per_lease_flags)

    _invalidate_discrepancy_derived_caches()
    alert_result = generate_alerts()

    return {
        "leases_checked": len(leases),
        "rent_roll_mismatches": len(rent_roll_result["mismatches"]),
        "new_alerts": alert_result["created"],
    }


def _persist_split_leases(filename, split_leases):
    """
    Persists every lease FieldExtractor.extract_multiple_leases()
    produced from one uploaded file as its own independent leases row —
    never merged or averaged together, regardless of whether there was
    1 or 100 of them. Returns the list of full lease summaries (each
    with tags attached — freshly inserted, so always empty). Does NOT
    log activity itself — callers log their own single/batch-appropriate
    entry, see upload_lease/upload_leases_batch.
    """
    created = []
    for lease_data in split_leases:
        lease_id = database.insert_lease(
            filename,
            lease_data["fields"],
            document_type="lease",
            date_candidates=lease_data["date_candidates"],
            display_name=lease_data["display_name"],
            source_page_start=lease_data["source_page_start"],
            source_page_end=lease_data["source_page_end"],
            processing_status="processing" if lease_data.get("pending") else lease_data.get("processing_status", "complete"),
            processing_error=lease_data.get("processing_error"),
        )
        if lease_data.get("ai_run_id"):
            database.link_ai_extraction_run_to_lease(lease_data["ai_run_id"], lease_id)
        lease_data["lease_id"] = lease_id  # so a deferred-extraction caller can find its rows
        # get_lease(), not get_effective_lease(): this lease was just
        # inserted with no amendments yet, so the amendment-merged
        # fields are identical to its own raw fields -- get_effective_lease
        # would spend 2 extra DB round-trips per lease confirming that.
        lease = dict(database.get_lease(lease_id))
        lease["amendment_count"] = 0
        lease["tags"] = []
        created.append(_lease_summary(lease))
    if created:
        _invalidate_lease_derived_caches()
    return created


def _start_deferred_extraction(filename, split_leases):
    """
    Kick off the background thread that runs AI extraction for every
    'pending' lease `_persist_split_leases` just inserted. Returns True
    if a thread was started. The thread: extracts each range, writes the
    real fields (or marks the row 'failed' with a plain reason on an AI
    error), links telemetry, invalidates caches, logs one activity
    entry. It touches only `database` and pure helpers -- never `request`
    or `session` -- so it's safe off the request context.
    """
    pending = [ld for ld in split_leases if ld.get("pending") and ld.get("lease_id")]
    if not pending:
        return False

    items = [{
        "lease_id": ld["lease_id"],
        "sub_pages": ld["sub_pages"],
        "date_candidates": ld["date_candidates"],
        "index": ld.get("index", i),
        "total": ld.get("total", len(pending)),
    } for i, ld in enumerate(pending)]

    def _run():
        field_extractor = FieldExtractor()
        completed = failed = 0
        for item in items:
            try:
                fields, run_id = _extract_one_range(item["sub_pages"], field_extractor, engine="ai")
            except ai_extraction.AIExtractionError as e:
                _record_ai_run(None, status="error", error_message=str(e))
                database.finalize_lease_processing(item["lease_id"], status="failed", error=str(e))
                failed += 1
                continue
            except Exception:
                # An unexpected bug must not leave the lease stuck
                # 'processing' forever -- mark it failed with a generic
                # message (details are logged), same as any other
                # failure path.
                logger.exception("Unexpected error extracting lease %s in background", item["lease_id"])
                database.finalize_lease_processing(
                    item["lease_id"], status="failed",
                    error="Something went wrong while extracting this document. Delete it and try again.",
                )
                failed += 1
                continue
            fields.pop("_ai_meta", None)
            display_name = _default_lease_name(fields, filename, item["index"], item["total"])
            database.finalize_lease_processing(
                item["lease_id"], status="complete", extracted_fields=fields,
                date_candidates=item["date_candidates"], display_name=display_name,
            )
            if run_id:
                database.link_ai_extraction_run_to_lease(run_id, item["lease_id"])
            completed += 1

        _invalidate_lease_derived_caches()
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

    threading.Thread(target=_run, name=f"extract:{filename}", daemon=True).start()
    return True


def _find_possible_resubmission_target(fields, all_leases, exclude_lease_id=None):
    """
    Requirement-1's "detect" half: a soft, advisory match against
    currently-active leases by (normalized property address, exact
    tenant name) -- deliberately exact-normalized rather than fuzzy, so
    this only ever fires on a genuinely confident match, never a
    guess that could point someone at the wrong lease. Returns a
    {"lease_id", "display_name", "reason"} dict, or None if there's no
    single confident match (including when the newly-extracted fields
    are missing tenant or property_address entirely -- nothing to
    match on). This never blocks or alters what gets created; it's
    surfaced to the caller as a hint the frontend can turn into a
    "did you mean to replace an existing lease?" prompt.

    `all_leases` is fetched once by the caller and reused across every
    lease in a multi-lease upload, rather than this function re-running
    a full get_all_effective_leases() scan per lease.
    """
    tenant = (field_value({"extracted_fields": fields}, "tenant") or "").strip().lower()
    address = _normalize_building_address(field_value({"extracted_fields": fields}, "property_address"))
    if not tenant or not address:
        return None

    matches = []
    for lease in all_leases:
        if lease["id"] == exclude_lease_id:
            continue
        other_tenant = (field_value(lease, "tenant") or "").strip().lower()
        other_address = _normalize_building_address(field_value(lease, "property_address"))
        if other_tenant == tenant and other_address == address:
            matches.append(lease)

    if len(matches) != 1:
        return None
    match = matches[0]
    return {
        "lease_id": match["id"],
        "display_name": match.get("display_name") or match["filename"],
        "reason": "Same tenant and property address as an existing active lease.",
    }


@app.route('/leases', methods=['POST'])
@require_role('analyst')
def upload_lease():
    """
    Upload a single lease document (PDF, Excel, CSV/TSV, Word, image,
    or plain text -- see document_extractor.py), extract its fields,
    and persist it as one or more base leases — one PER LEASE actually
    found in the file (see FieldExtractor.extract_multiple_leases). An
    ordinary single-lease document still produces exactly one lease,
    same as before, regardless of which format it arrived in.

    Each created lease is checked against the current portfolio for a
    likely resubmission match (same tenant + property address) -- see
    _find_possible_resubmission_target. A match is only ever a hint
    (`possible_resubmission_of`, null when there isn't one); this route
    always creates a new lease exactly as before. To actually REPLACE
    an existing lease rather than create a second one alongside it, use
    POST /leases/<id>/resubmit instead -- the explicit, auditable path
    requirement 1's "let the user select 'replace existing lease'"
    describes.
    """
    file, error = _validate_upload()
    if error:
        return error

    filename = file.filename
    split_leases, error = _extract_leases_from_file_storage(file, defer_ai=True)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    created = _persist_split_leases(filename, split_leases)

    if _start_deferred_extraction(filename, split_leases):
        # Model-backed extraction is running in the background. The
        # leases exist now, in 'processing' state; the client polls
        # GET /leases/<id> until processing_status is 'complete' or
        # 'failed'. 202 = accepted, not yet done.
        return jsonify({
            "leases": created,
            "split_count": len(created),
            "processing": True,
        }), 202

    all_leases = database.get_all_effective_leases()
    for lease_data, summary in zip(split_leases, created):
        summary["possible_resubmission_of"] = _find_possible_resubmission_target(
            lease_data["fields"], all_leases, exclude_lease_id=summary["id"]
        )
    if len(created) == 1:
        database.insert_activity("lease_uploaded", f"Uploaded {filename}", lease_id=created[0]["id"])
    else:
        database.insert_activity("lease_split", f"Split {filename} into {len(created)} separate leases")

    return jsonify({"leases": created, "split_count": len(created)}), 201


_SAMPLE_LEASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'sample_lease.pdf')


@app.route('/leases/sample', methods=['POST'])
@require_role('analyst')
def upload_sample_lease():
    """
    One-click "try it with sample data" for a first-time user: runs a
    bundled real lease PDF through the exact same extraction/persist
    pipeline as POST /leases (never a canned/fake response), so what
    the user sees is genuinely what the product does. The created
    lease is tagged "Sample" so it's obviously not real portfolio data
    and easy to filter out or delete from the normal lease list/detail
    view -- no separate deletion mechanism needed.
    """
    with open(_SAMPLE_LEASE_PATH, 'rb') as f:
        file_storage = FileStorage(stream=io.BytesIO(f.read()), filename='sample_lease.pdf', content_type='application/pdf')

    split_leases, error = _extract_leases_from_file_storage(file_storage)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    created = _persist_split_leases('sample_lease.pdf', split_leases)
    for summary in created:
        database.add_lease_tag(summary["id"], "Sample")
        summary["tags"] = ["Sample"]

    database.insert_activity("lease_uploaded", "Tried the sample lease", lease_id=created[0]["id"])
    return jsonify({"leases": created, "split_count": len(created)}), 201


@app.route('/leases/<int:lease_id>/resubmit', methods=['POST'])
@require_role('analyst')
def resubmit_lease(lease_id):
    """
    Upload a corrected/updated version of an EXISTING lease -- Canvas-
    style resubmission: replaces what's current, doesn't create a
    duplicate. Expects the same multipart 'file' field as POST /leases.

    What happens, in order:
      1. The existing lease must be active (not itself already
         superseded -- resubmit the CURRENT version, not an old one;
         see GET /leases/<id>/versions to find it).
      2. The new file is extracted exactly like a normal upload. It
         must contain exactly one lease -- a resubmission is a
         corrected version of ONE specific document, not a place to
         discover new leases (a file that splits into several should go
         through POST /leases or /leases/batch instead).
      3. A new lease row is inserted (v = old version + 1), and every
         reference that follows "the lease" rather than "the specific
         extraction" -- discrepancies, tags, comments, the assignment
         record -- is repointed from the old row to the new one (see
         database.repoint_lease_references). Amendments deliberately
         stay attached to the OLD row -- see that function's own
         docstring for why carrying them forward would silently let a
         stale amendment keep overriding the very field this
         resubmission is meant to correct.
      4. Risk analysis (single-lease flags + cross-lease mismatches) is
         re-run against the new data via the same sync path every other
         risk computation uses. Any discrepancy that was open and tied
         to this lease but ISN'T re-detected this pass is automatically
         resolved (system-attributed, in the same permanent resolution
         log a human resolve/reopen writes to) -- a genuinely new issue
         the new data raises creates a new discrepancy exactly like it
         would for any other lease.
      5. The old lease is marked superseded -- it stops appearing in
         GET /leases, the dashboard, exports, and every other "current
         portfolio" view, but stays fetchable at its own id forever
         (GET /leases/<old_id>, GET /leases/<old_id>/versions).
    """
    old_lease = database.get_lease(lease_id)
    if not old_lease:
        return jsonify({"error": "Lease not found"}), 404
    if old_lease.get("document_type") != "lease":
        return jsonify({"error": "Only a base lease can be resubmitted, not an amendment."}), 400
    if old_lease.get("status") == "superseded":
        current = _current_version_of(lease_id)
        return jsonify({
            "error": "This lease has already been superseded by a later resubmission.",
            "current_lease_id": current["id"] if current else None,
        }), 409

    file, error = _validate_upload()
    if error:
        return error

    filename = file.filename
    split_leases, error = _extract_leases_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status
    if len(split_leases) != 1:
        return jsonify({
            "error": f"Resubmission expects a single lease in the file, found {len(split_leases)}. "
                     "Upload a document containing multiple leases through the regular upload instead."
        }), 400

    lease_data = split_leases[0]
    new_version_number = (old_lease.get("version_number") or 1) + 1
    new_lease_id = database.insert_lease(
        filename,
        lease_data["fields"],
        document_type="lease",
        date_candidates=lease_data["date_candidates"],
        display_name=lease_data["display_name"] or old_lease.get("display_name"),
        source_page_start=lease_data["source_page_start"],
        source_page_end=lease_data["source_page_end"],
        status="active",
        supersedes_lease_id=lease_id,
        version_number=new_version_number,
    )

    if lease_data.get("ai_run_id"):
        database.link_ai_extraction_run_to_lease(lease_data["ai_run_id"], new_lease_id)

    database.repoint_lease_references(lease_id, new_lease_id)
    database.supersede_lease(lease_id)

    new_lease = database.get_effective_lease(new_lease_id)
    flags = _lease_risks(new_lease)
    touched_discrepancy_ids = [f["discrepancy_id"] for f in flags if f.get("discrepancy_id")]

    stale = database.get_stale_open_discrepancies_for_lease(
        new_lease_id, ["lease_risk_flag", "cross_lease_mismatch"], touched_discrepancy_ids
    )
    user = current_user()
    for discrepancy in stale:
        database.resolve_discrepancy(
            discrepancy["id"],
            correct_source="resubmission",
            note=f"Automatically resolved -- no longer detected after {user['name']} resubmitted a corrected "
                 f"version (v{new_version_number}) of this lease.",
            resolved_by="System",
            resolved_by_email=None,
        )

    _invalidate_lease_derived_caches()
    _invalidate_discrepancy_derived_caches()

    display_name = lease_data["display_name"] or old_lease.get("display_name") or old_lease["filename"]
    database.insert_activity(
        "lease_resubmitted",
        f"{user['name']} resubmitted a corrected version of {display_name} "
        f"(v{new_version_number} replaces v{old_lease.get('version_number') or 1})",
        lease_id=new_lease_id,
    )

    new_lease["tags"] = database.get_lease_tags(new_lease_id)
    return jsonify({
        "lease": _lease_summary(new_lease),
        "previous_lease_id": lease_id,
        "version_number": new_version_number,
        "discrepancies_auto_resolved": len(stale),
        "discrepancies_still_open": sum(1 for f in flags if f.get("resolution_status") == "open"),
        "discrepancies_detected": len(flags),
    }), 201


def _current_version_of(lease_id):
    """Given any lease id in a version chain, the one currently active version -- or None if the whole chain has somehow lost its active member (shouldn't happen; every resubmission always activates exactly one replacement before superseding the one it replaces)."""
    chain = database.get_lease_version_chain(lease_id)
    return next((v for v in chain if v.get("status") != "superseded"), None)


@app.route('/leases/<int:lease_id>/versions', methods=['GET'])
@require_role()
def lease_versions(lease_id):
    """
    The full resubmission history for this lease, oldest first, plus
    which one is current -- works from ANY version's id in the chain
    (the current one, or any superseded ancestor), so a link to an old
    archived version can always find its way to what replaced it, and
    vice versa. 404 only if the id doesn't exist at all.
    """
    if not database.get_lease(lease_id):
        return jsonify({"error": "Lease not found"}), 404
    chain = database.get_lease_version_chain(lease_id)
    versions = []
    for v in chain:
        versions.append({
            "id": v["id"],
            "version_number": v.get("version_number") or 1,
            "status": v.get("status") or "active",
            "is_current": v.get("status") != "superseded",
            "filename": v["filename"],
            "display_name": v.get("display_name") or v["filename"],
            "uploaded_at": v["uploaded_at"],
            "supersedes_lease_id": v.get("supersedes_lease_id"),
        })
    return jsonify({"lease_id": lease_id, "versions": versions}), 200


@app.route('/leases/batch', methods=['POST'])
@require_role('analyst')
def upload_leases_batch():
    """
    Upload multiple lease documents (any supported format -- see
    document_extractor.py) in one request. Each file is processed
    independently — if one fails (corrupted, unsupported format,
    extraction error), the rest still process. Any file that turns out
    to bundle more than one lease is split into its own leases, same as
    POST /leases — so one entry in `results` can carry several created
    leases in its `leases` list. Returns a per-file result list so the
    caller can see exactly what succeeded and what didn't.
    """
    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "No files uploaded (expected form field 'files')"}), 400

    results = []
    for file_storage in files:
        filename = file_storage.filename
        if not filename or not allowed_file(filename):
            supported = "PDF, Excel (.xlsx/.xls/.xlsm), CSV/TSV, Word (.docx/.doc), images (.jpg/.png/.tiff), or plain text (.txt)"
            results.append({"filename": filename or "(unnamed)", "success": False,
                             "error": f"Unsupported file type. Please upload one of: {supported}."})
            continue

        split_leases, error = _extract_leases_from_file_storage(file_storage, defer_ai=True)
        if error:
            message, _status = error
            results.append({"filename": filename, "success": False, "error": message})
            continue

        created = _persist_split_leases(filename, split_leases)
        processing = _start_deferred_extraction(filename, split_leases)
        results.append({"filename": filename, "success": True, "leases": created,
                        "split_count": len(created), "processing": processing})

    succeeded_files = sum(1 for r in results if r["success"])
    total_leases_created = sum(r["split_count"] for r in results if r["success"])
    # One summary entry for the whole batch rather than one per file (or
    # per split lease) — a 20-file batch shouldn't push everything else
    # out of a 10-item activity feed.
    if total_leases_created == 1:
        only = next(r for r in results if r["success"])
        database.insert_activity("lease_uploaded", f"Uploaded {only['filename']}", lease_id=only["leases"][0]["id"])
    elif total_leases_created > 1:
        database.insert_activity(
            "batch_upload",
            f"Uploaded a batch of {total_leases_created} leases from {succeeded_files} file(s)",
        )

    any_processing = any(r.get("processing") for r in results if r["success"])
    return jsonify({
        "total": len(results),
        "succeeded": succeeded_files,
        "failed": len(results) - succeeded_files,
        "total_leases_created": total_leases_created,
        "processing": any_processing,
        "results": results,
    }), (202 if any_processing else 200)


@app.route('/leases/import-rent-roll', methods=['POST'])
@require_role('analyst')
def import_rent_roll():
    """
    Upload a broker-built Excel (.xlsx) or CSV rent roll and import
    every real tenant row as its own lease record. See
    rent_roll_import.py for the parsing itself -- the key point is that
    it produces the exact same extracted_fields shape the PDF extractor
    does, so every existing portfolio computation (metrics, risk
    analysis, tenant concentration, WALT, rollover schedule, loss-to-
    lease) works on these rows with zero special-casing here or
    anywhere else.

    Expects multipart form data: 'file' (.csv or .xlsx), and an
    optional 'property_address' field -- the building this rent roll is
    for. Most rent rolls state the building once (a title/header area),
    not per row, so this is supplied by the uploader rather than parsed
    out of the file; combined with a per-row Unit/Suite column (if the
    file has one) to produce each row's full property_address. Omitting
    it is allowed (property_address is then only set when the file
    itself has a per-row unit/suite column, and left "not found"
    otherwise) but not recommended -- loss-to-lease's building-level
    comp grouping needs a real address to be useful.

    A file-level problem (wrong extension, empty file, no recognizable
    tenant/rent columns) is a 400 -- nothing is imported. A single bad
    DATA ROW (blank tenant, a vacant/total row, an unparseable cell) is
    never fatal to the rest of the file -- see `skipped_rows` in the
    response for what got skipped and why.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file_storage = request.files['file']
    if file_storage.filename == '':
        return jsonify({"error": "No file selected"}), 400

    filename = file_storage.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if extension not in ('csv', 'xlsx'):
        return jsonify({"error": "Invalid file type. Only .csv and .xlsx rent rolls are supported."}), 400

    base_property_address = (request.form.get('property_address') or '').strip() or None
    file_bytes = file_storage.read()

    try:
        if extension == 'csv':
            parsed = parse_csv_rent_roll(file_bytes, filename, base_property_address)
        else:
            parsed = parse_xlsx_rent_roll(file_bytes, filename, base_property_address)
    except RentRollImportError as e:
        return jsonify({"error": str(e)}), 400

    created = []
    for lease_data in parsed["leases"]:
        lease_id = database.insert_lease(
            filename,
            lease_data["extracted_fields"],
            document_type="lease",
            display_name=lease_data["display_name"],
        )
        lease = database.get_effective_lease(lease_id)
        lease["tags"] = []
        created.append(_lease_summary(lease))

    if created:
        _invalidate_lease_derived_caches()
        # Auto-reconcile the newly imported rows against whatever lease
        # PDFs are already on file, right away -- see
        # _run_reconciliation_sweep's own docstring. Fail-open, same
        # convention as every other best-effort side effect in this
        # app (email, alert generation): a reconciliation hiccup must
        # never turn a successful import into a failed response: the
        # leases are already committed by this point.
        try:
            _run_reconciliation_sweep()
        except Exception:
            logger.exception(
                "Auto-reconciliation after rent roll import failed (import itself still succeeded)."
            )

    skipped_note = f" ({len(parsed['skipped_rows'])} row(s) skipped)" if parsed["skipped_rows"] else ""
    database.insert_activity("rent_roll_imported", f"Imported {len(created)} lease(s) from {filename}{skipped_note}")

    return jsonify({
        "leases": created,
        "imported_count": len(created),
        "skipped_rows": parsed["skipped_rows"],
        "column_mapping": parsed["column_mapping"],
    }), 201


@app.route('/leases', methods=['GET'])
@require_role()
def list_leases():
    """
    List all base leases (not amendments), with amendment-merged
    effective field values. Optional ?tag=X filters to leases carrying
    that exact tag.
    """
    leases = database.get_all_effective_leases()

    tag_filter = request.args.get('tag')
    if tag_filter:
        allowed_ids = set(database.get_lease_ids_with_tag(tag_filter))
        leases = [l for l in leases if l["id"] in allowed_ids]

    tags_by_lease = database.get_tags_for_leases([l["id"] for l in leases])
    for lease in leases:
        lease["tags"] = tags_by_lease.get(lease["id"], [])

    return jsonify([_lease_summary(l) for l in leases]), 200


@app.route('/leases/<int:lease_id>', methods=['GET'])
@require_role()
def get_lease_detail(lease_id):
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    lease["tags"] = database.get_lease_tags(lease_id)
    return jsonify(_lease_summary(lease)), 200


@app.route('/leases/<int:lease_id>/fields/<field_name>/source', methods=['GET'])
@require_role()
def lease_field_source(lease_id, field_name):
    """
    The full audit trail for one extracted data point: the exact source
    (page + quote for a PDF-derived field, row + file + quote for a
    rent-roll-imported one) behind the value currently in effect for
    this lease, plus every other value this same field has held across
    the base lease and any amendments -- not just the winning one. See
    database.get_field_source_chain for the full shape.
    """
    if field_name not in FIELD_NAMES:
        return jsonify({
            "error": f"Unknown field '{field_name}'. Valid fields: {', '.join(FIELD_NAMES)}"
        }), 400
    chain = database.get_field_source_chain(lease_id, field_name)
    if chain is None:
        return jsonify({"error": "Lease not found"}), 404
    # Manual corrections are a separate provenance kind from a
    # document's own citation (see database.update_lease_field's
    # docstring) -- surfaced as their own key alongside `history`
    # rather than merged into it, so this stays additive and doesn't
    # change `history`'s existing shape for any caller already reading
    # it (see test_audit_trail.py). A manual edit may have landed on
    # any document in this field's history -- see edit_lease_field's
    # own resolve-to-the-governing-document logic -- not only the base
    # lease id given in the URL, so this collects across every
    # document `chain["history"]` already lists (base + amendments)
    # rather than just the one id the caller happened to ask about.
    manual_edits = []
    for entry in chain["history"]:
        manual_edits.extend(database.get_lease_field_edits(lease_id=entry["document_id"], field_name=field_name))
    manual_edits.sort(key=lambda e: (e["created_at"], e["id"]))
    chain["manual_edits"] = manual_edits
    return jsonify(chain), 200


@app.route('/leases/<int:lease_id>/fields/<field_name>', methods=['PATCH'])
@require_role('analyst')
def edit_lease_field(lease_id, field_name):
    """
    Body: {"value": str|null, "confidence": "high"|"medium"|"low" (optional,
    default "high" -- a human-entered value is presumed trustworthy
    unless the editor says otherwise), "note": str (optional), "task_id":
    int (optional -- links this edit to the task it happened under, see
    app/tasks.py's task_detail)}.

    Directly overwrites this field on this lease (see
    database.update_lease_field for what "this lease" means when the
    field's effective value currently comes from an amendment rather
    than the base document, and why source is always cleared to null
    rather than fabricated). Every edit is permanently logged --
    old value, new value, who, when -- via lease_field_edits, retrievable
    per-field through GET .../fields/<name>/source's `manual_edits`, or
    per-task through GET /tasks/<id>'s `field_edits`.

    `value` may be null/blank to explicitly record "I checked -- this
    genuinely isn't in the lease" (see update_lease_field's docstring
    on `manually_verified` for how that's distinguished from
    extraction simply never having found it).
    """
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    if field_name not in FIELD_NAMES:
        return jsonify({"error": f"Unknown field '{field_name}'. Valid fields: {', '.join(FIELD_NAMES)}"}), 400

    body = request.get_json(silent=True) or {}
    if "value" not in body:
        return jsonify({"error": "Missing required field: value (use null to clear it)"}), 400
    value = body.get("value")
    if isinstance(value, str):
        value = value.strip() or None
    confidence = body.get("confidence") or "high"
    if confidence not in ("high", "medium", "low"):
        return jsonify({"error": "confidence must be one of: high, medium, low"}), 400
    note = (body.get("note") or "").strip() or None
    task_id = body.get("task_id")
    if task_id is not None and not database.get_task(task_id):
        return jsonify({"error": "task_id does not match a real task"}), 400

    # Resolve to whichever document actually GOVERNS this field's
    # effective value right now -- the base lease, or whichever
    # amendment most recently overrode it (get_effective_fields'
    # "latest non-null amendment wins" rule). Editing the base id
    # blindly, when an amendment already overrides this exact field,
    # would silently have NO effect anywhere the effective value is
    # read (lease detail, rent roll, exports, dashboards, discrepancy
    # re-sync) -- the base row would change, but every reader would
    # keep showing the unchanged amendment value instead. This was
    # long documented as the intended behavior (see update_lease_
    # field's own docstring) but never actually implemented until now
    # -- found live, via the exact rent-roll-download verification
    # this feature was built to support.
    chain = database.get_field_source_chain(lease_id, field_name)
    target_lease_id = (chain or {}).get("effective_document_id") or lease_id

    user = current_user()
    new_entry = database.update_lease_field(
        target_lease_id, field_name, value, edited_by=user["name"], edited_by_email=user["email"],
        confidence=confidence, note=note, task_id=task_id,
    )
    _invalidate_lease_derived_caches()
    database.insert_activity(
        "lease_field_edited",
        f"{user['name']} corrected {field_name.replace('_', ' ')} on {lease.get('display_name') or lease['filename']}",
        lease_id=lease_id,
    )
    return jsonify({
        "lease_id": lease_id,
        "field_name": field_name,
        "field": new_entry,
        "edited_document_id": target_lease_id,
    }), 200


@app.route('/leases/<int:lease_id>/fields/<field_name>/verify', methods=['POST'])
@require_role('analyst')
def verify_lease_field(lease_id, field_name):
    """
    Body: {} (or {"note": str, "task_id": int}, both optional). "A human
    looked at this exact value and confirms it's right" -- for a medium
    (or low) confidence field where the extracted value itself needs no
    correction, this is a one-click confirm instead of retyping the same
    value through PATCH .../fields/<name> just to force confidence back
    to "high" (which would also needlessly null the source citation --
    see database.mark_field_verified's docstring for why this is a
    separate function, not a thin wrapper around update_lease_field).

    Same effective-document resolution as PATCH .../fields/<name> above:
    an amendment already overriding this field must be the one that
    gets verified, not the base lease, or the confirmation would be
    silently invisible everywhere the effective value is read.
    """
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    if field_name not in FIELD_NAMES:
        return jsonify({"error": f"Unknown field '{field_name}'. Valid fields: {', '.join(FIELD_NAMES)}"}), 400

    body = request.get_json(silent=True) or {}
    note = (body.get("note") or "").strip() or None
    task_id = body.get("task_id")
    if task_id is not None and not database.get_task(task_id):
        return jsonify({"error": "task_id does not match a real task"}), 400

    chain = database.get_field_source_chain(lease_id, field_name)
    target_lease_id = (chain or {}).get("effective_document_id") or lease_id

    user = current_user()
    new_entry = database.mark_field_verified(
        target_lease_id, field_name, edited_by=user["name"], edited_by_email=user["email"],
        note=note, task_id=task_id,
    )
    if new_entry is None:
        return jsonify({"error": "This field has no value yet -- nothing to verify."}), 400

    _invalidate_lease_derived_caches()
    database.insert_activity(
        "lease_field_verified",
        f"{user['name']} verified {field_name.replace('_', ' ')} on {lease.get('display_name') or lease['filename']}",
        lease_id=lease_id,
    )
    return jsonify({
        "lease_id": lease_id,
        "field_name": field_name,
        "field": new_entry,
        "edited_document_id": target_lease_id,
    }), 200


@app.route('/leases/<int:lease_id>', methods=['DELETE'])
@require_role('analyst')
def delete_lease(lease_id):
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    database.delete_lease(lease_id)
    _invalidate_lease_derived_caches()
    # Logged with lease_id=None (not lease_id) since the row this would
    # reference no longer exists once delete_lease() returns.
    database.insert_activity("lease_deleted", f"Deleted {lease['filename']}")
    return jsonify({"deleted": lease_id}), 200


@app.route('/leases/bulk-delete', methods=['POST'])
@require_role('analyst')
def bulk_delete_leases():
    """
    Body: {"ids": [1, 2, 3]}.

    Each id is deleted independently and the request never fails as a
    whole -- one already-deleted or bad id (a double-click, a stale
    selection from a second browser tab) shouldn't block deleting the
    rest of a real selection, same "loop + collect results, no
    all-or-nothing" philosophy as POST /leases/batch's upload side.
    Confirmation is the frontend's job (this route trusts its caller
    the same way single-lease DELETE does); this endpoint just needs to
    report exactly what happened to each id.
    """
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "Provide a non-empty 'ids' list of integers"}), 400

    leases_by_id = database.get_leases_by_ids(ids)
    deleted = []
    not_found = []
    for lease_id in ids:
        lease = leases_by_id.get(lease_id)
        if not lease:
            not_found.append(lease_id)
            continue
        database.delete_lease(lease_id)
        database.insert_activity("lease_deleted", f"Deleted {lease['filename']}")
        deleted.append(lease_id)

    if deleted:
        _invalidate_lease_derived_caches()
    return jsonify({"deleted": deleted, "not_found": not_found}), 200


@app.route('/leases/<int:lease_id>/amendments', methods=['POST'])
@require_role('analyst')
def upload_amendment(lease_id):
    """Upload an amendment/addendum document (any supported format -- see document_extractor.py) and link it to an existing base lease."""
    base_lease = database.get_lease(lease_id)
    if not base_lease:
        return jsonify({"error": "Base lease not found"}), 404
    if base_lease["document_type"] != "lease":
        return jsonify({"error": "Amendments can only be linked to a base lease, not another amendment"}), 400

    file, error = _validate_upload()
    if error:
        return error

    filename = file.filename
    split_leases, error = _extract_leases_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    # An amendment attaches to exactly one base lease, so even if
    # extract_multiple_leases() found more than one lease-shaped
    # section in this file (unexpected for an amendment/addendum, which
    # is normally a short single document), only the first is used —
    # the rest are silently ignored rather than creating orphan
    # amendment records with no clear base lease of their own.
    amendment_data = split_leases[0]
    amendment_id = database.insert_lease(
        filename, amendment_data["fields"], document_type="amendment", base_lease_id=lease_id,
        date_candidates=amendment_data["date_candidates"],
    )
    if amendment_data.get("ai_run_id"):
        database.link_ai_extraction_run_to_lease(amendment_data["ai_run_id"], amendment_id)
    database.insert_activity("amendment_uploaded", f"Added amendment {filename} to {base_lease['filename']}", lease_id=lease_id)
    _invalidate_lease_derived_caches()
    lease = database.get_effective_lease(lease_id)
    lease["tags"] = database.get_lease_tags(lease_id)
    return jsonify(_lease_summary(lease)), 201


@app.route('/leases/<int:lease_id>/amendments', methods=['GET'])
@require_role()
def list_amendments(lease_id):
    base_lease = database.get_lease(lease_id)
    if not base_lease:
        return jsonify({"error": "Lease not found"}), 404
    amendments = database.get_amendments(lease_id)
    return jsonify([{
        "id": a["id"], "filename": a["filename"], "uploaded_at": a["uploaded_at"],
        "extracted_fields": a["extracted_fields"],
    } for a in amendments]), 200


@app.route('/leases/<int:lease_id>', methods=['PATCH'])
@require_role('analyst')
def rename_lease(lease_id):
    """Body: {"display_name": str}. The only field this endpoint can change — renaming, not editing extracted fields (that's the inline-edit workflow on the detail page, unrelated to this)."""
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    body = request.get_json(silent=True) or {}
    display_name = (body.get("display_name") or "").strip()
    if not display_name:
        return jsonify({"error": "display_name is required and cannot be blank"}), 400
    if len(display_name) > 200:
        return jsonify({"error": "display_name must be 200 characters or fewer"}), 400

    database.update_lease_display_name(lease_id, display_name)
    updated = database.get_effective_lease(lease_id)
    updated["tags"] = database.get_lease_tags(lease_id)
    return jsonify(_lease_summary(updated)), 200


@app.route('/leases/<int:lease_id>/tags', methods=['GET'])
@require_role()
def list_lease_tags(lease_id):
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    return jsonify(database.get_lease_tags(lease_id)), 200


@app.route('/leases/<int:lease_id>/tags', methods=['POST'])
@require_role('analyst')
def add_lease_tag_route(lease_id):
    """Body: {"tag": str}."""
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    body = request.get_json(silent=True) or {}
    tag = (body.get("tag") or "").strip()
    if not tag:
        return jsonify({"error": "tag is required and cannot be blank"}), 400
    if len(tag) > 60:
        return jsonify({"error": "tag must be 60 characters or fewer"}), 400

    database.add_lease_tag(lease_id, tag)
    return jsonify(database.get_lease_tags(lease_id)), 200


@app.route('/leases/<int:lease_id>/tags/<path:tag>', methods=['DELETE'])
@require_role('analyst')
def remove_lease_tag_route(lease_id, tag):
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    database.remove_lease_tag(lease_id, tag)
    return jsonify(database.get_lease_tags(lease_id)), 200


def _validate_comment_payload(payload):
    """
    Shared by both comment-creation routes. Returns (body, error_response).
    author_name/author_email used to be request-body fields (trusted
    as-is, no accounts table) -- now that real per-user login exists,
    both routes are behind @require_role('analyst'), so the author is
    always the logged-in session user (see current_user()), never
    something the caller can just type in. Only `body` is still a
    request-body field to validate.
    """
    body = (payload.get('body') or '').strip()
    if not body:
        return None, (jsonify({"error": "Missing required field: body"}), 400)
    return body, None


@app.route('/leases/<int:lease_id>/comments', methods=['GET'])
@require_role()
def list_lease_comments(lease_id):
    """Team notes on this lease, oldest first, visible to everyone -- this app has no per-account data scoping at all yet, so "the whole team" is just everyone who can reach this API."""
    if not database.get_lease(lease_id):
        return jsonify({"error": "Lease not found"}), 404
    return jsonify(database.get_lease_comments(lease_id)), 200


@app.route('/leases/<int:lease_id>/comments', methods=['POST'])
@require_role('analyst')
def add_lease_comment(lease_id):
    """Body: {"body": "..."}. The comment's author is always the logged-in session user -- see _validate_comment_payload."""
    if not database.get_lease(lease_id):
        return jsonify({"error": "Lease not found"}), 404

    payload = request.get_json(silent=True) or {}
    body, error = _validate_comment_payload(payload)
    if error:
        return error

    user = current_user()
    database.add_comment(user["name"], body, lease_id=lease_id, author_email=user["email"])
    return jsonify(database.get_lease_comments(lease_id)), 201


@app.route('/tags', methods=['GET'])
@require_role()
def list_all_tags():
    """Every distinct tag currently in use across the whole portfolio — for filter dropdowns and tag-input autocomplete."""
    return jsonify(database.get_all_tags()), 200


@app.route('/leases/bulk-tag', methods=['POST'])
@require_role('analyst')
def bulk_tag_leases():
    """Body: {"ids": [1, 2, 3], "tag": "Downtown Portfolio"}. Applies one tag to every id independently -- same loop-and-report shape as bulk-delete, and reuses the single-lease tag validation/dedup already in database.add_lease_tag."""
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    tag = (body.get("tag") or "").strip()

    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "Provide a non-empty 'ids' list of integers"}), 400
    if not tag:
        return jsonify({"error": "tag is required and cannot be blank"}), 400
    if len(tag) > 60:
        return jsonify({"error": "tag must be 60 characters or fewer"}), 400

    leases_by_id = database.get_leases_by_ids(ids)
    tagged = []
    not_found = []
    for lease_id in ids:
        if lease_id not in leases_by_id:
            not_found.append(lease_id)
            continue
        database.add_lease_tag(lease_id, tag)
        tagged.append(lease_id)

    return jsonify({"tagged": tagged, "not_found": not_found}), 200


# ----------------------------------------------------------------------
# Team authentication
#
# Real per-user accounts (the `users` table -- see app/database.py and
# app/auth.py), each with a role (admin/analyst/viewer). Real
# password, real bcrypt check, backed by a signed session cookie (see
# the SESSION_COOKIE_* config and CORS setup near the top of this
# file). One login for every role, used by both the main app and the
# admin mini-SPA -- the old single-hardcoded-admin login
# (ADMIN_EMAIL/ADMIN_PASSWORD_HASH) has been retired; those env vars
# now only seed the first admin user once, into this same table (see
# database._seed_first_admin_user). Deliberately separate from the
# client-facing waitlist gate below (/waitlist/check) -- see
# app/auth.py's module docstring.
# ----------------------------------------------------------------------

# Online password-guessing / credential-stuffing defense for /auth/login.
# Two windows, both required: a wider per-IP cap stops one host hammering
# many accounts; a tighter per-email cap stops a distributed attempt
# against one specific account. Successful logins don't reset the
# counter (a real user logs in once and is done; an attacker who found
# the password shouldn't get a fresh budget), but the window is short
# enough that a locked-out real user just waits a few minutes. Same
# per-worker, in-memory caveat as every other limiter in this app.
_login_rate_limiter = RateLimiter(max_hits=20, window_seconds=300)          # per IP: 20 / 5 min
_login_email_rate_limiter = RateLimiter(max_hits=7, window_seconds=900)     # per email: 7 / 15 min


def _reset_login_rate_limit_for_tests():
    _login_rate_limiter.reset()
    _login_email_rate_limiter.reset()


@app.route('/auth/login', methods=['POST'])
def auth_login():
    """
    Body: {"email": str, "password": str}. On success, starts a
    session (signed cookie, 12-hour lifetime) and returns
    {"id", "email", "name", "role"}. On failure, always the same
    generic error regardless of whether the email, password, or
    account status was wrong -- see auth.verify_password for why the
    check itself is also timing-safe about that, not just the message.

    Rate-limited per IP and per submitted email (429 on either) to blunt
    online brute-force and credential stuffing.
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""

    ip = request.remote_addr or "unknown"
    limited = _login_rate_limiter.check([f"ip:{ip}"])
    if email:
        # Count the email key even for a nonexistent account -- otherwise
        # a 429-vs-401 difference would leak which emails are registered.
        limited = _login_email_rate_limiter.check([f"email:{email.lower()}"]) or limited
    if limited:
        return jsonify({"error": "Too many sign-in attempts. Please wait a few minutes and try again."}), 429

    user = verify_password(email, password)
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    session.permanent = True
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    session["name"] = user["name"]
    session["role"] = user["role"]
    session["is_owner"] = bool(user.get("is_owner"))
    database.update_user_last_login(user["id"])
    return jsonify({
        "id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"],
        "is_owner": bool(user.get("is_owner")),
    }), 200


@app.route('/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({"status": "logged_out"}), 200


@app.route('/auth/session', methods=['GET'])
def auth_session():
    """Used on every app boot to check current auth state without triggering a 401 (this route itself is intentionally public -- it only ever reflects the caller's own session back to them)."""
    user = current_user()
    if user:
        return jsonify({"authenticated": True, **user}), 200
    return jsonify({"authenticated": False, "id": None, "email": None, "name": None, "role": None, "is_owner": False}), 200


@app.route('/auth/change-password', methods=['POST'])
@require_role()
def auth_change_password():
    """Body: {"current_password": str, "new_password": str}. Any logged-in role may change their own password."""
    body = request.get_json(silent=True) or {}
    current_password = body.get("current_password") or ""
    new_password = body.get("new_password") or ""
    if not new_password or len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    user = current_user()
    full_user = database.get_user(user["id"])
    if not verify_password(full_user["email"], current_password):
        return jsonify({"error": "Current password is incorrect"}), 401

    database.update_user_password(user["id"], hash_password(new_password))
    return jsonify({"status": "password_updated"}), 200


# ---- "Forgot password?" — self-service reset over email --------------
#
# Two routes, both public (a locked-out person has no session):
#   POST /auth/forgot-password  {"email"}          -> always the same
#       generic 200, whether or not the address has an account, so this
#       endpoint can't be used to probe which emails are registered.
#   POST /auth/reset-password   {"token","new_password"} -> consumes a
#       single-use, 1-hour token (see database.consume_password_reset_token)
#       and sets the new password.
#
# The token is `secrets.token_urlsafe(32)`; only its SHA-256 hash is
# stored (database.create_password_reset_token), the raw value lives
# only in the emailed link. The reset link's origin is taken from the
# request's own Origin header, but only if it's in ALLOWED_ORIGINS --
# otherwise it falls back to the first configured origin, so a spoofed
# Origin can never point the link at an attacker's domain.
#
# NOTE: on a deployment with no EMAIL_USER/EMAIL_APP_PASSWORD set, the
# send is a silent no-op (email_service._send's existing fail-safe) and
# the person will never receive a link -- the route still returns the
# same generic 200. And on a deployment with no persistent database
# (Render free tier), the users table and these tokens are both wiped
# on every restart -- a reset link often won't outlive the dyno that
# issued it. See DEPLOYMENT.md / DECISIONS.md.

_PASSWORD_RESET_TOKEN_TTL_SECONDS = 3600

_FORGOT_PASSWORD_RATE_LIMIT_MAX = 3
_FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS = 3600

# Two independent counters, both required:
#   per IP    -- stops one host cycling through many addresses to find
#                which ones are registered (the generic response hides
#                existence, but volume alone is still abuse).
#   per email -- stops a distributed/rotating-IP attacker mailbombing
#                one person's inbox with reset links, which a per-IP
#                limit alone does nothing about.
# Keyed "ip:<addr>" / "email:<addr>" in one dict so both share this
# pruning and locking.
_forgot_password_rate_limit_state = {}  # key -> [monotonic timestamps in window]
_forgot_password_rate_limit_lock = threading.Lock()


def _forgot_password_rate_limited(keys) -> bool:
    """
    True if ANY of `keys` has already hit the cap in the current window.
    Every key is recorded on every call regardless -- see the caller for
    why the email key must be counted even when no such account exists
    (counting only real accounts would turn a 429 into an existence
    oracle, defeating the generic response).

    In-process and per-worker, like email_service's own send-side limit:
    it resets on restart and doesn't coordinate across gunicorn workers.
    That's a real ceiling on how strong this can be, accepted here for
    the same reason it was there -- a shared store (Redis) is
    infrastructure this project doesn't have, and a leaky per-worker
    limit still removes the trivial single-host flood this is aimed at.
    """
    now = time.monotonic()
    cutoff = now - _FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS
    with _forgot_password_rate_limit_lock:
        # Prune every expired key, not just the ones being touched --
        # without this the dict grows once per distinct IP/email seen
        # and never shrinks, which on a public unauthenticated endpoint
        # is a memory leak an attacker controls the size of.
        for key in [k for k, ts in _forgot_password_rate_limit_state.items() if not ts or ts[-1] <= cutoff]:
            del _forgot_password_rate_limit_state[key]

        limited = False
        for key in keys:
            timestamps = [t for t in _forgot_password_rate_limit_state.get(key, []) if t > cutoff]
            if len(timestamps) >= _FORGOT_PASSWORD_RATE_LIMIT_MAX:
                limited = True
            timestamps.append(now)
            _forgot_password_rate_limit_state[key] = timestamps
        return limited


def _reset_forgot_password_rate_limit_for_tests():
    """Test-only: clears the in-memory rate limit state between runs sharing a process (mirrors email_service._reset_rate_limit_state_for_tests)."""
    with _forgot_password_rate_limit_lock:
        _forgot_password_rate_limit_state.clear()


def _reset_link_base() -> str:
    """The frontend origin to build the reset link against -- the request's own Origin if it's allow-listed, else the first configured origin."""
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    if origin and origin in ALLOWED_ORIGINS:
        return origin
    return ALLOWED_ORIGINS[0].rstrip("/") if ALLOWED_ORIGINS else ""


def _send_email_off_request_path(send_fn, *args):
    """
    Fire-and-forget email send on a daemon thread.

    Required for /auth/forgot-password specifically, and it is a
    SECURITY control, not a latency optimization. Sending inline made
    the response ~1.4s for a registered address (a real SMTP round
    trip, up to email_service.SMTP_TIMEOUT_SECONDS on a slow server)
    versus ~5ms for an unregistered one -- measured, a ~260x gap. That
    turns response time into a reliable account-existence oracle and
    completely defeats the identical response body this endpoint
    returns to hide exactly that. Off the request path, the response
    time no longer depends on whether an account was found.

    Safe to background: email_service's send functions take plain
    string arguments (no Flask request context needed), already swallow
    every exception internally, and guard their own shared state with a
    lock. Nothing here needs the result -- delivery is best-effort by
    design, same as every other send in this app.
    """
    threading.Thread(
        target=_send_email_best_effort, args=(send_fn, *args), daemon=True,
    ).start()


@app.route('/auth/forgot-password', methods=['POST'])
def auth_forgot_password():
    """
    Body: {"email": str, "surface": "app"|"admin" (optional, default
    "app")}. Always returns the same generic 200 -- never reveals
    whether the address has an account. For a real, active user,
    generates a single-use 1-hour reset token and emails the link
    (best-effort -- a mail failure still returns 200).

    `surface` only selects which frontend page the emailed link points
    to (frontend/app/reset-password.html vs frontend/admin/
    reset-password.html -- both post to this same /auth/reset-password
    either way, so which one someone lands on is a UX nicety, not a
    security boundary). Restricted to this fixed two-value set rather
    than accepting a caller-supplied path, so this can never become an
    open redirect.
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    surface = body.get("surface") if body.get("surface") in ("app", "admin") else "app"
    generic = jsonify({"message": "If an account exists for that email, a reset link is on its way."})

    # Rate-limited on BOTH the caller's IP and the submitted address,
    # and deliberately before the account lookup: the email counter has
    # to advance for every syntactically valid address whether or not it
    # belongs to a real user. Counting only real accounts would make a
    # 429-vs-200 difference reveal exactly what the generic response
    # exists to hide.
    rate_limit_keys = [f"ip:{request.remote_addr or 'unknown'}"]
    if email and _EMAIL_RE.match(email):
        rate_limit_keys.append(f"email:{email.lower()}")
    if _forgot_password_rate_limited(rate_limit_keys):
        return jsonify({"error": "Too many reset requests. Please try again later."}), 429

    if not email or not _EMAIL_RE.match(email):
        return generic, 200

    user = database.get_user_by_email(email)
    if user and user["status"] == "active":
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        database.create_password_reset_token(user["id"], token_hash)

        base = _reset_link_base()
        reset_url = f"{base}/{surface}/reset-password.html?token={raw_token}"
        # Off the request path on purpose -- an inline SMTP round trip
        # only happens for real accounts, which made response time a
        # loud account-existence oracle. See
        # _send_email_off_request_path.
        _send_email_off_request_path(email_service.send_password_reset_email, user["email"], reset_url)

    return generic, 200


# The reset token is a 256-bit secrets.token_urlsafe(32), so brute
# force is infeasible regardless -- this limiter is defense-in-depth
# against a bug that ever weakened the token, and against sheer request
# volume against this public endpoint.
_reset_password_rate_limiter = RateLimiter(max_hits=15, window_seconds=900)  # per IP: 15 / 15 min


def _reset_reset_password_rate_limit_for_tests():
    _reset_password_rate_limiter.reset()


@app.route('/auth/reset-password', methods=['POST'])
def auth_reset_password():
    """
    Body: {"token": str, "new_password": str}. Consumes the token (see
    database.consume_password_reset_token -- single-use, 1-hour) and
    sets the new password. Any logged-in role's password can be reset
    this way; the token itself is the proof of identity.
    """
    if _reset_password_rate_limiter.check([f"ip:{request.remote_addr or 'unknown'}"]):
        return jsonify({"error": "Too many attempts. Please wait a few minutes and try again."}), 429

    body = request.get_json(silent=True) or {}
    token = (body.get("token") or "").strip()
    new_password = body.get("new_password") or ""

    if not new_password or len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400
    if not token:
        return jsonify({"error": "This reset link is invalid or has expired. Request a new one."}), 400

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    user_id = database.consume_password_reset_token(token_hash, _PASSWORD_RESET_TOKEN_TTL_SECONDS)
    if user_id is None:
        return jsonify({"error": "This reset link is invalid or has expired. Request a new one."}), 400

    database.update_user_password(user_id, hash_password(new_password))
    return jsonify({"status": "password_updated"}), 200


# ----------------------------------------------------------------------
# Team management -- admin-only. Real accounts (the `users` table --
# see app/database.py and app/auth.py), each with a role
# (admin/analyst/viewer). Deliberately separate from the waitlist
# admin routes below: approving a waitlist signup marks someone an
# approved prospect, it does NOT create a login -- an admin does that
# explicitly here, with a real password they share out-of-band (see
# DECISIONS.md's team-collaboration entries for why these are two
# decoupled steps, not one).
# ----------------------------------------------------------------------

_VALID_ROLES = {"admin", "analyst", "viewer"}
_VALID_STATUSES = {"active", "deactivated"}


def _user_public(user):
    """Strips password_hash before this ever reaches a response -- every route below must go through this, never return a raw `users` row."""
    return {k: v for k, v in user.items() if k != "password_hash"}


@app.route('/team/members', methods=['GET'])
@require_role('admin')
def list_team_members():
    return jsonify([_user_public(u) for u in database.list_users()]), 200


@app.route('/team/members', methods=['POST'])
@require_role('admin')
def create_team_member():
    """Body: {"email", "name", "role", "password"}. The admin sets the initial password directly and shares it with the new member out-of-band (see module comment above) -- there's no invite-link/email flow yet."""
    body = request.get_json(silent=True) or {}
    email = (body.get('email') or '').strip()
    name = (body.get('name') or '').strip()
    role = (body.get('role') or '').strip()
    password = body.get('password') or ''

    missing = [f for f, v in (('email', email), ('name', name), ('role', role), ('password', password)) if not v]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
    if role not in _VALID_ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(sorted(_VALID_ROLES))}"}), 400
    if not _EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    result = database.create_user(email, name, hash_password(password), role, created_by_user_id=current_user()["id"])
    if result["status"] == "duplicate":
        return jsonify({"error": "A team member with that email already exists"}), 409

    user = database.get_user(result["id"])
    # actor_user_id isn't a real insert_activity() param yet -- that
    # lands with the activity-feed enrichment step of the
    # collaboration-platform plan; the actor's name is embedded in the
    # description for now, same convention every other insert_activity
    # call site in this file still uses today.
    database.insert_activity("team_member_added", f"{name} ({email}) added to the team as {role} by {current_user()['name']}")
    return jsonify(_user_public(user)), 201


@app.route('/team/members/<int:member_id>', methods=['PATCH'])
@require_role('admin')
def update_team_member(member_id):
    """Body: any of {"name", "role", "status"}. Only the fields present are changed."""
    user = database.get_user(member_id)
    if not user:
        return jsonify({"error": "Team member not found"}), 404

    body = request.get_json(silent=True) or {}
    if 'name' in body:
        name = (body.get('name') or '').strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        database.update_user_name(member_id, name)
    if 'role' in body:
        role = (body.get('role') or '').strip()
        if role not in _VALID_ROLES:
            return jsonify({"error": f"role must be one of: {', '.join(sorted(_VALID_ROLES))}"}), 400
        database.update_user_role(member_id, role)
    if 'status' in body:
        status = (body.get('status') or '').strip()
        if status not in _VALID_STATUSES:
            return jsonify({"error": f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}"}), 400
        database.update_user_status(member_id, status)

    return jsonify(_user_public(database.get_user(member_id))), 200


@app.route('/team/members/<int:member_id>/reset-password', methods=['POST'])
@require_role('admin')
def reset_team_member_password(member_id):
    """Body: {"password"}. Admin-initiated reset, same as create -- the new password is shared with the member out-of-band."""
    if not database.get_user(member_id):
        return jsonify({"error": "Team member not found"}), 404

    body = request.get_json(silent=True) or {}
    password = body.get('password') or ''
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    database.update_user_password(member_id, hash_password(password))
    return jsonify({"status": "password_reset"}), 200


# ----------------------------------------------------------------------
# Assignments: giving a lease, discrepancy, or property a specific
# owner. See app/assignments.py for target_key derivation.
# ----------------------------------------------------------------------

@app.route('/assignments', methods=['GET'])
@require_role()
def list_assignments_route():
    """GET /assignments?assigned_to=<user_id>&status=<status>&target_type=<type>. Any combination of filters may be applied together."""
    assigned_to = request.args.get('assigned_to', type=int)
    status = request.args.get('status')
    target_type = request.args.get('target_type')
    if status and status not in assignments_module.VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {', '.join(sorted(assignments_module.VALID_STATUSES))}"}), 400
    if target_type and target_type not in assignments_module.VALID_TARGET_TYPES:
        return jsonify({"error": f"target_type must be one of: {', '.join(sorted(assignments_module.VALID_TARGET_TYPES))}"}), 400

    rows = database.list_assignments(assigned_to_user_id=assigned_to, status=status, target_type=target_type)
    return jsonify([assignments_module.assignment_detail(a) for a in rows]), 200


@app.route('/assignments', methods=['POST'])
@require_role('analyst')
def create_assignment_route():
    """Body: {"target_type": "lease"|"discrepancy"|"property", "target": <id or address>, "assigned_to_user_id": int, "note": str (optional)}."""
    body = request.get_json(silent=True) or {}
    target_type = (body.get('target_type') or '').strip()
    target = body.get('target')
    assigned_to_user_id = body.get('assigned_to_user_id')
    note = (body.get('note') or '').strip() or None

    if target_type not in assignments_module.VALID_TARGET_TYPES:
        return jsonify({"error": f"target_type must be one of: {', '.join(sorted(assignments_module.VALID_TARGET_TYPES))}"}), 400
    if not target:
        return jsonify({"error": "Missing required field: target"}), 400
    if not assigned_to_user_id:
        return jsonify({"error": "Missing required field: assigned_to_user_id"}), 400

    try:
        target_key = assignments_module.derive_target_key(target_type, target)
    except (ValueError, TypeError):
        return jsonify({"error": f"Invalid target for target_type={target_type!r}: {target!r}"}), 400

    assignee = database.get_user(assigned_to_user_id)
    if not assignee:
        return jsonify({"error": "assigned_to_user_id does not match a real team member"}), 400

    lease_id = discrepancy_id = property_address = None
    if target_type == 'lease':
        if not database.get_lease(int(target_key)):
            return jsonify({"error": "Lease not found"}), 404
        lease_id = int(target_key)
    elif target_type == 'discrepancy':
        if not database.get_discrepancy(int(target_key)):
            return jsonify({"error": "Discrepancy not found"}), 404
        discrepancy_id = int(target_key)
    else:
        # A property is just a string -- no existence check is
        # possible or required (assigning an upcoming acquisition
        # that hasn't been uploaded yet is legitimate).
        property_address = target_key

    assignment_id = database.upsert_assignment(
        target_type, target_key, assigned_to_user_id, current_user()["id"],
        lease_id=lease_id, discrepancy_id=discrepancy_id, property_address=property_address, note=note,
    )
    database.insert_activity(
        "assignment_created",
        f"{assignee['name']} assigned to {target_type} {target_key} by {current_user()['name']}",
        lease_id=lease_id,
    )
    return jsonify(assignments_module.assignment_detail(database.get_assignment(assignment_id))), 201


@app.route('/assignments/<int:assignment_id>', methods=['GET'])
@require_role()
def get_assignment_route(assignment_id):
    assignment = database.get_assignment(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found"}), 404
    return jsonify(assignments_module.assignment_detail(assignment)), 200


@app.route('/assignments/<int:assignment_id>', methods=['PATCH'])
@require_role('analyst')
def update_assignment_route(assignment_id):
    """Body: {"status": "assigned"|"in_review"|"resolved"}."""
    if not database.get_assignment(assignment_id):
        return jsonify({"error": "Assignment not found"}), 404

    body = request.get_json(silent=True) or {}
    status = (body.get('status') or '').strip()
    if status not in assignments_module.VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {', '.join(sorted(assignments_module.VALID_STATUSES))}"}), 400

    updated = database.update_assignment_status(assignment_id, status, current_user()["id"])
    return jsonify(assignments_module.assignment_detail(updated)), 200


@app.route('/assignments/<int:assignment_id>', methods=['DELETE'])
@require_role('analyst')
def delete_assignment_route(assignment_id):
    if not database.delete_assignment(assignment_id):
        return jsonify({"error": "Assignment not found"}), 404
    return jsonify({"status": "deleted"}), 200


@app.route('/tasks', methods=['GET'])
@require_role()
def list_tasks_route():
    """GET /tasks?assigned_to=<user_id>&status=<status>&due_before=<YYYY-MM-DD>&due_after=<YYYY-MM-DD>&lease_id=<id>&discrepancy_id=<id>. Any combination of filters may be applied together."""
    assigned_to = request.args.get('assigned_to', type=int)
    status = request.args.get('status')
    due_before = request.args.get('due_before')
    due_after = request.args.get('due_after')
    lease_id = request.args.get('lease_id', type=int)
    discrepancy_id = request.args.get('discrepancy_id', type=int)
    if status and status not in tasks_module.VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {', '.join(sorted(tasks_module.VALID_STATUSES))}"}), 400

    rows = database.list_tasks(
        assigned_to_user_id=assigned_to, status=status, due_before=due_before,
        due_after=due_after, lease_id=lease_id, discrepancy_id=discrepancy_id,
    )
    return jsonify([tasks_module.task_detail(t) for t in rows]), 200


@app.route('/tasks', methods=['POST'])
@require_role('analyst')
def create_task_route():
    """Body: {"title": str, "description": str (optional), "due_date": "YYYY-MM-DD" (optional), "assigned_to_user_id": int (optional), "lease_id": int (optional), "discrepancy_id": int (optional), "property_address": str (optional), "priority": "normal"|"high" (optional, default "normal")}."""
    body = request.get_json(silent=True) or {}
    title = (body.get('title') or '').strip()
    if not title:
        return jsonify({"error": "Missing required field: title"}), 400

    assigned_to_user_id = body.get('assigned_to_user_id')
    if assigned_to_user_id is not None and not database.get_user(assigned_to_user_id):
        return jsonify({"error": "assigned_to_user_id does not match a real team member"}), 400

    lease_id = body.get('lease_id')
    if lease_id is not None and not database.get_lease(lease_id):
        return jsonify({"error": "Lease not found"}), 404

    discrepancy_id = body.get('discrepancy_id')
    if discrepancy_id is not None and not database.get_discrepancy(discrepancy_id):
        return jsonify({"error": "Discrepancy not found"}), 404

    priority = body.get('priority') or 'normal'
    if priority not in tasks_module.VALID_PRIORITIES:
        return jsonify({"error": f"priority must be one of: {', '.join(sorted(tasks_module.VALID_PRIORITIES))}"}), 400

    task_id = database.create_task(
        title=title,
        created_by_user_id=current_user()["id"],
        description=body.get('description'),
        due_date=body.get('due_date'),
        assigned_to_user_id=assigned_to_user_id,
        lease_id=lease_id,
        discrepancy_id=discrepancy_id,
        property_address=(body.get('property_address') or '').strip() or None,
        priority=priority,
    )
    database.insert_activity("task_created", f"Task created: {title}", lease_id=lease_id)
    return jsonify(tasks_module.task_detail(database.get_task(task_id))), 201


@app.route('/tasks/from-discrepancy/<int:discrepancy_id>', methods=['POST'])
@require_role('analyst')
def create_task_from_discrepancy_route(discrepancy_id):
    """Body: {"assigned_to_user_id": int (optional), "due_date": "YYYY-MM-DD" (optional)}. Carries the discrepancy's category/severity/message into the new task automatically."""
    body = request.get_json(silent=True) or {}
    assigned_to_user_id = body.get('assigned_to_user_id')
    if assigned_to_user_id is not None and not database.get_user(assigned_to_user_id):
        return jsonify({"error": "assigned_to_user_id does not match a real team member"}), 400
    try:
        detail = tasks_module.create_task_from_discrepancy(
            discrepancy_id, current_user()["id"], assigned_to_user_id=assigned_to_user_id, due_date=body.get('due_date')
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    database.insert_activity("task_created", f"Task created from discrepancy: {detail['title']}", lease_id=detail.get('lease_id'))
    return jsonify(detail), 201


@app.route('/tasks/from-alert/<int:alert_id>', methods=['POST'])
@require_role('analyst')
def create_task_from_alert_route(alert_id):
    """Body: {"assigned_to_user_id": int (optional), "due_date": "YYYY-MM-DD" (optional)}. Carries the alert's title/severity/message into the new task automatically."""
    body = request.get_json(silent=True) or {}
    assigned_to_user_id = body.get('assigned_to_user_id')
    if assigned_to_user_id is not None and not database.get_user(assigned_to_user_id):
        return jsonify({"error": "assigned_to_user_id does not match a real team member"}), 400
    try:
        detail = tasks_module.create_task_from_alert(
            alert_id, current_user()["id"], assigned_to_user_id=assigned_to_user_id, due_date=body.get('due_date')
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    database.insert_activity("task_created", f"Task created from alert: {detail['title']}", lease_id=detail.get('lease_id'))
    return jsonify(detail), 201


@app.route('/tasks/<int:task_id>', methods=['GET'])
@require_role()
def get_task_route(task_id):
    task = database.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(tasks_module.task_detail(task)), 200


@app.route('/tasks/<int:task_id>', methods=['PATCH'])
@require_role('analyst')
def update_task_route(task_id):
    """Body: any of {"title": str, "description": str, "due_date": "YYYY-MM-DD"|null, "priority": "normal"|"high"}. due_date: null explicitly clears it; omitting the key leaves it unchanged."""
    if not database.get_task(task_id):
        return jsonify({"error": "Task not found"}), 404
    body = request.get_json(silent=True) or {}
    title = body.get('title')
    if title is not None and not title.strip():
        return jsonify({"error": "title cannot be blank"}), 400
    priority = body.get('priority')
    if priority is not None and priority not in tasks_module.VALID_PRIORITIES:
        return jsonify({"error": f"priority must be one of: {', '.join(sorted(tasks_module.VALID_PRIORITIES))}"}), 400
    clear_due_date = 'due_date' in body and body.get('due_date') is None
    updated = database.update_task_fields(
        task_id, title=title, description=body.get('description'), due_date=body.get('due_date'),
        _clear_due_date=clear_due_date, priority=priority,
    )
    return jsonify(tasks_module.task_detail(updated)), 200


@app.route('/tasks/<int:task_id>/assign', methods=['POST'])
@require_role('analyst')
def assign_task_route(task_id):
    """Body: {"assigned_to_user_id": int|null}. null unassigns the task."""
    if not database.get_task(task_id):
        return jsonify({"error": "Task not found"}), 404
    body = request.get_json(silent=True) or {}
    assigned_to_user_id = body.get('assigned_to_user_id')
    if assigned_to_user_id is not None and not database.get_user(assigned_to_user_id):
        return jsonify({"error": "assigned_to_user_id does not match a real team member"}), 400
    updated = database.update_task_assignee(task_id, assigned_to_user_id)
    return jsonify(tasks_module.task_detail(updated)), 200


@app.route('/tasks/<int:task_id>/status', methods=['POST'])
@require_role('analyst')
def update_task_status_route(task_id):
    """
    Body: {"status": "open"|"in_progress"|"done", "correct_source": str
    (optional), "note": str (optional)}. This is the SAME route the
    "Complete Task" button already used and was verified against
    end-to-end before this feature existed -- extended here, not
    replaced, so every existing caller (open/in_progress transitions,
    a plain "done" on a task with no discrepancy) behaves exactly as
    before.

    The one new behavior: completing ("done") a task that's tied to a
    discrepancy (task.discrepancy_id set) which is still open requires
    a decision about which source was correct, same as resolving that
    discrepancy directly would (POST /discrepancies/<id>/resolve) --
    `correct_source`/`note` in THIS request's body. Omitting them does
    NOT silently guess; it rejects the status change with 400 (same
    "Missing required field(s)" shape /resolve itself already uses) so
    the caller is forced to confirm, consistent with that existing
    flow rather than inventing a second way to resolve a discrepancy.
    Providing them resolves the discrepancy via the real
    resolve_discrepancy path (same permanent resolution log a human's
    direct resolve action writes to) before completing the task.

    If the linked discrepancy is already resolved (by a direct resolve,
    or auto-resolved by a lease resubmission) by the time this runs,
    the task completes with no further requirement -- there's nothing
    left to confirm.
    """
    task = database.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    body = request.get_json(silent=True) or {}
    status = (body.get('status') or '').strip()
    if status not in tasks_module.VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {', '.join(sorted(tasks_module.VALID_STATUSES))}"}), 400

    discrepancy_resolved_now = False
    if status == "done" and task.get("discrepancy_id"):
        discrepancy = database.get_discrepancy(task["discrepancy_id"])
        if discrepancy and discrepancy["status"] == "open":
            correct_source = (body.get('correct_source') or '').strip()
            note = (body.get('note') or '').strip()
            missing = [f for f, v in (('correct_source', correct_source), ('note', note)) if not v]
            if missing:
                return jsonify({
                    "error": f"Missing required field(s): {', '.join(missing)} -- this task is tied to an "
                             "open discrepancy, which must be resolved (confirm which source was correct) "
                             "before the task can be marked done.",
                    "discrepancy_id": discrepancy["id"],
                }), 400
            user = current_user()
            database.resolve_discrepancy(discrepancy["id"], correct_source, note, user["name"], user["email"])
            _invalidate_discrepancy_derived_caches()
            resolved_discrepancy = database.get_discrepancy(discrepancy["id"])
            database.insert_activity(
                "discrepancy_resolved",
                f"Discrepancy #{discrepancy['id']} ({resolved_discrepancy['category']}) resolved by "
                f"{user['name']} via completing task \"{task['title']}\": {note}",
                lease_id=_activity_lease_id(resolved_discrepancy.get("lease_id")),
            )
            discrepancy_resolved_now = True

    updated = database.update_task_status(task_id, status)
    detail = tasks_module.task_detail(updated)
    detail["discrepancy_resolved_now"] = discrepancy_resolved_now
    return jsonify(detail), 200


@app.route('/tasks/<int:task_id>', methods=['DELETE'])
@require_role('analyst')
def delete_task_route(task_id):
    if not database.delete_task(task_id):
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"status": "deleted"}), 200


@app.route('/tasks/bulk-status', methods=['POST'])
@require_role('analyst')
def bulk_update_task_status():
    """
    Body: {"ids": [1, 2, 3], "status": "open"|"in_progress"|"done"|"dismissed"}.
    The Tasks page's multi-select "Complete"/"Dismiss" bulk actions --
    same loop-and-report shape as /alerts/bulk-dismiss and
    /discrepancies/bulk-resolve.

    Completing ("done") a task tied to a still-open discrepancy is
    SKIPPED here, not force-completed -- a bulk action has no per-task
    field to confirm which source was correct (see the single-task
    POST /tasks/<id>/status route this mirrors), and guessing would
    contradict this app's "never silently guess" rule for discrepancy
    resolution. Skipped ids are reported back so the caller can open
    each one individually to resolve it there instead.
    """
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    status = (payload.get('status') or '').strip()
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "Provide a non-empty 'ids' list of integers"}), 400
    if status not in tasks_module.VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {', '.join(sorted(tasks_module.VALID_STATUSES))}"}), 400

    tasks_by_id = database.get_tasks_by_ids(ids)
    discrepancy_ids_to_check = [
        t["discrepancy_id"] for t in tasks_by_id.values()
        if status == "done" and t.get("discrepancy_id")
    ]
    discrepancies_by_id = database.get_discrepancies_by_ids(discrepancy_ids_to_check)

    updated, skipped_needs_discrepancy, not_found = [], [], []
    for task_id in ids:
        task = tasks_by_id.get(task_id)
        if not task:
            not_found.append(task_id)
            continue
        if status == "done" and task.get("discrepancy_id"):
            discrepancy = discrepancies_by_id.get(task["discrepancy_id"])
            if discrepancy and discrepancy["status"] == "open":
                skipped_needs_discrepancy.append(task_id)
                continue
        database.update_task_status(task_id, status)
        updated.append(task_id)

    if updated:
        database.insert_activity(
            "tasks_bulk_status_updated",
            f"{current_user()['name']} set {len(updated)} task(s) to '{status}' (bulk)",
        )
    return jsonify({"updated": updated, "skipped_needs_discrepancy": skipped_needs_discrepancy, "not_found": not_found}), 200


@app.route('/tasks/bulk-reassign', methods=['POST'])
@require_role('analyst')
def bulk_reassign_tasks():
    """Body: {"ids": [1, 2, 3], "assigned_to_user_id": int|null}. null unassigns every listed task."""
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    assigned_to_user_id = payload.get('assigned_to_user_id')
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "Provide a non-empty 'ids' list of integers"}), 400
    if assigned_to_user_id is not None and not database.get_user(assigned_to_user_id):
        return jsonify({"error": "assigned_to_user_id does not match a real team member"}), 400

    updated, not_found = [], []
    for task_id in ids:
        if not database.get_task(task_id):
            not_found.append(task_id)
            continue
        database.update_task_assignee(task_id, assigned_to_user_id)
        updated.append(task_id)

    if updated:
        assignee_name = database.get_user(assigned_to_user_id)["name"] if assigned_to_user_id is not None else "Unassigned"
        database.insert_activity(
            "tasks_bulk_reassigned",
            f"{current_user()['name']} reassigned {len(updated)} task(s) to {assignee_name} (bulk)",
        )
    return jsonify({"updated": updated, "not_found": not_found}), 200


@app.route('/tasks/<int:task_id>/comments', methods=['GET'])
@require_role()
def list_task_comments(task_id):
    """Team discussion on this task -- separate from lease_field_edits (that's a data-correction audit trail, this is conversation), visible to everyone, same "whole team" reasoning as lease/discrepancy comments."""
    if not database.get_task(task_id):
        return jsonify({"error": "Task not found"}), 404
    return jsonify(database.get_task_comments(task_id)), 200


@app.route('/tasks/<int:task_id>/comments', methods=['POST'])
@require_role('analyst')
def add_task_comment(task_id):
    """
    Body: {"body": "..."}. The comment's author is always the logged-in
    session user -- see _validate_comment_payload.

    Unlike lease/discrepancy comments (which don't write to
    activity_log), a task comment DOES -- explicitly requested so
    discussion on a task ("checked with the broker, this is
    intentional") is visible in the same portfolio-wide activity feed
    as everything else that happens to that task, not just to someone
    who happens to open the task's comment thread.
    """
    task = database.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    payload = request.get_json(silent=True) or {}
    body, error = _validate_comment_payload(payload)
    if error:
        return error
    user = current_user()
    database.add_comment(user["name"], body, task_id=task_id, author_email=user["email"])
    database.insert_activity(
        "task_commented",
        f"{user['name']} commented on task \"{task['title']}\": {body}",
        lease_id=_activity_lease_id(task.get("lease_id")),
    )
    return jsonify(database.get_task_comments(task_id)), 201


@app.route('/leases/<int:lease_id>/fields/<field_name>/edits/<int:edit_id>/undo', methods=['POST'])
@require_role('analyst')
def undo_lease_field_edit(lease_id, field_name, edit_id):
    """
    Reverts one specific field edit back to the value it held just
    before that edit was made (see database.revert_lease_field_edit --
    the original edit row is marked reverted_at, never deleted, and a
    new lease_field_edits row records the revert itself, so the audit
    trail stays a complete, honest timeline).

    Only allowed when ALL of the following hold:
      - the edit hasn't already been reverted
      - it's the single most recent (not-yet-reverted) edit for this
        lease+field -- undoing an older one while a later edit already
        superseded it would silently discard that later value
      - it happened within tasks_module.UNDO_WINDOW_MINUTES
      - if the edit is linked to a task (task_id set), that task isn't
        already done -- once a task is complete, its corrections are
        final, not something to keep unwinding after the fact (this is
        the exact "recently... and the task isn't completed yet" gate
        the in-task Undo option is built around)
    """
    edits = database.get_lease_field_edits(lease_id=lease_id, field_name=field_name)
    matching = next((e for e in edits if e["id"] == edit_id), None)
    if not matching:
        return jsonify({"error": "Edit not found for this lease/field"}), 404
    if matching.get("reverted_at"):
        return jsonify({"error": "This edit has already been undone."}), 400

    not_reverted = [e for e in edits if not e.get("reverted_at")]
    latest = not_reverted[-1] if not_reverted else None
    if not latest or latest["id"] != edit_id:
        return jsonify({"error": "A newer edit has already been made to this field -- only the most recent edit can be undone."}), 400

    edited_at = datetime.fromisoformat(matching["created_at"])
    age_minutes = (datetime.now(timezone.utc) - edited_at).total_seconds() / 60
    if age_minutes > tasks_module.UNDO_WINDOW_MINUTES:
        return jsonify({"error": f"This edit is more than {tasks_module.UNDO_WINDOW_MINUTES} minutes old and can no longer be undone."}), 400

    if matching.get("task_id"):
        task = database.get_task(matching["task_id"])
        if task and task["status"] == "done":
            return jsonify({"error": "This edit's task is already complete -- undo is only available while the task is still open."}), 400

    user = current_user()
    restored = database.revert_lease_field_edit(edit_id, user["name"], user["email"])
    if restored is None:
        return jsonify({"error": "Lease not found"}), 404
    _invalidate_lease_derived_caches()
    database.insert_activity(
        "lease_field_edit_undone",
        f"{user['name']} undid a correction to {field_name.replace('_', ' ')} on lease #{lease_id}",
        lease_id=lease_id,
    )
    return jsonify({"lease_id": lease_id, "field_name": field_name, "field": restored}), 200


@app.route('/today', methods=['GET'])
@require_role()
def today_view():
    """
    GET /today?user_id=<id> (optional, defaults to the caller). Powers
    the daily dashboard: this user's open assignments (leases,
    discrepancies, properties -- enriched, not just ids) plus the
    portfolio's currently-active alerts. See
    assignments.compute_today_view for exactly what "today" means and
    why alerts aren't filtered to the user. Any logged-in role may
    view any user's Today, same as every other shared view in this app
    (no per-account data scoping) -- but the id must be a real user.
    """
    user_id = request.args.get('user_id', type=int) or current_user()["id"]
    if not database.get_user(user_id):
        return jsonify({"error": "User not found"}), 404
    return jsonify(assignments_module.compute_today_view(user_id)), 200


@app.route('/action-items', methods=['GET'])
@require_role()
def action_items():
    """
    GET /action-items?user_id=<id> (optional, defaults to the caller).
    One prioritized, chronological list combining this user's open
    tasks with a due date, portfolio-wide lease expirations, and
    renewal-notice deadlines -- see app.action_items.compute_action_items
    for exactly how the merge and sort work. Same "any logged-in role
    may view any user's list, id must be real" convention as /today.
    """
    user_id = request.args.get('user_id', type=int) or current_user()["id"]
    if not database.get_user(user_id):
        return jsonify({"error": "User not found"}), 404
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify({"items": compute_action_items(user_id, leases)}), 200


# ----------------------------------------------------------------------
# AI assistant: a chat-style helper grounded in the real portfolio.
# See app/assistant.py for the actual Claude API call + grounding
# logic -- this route is just validation, rate limiting, and
# persisting the conversation.
# ----------------------------------------------------------------------

@app.route('/assistant/ask', methods=['POST'])
@require_role()
def assistant_ask():
    """
    Body: {"question": str}. Returns
    {"response_type": "informational"|"navigational"|"clarifying",
     "answer": str, "route": str|null, "lease_id": int|null}.
    Every call is persisted to this user's own conversation history
    (GET /assistant/conversations) -- see database.insert_assistant_conversation.
    """
    user = current_user()
    if assistant.is_rate_limited(user["id"]):
        return jsonify({"error": f"Too many questions -- please wait a moment and try again (limit: {assistant.RATE_LIMIT_MAX} per minute)."}), 429

    body = request.get_json(silent=True) or {}
    question = (body.get('question') or '').strip()
    if not question:
        return jsonify({"error": "Missing required field: question"}), 400
    if len(question) > 2000:
        return jsonify({"error": "Question is too long (max 2000 characters)."}), 400

    try:
        result = assistant.ask_assistant(question)
    except assistant.AssistantError:
        return jsonify({"error": "The assistant is temporarily unavailable. Please try again in a moment."}), 502

    database.insert_assistant_conversation(
        user["id"], question, result["response_type"], result["answer"],
        route=result.get("route"), route_params=({"lease_id": result["lease_id"]} if result.get("lease_id") is not None else None),
    )
    return jsonify(result), 200


@app.route('/assistant/conversations', methods=['GET'])
@require_role()
def assistant_conversations():
    """
    GET /assistant/conversations?limit=50. ALWAYS the caller's own
    history -- deliberately no user_id override like /today has, since
    a conversation can contain more sensitive back-and-forth than a
    task list, and there's no legitimate "let me see someone else's
    chat with the assistant" use case the way there is for viewing a
    teammate's assigned work. Scoped by session user_id only, never a
    request parameter -- see database.get_assistant_conversations.
    """
    limit = request.args.get('limit', default=50, type=int)
    conversations = database.get_assistant_conversations(current_user()["id"], limit=limit)
    return jsonify(conversations), 200


# ----------------------------------------------------------------------
# Internal team messaging: direct + group threads. Separate from the
# lease/discrepancy comments feature -- this is private chat tied to
# no record, isolated strictly to its participants (see
# app/messaging.py's module docstring). Every route below either
# lists ONLY the caller's own threads (list_threads_for_user already
# joins through participancy at the SQL level) or explicitly checks
# database.is_thread_participant before touching a specific thread --
# a non-participant gets 404, never 403, so a thread's mere existence
# isn't confirmed to someone who isn't in it.
# ----------------------------------------------------------------------

@app.route('/threads', methods=['GET'])
@require_role()
def list_threads():
    threads = database.list_threads_for_user(current_user()["id"])
    return jsonify([messaging.thread_detail(t, current_user()["id"]) for t in threads]), 200


@app.route('/threads', methods=['POST'])
@require_role()
def create_thread_route():
    """
    Body: {"thread_type": "direct"|"group", "participant_user_ids": [int, ...], "name": str (group only, optional)}.
    The caller is always added as a participant automatically, whether
    or not they included their own id. "direct" requires exactly one
    OTHER participant (so exactly 2 total) -- reuses an existing
    direct thread with that person if one exists, rather than creating
    a duplicate (see database.find_direct_thread).
    """
    body = request.get_json(silent=True) or {}
    thread_type = (body.get('thread_type') or '').strip()
    other_ids = body.get('participant_user_ids') or []
    name = (body.get('name') or '').strip() or None
    caller_id = current_user()["id"]

    if thread_type not in messaging.VALID_THREAD_TYPES:
        return jsonify({"error": f"thread_type must be one of: {', '.join(sorted(messaging.VALID_THREAD_TYPES))}"}), 400
    if not isinstance(other_ids, list) or not other_ids:
        return jsonify({"error": "Missing required field: participant_user_ids (non-empty list)"}), 400

    all_ids = sorted(set(other_ids) | {caller_id})
    for uid in all_ids:
        if not isinstance(uid, int) or not database.get_user(uid):
            return jsonify({"error": f"participant_user_ids must all be real team members (invalid: {uid!r})"}), 400

    if thread_type == "direct":
        if len(all_ids) != 2:
            return jsonify({"error": "A direct thread needs exactly one other participant"}), 400
        existing = database.find_direct_thread(all_ids[0], all_ids[1])
        if existing is not None:
            return jsonify(messaging.thread_detail(database.get_thread(existing), caller_id)), 200

    thread_id = database.create_thread(thread_type, all_ids, caller_id, name=name)
    return jsonify(messaging.thread_detail(database.get_thread(thread_id), caller_id)), 201


@app.route('/threads/<int:thread_id>/participants', methods=['POST'])
@require_role()
def add_thread_participant_route(thread_id):
    """Body: {"user_id": int}. Group threads only -- a direct thread's participant pair is fixed at creation."""
    if not database.is_thread_participant(thread_id, current_user()["id"]):
        return jsonify({"error": "Thread not found"}), 404
    thread = database.get_thread(thread_id)
    if thread["thread_type"] != "group":
        return jsonify({"error": "Only group threads support adding participants"}), 400

    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id')
    if not user_id or not database.get_user(user_id):
        return jsonify({"error": "user_id must be a real team member"}), 400

    database.add_thread_participant(thread_id, user_id)
    return jsonify(messaging.thread_detail(database.get_thread(thread_id), current_user()["id"])), 200


@app.route('/threads/<int:thread_id>/messages', methods=['GET'])
@require_role()
def get_thread_messages(thread_id):
    """GET /threads/<id>/messages?since=<ISO timestamp>&limit=100. `since` is for polling -- omit it for the full (capped) history."""
    if not database.is_thread_participant(thread_id, current_user()["id"]):
        return jsonify({"error": "Thread not found"}), 404
    since = request.args.get('since')
    limit = request.args.get('limit', default=100, type=int)
    messages = database.get_messages(thread_id, since=since, limit=limit)
    return jsonify([messaging.message_detail(m) for m in messages]), 200


@app.route('/threads/<int:thread_id>/messages', methods=['POST'])
@require_role()
def post_thread_message(thread_id):
    """Body: {"body": str}."""
    if not database.is_thread_participant(thread_id, current_user()["id"]):
        return jsonify({"error": "Thread not found"}), 404
    body = request.get_json(silent=True) or {}
    text = (body.get('body') or '').strip()
    if not text:
        return jsonify({"error": "Missing required field: body"}), 400
    if len(text) > 10000:
        return jsonify({"error": "Message is too long (max 10000 characters)."}), 400

    message_id = database.insert_message(thread_id, current_user()["id"], text)
    return jsonify(messaging.message_detail(database.get_message(message_id))), 201


@app.route('/threads/<int:thread_id>/read', methods=['POST'])
@require_role()
def mark_thread_read_route(thread_id):
    if not database.is_thread_participant(thread_id, current_user()["id"]):
        return jsonify({"error": "Thread not found"}), 404
    database.mark_thread_read(thread_id, current_user()["id"])
    return jsonify({"status": "marked_read"}), 200


@app.route('/messages/unread-count', methods=['GET'])
@require_role()
def messages_unread_count():
    """A single cheap number for a polling badge -- see the frontend's existing startLiveActivityPolling() for the established polling convention this is meant to plug into (same idea, scoped to this user's own unread messages instead of portfolio-wide activity)."""
    counts = database.get_unread_counts_for_user(current_user()["id"])
    return jsonify({"total_unread": sum(counts.values()), "by_thread": counts}), 200


# ----------------------------------------------------------------------
# Email account linking (OAuth send-as)
# ----------------------------------------------------------------------

def _owned_linked_account_or_404(account_id, user_id):
    """Same 404-not-403 isolation convention as thread access -- a linked account belonging to someone else should look identical to a nonexistent one."""
    account = database.get_linked_email_account(account_id)
    if account is None or account["user_id"] != user_id:
        return None
    return account


@app.route('/email-accounts/connect/<provider>', methods=['GET'])
@require_role()
def connect_email_account(provider):
    try:
        url = email_accounts.build_authorize_url(provider, current_user()["id"])
    except email_accounts.ProviderNotConfigured as e:
        return jsonify({"error": str(e)}), 503
    except email_accounts.EmailAccountError as e:
        return jsonify({"error": str(e)}), 400
    return redirect(url)


@app.route('/email-accounts/callback/<provider>', methods=['GET'])
def email_account_callback(provider):
    """The OAuth provider redirects the user's browser here after they grant (or deny) consent -- there is no session-based auth at this point in the flow (this is a cross-site navigation), so the user is identified entirely via the one-time state token minted in connect_email_account, not via current_user()."""
    error = request.args.get('error')
    if error:
        return f"<p>Email linking was cancelled or denied: {error}. You can close this tab.</p>", 200

    code = request.args.get('code')
    state = request.args.get('state')
    if not code or not state:
        return "<p>Missing code or state on the OAuth callback.</p>", 400

    try:
        account = email_accounts.handle_oauth_callback(provider, code, state)
    except email_accounts.EmailAccountError as e:
        return f"<p>Could not link this account: {e}</p>", 400

    return f"<p>Connected {account['provider_email']} ({account['provider']}). You can close this tab.</p>", 200


@app.route('/email-accounts', methods=['GET'])
@require_role()
def list_email_accounts():
    accounts = database.list_linked_email_accounts_for_user(current_user()["id"])
    return jsonify([email_accounts.account_detail(a) for a in accounts]), 200


@app.route('/email-accounts/<int:account_id>', methods=['DELETE'])
@require_role()
def disconnect_email_account(account_id):
    account = _owned_linked_account_or_404(account_id, current_user()["id"])
    if account is None:
        return jsonify({"error": "Linked email account not found"}), 404
    email_accounts.disconnect_account(account)
    return jsonify({"status": "disconnected"}), 200


@app.route('/email-accounts/<int:account_id>/send', methods=['POST'])
@require_role()
def send_email_via_linked_account(account_id):
    account = _owned_linked_account_or_404(account_id, current_user()["id"])
    if account is None:
        return jsonify({"error": "Linked email account not found"}), 404
    body = request.get_json(silent=True) or {}
    to = (body.get('to') or '').strip()
    subject = (body.get('subject') or '').strip()
    message_body = body.get('body') or ''
    if not to or not subject or not message_body.strip():
        return jsonify({"error": "Missing required fields: to, subject, body"}), 400
    try:
        email_accounts.send_email_as(account_id, to, subject, message_body)
    except email_accounts.EmailAccountError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"status": "sent"}), 200


# ----------------------------------------------------------------------
# Waitlist (landing page gate)
#
# /waitlist (GET), /waitlist/<id>/approve, and /waitlist/<id>/deny all
# require an authenticated admin-role session (see app/auth.py's
# require_role('admin')) -- viewing every signup's email and marking a
# request approved/denied is exactly the kind of privileged action
# that must sit behind real auth, not an unguessable-URL convention.
# Approving a signup here is advisory only -- it marks someone an
# approved prospect, it does not by itself create a real login. An
# admin separately creates the actual account (email/name/role/
# password) via POST /team/members once ready to actually onboard
# them.
#
# /waitlist/check (below) is DELIBERATELY still public, but that's a
# separate, narrower decision: it only ever answers "is this one email
# approved?" for the email the caller already supplies — it never
# returns the signup list, other people's emails, or anything the caller
# doesn't already know. This is what /app's access gate calls (see
# frontend/app/access-gate.js). It is not real authentication — there is
# no password and no proof the caller actually owns the email address,
# only a self-reported match against the waitlist's approval status. See
# DECISIONS.md "Access gate uses self-reported email, not real auth".
# ----------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _send_email_best_effort(send_fn, *args):
    """
    Calls a send_* function from email_service.py and swallows ANY
    exception it might raise. email_service.py's own functions already
    catch everything internally and return False rather than raising —
    this is a second, redundant layer at the call site itself, so a
    future bug in email_service (or in whatever library it uses) can
    never turn a successful waitlist signup/approval into a 500 response
    for the person submitting or the admin approving. Belt and
    suspenders, deliberately: the cost of the extra try/except is
    trivial, and the failure mode it guards against — an email problem
    blocking a real signup — is exactly what this feature must never do.
    """
    try:
        send_fn(*args)
    except Exception:
        logger.exception("Unexpected error calling %s", getattr(send_fn, "__name__", send_fn))


# In-memory, per-process, per-IP fixed-window rate limit on POST
# /waitlist -- deliberately not a new dependency (Flask-Limiter, Redis,
# ...), consistent with this project's minimal-dependencies precedent.
# Added after a real incident where two test files hit this exact route
# in a loop with no email mocking, sending real emails to ADMIN_EMAIL
# (see DECISIONS.md and the EMAIL_USER/EMAIL_APP_PASSWORD stripping now
# in test_access_gate.py/test_admin_auth.py/run_all_tests.py, which
# fixes the actual root cause of that specific incident). This is
# defense in depth on the route itself: it's a public, unauthenticated
# endpoint that sends two real emails per call, so it should never be
# hittable in a tight loop regardless of what's calling it. 15/60s
# comfortably clears every existing test file's own waitlist-signup
# count (the largest is 7, in test_waitlist_email.py) while cutting a
# real tight loop's throughput by well over 90%. Resets on backend
# restart -- fine here, since the goal is "can't be hit in a tight
# loop," not durable abuse tracking.
_waitlist_rate_limit_state = {}  # ip -> (window_start_epoch_seconds, count_in_window)
_WAITLIST_RATE_LIMIT_MAX = 15
_WAITLIST_RATE_LIMIT_WINDOW_SECONDS = 60


def _waitlist_rate_limited(ip: str) -> bool:
    now = time.time()
    window_start, count = _waitlist_rate_limit_state.get(ip, (now, 0))
    if now - window_start >= _WAITLIST_RATE_LIMIT_WINDOW_SECONDS:
        window_start, count = now, 0
    count += 1
    _waitlist_rate_limit_state[ip] = (window_start, count)
    return count > _WAITLIST_RATE_LIMIT_MAX


@app.route('/waitlist', methods=['POST'])
def join_waitlist():
    """Body: {"email": str}. Adds the email to the waitlist as 'pending'."""
    if _waitlist_rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Too many requests. Please try again in a minute."}), 429

    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()

    if not email or not _EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address"}), 400

    result = database.insert_waitlist_signup(email)
    if result["status"] == "duplicate":
        # Same UX either way — we don't want to reveal whether an email
        # is already on the list to a third party probing addresses.
        # No confirmation email here either, on purpose: it already went
        # out on the real first signup, and re-sending on every repeat
        # POST would let someone spam a stranger's inbox just by
        # resubmitting their address.
        return jsonify({"message": "Your request has been received. If it's a fit, we'll be in touch."}), 200

    # Best-effort — see _send_email_best_effort. The signup above is
    # already committed to the database regardless of whether either
    # send succeeds. Two separate emails, two separate recipients: the
    # requester gets a confirmation, the admin gets a notification that
    # a new request is waiting on them.
    _send_email_best_effort(email_service.send_waitlist_confirmation_email, email)
    _send_email_best_effort(email_service.send_admin_new_request_notification, email)

    return jsonify({"message": "Your request has been received. If it's a fit, we'll be in touch."}), 201


# Generous relative to the waitlist limiter above -- this fires once per
# marketing-page load (plus once more on a successful waitlist submit),
# not once per deliberate form submission, so normal browsing across
# index.html/pricing.html needs headroom the waitlist limiter doesn't.
_pageview_rate_limiter = RateLimiter(max_hits=60, window_seconds=60)  # per IP: 60 / minute


@app.route('/analytics/pageview', methods=['POST'])
def record_pageview():
    """
    Body: {"path": str, "referrer": str (optional), "session_id": str
    (optional)}. Public, unauthenticated -- fired by frontend/landing.js
    on every marketing-page load, and once more with a synthetic path on
    a successful waitlist submission (see database.PAGEVIEW_CONVERSION_
    PATH). Fire-and-forget telemetry: the response is never branched on
    for anything beyond ok/not-ok, so there's nothing here beyond basic
    shape validation and a generous per-IP rate limit against abuse.
    """
    if _pageview_rate_limiter.check([f"ip:{request.remote_addr or 'unknown'}"]):
        return jsonify({"error": "Too many requests."}), 429

    body = request.get_json(silent=True) or {}
    path = (body.get("path") or "").strip()
    referrer = (body.get("referrer") or "").strip() or None
    session_id = (body.get("session_id") or "").strip() or None

    if not path.startswith("/") or len(path) > 512:
        return jsonify({"error": "Invalid path"}), 400
    if referrer and len(referrer) > 1024:
        referrer = referrer[:1024]
    if session_id and len(session_id) > 128:
        session_id = session_id[:128]

    database.insert_pageview(path, referrer, session_id)
    return jsonify({"status": "ok"}), 201


@app.route('/waitlist', methods=['GET'])
@require_role('admin')
def list_waitlist():
    """Admin-only. Lists every signup, newest first."""
    return jsonify(database.get_all_waitlist_signups()), 200


@app.route('/waitlist/<int:signup_id>/approve', methods=['POST'])
@require_role('admin')
def approve_waitlist(signup_id):
    """Admin-only. Flips a signup's status to 'approved'."""
    signup = database.get_waitlist_signup(signup_id)
    if not signup:
        return jsonify({"error": "Signup not found"}), 404

    database.approve_waitlist_signup(signup_id)
    # Best-effort, same as the confirmation email above — never blocks
    # or fails this response.
    _send_email_best_effort(email_service.send_waitlist_approval_email, signup["email"])

    return jsonify({"id": signup_id, "status": "approved"}), 200


@app.route('/waitlist/<int:signup_id>/deny', methods=['POST'])
@require_role('admin')
def deny_waitlist(signup_id):
    """Admin-only. Flips a signup's status to 'denied'. No email is sent -- there's no "you were denied" template, and adding one wasn't asked for; this is a silent status change the admin dashboard reflects."""
    signup = database.get_waitlist_signup(signup_id)
    if not signup:
        return jsonify({"error": "Signup not found"}), 404

    database.deny_waitlist_signup(signup_id)
    return jsonify({"id": signup_id, "status": "denied"}), 200


@app.route('/waitlist/check', methods=['POST'])
def check_waitlist_access():
    """Body: {"email": str}. Used by /app's access gate to decide whether
    to let a visitor in. Returns only {"approved": bool, "found": bool} —
    see the NOTE above this section for why this narrow shape is fine to
    leave unauthenticated while /waitlist (GET) is not."""
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()

    if not email or not _EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address"}), 400

    signup = database.get_waitlist_signup_by_email(email)
    if not signup:
        return jsonify({"approved": False, "found": False}), 200

    return jsonify({"approved": signup["status"] == "approved", "found": True}), 200


# ----------------------------------------------------------------------
# Portfolio analysis
# ----------------------------------------------------------------------

def _lease_risks(lease):
    """Risk flags for one effective lease, using its own stored date_candidates, the current portfolio average, and any cross-lease mismatches with other leases at the same property as context."""
    all_leases = database.get_all_effective_leases()
    context = portfolio_context_for_risk_analysis(all_leases)
    date_candidates = lease.get("date_candidates")
    cross_lease_flags = compute_cross_lease_mismatches(all_leases).get(lease["id"], [])
    flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates, cross_lease_flags)
    return sync_lease_risk_flags(lease["id"], flags)


@app.route('/portfolio/summary', methods=['GET'])
@require_role()
def portfolio_summary():
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_portfolio_metrics(leases)), 200


@app.route('/portfolio/timeline', methods=['GET'])
@require_role()
def portfolio_timeline():
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_expiration_timeline(leases)), 200


@app.route('/portfolio/attention', methods=['GET'])
@require_role()
def portfolio_attention():
    """'What needs attention today' — expiring soon, missing data, needs verification, unusual terms. See compute_attention_items for the exact definitions."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_attention_items(leases)), 200


@app.route('/portfolio/expiration-alerts', methods=['GET'])
@require_role()
def portfolio_expiration_alerts():
    """Dashboard widget data: leases expiring within 90/60/30 days, plus renewal-notice deadlines closing soon -- see compute_expiration_alerts for the exact windows and why the two lists are kept separate."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_expiration_alerts(leases)), 200


@app.route('/portfolio/health', methods=['GET'])
@require_role()
def portfolio_health():
    """Morning-glance health strip: % verified, avg days to expiration, rent exposure expiring in 6/12 months."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_portfolio_health(leases)), 200


@app.route('/portfolio/confidence-summary', methods=['GET'])
@require_role()
def portfolio_confidence_summary():
    """The trust-mechanism number: field counts by confidence tier across the whole portfolio, plus how many were flagged for review during validation. See compute_portfolio_confidence_summary."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_portfolio_confidence_summary(leases)), 200


@app.route('/portfolio/health-score', methods=['GET'])
@require_role()
def portfolio_health_score_route():
    """
    GET /portfolio/health-score?staleness_threshold_months=6 (optional,
    defaults to 6). A single, defensible 0-100 trust score for the
    current portfolio's DATA, not the same thing as GET /portfolio/
    health's "what needs attention today" strip -- see
    app/portfolio_health_score.py's module docstring for the full,
    explicitly documented formula behind this number.

    Cached (see app/cache.py) -- this walks every lease's confidence/
    verification/staleness state plus every open discrepancy on every
    call, real work worth avoiding on a sidebar someone might switch
    into repeatedly. Invalidated explicitly whenever a lease or
    discrepancy mutates (see the cache.invalidate("health_score") call
    sites), with a 60s TTL as a safety net regardless.
    """
    threshold_raw = request.args.get('staleness_threshold_months')
    if threshold_raw is not None:
        try:
            threshold_months = float(threshold_raw)
        except ValueError:
            return jsonify({"error": "staleness_threshold_months must be a number"}), 400
        if threshold_months <= 0:
            return jsonify({"error": "staleness_threshold_months must be positive"}), 400
    else:
        threshold_months = DEFAULT_STALENESS_THRESHOLD_MONTHS

    cache_key = f"health_score:{threshold_months}"
    result = cache.get_or_compute(cache_key, lambda: compute_portfolio_health_score(staleness_threshold_months=threshold_months))
    return jsonify(result), 200


@app.route('/portfolio/tenant-concentration', methods=['GET'])
@require_role()
def portfolio_tenant_concentration():
    """How much of total rent depends on a small number of tenants -- top-1/3/5 cumulative share, Herfindahl-Hirschman Index, and a high/moderate/low read. See compute_tenant_concentration."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_tenant_concentration(leases)), 200


@app.route('/portfolio/rollover', methods=['GET'])
@require_role()
def portfolio_rollover():
    """
    Rollover risk and WALT together, in one response -- shipped as a
    single combined Platform feature, so both numbers are computed
    against the exact same `reference_date` (fetched once here, not
    independently inside each function) so they can never disagree
    about what "today" means if a request happened to straddle
    midnight. See compute_walt and compute_rollover_schedule.
    """
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    reference_date = date.today()
    return jsonify({
        "walt": compute_walt(leases, reference_date=reference_date),
        "rollover_schedule": compute_rollover_schedule(leases, reference_date=reference_date),
    }), 200


@app.route('/portfolio/loss-to-lease', methods=['GET'])
@require_role()
def portfolio_loss_to_lease():
    """Upside vs. this portfolio's own best-achieved rent/sqft per building (no external market-rent data source exists -- see compute_loss_to_lease's docstring for why this is an internal proxy, not true market rent)."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(compute_loss_to_lease(leases)), 200


@app.route('/portfolio/property-trends', methods=['GET'])
@require_role()
def portfolio_property_trends():
    """
    GET /portfolio/property-trends?property_address=X

    Every historical upload (lease PDF or rent-roll row, base leases
    only -- amendments are folded into their base lease's current
    values, not separately timelined) for one building, plus rent
    growth, tenant turnover, and rollover-pattern trends computed from
    it. Building-level matched (suite-insensitive) -- see
    compute_property_trends's own docstring for the full shape and the
    unit-vs-building matching distinction. 400 if property_address is
    missing/blank; otherwise 200 even when zero records match (an
    honest "no history yet" result, not an error).

    Cached per property_address (see app/cache.py) -- invalidated
    whenever a lease mutates, 60s TTL as a safety net regardless.
    """
    property_address = (request.args.get('property_address') or '').strip()
    if not property_address:
        return jsonify({"error": "property_address is required"}), 400

    def _compute():
        leases = database.get_all_effective_leases()
        return compute_property_trends(leases, property_address)

    trends = cache.get_or_compute(f"trends:property:{property_address}", _compute)
    if trends is None:
        return jsonify({"error": "property_address did not normalize to a usable address"}), 400
    return jsonify(trends), 200


@app.route('/portfolio/trends', methods=['GET'])
@require_role()
def portfolio_trends_route():
    """
    The portfolio-wide sibling of GET /portfolio/property-trends --
    every distinct building's trends in ONE response, plus portfolio-
    level tenant-turnover and rollover-pattern totals. See
    compute_portfolio_trends's own docstring for why this exists: it
    replaces what used to require the caller fetching property-trends
    once per building and merging the results itself (real,
    documented behavior the frontend's trends view was doing before
    this endpoint existed -- an O(number of properties) fan-out of
    separate requests just to render the default "All Properties"
    view). 200 with an honest all-zero result for an empty portfolio,
    not an error.

    Cached (see app/cache.py) -- invalidated whenever a lease mutates,
    60s TTL as a safety net regardless.
    """
    result = cache.get_or_compute("trends:portfolio", lambda: compute_portfolio_trends(database.get_all_effective_leases()))
    return jsonify(result), 200


@app.route('/portfolio/rent-roll-reconciliation', methods=['GET'])
@require_role()
def portfolio_rent_roll_reconciliation():
    """Cross-checks an imported rent roll (see /leases/import-rent-roll) against the actual lease PDFs on file for the same units, flagging tenant/rent/end-date disagreements. See compute_rent_roll_reconciliation."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    result = compute_rent_roll_reconciliation(leases)
    result["mismatches"] = sync_rent_roll_reconciliation(result["mismatches"])
    return jsonify(result), 200


@app.route('/portfolio/rent-roll-ai-validation', methods=['POST'])
@require_role('analyst')
def portfolio_rent_roll_ai_validation():
    """
    Model-backed rent-roll validation: for every unit where an imported
    rent-roll row and an abstracted lease document both exist, ask the
    model to cross-check the two and flag disagreements with a severity
    (high/medium/low) and a plain explanation -- catching what the
    arithmetic /portfolio/rent-roll-reconciliation can't (gross-vs-base
    rent, DBA-vs-legal-entity, a rent roll expiration that predates a
    renewal, ...).

    Only runs against lease documents that have actually been
    abstracted -- a unit whose lease PDF hasn't been (still processing,
    or extraction failed) is reported as skipped, not compared against
    empty data, and never errors.

    Persists each flagged disagreement to the discrepancies list
    (type "rent_roll_ai_validation") using the model's severity, so it
    shows up in the Discrepancies view alongside every other check.
    """
    if ai_extraction.resolve_engine() != "ai":
        return jsonify({"error": "AI validation is not enabled. Set LEASE_AI_EXTRACTION=true and configure an API key."}), 503

    leases = database.get_all_effective_leases()
    pairs = ai_rent_roll_validation.find_unit_pairs(leases)

    validated, skipped, all_discrepancies, failures = 0, 0, [], []
    for rent_roll_lease, lease_document, _address in pairs:
        try:
            result = ai_rent_roll_validation.validate_rent_roll_against_lease(rent_roll_lease, lease_document)
        except ai_extraction.AIExtractionError as e:
            failures.append({"rent_roll_lease_id": rent_roll_lease.get("id"),
                             "lease_document_id": lease_document.get("id"), "error": str(e)})
            continue
        if result["status"] == "not_abstracted":
            skipped += 1
            continue
        validated += 1
        all_discrepancies.extend(ai_rent_roll_validation.sync_validation_result(result))
        meta = result.get("_ai_meta") or {}
        database.record_ai_extraction_run(
            engine="ai", status="ok", model=meta.get("model"), kind="rent_roll_validation",
            lease_id=rent_roll_lease.get("id"), found_count=meta.get("discrepancy_count"),
            latency_ms=meta.get("latency_ms"), input_tokens=meta.get("input_tokens"),
            output_tokens=meta.get("output_tokens"),
        )

    if validated:
        _invalidate_discrepancy_derived_caches()

    return jsonify({
        "pairs_found": len(pairs),
        "validated": validated,
        "skipped_not_abstracted": skipped,
        "discrepancies": all_discrepancies,
        "failures": failures,
    }), 200


@app.route('/portfolio/t12-reconciliation', methods=['POST'])
@require_role('analyst')
def portfolio_t12_reconciliation():
    """
    Uploads a T12 (trailing 12-month operating statement) and cross-
    checks its actual rental income against the rent roll's own
    annualized rent for the same property. See t12_import.py for the
    parsing (always the ACTUAL collected-income line, never a "Gross
    Potential Rent"/market figure) and compute_t12_reconciliation in
    portfolio.py for the comparison itself.

    Expects multipart form data: 'file' (.csv or .xlsx) and a REQUIRED
    'property_address' field -- unlike rent roll import, there's no
    optional fallback here: a T12 covers exactly one property, and
    without knowing which one, there's nothing to compare it against.

    Stateless: the T12 is parsed and compared in this one request only,
    never persisted anywhere. A T12 doesn't represent a lease or
    tenant -- inserting it into the leases table the way a rent roll
    import does would corrupt tenant concentration, WALT, and every
    other per-lease computation with a fake non-lease row.

    A file-level problem (wrong extension, empty file, no recognizable
    way to compute an annual total, no recognizable actual-rental-
    income line) is a 400.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file_storage = request.files['file']
    if file_storage.filename == '':
        return jsonify({"error": "No file selected"}), 400

    property_address = (request.form.get('property_address') or '').strip()
    if not property_address:
        return jsonify({"error": "property_address is required -- a T12 covers one property, and without it there's nothing to compare against."}), 400

    filename = file_storage.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if extension not in ('csv', 'xlsx'):
        return jsonify({"error": "Invalid file type. Only .csv and .xlsx T12 statements are supported."}), 400

    file_bytes = file_storage.read()

    try:
        if extension == 'csv':
            parsed = parse_csv_t12(file_bytes, filename)
        else:
            parsed = parse_xlsx_t12(file_bytes, filename)
    except T12ImportError as e:
        return jsonify({"error": str(e)}), 400

    leases = database.get_all_effective_leases()
    result = compute_t12_reconciliation(leases, property_address, parsed["annual_rental_income"])
    result["t12_source"] = parsed["source"]
    result = sync_t12_reconciliation(result)
    return jsonify(result), 200


@app.route('/portfolio/reconciliation/run', methods=['POST'])
@require_role('analyst')
def run_reconciliation():
    """
    The Discrepancies page's "Run reconciliation" button -- an explicit,
    on-demand re-check of rent-roll-vs-lease-PDF mismatches and lease
    risk flags/cross-lease mismatches against current data (see
    _run_reconciliation_sweep's own docstring for exactly what it does
    and does NOT cover -- T12 reconciliation needs a fresh file upload,
    not a re-run). The same sweep also fires automatically after a rent
    roll import; this is for every other reason data might have changed
    since the last check (a lease PDF re-upload, an amendment, or just
    "it's been a month, check again").

    @require_role('analyst') because, like /discrepancies/<id>/resolve,
    this can create/update persisted discrepancy rows -- not a pure
    read, even though nothing here is destructive.
    """
    result = _run_reconciliation_sweep()
    database.insert_activity(
        "reconciliation_run",
        f"Reconciliation run: {result['leases_checked']} lease(s) checked, "
        f"{result['rent_roll_mismatches']} rent roll mismatch(es), {result['new_alerts']} new alert(s).",
    )
    return jsonify(result), 200


@app.route('/activity', methods=['GET'])
@require_role()
def recent_activity():
    """GET /activity?limit=10 — most recent account activity first."""
    limit = request.args.get('limit', default=10, type=int) or 10
    return jsonify(database.get_recent_activity(limit)), 200


@app.route('/portfolio/risks', methods=['GET'])
@require_role()
def portfolio_risks():
    """Risk flags for every lease in the portfolio, most-flagged-first isn't imposed here — callers sort/filter as needed."""
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    context = portfolio_context_for_risk_analysis(leases)
    cross_lease_mismatches = compute_cross_lease_mismatches(leases)

    per_lease_flags = []
    results = []
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        cross_lease_flags = cross_lease_mismatches.get(lease["id"], [])
        flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates, cross_lease_flags)
        per_lease_flags.append((lease["id"], flags))
        results.append({
            "lease_id": lease["id"],
            "filename": lease["filename"],
            "tenant": (lease["extracted_fields"].get("tenant") or {}).get("value"),
            "flags": flags,
        })
    # Bulk sync (one shared connection, one commit, batched status/
    # resolution reads) instead of sync_lease_risk_flags per lease --
    # see sync_all_lease_risk_flags_bulk's docstring. Mutates every
    # flag dict in `results` in place, same as the per-lease version.
    sync_all_lease_risk_flags_bulk(per_lease_flags)
    return jsonify(results), 200


@app.route('/portfolio/obligations', methods=['GET'])
@require_role()
def portfolio_obligations():
    """
    Every forward-looking, date-computed obligation across the whole
    portfolio, in one prioritized (soonest-due-first) list -- renewal
    notice deadlines, early-termination notice deadlines, rent-
    escalation trigger dates, and insurance-requirement obligations
    (present but not date-computable, never a guessed date). See
    app/obligations.py's own module docstring for exactly which
    obligation types this does and does not cover, and why.

    Computed live on every call (same as /portfolio/risks), not
    persisted -- an obligation is fully derived from the lease's own
    extracted fields, so a cached snapshot would go stale the moment a
    field is corrected.
    """
    leases = cache.get_or_compute("effective_leases", database.get_all_effective_leases)
    return jsonify(obligations_module.compute_portfolio_obligations(leases)), 200


@app.route('/leases/<int:lease_id>/risks', methods=['GET'])
@require_role()
def lease_risks(lease_id):
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    flags = _lease_risks(lease)
    return jsonify(flags), 200


def _discrepancy_detail(discrepancy):
    detail = dict(discrepancy)
    detail["resolutions"] = database.get_discrepancy_resolutions(discrepancy["id"])
    # "Flagged before, resolved as X" context from OTHER discrepancy
    # rows on this same lease/category/field -- see get_prior_
    # resolutions_for_lease's own docstring for why this can't just be
    # this row's own resolutions (a fresh rent-roll import creates a
    # brand-new row with no history of its own). Only fetched for a
    # single detail view, never in the bulk list -- see that function's
    # docstring on why.
    detail["prior_history"] = database.get_prior_resolutions_for_lease(
        discrepancy.get("lease_id"), discrepancy["category"], discrepancy.get("field"), discrepancy["id"],
    )
    return detail


def _activity_lease_id(lease_id):
    """
    activity_log.lease_id has a real FK to leases(id) -- a discrepancy's
    own lease_id can outlive the lease it once pointed at (a discrepancy
    is a permanent record; deleting a lease does not delete or
    renumber the discrepancies that referenced it), so it can't be
    passed straight through without checking the lease still exists.
    """
    return lease_id if lease_id is not None and database.get_lease(lease_id) else None


def _current_user_discrepancies_last_viewed_at():
    """
    None means either there's no session, or this user has never viewed
    the Discrepancies page through this feature -- both treated the
    same way by callers: "everything currently open counts as new."
    """
    user = current_user()
    if not user:
        return None
    row = database.get_user(user["id"])
    return row.get("discrepancies_last_viewed_at") if row else None


@app.route('/discrepancies', methods=['GET'])
@require_role()
def list_discrepancies():
    """
    GET /discrepancies?status=open|resolved&lease_id=N&type=lease_risk_flag|cross_lease_mismatch|rent_roll_reconciliation|t12_reconciliation

    Every filter is optional and may be combined. A discrepancy only
    exists here once it's been produced by one of the flag-computing
    routes at least once (/portfolio/risks, /leases/<id>/risks,
    /portfolio/rent-roll-reconciliation, /portfolio/t12-reconciliation)
    -- this endpoint lists what's already been persisted, it doesn't
    trigger a fresh computation of its own.

    Each row carries `is_new`: whether it was first detected after the
    CALLING user's own discrepancies_last_viewed_at (see
    POST /discrepancies/mark-viewed) -- per-user, since different team
    members open this page on different days. Purely a read; viewing
    this list does NOT itself advance that timestamp, so a badge stays
    visible until the frontend explicitly marks it seen.
    """
    status = request.args.get('status')
    if status and status not in ('open', 'resolved'):
        return jsonify({"error": "status must be 'open' or 'resolved'"}), 400

    lease_id = request.args.get('lease_id', type=int)
    discrepancy_type = request.args.get('type')

    discrepancies = database.list_discrepancies(status=status, lease_id=lease_id, discrepancy_type=discrepancy_type)
    last_viewed_at = _current_user_discrepancies_last_viewed_at()
    for d in discrepancies:
        d["is_new"] = last_viewed_at is None or d["first_detected_at"] > last_viewed_at
    return jsonify(discrepancies), 200


@app.route('/discrepancies/summary', methods=['GET'])
@require_role()
def discrepancies_summary():
    """
    Counts by status/severity/type across every discrepancy -- the
    header-stat digest a "Discrepancies" sidebar tab needs (how many
    total, how many still open, the severity/type breakdown) without
    fetching and counting the full list client-side, the same role
    GET /alerts/summary already plays for the Alerts tab. Same scope
    as GET /discrepancies itself (every discrepancy ever recorded), so
    this digest can never disagree with what that list returns -- see
    database.get_discrepancy_summary's own docstring.

    Also includes `new_since_last_view`: how many currently-OPEN
    discrepancies were first detected after the calling user last
    viewed this page -- the "3 new issues" count a user coming back
    after a month should see without re-scanning the whole list. Purely
    a read, same as the rest of this endpoint -- see
    POST /discrepancies/mark-viewed for what actually advances it.
    """
    summary = database.get_discrepancy_summary()
    last_viewed_at = _current_user_discrepancies_last_viewed_at()
    open_discrepancies = database.list_discrepancies(status="open")
    summary["new_since_last_view"] = (
        len(open_discrepancies) if last_viewed_at is None
        else sum(1 for d in open_discrepancies if d["first_detected_at"] > last_viewed_at)
    )
    return jsonify(summary), 200


@app.route('/discrepancies/mark-viewed', methods=['POST'])
@require_role()
def mark_discrepancies_viewed():
    """
    Stamps the calling user's discrepancies_last_viewed_at to now --
    called by the frontend right after it's read/rendered the current
    `is_new` state, so the "new" badge naturally clears going forward
    (this is a plain per-user bookkeeping action, not a change to any
    discrepancy itself, hence @require_role() rather than 'analyst').
    """
    user = current_user()
    database.set_discrepancies_last_viewed(user["id"], datetime.now(timezone.utc).isoformat())
    return jsonify({"status": "ok"}), 200


@app.route('/discrepancies/patterns', methods=['GET'])
@require_role()
def discrepancies_patterns():
    """
    GET /discrepancies/patterns?min_lease_count=3 (default 3) -- the
    same TYPE of discrepancy recurring across several leases, surfaced
    as one portfolio-level insight instead of N separate line items.
    See detect_discrepancy_patterns's own docstring.
    """
    min_lease_count = request.args.get('min_lease_count', type=int) or DEFAULT_PATTERN_MIN_LEASE_COUNT
    return jsonify(detect_discrepancy_patterns(min_lease_count=min_lease_count)), 200


@app.route('/discrepancies/<int:discrepancy_id>', methods=['GET'])
@require_role()
def get_discrepancy(discrepancy_id):
    discrepancy = database.get_discrepancy(discrepancy_id)
    if not discrepancy:
        return jsonify({"error": "Discrepancy not found"}), 404
    return jsonify(_discrepancy_detail(discrepancy)), 200


@app.route('/discrepancies/<int:discrepancy_id>/resolve', methods=['POST'])
@require_role('analyst')
def resolve_discrepancy(discrepancy_id):
    """
    Body: {"correct_source": "...", "note": "..."}

    Resolving is always allowed regardless of current status -- a
    second reviewer confirming, or updating the note, appends another
    permanent entry to the resolution log rather than being rejected.
    `correct_source`/`note` are free text: which of the two disagreeing
    values is correct, and why. Who resolved it is always the
    logged-in session user now (see current_user()), never a
    request-body field the caller could put any name into.
    """
    if not database.get_discrepancy(discrepancy_id):
        return jsonify({"error": "Discrepancy not found"}), 404

    payload = request.get_json(silent=True) or {}
    correct_source = (payload.get('correct_source') or '').strip()
    note = (payload.get('note') or '').strip()

    missing = [field for field, value in (('correct_source', correct_source), ('note', note)) if not value]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400

    user = current_user()
    resolved_by, resolved_by_email = user["name"], user["email"]
    resolution = database.resolve_discrepancy(discrepancy_id, correct_source, note, resolved_by, resolved_by_email)
    _invalidate_discrepancy_derived_caches()
    discrepancy = database.get_discrepancy(discrepancy_id)
    database.insert_activity(
        "discrepancy_resolved",
        f"Discrepancy #{discrepancy_id} ({discrepancy['category']}) resolved by {resolved_by}: {note}",
        lease_id=_activity_lease_id(discrepancy.get("lease_id")),
    )
    return jsonify(_discrepancy_detail(discrepancy) | {"latest_resolution": resolution}), 200


@app.route('/discrepancies/<int:discrepancy_id>/reopen', methods=['POST'])
@require_role('analyst')
def reopen_discrepancy(discrepancy_id):
    """Body: {"note": "..."}. Only valid on a currently-resolved discrepancy. Who reopened it is always the logged-in session user."""
    discrepancy = database.get_discrepancy(discrepancy_id)
    if not discrepancy:
        return jsonify({"error": "Discrepancy not found"}), 404
    if discrepancy["status"] != "resolved":
        return jsonify({"error": "Only a resolved discrepancy can be reopened"}), 400

    payload = request.get_json(silent=True) or {}
    note = (payload.get('note') or '').strip()
    if not note:
        return jsonify({"error": "Missing required field: note"}), 400

    user = current_user()
    resolved_by, resolved_by_email = user["name"], user["email"]
    resolution = database.reopen_discrepancy(discrepancy_id, note, resolved_by, resolved_by_email)
    _invalidate_discrepancy_derived_caches()
    discrepancy = database.get_discrepancy(discrepancy_id)
    database.insert_activity(
        "discrepancy_reopened",
        f"Discrepancy #{discrepancy_id} ({discrepancy['category']}) reopened by {resolved_by}: {note}",
        lease_id=_activity_lease_id(discrepancy.get("lease_id")),
    )
    return jsonify(_discrepancy_detail(discrepancy) | {"latest_resolution": resolution}), 200


@app.route('/discrepancies/bulk-resolve', methods=['POST'])
@require_role('analyst')
def bulk_resolve_discrepancies():
    """
    Body: {"ids": [1, 2, 3], "correct_source": "...", "note": "..."}

    Same resolution reasoning applied to every id in the list -- the
    toolbar's "resolve selected" action, for when a batch of
    discrepancies share the same real-world explanation (e.g. a whole
    rent roll import used a stale source file). ids that don't exist
    are reported back individually rather than failing the whole
    batch, since a stale selection (something else already deleted
    one of them) shouldn't block resolving the rest.
    """
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    correct_source = (payload.get('correct_source') or '').strip()
    note = (payload.get('note') or '').strip()

    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "Provide a non-empty 'ids' list of integers"}), 400
    missing = [field for field, value in (('correct_source', correct_source), ('note', note)) if not value]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400

    user = current_user()
    resolved, not_found = [], []
    for discrepancy_id in ids:
        if not database.get_discrepancy(discrepancy_id):
            not_found.append(discrepancy_id)
            continue
        database.resolve_discrepancy(discrepancy_id, correct_source, note, user["name"], user["email"])
        discrepancy = database.get_discrepancy(discrepancy_id)
        database.insert_activity(
            "discrepancy_resolved",
            f"Discrepancy #{discrepancy_id} ({discrepancy['category']}) resolved by {user['name']} (bulk): {note}",
            lease_id=_activity_lease_id(discrepancy.get("lease_id")),
        )
        resolved.append(discrepancy_id)
    _invalidate_discrepancy_derived_caches()
    return jsonify({"resolved": resolved, "not_found": not_found}), 200


@app.route('/discrepancies/export.csv', methods=['GET'])
@require_role()
def export_discrepancies_csv():
    """GET /discrepancies/export.csv?status=open|resolved&lease_id=N&type=... -- same filters as GET /discrepancies, exported as a flat CSV for the toolbar's export action."""
    status = request.args.get('status')
    if status and status not in ('open', 'resolved'):
        return jsonify({"error": "status must be 'open' or 'resolved'"}), 400
    lease_id = request.args.get('lease_id', type=int)
    discrepancy_type = request.args.get('type')
    rows = database.list_discrepancies(status=status, lease_id=lease_id, discrepancy_type=discrepancy_type)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "type", "category", "field", "severity", "status", "lease_id", "message", "first_detected_at", "last_seen_at"])
    for r in rows:
        writer.writerow([r["id"], r["discrepancy_type"], r["category"], r.get("field") or "", r.get("severity") or "", r["status"], r.get("lease_id") or "", r["message"], r["first_detected_at"], r["last_seen_at"]])
    database.insert_activity("discrepancies_exported", f"Exported {len(rows)} discrepancy(ies) as CSV")
    return Response(buf.getvalue(), mimetype='text/csv', headers={"Content-Disposition": "attachment; filename=discrepancies.csv"})


@app.route('/discrepancies/<int:discrepancy_id>/comments', methods=['GET'])
@require_role()
def list_discrepancy_comments(discrepancy_id):
    """Team notes on this discrepancy, oldest first -- separate from its resolution log (discrepancy_resolutions): a comment is a running discussion, a resolution is the final "here's which source is correct and why" decision."""
    if not database.get_discrepancy(discrepancy_id):
        return jsonify({"error": "Discrepancy not found"}), 404
    return jsonify(database.get_discrepancy_comments(discrepancy_id)), 200


@app.route('/discrepancies/<int:discrepancy_id>/comments', methods=['POST'])
@require_role('analyst')
def add_discrepancy_comment(discrepancy_id):
    """Body: {"body": "..."}. The comment's author is always the logged-in session user -- see _validate_comment_payload."""
    if not database.get_discrepancy(discrepancy_id):
        return jsonify({"error": "Discrepancy not found"}), 404

    payload = request.get_json(silent=True) or {}
    body, error = _validate_comment_payload(payload)
    if error:
        return error

    user = current_user()
    database.add_comment(user["name"], body, discrepancy_id=discrepancy_id, author_email=user["email"])
    return jsonify(database.get_discrepancy_comments(discrepancy_id)), 201


@app.route('/comments/recent', methods=['GET'])
@require_role()
def recent_comments():
    """
    GET /comments/recent?limit=20 (default 20, max 200). The most
    recent comments across BOTH leases and discrepancies in one feed --
    what a standalone "Team Notes" sidebar tab needs, which neither
    GET /leases/<id>/comments nor GET /discrepancies/<id>/comments
    (each scoped to one target) can answer alone. Each entry carries
    enough denormalized context (the lease's display name, or the
    discrepancy's category) to render without a follow-up request per
    comment -- see database.get_recent_comments.
    """
    limit = request.args.get('limit', default=20, type=int) or 20
    return jsonify(database.get_recent_comments(limit)), 200


@app.route('/alerts/generate', methods=['POST'])
@require_role('analyst')
def alerts_generate():
    """
    Runs all four alert detectors (lease expirations, new discrepancies,
    below-market rent, tenant concentration) against the current
    portfolio state and persists the results -- see app/alerts.py's
    generate_alerts for exactly what "persists" means for an already-
    dismissed or already-auto-resolved alert. Idempotent: re-running
    against unchanged data creates nothing new. No request body.
    Intended to be called on a schedule (a cron job, eventually) or
    manually -- email delivery of these alerts is explicitly out of
    scope for this pass, see DECISIONS.md.
    """
    return jsonify(generate_alerts()), 200


@app.route('/alerts', methods=['GET'])
@require_role()
def list_alerts_route():
    """GET /alerts?status=active|dismissed|auto_resolved&type=lease_expiration|new_discrepancy|below_market_rent|tenant_concentration&severity=high|medium|low&lease_id=N. Every filter optional and combinable. Lists what's already been persisted -- does not itself trigger a fresh generation pass."""
    status = request.args.get('status')
    if status and status not in ('active', 'dismissed', 'auto_resolved'):
        return jsonify({"error": "status must be 'active', 'dismissed', or 'auto_resolved'"}), 400
    severity = request.args.get('severity')
    if severity and severity not in ('high', 'medium', 'low'):
        return jsonify({"error": "severity must be 'high', 'medium', or 'low'"}), 400

    alert_type = request.args.get('type')
    lease_id = request.args.get('lease_id', type=int)
    return jsonify(database.list_alerts(status=status, alert_type=alert_type, severity=severity, lease_id=lease_id)), 200


@app.route('/alerts/summary', methods=['GET'])
@require_role()
def alerts_summary():
    """A digest suitable for a notification-feed header or a future email digest: active-alert counts by severity and by type. Reflects whatever was persisted as of the last /alerts/generate run, not a fresh computation."""
    return jsonify(get_alert_digest()), 200


@app.route('/alerts/<int:alert_id>', methods=['GET'])
@require_role()
def get_alert_route(alert_id):
    alert = database.get_alert(alert_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    return jsonify(alert), 200


@app.route('/alerts/<int:alert_id>/dismiss', methods=['POST'])
@require_role('analyst')
def dismiss_alert_route(alert_id):
    """
    Body: {"note": "..." (optional)}. Always allowed regardless of
    current status. Who dismissed it is always the logged-in session
    user now, never a request-body field the caller could put any name
    into.
    """
    if not database.get_alert(alert_id):
        return jsonify({"error": "Alert not found"}), 404

    payload = request.get_json(silent=True) or {}
    note = (payload.get('note') or '').strip() or None
    dismissed_by = current_user()["name"]

    database.dismiss_alert(alert_id, dismissed_by, note)
    return jsonify(database.get_alert(alert_id)), 200


@app.route('/alerts/bulk-dismiss', methods=['POST'])
@require_role('analyst')
def bulk_dismiss_alerts():
    """Body: {"ids": [1, 2, 3], "note": "..." (optional)}. The toolbar's "dismiss selected" action. ids that don't exist are reported back individually rather than failing the whole batch."""
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    note = (payload.get('note') or '').strip() or None
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "Provide a non-empty 'ids' list of integers"}), 400

    dismissed_by = current_user()["name"]
    dismissed, not_found = [], []
    for alert_id in ids:
        if not database.get_alert(alert_id):
            not_found.append(alert_id)
            continue
        database.dismiss_alert(alert_id, dismissed_by, note)
        dismissed.append(alert_id)
    return jsonify({"dismissed": dismissed, "not_found": not_found}), 200


@app.route('/alerts/export.csv', methods=['GET'])
@require_role()
def export_alerts_csv():
    """GET /alerts/export.csv?status=active|dismissed|auto_resolved&type=...&severity=...&lease_id=N -- same filters as GET /alerts, exported as a flat CSV for the toolbar's export action."""
    status = request.args.get('status')
    if status and status not in ('active', 'dismissed', 'auto_resolved'):
        return jsonify({"error": "status must be 'active', 'dismissed', or 'auto_resolved'"}), 400
    severity = request.args.get('severity')
    if severity and severity not in ('high', 'medium', 'low'):
        return jsonify({"error": "severity must be 'high', 'medium', or 'low'"}), 400
    alert_type = request.args.get('type')
    lease_id = request.args.get('lease_id', type=int)
    rows = database.list_alerts(status=status, alert_type=alert_type, severity=severity, lease_id=lease_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "type", "severity", "status", "lease_id", "title", "message", "dismissed_by", "dismissed_at", "first_detected_at", "last_seen_at"])
    for r in rows:
        writer.writerow([r["id"], r["alert_type"], r["severity"], r["status"], r.get("lease_id") or "", r["title"], r["message"], r.get("dismissed_by") or "", r.get("dismissed_at") or "", r["first_detected_at"], r["last_seen_at"]])
    database.insert_activity("alerts_exported", f"Exported {len(rows)} alert(s) as CSV")
    return Response(buf.getvalue(), mimetype='text/csv', headers={"Content-Disposition": "attachment; filename=alerts.csv"})


@app.route('/qa', methods=['POST'])
@require_role()
def ask_question():
    """
    Body: {"question": str, "lease_id": int (optional)}.
    If lease_id is given, the question is scoped to that one lease
    (the lease-detail "ask about this lease" UI); otherwise it's
    answered against the whole portfolio.
    """
    body = request.get_json(silent=True) or {}
    question = body.get("question")
    if not question or not isinstance(question, str):
        return jsonify({"error": "Request body must include a non-empty 'question' string"}), 400

    lease_id = body.get("lease_id")
    if lease_id is not None:
        lease = database.get_effective_lease(lease_id)
        if not lease:
            return jsonify({"error": "Lease not found"}), 404
        leases = [lease]
    else:
        leases = database.get_all_effective_leases()

    result = answer_question(question, leases)
    return jsonify(result), 200


@app.route('/leases/compare', methods=['GET'])
@require_role()
def leases_compare():
    """GET /leases/compare?ids=1,2,3"""
    ids_param = request.args.get('ids', '')
    try:
        ids = [int(i) for i in ids_param.split(',') if i.strip()]
    except ValueError:
        return jsonify({"error": "ids must be a comma-separated list of integers"}), 400

    if len(ids) < 2:
        return jsonify({"error": "Provide at least 2 lease ids to compare (e.g. ?ids=1,2)"}), 400

    leases = []
    for lease_id in ids:
        lease = database.get_effective_lease(lease_id)
        if not lease:
            return jsonify({"error": f"Lease {lease_id} not found"}), 404
        leases.append(lease)

    database.insert_activity("comparison_run", f"Compared {len(leases)} leases")
    return jsonify(compare_leases(leases)), 200


@app.route('/leases/selection-summary', methods=['GET'])
@require_role()
def leases_selection_summary():
    """
    GET /leases/selection-summary?ids=1,2,3

    Rollup totals/averages for an arbitrary subset of leases -- the
    dashboard's checkbox selection, not the whole portfolio. Reuses
    compute_portfolio_metrics (the same function behind the portfolio-
    wide dashboard tiles) rather than a separate summing routine, so a
    3-lease selection's total rent can't disagree with what the
    portfolio-wide total would be if all 3 were the entire portfolio --
    one definition of "how these numbers get summed," same reasoning as
    portfolio_context_for_risk_analysis above.

    Unlike /leases/compare, 1 id is allowed (a single-lease selection
    still has a meaningful sum -- it's just that lease's own numbers)
    and this doesn't log an activity entry, since selecting leases to
    glance at a running total is a routine, high-frequency browsing
    action, not a distinct user action worth an audit trail entry the
    way running a full comparison is.
    """
    ids_param = request.args.get('ids', '')
    try:
        ids = [int(i) for i in ids_param.split(',') if i.strip()]
    except ValueError:
        return jsonify({"error": "ids must be a comma-separated list of integers"}), 400

    if not ids:
        return jsonify({"error": "Provide at least 1 lease id (e.g. ?ids=1,2)"}), 400

    leases = []
    for lease_id in ids:
        lease = database.get_effective_lease(lease_id)
        if not lease:
            return jsonify({"error": f"Lease {lease_id} not found"}), 404
        leases.append(lease)

    return jsonify(compute_portfolio_metrics(leases)), 200


@app.route('/leases/<int:lease_id>/benchmark', methods=['GET'])
@require_role()
def lease_benchmark(lease_id):
    """Benchmarks one lease against every OTHER lease in the portfolio (this lease excluded from its own comparison average)."""
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    other_leases = [l for l in database.get_all_effective_leases() if l["id"] != lease_id]
    if not other_leases:
        return jsonify({"error": "No other leases in the portfolio to benchmark against yet"}), 400

    return jsonify(benchmark_lease(lease, other_leases)), 200


@app.route('/portfolio/rent-roll.csv', methods=['GET'])
@require_role()
def rent_roll_csv():
    leases = database.get_all_effective_leases()
    csv_text = generate_rent_roll_csv(leases)
    database.insert_activity("rent_roll_exported", f"Exported rent roll as CSV ({len(leases)} leases)")
    return Response(
        csv_text,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment; filename=rent_roll.csv"},
    )


@app.route('/portfolio/rent-roll.xlsx', methods=['GET'])
@require_role()
def rent_roll_excel():
    leases = database.get_all_effective_leases()
    excel_bytes = generate_rent_roll_excel(leases)
    database.insert_activity("rent_roll_exported", f"Exported rent roll as Excel ({len(leases)} leases)")
    return Response(
        excel_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": "attachment; filename=rent_roll.xlsx"},
    )


@app.route('/portfolio/export/google-sheets', methods=['POST'])
@require_role('analyst')
def portfolio_export_google_sheets():
    """
    Creates a brand-new Google Sheet with the current lease dataset and
    returns a link to it. Requires GOOGLE_APPLICATION_CREDENTIALS to be
    configured (see backend/.env.example) — SheetsExportError's message
    is always safe to return directly to the client (see its docstring
    in sheets_export.py); any other exception falls through to the
    global error handler like everywhere else in this file.
    """
    leases = database.get_all_effective_leases()
    try:
        result = export_to_google_sheets(leases)
    except SheetsExportError as e:
        return jsonify({"error": str(e)}), 502

    database.insert_activity(
        "google_sheets_exported",
        f"Exported {len(leases)} lease(s) to Google Sheets",
    )
    return jsonify(result), 200


@app.route('/leases/<int:lease_id>/export.xlsx', methods=['GET'])
@require_role()
def lease_export_excel(lease_id):
    """Same formatted workbook as the portfolio-wide export, scoped to one lease (a single data row)."""
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    excel_bytes = generate_rent_roll_excel([lease])
    display_name = lease.get("display_name") or lease.get("filename") or f"lease_{lease_id}"
    database.insert_activity("rent_roll_exported", f"Exported {display_name} as Excel")
    safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', display_name)
    return Response(
        excel_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f"attachment; filename={safe_name}.xlsx"},
    )


@app.route('/leases/<int:lease_id>/summary.pdf', methods=['GET'])
@require_role()
def lease_summary_pdf(lease_id):
    """
    Decision-ready one-page PDF memo for a single lease: key terms,
    confidence summary, and risk flags (including any cross-lease
    mismatches) -- meant to be forwarded to someone who will never open
    the app. See summary_memo.py.
    """
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    flags = _lease_risks(lease)
    pdf_bytes = generate_lease_summary_pdf(lease, flags)
    display_name = lease.get("display_name") or lease.get("filename") or f"lease_{lease_id}"
    database.insert_activity("summary_memo_exported", f"Exported {display_name} as a summary memo")
    safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', display_name)
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={"Content-Disposition": f"attachment; filename={safe_name}_summary.pdf"},
    )


def _parse_investment_memo_request():
    """
    Shared by both investment-memo export routes. POST (not GET) because
    a T12 file may be attached. `property_address` is optional --
    omitted means a whole-portfolio memo; a T12 file is only usable
    (and only accepted) alongside a property_address, since a T12
    covers exactly one building. Returns (property_address, t12_parsed,
    error_response) -- error_response is None on success.
    """
    property_address = (request.form.get('property_address') or '').strip() or None

    file_storage = request.files.get('t12_file')
    if file_storage is None or file_storage.filename == '':
        return property_address, None, None

    if not property_address:
        return None, None, (jsonify({"error": "t12_file requires property_address -- a T12 covers exactly one property."}), 400)

    filename = file_storage.filename
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if extension not in ('csv', 'xlsx'):
        return None, None, (jsonify({"error": "Invalid t12_file type. Only .csv and .xlsx T12 statements are supported."}), 400)

    file_bytes = file_storage.read()
    try:
        parsed = parse_csv_t12(file_bytes, filename) if extension == 'csv' else parse_xlsx_t12(file_bytes, filename)
    except T12ImportError as e:
        return None, None, (jsonify({"error": str(e)}), 400)

    return property_address, parsed, None


@app.route('/portfolio/investment-memo.pdf', methods=['POST'])
@require_role('analyst')
def investment_memo_pdf():
    """
    A clean, professional PDF suitable for an investment committee,
    lender, or partner -- key lease terms, flagged discrepancies AND
    their resolutions, a T12 cross-check summary, and a rollover risk
    summary. See app/investment_memo.py for the full design.

    Optional multipart form fields: 'property_address' (omit for a
    whole-portfolio memo), 't12_file' (.csv/.xlsx -- only usable
    alongside property_address; without one, the T12 section falls
    back to the last persisted T12 cross-check on file for that
    property, if any).
    """
    property_address, t12_parsed, error = _parse_investment_memo_request()
    if error:
        return error

    data = build_investment_memo_data(property_address=property_address, t12_parsed=t12_parsed)
    pdf_bytes = generate_investment_memo_pdf(data)

    scope_label = property_address or "portfolio"
    database.insert_activity("investment_memo_exported", f"Exported investment memo (PDF) for {scope_label}")
    safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', scope_label)
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={"Content-Disposition": f"attachment; filename=investment_memo_{safe_name}.pdf"},
    )


@app.route('/portfolio/investment-memo.xlsx', methods=['POST'])
@require_role('analyst')
def investment_memo_excel():
    """Same data and scope rules as POST /portfolio/investment-memo.pdf, rendered as a multi-sheet workbook instead."""
    property_address, t12_parsed, error = _parse_investment_memo_request()
    if error:
        return error

    data = build_investment_memo_data(property_address=property_address, t12_parsed=t12_parsed)
    excel_bytes = generate_investment_memo_excel(data)

    scope_label = property_address or "portfolio"
    database.insert_activity("investment_memo_exported", f"Exported investment memo (Excel) for {scope_label}")
    safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', scope_label)
    return Response(
        excel_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f"attachment; filename=investment_memo_{safe_name}.xlsx"},
    )


@app.route('/leases/<int:lease_id>/export/google-sheets', methods=['POST'])
@require_role('analyst')
def lease_export_google_sheets(lease_id):
    """Same Google Sheets export as the portfolio-wide one, scoped to one lease (a single data row)."""
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404

    try:
        result = export_to_google_sheets([lease])
    except SheetsExportError as e:
        return jsonify({"error": str(e)}), 502

    display_name = lease.get("display_name") or lease.get("filename") or f"lease_{lease_id}"
    database.insert_activity(
        "google_sheets_exported",
        f"Exported {display_name} to Google Sheets",
    )
    return jsonify(result), 200


def _leases_for_ids(ids):
    """Fetches each id's effective (amendment-merged) lease record, or returns a (response, status) error tuple for the first id not found -- same shape callers already check for from other route helpers in this file."""
    leases = []
    for lease_id in ids:
        lease = database.get_effective_lease(lease_id)
        if not lease:
            return None, (jsonify({"error": f"Lease {lease_id} not found"}), 404)
        leases.append(lease)
    return leases, None


@app.route('/leases/export.xlsx', methods=['GET'])
@require_role()
def leases_bulk_export_excel():
    """
    GET /leases/export.xlsx?ids=1,2,3

    Same formatted workbook (with its Portfolio Summary tab) as the
    portfolio-wide and single-lease exports, scoped to an arbitrary
    selection -- the dashboard's checkbox multi-select, not "all
    leases" and not just one. Same ids-parsing convention as
    /leases/selection-summary.
    """
    ids_param = request.args.get('ids', '')
    try:
        ids = [int(i) for i in ids_param.split(',') if i.strip()]
    except ValueError:
        return jsonify({"error": "ids must be a comma-separated list of integers"}), 400
    if not ids:
        return jsonify({"error": "Provide at least 1 lease id (e.g. ?ids=1,2)"}), 400

    leases, error = _leases_for_ids(ids)
    if error:
        return error

    excel_bytes = generate_rent_roll_excel(leases)
    database.insert_activity("rent_roll_exported", f"Exported {len(leases)} selected lease(s) as Excel")
    return Response(
        excel_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": "attachment; filename=selected_leases.xlsx"},
    )


@app.route('/leases/export/google-sheets', methods=['POST'])
@require_role('analyst')
def leases_bulk_export_google_sheets():
    """Body: {"ids": [1, 2, 3]}. Same Google Sheets export as the portfolio-wide and single-lease routes, scoped to an arbitrary selection."""
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({"error": "Provide a non-empty 'ids' list of integers"}), 400

    leases, error = _leases_for_ids(ids)
    if error:
        return error

    try:
        result = export_to_google_sheets(leases)
    except SheetsExportError as e:
        return jsonify({"error": str(e)}), 502

    database.insert_activity(
        "google_sheets_exported",
        f"Exported {len(leases)} selected lease(s) to Google Sheets",
    )
    return jsonify(result), 200


@app.route('/portfolio/report', methods=['GET'])
@require_role()
def portfolio_report():
    """
    Returns the printable portfolio summary as an HTML page (rendered
    directly, not downloaded, so the frontend can preview it before
    printing/saving).

    Deliberately does NOT log an activity_log entry: report-view.js
    calls this on every visit to the Report view (to refresh the
    preview), not only when the user actually intends to produce a
    report — logging here would mean switching tabs back and forth
    floods "Recent Activity" with noise. The rent-roll CSV/Excel
    endpoints below are real export actions with no such view-load
    trigger, so those do log.
    """
    leases = database.get_all_effective_leases()
    metrics = compute_portfolio_metrics(leases)
    timeline = compute_expiration_timeline(leases)
    context = portfolio_context_for_risk_analysis(leases)
    cross_lease_mismatches = compute_cross_lease_mismatches(leases)

    all_risks = []
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        cross_lease_flags = cross_lease_mismatches.get(lease["id"], [])
        flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates, cross_lease_flags)
        if flags:
            all_risks.append({
                "lease_id": lease["id"],
                "filename": lease["filename"],
                "tenant": (lease["extracted_fields"].get("tenant") or {}).get("value"),
                "flags": flags,
            })

    html = generate_portfolio_report_html(leases, metrics, timeline, all_risks)
    return Response(html, mimetype='text/html')


@app.route('/portfolio/summary.pdf', methods=['GET'])
@require_role()
def portfolio_summary_pdf():
    """
    Decision-ready one-page PDF memo for the whole portfolio: a rollup
    table, the portfolio-wide confidence summary, and the
    highest-severity risk flags across every lease. See summary_memo.py.
    """
    leases = database.get_all_effective_leases()
    context = portfolio_context_for_risk_analysis(leases)
    cross_lease_mismatches = compute_cross_lease_mismatches(leases)
    confidence_summary = compute_portfolio_confidence_summary(leases)

    risks_by_lease = {}
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        cross_lease_flags = cross_lease_mismatches.get(lease["id"], [])
        risks_by_lease[lease["id"]] = analyze_lease_risks(
            lease["extracted_fields"], context, date_candidates, cross_lease_flags,
        )

    pdf_bytes = generate_portfolio_summary_pdf(leases, confidence_summary, risks_by_lease)
    database.insert_activity("summary_memo_exported", f"Exported portfolio summary memo ({len(leases)} leases)")
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={"Content-Disposition": "attachment; filename=portfolio_summary.pdf"},
    )


@app.route('/portfolio/monthly-report.pdf', methods=['GET'])
@require_role()
def portfolio_monthly_report_pdf():
    """
    The monthly portfolio report -- same PDF memo format as
    /portfolio/summary.pdf, with three additional sections: leases
    expiring in the next 90 days, rent-per-sqft outliers in either
    direction, and an explicit "not available" for loss-to-lease (see
    monthly_report_extra_sections' docstring for why that one can't be
    computed from data this tool captures today).

    Manually triggered for now, by design (see Part 3 of the request
    this was built against) -- there is no scheduling infrastructure
    yet. To make this a real monthly automation later: add a scheduled
    job (APScheduler running in-process, a cron entry calling a small
    script that imports and calls the same generate_portfolio_summary_
    pdf()/monthly_report_extra_sections() functions this route calls,
    or a cloud provider's scheduled-function trigger hitting this exact
    route on a timer) and decide where the output goes each run --
    emailed via email_service.py's existing Gmail SMTP setup, or
    written to a dated file in storage. The generation logic itself
    (this route's body) would not need to change; only what triggers it
    and what happens to the resulting bytes.
    """
    leases = database.get_all_effective_leases()
    context = portfolio_context_for_risk_analysis(leases)
    cross_lease_mismatches = compute_cross_lease_mismatches(leases)
    confidence_summary = compute_portfolio_confidence_summary(leases)

    risks_by_lease = {}
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        cross_lease_flags = cross_lease_mismatches.get(lease["id"], [])
        risks_by_lease[lease["id"]] = analyze_lease_risks(
            lease["extracted_fields"], context, date_candidates, cross_lease_flags,
        )

    expiring_90_days = compute_expiration_alerts(leases)["expiring"]
    rent_variance_outliers = compute_rent_variance_outliers(leases)
    extra_sections = monthly_report_extra_sections(expiring_90_days, rent_variance_outliers)

    pdf_bytes = generate_portfolio_summary_pdf(
        leases, confidence_summary, risks_by_lease,
        extra_sections=extra_sections, title="Portfolio Monthly Report",
    )
    database.insert_activity("monthly_report_exported", f"Generated monthly portfolio report ({len(leases)} leases)")
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={"Content-Disposition": "attachment; filename=portfolio_monthly_report.pdf"},
    )


# ----------------------------------------------------------------------
# Owner console -- business management, NOT team/app management.
# Every route below is gated by @require_owner(), never
# @require_role('admin') -- role='admin' does not imply owner access,
# by deliberate design (see app/auth.py's require_owner docstring and
# DECISIONS.md's "Owner console" entry). There is no route anywhere
# that grants is_owner -- see backend/set_owner.py.
#
# "Accounts" here means logins in the `users` table, not isolated
# per-customer tenants -- this app has no multi-tenant data separation
# today (confirmed: no org_id/tenant_id/customer_id anywhere in the
# schema). Every login currently shares the exact same pool of leases
# and rent rolls. Usage stats are therefore per-login activity counts
# (tasks, field edits, discrepancy resolutions, comments -- see
# database.get_user_usage_stats), NOT "leases abstracted by this
# customer" -- the `leases` table has no uploaded-by column at all, so
# that specific number genuinely isn't tracked anywhere in this schema
# and is not fabricated here.
# ----------------------------------------------------------------------

def _owner_account_public_shape(account):
    """Strips password_hash before this row ever reaches a response -- an owner needing to reset a login's password uses /owner/accounts/<id>/reset-password (which writes a fresh hash), never has a reason to see the existing one, and putting a bcrypt hash in a JSON response/browser devtools/screen-share is needless exposure regardless of who's looking at it."""
    return {k: v for k, v in account.items() if k != "password_hash"}


@app.route('/owner/accounts', methods=['GET'])
@require_owner()
def owner_list_accounts():
    """
    ?email=<substring, case-insensitive>&status=active|deactivated&signup_after=YYYY-MM-DD&signup_before=YYYY-MM-DD
    All filters optional and combinable. Each account includes usage
    stats (see database.get_user_usage_stats) -- see this section's
    module comment above for exactly what that does and doesn't cover.
    """
    email_filter = (request.args.get("email") or "").strip().lower()
    status_filter = (request.args.get("status") or "").strip().lower()
    signup_after = (request.args.get("signup_after") or "").strip()
    signup_before = (request.args.get("signup_before") or "").strip()

    accounts = database.list_users()

    if email_filter:
        accounts = [a for a in accounts if email_filter in a["email"].lower()]
    if status_filter:
        accounts = [a for a in accounts if a["status"] == status_filter]
    if signup_after:
        accounts = [a for a in accounts if a["created_at"] >= signup_after]
    if signup_before:
        accounts = [a for a in accounts if a["created_at"] <= signup_before]

    usage_by_user = database.get_usage_stats_for_users(accounts)
    result = [
        {**_owner_account_public_shape(account), "usage": usage_by_user.get(account["id"], {})}
        for account in accounts
    ]
    return jsonify(result), 200


@app.route('/owner/accounts/<int:user_id>', methods=['GET'])
@require_owner()
def owner_account_detail(user_id):
    account = database.get_user(user_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    usage = database.get_user_usage_stats(account["id"], account["email"])
    return jsonify({**_owner_account_public_shape(account), "usage": usage}), 200


@app.route('/owner/accounts/<int:user_id>/suspend', methods=['POST'])
@require_owner()
def owner_suspend_account(user_id):
    """Reuses database.update_user_status -- the same function the (much more limited) Team view's admin-facing deactivate action already uses; owner access just isn't restricted to team members."""
    if not database.get_user(user_id):
        return jsonify({"error": "Account not found"}), 404
    database.update_user_status(user_id, "deactivated")
    return jsonify({"status": "suspended"}), 200


@app.route('/owner/accounts/<int:user_id>/reactivate', methods=['POST'])
@require_owner()
def owner_reactivate_account(user_id):
    if not database.get_user(user_id):
        return jsonify({"error": "Account not found"}), 404
    database.update_user_status(user_id, "active")
    return jsonify({"status": "activated"}), 200


@app.route('/owner/accounts/<int:user_id>/reset-password', methods=['POST'])
@require_owner()
def owner_reset_account_password(user_id):
    """
    Body: {"new_password": str}. Distinct from the self-serve
    /auth/forgot-password flow -- the owner needs unilateral power to
    reset ANY login's password directly, without that login's
    cooperation or a working email inbox. Same hashing
    (app.auth.hash_password) as every other password write path.
    """
    if not database.get_user(user_id):
        return jsonify({"error": "Account not found"}), 404
    body = request.get_json(silent=True) or {}
    new_password = body.get("new_password") or ""
    if not new_password or len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400
    database.update_user_password(user_id, hash_password(new_password))
    return jsonify({"status": "password_updated"}), 200


@app.route('/owner/revenue', methods=['GET', 'POST'])
@require_owner()
def owner_revenue():
    if request.method == 'GET':
        return jsonify(database.list_revenue_entries()), 200

    body = request.get_json(silent=True) or {}
    entry_date = (body.get("date") or "").strip()
    amount = body.get("amount")
    source = (body.get("source") or "").strip()
    note = (body.get("note") or "").strip() or None

    if not entry_date:
        return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400
    if not isinstance(amount, (int, float)):
        return jsonify({"error": "amount is required and must be a number"}), 400
    if not source:
        return jsonify({"error": "source is required"}), 400

    entry = database.create_revenue_entry(entry_date, float(amount), source, note, current_user()["id"])
    return jsonify(entry), 201


@app.route('/owner/revenue/<int:entry_id>', methods=['DELETE'])
@require_owner()
def owner_delete_revenue(entry_id):
    if not database.delete_revenue_entry(entry_id):
        return jsonify({"error": "Revenue entry not found"}), 404
    return jsonify({"status": "deleted"}), 200


@app.route('/owner/expenses', methods=['GET', 'POST'])
@require_owner()
def owner_expenses():
    if request.method == 'GET':
        return jsonify(database.list_expense_entries()), 200

    body = request.get_json(silent=True) or {}
    entry_date = (body.get("date") or "").strip()
    amount = body.get("amount")
    category = (body.get("category") or "").strip()
    note = (body.get("note") or "").strip() or None

    if not entry_date:
        return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400
    if not isinstance(amount, (int, float)):
        return jsonify({"error": "amount is required and must be a number"}), 400
    if not category:
        return jsonify({"error": "category is required"}), 400

    entry = database.create_expense_entry(entry_date, float(amount), category, note, current_user()["id"])
    return jsonify(entry), 201


@app.route('/owner/expenses/<int:entry_id>', methods=['DELETE'])
@require_owner()
def owner_delete_expense(entry_id):
    if not database.delete_expense_entry(entry_id):
        return jsonify({"error": "Expense entry not found"}), 404
    return jsonify({"status": "deleted"}), 200


@app.route('/owner/finance/summary', methods=['GET'])
@require_owner()
def owner_finance_summary():
    """Totals + a monthly trend (YYYY-MM buckets) covering both revenue and expenses. Computed here from the same list functions the /owner/revenue and /owner/expenses GET routes use, rather than a separate SQL aggregate, so there's exactly one source of truth for what counts as a valid entry."""
    revenue = database.list_revenue_entries()
    expenses = database.list_expense_entries()

    total_revenue = sum(r["amount"] for r in revenue)
    total_expenses = sum(e["amount"] for e in expenses)

    monthly = {}
    for r in revenue:
        month = r["entry_date"][:7]
        monthly.setdefault(month, {"revenue": 0.0, "expenses": 0.0})
        monthly[month]["revenue"] += r["amount"]
    for e in expenses:
        month = e["entry_date"][:7]
        monthly.setdefault(month, {"revenue": 0.0, "expenses": 0.0})
        monthly[month]["expenses"] += e["amount"]

    trend = [
        {"month": month, "revenue": vals["revenue"], "expenses": vals["expenses"], "profit": vals["revenue"] - vals["expenses"]}
        for month, vals in sorted(monthly.items())
    ]

    return jsonify({
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "profit": total_revenue - total_expenses,
        "monthly_trend": trend,
    }), 200


@app.route('/owner/analytics/summary', methods=['GET'])
@require_owner()
def owner_analytics_summary():
    """
    GET /owner/analytics/summary?days=30 -- pageview totals, top paths,
    top referrers, a daily trend for the given window, and the landing
    -> pricing -> waitlist-submitted funnel, all from the public
    marketing site (see database.get_pageview_summary and frontend/
    landing.js, which is what actually sends these). Owner-only, same
    guard as /owner/finance/summary -- this is business telemetry, not
    something every team member needs visibility into.
    """
    days = request.args.get('days', default=30, type=int) or 30
    return jsonify(database.get_pageview_summary(days=days)), 200


@app.route('/extraction-quality/trend', methods=['GET'])
@require_owner()
def extraction_quality_trend():
    """
    Owner console: how AI extraction quality has moved over time. The
    training-round trend (accuracy, high-confidence-wrong count,
    confidence calibration, and what changed each round -- from
    tools/training_harness.py) plus live production signal from
    ai_extraction_runs (daily volume, error rate, latency, confidence
    mix). Lets you tell if quality is drifting on real user documents,
    not just read a one-time report.
    """
    return jsonify(extraction_quality.compute_quality_trend(
        training_rounds=database.list_training_rounds(),
        ai_runs=database.list_ai_extraction_runs(limit=10000, kind="lease_abstraction"),
    )), 200


@app.route('/extraction-quality/field-reliability', methods=['GET'])
@require_role()
def extraction_quality_field_reliability():
    """
    Per field type: how much to trust it, from the latest training
    round's per-field accuracy and how often humans have corrected that
    field on real AI-extracted leases. The lease detail view uses this
    to tag historically-weak fields with a "double-check by eye" hint,
    so a reviewer knows where to look even before opening the source.
    """
    rounds = database.list_training_rounds()
    latest_report = rounds[-1]["report"] if rounds else None
    runs = database.list_ai_extraction_runs(limit=10000, kind="lease_abstraction")
    ai_lease_ids = {r["lease_id"] for r in runs if r.get("lease_id")}
    ai_leases = [l for l in database.get_all_leases(include_superseded=True) if l["id"] in ai_lease_ids]

    reliability = extraction_quality.compute_field_reliability(
        latest_training_report=latest_report,
        ai_extracted_leases=ai_leases,
        field_edits=database.get_lease_field_edits(),
    )
    return jsonify({
        "fields": reliability,
        "based_on_training_round": rounds[-1]["round_label"] if rounds else None,
        "ai_extracted_lease_count": len(ai_leases),
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check for Render (render.yaml healthCheckPath). Verifies the
    process is up AND that the database is actually reachable and
    writable-path-openable with a trivial query -- a broken disk / locked
    DB / bad DB_PATH should fail the health check so Render doesn't route
    traffic to (or keep) a dyno that can't serve real requests. Returns
    503 with {"status": "degraded", "database": "unavailable"} on a DB
    error, 200 {"status": "healthy"} otherwise. Never touches auth,
    never logs (it's hit constantly).
    """
    try:
        conn = database.get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception as e:
        logger.error("Health check DB probe failed: %s", e)
        return jsonify({"status": "degraded", "database": "unavailable"}), 503
    return jsonify({"status": "healthy"}), 200


@app.route('/config', methods=['GET'])
def get_config():
    """Public, read-only flags the frontend needs before it can decide how
    to render — currently just local_dev_mode, which lets /app's access
    gate (frontend/app/access-gate.js) know whether to skip itself. Keep
    this endpoint to flags that are safe for anyone to read; never put a
    secret or anything env-specific-but-sensitive here."""
    return jsonify({"local_dev_mode": LOCAL_DEV_MODE}), 200


@app.route('/demo/reset', methods=['POST'])
def demo_reset():
    """
    Wipes the demo database back to its clean seeded state. Demo-
    deployment only (404s everywhere else) and requires the
    X-Demo-Reset-Token header to match DEMO_RESET_TOKEN -- deliberately
    not session/role-gated, since the point is to be triggerable with a
    single curl command with no login step. See DEPLOYMENT.md.
    """
    if os.environ.get('DEMO_MODE', '').strip().lower() != 'true':
        return jsonify({"error": "not found"}), 404

    expected_token = os.environ.get('DEMO_RESET_TOKEN', '')
    provided_token = request.headers.get('X-Demo-Reset-Token', '')
    if not expected_token or not secrets.compare_digest(provided_token, expected_token):
        return jsonify({"error": "unauthorized"}), 401

    from app.demo_seed import reset_demo_data
    reset_demo_data()
    return jsonify({"status": "reset"}), 200


if __name__ == '__main__':
    # Run Flask development server
    # Note: For production, use a proper WSGI server like gunicorn
    #
    # debug=True (Werkzeug's interactive debugger + auto-reload) is
    # opt-in via FLASK_DEBUG, not the default — the debugger shows full
    # tracebacks, source code, and file paths for any unhandled
    # exception, which is invaluable when developing locally but must
    # never be on for anything reachable by anyone else. The
    # errorhandlers registered above return clean generic JSON errors
    # either way, so turning this on for local debugging doesn't bring
    # back the stack-trace leak this hardening pass closed — it only
    # adds the debugger AS WELL AS the JSON handlers, for exceptions
    # Flask decides to route to the debugger instead of a handler.
    debug_mode = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
