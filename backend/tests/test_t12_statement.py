"""
Tests for t12_statement.py multi-line-item T12 parsing.
"""

import io
import pytest
from openpyxl import Workbook

from app.t12_statement import (
    parse_csv_t12_statement, parse_xlsx_t12_statement, parse_pdf_t12_statement,
)
from app.t12_import import T12ImportError


def _csv_bytes(lines):
    """Helper: create CSV bytes from a list of lines."""
    text = "\n".join(lines)
    return text.encode("utf-8")


def _xlsx_bytes(rows):
    """Helper: create .xlsx bytes from a list of rows."""
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def test_t12_statement_clean_csv():
    """Clean CSV: all 6 categories, all 12 months present, Total column."""
    csv_data = _csv_bytes([
        "Month,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Total",
        "Gross Potential Rent,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,120000",
        "Rental Income,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,114000",
        "Concessions,500,500,500,500,500,500,500,500,500,500,500,500,6000",
        "Vacancy Loss,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,12000",
        "Bad Debt,200,200,200,200,200,200,200,200,200,200,200,200,2400",
        "Other Income,100,100,100,100,100,100,100,100,100,100,100,100,1200",
    ])
    result = parse_csv_t12_statement(csv_data, "test.csv")
    assert result["gross_potential_rent"]["annual"] == 120000
    assert result["rental_income_collected"]["annual"] == 114000
    assert result["concessions"]["annual"] == 6000
    assert result["vacancy_loss"]["annual"] == 12000
    assert result["bad_debt"]["annual"] == 2400
    assert result["other_income"]["annual"] == 1200
    assert result["gross_potential_rent"]["monthly"]["jan"] == 10000
    assert result["rental_income_collected"]["monthly"]["dec"] == 9500


def test_t12_statement_months_only():
    """No Total column, all 12 months (sum path)."""
    csv_data = _csv_bytes([
        "Month,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec",
        "Gross Potential Rent,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000",
        "Rental Income,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500",
    ])
    result = parse_csv_t12_statement(csv_data, "test.csv")
    assert result["gross_potential_rent"]["annual"] == 120000
    assert result["rental_income_collected"]["annual"] == 114000


def test_t12_statement_partial_categories():
    """Some categories present, some missing → None per missing category."""
    csv_data = _csv_bytes([
        "Month,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Total",
        "Gross Potential Rent,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,120000",
        "Rental Income,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,114000",
    ])
    result = parse_csv_t12_statement(csv_data, "test.csv")
    assert result["gross_potential_rent"]["annual"] == 120000
    assert result["rental_income_collected"]["annual"] == 114000
    assert result["concessions"] is None
    assert result["vacancy_loss"] is None
    assert result["bad_debt"] is None
    assert result["other_income"] is None


def test_t12_statement_renamed_aliases():
    """Alternate real-world labels per category."""
    csv_data = _csv_bytes([
        "Month,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Total",
        "Potential Rent,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,120000",
        "Rent Revenue,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,114000",
        "Rent Concessions,500,500,500,500,500,500,500,500,500,500,500,500,6000",
        "Loss to Vacancy,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,12000",
        "Uncollectible Rent,200,200,200,200,200,200,200,200,200,200,200,200,2400",
        "Miscellaneous Income,100,100,100,100,100,100,100,100,100,100,100,100,1200",
    ])
    result = parse_csv_t12_statement(csv_data, "test.csv")
    assert result["gross_potential_rent"]["annual"] == 120000
    assert result["rental_income_collected"]["annual"] == 114000
    assert result["concessions"]["annual"] == 6000
    assert result["vacancy_loss"]["annual"] == 12000
    assert result["bad_debt"]["annual"] == 2400
    assert result["other_income"]["annual"] == 1200


def test_t12_statement_with_subtotals():
    """Extra subtotal/blank rows interspersed, should be ignored."""
    csv_data = _csv_bytes([
        "Month,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Total",
        "Gross Potential Rent,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,120000",
        "",
        "Total Income,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,114000",
        "Rental Income,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,114000",
        "Concessions,500,500,500,500,500,500,500,500,500,500,500,500,6000",
        "",
        "Vacancy Loss,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,12000",
    ])
    result = parse_csv_t12_statement(csv_data, "test.csv")
    assert result["gross_potential_rent"]["annual"] == 120000
    assert result["rental_income_collected"]["annual"] == 114000
    assert result["concessions"]["annual"] == 6000
    assert result["vacancy_loss"]["annual"] == 12000


def test_t12_statement_decorative_header():
    """Decorative header block before the real header row."""
    csv_data = _csv_bytes([
        "PROPERTY OPERATING STATEMENT",
        "Quarter Ending December 31, 2023",
        "",
        "Month,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Total",
        "Gross Potential Rent,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,10000,120000",
        "Rental Income,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,9500,114000",
    ])
    result = parse_csv_t12_statement(csv_data, "test.csv")
    assert result["gross_potential_rent"]["annual"] == 120000
    assert result["rental_income_collected"]["annual"] == 114000


def test_t12_statement_xlsx():
    """Test .xlsx parsing with the same clean data."""
    rows = [
        ["Month", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Total"],
        ["Gross Potential Rent", 10000, 10000, 10000, 10000, 10000, 10000, 10000, 10000, 10000, 10000, 10000, 10000, 120000],
        ["Rental Income", 9500, 9500, 9500, 9500, 9500, 9500, 9500, 9500, 9500, 9500, 9500, 9500, 114000],
        ["Concessions", 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 6000],
        ["Vacancy Loss", 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 12000],
    ]
    xlsx_data = _xlsx_bytes(rows)
    result = parse_xlsx_t12_statement(xlsx_data, "test.xlsx")
    assert result["gross_potential_rent"]["annual"] == 120000
    assert result["rental_income_collected"]["annual"] == 114000
    assert result["concessions"]["annual"] == 6000
    assert result["vacancy_loss"]["annual"] == 12000


def test_t12_statement_empty_csv():
    """Empty CSV raises T12ImportError."""
    csv_data = _csv_bytes([])
    with pytest.raises(T12ImportError):
        parse_csv_t12_statement(csv_data, "empty.csv")


def test_t12_statement_no_valid_headers():
    """File with no recognizable month columns raises T12ImportError."""
    csv_data = _csv_bytes([
        "Prop Name,Value",
        "Rent,10000",
    ])
    with pytest.raises(T12ImportError):
        parse_csv_t12_statement(csv_data, "test.csv")
