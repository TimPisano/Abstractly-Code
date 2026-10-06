"""
Tests for feature/auth-flow: self-serve signup by emailed link, the
upgraded forgot-password flow, "Keep me signed in", sign-out-everywhere
on reset, and the rate limits around all of it.

Same conventions as test_password_reset.py: _fresh_temp_db() + Flask
test_client(). Email is captured at email_service._send (so the real
subject/text/HTML are checked) and never reaches SMTP, and the
background-thread send is made synchronous so assertions don't race it.
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import api as api_module
from app import database, email_service, password_rules, usage_limits, usage_limits_config
from app.auth import hash_password

GOOD_PASSWORD = "maple ridge closing day"
OTHER_PASSWORD = "a different long phrase"
SIGNUP_EMAIL = "jordan@mapleridge-capital.test"

_outbox = []


def _capture_send(to_email, subject, text_body, html_body, reply_to=None):
    _outbox.append({"to": to_email, "subject": subject, "text": text_body, "html": html_body})
    return True


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


class _Env:
    """Fresh DB, flag on, mail captured, every limiter cleared."""

    def __enter__(self):
        self.db = _fresh_temp_db()
        _outbox.clear()
        self.patches = [
            mock.patch.object(email_service, "_send", _capture_send),
            mock.patch.object(api_module, "_send_email_off_request_path", lambda fn, *a: api_module._send_email_best_effort(fn, *a)),
            mock.patch.dict(os.environ, {"SELF_SERVE_SIGNUP_ENABLED": "true"}),
        ]
        for p in self.patches:
            p.start()
        api_module._reset_reset_password_rate_limit_for_tests()
        api_module._reset_forgot_password_rate_limit_for_tests()
        api_module._reset_login_rate_limit_for_tests()
        email_service._reset_rate_limit_state_for_tests()
        return app.test_client()

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()
        os.unlink(self.db)


def _link_token(mail):
    m = re.search(r"token=([A-Za-z0-9_\-]+)", mail["text"])
    assert m, f"no link in email: {mail['subject']}"
    return m.group(1)


def _signup(client, email=SIGNUP_EMAIL, name="Jordan Lee", company="Maple Ridge Capital", ip="10.0.0.1"):
    return client.post("/auth/signup", json={"name": name, "email": email, "company": company},
                       environ_base={"REMOTE_ADDR": ip})


def _complete(client, token, password=GOOD_PASSWORD, remember=False):
    return client.post("/auth/complete-signup", json={"token": token, "password": password, "remember": remember})


def _link_status(client, kind, token):
    return client.post("/auth/link-status", json={"kind": kind, "token": token}).get_json()


def _status(client, kind, token):
    return _link_status(client, kind, token)["status"]


def _age_row(table, token, seconds):
    """Pretend the link was issued `seconds` ago."""
    when = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    conn = database.get_connection()
    try:
        conn.execute(f"UPDATE {table} SET created_at = ? WHERE token_hash = ?", (when, hashlib.sha256(token.encode()).hexdigest()))
        conn.commit()
    finally:
        conn.close()


def _count(sql, *args):
    conn = database.get_connection()
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def _make_user(email="casey@harbor.test", name="Casey Park", password=GOOD_PASSWORD, status="active"):
    team = database.create_team(f"Team for {email}")
    uid = database.create_user(email, name, hash_password(password), role="admin", team_id=team["id"])["id"]
    if status != "active":
        database.update_user_status(uid, status)
    return uid


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- signup

def test_signup_creates_no_account_until_the_link_is_used():
    with _Env() as client:
        resp = _signup(client)
        assert resp.status_code == 200
        assert "Check your inbox" in resp.get_json()["message"]
        assert _count("SELECT COUNT(*) FROM users WHERE email = ?", SIGNUP_EMAIL) == 0
        teams_before = _count("SELECT COUNT(*) FROM teams")
        assert len(_outbox) == 1
        mail = _outbox[0]
        assert mail["to"] == SIGNUP_EMAIL
        assert mail["subject"] == "Finish setting up your Abstractly account"
        assert "Hi Jordan," in mail["text"] and "72 hours" in mail["text"] and "Tim" in mail["text"]
        assert "/app/finish-signup.html?token=" in mail["text"]
        assert "Finish setting up your account" in mail["html"]
        # Only the hash is stored.
        token = _link_token(mail)
        assert _count("SELECT COUNT(*) FROM signup_requests WHERE token_hash = ?", token) == 0
        assert _count("SELECT COUNT(*) FROM signup_requests WHERE token_hash = ?", hashlib.sha256(token.encode()).hexdigest()) == 1
        assert _count("SELECT COUNT(*) FROM teams") == teams_before
    print("✓ test_signup_creates_no_account_until_the_link_is_used: PASS")


def test_complete_signup_creates_team_and_admin_and_logs_in():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        assert _status(client, "signup", token) == "valid"

        resp = _complete(client, token)
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["email"] == SIGNUP_EMAIL and data["role"] == "admin" and data["token"]
        user = database.get_user_by_email(SIGNUP_EMAIL)
        team = database.get_team(user["team_id"])
        assert team["name"] == "Maple Ridge Capital"
        assert user["name"] == "Jordan Lee"

        # Logged in on both surfaces: bearer token and cookie.
        session = client.get("/auth/session", headers=_bearer(data["token"])).get_json()
        assert session["authenticated"] and session["team_id"] == team["id"]
        assert client.get("/auth/session").get_json()["authenticated"]

        # Same default usage limits as an owner-created team.
        assert usage_limits._get_team_quotas(team["id"]) == (
            usage_limits_config.DEFAULT_MONTHLY_DOCUMENT_QUOTA,
            usage_limits_config.DEFAULT_MONTHLY_PAGE_QUOTA,
            usage_limits_config.DEFAULT_MONTHLY_BUDGET_USD,
        )
        assert usage_limits.check_team_quota(team["id"]) is None
        assert _status(client, "signup", token) == "used"
    print("✓ test_complete_signup_creates_team_and_admin_and_logs_in: PASS")


def test_link_status_only_describes_a_live_link():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        data = _link_status(client, "signup", token)
        assert data == {"status": "valid", "email": SIGNUP_EMAIL, "first_name": "Jordan", "company": "Maple Ridge Capital"}
        _signup(client)
        dead = _link_status(client, "signup", token)
        assert dead == {"status": "superseded"}, "a dead link must not reveal whose it was"

        _make_user()
        client.post("/auth/forgot-password", json={"email": "casey@harbor.test"})
        reset = _link_token(_outbox[-1])
        assert _link_status(client, "reset", reset) == {
            "status": "valid", "email": "casey@harbor.test", "first_name": "Casey"}
        _age_row("password_reset_tokens", reset, 4000)
        assert _link_status(client, "reset", reset) == {"status": "expired"}
    print("✓ test_link_status_only_describes_a_live_link: PASS")


def test_signing_up_twice_resends_and_kills_the_old_link():
    with _Env() as client:
        _signup(client)
        old = _link_token(_outbox[-1])
        _signup(client)
        new = _link_token(_outbox[-1])
        assert old != new and len(_outbox) == 2
        assert _status(client, "signup", old) == "superseded"
        resp = _complete(client, old)
        assert resp.status_code == 400 and resp.get_json()["link_status"] == "superseded"
        assert _complete(client, new).status_code == 201
    print("✓ test_signing_up_twice_resends_and_kills_the_old_link: PASS")


def test_signup_with_existing_email_looks_identical_but_mails_a_sign_in_note():
    with _Env() as client:
        _make_user("casey@harbor.test", "Casey Park")
        fresh = _signup(client, email="new-person@harbor.test")
        existing = _signup(client, email="Casey@Harbor.test")
        assert existing.status_code == fresh.status_code == 200
        assert existing.get_json() == fresh.get_json()
        mail = _outbox[-1]
        assert mail["to"] == "casey@harbor.test"
        assert mail["subject"] == "You already have an Abstractly account"
        assert "/app/login.html" in mail["text"] and "/app/forgot-password.html" in mail["text"]
        assert "token=" not in mail["text"]
        assert _count("SELECT COUNT(*) FROM signup_requests WHERE email = 'casey@harbor.test'") == 0
    print("✓ test_signup_with_existing_email_looks_identical_but_mails_a_sign_in_note: PASS")


def test_signup_for_deactivated_account_sends_nothing():
    with _Env() as client:
        _make_user("gone@harbor.test", status="deactivated")
        resp = _signup(client, email="gone@harbor.test")
        assert resp.status_code == 200
        assert _outbox == []
    print("✓ test_signup_for_deactivated_account_sends_nothing: PASS")


def test_signup_link_expires_after_72_hours():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        _age_row("signup_requests", token, 71 * 3600)
        assert _status(client, "signup", token) == "valid"
        _age_row("signup_requests", token, 72 * 3600 + 5)
        assert _status(client, "signup", token) == "expired"
        resp = _complete(client, token)
        assert resp.status_code == 400 and resp.get_json()["link_status"] == "expired"
        assert database.get_user_by_email(SIGNUP_EMAIL) is None
    print("✓ test_signup_link_expires_after_72_hours: PASS")


def test_signup_link_cannot_be_reused():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        assert _complete(client, token).status_code == 201
        teams = _count("SELECT COUNT(*) FROM teams")
        again = _complete(client, token, password=OTHER_PASSWORD)
        assert again.status_code == 400 and again.get_json()["link_status"] == "used"
        assert _count("SELECT COUNT(*) FROM teams") == teams
    print("✓ test_signup_link_cannot_be_reused: PASS")


def test_tampered_unknown_and_cross_kind_tokens_are_invalid():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        for bad in (tampered, "x" * 43, "nope", token + "x"):
            assert _status(client, "signup", bad) == "invalid", bad
            r = _complete(client, bad)
            assert r.status_code == 400 and r.get_json()["link_status"] == "invalid"
        # Junk that isn't even a token shape.
        for junk in ("<script>", "a" * 500, "a b"):
            assert _status(client, "signup", junk) == "invalid"
        r = client.post("/auth/complete-signup", json={"token": ["list"], "password": GOOD_PASSWORD})
        assert r.status_code == 400
        # A signup token is not a reset token, and vice versa.
        assert _status(client, "reset", token) == "invalid"
        uid = _make_user()
        api_module._reset_forgot_password_rate_limit_for_tests()
        client.post("/auth/forgot-password", json={"email": "casey@harbor.test"})
        reset_token = _link_token(_outbox[-1])
        assert _status(client, "signup", reset_token) == "invalid"
        assert _complete(client, reset_token).status_code == 400
        assert _status(client, "signup", token) == "valid", "probing must not consume the real link"
        assert uid
    print("✓ test_tampered_unknown_and_cross_kind_tokens_are_invalid: PASS")


def test_double_submit_creates_exactly_one_account():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        teams_before = _count("SELECT COUNT(*) FROM teams")
        results = []

        def go():
            results.append(app.test_client().post("/auth/complete-signup", json={"token": token, "password": GOOD_PASSWORD}).status_code)

        threads = [threading.Thread(target=go) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == [201, 400, 400, 400, 400], results
        assert _count("SELECT COUNT(*) FROM users WHERE email = ?", SIGNUP_EMAIL) == 1
        assert _count("SELECT COUNT(*) FROM teams") == teams_before + 1
    print("✓ test_double_submit_creates_exactly_one_account: PASS")


def test_company_name_collision_and_reserved_name():
    with _Env() as client:
        database.create_team("Maple Ridge Capital")
        _signup(client)
        assert _complete(client, _link_token(_outbox[-1])).status_code == 201
        user = database.get_user_by_email(SIGNUP_EMAIL)
        assert database.get_team(user["team_id"])["name"] == "Maple Ridge Capital (2)"

        _signup(client, email="pat@legacy.test", company="legacy")
        assert _complete(client, _link_token(_outbox[-1])).status_code == 201
        name = database.get_team(database.get_user_by_email("pat@legacy.test")["team_id"])["name"]
        assert name.lower() != "legacy" and name.startswith("legacy (")
    print("✓ test_company_name_collision_and_reserved_name: PASS")


def test_password_rules_are_enforced_server_side_without_burning_the_link():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        for bad, needle in (
            ("short1", "at least 10"),
            ("password123", "too common"),
            ("aaaaaaaaaaaa", "too common"),
            (SIGNUP_EMAIL, "email address or name"),
            ("jordan12345", "email address or name"),
            ("x" * 73, "too long"),
            ("é" * 40, "too long"),  # 80 bytes of UTF-8: bcrypt's real limit is bytes
        ):
            r = _complete(client, token, password=bad)
            assert r.status_code == 400, bad
            assert needle in r.get_json()["error"], (bad, r.get_json())
        assert _status(client, "signup", token) == "valid"
        assert _complete(client, token, password="Jordan likes long walks").status_code == 201
    print("✓ test_password_rules_are_enforced_server_side_without_burning_the_link: PASS")


def test_account_created_elsewhere_meanwhile_is_clean_409():
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        _make_user(SIGNUP_EMAIL, "Jordan Lee")
        teams = _count("SELECT COUNT(*) FROM teams")
        r = _complete(client, token)
        assert r.status_code == 409 and r.get_json()["link_status"] == "account_exists"
        assert _count("SELECT COUNT(*) FROM teams") == teams, "an orphan team was created"
    print("✓ test_account_created_elsewhere_meanwhile_is_clean_409: PASS")


def test_signup_input_validation_and_email_injection():
    with _Env() as client:
        for payload, field in (
            ({"name": "", "email": SIGNUP_EMAIL, "company": "X"}, "name"),
            ({"name": "A", "email": "not-an-email", "company": "X"}, "email"),
            ({"name": "A", "email": SIGNUP_EMAIL, "company": "   "}, "company"),
            ({"name": "A" * 101, "email": SIGNUP_EMAIL, "company": "X"}, "name"),
            ({"name": 5, "email": SIGNUP_EMAIL, "company": "X"}, "name"),
        ):
            api_module._reset_reset_password_rate_limit_for_tests()
            r = client.post("/auth/signup", json=payload)
            assert r.status_code == 400 and field in r.get_json()["fields"], payload
        assert client.post("/auth/signup", data="not json").status_code == 400
        assert _outbox == []

        # Whoever fills the form controls the name, and the email comes
        # from Tim -- so a name that isn't plainly a name is not echoed.
        _signup(client, name="<b>Visit evil.example</b>", company="Acme\r\nBcc: x@y.test")
        mail = _outbox[-1]
        assert "Hi there," in mail["text"] and "evil" not in mail["html"] and "<b>" not in mail["html"]
        conn = database.get_connection()
        try:
            company = conn.execute("SELECT company FROM signup_requests").fetchone()[0]
        finally:
            conn.close()
        assert "\r" not in company and "\n" not in company
    print("✓ test_signup_input_validation_and_email_injection: PASS")


def test_signup_flag_off_hides_every_signup_route():
    with _Env() as client:
        with mock.patch.dict(os.environ, {"SELF_SERVE_SIGNUP_ENABLED": ""}):
            assert client.get("/auth/options").get_json() == {"signup_enabled": False}
            assert _signup(client).status_code == 404
            assert _complete(client, "x" * 43).status_code == 404
            assert client.post("/auth/link-status", json={"kind": "signup", "token": "abc"}).status_code == 404
            assert client.post("/auth/resend-link", json={"kind": "signup", "token": "abc"}).status_code == 404
            assert _outbox == []
        assert client.get("/auth/options").get_json() == {"signup_enabled": True}
    print("✓ test_signup_flag_off_hides_every_signup_route: PASS")


def test_resend_from_a_dead_signup_link():
    with _Env() as client:
        _signup(client)
        old = _link_token(_outbox[-1])
        _age_row("signup_requests", old, 80 * 3600)
        r = client.post("/auth/resend-link", json={"kind": "signup", "token": old})
        assert r.status_code == 200 and SIGNUP_EMAIL not in r.get_data(as_text=True)
        new = _link_token(_outbox[-1])
        assert _outbox[-1]["to"] == SIGNUP_EMAIL and new != old
        assert _complete(client, new).status_code == 201

        # Used link -> account exists now -> a sign-in note, not a new link.
        r = client.post("/auth/resend-link", json={"kind": "signup", "token": new})
        assert r.status_code == 200
        assert _outbox[-1]["subject"] == "You already have an Abstractly account"

        # Forged token: same answer, nothing sent.
        n = len(_outbox)
        assert client.post("/auth/resend-link", json={"kind": "signup", "token": "f" * 43}).status_code == 200
        assert len(_outbox) == n
    print("✓ test_resend_from_a_dead_signup_link: PASS")


# ---------------------------------------------------------------- reset

def _forgot(client, email="casey@harbor.test", ip="10.0.0.9"):
    return client.post("/auth/forgot-password", json={"email": email}, environ_base={"REMOTE_ADDR": ip})


def _login(client, email="casey@harbor.test", password=GOOD_PASSWORD, remember=False):
    return client.post("/auth/login", json={"email": email, "password": password, "remember": remember})


def test_forgot_password_message_is_exact_and_identical():
    with _Env() as client:
        _make_user()
        a = _forgot(client).get_json()
        b = _forgot(client, "nobody@harbor.test", ip="10.0.0.10").get_json()
        assert a == b == {"message": "If an account exists for that email, we just sent a reset link."}
        assert len(_outbox) == 1 and _outbox[0]["subject"] == "Reset your Abstractly password"
        assert "Hi Casey," in _outbox[0]["text"] and "1 hour" in _outbox[0]["text"]
    print("✓ test_forgot_password_message_is_exact_and_identical: PASS")


def test_reset_logs_in_and_signs_out_every_other_session():
    with _Env() as client:
        uid = _make_user()
        other_device = app.test_client()
        old_login = _login(other_device, remember=True).get_json()
        assert other_device.get("/auth/session").get_json()["authenticated"]
        assert client.get("/auth/session", headers=_bearer(old_login["token"])).get_json()["authenticated"]

        _forgot(client)
        token = _link_token(_outbox[-1])
        r = client.post("/auth/reset-password", json={"token": token, "new_password": OTHER_PASSWORD})
        assert r.status_code == 200, r.get_json()
        data = r.get_json()
        assert data["logged_in"] and data["token"]

        # Old cookie and old 30-day token are dead; the new login works.
        assert not other_device.get("/auth/session").get_json()["authenticated"]
        assert not app.test_client().get("/auth/session", headers=_bearer(old_login["token"])).get_json()["authenticated"]
        assert app.test_client().get("/auth/session", headers=_bearer(data["token"])).get_json()["authenticated"]
        assert client.get("/auth/session").get_json()["authenticated"]
        # Old password no longer works, new one does.
        assert _login(app.test_client()).status_code == 401
        assert _login(app.test_client(), password=OTHER_PASSWORD).status_code == 200
        # And they're told.
        assert any(m["subject"] == "Your Abstractly password was changed" for m in _outbox)
        assert uid
    print("✓ test_reset_logs_in_and_signs_out_every_other_session: PASS")


def test_logging_in_during_a_reset():
    """Requesting a reset doesn't lock anyone out; remembering the password and logging in is fine; finishing the reset later still works and ends that login."""
    with _Env() as client:
        _make_user()
        _forgot(client)
        token = _link_token(_outbox[-1])
        laptop = app.test_client()
        assert _login(laptop).status_code == 200
        assert _status(client, "reset", token) == "valid"
        assert client.post("/auth/reset-password", json={"token": token, "new_password": OTHER_PASSWORD}).status_code == 200
        assert not laptop.get("/auth/session").get_json()["authenticated"]
    print("✓ test_logging_in_during_a_reset: PASS")


