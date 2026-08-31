"""
Tests for four extensions to the task workflow built on top of
in-task document editing (test_lease_field_editing.py): bulk task
actions, task comments (surfaced in the activity feed), task
priority (and its effect on Today/list ordering), and undo on a
recent field edit.

Also includes a regression check that the original single-task
completion + discrepancy-resolution flow (test_lease_field_editing.py's
core scenario) still behaves identically after these additions.

Same conventions as test_lease_field_editing.py / test_tasks.py:
_fresh_temp_db() + Flask test_client(), real database.create_user()-
backed sessions.
"""

import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password
from app import tasks as tasks_module
from app.portfolio import FIELD_NAMES


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
    second_analyst = database.create_user("second@example.com", "Second Analyst", hash_password("password123"), role="analyst")["id"]
    viewer = database.create_user("viewer@example.com", "Viewer User", hash_password("password123"), role="viewer")["id"]
    return admin, analyst, second_analyst, viewer


def _client_for(user_id, role):
    user = database.get_user(user_id)
    return _client_as(role, user["email"], user["name"], user_id)


def _fields(**overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            value = overrides[name]
            result[name] = {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


def _make_lease(**field_overrides):
    return database.insert_lease("lease.pdf", _fields(**field_overrides), display_name="Test Lease")


def _make_discrepancy(lease_id, field="rent_amount", key_suffix="0"):
    return database.upsert_discrepancy(
        "lease_risk_flag", f"lease_risk:{lease_id}:field_mismatch:{field}:{key_suffix}", "field_mismatch",
        f"{field} looks wrong", {"lease_amount": 5000}, lease_id=lease_id, severity="high",
    )


# ------------------------------------------------------------------
# 1. Bulk task actions
# ------------------------------------------------------------------

def test_bulk_status_completes_and_dismisses_plain_tasks():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        t1 = client.post("/tasks", json={"title": "A"}).get_json()["id"]
        t2 = client.post("/tasks", json={"title": "B"}).get_json()["id"]
        t3 = client.post("/tasks", json={"title": "C"}).get_json()["id"]

        resp = client.post("/tasks/bulk-status", json={"ids": [t1, t2, 999999], "status": "done"})
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert set(data["updated"]) == {t1, t2}
        assert data["not_found"] == [999999]
        assert data["skipped_needs_discrepancy"] == []

        assert database.get_task(t1)["status"] == "done"
        assert database.get_task(t2)["status"] == "done"
        assert database.get_task(t3)["status"] == "open", "untouched task must be unaffected"

        resp = client.post("/tasks/bulk-status", json={"ids": [t3], "status": "dismissed"})
        assert resp.status_code == 200
        assert database.get_task(t3)["status"] == "dismissed"

        activity = client.get("/activity?limit=10").get_json()
        bulk_entries = [a for a in activity if a["action_type"] == "tasks_bulk_status_updated"]
        assert len(bulk_entries) == 2
    finally:
        os.unlink(db_path)
    print("✓ test_bulk_status_completes_and_dismisses_plain_tasks: PASS")


def test_bulk_status_skips_discrepancy_tied_tasks_needing_confirmation():
    """The scenario the user's own request names explicitly: an analyst clearing a batch of similar low-risk discrepancy tasks. Bulk 'done' must never silently guess correct_source for a discrepancy-tied task -- it must be skipped and reported, not force-completed."""
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc1 = _make_discrepancy(lease_id, key_suffix="0")
        disc2 = _make_discrepancy(lease_id, key_suffix="1")
        task1 = tasks_module.create_task_from_discrepancy(disc1, admin, assigned_to_user_id=analyst)
        task2 = tasks_module.create_task_from_discrepancy(disc2, admin, assigned_to_user_id=analyst)
        plain_task = client.post("/tasks", json={"title": "Not tied to anything"}).get_json()["id"]

        resp = client.post("/tasks/bulk-status", json={"ids": [task1["id"], task2["id"], plain_task], "status": "done"})
        data = resp.get_json()
        assert set(data["skipped_needs_discrepancy"]) == {task1["id"], task2["id"]}
        assert data["updated"] == [plain_task]

        assert database.get_task(task1["id"])["status"] != "done"
        assert database.get_discrepancy(disc1)["status"] == "open", "must not be silently resolved by a bulk action"
        assert database.get_task(plain_task)["status"] == "done"

        # Resolve them for real first, THEN bulk-complete succeeds.
        database.resolve_discrepancy(disc1, "lease_document", "confirmed", "Analyst User")
        database.resolve_discrepancy(disc2, "lease_document", "confirmed", "Analyst User")
        resp = client.post("/tasks/bulk-status", json={"ids": [task1["id"], task2["id"]], "status": "done"})
        assert set(resp.get_json()["updated"]) == {task1["id"], task2["id"]}
    finally:
        os.unlink(db_path)
    print("✓ test_bulk_status_skips_discrepancy_tied_tasks_needing_confirmation: PASS")


def test_bulk_status_validation():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        assert client.post("/tasks/bulk-status", json={"ids": [], "status": "done"}).status_code == 400
        assert client.post("/tasks/bulk-status", json={"ids": [1], "status": "not_a_status"}).status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_bulk_status_validation: PASS")


def test_bulk_reassign():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, second_analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        t1 = client.post("/tasks", json={"title": "A"}).get_json()["id"]
        t2 = client.post("/tasks", json={"title": "B", "assigned_to_user_id": analyst}).get_json()["id"]

        resp = client.post("/tasks/bulk-reassign", json={"ids": [t1, t2, 999999], "assigned_to_user_id": second_analyst})
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert set(data["updated"]) == {t1, t2}
        assert data["not_found"] == [999999]
        assert database.get_task(t1)["assigned_to_user_id"] == second_analyst
        assert database.get_task(t2)["assigned_to_user_id"] == second_analyst

        resp = client.post("/tasks/bulk-reassign", json={"ids": [t1], "assigned_to_user_id": None})
        assert resp.status_code == 200
        assert database.get_task(t1)["assigned_to_user_id"] is None

        resp = client.post("/tasks/bulk-reassign", json={"ids": [t1], "assigned_to_user_id": 999999})
        assert resp.status_code == 400

        activity = client.get("/activity?limit=10").get_json()
        assert any(a["action_type"] == "tasks_bulk_reassigned" for a in activity)
    finally:
        os.unlink(db_path)
    print("✓ test_bulk_reassign: PASS")


def test_bulk_action_routes_require_login_and_analyst_role():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, viewer = _real_users()
        anon = app.test_client()
        assert anon.post("/tasks/bulk-status", json={"ids": [1], "status": "done"}).status_code == 401
        assert anon.post("/tasks/bulk-reassign", json={"ids": [1]}).status_code == 401

        viewer_client = _client_for(viewer, "viewer")
        assert viewer_client.post("/tasks/bulk-status", json={"ids": [1], "status": "done"}).status_code == 403
        assert viewer_client.post("/tasks/bulk-reassign", json={"ids": [1]}).status_code == 403
    finally:
        os.unlink(db_path)
    print("✓ test_bulk_action_routes_require_login_and_analyst_role: PASS")


# ------------------------------------------------------------------
# 2. Task comments
# ------------------------------------------------------------------

def test_task_comments_create_list_and_activity_feed():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        task_id = client.post("/tasks", json={"title": "Follow up with broker"}).get_json()["id"]

        resp = client.get(f"/tasks/{task_id}/comments")
        assert resp.status_code == 200
        assert resp.get_json() == []

        resp = client.post(f"/tasks/{task_id}/comments", json={"body": "Checked with the broker, this is intentional."})
        assert resp.status_code == 201, resp.get_json()
        comments = resp.get_json()
        assert len(comments) == 1
        assert comments[0]["body"] == "Checked with the broker, this is intentional."
        assert comments[0]["author_name"] == "Analyst User"

        # Must show up in task_detail too.
        detail = client.get(f"/tasks/{task_id}").get_json()
        assert len(detail["comments"]) == 1

        # And explicitly, per this feature's own requirement, in the activity feed.
        activity = client.get("/activity?limit=10").get_json()
        commented = [a for a in activity if a["action_type"] == "task_commented"]
        assert len(commented) == 1
        assert "Analyst User" in commented[0]["description"]
        assert "broker" in commented[0]["description"]
    finally:
        os.unlink(db_path)
    print("✓ test_task_comments_create_list_and_activity_feed: PASS")


def test_task_comments_separate_from_field_edits():
    """Comments (discussion) and field_edits (data-correction audit trail) must be two genuinely distinct lists on task_detail, never conflated."""
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        task_id = client.post("/tasks", json={"title": "Review", "lease_id": lease_id}).get_json()["id"]

        client.post(f"/tasks/{task_id}/comments", json={"body": "Looking into this."})
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$4,500.00", "task_id": task_id})

        detail = client.get(f"/tasks/{task_id}").get_json()
        assert len(detail["comments"]) == 1
        assert len(detail["field_edits"]) == 1
        assert detail["comments"][0]["body"] == "Looking into this."
        assert detail["field_edits"][0]["field_name"] == "rent_amount"
    finally:
        os.unlink(db_path)
    print("✓ test_task_comments_separate_from_field_edits: PASS")


def test_task_comments_validation_and_404():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        assert client.post("/tasks/999999/comments", json={"body": "x"}).status_code == 404
        task_id = client.post("/tasks", json={"title": "T"}).get_json()["id"]
        assert client.post(f"/tasks/{task_id}/comments", json={"body": "  "}).status_code == 400
        assert client.post(f"/tasks/{task_id}/comments", json={}).status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_task_comments_validation_and_404: PASS")


# ------------------------------------------------------------------
# 3. Task priority
# ------------------------------------------------------------------

def test_create_task_with_priority_and_default():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        default_task = client.post("/tasks", json={"title": "Normal"}).get_json()
        assert default_task["priority"] == "normal"

        urgent_task = client.post("/tasks", json={"title": "Urgent", "priority": "high"}).get_json()
        assert urgent_task["priority"] == "high"

        resp = client.post("/tasks", json={"title": "Bad", "priority": "critical"})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_create_task_with_priority_and_default: PASS")


def test_patch_task_can_change_priority():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        task_id = client.post("/tasks", json={"title": "T"}).get_json()["id"]
        assert database.get_task(task_id)["priority"] == "normal"

        resp = client.patch(f"/tasks/{task_id}", json={"priority": "high"})
        assert resp.status_code == 200
        assert resp.get_json()["priority"] == "high"
        assert database.get_task(task_id)["priority"] == "high"

        resp = client.patch(f"/tasks/{task_id}", json={"priority": "not_valid"})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_patch_task_can_change_priority: PASS")


def test_high_priority_tasks_sort_first_in_list_and_today_view():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        today = date(2026, 8, 24)

        # Deliberately create the LOW-urgency one first and the earliest-due
        # normal task, so a naive due-date-only sort would rank them ahead
        # of the high-priority one -- proving priority genuinely wins.
        normal_earlier = client.post("/tasks", json={
            "title": "Normal, due earlier", "assigned_to_user_id": analyst, "due_date": "2026-08-20",
        }).get_json()["id"]
        urgent_later = client.post("/tasks", json={
            "title": "Urgent, due later", "assigned_to_user_id": analyst, "due_date": "2026-08-23", "priority": "high",
        }).get_json()["id"]

        listed = client.get(f"/tasks?assigned_to={analyst}").get_json()
        ids_in_order = [t["id"] for t in listed]
        assert ids_in_order.index(urgent_later) < ids_in_order.index(normal_earlier), \
            "a high-priority task must sort ahead of an earlier-due normal task"

        from app.assignments import compute_today_view
        view = compute_today_view(analyst, reference_date=today)
        due_ids_in_order = [t["id"] for t in view["tasks_due_today_or_overdue"]]
        assert due_ids_in_order.index(urgent_later) < due_ids_in_order.index(normal_earlier), \
            "the Today view must also surface the high-priority task first"
    finally:
        os.unlink(db_path)
    print("✓ test_high_priority_tasks_sort_first_in_list_and_today_view: PASS")


# ------------------------------------------------------------------
# 4. Undo on recent field edits
# ------------------------------------------------------------------

def _age_edit(edit_id, minutes_ago):
    """Test-only helper: backdates a real edit row's created_at to simulate time passing, since we can't actually wait in a unit test."""
    conn = database.get_connection()
    conn.execute(
        "UPDATE lease_field_edits SET created_at = ? WHERE id = ?",
        ((datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(), edit_id),
    )
    conn.commit()
    conn.close()


def test_undo_reverts_a_recent_edit_and_restores_original_citation():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")

        edit_resp = client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$9,999.00", "note": "oops, wrong number"})
        assert edit_resp.status_code == 200
        edits = database.get_lease_field_edits(lease_id=lease_id, field_name="rent_amount")
        edit_id = edits[0]["id"]

        assert database.get_lease(lease_id)["extracted_fields"]["rent_amount"]["value"] == "$9,999.00"

        resp = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={})
        assert resp.status_code == 200, resp.get_json()
        restored = resp.get_json()["field"]
        assert restored["value"] == "$4,000.00"
        # The original value came from real extraction (a citation) --
        # undo must restore THAT exact entry, not treat itself as a
        # fresh manual edit that clobbers the citation with null.
        assert restored["source"] == {"page": 1, "quote": "...$4,000.00..."}
        assert restored["confidence"] == "high"

        lease_after = database.get_lease(lease_id)
        assert lease_after["extracted_fields"]["rent_amount"]["value"] == "$4,000.00"

        # Original edit marked reverted, a new revert edit row exists -- nothing deleted.
        all_edits = database.get_lease_field_edits(lease_id=lease_id, field_name="rent_amount")
        assert len(all_edits) == 2
        assert all_edits[0]["id"] == edit_id
        assert all_edits[0]["reverted_at"] is not None

        activity = client.get("/activity?limit=10").get_json()
        assert any(a["action_type"] == "lease_field_edit_undone" for a in activity)
    finally:
        os.unlink(db_path)
    print("✓ test_undo_reverts_a_recent_edit_and_restores_original_citation: PASS")


def test_undo_rejects_already_reverted_edit():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$9,999.00"})
        edit_id = database.get_lease_field_edits(lease_id=lease_id, field_name="rent_amount")[0]["id"]

        first = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={})
        assert first.status_code == 200

        second = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={})
        assert second.status_code == 400
        assert "already" in second.get_json()["error"].lower()
    finally:
        os.unlink(db_path)
    print("✓ test_undo_rejects_already_reverted_edit: PASS")


