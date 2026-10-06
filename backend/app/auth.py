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
import time
from datetime import datetime, timezone
from functools import wraps

import bcrypt
from flask import current_app, g, has_request_context, jsonify, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import database

logger = logging.getLogger(__name__)

ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}

# How long a login lasts. "Keep me signed in" checked = REMEMBER; unchecked
# = the short default. Both the bearer token (app/) and the session cookie
# (admin/, owner/) enforce the same pair, server-side, so neither can be
# stretched by a client that keeps a credential around longer.
TOKEN_MAX_AGE_SECONDS = 12 * 3600
REMEMBER_MAX_AGE_SECONDS = 30 * 24 * 3600


def _token_serializer() -> URLSafeTimedSerializer:
    # current_app.secret_key, not a module-level import of api.py's app
    # object -- avoids a circular import (api.py imports this module),
    # and current_app is valid anywhere inside a request context.
    return URLSafeTimedSerializer(current_app.secret_key, salt="bearer-auth")


def issue_token(user: dict, remember: bool = False) -> str:
    """
    Signed, stateless bearer token for the app/ client surface's
    Authorization header (see frontend/app/api.js) -- carries the same
    identity fields the session cookie does. admin/ and owner/ still
    use the cookie exclusively; this is additive, not a replacement,
    so a stale/pre-migration client still works unchanged.

    `rm` (remember) picks its lifetime: 30 days, or 12 hours.
    `sv` is the user's session_version at issue time -- a password
    reset bumps the row's copy, which kills this token on its next use
    (see _live_user). That is the only server-side revocation a
    stateless token has, and it's per-user, not per-token.
    """
    return _token_serializer().dumps({
        "user_id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "is_owner": bool(user.get("is_owner", False)),
        "team_id": user.get("team_id"),
        "sv": int(user.get("session_version") or 0),
        "rm": bool(remember),
    })


def _user_from_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    try:
        data, issued_at = _token_serializer().loads(
            auth_header[7:].strip(), max_age=REMEMBER_MAX_AGE_SECONDS, return_timestamp=True,
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    # Tokens issued before "keep me signed in" existed have no `rm` --
    # they were always 12-hour tokens and stay that way.
    if not data.get("rm"):
        age = (datetime.now(timezone.utc) - issued_at).total_seconds()
        if age > TOKEN_MAX_AGE_SECONDS:
            return None
    return {
        "id": data.get("user_id"),
        "email": data.get("email"),
        "name": data.get("name"),
        "role": data.get("role"),
        "is_owner": bool(data.get("is_owner", False)),
        "team_id": data.get("team_id"),
        "sv": int(data.get("sv") or 0),
    }

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
    user on an 'active' team), None otherwise -- including for a real,
    correct password on a 'deactivated' account OR a deactivated team
    (every user in a deactivated team is blocked, even one whose own
    status is still 'active'), which must fail exactly like a wrong
    password from the caller's point of view, not a different kind of
    error that would confirm the email exists.
    """
    # No stored password can be longer than 72 bytes (every write path
    # rejects it -- bcrypt raises past that), so a longer one is always
    # wrong. It takes the same dummy-hash path as an unknown email, cut
    # to 72 bytes so that path can't raise, keeping the timing identical.
    overlong = len((password or "").encode("utf-8")) > 72
    if overlong:
        password = (password or "").encode("utf-8")[:72].decode("utf-8", "ignore")
    user = None if overlong else database.get_user_by_email((email or "").strip().lower())
    team_deactivated = bool(user) and user.get("team_id") is not None and database.is_team_deactivated(user["team_id"])
    if not user or user["status"] != "active" or team_deactivated:
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
    The logged-in user's {"id", "email", "name", "role", "is_owner", "team_id"},
    or None if there's no session. Reads straight from the signed
    session cookie, or an Authorization: Bearer token (see
    issue_token) -- token checked first, cookie as fallback, since a
    request carries at most one of the two in practice. This is what
    resolved_by/author_name/dismissed_by/actor_user_id are sourced
    from now, never a client-supplied request-body field.

    is_owner defaults to False for any session predating this field
    (an old cookie from before the owner console existed) -- correct,
    since owner status is only ever granted explicitly (see
    require_owner) and such a session was never granted it.
    team_id defaults to None for old sessions; a fresh login always
    populates it from the user row.
    """
    # The signed cookie/token only proves WHO this is. Whether they may
    # still act -- and with which role and team -- is re-read from the
    # database on every request, so deactivating a user or a team, or
    # changing someone's role, takes effect on their very next request
    # instead of whenever their 12-hour token happens to expire.
    # Cached on flask.g: one users-row read per request, not per call.
    if has_request_context() and "_abstractly_user" in g:
        return g._abstractly_user
    claimed = _user_from_bearer_token()
    if claimed is None and session.get("user_id"):
        # `exp` is an absolute epoch stamped at login (api._start_session).
        # Cookie expiry alone is client-side, and Flask re-signs a
        # permanent session on every request, so this is what actually
        # ends a login. Sessions made before it existed have none and
        # are bounded by Flask's own permanent_session_lifetime.
        exp = session.get("exp")
        if exp is None or time.time() < exp:
            claimed = {"id": session["user_id"], "sv": int(session.get("sv") or 0)}
    user = _live_user(claimed["id"], claimed.get("sv", 0)) if claimed else None
    if has_request_context():
        g._abstractly_user = user
    return user


def _live_user(user_id, session_version=0):
    """
    The user's CURRENT row as the current_user() dict, or None if the
    account no longer exists, isn't active, or its team is deactivated
    -- the same rules verify_password applies at login. A session for a
    user who's been switched off is treated exactly like no session.
    Also None if the credential's session_version is stale: the user
    reset their password since it was issued (see
    database._migrate_users_add_session_version).
    """
    row = database.get_user(user_id)
    if not row or row.get("status") != "active":
        return None
    if int(row.get("session_version") or 0) != int(session_version or 0):
        return None
    if row.get("team_id") is not None and database.is_team_deactivated(row["team_id"]):
        return None
    return {
        "id": row["id"],
        "email": row.get("email"),
        "name": row.get("name"),
        "role": row.get("role"),
        "is_owner": bool(row.get("is_owner")),
        "team_id": row.get("team_id"),
    }


def current_team_id() -> int:
    """
    The logged-in user's team_id -- the real multi-tenant boundary
    every route that reads or writes team-owned data (leases,
    discrepancies, alerts, comments, tasks, ...) must scope its queries
    by. Never trust a client-supplied team_id; it always comes from
    here. Raises RuntimeError if there's no session or the session
    predates team isolation -- deliberately not a silent None return,
    since a caller that got None and forgot to check would otherwise
    run an unscoped, cross-tenant query (see DECISIONS.md's "Real
    multi-tenant data isolation" entry on why team_id has no
    Optional/default anywhere in this codebase). Every route already
    goes through require_role/require_owner first, which 401s with no
    session, so in practice this is only ever called when current_user()
    is known to be non-None.
    """
    user = current_user()
    if user is None or user.get("team_id") is None:
        raise RuntimeError("current_team_id() called with no logged-in team -- the route is missing a require_role/require_owner check before it")
    return user["team_id"]


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
