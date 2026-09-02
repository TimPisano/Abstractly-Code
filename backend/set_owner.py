#!/usr/bin/env python3
"""
Grants (or revokes) is_owner on an EXISTING user, directly in the
database. This is the ONLY way owner access is ever set -- there is
no signup path, no API route, no UI control that lets anyone grant
themselves or another account the owner flag. Deliberately separate
from role='admin' (see app.auth.require_owner's docstring): admin
role never implies owner access.

The account's env-var-seeded first admin (ADMIN_EMAIL/
ADMIN_PASSWORD_HASH) already gets is_owner=1 automatically on every
fresh seed (see database._seed_first_admin_user) -- this script exists
for local dev, or for the rare case of granting owner to a different
email than the seeded admin.

No password/secret is involved here (a boolean flag isn't sensitive),
so this runs non-interactively, unlike reset_admin_password.py.

Usage (against your LOCAL database):
    cd backend && source venv/bin/activate
    python3 set_owner.py you@example.com          # grants
    python3 set_owner.py you@example.com --revoke  # revokes

Usage (against a REMOTE database, e.g. Render): this script only ever
touches the database at DB_PATH (or the default local path) on the
machine it runs on -- it does NOT reach across the network to a live
Render deployment. Production's owner account is set automatically
via ADMIN_EMAIL/ADMIN_PASSWORD_HASH (see this script's docstring
above) -- nothing further is needed there.
"""

import sys

from app import database


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    revoke = "--revoke" in sys.argv[1:]

    if len(args) != 1:
        print("Usage: python3 set_owner.py <email> [--revoke]", file=sys.stderr)
        sys.exit(1)

    email = args[0].strip().lower()

    database.init_db()

    user = database.get_user_by_email(email)
    if not user:
        print(f"No user found with email {email!r}. Create the login first (e.g. via reset_admin_password.py or the Team view), then re-run this.", file=sys.stderr)
        sys.exit(1)

    database.set_user_owner_flag(user["id"], not revoke)

    if revoke:
        print(f"Done. Revoked owner access from user id={user['id']} ({email}).")
    else:
        print(f"Done. Granted owner access to user id={user['id']} ({email}).")
        print("They can now log in at /owner/login.html with their existing password.")


if __name__ == "__main__":
    main()
