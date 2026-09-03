"""
Unit tests (Flask test client, no server) for the Phase 1 security
hardening: the CSRF origin check, response security headers, and
login / reset-password rate limiting. Also covers the RateLimiter
primitive in app/security.py.
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app, ALLOWED_ORIGINS, _reset_login_rate_limit_for_tests, _reset_reset_password_rate_limit_for_tests
from app import database
from app.auth import hash_password
from app.security import RateLimiter

GOOD_ORIGIN = ALLOWED_ORIGINS[0]
BAD_ORIGIN = "https://evil.example.com"


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    _reset_login_rate_limit_for_tests()
    _reset_reset_password_rate_limit_for_tests()
    return tmp.name


# ----------------------------------------------------------------------
# CSRF origin check
# ----------------------------------------------------------------------

def test_state_changing_request_with_disallowed_origin_is_blocked():
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        r = c.post("/auth/login", json={"email": "x@y.com", "password": "z"}, headers={"Origin": BAD_ORIGIN})
        assert r.status_code == 403
        assert "Cross-origin" in r.get_json()["error"]
    finally:
        os.unlink(db)
    print("✓ test_state_changing_request_with_disallowed_origin_is_blocked: PASS")


def test_multipart_upload_with_disallowed_origin_is_blocked():
    """The core reason this exists -- multipart POST gets no CORS preflight."""
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        r = c.post("/extract", data={"file": (__import__("io").BytesIO(b"x"), "x.pdf")},
                   content_type="multipart/form-data", headers={"Origin": BAD_ORIGIN})
        assert r.status_code == 403
    finally:
        os.unlink(db)
    print("✓ test_multipart_upload_with_disallowed_origin_is_blocked: PASS")


def test_state_changing_request_with_allowed_origin_passes_the_csrf_check():
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        r = c.post("/auth/login", json={"email": "x@y.com", "password": "z"}, headers={"Origin": GOOD_ORIGIN})
        assert r.status_code == 401, "gets past CSRF to the real handler (bad creds -> 401, not 403)"
    finally:
        os.unlink(db)
    print("✓ test_state_changing_request_with_allowed_origin_passes_the_csrf_check: PASS")


def test_request_with_no_origin_is_not_treated_as_csrf():
    """A non-browser client (curl, script) sends no Origin and carries no ambient cookie -- not a CSRF vector."""
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        r = c.post("/auth/login", json={"email": "x@y.com", "password": "z"})
        assert r.status_code == 401
    finally:
        os.unlink(db)
    print("✓ test_request_with_no_origin_is_not_treated_as_csrf: PASS")


def test_disallowed_referer_also_blocks_when_no_origin_header():
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        r = c.post("/auth/login", json={"email": "x@y.com", "password": "z"},
                   headers={"Referer": "https://evil.example.com/attack.html"})
        assert r.status_code == 403
    finally:
        os.unlink(db)
    print("✓ test_disallowed_referer_also_blocks_when_no_origin_header: PASS")


def test_get_requests_are_never_csrf_blocked():
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        r = c.get("/auth/session", headers={"Origin": BAD_ORIGIN})
        assert r.status_code == 200
    finally:
        os.unlink(db)
    print("✓ test_get_requests_are_never_csrf_blocked: PASS")


# ----------------------------------------------------------------------
# Security headers
# ----------------------------------------------------------------------

def test_standard_security_headers_present_on_every_response():
    db = _fresh_temp_db()
    try:
        r = app.test_client().get("/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "Referrer-Policy" in r.headers
        assert "Content-Security-Policy" in r.headers
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    finally:
        os.unlink(db)
    print("✓ test_standard_security_headers_present_on_every_response: PASS")


def test_hsts_only_on_https_requests():
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        assert "Strict-Transport-Security" not in c.get("/health").headers
        r = c.get("/health", headers={"X-Forwarded-Proto": "https"})
        assert "max-age=" in r.headers.get("Strict-Transport-Security", "")
    finally:
        os.unlink(db)
    print("✓ test_hsts_only_on_https_requests: PASS")


def test_auth_responses_are_not_cacheable():
    db = _fresh_temp_db()
    try:
        r = app.test_client().get("/auth/session")
        assert r.headers.get("Cache-Control") == "no-store"
    finally:
        os.unlink(db)
    print("✓ test_auth_responses_are_not_cacheable: PASS")


# ----------------------------------------------------------------------
# Login / reset-password rate limiting
# ----------------------------------------------------------------------

def test_login_is_rate_limited_per_ip():
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        hdrs = {"Origin": GOOD_ORIGIN}
        env = {"REMOTE_ADDR": "203.0.113.9"}
        for i in range(20):
            r = c.post("/auth/login", json={"email": f"u{i}@y.com", "password": "z"}, headers=hdrs, environ_base=env)
            assert r.status_code == 401, f"attempt {i} should be a normal auth failure"
        r = c.post("/auth/login", json={"email": "u99@y.com", "password": "z"}, headers=hdrs, environ_base=env)
        assert r.status_code == 429, "the attempt past the per-IP cap must be throttled"
    finally:
        os.unlink(db)
    print("✓ test_login_is_rate_limited_per_ip: PASS")


def test_login_rate_limit_is_per_email_and_identical_for_unknown_accounts():
    db = _fresh_temp_db()
    try:
        database.create_user("real@example.com", "Real", hash_password("correct-horse"), role="analyst")
        c = app.test_client()
        hdrs = {"Origin": GOOD_ORIGIN}
        # hammer one email from rotating IPs -> per-email cap (7/15min) still bites
        for i in range(7):
            r = c.post("/auth/login", json={"email": "real@example.com", "password": "wrong"},
                       headers=hdrs, environ_base={"REMOTE_ADDR": f"198.51.100.{i}"})
            assert r.status_code == 401
        r = c.post("/auth/login", json={"email": "real@example.com", "password": "wrong"},
                   headers=hdrs, environ_base={"REMOTE_ADDR": "198.51.100.200"})
        assert r.status_code == 429

        # An unknown email must hit the same 429 at the same point -- no existence oracle.
        _reset_login_rate_limit_for_tests()
        for i in range(7):
            c.post("/auth/login", json={"email": "ghost@example.com", "password": "wrong"},
                   headers=hdrs, environ_base={"REMOTE_ADDR": f"198.51.100.{i}"})
        r = c.post("/auth/login", json={"email": "ghost@example.com", "password": "wrong"},
                   headers=hdrs, environ_base={"REMOTE_ADDR": "198.51.100.201"})
        assert r.status_code == 429
    finally:
        os.unlink(db)
    print("✓ test_login_rate_limit_is_per_email_and_identical_for_unknown_accounts: PASS")


def test_reset_password_is_rate_limited():
    db = _fresh_temp_db()
    try:
        c = app.test_client()
        hdrs = {"Origin": GOOD_ORIGIN}
        env = {"REMOTE_ADDR": "203.0.113.50"}
        for i in range(15):
            r = c.post("/auth/reset-password", json={"token": "bad", "new_password": "12345678"}, headers=hdrs, environ_base=env)
            assert r.status_code == 400
        r = c.post("/auth/reset-password", json={"token": "bad", "new_password": "12345678"}, headers=hdrs, environ_base=env)
        assert r.status_code == 429
    finally:
        os.unlink(db)
    print("✓ test_reset_password_is_rate_limited: PASS")


# ----------------------------------------------------------------------
# RateLimiter primitive
# ----------------------------------------------------------------------

def test_rate_limiter_windows_and_multi_key():
    rl = RateLimiter(max_hits=3, window_seconds=1000)
    assert rl.check(["a"]) is False
    assert rl.check(["a"]) is False
    assert rl.check(["a"]) is False
    assert rl.check(["a"]) is True, "4th hit on key 'a' is over the cap"
    assert rl.check(["b"]) is False, "independent key"
    # multi-key: limited if ANY key is saturated
    assert rl.check(["b", "a"]) is True
    print("✓ test_rate_limiter_windows_and_multi_key: PASS")


def test_rate_limiter_prunes_expired_keys():
    rl = RateLimiter(max_hits=1, window_seconds=0)  # everything immediately expired
    rl.check(["x"])
    rl.check(["y"])
    assert rl.check(["z"]) is False
    assert len(rl._state) <= 1, "expired keys are pruned, dict doesn't grow unbounded"
    print("✓ test_rate_limiter_prunes_expired_keys: PASS")


if __name__ == "__main__":
    test_state_changing_request_with_disallowed_origin_is_blocked()
    test_multipart_upload_with_disallowed_origin_is_blocked()
    test_state_changing_request_with_allowed_origin_passes_the_csrf_check()
    test_request_with_no_origin_is_not_treated_as_csrf()
    test_disallowed_referer_also_blocks_when_no_origin_header()
    test_get_requests_are_never_csrf_blocked()
    test_standard_security_headers_present_on_every_response()
    test_hsts_only_on_https_requests()
    test_auth_responses_are_not_cacheable()
    test_login_is_rate_limited_per_ip()
    test_login_rate_limit_is_per_email_and_identical_for_unknown_accounts()
    test_reset_password_is_rate_limited()
    test_rate_limiter_windows_and_multi_key()
    test_rate_limiter_prunes_expired_keys()
    print("\nAll security middleware tests passed.")
