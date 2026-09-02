#!/usr/bin/env python3
"""
Reset (or create) an admin user's password directly in the database,
for when you're locked out and can't use the normal in-app
change-password flow (which requires already being logged in).

Unlike set_admin_password.py (which only seeds the FIRST admin via
env vars, and only on a brand-new empty database), this script works
against an EXISTING database with existing users -- it looks up the
given email, and either updates that user's password in place
(preserving their id/role/history) or creates a new admin user if no
account with that email exists yet.

Uses the same bcrypt hashing as everywhere else in the app
(app.auth.hash_password) -- no second hashing scheme. Password is
never a command-line argument or a literal in this file; it's read
with getpass (hidden input, not saved to shell history), so it never
has to be typed anywhere but your own terminal.

Usage (against your LOCAL database):
    cd backend && source venv/bin/activate
    python3 reset_admin_password.py you@example.com

Usage (against a REMOTE database, e.g. Render): this script only ever
touches the database at DB_PATH (or the default local path) on the
machine it runs on. It does NOT reach across the network to a live
Render deployment's database -- see DEPLOYMENT.md / ask the assistant
for how to reset the password on a live deployment instead (it needs
either the Render Shell tab, or updating ADMIN_PASSWORD_HASH and
accepting a redeploy on the free tier's non-persistent storage).
"""

import getpass
import sys

from app import database
from app.auth import hash_password


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 reset_admin_password.py <email>", file=sys.stderr)
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    database.init_db()

    print(f"Resetting admin password for {email} (local database only -- see this script's docstring for remote/Render).")
    print("Typed with getpass -- it will not appear on screen or in your shell history.\n")

    password = getpass.getpass("New password: ")
    if len(password) < 8:
        print("\nPassword must be at least 8 characters. Nothing was changed.", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("\nPasswords didn't match. Nothing was changed.", file=sys.stderr)
        sys.exit(1)

    password_hash = hash_password(password)

    existing = database.get_user_by_email(email)
    if existing:
        database.update_user_password(existing["id"], password_hash)
        if existing["role"] != "admin":
            database.update_user_role(existing["id"], "admin")
        if existing["status"] != "active":
            database.update_user_status(existing["id"], "active")
        print(f"\nDone. Updated existing user id={existing['id']} ({email}) -- password reset, role set to admin, status set to active.")
    else:
        result = database.create_user(email=email, name="Admin", password_hash=password_hash, role="admin")
        if result["status"] == "created":
            print(f"\nDone. Created new admin user id={result['id']} ({email}).")
        else:
            print("\nUnexpected: create_user reported a duplicate right after get_user_by_email found none. Re-run the script.", file=sys.stderr)
            sys.exit(1)

    print(f"You can now log in at your app's login page with {email} and the password you just set.")


if __name__ == "__main__":
    main()
