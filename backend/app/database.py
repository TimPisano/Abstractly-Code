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

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "lease_portfolio.db")

# Module-level, overridable so tests can point at an isolated temp DB
# without touching the real one.
_db_path = DEFAULT_DB_PATH


def configure(db_path: str) -> None:
    """Point the module at a different DB file (used by tests)."""
    global _db_path
    _db_path = db_path


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
    }
    for column, sql_type in new_columns.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE leases ADD COLUMN {column} {sql_type}")


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
        conn.commit()
    finally:
        conn.close()


def reset_db() -> None:
    """Drop and recreate all tables. Used by tests for a clean slate."""
    conn = get_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS lease_tags")
        conn.execute("DROP TABLE IF EXISTS leases")
        conn.execute("DROP TABLE IF EXISTS waitlist_signups")
        conn.execute("DROP TABLE IF EXISTS activity_log")
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
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO leases (filename, uploaded_at, extracted_fields, document_type, base_lease_id, "
            "date_candidates, display_name, source_page_start, source_page_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            ),
        )
        conn.commit()
        return cur.lastrowid
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


def get_all_leases(document_type: Optional[str] = "lease") -> List[Dict[str, Any]]:
    """
    Base leases only by default (document_type='lease'), ordered by
    upload time. Pass document_type=None to include amendments too.
    """
    conn = get_connection()
    try:
        if document_type is None:
            rows = conn.execute("SELECT * FROM leases ORDER BY uploaded_at").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM leases WHERE document_type = ? ORDER BY uploaded_at",
                (document_type,),
            ).fetchall()
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
    finally:
        conn.close()


def get_effective_fields(lease_id: int) -> Optional[Dict[str, Any]]:
    """
    Merge a base lease's extracted_fields with its amendments' non-null
    fields — later-uploaded amendments take priority per field. Returns
    None if lease_id doesn't exist. This is what portfolio metrics, risk
    analysis, comparison, and the Q&A engine should read from, not the
    raw base lease alone, so an amendment (e.g. a rent increase
    addendum) is actually reflected in portfolio math.
    """
    base = get_lease(lease_id)
    if not base:
        return None

    effective = dict(base["extracted_fields"])
    for amendment in get_amendments(lease_id):
        for field_name, field_data in amendment["extracted_fields"].items():
            if isinstance(field_data, dict) and field_data.get("value") is not None:
                effective[field_name] = field_data
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
    """All base leases (not amendments) with their fields amendment-merged."""
    return [get_effective_lease(lease["id"]) for lease in get_all_leases(document_type="lease")]


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
    except sqlite3.IntegrityError:
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