def test_reset_link_expired_used_and_superseded():
    with _Env() as client:
        _make_user()
        _forgot(client)
        first = _link_token(_outbox[-1])
        _forgot(client)
        second = _link_token(_outbox[-1])
        assert _status(client, "reset", first) == "superseded"
        r = client.post("/auth/reset-password", json={"token": first, "new_password": OTHER_PASSWORD})
        assert r.status_code == 400 and r.get_json()["link_status"] == "superseded"

        _age_row("password_reset_tokens", second, 3601)
        assert _status(client, "reset", second) == "expired"
        r = client.post("/auth/reset-password", json={"token": second, "new_password": OTHER_PASSWORD})
        assert r.status_code == 400 and r.get_json()["link_status"] == "expired"

        _forgot(client, ip="10.0.0.11")
        third = _link_token(_outbox[-1])
        _age_row("password_reset_tokens", third, 3500)
        assert client.post("/auth/reset-password", json={"token": third, "new_password": OTHER_PASSWORD}).status_code == 200
        r = client.post("/auth/reset-password", json={"token": third, "new_password": "yet another phrase"})
        assert r.status_code == 400 and r.get_json()["link_status"] == "used"
        assert _status(client, "reset", third) == "used"
    print("✓ test_reset_link_expired_used_and_superseded: PASS")


