"""
Tests for the in-task document editing workflow: database.py's
update_lease_field/get_lease_field_edits, PATCH /leases/<id>/fields/
<name>, the `manual_edits` extension to GET .../fields/<name>/source,
task_detail's `lease`/`field_edits` attachment, and the discrepancy-
resolution-on-task-completion extension to POST /tasks/<id>/status.

Same conventions as test_tasks.py / test_discrepancies.py:
_fresh_temp_db() + Flask test_client(), real database.create_user()-
backed sessions.
"""

import os
import sys
import tempfile

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
    viewer = database.create_user("viewer@example.com", "Viewer User", hash_password("password123"), role="viewer")["id"]
    return admin, analyst, viewer


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


def _make_discrepancy(lease_id, field="rent_amount"):
    return database.upsert_discrepancy(
        "lease_risk_flag", f"lease_risk:{lease_id}:field_mismatch:{field}:0", "field_mismatch",
        f"{field} looks wrong", {"lease_amount": 5000}, lease_id=lease_id, severity="high",
    )


# ------------------------------------------------------------------
# database.py: update_lease_field / get_lease_field_edits
# ------------------------------------------------------------------

def test_update_lease_field_mutates_extracted_fields_and_logs_edit():
    db_path = _fresh_temp_db()
    try:
        lease_id = _make_lease(rent_amount="$4,000.00")
        new_entry = database.update_lease_field(
            lease_id, "rent_amount", "$5,000.00", edited_by="Alice", edited_by_email="alice@example.com", note="Corrected from lease p.3"
        )
        assert new_entry["value"] == "$5,000.00"
        assert new_entry["source"] is None, "a manual edit has no page/quote citation to fabricate"
        assert new_entry["confidence"] == "high"
        assert new_entry["manually_verified"] is True

        lease = database.get_lease(lease_id)
        assert lease["extracted_fields"]["rent_amount"]["value"] == "$5,000.00", \
            "the actual lease record must reflect the edit, not just the response"

        edits = database.get_lease_field_edits(lease_id=lease_id)
        assert len(edits) == 1
        edit = edits[0]
        assert edit["field_name"] == "rent_amount"
        assert edit["old_value"]["value"] == "$4,000.00"
        assert edit["new_value"]["value"] == "$5,000.00"
        assert edit["edited_by"] == "Alice"
        assert edit["edited_by_email"] == "alice@example.com"
        assert edit["note"] == "Corrected from lease p.3"
    finally:
        os.unlink(db_path)
    print("✓ test_update_lease_field_mutates_extracted_fields_and_logs_edit: PASS")


def test_update_lease_field_can_clear_to_none_with_manually_verified_flag():
    db_path = _fresh_temp_db()
    try:
        lease_id = _make_lease(cam_charges="$500.00")
        new_entry = database.update_lease_field(lease_id, "cam_charges", None, edited_by="Bob")
        assert new_entry["value"] is None
        assert new_entry["manually_verified"] is True, \
            "a human-confirmed absence must be distinguishable from extraction never having tried"

        lease = database.get_lease(lease_id)
        assert lease["extracted_fields"]["cam_charges"]["value"] is None
    finally:
        os.unlink(db_path)
    print("✓ test_update_lease_field_can_clear_to_none_with_manually_verified_flag: PASS")


def test_update_lease_field_nonexistent_lease_returns_none():
    db_path = _fresh_temp_db()
    try:
        assert database.update_lease_field(999999, "rent_amount", "$1", edited_by="X") is None
    finally:
        os.unlink(db_path)
    print("✓ test_update_lease_field_nonexistent_lease_returns_none: PASS")


def test_get_lease_field_edits_filters_and_ordering():
    db_path = _fresh_temp_db()
    try:
        lease_id = _make_lease()
        database.update_lease_field(lease_id, "rent_amount", "$1", edited_by="A")
        database.update_lease_field(lease_id, "cam_charges", "$2", edited_by="A")
        database.update_lease_field(lease_id, "rent_amount", "$3", edited_by="A")

        all_edits = database.get_lease_field_edits(lease_id=lease_id)
        assert [e["new_value"]["value"] for e in all_edits] == ["$1", "$2", "$3"], "oldest first"

        rent_only = database.get_lease_field_edits(lease_id=lease_id, field_name="rent_amount")
        assert [e["new_value"]["value"] for e in rent_only] == ["$1", "$3"]
    finally:
        os.unlink(db_path)
    print("✓ test_get_lease_field_edits_filters_and_ordering: PASS")


