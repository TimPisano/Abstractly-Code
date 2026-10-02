"""
Cross-team data isolation. Two real teams (Team A, Team B), one admin
user in each, each with their own lease/discrepancy/alert/task/
assignment/comment/thread. For every route category -- list, get-by-id,
export, create, update -- asserts Team B's session can never read,
list, export, or modify Team A's data, and vice versa: a direct-by-id
request 404s (never 403 -- indistinguishable from a nonexistent id,
never confirms the id exists), a list endpoint never includes the
other team's rows, and an export built under one team's session never
contains the other team's figures.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as every other route-level test in this suite.
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app import usage_limits

FIXTURES_DIR = os.path.dirname(__file__)
SAMPLE_LEASE_PDF = os.path.join(FIXTURES_DIR, "sample_lease_commercial.pdf")


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _make_team(name, admin_email):
    """Creates a real team + a real active admin user in it. Returns (team_id, user_id)."""
    team = database.create_team(name)
    result = database.create_user(admin_email, f"{name} Admin", database.get_user_by_email(admin_email)["password_hash"] if database.get_user_by_email(admin_email) else _hash("password123"), role="admin", team_id=team["id"])
    return team["id"], result["id"]


def _hash(password):
    from app.auth import hash_password
    return hash_password(password)


def _client_for(user_id, team_id, email, role="admin"):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["team_id"] = team_id
        sess["email"] = email
        sess["name"] = f"User {user_id}"
        sess["role"] = role
        sess["is_owner"] = False
    return client


def _setup_two_teams():
    """Returns (client_a, team_a_id, user_a_id, client_b, team_b_id, user_b_id)."""
    team_a = database.create_team("Team A")
    team_b = database.create_team("Team B")
    user_a = database.create_user("admin-a@example.com", "Admin A", _hash("password123"), role="admin", team_id=team_a["id"])["id"]
    user_b = database.create_user("admin-b@example.com", "Admin B", _hash("password123"), role="admin", team_id=team_b["id"])["id"]
    client_a = _client_for(user_a, team_a["id"], "admin-a@example.com")
    client_b = _client_for(user_b, team_b["id"], "admin-b@example.com")
    return client_a, team_a["id"], user_a, client_b, team_b["id"], user_b


def _upload_lease(client):
    usage_limits._reset_extraction_rate_limit_for_tests()
    with open(SAMPLE_LEASE_PDF, "rb") as f:
        content = f.read()
    resp = client.post(
        "/leases",
        data={"file": (io.BytesIO(content), "sample_lease_commercial.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["leases"][0]["id"]


# ------------------------------------------------------------------
# Leases
# ------------------------------------------------------------------

def test_lease_list_excludes_other_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        resp_a = client_a.get("/leases")
        assert any(l["id"] == lease_a_id for l in resp_a.get_json())

        resp_b = client_b.get("/leases")
        assert not any(l["id"] == lease_a_id for l in resp_b.get_json()), "Team B's lease list must never include Team A's lease"
    finally:
        os.unlink(db_path)
    print("✓ test_lease_list_excludes_other_team: PASS")


def test_lease_get_by_id_404s_for_other_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        resp_own = client_a.get(f"/leases/{lease_a_id}")
        assert resp_own.status_code == 200

        resp_cross = client_b.get(f"/leases/{lease_a_id}")
        assert resp_cross.status_code == 404, "Team B must get 404, not the lease, not 403"
    finally:
        os.unlink(db_path)
    print("✓ test_lease_get_by_id_404s_for_other_team: PASS")


def test_lease_delete_cannot_touch_other_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        resp = client_b.delete(f"/leases/{lease_a_id}")
        assert resp.status_code == 404

        # Still fully intact from Team A's own point of view.
        resp_a = client_a.get(f"/leases/{lease_a_id}")
        assert resp_a.status_code == 200
    finally:
        os.unlink(db_path)
    print("✓ test_lease_delete_cannot_touch_other_team: PASS")


def test_lease_rename_cannot_touch_other_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        resp = client_b.patch(f"/leases/{lease_a_id}", json={"display_name": "Hijacked"})
        assert resp.status_code == 404

        resp_a = client_a.get(f"/leases/{lease_a_id}")
        assert resp_a.get_json()["display_name"] != "Hijacked"
    finally:
        os.unlink(db_path)
    print("✓ test_lease_rename_cannot_touch_other_team: PASS")


# ------------------------------------------------------------------
# Discrepancies (via /portfolio/risks, which syncs risk-flag
# discrepancies for the caller's own team only)
# ------------------------------------------------------------------

def test_discrepancies_isolated_between_teams():
    db_path = _fresh_temp_db()
    try:
        client_a, team_a_id, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        some_disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k1", category="missing_clause",
            message="No insurance clause", details={"x": 1}, lease_id=lease_a_id,
            field="insurance_requirements", severity="medium", team_id=team_a_id,
        )

        discrepancies_a = client_a.get("/discrepancies").get_json()
        assert any(d["id"] == some_disc_id for d in discrepancies_a)

        discrepancies_b = client_b.get("/discrepancies").get_json()
        assert discrepancies_b == [], "Team B must see zero discrepancies -- it has no leases and none of Team A's"

        resp_cross = client_b.get(f"/discrepancies/{some_disc_id}")
        assert resp_cross.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_discrepancies_isolated_between_teams: PASS")


# ------------------------------------------------------------------
# Alerts
# ------------------------------------------------------------------

def test_alerts_isolated_between_teams():
    db_path = _fresh_temp_db()
    try:
        client_a, team_a_id, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        alert_id = database.upsert_alert(
            alert_type="below_market_rent", natural_key="alert-k1", severity="high",
            title="Rent below market", message="This unit is 25% below market.",
            details={}, team_id=team_a_id, lease_id=lease_a_id,
        )

        alerts_a = client_a.get("/alerts").get_json()
        assert any(a["id"] == alert_id for a in alerts_a)

        alerts_b = client_b.get("/alerts").get_json()
        assert alerts_b == [], "Team B must see zero alerts from Team A's portfolio"

        resp_cross = client_b.get(f"/alerts/{alert_id}")
        assert resp_cross.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_alerts_isolated_between_teams: PASS")


# ------------------------------------------------------------------
# Tasks
# ------------------------------------------------------------------

def test_task_isolated_between_teams():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        resp = client_a.post("/tasks", json={"title": "Review this lease", "lease_id": lease_a_id})
        assert resp.status_code == 201
        task_id = resp.get_json()["id"]

        resp_cross_get = client_b.get(f"/tasks/{task_id}")
        assert resp_cross_get.status_code == 404

        resp_cross_patch = client_b.patch(f"/tasks/{task_id}", json={"title": "Hijacked"})
        assert resp_cross_patch.status_code == 404

        tasks_b = client_b.get("/tasks").get_json()
        assert not any(t["id"] == task_id for t in tasks_b)

        # Team B cannot even create a task pointed at Team A's lease_id.
        resp_bad_create = client_b.post("/tasks", json={"title": "Sneaky", "lease_id": lease_a_id})
        assert resp_bad_create.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_task_isolated_between_teams: PASS")


def test_cannot_assign_task_to_a_user_on_another_team():
    db_path = _fresh_temp_db()
    try:
        client_a, team_a_id, user_a_id, client_b, team_b_id, user_b_id = _setup_two_teams()

        resp = client_a.post("/tasks", json={"title": "Try to assign across teams", "assigned_to_user_id": user_b_id})
        assert resp.status_code == 400, "assigning a task to a user on another team must be rejected"
    finally:
        os.unlink(db_path)
    print("✓ test_cannot_assign_task_to_a_user_on_another_team: PASS")


# ------------------------------------------------------------------
# Assignments
# ------------------------------------------------------------------

def test_assignment_isolated_between_teams():
    db_path = _fresh_temp_db()
    try:
        client_a, _, user_a_id, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        resp = client_a.post("/assignments", json={"target_type": "lease", "target": lease_a_id, "assigned_to_user_id": user_a_id})
        assert resp.status_code == 201
        assignment_id = resp.get_json()["id"]

        resp_cross = client_b.get(f"/assignments/{assignment_id}") if False else None  # no single-assignment GET route; covered by list below
        assignments_b = client_b.get("/assignments").get_json()
        assert not any(a["id"] == assignment_id for a in assignments_b)
    finally:
        os.unlink(db_path)
    print("✓ test_assignment_isolated_between_teams: PASS")


# ------------------------------------------------------------------
# Comments
# ------------------------------------------------------------------

def test_comments_isolated_between_teams():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        lease_a_id = _upload_lease(client_a)

        resp = client_a.post(f"/leases/{lease_a_id}/comments", json={"body": "Secret note about this deal"})
        assert resp.status_code == 201

        resp_cross_post = client_b.post(f"/leases/{lease_a_id}/comments", json={"body": "Trying to comment cross-team"})
        assert resp_cross_post.status_code == 404

        recent_b = client_b.get("/comments/recent").get_json()
        assert not any("Secret note" in c["body"] for c in recent_b), "Team B's recent-comments feed must never show Team A's comments"
    finally:
        os.unlink(db_path)
    print("✓ test_comments_isolated_between_teams: PASS")


# ------------------------------------------------------------------
# Deal Mismatch Report (export)
# ------------------------------------------------------------------

def test_deal_mismatch_report_isolated_between_teams():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        _upload_lease(client_a)

        resp_a = client_a.post("/portfolio/deal-mismatch-report", data={})
        assert resp_a.status_code == 200
        data_a = resp_a.get_json()
        assert data_a["total_units_checked"] >= 1

        resp_b = client_b.post("/portfolio/deal-mismatch-report", data={})
        assert resp_b.status_code == 200
        data_b = resp_b.get_json()
        assert data_b["total_units_checked"] == 0, "Team B's report must never reflect Team A's leases"
        assert data_b["discrepancies"] == []
    finally:
        os.unlink(db_path)
    print("✓ test_deal_mismatch_report_isolated_between_teams: PASS")


# ------------------------------------------------------------------
# Messaging threads
# ------------------------------------------------------------------

def test_cannot_create_thread_with_a_user_on_another_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, user_a_id, client_b, _, user_b_id = _setup_two_teams()

        resp = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [user_b_id]})
        assert resp.status_code == 400, "a direct thread naming a user on another team must be rejected"
    finally:
        os.unlink(db_path)
    print("✓ test_cannot_create_thread_with_a_user_on_another_team: PASS")


# ------------------------------------------------------------------
# Team member management -- the actual vulnerabilities this pass fixed
# ------------------------------------------------------------------

def test_cannot_create_user_directly_inside_another_team():
    """POST /team/members must always use the caller's own team_id -- a client-supplied team_id must never be honored."""
    db_path = _fresh_temp_db()
    try:
        client_a, team_a_id, _, client_b, team_b_id, _ = _setup_two_teams()

        resp = client_a.post("/team/members", json={
            "email": "sneaky@example.com", "name": "Sneaky", "role": "viewer",
            "password": "password123", "team_id": team_b_id,
        })
        assert resp.status_code == 201
        new_user = database.get_user(resp.get_json()["id"])
        assert new_user["team_id"] == team_a_id, "the new user must land in the CALLER's team, never a client-supplied team_id"
    finally:
        os.unlink(db_path)
    print("✓ test_cannot_create_user_directly_inside_another_team: PASS")


