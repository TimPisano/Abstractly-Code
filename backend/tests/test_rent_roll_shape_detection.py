"""
Tests for field_extractor.looks_like_rent_roll_table -- the guard that
stops a portfolio rent roll / unit ledger from being run through the
single-lease extraction path, where it doesn't fail cleanly but
confidently returns WRONG values (one unit's rent presented as "the"
lease's rent, a column header word as the tenant name, a portfolio-
wide aggregate as a per-lease figure). See DECISIONS.md for the real,
live example that prompted this (a 32-page rent-roll PDF uploaded
through POST /leases produced a "lease" with 4 high-confidence fields,
all of them wrong).

Unit-level tests here work directly on the {"page": N, "text": "..."}
shape FieldExtractor consumes, so no real PDF file is needed to prove
the threshold logic itself. Live, real-file, real-HTTP-route coverage
(confirming the actual upload routes reject a real rent-roll PDF with
a clean 422 and persist nothing) lives in test_security_hardening.py,
using the tests/synthetic_rent_roll_report.pdf fixture.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.field_extractor import looks_like_rent_roll_table


def _page(text, page=1):
    return {"page": page, "text": text}


def _rent_roll_row(i):
    return (
        f"10{i%9}-{i%20:02d}  Tenant {i} LLC  {1000+i*17}  "
        f"20{18+i%8}-0{1+i%9}-{10+i%18}  20{25+i%8}-0{1+i%9}-{10+i%18}  "
        f"${2000+i*23.5:,.2f}  ${(2000+i*23.5)*12:,.2f}  3.0%  Active"
    )


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    # ---- Real single-lease documents must never trigger this ----
    real_lease_text = """
        COMMERCIAL LEASE AGREEMENT
        This Lease is entered into by and between Meridian Properties Group, LLC ("Landlord"),
        and Blue Sky Coffee Roasters, Inc. ("Tenant"). The Premises are located at 4200 Commerce
        Parkway, Suite 110, Austin, Texas 78701, consisting of approximately 2,400 square feet.
        TERM. The term of this Lease shall commence on April 1, 2025 and shall expire on March 31, 2030.
        BASE RENT. Tenant shall pay to Landlord as base rent the sum of $6,250.00 per month.
        RENT ESCALATION. Base Rent shall increase by 3% on each anniversary thereafter.
        SECURITY DEPOSIT. Tenant shall deposit with Landlord the sum of $12,500.00.
        CAM. Tenant shall pay its proportionate share of Common Area Maintenance charges of $875.00 per month.
        INSURANCE. Tenant shall maintain commercial general liability insurance of $2,000,000 per occurrence.
    """
    pages = [_page(real_lease_text)]
    check(
        "a real, single-page prose lease is NOT flagged as a rent roll",
        looks_like_rent_roll_table(pages) is False,
        "false positive would block every normal upload",
    )

    # A longer, more financially complex real lease (a 20-year escalation
    # schedule) -- still nowhere near rent-roll density, must stay clear.
    escalation_lines = "\n".join(f"Year {y}: ${5000 + y*150}.00 per month" for y in range(1, 21))
    complex_lease_text = real_lease_text + "\nESCALATION SCHEDULE.\n" + escalation_lines
    check(
        "a real lease with a full 20-year escalation schedule is still NOT flagged",
        looks_like_rent_roll_table([_page(complex_lease_text)]) is False,
        "a legitimately complex lease must not false-positive just for having many rent figures",
    )

    check(
        "an empty document is not flagged",
        looks_like_rent_roll_table([_page("")]) is False,
    )

    # ---- A genuine rent-roll-shaped table must be flagged, even a small one ----
    small_table_text = "Unit  Tenant  Sq Ft  Lease Start  Lease End  Monthly Rent\n" + "\n".join(
        _rent_roll_row(i) for i in range(12)
    )
    check(
        "a small (12-row) rent-roll-shaped table IS flagged",
        looks_like_rent_roll_table([_page(small_table_text)]) is True,
        "the date/currency density from even a modest table should already clear the threshold",
    )

    large_table_text = "Unit  Tenant  Sq Ft  Lease Start  Lease End  Monthly Rent\n" + "\n".join(
        _rent_roll_row(i) for i in range(120)
    )
    check(
        "a large (120-row) rent-roll-shaped table IS flagged",
        looks_like_rent_roll_table([_page(large_table_text)]) is True,
    )

    # A table split across multiple pages (like the real 32-page PDF this
    # was found on) must still be caught -- the check looks at the whole
    # document's concatenated text, not one page in isolation.
    rows = [_rent_roll_row(i) for i in range(60)]
    multi_page = [_page("\n".join(rows[:20]), page=1), _page("\n".join(rows[20:40]), page=2), _page("\n".join(rows[40:]), page=3)]
    check(
        "a rent-roll table split across multiple pages IS flagged",
        looks_like_rent_roll_table(multi_page) is True,
    )

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    print("=" * 70)

    failed = [c for c in checks if not c[1]]
    if failed:
        print("\nFAILED:")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")

    return len(failed) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
