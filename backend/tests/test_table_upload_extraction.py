"""
Tests for the fix that lets a table-shaped .csv/.xlsx (a rent roll,
or this app's own export -- header row + one or more data rows) be
correctly re-uploaded through the GENERAL upload/resubmit paths
(POST /leases, /leases/batch, /leases/<id>/resubmit), instead of
falling through to FieldExtractor's label:value prose extraction,
which garbles a table (a header row and a data row each collapse
into one run-on line -- see document_extractor._rows_to_lines'
docstring) into confidently-wrong values.

Found live: re-uploading this app's own /leases/<id>/export.xlsx
through POST /leases produced a lease whose display_name was the
entire header row concatenated, with "tenant"/"landlord" holding
fragments of OTHER column headers.

Same conventions as test_rent_roll_import_api.py: _fresh_temp_db() +
Flask test_client(), no live server required.
"""

import csv
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openpyxl import Workbook

from app.api import app
from app import database
from app.rent_roll_export import generate_rent_roll_csv, generate_rent_roll_excel


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _authed_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["email"] = "test-analyst@example.com"
        sess["name"] = "Test Analyst"
        sess["role"] = "analyst"
    return client


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def _xlsx_bytes(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------
# Re-uploading THIS APP'S OWN export through the general upload path
# ------------------------------------------------------------------

def test_reuploading_own_single_lease_export_extracts_correctly_not_garbled():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease_id = database.insert_lease(
            "original.pdf",
            {
                "tenant": {"value": "Acme Corp", "source": {"page": 1, "quote": "Acme Corp"}, "confidence": "high"},
                "landlord": {"value": "Big Landlord LLC", "source": {"page": 1, "quote": "Big Landlord LLC"}, "confidence": "high"},
                "rent_amount": {"value": "$5,000.00", "source": {"page": 1, "quote": "$5,000.00"}, "confidence": "high"},
                "property_address": {"value": "100 Main St, Suite 5", "source": {"page": 1, "quote": "100 Main St"}, "confidence": "high"},
                "lease_start_date": {"value": "January 1, 2025", "source": None, "confidence": "high"},
                "lease_end_date": {"value": "December 31, 2029", "source": None, "confidence": "high"},
                "square_footage": {"value": None, "source": None, "confidence": None},
                "security_deposit": {"value": None, "source": None, "confidence": None},
                "cam_charges": {"value": None, "source": None, "confidence": None},
                "rent_escalation": {"value": None, "source": None, "confidence": None},
                "renewal_options": {"value": None, "source": None, "confidence": None},
                "permitted_use": {"value": None, "source": None, "confidence": None},
                "exclusivity_clause": {"value": None, "source": None, "confidence": None},
                "insurance_requirements": {"value": None, "source": None, "confidence": None},
                "default_cure_period": {"value": None, "source": None, "confidence": None},
            },
            display_name="Acme Corp - 100 Main St, Suite 5",
        )

        # Export it exactly like GET /leases/<id>/export.xlsx does.
        lease = database.get_effective_lease(lease_id)
        xlsx_bytes = generate_rent_roll_excel([lease])

        # Re-upload it through the GENERAL upload route -- what was broken.
        resp = client.post("/leases", data={"file": (io.BytesIO(xlsx_bytes), "reexported.xlsx")}, content_type="multipart/form-data")
        assert resp.status_code == 201, resp.get_json()
        new_lease = resp.get_json()["leases"][0]

        assert new_lease["extracted_fields"]["tenant"]["value"] == "Acme Corp", new_lease["extracted_fields"]["tenant"]
        assert new_lease["extracted_fields"]["landlord"]["value"] == "Big Landlord LLC"
        assert new_lease["extracted_fields"]["rent_amount"]["value"] == "$5,000.00"
        assert new_lease["extracted_fields"]["property_address"]["value"] == "100 Main St, Suite 5"
        assert new_lease["display_name"] == "Acme Corp - 100 Main St, Suite 5", \
            "display_name must not be the concatenated header row"
        # Citation shape: row/file/quote (table-sourced), not page/quote.
        assert "row" in new_lease["extracted_fields"]["tenant"]["source"]
    finally:
        os.unlink(db_path)
    print("✓ test_reuploading_own_single_lease_export_extracts_correctly_not_garbled: PASS")


def test_reuploading_own_portfolio_export_csv_extracts_correctly():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease_id = database.insert_lease(
            "original.pdf",
            {
                "tenant": {"value": "Beta Industries", "source": None, "confidence": "high"},
                "landlord": {"value": "Owner Co", "source": None, "confidence": "high"},
                "rent_amount": {"value": "$7,250.00", "source": None, "confidence": "high"},
                "property_address": {"value": "200 Second Ave", "source": None, "confidence": "high"},
                "lease_start_date": {"value": None, "source": None, "confidence": None},
                "lease_end_date": {"value": None, "source": None, "confidence": None},
                "square_footage": {"value": None, "source": None, "confidence": None},
                "security_deposit": {"value": None, "source": None, "confidence": None},
                "cam_charges": {"value": None, "source": None, "confidence": None},
                "rent_escalation": {"value": None, "source": None, "confidence": None},
                "renewal_options": {"value": None, "source": None, "confidence": None},
                "permitted_use": {"value": None, "source": None, "confidence": None},
                "exclusivity_clause": {"value": None, "source": None, "confidence": None},
                "insurance_requirements": {"value": None, "source": None, "confidence": None},
                "default_cure_period": {"value": None, "source": None, "confidence": None},
            },
        )
        lease = database.get_effective_lease(lease_id)
        csv_text = generate_rent_roll_csv([lease])

        resp = client.post("/leases", data={"file": (io.BytesIO(csv_text.encode()), "reexported.csv")}, content_type="multipart/form-data")
        assert resp.status_code == 201, resp.get_json()
        new_lease = resp.get_json()["leases"][0]
        assert new_lease["extracted_fields"]["tenant"]["value"] == "Beta Industries"
        assert new_lease["extracted_fields"]["rent_amount"]["value"] == "$7,250.00"
    finally:
        os.unlink(db_path)
    print("✓ test_reuploading_own_portfolio_export_csv_extracts_correctly: PASS")


# ------------------------------------------------------------------
# Fallback: a genuine label:value spreadsheet must keep working
# ------------------------------------------------------------------

def test_label_value_spreadsheet_still_falls_back_to_prose_extraction():
    """A spreadsheet built as a simple label:value form (one fact per row, e.g. "Tenant:" | "Acme Corp") is NOT a table the rent-roll column-alias matcher recognizes (no header row of known column names) -- must still fall back to the existing prose path and extract correctly, exactly as before this fix."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        rows = [
            ["Tenant:", "Acme Corp"],
            ["Landlord:", "Big Landlord LLC"],
            ["Monthly Rent:", "$5,000.00"],
            ["Lease Start Date:", "January 1, 2025"],
            ["Lease End Date:", "December 31, 2029"],
        ]
        xlsx_bytes = _xlsx_bytes(rows)
        resp = client.post("/leases", data={"file": (io.BytesIO(xlsx_bytes), "label_value_lease.xlsx")}, content_type="multipart/form-data")
        assert resp.status_code == 201, resp.get_json()
        new_lease = resp.get_json()["leases"][0]
        assert new_lease["extracted_fields"]["tenant"]["value"] == "Acme Corp"
        assert new_lease["extracted_fields"]["rent_amount"]["value"] == "$5,000.00"
    finally:
        os.unlink(db_path)
    print("✓ test_label_value_spreadsheet_still_falls_back_to_prose_extraction: PASS")


# ------------------------------------------------------------------
# Table extraction through the RESUBMIT path specifically
# ------------------------------------------------------------------

def test_resubmit_with_edited_xlsx_export_updates_the_lease():
    """The full user-facing scenario: export a lease, edit a value, resubmit it -- the existing record must reflect the new value, not a duplicate, not ignored."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease_id = database.insert_lease(
            "original.pdf",
            {
                "tenant": {"value": "Gamma LLC", "source": None, "confidence": "high"},
                "landlord": {"value": "Landlord Co", "source": None, "confidence": "high"},
                "rent_amount": {"value": "$4,000.00", "source": None, "confidence": "high"},
                "property_address": {"value": "300 Third St", "source": None, "confidence": "high"},
                "lease_start_date": {"value": None, "source": None, "confidence": None},
                "lease_end_date": {"value": None, "source": None, "confidence": None},
                "square_footage": {"value": None, "source": None, "confidence": None},
                "security_deposit": {"value": None, "source": None, "confidence": None},
                "cam_charges": {"value": None, "source": None, "confidence": None},
                "rent_escalation": {"value": None, "source": None, "confidence": None},
                "renewal_options": {"value": None, "source": None, "confidence": None},
                "permitted_use": {"value": None, "source": None, "confidence": None},
                "exclusivity_clause": {"value": None, "source": None, "confidence": None},
                "insurance_requirements": {"value": None, "source": None, "confidence": None},
                "default_cure_period": {"value": None, "source": None, "confidence": None},
            },
        )
        lease = database.get_effective_lease(lease_id)
        xlsx_bytes = generate_rent_roll_excel([lease])

        # Edit the exported file's rent cell.
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx_bytes))
        ws = wb["Rent Roll"]
        headers = [c.value for c in ws[1]]
        rent_col = headers.index("Monthly Rent") + 1
        ws.cell(row=2, column=rent_col, value=9999)
        buf = io.BytesIO()
        wb.save(buf)
        edited_bytes = buf.getvalue()

        resp = client.post(f"/leases/{lease_id}/resubmit", data={"file": (io.BytesIO(edited_bytes), "edited.xlsx")}, content_type="multipart/form-data")
        assert resp.status_code == 201, resp.get_json()
        result = resp.get_json()
        new_id = result["lease"]["id"]
        assert new_id != lease_id
        assert result["lease"]["extracted_fields"]["rent_amount"]["value"] == "$9,999.00"

        # Confirm on a fresh read too -- not just the response.
        after = database.get_effective_fields(new_id)
        assert after["rent_amount"]["value"] == "$9,999.00"
        assert after["tenant"]["value"] == "Gamma LLC"

        old = database.get_lease(lease_id)
        assert old["status"] == "superseded"
        active_ids = [l["id"] for l in database.get_all_effective_leases()]
        assert lease_id not in active_ids
        assert new_id in active_ids
    finally:
        os.unlink(db_path)
    print("✓ test_resubmit_with_edited_xlsx_export_updates_the_lease: PASS")


