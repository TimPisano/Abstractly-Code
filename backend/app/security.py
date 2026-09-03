"""
App-wide security middleware, all installed by install_security(app):

  1. CSRF defense for cross-site requests. The session cookie is
     SameSite=None (the frontend and API are different origins on
     Render, and a Lax/Strict cookie is never sent cross-site), so the
     browser WILL attach it to a cross-site request. CORS preflight
     already blocks disallowed origins for JSON requests, but
     multipart/form-data is a CORS "simple" content type -- no
     preflight -- so a malicious page could otherwise POST a file to an
     upload route with the victim's cookie. Defense: on every
     state-changing request, if the browser sent an Origin (or Referer)
     that isn't in the allow-list, reject with 403. Modern browsers
     send Origin on every non-GET request; a request with no
     Origin/Referer at all is a non-browser client (curl, a script,
     server-to-server) which carries no ambient cookies and is not a
     CSRF vector. This is the same header-verification approach Django
     uses.

  2. Transport security. HSTS on every HTTPS response. Optional
     app-level HTTP->HTTPS redirect via FORCE_HTTPS=true for non-Render
     hosts (Render already 301s http->https at its edge, so this is
     off by default).

  3. Standard response security headers (nosniff, frame denial,
     referrer policy, a tight Content-Security-Policy tuned to what the
     API actually returns -- JSON, files, and one self-contained HTML
     report).

Also provides RateLimiter: a small in-process fixed-window limiter
reused by the login and password-reset routes (same shape and same
per-worker caveat as the existing forgot-password limiter).
"""

import logging
import os
import threading
import time
from typing import Iterable
from urllib.parse import urlparse

from flask import request, jsonify, redirect

logger = logging.getLogger(__name__)

_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Requests that must NOT be subject to the CSRF origin check: the health
# check (GET anyway, but be explicit) and CORS preflight (OPTIONS,
# handled by flask-cors). Everything else that changes state is checked.
_CSRF_EXEMPT_PATHS = {"/health"}

_FORCE_HTTPS = (os.environ.get("FORCE_HTTPS", "").strip().lower() in ("1", "true", "yes"))


def _request_is_https() -> bool:
    if request.is_secure:
        return True
    # Behind Render's (or any) TLS-terminating proxy.
    return request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower() == "https"


def _origin_allowed(allowed_origins) -> bool:
    """
    True unless the request carries a browser-set Origin/Referer that is
    NOT in `allowed_origins`. Absent Origin AND Referer -> True (not a
    browser CSRF vector).
    """
    origin = request.headers.get("Origin")
    if origin is not None:
        return origin in allowed_origins
    referer = request.headers.get("Referer")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}" in allowed_origins
        return False
    return True


def install_security(app, allowed_origins: Iterable[str]) -> None:
    allowed_origins = set(allowed_origins or [])

    @app.before_request
    def _enforce_transport_and_csrf():
        # 1. Optional app-level HTTPS enforcement (Render already does
        #    this at the edge; on by request only, and never for local
        #    dev hosts).
        if _FORCE_HTTPS and not _request_is_https():
            host = request.host.split(":")[0]
            if host not in ("localhost", "127.0.0.1", "0.0.0.0"):
                url = request.url.replace("http://", "https://", 1)
                return redirect(url, code=301)

        # 2. CSRF: reject a state-changing request whose browser-set
        #    Origin/Referer isn't allow-listed.
        if request.method in _STATE_CHANGING_METHODS and request.path not in _CSRF_EXEMPT_PATHS:
            if not _origin_allowed(allowed_origins):
                logger.warning(
                    "Blocked cross-origin %s %s (Origin=%r Referer=%r)",
                    request.method, request.path,
                    request.headers.get("Origin"), request.headers.get("Referer"),
                )
                return jsonify({"error": "Cross-origin request blocked."}), 403

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        if _request_is_https():
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        # CSP tuned to what this API returns. Everything is JSON or a
        # file download except /portfolio/report, which is one
        # self-contained HTML doc with a single inline <style> and no
        # scripts.
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type == "text/html":
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            )
        else:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )

        # Don't let a browser or shared cache retain an authenticated
        # API response.
        if request.path.startswith("/auth/") or request.path.startswith("/owner/"):
            response.headers["Cache-Control"] = "no-store"

        return response


class RateLimiter:
    """
    In-process fixed-window rate limiter. One instance per protected
    endpoint. `check(keys)` records a hit against every key and returns
    True if ANY key was already at or over the cap for the current
    window -- so a caller can pass e.g. both an IP key and an email key
    and be limited if either is saturated.

    Per-worker and memory-resident: it resets on restart and doesn't
    coordinate across gunicorn workers, the same accepted ceiling as
    the existing forgot-password / waitlist limiters. Still removes the
    trivial single-host online brute-force this is aimed at.
    """

    def __init__(self, max_hits: int, window_seconds: int):
        self.max_hits = max_hits
        self.window_seconds = window_seconds
        self._state = {}  # key -> [monotonic timestamps within window]
        self._lock = threading.Lock()

    def check(self, keys: Iterable[str]) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            # Prune every expired key (not just the ones touched) so the
            # dict can't grow unbounded on a public endpoint.
            for key in [k for k, ts in self._state.items() if not ts or ts[-1] <= cutoff]:
                del self._state[key]

            limited = False
            for key in keys:
                timestamps = [t for t in self._state.get(key, []) if t > cutoff]
                if len(timestamps) >= self.max_hits:
                    limited = True
                timestamps.append(now)
                self._state[key] = timestamps
            return limited

    def reset(self) -> None:
        """Test-only: clear all state."""
        with self._lock:
            self._state.clear()
