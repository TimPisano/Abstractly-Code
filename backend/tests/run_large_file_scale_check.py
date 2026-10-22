"""
Full-size check of the background upload pipeline on the real fixtures,
with REAL OCR (all 300 scanned pages through tesseract) and the regex
engine -- no mocks. Not in run_all_tests.py: the scanned PDF alone takes
10-15 minutes. The unit tests stub OCR at full size and run real OCR on
slices; this is the one place the whole thing runs for real. Results go
in docs/plans/large-files-REPORT.md.

Each file runs in fresh subprocesses (one for the upload request, one for
the job) so each peak-memory number is its own.

Usage: python backend/tests/run_large_file_scale_check.py [name ...]
       names: text_lease scanned_lease rent_roll_xlsx rent_roll_csv
"""
import json
import os
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

SCENARIOS = {
    "text_lease": ("lease", "large_text_lease_500p.pdf", None),
    "scanned_lease": ("lease", "scanned_lease_300p.pdf", None),
    "rent_roll_xlsx": ("rent_roll", "messy_rent_roll_5000.xlsx", "1000 Juniper Row"),
    "rent_roll_csv": ("rent_roll", "messy_rent_roll_5000.csv", "1000 Juniper Row"),
}

# Two child processes per file, so each peak-memory number is honest: the
# first POSTs the file (Werkzeug's test client builds the whole request in
# memory -- a test-harness cost, not the server's), the second runs the
# job alone, the way the worker would.
COMMON = r'''
import io, json, os, resource, sys, tempfile, time
os.environ["LARGE_FILE_UPLOADS"] = "true"
os.environ["LEASE_EXTRACTION_ENGINE"] = "regex"
os.environ.pop("REDIS_URL", None)
os.environ["LARGE_FILE_UPLOAD_DIR"] = __UPLOAD_DIR__
sys.path.insert(0, os.path.abspath(os.path.join(__TESTS_DIR__, "..")))
sys.path.insert(0, __TESTS_DIR__)
from unittest import mock
from _session_users import sync_session_user
from create_large_fixtures import ensure_large_fixtures, path_of
from app import database, upload_jobs
from app.api import app
database.configure(__DB_PATH__)
database.init_db()
client = app.test_client()
with client.session_transaction() as s:
    s.update({"user_id": 1, "email": "scale@example.test", "name": "Scale", "role": "analyst", "team_id": 1})
    sync_session_user(s)

def peak_mb():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024)
'''

UPLOAD = COMMON + r'''
kind, name, address = __ARGS__
ensure_large_fixtures(only=[name])
queued = []
started = time.perf_counter()
with open(path_of(name), "rb") as f:
    data = {"file": (io.BytesIO(f.read()), name), "kind": kind}
if address:
    data["property_address"] = address
with mock.patch.object(upload_jobs, "start_job", side_effect=queued.append):
    resp = client.post("/uploads", data=data, content_type="multipart/form-data")
print("RESULT " + json.dumps({"job_id": queued[0], "http_status": resp.status_code,
                              "request_seconds": round(time.perf_counter() - started, 1)}))
'''

JOB = COMMON + r'''
kind, name, address = __ARGS__
job_id = __JOB_ID__
before = peak_mb()
started = time.perf_counter()
upload_jobs.run_upload_job(job_id)
job_s = time.perf_counter() - started
job_peak = peak_mb()
done = client.get(f"/uploads/{job_id}").get_json()["upload"]
out = {"file": name, "size_mb": round(os.path.getsize(path_of(name)) / 1e6, 1), "job_seconds": round(job_s, 1),
       "process_baseline_mb": before, "job_peak_rss_mb": job_peak, "status": done["status"], "error": done.get("error")}
result = done.get("result") or {}
if kind == "lease" and result:
    f = result["leases"][0]["extracted_fields"]
    out.update({"pages": result["page_count"], "ocr_pages": result["ocr_page_count"], "split_count": result["split_count"],
                "warnings": result["warnings"]})
    for field in ("tenant", "landlord", "rent_amount", "security_deposit", "square_footage", "renewal_options"):
        entry = f.get(field) or {}
        out[field] = entry.get("value")
        out[field + "_page"] = (entry.get("source") or {}).get("page")
elif result:
    out.update({"imported": result["imported_count"], "skipped": len(result["skipped_rows"])})
print("RESULT " + json.dumps(out))
'''


def _child(code, **values):
    for key, value in values.items():
        code = code.replace(key, repr(value))
    env = dict(os.environ, LOG_LEVEL="ERROR")
    env.pop("ADMIN_EMAIL", None)
    env.pop("ADMIN_PASSWORD_HASH", None)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=TESTS_DIR)
    line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT ")), None)
    if not line:
        raise RuntimeError(proc.stderr[-3000:])
    return json.loads(line[len("RESULT "):])


def run(name):
    import shutil
    import tempfile
    kind, filename, address = SCENARIOS[name]
    workdir = tempfile.mkdtemp(prefix="scale-check-")
    common = {"__TESTS_DIR__": TESTS_DIR, "__UPLOAD_DIR__": os.path.join(workdir, "uploads"),
              "__DB_PATH__": os.path.join(workdir, "db.sqlite"), "__ARGS__": (kind, filename, address)}
    try:
        upload = _child(UPLOAD, **common)
        result = _child(JOB, __JOB_ID__=upload["job_id"], **common)
    except RuntimeError as e:
        print(f"{name}: FAILED\n{e}")
        return None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    result.update({"http_status": upload["http_status"], "request_seconds": upload["request_seconds"]})
    print(f"{name}: {json.dumps(result)}", flush=True)
    return result


if __name__ == "__main__":
    for name in (sys.argv[1:] or list(SCENARIOS)):
        run(name)
