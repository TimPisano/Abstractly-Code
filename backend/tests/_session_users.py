"""
Test helper (not a test file -- leading underscore, not registered in
run_all_tests.py).

Since auth.current_user() re-reads the user and their team from the
database on every request (so deactivation and role changes take effect
immediately), a test can no longer fake a login by writing claims into
the session alone: a session for a user id with no matching row is
correctly treated as logged out.

sync_session_user(sess) makes the database agree with whatever the test
put in the session: it creates (or updates) a real `users` row with that
id, role, email, name, owner flag and team -- creating the team row too
if the test refers to one that doesn't exist yet. Call it at the end of
a `with client.session_transaction() as sess:` block. Tests that flip
one user id between roles keep working, because each call updates the
row to the role that test asked for.
"""
from datetime import datetime, timezone

from app import database


def sync_session_user(sess) -> None:
    user_id = sess.get("user_id")
    if not user_id:
        return
    team_id = sess.get("team_id")
    now = datetime.now(timezone.utc).isoformat()
    conn = database.get_connection()
    try:
        if team_id is not None and not conn.execute("SELECT 1 FROM teams WHERE id = ?", (team_id,)).fetchone():
            cols = {r[1] for r in conn.execute("PRAGMA table_info(teams)")}
            if "created_at" in cols:
                conn.execute("INSERT INTO teams (id, name, created_at) VALUES (?, ?, ?)", (team_id, f"Test team {team_id}", now))
            else:
                conn.execute("INSERT INTO teams (id, name) VALUES (?, ?)", (team_id, f"Test team {team_id}"))
        email = sess.get("email") or f"user{user_id}@abstractly.test"
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, role, status, created_at, is_owner, team_id)
            VALUES (?, ?, ?, 'x', ?, 'active', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email, name = excluded.name, role = excluded.role,
                status = 'active', is_owner = excluded.is_owner, team_id = excluded.team_id
            """,
            (user_id, email, sess.get("name") or f"User {user_id}", sess.get("role") or "viewer",
             now, 1 if sess.get("is_owner") else 0, team_id),
        )
        conn.commit()
    finally:
        conn.close()