# ------------------------------------------------------------------
# PATCH /leases/<id>/fields/<name>
# ------------------------------------------------------------------

def test_patch_field_route_happy_path_and_activity_log():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")

        resp = client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,250.00", "note": "Verified against p.3"})
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["field"]["value"] == "$5,250.00"
        assert data["field"]["manually_verified"] is True

        lease = client.get(f"/leases/{lease_id}").get_json()
        assert lease["extracted_fields"]["rent_amount"]["value"] == "$5,250.00"

        activity = client.get("/activity?limit=5").get_json()
        edit_entries = [a for a in activity if a["action_type"] == "lease_field_edited"]
        assert len(edit_entries) == 1
        assert "Analyst User" in edit_entries[0]["description"]
        assert "rent amount" in edit_entries[0]["description"]
    finally:
        os.unlink(db_path)
    print("✓ test_patch_field_route_happy_path_and_activity_log: PASS")


def test_patch_field_route_validation():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease()

        resp = client.patch(f"/leases/{lease_id}/fields/not_a_real_field", json={"value": "x"})
        assert resp.status_code == 400

        resp = client.patch(f"/leases/{lease_id}/fields/rent_amount", json={})
        assert resp.status_code == 400, "value key itself must be required (even if null)"

        resp = client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$1", "confidence": "extreme"})
        assert resp.status_code == 400

        resp = client.patch("/leases/999999/fields/rent_amount", json={"value": "$1"})
        assert resp.status_code == 404

        resp = client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$1", "task_id": 999999})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_patch_field_route_validation: PASS")


def test_patch_field_route_requires_login_and_analyst_role():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, viewer = _real_users()
        lease_id = _make_lease()

        anon = app.test_client()
        assert anon.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$1"}).status_code == 401

        viewer_client = _client_for(viewer, "viewer")
        assert viewer_client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$1"}).status_code == 403
    finally:
        os.unlink(db_path)
    print("✓ test_patch_field_route_requires_login_and_analyst_role: PASS")


def test_patch_field_route_value_can_be_null():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(insurance_requirements="$1,000,000")

        resp = client.patch(f"/leases/{lease_id}/fields/insurance_requirements", json={"value": None, "note": "Confirmed absent, not a miss"})
        assert resp.status_code == 200
        assert resp.get_json()["field"]["value"] is None
        assert resp.get_json()["field"]["manually_verified"] is True
    finally:
        os.unlink(db_path)
    print("✓ test_patch_field_route_value_can_be_null: PASS")


def test_source_route_surfaces_manual_edits():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")

        before = client.get(f"/leases/{lease_id}/fields/rent_amount/source").get_json()
        assert before["manual_edits"] == []
        assert "history" in before, "existing shape must be untouched, only additive"

        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,000.00", "note": "fix"})

        after = client.get(f"/leases/{lease_id}/fields/rent_amount/source").get_json()
        assert len(after["manual_edits"]) == 1
        assert after["manual_edits"][0]["new_value"]["value"] == "$5,000.00"
        assert after["effective_value"] == "$5,000.00", "the source-chain's effective value must reflect the edit too"
    finally:
        os.unlink(db_path)
    print("✓ test_source_route_surfaces_manual_edits: PASS")


# ------------------------------------------------------------------
# task_detail: lease + field_edits attachment
# ------------------------------------------------------------------

def test_task_detail_includes_lease_and_scoped_field_edits():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        task_id = client.post("/tasks", json={"title": "Fix rent", "lease_id": lease_id}).get_json()["id"]

        detail = client.get(f"/tasks/{task_id}").get_json()
        assert detail["lease"]["id"] == lease_id
        assert detail["lease"]["extracted_fields"]["rent_amount"]["value"] == "$4,000.00"
        assert detail["field_edits"] == [], "no edits made under this task yet"

        # Edit the field, explicitly scoped to this task.
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,000.00", "task_id": task_id})

        detail_after = client.get(f"/tasks/{task_id}").get_json()
        assert detail_after["lease"]["extracted_fields"]["rent_amount"]["value"] == "$5,000.00"
        assert len(detail_after["field_edits"]) == 1
        assert detail_after["field_edits"][0]["field_name"] == "rent_amount"

        # A separate, unrelated edit to the SAME lease NOT scoped to this task must not show up here.
        client.patch(f"/leases/{lease_id}/fields/cam_charges", json={"value": "$100.00"})
        detail_still = client.get(f"/tasks/{task_id}").get_json()
        assert len(detail_still["field_edits"]) == 1, "field_edits is scoped to THIS task, not the whole lease"
    finally:
        os.unlink(db_path)
    print("✓ test_task_detail_includes_lease_and_scoped_field_edits: PASS")


