"""
Tests for app/extraction_scoring.py -- the pure scoring/aggregation
logic behind the Phase 4 training loop. No API, no DB.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import extraction_scoring as sc


def _entry(value, confidence="high"):
    return {"value": value, "confidence": confidence, "source": None}


# ----------------------------------------------------------------------
# values_match
# ----------------------------------------------------------------------

def test_values_match_field_aware():
    assert sc.values_match("rent_amount", "$6,250.00", "$6,250") is True
    assert sc.values_match("rent_amount", "$6,300.00", "$6,250.00") is False
    assert sc.values_match("lease_start_date", "April 1, 2025", "April 1, 2025") is True
    assert sc.values_match("lease_start_date", "4/1/2025", "April 1, 2025") is True
    assert sc.values_match("lease_end_date", "03/31/2030", "March 31, 2030") is True
    assert sc.values_match("lease_end_date", "March 31, 2031", "March 31, 2030") is False
    assert sc.values_match("square_footage", "2,400 sq ft", "2400 square feet") is True
    assert sc.values_match("tenant", "Blue Sky Coffee Roasters", "Blue Sky Coffee Roasters, Inc.") is True
    assert sc.values_match("tenant", "Acme Corp", "Beta LLC") is False
    assert sc.values_match("rent_escalation", "3% annually", "3.0% each year") is True
    # a year-by-year dollar schedule is an accepted alternative to a "X% annually" rule
    assert sc.values_match("rent_escalation", "Year 1: $6,250.00; Year 2: $6,375.00; Year 3: $6,502.50", "2% annually") is True
    assert sc.values_match("rent_escalation", "Year 1: $6,250.00; Year 2: $9,999.00", "2% annually") is False
    assert sc.values_match("renewal_options", "2 option(s) of 5 year(s)", "2 options / 5 yrs") is True
    assert sc.values_match("permitted_use", "a retail coffee shop and roastery", "retail coffee shop") is True
    assert sc.values_match("cam_charges", None, None) is True
    assert sc.values_match("cam_charges", "$350.00", None) is False
    assert sc.values_match("cam_charges", None, "$350.00") is False
    print("✓ test_values_match_field_aware: PASS")


# ----------------------------------------------------------------------
# score_field kinds
# ----------------------------------------------------------------------

def test_score_field_kinds():
    assert sc.score_field("tenant", _entry("Acme, Inc."), "Acme")["kind"] == "correct_found"
    assert sc.score_field("cam_charges", _entry(None, None), None)["kind"] == "correct_absent"
    assert sc.score_field("rent_amount", _entry("$9,999.00"), "$6,250.00")["kind"] == "wrong"
    assert sc.score_field("rent_amount", _entry(None, None), "$6,250.00")["kind"] == "missed"
    assert sc.score_field("exclusivity_clause", _entry("exclusive use"), None)["kind"] == "spurious"

    wrong = sc.score_field("rent_amount", _entry("$9,999.00", "high"), "$6,250.00")
    assert wrong["asserted_wrong"] is True and wrong["confidence"] == "high"
    missed = sc.score_field("rent_amount", _entry(None, None), "$6,250.00")
    assert missed["asserted_wrong"] is False, "a miss is not an asserted-wrong -- the model didn't claim anything"
    print("✓ test_score_field_kinds: PASS")


# ----------------------------------------------------------------------
# aggregate: danger signals + calibration
# ----------------------------------------------------------------------

def _doc(fields_gt_pairs, fmt="pdf", doc_id="d1"):
    extracted = {f: e for f, (e, _gt) in fields_gt_pairs.items()}
    gt = {f: g for f, (_e, g) in fields_gt_pairs.items()}
    # fill the rest as not-found/not-expected
    for f in sc.ALL_FIELDS:
        extracted.setdefault(f, {"value": None, "confidence": None})
        gt.setdefault(f, None)
    return sc.score_document(extracted, gt, doc_meta={"id": doc_id, "format": fmt})


def test_aggregate_flags_high_confidence_wrong():
    docs = [
        _doc({"tenant": (_entry("Acme", "high"), "Acme"),
              "rent_amount": (_entry("$9,999.00", "high"), "$6,250.00")}, doc_id="bad1"),
        _doc({"tenant": (_entry("Beta", "high"), "Beta"),
              "rent_amount": (_entry("$5,000.00", "high"), "$5,000.00")}, doc_id="ok1"),
    ]
    report = sc.aggregate(docs)
    assert report["high_conf_wrong_count"] == 1
    assert report["high_conf_wrong"][0]["doc"] == "bad1"
    assert report["high_conf_wrong"][0]["field"] == "rent_amount"
    print("✓ test_aggregate_flags_high_confidence_wrong: PASS")


def test_aggregate_calibration_gap():
    # high-confidence values are mostly right; low-confidence mostly wrong -> positive gap
    docs = []
    for i in range(5):
        docs.append(_doc({"tenant": (_entry("Acme", "high"), "Acme"),
                          "landlord": (_entry("Wrongco", "low"), "Realco")}, doc_id=f"d{i}"))
    report = sc.aggregate(docs)
    cal = report["calibration"]
    assert cal["p_correct_given_high"] == 1.0
    assert cal["p_correct_given_low"] == 0.0
    assert cal["calibration_gap"] == 1.0
    print("✓ test_aggregate_calibration_gap: PASS")


def test_aggregate_identifies_weak_fields_and_formats():
    docs = [
        _doc({"tenant": (_entry("Acme"), "Acme"), "cam_charges": (_entry("$1.00"), "$350.00")}, fmt="pdf", doc_id="p1"),
        _doc({"tenant": (_entry("Beta"), "Beta"), "cam_charges": (_entry("$2.00"), "$350.00")}, fmt="docx", doc_id="d1"),
    ]
    report = sc.aggregate(docs)
    worst = {r["field"]: r["accuracy"] for r in report["worst_fields"]}
    assert "cam_charges" in worst and worst["cam_charges"] == 0.0
    fmt_acc = {r["format"]: r["accuracy"] for r in report["format_accuracy"]}
    assert set(fmt_acc) == {"pdf", "docx"}
    print("✓ test_aggregate_identifies_weak_fields_and_formats: PASS")


def test_aggregate_calibration_ignores_not_found_fields():
    # a doc that's all correct not-founds: no asserted values, calibration n's are 0
    docs = [_doc({}, doc_id="empty")]
    report = sc.aggregate(docs)
    assert report["calibration"]["n_high"] == 0
    assert report["overall_accuracy"] == 1.0, "correctly finding nothing is 100% accurate"
    print("✓ test_aggregate_calibration_ignores_not_found_fields: PASS")


if __name__ == "__main__":
    test_values_match_field_aware()
    test_score_field_kinds()
    test_aggregate_flags_high_confidence_wrong()
    test_aggregate_calibration_gap()
    test_aggregate_identifies_weak_fields_and_formats()
    test_aggregate_calibration_ignores_not_found_fields()
    print("\nAll extraction scoring tests passed.")
