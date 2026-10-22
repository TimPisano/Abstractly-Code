"""
Contract tests between the upload page (frontend/app/upload-view.js,
frontend/app/api.js) and the background-upload API, without a browser:

  - every /uploads path the frontend calls is a real route with that method;
  - every field the page reads off an upload job or its result is present
    in a real GET /uploads/<id> response (a renamed backend field would
    otherwise silently blank the progress bar or the results list);
  - with the flag off the page keeps using the old routes and the same
    16 MB limit the backend enforces.

The UI itself was checked headlessly at 1440/768/375 (see the report).
"""
import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

os.environ["LARGE_FILE_UPLOADS"] = "true"
os.environ.pop("REDIS_URL", None)
_UPLOAD_DIR = tempfile.mkdtemp(prefix="abstractly-test-uploads-")
os.environ["LARGE_FILE_UPLOAD_DIR"] = _UPLOAD_DIR

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _session_users import sync_session_user  # noqa: E402
from app import database, upload_jobs  # noqa: E402
from app.api import LEGACY_MAX_CONTENT_LENGTH, app  # noqa: E402

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.abspath(os.path.join(TESTS_DIR, "..", "..", "frontend", "app"))


def _read(name):
    with open(os.path.join(FRONTEND, name)) as f:
        return f.read()




def test_frontend_upload_calls_match_real_routes():
    api_js = _read("api.js")
    calls = {
        "getUploadConfig": ("GET", "/uploads/config"),
        "startUpload": ("POST", "/uploads"),
        "getUpload": ("GET", "/uploads/1"),
    }
    adapter = app.url_map.bind("localhost")
    for method_name, (http, path) in calls.items():
        body = re.search(rf"{method_name}\([^)]*\)\s*{{(.*?)\n    }},", api_js, re.S)
        assert body, f"Api.{method_name} missing from api.js"
        assert "/uploads" in body.group(1), method_name
        if http == "POST":
            assert "method: 'POST'" in body.group(1), method_name
        endpoint, _ = adapter.match(path, method=http)
        assert endpoint in ("upload_config", "create_upload", "get_upload"), (path, endpoint)
    start = re.search(r"startUpload\([^)]*\)\s*{(.*?)\n    },", api_js, re.S).group(1)
    for field in ("'file'", "'kind'", "'property_address'"):
        assert field in start, f"startUpload must send {field}"
    print("✓ test_frontend_upload_calls_match_real_routes: PASS")


def test_every_field_the_page_reads_is_in_the_api_response():
    js = _read("upload-view.js")
    job_fields = set(re.findall(r"\bjob\.(\w+)", js)) - {"progress"}
    progress_fields = set(re.findall(r"job\.progress\.(\w+)", js)) | set(
        re.findall(r"const \{ ([\w, ]+) \} = job\.progress", js)[0].replace(" ", "").split(","))
    config_fields = set(re.findall(r"this\.config\.(\w+)", js)) | {"accepted", "max_upload_mb"}

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    try:
        client = app.test_client()
        with client.session_transaction() as s:
            s.update({"user_id": 1, "email": "u1@example.com", "name": "U1", "role": "analyst", "team_id": 1})
            sync_session_user(s)
        config = client.get("/uploads/config").get_json()
        assert config_fields <= set(config), config_fields - set(config)
        for kind in ("lease", "rent_roll"):
            assert {"extensions", "label"} <= set(config["accepted"][kind])

        queued = []
        with open(os.path.join(TESTS_DIR, "multiformat_lease.txt"), "rb") as f:
            body = f.read()
        with mock.patch.object(upload_jobs, "start_job", side_effect=queued.append):
            resp = client.post("/uploads", data={"file": (io.BytesIO(body), "lease.txt"), "kind": "lease"},
                               content_type="multipart/form-data")
        job = resp.get_json()["upload"]
        assert job_fields - {"result"} <= set(job), job_fields - set(job)
        assert progress_fields <= set(job["progress"]), progress_fields - set(job["progress"])

        upload_jobs.run_upload_job(queued[0])
        done = client.get(f"/uploads/{queued[0]}").get_json()["upload"]
        for field in ("leases", "split_count", "warnings"):  # read by Upload.handleFiles
            assert field in done["result"], field

        with open(os.path.join(TESTS_DIR, "synthetic_appfolio_rent_roll.csv"), "rb") as f:
            roll = f.read()
        queued.clear()
        with mock.patch.object(upload_jobs, "start_job", side_effect=queued.append):
            client.post("/uploads", data={"file": (io.BytesIO(roll), "roll.csv"), "kind": "rent_roll"},
                        content_type="multipart/form-data")
        upload_jobs.run_upload_job(queued[0])
        result = client.get(f"/uploads/{queued[0]}").get_json()["upload"]["result"]
        rent_roll_js = js[js.index("const RentRollImport"):js.index("const T12CrossCheck")]
        # ocr_confidence is only present for OCR'd rolls, exactly as on the old route.
        rent_roll_fields = set(re.findall(r"response\.(\w+)", rent_roll_js)) - {"ocr_confidence"}
        assert rent_roll_fields <= set(result), rent_roll_fields - set(result)
    finally:
        os.unlink(tmp.name)
    print("✓ test_every_field_the_page_reads_is_in_the_api_response: PASS")


def test_flag_off_page_behavior_is_unchanged():
    js = _read("upload-view.js")
    assert "const LEGACY_MAX_UPLOAD_MB = 16;" in js
    assert LEGACY_MAX_CONTENT_LENGTH == 16 * 1024 * 1024, "frontend and backend legacy limits must agree"
    # The old calls are still what runs when the server says the flag is off.
    assert "response = await Api.uploadLease(file);" in js
    assert "response = await Api.importRentRoll(file, propertyAddress);" in js
    # A failed /uploads/config request means "off", never a broken page.
    assert ".catch(() => { this.config = { large_file_uploads: false }; return this.config; })" in js
    print("✓ test_flag_off_page_behavior_is_unchanged: PASS")


def test_frontend_files_parse():
    node = shutil.which("node")
    if not node:
        print("- test_frontend_files_parse: node not installed here; syntax not checked")
        return
    for name in ("upload-view.js", "api.js"):
        out = subprocess.run([node, "--check", os.path.join(FRONTEND, name)], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
    print("✓ test_frontend_files_parse: PASS")


if __name__ == "__main__":
    try:
        test_frontend_upload_calls_match_real_routes()
        test_every_field_the_page_reads_is_in_the_api_response()
        test_flag_off_page_behavior_is_unchanged()
        test_frontend_files_parse()
    finally:
        shutil.rmtree(_UPLOAD_DIR, ignore_errors=True)
    print("\nAll large-upload frontend contract tests passed!")
