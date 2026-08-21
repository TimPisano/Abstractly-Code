"""
Tests for app/t12_import.py -- the T12 (trailing 12-month operating
statement) parser. Deliberately exercises the two things that matter
most for correctness here: never mistaking "Gross Potential Rent" (the
theoretical, vacancy-inclusive maximum) for actual collected rent, and
computing an annual figure correctly whether the file has an explicit
Total column or only 12 monthly columns to sum.
"""

import csv
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openpyxl import Workbook

from app.t12_import import T12ImportError, parse_csv_t12, parse_xlsx_t12

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


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


def test_happy_path_with_total_column_prefers_actual_over_potential():
    """The core design goal: with BOTH a Gross Potential Rent line and a Total Rental Income line, the actual (lower) figure must win, not the theoretical (higher) one."""
    csv_bytes = _csv_bytes([
        ["Line Item", "Jan", "Feb", "Total"],
        ["Gross Potential Rent", "20000", "20000", "240000"],
        ["Vacancy Loss", "-2000", "-2000", "-24000"],
        ["Total Rental Income", "18000", "18000", "216000"],
        ["Net Operating Income", "13000", "13000", "156000"],
    ])
    result = parse_csv_t12(csv_bytes, "t12.csv")
    assert result["annual_rental_income"] == 216000.0, result
    assert result["source"]["quote"] == "Total Rental Income"
    print("✓ test_happy_path_with_total_column_prefers_actual_over_potential: PASS")


def test_no_total_column_sums_all_12_months():
    csv_bytes = _csv_bytes([
        ["Line Item"] + _MONTHS,
        ["Rental Income"] + [str(1000 + i * 10) for i in range(12)],
    ])
    result = parse_csv_t12(csv_bytes, "t12.csv")
    assert result["annual_rental_income"] == float(sum(1000 + i * 10 for i in range(12))), result
    print("✓ test_no_total_column_sums_all_12_months: PASS")


def test_partial_months_with_no_total_column_raises():
    """Fewer than all 12 month columns AND no Total column means there's genuinely no reliable way to compute an annual figure -- must fail honestly, not guess by scaling up a partial sum."""
    csv_bytes = _csv_bytes([
        ["Line Item", "Jan", "Feb", "Mar"],
        ["Rental Income", "1000", "1000", "1000"],
    ])
    try:
        parse_csv_t12(csv_bytes, "t12.csv")
        assert False, "should have raised -- only 3 of 12 months, no Total column"
    except T12ImportError:
        pass
    print("✓ test_partial_months_with_no_total_column_raises: PASS")


def test_potential_rent_only_raises_rather_than_being_used():
    """A file with ONLY a Gross Potential Rent line (no actual-income line at all) must fail honestly, not silently use the potential figure as if it were actual."""
    csv_bytes = _csv_bytes([
        ["Line Item", "Total"],
        ["Gross Potential Rent", "240000"],
    ])
    try:
        parse_csv_t12(csv_bytes, "t12.csv")
        assert False, "should have raised"
    except T12ImportError as e:
        assert "actual rental income" in str(e).lower() or "gross potential" in str(e).lower()
    print("✓ test_potential_rent_only_raises_rather_than_being_used: PASS")


def test_market_rent_income_also_excluded():
    """Same principle as Gross Potential Rent, different common phrasing -- "Market Rent Income" is also theoretical, not actual."""
    csv_bytes = _csv_bytes([
        ["Line Item", "Total"],
        ["Market Rent Income", "240000"],
        ["Total Rental Income", "200000"],
    ])
    result = parse_csv_t12(csv_bytes, "t12.csv")
    assert result["annual_rental_income"] == 200000.0, result
    print("✓ test_market_rent_income_also_excluded: PASS")


def test_scheduled_gross_income_excluded_but_scheduled_rent_income_allowed():
    """
    "Scheduled" is genuinely ambiguous across the industry -- on a T12
    specifically, "Scheduled Gross Income" commonly means the pre-
    vacancy potential figure (excluded), while "Scheduled Rent Income"
    is an unambiguous actual-income phrasing (allow-listed as its own
    exact alias). Both behaviors matter, not just one.
    """
    csv_bytes = _csv_bytes([
        ["Line Item", "Total"],
        ["Scheduled Gross Income", "240000"],
    ])
    try:
        parse_csv_t12(csv_bytes, "t12.csv")
        assert False, "should have raised -- Scheduled Gross Income is a potential-income phrasing"
    except T12ImportError:
        pass

    csv_bytes2 = _csv_bytes([
        ["Line Item", "Total"],
        ["Scheduled Rent Income", "200000"],
    ])
    result = parse_csv_t12(csv_bytes2, "t12.csv")
    assert result["annual_rental_income"] == 200000.0, result
    print("✓ test_scheduled_gross_income_excluded_but_scheduled_rent_income_allowed: PASS")


