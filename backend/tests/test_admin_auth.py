"""
Tests for admin authentication: app/auth.py's hash/verify functions
directly, and the /admin/login, /admin/logout, /admin/session routes
plus the now-admin-gated /waitlist (GET) and /waitlist/<id>/approve
and /waitlist/<id>/deny routes, end to end through Flask's in-process
test_client() (which keeps its own cookie jar across requests within
one `client` instance -- exactly what's needed to exercise a real
login -> protected-route -> logout session lifecycle without a
separately running live server).

ADMIN_EMAIL/ADMIN_PASSWORD_HASH are patched directly via
mock.patch.dict(os.environ, ...) for each test that needs specific
credentials configured -- app/auth.py reads them fresh from the
environment on every call (unlike LOCAL_DEV_MODE, which api.py reads
once into a module-level constant at import time), so this works
without any module-attribute patching.
"""

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password, verify_admin_credentials, admin_login_is_configured

# This file exercises real /waitlist POST/approve/deny routes through
# app.test_client(), which -- unlike test_waitlist_email.py -- never
# mocks app.email_service. Popped here (after app.api's own
# load_dotenv() has already run, so this can't be re-populated from
# backend/.env) so email_service._send()'s existing "not configured"
# fail-safe applies regardless of what's actually set in the real
# environment: every send_* call becomes a safe no-op instead of a real
# Gmail send. Protects this file even when run directly
# (`python3 test_admin_auth.py`), not just via run_all_tests.py's own
# env sanitizing. Added after a real incident where this file's
# "notafit@example.com" / "client@example.com" test signups sent real
# emails to the real ADMIN_EMAIL inbox -- see DECISIONS.md.
os.environ.pop("EMAIL_USER", None)
os.environ.pop("EMAIL_APP_PASSWORD", None)


TEST_EMAIL = "timmypisano24@gmail.com"
TEST_PASSWORD = "correct horse battery staple"
TEST_HASH = hash_password(TEST_PASSWORD)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _with_admin_env():
    return mock.patch.dict(os.environ, {"ADMIN_EMAIL": TEST_EMAIL, "ADMIN_PASSWORD_HASH": TEST_HASH})


# ---------------------------------------------------------------------
# app/auth.py unit tests
# ---------------------------------------------------------------------

def test_hash_password_produces_a_real_bcrypt_hash_not_the_plaintext():
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$"), "not a recognizable bcrypt hash"
    print("✓ test_hash_password_produces_a_real_bcrypt_hash_not_the_plaintext: PASS")


def test_verify_admin_credentials_correct_email_and_password():
    with _with_admin_env():
        assert verify_admin_credentials(TEST_EMAIL, TEST_PASSWORD) is True
    print("✓ test_verify_admin_credentials_correct_email_and_password: PASS")


def test_verify_admin_credentials_wrong_password():
    with _with_admin_env():
        assert verify_admin_credentials(TEST_EMAIL, "wrong password") is False
    print("✓ test_verify_admin_credentials_wrong_password: PASS")


def test_verify_admin_credentials_wrong_email():
    with _with_admin_env():
        assert verify_admin_credentials("nobody@example.com", TEST_PASSWORD) is False
    print("✓ test_verify_admin_credentials_wrong_email: PASS")


def test_verify_admin_credentials_email_is_case_insensitive():
    with _with_admin_env():
        assert verify_admin_credentials(TEST_EMAIL.upper(), TEST_PASSWORD) is True
    print("✓ test_verify_admin_credentials_email_is_case_insensitive: PASS")


def test_verify_admin_credentials_fails_closed_when_not_configured():
    with mock.patch.dict(os.environ, {"ADMIN_EMAIL": "", "ADMIN_PASSWORD_HASH": ""}):
        assert verify_admin_credentials(TEST_EMAIL, TEST_PASSWORD) is False
        assert admin_login_is_configured() is False
    print("✓ test_verify_admin_credentials_fails_closed_when_not_configured: PASS")


def test_verify_admin_credentials_malformed_hash_does_not_crash():
    with mock.patch.dict(os.environ, {"ADMIN_EMAIL": TEST_EMAIL, "ADMIN_PASSWORD_HASH": "not-a-real-bcrypt-hash"}):
        assert verify_admin_credentials(TEST_EMAIL, TEST_PASSWORD) is False
    print("✓ test_verify_admin_credentials_malformed_hash_does_not_crash: PASS")


# ---------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------

