"""
Live API regression suite for multi-format lease uploads -- follows
the exact convention established by test_live_discrepancies_api.py:
runs against the actually-running dev server over real HTTP,
specifically to catch "the route/logic is right in the source file,
but the currently-running server process is stale" (a real bug class
this project has hit before -- see DECISIONS.md).

This is the test the request itself asked for explicitly: "actually
upload one of each type and confirm it extracts correctly, don't just
trust that the code looks right." Every one of the 9 real fixture
files in tests/multiformat_lease.* (PDF already covered by the
existing live suite; Excel .xlsx/.xls, CSV, TSV, Word .docx/.doc,
images .jpg/.png/.tiff, plain .txt here) is POSTed to the real
POST /leases route and its persisted extraction result checked against
the same known field values -- not just that the request returned 200.
"""
import os
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

API_BASE_URL = "http://localhost:5000"
FIXTURES_DIR = os.path.dirname(__file__)

EXPECTED = {
    "tenant": "Cascade Outdoor Gear Co.",
    "landlord": "Timberline Properties LLC",
    "property_address": "500 Pioneer Square, Suite 300, Portland, Oregon 97204",
    "lease_start_date": "May 1, 2025",
    "lease_end_date": "April 30, 2032",
    "rent_amount": "$7,800.00",
    "security_deposit": "$7,800.00",
    "cam_charges": "$650.00",
    "square_footage": "2,900 sq ft",
}

_CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "jpg": "image/jpeg",
    "png": "image/png",
    "tiff": "image/tiff",
    "txt": "text/plain",
}


def _request(method, path, data=None, headers=None):
    url = f"{API_BASE_URL}{path}"
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "application/json" in content_type:
                return resp.status, json.loads(raw.decode())
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return e.code, raw


def _multipart_body(fields, files):
    boundary = "----MultiformatUploadTestBoundary"
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for field_name, filename, content, content_type in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def clear_all_leases():
    status, leases = _request("GET", "/leases")
    assert status == 200, f"could not list leases to clear: {status} {leases}"
    for lease in leases:
        _request("DELETE", f"/leases/{lease['id']}")


def _read_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    status, health_check = _request("GET", "/health")
    check("server is reachable", status == 200 and health_check.get("status") == "healthy")

    created_lease_ids = []
    try:
        clear_all_leases()

        # ---- Upload a real fixture of every new supported format ----
        for extension in ("xlsx", "xls", "csv", "tsv", "docx", "doc", "jpg", "png", "tiff", "txt"):
            filename = f"multiformat_lease.{extension}"
            print(f"\n--- Uploading real {extension.upper()} fixture ----")
            content = _read_fixture(filename)
            body, ct = _multipart_body({}, [("file", filename, content, _CONTENT_TYPES[extension])])
            status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
            check(f"{extension}: upload returns 201", status == 201, str(result))
            if status != 201:
                continue

            lease_id = result["leases"][0]["id"]
            created_lease_ids.append(lease_id)
            fields = result["leases"][0]["extracted_fields"]

            all_correct = True
            wrong = {}
            for field, expected_value in EXPECTED.items():
                actual = fields.get(field, {}).get("value")
                if actual != expected_value:
                    all_correct = False
                    wrong[field] = (expected_value, actual)
            check(f"{extension}: all {len(EXPECTED)} expected fields extracted correctly", all_correct, str(wrong))

            has_sources = all(fields.get(f, {}).get("source") is not None for f in EXPECTED)
            check(f"{extension}: every extracted field has a real source citation", has_sources)

            # Confirm it's actually persisted and retrievable, not just returned once
            status, fetched = _request("GET", f"/leases/{lease_id}")
            check(f"{extension}: persisted lease is retrievable via GET", status == 200 and fetched["extracted_fields"]["tenant"]["value"] == "Cascade Outdoor Gear Co.", str(status))

        # ---- Cross-format consistency: every format's result must actually match every other's ----
        print("\n--- Cross-format consistency ----")
        status, all_leases = _request("GET", "/leases")
        tenant_values = {l["extracted_fields"]["tenant"]["value"] for l in all_leases if l["id"] in created_lease_ids}
        check("every format extracted the IDENTICAL tenant value (one consistent pipeline, not per-format drift)", tenant_values == {"Cascade Outdoor Gear Co."}, str(tenant_values))

        # ---- Real error paths, over real HTTP ----
        print("\n--- Real error paths over HTTP ----")
        body, ct = _multipart_body({}, [("file", "notes.rtf", b"some content", "application/rtf")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        check("unsupported extension (.rtf) returns 400, not a crash", status == 400, str(result))

        body, ct = _multipart_body({}, [("file", "empty.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        check("empty file returns a clear 4xx, not a 500 or a hang", 400 <= status < 500, str(result))
        check("empty file error message says 'empty'", "empty" in result.get("error", "").lower(), str(result))

        body, ct = _multipart_body({}, [("file", "corrupted.docx", b"not a real docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        check("corrupted docx returns a clear 4xx with a specific message", 400 <= status < 500 and ("corrupted" in result.get("error", "").lower() or "unsupported" in result.get("error", "").lower()), str(result))

        # ---- Batch endpoint also accepts mixed formats in one request ----
        print("\n--- Batch upload with mixed formats ----")
        batch_boundary = "----BatchMixedFormatTest"
        parts = []
        for extension in ("xlsx", "docx", "txt"):
            filename = f"multiformat_lease.{extension}"
            content = _read_fixture(filename)
            parts.append((
                f"--{batch_boundary}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
                f"Content-Type: {_CONTENT_TYPES[extension]}\r\n\r\n"
            ).encode() + content + b"\r\n")
        parts.append(f"--{batch_boundary}--\r\n".encode())
        batch_body = b"".join(parts)
        status, batch_result = _request("POST", "/leases/batch", data=batch_body, headers={"Content-Type": f"multipart/form-data; boundary={batch_boundary}"})
        check("batch upload with 3 different formats returns 200", status == 200, str(batch_result)[:300])
        if status == 200:
            per_file_results = batch_result.get("results", [])
            for r in per_file_results:
                for lease in r.get("leases", []):
                    created_lease_ids.append(lease["id"])
            succeeded = [r for r in per_file_results if r["success"]]
            check("all 3 mixed-format files in the batch succeeded", len(succeeded) == 3, f"{batch_result.get('succeeded')} / {batch_result.get('total')}")

    finally:
        print("\nCleaning up test data...")
        for lease_id in created_lease_ids:
            _request("DELETE", f"/leases/{lease_id}")
        status, remaining = _request("GET", "/leases")
        check("cleanup leaves DB empty", status == 200 and remaining == [], f"{len(remaining) if isinstance(remaining, list) else remaining} leases remain")

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
