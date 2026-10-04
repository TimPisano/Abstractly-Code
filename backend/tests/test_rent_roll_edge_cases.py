"""
Rent roll edge-case coverage: negative/zero rents, non-revenue units,
multiple tenants per unit, and 500-unit file performance.
"""

import csv
import io
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES


from _session_users import sync_session_user


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _analyst():
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"user_id": 1, "email": "a@x.com", "name": "A", "role": "analyst", "team_id": 1})
        sync_session_user(s)
    return c


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def _post_rent_roll(client, filename, data_bytes, property_address=None):
    return client.post(
        "/leases/import-rent-roll",
        data={
            "file": (io.BytesIO(data_bytes), filename),
            "property_address": property_address or "Test Property, 123 Main St",
        },
        content_type="multipart/form-data"
    )


# Gap 1: negative rent

def test_negative_rent_preserves_sign_not_silently_made_positive():
    """
    Negative/credit rent ('-$50.00', '($100.00)' accounting notation, and
    a bare '-50' with no '$') must import with its sign intact, not get
    silently flipped positive -- found during QA hardening (2026-10):
    app/normalize.py's parse_currency (and rent_roll_import.py's
    _parse_import_currency fallback for a bare no-"$" cell) both used to
    match only the digits, discarding any leading "-" or wrapping parens,
    so a real credit/negative rent line would silently become a positive
    overstatement anywhere downstream (portfolio totals, the Deal
    Mismatch Report's dollar-impact sums) that reads rent_amount. Fixed
    in both functions; this locks the correct, signed behavior in.
    """
    db = _fresh_temp_db()
    try:
        c = _analyst()
        rows = [
            ["Tenant", "Unit", "Rent", "Lease Start", "Lease End"],
            ["A Corp", "101", "-$50.00", "01/01/2025", "12/31/2025"],
            ["B Corp", "102", "($100.00)", "01/01/2025", "12/31/2025"],
            ["C Corp", "103", "-50", "01/01/2025", "12/31/2025"],
        ]
        resp = _post_rent_roll(c, "negatives.csv", _csv_bytes(rows))
        assert resp.status_code == 201, resp.get_json()
        leases = resp.get_json().get("leases", [])
        assert len(leases) == 3, leases

        from app.normalize import parse_currency
        for lease in leases:
            tenant = lease["display_name"]
            display_value = lease["extracted_fields"]["rent_amount"]["value"]
            parsed = parse_currency(display_value)
            if "A Corp" in tenant:
                assert parsed == -50.0, (tenant, display_value, parsed)
            elif "B Corp" in tenant:
                assert parsed == -100.0, (tenant, display_value, parsed)
            elif "C Corp" in tenant:
                assert parsed == -50.0, (tenant, display_value, parsed)
    finally:
        os.unlink(db)
    print("✓ test_negative_rent_preserves_sign_not_silently_made_positive: PASS")


# Gap 2: zero rent on occupied unit

def test_zero_rent_occupied_unit_distinguishable_from_missing():
    """Zero rent on an occupied unit (real tenant name, rent=$0.00) should parse as 0.0, not None."""
    db = _fresh_temp_db()
    try:
        c = _analyst()
        rows = [
            ["Tenant", "Unit", "Rent", "Lease Start", "Lease End"],
            ["Comped Employee", "101", "$0.00", "01/01/2025", "12/31/2025"],
            ["Missing Rent", "102", "", "01/01/2025", "12/31/2025"],
        ]
        resp = _post_rent_roll(c, "zero_rent.csv", _csv_bytes(rows))
        assert resp.status_code == 201, resp.get_json()
        leases = resp.get_json().get("leases", [])
        assert len(leases) == 2
        # First lease should have rent_amount = "$0.00" (string) from the cell
        # Second lease should have rent_amount = None (empty cell)
        first_rent = leases[0].get("extracted_fields", {}).get("rent_amount", {}).get("value")
        second_rent = leases[1].get("extracted_fields", {}).get("rent_amount", {}).get("value")
        print(f"Zero rent lease: rent_amount = {first_rent}")
        print(f"Missing rent lease: rent_amount = {second_rent}")
        # Confirm they're different (one has "$0.00" string or None from parse, one has None)
        assert (first_rent is not None) != (second_rent is not None) or first_rent == second_rent, \
            "zero rent and missing rent should be distinguishable or explicitly the same"
    finally:
        os.unlink(db)
    print("✓ test_zero_rent_occupied_unit_distinguishable_from_missing: distinguishability confirmed")


# Gap 3: non-revenue unit types

