"""
Tests for team management (database.py's users CRUD, auth.py's
verify_password/require_role, GET/POST/PATCH /team/members*) and
assignments (database.py's assignments CRUD, app/assignments.py's
target_key derivation + Today view, GET/POST/PATCH/DELETE
/assignments* and GET /today).

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_discrepancies.py.
"""

import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password, verify_password, ROLE_RANK
from app.assignments import derive_target_key, compute_today_view
from app.portfolio import FIELD_NAMES


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


# ------------------------------------------------------------------
# Assignments: database.py CRUD + app/assignments.py
# ------------------------------------------------------------------

def _fields(**overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            value = overrides[name]
            result[name] = {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


def _real_users(db_ignored=None):
    """Two real user rows (not just a fake session identity) -- needed since assignment_detail() resolves assignee/assigner via database.get_user()."""
    admin = database.create_user("admin@example.com", "Admin User", hash_password("password123"), role="admin")["id"]
    analyst = database.create_user("analyst@example.com", "Analyst User", hash_password("password123"), role="analyst")["id"]
    return admin, analyst


def _client_for_real_user(user_id, role):
    user = database.get_user(user_id)
    return _client_as(role, email=user["email"], name=user["name"], user_id=user_id)


def test_derive_target_key():
    assert derive_target_key("lease", 42) == "42"
    assert derive_target_key("lease", "42") == "42"
    assert derive_target_key("discrepancy", 7) == "7"
    assert derive_target_key("property", "123 Main St, Suite 100") == derive_target_key("property", "123 Main St, Suite 200"), \
        "two suites at the same building must resolve to the same property target_key"
    try:
        derive_target_key("not_a_type", "x")
        assert False, "must raise on an invalid target_type"
    except ValueError:
        pass
    print("✓ test_derive_target_key: PASS")


def test_upsert_assignment_reassign_resets_status():
    db_path = _fresh_temp_db()
    try:
        admin_id, analyst_id = _real_users()
        second_analyst_id = database.create_user("second@example.com", "Second Analyst", hash_password("password123"), role="analyst")["id"]

        a1 = database.upsert_assignment("lease", "1", analyst_id, admin_id)
        database.update_assignment_status(a1, "resolved", admin_id)
        assert database.get_assignment(a1)["status"] == "resolved"

        a2 = database.upsert_assignment("lease", "1", second_analyst_id, admin_id)
        assert a2 == a1, "same target -- must update the SAME row, not create a second one"
        reloaded = database.get_assignment(a1)
        assert reloaded["status"] == "assigned", "reassigning must reset status, not inherit 'resolved'"
        assert reloaded["assigned_to_user_id"] == second_analyst_id
    finally:
        os.unlink(db_path)
    print("✓ test_upsert_assignment_reassign_resets_status: PASS")


def test_assignments_routes_full_lifecycle():
    db_path = _fresh_temp_db()
    try:
        admin_id, analyst_id = _real_users()
        lease_id = database.insert_lease("base.pdf", _fields(tenant="Acme Corp"))
        admin_client = _client_for_real_user(admin_id, "admin")

        resp = admin_client.post("/assignments", json={"target_type": "lease", "target": lease_id, "assigned_to_user_id": analyst_id, "note": "check this"})
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["status"] == "assigned"
        assert data["assigned_to"]["id"] == analyst_id
        assignment_id = data["id"]

        resp = admin_client.get(f"/assignments/{assignment_id}")
        assert resp.status_code == 200
        assert resp.get_json()["note"] == "check this"

        resp = admin_client.patch(f"/assignments/{assignment_id}", json={"status": "in_review"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "in_review"

        resp = admin_client.get("/assignments?target_type=lease")
        assert len(resp.get_json()) == 1

        resp = admin_client.delete(f"/assignments/{assignment_id}")
        assert resp.status_code == 200
        assert admin_client.get(f"/assignments/{assignment_id}").status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_assignments_routes_full_lifecycle: PASS")


def test_assignments_routes_require_at_least_analyst_for_writes():
    db_path = _fresh_temp_db()
    try:
        admin_id, analyst_id = _real_users()
        viewer_id = database.create_user("viewer@example.com", "Viewer User", hash_password("password123"), role="viewer")["id"]
        lease_id = database.insert_lease("base.pdf", _fields(tenant="Acme Corp"))

        viewer_client = _client_for_real_user(viewer_id, "viewer")
        resp = viewer_client.post("/assignments", json={"target_type": "lease", "target": lease_id, "assigned_to_user_id": analyst_id})
        assert resp.status_code == 403

        # reads still work for a viewer -- only writes are gated to analyst+
        resp = viewer_client.get("/assignments")
        assert resp.status_code == 200
    finally:
        os.unlink(db_path)
    print("✓ test_assignments_routes_require_at_least_analyst_for_writes: PASS")


def test_assignment_route_validates_target_exists():
    db_path = _fresh_temp_db()
    try:
        admin_id, analyst_id = _real_users()
        admin_client = _client_for_real_user(admin_id, "admin")

        resp = admin_client.post("/assignments", json={"target_type": "lease", "target": 999999, "assigned_to_user_id": analyst_id})
        assert resp.status_code == 404, "assigning a lease that doesn't exist must 404"

        resp = admin_client.post("/assignments", json={"target_type": "property", "target": "1 Upcoming Acquisition Rd", "assigned_to_user_id": analyst_id})
        assert resp.status_code == 201, "a property assignment needs no existence check -- an upcoming acquisition is legitimate"

        resp = admin_client.post("/assignments", json={"target_type": "lease", "target": 1, "assigned_to_user_id": 999999})
        assert resp.status_code == 400, "a nonexistent assignee must be rejected"
    finally:
        os.unlink(db_path)
    print("✓ test_assignment_route_validates_target_exists: PASS")


def test_concurrent_assignment_of_same_target_does_not_500():
    """The brief's own concern: two people racing to claim the same target must not raise, and must resolve to exactly one row."""
    db_path = _fresh_temp_db()
    try:
        admin_id, analyst_id = _real_users()
        errors = []
        ids = []
        lock = threading.Lock()

        def race(i):
            try:
                aid = database.upsert_assignment("lease", "1", analyst_id, admin_id)
                with lock:
                    ids.append(aid)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=race, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"concurrent upsert_assignment must never raise: {errors}"
        assert len(set(ids)) == 1, "all 20 concurrent calls must resolve to the SAME row"
    finally:
        os.unlink(db_path)
    print("✓ test_concurrent_assignment_of_same_target_does_not_500: PASS")


# ------------------------------------------------------------------
# Today view
# ------------------------------------------------------------------

def test_compute_today_view_includes_enriched_assignments_and_alerts():
    db_path = _fresh_temp_db()
    try:
        admin_id, analyst_id = _real_users()
        lease_id = database.insert_lease("base.pdf", _fields(tenant="Acme Corp", rent_amount="$5,000.00"))
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k1", category="missing_clause", message="m", details={}, lease_id=lease_id,
        )
        # lease_id/discrepancy_id passed explicitly, same as the real
        # /assignments route does -- upsert_assignment doesn't infer
        # them from target_key itself, only the API layer does that
        # derivation (see create_assignment_route in api.py).
        database.upsert_assignment("lease", str(lease_id), analyst_id, admin_id, lease_id=lease_id)
        database.upsert_assignment("discrepancy", str(disc_id), analyst_id, admin_id, discrepancy_id=disc_id)
        database.upsert_alert(alert_type="lease_expiration", natural_key="a1", severity="high", title="t", message="m", details={})

        view = compute_today_view(analyst_id)
        assert view["summary"]["total_open_assignments"] == 2
        assert view["summary"]["assigned_lease_count"] == 1
        assert view["summary"]["assigned_discrepancy_count"] == 1
        assert view["assigned_leases"][0]["lease"]["id"] == lease_id, "must be enriched with the real lease, not just the id"
        assert view["assigned_discrepancies"][0]["discrepancy"]["id"] == disc_id
        assert view["summary"]["active_alert_count"] == 1
        assert view["summary"]["high_severity_alert_count"] == 1

        # resolving the assignment must remove it from Today
        database.update_assignment_status(view["assigned_leases"][0]["id"], "resolved", admin_id)
        view2 = compute_today_view(analyst_id)
        assert view2["summary"]["assigned_lease_count"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_compute_today_view_includes_enriched_assignments_and_alerts: PASS")


def test_today_route_defaults_to_caller_and_validates_user():
    db_path = _fresh_temp_db()
    try:
        admin_id, analyst_id = _real_users()
        analyst_client = _client_for_real_user(analyst_id, "analyst")

        resp = analyst_client.get("/today")
        assert resp.status_code == 200
        assert resp.get_json()["user_id"] == analyst_id, "with no user_id param, /today defaults to the caller"

        resp = analyst_client.get("/today?user_id=999999")
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_today_route_defaults_to_caller_and_validates_user: PASS")


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
    test_derive_target_key()
    test_upsert_assignment_reassign_resets_status()
    test_assignments_routes_full_lifecycle()
    test_assignments_routes_require_at_least_analyst_for_writes()
    test_assignment_route_validates_target_exists()
    test_concurrent_assignment_of_same_target_does_not_500()
    test_compute_today_view_includes_enriched_assignments_and_alerts()
    test_today_route_defaults_to_caller_and_validates_user()
    print("\nAll team management, assignment, and Today-view tests passed.")
