"""
Tests for the landing page's "Book a Demo" form (POST /demo-request):
validation (client-independent, server-side), the honeypot spam trap, the
per-IP rate limit, and the same "email must never block a real submission"
guarantee the waitlist flow already has.

Follows test_waitlist_email.py's pattern: Flask's in-process test_client(),
mocked smtplib.SMTP_SSL, an isolated temp SQLite file per test.
"""

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import api as api_module
from app import database, email_service

# Same reasoning as test_waitlist_email.py: pop these so any /demo-request
# call in a test that doesn't explicitly opt back in via its own
# mock.patch.dict(os.environ, ...) can't reach real smtplib.
os.environ.pop("EMAIL_USER", None)
os.environ.pop("EMAIL_APP_PASSWORD", None)

_FAKE_ENV = {
    "EMAIL_USER": "fake@example.com",
    "EMAIL_APP_PASSWORD": "fake-app-password",
    "ADMIN_EMAIL": "timmypisano24@gmail.com",
}

_VALID_BODY = {
    "name": "Jane Doe",
    "work_email": "jane@example.com",
    "company": "Example Capital Partners",
    "units": 240,
    "message": "We're underwriting a 240-unit deal and want to see a sample report.",
}


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    # The per-IP rate limiter is in-process, module-level state shared
    # across every test in this file (Flask's test_client() has no real
    # per-test IP to key it by, so every request in this file lands on
    # the same "unknown" bucket) -- reset it alongside the DB so one
    # test's requests can't trip the cap for the next one.
    api_module._demo_request_rate_limiter.reset()
    return tmp.name


def _mocked_smtp():
    mock_server = mock.MagicMock()
    mock_smtp_ssl = mock.MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = mock_server
    return mock_smtp_ssl, mock_server


def test_valid_submission_succeeds_persists_and_sends_both_emails():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                client = app.test_client()
                resp = client.post("/demo-request", json=_VALID_BODY)

            assert resp.status_code == 201, resp.get_json()
            assert "message" in resp.get_json()

            requests = database.get_all_demo_requests()
            assert len(requests) == 1
            saved = requests[0]
            assert saved["name"] == "Jane Doe"
            assert saved["work_email"] == "jane@example.com"
            assert saved["company"] == "Example Capital Partners"
            assert saved["units"] == 240
            assert saved["message"] == _VALID_BODY["message"]

            assert mock_server.sendmail.call_count == 2
            recipients = [call.args[1] for call in mock_server.sendmail.call_args_list]
            assert ["jane@example.com"] in recipients
            assert ["timmypisano24@gmail.com"] in recipients
    finally:
        os.unlink(db_path)

    print("✓ test_valid_submission_succeeds_persists_and_sends_both_emails: PASS")


def test_submission_without_optional_message_succeeds():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            mock_smtp_ssl, _ = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                client = app.test_client()
                body = {k: v for k, v in _VALID_BODY.items() if k != "message"}
                resp = client.post("/demo-request", json=body)

            assert resp.status_code == 201, resp.get_json()
            requests = database.get_all_demo_requests()
            assert len(requests) == 1
            assert requests[0]["message"] is None
    finally:
        os.unlink(db_path)

    print("✓ test_submission_without_optional_message_succeeds: PASS")


def test_missing_name_rejected():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        body = {**_VALID_BODY, "name": ""}
        resp = client.post("/demo-request", json=body)

        assert resp.status_code == 400
        assert "error" in resp.get_json()
        assert database.get_all_demo_requests() == []
    finally:
        os.unlink(db_path)

    print("✓ test_missing_name_rejected: PASS")


def test_missing_company_rejected():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        body = {**_VALID_BODY, "company": "   "}
        resp = client.post("/demo-request", json=body)

        assert resp.status_code == 400
        assert database.get_all_demo_requests() == []
    finally:
        os.unlink(db_path)

    print("✓ test_missing_company_rejected: PASS")


def test_invalid_email_format_rejected():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        for bad_email in ["not-an-email", "missing-at.com", "@missing-local.com", ""]:
            body = {**_VALID_BODY, "work_email": bad_email}
            resp = client.post("/demo-request", json=body)
            assert resp.status_code == 400, f"{bad_email!r} should have been rejected"

        assert database.get_all_demo_requests() == []
    finally:
        os.unlink(db_path)

    print("✓ test_invalid_email_format_rejected: PASS")


def test_invalid_units_rejected():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        for bad_units in ["not-a-number", -5, 0, 5.5, "5.5", 10_000_000, None]:
            body = {**_VALID_BODY, "units": bad_units}
            resp = client.post("/demo-request", json=body)
            assert resp.status_code == 400, f"{bad_units!r} should have been rejected"

        assert database.get_all_demo_requests() == []
    finally:
        os.unlink(db_path)

    print("✓ test_invalid_units_rejected: PASS")


def test_boolean_units_rejected():
    """
    bool is technically an int subclass in Python, so True/False could
    otherwise slip through int(units_raw) as 1/0 and pass the range check
    -- a separate test (not folded into test_invalid_units_rejected's loop)
    since two extra requests there would trip the per-IP rate limit.
    """
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        for bad_units in [True, False]:
            body = {**_VALID_BODY, "units": bad_units}
            resp = client.post("/demo-request", json=body)
            assert resp.status_code == 400, f"{bad_units!r} should have been rejected"

        assert database.get_all_demo_requests() == []
    finally:
        os.unlink(db_path)

    print("✓ test_boolean_units_rejected: PASS")