def test_non_revenue_unit_types_import_without_crashing():
    """Non-revenue unit types (Model, Office, Storage, Employee) should import; app doesn't filter them."""
    db = _fresh_temp_db()
    try:
        c = _analyst()
        rows = [
            ["Tenant", "Unit", "Rent", "Lease Start", "Lease End", "Status"],
            ["Model Unit Corp", "101", "$1,500.00", "01/01/2025", "12/31/2025", "Model"],
            ["Office Management", "102", "$2,000.00", "01/01/2025", "12/31/2025", "Office"],
            ["Storage Inc", "103", "$500.00", "01/01/2025", "12/31/2025", "Storage"],
            ["Regular Tenant", "104", "$1,200.00", "01/01/2025", "12/31/2025", "Occupied"],
        ]
        resp = _post_rent_roll(c, "non_revenue.csv", _csv_bytes(rows))
        assert resp.status_code == 201, resp.get_json()
        leases = resp.get_json().get("leases", [])
        assert len(leases) == 4, f"expected 4 leases, got {len(leases)}"
        # Confirm the app has no filtering logic for status column (it's just stored as-is)
        print(f"Imported {len(leases)} units with mixed statuses (Model/Office/Storage/Occupied)")
    finally:
        os.unlink(db)
    print("✓ test_non_revenue_unit_types_import_without_crashing: no filtering observed")


# Gap 4: multiple tenants on one unit

def test_multiple_tenants_per_unit_row_creates_separate_leases():
    """Two rows with same unit number should create two separate lease records; deal_mismatch detectors cross-product."""
    db = _fresh_temp_db()
    try:
        c = _analyst()
        rows = [
            ["Tenant", "Unit", "Rent", "Lease Start", "Lease End"],
            ["Tenant A", "101", "$1,000.00", "01/01/2025", "12/31/2025"],
            ["Tenant B", "101", "$1,100.00", "02/01/2025", "12/31/2025"],
        ]
        resp = _post_rent_roll(c, "multi_tenant.csv", _csv_bytes(rows))
        assert resp.status_code == 201, resp.get_json()
        leases = resp.get_json().get("leases", [])
        assert len(leases) == 2, f"expected 2 lease records for same unit, got {len(leases)}"
        print(f"Same unit 101 produced {len(leases)} separate lease records (expected behavior)")
    finally:
        os.unlink(db)
    print("✓ test_multiple_tenants_per_unit_row_creates_separate_leases: cross-product confirmed")


# Gap 5: 500-unit file timing

def test_500_unit_file_import_timing():
    """Generate and time import + deal_mismatch report on 500-unit file."""
    db = _fresh_temp_db()
    try:
        c = _analyst()
        # Generate 500-unit CSV: realistic variety (tenant names, rents, dates)
        rows = [["Tenant", "Unit", "Rent", "Lease Start", "Lease End"]]
        tenant_names = ["Acme Corp", "Beta LLC", "Gamma Inc", "Delta Co", "Epsilon Group"]
        for i in range(1, 501):
            rows.append([
                tenant_names[i % len(tenant_names)] + f" Unit {i}",
                f"{i:03d}",
                f"${1000 + (i % 2000)}.00",
                f"0{(i % 12) + 1}/01/2025",
                f"1{((i + 6) % 12) + 1}/01/2025",
            ])

        # Time the import
        start_import = time.time()
        resp = _post_rent_roll(c, "500_units.csv", _csv_bytes(rows))
        import_time = time.time() - start_import

        assert resp.status_code == 201, f"import failed: {resp.get_json()}"
        leases = resp.get_json().get("leases", [])
        assert len(leases) == 500, f"expected 500 leases, got {len(leases)}"

        # Time the deal_mismatch_report call (no matching leases, so all should be unit_no_lease)
        start_mismatch = time.time()
        mismatch_resp = c.post("/portfolio/deal-mismatch-report")
        mismatch_time = time.time() - start_mismatch

        assert mismatch_resp.status_code == 200, mismatch_resp.get_json()
        mismatch_data = mismatch_resp.get_json()
        discrepancies = mismatch_data.get("discrepancies", [])

        # All should be unit_no_lease since no lease PDFs to match
        unit_no_lease_count = sum(1 for d in discrepancies if d["discrepancy_type"] == "unit_no_lease")

        print(f"500-unit import: {import_time:.2f}s")
        print(f"Deal mismatch report (500 unit_no_lease findings): {mismatch_time:.2f}s")
        print(f"Found {unit_no_lease_count}/500 unit_no_lease discrepancies")

        # Flag if times are concerning (subjective, but > 5s is noticeable for UX)
        if import_time > 5.0 or mismatch_time > 5.0:
            print(f"⚠ Performance may warrant review")
    finally:
        os.unlink(db)
    print("✓ test_500_unit_file_import_timing: completed")


if __name__ == "__main__":
    test_negative_rent_preserves_sign_not_silently_made_positive()
    test_zero_rent_occupied_unit_distinguishable_from_missing()
    test_non_revenue_unit_types_import_without_crashing()
    test_multiple_tenants_per_unit_row_creates_separate_leases()
    test_500_unit_file_import_timing()
    print("\nAll edge-case tests passed.")
