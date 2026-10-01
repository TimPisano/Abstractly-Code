"""
Quota and usage enforcement for protecting Anthropic API spend.

Functions:
- check_team_quota: rejects uploads if team is at/over monthly limit
- check_file_limits: rejects files that are too large/many-pages
- find_duplicate_upload: finds existing lease with same content hash
- log_usage_event: logs extraction attempt and fires budget alerts
- _extraction_rate_limited: checks if user hit per-minute rate limit
"""

import os
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import sqlite3

from app import database
from app import email_service
from app.usage_limits_config import (
    DEFAULT_MONTHLY_DOCUMENT_QUOTA,
    DEFAULT_MONTHLY_PAGE_QUOTA,
    DEFAULT_MONTHLY_BUDGET_USD,
    MAX_FILE_SIZE_MB,
    MAX_PAGES_PER_FILE,
    EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE,
    COST_PER_INPUT_TOKEN_USD,
    COST_PER_OUTPUT_TOKEN_USD,
    BUDGET_ALERT_THRESHOLD_PCTS,
)

# In-memory rate limiter: {user_id: [timestamp1, timestamp2, ...]}
# Timestamps older than 1 minute are pruned on each check.
_extraction_rate_limit_window = {}


def _get_team_quotas(team_id: int) -> Tuple[int, int, float]:
    """
    Returns (document_quota, page_quota, budget_usd) for a team.
    Uses team's overrides if set, otherwise falls back to defaults.
    """
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT monthly_document_quota, monthly_page_quota, monthly_budget_usd FROM teams WHERE id = ?",
            (team_id,)
        ).fetchone()
        if not row:
            return DEFAULT_MONTHLY_DOCUMENT_QUOTA, DEFAULT_MONTHLY_PAGE_QUOTA, DEFAULT_MONTHLY_BUDGET_USD

        doc_quota = row[0] if row[0] is not None else DEFAULT_MONTHLY_DOCUMENT_QUOTA
        page_quota = row[1] if row[1] is not None else DEFAULT_MONTHLY_PAGE_QUOTA
        budget = row[2] if row[2] is not None else DEFAULT_MONTHLY_BUDGET_USD
        return doc_quota, page_quota, budget
    finally:
        conn.close()


def check_team_quota(team_id: int) -> Optional[str]:
    """
    Returns a plain-English rejection message if the team is at/over
    its monthly quota for documents or pages. None means quota is OK.
    Computed fresh each call (current calendar month from usage_events).
    """
    conn = database.get_connection()
    try:
        now = datetime.now(timezone.utc)
        current_month = now.strftime("%Y-%m")

        doc_quota, page_quota, _ = _get_team_quotas(team_id)

        docs_used = conn.execute(
            "SELECT COUNT(*) FROM usage_events WHERE team_id = ? AND strftime('%Y-%m', created_at) = ? AND event_type != 'dedup_reuse'",
            (team_id, current_month)
        ).fetchone()[0]

        if docs_used >= doc_quota:
            return f"Your team has used all {doc_quota} documents included this month. Contact an admin to raise your limit."

        pages_used = conn.execute(
            "SELECT COALESCE(SUM(pages), 0) FROM usage_events WHERE team_id = ? AND strftime('%Y-%m', created_at) = ? AND event_type != 'dedup_reuse'",
            (team_id, current_month)
        ).fetchone()[0]

        if pages_used >= page_quota:
            return f"Your team has used all {page_quota} pages included this month. Contact an admin to raise your limit."

        return None
    finally:
        conn.close()


def check_file_limits(file_bytes: bytes, filename: str) -> Optional[str]:
    """
    Returns a plain-English rejection message if the file is too large
    or has too many pages. None means file is OK.
    """
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        return f"File too large: {file_size_mb:.1f}MB exceeds limit of {MAX_FILE_SIZE_MB}MB."

    # Try to count pages for PDF/supported formats. Non-PDF formats skip
    # page counting and rely on size check alone.
    if filename.lower().endswith('.pdf'):
        try:
            from app import document_extractor
            pages = document_extractor.extract_pages(file_bytes, filename, None)
            page_count = len(pages)
            if page_count > MAX_PAGES_PER_FILE:
                return f"File has too many pages: {page_count} exceeds limit of {MAX_PAGES_PER_FILE}."
        except Exception:
            # If page extraction fails for any reason, let the main
            # extraction pipeline handle it (will report a more specific error).
            pass

    return None


