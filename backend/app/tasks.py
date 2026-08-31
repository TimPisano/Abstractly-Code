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

VALID_STATUSES = {"open", "in_progress", "done", "dismissed"}
VALID_PRIORITIES = {"normal", "high"}

# How long after a field edit a revert is still allowed -- see
# api.py's undo_lease_field_edit. Kept here (not in database.py, which
# has no business-rule constants elsewhere either) alongside the other
# task-workflow constants this module already owns.
UNDO_WINDOW_MINUTES = 10


def task_detail(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attaches resolved assignee/creator name+email and, if linked, the
    lease/discrepancy itself -- so the frontend doesn't need per-task
    follow-up requests to render a task card.

    For a lease-linked task, `lease` is the full effective lease
    (extracted_fields, each with its own value/source/confidence) --
    this IS the in-task document view this app supports (see PATCH
    /leases/<id>/fields/<name> for editing): the app has never stored
    raw uploaded file bytes, only structured extraction with page/quote
    citations per field, so "viewing the document" here means the same
    citation-backed field view every other lease screen already uses,
    not a raw PDF render. `field_edits` is every correction made to
    this lease WHILE working this specific task (task_id-scoped, not
    the lease's whole history -- see database.get_lease_field_edits)
    -- always present (possibly empty) whenever lease_id is set, so a
    reviewer opening a task can see exactly what was changed under it
    without a separate request.
    """
    result = dict(task)
    assignee = database.get_user(task["assigned_to_user_id"]) if task["assigned_to_user_id"] else None
    creator = database.get_user(task["created_by_user_id"])
    result["assigned_to"] = {"id": assignee["id"], "name": assignee["name"], "email": assignee["email"]} if assignee else None
    result["created_by"] = {"id": creator["id"], "name": creator["name"], "email": creator["email"]} if creator else None
    if task.get("lease_id"):
        lease = database.get_effective_lease(task["lease_id"])
        # A task's own lease_id is never repointed by a later
        # resubmission (repoint_lease_references only follows
        # discrepancies/tags/comments/assignments, deliberately NOT
        # amendments or tasks -- see its own docstring), so a task
        # created before a full Canvas-style
        # resubmission (POST /leases/<id>/resubmit, not an amendment)
        # would otherwise show and let a user edit an archived,
        # superseded row that no longer appears anywhere else in the
        # app. Resolve forward to whichever version is current so the
        # in-task view always reflects live data, same as every other
        # "current lease" reader in this app.
        if lease and lease.get("status") == "superseded":
            chain = database.get_lease_version_chain(task["lease_id"])
            current = next((v for v in chain if v.get("status") != "superseded"), None)
            if current and current["id"] != task["lease_id"]:
                lease = database.get_effective_lease(current["id"])
                result["lease_redirected_from_id"] = task["lease_id"]
        result["lease"] = lease
        result["field_edits"] = database.get_lease_field_edits(task_id=task["id"])
    if task.get("discrepancy_id"):
        result["discrepancy"] = database.get_discrepancy(task["discrepancy_id"])
    # Team discussion on this task -- separate from field_edits (a
    # data-correction audit trail) and always present regardless of
    # whether the task is lease-linked, since a comment like "checked
    # with the broker, this is intentional" makes sense on any task.
    result["comments"] = database.get_task_comments(task["id"])
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
