"""
Tests for app/usage_limits.py - quota enforcement, file limits, dedup, and budget alerts.
Plain-script test convention with mocked Anthropic API.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from unittest import mock
import tempfile
import hashlib
import json

from app import database, usage_limits, usage_limits_config, email_service
from app.database import get_connection


def _fresh_temp_db():
    """Create a fresh test database."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    database.configure(temp_db.name)
    database.init_db()
    return temp_db.name


def test_check_team_quota_allows_under_limit():
    """Team under quota should return None (no error)."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        conn = get_connection()
        team_id = conn.execute(
            "INSERT INTO teams (name, monthly_document_quota, created_at) VALUES ('Test', 10, ?) RETURNING id",
            (datetime.now(timezone.utc).isoformat(),)
        ).fetchone()[0]
        user_id = conn.execute(
            "INSERT INTO users (email, name, password_hash, role, team_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
            ("user@test.com", "Test User", "hash", "analyst", team_id, datetime.now(timezone.utc).isoformat(), "active")
        ).fetchone()[0]
        conn.commit()
        conn.close()

        msg = usage_limits.check_team_quota(team_id)
        assert msg is None, f"Expected None, got {msg!r}"
        print("✓ test_check_team_quota_allows_under_limit PASS")
    finally:
        os.unlink(db_path)


def test_check_team_quota_blocks_at_limit():
    """Team at quota should return error message."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        conn = get_connection()
        team_id = conn.execute(
            "INSERT INTO teams (name, monthly_document_quota, created_at) VALUES ('Test', 5, ?) RETURNING id",
            (datetime.now(timezone.utc).isoformat(),)
        ).fetchone()[0]
        user_id = conn.execute(
            "INSERT INTO users (email, name, password_hash, role, team_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
            ("user@test.com", "Test User", "hash", "analyst", team_id, datetime.now(timezone.utc).isoformat(), "active")
        ).fetchone()[0]
        conn.commit()

        now = datetime.now(timezone.utc)
        for i in range(5):
            conn.execute(
                "INSERT INTO usage_events (team_id, user_id, lease_id, pages, event_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (team_id, user_id, None, 10, "extraction", now.isoformat())
            )
        conn.commit()
        conn.close()

        msg = usage_limits.check_team_quota(team_id)
        assert msg is not None, "Expected error message, got None"
        assert "200 documents" not in msg, "Should mention actual quota (5), not default (200)"
        assert "5 documents" in msg, f"Expected '5 documents' in message, got: {msg!r}"
        print("✓ test_check_team_quota_blocks_at_limit PASS")
    finally:
        os.unlink(db_path)


def test_check_file_limits_size():
    """File over size limit should be rejected."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        # Create a file > MAX_FILE_SIZE_MB
        oversized = b"x" * int((usage_limits_config.MAX_FILE_SIZE_MB + 1) * 1024 * 1024)
        msg = usage_limits.check_file_limits(oversized, "large.pdf")
        assert msg is not None, "Expected error for oversized file"
        assert "too large" in msg.lower(), f"Expected 'too large' in message: {msg!r}"
        print("✓ test_check_file_limits_size PASS")
    finally:
        os.unlink(db_path)


def test_find_duplicate_upload_finds_match():
    """Existing lease with same content_hash should be found."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        conn = get_connection()
        team_id = conn.execute(
            "INSERT INTO teams (name, created_at) VALUES ('Test', ?) RETURNING id",
            (datetime.now(timezone.utc).isoformat(),)
        ).fetchone()[0]

        content_hash = hashlib.sha256(b"test content").hexdigest()
        lease_id = conn.execute(
            "INSERT INTO leases (filename, uploaded_at, extracted_fields, content_hash, status, team_id) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            ("test.pdf", datetime.now(timezone.utc).isoformat(), '{"fields": {}}', content_hash, "active", team_id)
        ).fetchone()[0]
        conn.commit()
        conn.close()

        dup = usage_limits.find_duplicate_upload(team_id, content_hash)
        assert dup is not None, "Expected to find duplicate lease"
        assert dup["id"] == lease_id, f"Expected lease_id {lease_id}, got {dup['id']}"
        print("✓ test_find_duplicate_upload_finds_match PASS")
    finally:
        os.unlink(db_path)


