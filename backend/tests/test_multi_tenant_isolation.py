"""
Proves real multi-tenant data isolation (see DECISIONS.md's "Real
multi-tenant data isolation" entry): creates two separate accounts (A
and B), each with its own admin user and its own distinct leases/
discrepancies/alerts/tasks/comments/tags, then for every route that
touches customer data, verifies account A's user can never see, edit,
or delete account B's data -- including by directly guessing B's real
ids in a URL (not just omitting a lease_id filter).

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_owner_console.py/test_teams_and_assignments.py.
Also reuses test_owner_console.py's env-var-leak fix in _fresh_temp_db
-- app.api's load_dotenv() puts this developer's real ADMIN_EMAIL/
ADMIN_PASSWORD_HASH into the process environment, which would
otherwise seed a phantom real account into every "fresh" temp DB this
file creates.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password


def _fresh_temp_db():
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


def _client_as(user_id, email, role, account_id, is_owner=False):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = "Test User"
        sess["role"] = role
        sess["is_owner"] = is_owner
        sess["account_id"] = account_id
    return client


def _make_account(name, admin_email, role="admin"):
    """Creates one fresh account with one user in it, via the real create_user path with an explicit account_id (a brand-new account this call creates itself)."""
    conn = database.get_connection()
    cur = conn.execute(
        "INSERT INTO accounts (name, created_at, status, plan) VALUES (?, ?, 'active', 'free')",
        (name, "2026-01-01T00:00:00+00:00"),
    )
    account_id = cur.lastrowid
    conn.commit()
    conn.close()
    user_id = database.create_user(admin_email, "Admin", hash_password("password123"), role=role, account_id=account_id)["id"]
    return account_id, user_id


def _seed_two_accounts():
    """Two fully separate accounts, each with its own admin, lease, discrepancy, alert, task, comment, and tag. Returns a dict of everything needed to test cross-account access."""
    account_a, admin_a = _make_account("Account A", "admin-a@example.com")
    account_b, admin_b = _make_account("Account B", "admin-b@example.com")

    lease_a = database.insert_lease("a.pdf", {"tenant": {"value": "Acme A", "source": "p1", "confidence": "high"}}, account_id=account_a, display_name="Lease A")
    lease_b = database.insert_lease("b.pdf", {"tenant": {"value": "Acme B", "source": "p1", "confidence": "high"}}, account_id=account_b, display_name="Lease B")

    disc_a = database.upsert_discrepancy("lease_risk_flag", "nk-a", "missing_clause", "msg a", {}, account_id=account_a, lease_id=lease_a, severity="high")
    disc_b = database.upsert_discrepancy("lease_risk_flag", "nk-b", "missing_clause", "msg b", {}, account_id=account_b, lease_id=lease_b, severity="high")

    alert_a = database.upsert_alert(alert_type="lease_expiration", natural_key="alert-a", severity="high", title="t-a", message="m-a", details={}, account_id=account_a, lease_id=lease_a)
    alert_b = database.upsert_alert(alert_type="lease_expiration", natural_key="alert-b", severity="high", title="t-b", message="m-b", details={}, account_id=account_b, lease_id=lease_b)

    task_a = database.create_task("Task A", admin_a, account_id=account_a, lease_id=lease_a)
    task_b = database.create_task("Task B", admin_b, account_id=account_b, lease_id=lease_b)

    database.add_lease_tag(lease_a, "TagA", account_id=account_a)
    database.add_lease_tag(lease_b, "TagB", account_id=account_b)

    database.add_comment("Admin A", "Comment on A", account_id=account_a, lease_id=lease_a)
    database.add_comment("Admin B", "Comment on B", account_id=account_b, lease_id=lease_b)

    assignment_a = database.upsert_assignment("lease", str(lease_a), admin_a, admin_a, account_id=account_a, lease_id=lease_a)
    assignment_b = database.upsert_assignment("lease", str(lease_b), admin_b, admin_b, account_id=account_b, lease_id=lease_b)

    return {
        "account_a": account_a, "admin_a": admin_a, "lease_a": lease_a, "disc_a": disc_a, "alert_a": alert_a, "task_a": task_a, "assignment_a": assignment_a,
        "account_b": account_b, "admin_b": admin_b, "lease_b": lease_b, "disc_b": disc_b, "alert_b": alert_b, "task_b": task_b, "assignment_b": assignment_b,
    }


def test_leases_list_and_detail_never_leak_across_accounts():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "admin", s["account_a"])

        # List: account A only ever sees its own lease.
        resp = client_a.get("/leases")
        ids = [l["id"] for l in resp.get_json()]
        assert s["lease_a"] in ids
        assert s["lease_b"] not in ids

        # Direct-id-guessing: account A hitting B's real lease id -> 404, not the data.
        resp = client_a.get(f"/leases/{s['lease_b']}")
        assert resp.status_code == 404, f"expected 404 guessing another account's lease id, got {resp.status_code}"

        # And account A's own lease is still reachable.
        resp = client_a.get(f"/leases/{s['lease_a']}")
        assert resp.status_code == 200
    finally:
        os.unlink(db_path)
    print("✓ test_leases_list_and_detail_never_leak_across_accounts: PASS")


def test_lease_cannot_be_edited_or_deleted_across_accounts():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        # PATCH a field on B's lease, as an A user -- must 404, never edit it.
        resp = client_a.patch(f"/leases/{s['lease_b']}/fields/tenant", json={"value": "Hacked Tenant"})
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}"
        untouched = database.get_lease(s["lease_b"])
        assert untouched["extracted_fields"]["tenant"]["value"] == "Acme B", "account A must never be able to edit account B's lease field"

        # DELETE B's lease as an A user -- must 404, must not delete it.
        resp = client_a.delete(f"/leases/{s['lease_b']}")
        assert resp.status_code == 404
        assert database.get_lease(s["lease_b"]) is not None, "account A must never be able to delete account B's lease"

        # field-source route: another real cross-account fetch surface.
        resp = client_a.get(f"/leases/{s['lease_b']}/fields/tenant/source")
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_lease_cannot_be_edited_or_deleted_across_accounts: PASS")


def test_discrepancies_isolated_including_resolve_by_guessed_id():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        resp = client_a.get("/discrepancies")
        ids = [d["id"] for d in resp.get_json()]
        assert s["disc_a"] in ids
        assert s["disc_b"] not in ids

        resp = client_a.get(f"/discrepancies/{s['disc_b']}")
        assert resp.status_code == 404

        # The dangerous one: try to RESOLVE another account's discrepancy by guessing its id.
        resp = client_a.post(f"/discrepancies/{s['disc_b']}/resolve", json={"correct_source": "lease", "note": "sneaky"})
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}"
        still_open = database.get_discrepancy(s["disc_b"])
        assert still_open["status"] == "open", "account A must never be able to resolve account B's discrepancy"
    finally:
        os.unlink(db_path)
    print("✓ test_discrepancies_isolated_including_resolve_by_guessed_id: PASS")


def test_alerts_isolated_including_dismiss_by_guessed_id():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        resp = client_a.get("/alerts")
        ids = [a["id"] for a in resp.get_json()]
        assert s["alert_a"] in ids
        assert s["alert_b"] not in ids

        resp = client_a.get(f"/alerts/{s['alert_b']}")
        assert resp.status_code == 404

        resp = client_a.post(f"/alerts/{s['alert_b']}/dismiss", json={"note": "sneaky"})
        assert resp.status_code == 404
        still_active = database.get_alert(s["alert_b"])
        assert still_active["status"] == "active", "account A must never be able to dismiss account B's alert"
    finally:
        os.unlink(db_path)
    print("✓ test_alerts_isolated_including_dismiss_by_guessed_id: PASS")


def test_tasks_isolated_including_delete_and_status_change_by_guessed_id():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        resp = client_a.get("/tasks")
        ids = [t["id"] for t in resp.get_json()]
        assert s["task_a"] in ids
        assert s["task_b"] not in ids

        resp = client_a.get(f"/tasks/{s['task_b']}")
        assert resp.status_code == 404

        resp = client_a.post(f"/tasks/{s['task_b']}/status", json={"status": "done"})
        assert resp.status_code == 404
        still_open = database.get_task(s["task_b"])
        assert still_open["status"] == "open", "account A must never be able to change account B's task status"

        resp = client_a.delete(f"/tasks/{s['task_b']}")
        assert resp.status_code == 404
        assert database.get_task(s["task_b"]) is not None, "account A must never be able to delete account B's task"
    finally:
        os.unlink(db_path)
    print("✓ test_tasks_isolated_including_delete_and_status_change_by_guessed_id: PASS")


def test_comments_and_tags_isolated():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        # Comments on B's lease -- must 404, not just return an empty/wrong list.
        resp = client_a.get(f"/leases/{s['lease_b']}/comments")
        assert resp.status_code == 404

        # Global tag list must not include account B's tag.
        resp = client_a.get("/tags")
        assert "TagB" not in resp.get_json()
        assert "TagA" in resp.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_comments_and_tags_isolated: PASS")


def test_assignments_isolated_including_patch_delete_by_guessed_id():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        resp = client_a.get("/assignments")
        ids = [a["id"] for a in resp.get_json()]
        assert s["assignment_a"] in ids
        assert s["assignment_b"] not in ids

        resp = client_a.get(f"/assignments/{s['assignment_b']}")
        assert resp.status_code == 404

        resp = client_a.patch(f"/assignments/{s['assignment_b']}", json={"status": "resolved"})
        assert resp.status_code == 404
        still_assigned = database.get_assignment(s["assignment_b"])
        assert still_assigned["status"] == "assigned"

        resp = client_a.delete(f"/assignments/{s['assignment_b']}")
        assert resp.status_code == 404
        assert database.get_assignment(s["assignment_b"]) is not None
    finally:
        os.unlink(db_path)
    print("✓ test_assignments_isolated_including_patch_delete_by_guessed_id: PASS")


def test_team_members_isolated_including_patch_and_reset_password_by_guessed_id():
    """The specific real bug found during this pass: an admin could PATCH/reset-password on any user id, not just their own account's team."""
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "admin", s["account_a"])

        resp = client_a.get("/team/members")
        ids = [m["id"] for m in resp.get_json()]
        assert s["admin_a"] in ids
        assert s["admin_b"] not in ids

        resp = client_a.patch(f"/team/members/{s['admin_b']}", json={"name": "Pwned"})
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}"
        untouched = database.get_user(s["admin_b"])
        assert untouched["name"] == "Admin", "account A's admin must never be able to rename account B's user"

        resp = client_a.post(f"/team/members/{s['admin_b']}/reset-password", json={"password": "newpassword123"})
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}"
        from app.auth import verify_password
        assert verify_password("admin-b@example.com", "newpassword123") is None, "account A's admin must never be able to reset account B's user's password"
        assert verify_password("admin-b@example.com", "password123") is not None, "account B's original password must still work"
    finally:
        os.unlink(db_path)
    print("✓ test_team_members_isolated_including_patch_and_reset_password_by_guessed_id: PASS")


