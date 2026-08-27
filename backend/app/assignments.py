"""
Assignment ownership: giving a lease, discrepancy, or property a
specific team-member owner, with status tracking (assigned/in_review/
resolved). See database.py's assignments table for the persistence
layer -- one table, three target types, one active assignment per
target (natural-key upsert, same atomic pattern already used for
discrepancies/alerts).
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from app import database
from app import tasks as tasks_module
from app import messaging
from app.portfolio import _normalize_building_address

VALID_TARGET_TYPES = {"lease", "discrepancy", "property"}
VALID_STATUSES = {"assigned", "in_review", "resolved"}


def derive_target_key(target_type: str, raw: str) -> str:
    """
    Turns whatever the caller supplied for this target_type into the
    canonical string assignments.target_key is keyed on:
      - lease / discrepancy: an int id, as a string (str(int(raw))
        also validates it's actually numeric -- raises ValueError
        otherwise, same as the route-level <int:...> converter would).
      - property: a normalized building address (see
        _normalize_building_address) so "123 Main St, Suite 100" and
        "123 Main St, Suite 200" -- two units at the same building --
        resolve to the SAME property assignment, matching how every
        other property-scoped feature in this app already groups by
        building, not by suite.
    """
    if target_type not in VALID_TARGET_TYPES:
        raise ValueError(f"target_type must be one of: {', '.join(sorted(VALID_TARGET_TYPES))}")
    if target_type in ("lease", "discrepancy"):
        return str(int(raw))
    normalized = _normalize_building_address(raw)
    if not normalized:
        raise ValueError("property address is required for a property assignment")
    return normalized


def assignment_detail(assignment: Dict[str, Any]) -> Dict[str, Any]:
    """Attaches resolved assignee/assigner name+email (via database.get_user) so the frontend doesn't need a second round trip per assignment row."""
    result = dict(assignment)
    assignee = database.get_user(assignment["assigned_to_user_id"])
    assigner = database.get_user(assignment["assigned_by_user_id"])
    result["assigned_to"] = {"id": assignee["id"], "name": assignee["name"], "email": assignee["email"]} if assignee else None
    result["assigned_by"] = {"id": assigner["id"], "name": assigner["name"], "email": assigner["email"]} if assigner else None
    return result


def compute_today_view(user_id: int, reference_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Everything relevant to one user's work "today": their open
    (not-yet-resolved) assignments, their tasks due today or overdue,
    anything new since their last login (discrepancies, alerts, team
    comments), their unread messages, and the portfolio's
    currently-active alerts.

    `reference_date` defaults to the real current date -- pass an
    explicit one in tests for determinism, same convention
    app/portfolio.py already uses for its own "today"-relative
    calculations.

    "New since last login" is measured against previous_login_at, NOT
    last_login_at -- last_login_at gets overwritten the instant THIS
    session started (see database.update_user_last_login), so by the
    time this runs it would always equal "now" and nothing would ever
    show up as new. previous_login_at holds the login before this one,
    which is what "since I was last here" actually means. A user who
    has never logged in before (previous_login_at is NULL) gets an
    empty "new since" section rather than everything ever created --
    there's no meaningful baseline to diff against yet.

    Active alerts stay portfolio-wide, not filtered to this user --
    alerts have no assignee concept of their own (they're a fact about
    the portfolio, not a task handed to someone), matching the "no
    per-account data scoping" precedent every other shared view in
    this app already follows (see DECISIONS.md). Tasks, assignments,
    and unread messages ARE filtered to this user, since those really
    are personal to them.
    """
    reference_date = reference_date or datetime.now(timezone.utc).date()
    today_iso = reference_date.isoformat()

    open_assignments = [
        a for a in database.list_assignments(assigned_to_user_id=user_id) if a["status"] != "resolved"
    ]

    assigned_leases, assigned_discrepancies, assigned_properties = [], [], []
    for assignment in open_assignments:
        detail = assignment_detail(assignment)
        if assignment["target_type"] == "lease":
            lease = database.get_effective_lease(assignment["lease_id"]) if assignment["lease_id"] else None
            detail["lease"] = lease
            assigned_leases.append(detail)
        elif assignment["target_type"] == "discrepancy":
            disc = database.get_discrepancy(assignment["discrepancy_id"]) if assignment["discrepancy_id"] else None
            detail["discrepancy"] = disc
            assigned_discrepancies.append(detail)
        else:
            assigned_properties.append(detail)

    active_alerts = database.list_alerts(status="active")
    severity_order = {"high": 0, "medium": 1, "low": 2}
    active_alerts.sort(key=lambda a: severity_order.get(a["severity"], 3))

    due_tasks = [
        tasks_module.task_detail(t) for t in database.get_tasks_due_today_or_overdue(user_id, today_iso)
    ]

    user = database.get_user(user_id) or {}
    since = user.get("previous_login_at")
    if since:
        new_discrepancies = [d for d in database.list_discrepancies() if d["first_detected_at"] > since]
        new_alerts = [a for a in database.list_alerts() if a["first_detected_at"] > since]
        new_comments = [c for c in database.get_recent_comments(limit=100) if c["created_at"] > since]
    else:
        new_discrepancies, new_alerts, new_comments = [], [], []

    unread_by_thread = database.get_unread_counts_for_user(user_id)
    unread_threads = [
        messaging.thread_detail(database.get_thread(tid), user_id)
        for tid in unread_by_thread
        if database.get_thread(tid) is not None
    ]

    return {
        "user_id": user_id,
        "reference_date": today_iso,
        "assigned_leases": assigned_leases,
        "assigned_discrepancies": assigned_discrepancies,
        "assigned_properties": assigned_properties,
        "active_alerts": active_alerts,
        "tasks_due_today_or_overdue": due_tasks,
        "new_since_last_login": {
            "since": since,
            "discrepancies": new_discrepancies,
            "alerts": new_alerts,
            "comments": new_comments,
        },
        "unread_messages": {
            "total_unread": sum(unread_by_thread.values()),
            "threads": unread_threads,
        },
        "summary": {
            "total_open_assignments": len(open_assignments),
            "assigned_lease_count": len(assigned_leases),
            "assigned_discrepancy_count": len(assigned_discrepancies),
            "assigned_property_count": len(assigned_properties),
            "active_alert_count": len(active_alerts),
            "high_severity_alert_count": sum(1 for a in active_alerts if a["severity"] == "high"),
            "tasks_due_today_or_overdue_count": len(due_tasks),
            "new_since_last_login_count": len(new_discrepancies) + len(new_alerts) + len(new_comments),
            "unread_message_count": sum(unread_by_thread.values()),
        },
    }
