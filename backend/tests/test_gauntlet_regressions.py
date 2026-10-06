"""
Regression tests for bugs found by the overnight reliability gauntlet
(backend/tools/gauntlet/, branch qa/overnight-gauntlet). One test (or a
small group) per fix; each was confirmed failing before its fix landed.

Pure-function tests where possible (the detectors in deal_mismatch.py take
plain lease dicts), so these run in milliseconds and need no fixtures.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.portfolio import FIELD_NAMES, _normalize_address, _normalize_building_address
from app import deal_mismatch as dm
from datetime import date

TODAY = date(2026, 10, 5)


def _fields(**overrides):
    out = {}
    for name in FIELD_NAMES:
        v = overrides.get(name)
        out[name] = ({"value": v, "source": {"page": 1, "quote": str(v)}, "confidence": "high"} if v is not None
                     else {"value": None, "source": None, "confidence": None})
    return out


_ids = iter(range(1, 10_000))


def _rr(**f):
    return {"id": next(_ids), "filename": "rent_roll.csv", "extracted_fields": _fields(**f)}


def _doc(**f):
    return {"id": next(_ids), "filename": "lease.pdf", "extracted_fields": _fields(**f)}


def _types(rows):
    return sorted(r["discrepancy_type"] for r in rows)


# ---------------------------------------------------------------- unit matching
def test_same_unit_matches_across_designator_wording():
    """
    The rent-roll importer turns a bare "101" into "<typed address>, Suite 101";
    a multifamily lease says "Apt 101" (or "Unit 101", "#101") with the city
    after it. Same unit -- before the fix every such pair was reported as a
    false unit_no_lease + lease_no_unit and every real check on it was lost.
    """
    rr = "1450 Cedar Bend Dr, Austin, TX 78745, Suite 101"
    for lease in ("1450 Cedar Bend Dr, Apt 101, Austin, TX 78745",
                  "1450 Cedar Bend Dr, Unit 101, Austin, TX 78745",
                  "1450 Cedar Bend Dr #101, Austin, TX 78745",
                  "1450 Cedar Bend Dr, Apartment No. 101, Austin, TX 78745",
                  "1450 Cedar Bend Dr, Apt #101, Austin, TX 78745",
                  "1450 Cedar Bend Drive, Austin, TX 78745, Suite 101",
                  "1450 Cedar Bend Dr, Austin, TX 78745, Suite 0101"):
        assert _normalize_address(rr) == _normalize_address(lease), (lease, _normalize_address(rr), _normalize_address(lease))
    print("✓ test_same_unit_matches_across_designator_wording: PASS")


def test_different_units_and_buildings_still_do_not_match():
    a = "1450 Cedar Bend Dr, Austin, TX 78745, Suite 101"
    for other in ("1450 Cedar Bend Dr, Austin, TX 78745, Suite 102",
                  "1450 Cedar Bend Dr, Austin, TX 78745, Suite 1010",
                  "1452 Cedar Bend Dr, Austin, TX 78745, Suite 101",
                  "1450 Cedar Bend Dr, Austin, TX 78745",
                  "1450 Cedar Bend Ct, Austin, TX 78745, Suite 101"):
        assert _normalize_address(a) != _normalize_address(other), other
    # "Unity" is a street name, not "Unit y".
    assert _normalize_building_address("12 Unity Ave, Suite 3") == _normalize_building_address("12 Unity Ave, Suite 4")
    assert _normalize_building_address("12 Unity Ave") != _normalize_building_address("12 Ave")
    print("✓ test_different_units_and_buildings_still_do_not_match: PASS")


def test_report_pairs_apt_lease_with_suite_rent_roll_row():
    rr = _rr(tenant="Greta Fairbanks", rent_amount="$1,600.00", property_address="1450 Cedar Bend Dr, Austin, TX 78745, Suite 101",
             lease_start_date="04/01/2026", lease_end_date="03/31/2027")
    doc = _doc(tenant="Greta Fairbanks", rent_amount="$1,450.00", property_address="1450 Cedar Bend Dr, Apt 101, Austin, TX 78745",
               lease_start_date="April 1, 2026", lease_end_date="March 31, 2027")
    rows = []
    for det in dm._DETECTORS:
        rows += det([rr, doc], TODAY) if det in dm._DATE_AWARE_DETECTORS else det([rr, doc])
    assert _types(rows) == ["rent_mismatch"], _types(rows)
    print("✓ test_report_pairs_apt_lease_with_suite_rent_roll_row: PASS")


def test_typed_long_street_suffix_matches_abbreviated_lease_building():
    """Uploader typed "Drive", the leases say "Dr": same building for report scoping."""
    assert _normalize_building_address("1450 Cedar Bend Drive, Austin, TX 78745") == \
        _normalize_building_address("1450 Cedar Bend Dr., Apt 101, Austin, TX 78745")
    print("✓ test_typed_long_street_suffix_matches_abbreviated_lease_building: PASS")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nAll gauntlet regression tests passed.")
