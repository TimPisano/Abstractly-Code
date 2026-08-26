"""
Tests for the Part 2/3 lease-library additions: auto-generated
display_name at upload, PATCH /leases/<id> (rename), and the tag
endpoints (add/remove/list/filter). Uses Flask's in-process
test_client() (same pattern as test_waitlist_email.py /
test_sheets_export.py) against an isolated temp DB, plus a couple of
checks against database.py's tag functions directly.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app, _default_lease_name
from app import database

FIXTURES_DIR = os.path.dirname(__file__)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _authed_client():
    """
    A test_client() pre-authenticated as a logged-in analyst, via
    Flask's session_transaction() -- the standard way to test a
    session-gated route without driving an actual login POST through
    bcrypt for every test, same convention as test_admin_auth.py's
    _create_admin()/session pattern. Most routes now require at least
    a logged-in session (see app/auth.py's require_role()) since the
    RBAC audit -- analyst covers every route these tests exercise.
    """
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["email"] = "test-analyst@example.com"
        sess["name"] = "Test Analyst"
        sess["role"] = "analyst"
    return client


def _upload(client, filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        content = f.read()
    resp = client.post(
        "/leases",
        data={"file": (__import__("io").BytesIO(content), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["leases"][0]


# ------------------------------------------------------------------
# _default_lease_name() — pure unit tests, no DB/HTTP involved
# ------------------------------------------------------------------

def test_default_name_uses_tenant_and_address_when_both_found():
    fields = {
        "tenant": {"value": "Acme Roasters, Inc.", "source": None, "confidence": "high"},
        "property_address": {"value": "123 Main St, Portland, ME", "source": None, "confidence": "high"},
    }
    name = _default_lease_name(fields, "some_file.pdf", 0, 1)
    assert name == "Acme Roasters, Inc. - 123 Main St, Portland, ME"
    print("✓ test_default_name_uses_tenant_and_address_when_both_found: PASS")


def test_default_name_falls_back_to_filename_when_tenant_missing():
    fields = {
        "tenant": {"value": None, "source": None, "confidence": None},
        "property_address": {"value": "123 Main St", "source": None, "confidence": "high"},
    }
    name = _default_lease_name(fields, "unreadable_scan.pdf", 0, 1)
    assert name == "unreadable_scan", name
    print("✓ test_default_name_falls_back_to_filename_when_tenant_missing: PASS")


def test_default_name_appends_lease_number_only_when_split():
    fields = {"tenant": {"value": None}, "property_address": {"value": None}}
    single = _default_lease_name(fields, "bundle.pdf", 0, 1)
    split_first = _default_lease_name(fields, "bundle.pdf", 0, 3)
    split_second = _default_lease_name(fields, "bundle.pdf", 1, 3)
    assert single == "bundle", "a lone upload must not get a redundant 'Lease 1' suffix"
    assert split_first == "bundle - Lease 1"
    assert split_second == "bundle - Lease 2"
    print("✓ test_default_name_appends_lease_number_only_when_split: PASS")


# ------------------------------------------------------------------
# Auto-naming at real upload time
# ------------------------------------------------------------------

def test_upload_auto_generates_display_name():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "retail_lease.pdf")
        assert lease["display_name"] == "Cascade Apparel Co. - 8890 Riverside Plaza, Unit 12, Portland, Oregon 97201", lease["display_name"]
    finally:
        os.unlink(db_path)
    print("✓ test_upload_auto_generates_display_name: PASS")


# ------------------------------------------------------------------
# PATCH /leases/<id> — rename
# ------------------------------------------------------------------

def test_rename_lease():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "office_lease.pdf")

        resp = client.patch(f"/leases/{lease['id']}", json={"display_name": "My Custom Name"})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["display_name"] == "My Custom Name"

        # Persisted, not just returned in the response.
        resp2 = client.get(f"/leases/{lease['id']}")
        assert resp2.get_json()["display_name"] == "My Custom Name"
    finally:
        os.unlink(db_path)
    print("✓ test_rename_lease: PASS")


def test_rename_rejects_blank_name():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "office_lease.pdf")
        resp = client.patch(f"/leases/{lease['id']}", json={"display_name": "   "})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_rename_rejects_blank_name: PASS")


def test_rename_nonexistent_lease_returns_404():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        resp = client.patch("/leases/999999", json={"display_name": "Anything"})
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_rename_nonexistent_lease_returns_404: PASS")


def test_rename_reflected_in_dashboard_list():
    """The whole point of the rename feature: it must show up in GET /leases too, not just the single-lease GET."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "retail_lease.pdf")
        client.patch(f"/leases/{lease['id']}", json={"display_name": "Renamed For List View"})

        listing = client.get("/leases").get_json()
        assert any(l["display_name"] == "Renamed For List View" for l in listing)
    finally:
        os.unlink(db_path)
    print("✓ test_rename_reflected_in_dashboard_list: PASS")


# ------------------------------------------------------------------
# Tag endpoints
# ------------------------------------------------------------------

def test_add_and_list_lease_tags():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "office_lease.pdf")

        resp = client.post(f"/leases/{lease['id']}/tags", json={"tag": "Downtown Portfolio"})
        assert resp.status_code == 200
        assert resp.get_json() == ["Downtown Portfolio"]

        resp = client.get(f"/leases/{lease['id']}/tags")
        assert resp.get_json() == ["Downtown Portfolio"]
    finally:
        os.unlink(db_path)
    print("✓ test_add_and_list_lease_tags: PASS")


