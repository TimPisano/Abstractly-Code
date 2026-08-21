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

import email
import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database, email_service

# Popped here (after app.api's own load_dotenv() has already run, so
# this can't be re-populated from backend/.env) so any /waitlist or
# /waitlist/<id>/approve call in a test that DOESN'T explicitly opt
# back into fake credentials via its own mock.patch.dict(os.environ,
# ...) can never reach real smtplib -- email_service._send()'s
# "not configured" fail-safe applies by default. Tests that want to
# exercise the "credentials configured" code path still can, by
# setting fake_env themselves (mock.patch.dict layers on top of
# whatever's ambient, it doesn't care that this file already popped
# the real values) -- this only removes the *implicit*, easy-to-miss
# reliance on whatever happens to be in the real environment.
#
# Added after finding this file itself (ironically, the one
# specifically about testing email safely) had three tests that
# assumed a call site was covered by mocking but weren't: two used a
# real-looking fake_env while only mocking ONE of the two functions
# join_waitlist() calls, and one made a bare /waitlist POST with no
# patching at all, relying entirely on whatever the ambient
# environment happened to have. All three attempted a real SMTP
# connection with real credentials whenever this file ran with real
# EMAIL_USER/EMAIL_APP_PASSWORD already in the environment (e.g. set
# in backend/.env for local delivery) -- see DECISIONS.md.
os.environ.pop("EMAIL_USER", None)
os.environ.pop("EMAIL_APP_PASSWORD", None)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _login_as_admin(client):
    """
    GET /waitlist and POST /waitlist/<id>/approve now require an admin
    session (see app/auth.py's require_admin) -- this sets one directly
    via Flask's session_transaction(), the standard way to test a
    session-gated route without driving an actual login POST through
    bcrypt for every test that needs one.
    """
    with client.session_transaction() as sess:
        sess["admin_authenticated"] = True
        sess["admin_email"] = "timmypisano24@gmail.com"