def test_reset_rejected_password_does_not_burn_link():
    with _Env() as client:
        _make_user()
        _forgot(client)
        token = _link_token(_outbox[-1])
        for bad in ("short", "x" * 100, "casey@harbor.test"):
            r = client.post("/auth/reset-password", json={"token": token, "new_password": bad})
            assert r.status_code == 400 and "link_status" not in r.get_json(), bad
        assert _status(client, "reset", token) == "valid"
    print("✓ test_reset_rejected_password_does_not_burn_link: PASS")


def test_double_submit_reset_succeeds_once():
    with _Env() as client:
        _make_user()
        _forgot(client)
        token = _link_token(_outbox[-1])
        codes = []

        def go():
            codes.append(app.test_client().post("/auth/reset-password", json={"token": token, "new_password": OTHER_PASSWORD}).status_code)

        threads = [threading.Thread(target=go) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(codes) == [200, 400, 400, 400], codes
    print("✓ test_double_submit_reset_succeeds_once: PASS")


def test_resend_from_a_dead_reset_link():
    with _Env() as client:
        _make_user()
        _forgot(client)
        old = _link_token(_outbox[-1])
        _age_row("password_reset_tokens", old, 7200)
        r = client.post("/auth/resend-link", json={"kind": "reset", "token": old})
        assert r.status_code == 200 and "casey" not in r.get_data(as_text=True)
        new = _link_token(_outbox[-1])
        assert new != old and _status(client, "reset", new) == "valid"
    print("✓ test_resend_from_a_dead_reset_link: PASS")


def test_deactivated_user_finishing_a_reset_is_not_logged_in():
    with _Env() as client:
        uid = _make_user()
        _forgot(client)
        token = _link_token(_outbox[-1])
        database.update_user_status(uid, "deactivated")
        r = client.post("/auth/reset-password", json={"token": token, "new_password": OTHER_PASSWORD})
        assert r.status_code == 200 and r.get_json()["logged_in"] is False and "token" not in r.get_json()
        assert not client.get("/auth/session").get_json()["authenticated"]
    print("✓ test_deactivated_user_finishing_a_reset_is_not_logged_in: PASS")


def test_any_password_change_kills_outstanding_reset_links():
    with _Env() as client:
        _make_user()
        _forgot(client)
        token = _link_token(_outbox[-1])
        assert _login(client).status_code == 200
        r = client.post("/auth/change-password", json={"current_password": GOOD_PASSWORD, "new_password": OTHER_PASSWORD})
        assert r.status_code == 200
        assert _status(client, "reset", token) == "superseded"
    print("✓ test_any_password_change_kills_outstanding_reset_links: PASS")


def test_overlong_passwords_are_400_not_500():
    """Regression: bcrypt raises on >72 bytes, which used to surface as a 500 on every password-setting route."""
    with _Env() as client:
        _make_user()
        assert _login(client).status_code == 200
        r = client.post("/auth/change-password", json={"current_password": GOOD_PASSWORD, "new_password": "x" * 100})
        assert r.status_code == 400, r.status_code
        r = client.post("/team/members", json={"email": "n@harbor.test", "name": "N", "role": "viewer", "password": "y" * 100})
        assert r.status_code == 400, r.status_code
        # Logging in with a huge password is just a wrong password.
        assert _login(app.test_client(), password="z" * 200).status_code == 401
    print("✓ test_overlong_passwords_are_400_not_500: PASS")


def test_forgot_password_before_finishing_signup_resends_the_setup_link():
    """Signed up, never clicked the link, later tries "Forgot password?": they need the setup link, not silence."""
    with _Env() as client:
        _signup(client)
        old = _link_token(_outbox[-1])
        unknown = _forgot(client, "nobody@harbor.test", ip="10.0.1.1").get_json()
        pending = _forgot(client, SIGNUP_EMAIL, ip="10.0.1.2").get_json()
        assert pending == unknown, "response must not reveal a pending signup"
        mail = _outbox[-1]
        assert mail["to"] == SIGNUP_EMAIL and mail["subject"] == "Finish setting up your Abstractly account"
        new = _link_token(mail)
        assert new != old and _status(client, "signup", old) == "superseded"
        assert _complete(client, new).status_code == 201
        # Flag off: nothing about signup leaks through forgot-password.
        with mock.patch.dict(os.environ, {"SELF_SERVE_SIGNUP_ENABLED": ""}):
            _signup_raw = database.create_signup_request("late@harbor.test", "Late Person", "Late Co", "f" * 64)
            n = len(_outbox)
            _forgot(client, "late@harbor.test", ip="10.0.1.3")
            assert len(_outbox) == n
            assert _signup_raw is None
    print("✓ test_forgot_password_before_finishing_signup_resends_the_setup_link: PASS")


def test_stale_credential_from_a_wiped_database_is_rejected():
    """Regression: user ids restart when a database is recreated (no persistent disk), so an old token for user #1 must not sign its holder in as the NEW user #1."""
    with _Env() as client:
        first_db = database._db_path
        uid_a = _make_user("alice@first.test", "Alice First")
        login = _login(client, "alice@first.test").get_json()
        token = login["token"]
        assert client.get("/auth/session", headers=_bearer(token)).get_json()["authenticated"]

        second_db = _fresh_temp_db()
        try:
            uid_b = _make_user("bob@second.test", "Bob Second")
            assert uid_b == uid_a, "test setup: the new database should reuse the id"
            stale_token = app.test_client().get("/auth/session", headers=_bearer(token)).get_json()
            assert not stale_token["authenticated"], f"old token signed in as {stale_token.get('email')}"
            stale_cookie = client.get("/auth/session").get_json()
            assert not stale_cookie["authenticated"], f"old cookie signed in as {stale_cookie.get('email')}"
        finally:
            os.unlink(second_db)
            database.configure(first_db)
    print("✓ test_stale_credential_from_a_wiped_database_is_rejected: PASS")


def test_wrong_http_method_is_405_not_500():
    """Regression: the catch-all Exception handler turned Flask's own 405 into a 500 on every route."""
    with _Env() as client:
        for method, path in (("get", "/auth/login"), ("get", "/auth/signup"), ("delete", "/auth/session")):
            r = getattr(client, method)(path)
            assert r.status_code == 405, (method, path, r.status_code)
    print("✓ test_wrong_http_method_is_405_not_500: PASS")


def test_catch_all_handler_keeps_redirects_as_redirects():
    """Review note: HTTPException pass-through must not turn a 3xx into JSON without a Location."""
    from werkzeug.routing import RequestRedirect
    with app.test_request_context("/x"):
        resp = api_module.handle_unexpected_error(RequestRedirect("http://localhost/x/"))
        resp = resp.get_response() if hasattr(resp, "get_response") else resp
        assert resp.status_code == 308 and resp.headers.get("Location", "").endswith("/x/")


def test_change_password_is_not_counted_as_a_login():
    with _Env() as client:
        uid = _make_user()
        token = _login(client).get_json()["token"]
        before = database.get_user(uid)
        r = client.post("/auth/change-password", headers=_bearer(token),
                        json={"current_password": GOOD_PASSWORD, "new_password": OTHER_PASSWORD})
        assert r.status_code == 200
        after = database.get_user(uid)
        assert (after["last_login_at"], after["previous_login_at"]) == (before["last_login_at"], before["previous_login_at"])
    print("✓ test_change_password_is_not_counted_as_a_login: PASS")


def test_staff_consoles_send_a_bearer_token():
    """Regression: admin/dashboard.html's api.js sent no credential (every call 401'd, then bounced to a missing admin/login.html), and admin/owner were cookie-only, which Safari drops cross-site."""
    root = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    read = lambda rel: open(os.path.join(root, rel)).read()
    assert "sessionStorage.setItem('authToken', data.token)" in read("admin/login.js")
    assert "Authorization: `Bearer ${token}`" in read("admin/admin-bootstrap.js")
    assert "sessionStorage.setItem('ownerAuthToken', data.token)" in read("owner/login.js")
    assert "Authorization: `Bearer ${token}`" in read("owner/owner-app.js")
    api_js = read("app/api.js")
    assert "inAdmin ? 'index.html?expired=1'" in api_js and not os.path.exists(os.path.join(root, "admin", "login.html"))
    print("✓ test_staff_consoles_send_a_bearer_token: PASS")


def test_signing_in_never_momentarily_empties_the_shared_token():
    """Regression (round 4): finishLogin cleared localStorage before writing the new token; other open tabs saw "signed out" and left. Browser-checked in round4.mjs ("two people, one browser")."""
    js = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app", "auth-common.js")).read()
    start = js.index("function finishLogin(")
    body = js[start:js.index("\n    }\n", start)]
    assert "clearToken()" not in body, "finishLogin must overwrite, not clear-then-set"
    gate = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app", "access-gate.js")).read()
    assert "window.addEventListener('storage'" in gate, "app tabs must react to the shared token changing hands"
    print("✓ test_signing_in_never_momentarily_empties_the_shared_token: PASS")


def test_auth_inputs_tell_phone_keyboards_what_enter_does():
    root = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app")
    for page in ("login.html", "signup.html", "forgot-password.html", "finish-signup.html", "reset-password.html"):
        html = open(os.path.join(root, page)).read()
        for tag in re.findall(r"<input [^>]*>", html):
            if 'type="checkbox"' in tag or " hidden" in tag:
                continue
            assert "enterkeyhint=" in tag, f"{page}: {tag[:60]}"
    print("✓ test_auth_inputs_tell_phone_keyboards_what_enter_does: PASS")


def test_return_to_screen_only_accepts_a_plain_view_name():
    """Round 5: after a session ends mid-use, signing back in returns to that screen. The `next` value must never be able to send someone off-site (open redirect). Browser-checked in round5.mjs."""
    root = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app")
    for rel in ("login.js", "auth-common.js", "api.js"):
        js = open(os.path.join(root, rel)).read()
        assert "/^[a-z0-9-]{1,40}$/.test(" in js, f"{rel} must validate the view name"
    common = open(os.path.join(root, "auth-common.js")).read()
    assert "window.location.replace(`index.html${view}`)" in common
    pattern = re.compile(r"^[a-z0-9-]{1,40}$")
    for bad in ("https://evil.example", "//evil.example", "tasks#x", "../admin", "javascript:alert(1)", ""):
        assert not pattern.match(bad), bad
    print("✓ test_return_to_screen_only_accepts_a_plain_view_name: PASS")


def test_link_tokens_never_travel_in_a_url_to_the_api():
    """Regression (security audit): link-status was a GET with ?token=, which the access log records."""
    with _Env() as client:
        _signup(client)
        token = _link_token(_outbox[-1])
        assert client.get(f"/auth/link-status?kind=signup&token={token}").status_code == 405
        for path in ("signup.js", "finish-signup.js", "reset-password.js", "forgot-password.js", "login.js", "auth-common.js"):
            with open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app", path)) as f:
                js = f.read()
            assert "token=${" not in js and "?token=" not in js, f"{path} puts a token in an API URL"
    print("✓ test_link_tokens_never_travel_in_a_url_to_the_api: PASS")


def test_reset_and_setup_tokens_are_not_interchangeable():
    """Regression (security audit): a 1-hour forgot-password token was redeemable at /auth/team-setup under its 7-day limit."""
    with _Env() as client:
        _make_user()
        _forgot(client)
        reset_token = _link_token(_outbox[-1])
        _age_row("password_reset_tokens", reset_token, 2 * 3600)  # expired as a reset link
        r = client.post("/auth/team-setup", json={"token": reset_token, "new_password": OTHER_PASSWORD})
        assert r.status_code == 400, r.get_json()
        assert _login(app.test_client()).status_code == 200, "password changed through the wrong door"

        # And the other way: an owner's setup link isn't a reset link.
        uid = _make_user("setup@harbor.test", "Setup Person")
        raw = "s" * 43
        database.create_password_reset_token(uid, hashlib.sha256(raw.encode()).hexdigest(), purpose="setup")
        assert _status(client, "reset", raw) == "invalid"
        assert client.post("/auth/reset-password", json={"token": raw, "new_password": OTHER_PASSWORD}).status_code == 400
        assert client.post("/auth/team-setup", json={"token": raw, "new_password": OTHER_PASSWORD}).status_code == 200
    print("✓ test_reset_and_setup_tokens_are_not_interchangeable: PASS")


def test_change_password_signs_out_other_sessions_but_keeps_the_caller():
    """Regression (security audit): only the emailed reset revoked sessions; a stolen 30-day token survived a password change."""
    with _Env() as client:
        _make_user()
        stolen = _login(app.test_client(), remember=True).get_json()["token"]
        mine = _login(client, remember=True).get_json()["token"]
        r = client.post("/auth/change-password", headers=_bearer(mine),
                        json={"current_password": GOOD_PASSWORD, "new_password": OTHER_PASSWORD})
        assert r.status_code == 200, r.get_json()
        fresh = r.get_json()["token"]
        assert r.get_json()["remember"] is True, "keep-me-signed-in choice should carry over"
        assert not app.test_client().get("/auth/session", headers=_bearer(stolen)).get_json()["authenticated"]
        assert not app.test_client().get("/auth/session", headers=_bearer(mine)).get_json()["authenticated"]
        assert app.test_client().get("/auth/session", headers=_bearer(fresh)).get_json()["authenticated"]
        assert client.get("/auth/session").get_json()["authenticated"], "cookie caller should stay signed in"
        # Same rules as signup/reset now.
        r = client.post("/auth/change-password", headers=_bearer(fresh),
                        json={"current_password": OTHER_PASSWORD, "new_password": "password123"})
        assert r.status_code == 400 and "too common" in r.get_json()["error"]
    print("✓ test_change_password_signs_out_other_sessions_but_keeps_the_caller: PASS")


def test_plus_and_dot_aliases_share_one_email_budget():
    """Regression (security audit): +tags multiplied the per-email cap for mailbombing one inbox."""
    with _Env() as client:
        codes = [_signup(client, email=e, ip=f"10.8.0.{i}").status_code for i, e in enumerate(
            ["pat@gmail.com", "pat+1@gmail.com", "p.a.t@gmail.com", "PAT+x@googlemail.com"])]
        assert codes == [200, 200, 200, 429], codes
        assert api_module._email_rate_key("Pat+tag@Example.com") == "email:pat@example.com"
        assert api_module._email_rate_key("p.a.t@example.com") == "email:p.a.t@example.com", "dots only matter at gmail"
    print("✓ test_plus_and_dot_aliases_share_one_email_budget: PASS")


# ---------------------------------------------------------------- keep me signed in

def _set_cookie(resp):
    return next((h for h in resp.headers.getlist("Set-Cookie") if h.startswith("session=")), "")


def test_keep_me_signed_in_cookie_attributes():
    with _Env() as client:
        _make_user()
        remembered = _set_cookie(_login(client, remember=True))
        assert "HttpOnly" in remembered and "Secure" in remembered
        assert "Expires=" in remembered
        expires = datetime.strptime(re.search(r"Expires=([^;]+)", remembered).group(1), "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        assert timedelta(days=29) < expires - datetime.now(timezone.utc) <= timedelta(days=30, minutes=1)

        browser_session = _set_cookie(_login(app.test_client(), remember=False))
        assert "HttpOnly" in browser_session and "Secure" in browser_session
        assert "Expires=" not in browser_session and "Max-Age" not in browser_session

        # Anything but a real `true` is "don't remember".
        assert _login(app.test_client(), remember="yes").get_json()["remember"] is False
    print("✓ test_keep_me_signed_in_cookie_attributes: PASS")


def test_token_lifetimes_follow_keep_me_signed_in():
    with _Env() as client:
        _make_user()
        now = __import__("time").time()
        with mock.patch("itsdangerous.timed.time.time", return_value=now - 13 * 3600):
            short = _login(app.test_client()).get_json()["token"]
            long_ = _login(app.test_client(), remember=True).get_json()["token"]
        assert not client.get("/auth/session", headers=_bearer(short)).get_json()["authenticated"]
        assert client.get("/auth/session", headers=_bearer(long_)).get_json()["authenticated"]
        with mock.patch("itsdangerous.timed.time.time", return_value=now - 31 * 86400):
            ancient = _login(app.test_client(), remember=True).get_json()["token"]
        assert not client.get("/auth/session", headers=_bearer(ancient)).get_json()["authenticated"]
    print("✓ test_token_lifetimes_follow_keep_me_signed_in: PASS")


def test_server_side_session_expiry():
    """A cookie that outlives its login (a restored browser session, a stolen cookie) is still refused."""
    with _Env() as client:
        _make_user()
        _login(client)
        assert client.get("/auth/session").get_json()["authenticated"]
        with client.session_transaction() as sess:
            sess["exp"] = int(__import__("time").time()) - 1
        assert not client.get("/auth/session").get_json()["authenticated"]
    print("✓ test_server_side_session_expiry: PASS")


def test_pre_deploy_permanent_cookie_without_exp_must_sign_in_again():
    """Regression (review): cookie lifetime went 12h -> 30d, so an old 12-hour cookie (permanent, no exp) would slide for 30 days."""
    with _Env() as client:
        uid = _make_user()
        with client.session_transaction() as sess:
            sess.permanent = True
            sess["user_id"] = uid
        assert not client.get("/auth/session").get_json()["authenticated"]
        # A plain (non-permanent) session without exp -- how test fixtures
        # across the suite sign in -- still works.
        with client.session_transaction() as sess:
            sess.permanent = False
            sess["user_id"] = uid
        assert client.get("/auth/session").get_json()["authenticated"]
    print("✓ test_pre_deploy_permanent_cookie_without_exp_must_sign_in_again: PASS")


def test_logout_ends_the_cookie_session():
    with _Env() as client:
        _make_user()
        _login(client)
        assert client.post("/auth/logout").status_code == 200
        assert not client.get("/auth/session").get_json()["authenticated"]
    print("✓ test_logout_ends_the_cookie_session: PASS")


# ---------------------------------------------------------------- rate limits

def test_signup_rate_limits_per_email_and_per_ip():
    with _Env() as client:
        codes = [_signup(client, ip=f"10.1.0.{i}").status_code for i in range(4)]
        assert codes == [200, 200, 200, 429], codes
        api_module._reset_reset_password_rate_limit_for_tests()
        codes = [_signup(client, email=f"p{i}@spread.test", ip="10.2.0.1").status_code for i in range(11)]
        assert codes[:10] == [200] * 10 and codes[10] == 429, codes
        # A 429 doesn't depend on whether the account exists.
        api_module._reset_reset_password_rate_limit_for_tests()
        _make_user("known@spread.test")
        known = [_signup(client, email="known@spread.test", ip=f"10.3.0.{i}").status_code for i in range(4)]
        unknown = [_signup(client, email="unknown@spread.test", ip=f"10.4.0.{i}").status_code for i in range(4)]
        assert known == unknown == [200, 200, 200, 429]
    print("✓ test_signup_rate_limits_per_email_and_per_ip: PASS")


def test_login_and_reset_rate_limits():
    with _Env() as client:
        _make_user()
        codes = [client.post("/auth/login", json={"email": "casey@harbor.test", "password": "wrong guess!"},
                             environ_base={"REMOTE_ADDR": f"10.5.0.{i}"}).status_code for i in range(8)]
        assert codes[:7] == [401] * 7 and codes[7] == 429, codes
        codes = [client.post("/auth/reset-password", json={"token": "f" * 43, "new_password": OTHER_PASSWORD},
                             environ_base={"REMOTE_ADDR": "10.6.0.1"}).status_code for i in range(16)]
        assert codes[:15] == [400] * 15 and codes[15] == 429, codes
        codes = [client.post("/auth/resend-link", json={"kind": "reset", "token": "f" * 43},
                             environ_base={"REMOTE_ADDR": "10.7.0.1"}).status_code for i in range(6)]
        assert codes[:5] == [200] * 5 and codes[5] == 429, codes
    print("✓ test_login_and_reset_rate_limits: PASS")


def test_proxy_fix_uses_the_real_client_ip_and_cannot_be_spoofed():
    """Regression: behind Render's proxy every visitor had the proxy's IP, so the per-IP limits were one global bucket."""
    code = r'''
import os, sys
sys.path.insert(0, os.getcwd())
from flask import request
from app.api import app
@app.route("/__ip")
def __ip():
    return request.remote_addr
c = app.test_client()
print(c.get("/__ip", headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.7"}, environ_base={"REMOTE_ADDR": "10.9.9.9"}).get_data(as_text=True))
'''
    backend = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    for env_extra, expected in (({"RENDER": "true"}, "203.0.113.7"), ({"RENDER": ""}, "10.9.9.9"),
                                ({"RENDER": "true", "TRUSTED_PROXY_HOPS": "0"}, "10.9.9.9"),
                                ({"RENDER": "true", "TRUSTED_PROXY_HOPS": "two"}, "10.9.9.9")):
        env = {**os.environ, "TRUSTED_PROXY_HOPS": "", **env_extra}
        if not env["TRUSTED_PROXY_HOPS"]:
            env.pop("TRUSTED_PROXY_HOPS")
        out = subprocess.run([sys.executable, "-c", code], cwd=backend, env=env, capture_output=True, text=True, timeout=120)
        assert out.stdout.strip().splitlines()[-1] == expected, (env_extra, out.stdout[-300:], out.stderr[-500:])
    print("✓ test_proxy_fix_uses_the_real_client_ip_and_cannot_be_spoofed: PASS")


def test_frontend_common_password_list_matches_backend():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app", "auth-common.js")
    with open(path) as f:
        js = f.read()
    m = re.search(r"COMMON_PASSWORDS = new Set\(`([^`]*)`", js)
    assert m, "COMMON_PASSWORDS not found in auth-common.js"
    assert set(m.group(1).split()) == set(password_rules.COMMON_PASSWORDS)
    assert f"MIN_LENGTH = {password_rules.MIN_LENGTH}" in js
    print("✓ test_frontend_common_password_list_matches_backend: PASS")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} auth flow tests passed.")
