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
    check("corrupted PDF returns 500 with a clean error", status == 500 and isinstance(body, dict))
    error_text = json.dumps(body)
    check("corrupted PDF error has no file path leak", "/tmp/" not in error_text and "/Users/" not in error_text, error_text)
    check("corrupted PDF error has no Python exception type leak", "Error:" not in error_text and "Traceback" not in error_text, error_text)

    # --- Unknown route: framework default 404 HTML replaced with JSON. ---
    status, body, content_type = _request("GET", "/this-route-does-not-exist")
    check("unknown route returns JSON 404, not framework HTML", status == 404 and "application/json" in content_type, content_type)

    # --- XSS: a lease containing HTML/script-like text in extractable
    # fields must round-trip through the API as plain data (the API
    # itself doesn't render anything — this just confirms extraction
    # doesn't choke on it and returns it as inert JSON string data,
    # which the frontend's escapeHtml() then renders safely — see
    # run_xss_test.js in this session's scratch dir for the full
    # rendered-DOM verification). ---
    xss_pdf_path = "/tmp/xss_test_lease.pdf"
    if os.path.exists(xss_pdf_path):
        with open(xss_pdf_path, "rb") as f:
            xss_content = f.read()
        body_bytes, content_type_header = _multipart_body([("file", "xss.pdf", xss_content)])
        status, body, _ = _request(
            "POST", "/extract", data=body_bytes, headers={"Content-Type": content_type_header}
        )
        check("lease with HTML/script-like content extracts without error", status == 200)
        check(
            "response is well-formed JSON (script content didn't break serialization)",
            isinstance(body, dict) and isinstance(body.get("leases"), list) and len(body["leases"]) > 0
            and "tenant" in body["leases"][0].get("fields", {}),
        )
    else:
        print("(skipping XSS round-trip check — fixture not present in this run)")

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
