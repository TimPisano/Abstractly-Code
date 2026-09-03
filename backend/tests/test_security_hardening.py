"""
Regression tests for the production-readiness hardening pass: error
responses must never leak a stack trace or internal file path to the
client, oversized/malformed uploads must fail cleanly (not crash or
return a raw framework HTML page), and extracted PDF content containing
HTML/script-like text must never execute when rendered.

Requires the live backend running at http://localhost:5000. These
specifically re-create the failures found and fixed during the
hardening pass (see DECISIONS.md) so they can't silently regress.
"""
import os
import sys
import json
import urllib.request
import urllib.error

import pypdf

API_BASE_URL = "http://localhost:5000"
FIXTURES_DIR = os.path.dirname(__file__)


def _request(method, path, data=None, headers=None):
    req = urllib.request.Request(f"{API_BASE_URL}{path}", data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "application/json" in content_type:
                return resp.status, json.loads(raw.decode()), content_type
            return resp.status, raw, content_type
    except urllib.error.HTTPError as e:
        raw = e.read()
        content_type = e.headers.get("Content-Type", "")
        try:
            return e.code, json.loads(raw.decode()), content_type
        except (json.JSONDecodeError, UnicodeDecodeError):
            return e.code, raw, content_type


def _multipart_body(files):
    boundary = "----SecurityTestBoundary"
    parts = []
    for field_name, filename, content in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _multipart_body_with_content_type(files):
    """Like _multipart_body, but each file carries its own Content-Type -- needed for the XXE checks below, which upload .xlsx/.docx rather than .pdf. (The server itself only ever dispatches on the filename's extension, never this header, but sending an honest one keeps the request realistic.)"""
    boundary = "----SecurityTestBoundaryCT"
    parts = []
    for field_name, filename, content, content_type in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _build_xxe_xlsx(secret_path: str) -> bytes:
    """
    A minimal, hand-built .xlsx (a plain zip -- openpyxl's own writer
    API won't let us inject raw malicious XML) whose sharedStrings.xml
    carries a classic XXE payload: a DOCTYPE declaring an external
    entity pointing at `secret_path`, referenced from a cell value. If
    openpyxl's XML parsing ever resolved external entities, the
    extracted "spreadsheet" text would contain that file's contents.
    """
    import io
    import zipfile

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>'''
    sheet1 = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>
</sheetData>
</worksheet>'''
    xxe_shared_strings = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<!DOCTYPE sst [<!ENTITY xxe SYSTEM "file://{secret_path}">]>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">
<si><t>Tenant</t></si>
<si><t>Rent</t></si>
<si><t>&xxe;</t></si>
<si><t>$1000</t></si>
</sst>'''

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet1)
        z.writestr("xl/sharedStrings.xml", xxe_shared_strings)
    return buf.getvalue()


def _build_xxe_docx(secret_path: str) -> bytes:
    """Same idea as _build_xxe_xlsx, for .docx: document.xml carries the DOCTYPE/external-entity payload."""
    import io
    import zipfile

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    xxe_document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<!DOCTYPE document [<!ENTITY xxe SYSTEM "file://{secret_path}">]>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>Tenant: &xxe;</w:t></w:r></w:p>
</w:body>
</w:document>'''

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", xxe_document)
    return buf.getvalue()


def _build_xss_test_pdf() -> bytes:
    """A synthetic one-page lease whose Permitted Use clause is a script
    tag, built in-memory with reportlab (no fixture file on disk to go
    stale or be missing in a fresh environment). Deliberately targets
    permitted_use rather than tenant/landlord: the party-name patterns'
    character class ([A-Za-z0-9&,.'\\-\\s]) can't match angle brackets at
    all, so a script tag there would correctly extract as not-found and
    never actually exercise the "does script-like text round-trip
    safely once captured" question this test exists to answer. The
    permitted_use pattern ("permitted use[:\\s]+([^\\n]+)") has no such
    restriction, so this is the field that's actually reachable by this
    payload."""
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 10)
    lines = [
        "COMMERCIAL LEASE AGREEMENT",
        "This Lease is entered into by and between Harborview Properties LLC (\"Landlord\")",
        "and Test Tenant, Inc. (\"Tenant\").",
        "PREMISES: Landlord leases to Tenant the premises located at 1 Test Plaza.",
        "RENT: Monthly Rent: $4,000.00.",
        "Permitted Use: <script>alert(1)</script>",
    ]
    y = 700
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _build_empty_pdf() -> bytes:
    """A structurally valid PDF with zero pages -- reportlab's own
    output when .save() is called with nothing drawn/no showPage(),
    not corrupted/random bytes. Distinct edge case from the corrupted-
    PDF test above: this is a well-formed file a PDF library can open
    just fine, that simply has no content to extract from."""
    import io
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.save()
    return buf.getvalue()


