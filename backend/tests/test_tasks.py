"""
Tests for the tasks system (database.py's tasks CRUD, app/tasks.py's
enrichment + convert-from-discrepancy/alert, GET/POST/PATCH/DELETE
/tasks* routes) and the enriched GET /today view (tasks due today/
overdue, new-since-last-login diffing off previous_login_at, unread
messages).

Same conventions as test_teams_and_assignments.py: _fresh_temp_db() +
Flask test_client(), real database.create_user()-backed sessions
(tasks.created_by_user_id/assigned_to_user_id are real FKs).
"""

import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password
from app import tasks as tasks_module
from app.assignments import compute_today_view


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _client_as(role, email, name, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = name
        sess["role"] = role
    return client


def _real_users():
    admin = database.create_user("admin@example.com", "Admin User", hash_password("password123"), role="admin")["id"]
    analyst = database.create_user("analyst@example.com", "Analyst User", hash_password("password123"), role="analyst")["id"]
    viewer = database.create_user("viewer@example.com", "Viewer User", hash_password("password123"), role="viewer")["id"]
    return admin, analyst, viewer


def _client_for(user_id, role):
    user = database.get_user(user_id)
    return _client_as(role, user["email"], user["name"], user_id)


def _make_discrepancy(lease_id=None):
    return database.upsert_discrepancy(
        "rent_mismatch", f"rent_mismatch:{lease_id or 'x'}", "financial",
        "Rent roll rent doesn't match lease abstraction", {"lease_amount": 5000, "rent_roll_amount": 5200},
        lease_id=lease_id, severity="high",
    )


def _make_alert(lease_id=None):
    return database.upsert_alert(
        "lease_expiring", f"lease_expiring:{lease_id or 'x'}", "high",
        "Lease expiring within 90 days", "Tenant lease ends soon with no renewal option exercised",
        {"days_remaining": 45}, lease_id=lease_id,
    )


# ------------------------------------------------------------------
# database.py: tasks CRUD
# ------------------------------------------------------------------

def test_create_and_get_task():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        task_id = database.create_task("Follow up with tenant", admin, description="Call about renewal", due_date="2026-09-01", assigned_to_user_id=analyst)
        task = database.get_task(task_id)
        assert task["title"] == "Follow up with tenant"
        assert task["status"] == "open"
        assert task["assigned_to_user_id"] == analyst
        assert task["created_by_user_id"] == admin
        assert task["completed_at"] is None
    finally:
        os.unlink(db_path)
    print("✓ test_create_and_get_task: PASS")


def test_update_task_status_sets_and_clears_completed_at():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        task_id = database.create_task("Task", admin, assigned_to_user_id=analyst)
        updated = database.update_task_status(task_id, "done")
        assert updated["status"] == "done"
        assert updated["completed_at"] is not None

        reopened = database.update_task_status(task_id, "open")
        assert reopened["status"] == "open"
        assert reopened["completed_at"] is None, "reopening must clear completed_at"
    finally:
        os.unlink(db_path)
    print("✓ test_update_task_status_sets_and_clears_completed_at: PASS")


def test_update_task_fields_can_clear_due_date():
    db_path = _fresh_temp_db()
    try:
        admin, _, _ = _real_users()
        task_id = database.create_task("Task", admin, due_date="2026-09-01")
        updated = database.update_task_fields(task_id, title="Renamed")
        assert updated["title"] == "Renamed"
        assert updated["due_date"] == "2026-09-01", "omitting due_date must leave it unchanged"

        cleared = database.update_task_fields(task_id, _clear_due_date=True)
        assert cleared["due_date"] is None
    finally:
        os.unlink(db_path)
    print("✓ test_update_task_fields_can_clear_due_date: PASS")


def test_list_tasks_filters():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, viewer = _real_users()
        t1 = database.create_task("A", admin, assigned_to_user_id=analyst, due_date="2026-09-01")
        t2 = database.create_task("B", admin, assigned_to_user_id=viewer, due_date="2026-09-10")
        database.update_task_status(t2, "done")

        by_assignee = database.list_tasks(assigned_to_user_id=analyst)
        assert [t["id"] for t in by_assignee] == [t1]

        open_only = database.list_tasks(status="open")
        assert [t["id"] for t in open_only] == [t1]

        due_before = database.list_tasks(due_before="2026-09-05")
        assert [t["id"] for t in due_before] == [t1]
    finally:
        os.unlink(db_path)
    print("✓ test_list_tasks_filters: PASS")


def test_get_tasks_due_today_or_overdue():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        today = date(2026, 8, 24)
        overdue = database.create_task("Overdue", admin, assigned_to_user_id=analyst, due_date="2026-08-20")
        due_today = database.create_task("Due today", admin, assigned_to_user_id=analyst, due_date="2026-08-24")
        future = database.create_task("Future", admin, assigned_to_user_id=analyst, due_date="2026-09-01")
        no_due_date = database.create_task("No due date", admin, assigned_to_user_id=analyst)
        done_overdue = database.create_task("Done but overdue", admin, assigned_to_user_id=analyst, due_date="2026-08-10")
        database.update_task_status(done_overdue, "done")

        results = database.get_tasks_due_today_or_overdue(analyst, today.isoformat())
        ids = {t["id"] for t in results}
        assert ids == {overdue, due_today}, f"got {ids}"
        assert future not in ids
        assert no_due_date not in ids
        assert done_overdue not in ids, "a completed task is never due/overdue regardless of its due date"
    finally:
        os.unlink(db_path)
    print("✓ test_get_tasks_due_today_or_overdue: PASS")


def test_task_detail_enrichment():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        disc_id = _make_discrepancy()
        task_id = database.create_task("Fix it", admin, assigned_to_user_id=analyst, discrepancy_id=disc_id)
        detail = tasks_module.task_detail(database.get_task(task_id))
        assert detail["assigned_to"]["name"] == "Analyst User"
        assert detail["created_by"]["name"] == "Admin User"
        assert detail["discrepancy"]["id"] == disc_id
    finally:
        os.unlink(db_path)
    print("✓ test_task_detail_enrichment: PASS")


def test_create_task_from_discrepancy_carries_context():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        disc_id = _make_discrepancy()
        detail = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst, due_date="2026-09-01")
        assert "Rent roll rent doesn't match" in detail["title"]
        assert detail["discrepancy_id"] == disc_id
        assert detail["source_type"] == "discrepancy"
        assert detail["assigned_to"]["id"] == analyst
        assert detail["due_date"] == "2026-09-01"

        try:
            tasks_module.create_task_from_discrepancy(999999, admin)
            assert False, "should have raised on a nonexistent discrepancy"
        except ValueError:
            pass
    finally:
        os.unlink(db_path)
    print("✓ test_create_task_from_discrepancy_carries_context: PASS")


