"""
Runs every lease-text fixture in lease_fixtures/ through the REAL
FieldExtractor (the exact extraction code a real PDF upload uses) and
then the REAL obligations.py, and grades the computed dates against
each fixture's hand-verified truth.
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.field_extractor import FieldExtractor
from app import obligations

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(HERE, "lease_fixtures")
REFERENCE_DATE = date(2024, 1, 1)  # fixed, for reproducibility -- doesn't affect due_date correctness, only status/days_remaining


def run_one(fixture_id):
    with open(os.path.join(FIXTURES_DIR, fixture_id + ".json")) as f:
        data = json.load(f)

    extracted_fields = FieldExtractor().extract_fields(data["pages"])
    lease = {"id": None, "extracted_fields": extracted_fields}

    truth = data["truth"]
    mismatches = []

    if "renewal_notice_deadline" in truth:
        result = obligations.compute_renewal_notice_deadline(lease, REFERENCE_DATE)
        actual = result["due_date"] if result else None
        if actual != truth["renewal_notice_deadline"]:
            mismatches.append(f"renewal_notice_deadline: expected {truth['renewal_notice_deadline']!r}, got {actual!r}")

    if "termination_notice_deadline" in truth:
        result = obligations.compute_termination_notice_deadline(lease, REFERENCE_DATE)
        actual = result["due_date"] if result else None
        if actual != truth["termination_notice_deadline"]:
            mismatches.append(f"termination_notice_deadline: expected {truth['termination_notice_deadline']!r}, got {actual!r}")

    if "escalation_trigger_dates" in truth:
        results = obligations.compute_escalation_trigger_dates(lease, REFERENCE_DATE)
        actual = sorted(r["due_date"] for r in results)
        expected = sorted(truth["escalation_trigger_dates"])
        if actual != expected:
            mismatches.append(f"escalation_trigger_dates: expected {expected}, got {actual}")

    if "insurance_obligation_present" in truth:
        result = obligations.compute_insurance_obligation(lease)
        present = result is not None
        if present != truth["insurance_obligation_present"]:
            mismatches.append(f"insurance_obligation_present: expected {truth['insurance_obligation_present']}, got {present}")
        if present and result["due_date"] != truth.get("insurance_due_date"):
            mismatches.append(f"insurance_due_date: expected {truth.get('insurance_due_date')!r}, got {result['due_date']!r}")

    # Also surface what the extractor itself found for the relevant raw
    # fields, so a mismatch's root cause (extraction vs. date math) is
    # visible without re-running by hand.
    raw_fields = {
        k: (extracted_fields.get(k) or {}).get("value")
        for k in ("lease_start_date", "lease_end_date", "renewal_options", "termination_options", "rent_escalation")
    }

    return {"id": fixture_id, "pass": not mismatches, "mismatches": mismatches, "raw_fields": raw_fields}


def main():
    with open(os.path.join(FIXTURES_DIR, "_manifest.json")) as f:
        manifest = json.load(f)

    results = [run_one(entry["id"]) for entry in manifest]
    passed = sum(1 for r in results if r["pass"])

    print(f"# Obligations engine test report\n")
    print(f"{passed}/{len(results)} fixtures passed.\n")
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"## [{status}] {r['id']}")
        print(f"  raw extracted fields: {r['raw_fields']}")
        for m in r["mismatches"]:
            print(f"  MISMATCH: {m}")
        print()


if __name__ == "__main__":
    main()