def test_signup_succeeds_with_no_email_credentials_configured():
    """
    A signup with no EMAIL_USER/EMAIL_APP_PASSWORD configured must
    still succeed and persist. Deliberately patches those two vars
    missing regardless of the ambient dev environment's real state
    (backend/.env now has real credentials configured for actual
    delivery) — this test is about the missing-credentials code path
    specifically, not about what happens to be set locally right now.
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

            # And the lower-level function itself must report the
            # failure honestly (False), not silently pretend it worked
            # — kept inside the patched block so it's still exercising
            # the missing-credentials path, not the ambient environment.
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
            with mock.patch("app.email_service.send_waitlist_confirmation_email") as mock_send, \
                 mock.patch("app.email_service.send_admin_new_request_notification") as mock_admin_send:
                # join_waitlist() calls both functions -- both must be
                # mocked, or the unmocked one runs for real against the
                # fake-but-present credentials above and attempts an
                # actual SMTP connection (auth would fail, but the
                # point of this file is that NEITHER ever happens).
                mock_send.return_value = True
                mock_admin_send.return_value = True
                client = app.test_client()

                resp1 = client.post("/waitlist", json={"email": "repeat@example.com"})
                assert resp1.status_code == 201
                assert mock_send.call_count == 1

                resp2 = client.post("/waitlist", json={"email": "repeat@example.com"})
                assert resp2.status_code == 200
                assert mock_send.call_count == 1, "a duplicate submission must not trigger a second send"
                assert mock_admin_send.call_count == 1, "admin notification must also only fire on the first submission"
    finally:
        os.unlink(db_path)

    print("✓ test_duplicate_signup_does_not_resend_email: PASS")


def test_signup_notifies_admin_with_mocked_smtp():
    """
    A signup must send TWO emails: a confirmation to the requester and a
    notification to ADMIN_EMAIL so the admin actually finds out without
    having to keep the dashboard open.
    """
    db_path = _fresh_temp_db()
    try:
        fake_env = {
            "EMAIL_USER": "fake@example.com",
            "EMAIL_APP_PASSWORD": "fake-app-password",
            "ADMIN_EMAIL": "timmypisano24@gmail.com",
        }
        with mock.patch.dict(os.environ, fake_env):
            mock_server = mock.MagicMock()
            mock_smtp_ssl = mock.MagicMock()
            mock_smtp_ssl.return_value.__enter__.return_value = mock_server

            with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
                client = app.test_client()
                resp = client.post("/waitlist", json={"email": "newrequester@example.com"})

            assert resp.status_code == 201, resp.get_json()
            assert mock_server.sendmail.call_count == 2

            recipients = [call.args[1] for call in mock_server.sendmail.call_args_list]
            assert ["newrequester@example.com"] in recipients
            assert ["timmypisano24@gmail.com"] in recipients

            admin_call = next(
                call for call in mock_server.sendmail.call_args_list
                if call.args[1] == ["timmypisano24@gmail.com"]
            )
            assert "newrequester@example.com" in admin_call.args[2]
    finally:
        os.unlink(db_path)

    print("✓ test_signup_notifies_admin_with_mocked_smtp: PASS")


def test_admin_notification_escapes_html_in_requester_email():
    """
    The waitlist's email format check only requires something shaped
    like an email address — it doesn't forbid HTML metacharacters in the
    local part. The admin notification embeds the requester's address
    in an HTML email, so it must escape it, or a crafted "address" could
    inject markup into the admin's inbox.
    """
    fake_env = {"EMAIL_USER": "fake@example.com", "EMAIL_APP_PASSWORD": "fake-app-password"}
    malicious_email = "<img src=x onerror=alert(1)>@evil.com"
    with mock.patch.dict(os.environ, {**fake_env, "ADMIN_EMAIL": "timmypisano24@gmail.com"}):
        mock_server = mock.MagicMock()
        mock_smtp_ssl = mock.MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            sent = email_service.send_admin_new_request_notification(malicious_email)

        assert sent is True
        # The raw address legitimately appears in the plain-text MIME
        # part (no HTML there, nothing to inject) -- only the html part
        # needs escaping, so parse the multipart message and check that
        # part specifically rather than the whole raw string.
        raw_message = mock_server.sendmail.call_args[0][2]
        parsed = email.message_from_string(raw_message)
        html_part = next(part for part in parsed.walk() if part.get_content_type() == "text/html")
        html_payload = html_part.get_payload(decode=True).decode("utf-8")
        assert "<img src=x onerror=alert(1)>" not in html_payload, "raw HTML must not appear unescaped in the email's HTML part"
        assert "&lt;img src=x onerror=alert(1)&gt;" in html_payload

    print("✓ test_admin_notification_escapes_html_in_requester_email: PASS")


def test_admin_notification_noop_without_admin_email():
    """If ADMIN_EMAIL isn't configured, the notification is skipped (returns False), not an error."""
    with mock.patch.dict(os.environ, {"EMAIL_USER": "fake@example.com", "EMAIL_APP_PASSWORD": "fake"}, clear=False):
        os.environ.pop("ADMIN_EMAIL", None)
        sent = email_service.send_admin_new_request_notification("someone@example.com")
        assert sent is False

    print("✓ test_admin_notification_noop_without_admin_email: PASS")


def test_signup_succeeds_when_admin_notification_fails():
    """Same best-effort guarantee as the requester confirmation email, applied to the admin notification."""
    db_path = _fresh_temp_db()
    try:
        fake_env = {
            "EMAIL_USER": "fake@example.com",
            "EMAIL_APP_PASSWORD": "fake-app-password",
            "ADMIN_EMAIL": "timmypisano24@gmail.com",
        }
        with mock.patch.dict(os.environ, fake_env):
            with mock.patch(
                "app.email_service.send_admin_new_request_notification",
                side_effect=Exception("should never propagate"),
            ), mock.patch("app.email_service.send_waitlist_confirmation_email") as mock_confirm:
                # join_waitlist() calls both functions -- the confirmation
                # one must be mocked too, or it runs for real against the
                # fake-but-present credentials above (this test is
                # specifically about the ADMIN notification failing, not
                # about exercising a real SMTP connection for the other one).
                mock_confirm.return_value = True
                client = app.test_client()
                resp = client.post("/waitlist", json={"email": "stillworks@example.com"})

        assert resp.status_code == 201, resp.get_json()
        signups = database.get_all_waitlist_signups()
        assert any(s["email"] == "stillworks@example.com" for s in signups)
    finally:
        os.unlink(db_path)

    print("✓ test_signup_succeeds_when_admin_notification_fails: PASS")


