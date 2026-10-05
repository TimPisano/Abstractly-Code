"""
Authorization coverage: every state-changing route must be behind
auth, and the role ranks must actually be enforced. The headline test
introspects app.url_map and hits EVERY POST/PUT/PATCH/DELETE route with
no session -- so a route added later without @require_role is caught
automatically, not whenever someone happens to notice.
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# Routes that are unauthenticated BY DESIGN. Anything not here that
# accepts a mutating method must reject an anonymous caller.
_PUBLIC_MUTATING = {
    "/auth/login", "/auth/logout", "/auth/forgot-password", "/auth/reset-password",
    # A brand-new team's first admin has no session yet by definition
    # -- the 7-day setup token itself is the proof of identity, same
    # "unauthenticated by design" category as /auth/reset-password.
    "/auth/team-setup",
    "/waitlist", "/waitlist/check",
    # Fired by anonymous visitors on the public marketing site itself
    # (frontend/landing.js) -- same "public by design" category as
    # /waitlist above, not an oversight. See POST /analytics/pageview's
    # own docstring.
    "/analytics/pageview",
    # The landing page's "Book a Demo" form (frontend/landing.js) --
    # same "public by design" category as /waitlist above. CSRF is
    # still enforced (see security.py), plus its own rate limit and
    # honeypot check (see api.py's POST /demo-request).
    "/demo-request",
}


from _session_users import sync_session_user


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _sample_body_for(rule):
    """A minimal body so the route reaches its auth check rather than 400-ing on a missing content type first (either outcome is acceptable, but this exercises the real path)."""
    path = str(rule)
    if "import-rent-roll" in path or path.endswith("/amendments") or path.endswith("/resubmit") \
            or path in ("/leases", "/leases/batch", "/extract") or "t12-reconciliation" in path:
        return {"data": {"file": (io.BytesIO(b"x"), "x.pdf")}, "content_type": "multipart/form-data"}
    return {"json": {}}


def test_every_mutating_route_rejects_an_anonymous_caller():
    db = _fresh_temp_db()
    try:
        client = app.test_client()
        checked = 0
        offenders = []
        for rule in app.url_map.iter_rules():
            methods = rule.methods & _MUTATING
            if not methods or rule.rule in _PUBLIC_MUTATING:
                continue
            # substitute path params with 1
            path = rule.rule
            for arg in rule.arguments:
                path = path.replace(f"<{arg}>", "1").replace(f"<int:{arg}>", "1").replace(f"<path:{arg}>", "x").replace(f"<{arg.split(':')[-1]}>", "1")
            # cheap generic replace for any remaining "<...>"
            import re as _re
            path = _re.sub(r"<[^>]+>", "1", path)

            method = "POST" if "POST" in methods else sorted(methods)[0]
            kwargs = _sample_body_for(rule)
            resp = client.open(path, method=method, **kwargs)
            checked += 1
            if resp.status_code not in (401, 403, 404, 405):
                offenders.append(f"{method} {path} -> {resp.status_code}")
        assert checked > 30, f"introspection found suspiciously few mutating routes ({checked})"
        assert not offenders, "these state-changing routes let an anonymous caller through:\n  " + "\n  ".join(offenders)
    finally:
        os.unlink(db)
    print(f"✓ test_every_mutating_route_rejects_an_anonymous_caller: PASS ({checked} routes checked)")


def _client(role=None, is_owner=False):
    c = app.test_client()
    if role or is_owner:
        with c.session_transaction() as s:
            s.update({"user_id": 1, "email": "u@x.com", "name": "U", "role": role or "viewer", "is_owner": is_owner, "team_id": 1})
            sync_session_user(s)
    return c


def test_viewer_cannot_do_analyst_actions():
    db = _fresh_temp_db()
    try:
        v = _client("viewer")
        # a representative analyst-gated write
        r = v.post("/tasks", json={"title": "x"})
        assert r.status_code == 403, r.status_code
        r = v.post("/leases/bulk-delete", json={"lease_ids": [1]})
        assert r.status_code == 403
    finally:
        os.unlink(db)
    print("✓ test_viewer_cannot_do_analyst_actions: PASS")


def test_analyst_cannot_do_admin_actions():
    db = _fresh_temp_db()
    try:
        a = _client("analyst")
        r = a.post("/team/members", json={"email": "n@x.com", "name": "N", "role": "viewer", "password": "password123"})
        assert r.status_code == 403
        r = a.get("/team/members")
        assert r.status_code == 403
    finally:
        os.unlink(db)
    print("✓ test_analyst_cannot_do_admin_actions: PASS")


def test_non_owner_gets_404_on_owner_routes():
    db = _fresh_temp_db()
    try:
        admin = _client("admin", is_owner=False)
        for path in ("/owner/accounts", "/owner/revenue", "/owner/finance/summary", "/extraction-quality/trend"):
            assert admin.get(path).status_code == 404, path
        # a real owner gets in
        owner = _client("admin", is_owner=True)
        assert owner.get("/owner/accounts").status_code == 200
    finally:
        os.unlink(db)
    print("✓ test_non_owner_gets_404_on_owner_routes: PASS")


def test_extract_route_requires_login():
    """POST /extract runs the (potentially model-backed, billable) extraction pipeline -- it must not be anonymous."""
    db = _fresh_temp_db()
    try:
        anon = app.test_client().post("/extract", data={"file": (io.BytesIO(b"x"), "x.pdf")}, content_type="multipart/form-data")
        assert anon.status_code == 401, anon.status_code
    finally:
        os.unlink(db)
    print("✓ test_extract_route_requires_login: PASS")


# The headline introspection test above only walks POST/PUT/PATCH/DELETE
# routes (_MUTATING) -- these three rent-roll reads are GET-only
# (@require_role(), still gated, just never a "mutation") so they fall
# outside that sweep entirely and had no coverage of their own.
_RENT_ROLL_GET_ROUTES = [
    "/portfolio/rent-roll-reconciliation",
    "/portfolio/rent-roll.csv",
    "/portfolio/rent-roll.xlsx",
]


def test_rent_roll_get_routes_require_login():
    """GET /portfolio/rent-roll-reconciliation, rent-roll.csv, and rent-roll.xlsx are all @require_role()-gated reads of the same lease/rent-roll data every mutating route in this file already gets checked for -- confirm an anonymous caller is rejected here too, since the headline introspection test above never looks at GET routes at all."""
    db = _fresh_temp_db()
    try:
        anon = app.test_client()
        for path in _RENT_ROLL_GET_ROUTES:
            resp = anon.get(path)
            assert resp.status_code == 401, (path, resp.status_code)
    finally:
        os.unlink(db)
    print("✓ test_rent_roll_get_routes_require_login: PASS")


if __name__ == "__main__":
    test_every_mutating_route_rejects_an_anonymous_caller()
    test_viewer_cannot_do_analyst_actions()
    test_analyst_cannot_do_admin_actions()
    test_non_owner_gets_404_on_owner_routes()
    test_extract_route_requires_login()
    test_rent_roll_get_routes_require_login()
    print("\nAll route authorization tests passed.")