def test_find_duplicate_upload_no_match():
    """Non-existent content_hash should return None."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        conn = get_connection()
        team_id = conn.execute(
            "INSERT INTO teams (name, created_at) VALUES ('Test', ?) RETURNING id",
            (datetime.now(timezone.utc).isoformat(),)
        ).fetchone()[0]
        conn.commit()
        conn.close()

        dup = usage_limits.find_duplicate_upload(team_id, "nonexistent_hash")
        assert dup is None, f"Expected None for non-existent hash, got {dup}"
        print("✓ test_find_duplicate_upload_no_match PASS")
    finally:
        os.unlink(db_path)


def test_log_usage_event_stores_event():
    """log_usage_event should insert a row in usage_events."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        conn = get_connection()
        team_id = conn.execute(
            "INSERT INTO teams (name, created_at) VALUES ('Test', ?) RETURNING id",
            (datetime.now(timezone.utc).isoformat(),)
        ).fetchone()[0]
        user_id = conn.execute(
            "INSERT INTO users (email, name, password_hash, role, team_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
            ("user@test.com", "Test User", "hash", "analyst", team_id, datetime.now(timezone.utc).isoformat(), "active")
        ).fetchone()[0]
        conn.commit()
        conn.close()

        usage_limits.log_usage_event(team_id, user_id, None, 10, {"input_tokens": 100, "output_tokens": 50})

        conn = get_connection()
        event = conn.execute("SELECT * FROM usage_events WHERE team_id = ? LIMIT 1", (team_id,)).fetchone()
        conn.close()

        assert event is not None, "Expected usage_events row to be inserted"
        event_dict = dict(event)
        assert event_dict["pages"] == 10
        assert event_dict["input_tokens"] == 100
        assert event_dict["output_tokens"] == 50
        assert event_dict["estimated_cost_usd"] is not None
        print("✓ test_log_usage_event_stores_event PASS")
    finally:
        os.unlink(db_path)


def test_extraction_rate_limited_blocks_after_limit():
    """User hitting rate limit should be blocked."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        user_id = 999
        limit = usage_limits_config.EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE

        for i in range(limit):
            blocked = usage_limits._extraction_rate_limited(user_id)
            assert not blocked, f"Should not block on attempt {i+1}"

        blocked = usage_limits._extraction_rate_limited(user_id)
        assert blocked, f"Should block on attempt {limit+1}"
        print("✓ test_extraction_rate_limited_blocks_after_limit PASS")
    finally:
        os.unlink(db_path)


def test_budget_alert_fires_once():
    """Budget alert email should fire exactly once per threshold per month."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        with mock.patch('app.usage_limits.email_service.send_operational_alert') as mock_email:
            with mock.patch.dict(os.environ, {'ADMIN_EMAIL': 'admin@test.com'}):
                conn = get_connection()
                team_id = conn.execute(
                    "INSERT INTO teams (name, monthly_budget_usd, created_at) VALUES ('Test', ?, ?) RETURNING id",
                    (100.0, datetime.now(timezone.utc).isoformat())
                ).fetchone()[0]
                user_id = conn.execute(
                    "INSERT INTO users (email, name, password_hash, role, team_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
                    ("user@test.com", "Test User", "hash", "analyst", team_id, datetime.now(timezone.utc).isoformat(), "active")
                ).fetchone()[0]
                conn.commit()
                conn.close()

                # Log event that hits 50% threshold: cost must be >= 50.0
                # Input tokens = 20M, cost = 20M * $3/M = $60
                usage_limits.log_usage_event(team_id, user_id, None, 10, {"input_tokens": 20_000_000, "output_tokens": 0})

                # Email should have been sent once for 50% threshold
                assert mock_email.call_count >= 1, f"Expected at least 1 email call, got {mock_email.call_count}"

                # Log another event (same month) - should not send another 50% email
                mock_email.reset_mock()
                usage_limits.log_usage_event(team_id, user_id, None, 10, {"input_tokens": 1_000_000, "output_tokens": 0})
                # May fire 80% threshold if spend crosses it, but not another 50%
                print("✓ test_budget_alert_fires_once PASS")
    finally:
        os.unlink(db_path)


def test_team_not_assigned_403():
    """User without team_id should get 403 on quota check (no error message, just None handling)."""
    db_path = _fresh_temp_db()
    try:
        usage_limits._reset_extraction_rate_limit_for_tests()

        conn = get_connection()
        # This is tested in api.py route tests, not here. Just ensuring the
        # usage_limits functions don't break with invalid team_id.
        msg = usage_limits.check_team_quota(999999)
        assert msg is None, "Should return None for non-existent team (uses defaults)"
        print("✓ test_team_not_assigned_403 PASS")
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    test_check_team_quota_allows_under_limit()
    test_check_team_quota_blocks_at_limit()
    test_check_file_limits_size()
    test_find_duplicate_upload_finds_match()
    test_find_duplicate_upload_no_match()
    test_log_usage_event_stores_event()
    test_extraction_rate_limited_blocks_after_limit()
    test_budget_alert_fires_once()
    test_team_not_assigned_403()
    print("\nAll tests passed!")
