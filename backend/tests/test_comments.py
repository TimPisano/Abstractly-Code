"""
Tests for the collaboration layer: database.py's comments CRUD and the
GET/POST /leases/<id>/comments and /discrepancies/<id>/comments routes.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_lease_naming_and_tags.py.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES

FIXTURES_DIR = os.path.dirname(__file__)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _fields(**overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            value = overrides[name]
            result[name] = {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


# ------------------------------------------------------------------
# database.py CRUD
# ------------------------------------------------------------------

def test_add_and_get_lease_comments_chronological():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("base.pdf", _fields())
        database.add_comment("Jane Analyst", "First pass looks fine.", lease_id=lease_id)
        database.add_comment("Bob Reviewer", "Agreed, but check the CAM number.", lease_id=lease_id, author_email="bob@firm.com")

        comments = database.get_lease_comments(lease_id)
        assert len(comments) == 2
        assert comments[0]["author_name"] == "Jane Analyst"
        assert comments[0]["body"] == "First pass looks fine."
        assert comments[1]["author_name"] == "Bob Reviewer"
        assert comments[1]["author_email"] == "bob@firm.com"
        assert comments[0]["created_at"] <= comments[1]["created_at"]
    finally:
        os.unlink(db_path)
    print("✓ test_add_and_get_lease_comments_chronological: PASS")


def test_add_and_get_discrepancy_comments():
    db_path = _fresh_temp_db()
    try:
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k1", category="missing_clause", message="m", details={}, lease_id=1,
        )
        database.add_comment("Jane Analyst", "Confirmed with the broker this is intentional.", discrepancy_id=disc_id)

        comments = database.get_discrepancy_comments(disc_id)
        assert len(comments) == 1
        assert comments[0]["discrepancy_id"] == disc_id
        assert comments[0]["lease_id"] is None
    finally:
        os.unlink(db_path)
    print("✓ test_add_and_get_discrepancy_comments: PASS")


def test_lease_comments_deleted_with_lease():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("base.pdf", _fields())
        database.add_comment("Jane Analyst", "note", lease_id=lease_id)
        assert len(database.get_lease_comments(lease_id)) == 1

        database.delete_lease(lease_id)
        assert database.get_lease_comments(lease_id) == []
    finally:
        os.unlink(db_path)
    print("✓ test_lease_comments_deleted_with_lease: PASS")


# ------------------------------------------------------------------
# API routes
# ------------------------------------------------------------------

def test_lease_comment_routes_happy_path():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())

        resp = client.get(f"/leases/{lease_id}/comments")
        assert resp.status_code == 200
        assert resp.get_json() == []

        resp = client.post(f"/leases/{lease_id}/comments", json={
            "author_name": "Jane Analyst", "author_email": "jane@firm.com", "body": "Looks good to move forward.",
        })
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["author_name"] == "Jane Analyst"
        assert data[0]["body"] == "Looks good to move forward."

        resp = client.get(f"/leases/{lease_id}/comments")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1
    finally:
        os.unlink(db_path)
    print("✓ test_lease_comment_routes_happy_path: PASS")


def test_lease_comment_routes_validate_required_fields():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())

        resp = client.post(f"/leases/{lease_id}/comments", json={"body": "no author"})
        assert resp.status_code == 400
        assert "author_name" in resp.get_json()["error"]

        resp = client.post(f"/leases/{lease_id}/comments", json={"author_name": "Jane"})
        assert resp.status_code == 400
        assert "body" in resp.get_json()["error"]

        resp = client.post(f"/leases/{lease_id}/comments", json={"author_name": "  ", "body": "  "})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_lease_comment_routes_validate_required_fields: PASS")


def test_lease_comment_routes_404_for_nonexistent_lease():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        assert client.get("/leases/999999/comments").status_code == 404
        assert client.post("/leases/999999/comments", json={"author_name": "x", "body": "y"}).status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_lease_comment_routes_404_for_nonexistent_lease: PASS")


def test_discrepancy_comment_routes_happy_path_and_404():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())  # missing everything -> real flags
        flags = client.get(f"/leases/{lease_id}/risks").get_json()
        disc_id = flags[0]["discrepancy_id"]

        resp = client.get(f"/discrepancies/{disc_id}/comments")
        assert resp.status_code == 200
        assert resp.get_json() == []

        resp = client.post(f"/discrepancies/{disc_id}/comments", json={
            "author_name": "Bob Reviewer", "body": "Confirmed acceptable per the broker.",
        })
        assert resp.status_code == 201
        assert len(resp.get_json()) == 1

        assert client.get("/discrepancies/999999/comments").status_code == 404
        assert client.post("/discrepancies/999999/comments", json={"author_name": "x", "body": "y"}).status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_discrepancy_comment_routes_happy_path_and_404: PASS")


def test_comments_are_visible_regardless_of_which_client_posted_them():
    """The whole point of "visible to the team": no per-client/session filtering exists -- any reader sees every comment."""
    db_path = _fresh_temp_db()
    try:
        client_a = app.test_client()
        client_b = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())

        client_a.post(f"/leases/{lease_id}/comments", json={"author_name": "Jane", "body": "from Jane's session"})
        resp = client_b.get(f"/leases/{lease_id}/comments")
        assert len(resp.get_json()) == 1
        assert resp.get_json()[0]["author_name"] == "Jane"
    finally:
        os.unlink(db_path)
    print("✓ test_comments_are_visible_regardless_of_which_client_posted_them: PASS")


def test_recent_comments_route_merges_lease_and_discrepancy_comments():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields(), display_name="123 Main St Lease")
        disc_id = database.upsert_discrepancy(
            discrepancy_type="lease_risk_flag", natural_key="k", category="missing_clause",
            message="m", details={}, lease_id=lease_id,
        )

        resp = client.get("/comments/recent")
        assert resp.status_code == 200
        assert resp.get_json() == []

        client.post(f"/leases/{lease_id}/comments", json={"author_name": "Jane", "body": "Lease note"})
        client.post(f"/discrepancies/{disc_id}/comments", json={"author_name": "Bob", "body": "Discrepancy note"})

        resp = client.get("/comments/recent")
        data = resp.get_json()
        assert len(data) == 2, "must include comments from BOTH leases and discrepancies in one feed"

        by_body = {c["body"]: c for c in data}
        assert by_body["Lease note"]["lease_display_name"] == "123 Main St Lease", "lease comment must carry denormalized lease context"
        assert by_body["Lease note"]["discrepancy_category"] is None
        assert by_body["Discrepancy note"]["discrepancy_category"] == "missing_clause", "discrepancy comment must carry denormalized discrepancy context"

        # most recent first
        assert data[0]["body"] == "Discrepancy note"
    finally:
        os.unlink(db_path)
    print("✓ test_recent_comments_route_merges_lease_and_discrepancy_comments: PASS")


def test_recent_comments_route_respects_limit():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("base.pdf", _fields())
        for i in range(5):
            client.post(f"/leases/{lease_id}/comments", json={"author_name": "Jane", "body": f"note {i}"})

        resp = client.get("/comments/recent?limit=2")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2
        assert resp.get_json()[0]["body"] == "note 4", "must be most-recent-first"
    finally:
        os.unlink(db_path)
    print("✓ test_recent_comments_route_respects_limit: PASS")


if __name__ == "__main__":
    test_add_and_get_lease_comments_chronological()
    test_add_and_get_discrepancy_comments()
    test_lease_comments_deleted_with_lease()
    test_lease_comment_routes_happy_path()
    test_lease_comment_routes_validate_required_fields()
    test_lease_comment_routes_404_for_nonexistent_lease()
    test_discrepancy_comment_routes_happy_path_and_404()
    test_comments_are_visible_regardless_of_which_client_posted_them()
    test_recent_comments_route_merges_lease_and_discrepancy_comments()
    test_recent_comments_route_respects_limit()
    print("\nAll comment tests passed.")
