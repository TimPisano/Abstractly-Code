"""
Tests for the landing page's "Book a Demo" form (POST /demo-request):
validation (client-independent, server-side), the honeypot spam trap, the
per-IP rate limit, and the same "email must never block a real submission"
guarantee the waitlist flow already has.

Follows test_waitlist_email.py's pattern: Flask's in-process test_client(),
mocked smtplib.SMTP_SSL, an isolated temp SQLite file per test.
"""

import email
import email.header
import json
import os
import re
import subprocess
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
    "CALENDLY_URL": "https://calendly.com/test-host/intro-call",
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
    email_service._reset_rate_limit_state_for_tests()
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
            assert [_FAKE_ENV["ADMIN_EMAIL"]] in recipients
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
    email_service._reset_rate_limit_state_for_tests()
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


def _sent_messages(mock_server):
    """{recipient: parsed email.message.Message} for every mocked sendmail call."""
    return {
        call.args[1][0]: email.message_from_string(call.args[2])
        for call in mock_server.sendmail.call_args_list
    }


def _body_text(msg, subtype):
    for part in msg.walk():
        if part.get_content_type() == f"text/{subtype}":
            return part.get_payload(decode=True).decode()
    return ""


def test_notification_goes_to_admin_email_with_reply_to_the_visitor():
    """The founder gets every field at ADMIN_EMAIL and can hit Reply in
    Gmail to answer the visitor directly. Regression: it used to go to
    tim@getabstractly.com, which forwards back into the sending Gmail
    account, where Gmail hides it."""
    db_path = _fresh_temp_db()
    try:
        env = dict(_FAKE_ENV, ADMIN_EMAIL="founder-inbox@example.com")
        with mock.patch.dict(os.environ, env):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                resp = app.test_client().post("/demo-request", json=_VALID_BODY)
        assert resp.status_code == 201, resp.get_json()

        sent = _sent_messages(mock_server)
        assert set(sent) == {"founder-inbox@example.com", "jane@example.com"}, list(sent)
        assert "tim@getabstractly.com" not in sent
        note = sent["founder-inbox@example.com"]
        assert note["Reply-To"] == "jane@example.com", note["Reply-To"]
        text = _body_text(note, "plain")
        for value in ("Jane Doe", "jane@example.com", "Example Capital Partners",
                      "240", _VALID_BODY["message"]):
            assert value in text, (value, text)
    finally:
        os.unlink(db_path)

    print("✓ test_notification_goes_to_admin_email_with_reply_to_the_visitor: PASS")


def test_missing_admin_email_logs_error_and_requester_still_gets_confirmation():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            os.environ.pop("ADMIN_EMAIL", None)
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl), _CapturedLogs("app.email_service") as logs:
                resp = app.test_client().post("/demo-request", json=_VALID_BODY)
        assert resp.status_code == 201
        assert list(_sent_messages(mock_server)) == ["jane@example.com"]
        assert any("ADMIN_EMAIL is not set" in m for m in logs.errors()), logs.errors()
    finally:
        os.unlink(db_path)

    print("✓ test_missing_admin_email_logs_error_and_requester_still_gets_confirmation: PASS")


_TEST_CALENDLY_URL = "https://calendly.com/test-host/intro-call"


class _CapturedLogs(list):
    """Collects log records from one logger for the duration of a with-block."""

    def __init__(self, logger_name):
        super().__init__()
        self._logger = __import__("logging").getLogger(logger_name)
        self._handler = __import__("logging").Handler()
        self._handler.emit = self.append

    def __enter__(self):
        # run_all_tests.py may raise the log level; capture INFO regardless.
        self._old_level = self._logger.level
        self._logger.setLevel("INFO")
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, *exc):
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._old_level)

    def errors(self):
        return [r.getMessage() for r in self if r.levelname == "ERROR"]


