"""
One place that configures logging for the whole app. Called once at
process start (app/api.py import time, so it covers gunicorn workers
and `python run.py` alike).

What it sets up:
  - a single stdout StreamHandler on the root logger with a consistent
    format (Render, and every other modern host, captures stdout as the
    log stream). Level from LOG_LEVEL (default INFO). LOG_FORMAT=json
    switches to one-JSON-object-per-line for log processors.
  - a request-context filter: every line emitted during a request also
    carries the method+path and a short per-request id, so lines from
    concurrent requests can be told apart.
  - quieter third-party loggers (werkzeug's per-request line -- we log
    our own; anthropic/httpx connection chatter at INFO).
  - optionally, an email-on-error handler (see email_service): when
    SMTP + ADMIN_EMAIL are configured, an ERROR/CRITICAL log line also
    sends a rate-limited alert email, so a production break is
    something the operator finds out about rather than a customer.

Import side effects are avoided -- nothing here runs until
configure_logging() is called.
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Optional

try:
    from flask import has_request_context, request, g
except Exception:  # pragma: no cover - flask is always present in this app
    has_request_context = lambda: False  # noqa: E731
    request = None
    g = None

_configured = False
_lock = threading.Lock()


class RequestContextFilter(logging.Filter):
    """Adds `request_id` and `request_path` to every record -- the real
    values inside a Flask request, placeholders otherwise."""

    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            rid = getattr(g, "request_id", None) if g is not None else None
            record.request_id = rid or "-"
            record.request_path = f"{request.method} {request.path}" if request is not None else "-"
        else:
            record.request_id = "-"
            record.request_path = "-"
        return True


class _PlainFormatter(logging.Formatter):
    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record)} {record.levelname:<8} {record.name} [{record.request_id}] {record.request_path} :: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "request": getattr(record, "request_path", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


# ----------------------------------------------------------------------
# Email-on-error handler
# ----------------------------------------------------------------------

class SMTPErrorAlertHandler(logging.Handler):
    """
    Sends an alert email on ERROR/CRITICAL log records, rate-limited so
    a burst of the same failure doesn't mailbomb the operator. Uses the
    app's existing email_service (fail-open: a mail problem never
    propagates back into the logging path). No-op unless SMTP and a
    recipient are configured.
    """

    def __init__(self, recipient: str, min_interval_seconds: int = 300):
        super().__init__(level=logging.ERROR)
        self.recipient = recipient
        self.min_interval_seconds = min_interval_seconds
        self._last_sent_by_key = {}
        self._state_lock = threading.Lock()
        # Guards against re-entrancy: sending the alert goes through
        # email_service, which logs (at ERROR) if the send fails -- that
        # log record would otherwise trigger this handler again.
        self._sending = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._sending, "active", False):
            return
        try:
            key = f"{record.name}:{record.funcName}:{record.lineno}"
            now = time.monotonic()
            with self._state_lock:
                last = self._last_sent_by_key.get(key)
                if last is not None and now - last < self.min_interval_seconds:
                    return
                self._last_sent_by_key[key] = now
                # bound the dict
                if len(self._last_sent_by_key) > 200:
                    for k in sorted(self._last_sent_by_key, key=self._last_sent_by_key.get)[:100]:
                        del self._last_sent_by_key[k]

            subject = f"[Abstractly] {record.levelname}: {record.getMessage()[:120]}"
            body = self.format(record)
            from app import email_service
            self._sending.active = True
            try:
                email_service.send_operational_alert(self.recipient, subject, body)
            finally:
                self._sending.active = False
        except Exception:
            # A logging handler must never raise. Nothing to do but
            # swallow it -- the record is still on stdout regardless.
            pass


# ----------------------------------------------------------------------

def _resolve_level() -> int:
    name = (os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, name, logging.INFO)


def configure_logging(force: bool = False) -> None:
    global _configured
    with _lock:
        if _configured and not force:
            return
        _configured = True

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    level = _resolve_level()
    root.setLevel(level)

    handler = logging.StreamHandler()  # stdout
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        _JsonFormatter() if (os.environ.get("LOG_FORMAT") or "").strip().lower() == "json" else _PlainFormatter()
    )
    root.addHandler(handler)

    # Third-party noise control.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)   # we log our own per-request line
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.INFO)

    _maybe_add_email_alerts(root)

    logging.getLogger(__name__).info(
        "logging configured (level=%s, format=%s)", logging.getLevelName(level),
        (os.environ.get("LOG_FORMAT") or "plain"),
    )


def _maybe_add_email_alerts(root: logging.Logger) -> None:
    # OPT-IN, not opt-out: this app has a real history of an accidental
    # email storm (see DECISIONS.md), so an error-triggered send is only
    # wired up when explicitly asked for -- set ERROR_ALERT_EMAILS=true
    # in production, leave it unset for local dev where you hit errors
    # constantly. Still needs SMTP + a recipient configured.
    if os.environ.get("ERROR_ALERT_EMAILS", "").strip().lower() not in ("1", "true", "yes", "on"):
        return
    recipient = (os.environ.get("ADMIN_EMAIL") or "").strip()
    email_configured = bool((os.environ.get("EMAIL_USER") or "").strip() and (os.environ.get("EMAIL_APP_PASSWORD") or "").strip())
    if not (recipient and email_configured):
        logging.getLogger(__name__).warning(
            "ERROR_ALERT_EMAILS is on but SMTP/ADMIN_EMAIL isn't fully configured -- error alerts disabled."
        )
        return
    if any(isinstance(h, SMTPErrorAlertHandler) for h in root.handlers):
        return
    alert = SMTPErrorAlertHandler(recipient)
    alert.addFilter(RequestContextFilter())
    alert.setFormatter(_PlainFormatter())
    root.addHandler(alert)
    logging.getLogger(__name__).info("error-alert emails enabled -> %s", recipient)


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


def install_request_logging(app) -> None:
    """
    One structured log line per request: `METHOD path -> status Nms`.
    A per-request id (also on the X-Request-Id response header) ties
    together every other line the request emitted. /health is skipped
    (Render hits it constantly and a 200 there is not news). A 5xx is
    logged at ERROR so it reaches the email-on-error handler.
    """
    from flask import g as _g, request as _req

    @app.before_request
    def _assign_request_id():
        _g.request_id = new_request_id()
        _g._request_started = time.monotonic()

    @app.after_request
    def _log_request(response):
        if _req.path == "/health":
            return response
        duration_ms = None
        started = getattr(_g, "_request_started", None)
        if started is not None:
            duration_ms = (time.monotonic() - started) * 1000.0
        response.headers.setdefault("X-Request-Id", getattr(_g, "request_id", "-"))

        level = logging.INFO
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        logging.getLogger("app.request").log(
            level, "%s %s -> %s%s",
            _req.method, _req.path, response.status_code,
            f" {duration_ms:.0f}ms" if duration_ms is not None else "",
        )
        return response