def test_cannot_reset_password_of_a_user_on_another_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, user_b_id = _setup_two_teams()

        resp = client_a.post(f"/team/members/{user_b_id}/reset-password", json={"password": "hijacked123"})
        assert resp.status_code == 404, "an admin must never be able to reset another team's user's password"

        # Confirm the password genuinely didn't change.
        from app.auth import verify_password
        assert verify_password("admin-b@example.com", "hijacked123") is None
        assert verify_password("admin-b@example.com", "password123") is not None
    finally:
        os.unlink(db_path)
    print("✓ test_cannot_reset_password_of_a_user_on_another_team: PASS")


def test_cannot_modify_a_user_on_another_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, user_b_id = _setup_two_teams()

        resp = client_a.patch(f"/team/members/{user_b_id}", json={"role": "viewer", "status": "deactivated"})
        assert resp.status_code == 404

        user_b = database.get_user(user_b_id)
        assert user_b["role"] == "admin"
        assert user_b["status"] == "active"
    finally:
        os.unlink(db_path)
    print("✓ test_cannot_modify_a_user_on_another_team: PASS")


def test_team_members_list_excludes_other_team():
    db_path = _fresh_temp_db()
    try:
        client_a, _, user_a_id, client_b, _, user_b_id = _setup_two_teams()

        members_a = client_a.get("/team/members").get_json()
        assert {m["id"] for m in members_a} == {user_a_id}

        members_b = client_b.get("/team/members").get_json()
        assert {m["id"] for m in members_b} == {user_b_id}
    finally:
        os.unlink(db_path)
    print("✓ test_team_members_list_excludes_other_team: PASS")