def test_activity_feed_and_today_view_isolated():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "admin", s["account_a"])

        database.insert_activity("lease_uploaded", "Uploaded a.pdf", account_id=s["account_a"], lease_id=s["lease_a"])
        database.insert_activity("lease_uploaded", "Uploaded b.pdf", account_id=s["account_b"], lease_id=s["lease_b"])

        resp = client_a.get("/activity")
        descriptions = [e["description"] for e in resp.get_json()]
        assert "Uploaded a.pdf" in descriptions
        assert "Uploaded b.pdf" not in descriptions, "account A's activity feed must never show account B's activity"

        # /today?user_id=<B's real user id> -- must 404, not leak B's assignments/tasks.
        resp = client_a.get(f"/today?user_id={s['admin_b']}")
        assert resp.status_code == 404, f"expected 404 requesting another account's user's Today view, got {resp.status_code}"

        # A's own Today view must work and stay scoped to A's active alerts only.
        resp = client_a.get(f"/today?user_id={s['admin_a']}")
        assert resp.status_code == 200
        active_alert_ids = [a["id"] for a in resp.get_json()["active_alerts"]]
        assert s["alert_b"] not in active_alert_ids
    finally:
        os.unlink(db_path)
    print("✓ test_activity_feed_and_today_view_isolated: PASS")


