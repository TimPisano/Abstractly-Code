"""
The two-account check, end to end (feature/tester-ready step 5).

Team A is set up the way a real tester firm is: the owner creates it in
the owner console, its admin sets a password from the emailed setup
link, then invites a teammate, who accepts the invite. Both upload a
lease; each must see the other's. A user on a second, separately created
team (team B) must then get a 404 on every route that names one of team
A's leases -- every method, every export and download -- and nothing of
team A's may appear in team B's own portfolio-wide exports. Finally team
A's leases are checked unchanged, so none of team B's requests had an
effect.

Routes are discovered from Flask's URL map, not hand-listed: a new
`/leases/<int:lease_id>/...` route that isn't scoped fails this test
until it is. The same goes for every other route that names a record by
id in its path (alerts, discrepancies, tasks, assignments, threads, team
members and invites, linked email accounts): team B gets a 404 for each
of team A's records, and a new such route with an id the test doesn't
know how to fill in fails it. Routes that take ids in the request body
(bulk delete/tag/export, bulk task/discrepancy/alert actions, new
tasks, assignments and threads) are sent team A's ids, and afterwards
every team-scoped table is compared row for row: team A's rows must be
unchanged, and none of team B's new rows may point at a team A record.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openpyxl
import pypdf

from app import database
from app.api import app
from app.auth import hash_password
from test_monthly_page_limit import _Uploads, _pdf
from test_team_invites import _bearer, _link_token, _login, _outbox

GOOD_PASSWORD = "maple ridge closing day"
MARKER = "harborcapmarker"

# Body each mutating per-lease route gets, so a missing ownership check
# would actually reach the write instead of failing validation first.
_BODIES = {
    ("PATCH", "/leases/<int:lease_id>"): {"display_name": "hijacked"},
    ("POST", "/leases/<int:lease_id>/comments"): {"body": "hijacked"},
    ("POST", "/leases/<int:lease_id>/tags"): {"tag": "hijacked"},
    ("PATCH", "/leases/<int:lease_id>/fields/<field_name>"): {"value": "hijacked"},
    ("POST", "/leases/<int:lease_id>/fields/<field_name>/verify"): {},
    ("POST", "/leases/<int:lease_id>/export/google-sheets"): {},
}
_FILE_ROUTES = {"/leases/<int:lease_id>/amendments", "/leases/<int:lease_id>/resubmit"}


def _make_owner():
    team = database.get_team_by_name("Legacy") or database.create_team("Legacy")
    uid = database.create_user("tim@abstractly.test", "Tim", hash_password(GOOD_PASSWORD), role="admin", team_id=team["id"])["id"]
    conn = database.get_connection()
    try:
        conn.execute("UPDATE users SET is_owner = 1 WHERE id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()
    return uid


def _owner_creates_team(client, owner, firm, admin_name, admin_email):
    """Owner console -> setup email -> the admin sets their password. Returns (team_id, admin bearer token)."""
    before = len(_outbox)
    resp = client.post("/owner/teams", json={"firm_name": firm, "admin_name": admin_name, "admin_email": admin_email}, headers=owner)
    assert resp.status_code == 201, resp.get_json()
    assert len(_outbox) == before + 1 and _outbox[-1]["to"] == admin_email
    setup = client.post("/auth/team-setup", json={"token": _link_token(_outbox[-1]), "new_password": GOOD_PASSWORD})
    assert setup.status_code == 200, setup.get_json()
    return resp.get_json()["team"]["id"], _login(client, admin_email)


def _upload(client, token, name, pages=2):
    resp = client.post("/leases", data={"file": (io.BytesIO(_pdf(pages)), name)}, headers=_bearer(token),
                       content_type="multipart/form-data")
    assert resp.status_code in (200, 201, 202), resp.get_json()
    return resp.get_json()["leases"][0]["id"]


def _lease_ids(client, token):
    body = client.get("/leases", headers=_bearer(token)).get_json()
    leases = body["leases"] if isinstance(body, dict) else body
    return {lease["id"] for lease in leases}


# Any body a mutating record route could need, so a missing ownership
# check would reach the write instead of failing validation first.
_HIJACK_BODY = {
    "title": "hijacked", "body": "hijacked", "note": "hijacked", "status": "done",
    "correct_source": "rent_roll", "role": "viewer", "new_password": "hijacked password 123",
    "monthly_page_quota": 1, "to": "riley@harbor.test", "subject": "hijacked",
}

# Records that aren't any team's data: owner bookkeeping and the public
# waitlist. Every other `<int:...>` route must be in _record_ids below.
_NOT_TEAM_DATA = ("/owner/expenses/", "/owner/revenue/", "/waitlist/")

# Columns that point at another record, by the kind of record they name.
_REF_KINDS = {
    "lease_id": "leases", "base_lease_id": "leases", "supersedes_lease_id": "leases", "related_lease_id": "leases",
    "discrepancy_id": "discrepancies", "task_id": "tasks", "thread_id": "message_threads",
    "user_id": "users", "assigned_to_user_id": "users", "assigned_by_user_id": "users",
    "created_by_user_id": "users", "sender_user_id": "users",
}


def _team_tables(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return [n for n in names if any(c[1] == "team_id" for c in conn.execute(f"PRAGMA table_info({n})"))]


def _team_state(team_id):
    """Every row of every team-scoped table that belongs to `team_id`, plus its users' link tokens."""
    conn = database.get_connection()
    try:
        state = {t: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {t} WHERE team_id = ?", (team_id,)).fetchall())
                 for t in _team_tables(conn)}
        state["password_reset_tokens"] = sorted(tuple(r) for r in conn.execute(
            "SELECT * FROM password_reset_tokens WHERE user_id IN (SELECT id FROM users WHERE team_id = ?)", (team_id,)).fetchall())
        return state
    finally:
        conn.close()


