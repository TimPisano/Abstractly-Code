"""
Tests for internal team messaging: database.py's thread/message CRUD,
app/messaging.py's enrichment, and the GET/POST /threads*,
GET/POST /threads/<id>/messages, /threads/<id>/read,
/messages/unread-count routes.

The isolation requirement is the whole point of this feature -- it
gets more test coverage here than any single other behavior, both at
the database layer directly and through the real HTTP routes.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_discrepancies.py.
"""

import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password
from app import messaging


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _make_user(email, name="Test User", role="analyst"):
    return database.create_user(email, name, hash_password("password123"), role=role)["id"]


def _client_for(user_id, role="analyst"):
    user = database.get_user(user_id)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = user["email"]
        sess["name"] = user["name"]
        sess["role"] = role
    return client


# ------------------------------------------------------------------
# database.py: threads + messages
# ------------------------------------------------------------------

def test_create_direct_thread_reuses_existing():
    db_path = _fresh_temp_db()
    try:
        a = _make_user("a@example.com")
        b = _make_user("b@example.com")
        t1 = database.create_thread("direct", [a, b], a)
        t2 = database.create_thread("direct", [a, b], b)
        assert t1 == t2, "starting a DM with someone you already have a thread with must reuse it"
        t3 = database.create_thread("direct", [b, a], a)  # order shouldn't matter
        assert t3 == t1
    finally:
        os.unlink(db_path)
    print("✓ test_create_direct_thread_reuses_existing: PASS")


def test_create_group_thread_never_reused():
    db_path = _fresh_temp_db()
    try:
        a, b, c = _make_user("a@example.com"), _make_user("b@example.com"), _make_user("c@example.com")
        t1 = database.create_thread("group", [a, b, c], a, name="Team Chat")
        t2 = database.create_thread("group", [a, b, c], a, name="Team Chat")
        assert t1 != t2, "group threads are never deduped, even with identical participants/name"
        assert len(database.get_thread_participants(t1)) == 3
    finally:
        os.unlink(db_path)
    print("✓ test_create_group_thread_never_reused: PASS")


def test_is_thread_participant():
    db_path = _fresh_temp_db()
    try:
        a, b, c = _make_user("a@example.com"), _make_user("b@example.com"), _make_user("c@example.com")
        t = database.create_thread("direct", [a, b], a)
        assert database.is_thread_participant(t, a) is True
        assert database.is_thread_participant(t, b) is True
        assert database.is_thread_participant(t, c) is False
        assert database.is_thread_participant(999999, a) is False
    finally:
        os.unlink(db_path)
    print("✓ test_is_thread_participant: PASS")


def test_messages_ordered_and_since_filter_works():
    db_path = _fresh_temp_db()
    try:
        a, b = _make_user("a@example.com"), _make_user("b@example.com")
        t = database.create_thread("direct", [a, b], a)
        database.insert_message(t, a, "first")
        m2 = database.insert_message(t, b, "second")
        database.insert_message(t, a, "third")

        all_msgs = database.get_messages(t)
        assert [m["body"] for m in all_msgs] == ["first", "second", "third"]

        since_msg = database.get_message(m2)
        newer = database.get_messages(t, since=since_msg["created_at"])
        assert [m["body"] for m in newer] == ["third"], "since= must only return messages strictly after that timestamp"
    finally:
        os.unlink(db_path)
    print("✓ test_messages_ordered_and_since_filter_works: PASS")


def test_unread_counts_exclude_own_messages_and_respect_last_read():
    db_path = _fresh_temp_db()
    try:
        a, b = _make_user("a@example.com"), _make_user("b@example.com")
        t = database.create_thread("direct", [a, b], a)

        database.insert_message(t, a, "hello from a")
        assert database.get_unread_counts_for_user(a).get(t, 0) == 0, "your own message is never unread for you"
        assert database.get_unread_counts_for_user(b).get(t, 0) == 1, "but it IS unread for the other participant"

        database.mark_thread_read(t, b)
        assert database.get_unread_counts_for_user(b).get(t, 0) == 0, "marking read clears it"

        database.insert_message(t, a, "second message")
        assert database.get_unread_counts_for_user(b).get(t, 0) == 1, "a new message after mark-read is unread again"
    finally:
        os.unlink(db_path)
    print("✓ test_unread_counts_exclude_own_messages_and_respect_last_read: PASS")