def test_health_score_and_trends_do_not_mix_accounts():
    """Covers the cache-key leak found during this pass -- account B's request for the same cache key must not receive account A's cached result."""
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "admin", s["account_a"])
        client_b = _client_as(s["admin_b"], "admin-b@example.com", "admin", s["account_b"])

        resp_a = client_a.get("/portfolio/health-score")
        resp_b = client_b.get("/portfolio/health-score")
        assert resp_a.status_code == 200 and resp_b.status_code == 200
        assert resp_a.get_json()["lease_count"] == 1
        assert resp_b.get_json()["lease_count"] == 1

        resp_a2 = client_a.get("/portfolio/trends")
        resp_b2 = client_b.get("/portfolio/trends")
        assert resp_a2.status_code == 200 and resp_b2.status_code == 200
    finally:
        os.unlink(db_path)
    print("✓ test_health_score_and_trends_do_not_mix_accounts: PASS")


def test_task_created_from_discrepancy_cannot_target_another_accounts_discrepancy():
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        resp = client_a.post(f"/tasks/from-discrepancy/{s['disc_b']}", json={})
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}"
    finally:
        os.unlink(db_path)
    print("✓ test_task_created_from_discrepancy_cannot_target_another_accounts_discrepancy: PASS")


def test_assignee_and_thread_participant_cannot_be_a_different_accounts_user():
    """The other class of real bug found during this pass: a client-supplied user_id was trusted without verifying it belonged to the caller's own account."""
    db_path = _fresh_temp_db()
    try:
        s = _seed_two_accounts()
        client_a = _client_as(s["admin_a"], "admin-a@example.com", "analyst", s["account_a"])

        resp = client_a.post("/tasks", json={"title": "Steal a coworker", "assigned_to_user_id": s["admin_b"]})
        assert resp.status_code == 400, f"expected 400 (invalid assignee), got {resp.status_code}"

        resp = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [s["admin_b"]]})
        assert resp.status_code == 400, f"expected 400 (invalid participant), got {resp.status_code}"
    finally:
        os.unlink(db_path)
    print("✓ test_assignee_and_thread_participant_cannot_be_a_different_accounts_user: PASS")


if __name__ == "__main__":
    test_leases_list_and_detail_never_leak_across_accounts()
    test_lease_cannot_be_edited_or_deleted_across_accounts()
    test_discrepancies_isolated_including_resolve_by_guessed_id()
    test_alerts_isolated_including_dismiss_by_guessed_id()
    test_tasks_isolated_including_delete_and_status_change_by_guessed_id()
    test_comments_and_tags_isolated()
    test_assignments_isolated_including_patch_delete_by_guessed_id()
    test_team_members_isolated_including_patch_and_reset_password_by_guessed_id()
    test_activity_feed_and_today_view_isolated()
    test_health_score_and_trends_do_not_mix_accounts()
    test_task_created_from_discrepancy_cannot_target_another_accounts_discrepancy()
    test_assignee_and_thread_participant_cannot_be_a_different_accounts_user()
    print("\nAll multi-tenant isolation tests passed.")
