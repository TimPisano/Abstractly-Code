"""
Tests for the first-party pageview analytics added to the public
marketing site: POST /analytics/pageview (public ingestion, rate
limited) and GET /owner/analytics/summary (owner-only reporting).

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_waitlist_email.py / test_owner_console.py.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app, _pageview_rate_limiter
from app import database


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _client_as_owner():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["email"] = "owner@example.com"
        sess["name"] = "Test Owner"
        sess["role"] = "admin"
        sess["is_owner"] = True
    return client


def test_pageview_stores_a_valid_beacon():
    db_path = _fresh_temp_db()
    _pageview_rate_limiter.reset()
    try:
        client = app.test_client()
        resp = client.post("/analytics/pageview", json={"path": "/", "referrer": "https://google.com/search", "session_id": "abc123"})
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json() == {"status": "ok"}

        rows = database.get_pageview_summary()
        assert rows["total_pageviews"] == 1
        assert rows["unique_sessions"] == 1
        assert rows["top_paths"] == [{"path": "/", "count": 1}]
        assert rows["top_referrers"] == [{"referrer": "google.com", "count": 1}]
    finally:
        os.unlink(db_path)
    print("✓ test_pageview_stores_a_valid_beacon: PASS")


def test_pageview_without_referrer_or_session_id_still_stores():
    db_path = _fresh_temp_db()
    _pageview_rate_limiter.reset()
    try:
        client = app.test_client()
        resp = client.post("/analytics/pageview", json={"path": "/pricing.html"})
        assert resp.status_code == 201
        summary = database.get_pageview_summary()
        assert summary["total_pageviews"] == 1
        assert summary["unique_sessions"] == 0  # no session_id -- excluded from the session-based funnel/count
        assert summary["top_referrers"] == [{"referrer": "direct", "count": 1}]
    finally:
        os.unlink(db_path)
    print("✓ test_pageview_without_referrer_or_session_id_still_stores: PASS")


def test_pageview_rejects_a_path_that_is_not_actually_a_path():
    db_path = _fresh_temp_db()
    _pageview_rate_limiter.reset()
    try:
        client = app.test_client()
        for bad_path in ["not-a-path", "", "http://evil.example.com/"]:
            resp = client.post("/analytics/pageview", json={"path": bad_path})
            assert resp.status_code == 400, f"{bad_path!r} should be rejected, got {resp.status_code}"
        assert database.get_pageview_summary()["total_pageviews"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_pageview_rejects_a_path_that_is_not_actually_a_path: PASS")


def test_pageview_rate_limit_caps_repeated_requests_from_one_ip():
    db_path = _fresh_temp_db()
    _pageview_rate_limiter.reset()
    try:
        client = app.test_client()
        for _ in range(60):
            resp = client.post("/analytics/pageview", json={"path": "/"})
            assert resp.status_code == 201
        limited = client.post("/analytics/pageview", json={"path": "/"})
        assert limited.status_code == 429
    finally:
        _pageview_rate_limiter.reset()
        os.unlink(db_path)
    print("✓ test_pageview_rate_limit_caps_repeated_requests_from_one_ip: PASS")


def test_funnel_counts_by_distinct_session_not_raw_pageviews():
    db_path = _fresh_temp_db()
    _pageview_rate_limiter.reset()
    try:
        client = app.test_client()
        # Session A: landed, viewed pricing twice (should count once), converted.
        client.post("/analytics/pageview", json={"path": "/", "session_id": "session-a"})
        client.post("/analytics/pageview", json={"path": "/pricing.html", "session_id": "session-a"})
        client.post("/analytics/pageview", json={"path": "/pricing.html", "session_id": "session-a"})
        client.post("/analytics/pageview", json={"path": "/__event/waitlist_submitted", "session_id": "session-a"})
        # Session B: landed only, never converted.
        client.post("/analytics/pageview", json={"path": "/", "session_id": "session-b"})

        summary = database.get_pageview_summary()
        assert summary["funnel"] == {"landing": 2, "pricing": 1, "waitlist_submitted": 1}
        assert summary["unique_sessions"] == 2
        assert summary["total_pageviews"] == 5
    finally:
        os.unlink(db_path)
    print("✓ test_funnel_counts_by_distinct_session_not_raw_pageviews: PASS")


def test_owner_analytics_summary_requires_owner_session():
    db_path = _fresh_temp_db()
    _pageview_rate_limiter.reset()
    try:
        client = app.test_client()
        client.post("/analytics/pageview", json={"path": "/", "session_id": "s1"})

        anon = app.test_client()
        assert anon.get("/owner/analytics/summary").status_code == 401

        owner_client = _client_as_owner()
        resp = owner_client.get("/owner/analytics/summary")
        assert resp.status_code == 200
        assert resp.get_json()["total_pageviews"] == 1
    finally:
        os.unlink(db_path)
    print("✓ test_owner_analytics_summary_requires_owner_session: PASS")


if __name__ == "__main__":
    test_pageview_stores_a_valid_beacon()
    test_pageview_without_referrer_or_session_id_still_stores()
    test_pageview_rejects_a_path_that_is_not_actually_a_path()
    test_pageview_rate_limit_caps_repeated_requests_from_one_ip()
    test_funnel_counts_by_distinct_session_not_raw_pageviews()
    test_owner_analytics_summary_requires_owner_session()
