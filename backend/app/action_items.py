"""
The single prioritized, chronological "what do I need to do so I never
miss a date" list -- merges three things that already exist separately
(tasks with a due_date, lease expirations, renewal-notice deadlines)
into one list sorted soonest-first, overdue naturally sorting to the
top since its date is already in the past. Nothing here computes a new
date; it only tags and re-sorts dates portfolio.py and database.py
already compute, the same way assignments.compute_today_view merges
several existing sources into one "today" response without owning any
of their underlying logic.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app import database
from app import tasks as tasks_module
from app.portfolio import compute_expiration_alerts


def _task_entry(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "category": "task",
        "date": task["due_date"],
        "title": task["title"],
        "lease_id": task.get("lease_id"),
        "tenant": None,
        "priority": task.get("priority"),
        "detail": tasks_module.task_detail(task),
    }


def _expiration_entry(entry: Dict[str, Any], reference_date: date) -> Dict[str, Any]:
    # entry["days_remaining"] is already computed by compute_expiration_alerts
    # against the same reference_date -- deriving the sort date from it
    # (rather than re-parsing entry["lease_end_date"], which is the RAW
    # extracted field value, not guaranteed ISO format) is exact and
    # avoids a second, possibly-inconsistent date parse.
    sort_date = reference_date + timedelta(days=entry["days_remaining"])
    return {
        "category": "lease_expiration",
        "date": sort_date.isoformat(),
        "title": f"Lease expires — {entry.get('display_name') or entry.get('tenant') or 'Unknown tenant'}",
        "lease_id": entry.get("lease_id"),
        "tenant": entry.get("tenant"),
        "priority": None,
        "detail": entry,
    }


def _renewal_deadline_entry(entry: Dict[str, Any], reference_date: date) -> Dict[str, Any]:
    sort_date = reference_date + timedelta(days=entry["days_remaining"])
    return {
        "category": "renewal_deadline",
        "date": sort_date.isoformat(),
        "title": f"Renewal notice deadline — {entry.get('display_name') or entry.get('tenant') or 'Unknown tenant'}",
        "lease_id": entry.get("lease_id"),
        "tenant": entry.get("tenant"),
        "priority": None,
        "detail": entry,
    }


def compute_action_items(
    user_id: int,
    leases: List[Dict[str, Any]],
    reference_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    One chronologically-sorted list combining:
      - this user's open tasks with a due date (overdue, due today, and
        due later -- unlike get_tasks_due_today_or_overdue alone, which
        stops at today)
      - portfolio-wide lease expirations and renewal-notice deadlines
        within compute_expiration_alerts' 90-day window

    Each item is tagged with a `category` and a single ISO `date` so the
    frontend can render one list without caring which source an item
    came from. Sorting by that date string (not by days_remaining, and
    not by severity) is what makes an overdue renewal deadline outrank
    a lease expiring in 45 days, which outranks a task due next week --
    exactly the "what do I need to do so I never miss a date" ordering
    this view exists to provide, not a portfolio-wide severity ranking
    (that's what /portfolio/attention and /alerts are already for).
    """
    reference_date = reference_date or datetime.now(timezone.utc).date()
    today_iso = reference_date.isoformat()
    tomorrow_iso = (reference_date + timedelta(days=1)).isoformat()

    overdue_or_due_today = database.get_tasks_due_today_or_overdue(user_id, today_iso)
    due_later = [
        t for t in database.list_tasks(assigned_to_user_id=user_id, due_after=tomorrow_iso)
        if t["status"] not in ("done", "dismissed")
    ]
    task_items = [_task_entry(t) for t in overdue_or_due_today + due_later]

    expiration_alerts = compute_expiration_alerts(leases, reference_date=reference_date)
    expiring_items = [_expiration_entry(e, reference_date) for e in expiration_alerts["expiring"]]
    renewal_items = [_renewal_deadline_entry(e, reference_date) for e in expiration_alerts["renewal_deadlines"]]

    items = task_items + expiring_items + renewal_items
    items.sort(key=lambda item: item["date"])
    for item in items:
        item["overdue"] = item["date"] < today_iso
    return items