def test_send_side_rate_limit_caps_repeated_sends_to_same_recipient():
    """
    Defense-in-depth safety net added after the real incident (see
    DECISIONS.md): even with real-looking credentials and a caller that
    misfires repeatedly, no single recipient can receive more than
    email_service._RATE_LIMIT_MAX_PER_WINDOW emails within
    _RATE_LIMIT_WINDOW_SECONDS. Uses a recipient address not touched by
    any other test in this file, so this test's cap-tripping can't
    affect (or be affected by) other tests sharing this process.
    """
    email_service._reset_rate_limit_state_for_tests()
    target = "ratelimit-target@example.com"
    fake_env = {"EMAIL_USER": "fake@example.com", "EMAIL_APP_PASSWORD": "fake-app-password"}
    with mock.patch.dict(os.environ, fake_env):
        mock_server = mock.MagicMock()
        mock_smtp_ssl = mock.MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            results = [
                email_service.send_waitlist_confirmation_email(target)
                for _ in range(email_service._RATE_LIMIT_MAX_PER_WINDOW + 3)
            ]

        assert results[:email_service._RATE_LIMIT_MAX_PER_WINDOW] == [True] * email_service._RATE_LIMIT_MAX_PER_WINDOW, \
            "every send within the cap must still succeed"
        assert results[email_service._RATE_LIMIT_MAX_PER_WINDOW:] == [False, False, False], \
            "sends beyond the cap must be blocked, not attempted"
        assert mock_server.sendmail.call_count == email_service._RATE_LIMIT_MAX_PER_WINDOW, \
            "smtplib must never actually be called for a rate-limited send"

    email_service._reset_rate_limit_state_for_tests()
    print("✓ test_send_side_rate_limit_caps_repeated_sends_to_same_recipient: PASS")


def test_send_side_rate_limit_is_per_recipient():
    """Hitting the cap for one recipient must not block sends to a different recipient."""
    email_service._reset_rate_limit_state_for_tests()
    fake_env = {"EMAIL_USER": "fake@example.com", "EMAIL_APP_PASSWORD": "fake-app-password"}
    with mock.patch.dict(os.environ, fake_env):
        mock_server = mock.MagicMock()
        mock_smtp_ssl = mock.MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server

        with mock.patch("smtplib.SMTP_SSL", mock_smtp_ssl):
            for _ in range(email_service._RATE_LIMIT_MAX_PER_WINDOW):
                email_service.send_waitlist_confirmation_email("ratelimit-a@example.com")
            # Recipient A is now at its cap; a different recipient must be unaffected.
            sent = email_service.send_waitlist_confirmation_email("ratelimit-b@example.com")

        assert sent is True, "a different recipient's own quota must be independent"

    email_service._reset_rate_limit_state_for_tests()
    print("✓ test_send_side_rate_limit_is_per_recipient: PASS")


def test_approval_sends_email_and_still_succeeds_if_it_fails():
    """Approving a signup must attempt an approval email, and must succeed regardless of whether that send works."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/waitlist", json={"email": "approveme@example.com"})
        signup_id = database.get_all_waitlist_signups()[0]["id"]
        _login_as_admin(client)

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
    test_signup_notifies_admin_with_mocked_smtp()
    test_admin_notification_escapes_html_in_requester_email()
    test_admin_notification_noop_without_admin_email()
    test_signup_succeeds_when_admin_notification_fails()
    test_send_side_rate_limit_caps_repeated_sends_to_same_recipient()
    test_send_side_rate_limit_is_per_recipient()
    test_approval_sends_email_and_still_succeeds_if_it_fails()
    print("\nAll waitlist-email tests passed.")
