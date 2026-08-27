"""
Internal team messaging: direct (1-on-1) and group threads, separate
from the existing lease/discrepancy comments feature (that's notes
about a specific record, visible to the whole team; this is private
workplace chat between specific people, tied to no record at all).

Isolation is the whole point of this feature working correctly --
every function here that touches a thread's content requires the
caller to already be a verified participant (see
database.is_thread_participant), enforced at the database layer, not
just this module. See api.py's routes for where that check actually
gets applied before any read/write.
"""
from typing import Any, Dict, List, Optional

from . import database

VALID_THREAD_TYPES = {"direct", "group"}


def thread_detail(thread: Dict[str, Any], viewer_user_id: int) -> Dict[str, Any]:
    """
    Attaches participant info (id/name/email, never password_hash --
    see api.py's _user_public for the same rule applied to team
    management) and this viewer's own unread count, so the frontend
    doesn't need per-thread follow-up requests to render a thread list.
    """
    result = dict(thread)
    participants = []
    for p in database.get_thread_participants(thread["id"]):
        user = database.get_user(p["user_id"])
        if user is not None:
            participants.append({"id": user["id"], "name": user["name"], "email": user["email"], "joined_at": p["joined_at"]})
    result["participants"] = participants
    unread = database.get_unread_counts_for_user(viewer_user_id)
    result["unread_count"] = unread.get(thread["id"], 0)

    # For a direct thread, the frontend almost always wants "who am I
    # talking to" without having to filter participants client-side --
    # the other participant, or None for the degenerate case of a
    # thread with yourself (allowed, not special-cased away).
    if thread["thread_type"] == "direct":
        other = next((p for p in result["participants"] if p["id"] != viewer_user_id), None)
        result["other_participant"] = other
    return result


def message_detail(message: Dict[str, Any]) -> Dict[str, Any]:
    """Attaches the sender's name/email so the frontend doesn't need a lookup per message."""
    result = dict(message)
    sender = database.get_user(message["sender_user_id"])
    result["sender"] = {"id": sender["id"], "name": sender["name"], "email": sender["email"]} if sender else None
    return result
