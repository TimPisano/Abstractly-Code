"""
Real per-user team authentication: every team member is a row in the
`users` table (email, name, bcrypt password hash, role), verified with
bcrypt, backed by Flask's signed-cookie session -- the same session
mechanism this app has always used (SESSION_COOKIE_SAMESITE='None' +
SECURE=True + HTTPONLY=True, see app/api.py), just now backing a real
per-user lookup instead of one hardcoded env-var account.

Replaces the old single-hardcoded-admin login this app shipped with
initially. The env-var ADMIN_EMAIL/ADMIN_PASSWORD_HASH pair is now
only used once, to seed the first admin user into the `users` table
on a brand-new database (see database._seed_first_admin_user) -- after
that, login is entirely database-backed like any other user, and the
env vars have no further effect. See DECISIONS.md's "Reliability
hardening pass" and "Identity model for resolutions/comments" entries
for the full history of why this replaced the old model rather than
sitting alongside it.
"""

import logging
from functools import wraps

import bcrypt
from flask import jsonify, session

from app import database

logger = logging.getLogger(__name__)

ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}

# A precomputed bcrypt hash of a fixed, never-issued dummy password --
# checked (and always fails) whenever the email doesn't match a real,
# active user, so a login attempt against a nonexistent or deactivated
# account still pays the same bcrypt cost a real-account-wrong-password
# attempt would. Without this, response timing would leak which emails
# have real accounts (fast rejection = no such user, slow rejection =
# real user, wrong password) -- the same property the old single-admin
# verify_admin_credentials() protected, extended correctly from one
# fixed account to a real per-row lookup.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password-never-issued", bcrypt.gensalt()).decode("utf-8")


def hash_password(password: str) -> str:
    """Returns a bcrypt hash (str) suitable for storing in users.password_hash."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(email: str, password: str):
    """
    Returns the matching user dict on success (only for an 'active'
    user), None otherwise -- including for a real, correct password on
    a 'deactivated' account, which must fail exactly like a wrong
    password from the caller's point of view, not a different kind of
    error that would confirm the email exists.
    """
    user = database.get_user_by_email((email or "").strip().lower())
    if not user or user["status"] != "active":
        try:
            bcrypt.checkpw((password or "").encode("utf-8"), _DUMMY_HASH.encode("utf-8"))
        except (ValueError, TypeError):
            pass
        return None

    try:
        password_matches = bcrypt.checkpw((password or "").encode("utf-8"), user["password_hash"].encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed password_hash (shouldn't happen -- every write
        # path goes through hash_password()) -- fail closed rather
        # than raise a 500 with a traceback.
        logger.exception("users.id=%s has a password_hash that isn't valid bcrypt output", user["id"])
        password_matches = False

    return user if password_matches else None


def current_user():
    """
    The logged-in user's {"id", "email", "name", "role", "is_owner"},
    or None if there's no session. Reads straight from the signed
    session cookie -- this is what resolved_by/author_name/
    dismissed_by/actor_user_id are sourced from now, never a
    client-supplied request-body field.

    is_owner defaults to False for any session predating this field
    (an old cookie from before the owner console existed) -- correct,
    since owner status is only ever granted explicitly (see
    require_owner) and such a session was never granted it.
    """
    if not session.get("user_id"):
        return None
    return {
        "id": session["user_id"],
        "email": session.get("email"),
        "name": session.get("name"),
        "role": session.get("role"),
        "is_owner": bool(session.get("is_owner", False)),
    }


def require_role(min_role: str = "viewer"):
    """
    Route decorator factory: @require_role('analyst') requires at
    least analyst rank; bare @require_role() requires only "logged in,
    any role" (viewer is the lowest rank, so it's the default floor).
    Put closest to the route decorator (innermost), same convention
    the old require_admin used.

    401s if there's no session at all, 403s if the session's role
    doesn't meet min_role -- deliberately different statuses (this app
    had no 403 usage before this system): "you're not logged in" and
    "you're logged in but not allowed to do this" are different
    situations a frontend should handle differently (redirect to
    login vs. show a permission error), and collapsing them into one
    status would lose that distinction for no reason.
    """
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"error": "Login required"}), 401
            if ROLE_RANK.get(user["role"], -1) < ROLE_RANK[min_role]:
                return jsonify({"error": f"{min_role.capitalize()} role required"}), 403
            return view_fn(*args, **kwargs)
        return wrapped
    return decorator


def require_owner():
    """
    Route decorator for the owner console (business-management routes:
    every login's usage, suspend/reactivate/reset-password on ANY
    account, revenue/expenses). Deliberately independent of
    require_role()/ROLE_RANK -- role='admin' never implies is_owner,
    and this never checks role at all, only the is_owner flag.

    401 if there's no session (same as require_role, reveals nothing).
    404 -- not 403 -- if logged in but not owner. A 403 would confirm
    to a curious admin that a hidden owner-only route exists at all;
    404 makes an /owner/* route genuinely indistinguishable from a URL
    that doesn't exist, matching the explicit requirement that this
    console not be discoverable by regular users or regular admins.
    """
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"error": "Login required"}), 401
            if not user["is_owner"]:
                return jsonify({"error": "Not found"}), 404
            return view_fn(*args, **kwargs)
        return wrapped
    return decorator