def test_create_task_from_alert_carries_context():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        alert_id = _make_alert()
        detail = tasks_module.create_task_from_alert(alert_id, admin, assigned_to_user_id=analyst)
        assert "Lease expiring within 90 days" in detail["title"]
        assert detail["source_type"] == "alert"
        assert detail["assigned_to"]["id"] == analyst
    finally:
        os.unlink(db_path)
    print("✓ test_create_task_from_alert_carries_context: PASS")


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

def test_task_routes_require_login_and_role():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, viewer = _real_users()
        anon = app.test_client()
        assert anon.get("/tasks").status_code == 401
        assert anon.post("/tasks", json={}).status_code == 401

        viewer_client = _client_for(viewer, "viewer")
        assert viewer_client.get("/tasks").status_code == 200, "viewers can read"
        assert viewer_client.post("/tasks", json={"title": "x"}).status_code == 403, "viewers cannot write"
    finally:
        os.unlink(db_path)
    print("✓ test_task_routes_require_login_and_role: PASS")


def test_create_task_route_and_validation():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(admin, "admin")

        resp = client.post("/tasks", json={})
        assert resp.status_code == 400, "title is required"

        resp = client.post("/tasks", json={"title": "Renew Acme lease", "assigned_to_user_id": analyst, "due_date": "2026-09-15"})
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["title"] == "Renew Acme lease"
        assert data["assigned_to"]["id"] == analyst
        assert data["created_by"]["id"] == admin

        resp = client.post("/tasks", json={"title": "Bad assignee", "assigned_to_user_id": 999999})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_create_task_route_and_validation: PASS")