def test_undo_rejects_when_superseded_by_a_newer_edit():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")

        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,000.00"})
        first_edit_id = database.get_lease_field_edits(lease_id=lease_id, field_name="rent_amount")[0]["id"]
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$6,000.00"})

        resp = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{first_edit_id}/undo", json={})
        assert resp.status_code == 400
        assert "newer edit" in resp.get_json()["error"].lower()
        assert database.get_lease(lease_id)["extracted_fields"]["rent_amount"]["value"] == "$6,000.00", \
            "the rejected undo must not have changed anything"
    finally:
        os.unlink(db_path)
    print("✓ test_undo_rejects_when_superseded_by_a_newer_edit: PASS")


def test_undo_rejects_after_time_window_expires():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$9,999.00"})
        edit_id = database.get_lease_field_edits(lease_id=lease_id, field_name="rent_amount")[0]["id"]

        _age_edit(edit_id, minutes_ago=tasks_module.UNDO_WINDOW_MINUTES + 5)

        resp = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={})
        assert resp.status_code == 400
        assert "minutes old" in resp.get_json()["error"]
        assert database.get_lease(lease_id)["extracted_fields"]["rent_amount"]["value"] == "$9,999.00"
    finally:
        os.unlink(db_path)
    print("✓ test_undo_rejects_after_time_window_expires: PASS")


