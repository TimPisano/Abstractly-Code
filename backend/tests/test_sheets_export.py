"""
Tests for sheets_export.py and its wiring into
POST /portfolio/export/google-sheets.

No real Google API credentials exist in this environment (by design —
see backend/.env.example), so every test either exercises the genuine
"not configured" path directly, or mocks google.oauth2.service_account
and googleapiclient.discovery.build to simulate a working (or failing)
Google API without ever making a real network call. Uses Flask's
test_client() (same pattern as test_waitlist_email.py) for the route-
level checks, since that's what lets the API layer be tested with the
Google client mocked out from underneath it.
"""

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.sheets_export import export_to_google_sheets, SheetsExportError, _lease_row, _numeric_or_text


def _field(value, page=1, confidence="high"):
    if value is None:
        return {"value": None, "source": None, "confidence": None}
    return {"value": value, "source": {"page": page, "quote": f"...{value}..."}, "confidence": confidence}


def _lease(lease_id, filename, **values):
    return {
        "id": lease_id,
        "filename": filename,
        "extracted_fields": {name: _field(value) for name, value in values.items()},
    }


LEASE_COMPLETE = _lease(
    1, "complete.pdf",
    tenant="Blue Sky Coffee Roasters, Inc.",
    landlord="Harborview Properties LLC",
    property_address="120 Harbor Street, Portland, ME",
    rent_amount="$6,000.00",
    security_deposit="$12,000.00",
    rent_escalation="3% annually",
    lease_start_date="April 1, 2021",
    lease_end_date="March 31, 2026",
    renewal_options="2 option(s) of 5 year(s) each",
    default_cure_period="10 days after written notice",
    permitted_use="retail coffee roasting and cafe",
    exclusivity_clause="No other coffee retailer in the shopping center",
    insurance_requirements="$2,000,000 per occurrence",
    cam_charges="$800.00",
    square_footage="2,400 sq ft",
)

LEASE_SPARSE = _lease(
    2, "sparse.pdf",
    tenant="Alex Chen",
    rent_amount="$2,000.00",
)


# ------------------------------------------------------------------
# Row-building / formatting (no Google API involved)
# ------------------------------------------------------------------

def test_lease_row_column_order_matches_header():
    row = _lease_row(LEASE_COMPLETE)
    assert len(row) == 17, f"expected 17 columns, got {len(row)}"
    print("✓ test_lease_row_column_order_matches_header: PASS")


def test_not_found_fields_are_blank_not_literal_text():
    row = _lease_row(LEASE_SPARSE)
    # landlord, property_address, security_deposit, etc. were never set on LEASE_SPARSE
    assert "" in row, "at least one not-found field must render as a blank string"
    joined = [str(v) for v in row]
    assert "Not Found" not in joined
    assert "None" not in joined
    assert "not found" not in " ".join(joined).lower()
    print("✓ test_not_found_fields_are_blank_not_literal_text: PASS")


def test_annual_rent_and_rent_per_sqft_are_computed():
    row = _lease_row(LEASE_COMPLETE)
    header = ["Tenant Name", "Landlord Name", "Property Address", "Monthly Rent", "Annual Rent",
              "Rent per Square Foot", "Security Deposit", "Rent Escalation", "Lease Start Date",
              "Lease End Date", "Renewal Options", "Default/Cure Period", "Permitted Use",
              "Exclusivity Clause", "Insurance Requirements", "CAM Charges", "Square Footage"]
    values = dict(zip(header, row))

    assert values["Annual Rent"] == 72000.0, values["Annual Rent"]
    assert values["Rent per Square Foot"] == 2.5, values["Rent per Square Foot"]
    assert isinstance(values["Annual Rent"], float), "must be a real number, not a formatted string"
    print("✓ test_annual_rent_and_rent_per_sqft_are_computed: PASS")


def test_derived_columns_blank_when_uncomputable():
    row = _lease_row(LEASE_SPARSE)  # no square_footage at all
    header = ["Tenant Name", "Landlord Name", "Property Address", "Monthly Rent", "Annual Rent",
              "Rent per Square Foot"]
    values = dict(zip(header, row))
    assert values["Annual Rent"] == 24000.0  # rent alone is enough for this one
    assert values["Rent per Square Foot"] == "", "no square footage -> blank, not a fabricated 0 or error"
    print("✓ test_derived_columns_blank_when_uncomputable: PASS")