def test_resubmit_with_edited_csv_updates_the_lease():
    """Same round trip, CSV instead of Excel."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease_id = database.insert_lease(
            "original.pdf",
            {
                "tenant": {"value": "Delta Inc", "source": None, "confidence": "high"},
                "landlord": {"value": None, "source": None, "confidence": None},
                "rent_amount": {"value": "$3,000.00", "source": None, "confidence": "high"},
                "property_address": {"value": "400 Fourth Ave", "source": None, "confidence": "high"},
                "lease_start_date": {"value": None, "source": None, "confidence": None},
                "lease_end_date": {"value": None, "source": None, "confidence": None},
                "square_footage": {"value": None, "source": None, "confidence": None},
                "security_deposit": {"value": None, "source": None, "confidence": None},
                "cam_charges": {"value": None, "source": None, "confidence": None},
                "rent_escalation": {"value": None, "source": None, "confidence": None},
                "renewal_options": {"value": None, "source": None, "confidence": None},
                "permitted_use": {"value": None, "source": None, "confidence": None},
                "exclusivity_clause": {"value": None, "source": None, "confidence": None},
                "insurance_requirements": {"value": None, "source": None, "confidence": None},
                "default_cure_period": {"value": None, "source": None, "confidence": None},
            },
        )
        lease = database.get_effective_lease(lease_id)
        csv_text = generate_rent_roll_csv([lease])
        edited_csv = csv_text.replace("$3,000.00", "$6,500.00")

        resp = client.post(f"/leases/{lease_id}/resubmit", data={"file": (io.BytesIO(edited_csv.encode()), "edited.csv")}, content_type="multipart/form-data")
        assert resp.status_code == 201, resp.get_json()
        new_id = resp.get_json()["lease"]["id"]
        after = database.get_effective_fields(new_id)
        assert after["rent_amount"]["value"] == "$6,500.00"
        assert after["tenant"]["value"] == "Delta Inc"
    finally:
        os.unlink(db_path)
    print("✓ test_resubmit_with_edited_csv_updates_the_lease: PASS")


def test_multi_row_table_still_rejected_by_resubmit():
    """A resubmission expects exactly one lease -- a multi-row table (an accidental full rent roll) must still be rejected, same as before this fix, now via the table-extraction path instead of looks_like_rent_roll_table (which only guards the prose path)."""
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        lease_id = database.insert_lease(
            "original.pdf",
            {"tenant": {"value": "Epsilon Co", "source": None, "confidence": "high"},
             "rent_amount": {"value": "$1,000.00", "source": None, "confidence": "high"},
             **{f: {"value": None, "source": None, "confidence": None} for f in
                ["landlord", "property_address", "lease_start_date", "lease_end_date", "square_footage",
                 "security_deposit", "cam_charges", "rent_escalation", "renewal_options", "permitted_use",
                 "exclusivity_clause", "insurance_requirements", "default_cure_period"]}},
        )
        rows = [
            ["Tenant Name", "Monthly Rent"],
            ["Row One LLC", "1000"],
            ["Row Two LLC", "2000"],
        ]
        xlsx_bytes = _xlsx_bytes(rows)
        resp = client.post(f"/leases/{lease_id}/resubmit", data={"file": (io.BytesIO(xlsx_bytes), "multi_row.xlsx")}, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert "single lease" in resp.get_json()["error"].lower()
    finally:
        os.unlink(db_path)
    print("✓ test_multi_row_table_still_rejected_by_resubmit: PASS")


if __name__ == "__main__":
    test_reuploading_own_single_lease_export_extracts_correctly_not_garbled()
    test_reuploading_own_portfolio_export_csv_extracts_correctly()
    test_label_value_spreadsheet_still_falls_back_to_prose_extraction()
    test_resubmit_with_edited_xlsx_export_updates_the_lease()
    test_resubmit_with_edited_csv_updates_the_lease()
    test_multi_row_table_still_rejected_by_resubmit()
    print("\nAll table-upload extraction tests passed.")