def _build_nonenglish_pdf() -> bytes:
    """A one-page lease written entirely in Spanish with accented
    characters -- the extraction patterns are English-only by design,
    so the correct behavior is graceful non-extraction (every field
    stays null), not a crash and not a false-positive match."""
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 10)
    lines = [
        "CONTRATO DE ARRENDAMIENTO COMERCIAL",
        "Este contrato se celebra entre Propiedades del Sol S.A. (\"Arrendador\") y",
        "Café Nacional, S. de R.L. (\"Arrendatario\").",
        "El Arrendatario pagará un alquiler mensual de $3,200.00.",
        "Superficie aproximada: 1,800 pies cuadrados.",
    ]
    y = 700
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _build_password_protected_pdf() -> bytes:
    """A real one-page lease, structurally valid, encrypted with a real
    user password via PyPDF2 -- distinct from both the corrupted-bytes
    case (not a valid PDF at all) and the empty-PDF case (valid but
    contentless). This one is entirely valid and has real content; it
    just can't be opened without a password nobody supplied."""
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 10)
    c.drawString(72, 700, 'This Lease is between Example Landlord LLC ("Landlord") and Example Tenant Inc. ("Tenant").')
    c.save()

    reader = pypdf.PdfReader(io.BytesIO(buf.getvalue()))
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password="hunter2")

    encrypted_buf = io.BytesIO()
    writer.write(encrypted_buf)
    return encrypted_buf.getvalue()


def _build_owner_password_only_pdf() -> bytes:
    """Encrypted, but with only an owner password set and no user
    password -- pypdf.is_encrypted is still true, but decrypt("")
    fully opens it since no password is actually required to read the
    content, only to edit/print it. Must NOT be misclassified as
    "password-protected" the way a real user-password file is."""
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 10)
    # Comfortably over PDFExtractor.min_text_length (100 chars) so this
    # exercises the direct PyPDF2 decrypt path deterministically,
    # rather than depending on whether OCR fallback happens to be
    # available in the environment running this test.
    c.drawString(72, 700, 'This Lease is between Example Landlord LLC ("Landlord") and Example Tenant Inc. ("Tenant").')
    c.drawString(72, 680, "TERM: Lease Start Date: January 1, 2026. Lease End Date: December 31, 2030.")
    c.save()

    reader = pypdf.PdfReader(io.BytesIO(buf.getvalue()))
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password="", owner_password="ownerhunter2")

    encrypted_buf = io.BytesIO()
    writer.write(encrypted_buf)
    return encrypted_buf.getvalue()


