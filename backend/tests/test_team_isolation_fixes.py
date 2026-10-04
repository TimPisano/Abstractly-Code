"""
Regression tests for the cross-team bugs the 2026-10-02 review and
security audit of feature/team-isolation found. Each test failed
before its fix (verified against b75b947) and passes after.

1. Undo of a field edit had no team check: team A could revert team B's
   lease edits by guessing ids. The revert's audit row also landed in
   the Legacy team.
2. Field-edit / version-chain helpers didn't require a team, so an
   unscoped call read every team's rows.
3. Legacy /teams routes were admin-only, so any team admin could list
   every firm and zero another firm's quota. The waitlist admin routes
   had the same problem.
4. alerts/discrepancies natural_key is globally unique, and two key
   families (tenant concentration, T-12 reconciliation) were built from
   names alone, so two teams with the same tenant or building
   overwrote each other's row.
5. assignments was UNIQUE(target_type, target_key), so two teams
   assigning the same property address collided on one row.
6. Sessions were trusted for 12h: deactivating a user or team, or
   changing a role, didn't apply until the token expired. A pre-team
   session 500'd instead of working.
7. A team admin could demote / reset the platform owner's account
   through the ordinary team routes.

Same in-process test_client + temp SQLite pattern as test_team_isolation.py.
"""
import io
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app import discrepancies as discrepancies_module
from app import usage_limits
from app.auth import hash_password

