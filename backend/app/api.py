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

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
import logging
import os
import re
import tempfile

# Loads backend/.env (if present) into os.environ before anything below
# reads an env var from it — real deployments can just set real
# environment variables instead, load_dotenv() is a silent no-op if
# there's no .env file to find. Must run before email_service is used
# (it reads EMAIL_USER/EMAIL_APP_PASSWORD from os.environ), so this
# happens before that import.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

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
    compute_portfolio_health,
    portfolio_context_for_risk_analysis,
)
from app.comparison import compare_leases, benchmark_lease
from app.rent_roll_export import generate_rent_roll_csv, generate_rent_roll_excel
from app.report import generate_portfolio_report_html


app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

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


def _extract_fields_from_file_storage(file_storage):
    """
    Shared pipeline: save an uploaded werkzeug FileStorage to a temp path,
    run PDF text extraction + field extraction, clean up the temp file.

    Also computes every start/end date candidate found in the document
    (FieldExtractor.find_all_date_candidates) so it can be persisted
    alongside the extracted fields — this is the only point where the
    raw PDF text is available; once the temp file is cleaned up,
    risk_analysis's cross-section date-conflict check would otherwise
    have nothing to work from for a lease loaded back out of storage.

    Returns (extracted_fields, date_candidates, None) on success, or
    (None, None, (error_message, http_status)) on failure — callers turn
    that into a JSON error response themselves, since batch endpoints
    need to report a per-file error without aborting the whole request.
    """
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_path = temp_file.name
            file_storage.save(temp_path)

        pdf_extractor = PDFExtractor()
        with open(temp_path, 'rb') as pdf_file:
            pages = pdf_extractor.extract_text(pdf_file, pdf_path=temp_path)

        if not pages or len(pages) == 0:
            return None, None, ("Failed to extract text from PDF. The file may be corrupted or unsupported.", 500)

        field_extractor = FieldExtractor()
        extracted_fields = field_extractor.extract_fields(pages)
        date_candidates = {
            "start": field_extractor.find_all_date_candidates(pages, "start"),
            "end": field_extractor.find_all_date_candidates(pages, "end"),
        }
        return extracted_fields, date_candidates, None

    except Exception:
        # The real exception (which can include the temp file's path,
        # e.g. a FileNotFoundError) is logged server-side only — the
        # client gets a generic message, never str(e) verbatim.
        logger.exception("Error processing uploaded PDF")
        return None, None, ("Error processing PDF. The file may be corrupted or unsupported.", 500)

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
    Returns: JSON with one entry per extracted field, each shaped as
        {"value": ..., "source": {"page": N, "quote": "..."} | null,
         "confidence": "high"|"medium"|"low" | null}
    Error responses: 400 (no/invalid file), 500 (extraction failure).
    """
    file, error = _validate_upload()
    if error:
        return error

    extracted_fields, _date_candidates, error = _extract_fields_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    return jsonify(extracted_fields), 200


# ----------------------------------------------------------------------
# Persisted leases (portfolio)
# ----------------------------------------------------------------------

def _lease_summary(lease):
    """Trim a DB lease record down to what list views need, keeping full extracted_fields (the dashboard needs most columns anyway)."""
    return {
        "id": lease["id"],
        "filename": lease["filename"],
        "uploaded_at": lease["uploaded_at"],
        "document_type": lease["document_type"],
        "base_lease_id": lease["base_lease_id"],
        "amendment_count": lease.get("amendment_count", 0),
        "extracted_fields": lease["extracted_fields"],
    }


@app.route('/leases', methods=['POST'])
def upload_lease():
    """Upload a single PDF, extract its fields, and persist it as a base lease."""
    file, error = _validate_upload()
    if error:
        return error

    filename = file.filename
    extracted_fields, date_candidates, error = _extract_fields_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    lease_id = database.insert_lease(filename, extracted_fields, document_type="lease", date_candidates=date_candidates)
    database.insert_activity("lease_uploaded", f"Uploaded {filename}", lease_id=lease_id)
    lease = database.get_effective_lease(lease_id)
    return jsonify(_lease_summary(lease)), 201


@app.route('/leases/batch', methods=['POST'])
def upload_leases_batch():
    """
    Upload multiple PDFs in one request. Each file is processed
    independently — if one fails (corrupted, wrong type, extraction
    error), the rest still process. Returns a per-file result list so
    the caller can see exactly what succeeded and what didn't.
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

        extracted_fields, date_candidates, error = _extract_fields_from_file_storage(file_storage)
        if error:
            message, _status = error
            results.append({"filename": filename, "success": False, "error": message})
            continue

        lease_id = database.insert_lease(filename, extracted_fields, document_type="lease", date_candidates=date_candidates)
        lease = database.get_effective_lease(lease_id)
        results.append({"filename": filename, "success": True, "lease": _lease_summary(lease)})

    succeeded = sum(1 for r in results if r["success"])
    # One summary entry for the whole batch rather than one per file — a
    # 20-file batch shouldn't push everything else out of a 10-item feed.
    if succeeded == 1:
        only = next(r for r in results if r["success"])
        database.insert_activity("lease_uploaded", f"Uploaded {only['filename']}", lease_id=only["lease"]["id"])
    elif succeeded > 1:
        database.insert_activity("batch_upload", f"Uploaded a batch of {succeeded} leases")
    return jsonify({
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }), 200