def find_duplicate_upload(team_id: int, content_hash: str) -> Optional[Dict[str, Any]]:
    """
    Looks up an existing, non-superseded lease for this team whose
    stored content_hash matches. Returns the lease's effective fields
    if found, else None.
    """
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM leases WHERE content_hash = ? AND status = 'active' LIMIT 1",
            (content_hash,)
        ).fetchone()
        if not row:
            return None

        lease_id = row[0]
        lease = database.get_lease(lease_id)
        if lease:
            return {
                "id": lease["id"],
                "fields": database.get_effective_fields(lease_id),
                "display_name": lease.get("display_name", ""),
                "source_page_start": lease.get("source_page_start"),
                "source_page_end": lease.get("source_page_end"),
            }
        return None
    finally:
        conn.close()


def log_usage_event(
    team_id: int,
    user_id: int,
    lease_id: Optional[int],
    pages: Optional[int],
    token_usage: Optional[Dict[str, int]],
    event_type: str = "extraction"
) -> None:
    """
    Logs a usage event (extraction attempt, success or failure) and
    fires budget-alert emails exactly once per threshold per month.

    token_usage: {"input_tokens": N, "output_tokens": N} or None (for
    regex engine, which makes no API call).
    """
    conn = database.get_connection()
    try:
        input_tokens = token_usage.get("input_tokens") if token_usage else None
        output_tokens = token_usage.get("output_tokens") if token_usage else None

        estimated_cost = None
        if input_tokens is not None and output_tokens is not None:
            estimated_cost = (
                input_tokens * COST_PER_INPUT_TOKEN_USD +
                output_tokens * COST_PER_OUTPUT_TOKEN_USD
            )

        now = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO usage_events (team_id, user_id, lease_id, pages, input_tokens, output_tokens, estimated_cost_usd, event_type, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (team_id, user_id, lease_id, pages, input_tokens, output_tokens, estimated_cost, event_type, now.isoformat())
        )
        conn.commit()

        # Check budget and fire alerts if needed.
        _, _, budget_usd = _get_team_quotas(team_id)
        current_month = now.strftime("%Y-%m")

        monthly_spent = conn.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM usage_events WHERE team_id = ? AND strftime('%Y-%m', created_at) = ?",
            (team_id, current_month)
        ).fetchone()[0]

        admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
        if not admin_email:
            return

        for threshold_pct in BUDGET_ALERT_THRESHOLD_PCTS:
            threshold_usd = budget_usd * (threshold_pct / 100.0)
            if monthly_spent >= threshold_usd:
                alert_column = f"budget_alert_{threshold_pct}_sent_month"
                row = conn.execute(
                    f"SELECT {alert_column} FROM teams WHERE id = ?",
                    (team_id,)
                ).fetchone()

                sent_month = row[0] if row else None
                if sent_month != current_month:
                    conn.execute(
                        f"UPDATE teams SET {alert_column} = ? WHERE id = ?",
                        (current_month, team_id)
                    )
                    conn.commit()

                    team_row = conn.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone()
                    team_name = team_row[0] if team_row else f"team {team_id}"

                    subject = f"Budget alert: team '{team_name}' at {threshold_pct}% of monthly spend"
                    body = (
                        f"Team '{team_name}' has spent ${monthly_spent:.2f} of its ${budget_usd:.2f} "
                        f"monthly budget ({threshold_pct}%). Remaining: ${budget_usd - monthly_spent:.2f}."
                    )
                    email_service.send_operational_alert(admin_email, subject, body)
    finally:
        conn.close()


def _extraction_rate_limited(user_id: int) -> bool:
    """
    Returns True if the user has hit the per-minute rate limit.
    Rate limit window is in-memory; timestamps older than 1 minute
    are pruned automatically.
    """
    global _extraction_rate_limit_window
    now = time.time()
    one_minute_ago = now - 60

    if user_id not in _extraction_rate_limit_window:
        _extraction_rate_limit_window[user_id] = []

    window = _extraction_rate_limit_window[user_id]
    window = [ts for ts in window if ts > one_minute_ago]
    _extraction_rate_limit_window[user_id] = window

    if len(window) >= EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE:
        return True

    window.append(now)
    return False


def _reset_extraction_rate_limit_for_tests() -> None:
    """
    Clears the in-memory rate limiter. Call from test fixtures to
    reset state between test cases.
    """
    global _extraction_rate_limit_window
    _extraction_rate_limit_window = {}
