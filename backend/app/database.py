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
    }
    for column, sql_type in new_columns.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE leases ADD COLUMN {column} {sql_type}")


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
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM discrepancies WHERE natural_key = ?", (natural_key,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE discrepancies SET category = ?, field = ?, severity = ?, message = ?, "
                "details = ?, lease_id = ?, related_lease_id = ?, last_seen_at = ? WHERE id = ?",
                (category, field, severity, message, json.dumps(details), lease_id, related_lease_id, now, existing["id"]),
            )
            conn.commit()
            return existing["id"]

        cur = conn.execute(
            "INSERT INTO discrepancies (discrepancy_type, natural_key, lease_id, related_lease_id, "
            "category, field, severity, message, details, status, first_detected_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
            (discrepancy_type, natural_key, lease_id, related_lease_id, category, field, severity, message, json.dumps(details), now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


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
) -> int:
    """Exactly one of lease_id/discrepancy_id is expected to be set -- enforced by the API layer, not here, consistent with how validation is layered throughout this module."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO comments (lease_id, discrepancy_id, author_name, author_email, body, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (lease_id, discrepancy_id, author_name, author_email, body, datetime.now(timezone.utc).isoformat()),
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
    finally:
        conn.close()


def get_discrepancy_comments(discrepancy_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM comments WHERE discrepancy_id = ? ORDER BY created_at ASC, id ASC", (discrepancy_id,)
        ).fetchall()
        return [dict(r) for r in rows]
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
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id, status FROM alerts WHERE natural_key = ?", (natural_key,)).fetchone()
        if existing:
            new_status = "active" if existing["status"] == "auto_resolved" else existing["status"]
            conn.execute(
                "UPDATE alerts SET severity = ?, title = ?, message = ?, details = ?, lease_id = ?, "
                "status = ?, last_seen_at = ? WHERE id = ?",
                (severity, title, message, json.dumps(details), lease_id, new_status, now, existing["id"]),
            )
            conn.commit()
            return existing["id"]

        cur = conn.execute(
            "INSERT INTO alerts (alert_type, natural_key, lease_id, severity, title, message, details, "
            "status, first_detected_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (alert_type, natural_key, lease_id, severity, title, message, json.dumps(details), now, now),
        )
        conn.commit()
        return cur.lastrowid
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