# ------------------------------------------------------------------
# Task completion + discrepancy resolution (the core end-to-end path)
# ------------------------------------------------------------------

def test_complete_task_tied_to_open_discrepancy_requires_confirmation():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc_id = _make_discrepancy(lease_id)
        task = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst)
        task_id = task["id"]

        # Marking done WITHOUT confirming the source must be rejected, task stays open.
        resp = client.post(f"/tasks/{task_id}/status", json={"status": "done"})
        assert resp.status_code == 400, resp.get_json()
        assert resp.get_json()["discrepancy_id"] == disc_id
        assert database.get_task(task_id)["status"] != "done"
        assert database.get_discrepancy(disc_id)["status"] == "open"
    finally:
        os.unlink(db_path)
    print("✓ test_complete_task_tied_to_open_discrepancy_requires_confirmation: PASS")


def test_complete_task_resolves_discrepancy_when_confirmed():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc_id = _make_discrepancy(lease_id)
        task = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst)
        task_id = task["id"]

        # Correct the field, then complete the task with confirmation.
        client.patch(f"/leases/{lease_id}/fields/rent_amount", json={"value": "$5,000.00", "task_id": task_id})
        resp = client.post(f"/tasks/{task_id}/status", json={
            "status": "done", "correct_source": "lease_document", "note": "Rent corrected to $5,000.00 per lease p.3"
        })
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["status"] == "done"
        assert data["discrepancy_resolved_now"] is True
        assert data["discrepancy"]["status"] == "resolved"

        # Real, permanent DB state.
        assert database.get_task(task_id)["status"] == "done"
        assert database.get_discrepancy(disc_id)["status"] == "resolved"
        resolutions = database.get_discrepancy_resolutions(disc_id)
        assert resolutions[-1]["resolved_by"] == "Analyst User"
        assert resolutions[-1]["correct_source"] == "lease_document"

        activity = client.get("/activity?limit=10").get_json()
        resolved_entries = [a for a in activity if a["action_type"] == "discrepancy_resolved"]
        assert len(resolved_entries) == 1
        assert "Analyst User" in resolved_entries[0]["description"]
        assert "task" in resolved_entries[0]["description"].lower()
    finally:
        os.unlink(db_path)
    print("✓ test_complete_task_resolves_discrepancy_when_confirmed: PASS")


def test_complete_task_removed_from_active_list():
    """
    Reuses the exact completion mechanism already verified for the
    plain 'Complete Task' button -- confirms a discrepancy-linked task
    ALSO disappears from the active view once done. GET /tasks itself
    returns every status by default (no implicit filtering -- see
    list_tasks_route); "active list" excluding done tasks is the
    frontend's own default filter (tasks-view.js's showDone toggle),
    same as it already was before this feature. What this feature must
    guarantee is that ?status=open (what that active view actually
    requests) stops including the task, and ?status=done does -- both
    checked here.
    """
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc_id = _make_discrepancy(lease_id)
        task = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst)
        task_id = task["id"]

        open_before = client.get(f"/tasks?assigned_to={analyst}&status=open").get_json()
        assert any(t["id"] == task_id for t in open_before)

        client.post(f"/tasks/{task_id}/status", json={
            "status": "done", "correct_source": "lease_document", "note": "fixed"
        })

        open_after = client.get(f"/tasks?assigned_to={analyst}&status=open").get_json()
        assert all(t["id"] != task_id for t in open_after), "a completed task must not appear in the active (open) view"

        with_done = client.get(f"/tasks?assigned_to={analyst}&status=done").get_json()
        assert any(t["id"] == task_id for t in with_done), "but it must still exist and be retrievable"
    finally:
        os.unlink(db_path)
    print("✓ test_complete_task_removed_from_active_list: PASS")


