"""
Tests for team management: database.py's users CRUD, auth.py's
verify_password/require_role, and the GET/POST/PATCH /team/members*
routes. (Assignment tests join this file once that feature lands --
see the collaboration-platform plan.)

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_discrepancies.py.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password, verify_password, ROLE_RANK


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _client_as(role, email="test@example.com", name="Test User", user_id=1):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = name
        sess["role"] = role
    return client


# ------------------------------------------------------------------
# database.py: users CRUD
# ------------------------------------------------------------------

def test_create_user_and_get_by_email_case_insensitive():
    db_path = _fresh_temp_db()
    try:
        result = database.create_user("Alice@Example.com", "Alice", hash_password("password123"), role="analyst")
        assert result["status"] == "created"
        user = database.get_user_by_email("alice@example.com")
        assert user is not None
        assert user["email"] == "alice@example.com"
        assert user["name"] == "Alice"
        assert user["role"] == "analyst"
        assert user["status"] == "active"
    finally:
        os.unlink(db_path)
    print("✓ test_create_user_and_get_by_email_case_insensitive: PASS")


def test_create_user_duplicate_email_returns_duplicate_status():
    db_path = _fresh_temp_db()
    try:
        database.create_user("bob@example.com", "Bob", hash_password("password123"), role="viewer")
        result = database.create_user("bob@example.com", "Bob Again", hash_password("other"), role="admin")
        assert result["status"] == "duplicate"
        assert database.get_user_by_email("bob@example.com")["name"] == "Bob", "the original row must be untouched"
    finally:
        os.unlink(db_path)
    print("✓ test_create_user_duplicate_email_returns_duplicate_status: PASS")


def test_update_user_role_status_name():
    db_path = _fresh_temp_db()
    try:
        result = database.create_user("carol@example.com", "Carol", hash_password("password123"), role="viewer")
        user_id = result["id"]

        assert database.update_user_role(user_id, "admin") is True
        assert database.get_user(user_id)["role"] == "admin"

        assert database.update_user_status(user_id, "deactivated") is True
        assert database.get_user(user_id)["status"] == "deactivated"

        assert database.update_user_name(user_id, "Carol Renamed") is True
        assert database.get_user(user_id)["name"] == "Carol Renamed"

        assert database.update_user_role(999999, "admin") is False, "nonexistent id returns False"
    finally:
        os.unlink(db_path)
    print("✓ test_update_user_role_status_name: PASS")


def test_role_rank_ordering():
    assert ROLE_RANK["viewer"] < ROLE_RANK["analyst"] < ROLE_RANK["admin"]
    print("✓ test_role_rank_ordering: PASS")


def test_verify_password_deactivated_user_fails_even_with_correct_password():
    db_path = _fresh_temp_db()
    try:
        result = database.create_user("dana@example.com", "Dana", hash_password("password123"), role="analyst")
        database.update_user_status(result["id"], "deactivated")
        assert verify_password("dana@example.com", "password123") is None
    finally:
        os.unlink(db_path)
    print("✓ test_verify_password_deactivated_user_fails_even_with_correct_password: PASS")


# ------------------------------------------------------------------
# Route-level permission matrix: viewer/analyst 403, admin 200
# ------------------------------------------------------------------

def test_team_members_routes_require_admin_role():
    db_path = _fresh_temp_db()
    try:
        for role in ("viewer", "analyst"):
            client = _client_as(role)
            resp = client.get("/team/members")
            assert resp.status_code == 403, f"{role} should be 403'd on GET /team/members, got {resp.status_code}"

            resp = client.post("/team/members", json={"email": "x@example.com", "name": "X", "role": "viewer", "password": "password123"})
            assert resp.status_code == 403, f"{role} should be 403'd on POST /team/members"

        admin_client = _client_as("admin")
        resp = admin_client.get("/team/members")
        assert resp.status_code == 200, resp.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_team_members_routes_require_admin_role: PASS")


def test_team_members_routes_401_without_any_session():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/team/members")
        assert resp.status_code == 401, "no session at all must be 401, not 403 -- see auth.require_role's docstring for why the distinction matters"
    finally:
        os.unlink(db_path)
    print("✓ test_team_members_routes_401_without_any_session: PASS")


def test_create_team_member_happy_path_never_leaks_password_hash():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("admin")
        resp = client.post("/team/members", json={
            "email": "newhire@example.com", "name": "New Hire", "role": "analyst", "password": "a-real-password",
        })
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["email"] == "newhire@example.com"
        assert data["role"] == "analyst"
        assert "password_hash" not in data, "a user response must never include the password hash"

        # The password actually works for real login.
        assert verify_password("newhire@example.com", "a-real-password") is not None
    finally:
        os.unlink(db_path)
    print("✓ test_create_team_member_happy_path_never_leaks_password_hash: PASS")


def test_create_team_member_validation():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("admin")

        resp = client.post("/team/members", json={"email": "x@example.com", "name": "X"})
        assert resp.status_code == 400, "missing role and password"

        resp = client.post("/team/members", json={"email": "x@example.com", "name": "X", "role": "superuser", "password": "password123"})
        assert resp.status_code == 400, "invalid role"

        resp = client.post("/team/members", json={"email": "not-an-email", "name": "X", "role": "viewer", "password": "password123"})
        assert resp.status_code == 400, "invalid email"

        resp = client.post("/team/members", json={"email": "x@example.com", "name": "X", "role": "viewer", "password": "short"})
        assert resp.status_code == 400, "password too short"
    finally:
        os.unlink(db_path)
    print("✓ test_create_team_member_validation: PASS")


def test_create_team_member_duplicate_email_returns_409():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("admin")
        client.post("/team/members", json={"email": "dup@example.com", "name": "First", "role": "viewer", "password": "password123"})
        resp = client.post("/team/members", json={"email": "dup@example.com", "name": "Second", "role": "admin", "password": "password456"})
        assert resp.status_code == 409
    finally:
        os.unlink(db_path)
    print("✓ test_create_team_member_duplicate_email_returns_409: PASS")


def test_update_team_member_route():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("admin")
        create_resp = client.post("/team/members", json={"email": "toupdate@example.com", "name": "Original", "role": "viewer", "password": "password123"})
        member_id = create_resp.get_json()["id"]

        resp = client.patch(f"/team/members/{member_id}", json={"role": "analyst", "status": "deactivated", "name": "Updated Name"})
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["role"] == "analyst"
        assert data["status"] == "deactivated"
        assert data["name"] == "Updated Name"

        resp = client.patch("/team/members/999999", json={"role": "admin"})
        assert resp.status_code == 404

        resp = client.patch(f"/team/members/{member_id}", json={"role": "not-a-role"})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_update_team_member_route: PASS")


def test_reset_password_route_actually_changes_the_password():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("admin")
        create_resp = client.post("/team/members", json={"email": "reset@example.com", "name": "Reset Me", "role": "viewer", "password": "old-password-123"})
        member_id = create_resp.get_json()["id"]

        resp = client.post(f"/team/members/{member_id}/reset-password", json={"password": "new-password-456"})
        assert resp.status_code == 200

        assert verify_password("reset@example.com", "old-password-123") is None, "old password must no longer work"
        assert verify_password("reset@example.com", "new-password-456") is not None, "new password must work"

        resp = client.post("/team/members/999999/reset-password", json={"password": "new-password-456"})
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_reset_password_route_actually_changes_the_password: PASS")


if __name__ == "__main__":
    test_create_user_and_get_by_email_case_insensitive()
    test_create_user_duplicate_email_returns_duplicate_status()
    test_update_user_role_status_name()
    test_role_rank_ordering()
    test_verify_password_deactivated_user_fails_even_with_correct_password()
    test_team_members_routes_require_admin_role()
    test_team_members_routes_401_without_any_session()
    test_create_team_member_happy_path_never_leaks_password_hash()
    test_create_team_member_validation()
    test_create_team_member_duplicate_email_returns_409()
    test_update_team_member_route()
    test_reset_password_route_actually_changes_the_password()
    print("\nAll team management tests passed.")