@app.route('/leases', methods=['GET'])
def list_leases():
    """List all base leases (not amendments), with amendment-merged effective field values."""
    leases = database.get_all_effective_leases()
    return jsonify([_lease_summary(l) for l in leases]), 200


@app.route('/leases/<int:lease_id>', methods=['GET'])
def get_lease_detail(lease_id):
    lease = database.get_effective_lease(lease_id)
    if not lease:
        return jsonify({"error": "Lease not found"}), 404
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
    extracted_fields, date_candidates, error = _extract_fields_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    database.insert_lease(filename, extracted_fields, document_type="amendment", base_lease_id=lease_id, date_candidates=date_candidates)
    database.insert_activity("amendment_uploaded", f"Added amendment {filename} to {base_lease['filename']}", lease_id=lease_id)
    lease = database.get_effective_lease(lease_id)
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


# ----------------------------------------------------------------------
# Waitlist (landing page gate)
#
# NOTE: /waitlist (GET) and /waitlist/<id>/approve are unauthenticated —
# anyone who finds the admin URL can view every signup email and approve
# accounts. This is acceptable for the current pre-launch stage (per
# explicit product decision) but MUST be locked down behind real auth
# before this goes live to real users.
#
# /waitlist/check (below) is DELIBERATELY public too, but that's a
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


@app.route('/waitlist', methods=['POST'])
def join_waitlist():
    """Body: {"email": str}. Adds the email to the waitlist as 'pending'."""
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
    # already committed to the database regardless of whether this
    # send succeeds.
    _send_email_best_effort(email_service.send_waitlist_confirmation_email, email)

    return jsonify({"message": "Your request has been received. If it's a fit, we'll be in touch."}), 201


@app.route('/waitlist', methods=['GET'])
def list_waitlist():
    """Admin-only (unauthenticated for now, see NOTE above). Lists every signup, newest first."""
    return jsonify(database.get_all_waitlist_signups()), 200


@app.route('/waitlist/<int:signup_id>/approve', methods=['POST'])
def approve_waitlist(signup_id):
    """Admin-only (unauthenticated for now, see NOTE above). Flips a signup's status to 'approved'."""
    signup = database.get_waitlist_signup(signup_id)
    if not signup:
        return jsonify({"error": "Signup not found"}), 404

    database.approve_waitlist_signup(signup_id)
    # Best-effort, same as the confirmation email above — never blocks
    # or fails this response.
    _send_email_best_effort(email_service.send_waitlist_approval_email, signup["email"])

    return jsonify({"id": signup_id, "status": "approved"}), 200


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
    """Risk flags for one effective lease, using its own stored date_candidates and the current portfolio average as context."""
    all_leases = database.get_all_effective_leases()
    context = portfolio_context_for_risk_analysis(all_leases)
    date_candidates = lease.get("date_candidates")
    flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates)
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


@app.route('/portfolio/health', methods=['GET'])
def portfolio_health():
    """Morning-glance health strip: % verified, avg days to expiration, rent exposure expiring in 6/12 months."""
    leases = database.get_all_effective_leases()
    return jsonify(compute_portfolio_health(leases)), 200


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

    results = []
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates)
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

    all_risks = []
    for lease in leases:
        date_candidates = lease.get("date_candidates")
        flags = analyze_lease_risks(lease["extracted_fields"], context, date_candidates)
        if flags:
            all_risks.append({
                "lease_id": lease["id"],
                "filename": lease["filename"],
                "tenant": (lease["extracted_fields"].get("tenant") or {}).get("value"),
                "flags": flags,
            })

    html = generate_portfolio_report_html(leases, metrics, timeline, all_risks)
    return Response(html, mimetype='text/html')


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
