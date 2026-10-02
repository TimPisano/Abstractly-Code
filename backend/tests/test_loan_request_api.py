"""
Route tests for the loan underwriting module.

Three things get the most attention here, because they're the ones a
regression would make genuinely dangerous rather than merely broken:

  1. THE FEATURE FLAG. Every route must 404 when
     LOAN_UNDERWRITING_ENABLED is unset. Current beta testers must see no
     trace of this feature, and 404 (not 403) means the paths are
     indistinguishable from URLs that were never built.
  2. ROLES. Every route carries an explicit @require_role. Reads need
     viewer, writes and the memo export need analyst.
  3. VALIDATION THAT REFUSES RATHER THAN GUESSES. A loan request with a
     garbage number, or an underwriting run with no T-12, must fail with
     a message -- never silently substitute a zero and produce a
     confident, wrong ratio.

NOTE ON TENANCY: there is deliberately no cross-team isolation test here,
because this branch has no team model to isolate by -- a separate branch
owns that work (see app/loan_request.py's docstring and SUMMARY.md). When
team_id lands, the tests to add are: a request created under team A is
404 for a caller in team B, on every one of these routes.
"""

import csv
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.auth import hash_password

_FLAG = "LOAN_UNDERWRITING_ENABLED"

_ADDRESS = "4500 Maple Ridge Trail, Dallas, TX 75248"

_VALID_REQUEST = {
    "deal_name": "Maple Ridge Apartments",
    "property_address": _ADDRESS,
    "loan_amount": 13_875_000,
    "annual_rate_pct": 6.25,
    "amortization_years": 30,
    "term_years": 10,
    "interest_only_months": 24,
    "purchase_price": 18_500_000,
    "appraised_value": 18_750_000,
    "unit_count": 120,
}

# A minimal synthetic T-12 with every line the NOI build-up needs.
# Fictional figures -- no real property or customer data.
_T12_ROWS = [
    ["Synthetic Test Property"],
    ["Trailing 12-Month Operating Statement -- SYNTHETIC TEST DATA"],
    ["Line Item", "Total"],
    ["INCOME", ""],
    ["Gross Potential Rent", "2000000"],
    ["Vacancy Loss", "-100000"],
    ["Loss to Lease", "-20000"],
    ["Concessions", "-10000"],
    ["Bad Debt / Collection Loss", "-30000"],
    ["Total Rent Collected", "1840000"],
    ["Total Other Income", "80000"],
    ["OPERATING EXPENSES", ""],
    ["Property Taxes", "250000"],
    ["Insurance", "60000"],
    ["Management Fee (3% of Total Income)", "57600"],
    ["TOTAL OPERATING EXPENSES", "700000"],
    ["NET OPERATING INCOME (NOI)", "1220000"],
]


def _t12_csv_bytes():
    buf = io.StringIO()
    csv.writer(buf).writerows(_T12_ROWS)
    return buf.getvalue().encode("utf-8")


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _user(email, role):
    result = database.create_user(email, "Test User", hash_password("pw-not-used"), role=role)
    return result["id"]


