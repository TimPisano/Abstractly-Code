"""
Flask API for lease PDF extraction.

Provides a single endpoint POST /extract that accepts a PDF file
and returns extracted lease fields in JSON format.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import tempfile

from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor


app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max file size
ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/extract', methods=['POST'])
def extract_lease_data():
    """
    Extract lease data from uploaded PDF file.

    Expects:
        - Multipart form data with 'file' field containing PDF

    Returns:
        JSON with extracted fields:
        {
            "tenant": {"value": "...", "source": {"page": N, "quote": "..."}},
            "rent_amount": {...},
            "lease_start_date": {...},
            "lease_end_date": {...}
        }

    Error responses:
        - 400: No file uploaded or invalid file type
        - 500: Server error during processing
    """
    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']

    # Check if filename is empty
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Check if file type is allowed
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Only PDF files are allowed."}), 400

    try:
        # Save uploaded file to temporary location
        # Note: We use a temp file because some libraries need file paths
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_path = temp_file.name
            file.save(temp_path)

        # Extract text from PDF
        pdf_extractor = PDFExtractor()
        with open(temp_path, 'rb') as pdf_file:
            pages = pdf_extractor.extract_text(pdf_file, pdf_path=temp_path)

        # Clean up temporary file
        os.unlink(temp_path)

        # Check if extraction was successful
        if not pages or len(pages) == 0:
            return jsonify({
                "error": "Failed to extract text from PDF. The file may be corrupted or unsupported."
            }), 500

        # Extract fields from text
        field_extractor = FieldExtractor()
        extracted_fields = field_extractor.extract_fields(pages)

        return jsonify(extracted_fields), 200

    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)

        # Return error response
        return jsonify({
            "error": f"Error processing PDF: {str(e)}"
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    # Run Flask development server
    # Note: For production, use a proper WSGI server like gunicorn
    app.run(debug=True, host='0.0.0.0', port=5000)
