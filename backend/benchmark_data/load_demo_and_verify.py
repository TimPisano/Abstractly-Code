"""
End-to-end check for the demo flow (checklist Step 1): run all 12 real
sample lease PDFs and all 3 rent rolls through the REAL pipeline against
an isolated temp database, then compute the lease-vs-rent-roll
reconciliation -- the flow a recorded demo walkthrough exercises -- and
report that it completes with no errors, plus what reconciliation flagged
vs. what was deliberately planted in the rent rolls.

Engine is regex unless LEASE_AI_EXTRACTION=true + a funded key.

  PYTHONPATH=. venv/bin/python benchmark_data/load_demo_and_verify.py
  PYTHONPATH=. venv/bin/python benchmark_data/load_demo_and_verify.py --use-ground-truth
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

from app import database, document_extractor, rent_roll_import  # noqa: E402
from app.ai_extraction import resolve_engine  # noqa: E402
from app.field_extractor import FieldExtractor  # noqa: E402
from app.portfolio import compute_rent_roll_reconciliation  # noqa: E402

database.configure(_tmp_db.name)


def _extract(pages, filename):
    if resolve_engine() == "ai":
        from app import ai_extraction
        fields = ai_extraction.extract_lease_fields(pages)
        fields.pop("_ai_meta", None)
        return fields
    return FieldExtractor().extract_fields(pages, source_label=filename)


def _gt_to_field_shape(gt):
    out = {}
    for k, v in gt.items():
        out[k] = ({"value": None, "source": None, "confidence": None} if v is None
                  else {"value": v, "source": {"page": 1, "quote": v}, "confidence": "high"})
    return out


def main():
    use_gt = "--use-ground-truth" in sys.argv
    errors = []
    database.init_db()

    gt = json.load(open(os.path.join(HERE, "ground_truth.json")))
    manifest = gt["leases"]
    rent_rolls = gt.get("rent_rolls", [])
    mode = "GROUND TRUTH (demo-quality fields)" if use_gt else f"{resolve_engine()} extraction (real pipeline)"
    print(f"mode = {mode}   db = {_tmp_db.name}\n")

    loaded = 0
    for entry in manifest:
        path = os.path.join(HERE, "leases", entry["file"])
        try:
            if use_gt:
                fields = _gt_to_field_shape(entry["ground_truth"])
            else:
                pages = document_extractor.extract_pages(open(path, "rb").read(), entry["file"], path)
                fields = _extract(pages, entry["file"])
            database.insert_lease(entry["file"], fields, display_name=entry["id"])
            loaded += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"lease {entry['id']}: {type(e).__name__}: {e}")
    print(f"abstraction: {loaded}/{len(manifest)} lease PDFs processed and stored")

    rr_rows = 0
    for rr in rent_rolls:
        path = os.path.join(HERE, rr["file"])
        try:
            parsed = rent_roll_import.parse_rent_roll_file(
                open(path, "rb").read(), os.path.basename(rr["file"]), base_property_address=None)
            for row in parsed["leases"]:
                database.insert_lease(os.path.basename(rr["file"]), row["extracted_fields"],
                                      display_name=row.get("display_name"))
                rr_rows += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"rent roll {rr['name']}: {type(e).__name__}: {e}")
    print(f"rent-roll import: {rr_rows} rows imported across {len(rent_rolls)} files")

    try:
        leases = database.get_all_leases()
        recon = compute_rent_roll_reconciliation(leases)
        mismatches = recon.get("mismatches", recon.get("discrepancies", []))
    except Exception as e:  # noqa: BLE001
        errors.append(f"reconciliation: {type(e).__name__}: {e}")
        mismatches = []

    print(f"\nreconciliation flagged {len(mismatches)} disagreement(s):")
    for m in mismatches:
        print(f"  - {m.get('address')}  [{m.get('field')}]  "
              f"rent_roll={m.get('rent_roll_value')!r}  lease={m.get('lease_document_value')!r}")

    planted = [p for rr in rent_rolls for p in rr.get("planted_disagreements", [])]
    print(f"\nplanted disagreements: {len(planted)}")
    flagged = {(str(m.get('address', '')).lower().strip(), m.get('field')) for m in mismatches}
    for p in planted:
        hit = any(p["address"].lower()[:20] in k[0] and k[1] == p["field"] for k in flagged)
        print(f"  [{'FLAGGED' if hit else 'missed '}] {p['address']} [{p['field']}] -- {p['note']}")

    print("\n" + ("=" * 60))
    if errors:
        print(f"RESULT: {len(errors)} ERROR(S) -- flow did NOT complete clean:")
        for e in errors:
            print(f"  ! {e}")
        sys.exit(1)
    print("RESULT: end-to-end flow completed with no errors.")
    os.unlink(_tmp_db.name)


if __name__ == "__main__":
    main()