def _rows_pointing_across(from_team, to_team):
    """Rows owned by `from_team` that reference one of `to_team`'s records."""
    conn = database.get_connection()
    try:
        theirs = {kind: {r[0] for r in conn.execute(f"SELECT id FROM {kind} WHERE team_id = ?", (to_team,))}
                  for kind in set(_REF_KINDS.values())}
        found = []
        for table in _team_tables(conn):
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            for row in conn.execute(f"SELECT * FROM {table} WHERE team_id = ?", (from_team,)).fetchall():
                for col, kind in _REF_KINDS.items():
                    if col in cols and row[cols.index(col)] in theirs[kind]:
                        found.append(f"{table}.{col} = {row[cols.index(col)]} (team {to_team}'s {kind})")
        return found
    finally:
        conn.close()


def _snapshot(lease_ids):
    conn = database.get_connection()
    try:
        out = {}
        for lid in lease_ids:
            out[lid] = {
                "lease": dict(conn.execute("SELECT * FROM leases WHERE id = ?", (lid,)).fetchone()),
                "tags": [tuple(r) for r in conn.execute("SELECT * FROM lease_tags WHERE lease_id = ?", (lid,)).fetchall()],
                "comments": [tuple(r) for r in conn.execute("SELECT * FROM comments WHERE lease_id = ?", (lid,)).fetchall()],
                "amendments": [tuple(r) for r in conn.execute("SELECT id FROM leases WHERE base_lease_id = ?", (lid,)).fetchall()],
            }
        return out
    finally:
        conn.close()


def _concrete(rule, lease_id):
    path = rule.rule.replace("<int:lease_id>", str(lease_id))
    path = path.replace("<field_name>", "tenant").replace("<int:edit_id>", "1").replace("<path:tag>", "anything")
    assert "<" not in path, f"test doesn't know how to fill in {rule.rule}"
    return path


def _call(client, method, path, rule, headers):
    if rule.rule in _FILE_ROUTES and method == "POST":
        return client.open(path, method=method, headers=headers, content_type="multipart/form-data",
                           data={"file": (io.BytesIO(_pdf(1)), "x.pdf")})
    body = _BODIES.get((method, rule.rule))
    if body is not None:
        return client.open(path, method=method, headers=headers, json=body)
    return client.open(path, method=method, headers=headers)