def test_undo_rejects_when_linked_task_already_done():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc_id = _make_discrepancy(lease_id)
        task = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst)
        task_id = task["id"]

        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,000.00", "task_id": task_id})
        edit_id = database.get_lease_field_edits(task_id=task_id)[0]["id"]

        client.post(f"/tasks/{task_id}/status", json={"status": "done", "correct_source": "lease_document", "note": "fixed"})

        resp = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={})
        assert resp.status_code == 400
        assert "already complete" in resp.get_json()["error"].lower()
        assert database.get_lease(lease_id)["extracted_fields"]["rent_amount"]["value"] == "$5,000.00"
    finally:
        os.unlink(db_path)
    print("✓ test_undo_rejects_when_linked_task_already_done: PASS")


def test_undo_allowed_when_linked_task_dismissed_not_done():
    """Dismissing a task is explicitly NOT a 'completed/resolved' action (see the api.py route's own reasoning) -- undo must still be available."""
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        task_id = client.post("/tasks", json={"title": "T", "lease_id": lease_id}).get_json()["id"]

        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,000.00", "task_id": task_id})
        edit_id = database.get_lease_field_edits(task_id=task_id)[0]["id"]

        client.post(f"/tasks/{task_id}/status", json={"status": "dismissed"})

        resp = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={})
        assert resp.status_code == 200, resp.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_undo_allowed_when_linked_task_dismissed_not_done: PASS")


