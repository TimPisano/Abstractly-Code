"""
General-purpose tasks: title/description/due date/assignee/status,
optionally linked to a specific lease, discrepancy, or property.
Distinct from assignments.py's "who owns this record" concept --
a task is a concrete to-do (with its own due date and free-text
description) that may or may not be about a specific record, whereas
an assignment IS the record's owner. A discrepancy can have both: an
assignee (assignments.py) and, separately, one or more tasks created
to actually go resolve it (see create_task_from_discrepancy below).
"""
from typing import Any, Dict, Optional

from app import database

VALID_STATUSES = {"open", "in_progress", "done"}


def task_detail(task: Dict[str, Any]) -> Dict[str, Any]:
    """Attaches resolved assignee/creator name+email and, if linked, the lease/discrepancy itself -- so the frontend doesn't need per-task follow-up requests to render a task card."""
    result = dict(task)
    assignee = database.get_user(task["assigned_to_user_id"]) if task["assigned_to_user_id"] else None
    creator = database.get_user(task["created_by_user_id"])
    result["assigned_to"] = {"id": assignee["id"], "name": assignee["name"], "email": assignee["email"]} if assignee else None
    result["created_by"] = {"id": creator["id"], "name": creator["name"], "email": creator["email"]} if creator else None
    if task.get("lease_id"):
        result["lease"] = database.get_effective_lease(task["lease_id"])
    if task.get("discrepancy_id"):
        result["discrepancy"] = database.get_discrepancy(task["discrepancy_id"])
    return result


def create_task_from_discrepancy(discrepancy_id: int, created_by_user_id: int, assigned_to_user_id: Optional[int] = None, due_date: Optional[str] = None) -> Dict[str, Any]:
    """Carries over the discrepancy's own message/category/severity into the task's title/description, and links lease_id straight through, so the assignee doesn't have to re-open the discrepancy just to know what the task is about."""
    disc = database.get_discrepancy(discrepancy_id)
    if disc is None:
        raise ValueError("Discrepancy not found")
    title = f"Resolve discrepancy: {disc['message']}"
    description = (
        f"Category: {disc['category']}\n"
        f"Severity: {disc.get('severity') or 'n/a'}\n"
        f"Field: {disc.get('field') or 'n/a'}\n\n"
        f"{disc['message']}"
    )
    task_id = database.create_task(
        title=title,
        created_by_user_id=created_by_user_id,
        description=description,
        due_date=due_date,
        assigned_to_user_id=assigned_to_user_id,
        lease_id=disc.get("lease_id"),
        discrepancy_id=discrepancy_id,
        source_type="discrepancy",
        source_natural_key=disc["natural_key"],
    )
    return task_detail(database.get_task(task_id))


def create_task_from_alert(alert_id: int, created_by_user_id: int, assigned_to_user_id: Optional[int] = None, due_date: Optional[str] = None) -> Dict[str, Any]:
    alert = database.get_alert(alert_id)
    if alert is None:
        raise ValueError("Alert not found")
    title = f"Follow up: {alert['title']}"
    description = f"Severity: {alert['severity']}\n\n{alert['message']}"
    task_id = database.create_task(
        title=title,
        created_by_user_id=created_by_user_id,
        description=description,
        due_date=due_date,
        assigned_to_user_id=assigned_to_user_id,
        lease_id=alert.get("lease_id"),
        source_type="alert",
        source_natural_key=alert["natural_key"],
    )
    return task_detail(database.get_task(task_id))
