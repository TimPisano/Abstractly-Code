"""
Runs every fixture in fixtures/ through the REAL parse_csv_rent_roll /
parse_xlsx_rent_roll (the exact functions POST /leases/import-rent-roll
calls), grades the result against each fixture's ground-truth sidecar,
and writes a report.

Usage: python3 run_stress_test.py [--out report_before.md]

Classification per file:
  PASS            every field on every row matches truth exactly
  SILENT_WRONG    at least one field has a value that DISAGREES with
                  truth without erroring -- the dangerous category
  UNDER_EXTRACTED no silent-wrong fields, but at least one field truth
                  says should have a real value came back "not found"
                  (a safe, conservative miss -- still tracked)
  FAILED          raised an exception when truth expected success, or
                  succeeded when truth expected a file-level failure
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.rent_roll_import import parse_csv_rent_roll, parse_xlsx_rent_roll, RentRollImportError
from app.normalize import parse_currency, parse_date

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
BASE_ADDR = "500 Commerce Way"


def _field_value(lease, name):
    entry = (lease.get("extracted_fields") or {}).get(name)
    if not isinstance(entry, dict):
        return None
    v = entry.get("value")
    return v if v not in (None, "") else None


def _compare_row(actual_lease, truth_row):
    """Returns a list of mismatch dicts: {field, expected, actual, danger}."""
    mismatches = []

    tenant_actual = _field_value(actual_lease, "tenant")
    if tenant_actual != truth_row["tenant"]:
        mismatches.append(_classify("tenant", truth_row["tenant"], tenant_actual))

    rent_actual_raw = _field_value(actual_lease, "rent_amount")
    rent_actual = parse_currency(rent_actual_raw) if rent_actual_raw else None
    rent_truth = truth_row["rent_amount"]
    if (rent_actual is None) != (rent_truth is None) or (rent_actual is not None and abs(rent_actual - rent_truth) > 0.001):
        mismatches.append(_classify("rent_amount", rent_truth, rent_actual))

    for date_field in ("lease_start_date", "lease_end_date"):
        raw = _field_value(actual_lease, date_field)
        parsed = parse_date(raw) if raw else None
        actual_iso = parsed.isoformat() if parsed else None
        truth_iso = truth_row[date_field]
        if actual_iso != truth_iso:
            mismatches.append(_classify(date_field, truth_iso, actual_iso))

    addr_actual = _field_value(actual_lease, "property_address")
    if addr_actual != truth_row["property_address"]:
        mismatches.append(_classify("property_address", truth_row["property_address"], addr_actual))

    return mismatches


def _classify(field, expected, actual):
    if expected is None and actual is not None:
        danger = "SILENT_WRONG"  # fabricated a value where there should be none
    elif expected is not None and actual is None:
        danger = "UNDER_EXTRACTED"  # safe, conservative miss
    else:
        danger = "SILENT_WRONG"  # both have values, but they disagree -- worst case
    return {"field": field, "expected": expected, "actual": actual, "danger": danger}


def run_one(entry):
    fixture_id = entry["id"]
    filename = entry["file"]
    path = os.path.join(FIXTURES_DIR, filename)
    truth_path = os.path.join(FIXTURES_DIR, fixture_id + ".truth.json")
    with open(truth_path) as f:
        truth = json.load(f)
    truth_rows = truth["rows"]  # None => expected file-level failure

    with open(path, "rb") as f:
        file_bytes = f.read()

    parser = parse_csv_rent_roll if filename.endswith(".csv") else parse_xlsx_rent_roll

    try:
        result = parser(file_bytes, filename, base_property_address=BASE_ADDR)
        raised = None
    except RentRollImportError as exc:
        result = None
        raised = str(exc)
    except Exception as exc:  # noqa: BLE001 -- a crash is itself a finding, not something to hide
        result = None
        raised = f"UNEXPECTED {type(exc).__name__}: {exc}"

    if truth_rows is None:
        # Expected a clean file-level failure.
        if raised and "UNEXPECTED" not in raised:
            return {"id": fixture_id, "category": "PASS", "detail": f"correctly rejected: {raised}"}
        elif raised:
            return {"id": fixture_id, "category": "FAILED", "detail": raised}
        else:
            return {"id": fixture_id, "category": "FAILED",
                    "detail": f"expected a clean rejection, but it succeeded and imported {len(result['leases'])} row(s)"}

    if raised:
        return {"id": fixture_id, "category": "FAILED", "detail": f"raised unexpectedly: {raised}"}

    leases = result["leases"]
    lease_iter = iter(leases)
    all_mismatches = []
    expected_skips = sum(1 for r in truth_rows if r["skip"])
    actual_skips = len(result["skipped_rows"])

    for i, truth_row in enumerate(truth_rows):
        if truth_row["skip"]:
            continue
        actual_lease = next(lease_iter, None)
        if actual_lease is None:
            all_mismatches.append({"row": i, "field": "(row)", "expected": "a real lease", "actual": "none produced (row was skipped/dropped)", "danger": "UNDER_EXTRACTED"})
            continue
        for m in _compare_row(actual_lease, truth_row):
            m["row"] = i
            all_mismatches.append(m)

    if expected_skips != actual_skips:
        all_mismatches.append({
            "row": "-", "field": "(skip count)",
            "expected": f"{expected_skips} skipped row(s)", "actual": f"{actual_skips} skipped row(s)",
            "danger": "SILENT_WRONG" if actual_skips < expected_skips else "UNDER_EXTRACTED",
        })

    if not all_mismatches:
        return {"id": fixture_id, "category": "PASS", "detail": "all fields matched truth"}

    worst = "SILENT_WRONG" if any(m["danger"] == "SILENT_WRONG" for m in all_mismatches) else "UNDER_EXTRACTED"
    detail_lines = [
        f"row {m['row']} field={m['field']}: expected={m['expected']!r} actual={m['actual']!r} ({m['danger']})"
        for m in all_mismatches
    ]
    return {"id": fixture_id, "category": worst, "detail": "; ".join(detail_lines)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="report.md")
    args = parser.parse_args()

    with open(os.path.join(FIXTURES_DIR, "_manifest.json")) as f:
        manifest = json.load(f)

    results = [run_one(entry) for entry in manifest]

    counts = {"PASS": 0, "SILENT_WRONG": 0, "UNDER_EXTRACTED": 0, "FAILED": 0}
    for r in results:
        counts[r["category"]] += 1

    lines = [
        "# Rent roll stress test report",
        "",
        f"**{len(results)} fixtures.** PASS={counts['PASS']}  SILENT_WRONG={counts['SILENT_WRONG']}  "
        f"UNDER_EXTRACTED={counts['UNDER_EXTRACTED']}  FAILED={counts['FAILED']}",
        "",
        f"Pass rate: {counts['PASS']}/{len(results)} = {counts['PASS']/len(results)*100:.1f}%",
        "",
        "## SILENT_WRONG (most dangerous -- looked successful, wasn't)",
    ]
    for r in results:
        if r["category"] == "SILENT_WRONG":
            lines.append(f"- **{r['id']}**: {r['detail']}")
    lines.append("")
    lines.append("## FAILED")
    for r in results:
        if r["category"] == "FAILED":
            lines.append(f"- **{r['id']}**: {r['detail']}")
    lines.append("")
    lines.append("## UNDER_EXTRACTED (safe miss, not dangerous)")
    for r in results:
        if r["category"] == "UNDER_EXTRACTED":
            lines.append(f"- **{r['id']}**: {r['detail']}")
    lines.append("")
    lines.append("## PASS")
    for r in results:
        if r["category"] == "PASS":
            lines.append(f"- {r['id']}")

    report = "\n".join(lines)
    out_path = os.path.join(HERE, args.out)
    with open(out_path, "w") as f:
        f.write(report)

    print(report)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