def test_confirmation_includes_calendly_link_and_replies_to_tim():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {**_FAKE_ENV, "CALENDLY_URL": _TEST_CALENDLY_URL}):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                resp = app.test_client().post("/demo-request", json=_VALID_BODY)
        assert resp.status_code == 201
        assert resp.get_json()["message"] == api_module._DEMO_REQUEST_SUCCESS_WITH_LINK_MESSAGE

        confirm = _sent_messages(mock_server)["jane@example.com"]
        assert confirm["Reply-To"] == "tim@getabstractly.com"
        assert _TEST_CALENDLY_URL in _body_text(confirm, "plain")
        assert f'href="{_TEST_CALENDLY_URL}"' in _body_text(confirm, "html")
    finally:
        os.unlink(db_path)

    print("✓ test_confirmation_includes_calendly_link_and_replies_to_tim: PASS")


def test_missing_calendly_url_logs_error_and_sends_confirmation_without_a_link():
    """Regression: an unset CALENDLY_URL used to fall back silently to a
    hard-coded link. Now it's an ERROR naming the variable, the visitor
    still gets an acknowledgement (minus the link), and the form doesn't
    claim a link was emailed."""
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            os.environ.pop("CALENDLY_URL", None)
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl), _CapturedLogs("app.email_service") as logs:
                resp = app.test_client().post("/demo-request", json=_VALID_BODY)

        assert resp.status_code == 201
        assert resp.get_json()["message"] == api_module._DEMO_REQUEST_SUCCESS_MESSAGE
        assert len(database.get_all_demo_requests()) == 1
        assert any("CALENDLY_URL is not set" in m for m in logs.errors()), logs.errors()

        confirm = _sent_messages(mock_server)["jane@example.com"]
        assert "calendly.com" not in _body_text(confirm, "plain")
        assert "Grab a time" not in _body_text(confirm, "plain")
        assert "just reply here with a few times" in _body_text(confirm, "plain").lower()
        assert confirm["Reply-To"] == "tim@getabstractly.com"
    finally:
        os.unlink(db_path)

    print("✓ test_missing_calendly_url_logs_error_and_sends_confirmation_without_a_link: PASS")


def test_non_https_calendly_url_is_treated_as_missing():
    with mock.patch.dict(os.environ, {"CALENDLY_URL": "javascript:alert(1)"}):
        assert email_service.calendly_url() is None
    with mock.patch.dict(os.environ, {"CALENDLY_URL": "  " + _TEST_CALENDLY_URL + "  "}):
        assert email_service.calendly_url() == _TEST_CALENDLY_URL

    print("✓ test_non_https_calendly_url_is_treated_as_missing: PASS")


def test_missing_email_credentials_log_an_error_naming_the_variable():
    """Regression: missing SMTP credentials used to be a WARNING that
    didn't say which one. Now it's an ERROR naming the missing variable,
    and the submission is still saved."""
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {"EMAIL_USER": "fake@example.com", "CALENDLY_URL": _TEST_CALENDLY_URL}):
            os.environ.pop("EMAIL_APP_PASSWORD", None)
            with _CapturedLogs("app.email_service") as logs:
                resp = app.test_client().post("/demo-request", json=_VALID_BODY)

        assert resp.status_code == 201
        # No email went out, so the form must not claim one did.
        assert resp.get_json()["message"] == api_module._DEMO_REQUEST_SUCCESS_MESSAGE
        assert len(database.get_all_demo_requests()) == 1
        errors = logs.errors()
        assert any("EMAIL_APP_PASSWORD not set" in m and "jane@example.com" in m for m in errors), errors
        assert not any("EMAIL_USER and" in m for m in errors), errors
    finally:
        os.unlink(db_path)

    print("✓ test_missing_email_credentials_log_an_error_naming_the_variable: PASS")


def test_from_header_keeps_a_parseable_sender_address():
    """Regression: the em dash in the display name made Python encode the
    whole From header, address included, so no client could parse a
    sender out of it (parseaddr returned an empty address)."""
    from email.utils import parseaddr
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {**_FAKE_ENV, "CALENDLY_URL": _TEST_CALENDLY_URL}):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                app.test_client().post("/demo-request", json=_VALID_BODY)
        confirm = _sent_messages(mock_server)["jane@example.com"]
        name, address = parseaddr(confirm["From"])
        assert address == "fake@example.com", confirm["From"]
        assert str(email.header.make_header(email.header.decode_header(name))) == "Tim Pisano — Abstractly"
    finally:
        os.unlink(db_path)

    print("✓ test_from_header_keeps_a_parseable_sender_address: PASS")