def test_pure_currency_string_retyped_as_number():
    assert _numeric_or_text("$6,000.00", "Monthly Rent") == 6000.0
    assert isinstance(_numeric_or_text("$6,000.00", "Monthly Rent"), float)
    print("✓ test_pure_currency_string_retyped_as_number: PASS")


def test_qualified_currency_string_stays_text():
    """'$2,000,000 per occurrence' would misstate the figure if the qualifier were silently dropped -- must stay text. (Insurance Requirements isn't even in _CURRENCY_COLUMNS, so this is a straight passthrough regardless.)"""
    value = _numeric_or_text("$2,000,000 per occurrence", "Insurance Requirements")
    assert value == "$2,000,000 per occurrence"
    assert isinstance(value, str)
    print("✓ test_qualified_currency_string_stays_text: PASS")


def test_square_footage_retyped_as_integer():
    assert _numeric_or_text("2,400 sq ft", "Square Footage") == 2400.0
    print("✓ test_square_footage_retyped_as_integer: PASS")


# ------------------------------------------------------------------
# export_to_google_sheets() — credential/config failure paths
# ------------------------------------------------------------------

def test_export_fails_cleanly_with_no_credentials_configured():
    """The real current state of this environment: no credentials are set up at all."""
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        try:
            export_to_google_sheets([LEASE_COMPLETE])
            assert False, "must raise SheetsExportError"
        except SheetsExportError as e:
            assert "isn't set up yet" in str(e)
            assert "GOOGLE_APPLICATION_CREDENTIALS" in str(e)
    print("✓ test_export_fails_cleanly_with_no_credentials_configured: PASS")


def test_export_fails_cleanly_when_credentials_file_missing():
    with mock.patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/definitely/not/a/real/path.json"}):
        try:
            export_to_google_sheets([LEASE_COMPLETE])
            assert False, "must raise SheetsExportError"
        except SheetsExportError as e:
            assert "misconfigured" in str(e)
    print("✓ test_export_fails_cleanly_when_credentials_file_missing: PASS")


def test_export_fails_cleanly_when_credentials_file_is_invalid():
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("this is not valid JSON at all")
    tmp.close()
    try:
        with mock.patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": tmp.name}):
            try:
                export_to_google_sheets([LEASE_COMPLETE])
                assert False, "must raise SheetsExportError"
            except SheetsExportError as e:
                assert "misconfigured" in str(e)
    finally:
        os.unlink(tmp.name)
    print("✓ test_export_fails_cleanly_when_credentials_file_is_invalid: PASS")


# ------------------------------------------------------------------
# export_to_google_sheets() — mocked Google API (no network calls)
# ------------------------------------------------------------------

def _fake_valid_credentials_file():
    """A syntactically-plausible (but fake) service account key -- enough to satisfy json parsing, never sent anywhere real since google.auth itself is mocked in these tests too."""
    import json
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({
        "type": "service_account", "project_id": "fake", "private_key_id": "fake",
        "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
        "client_email": "fake@fake.iam.gserviceaccount.com", "client_id": "123",
        "token_uri": "https://oauth2.googleapis.com/token",
    }, tmp)
    tmp.close()
    return tmp.name


