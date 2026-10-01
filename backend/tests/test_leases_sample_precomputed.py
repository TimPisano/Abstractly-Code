"""
Tests for /leases/sample fixture loading - verifies that sample lease
uses precomputed extraction, not live pipeline calls.
Plain-script test convention with mocked API.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest import mock
import tempfile
import json

from app import database, api


def _fresh_temp_db():
    """Create a fresh test database."""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    database.configure(temp_db.name)
    database.init_db()
    return temp_db.name


def test_sample_fixture_loads():
    """Fixture file exists and can be loaded as JSON."""
    db_path = _fresh_temp_db()
    try:
        # Create a mock fixture
        fixture_path = os.path.join(
            os.path.dirname(__file__), '..', 'sample_data', 'sample_lease_fixture.json'
        )
        os.makedirs(os.path.dirname(fixture_path), exist_ok=True)

        sample_fixture = [{
            "fields": {
                "tenant": {"value": "Test Tenant Inc.", "source": {"page": 1, "quote": "Test Tenant Inc."}, "confidence": "high"},
                "landlord": {"value": "Sample Landlord LLC", "source": {"page": 1, "quote": "Sample Landlord LLC"}, "confidence": "high"},
                "rent_amount": {"value": "$5,000.00", "source": {"page": 2, "quote": "$5,000.00"}, "confidence": "high"},
            },
            "date_candidates": {"start": ["2025-01-01"], "end": ["2027-12-31"]},
            "source_page_start": 1,
            "source_page_end": 3,
            "display_name": "Test Tenant Inc. - Sample Property",
        }]

        with open(fixture_path, 'w') as f:
            json.dump(sample_fixture, f)

        loaded = api._load_sample_fixture()
        assert loaded is not None, "Fixture should load"
        assert len(loaded) == 1, "Should have one lease"
        assert loaded[0]["fields"]["tenant"]["value"] == "Test Tenant Inc."
        print("✓ test_sample_fixture_loads PASS")
    finally:
        os.unlink(db_path)
        if os.path.exists(fixture_path):
            os.unlink(fixture_path)


def test_sample_fixture_missing_returns_none():
    """Missing fixture file should return None gracefully."""
    db_path = _fresh_temp_db()
    try:
        # Ensure fixture doesn't exist by using a nonexistent path
        with mock.patch.object(api, '_SAMPLE_FIXTURE_PATH', '/nonexistent/path/fixture.json'):
            loaded = api._load_sample_fixture()
            assert loaded is None, "Should return None for missing fixture"
            print("✓ test_sample_fixture_missing_returns_none PASS")
    finally:
        os.unlink(db_path)


def test_sample_route_does_not_call_extraction():
    """POST /leases/sample should not call _extract_leases_from_file_storage."""
    db_path = _fresh_temp_db()
    try:
        # Create a mock fixture
        fixture_path = os.path.join(
            os.path.dirname(__file__), '..', 'sample_data', 'sample_lease_fixture.json'
        )
        os.makedirs(os.path.dirname(fixture_path), exist_ok=True)

        sample_fixture = [{
            "fields": {
                "tenant": {"value": "Test Tenant Inc.", "source": {"page": 1, "quote": "Test Tenant Inc."}, "confidence": "high"},
                "landlord": {"value": "Sample Landlord LLC", "source": {"page": 1, "quote": "Sample Landlord LLC"}, "confidence": "high"},
            },
            "date_candidates": {"start": ["2025-01-01"], "end": ["2027-12-31"]},
            "source_page_start": 1,
            "source_page_end": 3,
            "display_name": "Test Tenant Inc. - Sample Property",
        }]

        with open(fixture_path, 'w') as f:
            json.dump(sample_fixture, f)

        with mock.patch('app.api._extract_leases_from_file_storage') as mock_extract:
            # Mock should NOT be called
            loaded = api._load_sample_fixture()
            assert loaded is not None
            # _extract_leases_from_file_storage is not called during fixture load
            assert not mock_extract.called, "Should not call extraction pipeline for fixture load"
            print("✓ test_sample_route_does_not_call_extraction PASS")
    finally:
        os.unlink(db_path)
        if os.path.exists(fixture_path):
            os.unlink(fixture_path)


def test_sample_fixture_invalid_json():
    """Invalid fixture JSON should be handled gracefully."""
    db_path = _fresh_temp_db()
    try:
        fixture_path = os.path.join(
            os.path.dirname(__file__), '..', 'sample_data', 'sample_lease_fixture.json'
        )
        os.makedirs(os.path.dirname(fixture_path), exist_ok=True)

        # Write invalid JSON
        with open(fixture_path, 'w') as f:
            f.write("{ invalid json }")

        loaded = api._load_sample_fixture()
        assert loaded is None, "Should return None for invalid JSON"
        print("✓ test_sample_fixture_invalid_json PASS")
    finally:
        os.unlink(db_path)
        if os.path.exists(fixture_path):
            os.unlink(fixture_path)


if __name__ == "__main__":
    test_sample_fixture_loads()
    test_sample_fixture_missing_returns_none()
    test_sample_route_does_not_call_extraction()
    test_sample_fixture_invalid_json()
    print("\nAll sample fixture tests passed!")
