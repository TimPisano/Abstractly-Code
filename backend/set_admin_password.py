#!/usr/bin/env python3
"""
Setup helper for the FIRST admin account only: prompts for a password
with getpass (never echoed to the terminal, never written to shell
history) and prints the bcrypt hash to paste into backend/.env as
ADMIN_PASSWORD_HASH. That value is read exactly once, the first time
the backend starts against a brand-new empty database, to seed one
admin-role row into the `users` table (see
app.database._seed_first_admin_user) -- running this script again
after that first start has no effect; change an existing admin's
password via POST /auth/change-password or the Team view instead.

This script never reads or writes .env itself -- it only prints the
hash, so you can see exactly what you're pasting rather than trusting
a script to edit your secrets file for you.

Usage:
    cd backend && venv/bin/python3 set_admin_password.py
"""

import getpass
import sys

from app.auth import hash_password


def main():
    print("Setting the FIRST admin account's password for Abstractly (one-time seed only).")
    print("This is typed with getpass -- it will not appear on screen or in your shell history.\n")

    password = getpass.getpass("New admin password: ")
    if len(password) < 8:
        print("\nPassword must be at least 8 characters. Nothing was generated.", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("\nPasswords didn't match. Nothing was generated.", file=sys.stderr)
        sys.exit(1)

    password_hash = hash_password(password)

    print("\nAdd (or replace) this line in backend/.env:\n")
    print(f"ADMIN_PASSWORD_HASH={password_hash}\n")
    print("Then start the backend against a fresh (or pre-users-table) database for it to take effect.")


if __name__ == "__main__":
    main()