def test_header_row_auto_detection_skips_decorative_rows():
    """Same real-world pattern as rent rolls -- a T12 export routinely opens with a property name/title/date-range block before the real header row."""
    csv_bytes = _csv_bytes([
        ["Riverside Commons Shopping Center"],
        ["Operating Statement"],
        ["Trailing 12 Months Ending 07/31/2026"],
        [],
        ["Line Item", "Jan", "Feb", "Total"],
        ["Total Rental Income", "18000", "18000", "216000"],
    ])
    result = parse_csv_t12(csv_bytes, "t12.csv")
    assert result["annual_rental_income"] == 216000.0
    # True file row 6, not shifted by the dropped blank spacer row (file row 4).
    assert result["source"]["row"] == 6, result["source"]
    print("✓ test_header_row_auto_detection_skips_decorative_rows: PASS")


def test_no_header_row_found_raises_clear_error():
    csv_bytes = _csv_bytes([["Notes"], ["Nothing recognizable here"]])
    try:
        parse_csv_t12(csv_bytes, "not_a_t12.csv")
        assert False, "should have raised"
    except T12ImportError:
        pass
    print("✓ test_no_header_row_found_raises_clear_error: PASS")


def test_empty_csv_raises():
    try:
        parse_csv_t12(b"", "empty.csv")
        assert False, "should have raised"
    except T12ImportError:
        pass
    print("✓ test_empty_csv_raises: PASS")


def test_xlsx_happy_path():
    xlsx_bytes = _xlsx_bytes([
        ["Meridian Business Park"],
        ["Operating Statement"],
        ["Line Item", "Jan", "Feb", "Total"],
        ["Gross Potential Rent", 14400, 14400, 172800],
        ["Total Rental Income", 12800, 12800, 153600],
    ])
    result = parse_xlsx_t12(xlsx_bytes, "t12.xlsx")
    assert result["annual_rental_income"] == 153600.0, result
    assert result["source"]["row"] == 5
    print("✓ test_xlsx_happy_path: PASS")


def test_first_matching_row_used_when_multiple_actual_income_rows_exist():
    """If a file somehow has more than one row that looks like actual rental income, the first one (top-down) wins -- deterministic, not ambiguous."""
    csv_bytes = _csv_bytes([
        ["Line Item", "Total"],
        ["Total Rental Income", "200000"],
        ["Rental Income", "199000"],
    ])
    result = parse_csv_t12(csv_bytes, "t12.csv")
    assert result["annual_rental_income"] == 200000.0, result
    print("✓ test_first_matching_row_used_when_multiple_actual_income_rows_exist: PASS")


def test_blank_label_rows_are_skipped_not_errors():
    """A T12 often has blank-labeled subtotal/spacer rows between sections -- must not crash or be mistaken for anything."""
    csv_bytes = _csv_bytes([
        ["Line Item", "Total"],
        ["", "0"],
        ["Total Rental Income", "200000"],
    ])
    result = parse_csv_t12(csv_bytes, "t12.csv")
    assert result["annual_rental_income"] == 200000.0, result
    print("✓ test_blank_label_rows_are_skipped_not_errors: PASS")


if __name__ == "__main__":
    test_happy_path_with_total_column_prefers_actual_over_potential()
    test_no_total_column_sums_all_12_months()
    test_partial_months_with_no_total_column_raises()
    test_potential_rent_only_raises_rather_than_being_used()
    test_market_rent_income_also_excluded()
    test_scheduled_gross_income_excluded_but_scheduled_rent_income_allowed()
    test_header_row_auto_detection_skips_decorative_rows()
    test_no_header_row_found_raises_clear_error()
    test_empty_csv_raises()
    test_xlsx_happy_path()
    test_first_matching_row_used_when_multiple_actual_income_rows_exist()
    test_blank_label_rows_are_skipped_not_errors()
    print("\nAll T12 import tests passed.")
