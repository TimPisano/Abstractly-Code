"""
Tests for the background (async) AI extraction path added in the
performance hardening pass: an AI-engine upload returns 202 immediately
with the leases in 'processing' state, and a background thread fills in
the fields (or marks the row 'failed' with a plain reason).

The background thread is made deterministic by patching
app.api.threading.Thread so .start() runs the target synchronously.
"""

import io
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app import api
from app.api import app
from app import database
from app import ai_extraction
from app.portfolio import FIELD_NAMES


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _analyst_client():
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"user_id": 1, "email": "a@example.com", "name": "A", "role": "analyst"})
    return c


def _pdf_bytes(*lines):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 720
    for ln in lines or ('Lease between Property Holdings LLC ("Landlord") and Acme Corp ("Tenant"). Base Rent: $6,250.00 per month.',):
        c.drawString(72, y, ln)
        y -= 18
    c.save()
    return buf.getvalue()


def _fields(**overrides):
    out = {}
    for name in FIELD_NAMES:
        v = overrides.get(name)
        out[name] = {"value": v, "source": {"page": 1, "quote": "..."} if v else None,
                     "confidence": "high" if v else None, "engine": "ai"}
    return out


class _SyncThread:
    """Stand-in for threading.Thread whose .start() runs the target inline."""
    def __init__(self, target=None, name=None, daemon=None, args=(), kwargs=None):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


def _upload(client, filename="acme.pdf", body=None):
    return client.post("/leases", data={"file": (io.BytesIO(body or _pdf_bytes()), filename)},
                       content_type="multipart/form-data")


# ----------------------------------------------------------------------

def test_ai_upload_returns_202_and_leases_start_in_processing_state():
    db = _fresh_temp_db()
    try:
        # thread does NOT run (real Thread, but we don't wait) -> observe the immediate 202 state
        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"), \
             mock.patch.object(api.threading, "Thread") as FakeThread:
            FakeThread.return_value = mock.Mock()  # .start() is a no-op
            resp = _upload(_analyst_client())
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["processing"] is True
        assert body["leases"][0]["processing_status"] == "processing"
        assert body["leases"][0]["looks_like_lease"] is True, "don't pre-flag a still-processing lease as non-lease"

        lease_id = body["leases"][0]["id"]
        assert database.get_lease(lease_id)["processing_status"] == "processing"
    finally:
        os.unlink(db)
    print("✓ test_ai_upload_returns_202_and_leases_start_in_processing_state: PASS")


def test_background_thread_fills_in_fields_and_links_telemetry():
    db = _fresh_temp_db()
    try:
        extracted = _fields(tenant="Acme Corp", rent_amount="$6,250.00")
        extracted_with_meta = dict(extracted)
        extracted_with_meta["_ai_meta"] = {"model": "claude-sonnet-5", "latency_ms": 40,
                                           "input_tokens": 90, "output_tokens": 15, "found_count": 2}
        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"), \
             mock.patch.object(api.threading, "Thread", _SyncThread), \
             mock.patch.object(ai_extraction, "extract_lease_fields", return_value=extracted_with_meta):
            resp = _upload(_analyst_client())

        assert resp.status_code == 202
        lease_id = resp.get_json()["leases"][0]["id"]

        lease = database.get_lease(lease_id)
        assert lease["processing_status"] == "complete"
        assert lease["processing_error"] is None
        assert lease["extracted_fields"]["tenant"]["value"] == "Acme Corp"
        assert "_ai_meta" not in lease["extracted_fields"]

        runs = database.list_ai_extraction_runs()
        assert len(runs) == 1 and runs[0]["status"] == "ok" and runs[0]["lease_id"] == lease_id

        # GET routes expose the finished status
        detail = _analyst_client().get(f"/leases/{lease_id}").get_json()
        assert detail["processing_status"] == "complete"
    finally:
        os.unlink(db)
    print("✓ test_background_thread_fills_in_fields_and_links_telemetry: PASS")