SAMPLE_LEASE_PDF = os.path.join(os.path.dirname(__file__), "sample_lease_commercial.pdf")


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _login(user_id):
    """A client logged in as a REAL user row (no faked claims)."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _two_teams(role="admin"):
    a = database.create_team("Team A")["id"]
    b = database.create_team("Team B")["id"]
    ua = database.create_user("a@abstractly.test", "A", hash_password("password123"), role=role, team_id=a)["id"]
    ub = database.create_user("b@abstractly.test", "B", hash_password("password123"), role=role, team_id=b)["id"]
    return a, ua, _login(ua), b, ub, _login(ub)


def _upload(client):
    usage_limits._reset_extraction_rate_limit_for_tests()
    with open(SAMPLE_LEASE_PDF, "rb") as f:
        data = f.read()
    resp = client.post("/leases", data={"file": (io.BytesIO(data), "lease.pdf")}, content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["leases"][0]["id"]


def _rent(client, lease_id):
    return client.get(f"/leases/{lease_id}").get_json()["extracted_fields"]["rent_amount"]["value"]


# ---------------------------------------------------------------- 1, 2

def test_undo_of_another_teams_field_edit_is_a_404_and_changes_nothing():
    db = _fresh_temp_db()
    try:
        _, _, client_a, _, _, client_b = _two_teams()
        lease_b = _upload(client_b)
        assert client_b.patch(f"/leases/{lease_b}/fields/rent_amount", json={"value": "$5,000.00"}).status_code == 200
        edit_id = client_b.get(f"/leases/{lease_b}/fields/rent_amount/source").get_json()["manual_edits"][-1]["id"]

        resp = client_a.post(f"/leases/{lease_b}/fields/rent_amount/edits/{edit_id}/undo")
        assert resp.status_code == 404, (resp.status_code, resp.get_json())
        assert _rent(client_b, lease_b) == "$5,000.00", "team A must not be able to revert team B's edit"
    finally:
        os.unlink(db)
    print("✓ test_undo_of_another_teams_field_edit_is_a_404_and_changes_nothing: PASS")


def test_same_team_undo_still_works_and_its_audit_row_stays_in_the_team():
    db = _fresh_temp_db()
    try:
        _, _, _, team_b, _, client_b = _two_teams()
        lease_b = _upload(client_b)
        before = _rent(client_b, lease_b)
        client_b.patch(f"/leases/{lease_b}/fields/rent_amount", json={"value": "$5,000.00"})
        edit_id = client_b.get(f"/leases/{lease_b}/fields/rent_amount/source").get_json()["manual_edits"][-1]["id"]

        resp = client_b.post(f"/leases/{lease_b}/fields/rent_amount/edits/{edit_id}/undo")
        assert resp.status_code == 200, resp.get_json()
        assert _rent(client_b, lease_b) == before
        rows = database.get_lease_field_edits(team_b, lease_id=lease_b, field_name="rent_amount")
        assert len(rows) == 2 and all(r["team_id"] == team_b for r in rows), \
            "the undo's own audit row must belong to the lease's team, not the Legacy default"
    finally:
        os.unlink(db)
    print("✓ test_same_team_undo_still_works_and_its_audit_row_stays_in_the_team: PASS")


def test_field_edit_and_version_chain_helpers_require_and_enforce_a_team():
    db = _fresh_temp_db()
    try:
        team_a, _, _, team_b, _, client_b = _two_teams()
        lease_b = _upload(client_b)
        client_b.patch(f"/leases/{lease_b}/fields/rent_amount", json={"value": "$5,000.00"})
        for call in (lambda: database.get_lease_field_edits(lease_id=lease_b),
                     lambda: database.get_lease_version_chain(lease_b)):
            try:
                call()
            except TypeError:
                pass
            else:
                raise AssertionError("calling without team_id must fail loudly, not read across teams")
        assert database.get_lease_field_edits(team_a, lease_id=lease_b) == []
        assert database.get_lease_version_chain(lease_b, team_a) == []
        assert len(database.get_lease_field_edits(team_b, lease_id=lease_b)) == 1
        assert [v["id"] for v in database.get_lease_version_chain(lease_b, team_b)] == [lease_b]
    finally:
        os.unlink(db)
    print("✓ test_field_edit_and_version_chain_helpers_require_and_enforce_a_team: PASS")


# ---------------------------------------------------------------- 3

def test_team_admin_cannot_list_or_change_other_teams_or_read_the_waitlist():
    db = _fresh_temp_db()
    try:
        _, _, client_a, team_b, _, _ = _two_teams()
        app.test_client().post("/waitlist", json={"email": "prospect@abstractly.test"})
        assert client_a.get("/teams").status_code == 404
        assert client_a.patch(f"/teams/{team_b}", json={"monthly_document_quota": 0}).status_code == 404
        assert client_a.post("/teams", json={"name": "Rogue"}).status_code == 404
        assert client_a.get("/waitlist").status_code == 404
        conn = database.get_connection()
        quota = conn.execute("SELECT monthly_document_quota FROM teams WHERE id = ?", (team_b,)).fetchone()[0]
        conn.close()
        assert quota is None, "team B's quota must be untouched"
    finally:
        os.unlink(db)
    print("✓ test_team_admin_cannot_list_or_change_other_teams_or_read_the_waitlist: PASS")


def test_owner_can_still_manage_teams_and_the_waitlist():
    db = _fresh_temp_db()
    try:
        team = database.create_team("Owner Co")["id"]
        uid = database.create_user("owner@abstractly.test", "Owner", hash_password("password123"), role="admin", team_id=team)["id"]
        conn = database.get_connection()
        conn.execute("UPDATE users SET is_owner = 1 WHERE id = ?", (uid,))
        conn.commit(); conn.close()
        owner = _login(uid)
        assert owner.get("/teams").status_code == 200
        assert owner.get("/waitlist").status_code == 200
    finally:
        os.unlink(db)
    print("✓ test_owner_can_still_manage_teams_and_the_waitlist: PASS")


# ---------------------------------------------------------------- 4

def test_two_teams_with_the_same_tenant_each_get_their_own_concentration_alert():
    db = _fresh_temp_db()
    try:
        team_a, _, client_a, team_b, _, client_b = _two_teams()
        _upload(client_a)
        _upload(client_b)  # same file: same tenant name in both teams
        assert client_a.post("/alerts/generate").status_code == 200
        resp_b = client_b.post("/alerts/generate")
        assert resp_b.status_code == 200, resp_b.get_json()
        for client, team in ((client_a, team_a), (client_b, team_b)):
            alerts = [a for a in client.get("/alerts").get_json() if a["alert_type"] == "tenant_concentration"]
            assert len(alerts) == 1, (team, alerts)
            assert alerts[0]["natural_key"].startswith(f"tenant_concentration:team{team}:")
    finally:
        os.unlink(db)
    print("✓ test_two_teams_with_the_same_tenant_each_get_their_own_concentration_alert: PASS")


def _t12_result(diff):
    return {"property_address": "1 Main St", "flagged": True, "difference": diff,
            "rent_roll_annual_rent": 100000 + diff, "t12_annual_rental_income": 100000}


def test_two_teams_with_the_same_t12_address_dont_overwrite_each_other():
    db = _fresh_temp_db()
    try:
        team_a, _, _, team_b, _, _ = _two_teams()
        discrepancies_module.sync_t12_reconciliation(_t12_result(11111), team_a)
        discrepancies_module.sync_t12_reconciliation(_t12_result(77777), team_b)  # used to 500 and overwrite A
        a_rows = [d for d in database.list_discrepancies(team_id=team_a) if d["discrepancy_type"] == "t12_reconciliation"]
        b_rows = [d for d in database.list_discrepancies(team_id=team_b) if d["discrepancy_type"] == "t12_reconciliation"]
        assert len(a_rows) == 1 and "111111" in a_rows[0]["message"], a_rows
        assert len(b_rows) == 1 and "177777" in b_rows[0]["message"], b_rows
    finally:
        os.unlink(db)
    print("✓ test_two_teams_with_the_same_t12_address_dont_overwrite_each_other: PASS")


def test_migration_rewrites_old_name_based_keys_once():
    db = _fresh_temp_db()
    try:
        team_a = database.create_team("Team A")["id"]
        now = datetime.now(timezone.utc).isoformat()
        conn = database.get_connection()
        conn.execute("INSERT INTO alerts (alert_type, natural_key, severity, title, message, details, status, first_detected_at, last_seen_at, team_id) "
                     "VALUES ('tenant_concentration', 'tenant_concentration:acme', 'high', 't', 'm', '{}', 'active', ?, ?, ?)", (now, now, team_a))
        conn.execute("INSERT INTO discrepancies (discrepancy_type, natural_key, category, message, details, status, first_detected_at, last_seen_at, team_id) "
                     "VALUES ('t12_reconciliation', 't12_recon:1 main st', 't12_reconciliation', 'm', '{}', 'open', ?, ?, ?)", (now, now, team_a))
        conn.commit(); conn.close()
        database.init_db()
        database.init_db()  # idempotent: second run must not double-prefix
        conn = database.get_connection()
        a = conn.execute("SELECT natural_key FROM alerts").fetchone()[0]
        d = conn.execute("SELECT natural_key FROM discrepancies").fetchone()[0]
        conn.close()
        assert a == f"tenant_concentration:team{team_a}:acme", a
        assert d == f"t12_recon:team{team_a}:1 main st", d
    finally:
        os.unlink(db)
    print("✓ test_migration_rewrites_old_name_based_keys_once: PASS")


# ---------------------------------------------------------------- 5

def test_two_teams_can_assign_the_same_property_address_independently():
    db = _fresh_temp_db()
    try:
        team_a, ua, client_a, team_b, ub, client_b = _two_teams()
        body = {"target_type": "property", "target": "100 Maple Ridge Dr"}
        ra = client_a.post("/assignments", json={**body, "assigned_to_user_id": ua})
        rb = client_b.post("/assignments", json={**body, "assigned_to_user_id": ub})
        assert ra.status_code in (200, 201) and rb.status_code in (200, 201), (ra.get_json(), rb.get_json())
        a_rows = database.list_assignments(team_id=team_a)
        b_rows = database.list_assignments(team_id=team_b)
        assert len(a_rows) == 1 and a_rows[0]["assigned_to_user_id"] == ua, a_rows
        assert len(b_rows) == 1 and b_rows[0]["assigned_to_user_id"] == ub, b_rows
    finally:
        os.unlink(db)
    print("✓ test_two_teams_can_assign_the_same_property_address_independently: PASS")


def test_assignments_migration_keeps_existing_rows():
    db = _fresh_temp_db()
    try:
        team, uid, _, _, _, _ = _two_teams()
        assert database.upsert_assignment("property", "1 main st", uid, uid, team, property_address="1 main st")
        database.init_db()  # rerun: must be a no-op on an already-migrated table
        rows = database.list_assignments(team_id=team)
        assert len(rows) == 1 and rows[0]["target_key"] == "1 main st"
    finally:
        os.unlink(db)
    print("✓ test_assignments_migration_keeps_existing_rows: PASS")


# ---------------------------------------------------------------- 6

def test_deactivating_a_user_or_team_ends_live_sessions_immediately():
    db = _fresh_temp_db()
    try:
        team_a, ua, client_a, team_b, ub, client_b = _two_teams()
        assert client_a.get("/leases").status_code == 200
        database.update_user_status(ua, "deactivated")
        assert client_a.get("/leases").status_code == 401, "a deactivated user's live session must stop working"

        assert client_b.get("/leases").status_code == 200
        conn = database.get_connection()
        conn.execute("UPDATE teams SET status = 'deactivated' WHERE id = ?", (team_b,))
        conn.commit(); conn.close()
        assert client_b.get("/leases").status_code == 401, "a deactivated team's live sessions must stop working"
    finally:
        os.unlink(db)
    print("✓ test_deactivating_a_user_or_team_ends_live_sessions_immediately: PASS")


def test_role_downgrade_applies_on_the_next_request():
    db = _fresh_temp_db()
    try:
        _, ua, client_a, _, _, _ = _two_teams(role="admin")
        assert client_a.get("/team/members").status_code == 200
        database.update_user_role(ua, "viewer")
        assert client_a.get("/team/members").status_code == 403
    finally:
        os.unlink(db)
    print("✓ test_role_downgrade_applies_on_the_next_request: PASS")


def test_session_from_before_team_isolation_gets_its_team_from_the_database():
    db = _fresh_temp_db()
    try:
        team_a, ua, _, _, _, _ = _two_teams()
        client = app.test_client()
        with client.session_transaction() as sess:  # old cookie shape: no team_id claim
            sess["user_id"] = ua
            sess["role"] = "admin"
        assert client.get("/leases").status_code == 200, "must work (team read from the user row), not 500"
    finally:
        os.unlink(db)
    print("✓ test_session_from_before_team_isolation_gets_its_team_from_the_database: PASS")


# ---------------------------------------------------------------- 7

def test_team_admin_cannot_change_or_reset_the_owner_account():
    db = _fresh_temp_db()
    try:
        team = database.create_team("Legacy-like")["id"]
        owner = database.create_user("owner@abstractly.test", "Owner", hash_password("password123"), role="admin", team_id=team)["id"]
        admin = database.create_user("admin@abstractly.test", "Admin", hash_password("password123"), role="admin", team_id=team)["id"]
        conn = database.get_connection()
        conn.execute("UPDATE users SET is_owner = 1 WHERE id = ?", (owner,))
        conn.commit(); conn.close()
        client = _login(admin)
        assert client.patch(f"/team/members/{owner}", json={"role": "viewer"}).status_code == 403
        assert client.post(f"/team/members/{owner}/reset-password", json={"password": "attacker-pass"}).status_code == 403
        assert database.get_user(owner)["role"] == "admin"
        assert client.patch(f"/team/members/{admin}", json={"name": "Renamed"}).status_code == 200, "ordinary members still editable"
    finally:
        os.unlink(db)
    print("✓ test_team_admin_cannot_change_or_reset_the_owner_account: PASS")


if __name__ == "__main__":
    test_undo_of_another_teams_field_edit_is_a_404_and_changes_nothing()
    test_same_team_undo_still_works_and_its_audit_row_stays_in_the_team()
    test_field_edit_and_version_chain_helpers_require_and_enforce_a_team()
    test_team_admin_cannot_list_or_change_other_teams_or_read_the_waitlist()
    test_owner_can_still_manage_teams_and_the_waitlist()
    test_two_teams_with_the_same_tenant_each_get_their_own_concentration_alert()
    test_two_teams_with_the_same_t12_address_dont_overwrite_each_other()
    test_migration_rewrites_old_name_based_keys_once()
    test_two_teams_can_assign_the_same_property_address_independently()
    test_assignments_migration_keeps_existing_rows()
    test_deactivating_a_user_or_team_ends_live_sessions_immediately()
    test_role_downgrade_applies_on_the_next_request()
    test_session_from_before_team_isolation_gets_its_team_from_the_database()
    test_team_admin_cannot_change_or_reset_the_owner_account()
    print("\nAll team-isolation regression tests passed.")
