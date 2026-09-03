"""
Tests for app/ai_extraction.py: the model-backed lease abstraction
engine. Same convention as test_assistant.py -- NO real Claude calls
here (the anthropic client is mocked with real anthropic.types
objects), with the real end-to-end call proven separately in
test_live_extraction_api.py (--live).

Covers:
  - the tool payload -> engine-independent {value/source/confidence}
    shape, including page-locating a verbatim quote
  - the "found a value but no verbatim quote" / "garbled confidence"
    degrade-don't-drop rules
  - retry-with-backoff on transient failures, no-retry on auth/4xx,
    and that everything surfaces as AIExtractionError (never a raw SDK
    exception, never a partial dict)
  - resolve_engine() flag behavior
  - the upload route wired to AI: persists AI fields, writes an
    ai_extraction_runs telemetry row linked to the lease, and 502s
    cleanly (no regex fallback) when extraction fails
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import anthropic
import httpx
from anthropic.types import ToolUseBlock

from app.api import app
from app import database
from app import ai_extraction
from app.portfolio import FIELD_NAMES


PAGES = [
    {"page": 1, "text": "COMMERCIAL LEASE AGREEMENT\nThis lease is between Property Holdings LLC (\"Landlord\") "
                        "and Blue Sky Coffee Roasters, Inc. (\"Tenant\")."},
    {"page": 2, "text": "Base Rent: $6,250.00 per month. The term shall commence on April 1, 2025 and "
                        "expire on March 31, 2030. Security Deposit: $12,500.00."},
]


def _full_payload(**overrides):
    """A complete tool payload: every field present, null unless overridden with (value, confidence, source_text)."""
    payload = {}
    for name in ai_extraction.LEASE_FIELDS:
        if name in overrides:
            value, confidence, source_text = overrides[name]
            payload[name] = {"value": value, "confidence": confidence, "source_text": source_text}
        else:
            payload[name] = {"value": None, "confidence": None, "source_text": None}
    return payload


def _mock_client(tool_input):
    fake_response = mock.Mock()
    fake_response.content = [ToolUseBlock(id="toolu_x", input=tool_input, name="record_lease_abstraction", type="tool_use")]
    fake_response.usage = mock.Mock(input_tokens=1234, output_tokens=567)
    fake_response.stop_reason = "tool_use"
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = fake_response
    return fake_client


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _http_status_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls("boom", response=response, body=None)


# ----------------------------------------------------------------------
# Payload parsing -> stored shape
# ----------------------------------------------------------------------

def test_extract_maps_payload_to_engine_independent_shape_and_locates_pages():
    payload = _full_payload(
        tenant=("Blue Sky Coffee Roasters, Inc.", "high", 'Blue Sky Coffee Roasters, Inc. ("Tenant")'),
        rent_amount=("$6,250.00", "high", "Base Rent: $6,250.00 per month"),
        lease_start_date=("April 1, 2025", "medium", "shall commence on April 1, 2025"),
    )
    fields = ai_extraction.extract_lease_fields(PAGES, client=_mock_client(payload))

    assert set(fields) == set(ai_extraction.LEASE_FIELDS) | {"_ai_meta"}
    assert fields["tenant"]["value"] == "Blue Sky Coffee Roasters, Inc."
    assert fields["tenant"]["confidence"] == "high"
    assert fields["tenant"]["engine"] == "ai"
    # verbatim quote located back to its real page
    assert fields["tenant"]["source"] == {"page": 1, "quote": 'Blue Sky Coffee Roasters, Inc. ("Tenant")'}
    assert fields["rent_amount"]["source"]["page"] == 2
    assert fields["lease_start_date"]["source"]["page"] == 2
    # untouched fields are proper not-found entries
    assert fields["cam_charges"] == {"value": None, "source": None, "confidence": None, "engine": "ai"}
    # telemetry stash
    assert fields["_ai_meta"]["found_count"] == 3
    assert fields["_ai_meta"]["input_tokens"] == 1234
    print("✓ test_extract_maps_payload_to_engine_independent_shape_and_locates_pages: PASS")


def test_value_without_source_text_is_kept_but_forced_low_and_flagged():
    payload = _full_payload(rent_amount=("$6,250.00", "high", None))
    fields = ai_extraction.extract_lease_fields(PAGES, client=_mock_client(payload))
    entry = fields["rent_amount"]
    assert entry["value"] == "$6,250.00"
    assert entry["confidence"] == "low", "a value with no verbatim support must never read as high"
    assert entry["source"] is None
    assert "validation_note" in entry
    print("✓ test_value_without_source_text_is_kept_but_forced_low_and_flagged: PASS")


def test_garbled_confidence_degrades_to_low_not_dropped():
    payload = _full_payload(tenant=("Acme Corp", "very-sure", "Acme Corp (\"Tenant\")"))
    fields = ai_extraction.extract_lease_fields(PAGES, client=_mock_client(payload))
    assert fields["tenant"]["value"] == "Acme Corp"
    assert fields["tenant"]["confidence"] == "low"
    print("✓ test_garbled_confidence_degrades_to_low_not_dropped: PASS")


def test_unlocatable_quote_still_kept_as_source_text_with_best_effort_page():
    payload = _full_payload(permitted_use=("retail coffee shop", "medium", "operated solely as a retail coffee shop and roastery"))
    fields = ai_extraction.extract_lease_fields(PAGES, client=_mock_client(payload))
    entry = fields["permitted_use"]
    assert entry["value"] == "retail coffee shop"
    assert entry["source_text"] == "operated solely as a retail coffee shop and roastery"
    assert entry["source"]["quote"] == "operated solely as a retail coffee shop and roastery"
    assert entry["source"]["page"] in (1, 2)
    print("✓ test_unlocatable_quote_still_kept_as_source_text_with_best_effort_page: PASS")


# ----------------------------------------------------------------------
# Failure handling
# ----------------------------------------------------------------------

def test_transient_failure_retries_then_raises_ai_extraction_error():
    fake_client = mock.Mock()
    fake_client.messages.create.side_effect = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    with mock.patch("time.sleep") as sleep:
        try:
            ai_extraction.extract_lease_fields(PAGES, client=fake_client)
            assert False, "must raise AIExtractionError"
        except ai_extraction.AIExtractionError:
            pass
    assert fake_client.messages.create.call_count == ai_extraction.MAX_ATTEMPTS
    assert sleep.call_count == ai_extraction.MAX_ATTEMPTS - 1
    print("✓ test_transient_failure_retries_then_raises_ai_extraction_error: PASS")


def test_transient_failure_then_success_returns_fields():
    good = _mock_client(_full_payload(tenant=("Acme Corp", "high", 'Acme Corp ("Tenant")'))).messages.create.return_value
    fake_client = mock.Mock()
    fake_client.messages.create.side_effect = [anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")), good]
    with mock.patch("time.sleep"):
        fields = ai_extraction.extract_lease_fields(PAGES, client=fake_client)
    assert fields["tenant"]["value"] == "Acme Corp"
    assert fake_client.messages.create.call_count == 2
    print("✓ test_transient_failure_then_success_returns_fields: PASS")


def test_auth_error_is_not_retried():
    fake_client = mock.Mock()
    fake_client.messages.create.side_effect = _http_status_error(anthropic.AuthenticationError, 401)
    with mock.patch("time.sleep") as sleep:
        try:
            ai_extraction.extract_lease_fields(PAGES, client=fake_client)
            assert False, "must raise AIExtractionError"
        except ai_extraction.AIExtractionError:
            pass
    assert fake_client.messages.create.call_count == 1, "auth failure won't fix itself -- do not retry"
    assert sleep.call_count == 0
    print("✓ test_auth_error_is_not_retried: PASS")


def test_bad_request_is_not_retried():
    fake_client = mock.Mock()
    fake_client.messages.create.side_effect = _http_status_error(anthropic.BadRequestError, 400)
    with mock.patch("time.sleep"):
        try:
            ai_extraction.extract_lease_fields(PAGES, client=fake_client)
            assert False
        except ai_extraction.AIExtractionError:
            pass
    assert fake_client.messages.create.call_count == 1
    print("✓ test_bad_request_is_not_retried: PASS")


def test_response_with_no_tool_use_block_raises_clean_error():
    fake_response = mock.Mock()
    fake_response.content = [mock.Mock(type="text")]
    fake_response.stop_reason = "end_turn"
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = fake_response
    try:
        ai_extraction.extract_lease_fields(PAGES, client=fake_client)
        assert False
    except ai_extraction.AIExtractionError:
        pass
    print("✓ test_response_with_no_tool_use_block_raises_clean_error: PASS")


def test_empty_pages_raises_without_calling_model():
    fake_client = mock.Mock()
    try:
        ai_extraction.extract_lease_fields([], client=fake_client)
        assert False
    except ai_extraction.AIExtractionError:
        pass
    fake_client.messages.create.assert_not_called()
    print("✓ test_empty_pages_raises_without_calling_model: PASS")


# ----------------------------------------------------------------------
# Engine selection
# ----------------------------------------------------------------------

def test_resolve_engine_flag_behavior():
    keep = {k: os.environ.get(k) for k in ("LEASE_EXTRACTION_ENGINE", "LEASE_AI_EXTRACTION", "ANTHROPIC_API_KEY")}
    try:
        for k in keep:
            os.environ.pop(k, None)
        assert ai_extraction.resolve_engine() == "regex", "default is regex"

        os.environ["LEASE_AI_EXTRACTION"] = "true"
        assert ai_extraction.resolve_engine() == "regex", "flag on but no API key -> regex"

        os.environ["ANTHROPIC_API_KEY"] = "sk-test"
        assert ai_extraction.resolve_engine() == "ai", "flag on + key -> ai"

        os.environ["LEASE_EXTRACTION_ENGINE"] = "regex"
        assert ai_extraction.resolve_engine() == "regex", "explicit override wins"
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("✓ test_resolve_engine_flag_behavior: PASS")


# ----------------------------------------------------------------------
# Upload route wired to AI
# ----------------------------------------------------------------------

def _analyst_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess.update({"user_id": 1, "email": "a@example.com", "name": "A", "role": "analyst"})
    return client


def _pdf_bytes():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(72, 720, 'Lease between Property Holdings LLC ("Landlord") and Acme Corp ("Tenant").')
    c.drawString(72, 700, "Base Rent: $6,250.00 per month.")
    c.save()
    return buf.getvalue()


import contextlib


@contextlib.contextmanager
def _sync_ai_engine():
    """Force the AI engine AND the synchronous (non-deferred) extraction path -- the async path has its own coverage in test_async_extraction.py."""
    prev = os.environ.get("LEASE_ASYNC_EXTRACTION")
    os.environ["LEASE_ASYNC_EXTRACTION"] = "false"
    try:
        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"):
            yield
    finally:
        if prev is None:
            os.environ.pop("LEASE_ASYNC_EXTRACTION", None)
        else:
            os.environ["LEASE_ASYNC_EXTRACTION"] = prev


def test_upload_route_uses_ai_engine_and_records_linked_telemetry():
    db_path = _fresh_temp_db()
    try:
        payload = _full_payload(
            tenant=("Acme Corp", "high", 'Acme Corp ("Tenant")'),
            rent_amount=("$6,250.00", "medium", "Base Rent: $6,250.00 per month"),
        )
        with _sync_ai_engine(), \
             mock.patch.object(ai_extraction, "extract_lease_fields",
                               side_effect=lambda pages, **kw: ai_extraction._parse_tool_payload(payload, pages) | {
                                   "_ai_meta": {"model": "claude-sonnet-5", "latency_ms": 42,
                                                "input_tokens": 100, "output_tokens": 20, "found_count": 2}}):
            resp = _analyst_client().post(
                "/leases",
                data={"file": (__import__("io").BytesIO(_pdf_bytes()), "acme.pdf")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201, resp.get_json()
        lease = resp.get_json()["leases"][0]
        assert lease["extracted_fields"]["tenant"]["value"] == "Acme Corp"
        assert lease["extracted_fields"]["tenant"]["engine"] == "ai"
        assert "_ai_meta" not in lease["extracted_fields"]

        runs = database.list_ai_extraction_runs()
        assert len(runs) == 1
        assert runs[0]["engine"] == "ai"
        assert runs[0]["status"] == "ok"
        assert runs[0]["lease_id"] == lease["id"], "telemetry row must be linked to the persisted lease"
        assert runs[0]["high_count"] == 1 and runs[0]["medium_count"] == 1
    finally:
        os.unlink(db_path)
    print("✓ test_upload_route_uses_ai_engine_and_records_linked_telemetry: PASS")


def test_upload_route_502s_cleanly_when_ai_extraction_fails_no_regex_fallback():
    db_path = _fresh_temp_db()
    try:
        with _sync_ai_engine(), \
             mock.patch.object(ai_extraction, "extract_lease_fields",
                               side_effect=ai_extraction.AIExtractionError("The document-extraction service is temporarily unavailable. Please try again in a moment.")):
            resp = _analyst_client().post(
                "/leases",
                data={"file": (__import__("io").BytesIO(_pdf_bytes()), "acme.pdf")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 502
        body = resp.get_json()
        assert "temporarily unavailable" in body["error"]
        assert "Traceback" not in str(body)
        assert database.get_all_effective_leases() == [], "nothing persisted on a failed synchronous extraction"
    finally:
        os.unlink(db_path)
    print("✓ test_upload_route_502s_cleanly_when_ai_extraction_fails_no_regex_fallback: PASS")


if __name__ == "__main__":
    test_extract_maps_payload_to_engine_independent_shape_and_locates_pages()
    test_value_without_source_text_is_kept_but_forced_low_and_flagged()
    test_garbled_confidence_degrades_to_low_not_dropped()
    test_unlocatable_quote_still_kept_as_source_text_with_best_effort_page()
    test_transient_failure_retries_then_raises_ai_extraction_error()
    test_transient_failure_then_success_returns_fields()
    test_auth_error_is_not_retried()
    test_bad_request_is_not_retried()
    test_response_with_no_tool_use_block_raises_clean_error()
    test_empty_pages_raises_without_calling_model()
    test_resolve_engine_flag_behavior()
    test_upload_route_uses_ai_engine_and_records_linked_telemetry()
    test_upload_route_502s_cleanly_when_ai_extraction_fails_no_regex_fallback()
    print("\nAll AI extraction tests passed.")
