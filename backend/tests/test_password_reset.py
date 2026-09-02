"""
Tests for the "Forgot password?" self-service reset flow:
POST /auth/forgot-password and POST /auth/reset-password.

The security-relevant properties here are as important as the happy
path, and each has its own test below:
  - the response never reveals whether an email has an account, in the
    body OR in how the rate limiter behaves
  - the emailed token is single-use, time-limited, and superseded by a
    newer request
  - the raw token is never stored (only its SHA-256 hash)
  - reset requests are throttled per email AND per IP

Same conventions as test_task_workflow_extensions.py: _fresh_temp_db()
+ Flask test_client(). The SMTP send is stubbed throughout -- these
tests must never attempt real delivery (see DECISIONS.md's incident
where an unmocked test suite mailed a real inbox once real credentials
were configured).
"""

import hashlib
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import api as api_module
from app import database, email_service
from app.auth import hash_password, verify_password

USER_EMAIL = "reset-me@example.com"
USER_PASSWORD = "OriginalPass123!"
NEW_PASSWORD = "BrandNewPass456!"


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _setup():
    """Fresh DB + one active user + stubbed mail + cleared rate limiter. Returns (client, user_id, sent)."""
    user = database.create_user(USER_EMAIL, "Reset Me", hash_password(USER_PASSWORD), role="analyst")
    sent = []
    email_service.send_password_reset_email = lambda to, url: (sent.append((to, url)), True)[1]
    api_module._reset_forgot_password_rate_limit_for_tests()
    return app.test_client(), user["id"], sent


def _token_from(sent):
    """The raw token out of the most recent emailed link -- the only place it exists."""
    assert sent, "no reset email was generated"
    return sent[-1][1].split("token=")[1]


def _request_reset(client, email):
    return client.post("/auth/forgot-password", json={"email": email})


def test_reset_email_is_sent_for_a_real_account():
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        resp = _request_reset(client, USER_EMAIL)
        assert resp.status_code == 200
        assert len(sent) == 1
        to, url = sent[0]
        assert to == USER_EMAIL
        assert "/app/reset-password.html?token=" in url
        # A real token, not a placeholder -- token_urlsafe(32) is 43 chars.
        assert len(_token_from(sent)) >= 40
    finally:
        os.unlink(db_path)
    print("✓ test_reset_email_is_sent_for_a_real_account: PASS")


def test_response_is_identical_for_unknown_email_and_no_email_is_sent():
    """The whole point of the generic response: no account-existence oracle."""
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        real = _request_reset(client, USER_EMAIL)
        api_module._reset_forgot_password_rate_limit_for_tests()
        sent.clear()
        unknown = _request_reset(client, "nobody@example.com")

        assert unknown.status_code == real.status_code == 200
        assert unknown.get_json() == real.get_json()
        assert sent == [], "an email was generated for an address with no account"
    finally:
        os.unlink(db_path)
    print("✓ test_response_is_identical_for_unknown_email_and_no_email_is_sent: PASS")


def test_deactivated_user_gets_no_reset_email_but_same_response():
    db_path = _fresh_temp_db()
    try:
        client, user_id, sent = _setup()
        database.update_user_status(user_id, "deactivated")
        resp = _request_reset(client, USER_EMAIL)
        assert resp.status_code == 200
        assert sent == [], "a deactivated account was sent a working reset link"
    finally:
        os.unlink(db_path)
    print("✓ test_deactivated_user_gets_no_reset_email_but_same_response: PASS")


def test_only_the_token_hash_is_stored():
    """A dump of password_reset_tokens must not hand an attacker usable links."""
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        _request_reset(client, USER_EMAIL)
        raw = _token_from(sent)

        conn = database.get_connection()
        try:
            rows = conn.execute("SELECT token_hash FROM password_reset_tokens").fetchall()
        finally:
            conn.close()
        stored = [r["token_hash"] for r in rows]
        assert raw not in stored, "the RAW token was stored"
        assert hashlib.sha256(raw.encode()).hexdigest() in stored
    finally:
        os.unlink(db_path)
    print("✓ test_only_the_token_hash_is_stored: PASS")


def test_full_reset_then_login_with_new_password():
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        _request_reset(client, USER_EMAIL)
        token = _token_from(sent)

        resp = client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        assert resp.status_code == 200, resp.get_json()

        assert verify_password(USER_EMAIL, NEW_PASSWORD) is not None
        assert verify_password(USER_EMAIL, USER_PASSWORD) is None

        login = client.post("/auth/login", json={"email": USER_EMAIL, "password": NEW_PASSWORD})
        assert login.status_code == 200, login.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_full_reset_then_login_with_new_password: PASS")


def test_token_is_single_use():
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        _request_reset(client, USER_EMAIL)
        token = _token_from(sent)

        first = client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        assert first.status_code == 200
        replay = client.post("/auth/reset-password", json={"token": token, "new_password": "ThirdPassword789!"})
        assert replay.status_code == 400
        # The replay must not have changed anything.
        assert verify_password(USER_EMAIL, NEW_PASSWORD) is not None
    finally:
        os.unlink(db_path)
    print("✓ test_token_is_single_use: PASS")


