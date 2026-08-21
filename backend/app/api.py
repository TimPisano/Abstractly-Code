"""
Flask API for the lease abstraction / portfolio intelligence tool.

Three layers of endpoints:
  - Stateless single-document extraction (/extract) — unchanged from
    earlier sessions, for quick one-off use that doesn't need to persist
    anything.
  - Persisted leases (/leases, /leases/batch, amendments) — upload PDFs,
    store their extraction results (and amendments) in SQLite.
  - Portfolio analysis (/portfolio/*, /leases/<id>/risks, /qa,
    /leases/compare, /leases/<id>/benchmark) — everything downstream of
    persisted leases: metrics, timeline, risk flags, grounded Q&A,
    comparison/benchmarking, rent roll export, and the printable report.
    These are thin wiring around the analysis modules (risk_analysis.py,
    qa_engine.py, portfolio.py, comparison.py, rent_roll_export.py,
    report.py) — the actual logic lives there, not here.
"""

from flask import Flask, request, jsonify, Response, session
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import timedelta
import logging
import os
import re
import secrets
import tempfile
import time

# Loads backend/.env (if present) into os.environ before anything below
# reads an env var from it — real deployments can just set real
# environment variables instead, load_dotenv() is a silent no-op if
# there's no .env file to find. Must run before email_service is used
# (it reads EMAIL_USER/EMAIL_APP_PASSWORD from os.environ), so this
# happens before that import.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import PyPDF2
from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor
from app import database
from app import email_service
from app.risk_analysis import analyze_lease_risks
from app.qa_engine import answer_question
from app.portfolio import (
    compute_portfolio_metrics,
    compute_expiration_timeline,
    compute_attention_items,
    compute_expiration_alerts,
    compute_portfolio_health,
    compute_cross_lease_mismatches,
    compute_lease_confidence_summary,
    compute_portfolio_confidence_summary,
    compute_rent_variance_outliers,
    portfolio_context_for_risk_analysis,
)
from app.comparison import compare_leases, benchmark_lease
from app.rent_roll_export import generate_rent_roll_csv, generate_rent_roll_excel
from app.report import generate_portfolio_report_html
from app.summary_memo import generate_lease_summary_pdf, generate_portfolio_summary_pdf, monthly_report_extra_sections
from app.sheets_export import export_to_google_sheets, SheetsExportError
from app.auth import verify_admin_credentials, admin_login_is_configured, require_admin


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