def test_undo_route_requires_login_and_analyst_role():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, viewer = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$9,999.00"})
        edit_id = database.get_lease_field_edits(lease_id=lease_id, field_name="rent_amount")[0]["id"]

        anon = app.test_client()
        assert anon.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={}).status_code == 401

        viewer_client = _client_for(viewer, "viewer")
        assert viewer_client.post(f"/leases/{lease_id}/fields/rent_amount/edits/{edit_id}/undo", json={}).status_code == 403
    finally:
        os.unlink(db_path)
    print("✓ test_undo_route_requires_login_and_analyst_role: PASS")


def test_undo_route_404_for_nonexistent_edit():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        resp = client.post(f"/leases/{lease_id}/fields/rent_amount/edits/999999/undo", json={})
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_undo_route_404_for_nonexistent_edit: PASS")


# ------------------------------------------------------------------
# Regression: the original single-task completion + discrepancy-
# resolution flow (test_lease_field_editing.py's core scenario) must
# still behave identically after all four extensions above.
# ------------------------------------------------------------------

def test_regression_single_task_completion_and_discrepancy_resolution_still_works():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc_id = _make_discrepancy(lease_id)
        task = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst)
        task_id = task["id"]

        # Still rejected without confirmation.
        resp = client.post(f"/tasks/{task_id}/status", json={"status": "done"})
        assert resp.status_code == 400
        assert database.get_discrepancy(disc_id)["status"] == "open"

        # Edit the field, same as before.
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,000.00", "task_id": task_id})

        # Still succeeds with confirmation, still resolves the discrepancy for real.
        resp = client.post(f"/tasks/{task_id}/status", json={
            "status": "done", "correct_source": "lease_document", "note": "Rent corrected per lease p.3",
        })
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["status"] == "done"
        assert data["discrepancy_resolved_now"] is True
        assert data["discrepancy"]["status"] == "resolved"
        assert database.get_discrepancy(disc_id)["status"] == "resolved"

        # Still drops out of the open view, still shows up in the done view.
        open_tasks = client.get(f"/tasks?assigned_to={analyst}&status=open").get_json()
        assert all(t["id"] != task_id for t in open_tasks)
        done_tasks = client.get(f"/tasks?assigned_to={analyst}&status=done").get_json()
        assert any(t["id"] == task_id for t in done_tasks)

        # And the new field_edits/comments keys are present and correctly shaped even on this classic path.
        detail = client.get(f"/tasks/{task_id}").get_json()
        assert len(detail["field_edits"]) == 1
        assert detail["comments"] == []
        assert detail["priority"] == "normal"
    finally:
        os.unlink(db_path)
    print("✓ test_regression_single_task_completion_and_discrepancy_resolution_still_works: PASS")


if __name__ == "__main__":
    test_bulk_status_completes_and_dismisses_plain_tasks()
    test_bulk_status_skips_discrepancy_tied_tasks_needing_confirmation()
    test_bulk_status_validation()
    test_bulk_reassign()
    test_bulk_action_routes_require_login_and_analyst_role()
    test_task_comments_create_list_and_activity_feed()
    test_task_comments_separate_from_field_edits()
    test_task_comments_validation_and_404()
    test_create_task_with_priority_and_default()
    test_patch_task_can_change_priority()
    test_high_priority_tasks_sort_first_in_list_and_today_view()
    test_undo_reverts_a_recent_edit_and_restores_original_citation()
    test_undo_rejects_already_reverted_edit()
    test_undo_rejects_when_superseded_by_a_newer_edit()
    test_undo_rejects_after_time_window_expires()
    test_undo_rejects_when_linked_task_already_done()
    test_undo_allowed_when_linked_task_dismissed_not_done()
    test_undo_route_requires_login_and_analyst_role()
    test_undo_route_404_for_nonexistent_edit()
    test_regression_single_task_completion_and_discrepancy_resolution_still_works()
    print("\nAll task workflow extension tests passed.")
