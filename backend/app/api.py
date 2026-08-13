"""
Flask API for the lease abstraction / portfolio intelligence tool.

Two layers of endpoints:
  - Stateless single-document extraction (/extract) — unchanged from
    earlier sessions, for quick one-off use that doesn't need to persist
    anything.
  - Persisted portfolio endpoints (/leases, /leases/batch, amendments,
    /portfolio/*, /qa, /leases/compare) — upload PDFs, store their
    extraction results in SQLite, and analyze them as a collection.
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import os
import tempfile

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor
from app import database


app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max file size
ALLOWED_EXTENSIONS = {'pdf'}

database.init_db()


def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _extract_fields_from_file_storage(file_storage):
    """
    Shared pipeline: save an uploaded werkzeug FileStorage to a temp path,
    run PDF text extraction + field extraction, clean up the temp file.

    Returns (extracted_fields, None) on success, or (None, (error_message,
    http_status)) on failure — callers turn that into a JSON error
    response themselves, since batch endpoints need to report a per-file
    error without aborting the whole request.
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
            return None, ("Failed to extract text from PDF. The file may be corrupted or unsupported.", 500)

        field_extractor = FieldExtractor()
        extracted_fields = field_extractor.extract_fields(pages)
        return extracted_fields, None

    except Exception as e:
        return None, (f"Error processing PDF: {str(e)}", 500)

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

    extracted_fields, error = _extract_fields_from_file_storage(file)
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
    extracted_fields, error = _extract_fields_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    lease_id = database.insert_lease(filename, extracted_fields, document_type="lease")
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

        extracted_fields, error = _extract_fields_from_file_storage(file_storage)
        if error:
            message, _status = error
            results.append({"filename": filename, "success": False, "error": message})
            continue

        lease_id = database.insert_lease(filename, extracted_fields, document_type="lease")
        lease = database.get_effective_lease(lease_id)
        results.append({"filename": filename, "success": True, "lease": _lease_summary(lease)})

    succeeded = sum(1 for r in results if r["success"])
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
    extracted_fields, error = _extract_fields_from_file_storage(file)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    amendment_id = database.insert_lease(filename, extracted_fields, document_type="amendment", base_lease_id=lease_id)
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


@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    # Run Flask development server
    # Note: For production, use a proper WSGI server like gunicorn
    app.run(debug=True, host='0.0.0.0', port=5000)
