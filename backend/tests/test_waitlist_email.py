"""
Tests for real email sending on the waitlist flow (email_service.py)
and, critically, that the waitlist signup/approval endpoints never fail
because an email failed to send.

Uses Flask's in-process test_client() rather than hitting a separately
running live server (unlike most of this suite's live-API tests) —
that's what lets these tests monkeypatch smtplib.SMTP_SSL directly to
simulate a real send succeeding or failing, which isn't possible against
a server running in its own separate process. Points database.py at an
isolated temp SQLite file so nothing here touches the real dev database.
"""

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database, email_service


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def test_signup_succeeds_with_no_email_credentials_configured():
    """
    The real current state of this environment: EMAIL_USER/
    EMAIL_APP_PASSWORD are not set. A waitlist signup must still
    succeed and persist — this is the exact scenario the task asked to
    have explicitly verified.
    """
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMAIL_USER", None)
            os.environ.pop("EMAIL_APP_PASSWORD", None)

            client = app.test_client()
            resp = client.post("/waitlist", json={"email": "noemail@example.com"})

            assert resp.status_code == 201, resp.get_json()
            assert "message" in resp.get_json()

            signups = database.get_all_waitlist_signups()
            assert any(s["email"] == "noemail@example.com" for s in signups), \
                "signup must be persisted even though no email could be sent"

        # And the lower-level function itself must report the failure
        # honestly (False), not silently pretend it worked.
        sent = email_service.send_waitlist_confirmation_email("noemail@example.com")
        assert sent is False
    finally:
        os.unlink(db_path)

    print("✓ test_signup_succeeds_with_no_email_credentials_configured: PASS")


def test_signup_succeeds_when_smtp_raises():
    """
    Credentials ARE configured (fake ones), but the actual SMTP call
    fails (bad credentials, rate limit, network error — all surface as
    smtplib raising). The signup must still succeed.
    """
    db_path = _fresh_temp_db()
    try:
        fake_env = {"EMAIL_USER": "fake@example.com", "EMAIL_APP_PASSWORD": "not-a-real-password"}
        with mock.patch.dict(os.environ, fake_env):
            with mock.patch("smtplib.SMTP_SSL", side_effect=Exception("535 Authentication failed")):
                client = app.test_client()
                resp = client.post("/waitlist", json={"email": "willfail@example.com"})

                assert resp.status_code == 201, resp.get_json()

                signups = database.get_all_waitlist_signups()
                assert any(s["email"] == "willfail@example.com" for s in signups), \
                    "signup must be persisted even when the SMTP send raises"

            with mock.patch("smtplib.SMTP_SSL", side_effect=Exception("535 Authentication failed")):
                sent = email_service.send_waitlist_confirmation_email("willfail@example.com")
                assert sent is False
    finally:
        os.unlink(db_path)

    print("✓ test_signup_succeeds_when_smtp_raises: PASS")


def test_email_sent_successfully_with_mocked_smtp():
    """
    The happy path, verified without touching a real Gmail account:
    with fake-but-present credentials and a mocked SMTP_SSL that
    succeeds, send_waitlist_confirmation_email must return True and
    must have actually called login()/sendmail() with the right
    recipient.
    """
    fake_env = {"EMAIL_USER": "fake@example.com", "EMAIL_APP_PASSWORD": "fake-app-password"}
    with mock.patch.dict(os.environ, fake_env):
        mock_server = mock.MagicMock()
        mock_smtp_ssl = mock.MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            sent = email_service.send_waitlist_confirmation_email("realtarget@example.com")

        assert sent is True
        mock_server.login.assert_called_once_with("fake@example.com", "fake-app-password")
        assert mock_server.sendmail.call_count == 1
        call_args = mock_server.sendmail.call_args
        assert call_args[0][0] == "fake@example.com"  # from
        assert call_args[0][1] == ["realtarget@example.com"]  # to
        assert "We've received your request" in call_args[0][2]  # message body includes the subject line

    print("✓ test_email_sent_successfully_with_mocked_smtp: PASS")


def test_duplicate_signup_does_not_resend_email():
    """
    Resubmitting the same email a second time must not trigger a second
    send — otherwise anyone could spam a stranger's inbox just by
    reposting their address repeatedly.
    """
    db_path = _fresh_temp_db()
    try:
        fake_env = {"EMAIL_USER": "fake@example.com", "EMAIL_APP_PASSWORD": "fake-app-password"}
        with mock.patch.dict(os.environ, fake_env):
            with mock.patch("app.email_service.send_waitlist_confirmation_email") as mock_send:
                mock_send.return_value = True
                client = app.test_client()

                resp1 = client.post("/waitlist", json={"email": "repeat@example.com"})
                assert resp1.status_code == 201
                assert mock_send.call_count == 1

                resp2 = client.post("/waitlist", json={"email": "repeat@example.com"})
                assert resp2.status_code == 200
                assert mock_send.call_count == 1, "a duplicate submission must not trigger a second send"
    finally:
        os.unlink(db_path)

    print("✓ test_duplicate_signup_does_not_resend_email: PASS")


def test_approval_sends_email_and_still_succeeds_if_it_fails():
    """Approving a signup must attempt an approval email, and must succeed regardless of whether that send works."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/waitlist", json={"email": "approveme@example.com"})
        signup_id = database.get_all_waitlist_signups()[0]["id"]

        with mock.patch("app.email_service.send_waitlist_approval_email") as mock_send:
            mock_send.side_effect = Exception("should never propagate — send_* must catch its own errors")
            # send_waitlist_approval_email itself never raises in real
            # code (see email_service.py) — this mock simulates a
            # defensive-programming failure to prove the ROUTE doesn't
            # depend on that guarantee holding, i.e. it doesn't wrap the
            # call in its own try/except assuming the callee is safe.
            # If this test fails with an unhandled exception, that's a
            # real gap; Flask's own error handler should still turn it
            # into a clean response, not a raw 500 traceback either way.
            resp = client.post(f"/waitlist/{signup_id}/approve")

        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["status"] == "approved"

        signups = database.get_all_waitlist_signups()
        assert signups[0]["status"] == "approved", "status must still flip even if the email attempt blows up"
    finally:
        os.unlink(db_path)

    print("✓ test_approval_sends_email_and_still_succeeds_if_it_fails: PASS")


if __name__ == "__main__":
    test_signup_succeeds_with_no_email_credentials_configured()
    test_signup_succeeds_when_smtp_raises()
    test_email_sent_successfully_with_mocked_smtp()
    test_duplicate_signup_does_not_resend_email()
    test_approval_sends_email_and_still_succeeds_if_it_fails()
    print("\nAll waitlist-email tests passed.")