def _client_as(user_id, email, role):
    """Same session_transaction approach tests/test_owner_console.py uses -- sets the signed session directly rather than round-tripping a login."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = "Test User"
        sess["role"] = role
        sess["is_owner"] = False
    return client


def _enable_flag():
    os.environ[_FLAG] = "true"


def _disable_flag():
    os.environ.pop(_FLAG, None)


def _create_request(client, overrides=None):
    body = dict(_VALID_REQUEST)
    if overrides:
        body.update(overrides)
    return client.post("/loan-underwriting/requests", json=body)


_ALL_ROUTES = [
    ("GET", "/loan-underwriting/requests"),
    ("POST", "/loan-underwriting/requests"),
    ("GET", "/loan-underwriting/requests/1"),
    ("PUT", "/loan-underwriting/requests/1"),
    ("PUT", "/loan-underwriting/requests/1/assumptions"),
    ("POST", "/loan-underwriting/requests/1/t12"),
    ("GET", "/loan-underwriting/requests/1/underwriting"),
    ("POST", "/loan-underwriting/requests/1/credit-memo.docx"),
]


# ----------------------------------------------------------------------
# Feature flag
# ----------------------------------------------------------------------

def test_every_route_404s_when_the_flag_is_off():
    """The headline guarantee of this branch: with the flag off, the feature does not exist."""
    _fresh_temp_db()
    _disable_flag()
    user_id = _user("analyst@example.com", "admin")
    client = _client_as(user_id, "analyst@example.com", "admin")

    for method, path in _ALL_ROUTES:
        response = client.open(path, method=method, json={})
        assert response.status_code == 404, f"{method} {path} returned {response.status_code}, expected 404"
    print("✓ test_every_route_404s_when_the_flag_is_off: PASS")


def test_flag_off_404s_even_for_an_anonymous_caller():
    """
    404 rather than 401 for an anonymous caller too -- the flag check runs
    OUTSIDE the role check, so an unauthenticated prober learns nothing
    about the feature's existence or about auth.
    """
    _fresh_temp_db()
    _disable_flag()
    client = app.test_client()
    for method, path in _ALL_ROUTES:
        response = client.open(path, method=method, json={})
        assert response.status_code == 404, f"{method} {path} returned {response.status_code}"
    print("✓ test_flag_off_404s_even_for_an_anonymous_caller: PASS")


def test_routes_exist_when_the_flag_is_on():
    _fresh_temp_db()
    _enable_flag()
    try:
        user_id = _user("analyst@example.com", "analyst")
        client = _client_as(user_id, "analyst@example.com", "analyst")
        response = client.get("/loan-underwriting/requests")
        assert response.status_code == 200, response.data
        assert response.get_json()["requests"] == []
    finally:
        _disable_flag()
    print("✓ test_routes_exist_when_the_flag_is_on: PASS")


# ----------------------------------------------------------------------
# Roles
# ----------------------------------------------------------------------

def test_anonymous_caller_is_rejected_on_every_route_with_the_flag_on():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = app.test_client()
        for method, path in _ALL_ROUTES:
            response = client.open(path, method=method, json={})
            assert response.status_code == 401, f"{method} {path} returned {response.status_code}, expected 401"
    finally:
        _disable_flag()
    print("✓ test_anonymous_caller_is_rejected_on_every_route_with_the_flag_on: PASS")


def test_viewer_can_read_but_cannot_write_or_export():
    """
    A viewer sees the analysis; a viewer does not create requests, edit
    assumptions, upload a T-12, or generate a credit memo. Exporting a
    memo is explicitly an analyst action -- it produces a document that
    leaves the building.
    """
    _fresh_temp_db()
    _enable_flag()
    try:
        analyst_id = _user("analyst@example.com", "analyst")
        analyst = _client_as(analyst_id, "analyst@example.com", "analyst")
        created = _create_request(analyst)
        assert created.status_code == 201, created.data
        request_id = created.get_json()["id"]

        viewer_id = _user("viewer@example.com", "viewer")
        viewer = _client_as(viewer_id, "viewer@example.com", "viewer")

        # Reads: allowed.
        assert viewer.get("/loan-underwriting/requests").status_code == 200
        assert viewer.get(f"/loan-underwriting/requests/{request_id}").status_code == 200

        # Writes and exports: forbidden.
        assert _create_request(viewer).status_code == 403
        assert viewer.put(f"/loan-underwriting/requests/{request_id}", json={"loan_amount": 1}).status_code == 403
        assert viewer.put(
            f"/loan-underwriting/requests/{request_id}/assumptions", json={"assumptions": {"vacancy_pct": 7}}
        ).status_code == 403
        assert viewer.post(
            f"/loan-underwriting/requests/{request_id}/t12",
            data={"file": (io.BytesIO(_t12_csv_bytes()), "t12.csv")},
            content_type="multipart/form-data",
        ).status_code == 403
        assert viewer.post(
            f"/loan-underwriting/requests/{request_id}/credit-memo.docx"
        ).status_code == 403
    finally:
        _disable_flag()
    print("✓ test_viewer_can_read_but_cannot_write_or_export: PASS")


# ----------------------------------------------------------------------
# Create / validate
# ----------------------------------------------------------------------

def test_create_stores_every_loan_term_and_the_default_assumptions():
    _fresh_temp_db()
    _enable_flag()
    try:
        user_id = _user("a@example.com", "analyst")
        client = _client_as(user_id, "a@example.com", "analyst")
        saved = _create_request(client).get_json()

        assert saved["loan_amount"] == 13_875_000.0
        assert saved["annual_rate_pct"] == 6.25
        assert saved["amortization_years"] == 30
        assert saved["term_years"] == 10
        assert saved["interest_only_months"] == 24
        assert saved["purchase_price"] == 18_500_000.0
        assert saved["appraised_value"] == 18_750_000.0
        assert saved["unit_count"] == 120
        # The deal key: normalized building address.
        assert saved["normalized_property_address"], saved
        # Defaults stored explicitly, not left NULL.
        assert saved["assumptions"]["vacancy_pct"] == 5.0, saved["assumptions"]
        assert saved["constraints"]["target_dscr"] == 1.25, saved["constraints"]
        assert saved["created_by_user_id"] == user_id
    finally:
        _disable_flag()
    print("✓ test_create_stores_every_loan_term_and_the_default_assumptions: PASS")


def test_create_accepts_assumption_and_constraint_overrides():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        body = dict(_VALID_REQUEST)
        body["assumptions"] = {"vacancy_pct": 7.5, "replacement_reserves_per_unit": 300}
        body["constraints"] = {"target_dscr": 1.35}
        saved = client.post("/loan-underwriting/requests", json=body).get_json()

        assert saved["assumptions"]["vacancy_pct"] == 7.5
        assert saved["assumptions"]["replacement_reserves_per_unit"] == 300.0
        # Unsupplied ones still get their default.
        assert saved["assumptions"]["management_fee_pct"] == 3.0
        assert saved["constraints"]["target_dscr"] == 1.35
        assert saved["constraints"]["max_ltv_pct"] == 75.0
    finally:
        _disable_flag()
    print("✓ test_create_accepts_assumption_and_constraint_overrides: PASS")


def test_invalid_numbers_are_refused_with_a_message_not_coerced_to_zero():
    """
    The important half of validation: a garbage figure must produce a 400
    naming the field, never a silent 0.0 that yields a confident wrong
    DSCR downstream.
    """
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")

        for overrides, expect_in_message in [
            ({"loan_amount": "not-a-number"}, "loan_amount"),
            ({"loan_amount": 0}, "loan_amount"),
            ({"loan_amount": -5_000}, "loan_amount"),
            ({"annual_rate_pct": -1}, "annual_rate_pct"),
            ({"amortization_years": 0}, "amortization_years"),
            ({"interest_only_months": -12}, "interest_only_months"),
        ]:
            response = _create_request(client, overrides)
            assert response.status_code == 400, (overrides, response.status_code)
            assert expect_in_message in response.get_json()["error"], (overrides, response.get_json())
    finally:
        _disable_flag()
    print("✓ test_invalid_numbers_are_refused_with_a_message_not_coerced_to_zero: PASS")


def test_missing_required_fields_are_refused():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        response = client.post("/loan-underwriting/requests", json={"property_address": _ADDRESS})
        assert response.status_code == 400, response.data
        assert "Missing required field" in response.get_json()["error"]
    finally:
        _disable_flag()
    print("✓ test_missing_required_fields_are_refused: PASS")


def test_a_zero_percent_rate_is_accepted():
    """0% is a legitimate loan (seller financing), not a validation error."""
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        response = _create_request(client, {"annual_rate_pct": 0})
        assert response.status_code == 201, response.data
        assert response.get_json()["annual_rate_pct"] == 0.0
    finally:
        _disable_flag()
    print("✓ test_a_zero_percent_rate_is_accepted: PASS")


def test_no_value_basis_at_all_is_refused():
    """Neither purchase price nor appraised value means no LTV is computable -- almost certainly a mistake, so it's refused with an explanation."""
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        body = {k: v for k, v in _VALID_REQUEST.items() if k not in ("purchase_price", "appraised_value")}
        response = client.post("/loan-underwriting/requests", json=body)
        assert response.status_code == 400, response.data
        assert "purchase_price" in response.get_json()["error"]
    finally:
        _disable_flag()
    print("✓ test_no_value_basis_at_all_is_refused: PASS")