# ------------------------------------------------------------------
# Team deactivation blocks login for every member
# ------------------------------------------------------------------

def test_deactivating_a_team_blocks_login_for_every_member_even_if_individually_active():
    db_path = _fresh_temp_db()
    try:
        team_a = database.create_team("Team A")
        user_a = database.create_user("admin-a@example.com", "Admin A", _hash("password123"), role="admin", team_id=team_a["id"])["id"]
        assert database.get_user(user_a)["status"] == "active"

        from app.auth import verify_password
        assert verify_password("admin-a@example.com", "password123") is not None

        database.update_team_status(team_a["id"], "deactivated")
        assert verify_password("admin-a@example.com", "password123") is None, "a deactivated team must block login even for an individually-active user"

        database.update_team_status(team_a["id"], "active")
        assert verify_password("admin-a@example.com", "password123") is not None, "reactivating the team must restore login"
    finally:
        os.unlink(db_path)
    print("✓ test_deactivating_a_team_blocks_login_for_every_member_even_if_individually_active: PASS")


# ------------------------------------------------------------------
# Owner console: team provisioning
# ------------------------------------------------------------------

def _owner_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 999
        sess["team_id"] = 1
        sess["email"] = "owner@abstractly.app"
        sess["name"] = "Owner"
        sess["role"] = "admin"
        sess["is_owner"] = True
    return client