def test_concurrent_message_sends_all_persist():
    """Sanity check: concurrent sends to the same thread must not raise or lose any message -- plain INSERTs on a shared table, not a natural-key upsert, so this is really confirming SQLite's own concurrency handling holds under this app's connection pattern."""
    db_path = _fresh_temp_db()
    try:
        a, b = _make_user("a@example.com"), _make_user("b@example.com")
        t = database.create_thread("direct", [a, b], a)
        errors = []
        lock = threading.Lock()

        def send(i):
            try:
                database.insert_message(t, a if i % 2 == 0 else b, f"message {i}")
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=send, args=(i,)) for i in range(30)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert errors == [], f"concurrent sends must never raise: {errors}"
        assert len(database.get_messages(t, limit=100)) == 30
    finally:
        os.unlink(db_path)
    print("✓ test_concurrent_message_sends_all_persist: PASS")


# ------------------------------------------------------------------
# Routes -- including the explicit isolation requirement
# ------------------------------------------------------------------

def test_threads_route_requires_login():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        assert client.get("/threads").status_code == 401
        assert client.post("/threads", json={}).status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_threads_route_requires_login: PASS")


def test_create_direct_thread_route_and_send_message():
    db_path = _fresh_temp_db()
    try:
        a = _make_user("a@example.com", name="Alice")
        b = _make_user("b@example.com", name="Bob")
        client_a = _client_for(a)

        resp = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b]})
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["thread_type"] == "direct"
        assert data["other_participant"]["name"] == "Bob"
        thread_id = data["id"]

        resp = client_a.post(f"/threads/{thread_id}/messages", json={"body": "hey Bob"})
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["sender"]["name"] == "Alice"
        assert resp.get_json()["body"] == "hey Bob"
    finally:
        os.unlink(db_path)
    print("✓ test_create_direct_thread_route_and_send_message: PASS")


def test_create_direct_thread_route_reuses_and_returns_200():
    db_path = _fresh_temp_db()
    try:
        a = _make_user("a@example.com")
        b = _make_user("b@example.com")
        client_a = _client_for(a)
        first = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b]})
        second = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b]})
        assert first.get_json()["id"] == second.get_json()["id"]
        assert second.status_code == 200, "reusing an existing thread is 200, not 201 (nothing new created)"
    finally:
        os.unlink(db_path)
    print("✓ test_create_direct_thread_route_reuses_and_returns_200: PASS")


def test_create_thread_route_validation():
    db_path = _fresh_temp_db()
    try:
        a = _make_user("a@example.com")
        client_a = _client_for(a)

        resp = client_a.post("/threads", json={"thread_type": "not_a_type", "participant_user_ids": [999]})
        assert resp.status_code == 400

        resp = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [999999]})
        assert resp.status_code == 400, "a nonexistent participant must be rejected"

        b, c = _make_user("b@example.com"), _make_user("c@example.com")
        resp = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b, c]})
        assert resp.status_code == 400, "direct threads need exactly one other participant"
    finally:
        os.unlink(db_path)
    print("✓ test_create_thread_route_validation: PASS")


def test_THE_ISOLATION_REQUIREMENT_a_non_participant_cannot_see_or_post_to_a_thread():
    """The explicit, headline requirement: no cross-account leakage, confirmed through the real routes, not just reasoned about."""
    db_path = _fresh_temp_db()
    try:
        a = _make_user("a@example.com")
        b = _make_user("b@example.com")
        c = _make_user("c@example.com")  # not in the conversation at all
        client_a = _client_for(a)
        client_c = _client_for(c)

        thread_id = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b]}).get_json()["id"]
        client_a.post(f"/threads/{thread_id}/messages", json={"body": "a private message between a and b"})

        # C cannot list it
        c_threads = client_c.get("/threads").get_json()
        assert all(t["id"] != thread_id for t in c_threads), "a non-participant's thread list must never include this thread"

        # C cannot read its messages -- 404, not 403 (existence itself is hidden)
        resp = client_c.get(f"/threads/{thread_id}/messages")
        assert resp.status_code == 404, f"non-participant read must 404, got {resp.status_code}"

        # C cannot post to it
        resp = client_c.post(f"/threads/{thread_id}/messages", json={"body": "I shouldn't be able to send this"})
        assert resp.status_code == 404, f"non-participant post must 404, got {resp.status_code}"

        # C cannot mark it read, or add themselves as a participant
        assert client_c.post(f"/threads/{thread_id}/read").status_code == 404
        assert client_c.post(f"/threads/{thread_id}/participants", json={"user_id": c}).status_code == 404

        # A and B (the real participants) both still see it fine
        client_b = _client_for(b)
        assert any(t["id"] == thread_id for t in client_a.get("/threads").get_json())
        assert any(t["id"] == thread_id for t in client_b.get("/threads").get_json())
        assert len(client_b.get(f"/threads/{thread_id}/messages").get_json()) == 1
    finally:
        os.unlink(db_path)
    print("✓ test_THE_ISOLATION_REQUIREMENT_a_non_participant_cannot_see_or_post_to_a_thread: PASS")


