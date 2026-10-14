"""
Builds precomputed_section8_sample.json: the Section 8 sample portfolio
that "Load Sample Deal" (and the demo seed) loads when SECTION8_MODE is
on. See app/sample_deal.py:load_section8_sample.

Two halves, both from the fictional fixture set in
backend/tests/fixtures/section8/ (the graded answer key lives there):

  documents -- the 10 voucher leases, 5 HAP contracts and both October
      rent rolls, run through the REAL upload routes (POST /leases and
      POST /leases/import-rent-roll) on a throwaway database with the
      regex extraction engine forced, then read back exactly as stored.
      Same "static capture of what the real routes produced" idea as the
      Maple Ridge precomputed_sample_deal.json, but scripted, so it can be
      re-run. Anthropic is never called.

  records -- the Section 8 rows (PHA, properties, units, tenancies, HAP
      contracts, document links), built from the fixture generator's own
      data. Tenancy amounts are what the October rent rolls SHOW (the
      seller's system, planted errors included), so later checks have
      real problems to find in the sample.

Re-run whenever the fixtures or the extraction/import code change (e.g.
after qa/overnight-gauntlet merges its Section 8 rent-roll columns):

    cd backend && venv/bin/python benchmark_data/section8_sample/capture_section8_sample.py

test_section8_sample_data.py fails if the fixture files' sha256s no
longer match what this file recorded.
"""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(BACKEND, "tests", "fixtures", "section8")
OUT_PATH = os.path.join(HERE, "precomputed_section8_sample.json")

# The rent rolls the sample loads (October, one per property). The
# September rolls and the seller's workbook stay test-only fixtures.
RENT_ROLLS = {"RR1": "JR", "RR3": "BT"}
# The single "try a sample lease" lease: the fixture set's clean control.
SINGLE_LEASE_UNIT = ("JR", "214")


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_section8_fixtures", os.path.join(FIXTURES, "generate_section8_fixtures.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    return gen


