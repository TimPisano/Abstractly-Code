"""
Tests for team invites by email (feature/tester-ready, behind
TEAM_INVITES_ENABLED) and for removing a member ending their sessions.

Same conventions as test_auth_flow.py: _fresh_temp_db() + Flask
test_client(), email captured at email_service._send (never reaches
SMTP), every rate limiter cleared per test.
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import hashlib
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import api as api_module
from app import database, email_service
from app.auth import hash_password

GOOD_PASSWORD = "maple ridge closing day"
INVITEE_PASSWORD = "harbor lights at dusk"

_outbox = []


def _capture_send(to_email, subject, text_body, html_body, reply_to=None):
    _outbox.append({"to": to_email, "subject": subject, "text": text_body, "html": html_body})
    return True


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


class _Env:
    """Fresh DB, invites on (unless flag=False), mail captured, every limiter cleared."""

    def __init__(self, flag=True, send=_capture_send):
        self.flag = flag
        self.send = send

    def __enter__(self):
        self.db = _fresh_temp_db()
        _outbox.clear()
        self.patches = [
            mock.patch.object(email_service, "_send", self.send),
            mock.patch.object(api_module, "_send_email_off_request_path", lambda fn, *a: api_module._send_email_best_effort(fn, *a)),
            mock.patch.dict(os.environ, {"TEAM_INVITES_ENABLED": "true" if self.flag else ""}),
        ]
        for p in self.patches:
            p.start()
        api_module._reset_reset_password_rate_limit_for_tests()
        api_module._reset_forgot_password_rate_limit_for_tests()
        api_module._reset_login_rate_limit_for_tests()
        api_module._reset_invite_rate_limit_for_tests()
        email_service._reset_rate_limit_state_for_tests()
        return app.test_client()

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()
        os.unlink(self.db)


def _make_admin(email="avery@harbor.test", name="Avery Stone", team_name="Harbor Capital", role="admin"):
    team = database.get_team_by_name(team_name) or database.create_team(team_name)
    uid = database.create_user(email, name, hash_password(GOOD_PASSWORD), role=role, team_id=team["id"])["id"]
    return uid, team["id"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password=GOOD_PASSWORD):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["token"]


def _invite(client, admin_token, email="riley@harbor.test", role="analyst", name="Riley Shaw", **extra):
    return client.post("/team/invites", json={"email": email, "role": role, "name": name, **extra}, headers=_bearer(admin_token))


def _link_token(mail):
    m = re.search(r"token=([A-Za-z0-9_\-]+)", mail["text"])
    assert m, f"no link in email: {mail['subject']}"
    return m.group(1)


def _accept(client, token, password=INVITEE_PASSWORD):
    return client.post("/auth/accept-invite", json={"token": token, "new_password": password})


def _invite_status(client, token):
    return client.post("/auth/invite-status", json={"token": token}).get_json()


def _age_invite(token, seconds):
    when = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    conn = database.get_connection()
    try:
        conn.execute("UPDATE password_reset_tokens SET created_at = ? WHERE token_hash = ?", (when, hashlib.sha256(token.encode()).hexdigest()))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- flag

def test_flag_off_hides_every_invite_route():
    with _Env(flag=False) as client:
        _make_admin()
        token = _login(client, "avery@harbor.test")
        assert client.get("/team/invites", headers=_bearer(token)).get_json() == {"enabled": False, "invites": []}
        assert _invite(client, token).status_code == 404
        assert client.post("/team/invites/1/resend", headers=_bearer(token)).status_code == 404
        assert client.post("/team/invites/1/revoke", headers=_bearer(token)).status_code == 404
        assert client.post("/auth/invite-status", json={"token": "x" * 43}).status_code == 404
        assert client.post("/auth/accept-invite", json={"token": "x" * 43, "new_password": INVITEE_PASSWORD}).status_code == 404
        assert _outbox == []
    print("✓ test_flag_off_hides_every_invite_route: PASS")


# ---------------------------------------------------------------- happy path

def test_invite_then_accept_joins_the_admins_team():
    with _Env() as client:
        admin_id, team_id = _make_admin()
        admin_token = _login(client, "avery@harbor.test")

        resp = _invite(client, admin_token)
        assert resp.status_code == 201, resp.get_json()
        body = resp.get_json()
        assert body["emailed"] is True and "invite_url" not in body
        assert body["invite"]["email"] == "riley@harbor.test" and body["invite"]["expired"] is False

        assert len(_outbox) == 1
        mail = _outbox[0]
        assert mail["to"] == "riley@harbor.test"
        assert mail["subject"] == "Join Harbor Capital on Abstractly"
        assert "Avery Stone invited you to join Harbor Capital" in mail["text"]
        assert "72 hours" in mail["text"]
        assert "/app/team-setup.html?kind=invite&token=" in mail["text"]
        raw = _link_token(mail)

        pending = database.get_user_by_email("riley@harbor.test")
        assert pending["status"] == "invited" and pending["team_id"] == team_id and pending["role"] == "analyst"
        assert pending["created_by_user_id"] == admin_id
        # Pending: can't sign in, not in the member list, listed as an invite.
        assert client.post("/auth/login", json={"email": "riley@harbor.test", "password": INVITEE_PASSWORD}).status_code == 401
        members = client.get("/team/members", headers=_bearer(admin_token)).get_json()
        assert [m["email"] for m in members] == ["avery@harbor.test"]
        invites = client.get("/team/invites", headers=_bearer(admin_token)).get_json()
        assert invites["enabled"] is True and [i["email"] for i in invites["invites"]] == ["riley@harbor.test"]
        assert invites["invites"][0]["invited_by_name"] == "Avery Stone"

        status = _invite_status(client, raw)
        assert status == {"status": "valid", "email": "riley@harbor.test", "first_name": "Riley", "team_name": "Harbor Capital"}

        accepted = _accept(app.test_client(), raw)
        assert accepted.status_code == 201, accepted.get_json()
        joined = accepted.get_json()
        assert joined["team_id"] == team_id and joined["role"] == "analyst" and joined["token"]

        session = client.get("/auth/session", headers=_bearer(joined["token"])).get_json()
        assert session["authenticated"] is True and session["team_id"] == team_id
        assert database.get_user_by_email("riley@harbor.test")["status"] == "active"
        assert _login(app.test_client(), "riley@harbor.test", INVITEE_PASSWORD)
        assert client.get("/team/invites", headers=_bearer(admin_token)).get_json()["invites"] == []

        # Single use.
        again = _accept(app.test_client(), raw, password="another long passphrase")
        assert again.status_code == 400 and again.get_json()["link_status"] == "used"
    print("✓ test_invite_then_accept_joins_the_admins_team: PASS")


def test_rejected_password_does_not_burn_the_invite():
    with _Env() as client:
        _make_admin()
        _invite(client, _login(client, "avery@harbor.test"))
        raw = _link_token(_outbox[0])
        weak = _accept(client, raw, password="short")
        assert weak.status_code == 400 and "link_status" not in weak.get_json()
        assert _invite_status(client, raw)["status"] == "valid"
        assert _accept(client, raw).status_code == 201
    print("✓ test_rejected_password_does_not_burn_the_invite: PASS")


def test_without_email_the_admin_gets_the_link_to_share():
    with _Env(send=lambda *a, **k: False) as client:
        _make_admin()
        body = _invite(client, _login(client, "avery@harbor.test")).get_json()
        assert body["emailed"] is False
        m = re.search(r"/app/team-setup\.html\?kind=invite&token=([A-Za-z0-9_\-]+)$", body["invite_url"])
        assert m, body["invite_url"]
        assert _accept(client, m.group(1)).status_code == 201
    print("✓ test_without_email_the_admin_gets_the_link_to_share: PASS")


# ---------------------------------------------------------------- tokens

def test_invite_tokens_are_stored_hashed_never_raw():
    with _Env() as client:
        _make_admin()
        _invite(client, _login(client, "avery@harbor.test"))
        raw = _link_token(_outbox[0])
        conn = database.get_connection()
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM password_reset_tokens WHERE purpose = 'invite'").fetchall()]
            dump = "\n".join(conn.iterdump())
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["token_hash"] == hashlib.sha256(raw.encode()).hexdigest()
        assert raw not in dump, "the raw invite token must never be written to the database"
        with open(api_module.database.get_db_path(), "rb") as f:
            assert raw.encode() not in f.read()
    print("✓ test_invite_tokens_are_stored_hashed_never_raw: PASS")


def test_invite_link_expires_after_72_hours_and_resend_replaces_it():
    with _Env() as client:
        _make_admin()
        admin_token = _login(client, "avery@harbor.test")
        _invite(client, admin_token)
        old = _link_token(_outbox[0])
        invite_id = database.get_user_by_email("riley@harbor.test")["id"]

        _age_invite(old, 71 * 3600)
        assert _invite_status(client, old)["status"] == "valid"
        _age_invite(old, 73 * 3600)
        assert _invite_status(client, old) == {"status": "expired"}
        listed = client.get("/team/invites", headers=_bearer(admin_token)).get_json()["invites"][0]
        assert listed["expired"] is True
        assert _accept(client, old).get_json()["link_status"] == "expired"

        resent = client.post(f"/team/invites/{invite_id}/resend", headers=_bearer(admin_token))
        assert resent.status_code == 200 and resent.get_json()["invite"]["expired"] is False
        new = _link_token(_outbox[-1])
        assert new != old
        assert _invite_status(client, old)["status"] == "superseded"
        assert _accept(client, new).status_code == 201
    print("✓ test_invite_link_expires_after_72_hours_and_resend_replaces_it: PASS")


def test_other_link_kinds_cannot_stand_in_for_an_invite():
    with _Env() as client:
        _make_admin()
        _invite(client, _login(client, "avery@harbor.test"))
        invite_raw = _link_token(_outbox[0])
        # An invite token is not a reset or setup link.
        assert client.post("/auth/reset-password", json={"token": invite_raw, "new_password": INVITEE_PASSWORD}).status_code == 400
        assert client.post("/auth/team-setup", json={"token": invite_raw, "new_password": INVITEE_PASSWORD}).status_code == 400
        # And a reset token for an active member is not an invite.
        member_id, _ = _make_admin(email="sam@harbor.test", name="Sam Ortiz", role="viewer")
        reset_raw = "r" * 43
        database.create_password_reset_token(member_id, hashlib.sha256(reset_raw.encode()).hexdigest(), purpose="reset")
        assert _invite_status(client, reset_raw) == {"status": "invalid"}
        assert _accept(client, reset_raw).status_code == 400
        assert _invite_status(client, invite_raw)["status"] == "valid"
    print("✓ test_other_link_kinds_cannot_stand_in_for_an_invite: PASS")


# ---------------------------------------------------------------- revoke

def test_revoke_kills_the_link_and_frees_the_email():
    with _Env() as client:
        _make_admin()
        admin_token = _login(client, "avery@harbor.test")
        _invite(client, admin_token)
        raw = _link_token(_outbox[0])
        invite_id = database.get_user_by_email("riley@harbor.test")["id"]

        assert client.post(f"/team/invites/{invite_id}/revoke", headers=_bearer(admin_token)).status_code == 200
        assert database.get_user_by_email("riley@harbor.test") is None
        assert _invite_status(client, raw) == {"status": "invalid"}
        assert _accept(client, raw).status_code == 400
        assert client.post(f"/team/invites/{invite_id}/revoke", headers=_bearer(admin_token)).status_code == 404

        assert _invite(client, admin_token).status_code == 201, "a revoked address can be invited again"
    print("✓ test_revoke_kills_the_link_and_frees_the_email: PASS")


def test_revoke_and_resend_never_touch_a_member_who_joined():
    with _Env() as client:
        _make_admin()
        admin_token = _login(client, "avery@harbor.test")
        _invite(client, admin_token)
        _accept(client, _link_token(_outbox[0]))
        member_id = database.get_user_by_email("riley@harbor.test")["id"]
        assert client.post(f"/team/invites/{member_id}/revoke", headers=_bearer(admin_token)).status_code == 404
        assert client.post(f"/team/invites/{member_id}/resend", headers=_bearer(admin_token)).status_code == 404
        assert database.get_user(member_id)["status"] == "active"
    print("✓ test_revoke_and_resend_never_touch_a_member_who_joined: PASS")


# ---------------------------------------------------------------- validation + who may

def test_invite_conflicts_are_clear_409s():
    with _Env() as client:
        _make_admin()
        _make_admin(email="sam@harbor.test", name="Sam Ortiz", role="viewer")
        _make_admin(email="lee@otherfirm.test", name="Lee Park", team_name="Other Firm")
        admin_token = _login(client, "avery@harbor.test")

        assert _invite(client, admin_token, email="sam@harbor.test").status_code == 409
        assert _invite(client, admin_token, email="LEE@otherfirm.test").status_code == 409
        assert database.get_user_by_email("lee@otherfirm.test")["status"] == "active", "another team's user is untouched"
        assert _invite(client, admin_token).status_code == 201
        dup = _invite(client, admin_token)
        assert dup.status_code == 409 and "Resend" in dup.get_json()["error"]

        sam = database.get_user_by_email("sam@harbor.test")
        database.update_user_status(sam["id"], "deactivated")
        assert "Reactivate" in _invite(client, admin_token, email="sam@harbor.test").get_json()["error"]

        assert _invite(client, admin_token, email="not-an-email").status_code == 400
        assert _invite(client, admin_token, email="pat@harbor.test", role="owner").status_code == 400
        assert len(_outbox) == 1
    print("✓ test_invite_conflicts_are_clear_409s: PASS")


def test_only_admins_invite_and_only_into_their_own_team():
    with _Env() as client:
        _, team_a = _make_admin()
        _, team_b = _make_admin(email="lee@otherfirm.test", name="Lee Park", team_name="Other Firm")
        _make_admin(email="sam@harbor.test", name="Sam Ortiz", role="analyst")
        a_token = _login(client, "avery@harbor.test")
        b_token = _login(client, "lee@otherfirm.test")
        analyst_token = _login(client, "sam@harbor.test")

        assert _invite(client, analyst_token).status_code == 403
        assert client.get("/team/invites", headers=_bearer(analyst_token)).status_code == 403
        assert app.test_client().post("/team/invites", json={"email": "x@y.test", "role": "viewer"}).status_code == 401

        # A team_id in the body is ignored: the invite lands on the caller's team.
        assert _invite(client, a_token, team_id=team_b).status_code == 201
        assert database.get_user_by_email("riley@harbor.test")["team_id"] == team_a
        invite_id = database.get_user_by_email("riley@harbor.test")["id"]

        # Team B's admin can't see, resend or revoke team A's invite.
        assert client.get("/team/invites", headers=_bearer(b_token)).get_json()["invites"] == []
        assert client.post(f"/team/invites/{invite_id}/resend", headers=_bearer(b_token)).status_code == 404
        assert client.post(f"/team/invites/{invite_id}/revoke", headers=_bearer(b_token)).status_code == 404
        assert database.get_user(invite_id)["status"] == "invited"
    print("✓ test_only_admins_invite_and_only_into_their_own_team: PASS")


def test_pending_invitee_cannot_be_assigned_or_edited():
    with _Env() as client:
        _, team_id = _make_admin()
        admin_token = _login(client, "avery@harbor.test")
        _invite(client, admin_token)
        invite_id = database.get_user_by_email("riley@harbor.test")["id"]
        assert api_module._get_team_member(invite_id, team_id) is None
        # Can't be switched to active (with no password) through the member routes.
        patched = client.patch(f"/team/members/{invite_id}", json={"status": "active"}, headers=_bearer(admin_token))
        assert patched.status_code == 404
        assert database.get_user(invite_id)["status"] == "invited"
    print("✓ test_pending_invitee_cannot_be_assigned_or_edited: PASS")


def test_invite_to_a_deactivated_team_cannot_be_accepted():
    with _Env() as client:
        _, team_id = _make_admin()
        _invite(client, _login(client, "avery@harbor.test"))
        raw = _link_token(_outbox[0])
        database.update_team_status(team_id, "deactivated")
        assert _invite_status(client, raw) == {"status": "invalid"}
        assert _accept(client, raw).status_code == 400
        assert database.get_user_by_email("riley@harbor.test")["status"] == "invited"
    print("✓ test_invite_to_a_deactivated_team_cannot_be_accepted: PASS")


def test_invite_email_escapes_names_and_keeps_the_subject_on_one_line():
    with _Env() as client:
        team = database.create_team("Harbor <b>Capital</b>\r\nBcc: x@evil.test")
        database.create_user("avery@harbor.test", "Avery <script>", hash_password(GOOD_PASSWORD), role="admin", team_id=team["id"])
        _invite(client, _login(client, "avery@harbor.test"))
        mail = _outbox[0]
        assert "\n" not in mail["subject"] and "\r" not in mail["subject"]
        assert "<script>" not in mail["html"] and "<b>Capital</b>" not in mail["html"]
        assert "&lt;b&gt;Capital&lt;/b&gt;" in mail["html"]
    print("✓ test_invite_email_escapes_names_and_keeps_the_subject_on_one_line: PASS")


# ---------------------------------------------------------------- removing a member

def test_removing_a_member_ends_their_sessions_even_after_reactivation():
    """
    Regression: deactivating a member only blocked them while deactivated.
    Reactivating them brought every old cookie and bearer token back to
    life (session_version was never bumped). Removal must end those
    sessions for good.
    """
    with _Env() as client:
        _make_admin()
        member_id, _ = _make_admin(email="sam@harbor.test", name="Sam Ortiz", role="analyst")
        admin_token = _login(client, "avery@harbor.test")

        member_browser = app.test_client()
        cookie_login = member_browser.post("/auth/login", json={"email": "sam@harbor.test", "password": GOOD_PASSWORD},
                                           base_url="https://localhost")
        assert cookie_login.status_code == 200
        bearer = cookie_login.get_json()["token"]

        def signed_in_by_cookie():
            return member_browser.get("/auth/session", base_url="https://localhost").get_json()["authenticated"]

        def signed_in_by_bearer():
            return client.get("/team/usage", headers=_bearer(bearer)).status_code == 200

        assert signed_in_by_cookie() and signed_in_by_bearer()

        assert client.patch(f"/team/members/{member_id}", json={"status": "deactivated"}, headers=_bearer(admin_token)).status_code == 200
        assert not signed_in_by_cookie() and not signed_in_by_bearer(), "removal must end sessions immediately"

        assert client.patch(f"/team/members/{member_id}", json={"status": "active"}, headers=_bearer(admin_token)).status_code == 200
        assert not signed_in_by_cookie(), "an old cookie must not come back to life on reactivation"
        assert not signed_in_by_bearer(), "an old bearer token must not come back to life on reactivation"

        # A fresh login after reactivation works.
        assert _login(app.test_client(), "sam@harbor.test")
    print("✓ test_removing_a_member_ends_their_sessions_even_after_reactivation: PASS")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} team invite tests passed.")