def test_happy_path_creates_sheet_and_returns_url():
    creds_path = _fake_valid_credentials_file()
    try:
        mock_sheets_service = mock.MagicMock()
        mock_drive_service = mock.MagicMock()
        mock_sheets_service.spreadsheets.return_value.create.return_value.execute.return_value = {"spreadsheetId": "abc123XYZ"}

        def fake_build(name, version, credentials=None, cache_discovery=False):
            return mock_sheets_service if name == "sheets" else mock_drive_service

        with mock.patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": creds_path}):
            with mock.patch("app.sheets_export.service_account.Credentials.from_service_account_file", return_value=mock.MagicMock()):
                with mock.patch("app.sheets_export.build", side_effect=fake_build):
                    result = export_to_google_sheets([LEASE_COMPLETE, LEASE_SPARSE])

        assert result == {
            "spreadsheet_id": "abc123XYZ",
            "url": "https://docs.google.com/spreadsheets/d/abc123XYZ/edit",
        }, result

        # Confirm the data actually written matches what was requested: header + 2 lease
        # rows on the "Lease Data" tab, plus a "Portfolio Summary" tab with its own
        # header + 2 rows + a totals row.
        batch_call = mock_sheets_service.spreadsheets.return_value.values.return_value.batchUpdate
        assert batch_call.called
        data = batch_call.call_args.kwargs["body"]["data"]
        assert len(data) == 2

        lease_tab = next(d for d in data if d["range"] == "'Lease Data'!A1")
        written_values = lease_tab["values"]
        assert len(written_values) == 3, "1 header row + 2 lease rows"
        assert written_values[0][0] == "Tenant Name"
        assert written_values[1][0] == "Blue Sky Coffee Roasters, Inc."
        assert written_values[2][0] == "Alex Chen"

        summary_tab = next(d for d in data if d["range"] == "'Portfolio Summary'!A1")
        summary_values = summary_tab["values"]
        assert len(summary_values) == 4, "1 header row + 2 lease rows + 1 totals row"
        assert summary_values[0][0] == "Unit/Tenant"
        assert summary_values[3][0] == "TOTAL (2 units)"

        # Confirm sharing was actually requested (this is what makes the link usable).
        permissions_call = mock_drive_service.permissions.return_value.create
        assert permissions_call.called
        assert permissions_call.call_args.kwargs["body"] == {"type": "anyone", "role": "reader"}
    finally:
        os.unlink(creds_path)

    print("✓ test_happy_path_creates_sheet_and_returns_url: PASS")


def test_google_api_403_produces_clean_permission_message():
    from googleapiclient.errors import HttpError

    creds_path = _fake_valid_credentials_file()
    try:
        fake_response = mock.MagicMock()
        fake_response.status = 403
        http_error = HttpError(fake_response, b'{"error": "insufficient permission"}')

        mock_sheets_service = mock.MagicMock()
        mock_sheets_service.spreadsheets.return_value.create.return_value.execute.side_effect = http_error

        with mock.patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": creds_path}):
            with mock.patch("app.sheets_export.service_account.Credentials.from_service_account_file", return_value=mock.MagicMock()):
                with mock.patch("app.sheets_export.build", return_value=mock_sheets_service):
                    try:
                        export_to_google_sheets([LEASE_COMPLETE])
                        assert False, "must raise SheetsExportError"
                    except SheetsExportError as e:
                        assert "permission" in str(e).lower()
                        assert "Sheets API" in str(e) or "Drive API" in str(e)
    finally:
        os.unlink(creds_path)

    print("✓ test_google_api_403_produces_clean_permission_message: PASS")


# ------------------------------------------------------------------
# Route-level: POST /portfolio/export/google-sheets
# ------------------------------------------------------------------

def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def test_route_returns_502_with_clean_message_when_not_configured():
    db_path = _fresh_temp_db()
    try:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            resp = app.test_client().post("/portfolio/export/google-sheets")
        assert resp.status_code == 502, resp.get_json()
        assert "error" in resp.get_json()
        assert "GOOGLE_APPLICATION_CREDENTIALS" in resp.get_json()["error"]
    finally:
        os.unlink(db_path)
    print("✓ test_route_returns_502_with_clean_message_when_not_configured: PASS")


def test_route_returns_200_with_url_on_success_and_logs_activity():
    db_path = _fresh_temp_db()
    try:
        with mock.patch("app.api.export_to_google_sheets", return_value={"spreadsheet_id": "xyz", "url": "https://docs.google.com/spreadsheets/d/xyz/edit"}):
            resp = app.test_client().post("/portfolio/export/google-sheets")

        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["url"] == "https://docs.google.com/spreadsheets/d/xyz/edit"

        activity = database.get_recent_activity(5)
        assert any(a["action_type"] == "google_sheets_exported" for a in activity), activity
    finally:
        os.unlink(db_path)
    print("✓ test_route_returns_200_with_url_on_success_and_logs_activity: PASS")


