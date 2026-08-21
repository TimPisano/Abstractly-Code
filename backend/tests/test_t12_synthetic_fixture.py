"""
Tests the T12 reconciliation against a SYNTHETIC T12 fixture --
synthetic_t12_operating_statement.csv, in this directory -- combined
with synthetic_yardi_rent_roll.csv (the PMS import fixture from the
same batch of work). Both are clearly labeled as fabricated test
fixtures in their own first row, not real vendor/operator files -- see
DECISIONS.md's "Rent-roll-vs-T12 cross-check" entry.

Deliberately built to represent the SAME property (Riverside Commons
Shopping Center) as the Yardi rent roll fixture, so this test exercises
the real end-to-end story this feature exists for: import a rent roll
through one real route, upload a T12 through another real route, and
confirm the cross-check correctly compares the two. The T12's actual
rental income ($187,900) is a small, realistic amount above the rent
roll's own annualized total ($179,400 -- 3 real tenants from the Yardi
fixture, Market Rent correctly excluded) -- close enough that it must
NOT be flagged, proving the tolerance logic holds on believable,
non-hand-picked numbers, not just a clean synthetic example.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.rent_roll_import import parse_csv_rent_roll
from app.t12_import import parse_csv_t12
from app.portfolio import compute_t12_reconciliation

FIXTURES_DIR = os.path.dirname(__file__)


def _read(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


def _leases_from_rent_roll():
    parsed = parse_csv_rent_roll(
        _read("synthetic_yardi_rent_roll.csv"),
        "synthetic_yardi_rent_roll.csv",
        base_property_address="Riverside Commons Shopping Center",
    )
    # Mirrors what database.insert_lease/get_effective_lease actually
    # store -- id, filename, extracted_fields -- without touching a
    # real database, since compute_t12_reconciliation only needs those.
    return [
        {"id": i, "filename": "synthetic_yardi_rent_roll.csv", "extracted_fields": lease_data["extracted_fields"]}
        for i, lease_data in enumerate(parsed["leases"])
    ]


def test_synthetic_t12_extracts_actual_income_not_gross_potential():
    result = parse_csv_t12(_read("synthetic_t12_operating_statement.csv"), "synthetic_t12_operating_statement.csv")
    assert result["annual_rental_income"] == 187900.0, result  # not 198300 (Gross Potential Rent)
    assert result["source"]["quote"] == "Total Rental Income"
    print("✓ test_synthetic_t12_extracts_actual_income_not_gross_potential: PASS")


def test_synthetic_t12_vs_matching_rent_roll_small_realistic_gap_not_flagged():
    leases = _leases_from_rent_roll()
    t12 = parse_csv_t12(_read("synthetic_t12_operating_statement.csv"), "synthetic_t12_operating_statement.csv")

    result = compute_t12_reconciliation(leases, "Riverside Commons Shopping Center", t12["annual_rental_income"])
    assert result["rent_roll_annual_rent"] == 179400.0, result  # (3200+4950+6800)*12
    assert result["t12_annual_rental_income"] == 187900.0
    assert result["direction"] == "t12_higher"
    assert result["flagged"] is False  # 4.7% gap -- real, but under the 5% bar
    print("✓ test_synthetic_t12_vs_matching_rent_roll_small_realistic_gap_not_flagged: PASS")


def test_synthetic_t12_vs_rent_roll_large_gap_is_flagged():
    """Same rent roll, but a T12 reporting a genuinely large shortfall (e.g. the export is stale, or several units went vacant since it was pulled) -- must be flagged."""
    leases = _leases_from_rent_roll()
    result = compute_t12_reconciliation(leases, "Riverside Commons Shopping Center", 130000.0)
    assert result["direction"] == "rent_roll_higher"
    assert result["flagged"] is True
    print("✓ test_synthetic_t12_vs_rent_roll_large_gap_is_flagged: PASS")


if __name__ == "__main__":
    test_synthetic_t12_extracts_actual_income_not_gross_potential()
    test_synthetic_t12_vs_matching_rent_roll_small_realistic_gap_not_flagged()
    test_synthetic_t12_vs_rent_roll_large_gap_is_flagged()
    print("\nAll T12 synthetic fixture tests passed.")