def test_group_thread_add_participant_route():
    db_path = _fresh_temp_db()
    try:
        a, b, c = _make_user("a@example.com"), _make_user("b@example.com"), _make_user("c@example.com")
        client_a = _client_for(a)
        thread_id = client_a.post("/threads", json={"thread_type": "group", "participant_user_ids": [b], "name": "Ops"}).get_json()["id"]

        resp = client_a.post(f"/threads/{thread_id}/participants", json={"user_id": c})
        assert resp.status_code == 200, resp.get_json()
        assert any(p["id"] == c for p in resp.get_json()["participants"])

        # now C is a real participant and can read it
        client_c = _client_for(c)
        assert client_c.get(f"/threads/{thread_id}/messages").status_code == 200

        # can't add a participant to a DIRECT thread
        direct_id = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b]}).get_json()["id"]
        resp = client_a.post(f"/threads/{direct_id}/participants", json={"user_id": c})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_group_thread_add_participant_route: PASS")


def test_mark_read_route_and_unread_count_route():
    db_path = _fresh_temp_db()
    try:
        a, b = _make_user("a@example.com"), _make_user("b@example.com")
        client_a, client_b = _client_for(a), _client_for(b)
        thread_id = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b]}).get_json()["id"]
        client_a.post(f"/threads/{thread_id}/messages", json={"body": "unread for b"})

        resp = client_b.get("/messages/unread-count")
        assert resp.status_code == 200
        assert resp.get_json()["total_unread"] == 1

        client_b.post(f"/threads/{thread_id}/read")
        resp = client_b.get("/messages/unread-count")
        assert resp.get_json()["total_unread"] == 0
    finally:
        os.unlink(db_path)
    print("✓ test_mark_read_route_and_unread_count_route: PASS")


def test_post_message_route_validation():
    db_path = _fresh_temp_db()
    try:
        a, b = _make_user("a@example.com"), _make_user("b@example.com")
        client_a = _client_for(a)
        thread_id = client_a.post("/threads", json={"thread_type": "direct", "participant_user_ids": [b]}).get_json()["id"]

        assert client_a.post(f"/threads/{thread_id}/messages", json={}).status_code == 400
        assert client_a.post(f"/threads/{thread_id}/messages", json={"body": "  "}).status_code == 400
        assert client_a.post(f"/threads/{thread_id}/messages", json={"body": "x" * 10001}).status_code == 400
        assert client_a.post("/threads/999999/messages", json={"body": "x"}).status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_post_message_route_validation: PASS")


if __name__ == "__main__":
    test_create_direct_thread_reuses_existing()
    test_create_group_thread_never_reused()
    test_is_thread_participant()
    test_messages_ordered_and_since_filter_works()
    test_unread_counts_exclude_own_messages_and_respect_last_read()
    test_concurrent_message_sends_all_persist()
    test_threads_route_requires_login()
    test_create_direct_thread_route_and_send_message()
    test_create_direct_thread_route_reuses_and_returns_200()
    test_create_thread_route_validation()
    test_THE_ISOLATION_REQUIREMENT_a_non_participant_cannot_see_or_post_to_a_thread()
    test_group_thread_add_participant_route()
    test_mark_read_route_and_unread_count_route()
    test_post_message_route_validation()
    print("\nAll messaging tests passed.")