def test_overlong_message_is_truncated_not_rejected():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            mock_smtp_ssl, _ = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                client = app.test_client()
                body = {**_VALID_BODY, "message": "x" * 5000}
                resp = client.post("/demo-request", json=body)

            assert resp.status_code == 201, resp.get_json()
            saved = database.get_all_demo_requests()[0]
            assert len(saved["message"]) == 2000
    finally:
        os.unlink(db_path)

    print("✓ test_overlong_message_is_truncated_not_rejected: PASS")


def test_honeypot_field_silently_discards_submission():
    """
    A bot that fills every field it can find (including the hidden
    'website' honeypot) must get the SAME success response a real
    visitor gets -- but nothing is persisted and no email is sent.
    """
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                client = app.test_client()
                body = {**_VALID_BODY, "website": "http://spammy-bot.example"}
                resp = client.post("/demo-request", json=body)

            assert resp.status_code == 201, resp.get_json()
            assert "message" in resp.get_json()
            assert database.get_all_demo_requests() == [], "honeypot submission must not be persisted"
            assert mock_server.sendmail.call_count == 0, "honeypot submission must not trigger any email"
    finally:
        os.unlink(db_path)

    print("✓ test_honeypot_field_silently_discards_submission: PASS")


def test_submission_succeeds_with_no_email_credentials_configured():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMAIL_USER", None)
            os.environ.pop("EMAIL_APP_PASSWORD", None)

            client = app.test_client()
            resp = client.post("/demo-request", json=_VALID_BODY)

            assert resp.status_code == 201, resp.get_json()
            assert len(database.get_all_demo_requests()) == 1
    finally:
        os.unlink(db_path)

    print("✓ test_submission_succeeds_with_no_email_credentials_configured: PASS")


def test_submission_succeeds_when_smtp_raises():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            with mock.patch("smtplib.SMTP_SSL", side_effect=Exception("535 Authentication failed")):
                client = app.test_client()
                resp = client.post("/demo-request", json=_VALID_BODY)

            assert resp.status_code == 201, resp.get_json()
            assert len(database.get_all_demo_requests()) == 1
    finally:
        os.unlink(db_path)

    print("✓ test_submission_succeeds_when_smtp_raises: PASS")


def test_error_response_never_leaks_internal_detail():
    """A 400 response body must only ever contain the short, safe message we wrote -- never a stack trace or exception repr."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/demo-request", json={**_VALID_BODY, "units": "definitely-not-a-number"})

        assert resp.status_code == 400
        data = resp.get_json()
        assert set(data.keys()) == {"error"}
        assert "Traceback" not in data["error"]
        assert "Exception" not in data["error"]
    finally:
        os.unlink(db_path)

    print("✓ test_error_response_never_leaks_internal_detail: PASS")


def test_rate_limit_blocks_after_max_requests_per_ip():
    from app import api as api_module

    api_module._demo_request_rate_limiter.reset()
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        max_hits = api_module._demo_request_rate_limiter.max_hits

        for _ in range(max_hits):
            resp = client.post("/demo-request", json={**_VALID_BODY, "work_email": "ratelimit@example.com"})
            assert resp.status_code in (201, 400), resp.get_json()

        resp = client.post("/demo-request", json={**_VALID_BODY, "work_email": "ratelimit@example.com"})
        assert resp.status_code == 429, resp.get_json()
    finally:
        os.unlink(db_path)
        api_module._demo_request_rate_limiter.reset()

    print("✓ test_rate_limit_blocks_after_max_requests_per_ip: PASS")


def test_cross_origin_request_rejected_by_csrf_middleware():
    """
    /demo-request is state-changing and not in security.py's
    _CSRF_EXEMPT_PATHS, so the app-wide Origin/Referer check must reject a
    request carrying a disallowed Origin -- this is inherited from
    install_security(), not reimplemented per-route.
    """
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post(
            "/demo-request",
            json=_VALID_BODY,
            headers={"Origin": "https://evil.example.com"},
        )

        assert resp.status_code == 403, resp.get_json()
        assert database.get_all_demo_requests() == []
    finally:
        os.unlink(db_path)

    print("✓ test_cross_origin_request_rejected_by_csrf_middleware: PASS")


if __name__ == "__main__":
    test_valid_submission_succeeds_persists_and_sends_both_emails()
    test_submission_without_optional_message_succeeds()
    test_missing_name_rejected()
    test_missing_company_rejected()
    test_invalid_email_format_rejected()
    test_invalid_units_rejected()
    test_boolean_units_rejected()
    test_overlong_message_is_truncated_not_rejected()
    test_honeypot_field_silently_discards_submission()
    test_submission_succeeds_with_no_email_credentials_configured()
    test_submission_succeeds_when_smtp_raises()
    test_error_response_never_leaks_internal_detail()
    test_rate_limit_blocks_after_max_requests_per_ip()
    test_cross_origin_request_rejected_by_csrf_middleware()
    print("\nAll demo-request tests passed.")