def test_background_ai_failure_marks_lease_failed_and_keeps_the_row():
    db = _fresh_temp_db()
    try:
        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"), \
             mock.patch.object(api.threading, "Thread", _SyncThread), \
             mock.patch.object(ai_extraction, "extract_lease_fields",
                               side_effect=ai_extraction.AIExtractionError("AI processing is unavailable: the API credit balance is too low.")):
            resp = _upload(_analyst_client())

        assert resp.status_code == 202
        lease_id = resp.get_json()["leases"][0]["id"]

        lease = database.get_lease(lease_id)
        assert lease["processing_status"] == "failed"
        assert "credit balance" in lease["processing_error"]
        # the row is kept (so the user sees WHY), not silently dropped
        assert database.get_lease(lease_id) is not None

        runs = database.list_ai_extraction_runs()
        assert len(runs) == 1 and runs[0]["status"] == "error"
    finally:
        os.unlink(db)
    print("✓ test_background_ai_failure_marks_lease_failed_and_keeps_the_row: PASS")


def test_multi_lease_document_processes_every_split_lease():
    db = _fresh_temp_db()
    try:
        two_lease_pdf = _pdf_bytes(
            'Lease between Owner A LLC ("Landlord") and Tenant One Inc. ("Tenant"). Base Rent: $1,000.00 per month.',
            'Lease between Owner B LLC ("Landlord") and Tenant Two Inc. ("Tenant"). Base Rent: $2,000.00 per month.',
        )
        calls = []

        def _fake_extract(pages, **kw):
            calls.append(1)
            return {**_fields(tenant=f"Tenant {len(calls)}"), "_ai_meta": {"model": "m", "found_count": 1}}

        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"), \
             mock.patch.object(api.threading, "Thread", _SyncThread), \
             mock.patch.object(api.FieldExtractor, "detect_lease_boundaries", return_value=[(1, 1), (2, 2)]), \
             mock.patch.object(ai_extraction, "extract_lease_fields", side_effect=_fake_extract):
            resp = _upload(_analyst_client(), body=two_lease_pdf)

        assert resp.status_code == 202
        assert resp.get_json()["split_count"] == 2
        leases = database.get_all_effective_leases()
        assert len(leases) == 2
        assert all(l["processing_status"] == "complete" for l in leases)
    finally:
        os.unlink(db)
    print("✓ test_multi_lease_document_processes_every_split_lease: PASS")


def test_fail_orphaned_processing_leases_recovers_stuck_rows():
    db = _fresh_temp_db()
    try:
        lid = database.insert_lease("stuck.pdf", _fields(), processing_status="processing")
        assert database.get_lease(lid)["processing_status"] == "processing"
        n = database.fail_orphaned_processing_leases()
        assert n == 1
        lease = database.get_lease(lid)
        assert lease["processing_status"] == "failed"
        assert "restart" in lease["processing_error"]
        assert database.fail_orphaned_processing_leases() == 0, "idempotent -- nothing left to reset"
    finally:
        os.unlink(db)
    print("✓ test_fail_orphaned_processing_leases_recovers_stuck_rows: PASS")


def test_async_disabled_falls_back_to_synchronous_201():
    db = _fresh_temp_db()
    prev = os.environ.get("LEASE_ASYNC_EXTRACTION")
    os.environ["LEASE_ASYNC_EXTRACTION"] = "false"
    try:
        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"), \
             mock.patch.object(ai_extraction, "extract_lease_fields",
                               return_value={**_fields(tenant="Acme"), "_ai_meta": {"model": "m", "found_count": 1}}):
            resp = _upload(_analyst_client())
        assert resp.status_code == 201
        assert "processing" not in resp.get_json()
        assert resp.get_json()["leases"][0]["processing_status"] == "complete"
    finally:
        if prev is None:
            os.environ.pop("LEASE_ASYNC_EXTRACTION", None)
        else:
            os.environ["LEASE_ASYNC_EXTRACTION"] = prev
        os.unlink(db)
    print("✓ test_async_disabled_falls_back_to_synchronous_201: PASS")


if __name__ == "__main__":
    test_ai_upload_returns_202_and_leases_start_in_processing_state()
    test_background_thread_fills_in_fields_and_links_telemetry()
    test_background_ai_failure_marks_lease_failed_and_keeps_the_row()
    test_multi_lease_document_processes_every_split_lease()
    test_fail_orphaned_processing_leases_recovers_stuck_rows()
    test_async_disabled_falls_back_to_synchronous_201()
    print("\nAll async extraction tests passed.")
