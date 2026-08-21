"""
Admin authentication: a single hardcoded-by-configuration admin
account (not a users table -- there is exactly one admin for now, and
its identity/credential live in environment variables, never in code
or the database), verified with bcrypt, backed by Flask's signed-
cookie session.

This is deliberately separate from the client-facing access gate
(frontend/app/access-gate.js, backend's /waitlist/check route): that
flow is a self-reported email match with no password and no real
identity proof (see DECISIONS.md "Access gate uses self-reported
email, not real auth"). This module is real authentication -- a
password, hashed, checked with a timing-safe comparison, backing a
cryptographically signed session cookie the browser can't forge or
read the contents of. The two systems will very likely merge into one
real per-account auth system later (see the deferred "enterprise
readiness" work), but for now the admin login this module powers and
the client access gate remain intentionally independent, per explicit
product decision.
"""

import logging
import os
from functools import wraps

import bcrypt
from flask import jsonify, session

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Returns a bcrypt hash (str) suitable for storing in ADMIN_PASSWORD_HASH. Never called at request time in this app -- only by the one-off setup script an operator runs to generate the env var value."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _admin_credentials():
    """(email, password_hash) from the environment, lowercased/stripped email. Either can be empty if not configured."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    return email, password_hash


def admin_login_is_configured() -> bool:
    email, password_hash = _admin_credentials()
    return bool(email and password_hash)


def verify_admin_credentials(email: str, password: str) -> bool:
    """
    True only if both the email and password match the configured
    admin account. Deliberately always runs the bcrypt comparison, even
    when the email is already known not to match, using the real
    configured hash -- so a login attempt with a wrong email takes the
    same time as one with a wrong password, and the response timing
    itself can't leak which one was wrong (the API layer's error
    message already doesn't say; this closes the same gap one layer
    lower). bcrypt.checkpw is itself a constant-time comparison for the
    hash check.
    """
    admin_email, admin_hash = _admin_credentials()
    if not admin_email or not admin_hash:
        logger.error(
            "Admin login attempted but is not configured -- set ADMIN_EMAIL and "
            "ADMIN_PASSWORD_HASH in backend/.env. See .env.example."
        )
        return False

    email_matches = (email or "").strip().lower() == admin_email
    try:
        password_matches = bcrypt.checkpw(
            (password or "").encode("utf-8"), admin_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        # A malformed ADMIN_PASSWORD_HASH (not real bcrypt output) --
        # fail closed rather than raise a 500 with a traceback.
        logger.exception("ADMIN_PASSWORD_HASH is not a valid bcrypt hash")
        password_matches = False

    return email_matches and password_matches


def require_admin(view_fn):
    """Route decorator: 401s with a generic message if the current session isn't an authenticated admin session. Put closest to the route decorator (innermost) so Flask's routing still sees the real function name/docstring."""
    @wraps(view_fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return jsonify({"error": "Admin authentication required"}), 401
        return view_fn(*args, **kwargs)
    return wrapped
