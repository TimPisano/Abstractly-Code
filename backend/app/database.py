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


def init_db() -> None:
    """Create the leases table if it doesn't already exist. Safe to call repeatedly."""
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
                FOREIGN KEY (base_lease_id) REFERENCES leases(id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def reset_db() -> None:
    """Drop and recreate the leases table. Used by tests for a clean slate."""
    conn = get_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS leases")
        conn.commit()
    finally:
        conn.close()
    init_db()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["extracted_fields"] = json.loads(d["extracted_fields"])
    return d


def insert_lease(
    filename: str,
    extracted_fields: Dict[str, Any],
    document_type: str = "lease",
    base_lease_id: Optional[int] = None,
) -> int:
    """Persist one extracted document. Returns its new lease id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO leases (filename, uploaded_at, extracted_fields, document_type, base_lease_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                filename,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(extracted_fields),
                document_type,
                base_lease_id,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_lease(lease_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        return _row_to_dict(row) if row else None
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