# Signs the admin session cookie -- if FLASK_SECRET_KEY isn't set, a
# random key is generated for this process only, logged as a warning
# (every admin session is invalidated on the next restart, but nothing
# about this is silently insecure; a fresh random key each start is
# strictly safer than any hardcoded fallback would be). Set a real,
# stable FLASK_SECRET_KEY in backend/.env to keep admin sessions alive
# across restarts -- see .env.example for how to generate one.
_flask_secret_key = os.environ.get("FLASK_SECRET_KEY", "").strip()
if not _flask_secret_key:
    _flask_secret_key = secrets.token_hex(32)
    logging.getLogger(__name__).warning(
        "FLASK_SECRET_KEY is not set -- generated a random one for this process only. "
        "Admin login sessions will not survive a backend restart until you set a real, "
        "stable value in backend/.env (see .env.example)."
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
ALLOWED_EXTENSIONS = {'pdf'}

# Local-only bypass for the /app access gate (see frontend/app/access-gate.js).
# Read once at process start from backend/.env (or a real env var in any
# other environment) — never from a request, so a client can't set this
# itself. Defaults to False/off, so any environment that doesn't
# explicitly set it (including a real deployment) gets the real gate.
LOCAL_DEV_MODE = os.environ.get('LOCAL_DEV_MODE', '').strip().lower() in ('1', 'true', 'yes')

logger = logging.getLogger(__name__)

database.init_db()


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


def _extract_leases_from_file_storage(file_storage):
    """
    Shared pipeline: save an uploaded werkzeug FileStorage to a temp
    path, run PDF text extraction, then FieldExtractor.
    extract_multiple_leases() to split it into one or more per-lease
    results — a genuine single-lease PDF always comes back as exactly
    one result (same fields/confidence/citations extract_fields() alone
    would have produced), so this replaced the old single-lease-only
    _extract_fields_from_file_storage without changing behavior for the
    common case. A real multi-lease PDF instead comes back as N
    independent results, each extracted only from its own page range —
    see DECISIONS.md for why that matters (fields and risk-relevant
    date candidates used to bleed across the constituent leases).

    Returns (leases, None) on success, where `leases` is a non-empty
    list of dicts: {"fields": {...}, "date_candidates": {...},
    "source_page_start": N, "source_page_end": M, "display_name": "..."}
    — or (None, (error_message, http_status)) on failure. Callers turn
    the error into a JSON response themselves, since batch endpoints
    need to report a per-file error without aborting the whole request.
    """
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_path = temp_file.name
            file_storage.save(temp_path)

        # Checked before extraction, not left to surface as a generic
        # "corrupted or unsupported" failure: a password-protected PDF
        # is structurally fine and has a specific, actionable fix (open
        # it, remove the password, re-upload) that a vague corruption
        # message would hide. PyPDF2.is_encrypted is true even for a
        # PDF with only an *owner* password (no password needed to
        # open/read it) -- decrypt("") succeeds for those, and only
        # genuinely unreadable-without-a-real-password files fail here.
        with open(temp_path, 'rb') as pdf_file:
            try:
                reader = PyPDF2.PdfReader(pdf_file)
                if reader.is_encrypted and reader.decrypt("") == 0:
                    return None, (
                        "This PDF is password-protected. Remove the password (or save an "
                        "unprotected copy) and upload it again.", 422,
                    )
            except Exception:
                # Not our concern here -- extract_text() below runs its
                # own extraction attempt and OCR fallback, and reports
                # its own failure if the file turns out to be
                # unreadable for some other reason.
                pass

        pdf_extractor = PDFExtractor()
        with open(temp_path, 'rb') as pdf_file:
            pages = pdf_extractor.extract_text(pdf_file, pdf_path=temp_path)

        if not pages or len(pages) == 0:
            return None, ("Failed to extract text from PDF. The file may be corrupted or unsupported.", 500)

        field_extractor = FieldExtractor()
        split_results = field_extractor.extract_multiple_leases(pages)

        total = len(split_results)
        leases = []
        for index, result in enumerate(split_results):
            leases.append({
                "fields": result["fields"],
                "date_candidates": result["date_candidates"],
                "source_page_start": result["source_page_start"],
                "source_page_end": result["source_page_end"],
                "display_name": _default_lease_name(result["fields"], file_storage.filename, index, total),
                "looks_like_lease": _looks_like_lease(result["fields"]),
            })
        return leases, None

    except Exception:
        # The real exception (which can include the temp file's path,
        # e.g. a FileNotFoundError) is logged server-side only — the
        # client gets a generic message, never str(e) verbatim.
        logger.exception("Error processing uploaded PDF")
        return None, ("Error processing PDF. The file may be corrupted or unsupported.", 500)

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
        return None, (jsonify({"error": "Invalid file type. Only PDF files are allowed."}), 400)

    return file, None


# ----------------------------------------------------------------------
# Stateless single-document extraction (no persistence)
# ----------------------------------------------------------------------

@app.route('/extract', methods=['POST'])
def extract_lease_data():
    """
    Extract lease data from an uploaded PDF without persisting it.

    Expects: multipart form data with a 'file' field containing a PDF.
    Returns: {"leases": [{"display_name":..., "source_page_start":...,
    "source_page_end":..., "fields": {one entry per extracted field,
    each shaped as {"value":..., "source": {"page":N, "quote":"..."} |
    null, "confidence": "high"|"medium"|"low"|null}}}, ...]} — always a
    list, even for a single-lease PDF (a list of one), so a caller never
    needs two different response shapes depending on whether the file
    turned out to contain more than one lease.
    Error responses: 400 (no/invalid file), 500 (extraction failure).
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
    return {
        "id": lease["id"],
        "filename": lease["filename"],
        "display_name": lease.get("display_name") or lease["filename"],
        "uploaded_at": lease["uploaded_at"],
        "document_type": lease["document_type"],
        "base_lease_id": lease["base_lease_id"],
        "amendment_count": lease.get("amendment_count", 0),
        "extracted_fields": lease["extracted_fields"],
        "looks_like_lease": _looks_like_lease(lease["extracted_fields"]),
        "confidence_summary": compute_lease_confidence_summary(lease),
        "source_page_start": lease.get("source_page_start"),
        "source_page_end": lease.get("source_page_end"),
        "tags": lease.get("tags", []),
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
        )
        lease = database.get_effective_lease(lease_id)
        lease["tags"] = []
        created.append(_lease_summary(lease))
    return created


@app.route('/leases', methods=['POST'])
def upload_lease():
    """
    Upload a single PDF, extract its fields, and persist it as one or
    more base leases — one PER LEASE actually found in the file (see
    FieldExtractor.extract_multiple_leases). An ordinary single-lease
    PDF still produces exactly one lease, same as before.
    """
    file, error = _validate_upload()
    if error:
        return error

    filename = file.filename
    split_leases, error = _extract_leases_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    created = _persist_split_leases(filename, split_leases)
    if len(created) == 1:
        database.insert_activity("lease_uploaded", f"Uploaded {filename}", lease_id=created[0]["id"])
    else:
        database.insert_activity("lease_split", f"Split {filename} into {len(created)} separate leases")

    return jsonify({"leases": created, "split_count": len(created)}), 201


@app.route('/leases/batch', methods=['POST'])
def upload_leases_batch():
    """
    Upload multiple PDFs in one request. Each file is processed
    independently — if one fails (corrupted, wrong type, extraction
    error), the rest still process. Any file that turns out to bundle
    more than one lease is split into its own leases, same as
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
            results.append({"filename": filename or "(unnamed)", "success": False,
                             "error": "Invalid file type. Only PDF files are allowed."})
            continue

        split_leases, error = _extract_leases_from_file_storage(file_storage)
        if error:
            message, _status = error
            results.append({"filename": filename, "success": False, "error": message})
            continue

        created = _persist_split_leases(filename, split_leases)
        results.append({"filename": filename, "success": True, "leases": created, "split_count": len(created)})

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

    return jsonify({
        "total": len(results),
        "succeeded": succeeded_files,
        "failed": len(results) - succeeded_files,
        "total_leases_created": total_leases_created,
        "results": results,
    }), 200


@app.route('/leases', methods=['GET'])
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
def get_lease_detail(lease_id):
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    lease["tags"] = database.get_lease_tags(lease_id)
    return jsonify(_lease_summary(lease)), 200


@app.route('/leases/<int:lease_id>', methods=['DELETE'])
def delete_lease(lease_id):
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    database.delete_lease(lease_id)
    # Logged with lease_id=None (not lease_id) since the row this would
    # reference no longer exists once delete_lease() returns.
    database.insert_activity("lease_deleted", f"Deleted {lease['filename']}")
    return jsonify({"deleted": lease_id}), 200


@app.route('/leases/bulk-delete', methods=['POST'])
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

    deleted = []
    not_found = []
    for lease_id in ids:
        lease = database.get_lease(lease_id)
        if not lease:
            not_found.append(lease_id)
            continue
        database.delete_lease(lease_id)
        database.insert_activity("lease_deleted", f"Deleted {lease['filename']}")
        deleted.append(lease_id)

    return jsonify({"deleted": deleted, "not_found": not_found}), 200


@app.route('/leases/<int:lease_id>/amendments', methods=['POST'])
def upload_amendment(lease_id):
    """Upload a PDF (amendment/addendum) and link it to an existing base lease."""
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
    database.insert_lease(
        filename, amendment_data["fields"], document_type="amendment", base_lease_id=lease_id,
        date_candidates=amendment_data["date_candidates"],
    )
    database.insert_activity("amendment_uploaded", f"Added amendment {filename} to {base_lease['filename']}", lease_id=lease_id)
    lease = database.get_effective_lease(lease_id)
    lease["tags"] = database.get_lease_tags(lease_id)
    return jsonify(_lease_summary(lease)), 201


@app.route('/leases/<int:lease_id>/amendments', methods=['GET'])
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
def list_lease_tags(lease_id):
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    return jsonify(database.get_lease_tags(lease_id)), 200


@app.route('/leases/<int:lease_id>/tags', methods=['POST'])
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
def remove_lease_tag_route(lease_id, tag):
    lease = database.get_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    database.remove_lease_tag(lease_id, tag)
    return jsonify(database.get_lease_tags(lease_id)), 200


@app.route('/tags', methods=['GET'])
def list_all_tags():
    """Every distinct tag currently in use across the whole portfolio — for filter dropdowns and tag-input autocomplete."""
    return jsonify(database.get_all_tags()), 200


@app.route('/leases/bulk-tag', methods=['POST'])
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

    tagged = []
    not_found = []
    for lease_id in ids:
        lease = database.get_lease(lease_id)
        if not lease:
            not_found.append(lease_id)
            continue
        database.add_lease_tag(lease_id, tag)
        tagged.append(lease_id)

    return jsonify({"tagged": tagged, "not_found": not_found}), 200


# ----------------------------------------------------------------------
# Admin authentication
#
# A single admin account, configured via ADMIN_EMAIL/ADMIN_PASSWORD_HASH
# in backend/.env (see app/auth.py and .env.example) -- not a users
# table, since there is exactly one admin account for now. Real
# password, real bcrypt check, backed by a signed session cookie (see
# the SESSION_COOKIE_* config and CORS setup near the top of this
# file). Deliberately separate from the client-facing access gate
# below (/waitlist/check) -- see app/auth.py's module docstring.
# ----------------------------------------------------------------------

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """
    Body: {"email": str, "password": str}. On success, starts an admin
    session (signed cookie, 12-hour lifetime) and returns {"email": ...}.
    On failure, always the same generic error regardless of whether the
    email or the password was wrong -- see verify_admin_credentials for
    why the check itself is also timing-safe about that, not just the
    message.
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""

    if not verify_admin_credentials(email, password):
        return jsonify({"error": "Invalid email or password"}), 401

    session.permanent = True
    session["admin_authenticated"] = True
    session["admin_email"] = email
    return jsonify({"email": email}), 200


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return jsonify({"status": "logged_out"}), 200


@app.route('/admin/session', methods=['GET'])
def admin_session():
    """Used by the admin login page and dashboard on load to check current auth state without triggering a 401 (this route itself is intentionally public -- it only ever reflects the caller's own session back to them)."""
    if session.get("admin_authenticated"):
        return jsonify({"authenticated": True, "email": session.get("admin_email")}), 200
    return jsonify({"authenticated": False, "email": None}), 200


# ----------------------------------------------------------------------
# Waitlist (landing page gate)
#
# /waitlist (GET), /waitlist/<id>/approve, and /waitlist/<id>/deny all
# require an authenticated admin session (see app/auth.py's
# require_admin) -- viewing every signup's email and granting/denying
# access is exactly the kind of privileged action that must sit behind
# real auth, not an unguessable-URL "don't share this link" convention.
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


@app.route('/waitlist', methods=['GET'])
@require_admin
def list_waitlist():
    """Admin-only. Lists every signup, newest first."""
    return jsonify(database.get_all_waitlist_signups()), 200


@app.route('/waitlist/<int:signup_id>/approve', methods=['POST'])
@require_admin
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
@require_admin
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
    return flags


@app.route('/portfolio/summary', methods=['GET'])
def portfolio_summary():
    leases = database.get_all_effective_leases()
    return jsonify(compute_portfolio_metrics(leases)), 200


@app.route('/portfolio/timeline', methods=['GET'])
def portfolio_timeline():
    leases = database.get_all_effective_leases()
    return jsonify(compute_expiration_timeline(leases)), 200


@app.route('/portfolio/attention', methods=['GET'])
def portfolio_attention():
    """'What needs attention today' — expiring soon, missing data, unusual terms. See compute_attention_items for the exact definitions."""
    leases = database.get_all_effective_leases()
    return jsonify(compute_attention_items(leases)), 200


@app.route('/portfolio/expiration-alerts', methods=['GET'])
def portfolio_expiration_alerts():
    """Dashboard widget data: leases expiring within 90/60/30 days, plus renewal-notice deadlines closing soon -- see compute_expiration_alerts for the exact windows and why the two lists are kept separate."""
    leases = database.get_all_effective_leases()
    return jsonify(compute_expiration_alerts(leases)), 200


@app.route('/portfolio/health', methods=['GET'])
def portfolio_health():
    """Morning-glance health strip: % verified, avg days to expiration, rent exposure expiring in 6/12 months."""
    leases = database.get_all_effective_leases()
    return jsonify(compute_portfolio_health(leases)), 200


@app.route('/portfolio/confidence-summary', methods=['GET'])
def portfolio_confidence_summary():
    """The trust-mechanism number: field counts by confidence tier across the whole portfolio, plus how many were flagged for review during validation. See compute_portfolio_confidence_summary."""
    leases = database.get_all_effective_leases()
    return jsonify(compute_portfolio_confidence_summary(leases)), 200


@app.route('/activity', methods=['GET'])
def recent_activity():
    """GET /activity?limit=10 — most recent account activity first."""
    limit = request.args.get('limit', default=10, type=int) or 10
    return jsonify(database.get_recent_activity(limit)), 200


@app.route('/portfolio/risks', methods=['GET'])
def portfolio_risks():
    """Risk flags for every lease in the portfolio, most-flagged-first isn't imposed here — callers sort/filter as needed."""
    leases = database.get_all_effective_leases()
    context = portfolio_context_for_risk_analysis(leases)
    cross_lease_mismatches = compute_cross_lease_mismatches(leases)

    results = []
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        cross_lease_flags = cross_lease_mismatches.get(lease["id"], [])
        flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates, cross_lease_flags)
        results.append({
            "lease_id": lease["id"],
            "filename": lease["filename"],
            "tenant": (lease["extracted_fields"].get("tenant") or {}).get("value"),
            "flags": flags,
        })
    return jsonify(results), 200


@app.route('/leases/<int:lease_id>/risks', methods=['GET'])
def lease_risks(lease_id):
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
    flags = _lease_risks(lease)
    return jsonify(flags), 200


@app.route('/qa', methods=['POST'])
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


@app.route('/leases/<int:lease_id>/export/google-sheets', methods=['POST'])
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


@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route('/config', methods=['GET'])
def get_config():
    """Public, read-only flags the frontend needs before it can decide how
    to render — currently just local_dev_mode, which lets /app's access
    gate (frontend/app/access-gate.js) know whether to skip itself. Keep
    this endpoint to flags that are safe for anyone to read; never put a
    secret or anything env-specific-but-sensitive here."""
    return jsonify({"local_dev_mode": LOCAL_DEV_MODE}), 200


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