def test_assign_and_status_routes():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, viewer = _real_users()
        client = _client_for(admin, "admin")
        task_id = client.post("/tasks", json={"title": "T"}).get_json()["id"]

        resp = client.post(f"/tasks/{task_id}/assign", json={"assigned_to_user_id": analyst})
        assert resp.status_code == 200
        assert resp.get_json()["assigned_to"]["id"] == analyst

        resp = client.post(f"/tasks/{task_id}/status", json={"status": "in_progress"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "in_progress"

        resp = client.post(f"/tasks/{task_id}/status", json={"status": "not_a_status"})
        assert resp.status_code == 400

        resp = client.post(f"/tasks/{task_id}/assign", json={"assigned_to_user_id": None})
        assert resp.status_code == 200
        assert resp.get_json()["assigned_to"] is None, "must support unassigning"
    finally:
        os.unlink(db_path)
    print("✓ test_assign_and_status_routes: PASS")


def test_patch_task_route():
    db_path = _fresh_temp_db()
    try:
        admin, _, _ = _real_users()
        client = _client_for(admin, "admin")
        task_id = client.post("/tasks", json={"title": "T", "due_date": "2026-09-01"}).get_json()["id"]

        resp = client.patch(f"/tasks/{task_id}", json={"title": "Renamed", "description": "New description"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["title"] == "Renamed"
        assert data["description"] == "New description"
        assert data["due_date"] == "2026-09-01", "unspecified due_date must be unchanged"

        resp = client.patch(f"/tasks/{task_id}", json={"due_date": None})
        assert resp.get_json()["due_date"] is None

        resp = client.patch(f"/tasks/{task_id}", json={"title": "   "})
        assert resp.status_code == 400, "blank title must be rejected"
    finally:
        os.unlink(db_path)
    print("✓ test_patch_task_route: PASS")


def test_delete_task_route():
    db_path = _fresh_temp_db()
    try:
        admin, _, _ = _real_users()
        client = _client_for(admin, "admin")
        task_id = client.post("/tasks", json={"title": "T"}).get_json()["id"]
        assert client.delete(f"/tasks/{task_id}").status_code == 200
        assert client.get(f"/tasks/{task_id}").status_code == 404
        assert client.delete(f"/tasks/{task_id}").status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_delete_task_route: PASS")


def test_list_tasks_route_filters():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, viewer = _real_users()
        client = _client_for(admin, "admin")
        client.post("/tasks", json={"title": "A", "assigned_to_user_id": analyst})
        client.post("/tasks", json={"title": "B", "assigned_to_user_id": viewer})

        resp = client.get(f"/tasks?assigned_to={analyst}")
        data = resp.get_json()
        assert len(data) == 1 and data[0]["title"] == "A"
    finally:
        os.unlink(db_path)
    print("✓ test_list_tasks_route_filters: PASS")


def test_convert_discrepancy_and_alert_routes():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(admin, "admin")
        disc_id = _make_discrepancy()
        alert_id = _make_alert()

        resp = client.post(f"/tasks/from-discrepancy/{disc_id}", json={"assigned_to_user_id": analyst})
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["discrepancy_id"] == disc_id

        resp = client.post("/tasks/from-discrepancy/999999", json={})
        assert resp.status_code == 404

        resp = client.post(f"/tasks/from-alert/{alert_id}", json={"assigned_to_user_id": analyst})
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["source_type"] == "alert"

        resp = client.post("/tasks/from-alert/999999", json={})
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_convert_discrepancy_and_alert_routes: PASS")


# ------------------------------------------------------------------
# /today enrichment
# ------------------------------------------------------------------

def test_today_view_includes_due_and_overdue_tasks():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        today = date(2026, 8, 24)
        overdue = database.create_task("Overdue", admin, assigned_to_user_id=analyst, due_date="2026-08-20")
        future = database.create_task("Future", admin, assigned_to_user_id=analyst, due_date="2026-09-01")

        view = compute_today_view(analyst, reference_date=today)
        ids = {t["id"] for t in view["tasks_due_today_or_overdue"]}
        assert overdue in ids and future not in ids
        assert view["summary"]["tasks_due_today_or_overdue_count"] == 1
    finally:
        os.unlink(db_path)
    print("✓ test_today_view_includes_due_and_overdue_tasks: PASS")


def test_today_view_new_since_last_login_uses_previous_not_current_login():
    """The core correctness requirement: /today must diff against the login BEFORE this session, not the one that just started -- otherwise nothing would ever show as new."""
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()

        # First-ever login: previous_login_at is still NULL, so there's no baseline yet.
        database.update_user_last_login(analyst)
        view = compute_today_view(analyst)
        assert view["new_since_last_login"]["since"] is None
        assert view["new_since_last_login"]["discrepancies"] == []

        # Something happens while the user is away...
        disc_id = _make_discrepancy()
        _make_alert()
        database.add_comment("Admin User", "Heads up on this one", discrepancy_id=disc_id)

        # ...then the user logs in again (second login) -- previous_login_at now holds the FIRST login's timestamp.
        database.update_user_last_login(analyst)
        view = compute_today_view(analyst)
        assert view["new_since_last_login"]["since"] is not None
        assert len(view["new_since_last_login"]["discrepancies"]) == 1
        assert len(view["new_since_last_login"]["alerts"]) == 1
        assert len(view["new_since_last_login"]["comments"]) == 1
    finally:
        os.unlink(db_path)
    print("✓ test_today_view_new_since_last_login_uses_previous_not_current_login: PASS")


def test_today_view_includes_unread_messages():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        thread_id = database.create_thread("direct", [admin, analyst], admin)
        database.insert_message(thread_id, admin, "Hey, can you look at this?")

        view = compute_today_view(analyst)
        assert view["unread_messages"]["total_unread"] == 1
        assert len(view["unread_messages"]["threads"]) == 1
        assert view["summary"]["unread_message_count"] == 1
    finally:
        os.unlink(db_path)
    print("✓ test_today_view_includes_unread_messages: PASS")


def test_today_route_still_works_end_to_end():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        resp = client.get("/today")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "tasks_due_today_or_overdue" in data
        assert "new_since_last_login" in data
        assert "unread_messages" in data
    finally:
        os.unlink(db_path)
    print("✓ test_today_route_still_works_end_to_end: PASS")


if __name__ == "__main__":
    test_create_and_get_task()
    test_update_task_status_sets_and_clears_completed_at()
    test_update_task_fields_can_clear_due_date()
    test_list_tasks_filters()
    test_get_tasks_due_today_or_overdue()
    test_task_detail_enrichment()
    test_create_task_from_discrepancy_carries_context()
    test_create_task_from_alert_carries_context()
    test_task_routes_require_login_and_role()
    test_create_task_route_and_validation()
    test_assign_and_status_routes()
    test_patch_task_route()
    test_delete_task_route()
    test_list_tasks_route_filters()
    test_convert_discrepancy_and_alert_routes()
    test_today_view_includes_due_and_overdue_tasks()
    test_today_view_new_since_last_login_uses_previous_not_current_login()
    test_today_view_includes_unread_messages()
    test_today_route_still_works_end_to_end()
    print("\nAll tasks tests passed.")
