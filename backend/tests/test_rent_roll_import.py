"""
Tests for app/rent_roll_import.py -- the broker Excel/CSV rent roll
importer. No fixed format is assumed (that's the whole point), so
these tests deliberately exercise header-naming diversity, vacant/
total rows, currency formatting variety, and missing columns, not just
one clean example.
"""

import csv
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openpyxl import Workbook

from app.rent_roll_import import (
    RentRollImportError,
    parse_csv_rent_roll,
    parse_rent_roll_rows,
    parse_xlsx_rent_roll,
)


def _csv_bytes(rows):
    """
    Proper CSV encoding, not a naive ",".join() -- several test fixtures
    below intentionally use values like "$4,500.00" that themselves
    contain a comma, which a naive join would incorrectly split into
    two fields. Using csv.writer catches exactly that class of bug
    (caught for real during initial test authoring here, not
    hypothetically -- see DECISIONS.md).
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _xlsx_bytes(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_csv_happy_path_standard_headers():
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent", "Square Footage", "Lease Start", "Lease End"],
        ["Acme Corp", "$4,500.00", "2,000 sq ft", "01/01/2024", "12/31/2028"],
        ["Beta LLC", "$3,200.00", "1,500 sq ft", "06/01/2023", "05/31/2027"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rentroll.csv", base_property_address="100 Main St")

    assert result["skipped_rows"] == []
    assert len(result["leases"]) == 2
    acme = result["leases"][0]["extracted_fields"]
    assert acme["tenant"]["value"] == "Acme Corp"
    assert acme["rent_amount"]["value"] == "$4,500.00"
    assert acme["square_footage"]["value"] == "2,000 sq ft"
    assert acme["property_address"]["value"] == "100 Main St"
    assert acme["lease_start_date"]["source"]["row"] == 2
    assert acme["lease_start_date"]["source"]["file"] == "rentroll.csv"
    print("✓ test_csv_happy_path_standard_headers: PASS")


def test_xlsx_happy_path_with_real_numeric_and_date_cell_types():
    """xlsx cells commonly come back as real Python int/float/date objects, not strings -- confirms those are handled, not just string cells."""
    from datetime import date
    xlsx_bytes = _xlsx_bytes([
        ["Tenant Name", "Monthly Rent", "Sq Ft", "Commencement Date"],
        ["Acme Corp", 4500, 2000, date(2024, 1, 1)],  # real numbers/date, not strings
    ])
    result = parse_xlsx_rent_roll(xlsx_bytes, "rentroll.xlsx")

    assert len(result["leases"]) == 1
    fields = result["leases"][0]["extracted_fields"]
    assert fields["rent_amount"]["value"] == "$4,500.00"
    assert fields["square_footage"]["value"] == "2,000 sq ft"
    assert fields["lease_start_date"]["value"] == "January 01, 2024"
    print("✓ test_xlsx_happy_path_with_real_numeric_and_date_cell_types: PASS")


def test_header_alias_diversity():
    """Different brokers name columns differently -- confirms several realistic header variants all map correctly, not just one exact spelling."""
    csv_bytes = _csv_bytes([
        ["Lessee", "Base Rent", "RSF", "Suite #"],
        ["Gamma Inc", "$2,000.00", "1,000", "204"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv", base_property_address="500 Plaza Dr")
    fields = result["leases"][0]["extracted_fields"]
    assert fields["tenant"]["value"] == "Gamma Inc"
    assert fields["rent_amount"]["value"] == "$2,000.00"
    assert fields["square_footage"]["value"] == "1,000 sq ft"
    assert fields["property_address"]["value"] == "500 Plaza Dr, Suite 204"
    print("✓ test_header_alias_diversity: PASS")


def test_bare_numeric_rent_with_no_dollar_sign():
    """A rent column stored as a plain number string (no "$") -- common in CSV exports -- must still parse."""
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],
        ["Delta Co", "3200.50"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert result["leases"][0]["extracted_fields"]["rent_amount"]["value"] == "$3,200.50"
    print("✓ test_bare_numeric_rent_with_no_dollar_sign: PASS")


def test_vacant_row_skipped():
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],
        ["Real Tenant Co", "$1,000.00"],
        ["VACANT", "$0.00"],
        ["Vacant", ""],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert len(result["leases"]) == 1
    assert len(result["skipped_rows"]) == 2
    assert result["skipped_rows"][0]["row"] == 3
    print("✓ test_vacant_row_skipped: PASS")


def test_total_row_skipped():
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],
        ["Real Tenant Co", "$1,000.00"],
        ["Total", "$1,000.00"],
        ["Subtotal", "$1,000.00"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert len(result["leases"]) == 1
    assert len(result["skipped_rows"]) == 2
    print("✓ test_total_row_skipped: PASS")


def test_blank_tenant_row_skipped():
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],
        ["Real Tenant Co", "$1,000.00"],
        ["", "$500.00"],  # blank tenant, e.g. a formatting/spacer row
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert len(result["leases"]) == 1
    assert len(result["skipped_rows"]) == 1
    print("✓ test_blank_tenant_row_skipped: PASS")


def test_missing_tenant_and_rent_columns_raises():
    csv_bytes = _csv_bytes([
        ["Property Name", "Notes"],
        ["Building A", "some note"],
    ])
    try:
        parse_csv_rent_roll(csv_bytes, "rr.csv")
        assert False, "should have raised RentRollImportError"
    except RentRollImportError:
        pass
    print("✓ test_missing_tenant_and_rent_columns_raises: PASS")


def test_missing_optional_column_does_not_block_import():
    """No square-footage column at all -- rows must still import, with square_footage honestly 'not found', not a crash."""
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],
        ["Epsilon LLC", "$2,500.00"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert len(result["leases"]) == 1
    fields = result["leases"][0]["extracted_fields"]
    assert fields["square_footage"]["value"] is None
    assert fields["square_footage"]["source"] is None
    print("✓ test_missing_optional_column_does_not_block_import: PASS")


def test_unrecognized_extra_columns_ignored():
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent", "Parking Spaces", "Notes"],
        ["Zeta Inc", "$1,800.00", "4", "corner unit"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert len(result["leases"]) == 1  # extra columns don't break anything
    print("✓ test_unrecognized_extra_columns_ignored: PASS")


def test_blank_rows_in_file_are_skipped_entirely():
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],
        ["Eta Co", "$1,200.00"],
        ["", ""],  # a fully blank spacer row
        ["Theta Co", "$1,400.00"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert len(result["leases"]) == 2
    assert result["skipped_rows"] == []  # fully-blank rows are dropped before parsing, not reported as skipped
    print("✓ test_blank_rows_in_file_are_skipped_entirely: PASS")


def test_no_base_address_and_no_unit_column_leaves_address_unset():
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],
        ["Iota Inc", "$900.00"],
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")  # no base_property_address passed
    fields = result["leases"][0]["extracted_fields"]
    assert fields["property_address"]["value"] is None
    print("✓ test_no_base_address_and_no_unit_column_leaves_address_unset: PASS")


def test_empty_csv_raises():
    try:
        parse_csv_rent_roll(b"", "empty.csv")
        assert False, "should have raised RentRollImportError"
    except RentRollImportError:
        pass
    print("✓ test_empty_csv_raises: PASS")


def test_empty_xlsx_raises():
    empty_bytes = _xlsx_bytes([])
    try:
        parse_xlsx_rent_roll(empty_bytes, "empty.xlsx")
        assert False, "should have raised RentRollImportError"
    except RentRollImportError:
        pass
    print("✓ test_empty_xlsx_raises: PASS")


def test_row_numbers_reflect_actual_file_position():
    """Row numbering must match what a human looking at the actual spreadsheet would count (1-indexed, header is row 1)."""
    csv_bytes = _csv_bytes([
        ["Tenant", "Rent"],   # row 1
        ["First Co", "$1,000.00"],  # row 2
        ["Second Co", "$2,000.00"],  # row 3
    ])
    result = parse_csv_rent_roll(csv_bytes, "rr.csv")
    assert result["leases"][0]["extracted_fields"]["tenant"]["source"]["row"] == 2
    assert result["leases"][1]["extracted_fields"]["tenant"]["source"]["row"] == 3
    print("✓ test_row_numbers_reflect_actual_file_position: PASS")


def test_specific_date_column_not_misattributed_to_rent_amount():
    """
    Regression test for a real bug: "Rent Commencement"/"Rent
    Expiration" are standard commercial lease terms (rent can start
    later than the lease itself during a free-rent period) -- these
    must map to lease_start_date/lease_end_date, not get grabbed by
    rent_amount's bare "rent" alias just because that field happens to
    be checked first. With no unambiguous rent-amount column present at
    all, rent_amount should end up genuinely unmapped (honest failure)
    rather than incorrectly pointed at a date column.
    """
    csv_bytes = _csv_bytes([
        ["Tenant", "Monthly Payment", "Rent Commencement", "Rent Expiration"],
        ["Acme Corp", "$4,000.00", "01/01/2024", "12/31/2028"],
    ])
    try:
        parse_csv_rent_roll(csv_bytes, "rr.csv")
        assert False, "should have raised -- 'Monthly Payment' isn't a recognized rent alias, so rent_amount is genuinely unmapped"
    except RentRollImportError:
        pass

    # But WITH an unambiguous "Rent" column present, the date columns
    # must still land correctly, not collide with it.
    csv_bytes2 = _csv_bytes([
        ["Tenant", "Rent", "Rent Commencement", "Rent Expiration"],
        ["Acme Corp", "$4,000.00", "01/01/2024", "12/31/2028"],
    ])
    result = parse_csv_rent_roll(csv_bytes2, "rr.csv")
    fields = result["leases"][0]["extracted_fields"]
    assert fields["rent_amount"]["value"] == "$4,000.00"
    assert fields["lease_start_date"]["value"] == "01/01/2024"
    assert fields["lease_end_date"]["value"] == "12/31/2028"
    print("✓ test_specific_date_column_not_misattributed_to_rent_amount: PASS")


if __name__ == "__main__":
    test_csv_happy_path_standard_headers()
    test_xlsx_happy_path_with_real_numeric_and_date_cell_types()
    test_header_alias_diversity()
    test_bare_numeric_rent_with_no_dollar_sign()
    test_vacant_row_skipped()
    test_total_row_skipped()
    test_blank_tenant_row_skipped()
    test_missing_tenant_and_rent_columns_raises()
    test_missing_optional_column_does_not_block_import()
    test_unrecognized_extra_columns_ignored()
    test_blank_rows_in_file_are_skipped_entirely()
    test_no_base_address_and_no_unit_column_leaves_address_unset()
    test_empty_csv_raises()
    test_empty_xlsx_raises()
    test_row_numbers_reflect_actual_file_position()
    test_specific_date_column_not_misattributed_to_rent_amount()
    print("\nAll rent roll import tests passed.")
