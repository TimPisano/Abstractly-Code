"""
End-to-end check for the sample set (checklist Step 1): run all ten
sample lease PDFs and all three rent rolls through the REAL pipeline
against an isolated temp database, then compute the lease-vs-rent-roll
reconciliation — the exact flow a demo walkthrough exercises — and
report that it completes with no errors, plus what the reconciliation
flagged vs. what was deliberately planted.

Regex engine unless LEASE_AI_EXTRACTION=true + a funded key.

Run:  PYTHONPATH=. venv/bin/python benchmark_data/load_demo_and_verify.py
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

# Point every DB call at an isolated throwaway file — never the dev DB.
database.configure(_tmp_db.name)


def _regex_or_ai_fields(pages, filename):
    # Mirror api.py's engine selection at a small scale.
    if resolve_engine() == "ai":
        from app import ai_extraction
        return ai_extraction.extract_lease_fields(pages)
    return FieldExtractor().extract_fields(pages, source_label=filename)


def _gt_to_field_shape(gt):
    """Ground-truth dict -> the {value, source, confidence} shape insert_lease expects."""
    out = {}
    for k, v in gt.items():
        out[k] = ({"value": None, "source": None, "confidence": None} if v is None
                  else {"value": v, "source": {"page": 1, "quote": v}, "confidence": "high"})
    return out


def main():
    use_gt = "--use-ground-truth" in sys.argv
    errors = []
    database.init_db()  # fresh temp DB — nothing to reset

    manifest = json.load(open(os.path.join(HERE, "ground_truth.json")))
    mode = "GROUND TRUTH (demo-quality fields)" if use_gt else f"{resolve_engine()} extraction (real pipeline)"
    print(f"mode = {mode}   db = {_tmp_db.name}\n")

    # --- 1. abstraction: every lease PDF through the real pipeline -----
    loaded = 0
    for entry in manifest["leases"]:
        path = os.path.join(HERE, "leases", entry["file"])
        try:
            if use_gt:
                fields = _gt_to_field_shape(entry["ground_truth"])
            else:
                pages = document_extractor.extract_pages(open(path, "rb").read(), entry["file"], path)
                fields = _regex_or_ai_fields(pages, entry["file"])
            database.insert_lease(entry["file"], fields, display_name=entry["id"])
            loaded += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"lease {entry['id']}: {type(e).__name__}: {e}")
    print(f"abstraction: {loaded}/{len(manifest['leases'])} lease PDFs processed and stored")

    # --- 2. rent-roll import through the real importer ----------------
    rr_rows = 0
    for rr in manifest["rent_rolls"]:
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
    print(f"rent-roll import: {rr_rows} rows imported across {len(manifest['rent_rolls'])} files")

    # --- 3. reconciliation ------------------------------------------------
    try:
        leases = database.get_all_leases()
        recon = compute_rent_roll_reconciliation(leases)
        mismatches = recon["mismatches"]
    except Exception as e:  # noqa: BLE001
        errors.append(f"reconciliation: {type(e).__name__}: {e}")
        mismatches = []

    print(f"\nreconciliation flagged {len(mismatches)} disagreement(s):")
    for m in mismatches:
        print(f"  - {m['address']}  [{m['field']}]  rent_roll={m['rent_roll_value']!r}  lease={m['lease_document_value']!r}")

    planted = [g for rr in manifest["rent_rolls"] for g in rr["planted_disagreements"]]
    print(f"\nplanted disagreements: {len(planted)}")
    flagged_keys = {(m["address"].lower().strip(), m["field"]) for m in mismatches}
    for g in planted:
        hit = (g["address"].lower().strip(), g["field"]) in flagged_keys
        print(f"  [{'FLAGGED' if hit else 'missed '}] {g['address']} [{g['field']}] — {g['note']}")

    print("\n" + ("=" * 60))
    if errors:
        print(f"RESULT: {len(errors)} ERROR(S) — flow did NOT complete clean:")
        for e in errors:
            print(f"  ! {e}")
        sys.exit(1)
    print("RESULT: end-to-end flow completed with no errors.")
    os.unlink(_tmp_db.name)


if __name__ == "__main__":
    main()
