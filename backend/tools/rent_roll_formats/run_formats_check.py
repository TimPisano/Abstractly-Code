"""
Push every fixture in fixtures/ through the REAL
rent_roll_import.parse_rent_roll_file (the exact function
POST /leases/import-rent-roll now calls) and report, per format:

  - did it parse?
  - source_kind + any warnings + OCR confidence
  - how many lease rows, how many skipped (with reasons)
  - the column mapping it recovered
  - tenant / rent / dates for the first few rows, so column alignment
    is visible at a glance
  - on failure: the exact user-facing error string

Deterministic for structured formats. The image path depends on whether
a `tesseract` binary is installed on this machine.

Usage:  python3 tools/rent_roll_formats/run_formats_check.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.rent_roll_import import parse_rent_roll_file, RentRollImportError

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
BASE_ADDR = "1 Meridian Plaza, Portland, OR 97204"


def _fv(lease, name):
    e = (lease.get("extracted_fields") or {}).get(name) or {}
    return e.get("value")


def run_one(path):
    name = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    print(f"\n{'=' * 72}\n{name}  ({len(data):,} bytes)\n{'=' * 72}")
    try:
        result = parse_rent_roll_file(data, name, BASE_ADDR)
    except RentRollImportError as e:
        print(f"  PARSE FAILED (clean 400): {e}")
        return
    except Exception as e:  # noqa: BLE001
        print(f"  CRASHED ({type(e).__name__}): {e}")
        return

    leases = result["leases"]
    skipped = result["skipped_rows"]
    print(f"  source_kind : {result.get('source_kind')}")
    if "ocr_confidence" in result:
        print(f"  ocr_conf    : {result['ocr_confidence']}%")
    for w in result.get("warnings", []):
        print(f"  warning     : {w}")
    print(f"  column map  : {result['column_mapping']}")
    print(f"  imported    : {len(leases)} lease row(s)")
    print(f"  skipped     : {len(skipped)}")
    for s in skipped:
        print(f"      row {s.get('row')}: {s.get('reason')}")
    for lease in leases[:4]:
        print(f"      - tenant={_fv(lease,'tenant')!r}  rent={_fv(lease,'rent_amount')!r}  "
              f"start={_fv(lease,'lease_start_date')!r}  end={_fv(lease,'lease_end_date')!r}  "
              f"sqft={_fv(lease,'square_footage')!r}")
    if len(leases) > 4:
        print(f"      ... +{len(leases) - 4} more")


if __name__ == "__main__":
    fixtures = sorted(glob.glob(os.path.join(FIXTURES_DIR, "*")))
    if not fixtures:
        print("No fixtures. Run make_fixtures.py first.")
        sys.exit(1)
    for path in fixtures:
        run_one(path)
    print()
