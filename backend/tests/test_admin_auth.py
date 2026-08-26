"""
Tests for team authentication: app/auth.py's hash/verify functions
directly, and the /auth/login, /auth/logout, /auth/session routes
plus the admin-role-gated /waitlist (GET) and /waitlist/<id>/approve
and /waitlist/<id>/deny routes, end to end through Flask's in-process
test_client() (which keeps its own cookie jar across requests within
one `client` instance -- exactly what's needed to exercise a real
login -> protected-route -> logout session lifecycle without a
separately running live server).

Real users are created directly via database.create_user() against
each test's own fresh temp db, rather than mocking environment
variables -- there is no env-var-based admin account anymore (see
app.database._seed_first_admin_user for the one-time migration path,
covered separately in test_teams_and_assignments.py).
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password, verify_password

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


TEST_EMAIL = "admin@example.com"
TEST_PASSWORD = "correct horse battery staple"
TEST_HASH = hash_password(TEST_PASSWORD)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _create_admin():
    """Creates the one admin user this file's route tests log in as. Assumes init_db() has already run against a fresh temp db with no ADMIN_EMAIL/ADMIN_PASSWORD_HASH seed (so this is the only user)."""
    result = database.create_user(TEST_EMAIL, "Test Admin", TEST_HASH, role="admin")
    assert result["status"] == "created", result
    return result["id"]


# ---------------------------------------------------------------------
# app/auth.py unit tests
# ---------------------------------------------------------------------

def test_hash_password_produces_a_real_bcrypt_hash_not_the_plaintext():
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$"), "not a recognizable bcrypt hash"
    print("✓ test_hash_password_produces_a_real_bcrypt_hash_not_the_plaintext: PASS")


def test_verify_password_correct_email_and_password():
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        user = verify_password(TEST_EMAIL, TEST_PASSWORD)
        assert user is not None and user["email"] == TEST_EMAIL and user["role"] == "admin"
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_correct_email_and_password: PASS")


def test_verify_password_wrong_password():
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        assert verify_password(TEST_EMAIL, "wrong password") is None
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_wrong_password: PASS")


def test_verify_password_wrong_email():
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        assert verify_password("nobody@example.com", TEST_PASSWORD) is None
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_wrong_email: PASS")


def test_verify_password_email_is_case_insensitive():
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        user = verify_password(TEST_EMAIL.upper(), TEST_PASSWORD)
        assert user is not None and user["email"] == TEST_EMAIL
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_email_is_case_insensitive: PASS")


def test_verify_password_fails_closed_when_no_users_exist_at_all():
    db_path = _fresh_temp_db()
    try:
        assert verify_password(TEST_EMAIL, TEST_PASSWORD) is None
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_fails_closed_when_no_users_exist_at_all: PASS")


def test_verify_password_deactivated_user_cannot_log_in():
    db_path = _fresh_temp_db()
    try:
        user_id = _create_admin()
        database.update_user_status(user_id, "deactivated")
        assert verify_password(TEST_EMAIL, TEST_PASSWORD) is None
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_deactivated_user_cannot_log_in: PASS")


def test_verify_password_malformed_hash_does_not_crash():
    db_path = _fresh_temp_db()
    try:
        database.create_user(TEST_EMAIL, "Test Admin", "not-a-real-bcrypt-hash", role="admin")
        assert verify_password(TEST_EMAIL, TEST_PASSWORD) is None
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_malformed_hash_does_not_crash: PASS")


# ---------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------

def test_login_route_succeeds_with_correct_credentials_and_starts_a_session():
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        client = app.test_client()
        resp = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["email"] == TEST_EMAIL
        assert resp.get_json()["role"] == "admin"

        session_resp = client.get("/auth/session").get_json()
        assert session_resp["authenticated"] is True
        assert session_resp["email"] == TEST_EMAIL
        assert session_resp["role"] == "admin"
    finally:
        os.unlink(db_path)
    print("✓ test_login_route_succeeds_with_correct_credentials_and_starts_a_session: PASS")