def test_public_config_serves_calendly_url_without_login():
    client = app.test_client()
    with mock.patch.dict(os.environ, {"CALENDLY_URL": _TEST_CALENDLY_URL}):
        resp = client.get("/public-config")
    assert resp.status_code == 200
    assert resp.get_json() == {"calendly_url": _TEST_CALENDLY_URL}

    with mock.patch.dict(os.environ, {}):
        os.environ.pop("CALENDLY_URL", None)
        resp = client.get("/public-config")
    assert resp.status_code == 200
    assert resp.get_json() == {"calendly_url": None}

    print("✓ test_public_config_serves_calendly_url_without_login: PASS")


def test_requester_confirmation_is_sent_with_link_and_logged():
    """The requester's own email: sent to the address they typed, with the
    CALENDLY_URL link and Reply-To tim@getabstractly.com, and a success
    line in the log naming the recipient (so "did it send?" is answerable
    from the Render logs)."""
    db_path = _fresh_temp_db()
    try:
        body = dict(_VALID_BODY, work_email="requester@example.org")
        with mock.patch.dict(os.environ, {**_FAKE_ENV, "CALENDLY_URL": _TEST_CALENDLY_URL}):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl), _CapturedLogs("app.email_service") as logs:
                resp = app.test_client().post("/demo-request", json=body)
        assert resp.status_code == 201
        assert resp.get_json()["message"] == api_module._DEMO_REQUEST_SUCCESS_WITH_LINK_MESSAGE

        confirm = _sent_messages(mock_server)["requester@example.org"]
        assert confirm["To"] == "requester@example.org"
        assert confirm["Reply-To"] == "tim@getabstractly.com"
        assert _TEST_CALENDLY_URL in _body_text(confirm, "plain")
        infos = [r.getMessage() for r in logs if r.levelname == "INFO"]
        assert any("Email sent to requester@example.org" in m for m in infos), infos
        assert not logs.errors(), logs.errors()
    finally:
        os.unlink(db_path)

    print("✓ test_requester_confirmation_is_sent_with_link_and_logged: PASS")


def test_requester_send_failure_logs_the_exact_error():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {**_FAKE_ENV, "CALENDLY_URL": _TEST_CALENDLY_URL}):
            boom = mock.MagicMock(side_effect=OSError("[Errno 101] Network is unreachable"))
            with mock.patch("smtplib.SMTP_SSL", boom), _CapturedLogs("app.email_service") as logs:
                resp = app.test_client().post("/demo-request", json=_VALID_BODY)
        assert resp.status_code == 201
        # Nothing was emailed, so the form must not say a link was.
        assert resp.get_json()["message"] == api_module._DEMO_REQUEST_SUCCESS_MESSAGE
        assert any("Email FAILED to jane@example.com" in m and "OSError: [Errno 101] Network is unreachable" in m
                   for m in logs.errors()), logs.errors()
    finally:
        os.unlink(db_path)

    print("✓ test_requester_send_failure_logs_the_exact_error: PASS")


def test_refused_recipient_is_logged_as_a_failure():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {**_FAKE_ENV, "CALENDLY_URL": _TEST_CALENDLY_URL}):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            mock_server.sendmail.side_effect = lambda frm, to, msg: (
                {to[0]: (550, b"5.1.1 No such user")} if to[0] == "jane@example.com" else {})
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl), _CapturedLogs("app.email_service") as logs:
                resp = app.test_client().post("/demo-request", json=_VALID_BODY)
        assert resp.get_json()["message"] == api_module._DEMO_REQUEST_SUCCESS_MESSAGE
        assert any("Email FAILED to jane@example.com" in m and "No such user" in m for m in logs.errors()), logs.errors()
    finally:
        os.unlink(db_path)

    print("✓ test_refused_recipient_is_logged_as_a_failure: PASS")


def _confirmation_for(body):
    """POST a demo request with mocked SMTP; return the requester's parsed confirmation."""
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                resp = app.test_client().post("/demo-request", json=body)
        assert resp.status_code == 201, resp.get_json()
        return _sent_messages(mock_server)[body["work_email"]]
    finally:
        os.unlink(db_path)