def test_requesting_again_invalidates_the_previous_link():
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        _request_reset(client, USER_EMAIL)
        first_token = _token_from(sent)
        _request_reset(client, USER_EMAIL)
        second_token = _token_from(sent)
        assert first_token != second_token

        stale = client.post("/auth/reset-password", json={"token": first_token, "new_password": NEW_PASSWORD})
        assert stale.status_code == 400, "an older reset link still worked"
        fresh = client.post("/auth/reset-password", json={"token": second_token, "new_password": NEW_PASSWORD})
        assert fresh.status_code == 200
    finally:
        os.unlink(db_path)
    print("✓ test_requesting_again_invalidates_the_previous_link: PASS")


def test_expired_token_is_rejected():
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        _request_reset(client, USER_EMAIL)
        token = _token_from(sent)

        # Age the token past its TTL by rewriting created_at.
        stale_at = (datetime.now(timezone.utc) - timedelta(seconds=api_module._PASSWORD_RESET_TOKEN_TTL_SECONDS + 60)).isoformat()
        conn = database.get_connection()
        try:
            conn.execute("UPDATE password_reset_tokens SET created_at = ?", (stale_at,))
            conn.commit()
        finally:
            conn.close()

        resp = client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        assert resp.status_code == 400, "an expired token was accepted"
        assert verify_password(USER_EMAIL, USER_PASSWORD) is not None, "password changed via an expired token"
    finally:
        os.unlink(db_path)
    print("✓ test_expired_token_is_rejected: PASS")


def test_short_password_rejected_without_consuming_the_token():
    """A validation failure must not burn the link -- otherwise one typo forces a whole new email."""
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        _request_reset(client, USER_EMAIL)
        token = _token_from(sent)

        short = client.post("/auth/reset-password", json={"token": token, "new_password": "short"})
        assert short.status_code == 400
        # Same token must still work.
        ok = client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        assert ok.status_code == 200, "the token was consumed by a failed length check"
    finally:
        os.unlink(db_path)
    print("✓ test_short_password_rejected_without_consuming_the_token: PASS")


def test_rate_limit_per_email_and_throttles_unknown_emails_identically():
    """
    Cap applies per address, and must apply to addresses with NO account
    too -- if only real accounts were counted, a 429-vs-200 difference
    would reveal exactly what the generic body hides.
    """
    db_path = _fresh_temp_db()
    try:
        client, _, _ = _setup()
        cap = api_module._FORGOT_PASSWORD_RATE_LIMIT_MAX

        real_codes = [_request_reset(client, USER_EMAIL).status_code for _ in range(cap + 2)]
        api_module._reset_forgot_password_rate_limit_for_tests()
        ghost_codes = [_request_reset(client, "ghost@example.com").status_code for _ in range(cap + 2)]

        assert real_codes.count(200) == cap
        assert real_codes[-1] == 429
        assert real_codes == ghost_codes, "throttling differs by account existence -> oracle"
    finally:
        os.unlink(db_path)
    print("✓ test_rate_limit_per_email_and_throttles_unknown_emails_identically: PASS")


def test_rate_limit_per_ip_across_different_emails():
    """Per-email alone wouldn't stop one host probing many addresses."""
    db_path = _fresh_temp_db()
    try:
        client, _, _ = _setup()
        cap = api_module._FORGOT_PASSWORD_RATE_LIMIT_MAX
        # Every request uses a DIFFERENT email, so only the shared IP
        # counter can trip here.
        codes = [_request_reset(client, f"user{i}@example.com").status_code for i in range(cap + 2)]
        assert codes.count(200) == cap
        assert codes[-1] == 429, "distinct emails from one IP were never throttled"
    finally:
        os.unlink(db_path)
    print("✓ test_rate_limit_per_ip_across_different_emails: PASS")


def test_malformed_and_missing_input_is_handled():
    db_path = _fresh_temp_db()
    try:
        client, _, sent = _setup()
        for payload in ({}, {"email": ""}, {"email": "not-an-email"}, {"email": "   "}):
            # Cleared each time: these all share one IP and there are
            # more payloads here than the per-IP cap, so without this
            # the later ones would 429 for reasons unrelated to input
            # validation, which is what this test is actually about.
            api_module._reset_forgot_password_rate_limit_for_tests()
            resp = client.post("/auth/forgot-password", json=payload)
            assert resp.status_code == 200, payload
        assert sent == [], "a malformed address produced a reset email"

        for payload in ({}, {"token": ""}, {"token": "x"}, {"token": "x", "new_password": ""}):
            resp = client.post("/auth/reset-password", json=payload)
            assert resp.status_code == 400, payload
    finally:
        os.unlink(db_path)
    print("✓ test_malformed_and_missing_input_is_handled: PASS")


if __name__ == "__main__":
    test_reset_email_is_sent_for_a_real_account()
    test_response_is_identical_for_unknown_email_and_no_email_is_sent()
    test_deactivated_user_gets_no_reset_email_but_same_response()
    test_only_the_token_hash_is_stored()
    test_full_reset_then_login_with_new_password()
    test_token_is_single_use()
    test_requesting_again_invalidates_the_previous_link()
    test_expired_token_is_rejected()
    test_short_password_rejected_without_consuming_the_token()
    test_rate_limit_per_email_and_throttles_unknown_emails_identically()
    test_rate_limit_per_ip_across_different_emails()
    test_malformed_and_missing_input_is_handled()
    print("\nAll password reset tests passed.")
