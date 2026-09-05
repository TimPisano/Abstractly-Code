"""
SQLite persistence for the lease portfolio.

Single table (`leases`): every uploaded document — whether a base lease
or an amendment/addendum — is a row. Amendments are linked to a base
lease via `base_lease_id` rather than treated as standalone documents,
per the "handle amendments as linked documents" requirement. An
"effective" lease (see get_effective_lease) merges a base lease's fields
with its amendments' non-null fields, most recent amendment wins per
field, so portfolio math always reflects the current state of a lease
even after it's been amended.

Uses Python's stdlib sqlite3 — no new dependency — which is the right
scale for a tool meant to hold dozens to low hundreds of leases. See
DECISIONS.md for the full reasoning.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from . import cache

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "lease_portfolio.db")

# Module-level, overridable so tests can point at an isolated temp DB
# without touching the real one.
_db_path = DEFAULT_DB_PATH


def configure(db_path: str) -> None:
    """
    Point the module at a different DB file (used by tests). Also
    clears app/cache.py's in-process cache -- that cache is keyed by
    things like "health_score:6.0" with no database identity baked in,
    so without this, a test suite that creates a fresh temp DB per
    test function (this project's standard pattern -- see
    _fresh_temp_db() in most test files) would leak a cached result
    computed against an EARLIER test's database into a LATER test's,
    since both share the same process and the same cache keys. Real
    api.py request handling never calls configure() mid-run (it's only
    ever called once, at test/process setup), so this has no effect on
    the cache's actual job of avoiding repeat work within one real run.
    """
    global _db_path
    _db_path = db_path
    cache.invalidate_all()


def get_db_path() -> str:
    return _db_path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """
    Adds columns to an already-existing `leases` table that `CREATE
    TABLE IF NOT EXISTS` above can't add on its own — that statement is
    a no-op once the table already exists, so a real database created
    before these columns existed would otherwise never get them. This
    is what makes adding display_name/source_page_start/source_page_end
    safe to ship without dropping or losing any existing row — every
    already-uploaded lease keeps its id, its extracted_fields, and every
    other column exactly as it was; the new columns just come back NULL
    for rows that predate them (handled the same as "not set yet"
    everywhere they're read).
    """
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(leases)").fetchall()}
    new_columns = {
        "display_name": "TEXT",
        "source_page_start": "INTEGER",
        "source_page_end": "INTEGER",
        # Resubmission/versioning (see the "resubmit lease" workflow):
        # status distinguishes the one CURRENT version of a lease from
        # every version a resubmission has since superseded -- every
        # existing row backfills to 'active' (the default), which is
        # correct: nothing was ever superseded before this existed.
        # supersedes_lease_id points at the version this one replaced
        # (NULL for an original upload, never for a superseded one --
        # walking it backward from any version reaches the original).
        # version_number is 1-based and increments per resubmission
        # within one lease's chain, purely for human-facing "Version 2"
        # labeling -- nothing computes from it, it's stored rather than
        # derived so it stays stable even if a version in the middle of
        # a chain is later deleted outright (not just superseded).
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "supersedes_lease_id": "INTEGER",
        "version_number": "INTEGER NOT NULL DEFAULT 1",
        # Async extraction (see api.py's background-processing path): a
        # lease uploaded through the model-backed engine is inserted
        # immediately in 'processing' state and its fields are filled in
        # by a background thread, so the upload request returns right
        # away instead of blocking on a 5-15s-per-lease model call (and
        # instead of risking a gunicorn worker timeout + partial write
        # on a large multi-lease document). Default 'complete' so every
        # existing row, and every fast regex-path insert, is born done
        # with no behavior change. processing_error holds the
        # user-facing reason when status is 'failed'.
        "processing_status": "TEXT NOT NULL DEFAULT 'complete'",
        "processing_error": "TEXT",
    }
    for column, sql_type in new_columns.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE leases ADD COLUMN {column} {sql_type}")


def _migrate_users_table_add_previous_login_at(conn: sqlite3.Connection) -> None:
    """
    Adds `previous_login_at`, distinct from `last_login_at`. The
    daily-briefing endpoint ('what's new since I last logged in') needs
    the login timestamp from BEFORE this session -- but auth_login()
    overwrites last_login_at the moment a session starts, so by the time
    the frontend calls /today, last_login_at already equals "now" and
    would make "since last login" always empty. update_user_last_login()
    shifts the old last_login_at into previous_login_at in the same
    UPDATE, atomically, so this column always holds "the login before
    the current one" for exactly this purpose.
    """
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "previous_login_at" not in existing_columns:
        conn.execute("ALTER TABLE users ADD COLUMN previous_login_at TEXT")


def _migrate_users_table_add_is_owner(conn: sqlite3.Connection) -> None:
    """
    `is_owner` is a completely separate flag from `role`/ROLE_RANK --
    it does NOT sit in the viewer/analyst/admin hierarchy, and
    `role='admin'` never implies it. It gates the owner console
    (business-management routes: every login's usage, suspend/
    reactivate/reset-password on any account, revenue/expenses) --
    power an admin team member should never automatically have. See
    auth.require_owner() and api.py's /owner/* routes. Every existing
    row backfills to 0/false -- correct, since only the operator's own
    account should ever hold this, set explicitly via
    backend/set_owner.py, never through any API route or signup path.
    """
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_owner" not in existing_columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_owner INTEGER NOT NULL DEFAULT 0")


def _migrate_comments_table_add_task_id(conn: sqlite3.Connection) -> None:
    """
    Adds `task_id` so a comment can be attached to a task -- lease_id/
    discrepancy_id already exist; a comment is otherwise assumed to be
    about exactly one of the three (enforced at the API layer, same as
    the existing lease_id/discrepancy_id pair). Not FK'd to tasks(id)
    ON DELETE CASCADE like the other two are -- a task comment is team
    discussion ("checked with the broker, this is intentional") that
    should survive the task itself being deleted later, same "permanent
    record" reasoning already applied to lease_field_edits.task_id.
    """
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(comments)").fetchall()}
    if "task_id" not in existing_columns:
        conn.execute("ALTER TABLE comments ADD COLUMN task_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_task_id ON comments(task_id)")


def _migrate_lease_field_edits_table_add_reverted_at(conn: sqlite3.Connection) -> None:
    """`reverted_at` marks an edit as having been undone (see revert_lease_field_edit) -- kept on the ORIGINAL edit row rather than deleting it, so the audit trail honestly shows both that a correction was made AND that it was later reverted, instead of erasing the fact it ever happened."""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(lease_field_edits)").fetchall()}
    if "reverted_at" not in existing_columns:
        conn.execute("ALTER TABLE lease_field_edits ADD COLUMN reverted_at TEXT")


def _migrate_tasks_table_add_priority(conn: sqlite3.Connection) -> None:
    """`priority` ('normal' | 'high') -- every existing task backfills to 'normal' (the default), correct since nothing was ever marked urgent before this existed."""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "priority" not in existing_columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")


def _migrate_discrepancies_table_drop_lease_fk(conn: sqlite3.Connection) -> None:
    """
    Rebuilds an already-existing `discrepancies` table that still has
    the ORIGINAL `FOREIGN KEY (lease_id) REFERENCES leases(id) ON
    DELETE SET NULL` constraint (and the same for related_lease_id)
    this table shipped with initially, into the corrected schema with
    no such constraint at all.

    That original constraint was a real, live bug, not just a design
    change: a discrepancy is meant to be a PERMANENT record that
    survives its lease being deleted (see this table's own module
    comment above, and the "Discrepancies from deleted leases" fix in
    portfolio_health_score.py) -- but `ON DELETE SET NULL` meant
    deleting a lease silently NULLED OUT every discrepancy's lease_id
    that had ever referenced it, discarding exactly the information
    ("which lease was this about") that made the permanent record
    useful. `CREATE TABLE IF NOT EXISTS` never retroactively fixes an
    already-existing table's constraints, so any database created
    before the FK was removed from this file keeps enforcing the old
    behavior forever unless explicitly migrated -- confirmed this
    exact scenario happening for real, live, in this project's own dev
    database (343 discrepancies silently lost their lease_id this way)
    before this migration was added.

    SQLite has no ALTER TABLE ... DROP CONSTRAINT, so this uses the
    standard rebuild dance: rename the old table aside, create a fresh
    one with the correct (no-FK) shape, copy every row across
    verbatim, drop the old one -- with PRAGMA foreign_keys OFF for the
    duration so SQLite doesn't try to "helpfully" rewrite `comments`'s
    FK text mid-rebuild (it targets `discrepancies` by name, and
    resolves correctly again once the real table exists again under
    that name at the end). A no-op, safe to call every time init_db()
    runs, if the table doesn't exist yet or has already been migrated.
    """
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='discrepancies'"
    ).fetchone()
    if not existing:
        return

    has_old_fk = any(row[2] == "leases" for row in conn.execute("PRAGMA foreign_key_list(discrepancies)"))
    if not has_old_fk:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ALTER TABLE discrepancies RENAME TO discrepancies_pre_fk_migration")
    conn.execute("""
        CREATE TABLE discrepancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discrepancy_type TEXT NOT NULL,
            natural_key TEXT NOT NULL UNIQUE,
            lease_id INTEGER,
            related_lease_id INTEGER,
            category TEXT NOT NULL,
            field TEXT,
            severity TEXT,
            message TEXT NOT NULL,
            details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            first_detected_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO discrepancies (id, discrepancy_type, natural_key, lease_id, related_lease_id,
            category, field, severity, message, details, status, first_detected_at, last_seen_at)
        SELECT id, discrepancy_type, natural_key, lease_id, related_lease_id,
            category, field, severity, message, details, status, first_detected_at, last_seen_at
        FROM discrepancies_pre_fk_migration
    """)
    conn.execute("DROP TABLE discrepancies_pre_fk_migration")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def _seed_first_admin_user(conn: sqlite3.Connection) -> None:
    """
    Migrates the old env-var-only admin account into the real `users`
    table, exactly once, so upgrading from the pre-team-accounts
    version of this app never locks the operator out. No-op if any
    user already exists (this has already run, or an admin was
    created some other way), or if ADMIN_EMAIL/ADMIN_PASSWORD_HASH
    aren't set (a genuinely fresh install with no admin configured
    yet -- nothing to seed).

    ADMIN_PASSWORD_HASH is already a bcrypt hash in exactly the format
    auth.hash_password() produces for any other user, so it's inserted
    directly -- no re-hashing, and this module deliberately doesn't
    import bcrypt itself to re-derive it.

    After this runs once, ADMIN_EMAIL/ADMIN_PASSWORD_HASH have no
    further effect -- the seeded row lives in the database like any
    other user from then on (role can be changed, password reset,
    etc. through the normal `users` functions below).

    Also seeds is_owner=1 on this row. Whoever controls ADMIN_EMAIL/
    ADMIN_PASSWORD_HASH is, by construction, whoever has access to this
    deployment's env vars (e.g. Render's dashboard) -- i.e. the actual
    operator/business owner, not just any team member. This is what
    makes owner access survive a production redeploy on a non-
    persistent-disk deployment (see DEPLOYMENT.md) without a manual
    step: the users table gets wiped and this function re-seeds a
    fresh admin+owner row from the same env vars every time.
    """
    existing = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    if existing:
        return

    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    if not email or not password_hash:
        return

    conn.execute(
        "INSERT INTO users (email, name, password_hash, role, status, created_at, created_by_user_id, is_owner) "
        "VALUES (?, 'Admin', ?, 'admin', 'active', ?, NULL, 1)",
        (email, password_hash, datetime.now(timezone.utc).isoformat()),
    )


def init_db() -> None:
    """Create tables if they don't already exist, and migrate any existing `leases` table to the current schema. Safe to call repeatedly."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                extracted_fields TEXT NOT NULL,
                document_type TEXT NOT NULL DEFAULT 'lease',
                base_lease_id INTEGER,
                date_candidates TEXT,
                display_name TEXT,
                source_page_start INTEGER,
                source_page_end INTEGER,
                FOREIGN KEY (base_lease_id) REFERENCES leases(id)
            )
        """)
        _migrate_schema(conn)
        # get_amendments()'s `WHERE base_lease_id = ?` (called by
        # get_effective_lease/get_effective_fields, both on the
        # single-lease read path AND once per row during a rent-roll
        # import) has no index to use without this -- SQLite doesn't
        # auto-index a bare FOREIGN KEY column, only PRIMARY KEY/UNIQUE
        # ones. Without it, that query full-table-scans `leases` on
        # every call, so cost grows with total row count: importing
        # row N does an O(N) scan just to confirm row N has no
        # amendments yet, making an M-row import O(M^2) overall.
        # Measured directly: a 20,000-row synthetic rent-roll import
        # (not the real 500-unit stress file, which imports in ~2s and
        # was never actually slow) took over 2 minutes and was still
        # climbing before this index existed. `CREATE INDEX IF NOT
        # EXISTS` is safe to run on every init_db() call, including
        # against an already-populated table from before this fix.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leases_base_lease_id ON leases(base_lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leases_supersedes_lease_id ON leases(supersedes_lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leases_status ON leases(status)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS waitlist_signups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                lease_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (lease_id) REFERENCES leases(id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lease_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lease_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (lease_id) REFERENCES leases(id) ON DELETE CASCADE,
                UNIQUE (lease_id, tag)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discrepancies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discrepancy_type TEXT NOT NULL,
                natural_key TEXT NOT NULL UNIQUE,
                lease_id INTEGER,
                related_lease_id INTEGER,
                category TEXT NOT NULL,
                field TEXT,
                severity TEXT,
                message TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                first_detected_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
        """)
        _migrate_discrepancies_table_drop_lease_fk(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discrepancy_resolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discrepancy_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                correct_source TEXT,
                note TEXT NOT NULL,
                resolved_by TEXT NOT NULL,
                resolved_by_email TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (discrepancy_id) REFERENCES discrepancies(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                natural_key TEXT NOT NULL UNIQUE,
                lease_id INTEGER,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                dismissed_by TEXT,
                dismissed_at TEXT,
                dismissal_note TEXT,
                first_detected_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lease_id INTEGER,
                discrepancy_id INTEGER,
                author_name TEXT NOT NULL,
                author_email TEXT,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (lease_id) REFERENCES leases(id) ON DELETE CASCADE,
                FOREIGN KEY (discrepancy_id) REFERENCES discrepancies(id) ON DELETE CASCADE
            )
        """)
        _migrate_comments_table_add_task_id(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                created_by_user_id INTEGER,
                last_login_at TEXT,
                FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        _migrate_users_table_add_previous_login_at(conn)
        _migrate_users_table_add_is_owner(conn)
        _seed_first_admin_user(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id)")
        # Owner-console finance tracking (see api.py's /owner/revenue,
        # /owner/expenses). external_source/external_id are nullable and
        # unused today (no billing integration exists yet -- every row
        # right now is manually entered) but let a future integration
        # (e.g. a Stripe webhook) insert rows idempotently later without
        # a schema change: the partial UNIQUE index below only applies
        # when both are non-null, so manual entries (which leave them
        # NULL) are never blocked by it.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS revenue_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                amount REAL NOT NULL,
                source TEXT NOT NULL,
                note TEXT,
                external_source TEXT,
                external_id TEXT,
                created_at TEXT NOT NULL,
                created_by_user_id INTEGER,
                FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_revenue_entries_external "
            "ON revenue_entries(external_source, external_id) "
            "WHERE external_source IS NOT NULL AND external_id IS NOT NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_revenue_entries_date ON revenue_entries(entry_date)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expense_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                note TEXT,
                external_source TEXT,
                external_id TEXT,
                created_at TEXT NOT NULL,
                created_by_user_id INTEGER,
                FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_expense_entries_external "
            "ON expense_entries(external_source, external_id) "
            "WHERE external_source IS NOT NULL AND external_id IS NOT NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_expense_entries_date ON expense_entries(entry_date)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_key TEXT NOT NULL,
                lease_id INTEGER,
                discrepancy_id INTEGER,
                property_address TEXT,
                assigned_to_user_id INTEGER NOT NULL,
                assigned_by_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'assigned',
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (target_type, target_key),
                FOREIGN KEY (assigned_to_user_id) REFERENCES users(id),
                FOREIGN KEY (assigned_by_user_id) REFERENCES users(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assignments_assigned_to ON assignments(assigned_to_user_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assistant_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                response_type TEXT NOT NULL,
                answer TEXT NOT NULL,
                route TEXT,
                route_params TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_conversations_user_id ON assistant_conversations(user_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_type TEXT NOT NULL,
                name TEXT,
                created_by_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (created_by_user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_thread_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                last_read_at TEXT,
                UNIQUE (thread_id, user_id),
                FOREIGN KEY (thread_id) REFERENCES message_threads(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_participants_user_id ON message_thread_participants(user_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                sender_user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES message_threads(id) ON DELETE CASCADE,
                FOREIGN KEY (sender_user_id) REFERENCES users(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_thread_id_created_at ON messages(thread_id, created_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS linked_email_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                provider_email TEXT NOT NULL,
                access_token_encrypted TEXT NOT NULL,
                refresh_token_encrypted TEXT NOT NULL,
                token_expires_at TEXT NOT NULL,
                scopes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (user_id, provider),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                assigned_to_user_id INTEGER,
                created_by_user_id INTEGER NOT NULL,
                lease_id INTEGER,
                discrepancy_id INTEGER,
                property_address TEXT,
                source_type TEXT,
                source_natural_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (assigned_to_user_id) REFERENCES users(id),
                FOREIGN KEY (created_by_user_id) REFERENCES users(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to_user_id ON tasks(assigned_to_user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lease_field_edits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lease_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,
                edited_by TEXT NOT NULL,
                edited_by_email TEXT,
                note TEXT,
                task_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (lease_id) REFERENCES leases(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_field_edits_lease_id ON lease_field_edits(lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_field_edits_task_id ON lease_field_edits(task_id)")
        _migrate_lease_field_edits_table_add_reverted_at(conn)
        _migrate_tasks_table_add_priority(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_extraction_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'lease_abstraction',
                engine TEXT NOT NULL,
                model TEXT,
                status TEXT NOT NULL,
                lease_id INTEGER,
                field_count INTEGER,
                found_count INTEGER,
                high_count INTEGER,
                medium_count INTEGER,
                low_count INTEGER,
                not_found_count INTEGER,
                latency_ms INTEGER,
                input_tokens INTEGER,
                output_tokens INTEGER,
                error_message TEXT,
                detail TEXT,
                FOREIGN KEY (lease_id) REFERENCES leases(id) ON DELETE SET NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_extraction_runs_created_at ON ai_extraction_runs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_extraction_runs_lease_id ON ai_extraction_runs(lease_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                round_label TEXT NOT NULL,
                model TEXT,
                prompt_version TEXT,
                corpus_seed INTEGER,
                corpus_size INTEGER,
                documents INTEGER,
                fields_evaluated INTEGER,
                overall_accuracy REAL,
                high_conf_wrong_count INTEGER,
                high_conf_wrong_rate REAL,
                calibration_gap REAL,
                p_correct_given_high REAL,
                p_correct_given_low REAL,
                changed_this_round TEXT,
                report TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_training_rounds_created_at ON training_rounds(created_at)")

        # ---- Hardening pass (perf): indexes for lookups that were
        # full-table-scanning. SQLite does NOT auto-index a plain
        # FOREIGN KEY column, and a `WHERE lower(col) = ?` predicate
        # can't use a plain index -- the matching queries were changed
        # to `col = ? COLLATE NOCASE` so these NOCASE indexes apply.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_by_user_id ON tasks(created_by_user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_field_edits_edited_by_email ON lease_field_edits(edited_by_email COLLATE NOCASE)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discrepancy_resolutions_discrepancy_id ON discrepancy_resolutions(discrepancy_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discrepancy_resolutions_resolved_by_email ON discrepancy_resolutions(resolved_by_email COLLATE NOCASE)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_author_email ON comments(author_email COLLATE NOCASE)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_lease_id ON comments(lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discrepancies_lease_id ON discrepancies(lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discrepancies_related_lease_id ON discrepancies(related_lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discrepancies_status ON discrepancies(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_lease_id ON alerts(lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON activity_log(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_lease_id ON activity_log(lease_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lease_tags_tag ON lease_tags(tag)")

        conn.commit()
    finally:
        conn.close()


def reset_db() -> None:
    """Drop and recreate all tables. Used by tests for a clean slate."""
    conn = get_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS lease_tags")
        conn.execute("DROP TABLE IF EXISTS comments")
        conn.execute("DROP TABLE IF EXISTS alerts")
        conn.execute("DROP TABLE IF EXISTS discrepancy_resolutions")
        conn.execute("DROP TABLE IF EXISTS discrepancies")
        conn.execute("DROP TABLE IF EXISTS leases")
        conn.execute("DROP TABLE IF EXISTS waitlist_signups")
        conn.execute("DROP TABLE IF EXISTS activity_log")
        conn.execute("DROP TABLE IF EXISTS users")
        conn.execute("DROP TABLE IF EXISTS assignments")
        conn.execute("DROP TABLE IF EXISTS assistant_conversations")
        conn.execute("DROP TABLE IF EXISTS messages")
        conn.execute("DROP TABLE IF EXISTS message_thread_participants")
        conn.execute("DROP TABLE IF EXISTS message_threads")
        conn.execute("DROP TABLE IF EXISTS linked_email_accounts")
        conn.execute("DROP TABLE IF EXISTS oauth_states")
        conn.execute("DROP TABLE IF EXISTS tasks")
        conn.execute("DROP TABLE IF EXISTS lease_field_edits")
        conn.execute("DROP TABLE IF EXISTS revenue_entries")
        conn.execute("DROP TABLE IF EXISTS expense_entries")
        conn.execute("DROP TABLE IF EXISTS ai_extraction_runs")
        conn.execute("DROP TABLE IF EXISTS training_rounds")
        conn.commit()
    finally:
        conn.close()
    init_db()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["extracted_fields"] = json.loads(d["extracted_fields"])
    d["date_candidates"] = json.loads(d["date_candidates"]) if d.get("date_candidates") else None
    return d


def insert_lease(
    filename: str,
    extracted_fields: Dict[str, Any],
    document_type: str = "lease",
    base_lease_id: Optional[int] = None,
    date_candidates: Optional[Dict[str, Any]] = None,
    display_name: Optional[str] = None,
    source_page_start: Optional[int] = None,
    source_page_end: Optional[int] = None,
    status: str = "active",
    supersedes_lease_id: Optional[int] = None,
    version_number: int = 1,
    processing_status: str = "complete",
) -> int:
    """
    Persist one extracted document. Returns its new lease id.

    `date_candidates` (shape: {"start": [...], "end": [...]}, from
    FieldExtractor.find_all_date_candidates) is stored alongside the
    extracted fields specifically so risk_analysis's cross-section
    date-conflict check can run later without re-parsing the PDF —
    only the extracted text is available at upload time, not after.

    `display_name` is the lease's human-facing name (auto-generated at
    upload time by the caller — see api.py's _default_lease_name — and
    editable later via update_lease_display_name). `source_page_start`/
    `source_page_end` record which page range of the ORIGINAL uploaded
    PDF this lease came from, for leases split out of a multi-lease
    document (FieldExtractor.extract_multiple_leases) — both None for a
    lease that was already a single-lease PDF, or for an amendment.

    `status`/`supersedes_lease_id`/`version_number` are only ever
    non-default when this call comes from the resubmission flow (see
    api.py's resubmit_lease) -- every other caller (normal upload,
    batch upload, rent-roll import, amendment) leaves them at the
    defaults, producing an ordinary standalone active v1 lease exactly
    as before this feature existed.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO leases (filename, uploaded_at, extracted_fields, document_type, base_lease_id, "
            "date_candidates, display_name, source_page_start, source_page_end, status, supersedes_lease_id, version_number, processing_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                filename,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(extracted_fields),
                document_type,
                base_lease_id,
                json.dumps(date_candidates) if date_candidates is not None else None,
                display_name,
                source_page_start,
                source_page_end,
                status,
                supersedes_lease_id,
                version_number,
                processing_status,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def finalize_lease_processing(
    lease_id: int,
    *,
    status: str,
    extracted_fields: Optional[Dict[str, Any]] = None,
    date_candidates: Optional[Dict[str, Any]] = None,
    display_name: Optional[str] = None,
    error: Optional[str] = None,
) -> bool:
    """
    Called by the background extraction thread (see api.py) to fill in a
    lease that was inserted in 'processing' state.

      status='complete' -> writes extracted_fields / date_candidates /
        display_name and clears any error.
      status='failed'   -> leaves the placeholder fields as-is and
        records `error` (a plain, user-facing message) so the detail
        view can show why, and the row can be deleted or the upload
        retried. Never leaves a half-written field set.

    Returns False if the lease id no longer exists (e.g. deleted while
    processing).
    """
    sets = ["processing_status = ?", "processing_error = ?"]
    params: List[Any] = [status, error]
    if extracted_fields is not None:
        sets.append("extracted_fields = ?")
        params.append(json.dumps(extracted_fields))
    if date_candidates is not None:
        sets.append("date_candidates = ?")
        params.append(json.dumps(date_candidates))
    if display_name is not None:
        sets.append("display_name = ?")
        params.append(display_name)
    params.append(lease_id)

    conn = get_connection()
    try:
        cur = conn.execute(f"UPDATE leases SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def fail_orphaned_processing_leases() -> int:
    """
    Mark every lease still in 'processing' state as 'failed' -- called
    once at process startup. A background extraction thread doesn't
    survive a restart/redeploy, so any lease that was mid-extraction
    would otherwise sit 'processing' forever. Returns how many were
    reset. Safe/cheap to run on every boot (usually 0 rows).
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE leases SET processing_status = 'failed', "
            "processing_error = 'Processing was interrupted by a server restart. Delete this and upload again.' "
            "WHERE processing_status = 'processing'"
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def update_lease_display_name(lease_id: int, display_name: str) -> bool:
    """Renames a lease. Returns False if no such id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE leases SET display_name = ? WHERE id = ?",
            (display_name, lease_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Lease resubmission / versioning: a resubmission inserts a brand-new
# lease row (via insert_lease's status/supersedes_lease_id/version_number
# params) rather than mutating the old one in place, then this section's
# functions link the two together and carry every reference that
# conceptually followed "the lease" (not "this specific extraction")
# over to the new row -- see api.py's resubmit_lease for the full flow.
# ----------------------------------------------------------------------

def supersede_lease(lease_id: int) -> bool:
    """Marks a lease 'superseded' -- excluded from get_all_leases/get_all_effective_leases by default, but still fetchable directly by id (get_lease never filters by status), so an old version stays permanently retrievable, just no longer 'the' current one. Returns False if no such id."""
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE leases SET status = 'superseded' WHERE id = ?", (lease_id,))
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def get_lease_version_chain(lease_id: int) -> List[Dict[str, Any]]:
    """
    Every version of this lease, oldest first, regardless of which
    version id was passed in -- walks supersedes_lease_id backward to
    find the original (v1), then forward from there to collect every
    later resubmission, so asking about v1, v2, or the current version
    all return the identical full chain. A lease with no resubmission
    history returns a list of exactly one (itself).
    """
    conn = get_connection()
    try:
        current = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if current is None:
            return []
        current = dict(current)

        # Walk backward to the root (v1).
        node = current
        while node.get("supersedes_lease_id") is not None:
            prior = conn.execute("SELECT * FROM leases WHERE id = ?", (node["supersedes_lease_id"],)).fetchone()
            if prior is None:
                break
            node = dict(prior)

        # Walk forward from the root, following whichever lease
        # supersedes each node in turn, until nothing supersedes the
        # current end of the chain.
        chain_rows = [node]
        while True:
            nxt = conn.execute("SELECT * FROM leases WHERE supersedes_lease_id = ?", (chain_rows[-1]["id"],)).fetchone()
            if nxt is None:
                break
            chain_rows.append(dict(nxt))

        return [_row_to_dict_from_plain(r) for r in chain_rows]
    finally:
        conn.close()


def _row_to_dict_from_plain(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Same JSON-decoding _row_to_dict does for a sqlite3.Row, but for a plain dict already pulled out of one (get_lease_version_chain builds plain dicts while walking, since it needs to re-fetch rows across a loop the original sqlite3.Row objects don't survive)."""
    d = dict(row_dict)
    d["extracted_fields"] = json.loads(d["extracted_fields"])
    d["date_candidates"] = json.loads(d["date_candidates"]) if d.get("date_candidates") else None
    return d


def _repointed_natural_key(discrepancy_type: str, natural_key: str, old_lease_id: int, new_lease_id: int) -> str:
    """
    natural_key is a formatted string that embeds the lease id as
    literal text (see discrepancies.py's own docstring on why: it's
    what makes a discrepancy "the same one" across recomputations). A
    plain column repoint of discrepancies.lease_id is not enough by
    itself -- a fresh sync pass derives ITS natural_key from the
    CURRENT lease id and can only find (and update in place, rather
    than duplicate) an existing row if that row's natural_key text
    already says the same id. This regenerates it precisely, matching
    each type's own format in discrepancies.py exactly:
      lease_risk_flag:      "lease_risk:{lease_id}:{category}:{field}:{n}"
      cross_lease_mismatch: "cross_lease:{lo}:{hi}:{field}" (sorted pair)
                          or "cross_lease:{lease_id}:none:{field}"
    Only these two types are ever passed in here -- see
    repoint_lease_references, which only calls this for the types the
    resubmission re-sync pass actually recomputes.
    """
    parts = natural_key.split(":")
    if discrepancy_type == "lease_risk_flag":
        if parts[1] == str(old_lease_id):
            parts[1] = str(new_lease_id)
        return ":".join(parts)

    # cross_lease_mismatch
    if parts[2] == "none":
        if parts[1] == str(old_lease_id):
            parts[1] = str(new_lease_id)
        return ":".join(parts)
    lo_id, hi_id = int(parts[1]), int(parts[2])
    other_id = hi_id if lo_id == old_lease_id else lo_id
    new_lo, new_hi = sorted((new_lease_id, other_id))
    parts[1], parts[2] = str(new_lo), str(new_hi)
    return ":".join(parts)


def repoint_lease_references(old_lease_id: int, new_lease_id: int) -> None:
    """
    Carries forward everything that's conceptually about "this lease"
    (not about the specific extraction that produced the old row) from
    the superseded version to its replacement: discrepancies, tags,
    comments, and any assignment (ownership) record. Called once,
    right after the new lease row is inserted and before it's synced
    against risk analysis -- see resubmit_lease in api.py.

    Deliberately does NOT repoint amendments (base_lease_id) onto the
    new lease -- a real bug this used to have, found live via the
    resubmit-a-corrected-file workflow: get_effective_fields' "latest
    non-null amendment wins" rule means a repointed OLD amendment would
    keep silently overriding the very field the resubmission was
    correcting, on every future read, defeating the entire point of
    resubmitting a corrected document. An amendment is a partial
    addendum to a SPECIFIC prior document; when that document itself is
    wholesale replaced by a resubmission, the amendment's relevance is
    genuinely superseded too (the new document is the corrected,
    complete, current statement of terms) -- so it stays exactly where
    it is, attached to the now-archived old version, remaining part of
    THAT version's own history (still viewable via the old lease's own
    effective fields, or the lease's version-history view) without
    bleeding into what the new current version shows.

    Only discrepancies of type lease_risk_flag / cross_lease_mismatch
    get their natural_key regenerated (see _repointed_natural_key) --
    those are the only two types the resubmission's re-sync pass
    actually recomputes, so they're the only two where a fresh sync
    needs to find these rows by natural_key to reconcile them.
    rent_roll_reconciliation / t12_reconciliation discrepancies are
    deliberately left untouched entirely (neither lease_id nor
    natural_key) -- repointing lease_id alone without also fixing
    natural_key would leave a row whose two identifying fields
    disagree, which is worse than leaving both pointed at the archived
    version; re-running the rent-roll/T12 reconciliation that actually
    produced them (a separate upload, not part of resubmitting a lease
    PDF) is what would properly re-evaluate those, same as before this
    feature existed.

    Also deliberately NOT repointed: activity_log entries (an old entry
    like "uploaded original.pdf" is a true historical fact about the
    OLD row and would become false if rewritten to claim it happened to
    the new one) and alerts (same natural-key-disagreement reasoning as
    rent_roll_reconciliation above -- regenerated wholesale by the
    existing POST /alerts/generate pass instead).
    """
    conn = get_connection()
    try:
        affected = conn.execute(
            "SELECT * FROM discrepancies WHERE lease_id = ? OR related_lease_id = ?",
            (old_lease_id, old_lease_id),
        ).fetchall()
        for row in affected:
            row = dict(row)
            if row["discrepancy_type"] not in ("lease_risk_flag", "cross_lease_mismatch"):
                continue
            new_lease_id_col = new_lease_id if row["lease_id"] == old_lease_id else row["lease_id"]
            new_related_id_col = new_lease_id if row["related_lease_id"] == old_lease_id else row["related_lease_id"]
            new_natural_key = _repointed_natural_key(row["discrepancy_type"], row["natural_key"], old_lease_id, new_lease_id)
            conn.execute(
                "UPDATE discrepancies SET lease_id = ?, related_lease_id = ?, natural_key = ? WHERE id = ?",
                (new_lease_id_col, new_related_id_col, new_natural_key, row["id"]),
            )

        conn.execute("UPDATE lease_tags SET lease_id = ? WHERE lease_id = ?", (new_lease_id, old_lease_id))
        conn.execute("UPDATE comments SET lease_id = ? WHERE lease_id = ?", (new_lease_id, old_lease_id))
        conn.execute(
            "UPDATE assignments SET lease_id = ?, target_key = ? WHERE lease_id = ? AND target_type = 'lease'",
            (new_lease_id, str(new_lease_id), old_lease_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_stale_open_discrepancies_for_lease(lease_id: int, discrepancy_types: List[str], keep_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Open discrepancies of the given type(s) attached to this lease
    (as either lease_id or related_lease_id) that were NOT among the
    ids a fresh sync pass just touched -- i.e. conditions that used to
    be flagged and are no longer being detected, the auto-resolve
    candidates after a resubmission. `discrepancy_types` must be scoped
    to exactly the types that fresh sync pass actually recomputes
    (lease_risk_flag, cross_lease_mismatch) -- a type the sync pass
    never touches in the first place (rent_roll_reconciliation,
    t12_reconciliation) would look "stale" by this same test on every
    single call, which is not the same thing as "no longer a problem".
    """
    if not discrepancy_types:
        return []
    conn = get_connection()
    try:
        type_placeholders = ",".join("?" for _ in discrepancy_types)
        if keep_ids:
            keep_placeholders = ",".join("?" for _ in keep_ids)
            query = (
                f"SELECT * FROM discrepancies WHERE (lease_id = ? OR related_lease_id = ?) "
                f"AND status = 'open' AND discrepancy_type IN ({type_placeholders}) "
                f"AND id NOT IN ({keep_placeholders})"
            )
            params = [lease_id, lease_id, *discrepancy_types, *keep_ids]
        else:
            query = (
                f"SELECT * FROM discrepancies WHERE (lease_id = ? OR related_lease_id = ?) "
                f"AND status = 'open' AND discrepancy_type IN ({type_placeholders})"
            )
            params = [lease_id, lease_id, *discrepancy_types]
        rows = conn.execute(query, params).fetchall()
        return [_discrepancy_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Manual field edits: a human directly correcting an extracted value
# (as opposed to a new document -- an amendment -- superseding it, or a
# whole new resubmitted lease version). Mutates the target lease row's
# extracted_fields in place -- see update_lease_field's own docstring
# for why this is a real data change, not a cosmetic overlay, and
# get_lease_field_edits for the audit trail this produces.
# ----------------------------------------------------------------------

def update_lease_field(
    lease_id: int,
    field_name: str,
    value: Optional[str],
    edited_by: str,
    edited_by_email: Optional[str] = None,
    confidence: str = "high",
    note: Optional[str] = None,
    task_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Overwrites one field's entry on this exact lease row (base lease OR
    amendment -- callers pass whichever document currently governs the
    EFFECTIVE value for this field, see api.py's PATCH .../fields/<name>
    route) with {"value": value, "source": None, "confidence": confidence,
    "manually_verified": True}. `source` is deliberately None, not a
    fabricated page/quote -- there IS no document citation for a value a
    human typed directly; existing renderers (see verify-popover.js's
    own docstring: "null/undefined renders an honest empty state")
    already handle a null source correctly, and the real provenance
    (who, when, from what) lives in the lease_field_edits row this also
    writes, not smuggled into the citation shape. `manually_verified`
    lets a future caller distinguish "a human confirmed this field is
    genuinely absent" (value=None but manually_verified=True) from
    "extraction never found it" (value=None, no such flag) -- the same
    distinction requirement 5 of the resubmission-adjacent editing
    feature cares about: a "Not found" that's been human-checked is a
    different, more trustworthy state than one that hasn't.

    Because this mutates extracted_fields on the lease row directly
    (not a new amendment layered on top), every downstream reader that
    already goes through get_effective_fields/get_effective_lease/
    get_all_effective_leases -- the dashboard, exports, risk analysis,
    discrepancy sync -- picks up the change on its very next read, with
    no separate propagation step required. That's what makes this a
    real edit to "the actual lease record," not a cosmetic overlay.

    Returns the new field entry, or None if lease_id doesn't exist.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT extracted_fields FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if row is None:
            return None
        fields = json.loads(row["extracted_fields"])
        old_entry = fields.get(field_name) or {"value": None, "source": None, "confidence": None}
        new_entry = {"value": value, "source": None, "confidence": confidence, "manually_verified": True}
        fields[field_name] = new_entry

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE leases SET extracted_fields = ? WHERE id = ?", (json.dumps(fields), lease_id))
        conn.execute(
            "INSERT INTO lease_field_edits (lease_id, field_name, old_value, new_value, edited_by, "
            "edited_by_email, note, task_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lease_id, field_name, json.dumps(old_entry), json.dumps(new_entry), edited_by, edited_by_email, note, task_id, now),
        )
        conn.commit()
        return new_entry
    finally:
        conn.close()


def mark_field_verified(
    lease_id: int,
    field_name: str,
    edited_by: str,
    edited_by_email: Optional[str] = None,
    note: Optional[str] = None,
    task_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    "A human looked at this exact extracted value and confirmed it's
    correct" -- upgrades confidence to "high" and sets manually_verified,
    WITHOUT touching value or source, unlike update_lease_field above
    (which is for correcting a wrong value, and always nulls source
    since there's no document citation for text a human just typed).
    Here the original citation is still accurate -- the human confirmed
    the extractor read it right -- so erasing it would throw away real
    provenance for no reason. Any now-stale validation_note/
    validation_reason (e.g. "verify against the source document" or an
    OCR-clarity flag) is cleared, since a human just did exactly that.

    Returns None (no-op, nothing written) if this field has no value to
    verify -- confirming an absence isn't what this is for; see
    update_lease_field's docstring for how a genuine "checked, it's not
    in the lease" gets recorded instead. Also a no-op-but-still-returns
    the current entry if it's already high-confidence + manually
    verified, so callers don't need to check that themselves first.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT extracted_fields FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if row is None:
            return None
        fields = json.loads(row["extracted_fields"])
        old_entry = fields.get(field_name)
        if not old_entry or old_entry.get("value") is None:
            return None
        if old_entry.get("confidence") == "high" and old_entry.get("manually_verified"):
            return old_entry  # already verified -- nothing to change

        new_entry = {k: v for k, v in old_entry.items() if k not in ("validation_note", "validation_reason")}
        new_entry["confidence"] = "high"
        new_entry["manually_verified"] = True
        fields[field_name] = new_entry

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE leases SET extracted_fields = ? WHERE id = ?", (json.dumps(fields), lease_id))
        conn.execute(
            "INSERT INTO lease_field_edits (lease_id, field_name, old_value, new_value, edited_by, "
            "edited_by_email, note, task_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lease_id, field_name, json.dumps(old_entry), json.dumps(new_entry), edited_by, edited_by_email, note, task_id, now),
        )
        conn.commit()
        return new_entry
    finally:
        conn.close()


def get_lease_field_edits(lease_id: Optional[int] = None, field_name: Optional[str] = None, task_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Oldest first -- a correction history reads top-to-bottom like a timeline, same convention as get_discrepancy_resolutions. Any combination of filters may be applied together; at least one should normally be given or this returns every edit ever made across the whole portfolio."""
    conn = get_connection()
    try:
        clauses, params = [], []
        if lease_id is not None:
            clauses.append("lease_id = ?")
            params.append(lease_id)
        if field_name is not None:
            clauses.append("field_name = ?")
            params.append(field_name)
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM lease_field_edits {where} ORDER BY created_at ASC, id ASC", params
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["old_value"] = json.loads(d["old_value"])
            d["new_value"] = json.loads(d["new_value"])
            results.append(d)
        return results
    except OverflowError:
        return []
    finally:
        conn.close()


def get_lease_field_edit(edit_id: int) -> Optional[Dict[str, Any]]:
    """Single edit by id, decoded -- what api.py's undo route checks eligibility against (age window, whether a newer edit has superseded it, whether the task it happened under has since completed) before calling revert_lease_field_edit."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM lease_field_edits WHERE id = ?", (edit_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["old_value"] = json.loads(d["old_value"])
        d["new_value"] = json.loads(d["new_value"])
        return d
    except OverflowError:
        return None
    finally:
        conn.close()


def revert_lease_field_edit(edit_id: int, reverted_by: str, reverted_by_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Undoes one specific field edit: restores the field on its lease row
    to `old_value` (the value it held right before that edit), marks
    the ORIGINAL edit row `reverted_at` (never deleted -- see
    _migrate_lease_field_edits_table_add_reverted_at), and inserts a
    NEW lease_field_edits row for the revert itself. The audit trail
    stays a complete, append-only timeline this way -- "edited to X,
    then undone back to Y" -- rather than rewriting history to look
    like the original edit never happened.

    Whether this specific edit is actually eligible to be undone (not
    already reverted, not superseded by a later edit to the same
    field) is the API layer's job to check first, same as every other
    validation split in this module -- this function trusts the caller
    and just performs the revert.

    Returns the restored field entry (old_value), or None if edit_id
    or its lease no longer exist.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM lease_field_edits WHERE id = ?", (edit_id,)).fetchone()
        if row is None:
            return None
        edit = dict(row)
        old_value = json.loads(edit["old_value"])

        lease_row = conn.execute("SELECT extracted_fields FROM leases WHERE id = ?", (edit["lease_id"],)).fetchone()
        if lease_row is None:
            return None
        fields = json.loads(lease_row["extracted_fields"])
        current_value = fields.get(edit["field_name"])
        fields[edit["field_name"]] = old_value

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE leases SET extracted_fields = ? WHERE id = ?", (json.dumps(fields), edit["lease_id"]))
        conn.execute("UPDATE lease_field_edits SET reverted_at = ? WHERE id = ?", (now, edit_id))
        conn.execute(
            "INSERT INTO lease_field_edits (lease_id, field_name, old_value, new_value, edited_by, "
            "edited_by_email, note, task_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (edit["lease_id"], edit["field_name"], json.dumps(current_value), json.dumps(old_value),
             reverted_by, reverted_by_email, f"Undo of edit #{edit_id}", edit["task_id"], now),
        )
        conn.commit()
        return old_value
    finally:
        conn.close()


def get_lease(lease_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        return _row_to_dict(row) if row else None
    except OverflowError:
        # SQLite's INTEGER column is a signed 64-bit int; an id outside
        # that range (e.g. from a malicious or malformed URL — Flask's
        # <int:lease_id> converter accepts any Python int, unbounded)
        # can never match a real row, so treat it the same as "not
        # found" rather than letting the OverflowError propagate as a
        # 500.
        return None
    finally:
        conn.close()


def get_leases_by_ids(lease_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Batched version of get_lease for many ids at once — {id: lease}. Same OverflowError safety as get_lease (an out-of-range id just won't match any row)."""
    if not lease_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in lease_ids)
        rows = conn.execute(f"SELECT * FROM leases WHERE id IN ({placeholders})", lease_ids).fetchall()
        return {row["id"]: _row_to_dict(row) for row in rows}
    except OverflowError:
        return {}
    finally:
        conn.close()


def get_all_leases(document_type: Optional[str] = "lease", include_superseded: bool = False) -> List[Dict[str, Any]]:
    """
    Base leases only by default (document_type='lease'), ordered by
    upload time. Pass document_type=None to include amendments too.

    Excludes superseded lease versions by default -- a resubmitted-over
    version should behave as if it doesn't exist for every ordinary
    "list the leases" caller (dashboard, exports, portfolio-wide
    computations), same as this function's role before versioning
    existed. Pass include_superseded=True for the version-history view,
    which needs every version, current or not.
    """
    conn = get_connection()
    try:
        clauses, params = [], []
        if document_type is not None:
            clauses.append("document_type = ?")
            params.append(document_type)
        if not include_superseded:
            clauses.append("status != 'superseded'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(f"SELECT * FROM leases {where} ORDER BY uploaded_at", params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_lease(lease_id: int) -> None:
    """Deletes a lease and any amendments linked to it."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM leases WHERE base_lease_id = ?", (lease_id,))
        conn.execute("DELETE FROM leases WHERE id = ?", (lease_id,))
        conn.commit()
    except OverflowError:
        # An out-of-range id (see get_lease) can never match a real
        # row, so this is a no-op rather than a 500.
        pass
    finally:
        conn.close()


def get_amendments(base_lease_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM leases WHERE base_lease_id = ? ORDER BY uploaded_at",
            (base_lease_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def get_amendments_for_leases(base_lease_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Batched version of get_amendments for many base lease ids at once — {base_lease_id: [amendments]} — used by portfolio_health_score's data-freshness component so it isn't one query per amended lease."""
    if not base_lease_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in base_lease_ids)
        rows = conn.execute(
            f"SELECT * FROM leases WHERE base_lease_id IN ({placeholders}) ORDER BY uploaded_at",
            base_lease_ids,
        ).fetchall()
        result: Dict[int, List[Dict[str, Any]]] = {bid: [] for bid in base_lease_ids}
        for row in rows:
            result[row["base_lease_id"]].append(_row_to_dict(row))
        return result
    except OverflowError:
        return {}
    finally:
        conn.close()


def _tag_field_document(field_data: Any, document: Dict[str, Any]) -> Any:
    """
    Returns a copy of one field's value-dict with a `document` key added
    (`{"lease_id", "filename"}` of whichever document this value actually
    came from) -- never mutates the caller's dict. Only added when there's
    a real value to attribute; a not-found field has no source document to
    name, same reasoning as `source`/`reason` staying null in that case.
    """
    if not isinstance(field_data, dict):
        return field_data
    entry = dict(field_data)
    if entry.get("value") is not None:
        entry["document"] = {"lease_id": document["id"], "filename": document["filename"]}
    return entry


def get_effective_fields(lease_id: int) -> Optional[Dict[str, Any]]:
    """
    Merge a base lease's extracted_fields with its amendments' non-null
    fields — later-uploaded amendments take priority per field. Returns
    None if lease_id doesn't exist. This is what portfolio metrics, risk
    analysis, comparison, and the Q&A engine should read from, not the
    raw base lease alone, so an amendment (e.g. a rent increase
    addendum) is actually reflected in portfolio math.

    Each returned field also carries a `document` key naming which
    document (base lease or a specific amendment) it actually came
    from -- necessary once a lease has amendments, since two documents
    can each state the same field and only one wins per field.
    """
    base = get_lease(lease_id)
    if not base:
        return None

    effective = {name: _tag_field_document(data, base) for name, data in base["extracted_fields"].items()}
    for amendment in get_amendments(lease_id):
        for field_name, field_data in amendment["extracted_fields"].items():
            if isinstance(field_data, dict) and field_data.get("value") is not None:
                effective[field_name] = _tag_field_document(field_data, amendment)
    return effective


def get_effective_lease(lease_id: int) -> Optional[Dict[str, Any]]:
    """Like get_lease, but with extracted_fields replaced by the effective (amendment-merged) fields."""
    base = get_lease(lease_id)
    if not base:
        return None
    effective_fields = get_effective_fields(lease_id)
    result = dict(base)
    result["extracted_fields"] = effective_fields
    result["amendment_count"] = len(get_amendments(lease_id))
    return result


def get_all_effective_leases() -> List[Dict[str, Any]]:
    """
    All base leases (not amendments) with their fields amendment-merged
    -- same output shape as calling get_effective_lease() on every base
    lease individually, but in a single query instead of one connection
    per lease per amendment lookup.

    This function is the read path behind nearly every portfolio-wide
    endpoint (dashboard, risks, trends, health-score, alerts, Q&A,
    investment memos, ...), so its cost multiplies across the whole
    app. The naive per-lease version (get_effective_lease in a loop)
    opens 4 new SQLite connections per lease -- get_lease x2,
    get_amendments x2 -- which is fine for a handful of leases but was
    measured at ~1.7s for 831 leases (a real rent-roll-import-scale
    portfolio) purely from connection/round-trip overhead, well before
    the number of leases gets anywhere close to what would actually
    strain SQLite itself. Fetching every lease (base + amendments) in
    one query and merging in Python removes the N+1 pattern entirely.
    """
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM leases ORDER BY uploaded_at").fetchall()
    finally:
        conn.close()

    all_leases = [_row_to_dict(r) for r in rows]
    amendments_by_base: Dict[int, List[Dict[str, Any]]] = {}
    for lease in all_leases:
        if lease["document_type"] != "lease" and lease.get("base_lease_id") is not None:
            amendments_by_base.setdefault(lease["base_lease_id"], []).append(lease)

    results = []
    for base in all_leases:
        if base["document_type"] != "lease":
            continue
        if base.get("status") == "superseded":
            continue
        amendments = amendments_by_base.get(base["id"], [])
        effective = dict(base["extracted_fields"])
        for amendment in amendments:
            for field_name, field_data in amendment["extracted_fields"].items():
                if isinstance(field_data, dict) and field_data.get("value") is not None:
                    effective[field_name] = field_data
        result = dict(base)
        result["extracted_fields"] = effective
        result["amendment_count"] = len(amendments)
        results.append(result)
    return results


def get_field_source_chain(lease_id: int, field_name: str) -> Optional[Dict[str, Any]]:
    """
    The full audit trail for one extracted field on one lease: which
    document currently governs its effective value (base lease, or
    whichever amendment most recently overrode it -- same "latest
    non-null amendment wins" rule get_effective_fields already uses),
    that document's exact source citation (page/quote for a PDF-derived
    field, row/file/quote for a rent-roll-imported one), AND the full
    history of every value this field has ever held across the base
    lease and every amendment -- not just the winning one. That full
    history is the point: a reviewer can see a field was originally X
    per the base lease, then changed to Y by a later amendment, with
    each value's own citation, rather than only being able to see
    today's answer.

    Returns None if lease_id doesn't exist. Each history entry's
    `value`/`source` is None if that document didn't state this field at
    all (not an error -- just nothing to cite there).
    """
    base = get_lease(lease_id)
    if not base:
        return None

    def _entry(document: Dict[str, Any]) -> Dict[str, Any]:
        field = document["extracted_fields"].get(field_name) or {"value": None, "source": None, "confidence": None}
        return {
            "document_id": document["id"],
            "document_type": document["document_type"],
            "filename": document["filename"],
            "display_name": document.get("display_name"),
            "uploaded_at": document["uploaded_at"],
            "value": field.get("value"),
            "source": field.get("source"),
            "confidence": field.get("confidence"),
            "is_effective": False,
        }

    history = [_entry(base)]
    for amendment in get_amendments(lease_id):
        history.append(_entry(amendment))

    winner_index = None
    for i, entry in enumerate(history):
        if entry["value"] is not None:
            winner_index = i  # last non-null wins, walking in upload order

    if winner_index is not None:
        history[winner_index]["is_effective"] = True

    return {
        "lease_id": lease_id,
        "field_name": field_name,
        "effective_value": history[winner_index]["value"] if winner_index is not None else None,
        "effective_source": history[winner_index]["source"] if winner_index is not None else None,
        "effective_confidence": history[winner_index]["confidence"] if winner_index is not None else None,
        "effective_document_id": history[winner_index]["document_id"] if winner_index is not None else None,
        "history": history,
    }


def insert_waitlist_signup(email: str) -> Dict[str, Any]:
    """
    Add an email to the waitlist. Returns {"status": "created", "id": ...}
    on success, or {"status": "duplicate"} if the email is already on the
    list — the caller should treat "duplicate" as a friendly no-op, not
    an error, since re-submitting the same email is expected user behavior
    (e.g. hitting submit twice), not bad input.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO waitlist_signups (email, created_at, status) VALUES (?, ?, 'pending')",
            (email, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"status": "created", "id": cur.lastrowid}
    except sqlite3.IntegrityError:
        return {"status": "duplicate"}
    finally:
        conn.close()


def get_all_waitlist_signups() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM waitlist_signups ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_waitlist_signup(signup_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM waitlist_signups WHERE id = ?", (signup_id,)).fetchone()
        return dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def get_waitlist_signup_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Case-insensitive lookup, since the email a visitor types into the
    access gate won't necessarily match the casing they originally signed
    up with."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM waitlist_signups WHERE lower(email) = lower(?)", (email,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def approve_waitlist_signup(signup_id: int) -> bool:
    """Flip a signup's status to 'approved'. Returns False if no such id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE waitlist_signups SET status = 'approved' WHERE id = ?",
            (signup_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def deny_waitlist_signup(signup_id: int) -> bool:
    """Flip a signup's status to 'denied'. Returns False if no such id. A denied signup stays in the table (not deleted) so the admin dashboard keeps a record of the decision, rather than the request silently vanishing."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE waitlist_signups SET status = 'denied' WHERE id = ?",
            (signup_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Team accounts: real per-user login backing app/auth.py's session-based
# auth. Replaces the old single-hardcoded-admin account (see
# _seed_first_admin_user above and DECISIONS.md's "Reliability
# hardening pass" / "Identity model for resolutions/comments" entries)
# -- every team member is a real row here now, with a role
# (admin/analyst/viewer) auth.require_role() checks against the
# session on every protected route.
# ----------------------------------------------------------------------

def create_user(
    email: str, name: str, password_hash: str, role: str = "viewer", created_by_user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Returns {"status": "created", "id": ...} on success, or
    {"status": "duplicate"} if the email is already taken -- same
    created/duplicate shape as insert_waitlist_signup, for the same
    reason: a UNIQUE-constraint collision here is an expected,
    friendly outcome (an admin fat-fingering an add-member form twice,
    or two admins racing to add the same person), not a server error.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, name, password_hash, role, status, created_at, created_by_user_id) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (email.strip().lower(), name, password_hash, role, datetime.now(timezone.utc).isoformat(), created_by_user_id),
        )
        conn.commit()
        return {"status": "created", "id": cur.lastrowid}
    except sqlite3.IntegrityError:
        return {"status": "duplicate"}
    finally:
        conn.close()


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Case-insensitive lookup -- login shouldn't be case-sensitive on the
    email a person types. `users.email` is always stored already
    lower-cased (create_user / the env seed both do `.strip().lower()`),
    so normalizing the input here and matching with a plain `=` lets
    this use the UNIQUE index directly instead of a full scan with
    `lower()` on every row -- and this runs on every login.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", ((email or "").strip().lower(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users() -> List[Dict[str, Any]]:
    """Every team member, active and deactivated alike (the Team view distinguishes them in the UI), oldest first."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_user_role(user_id: int, role: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def update_user_name(user_id: int, name: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def update_user_status(user_id: int, status: str) -> bool:
    """status: 'active' | 'deactivated'. A deactivated user can no longer log in (auth.verify_password checks status), but their id stays valid everywhere it's already referenced (assignments, activity_log) -- see users.status's own column comment for why this is a status flip, not a DELETE."""
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def update_user_password(user_id: int, password_hash: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def set_user_owner_flag(user_id: int, is_owner: bool) -> bool:
    """
    Sets/clears is_owner on an EXISTING user row. No API route ever
    calls this -- the only callers are backend/set_owner.py (a local,
    manually-run script, never exposed over HTTP) and
    _seed_first_admin_user (production's env-var-driven reseed). This
    is deliberate: there is no signup or self-service path to owner
    access, by the operator's own explicit requirement.
    """
    conn = get_connection()
    try:
        cur = conn.execute("UPDATE users SET is_owner = ? WHERE id = ?", (1 if is_owner else 0, user_id))
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def get_user_usage_stats(user_id: int, email: str) -> Dict[str, int]:
    """
    Best-effort per-login activity counts for the owner console's
    account list. Deliberately NOT "leases abstracted" or "rent rolls
    validated" -- the `leases` table has no uploaded_by/
    created_by_user_id column at all, so which login uploaded a given
    lease or rent roll genuinely isn't tracked anywhere in this schema
    today. What IS real and attributable: tasks (a true user_id FK),
    and field edits/discrepancy resolutions/comments (matched by
    edited_by_email/resolved_by_email/author_email -- these tables
    store the acting person's email as text, not a user_id FK, so this
    is an email match, not a foreign key join; still accurate as long
    as the login's email hasn't changed).
    """
    return get_usage_stats_for_users([{"id": user_id, "email": email}])[user_id]


_ZERO_USAGE = {
    "tasks_created": 0, "tasks_assigned": 0, "tasks_completed": 0,
    "field_edits": 0, "discrepancies_resolved": 0, "comments_posted": 0,
}


def get_usage_stats_for_users(users: List[Dict[str, Any]]) -> Dict[int, Dict[str, int]]:
    """
    Batched version of get_user_usage_stats for the owner console's
    account list: 6 grouped aggregate queries total on ONE connection,
    instead of (new connection + 6 COUNTs) per user. `users` is a list
    of dicts with at least "id" and "email". Returns {user_id: stats}.

    The email-keyed tables (lease_field_edits, discrepancy_resolutions,
    comments) store the acting person's email as free text, so this is
    a case-insensitive email match, not an FK join -- accurate as long
    as a login's email hasn't changed since they acted.
    """
    if not users:
        return {}
    result = {u["id"]: dict(_ZERO_USAGE) for u in users}
    id_by_lower_email = {(u.get("email") or "").strip().lower(): u["id"] for u in users if u.get("email")}

    conn = get_connection()
    try:
        for uid, cnt in conn.execute(
            "SELECT created_by_user_id, COUNT(*) FROM tasks WHERE created_by_user_id IS NOT NULL GROUP BY created_by_user_id"
        ):
            if uid in result:
                result[uid]["tasks_created"] = cnt
        for uid, cnt in conn.execute(
            "SELECT assigned_to_user_id, COUNT(*) FROM tasks WHERE assigned_to_user_id IS NOT NULL GROUP BY assigned_to_user_id"
        ):
            if uid in result:
                result[uid]["tasks_assigned"] = cnt
        for uid, cnt in conn.execute(
            "SELECT assigned_to_user_id, COUNT(*) FROM tasks WHERE assigned_to_user_id IS NOT NULL AND status = 'completed' GROUP BY assigned_to_user_id"
        ):
            if uid in result:
                result[uid]["tasks_completed"] = cnt

        for table, col, key in (
            ("lease_field_edits", "edited_by_email", "field_edits"),
            ("discrepancy_resolutions", "resolved_by_email", "discrepancies_resolved"),
            ("comments", "author_email", "comments_posted"),
        ):
            for raw_email, cnt in conn.execute(
                f"SELECT {col}, COUNT(*) FROM {table} WHERE {col} IS NOT NULL GROUP BY {col} COLLATE NOCASE"
            ):
                uid = id_by_lower_email.get((raw_email or "").strip().lower())
                if uid is not None:
                    result[uid][key] = result[uid][key] + cnt
        return result
    finally:
        conn.close()


def create_password_reset_token(user_id: int, token_hash: str) -> None:
    """
    Stores a single-use password reset token, keyed by the SHA-256
    hash of the random token (the raw token itself only ever exists in
    the reset link that's emailed -- a leak of this table must not hand
    an attacker working reset links, exactly the same reasoning that
    keeps users.password_hash a hash and not the password).

    Any earlier unused token for the same user is deleted first, so a
    person who clicks "forgot password" twice only ever has one live
    link -- the most recent one -- and the older email's link stops
    working immediately.
    """
    conn = get_connection()
    try:
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ? AND used_at IS NULL", (user_id,))
        conn.execute(
            "INSERT INTO password_reset_tokens (token_hash, user_id, created_at) VALUES (?, ?, ?)",
            (token_hash, user_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def consume_password_reset_token(token_hash: str, max_age_seconds: int = 3600) -> Optional[int]:
    """
    Looks up a reset token by its hash and, if it's valid (exists,
    never used, not older than max_age_seconds), marks it used and
    returns the user_id it belongs to. Returns None otherwise --
    unknown, already-used, or expired all look identical to the caller,
    which must treat every None as "this link is no longer valid."

    Marking used and checking age happen in one call so a token can
    never be redeemed twice, even by two requests racing each other:
    the UPDATE ... WHERE used_at IS NULL is atomic, and only the
    request whose UPDATE actually changed a row gets the user_id.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id, created_at FROM password_reset_tokens WHERE token_hash = ? AND used_at IS NULL",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None

        age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])).total_seconds()
        if age > max_age_seconds:
            return None

        cur = conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ? AND used_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), token_hash),
        )
        conn.commit()
        if cur.rowcount == 0:
            # Another request consumed it between the SELECT and here.
            return None
        return row["user_id"]
    finally:
        conn.close()


def update_user_last_login(user_id: int) -> None:
    """Shifts the existing last_login_at into previous_login_at before overwriting it, atomically -- see _migrate_users_table_add_previous_login_at for why this two-column shift exists (the daily briefing needs the PRIOR login timestamp, not the one being recorded right now)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET previous_login_at = last_login_at, last_login_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )
        conn.commit()
    except OverflowError:
        pass
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Assignments: ownership of a lease, discrepancy, or property. One
# table covers all three via target_type/target_key (leases/
# discrepancies have a real int id -- target_key is just str(id);
# properties have no id at all, only a normalized address string --
# see app.assignments.derive_target_key). One active assignment per
# target (UNIQUE(target_type, target_key)) -- reassigning overwrites
# who owns it, it doesn't stack a list; the activity log (once wired
# up) is the audit trail for past assignees, not this table.
# ----------------------------------------------------------------------

def upsert_assignment(
    target_type: str, target_key: str, assigned_to_user_id: int, assigned_by_user_id: int,
    lease_id: Optional[int] = None, discrepancy_id: Optional[int] = None,
    property_address: Optional[str] = None, note: Optional[str] = None,
) -> int:
    """
    Atomic INSERT ... ON CONFLICT DO UPDATE, same pattern as
    upsert_discrepancy/upsert_alert (see those functions' docstrings
    for the concurrency-race reasoning this fix originally came from --
    two people racing to claim the same unowned discrepancy must not
    500 the loser). Reassigning always resets status to 'assigned' --
    a freshly (re)assigned item shouldn't silently inherit 'resolved'
    from whoever had it before.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO assignments (target_type, target_key, lease_id, discrepancy_id, property_address,
                assigned_to_user_id, assigned_by_user_id, status, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'assigned', ?, ?, ?)
            ON CONFLICT(target_type, target_key) DO UPDATE SET
                assigned_to_user_id = excluded.assigned_to_user_id,
                assigned_by_user_id = excluded.assigned_by_user_id,
                status = 'assigned',
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (target_type, target_key, lease_id, discrepancy_id, property_address,
             assigned_to_user_id, assigned_by_user_id, note, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM assignments WHERE target_type = ? AND target_key = ?", (target_type, target_key)
        ).fetchone()
        return row["id"]
    finally:
        conn.close()


def update_assignment_status(assignment_id: int, status: str, updated_by_user_id: int) -> Optional[Dict[str, Any]]:
    """Plain UPDATE by primary key -- SQLite already serializes this correctly on its own (last-write-wins, no exception), unlike the natural-key race upsert_assignment guards against. See DECISIONS.md for why these are deliberately different race shapes needing different treatment."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE assignments SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat(), assignment_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
        return dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def get_assignment(assignment_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
        return dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def get_assignment_for_target(target_type: str, target_key: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM assignments WHERE target_type = ? AND target_key = ?", (target_type, target_key)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_assignments_for_targets(target_type: str, target_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    """Batched version of get_assignment_for_target for a whole list of keys at once -- {target_key: assignment}, only for keys that actually have one. Mirrors get_discrepancies_by_ids -- used to annotate a whole lease/discrepancy list in one query, not N+1."""
    if not target_keys:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in target_keys)
        rows = conn.execute(
            f"SELECT * FROM assignments WHERE target_type = ? AND target_key IN ({placeholders})",
            [target_type] + list(target_keys),
        ).fetchall()
        return {row["target_key"]: dict(row) for row in rows}
    finally:
        conn.close()


def list_assignments(
    assigned_to_user_id: Optional[int] = None, status: Optional[str] = None, target_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Any combination of filters may be applied together. Most-recently-updated first."""
    conn = get_connection()
    try:
        clauses, params = [], []
        if assigned_to_user_id is not None:
            clauses.append("assigned_to_user_id = ?")
            params.append(assigned_to_user_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if target_type:
            clauses.append("target_type = ?")
            params.append(target_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(f"SELECT * FROM assignments {where} ORDER BY updated_at DESC, id DESC", params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_assignment(assignment_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Assistant conversations: every question/answer pair a user has asked
# the AI assistant. Scoped strictly by user_id -- every read function
# here requires it and filters by it in SQL, never returns another
# user's rows under any circumstance. See app/assistant.py for what
# actually generates these.
# ----------------------------------------------------------------------

def insert_assistant_conversation(
    user_id: int, question: str, response_type: str, answer: str,
    route: Optional[str] = None, route_params: Optional[Dict[str, Any]] = None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO assistant_conversations (user_id, question, response_type, answer, route, route_params, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, question, response_type, answer, route, json.dumps(route_params) if route_params is not None else None,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_assistant_conversations(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """This user's own conversation history, most recent first. limit is clamped to a sane range -- same convention as get_recent_activity."""
    limit = max(1, min(limit, 200))
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM assistant_conversations WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    except OverflowError:
        return []
    finally:
        conn.close()

    result = []
    for row in rows:
        d = dict(row)
        d["route_params"] = json.loads(d["route_params"]) if d["route_params"] else None
        result.append(d)
    return result


# ----------------------------------------------------------------------
# Internal team messaging: direct + group threads. Isolation is
# enforced entirely through message_thread_participants -- a user can
# read/post/see a thread ONLY if a row exists here for them; every
# route-level check (see api.py) and every function below that takes a
# user_id filters through this table, never returns a thread's content
# to a non-participant under any circumstance. See is_thread_participant.
# ----------------------------------------------------------------------

def find_direct_thread(user_id_a: int, user_id_b: int) -> Optional[int]:
    """
    The existing 1-on-1 thread between exactly these two users, if one
    already exists -- so starting a new direct message with someone
    you already have a thread with reuses it instead of creating a
    duplicate. A 'direct' thread always has exactly 2 participants by
    construction (create_thread enforces this), so "thread_type =
    'direct' AND both users are participants" is sufficient to
    identify it uniquely without an extra COUNT check.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT t.id FROM message_threads t
            JOIN message_thread_participants p1 ON p1.thread_id = t.id AND p1.user_id = ?
            JOIN message_thread_participants p2 ON p2.thread_id = t.id AND p2.user_id = ?
            WHERE t.thread_type = 'direct'
            """,
            (user_id_a, user_id_b),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def create_thread(thread_type: str, participant_user_ids: List[int], created_by_user_id: int, name: Optional[str] = None) -> int:
    """
    For thread_type='direct' with exactly 2 participants, reuses an
    existing thread between them if one exists (see find_direct_thread)
    rather than creating a duplicate -- callers should generally check
    this themselves first if they want to distinguish "reused" from
    "created" (see api.py's create_thread_route), but this function is
    safe to call either way.
    """
    if thread_type == "direct" and len(participant_user_ids) == 2:
        existing = find_direct_thread(participant_user_ids[0], participant_user_ids[1])
        if existing is not None:
            return existing

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO message_threads (thread_type, name, created_by_user_id, created_at) VALUES (?, ?, ?, ?)",
            (thread_type, name, created_by_user_id, now),
        )
        thread_id = cur.lastrowid
        for user_id in set(participant_user_ids):
            conn.execute(
                "INSERT INTO message_thread_participants (thread_id, user_id, joined_at, last_read_at) VALUES (?, ?, ?, NULL)",
                (thread_id, user_id, now),
            )
        conn.commit()
        return thread_id
    finally:
        conn.close()


def add_thread_participant(thread_id: int, user_id: int) -> bool:
    """Adds someone to a group thread. Silently a no-op if they're already in it (UNIQUE(thread_id, user_id)) -- same convention as add_lease_tag."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO message_thread_participants (thread_id, user_id, joined_at, last_read_at) VALUES (?, ?, ?, NULL)",
            (thread_id, user_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except OverflowError:
        return False
    finally:
        conn.close()


def is_thread_participant(thread_id: int, user_id: int) -> bool:
    """The one check every message-reading/writing route must pass before touching a thread at all -- see this module's messaging section docstring."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM message_thread_participants WHERE thread_id = ? AND user_id = ?", (thread_id, user_id)
        ).fetchone()
        return row is not None
    except OverflowError:
        return False
    finally:
        conn.close()


def get_thread(thread_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM message_threads WHERE id = ?", (thread_id,)).fetchone()
        return dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def get_thread_participants(thread_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM message_thread_participants WHERE thread_id = ?", (thread_id,)).fetchall()
        return [dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def list_threads_for_user(user_id: int) -> List[Dict[str, Any]]:
    """
    Every thread this user participates in -- deliberately joins
    through message_thread_participants (never a bare SELECT * FROM
    message_threads), so a thread the user isn't in can never appear
    here regardless of any other bug elsewhere. Most-recent-activity
    first (latest message, or thread creation if it has none yet).
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT t.*, p.last_read_at,
                   (SELECT MAX(created_at) FROM messages m WHERE m.thread_id = t.id) AS last_message_at
            FROM message_threads t
            JOIN message_thread_participants p ON p.thread_id = t.id AND p.user_id = ?
            ORDER BY COALESCE(last_message_at, t.created_at) DESC, t.id DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def insert_message(thread_id: int, sender_user_id: int, body: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO messages (thread_id, sender_user_id, body, created_at) VALUES (?, ?, ?, ?)",
            (thread_id, sender_user_id, body, now),
        )
        # Sending a message always marks the sender's own copy of the
        # thread read as of now -- you obviously already know what you
        # just wrote, it should never count as unread for you.
        conn.execute(
            "UPDATE message_thread_participants SET last_read_at = ? WHERE thread_id = ? AND user_id = ?",
            (now, thread_id, sender_user_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_message(message_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def get_messages(thread_id: int, since: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Oldest first (a message thread reads top-to-bottom). `since` (an ISO timestamp) is for polling -- only messages strictly after it, so a client re-polling an open thread gets just what's new."""
    limit = max(1, min(limit, 500))
    conn = get_connection()
    try:
        if since:
            rows = conn.execute(
                "SELECT * FROM messages WHERE thread_id = ? AND created_at > ? ORDER BY created_at ASC, id ASC LIMIT ?",
                (thread_id, since, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC, id ASC LIMIT ?",
                (thread_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def mark_thread_read(thread_id: int, user_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE message_thread_participants SET last_read_at = ? WHERE thread_id = ? AND user_id = ?",
            (datetime.now(timezone.utc).isoformat(), thread_id, user_id),
        )
        conn.commit()
    except OverflowError:
        pass
    finally:
        conn.close()


def get_unread_counts_for_user(user_id: int) -> Dict[int, int]:
    """{thread_id: unread_count} for every thread this user is in that has at least one unread message -- a message counts as unread if it's newer than the user's last_read_at (or the thread has never been read at all) AND wasn't sent by the user themselves (see insert_message -- your own messages never count as unread for you, so this mirrors that at read time too, for a participant who somehow still shows one, e.g. a first message in a brand-new thread they didn't send)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.thread_id, COUNT(m.id) AS unread
            FROM message_thread_participants p
            JOIN messages m ON m.thread_id = p.thread_id
                AND m.sender_user_id != p.user_id
                AND (p.last_read_at IS NULL OR m.created_at > p.last_read_at)
            WHERE p.user_id = ?
            GROUP BY p.thread_id
            """,
            (user_id,),
        ).fetchall()
        return {row["thread_id"]: row["unread"] for row in rows}
    except OverflowError:
        return {}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Email account linking (OAuth send-as)
# ----------------------------------------------------------------------

def create_oauth_state(state: str, user_id: int, provider: str) -> None:
    """A one-time CSRF token for the OAuth authorize->callback round trip, keyed by the random state string itself (not by user, since the callback arrives with only the state to go on)."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO oauth_states (state, user_id, provider, created_at) VALUES (?, ?, ?, ?)",
            (state, user_id, provider, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def consume_oauth_state(state: str, max_age_seconds: int = 600) -> Optional[Dict[str, Any]]:
    """Looks up and deletes a state token in one call (single-use, matching what 'state' is for). Returns None if the state doesn't exist or is older than max_age_seconds, either of which the callback route must treat as a rejected/expired OAuth attempt."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM oauth_states WHERE state = ?", (state,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()
        created_at = datetime.fromisoformat(row["created_at"])
        age = (datetime.now(timezone.utc) - created_at).total_seconds()
        if age > max_age_seconds:
            return None
        return dict(row)
    finally:
        conn.close()


def upsert_linked_email_account(
    user_id: int,
    provider: str,
    provider_email: str,
    access_token_encrypted: str,
    refresh_token_encrypted: str,
    token_expires_at: str,
    scopes: str,
) -> int:
    """Re-linking the same provider replaces the stored tokens rather than creating a second row -- one linked account per (user, provider), matching the UNIQUE constraint."""
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO linked_email_accounts
                (user_id, provider, provider_email, access_token_encrypted, refresh_token_encrypted, token_expires_at, scopes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                provider_email = excluded.provider_email,
                access_token_encrypted = excluded.access_token_encrypted,
                refresh_token_encrypted = excluded.refresh_token_encrypted,
                token_expires_at = excluded.token_expires_at,
                scopes = excluded.scopes,
                updated_at = excluded.updated_at
            """,
            (user_id, provider, provider_email, access_token_encrypted, refresh_token_encrypted, token_expires_at, scopes, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM linked_email_accounts WHERE user_id = ? AND provider = ?", (user_id, provider)
        ).fetchone()
        return row["id"]
    finally:
        conn.close()


def get_linked_email_account(account_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM linked_email_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_linked_email_accounts_for_user(user_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM linked_email_accounts WHERE user_id = ? ORDER BY created_at", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_linked_email_account_tokens(
    account_id: int,
    access_token_encrypted: str,
    token_expires_at: str,
    refresh_token_encrypted: Optional[str] = None,
) -> None:
    """Called after a refresh. refresh_token_encrypted is only passed when the provider actually rotated it (Google normally doesn't; Microsoft can) -- omitting it leaves the existing refresh token in place rather than overwriting it with nothing."""
    conn = get_connection()
    try:
        if refresh_token_encrypted is not None:
            conn.execute(
                "UPDATE linked_email_accounts SET access_token_encrypted = ?, token_expires_at = ?, refresh_token_encrypted = ?, updated_at = ? WHERE id = ?",
                (access_token_encrypted, token_expires_at, refresh_token_encrypted, datetime.now(timezone.utc).isoformat(), account_id),
            )
        else:
            conn.execute(
                "UPDATE linked_email_accounts SET access_token_encrypted = ?, token_expires_at = ?, updated_at = ? WHERE id = ?",
                (access_token_encrypted, token_expires_at, datetime.now(timezone.utc).isoformat(), account_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete_linked_email_account(account_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM linked_email_accounts WHERE id = ?", (account_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Tasks
# ----------------------------------------------------------------------

def create_task(
    title: str,
    created_by_user_id: int,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    assigned_to_user_id: Optional[int] = None,
    lease_id: Optional[int] = None,
    discrepancy_id: Optional[int] = None,
    property_address: Optional[str] = None,
    source_type: Optional[str] = None,
    source_natural_key: Optional[str] = None,
    priority: str = "normal",
) -> int:
    """lease_id/discrepancy_id are intentionally not FK'd -- same 'survives deletion of the thing it referenced' reasoning as discrepancies.lease_id and assignments.lease_id, so a task doesn't silently vanish or corrupt if the linked record is later removed."""
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO tasks
                (title, description, due_date, status, assigned_to_user_id, created_by_user_id,
                 lease_id, discrepancy_id, property_address, source_type, source_natural_key,
                 priority, created_at, updated_at)
            VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, description, due_date, assigned_to_user_id, created_by_user_id,
             lease_id, discrepancy_id, property_address, source_type, source_natural_key, priority, now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_tasks_by_ids(task_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Batched version of get_task for many ids at once — {id: task}."""
    if not task_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in task_ids)
        rows = conn.execute(f"SELECT * FROM tasks WHERE id IN ({placeholders})", task_ids).fetchall()
        return {row["id"]: dict(row) for row in rows}
    except OverflowError:
        return {}
    finally:
        conn.close()


def list_tasks(
    assigned_to_user_id: Optional[int] = None,
    status: Optional[str] = None,
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    lease_id: Optional[int] = None,
    discrepancy_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Every filter is optional and AND-combined -- callers pass only the ones they need (the /tasks route maps straight from its own optional query params to these same keyword args)."""
    conn = get_connection()
    try:
        clauses, params = [], []
        if assigned_to_user_id is not None:
            clauses.append("assigned_to_user_id = ?")
            params.append(assigned_to_user_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if due_before is not None:
            clauses.append("due_date IS NOT NULL AND due_date <= ?")
            params.append(due_before)
        if due_after is not None:
            clauses.append("due_date IS NOT NULL AND due_date >= ?")
            params.append(due_after)
        if lease_id is not None:
            clauses.append("lease_id = ?")
            params.append(lease_id)
        if discrepancy_id is not None:
            clauses.append("discrepancy_id = ?")
            params.append(discrepancy_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # High-priority tasks sort first, ahead of due-date ordering --
        # `(priority != 'high')` is 0 for a high-priority row and 1
        # otherwise, so ascending puts every high-priority task before
        # every normal one; due_date/created_at still order within each
        # of those two groups exactly as before.
        rows = conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY (priority != 'high'), (due_date IS NULL), due_date, created_at",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_tasks_due_today_or_overdue(user_id: int, reference_date: str) -> List[Dict[str, Any]]:
    """reference_date is an ISO date string (YYYY-MM-DD). 'Due today or overdue' = not done or dismissed, has a due date, and that due date is on or before reference_date -- a task with no due date never shows up here (it isn't time-bound, so it can't be overdue). High-priority tasks sort first (see list_tasks' identical ORDER BY reasoning), so the Today briefing surfaces them ahead of anything else due."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE assigned_to_user_id = ? AND status NOT IN ('done', 'dismissed') AND due_date IS NOT NULL AND due_date <= ?
            ORDER BY (priority != 'high'), due_date
            """,
            (user_id, reference_date),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_task_status(task_id: int, status: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        completed_at = now if status == "done" else None
        conn.execute(
            "UPDATE tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
            (status, completed_at, now, task_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_task_assignee(task_id: int, assigned_to_user_id: Optional[int]) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE tasks SET assigned_to_user_id = ?, updated_at = ? WHERE id = ?",
            (assigned_to_user_id, datetime.now(timezone.utc).isoformat(), task_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_task_fields(task_id: int, title: Optional[str] = None, description: Optional[str] = None, due_date: Optional[str] = None, _clear_due_date: bool = False, priority: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Only overwrites fields actually passed -- None means 'leave as-is' for title/description/priority, EXCEPT due_date, which needs to support being cleared back to no-due-date; _clear_due_date=True is how a caller says 'set it to NULL' instead of 'I didn't pass one'."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if existing is None:
            return None
        new_title = title if title is not None else existing["title"]
        new_description = description if description is not None else existing["description"]
        new_due_date = None if _clear_due_date else (due_date if due_date is not None else existing["due_date"])
        new_priority = priority if priority is not None else existing["priority"]
        conn.execute(
            "UPDATE tasks SET title = ?, description = ?, due_date = ?, priority = ?, updated_at = ? WHERE id = ?",
            (new_title, new_description, new_due_date, new_priority, datetime.now(timezone.utc).isoformat(), task_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_task(task_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def insert_activity(action_type: str, description: str, lease_id: Optional[int] = None) -> int:
    """
    Records one entry in the account-wide activity feed. Called
    directly from the API route handling an action (upload, delete,
    comparison run, report generated, etc) — this module doesn't infer
    activity from other state, it just persists what the caller tells it
    happened. `lease_id` is set to NULL (not deleted) if that lease is
    later removed — see the ON DELETE SET NULL on the FK in init_db —
    so the activity entry (whose `description` already has the filename
    baked in) survives as history rather than vanishing or blocking the
    delete.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO activity_log (action_type, description, lease_id, created_at) VALUES (?, ?, ?, ?)",
            (action_type, description, lease_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_recent_activity(limit: int = 10) -> List[Dict[str, Any]]:
    """Most recent activity first. `limit` is clamped to a sane range so an
    unbounded/absurd query param can't force a full-table scan-and-return."""
    limit = max(1, min(limit, 200))
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Lease tags (simple flat tagging — see DECISIONS.md for why tags over
# folders). A tag has no existence independent of the leases wearing it
# — there's no separate "tags" table to manage; the set of all tags in
# use is just DISTINCT tag over lease_tags, computed on read.
# ----------------------------------------------------------------------

def add_lease_tag(lease_id: int, tag: str) -> None:
    """Adds one tag to a lease. Silently a no-op if that exact tag is already there (UNIQUE(lease_id, tag)) — tagging something twice isn't an error, just redundant."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO lease_tags (lease_id, tag) VALUES (?, ?)",
            (lease_id, tag),
        )
        conn.commit()
    except (sqlite3.IntegrityError, OverflowError):
        pass
    finally:
        conn.close()


def remove_lease_tag(lease_id: int, tag: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM lease_tags WHERE lease_id = ? AND tag = ?",
            (lease_id, tag),
        )
        conn.commit()
    except OverflowError:
        pass
    finally:
        conn.close()


def get_lease_tags(lease_id: int) -> List[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT tag FROM lease_tags WHERE lease_id = ? ORDER BY tag",
            (lease_id,),
        ).fetchall()
        return [row["tag"] for row in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def get_tags_for_leases(lease_ids: List[int]) -> Dict[int, List[str]]:
    """Batched version of get_lease_tags for a whole list of ids at once — used when rendering a lease list, so that doesn't run one query per row."""
    if not lease_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in lease_ids)
        rows = conn.execute(
            f"SELECT lease_id, tag FROM lease_tags WHERE lease_id IN ({placeholders}) ORDER BY tag",
            lease_ids,
        ).fetchall()
        result: Dict[int, List[str]] = {lease_id: [] for lease_id in lease_ids}
        for row in rows:
            result[row["lease_id"]].append(row["tag"])
        return result
    finally:
        conn.close()


def get_all_tags() -> List[str]:
    """Every distinct tag currently in use, alphabetically — for filter-by-tag UI and tag autocomplete."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT tag FROM lease_tags ORDER BY tag").fetchall()
        return [row["tag"] for row in rows]
    finally:
        conn.close()


def get_lease_ids_with_tag(tag: str) -> List[int]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT lease_id FROM lease_tags WHERE tag = ?", (tag,)
        ).fetchall()
        return [row["lease_id"] for row in rows]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Discrepancies + resolutions.
#
# A "discrepancy" is a stable, persisted identity for something that's
# otherwise computed fresh on every request (a risk flag, a cross-lease
# mismatch, a rent-roll-vs-lease-PDF or rent-roll-vs-T12 reconciliation
# disagreement). None of those computations have ever had a database
# row of their own -- upsert_discrepancy is what gives one a permanent
# identity (via natural_key, a deterministic string the caller derives
# from the flag's own identifying fields) so a resolution attached to
# it survives being recomputed. See app/discrepancies.py for how
# natural keys are derived per discrepancy type, and how resolution
# status gets merged back into the live-computed flags a caller sees.
# ----------------------------------------------------------------------

def upsert_discrepancy(
    discrepancy_type: str,
    natural_key: str,
    category: str,
    message: str,
    details: Dict[str, Any],
    lease_id: Optional[int] = None,
    related_lease_id: Optional[int] = None,
    field: Optional[str] = None,
    severity: Optional[str] = None,
) -> int:
    """
    Records that this discrepancy was seen in the current computation.
    First time this natural_key is seen: inserts a new row, status
    'open'. Every subsequent time: updates the latest-known snapshot
    (category/field/severity/message/details/last_seen_at) but
    deliberately leaves `status` untouched -- recomputing a flag must
    never silently un-resolve or re-resolve it; only an explicit
    resolve_discrepancy/reopen_discrepancy call changes status. Returns
    the discrepancy's id either way.

    A single atomic `INSERT ... ON CONFLICT DO UPDATE` statement, NOT
    a "SELECT to check, then INSERT or UPDATE" pair -- that older
    pattern has a real, confirmed race: two concurrent requests
    syncing the SAME natural_key (e.g. two people uploading the same
    file at once, or two tabs hitting /portfolio/risks together) could
    both see "doesn't exist yet" and both attempt to INSERT, and the
    loser would hit the `natural_key` UNIQUE constraint as an uncaught
    `IntegrityError` -- reproduced directly with 5 concurrent SQLite
    connections racing the old two-step pattern before this fix (4 of
    5 failed). `ON CONFLICT` pushes the check-and-act into SQLite
    itself, which is what's actually safe to do it atomically.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO discrepancies (discrepancy_type, natural_key, lease_id, related_lease_id,
                category, field, severity, message, details, status, first_detected_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            ON CONFLICT(natural_key) DO UPDATE SET
                category = excluded.category,
                field = excluded.field,
                severity = excluded.severity,
                message = excluded.message,
                details = excluded.details,
                lease_id = excluded.lease_id,
                related_lease_id = excluded.related_lease_id,
                last_seen_at = excluded.last_seen_at
            """,
            (discrepancy_type, natural_key, lease_id, related_lease_id, category, field, severity, message, json.dumps(details), now, now),
        )
        conn.commit()
        # A second SELECT after the atomic upsert above is race-free --
        # the row is now guaranteed to exist under this natural_key
        # (the race this fixes was in the OLD check-then-act pattern,
        # not here).
        row = conn.execute("SELECT id FROM discrepancies WHERE natural_key = ?", (natural_key,)).fetchone()
        return row["id"]
    finally:
        conn.close()


def upsert_discrepancies_bulk(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Same atomic upsert as upsert_discrepancy, for many discrepancies at
    once, sharing ONE connection and ONE commit instead of one
    connect()+commit() pair per item. Each item in `items` is a dict
    with the same keys as upsert_discrepancy's params (natural_key,
    discrepancy_type, category, message, details, and optionally
    lease_id/related_lease_id/field/severity). Returns
    {natural_key: discrepancy_id} for every item.

    Exists purely for the full-portfolio risk-flag resync
    (GET /portfolio/risks), which upserts one discrepancy per flag --
    thousands at real portfolio scale (measured: 3142 flags across 831
    leases). Profiling that resync found sqlite3.Connection.commit()
    and .connect() alone accounted for ~1.4s of a ~2.9s request purely
    from being called thousands of times, with the actual SQL execute()
    time being comparable -- i.e. per-call overhead, not query
    complexity, was the bottleneck. This function is that hot path's
    replacement; upsert_discrepancy itself is untouched and still used
    everywhere a single discrepancy is upserted (a single lease's own
    risk flags, rent-roll/T12 reconciliation, etc.), where that
    overhead is negligible.
    """
    if not items:
        return {}
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        for item in items:
            conn.execute(
                """
                INSERT INTO discrepancies (discrepancy_type, natural_key, lease_id, related_lease_id,
                    category, field, severity, message, details, status, first_detected_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                ON CONFLICT(natural_key) DO UPDATE SET
                    category = excluded.category,
                    field = excluded.field,
                    severity = excluded.severity,
                    message = excluded.message,
                    details = excluded.details,
                    lease_id = excluded.lease_id,
                    related_lease_id = excluded.related_lease_id,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    item["discrepancy_type"], item["natural_key"], item.get("lease_id"), item.get("related_lease_id"),
                    item["category"], item.get("field"), item.get("severity"), item["message"],
                    json.dumps(item["details"]), now, now,
                ),
            )
        conn.commit()

        natural_keys = [item["natural_key"] for item in items]
        placeholders = ",".join("?" for _ in natural_keys)
        rows = conn.execute(
            f"SELECT id, natural_key FROM discrepancies WHERE natural_key IN ({placeholders})", natural_keys
        ).fetchall()
        return {row["natural_key"]: row["id"] for row in rows}
    finally:
        conn.close()


def get_discrepancies_by_ids(discrepancy_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Batched version of get_discrepancy for many ids at once — {id: discrepancy}. Same OverflowError safety as get_discrepancy (an out-of-range id just won't match any row)."""
    if not discrepancy_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in discrepancy_ids)
        rows = conn.execute(f"SELECT * FROM discrepancies WHERE id IN ({placeholders})", discrepancy_ids).fetchall()
        return {row["id"]: _discrepancy_row_to_dict(row) for row in rows}
    except OverflowError:
        return {}
    finally:
        conn.close()


def get_discrepancy_resolutions_bulk(discrepancy_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Batched version of get_discrepancy_resolutions for many ids at once — {discrepancy_id: [resolutions, oldest first]}."""
    if not discrepancy_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in discrepancy_ids)
        rows = conn.execute(
            f"SELECT * FROM discrepancy_resolutions WHERE discrepancy_id IN ({placeholders}) ORDER BY created_at ASC, id ASC",
            discrepancy_ids,
        ).fetchall()
    except OverflowError:
        return {}
    finally:
        conn.close()

    result: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row["discrepancy_id"], []).append(dict(row))
    return result


def _discrepancy_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["details"] = json.loads(d["details"])
    return d


def get_discrepancy_by_natural_key(natural_key: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM discrepancies WHERE natural_key = ?", (natural_key,)).fetchone()
        return _discrepancy_row_to_dict(row) if row else None
    finally:
        conn.close()


def get_discrepancy(discrepancy_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM discrepancies WHERE id = ?", (discrepancy_id,)).fetchone()
        return _discrepancy_row_to_dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def list_discrepancies(
    status: Optional[str] = None,
    lease_id: Optional[int] = None,
    discrepancy_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Most-recently-seen first. Any combination of filters may be applied together."""
    conn = get_connection()
    try:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if lease_id is not None:
            clauses.append("(lease_id = ? OR related_lease_id = ?)")
            params.extend([lease_id, lease_id])
        if discrepancy_type:
            clauses.append("discrepancy_type = ?")
            params.append(discrepancy_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM discrepancies {where} ORDER BY last_seen_at DESC, id DESC", params
        ).fetchall()
        return [_discrepancy_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _add_resolution(
    discrepancy_id: int,
    action: str,
    note: str,
    resolved_by: str,
    correct_source: Optional[str],
    resolved_by_email: Optional[str],
    new_status: str,
) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        exists = conn.execute("SELECT id FROM discrepancies WHERE id = ?", (discrepancy_id,)).fetchone()
        if not exists:
            return None
        cur = conn.execute(
            "INSERT INTO discrepancy_resolutions (discrepancy_id, action, correct_source, note, "
            "resolved_by, resolved_by_email, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (discrepancy_id, action, correct_source, note, resolved_by, resolved_by_email, now),
        )
        conn.execute("UPDATE discrepancies SET status = ? WHERE id = ?", (new_status, discrepancy_id))
        conn.commit()
        return {
            "id": cur.lastrowid,
            "discrepancy_id": discrepancy_id,
            "action": action,
            "correct_source": correct_source,
            "note": note,
            "resolved_by": resolved_by,
            "resolved_by_email": resolved_by_email,
            "created_at": now,
        }
    except OverflowError:
        return None
    finally:
        conn.close()


def resolve_discrepancy(
    discrepancy_id: int, correct_source: str, note: str, resolved_by: str, resolved_by_email: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Logs a resolution and marks the discrepancy 'resolved'. Always
    allowed regardless of current status -- resolving an already-
    resolved discrepancy again (e.g. a second reviewer confirming, or
    updating the note) just appends another permanent entry to the log
    rather than being rejected, since nothing about that should be
    treated as an error. Returns None if discrepancy_id doesn't exist.
    """
    return _add_resolution(discrepancy_id, "resolved", note, resolved_by, correct_source, resolved_by_email, "resolved")


def reopen_discrepancy(
    discrepancy_id: int, note: str, resolved_by: str, resolved_by_email: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Logs a reopen action and marks the discrepancy 'open' again. Returns None if discrepancy_id doesn't exist."""
    return _add_resolution(discrepancy_id, "reopened", note, resolved_by, None, resolved_by_email, "open")


def get_discrepancy_resolutions(discrepancy_id: int) -> List[Dict[str, Any]]:
    """The full, permanent resolve/reopen history for one discrepancy, oldest first (a readable timeline)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM discrepancy_resolutions WHERE discrepancy_id = ? ORDER BY created_at ASC, id ASC",
            (discrepancy_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def get_discrepancy_summary() -> Dict[str, Any]:
    """
    Counts across every discrepancy, by status/severity/type -- the
    header-stat digest a "Discrepancies" sidebar tab needs (how many
    total, how many still open, the severity/type breakdown) without
    fetching the full list just to count it client-side. Deliberately
    scoped identically to list_discrepancies() (every discrepancy ever
    recorded, not just ones tied to leases currently in the portfolio)
    so this digest can never disagree with what GET /discrepancies
    itself returns -- see portfolio_health_score.py's own discrepancy-
    scoping logic for the DIFFERENT, narrower scope that function
    needs instead, and why.
    """
    conn = get_connection()
    try:
        rows = conn.execute("SELECT status, severity, discrepancy_type FROM discrepancies").fetchall()
    finally:
        conn.close()

    by_status = {"open": 0, "resolved": 0}
    by_severity = {"high": 0, "medium": 0, "low": 0}
    by_type: Dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        if row["severity"] in by_severity:
            by_severity[row["severity"]] += 1
        by_type[row["discrepancy_type"]] = by_type.get(row["discrepancy_type"], 0) + 1

    return {"total": len(rows), "by_status": by_status, "by_severity": by_severity, "by_type": by_type}


# ----------------------------------------------------------------------
# Comments: team notes on a lease or a discrepancy, visible to everyone
# on the account (there's no per-account data scoping in this app at
# all yet -- see the Session 14 pre-sale audit in PROGRESS.md -- so
# "visible to the whole team" is already the natural behavior of any
# plain list/read here, nothing extra to build for that specifically).
# `author_name`/`author_email` are exactly what the caller supplies,
# trusted as-is -- same self-reported-identity convention as
# discrepancy resolutions; see DECISIONS.md.
# ----------------------------------------------------------------------

def add_comment(
    author_name: str, body: str, lease_id: Optional[int] = None,
    discrepancy_id: Optional[int] = None, author_email: Optional[str] = None,
    task_id: Optional[int] = None,
) -> int:
    """Exactly one of lease_id/discrepancy_id/task_id is expected to be set -- enforced by the API layer, not here, consistent with how validation is layered throughout this module."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO comments (lease_id, discrepancy_id, task_id, author_name, author_email, body, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lease_id, discrepancy_id, task_id, author_name, author_email, body, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_lease_comments(lease_id: int) -> List[Dict[str, Any]]:
    """Oldest first -- a comment thread reads top-to-bottom like a conversation."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM comments WHERE lease_id = ? ORDER BY created_at ASC, id ASC", (lease_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def get_discrepancy_comments(discrepancy_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM comments WHERE discrepancy_id = ? ORDER BY created_at ASC, id ASC", (discrepancy_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def get_task_comments(task_id: int) -> List[Dict[str, Any]]:
    """Task discussion -- separate from lease_field_edits (that's a data-correction audit trail, this is team conversation: 'checked with the broker, waiting to hear back')."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM comments WHERE task_id = ? ORDER BY created_at ASC, id ASC", (task_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except OverflowError:
        return []
    finally:
        conn.close()


def get_recent_comments(limit: int = 20) -> List[Dict[str, Any]]:
    """
    The most recent comments across BOTH leases and discrepancies, one
    portfolio-wide feed -- what a standalone "Team Notes" sidebar tab
    needs, which neither get_lease_comments nor get_discrepancy_
    comments (each scoped to a single target) can answer alone.
    Denormalizes just enough context via a LEFT JOIN (the lease's own
    display name/filename, or the discrepancy's category) so a caller
    can render each entry directly, without a follow-up request per
    comment to find out what it's actually about. A comment's lease/
    discrepancy may have since been deleted (comments cascade-delete
    with their lease, but not with the discrepancy they're attached to
    -- discrepancies are permanent records, see database.py's own
    discrepancies-table comment) -- either LEFT JOIN simply comes back
    NULL in that case, handled the same as "no extra context available"
    rather than as an error.
    """
    limit = max(1, min(limit, 200))
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT c.*,
                   l.display_name AS lease_display_name, l.filename AS lease_filename,
                   d.category AS discrepancy_category, d.discrepancy_type AS discrepancy_type_name
            FROM comments c
            LEFT JOIN leases l ON c.lease_id = l.id
            LEFT JOIN discrepancies d ON c.discrepancy_id = d.id
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Alerts: proactive notifications generated by app/alerts.py, persisted
# here with the same natural-key upsert identity pattern discrepancies
# use (see that section's comment above for the full reasoning) --
# recomputing must never silently reactivate or hide something a human
# already dismissed, only refresh what's currently true about it.
#
# One thing alerts add beyond discrepancies: `status` also includes
# 'auto_resolved' (not just 'active'/'dismissed') -- an alert whose
# underlying condition genuinely cleared on its own (a lease got
# renewed further out, rent caught up to market, a tenant's share
# dropped back under threshold) is a materially different situation
# from a human saying "I've seen this, stop showing it to me." See
# upsert_alert for exactly which status transitions are and aren't
# allowed.
# ----------------------------------------------------------------------

def _alert_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["details"] = json.loads(d["details"])
    return d


def get_alert_by_natural_key(natural_key: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM alerts WHERE natural_key = ?", (natural_key,)).fetchone()
        return _alert_row_to_dict(row) if row else None
    finally:
        conn.close()


def upsert_alert(
    alert_type: str,
    natural_key: str,
    severity: str,
    title: str,
    message: str,
    details: Dict[str, Any],
    lease_id: Optional[int] = None,
) -> int:
    """
    First time this natural_key is seen: inserts a new row, status
    'active'. Every subsequent time the SAME real-world condition is
    still detected:
      - status 'active' stays 'active' (just refreshes the snapshot).
      - status 'auto_resolved' flips back to 'active' -- the condition
        wasn't seen last run (which is exactly what auto-resolved
        means) but is genuinely present again now, so it's active
        again, same as it would have been if it had simply never
        cleared.
      - status 'dismissed' stays 'dismissed' -- a human decision is
        never silently overturned just because the condition
        recurred; that's what makes dismiss meaningfully different
        from the system's own auto-resolve.
    Returns the alert's id either way.

    A single atomic `INSERT ... ON CONFLICT DO UPDATE`, not a
    "SELECT to check, then INSERT or UPDATE" pair -- the old two-step
    pattern has a real, confirmed race between concurrent requests
    syncing the same natural_key (see upsert_discrepancy for the full
    writeup and reproduction). The status-transition rule above is
    expressed directly in the SET clause via a CASE so it still holds
    under the atomic path.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO alerts (alert_type, natural_key, lease_id, severity, title, message, details,
                status, first_detected_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(natural_key) DO UPDATE SET
                severity = excluded.severity,
                title = excluded.title,
                message = excluded.message,
                details = excluded.details,
                lease_id = excluded.lease_id,
                status = CASE WHEN alerts.status = 'auto_resolved' THEN 'active' ELSE alerts.status END,
                last_seen_at = excluded.last_seen_at
            """,
            (alert_type, natural_key, lease_id, severity, title, message, json.dumps(details), now, now),
        )
        conn.commit()
        row = conn.execute("SELECT id FROM alerts WHERE natural_key = ?", (natural_key,)).fetchone()
        return row["id"]
    finally:
        conn.close()


def get_alerts_existing_natural_keys(natural_keys: List[str]) -> set:
    """Which of these natural_keys already have an alert row -- used to compute created-vs-refreshed counts around upsert_alerts_bulk without a get_alert_by_natural_key round trip per candidate."""
    if not natural_keys:
        return set()
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in natural_keys)
        rows = conn.execute(f"SELECT natural_key FROM alerts WHERE natural_key IN ({placeholders})", natural_keys).fetchall()
        return {row["natural_key"] for row in rows}
    finally:
        conn.close()


def upsert_alerts_bulk(items: List[Dict[str, Any]]) -> None:
    """
    Same atomic upsert as upsert_alert (including the auto_resolved ->
    active status-transition rule), for many alerts at once, sharing
    ONE connection and ONE commit instead of one connect()+commit() per
    item. Each item is a dict with the same keys as upsert_alert's
    params. Exists for the same reason as upsert_discrepancies_bulk --
    see that function's docstring; app/alerts.py's generate_alerts()
    is the caller, upserting one candidate per detected condition
    across the whole portfolio in one pass.
    """
    if not items:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        for item in items:
            conn.execute(
                """
                INSERT INTO alerts (alert_type, natural_key, lease_id, severity, title, message, details,
                    status, first_detected_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(natural_key) DO UPDATE SET
                    severity = excluded.severity,
                    title = excluded.title,
                    message = excluded.message,
                    details = excluded.details,
                    lease_id = excluded.lease_id,
                    status = CASE WHEN alerts.status = 'auto_resolved' THEN 'active' ELSE alerts.status END,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    item["alert_type"], item["natural_key"], item.get("lease_id"), item["severity"],
                    item["title"], item["message"], json.dumps(item["details"]), now, now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def auto_resolve_alerts_bulk(alert_ids: List[int]) -> int:
    """Batched version of auto_resolve_alert for many ids at once, one connection/commit. Returns how many were actually transitioned (already-non-'active' ids are silently skipped, same as the single-id version)."""
    if not alert_ids:
        return 0
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in alert_ids)
        cur = conn.execute(
            f"UPDATE alerts SET status = 'auto_resolved' WHERE id IN ({placeholders}) AND status = 'active'",
            alert_ids,
        )
        conn.commit()
        return cur.rowcount
    except OverflowError:
        return 0
    finally:
        conn.close()


def auto_resolve_alert(alert_id: int) -> bool:
    """
    Marks an alert 'auto_resolved' -- called by app/alerts.py's
    generation pass for an alert that was 'active' last run but whose
    underlying condition no longer reproduces this run. Deliberately
    only transitions FROM 'active' -- an already-'dismissed' alert
    stays 'dismissed' (nothing to resolve, a human already closed it),
    and an already-'auto_resolved' one is a no-op. Returns False if no
    such id.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE alerts SET status = 'auto_resolved' WHERE id = ? AND status = 'active'", (alert_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    except OverflowError:
        return False
    finally:
        conn.close()


def dismiss_alert(alert_id: int, dismissed_by: str, note: Optional[str] = None) -> bool:
    """Marks an alert 'dismissed' with who/when/why. Always allowed regardless of current status (dismissing an already-auto_resolved alert is a legitimate 'yes, and don't bring it back' action). Returns False if no such id."""
    conn = get_connection()
    try:
        exists = conn.execute("SELECT id FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        if not exists:
            return False
        conn.execute(
            "UPDATE alerts SET status = 'dismissed', dismissed_by = ?, dismissed_at = ?, dismissal_note = ? WHERE id = ?",
            (dismissed_by, datetime.now(timezone.utc).isoformat(), note, alert_id),
        )
        conn.commit()
        return True
    except OverflowError:
        return False
    finally:
        conn.close()


def get_alert(alert_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return _alert_row_to_dict(row) if row else None
    except OverflowError:
        return None
    finally:
        conn.close()


def list_alerts(
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
    severity: Optional[str] = None,
    lease_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Any combination of filters may be applied together. Ordered by severity (high first) then most-recently-seen -- a notification feed's natural reading order."""
    conn = get_connection()
    try:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if alert_type:
            clauses.append("alert_type = ?")
            params.append(alert_type)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if lease_id is not None:
            clauses.append("lease_id = ?")
            params.append(lease_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM alerts {where} "
            "ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END, "
            "last_seen_at DESC, id DESC",
            params,
        ).fetchall()
        return [_alert_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Owner console: revenue/expense tracking (manual-entry today -- no
# billing integration exists in this codebase; external_source/
# external_id exist for a future one, see the CREATE TABLE comments in
# init_db()). Every route that calls these is gated by
# auth.require_owner(), never require_role() -- see api.py's /owner/*
# section and DECISIONS.md's "Owner console" entry.
# ----------------------------------------------------------------------

def create_revenue_entry(
    entry_date: str, amount: float, source: str, note: Optional[str],
    created_by_user_id: Optional[int], external_source: Optional[str] = None, external_id: Optional[str] = None,
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO revenue_entries (entry_date, amount, source, note, external_source, external_id, created_at, created_by_user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_date, amount, source, note, external_source, external_id, datetime.now(timezone.utc).isoformat(), created_by_user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM revenue_entries WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_revenue_entries() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM revenue_entries ORDER BY entry_date DESC, id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_revenue_entry(entry_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM revenue_entries WHERE id = ?", (entry_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def create_expense_entry(
    entry_date: str, amount: float, category: str, note: Optional[str],
    created_by_user_id: Optional[int], external_source: Optional[str] = None, external_id: Optional[str] = None,
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO expense_entries (entry_date, amount, category, note, external_source, external_id, created_at, created_by_user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_date, amount, category, note, external_source, external_id, datetime.now(timezone.utc).isoformat(), created_by_user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM expense_entries WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_expense_entries() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM expense_entries ORDER BY entry_date DESC, id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_expense_entry(entry_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM expense_entries WHERE id = ?", (entry_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ----------------------------------------------------------------------
# AI extraction telemetry: one row per model-backed extraction call
# (lease abstraction, rent-roll validation, ...). This is the data
# source for the owner console's "is extraction quality drifting"
# view (see api.py's /owner/ai-quality) and the basis a future
# per-account usage cap would count against. Deliberately append-only
# and cheap -- never on the request's critical path in a way that can
# fail the upload (callers swallow errors from here).
# ----------------------------------------------------------------------

def record_ai_extraction_run(
    *,
    engine: str,
    status: str,
    model: Optional[str] = None,
    kind: str = "lease_abstraction",
    lease_id: Optional[int] = None,
    field_count: Optional[int] = None,
    found_count: Optional[int] = None,
    high_count: Optional[int] = None,
    medium_count: Optional[int] = None,
    low_count: Optional[int] = None,
    not_found_count: Optional[int] = None,
    latency_ms: Optional[int] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    error_message: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO ai_extraction_runs (created_at, kind, engine, model, status, lease_id, "
            "field_count, found_count, high_count, medium_count, low_count, not_found_count, "
            "latency_ms, input_tokens, output_tokens, error_message, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(), kind, engine, model, status, lease_id,
                field_count, found_count, high_count, medium_count, low_count, not_found_count,
                latency_ms, input_tokens, output_tokens, error_message,
                json.dumps(detail) if detail is not None else None,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def link_ai_extraction_run_to_lease(run_id: int, lease_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE ai_extraction_runs SET lease_id = ? WHERE id = ?", (lease_id, run_id))
        conn.commit()
    finally:
        conn.close()


def record_training_round(*, round_label: str, report: Dict[str, Any], model: Optional[str] = None,
                          prompt_version: Optional[str] = None, corpus_seed: Optional[int] = None,
                          corpus_size: Optional[int] = None, changed_this_round: Optional[str] = None) -> int:
    """One row per measure-refine-remeasure round. `report` is the full
    extraction_scoring.aggregate() output (stored as JSON); the flat
    columns are the headline numbers pulled out for cheap trend queries."""
    cal = report.get("calibration") or {}
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO training_rounds (created_at, round_label, model, prompt_version, corpus_seed, corpus_size, "
            "documents, fields_evaluated, overall_accuracy, high_conf_wrong_count, high_conf_wrong_rate, "
            "calibration_gap, p_correct_given_high, p_correct_given_low, changed_this_round, report) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(), round_label, model, prompt_version, corpus_seed, corpus_size,
                report.get("documents"), report.get("fields_evaluated"), report.get("overall_accuracy"),
                report.get("high_conf_wrong_count"), report.get("high_conf_wrong_rate"),
                cal.get("calibration_gap"), cal.get("p_correct_given_high"), cal.get("p_correct_given_low"),
                changed_this_round, json.dumps(report),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_training_rounds(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM training_rounds ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["report"] = json.loads(d["report"]) if d.get("report") else None
            out.append(d)
        return out
    finally:
        conn.close()


def list_ai_extraction_runs(limit: int = 500, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        if kind:
            rows = conn.execute(
                "SELECT * FROM ai_extraction_runs WHERE kind = ? ORDER BY id DESC LIMIT ?", (kind, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ai_extraction_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d["detail"]) if d.get("detail") else None
            out.append(d)
        return out
    finally:
        conn.close()