def _build_unrelated_document_pdf() -> bytes:
    """A structurally valid, plain-English, multi-line PDF with real
    extractable text -- but nothing that reads as a lease. Distinct
    from the non-English case above: this one fails for content
    reasons, not language ones, and every one of the 5 lease-identity
    fields (tenant/landlord/rent/start/end) should come back null."""
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 10)
    lines = [
        "QUARTERLY MARKETING PERFORMANCE SUMMARY",
        "Prepared for the Northwest Regional Sales Team",
        "This report reviews campaign engagement metrics across all channels",
        "for the quarter ending in June. Overall click-through rates improved",
        "by twelve percent compared to the prior period.",
    ]
    y = 700
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print(f"{'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail else ""))

    status, health, _ = _request("GET", "/health")
    check("server is reachable", status == 200 and health.get("status") == "healthy")

    # --- Oversized lease ID: previously an unhandled OverflowError with
    # a full Werkzeug interactive-debugger traceback (file paths, source
    # code). Must now be a clean 404. ---
    huge_id = "9" * 40
    status, body, content_type = _request("GET", f"/leases/{huge_id}")
    check("oversized lease ID returns 404, not 500", status == 404, str(status))
    check("oversized lease ID response is JSON", "application/json" in content_type, content_type)
    check("oversized lease ID error has no traceback/path leak", isinstance(body, dict) and "Traceback" not in json.dumps(body) and "/Users/" not in json.dumps(body))

    status, body, _ = _request("DELETE", f"/leases/{huge_id}")
    check("oversized lease ID on DELETE also returns 404", status == 404, str(status))

    # --- Oversized file: previously Flask's raw HTML 413 page. Must now
    # be JSON with a clear message. ---
    oversized_content = os.urandom(17 * 1024 * 1024)  # > 16MB limit
    body_bytes, content_type_header = _multipart_body([("file", "big.pdf", oversized_content)])
    status, body, content_type = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("oversized file returns 413", status == 413, str(status))
    check("oversized file response is JSON, not raw HTML", "application/json" in content_type, content_type)
    check("oversized file error message mentions the size limit", isinstance(body, dict) and "16" in body.get("error", ""), str(body))

    # --- Corrupted PDF: error message must be generic, never str(e)
    # verbatim (which could include a temp file path). ---
    corrupted = os.urandom(300)
    body_bytes, content_type_header = _multipart_body([("file", "corrupted.pdf", corrupted)])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    # 422 (not 500) since document_extractor.py's refactor for
    # multi-format upload support: "this file's content can't be
    # processed" is a client-actionable outcome (try a clean copy,
    # re-export it, etc.), not evidence of a server bug -- the same
    # reasoning the password-protected-PDF check below already applied
    # before this file's content-problem paths were unified with it.
    check("corrupted PDF returns 422 with a clean error", status == 422 and isinstance(body, dict), str(status))
    error_text = json.dumps(body)
    check("corrupted PDF error has no file path leak", "/tmp/" not in error_text and "/Users/" not in error_text, error_text)
    check("corrupted PDF error has no Python exception type leak", "Error:" not in error_text and "Traceback" not in error_text, error_text)

    # --- Unknown route: framework default 404 HTML replaced with JSON. ---
    status, body, content_type = _request("GET", "/this-route-does-not-exist")
    check("unknown route returns JSON 404, not framework HTML", status == 404 and "application/json" in content_type, content_type)

    # --- Empty PDF: a structurally valid PDF with zero pages (not
    # corrupted bytes -- a real, well-formed file reportlab itself
    # produces when .save() is called with nothing drawn). Must fail
    # the same clean way a corrupted file does, not crash differently. ---
    empty_pdf = _build_empty_pdf()
    body_bytes, content_type_header = _multipart_body([("file", "empty.pdf", empty_pdf)])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("empty (0-page) PDF fails cleanly, not a 200 with fabricated data", status in (400, 422, 500), str(status))
    check(
        "empty PDF error has no path/traceback leak",
        isinstance(body, dict) and "/tmp/" not in json.dumps(body) and "Traceback" not in json.dumps(body),
        json.dumps(body) if isinstance(body, dict) else str(body),
    )

    # --- Non-English content: the extraction patterns are English-
    # specific by design (see field_extractor.py) -- the bar here isn't
    # "extracts Spanish text," it's "doesn't crash, doesn't mangle
    # encoding, and honestly reports fields as not-found rather than
    # fabricating a match on foreign text." ---
    nonenglish_pdf = _build_nonenglish_pdf()
    body_bytes, content_type_header = _multipart_body([("file", "nonenglish.pdf", nonenglish_pdf)])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("non-English (Spanish) lease extracts without error", status == 200, str(status))
    if isinstance(body, dict) and body.get("leases"):
        fields = body["leases"][0]["fields"]
        check(
            "non-English lease honestly reports fields as not-found rather than fabricating a match",
            all(f.get("value") is None for f in fields.values()),
            json.dumps({k: v.get("value") for k, v in fields.items()}),
        )

    # --- XSS: a lease containing HTML/script-like text in extractable
    # fields must round-trip through the API as plain data (the API
    # itself doesn't render anything — this just confirms extraction
    # doesn't choke on it and returns it as inert JSON string data,
    # which the frontend's escapeHtml() then renders safely).
    #
    # Generated in-memory here rather than relying on a fixture file on
    # disk — an earlier version of this test read a PDF from a fixed
    # /tmp path that nothing in the repo ever (re)created, so the check
    # silently no-op'd (never failed, just never ran) in any environment
    # where that exact file hadn't been manually placed first, e.g. a
    # fresh clone or CI. Found during the pre-sale test-coverage audit. ---
    xss_content = _build_xss_test_pdf()
    body_bytes, content_type_header = _multipart_body([("file", "xss.pdf", xss_content)])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("lease with HTML/script-like content extracts without error", status == 200, str(status))
    check(
        "response is well-formed JSON (script content didn't break serialization)",
        isinstance(body, dict) and isinstance(body.get("leases"), list) and len(body["leases"]) > 0
        and "tenant" in body["leases"][0].get("fields", {}),
        json.dumps(body)[:300],
    )
    if isinstance(body, dict) and body.get("leases"):
        use_field = body["leases"][0]["fields"].get("permitted_use") or {}
        use_value = use_field.get("value") or ""
        check(
            "script tag survives extraction as inert string data, not executed/stripped",
            "<script>" in use_value,
            use_value,
        )

    # --- Password-protected PDF: must be distinguished from generic
    # corruption with a specific, actionable message -- found during
    # the reliability pass that this previously fell through to the
    # same vague "corrupted or unsupported" 500 as truly unreadable
    # garbage bytes, giving the user no way to tell the two apart. ---
    password_protected_pdf = _build_password_protected_pdf()
    body_bytes, content_type_header = _multipart_body([("file", "protected.pdf", password_protected_pdf)])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("password-protected PDF returns 422, not the generic corrupted-PDF 500", status == 422, str(status))
    check(
        "password-protected PDF error specifically names the password, not generic corruption language",
        isinstance(body, dict) and "password" in body.get("error", "").lower(),
        json.dumps(body),
    )
    error_text = json.dumps(body)
    check("password-protected PDF error has no path/traceback leak", "/tmp/" not in error_text and "Traceback" not in error_text, error_text)

    # An owner-password-only PDF (no password needed to open/read it,
    # just to edit/print) must still extract normally -- PyPDF2 can
    # decrypt those with an empty password, so this must NOT be
    # misclassified as "password-protected."
    owner_only_pdf = _build_owner_password_only_pdf()
    body_bytes, content_type_header = _multipart_body([("file", "owner_only.pdf", owner_only_pdf)])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("an owner-password-only PDF (no password needed to read it) extracts normally, not flagged as password-protected", status == 200, str(status))

    # --- Non-lease document: a structurally valid, readable, plain-
    # English PDF that simply isn't a lease. Extraction must not
    # silently produce a normal-looking empty lease -- looks_like_lease
    # must come back false so the frontend can warn the user instead of
    # quietly filing it as a real, if sparse, lease. ---
    unrelated_pdf = _build_unrelated_document_pdf()
    body_bytes, content_type_header = _multipart_body([("file", "unrelated.pdf", unrelated_pdf)])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("non-lease document still extracts without error (real text, just not a lease)", status == 200, str(status))
    if isinstance(body, dict) and body.get("leases"):
        entry = body["leases"][0]
        check(
            "non-lease document is flagged looks_like_lease=false",
            entry.get("looks_like_lease") is False,
            json.dumps({k: v for k, v in entry.items() if k != "fields"}),
        )

    # A real lease, by contrast, must NOT be flagged -- this isn't a
    # blanket "always warn" switch.
    body_bytes, content_type_header = _multipart_body([("file", "xss.pdf", _build_xss_test_pdf())])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    if isinstance(body, dict) and body.get("leases"):
        check(
            "a genuine lease (has tenant/landlord found) is NOT flagged looks_like_lease=false",
            body["leases"][0].get("looks_like_lease") is True,
            json.dumps({k: v for k, v in body["leases"][0].items() if k != "fields"}),
        )

    # --- Missing 'file' field entirely (not just an empty filename):
    # a multipart body with no file part at all must fail the same
    # clean way, not KeyError its way into the generic 500 handler. ---
    body_bytes, content_type_header = _multipart_body([])
    status, body, _ = _request(
        "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
    )
    check("upload with no file field returns 400 with a clear message", status == 400 and isinstance(body, dict) and "file" in body.get("error", "").lower(), str((status, body)))

    # --- Completely empty request body (no multipart structure at
    # all, just a zero-length POST) against an upload route. ---
    status, body, _ = _request(
        "POST", "/extract", data=b"", headers={"Content-Type": "multipart/form-data; boundary=x"}
    )
    check("zero-length upload body fails cleanly (400/422), not a 500", status in (400, 422), str((status, body)))

    # --- Concurrent uploads of the SAME file: the literal scenario
    # named in the hardening request. This is what would have raced
    # database.upsert_discrepancy's natural_key before the atomic
    # INSERT ... ON CONFLICT fix (see test_concurrency.py for the
    # direct DB-layer reproduction) -- two people uploading the same
    # messy lease at once both trigger a risk-flag sync for the exact
    # same natural_key concurrently. Every concurrent request must
    # succeed (201), none may 500. ---
    print("\n--- Concurrent uploads of the same file ---")
    import threading
    messy_lease_bytes = None
    fixture_path = os.path.join(FIXTURES_DIR, "missing_clauses_office.pdf")
    if os.path.exists(fixture_path):
        with open(fixture_path, "rb") as f:
            messy_lease_bytes = f.read()

    concurrent_results = []
    concurrent_created_ids = []
    results_lock = threading.Lock()

    def upload_once():
        body_bytes, content_type_header = _multipart_body([("file", "missing_clauses_office.pdf", messy_lease_bytes)])
        status, body, _ = _request("POST", "/leases", data=body_bytes, headers={"Content-Type": content_type_header})
        with results_lock:
            concurrent_results.append((status, body))
            if status == 201 and isinstance(body, dict):
                for lease in body.get("leases", []):
                    concurrent_created_ids.append(lease["id"])

    if messy_lease_bytes:
        threads = [threading.Thread(target=upload_once) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        statuses = [s for s, _ in concurrent_results]
        check("6 concurrent uploads of the same file all return 201 (none 500 from the natural_key race)", all(s == 201 for s in statuses), str(statuses))

        # Give the async-ish sync a moment then confirm the portfolio
        # endpoints that read the synced discrepancies still respond
        # cleanly (would 500 if a race left the DB in a bad state).
        status, risks_body, _ = _request("GET", "/portfolio/risks")
        check("portfolio risks endpoint still responds cleanly after the concurrent uploads", status == 200, str(status))

        for lease_id in concurrent_created_ids:
            _request("DELETE", f"/leases/{lease_id}")
    else:
        check("concurrent same-file upload test skipped (fixture missing)", True, "missing_clauses_office.pdf not found")

    # --- XXE (XML External Entity) on the .xlsx/.docx upload paths --
    # a new risk surface introduced by multi-format upload support,
    # since both formats are ZIP archives of XML that openpyxl/
    # python-docx parse internally. Investigated and confirmed safe:
    # both libraries construct their lxml parser with
    # resolve_entities=False (openpyxl: app/xml/functions.py;
    # python-docx: docx/oxml/parser.py), so a DOCTYPE-declared
    # external entity is never resolved -- verified here by actually
    # trying to exfiltrate a real local file through it, not just by
    # reading the library source. ---
    print("\n--- XXE on .xlsx/.docx uploads ---")
    import tempfile
    secret_fd, secret_path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(secret_fd, "w") as f:
        f.write("XXE_SECRET_MARKER_do_not_leak")
    try:
        xlsx_bytes = _build_xxe_xlsx(secret_path)
        body_bytes, content_type_header = _multipart_body_with_content_type(
            [("file", "xxe.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
        )
        status, body, _ = _request("POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header})
        response_text = json.dumps(body) if isinstance(body, dict) else str(body)
        check("malicious .xlsx (XXE payload) does not leak the target file's contents", "XXE_SECRET_MARKER" not in response_text, response_text[:300])
        check("malicious .xlsx fails cleanly (400/422), not a 500 or a silent 200 with fabricated data", status in (400, 422), str(status))

        docx_bytes = _build_xxe_docx(secret_path)
        body_bytes, content_type_header = _multipart_body_with_content_type(
            [("file", "xxe.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]
        )
        status, body, _ = _request("POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header})
        response_text = json.dumps(body) if isinstance(body, dict) else str(body)
        check("malicious .docx (XXE payload) does not leak the target file's contents", "XXE_SECRET_MARKER" not in response_text, response_text[:300])
        check("malicious .docx doesn't 500 (either extracts safely with the entity dropped, or fails cleanly)", status in (200, 400, 422), str(status))
    finally:
        os.unlink(secret_path)

    # --- Rent-roll-shaped document uploaded through the single-lease
    # path: previously succeeded (200/201) and confidently returned
    # WRONG values with false high confidence (a column header word as
    # the tenant, a portfolio-wide aggregate as a per-lease figure) --
    # see DECISIONS.md for the real example. Must now fail cleanly with
    # a specific, actionable error instead, and persist nothing. ---
    print("\n--- Rent-roll-shaped document rejected on the single-lease path ---")
    rent_roll_path = os.path.join(FIXTURES_DIR, "synthetic_rent_roll_report.pdf")
    if os.path.exists(rent_roll_path):
        with open(rent_roll_path, "rb") as f:
            rent_roll_bytes = f.read()
        body_bytes, content_type_header = _multipart_body([("file", "synthetic_rent_roll_report.pdf", rent_roll_bytes)])
        status, body, _ = _request("POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header})
        check("rent-roll-shaped PDF via /extract returns 422, not 200 with garbage data", status == 422, str(status))
        check(
            "the error specifically names the rent-roll importer as the fix, not a generic message",
            isinstance(body, dict) and "import-rent-roll" in body.get("error", ""),
            str(body),
        )

        status, leases_before, _ = _request("GET", "/leases")
        count_before = len(leases_before) if isinstance(leases_before, list) else None
        status, body, _ = _request("POST", "/leases", data=body_bytes, headers={"Content-Type": content_type_header})
        check("rent-roll-shaped PDF via POST /leases also returns 422 (persist path, not just /extract)", status == 422, str(status))
        status, leases_after, _ = _request("GET", "/leases")
        count_after = len(leases_after) if isinstance(leases_after, list) else None
        check("the rejected upload persisted nothing", count_before == count_after, f"{count_before} -> {count_after}")
    else:
        check("rent-roll-shape test skipped (fixture missing)", True, "synthetic_rent_roll_report.pdf not found")

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    print("=" * 70)

    failed = [c for c in checks if not c[1]]
    if failed:
        print("\nFAILED:")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")

    return len(failed) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
