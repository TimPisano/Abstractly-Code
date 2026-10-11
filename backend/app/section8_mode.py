"""
SECTION8_MODE feature flag (default OFF).

Gates every Section 8 surface added for the pivot (PIVOT_PLAN.md on
branch pivot/section8). With the flag off, the /section8/* routes 404 --
indistinguishable from routes that don't exist -- and nothing a tester
sees changes. The Section 8 tables are created either way (additive,
empty until used), so turning the flag on later needs no migration.

Read on every call, not at import, so flipping the env var on Render
takes effect on the next restart and tests can toggle it -- same as
SELF_SERVE_SIGNUP_ENABLED (api._signup_enabled).
"""

import os
from functools import wraps

from flask import jsonify

FLAG_ENV = "SECTION8_MODE"


def section8_mode_enabled() -> bool:
    return os.environ.get(FLAG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def require_section8_mode(fn):
    """404 when the flag is off. Put it ABOVE @require_role (outermost after @app.route), so with the flag off every caller -- logged in or not -- gets the same 404 a nonexistent route gives, rather than a 401 that confirms the route exists."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not section8_mode_enabled():
            return jsonify({"error": "Not found"}), 404
        return fn(*args, **kwargs)
    return wrapper