def _readable_text(resp):
    """Whatever a response says, as text: JSON/CSV as-is, PDF via its text layer, XLSX via its cells."""
    data = resp.get_data()
    if data[:4] == b"%PDF":
        return "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages)
    if data[:2] == b"PK":
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        return "\n".join(str(cell) for sheet in book.worksheets for row in sheet.iter_rows(values_only=True) for cell in row if cell is not None)
    return data.decode("utf-8", "replace")


def test_two_accounts_share_one_team_and_another_team_sees_nothing():
    with _Uploads() as client:
        _make_owner()
        owner = _bearer(_login(client, "tim@abstractly.test"))

        # ---- team A: owner creates it, admin invites a teammate, teammate accepts
        team_a, admin_token = _owner_creates_team(client, owner, "Harbor Capital", "Avery Stone", "avery@harbor.test")
        invite = client.post("/team/invites", json={"email": "riley@harbor.test", "name": "Riley Shaw", "role": "analyst"},
                             headers=_bearer(admin_token))
        assert invite.status_code == 201, invite.get_json()
        accepted = app.test_client().post("/auth/accept-invite", json={"token": _link_token(_outbox[-1]), "new_password": "harbor lights at dusk"})
        assert accepted.status_code == 201, accepted.get_json()
        teammate_token = accepted.get_json()["token"]
        assert accepted.get_json()["team_id"] == team_a

        # ---- both upload; each sees the other's lease
        from_admin = _upload(client, admin_token, f"{MARKER}-admin-lease.pdf")
        from_teammate = _upload(client, teammate_token, f"{MARKER}-teammate-lease.pdf")
        team_a_leases = {from_admin, from_teammate}
        assert _lease_ids(client, admin_token) == team_a_leases
        assert _lease_ids(client, teammate_token) == team_a_leases
        for token in (admin_token, teammate_token):
            for lid in team_a_leases:
                assert client.get(f"/leases/{lid}", headers=_bearer(token)).status_code == 200
        # Sanity: the export scan below really can see the marker when it's there.
        a_ids = ",".join(str(i) for i in sorted(team_a_leases))
        assert MARKER in _readable_text(client.get(f"/leases/export.xlsx?ids={a_ids}", headers=_bearer(teammate_token)))

        # ---- team B: created the same way, separately
        team_b, outsider_token = _owner_creates_team(client, owner, "Other Firm", "Lee Park", "lee@otherfirm.test")
        assert team_b != team_a
        outsider = _bearer(outsider_token)
        assert _lease_ids(client, outsider_token) == set()
        team_b_lease = _upload(client, outsider_token, "otherfirm-lease.pdf")
        outsider_id = database.get_user_by_email("lee@otherfirm.test")["id"]

        # ---- team A's records beyond leases, each made the way the app makes it
        admin = _bearer(admin_token)
        admin_id = database.get_user_by_email("avery@harbor.test")["id"]
        teammate_id = database.get_user_by_email("riley@harbor.test")["id"]
        one = sorted(team_a_leases)[0]
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="two-team-k1", category="missing_clause",
            message="No insurance clause", details={}, lease_id=one,
            field="insurance_requirements", severity="medium", team_id=team_a,
        )
        alert_id = database.upsert_alert(
            alert_type="below_market_rent", natural_key="two-team-alert-k1", severity="high",
            title="Rent below market", message="msg", details={}, team_id=team_a, lease_id=one,
        )
        task_id = client.post("/tasks", json={"title": "Team A task", "lease_id": one}, headers=admin).get_json()["id"]
        assignment = client.post("/assignments", json={"target_type": "lease", "target": one, "assigned_to_user_id": teammate_id}, headers=admin)
        assert assignment.status_code in (200, 201), assignment.get_json()
        thread = client.post("/threads", json={"thread_type": "direct", "participant_user_ids": [teammate_id]}, headers=admin)
        assert thread.status_code in (200, 201), thread.get_json()
        thread_id = thread.get_json()["id"]
        assert client.post(f"/threads/{thread_id}/messages", json={"body": "Team A only"}, headers=admin).status_code in (200, 201)
        pending = client.post("/team/invites", json={"email": "quinn@harbor.test", "name": "Quinn Lake", "role": "viewer"}, headers=admin)
        assert pending.status_code == 201, pending.get_json()
        email_account_id = database.upsert_linked_email_account(
            admin_id, "google", "avery@harbor.test", "not-a-real-token", "not-a-real-token", "2099-01-01T00:00:00", "email.send", team_id=team_a,
        )
        record_ids = {
            "alert_id": alert_id, "discrepancy_id": disc_id, "task_id": task_id,
            "assignment_id": assignment.get_json()["id"], "thread_id": thread_id,
            "invite_id": pending.get_json()["invite"]["id"], "member_id": teammate_id,
            "account_id": email_account_id, "user_id": admin_id, "team_id": team_a,
        }

        before = _snapshot(team_a_leases)
        team_a_before = _team_state(team_a)

        # ---- every route naming a lease in its path: 404, every method
        checked = []
        for rule in app.url_map.iter_rules():
            if "<int:lease_id>" not in rule.rule:
                continue
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                for lid in team_a_leases:
                    resp = _call(client, method, _concrete(rule, lid), rule, outsider)
                    assert resp.status_code == 404, f"{method} {rule.rule} as team B -> {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
                    assert MARKER not in resp.get_data(as_text=True)
                checked.append(f"{method} {rule.rule}")
        assert len(checked) >= 20, checked  # 21 today; a shrinking list means routes stopped being found

        # ---- routes taking lease ids in the query string or body
        ids = ",".join(str(i) for i in sorted(team_a_leases))
        by_query = [
            ("GET", f"/leases/compare?ids={ids}", None),
            ("GET", f"/leases/selection-summary?ids={ids}", None),
            ("GET", f"/leases/export.xlsx?ids={ids}", None),
            ("GET", f"/discrepancies?lease_id={one}", None),
            ("GET", f"/discrepancies/export.csv?lease_id={one}", None),
            ("GET", f"/alerts?lease_id={one}", None),
            ("GET", f"/alerts/export.csv?lease_id={one}", None),
            ("GET", f"/tasks?lease_id={one}", None),
            ("POST", "/tasks", {"lease_id": one, "title": "hijacked"}),
            ("POST", "/qa", {"lease_id": one, "question": "What is the rent?"}),
        ]
        not_404 = []
        for method, path, body in by_query:
            resp = client.open(path, method=method, headers=outsider, json=body) if body is not None else client.open(path, method=method, headers=outsider)
            assert resp.status_code < 500, f"{method} {path} -> {resp.status_code}"
            assert MARKER not in _readable_text(resp), f"{method} {path} leaked team A's data"
            if resp.status_code != 404:
                not_404.append(f"{method} {path} -> {resp.status_code}")

        # ---- team B's own portfolio-wide exports and downloads hold nothing of team A's
        for method, path in [("GET", f"/leases/export.xlsx?ids={team_b_lease}"), ("GET", "/portfolio/rent-roll.csv"), ("GET", "/portfolio/rent-roll.xlsx"),
                             ("GET", "/portfolio/summary.pdf"), ("GET", "/portfolio/monthly-report.pdf"), ("GET", "/portfolio/report"),
                             ("GET", "/discrepancies/export.csv"), ("GET", "/alerts/export.csv"), ("GET", "/leases")]:
            resp = client.open(path, method=method, headers=outsider)
            assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.get_data(as_text=True)[:150]}"
            text = _readable_text(resp)
            assert MARKER not in text, f"{path} as team B contains team A's lease"
            if path in ("/leases", f"/leases/export.xlsx?ids={team_b_lease}"):
                assert "otherfirm-lease" in text, f"sanity: team B's own {path} shows team B's data"

        # ---- every other route naming a record in its path: 404, every method
        record_checked = []
        for rule in app.url_map.iter_rules():
            if "<int:" not in rule.rule or "<int:lease_id>" in rule.rule or rule.rule.startswith(_NOT_TEAM_DATA):
                continue
            path = rule.rule
            for arg in rule.arguments:
                assert arg in record_ids, f"{rule.rule}: test doesn't know which team A record to use for <{arg}>; add one"
                path = re.sub(rf"<(?:int:)?{arg}>", str(record_ids[arg]), path)
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                resp = client.open(path, method=method, headers=outsider, json=_HIJACK_BODY if method != "GET" else None)
                assert resp.status_code == 404, f"{method} {rule.rule} as team B -> {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
                record_checked.append(f"{method} {rule.rule}")
        assert len(record_checked) >= 35, record_checked  # 37 today; a shrinking list means routes stopped being found

        # ---- routes taking team A's ids in the request body
        a_ids = sorted(team_a_leases)
        bulk_delete = client.post("/leases/bulk-delete", json={"ids": a_ids}, headers=outsider)
        assert bulk_delete.status_code == 200 and bulk_delete.get_json()["deleted"] == [], bulk_delete.get_json()
        bulk_tag = client.post("/leases/bulk-tag", json={"ids": a_ids, "tag": "hijacked"}, headers=outsider)
        assert bulk_tag.status_code == 200 and bulk_tag.get_json()["tagged"] == [], bulk_tag.get_json()
        by_body = [
            ("/leases/export/google-sheets", {"ids": a_ids}),
            ("/tasks", {"title": "hijacked", "discrepancy_id": disc_id}),
            ("/tasks", {"title": "hijacked", "assigned_to_user_id": teammate_id}),
            ("/tasks/bulk-status", {"ids": [task_id], "status": "done"}),
            ("/tasks/bulk-reassign", {"ids": [task_id], "assigned_to_user_id": outsider_id}),
            ("/tasks/bulk-reassign", {"ids": [], "assigned_to_user_id": teammate_id}),
            ("/discrepancies/bulk-resolve", {"ids": [disc_id], "correct_source": "rent_roll", "note": "hijacked"}),
            ("/alerts/bulk-dismiss", {"ids": [alert_id], "note": "hijacked"}),
            ("/assignments", {"target_type": "lease", "target": one, "assigned_to_user_id": outsider_id}),
            ("/assignments", {"target_type": "discrepancy", "target": disc_id, "assigned_to_user_id": outsider_id}),
            ("/assignments", {"target_type": "lease", "target": team_b_lease, "assigned_to_user_id": teammate_id}),
            ("/threads", {"thread_type": "direct", "participant_user_ids": [teammate_id]}),
            ("/threads", {"thread_type": "group", "participant_user_ids": [admin_id, teammate_id], "name": "hijacked"}),
        ]
        for path, body in by_body:
            resp = client.post(path, json=body, headers=outsider)
            assert resp.status_code < 500, f"POST {path} {body} -> {resp.status_code}"
            assert MARKER not in resp.get_data(as_text=True), f"POST {path} leaked team A's data"
        own_thread = client.post("/threads", json={"thread_type": "group", "participant_user_ids": [outsider_id], "name": "B only"}, headers=outsider)
        if own_thread.status_code in (200, 201):
            resp = client.post(f"/threads/{own_thread.get_json()['id']}/participants", json={"user_id": teammate_id}, headers=outsider)
            assert resp.status_code in (400, 404), f"team B added team A's user to its thread -> {resp.status_code}"

        # ---- nothing team B sent changed team A's records or linked to them
        assert _snapshot(team_a_leases) == before
        assert _lease_ids(client, admin_token) == team_a_leases
        after = _team_state(team_a)
        changed = [t for t in team_a_before if team_a_before[t] != after[t]]
        assert not changed, f"team B's requests changed team A's rows in: {changed}"
        crossing = _rows_pointing_across(team_b, team_a)
        assert not crossing, "team B's rows point at team A's records:\n  " + "\n  ".join(crossing)

        print(f"✓ test_two_accounts_share_one_team_and_another_team_sees_nothing: PASS "
              f"({len(checked)} per-lease and {len(record_checked)} other record route/method pairs -> 404; "
              f"{len(by_body) + 2} body-id requests changed nothing; query routes not 404 but empty: {not_404 or 'none'})")


if __name__ == "__main__":
    test_two_accounts_share_one_team_and_another_team_sees_nothing()
    print("\nAll 1 two-team access tests passed.")