def test_login_route_wrong_password_and_wrong_email_give_the_identical_generic_error():
    """The whole point: a caller must not be able to tell which of the two was wrong from the response."""
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        client = app.test_client()

        wrong_password = client.post("/auth/login", json={"email": TEST_EMAIL, "password": "nope"})
        wrong_email = client.post("/auth/login", json={"email": "nobody@example.com", "password": TEST_PASSWORD})

        assert wrong_password.status_code == 401
        assert wrong_email.status_code == 401
        assert wrong_password.get_json() == wrong_email.get_json(), "response body must not reveal which field was wrong"
    finally:
        os.unlink(db_path)
    print("✓ test_login_route_wrong_password_and_wrong_email_give_the_identical_generic_error: PASS")


def test_login_route_error_message_never_leaks_a_traceback_or_path():
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        resp = app.test_client().post("/auth/login", json={"email": TEST_EMAIL, "password": "wrong"})
        body_text = str(resp.get_json())
        assert "Traceback" not in body_text and "/Users/" not in body_text and "/tmp/" not in body_text
    finally:
        os.unlink(db_path)
    print("✓ test_login_route_error_message_never_leaks_a_traceback_or_path: PASS")


def test_session_check_reports_unauthenticated_before_login():
    db_path = _fresh_temp_db()
    try:
        resp = app.test_client().get("/auth/session")
        assert resp.status_code == 200
        assert resp.get_json() == {"authenticated": False, "id": None, "email": None, "name": None, "role": None}
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
        _create_admin()
        client = app.test_client()
        client.post("/waitlist", json={"email": "applicant@example.com"})

        still_blocked = client.get("/waitlist")
        assert still_blocked.status_code == 401, "signing up is public, but viewing the list must not be"

        login = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
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
        _create_admin()
        client = app.test_client()
        client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert client.get("/waitlist").status_code == 200

        logout_resp = client.post("/auth/logout")
        assert logout_resp.status_code == 200

        assert client.get("/auth/session").get_json()["authenticated"] is False
        assert client.get("/waitlist").status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_logout_ends_the_session_and_protected_routes_401_again: PASS")


def test_non_admin_role_gets_403_not_401_on_admin_only_route():
    """A logged-in-but-wrong-role request must be distinguishable from a not-logged-in one."""
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        result = database.create_user("analyst@example.com", "Test Analyst", hash_password("whatever password"), role="analyst")
        assert result["status"] == "created"

        client = app.test_client()
        client.post("/auth/login", json={"email": "analyst@example.com", "password": "whatever password"})
        resp = client.get("/waitlist")
        assert resp.status_code == 403, resp.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_non_admin_role_gets_403_not_401_on_admin_only_route: PASS")


def test_deny_route_requires_admin_and_flips_status_to_denied():
    db_path = _fresh_temp_db()
    try:
        _create_admin()
        client = app.test_client()
        client.post("/waitlist", json={"email": "notafit@example.com"})
        signup_id = database.get_all_waitlist_signups()[0]["id"]

        blocked = client.post(f"/waitlist/{signup_id}/deny")
        assert blocked.status_code == 401

        client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
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
        _create_admin()
        client = app.test_client()
        client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        resp = client.post("/waitlist/999999/deny")
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_deny_route_for_nonexistent_signup_returns_404: PASS")


def test_client_signup_and_check_flow_still_fully_public_and_unaffected():
    """The client-facing waitlist signup + /waitlist/check gate must need no session at all -- only the admin-only views changed."""
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
    test_verify_password_correct_email_and_password()
    test_verify_password_wrong_password()
    test_verify_password_wrong_email()
    test_verify_password_email_is_case_insensitive()
    test_verify_password_fails_closed_when_no_users_exist_at_all()
    test_verify_password_deactivated_user_cannot_log_in()
    test_verify_password_malformed_hash_does_not_crash()
    test_login_route_succeeds_with_correct_credentials_and_starts_a_session()
    test_login_route_wrong_password_and_wrong_email_give_the_identical_generic_error()
    test_login_route_error_message_never_leaks_a_traceback_or_path()
    test_session_check_reports_unauthenticated_before_login()
    test_protected_waitlist_route_401s_without_a_session()
    test_protected_waitlist_route_works_after_real_login()
    test_logout_ends_the_session_and_protected_routes_401_again()
    test_non_admin_role_gets_403_not_401_on_admin_only_route()
    test_deny_route_requires_admin_and_flips_status_to_denied()
    test_deny_route_for_nonexistent_signup_returns_404()
    test_client_signup_and_check_flow_still_fully_public_and_unaffected()
    print("\nAll team auth tests passed.")