def test_unknown_fields_are_rejected_so_audit_columns_cannot_be_set_by_a_client():
    """An allow-list, not 'whatever keys the body had' -- otherwise a client could set created_at or created_by_user_id."""
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        response = _create_request(client, {"created_by_user_id": 999})
        assert response.status_code == 400, response.data
        assert "Unknown field" in response.get_json()["error"]
    finally:
        _disable_flag()
    print("✓ test_unknown_fields_are_rejected_so_audit_columns_cannot_be_set_by_a_client: PASS")


# ----------------------------------------------------------------------
# Update / assumptions
# ----------------------------------------------------------------------

def test_updating_assumptions_merges_rather_than_replacing():
    """Editing vacancy alone must not reset the management fee to its default."""
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        body = dict(_VALID_REQUEST)
        body["assumptions"] = {"management_fee_pct": 4.0}
        request_id = client.post("/loan-underwriting/requests", json=body).get_json()["id"]

        updated = client.put(
            f"/loan-underwriting/requests/{request_id}/assumptions",
            json={"assumptions": {"vacancy_pct": 8.0}},
        ).get_json()

        assert updated["assumptions"]["vacancy_pct"] == 8.0
        assert updated["assumptions"]["management_fee_pct"] == 4.0, updated["assumptions"]
        assert updated["updated_at"] is not None
    finally:
        _disable_flag()
    print("✓ test_updating_assumptions_merges_rather_than_replacing: PASS")


