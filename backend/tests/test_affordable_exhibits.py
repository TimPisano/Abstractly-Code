"""
Tests for app/affordable/exhibits.py (PBV Exhibit A reader) and the router
helpers that let a partly scanned contract through (route.fill_low_text_pages,
route.merge_reads). No AI calls. Exhibit text below is fictional but laid out
the way PHAs write these exhibits, including the OCR noise seen on real ones.

Run: python backend/tests/test_affordable_exhibits.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.affordable.exhibits import read_exhibit_a, _rent_from_line
from app.affordable.route import merge_reads

EXHIBIT = """EXHIBIT A
Project Name: Maple Ridge Commons
Address: 100 Example Way, Springfield, ZZ 00000
Total Number of Project Based Voucher (PBV) Units in Project Covered by HAP Contract: 10
Total Number Units in the Project: 40
Description and Quantity in Project:
Total units: 20 1-bedroom, 16 2-bedroom and 4 3-bedroom
Bedroom/Bathroom  AMI  Quantity  Unit #s and Accessible
One Bedroom/  30%  4  101, 102, 103, 104
One Bathroom
50%  2  105, 106
Two Bedroom/  30%  4  201 & 202
Total  10 Units
Initial Rent to Owner for Contract Units (net of utility allowance):
Contract rent for 1br apartment: $1,200 = ($1,260 payment std - $60 UA)
Contract rent for 2br apartment: $1,450 -- ($1,600 payment std - $80 UA)
"""
PART1_TOC = "EXHIBIT A: TOTAL NUMBER OF UNITS IN PROJECT COVERED BY THIS HAP CONTRACT; INITIAL RENT TO OWNER"


def test_reads_the_required_exhibit_a_items():
    f = read_exhibit_a([{"page": 1, "text": PART1_TOC}, {"page": 9, "text": EXHIBIT}])
    got = {k: v["value"] for k, v in f.items()}
    assert got["project_name"] == "Maple Ridge Commons"
    assert got["property_address"] == "100 Example Way, Springfield, ZZ 00000"
    assert (got["contract_units"], got["total_units"]) == ("10", "40")
    assert (got["units_1br"], got["units_2br"], got["units_3br"]) == ("20", "16", "4")
    assert (got["contract_units_1br"], got["contract_units_2br"]) == ("6", "4")   # 4 + 2 continuation row
    assert got["ami_limit_pct"] == "50%"
    assert got["contract_rent_1br"] == "$1,200.00"
    assert all(v["source"]["page"] == 9 for v in f.values())


def test_a_rent_line_that_doesnt_add_up_is_flagged_not_changed():
    f = read_exhibit_a([{"page": 9, "text": EXHIBIT}])
    rent = f["contract_rent_2br"]
    assert rent["value"] == "$1,450.00"
    assert rent["confidence"] == "low"
    assert "$1,520" in rent["check_note"] and "Verify with your PHA" in rent["check_note"]
    assert f["contract_rent_1br"]["confidence"] == "medium"


def test_rent_lines_are_told_apart_by_their_labels():
    r = _rent_from_line("1br $2,002 - $65 (Utility Allowance) = $1,937 Contract Rent")
    assert (r["rent"], r["allowance"], r["standard"], r["adds_up"]) == (1937, 65, 2002, True)
    assert _rent_from_line("Contract rent for 1br: $900")["rent"] == 900
    assert _rent_from_line("1br $900 or $950") is None


def test_a_garbled_size_row_makes_the_table_untrusted():
    """Regression: an OCR-garbled '30%' on the Three Bedroom row put its rows under 2BR (6 instead of 3)."""
    text = EXHIBIT.replace("Two Bedroom/  30%  4  201 & 202",
                           "Two Bedroom/  30%  2  201 & 202\n40%  1  203\nThree Bedroom/  3Oo/o  2  301\n45%  1  302")
    f = read_exhibit_a([{"page": 9, "text": text}])
    assert "contract_units_2br" not in f and "contract_units_1br" not in f and "ami_limit_pct" not in f
    assert f["contract_units"]["value"] == "10"


def test_no_exhibit_no_fields():
    assert read_exhibit_a([{"page": 1, "text": PART1_TOC}]) == {}


def _e(value, conf="medium", page=1):
    return {"value": value, "source": {"page": page, "quote": value}, "confidence": conf, "method": "ai"}


def test_merge_fills_gaps_and_flags_disagreements_without_changing_values():
    ai = {"owner_name": _e("Maple Ridge LP"), "contract_rent_1br": _e("$1,250")}
    form = {"owner_name": _e("Maple Ridge LP"), "contract_rent_1br": _e("$1,200", page=9), "total_units": _e("40")}
    merged = merge_reads(ai, form)
    assert merged["total_units"]["value"] == "40"
    assert merged["contract_rent_1br"]["value"] == "$1,250"
    assert merged["contract_rent_1br"]["confidence"] == "low"
    assert "$1,200" in merged["contract_rent_1br"]["check_note"]
    assert merged["owner_name"]["confidence"] == "medium"
    assert ai["contract_rent_1br"]["confidence"] == "medium"   # inputs untouched


if __name__ == "__main__":
    test_reads_the_required_exhibit_a_items()
    test_a_rent_line_that_doesnt_add_up_is_flagged_not_changed()
    test_rent_lines_are_told_apart_by_their_labels()
    test_a_garbled_size_row_makes_the_table_untrusted()
    test_no_exhibit_no_fields()
    test_merge_fills_gaps_and_flags_disagreements_without_changing_values()
    print("\nAll Exhibit A and merge tests passed.")