def _sha256(rel):
    with open(os.path.join(FIXTURES, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _address(gen, prop, unit):
    p = gen.PROPS[prop]
    return f"{p['street']}, {p['city']}, Unit {unit}"


def _capture_documents(gen):
    """Upload every sample document through the real routes; return (rows, single_lease_split)."""
    os.environ["LEASE_EXTRACTION_ENGINE"] = "regex"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    sys.path.insert(0, BACKEND)
    sys.path.insert(0, os.path.join(BACKEND, "tests"))
    from app import database, usage_limits
    from app.api import app
    from app.auth import hash_password
    from _session_users import sync_session_user

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    team_id = database.get_team_by_name("Legacy")["id"]
    user = database.create_user("capture@abstractly.test", "Capture", hash_password("x"),
                                role="analyst", team_id=team_id)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=user["id"], email="capture@abstractly.test", name="Capture",
                    role="analyst", team_id=team_id)
        sync_session_user(sess)

    rows = []

    def collect(before_ids, key):
        for lease in database.get_all_leases(team_id, document_type=None):
            if lease["id"] in before_ids:
                continue
            fields = lease["extracted_fields"]
            rows.append({
                "key": key,
                "filename": lease["filename"],
                "extracted_fields": json.loads(fields) if isinstance(fields, str) else fields,
                "document_type": lease["document_type"],
                "date_candidates": (json.loads(lease["date_candidates"]) if isinstance(lease.get("date_candidates"), str)
                                    else lease.get("date_candidates")),
                "display_name": lease.get("display_name"),
                "source_page_start": lease.get("source_page_start"),
                "source_page_end": lease.get("source_page_end"),
            })

    def ids():
        return {l["id"] for l in database.get_all_leases(team_id, document_type=None)}

    pdfs = [(f"lease:{s['prop']}:{s['unit']}", s["file"]) for s in gen.LEASES] + \
           [(f"hap_contract:{k}", v["file"]) for k, v in gen.HAP_CONTRACTS.items()]
    single = None
    for key, rel in pdfs:
        usage_limits._reset_extraction_rate_limit_for_tests()
        before = ids()
        with open(os.path.join(FIXTURES, rel), "rb") as f:
            resp = client.post("/leases", data={"file": (io.BytesIO(f.read()), os.path.basename(rel))},
                               content_type="multipart/form-data")
        assert resp.status_code == 201, (rel, resp.status_code, resp.get_json())
        n_before = len(rows)
        collect(before, key)
        if key == f"lease:{SINGLE_LEASE_UNIT[0]}:{SINGLE_LEASE_UNIT[1]}":
            single = [{"fields": r["extracted_fields"], "date_candidates": r["date_candidates"],
                       "display_name": r["display_name"], "source_page_start": r["source_page_start"],
                       "source_page_end": r["source_page_end"]} for r in rows[n_before:]]

    for rr, prop in RENT_ROLLS.items():
        rel = gen.RENT_ROLLS[rr]["file"]
        p = gen.PROPS[prop]
        before = ids()
        with open(os.path.join(FIXTURES, rel), "rb") as f:
            resp = client.post("/leases/import-rent-roll",
                               data={"file": (io.BytesIO(f.read()), os.path.basename(rel)),
                                     "property_address": f"{p['street']}, {p['city']}"},
                               content_type="multipart/form-data")
        assert resp.status_code == 201, (rel, resp.status_code, resp.get_json())
        collect(before, f"rent_roll:{rr}")
    os.unlink(tmp.name)
    return rows, single


def _records(gen):
    """The Section 8 rows, in plain dollars / ISO dates, keyed so the loader can wire up ids."""
    pha = {
        "key": "pha:HCHA", "name": gen.PHA["name"], "short_name": gen.PHA["short"], "jurisdiction": "Harrow County",
        "inspection_standard": "HQS", "payment_day": 1, "rent_increase_notice_days": 60,
        "contact_phone": gen.PHA["phone"], "contact_email": gen.PHA["email"],
        "notes": "Fictional sample PHA (Abstractly Section 8 sample portfolio).",
    }
    properties = [
        {"key": "property:JR", "name": gen.PROPS["JR"]["name"],
         "address": f"{gen.PROPS['JR']['street']}, {gen.PROPS['JR']['city']}", "program": "HCV",
         "default_pha": "pha:HCHA", "notes": f"Owner: {gen.PROPS['JR']['owner']}"},
        {"key": "property:BT", "name": gen.PROPS["BT"]["name"],
         "address": f"{gen.PROPS['BT']['street']}, {gen.PROPS['BT']['city']}", "program": "mixed",
         "default_pha": "pha:HCHA",
         "notes": f"Owner: {gen.PROPS['BT']['owner']}. 1A-1D PBRA ({gen.PBRA_CONTRACT}); "
                  f"2A-3D PBV ({gen.PBV_CONTRACT})."},
    ]
    units, tenancies, contracts = [], [], []
    for rr, prop in RENT_ROLLS.items():
        shown = {r["unit"]: r for r in gen.rr_rows(rr)}
        for u in gen.UNITS:
            if u["prop"] != prop:
                continue
            r = shown[u["unit"]]
            ukey = f"unit:{prop}:{u['unit']}"
            units.append({"key": ukey, "property": f"property:{prop}", "unit_label": u["unit"],
                          "address": _address(gen, prop, u["unit"]), "bedrooms": int(u["type"][0]),
                          "status": "occupied" if r["status"] == "Occupied" else "vacant"})
            program = u["program"] if u["program"] != "Market" else "market"
            assisted = program in ("HCV", "PBV", "PBRA")
            if r["status"] == "Occupied":
                tenancies.append({
                    "key": f"tenancy:{prop}:{u['unit']}", "unit": ukey, "head_of_household": u["tenant"],
                    "household_size": len(u.get("members", [])) or None,
                    "pha": "pha:HCHA" if program in ("HCV", "PBV") else None, "program": program,
                    "move_in_date": u.get("move_in"),
                    "contract_rent": r["contract"], "tenant_rent": r["ttp"],
                    "hap": r["hap"] if assisted else None,
                    "amounts_effective_date": gen.RENT_ROLLS[rr]["as_of"].isoformat(),
                    "source": f"rent_roll:{rr}:{u['unit']}", "status": "current",
                })
            elif u.get("move_out"):
                tenancies.append({
                    "key": f"tenancy:{prop}:{u['unit']}", "unit": ukey, "head_of_household": u["tenant"],
                    "household_size": len(u.get("members", [])) or None, "pha": "pha:HCHA", "program": program,
                    "move_in_date": u.get("move_in"), "move_out_date": u["move_out"],
                    "contract_rent": u["contract"], "tenant_rent": u["ttp"], "hap": u["hap"],
                    "source": f"lease:{prop}:{u['unit']}", "status": "past",
                })
    for key, spec in gen.HAP_CONTRACTS.items():
        if spec["kind"] == "HCV":
            prop, unit = spec["unit"]
            u = gen.U[(prop, unit)]
            contracts.append({
                "key": f"contract:{key}", "contract_type": "HCV", "contract_number": gen.hcv_contract_no(u),
                "form": "HUD-52641 (model)", "pha": "pha:HCHA", "property": f"property:{prop}",
                "unit": f"unit:{prop}:{unit}", "tenancy": f"tenancy:{prop}:{unit}",
                "start_date": u.get("hap_effective") or u["lease"][0], "end_date": u["lease"][1],
                "contract_rent": u["contract"], "initial_hap": u["hap"], "document": f"hap_contract:{key}",
                "status": "active"})
        elif spec["kind"] == "PBV":
            for unit in gen.PBV_EXHIBIT_A:
                u = gen.U[("BT", unit)]
                contracts.append({
                    "key": f"contract:{key}:{unit}", "contract_type": "PBV", "contract_number": gen.PBV_CONTRACT,
                    "form": "HUD-52530-A (model), Exhibit A", "pha": "pha:HCHA", "property": "property:BT",
                    "unit": f"unit:BT:{unit}", "tenancy": f"tenancy:BT:{unit}" if u.get("tenant") else None,
                    "start_date": "2024-07-01", "end_date": "2044-06-30", "contract_rent": u["contract"],
                    "initial_hap": None, "document": f"hap_contract:{key}", "status": "active"})
        else:
            for unit in gen.PBRA_UNITS:
                u = gen.U[("BT", unit)]
                contracts.append({
                    "key": f"contract:{key}:{unit}", "contract_type": "PBRA", "contract_number": gen.PBRA_CONTRACT,
                    "form": "Multifamily HAP renewal (model)", "pha": None, "property": "property:BT",
                    "unit": f"unit:BT:{unit}", "tenancy": f"tenancy:BT:{unit}",
                    "start_date": "2021-09-01", "end_date": gen.PBRA_EXPIRES.isoformat(),
                    "contract_rent": u["contract"], "initial_hap": None, "document": f"hap_contract:{key}",
                    "status": "active"})
    return {"pha": pha, "properties": properties, "units": units, "tenancies": tenancies,
            "hap_contracts": contracts}


def _rent_roll_row_unit(row, rr, gen):
    """Which fixture unit a captured rent-roll row is (by the unit label on the end of its address)."""
    addr = ((row["extracted_fields"].get("property_address") or {}).get("value") or "")
    labels = sorted((u["unit"] for u in gen.UNITS if u["prop"] == RENT_ROLLS[rr]), key=len, reverse=True)
    tenant = ((row["extracted_fields"].get("tenant") or {}).get("value") or "")
    for label in labels:
        if addr.rstrip().endswith(" " + label):
            return label
    for u in gen.UNITS:
        if u["prop"] == RENT_ROLLS[rr] and u.get("tenant") == tenant:
            return u["unit"]
    return None


def main():
    gen = _load_generator()
    captured, single = _capture_documents(gen)
    rows, dropped = [], []
    for row in captured:
        if row["key"].startswith("rent_roll:"):
            unit = _rent_roll_row_unit(row, row["key"].split(":")[1], gen)
            if unit is None:
                # e.g. main's importer reads the AppFolio "Total" row as a
                # tenant ("16 occupied / 18 units"). Not a unit -- keep it
                # out of the sample, but record it so it isn't silently lost.
                f = row["extracted_fields"]
                dropped.append({"file": row["filename"],
                                "tenant": (f.get("tenant") or {}).get("value"),
                                "property_address": (f.get("property_address") or {}).get("value"),
                                "reason": "imported row matches no unit (importer read a totals row as a tenant)"})
                continue
            row["key"] = f"{row['key']}:{unit}"
        rows.append(row)
    used = [s["file"] for s in gen.LEASES] + [v["file"] for v in gen.HAP_CONTRACTS.values()] + \
           [gen.RENT_ROLLS[rr]["file"] for rr in RENT_ROLLS] + ["generate_section8_fixtures.py"]
    out = {
        "name": "Juniper Row & Bellmont Terrace (Section 8 sample portfolio)",
        "as_of": gen.AS_OF.isoformat(),
        "fixture_sha256": {rel: _sha256(rel) for rel in sorted(used)},
        "documents": rows,
        "dropped_rows": dropped,
        "single_lease": single,
        "records": _records(gen),
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}: {len(rows)} documents, "
          + ", ".join(f"{len(v) if isinstance(v, list) else 1} {k}" for k, v in out["records"].items()))


if __name__ == "__main__":
    main()
