"""
Regression tests for team-setup.html's setup mode (a new team's first
admin, link from POST /owner/teams).

The bug: the page checked for 8 characters while the server requires 10,
and treated any 400 whose error didn't mention "8 characters" as a dead
link. A 9-character password therefore got "Ask whoever set up your team
to invite you again" and the form disappeared, though the link still
worked. Now the server marks dead links with `link_status` and the page
decides from that alone.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import database
from app.auth import hash_password
from test_team_invites import _Env, _make_admin

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "app")
GOOD_PASSWORD = "harbor lights at dusk"


def _setup_link(email="avery@harbor.test"):
    uid, _ = _make_admin(email=email)
    raw = f"setup{email.split('@')[0]}".ljust(43, "x")
    database.create_password_reset_token(uid, hashlib.sha256(raw.encode()).hexdigest(), purpose="setup")
    return raw


def _setup(client, token, password):
    return client.post("/auth/team-setup", json={"token": token, "new_password": password})


def test_a_password_the_server_rejects_leaves_the_setup_link_alive():
    with _Env() as client:
        raw = _setup_link()
        nine = _setup(client, raw, "ninechars")
        assert nine.status_code == 400
        body = nine.get_json()
        assert "link_status" not in body, "a password problem must not read as a dead link"
        assert "10 characters" in body["error"]
        ok = _setup(client, raw, GOOD_PASSWORD)
        assert ok.status_code == 200, ok.get_json()
    print("✓ test_a_password_the_server_rejects_leaves_the_setup_link_alive: PASS")


def test_dead_setup_links_carry_link_status():
    with _Env() as client:
        raw = _setup_link()
        assert _setup(client, raw, GOOD_PASSWORD).status_code == 200
        used = _setup(client, raw, "another long passphrase")
        assert used.status_code == 400 and used.get_json()["link_status"] == "used"
        forged = _setup(client, "y" * 43, GOOD_PASSWORD)
        assert forged.status_code == 400 and forged.get_json()["link_status"] == "invalid"
        empty = _setup(client, "", GOOD_PASSWORD)
        assert empty.status_code == 400 and empty.get_json()["link_status"] == "invalid"
    print("✓ test_dead_setup_links_carry_link_status: PASS")


def test_setup_page_decides_a_dead_link_from_link_status_not_the_message():
    js = open(os.path.join(FRONTEND, "team-setup.js")).read()
    html = open(os.path.join(FRONTEND, "team-setup.html")).read()
    assert "includes('8 characters')" not in js, "must not guess deadness from the error text"
    assert "err.tokenDead = Boolean(data.link_status);" in js
    assert "password.length < 8" not in js, "client rules must match the server's (10+, see password_rules.py)"
    assert "Auth.passwordProblems(password" in js
    assert "at least 8 characters" not in html and 'minlength="8"' not in html
    assert 'minlength="10"' in html
    print("✓ test_setup_page_decides_a_dead_link_from_link_status_not_the_message: PASS")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} team setup link tests passed.")
