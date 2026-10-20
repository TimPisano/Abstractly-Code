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
until it is.
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

        before = _snapshot(team_a_leases)

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
        one = sorted(team_a_leases)[0]
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

        # ---- nothing team B sent changed team A's leases
        assert _snapshot(team_a_leases) == before
        assert _lease_ids(client, admin_token) == team_a_leases

        print(f"✓ test_two_accounts_share_one_team_and_another_team_sees_nothing: PASS "
              f"({len(checked)} per-lease route/method pairs -> 404; query/body routes not 404 but empty: {not_404 or 'none'})")


if __name__ == "__main__":
    test_two_accounts_share_one_team_and_another_team_sees_nothing()
    print("\nAll 1 two-team access tests passed.")
