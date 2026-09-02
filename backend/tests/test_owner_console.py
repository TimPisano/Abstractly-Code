"""
Tests for the owner console: is_owner is a flag independent of
role/ROLE_RANK (database.py's set_user_owner_flag,
_seed_first_admin_user's is_owner=1 seed), auth.py's require_owner
(401/404/200, never 403 -- see its own docstring for why), and every
/owner/* route (accounts list/detail/suspend/reactivate/reset-
password, revenue/expenses CRUD, finance summary).

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_teams_and_assignments.py. The permission
matrix below is the single most important thing this file checks:
role='admin' must NOT imply is_owner -- a regression here would expose
account suspension and financial data to every team admin.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password


def _fresh_temp_db():
    """
    Note: app.api's load_dotenv() (run at import time, above) puts
    this developer's REAL ADMIN_EMAIL/ADMIN_PASSWORD_HASH into the
    process-wide environment for the rest of this process's life. If
    those are left set here, _seed_first_admin_user seeds that real
    account into every "fresh" temp DB this helper creates -- harmless
    for tests that don't care who the first user is, but it silently
    defeats any test (like this file's own
    test_seed_first_admin_user_sets_is_owner) that needs the table to
    start genuinely empty so it can control the seed via its own env
    vars. Popping them here, scoped to just this one init_db() call,
    keeps every test in this file deterministic regardless of the
    local .env's contents.
    """
    real_admin_email = os.environ.pop("ADMIN_EMAIL", None)
    real_admin_hash = os.environ.pop("ADMIN_PASSWORD_HASH", None)
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        database.configure(tmp.name)
        database.init_db()
        return tmp.name
    finally:
        if real_admin_email is not None:
            os.environ["ADMIN_EMAIL"] = real_admin_email
        if real_admin_hash is not None:
            os.environ["ADMIN_PASSWORD_HASH"] = real_admin_hash


def _client_as(user_id, email, role, is_owner):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = "Test User"
        sess["role"] = role
        sess["is_owner"] = is_owner
    return client


OWNER_ROUTES_GET = [
    "/owner/accounts",
    "/owner/revenue",
    "/owner/expenses",
    "/owner/finance/summary",
]


def test_seed_first_admin_user_sets_is_owner():
    db_path = _fresh_temp_db()
    try:
        os.environ["ADMIN_EMAIL"] = "seeded.owner@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("whatever12345")
        try:
            database.init_db()  # idempotent -- users table already exists but empty, so this re-triggers the seed
        finally:
            del os.environ["ADMIN_EMAIL"]
            del os.environ["ADMIN_PASSWORD_HASH"]
        user = database.get_user_by_email("seeded.owner@example.com")
        assert user is not None
        assert user["role"] == "admin"
        assert user["is_owner"] == 1, "the env-var-seeded first admin must also be seeded as owner, so production owner access survives a redeploy on non-persistent storage"
    finally:
        os.unlink(db_path)
    print("✓ test_seed_first_admin_user_sets_is_owner: PASS")


def test_set_user_owner_flag_independent_of_role():
    db_path = _fresh_temp_db()
    try:
        result = database.create_user("plain.admin@example.com", "Plain Admin", hash_password("password123"), role="admin")
        user_id = result["id"]
        user = database.get_user(user_id)
        assert user["is_owner"] == 0, "role='admin' must not imply is_owner by default"

        database.set_user_owner_flag(user_id, True)
        assert database.get_user(user_id)["is_owner"] == 1

        database.set_user_owner_flag(user_id, False)
        assert database.get_user(user_id)["is_owner"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_set_user_owner_flag_independent_of_role: PASS")


def test_owner_routes_401_with_no_session():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        for route in OWNER_ROUTES_GET:
            resp = client.get(route)
            assert resp.status_code == 401, f"{route} should 401 with no session, got {resp.status_code}"
    finally:
        os.unlink(db_path)
    print("✓ test_owner_routes_401_with_no_session: PASS")


def test_owner_routes_404_for_regular_viewer_and_analyst():
    db_path = _fresh_temp_db()
    try:
        for role in ("viewer", "analyst"):
            client = _client_as(1, f"{role}@example.com", role, is_owner=False)
            for route in OWNER_ROUTES_GET:
                resp = client.get(route)
                assert resp.status_code == 404, f"{route} should 404 for a non-owner {role}, got {resp.status_code}"
                assert resp.status_code != 403, "require_owner must never leak a 403 (that would confirm the route exists)"
    finally:
        os.unlink(db_path)
    print("✓ test_owner_routes_404_for_regular_viewer_and_analyst: PASS")


def test_owner_routes_404_for_non_owner_admin():
    """The single most important check: role='admin' must NOT imply owner access."""
    db_path = _fresh_temp_db()
    try:
        client = _client_as(1, "admin@example.com", "admin", is_owner=False)
        for route in OWNER_ROUTES_GET:
            resp = client.get(route)
            assert resp.status_code == 404, f"{route} should 404 for a non-owner admin, got {resp.status_code}"
    finally:
        os.unlink(db_path)
    print("✓ test_owner_routes_404_for_non_owner_admin: PASS")


def test_owner_routes_200_for_real_owner():
    db_path = _fresh_temp_db()
    try:
        result = database.create_user("owner@example.com", "Owner", hash_password("password123"), role="admin")
        database.set_user_owner_flag(result["id"], True)
        client = _client_as(result["id"], "owner@example.com", "admin", is_owner=True)
        for route in OWNER_ROUTES_GET:
            resp = client.get(route)
            assert resp.status_code == 200, f"{route} should 200 for the real owner, got {resp.status_code}"
    finally:
        os.unlink(db_path)
    print("✓ test_owner_routes_200_for_real_owner: PASS")


def test_owner_accounts_list_never_includes_password_hash():
    db_path = _fresh_temp_db()
    try:
        result = database.create_user("owner@example.com", "Owner", hash_password("password123"), role="admin")
        database.set_user_owner_flag(result["id"], True)
        database.create_user("someone@example.com", "Someone", hash_password("password456"), role="viewer")
        client = _client_as(result["id"], "owner@example.com", "admin", is_owner=True)

        resp = client.get("/owner/accounts")
        assert resp.status_code == 200
        accounts = resp.get_json()
        assert len(accounts) == 2
        for a in accounts:
            assert "password_hash" not in a, "password_hash must never appear in an owner console response"

        resp2 = client.get(f"/owner/accounts/{result['id']}")
        assert "password_hash" not in resp2.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_owner_accounts_list_never_includes_password_hash: PASS")


def test_owner_can_suspend_reactivate_and_reset_password():
    db_path = _fresh_temp_db()
    try:
        owner_result = database.create_user("owner@example.com", "Owner", hash_password("ownerpass123"), role="admin")
        database.set_user_owner_flag(owner_result["id"], True)
        owner_client = _client_as(owner_result["id"], "owner@example.com", "admin", is_owner=True)

        target = database.create_user("target@example.com", "Target", hash_password("originalpass123"), role="viewer")
        target_id = target["id"]

        resp = owner_client.post(f"/owner/accounts/{target_id}/suspend")
        assert resp.status_code == 200
        assert database.get_user(target_id)["status"] == "deactivated"

        target_client = app.test_client()
        login_resp = target_client.post("/auth/login", json={"email": "target@example.com", "password": "originalpass123"})
        assert login_resp.status_code == 401, "a suspended account must not be able to log in"

        resp = owner_client.post(f"/owner/accounts/{target_id}/reactivate")
        assert resp.status_code == 200
        assert database.get_user(target_id)["status"] == "active"

        login_resp = target_client.post("/auth/login", json={"email": "target@example.com", "password": "originalpass123"})
        assert login_resp.status_code == 200, "a reactivated account must be able to log in again"

        resp = owner_client.post(f"/owner/accounts/{target_id}/reset-password", json={"new_password": "brandnewpass456"})
        assert resp.status_code == 200

        old_pw_resp = target_client.post("/auth/login", json={"email": "target@example.com", "password": "originalpass123"})
        assert old_pw_resp.status_code == 401, "old password must stop working after an owner reset"

        new_pw_resp = target_client.post("/auth/login", json={"email": "target@example.com", "password": "brandnewpass456"})
        assert new_pw_resp.status_code == 200, "new password must work after an owner reset"
    finally:
        os.unlink(db_path)
    print("✓ test_owner_can_suspend_reactivate_and_reset_password: PASS")


def test_owner_revenue_expense_crud_and_finance_summary():
    db_path = _fresh_temp_db()
    try:
        owner_result = database.create_user("owner@example.com", "Owner", hash_password("ownerpass123"), role="admin")
        database.set_user_owner_flag(owner_result["id"], True)
        client = _client_as(owner_result["id"], "owner@example.com", "admin", is_owner=True)

        r1 = client.post("/owner/revenue", json={"date": "2026-08-01", "amount": 500, "source": "Acme"})
        assert r1.status_code == 201
        r2 = client.post("/owner/revenue", json={"date": "2026-09-01", "amount": 1500, "source": "Acme"})
        assert r2.status_code == 201
        e1 = client.post("/owner/expenses", json={"date": "2026-08-05", "amount": 85.50, "category": "Hosting"})
        assert e1.status_code == 201

        summary = client.get("/owner/finance/summary").get_json()
        assert summary["total_revenue"] == 2000
        assert summary["total_expenses"] == 85.50
        assert summary["profit"] == 2000 - 85.50
        months = {m["month"]: m for m in summary["monthly_trend"]}
        assert months["2026-08"]["revenue"] == 500
        assert months["2026-08"]["expenses"] == 85.50
        assert months["2026-09"]["revenue"] == 1500

        revenue_id = r1.get_json()["id"]
        del_resp = client.delete(f"/owner/revenue/{revenue_id}")
        assert del_resp.status_code == 200

        summary_after = client.get("/owner/finance/summary").get_json()
        assert summary_after["total_revenue"] == 1500, "deleting the $500 entry must drop total revenue to just the remaining $1500"

        missing_resp = client.delete(f"/owner/revenue/{revenue_id}")
        assert missing_resp.status_code == 404

        bad_resp = client.post("/owner/revenue", json={"date": "2026-09-01", "source": "No amount"})
        assert bad_resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_owner_revenue_expense_crud_and_finance_summary: PASS")


def test_owner_accounts_filters():
    db_path = _fresh_temp_db()
    try:
        owner_result = database.create_user("owner@example.com", "Owner", hash_password("ownerpass123"), role="admin")
        database.set_user_owner_flag(owner_result["id"], True)
        client = _client_as(owner_result["id"], "owner@example.com", "admin", is_owner=True)

        database.create_user("alice@example.com", "Alice", hash_password("password123"), role="viewer")
        bob_result = database.create_user("bob@example.com", "Bob", hash_password("password123"), role="viewer")
        database.update_user_status(bob_result["id"], "deactivated")

        resp = client.get("/owner/accounts?email=alice")
        emails = [a["email"] for a in resp.get_json()]
        assert emails == ["alice@example.com"]

        resp = client.get("/owner/accounts?status=deactivated")
        emails = [a["email"] for a in resp.get_json()]
        assert emails == ["bob@example.com"]
    finally:
        os.unlink(db_path)
    print("✓ test_owner_accounts_filters: PASS")


if __name__ == "__main__":
    test_seed_first_admin_user_sets_is_owner()
    test_set_user_owner_flag_independent_of_role()
    test_owner_routes_401_with_no_session()
    test_owner_routes_404_for_regular_viewer_and_analyst()
    test_owner_routes_404_for_non_owner_admin()
    test_owner_routes_200_for_real_owner()
    test_owner_accounts_list_never_includes_password_hash()
    test_owner_can_suspend_reactivate_and_reset_password()
    test_owner_revenue_expense_crud_and_finance_summary()
    test_owner_accounts_filters()
    print("\nAll owner console tests passed!")