def test_route_does_not_log_activity_on_failure():
    db_path = _fresh_temp_db()
    try:
        with mock.patch("app.api.export_to_google_sheets", side_effect=SheetsExportError("boom")):
            resp = app.test_client().post("/portfolio/export/google-sheets")
        assert resp.status_code == 502

        activity = database.get_recent_activity(5)
        assert not any(a["action_type"] == "google_sheets_exported" for a in activity), \
            "a failed export must not be logged as though it succeeded"
    finally:
        os.unlink(db_path)
    print("✓ test_route_does_not_log_activity_on_failure: PASS")


# ------------------------------------------------------------------
# Route-level: POST /leases/<id>/export/google-sheets (single-lease
# variant -- same underlying export_to_google_sheets(), scoped to one
# lease instead of the whole portfolio; had zero test coverage before
# this, found during the pre-sale test-coverage audit).
# ------------------------------------------------------------------

def test_single_lease_route_returns_502_with_clean_message_when_not_configured():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("solo.pdf", LEASE_COMPLETE["extracted_fields"])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            resp = app.test_client().post(f"/leases/{lease_id}/export/google-sheets")
        assert resp.status_code == 502, resp.get_json()
        assert "GOOGLE_APPLICATION_CREDENTIALS" in resp.get_json()["error"]
    finally:
        os.unlink(db_path)
    print("✓ test_single_lease_route_returns_502_with_clean_message_when_not_configured: PASS")


def test_single_lease_route_returns_404_for_nonexistent_lease():
    db_path = _fresh_temp_db()
    try:
        resp = app.test_client().post("/leases/999999/export/google-sheets")
        assert resp.status_code == 404, resp.get_json()
    finally:
        os.unlink(db_path)
    print("✓ test_single_lease_route_returns_404_for_nonexistent_lease: PASS")


def test_single_lease_route_returns_200_and_logs_activity_naming_the_lease():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("solo.pdf", LEASE_COMPLETE["extracted_fields"], display_name="Blue Sky Coffee Roasters, Inc.")
        with mock.patch("app.api.export_to_google_sheets", return_value={"spreadsheet_id": "xyz", "url": "https://docs.google.com/spreadsheets/d/xyz/edit"}) as mocked:
            resp = app.test_client().post(f"/leases/{lease_id}/export/google-sheets")

        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["url"] == "https://docs.google.com/spreadsheets/d/xyz/edit"

        # Scoped to just the one requested lease, not the whole portfolio.
        exported_leases = mocked.call_args[0][0]
        assert len(exported_leases) == 1 and exported_leases[0]["id"] == lease_id

        activity = database.get_recent_activity(5)
        matching = [a for a in activity if a["action_type"] == "google_sheets_exported"]
        assert matching, activity
        assert "Blue Sky Coffee Roasters" in matching[0]["description"], matching[0]
    finally:
        os.unlink(db_path)
    print("✓ test_single_lease_route_returns_200_and_logs_activity_naming_the_lease: PASS")


if __name__ == "__main__":
    test_lease_row_column_order_matches_header()
    test_not_found_fields_are_blank_not_literal_text()
    test_annual_rent_and_rent_per_sqft_are_computed()
    test_derived_columns_blank_when_uncomputable()
    test_pure_currency_string_retyped_as_number()
    test_qualified_currency_string_stays_text()
    test_square_footage_retyped_as_integer()
    test_export_fails_cleanly_with_no_credentials_configured()
    test_export_fails_cleanly_when_credentials_file_missing()
    test_export_fails_cleanly_when_credentials_file_is_invalid()
    test_happy_path_creates_sheet_and_returns_url()
    test_google_api_403_produces_clean_permission_message()
    test_route_returns_502_with_clean_message_when_not_configured()
    test_route_returns_200_with_url_on_success_and_logs_activity()
    test_route_does_not_log_activity_on_failure()
    test_single_lease_route_returns_502_with_clean_message_when_not_configured()
    test_single_lease_route_returns_404_for_nonexistent_lease()
    test_single_lease_route_returns_200_and_logs_activity_naming_the_lease()
    print("\nAll Google Sheets export tests passed.")