def test_complete_task_already_resolved_discrepancy_needs_no_confirmation():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc_id = _make_discrepancy(lease_id)
        task = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst)
        task_id = task["id"]

        # Someone else resolves the discrepancy directly, outside this task.
        database.resolve_discrepancy(disc_id, "rent_roll", "Confirmed via rent roll instead", "Someone Else")

        resp = client.post(f"/tasks/{task_id}/status", json={"status": "done"})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["discrepancy_resolved_now"] is False, "nothing left to resolve -- already resolved"
        assert database.get_task(task_id)["status"] == "done"
    finally:
        os.unlink(db_path)
    print("✓ test_complete_task_already_resolved_discrepancy_needs_no_confirmation: PASS")


def test_complete_task_not_tied_to_discrepancy_unaffected():
    """A plain task with no discrepancy_id must behave exactly as it did before this feature -- no confirmation required, no discrepancy_resolved_now surprises."""
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        task_id = client.post("/tasks", json={"title": "Plain task"}).get_json()["id"]

        resp = client.post(f"/tasks/{task_id}/status", json={"status": "done"})
        assert resp.status_code == 200
        assert resp.get_json()["discrepancy_resolved_now"] is False
        assert resp.get_json()["status"] == "done"
    finally:
        os.unlink(db_path)
    print("✓ test_complete_task_not_tied_to_discrepancy_unaffected: PASS")


def test_reopening_a_task_does_not_touch_discrepancy():
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        lease_id = _make_lease(rent_amount="$4,000.00")
        disc_id = _make_discrepancy(lease_id)
        task = tasks_module.create_task_from_discrepancy(disc_id, admin, assigned_to_user_id=analyst)
        task_id = task["id"]

        resp = client.post(f"/tasks/{task_id}/status", json={"status": "in_progress"})
        assert resp.status_code == 200
        assert database.get_discrepancy(disc_id)["status"] == "open", "only completing (done) triggers the resolution requirement"
    finally:
        os.unlink(db_path)
    print("✓ test_reopening_a_task_does_not_touch_discrepancy: PASS")


def test_task_detail_lease_view_follows_resubmission_to_current_version():
    """
    A task created against a lease that's later resubmitted (Canvas-
    style replace, not an amendment) must show the CURRENT version in
    its in-task document view, not the archived one -- otherwise
    opening an old task would edit a superseded lease that no longer
    appears or matters anywhere else in the app.
    """
    db_path = _fresh_temp_db()
    try:
        admin, analyst, _ = _real_users()
        client = _client_for(analyst, "analyst")
        old_lease_id = _make_lease(rent_amount="$4,000.00")
        task_id = client.post("/tasks", json={"title": "Review this lease", "lease_id": old_lease_id}).get_json()["id"]

        new_lease_id = database.insert_lease(
            "lease_v2.pdf", _fields(rent_amount="$4,500.00"),
            status="active", supersedes_lease_id=old_lease_id, version_number=2,
        )
        database.repoint_lease_references(old_lease_id, new_lease_id)
        database.supersede_lease(old_lease_id)

        detail = client.get(f"/tasks/{task_id}").get_json()
        assert detail["lease"]["id"] == new_lease_id, "must resolve forward to the current version"
        assert detail["lease"]["extracted_fields"]["rent_amount"]["value"] == "$4,500.00"
        assert detail["lease_redirected_from_id"] == old_lease_id
    finally:
        os.unlink(db_path)
    print("✓ test_task_detail_lease_view_follows_resubmission_to_current_version: PASS")


if __name__ == "__main__":
    test_update_lease_field_mutates_extracted_fields_and_logs_edit()
    test_update_lease_field_can_clear_to_none_with_manually_verified_flag()
    test_update_lease_field_nonexistent_lease_returns_none()
    test_get_lease_field_edits_filters_and_ordering()
    test_patch_field_route_happy_path_and_activity_log()
    test_patch_field_route_validation()
    test_patch_field_route_requires_login_and_analyst_role()
    test_patch_field_route_value_can_be_null()
    test_source_route_surfaces_manual_edits()
    test_task_detail_includes_lease_and_scoped_field_edits()
    test_complete_task_tied_to_open_discrepancy_requires_confirmation()
    test_complete_task_resolves_discrepancy_when_confirmed()
    test_complete_task_removed_from_active_list()
    test_complete_task_already_resolved_discrepancy_needs_no_confirmation()
    test_complete_task_not_tied_to_discrepancy_unaffected()
    test_reopening_a_task_does_not_touch_discrepancy()
    test_task_detail_lease_view_follows_resubmission_to_current_version()
    print("\nAll lease field editing tests passed.")