def test_login_route_succeeds_with_correct_credentials_and_starts_a_session():
    db_path = _fresh_temp_db()
    try:
        with _with_admin_env():
            client = app.test_client()
            resp = client.post("/admin/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            assert resp.status_code == 200, resp.get_json()
            assert resp.get_json()["email"] == TEST_EMAIL

            session_resp = client.get("/admin/session").get_json()
            assert session_resp == {"authenticated": True, "email": TEST_EMAIL}
    finally:
        os.unlink(db_path)
    print("✓ test_login_route_succeeds_with_correct_credentials_and_starts_a_session: PASS")


def test_login_route_wrong_password_and_wrong_email_give_the_identical_generic_error():
    """The whole point: a caller must not be able to tell which of the two was wrong from the response."""
    db_path = _fresh_temp_db()
    try:
        with _with_admin_env():
            client = app.test_client()

            wrong_password = client.post("/admin/login", json={"email": TEST_EMAIL, "password": "nope"})
            wrong_email = client.post("/admin/login", json={"email": "nobody@example.com", "password": TEST_PASSWORD})

            assert wrong_password.status_code == 401
            assert wrong_email.status_code == 401
            assert wrong_password.get_json() == wrong_email.get_json(), "response body must not reveal which field was wrong"
    finally:
        os.unlink(db_path)
    print("✓ test_login_route_wrong_password_and_wrong_email_give_the_identical_generic_error: PASS")


def test_login_route_error_message_never_leaks_a_traceback_or_path():
    db_path = _fresh_temp_db()
    try:
        with _with_admin_env():
            resp = app.test_client().post("/admin/login", json={"email": TEST_EMAIL, "password": "wrong"})
            body_text = str(resp.get_json())
            assert "Traceback" not in body_text and "/Users/" not in body_text and "/tmp/" not in body_text
    finally:
        os.unlink(db_path)
    print("✓ test_login_route_error_message_never_leaks_a_traceback_or_path: PASS")


def test_session_check_reports_unauthenticated_before_login():
    db_path = _fresh_temp_db()
    try:
        resp = app.test_client().get("/admin/session")
        assert resp.status_code == 200
        assert resp.get_json() == {"authenticated": False, "email": None}
    finally:
        os.unlink(db_path)
    print("✓ test_session_check_reports_unauthenticated_before_login: PASS")


def test_protected_waitlist_route_401s_without_a_session():
    db_path = _fresh_temp_db()
    try:
        resp = app.test_client().get("/waitlist")
        assert resp.status_code == 401
        assert "error" in resp.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_protected_waitlist_route_401s_without_a_session: PASS")


def test_protected_waitlist_route_works_after_real_login():
    db_path = _fresh_temp_db()
    try:
        with _with_admin_env():
            client = app.test_client()
            client.post("/waitlist", json={"email": "applicant@example.com"})

            still_blocked = client.get("/waitlist")
            assert still_blocked.status_code == 401, "signing up is public, but viewing the list must not be"

            login = client.post("/admin/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            assert login.status_code == 200

            now_allowed = client.get("/waitlist")
            assert now_allowed.status_code == 200
            assert any(s["email"] == "applicant@example.com" for s in now_allowed.get_json())
    finally:
        os.unlink(db_path)
    print("✓ test_protected_waitlist_route_works_after_real_login: PASS")


def test_logout_ends_the_session_and_protected_routes_401_again():
    db_path = _fresh_temp_db()
    try:
        with _with_admin_env():
            client = app.test_client()
            client.post("/admin/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            assert client.get("/waitlist").status_code == 200

            logout_resp = client.post("/admin/logout")
            assert logout_resp.status_code == 200

            assert client.get("/admin/session").get_json()["authenticated"] is False
            assert client.get("/waitlist").status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_logout_ends_the_session_and_protected_routes_401_again: PASS")


def test_deny_route_requires_admin_and_flips_status_to_denied():
    db_path = _fresh_temp_db()
    try:
        with _with_admin_env():
            client = app.test_client()
            client.post("/waitlist", json={"email": "notafit@example.com"})
            signup_id = database.get_all_waitlist_signups()[0]["id"]

            blocked = client.post(f"/waitlist/{signup_id}/deny")
            assert blocked.status_code == 401

            client.post("/admin/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            resp = client.post(f"/waitlist/{signup_id}/deny")
            assert resp.status_code == 200
            assert resp.get_json()["status"] == "denied"

            listing = client.get("/waitlist").get_json()
            assert any(s["email"] == "notafit@example.com" and s["status"] == "denied" for s in listing)
    finally:
        os.unlink(db_path)
    print("✓ test_deny_route_requires_admin_and_flips_status_to_denied: PASS")


def test_deny_route_for_nonexistent_signup_returns_404():
    db_path = _fresh_temp_db()
    try:
        with _with_admin_env():
            client = app.test_client()
            client.post("/admin/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
            resp = client.post("/waitlist/999999/deny")
            assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_deny_route_for_nonexistent_signup_returns_404: PASS")


def test_client_signup_and_check_flow_still_fully_public_and_unaffected():
    """The client-facing waitlist signup + /waitlist/check gate must need no admin session at all -- only the admin-only views changed."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        signup = client.post("/waitlist", json={"email": "client@example.com"})
        assert signup.status_code == 201

        check = client.post("/waitlist/check", json={"email": "client@example.com"})
        assert check.status_code == 200
        assert check.get_json() == {"approved": False, "found": True}
    finally:
        os.unlink(db_path)
    print("✓ test_client_signup_and_check_flow_still_fully_public_and_unaffected: PASS")


if __name__ == "__main__":
    test_hash_password_produces_a_real_bcrypt_hash_not_the_plaintext()
    test_verify_admin_credentials_correct_email_and_password()
    test_verify_admin_credentials_wrong_password()
    test_verify_admin_credentials_wrong_email()
    test_verify_admin_credentials_email_is_case_insensitive()
    test_verify_admin_credentials_fails_closed_when_not_configured()
    test_verify_admin_credentials_malformed_hash_does_not_crash()
    test_login_route_succeeds_with_correct_credentials_and_starts_a_session()
    test_login_route_wrong_password_and_wrong_email_give_the_identical_generic_error()
    test_login_route_error_message_never_leaks_a_traceback_or_path()
    test_session_check_reports_unauthenticated_before_login()
    test_protected_waitlist_route_401s_without_a_session()
    test_protected_waitlist_route_works_after_real_login()
    test_logout_ends_the_session_and_protected_routes_401_again()
    test_deny_route_requires_admin_and_flips_status_to_denied()
    test_deny_route_for_nonexistent_signup_returns_404()
    test_client_signup_and_check_flow_still_fully_public_and_unaffected()
    print("\nAll admin auth tests passed.")