def test_adding_same_tag_twice_is_not_an_error():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "office_lease.pdf")
        client.post(f"/leases/{lease['id']}/tags", json={"tag": "Downtown"})
        resp = client.post(f"/leases/{lease['id']}/tags", json={"tag": "Downtown"})
        assert resp.status_code == 200
        assert resp.get_json() == ["Downtown"], "must not duplicate, must not error"
    finally:
        os.unlink(db_path)
    print("✓ test_adding_same_tag_twice_is_not_an_error: PASS")


def test_remove_lease_tag():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "office_lease.pdf")
        client.post(f"/leases/{lease['id']}/tags", json={"tag": "Downtown"})
        client.post(f"/leases/{lease['id']}/tags", json={"tag": "2026 Acquisitions"})

        resp = client.delete(f"/leases/{lease['id']}/tags/Downtown")
        assert resp.status_code == 200
        assert resp.get_json() == ["2026 Acquisitions"]
    finally:
        os.unlink(db_path)
    print("✓ test_remove_lease_tag: PASS")


def test_reject_blank_and_oversized_tags():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "office_lease.pdf")

        resp = client.post(f"/leases/{lease['id']}/tags", json={"tag": "  "})
        assert resp.status_code == 400

        resp = client.post(f"/leases/{lease['id']}/tags", json={"tag": "x" * 61})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_reject_blank_and_oversized_tags: PASS")


def test_list_all_tags_and_filter_leases_by_tag():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        retail = _upload(client, "retail_lease.pdf")
        office = _upload(client, "office_lease.pdf")

        client.post(f"/leases/{retail['id']}/tags", json={"tag": "Downtown Portfolio"})
        client.post(f"/leases/{office['id']}/tags", json={"tag": "Downtown Portfolio"})
        client.post(f"/leases/{office['id']}/tags", json={"tag": "2026 Acquisitions"})

        all_tags = client.get("/tags").get_json()
        assert set(all_tags) == {"Downtown Portfolio", "2026 Acquisitions"}

        filtered = client.get("/leases?tag=Downtown Portfolio").get_json()
        assert len(filtered) == 2

        filtered2 = client.get("/leases?tag=2026 Acquisitions").get_json()
        assert len(filtered2) == 1
        assert filtered2[0]["id"] == office["id"]
    finally:
        os.unlink(db_path)
    print("✓ test_list_all_tags_and_filter_leases_by_tag: PASS")


def test_tags_deleted_with_lease():
    """A lease's tags must not survive (or dangle) after the lease itself is deleted — ON DELETE CASCADE on lease_tags."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease = _upload(client, "office_lease.pdf")
        client.post(f"/leases/{lease['id']}/tags", json={"tag": "Downtown"})

        client.delete(f"/leases/{lease['id']}")

        all_tags = client.get("/tags").get_json()
        assert all_tags == [], "tags must be cleaned up when the lease is deleted"
    finally:
        os.unlink(db_path)
    print("✓ test_tags_deleted_with_lease: PASS")


def test_tag_operations_on_nonexistent_lease_return_404():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        assert client.get("/leases/999999/tags").status_code == 404
        assert client.post("/leases/999999/tags", json={"tag": "x"}).status_code == 404
        assert client.delete("/leases/999999/tags/x").status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_tag_operations_on_nonexistent_lease_return_404: PASS")


if __name__ == "__main__":
    test_default_name_uses_tenant_and_address_when_both_found()
    test_default_name_falls_back_to_filename_when_tenant_missing()
    test_default_name_appends_lease_number_only_when_split()
    test_upload_auto_generates_display_name()
    test_rename_lease()
    test_rename_rejects_blank_name()
    test_rename_nonexistent_lease_returns_404()
    test_rename_reflected_in_dashboard_list()
    test_add_and_list_lease_tags()
    test_adding_same_tag_twice_is_not_an_error()
    test_remove_lease_tag()
    test_reject_blank_and_oversized_tags()
    test_list_all_tags_and_filter_leases_by_tag()
    test_tags_deleted_with_lease()
    test_tag_operations_on_nonexistent_lease_return_404()
    print("\nAll lease naming/tags tests passed.")