def test_confirmation_reads_as_a_personal_note_from_the_founder():
    confirm = _confirmation_for(_VALID_BODY)
    assert confirm["Subject"] == "Thanks for reaching out, Jane"
    assert confirm["Reply-To"] == "tim@getabstractly.com"

    plain = _body_text(confirm, "plain")
    lines = plain.splitlines()
    assert lines[0] == "Hi Jane,"
    assert ("Thanks for requesting a demo of Abstractly. I'm Tim, the founder, and I "
            "read every request that comes in personally.") in plain
    assert ("I'd love to hear how Example Capital Partners handles leases and rent rolls "
            "today, then show you how Abstractly catches the mismatches before they cost "
            "you money. It only takes about 20 minutes.") in plain
    assert f"Grab a time that works for you: {_FAKE_ENV['CALENDLY_URL']}" in plain
    assert "If none of those times fit, just reply here and I'll work around your schedule." in plain
    assert lines[-3:] == ["Talk soon,", "Tim Pisano", "Founder, Abstractly"]
    assert "Doe" not in plain  # first name only

    page = _body_text(confirm, "html")
    assert 'name="viewport"' in page
    assert f'href="{_FAKE_ENV["CALENDLY_URL"]}"' in page
    assert "Grab a time that works for you &rarr;</a>" in page
    assert "Hi Jane," in page
    # The light "normal email" layout, not the branded card template.
    assert "<h1" not in page and "letter-spacing:2px" not in page

    print("✓ test_confirmation_reads_as_a_personal_note_from_the_founder: PASS")


def test_confirmation_first_name_and_company_fallbacks():
    assert email_service._first_name("jacinta pisano") == "Jacinta"
    assert email_service._first_name("  McKenzie  Smith ") == "McKenzie"
    assert email_service._first_name("") == "there"

    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, _FAKE_ENV):
            mock_smtp_ssl, mock_server = _mocked_smtp()
            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                email_service.send_demo_request_confirmation("x@example.com", "sam", "   ")
        confirm = _sent_messages(mock_server)["x@example.com"]
    finally:
        os.unlink(db_path)
    assert confirm["Subject"] == "Thanks for reaching out, Sam"
    plain = _body_text(confirm, "plain")
    assert "I'd love to hear how your team handles leases and rent rolls today" in plain
    assert "how  handles" not in plain

    print("✓ test_confirmation_first_name_and_company_fallbacks: PASS")


def test_confirmation_escapes_what_the_visitor_typed():
    confirm = _confirmation_for(dict(_VALID_BODY, name="<b>Jane</b> Doe", company="Acme & <i>Co</i>"))
    page = _body_text(confirm, "html")
    assert "<b>Jane" not in page and "<i>Co</i>" not in page
    assert "Acme &amp; &lt;i&gt;Co&lt;/i&gt;" in page

    print("✓ test_confirmation_escapes_what_the_visitor_typed: PASS")


def test_reply_to_cannot_inject_extra_headers():
    """Defence in depth: the route's email regex already rejects whitespace,
    but _send must never let a CR/LF in a Reply-To add headers."""
    with mock.patch.dict(os.environ, _FAKE_ENV):
        email_service._reset_rate_limit_state_for_tests()
        mock_smtp_ssl, mock_server = _mocked_smtp()
        with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            email_service.send_demo_request_notification(
                "Eve", "eve@example.com\r\nBcc: victim@example.com", "X", 10, None)
        raw = mock_server.sendmail.call_args.args[2]
    headers = email.message_from_string(raw)
    assert headers["Bcc"] is None, raw
    assert headers["Reply-To"] == "tim@getabstractly.com", headers["Reply-To"]

    print("✓ test_reply_to_cannot_inject_extra_headers: PASS")


