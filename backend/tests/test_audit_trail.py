"""
Tests for the full audit-trail feature: (1) the invariant that every
extracted field carries a real source citation whenever it has a value
-- checked against every real fixture this project has, both PDF
leases and PMS rent-roll imports, not just hand-built unit fixtures --
and (2) GET /leases/<id>/fields/<field_name>/source, which returns the
full source chain (including amendment history) for one data point.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_rollover_api.py / test_lease_naming_and_tags.py.
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES
from app.pdf_extractor import PDFExtractor
from app.field_extractor import FieldExtractor
from app.rent_roll_import import parse_csv_rent_roll, parse_xlsx_rent_roll

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


def _read(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


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
# Invariant: value present => source present, across every real
# extraction pathway this project has -- not just a hand-built fixture.
# ------------------------------------------------------------------

_PDF_FIXTURES = [
    "sample_lease.pdf",
    "sample_lease_commercial.pdf",
    "retail_lease.pdf",
    "office_lease.pdf",
    "casual_sublease.pdf",
    "missing_clauses_office.pdf",
    "reversed_dates.pdf",
    "inconsistent_escalation.pdf",
    "tenant_friendly_terms.pdf",
]


def _assert_field_invariant(extracted_fields, context):
    """Returns how many fields in this record had a real value, so callers
    can guard against a vacuous pass (e.g. extraction silently returning
    nothing, which would make every field's "if it has a value" check a
    no-op and hide a real regression instead of catching one)."""
    found_count = 0
    for field_name, field_data in extracted_fields.items():
        if field_data.get("value") is not None:
            found_count += 1
            source = field_data.get("source")
            assert source is not None, f"{context}: field '{field_name}' has a value but no source"
            assert source.get("quote"), f"{context}: field '{field_name}' source has no quote"
            has_page = source.get("page") is not None
            has_row = source.get("row") is not None
            assert has_page or has_row, f"{context}: field '{field_name}' source has neither page nor row"
    return found_count


def test_every_real_pdf_fixture_satisfies_the_source_invariant():
    checked = 0
    total_found = 0
    for filename in _PDF_FIXTURES:
        path = os.path.join(FIXTURES_DIR, filename)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            pages = PDFExtractor().extract_text(f, pdf_path=path)
        result = FieldExtractor().extract_fields(pages)
        found = _assert_field_invariant(result, filename)
        assert found >= 3, f"{filename}: only {found} fields found -- extraction may be silently broken, not a real check"
        total_found += found
        checked += 1
    assert checked >= 5, f"expected to check at least 5 real fixtures, only found {checked}"
    print(f"✓ test_every_real_pdf_fixture_satisfies_the_source_invariant: PASS ({checked} fixtures, {total_found} sourced fields checked)")


def test_every_pms_rent_roll_fixture_satisfies_the_source_invariant():
    csv_fixtures = [
        "synthetic_yardi_rent_roll.csv",
        "synthetic_appfolio_rent_roll.csv",
        "synthetic_realpage_rent_roll.csv",
        "synthetic_mri_rent_roll.csv",
        "synthetic_buildium_rent_roll.csv",
    ]
    checked = 0
    total_found = 0
    for filename in csv_fixtures:
        path = os.path.join(FIXTURES_DIR, filename)
        if not os.path.exists(path):
            continue
        parsed = parse_csv_rent_roll(_read(filename), filename, None)
        assert parsed["leases"], f"{filename}: fixture imported zero leases -- not a real check"
        for lease_data in parsed["leases"]:
            total_found += _assert_field_invariant(lease_data["extracted_fields"], filename)
        checked += 1

    xlsx_path = os.path.join(FIXTURES_DIR, "synthetic_yardi_rent_roll.xlsx")
    if os.path.exists(xlsx_path):
        parsed = parse_xlsx_rent_roll(_read("synthetic_yardi_rent_roll.xlsx"), "synthetic_yardi_rent_roll.xlsx", None)
        assert parsed["leases"], "synthetic_yardi_rent_roll.xlsx: fixture imported zero leases -- not a real check"
        for lease_data in parsed["leases"]:
            total_found += _assert_field_invariant(lease_data["extracted_fields"], "synthetic_yardi_rent_roll.xlsx")
        checked += 1

    assert checked >= 5, f"expected to check at least 5 PMS fixtures, only found {checked}"
    assert total_found >= 20, f"only {total_found} sourced fields found across all PMS fixtures -- not a real check"
    print(f"✓ test_every_pms_rent_roll_fixture_satisfies_the_source_invariant: PASS ({checked} fixtures, {total_found} sourced fields checked)")


# ------------------------------------------------------------------
# database.get_field_source_chain
# ------------------------------------------------------------------

def test_source_chain_for_base_lease_only():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("base.pdf", _fields(rent_amount="$5,000.00"))
        chain = database.get_field_source_chain(lease_id, "rent_amount")

        assert chain["effective_value"] == "$5,000.00"
        assert chain["effective_source"]["quote"] == "...$5,000.00..."
        assert chain["effective_document_id"] == lease_id
        assert len(chain["history"]) == 1
        assert chain["history"][0]["is_effective"] is True
    finally:
        os.unlink(db_path)
    print("✓ test_source_chain_for_base_lease_only: PASS")


def test_source_chain_reflects_amendment_override_but_keeps_full_history():
    db_path = _fresh_temp_db()
    try:
        base_id = database.insert_lease("base.pdf", _fields(rent_amount="$5,000.00"))
        amendment_id = database.insert_lease(
            "amendment.pdf",
            _fields(rent_amount="$5,500.00"),
            document_type="amendment",
            base_lease_id=base_id,
        )

        chain = database.get_field_source_chain(base_id, "rent_amount")

        assert chain["effective_value"] == "$5,500.00", "amendment must win"
        assert chain["effective_document_id"] == amendment_id
        assert len(chain["history"]) == 2, "both the base lease's original value and the amendment's must be kept"
        assert chain["history"][0]["value"] == "$5,000.00"
        assert chain["history"][0]["is_effective"] is False
        assert chain["history"][1]["value"] == "$5,500.00"
        assert chain["history"][1]["is_effective"] is True
        assert chain["history"][1]["document_id"] == amendment_id
    finally:
        os.unlink(db_path)
    print("✓ test_source_chain_reflects_amendment_override_but_keeps_full_history: PASS")


def test_source_chain_amendment_that_does_not_touch_field_does_not_override_it():
    db_path = _fresh_temp_db()
    try:
        base_id = database.insert_lease("base.pdf", _fields(rent_amount="$5,000.00"))
        database.insert_lease(
            "amendment.pdf",
            _fields(lease_end_date="December 31, 2030"),  # doesn't touch rent_amount
            document_type="amendment",
            base_lease_id=base_id,
        )

        chain = database.get_field_source_chain(base_id, "rent_amount")
        assert chain["effective_value"] == "$5,000.00"
        assert chain["effective_document_id"] == base_id
        assert chain["history"][1]["value"] is None
        assert chain["history"][1]["is_effective"] is False
    finally:
        os.unlink(db_path)
    print("✓ test_source_chain_amendment_that_does_not_touch_field_does_not_override_it: PASS")


def test_source_chain_field_never_found_returns_none_effective_value():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("base.pdf", _fields())  # nothing set
        chain = database.get_field_source_chain(lease_id, "cam_charges")
        assert chain["effective_value"] is None
        assert chain["effective_source"] is None
        assert chain["effective_document_id"] is None
        assert chain["history"][0]["is_effective"] is False
    finally:
        os.unlink(db_path)
    print("✓ test_source_chain_field_never_found_returns_none_effective_value: PASS")


def test_source_chain_nonexistent_lease_returns_none():
    db_path = _fresh_temp_db()
    try:
        assert database.get_field_source_chain(999999, "rent_amount") is None
    finally:
        os.unlink(db_path)
    print("✓ test_source_chain_nonexistent_lease_returns_none: PASS")


# ------------------------------------------------------------------
# GET /leases/<id>/fields/<field_name>/source
# ------------------------------------------------------------------

def test_field_source_route_happy_path():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        with open(os.path.join(FIXTURES_DIR, "sample_lease_commercial.pdf"), "rb") as f:
            content = f.read()
        resp = client.post(
            "/leases",
            data={"file": (io.BytesIO(content), "sample_lease_commercial.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, resp.get_json()
        lease_id = resp.get_json()["leases"][0]["id"]

        resp = client.get(f"/leases/{lease_id}/fields/tenant/source")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["field_name"] == "tenant"
        assert data["effective_value"] == "Blue Sky Coffee Roasters, Inc."
        assert data["effective_source"]["page"] is not None
        assert data["effective_source"]["quote"]
    finally:
        os.unlink(db_path)
    print("✓ test_field_source_route_happy_path: PASS")


def test_field_source_route_unknown_field_returns_400():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease_id = database.insert_lease("base.pdf", _fields(rent_amount="$5,000.00"))
        resp = client.get(f"/leases/{lease_id}/fields/not_a_real_field/source")
        assert resp.status_code == 400
        assert "Unknown field" in resp.get_json()["error"]
    finally:
        os.unlink(db_path)
    print("✓ test_field_source_route_unknown_field_returns_400: PASS")


def test_field_source_route_nonexistent_lease_returns_404():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        resp = client.get("/leases/999999/fields/rent_amount/source")
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_field_source_route_nonexistent_lease_returns_404: PASS")


def test_field_source_route_rent_roll_imported_lease_uses_row_citation():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        content = _read("synthetic_yardi_rent_roll.csv")
        resp = client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(content), "synthetic_yardi_rent_roll.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, resp.get_json()
        leases = resp.get_json()["leases"]
        assert leases, "fixture must import at least one lease"
        lease_id = leases[0]["id"]

        resp = client.get(f"/leases/{lease_id}/fields/tenant/source")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["effective_source"]["row"] is not None
        assert data["effective_source"]["file"] == "synthetic_yardi_rent_roll.csv"
    finally:
        os.unlink(db_path)
    print("✓ test_field_source_route_rent_roll_imported_lease_uses_row_citation: PASS")


if __name__ == "__main__":
    test_every_real_pdf_fixture_satisfies_the_source_invariant()
    test_every_pms_rent_roll_fixture_satisfies_the_source_invariant()
    test_source_chain_for_base_lease_only()
    test_source_chain_reflects_amendment_override_but_keeps_full_history()
    test_source_chain_amendment_that_does_not_touch_field_does_not_override_it()
    test_source_chain_field_never_found_returns_none_effective_value()
    test_source_chain_nonexistent_lease_returns_none()
    test_field_source_route_happy_path()
    test_field_source_route_unknown_field_returns_400()
    test_field_source_route_nonexistent_lease_returns_404()
    test_field_source_route_rent_roll_imported_lease_uses_row_citation()
    print("\nAll audit trail tests passed.")