def test_owner_create_team_issues_working_setup_link_and_admin_cannot_login_until_consumed():
    db_path = _fresh_temp_db()
    try:
        owner = _owner_client()
        resp = owner.post("/owner/teams", json={
            "firm_name": "Maple Ridge Capital", "admin_name": "Jordan Lee", "admin_email": "jordan@mapleridge.example.com",
        })
        assert resp.status_code == 201, resp.get_json()
        body = resp.get_json()
        assert body["team"]["name"] == "Maple Ridge Capital"
        assert body["admin"]["email"] == "jordan@mapleridge.example.com"
        assert "password_hash" not in body["admin"], "the owner must never see a password hash"
        assert "setup_url" in body, "no email backend configured in tests, so the fallback raw link must be returned"

        from app.auth import verify_password
        assert verify_password("jordan@mapleridge.example.com", "anything") is None, "brand-new admin must not be loggable-into before setup"

        raw_token = body["setup_url"].split("token=")[1]
        resp_setup = owner.post("/auth/team-setup", json={"token": raw_token, "new_password": "realpassword123"})
        assert resp_setup.status_code == 200

        assert verify_password("jordan@mapleridge.example.com", "realpassword123") is not None, "after consuming the setup link, the real password must work"

        # Token is single-use.
        resp_replay = owner.post("/auth/team-setup", json={"token": raw_token, "new_password": "other12345"})
        assert resp_replay.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_owner_create_team_issues_working_setup_link_and_admin_cannot_login_until_consumed: PASS")


def test_new_team_workspace_starts_completely_empty():
    db_path = _fresh_temp_db()
    try:
        client_a, _, _, client_b, _, _ = _setup_two_teams()
        _upload_lease(client_a)

        resp = client_b.get("/leases")
        assert resp.get_json() == [], "a brand-new team must see zero leases, never another team's data"
    finally:
        os.unlink(db_path)
    print("✓ test_new_team_workspace_starts_completely_empty: PASS")


def test_owner_teams_list_shows_usage_per_team():
    db_path = _fresh_temp_db()
    try:
        client_a, team_a_id, _, client_b, team_b_id, _ = _setup_two_teams()
        _upload_lease(client_a)

        owner = _owner_client()
        teams = owner.get("/owner/teams").get_json()
        by_id = {t["id"]: t for t in teams}
        assert by_id[team_a_id]["lease_count"] == 1
        assert by_id[team_b_id]["lease_count"] == 0
        assert by_id[team_a_id]["user_count"] == 1
    finally:
        os.unlink(db_path)
    print("✓ test_owner_teams_list_shows_usage_per_team: PASS")


if __name__ == "__main__":
    test_lease_list_excludes_other_team()
    test_lease_get_by_id_404s_for_other_team()
    test_lease_delete_cannot_touch_other_team()
    test_lease_rename_cannot_touch_other_team()
    test_discrepancies_isolated_between_teams()
    test_alerts_isolated_between_teams()
    test_task_isolated_between_teams()
    test_cannot_assign_task_to_a_user_on_another_team()
    test_assignment_isolated_between_teams()
    test_comments_isolated_between_teams()
    test_deal_mismatch_report_isolated_between_teams()
    test_cannot_create_thread_with_a_user_on_another_team()
    test_cannot_create_user_directly_inside_another_team()
    test_cannot_reset_password_of_a_user_on_another_team()
    test_cannot_modify_a_user_on_another_team()
    test_team_members_list_excludes_other_team()
    test_deactivating_a_team_blocks_login_for_every_member_even_if_individually_active()
    test_owner_create_team_issues_working_setup_link_and_admin_cannot_login_until_consumed()
    test_new_team_workspace_starts_completely_empty()
    test_owner_teams_list_shows_usage_per_team()
    print("\nAll team isolation tests passed.")