def test_request_from_getabstractly_origin_is_accepted_with_production_config():
    """The production bug: the site moved to getabstractly.com and the API
    rejected its Origin, so the form showed "Couldn't reach the server".
    Boots the app in a fresh process with ADMIN_ALLOWED_ORIGINS set to
    exactly what render.yaml gives abstractly-api (the list is read once
    at import), then sends a real browser-shaped preflight + POST from each
    public origin. Email is mocked; no network."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    with open(os.path.join(root, "render.yaml")) as f:
        api_block = f.read().split("name: abstractly-api", 1)[1].split("\n  - type: ", 1)[0]
    prod_origins = re.search(r"key: ADMIN_ALLOWED_ORIGINS\s+value: (\S+)", api_block).group(1)

    script = r"""
import json, os, sys, tempfile, unittest.mock as mock
sys.path.insert(0, os.getcwd())
from app.api import app
from app import database
tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
database.configure(tmp.name); database.init_db()
out = {}
with mock.patch("smtplib.SMTP_SSL"):
    client = app.test_client()
    for origin in sys.argv[1:]:
        pre = client.options("/demo-request", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"})
        resp = client.post("/demo-request", headers={"Origin": origin}, json={
            "name": "Jane Doe", "work_email": "jane@example.com",
            "company": "Example Capital", "units": 240})
        out[origin] = [pre.headers.get("Access-Control-Allow-Origin"),
                       resp.status_code, resp.headers.get("Access-Control-Allow-Origin")]
os.unlink(tmp.name)
print(json.dumps(out))
"""
    env = {k: v for k, v in os.environ.items() if k not in ("EMAIL_USER", "EMAIL_APP_PASSWORD")}
    env["ADMIN_ALLOWED_ORIGINS"] = prod_origins
    origins = ["https://getabstractly.com", "https://www.getabstractly.com",
               "https://abstractly-n0id.onrender.com", "https://evil.example.com"]
    proc = subprocess.run([sys.executable, "-c", script, *origins],
                          cwd=os.path.join(root, "backend"), env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    for origin in origins[:3]:
        preflight_allow, status, post_allow = result[origin]
        assert preflight_allow == origin, (origin, result[origin])
        assert status == 201, (origin, result[origin])
        assert post_allow == origin, (origin, result[origin])
    # ...and the allow-list still means something.
    assert result["https://evil.example.com"][1] == 403, result

    print("✓ test_request_from_getabstractly_origin_is_accepted_with_production_config: PASS")


def test_line_break_in_company_still_delivers_notification():
    """A CR/LF in a user-supplied field that reaches the Subject must not
    make the notification fail to build (the stdlib refuses such headers,
    and the failure was swallowed, so Tim silently got nothing)."""
    with mock.patch.dict(os.environ, _FAKE_ENV):
        email_service._reset_rate_limit_state_for_tests()
        mock_smtp_ssl, mock_server = _mocked_smtp()
        with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            sent = email_service.send_demo_request_notification(
                "Eve", "eve@example.com", "Acme\r\nBcc: victim@example.com", 10, None)
    assert sent is True
    headers = email.message_from_string(mock_server.sendmail.call_args.args[2])
    assert headers["Bcc"] is None
    assert "Acme" in headers["Subject"]

    print("✓ test_line_break_in_company_still_delivers_notification: PASS")


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
    test_notification_goes_to_admin_email_with_reply_to_the_visitor()
    test_missing_admin_email_logs_error_and_requester_still_gets_confirmation()
    test_confirmation_includes_calendly_link_and_replies_to_tim()
    test_missing_calendly_url_logs_error_and_sends_confirmation_without_a_link()
    test_non_https_calendly_url_is_treated_as_missing()
    test_missing_email_credentials_log_an_error_naming_the_variable()
    test_from_header_keeps_a_parseable_sender_address()
    test_public_config_serves_calendly_url_without_login()
    test_requester_confirmation_is_sent_with_link_and_logged()
    test_confirmation_reads_as_a_personal_note_from_the_founder()
    test_confirmation_first_name_and_company_fallbacks()
    test_confirmation_escapes_what_the_visitor_typed()
    test_requester_send_failure_logs_the_exact_error()
    test_refused_recipient_is_logged_as_a_failure()
    test_reply_to_cannot_inject_extra_headers()
    test_request_from_getabstractly_origin_is_accepted_with_production_config()
    test_line_break_in_company_still_delivers_notification()
    print("\nAll demo-request tests passed.")
