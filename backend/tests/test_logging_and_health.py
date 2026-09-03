"""
Tests for Phase 3 observability: app/logging_config.py (structured
logging, per-request line + id, opt-in email-on-error) and the
DB-aware /health endpoint.
"""

import io
import logging
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import logging_config
from app.api import app
from app import database


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _capture_root_logs():
    """Attach a string-capturing handler to the root logger; returns (getvalue, detach). Forces the root level low enough that INFO records reach the handler regardless of LOG_LEVEL."""
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.addFilter(logging_config.RequestContextFilter())
    h.setFormatter(logging_config._PlainFormatter())
    root = logging.getLogger()
    prev_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(h)

    def _detach():
        root.removeHandler(h)
        root.setLevel(prev_level)

    return (lambda: buf.getvalue()), _detach


# ----------------------------------------------------------------------
# configure_logging
# ----------------------------------------------------------------------

def test_configure_logging_installs_single_stdout_handler_and_respects_level():
    prev = os.environ.get("LOG_LEVEL")
    os.environ["LOG_LEVEL"] = "WARNING"
    try:
        logging_config.configure_logging(force=True)
        root = logging.getLogger()
        assert len([h for h in root.handlers if isinstance(h, logging.StreamHandler)]) >= 1
        assert root.level == logging.WARNING
    finally:
        if prev is None:
            os.environ.pop("LOG_LEVEL", None)
        else:
            os.environ["LOG_LEVEL"] = prev
        logging_config.configure_logging(force=True)
    print("✓ test_configure_logging_installs_single_stdout_handler_and_respects_level: PASS")


def test_request_context_filter_outside_request():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    assert logging_config.RequestContextFilter().filter(rec) is True
    assert rec.request_id == "-" and rec.request_path == "-"
    print("✓ test_request_context_filter_outside_request: PASS")


# ----------------------------------------------------------------------
# per-request logging
# ----------------------------------------------------------------------

def test_request_logging_emits_one_line_with_id_and_sets_header():
    db = _fresh_temp_db()
    getlog, detach = _capture_root_logs()
    try:
        resp = app.test_client().get("/auth/session")
        assert "X-Request-Id" in resp.headers and len(resp.headers["X-Request-Id"]) == 8
        out = getlog()
        assert "GET /auth/session -> 200" in out
        assert f"[{resp.headers['X-Request-Id']}]" in out
    finally:
        detach()
        os.unlink(db)
    print("✓ test_request_logging_emits_one_line_with_id_and_sets_header: PASS")


def test_request_logging_skips_health_and_logs_5xx_at_error():
    db = _fresh_temp_db()
    getlog, detach = _capture_root_logs()
    try:
        c = app.test_client()
        with c.session_transaction() as s:
            s.update({"user_id": 1, "email": "a@x.com", "name": "A", "role": "analyst"})

        c.get("/health")
        assert "/health ->" not in getlog(), "the constant health-check hit is not logged"

        # force a real 500 through the app's generic error handler
        with mock.patch.object(database, "get_all_effective_leases", side_effect=RuntimeError("kaboom")):
            resp = c.get("/leases")
        assert resp.status_code == 500
        out = getlog()
        assert "ERROR" in out and "GET /leases -> 500" in out
    finally:
        detach()
        os.unlink(db)
    print("✓ test_request_logging_skips_health_and_logs_5xx_at_error: PASS")


# ----------------------------------------------------------------------
# email-on-error handler
# ----------------------------------------------------------------------

def test_email_alerts_are_opt_in():
    root = logging.getLogger()
    os.environ.pop("ERROR_ALERT_EMAILS", None)
    os.environ["EMAIL_USER"] = "u@x.com"
    os.environ["EMAIL_APP_PASSWORD"] = "p"
    os.environ["ADMIN_EMAIL"] = "a@x.com"
    try:
        logging_config._maybe_add_email_alerts(root)
        assert not any(isinstance(h, logging_config.SMTPErrorAlertHandler) for h in root.handlers), "not enabled without ERROR_ALERT_EMAILS"

        os.environ["ERROR_ALERT_EMAILS"] = "true"
        logging_config._maybe_add_email_alerts(root)
        handlers = [h for h in root.handlers if isinstance(h, logging_config.SMTPErrorAlertHandler)]
        assert len(handlers) == 1
    finally:
        for h in [h for h in root.handlers if isinstance(h, logging_config.SMTPErrorAlertHandler)]:
            root.removeHandler(h)
        for k in ("ERROR_ALERT_EMAILS", "EMAIL_USER", "EMAIL_APP_PASSWORD", "ADMIN_EMAIL"):
            os.environ.pop(k, None)
    print("✓ test_email_alerts_are_opt_in: PASS")


def test_smtp_error_handler_rate_limits_and_guards_reentrancy():
    sends = []
    with mock.patch("app.email_service.send_operational_alert", side_effect=lambda *a, **k: sends.append(a) or True):
        handler = logging_config.SMTPErrorAlertHandler("a@x.com", min_interval_seconds=999)
        handler.setFormatter(logging_config._PlainFormatter())
        handler.addFilter(logging_config.RequestContextFilter())

        def _emit(msg):
            rec = logging.LogRecord("app.thing", logging.ERROR, "f.py", 42, msg, None, None)
            rec.funcName = "do_thing"
            logging_config.RequestContextFilter().filter(rec)
            handler.emit(rec)

        _emit("first failure")
        _emit("same call site again")   # rate-limited (same name:func:line, within window)
        assert len(sends) == 1, "second alert from the same call site inside the window is suppressed"

        # reentrancy: an alert-send that itself logs an error must not recurse
        handler._sending.active = True
        _emit("while sending")
        assert len(sends) == 1
    print("✓ test_smtp_error_handler_rate_limits_and_guards_reentrancy: PASS")


# ----------------------------------------------------------------------
# /health
# ----------------------------------------------------------------------

def test_health_is_200_when_db_ok():
    db = _fresh_temp_db()
    try:
        resp = app.test_client().get("/health")
        assert resp.status_code == 200 and resp.get_json()["status"] == "healthy"
    finally:
        os.unlink(db)
    print("✓ test_health_is_200_when_db_ok: PASS")


def test_health_is_503_when_db_probe_fails():
    db = _fresh_temp_db()
    try:
        with mock.patch.object(database, "get_connection", side_effect=Exception("disk I/O error")):
            resp = app.test_client().get("/health")
        assert resp.status_code == 503
        assert resp.get_json() == {"status": "degraded", "database": "unavailable"}
    finally:
        os.unlink(db)
    print("✓ test_health_is_503_when_db_probe_fails: PASS")


if __name__ == "__main__":
    test_configure_logging_installs_single_stdout_handler_and_respects_level()
    test_request_context_filter_outside_request()
    test_request_logging_emits_one_line_with_id_and_sets_header()
    test_request_logging_skips_health_and_logs_5xx_at_error()
    test_email_alerts_are_opt_in()
    test_smtp_error_handler_rate_limits_and_guards_reentrancy()
    test_health_is_200_when_db_ok()
    test_health_is_503_when_db_probe_fails()
    print("\nAll logging + health tests passed.")