def test_unknown_assumption_key_is_rejected_not_silently_ignored():
    """A typo'd assumption key must be an error -- silently ignoring it would let an analyst believe they'd changed something they hadn't."""
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        request_id = _create_request(client).get_json()["id"]
        response = client.put(
            f"/loan-underwriting/requests/{request_id}/assumptions",
            json={"assumptions": {"vacancy_percent": 8.0}},
        )
        assert response.status_code == 400, response.data
        assert "vacancy_percent" in response.get_json()["error"]
    finally:
        _disable_flag()
    print("✓ test_unknown_assumption_key_is_rejected_not_silently_ignored: PASS")


def test_updating_a_missing_request_is_404():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        assert client.put("/loan-underwriting/requests/9999", json={"loan_amount": 1_000}).status_code == 404
        assert client.get("/loan-underwriting/requests/9999").status_code == 404
    finally:
        _disable_flag()
    print("✓ test_updating_a_missing_request_is_404: PASS")


# ----------------------------------------------------------------------
# T-12 upload and underwriting
# ----------------------------------------------------------------------

def test_t12_upload_stores_parsed_figures_with_source_rows():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        request_id = _create_request(client).get_json()["id"]

        response = client.post(
            f"/loan-underwriting/requests/{request_id}/t12",
            data={"file": (io.BytesIO(_t12_csv_bytes()), "t12.csv")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 201, response.data
        payload = response.get_json()
        inputs = payload["snapshot"]["t12_inputs"]

        assert inputs["gross_potential_rent"] == 2_000_000.0, inputs
        assert inputs["loss_to_lease"] == 20_000.0, inputs
        assert inputs["bad_debt"] == 30_000.0, inputs
        assert inputs["other_income"] == 80_000.0, inputs
        # 700,000 total opex less the 57,600 management fee.
        assert inputs["operating_expenses_ex_management"] == 642_400.0, inputs
        assert payload["snapshot"]["management_fee_removed"] == 57_600.0, payload

        # Every T-12 figure cites the row it came from.
        assert payload["snapshot"]["sources"]["gross_potential_rent"]["row"] == 5, payload["snapshot"]["sources"]
        assert payload["snapshot"]["sources"]["gross_potential_rent"]["file"] == "t12.csv"
    finally:
        _disable_flag()
    print("✓ test_t12_upload_stores_parsed_figures_with_source_rows: PASS")


def test_underwriting_refuses_before_a_t12_is_uploaded():
    """A refusal with an explanation, not a zero-filled result."""
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        request_id = _create_request(client).get_json()["id"]
        response = client.get(f"/loan-underwriting/requests/{request_id}/underwriting")
        assert response.status_code == 400, response.data
        assert "T-12" in response.get_json()["error"]
    finally:
        _disable_flag()
    print("✓ test_underwriting_refuses_before_a_t12_is_uploaded: PASS")


def test_underwriting_returns_the_full_result_after_a_t12_upload():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        request_id = _create_request(client).get_json()["id"]
        client.post(
            f"/loan-underwriting/requests/{request_id}/t12",
            data={"file": (io.BytesIO(_t12_csv_bytes()), "t12.csv")},
            content_type="multipart/form-data",
        )

        result = client.get(f"/loan-underwriting/requests/{request_id}/underwriting").get_json()

        for key in ("noi_build_up", "debt_service", "ratios", "sizing", "stress_tests",
                    "assumption_rows", "input_rows", "assumptions_used", "constraints_used"):
            assert key in result, key
        assert len(result["stress_tests"]) == 5
        assert result["ratios"]["dscr"] is not None
        assert result["sizing"]["binding_constraint"] in ("dscr", "ltv", "debt_yield")

        # Every assumption is present, labelled, and flagged default-or-edited.
        keys = {row["key"] for row in result["assumption_rows"]}
        assert {"vacancy_pct", "management_fee_pct", "replacement_reserves_per_unit",
                "target_dscr", "max_ltv_pct", "min_debt_yield_pct"} <= keys, keys
        assert all("label" in row and "unit" in row and "is_default" in row
                   for row in result["assumption_rows"])
    finally:
        _disable_flag()
    print("✓ test_underwriting_returns_the_full_result_after_a_t12_upload: PASS")


def test_input_rows_distinguish_cited_figures_from_analyst_entered_ones():
    """
    "Every input number links to its source document" -- T-12 figures
    carry a {file,row,quote} citation; loan terms the analyst typed carry
    source: None rather than a fabricated citation.
    """
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        request_id = _create_request(client).get_json()["id"]
        client.post(
            f"/loan-underwriting/requests/{request_id}/t12",
            data={"file": (io.BytesIO(_t12_csv_bytes()), "t12.csv")},
            content_type="multipart/form-data",
        )
        rows = {r["key"]: r for r in
                client.get(f"/loan-underwriting/requests/{request_id}/underwriting").get_json()["input_rows"]}

        assert rows["loan_amount"]["origin"] == "user_entered"
        assert rows["loan_amount"]["source"] is None

        gpr = rows["gross_potential_rent"]
        assert gpr["origin"] == "t12_document"
        assert gpr["source"]["file"] == "t12.csv"
        assert gpr["source"]["row"] == 5
        # A spreadsheet has no pages: page is present and None, which is
        # different from having no source at all.
        assert gpr["source"]["page"] is None
    finally:
        _disable_flag()
    print("✓ test_input_rows_distinguish_cited_figures_from_analyst_entered_ones: PASS")


def test_t12_upload_with_no_file_or_a_bad_file_is_refused():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        request_id = _create_request(client).get_json()["id"]

        assert client.post(f"/loan-underwriting/requests/{request_id}/t12").status_code == 400

        unparseable = client.post(
            f"/loan-underwriting/requests/{request_id}/t12",
            data={"file": (io.BytesIO(b"not,a,t12\n1,2,3"), "junk.csv")},
            content_type="multipart/form-data",
        )
        assert unparseable.status_code == 400, unparseable.data
    finally:
        _disable_flag()
    print("✓ test_t12_upload_with_no_file_or_a_bad_file_is_refused: PASS")


def test_reuploading_a_t12_supersedes_the_previous_snapshot():
    """A corrected T-12 is routine; the newest snapshot is the one underwriting uses, and the old one is kept rather than overwritten."""
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        request_id = _create_request(client).get_json()["id"]
        client.post(
            f"/loan-underwriting/requests/{request_id}/t12",
            data={"file": (io.BytesIO(_t12_csv_bytes()), "first.csv")},
            content_type="multipart/form-data",
        )

        corrected = [list(row) for row in _T12_ROWS]
        corrected[4] = ["Gross Potential Rent", "2500000"]
        buf = io.StringIO()
        csv.writer(buf).writerows(corrected)
        client.post(
            f"/loan-underwriting/requests/{request_id}/t12",
            data={"file": (io.BytesIO(buf.getvalue().encode()), "second.csv")},
            content_type="multipart/form-data",
        )

        result = client.get(f"/loan-underwriting/requests/{request_id}/underwriting").get_json()
        assert result["noi_build_up"]["gross_potential_rent"] == 2_500_000.0, result["noi_build_up"]
        assert result["t12_snapshot"]["filename"] == "second.csv"
    finally:
        _disable_flag()
    print("✓ test_reuploading_a_t12_supersedes_the_previous_snapshot: PASS")


def test_listing_can_be_filtered_to_one_building():
    _fresh_temp_db()
    _enable_flag()
    try:
        client = _client_as(_user("a@example.com", "analyst"), "a@example.com", "analyst")
        _create_request(client)
        _create_request(client, {"property_address": "900 Different Street, Austin, TX 78701"})

        all_requests = client.get("/loan-underwriting/requests").get_json()["requests"]
        assert len(all_requests) == 2, all_requests

        filtered = client.get(
            "/loan-underwriting/requests", query_string={"property_address": _ADDRESS}
        ).get_json()["requests"]
        assert len(filtered) == 1, filtered
        assert filtered[0]["property_address"] == _ADDRESS
    finally:
        _disable_flag()
    print("✓ test_listing_can_be_filtered_to_one_building: PASS")


if __name__ == "__main__":
    test_every_route_404s_when_the_flag_is_off()
    test_flag_off_404s_even_for_an_anonymous_caller()
    test_routes_exist_when_the_flag_is_on()
    test_anonymous_caller_is_rejected_on_every_route_with_the_flag_on()
    test_viewer_can_read_but_cannot_write_or_export()
    test_create_stores_every_loan_term_and_the_default_assumptions()
    test_create_accepts_assumption_and_constraint_overrides()
    test_invalid_numbers_are_refused_with_a_message_not_coerced_to_zero()
    test_missing_required_fields_are_refused()
    test_a_zero_percent_rate_is_accepted()
    test_no_value_basis_at_all_is_refused()
    test_unknown_fields_are_rejected_so_audit_columns_cannot_be_set_by_a_client()
    test_updating_assumptions_merges_rather_than_replacing()
    test_unknown_assumption_key_is_rejected_not_silently_ignored()
    test_updating_a_missing_request_is_404()
    test_t12_upload_stores_parsed_figures_with_source_rows()
    test_underwriting_refuses_before_a_t12_is_uploaded()
    test_underwriting_returns_the_full_result_after_a_t12_upload()
    test_input_rows_distinguish_cited_figures_from_analyst_entered_ones()
    test_t12_upload_with_no_file_or_a_bad_file_is_refused()
    test_reuploading_a_t12_supersedes_the_previous_snapshot()
    test_listing_can_be_filtered_to_one_building()
    print("\nAll loan request API tests passed.")
