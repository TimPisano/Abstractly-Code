"""
Tests for the /app access gate: /config (LOCAL_DEV_MODE bypass) and
/waitlist/check (approved-email lookup used by
frontend/app/access-gate.js).

Uses Flask's in-process test_client(), same pattern as
test_waitlist_email.py. LOCAL_DEV_MODE is read once at import time from
the environment (see api.py) -- patched directly on the app.api module
per test rather than via the environment, since re-patching os.environ
after import wouldn't change the already-evaluated module-level constant.
"""

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database

# This file exercises real /waitlist POST routes through
# app.test_client(), unlike test_waitlist_email.py, which mocks
# app.email_service everywhere. Popped here (after app.api's own
# load_dotenv() has already run, so this can't be re-populated from
# backend/.env) so email_service._send()'s existing "not configured"
# fail-safe applies regardless of what's actually set in the real
# environment: every send_* call becomes a safe no-op instead of a real
# Gmail send. Protects this file even when run directly
# (`python3 test_access_gate.py`), not just via run_all_tests.py's own
# env sanitizing. Added after a real incident where this file's
# "secret1@example.com" / "secret2@example.com" / "MixedCase@Example.com"
# test signups sent real emails to the real ADMIN_EMAIL inbox -- see
# DECISIONS.md.
os.environ.pop("EMAIL_USER", None)
os.environ.pop("EMAIL_APP_PASSWORD", None)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _login_as_admin(client):
    """GET /waitlist and POST /waitlist/<id>/approve now require an admin session (see app/auth.py's require_admin) -- set directly via session_transaction() rather than driving a real login POST through bcrypt for every test that needs one."""
    with client.session_transaction() as sess:
        sess["admin_authenticated"] = True
        sess["admin_email"] = "timmypisano24@gmail.com"


def test_config_reports_local_dev_mode_off_by_default():
    with mock.patch("app.api.LOCAL_DEV_MODE", False):
        resp = app.test_client().get("/config")
        assert resp.status_code == 200
        assert resp.get_json() == {"local_dev_mode": False}
    print("✓ test_config_reports_local_dev_mode_off_by_default: PASS")


def test_config_reports_local_dev_mode_on_when_set():
    with mock.patch("app.api.LOCAL_DEV_MODE", True):
        resp = app.test_client().get("/config")
        assert resp.status_code == 200
        assert resp.get_json() == {"local_dev_mode": True}
    print("✓ test_config_reports_local_dev_mode_on_when_set: PASS")


def test_check_access_for_unknown_email():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/waitlist/check", json={"email": "nobody@example.com"})
        assert resp.status_code == 200
        assert resp.get_json() == {"approved": False, "found": False}
    finally:
        os.unlink(db_path)
    print("✓ test_check_access_for_unknown_email: PASS")


def test_check_access_for_pending_email():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        client.post("/waitlist", json={"email": "pending@example.com"})

        resp = client.post("/waitlist/check", json={"email": "pending@example.com"})
        assert resp.status_code == 200
        assert resp.get_json() == {"approved": False, "found": True}
    finally:
        os.unlink(db_path)
    print("✓ test_check_access_for_pending_email: PASS")


def test_check_access_for_approved_email():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        client.post("/waitlist", json={"email": "approved@example.com"})
        signup_id = database.get_all_waitlist_signups()[0]["id"]
        _login_as_admin(client)
        client.post(f"/waitlist/{signup_id}/approve")

        resp = client.post("/waitlist/check", json={"email": "approved@example.com"})
        assert resp.status_code == 200
        assert resp.get_json() == {"approved": True, "found": True}
    finally:
        os.unlink(db_path)
    print("✓ test_check_access_for_approved_email: PASS")


def test_check_access_is_case_insensitive():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        client.post("/waitlist", json={"email": "MixedCase@Example.com"})
        signup_id = database.get_all_waitlist_signups()[0]["id"]
        _login_as_admin(client)
        client.post(f"/waitlist/{signup_id}/approve")

        resp = client.post("/waitlist/check", json={"email": "mixedcase@example.com"})
        assert resp.status_code == 200
        assert resp.get_json()["approved"] is True
    finally:
        os.unlink(db_path)
    print("✓ test_check_access_is_case_insensitive: PASS")


def test_check_access_rejects_invalid_email():
    db_path = _fresh_temp_db()
    try:
        resp = app.test_client().post("/waitlist/check", json={"email": "not-an-email"})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_check_access_rejects_invalid_email: PASS")


def test_check_access_never_leaks_full_signup_list():
    """The whole point of this endpoint's narrow response shape: it must
    never include other people's emails or any field beyond
    approved/found for the one email asked about, unlike GET /waitlist."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        client.post("/waitlist", json={"email": "secret1@example.com"})
        client.post("/waitlist", json={"email": "secret2@example.com"})

        resp = client.post("/waitlist/check", json={"email": "secret1@example.com"})
        body = resp.get_json()
        assert set(body.keys()) == {"approved", "found"}
        assert "secret2@example.com" not in resp.get_data(as_text=True)
    finally:
        os.unlink(db_path)
    print("✓ test_check_access_never_leaks_full_signup_list: PASS")


def test_waitlist_signup_and_admin_approval_flow_unaffected():
    """The pre-existing waitlist signup + admin approval flow (used by the
    landing page and the admin dashboard) must work exactly as before --
    this feature only adds a new read-only lookup, it doesn't touch
    insert_waitlist_signup / get_all_waitlist_signups /
    approve_waitlist_signup or the waitlist_signups table's schema."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/waitlist", json={"email": "regular@example.com"})
        assert resp.status_code == 201
        _login_as_admin(client)

        listing = client.get("/waitlist").get_json()
        assert any(s["email"] == "regular@example.com" and s["status"] == "pending" for s in listing)

        signup_id = next(s["id"] for s in listing if s["email"] == "regular@example.com")
        approve_resp = client.post(f"/waitlist/{signup_id}/approve")
        assert approve_resp.status_code == 200
        assert approve_resp.get_json()["status"] == "approved"

        listing_after = client.get("/waitlist").get_json()
        assert any(s["email"] == "regular@example.com" and s["status"] == "approved" for s in listing_after)
    finally:
        os.unlink(db_path)
    print("✓ test_waitlist_signup_and_admin_approval_flow_unaffected: PASS")


if __name__ == "__main__":
    test_config_reports_local_dev_mode_off_by_default()
    test_config_reports_local_dev_mode_on_when_set()
    test_check_access_for_unknown_email()
    test_check_access_for_pending_email()
    test_check_access_for_approved_email()
    test_check_access_is_case_insensitive()
    test_check_access_rejects_invalid_email()
    test_check_access_never_leaks_full_signup_list()
    test_waitlist_signup_and_admin_approval_flow_unaffected()
    print("\nAll access-gate tests passed.")
