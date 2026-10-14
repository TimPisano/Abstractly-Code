"""
"Load sample deal" -- copies the fictional Maple Ridge demo deal
(15 real lease PDFs + a 16-unit rent roll, see
backend/benchmark_data/demo_deal/) into a single team's workspace, so a
brand-new team can see what the product does on day one without
uploading their own documents first.

The fixture (precomputed_sample_deal.json) is a static capture of what
the real /leases and /leases/import-rent-roll routes already produced
from these same files, via the non-AI regex/pdfplumber fallback engine
(this environment has no ANTHROPIC_API_KEY) -- see
backend/tests/test_demo_deal_golden.py, which validates that flow
against the deal's own planted expected_findings.json. Loading it here
is a direct database.insert_lease() per row, no extraction call of any
kind -- this is the whole point: a team can click this as often as they
like without ever touching the AI pipeline or a real API.
"""
import json
import os

from . import database

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "benchmark_data", "demo_deal", "precomputed_sample_deal.json")

_cached_fixture = None


def _load_fixture():
    global _cached_fixture
    if _cached_fixture is None:
        with open(_FIXTURE_PATH) as f:
            _cached_fixture = json.load(f)
    return _cached_fixture


def load_sample_deal(team_id: int) -> int:
    """
    Inserts every precomputed Maple Ridge row into `team_id`'s own
    workspace. Safe to call more than once -- each call inserts a fresh
    copy (same convention as a real re-upload), it doesn't check for or
    dedupe against a prior load; the route this backs is intended for a
    genuinely empty workspace, not idempotent syncing. Returns how many
    leases were created.
    """
    fixture = _load_fixture()
    for row in fixture:
        database.insert_lease(
            row["filename"],
            row["extracted_fields"],
            team_id,
            document_type=row["document_type"],
            date_candidates=row.get("date_candidates"),
            display_name=row.get("display_name"),
            source_page_start=row.get("source_page_start"),
            source_page_end=row.get("source_page_end"),
        )
    return len(fixture)


# ----------------------------------------------------------------------
# Section 8 sample portfolio (feature/s8-sample-data, T13). Used instead
# of Maple Ridge when SECTION8_MODE is on -- see api.load_sample_deal_route
# and demo_seed. Same idea as above: a precomputed capture
# (benchmark_data/section8_sample/, built by capture_section8_sample.py
# from the fictional fixture set), loaded by direct inserts, never an
# extraction or Anthropic call.
# ----------------------------------------------------------------------
from . import section8_records as s8_records
from .portfolio import _normalize_address, _normalize_building_address

_S8_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "benchmark_data", "section8_sample", "precomputed_section8_sample.json")
SAMPLE_TAG = "Sample"

_cached_s8_fixture = None


class SampleAlreadyLoaded(Exception):
    """The team already has the sample's properties (T1's tables are unique per team + address)."""


def _load_s8_fixture():
    global _cached_s8_fixture
    if _cached_s8_fixture is None:
        with open(_S8_FIXTURE_PATH) as f:
            _cached_s8_fixture = json.load(f)
    return _cached_s8_fixture


def section8_sample_name() -> str:
    return _load_s8_fixture()["name"]


def section8_single_lease():
    """The one-lease sample for POST /leases/sample: the clean-control voucher lease, in _persist_split_leases' shape."""
    return _load_s8_fixture()["single_lease"]


def section8_sample_loaded(team_id: int) -> bool:
    wanted = {_normalize_building_address(p["address"]) for p in _load_s8_fixture()["records"]["properties"]}
    have = {p["normalized_address"] for p in database.list_section8_records("properties", team_id, include_archived=True)}
    return bool(wanted & have)


def _create(table, team_id, body, extra=None):
    """Same validation and same-team reference checks the /section8 routes apply (clean_body), then T1's insert."""
    values = s8_records.clean_body(table, body, team_id, creating=True)
    values.update(extra or {})
    return database.create_section8_record(table, team_id, values)


def load_section8_sample(team_id: int) -> dict:
    """
    Inserts the Section 8 sample portfolio into `team_id`'s workspace:
    every captured document (tagged "Sample") plus the PHA, properties,
    units, tenancies, HAP contracts and unit-document links, all owned by
    `team_id`. Raises SampleAlreadyLoaded if the team already has it --
    unlike Maple Ridge, a second copy can't coexist (unique addresses).
    Returns counts per kind.
    """
    if section8_sample_loaded(team_id):
        raise SampleAlreadyLoaded()
    fx = _load_s8_fixture()
    rec = fx["records"]

    leases = {}  # capture key -> [lease ids], in file order
    for row in fx["documents"]:
        lease_id = database.insert_lease(
            row["filename"], row["extracted_fields"], team_id,
            document_type=row["document_type"], date_candidates=row.get("date_candidates"),
            display_name=row.get("display_name"), source_page_start=row.get("source_page_start"),
            source_page_end=row.get("source_page_end"),
        )
        database.add_lease_tag(lease_id, SAMPLE_TAG, team_id=team_id)
        leases.setdefault(row["key"], []).append(lease_id)

    ids = {}
    pha = {k: v for k, v in rec["pha"].items() if k != "key"}
    ids[rec["pha"]["key"]] = _create("phas", team_id, pha)

    for p in rec["properties"]:
        body = {"name": p["name"], "address": p["address"], "program": p["program"],
                "default_pha_id": ids[p["default_pha"]], "notes": p["notes"]}
        ids[p["key"]] = _create("properties", team_id, body,
                                {"normalized_address": _normalize_building_address(p["address"])})

    for u in rec["units"]:
        body = {"property_id": ids[u["property"]], "unit_label": u["unit_label"],
                "bedrooms": u["bedrooms"], "status": u["status"]}
        ids[u["key"]] = _create("units", team_id, body, {"normalized_address": _normalize_address(u["address"])})

    for t in rec["tenancies"]:
        source = leases.get(t["source"], [None])[0]
        body = {"unit_id": ids[t["unit"]], "head_of_household": t["head_of_household"],
                "household_size": t["household_size"], "pha_id": ids.get(t["pha"]) if t["pha"] else None,
                "program": t["program"], "move_in_date": t["move_in_date"],
                "move_out_date": t.get("move_out_date"), "contract_rent": t["contract_rent"],
                "tenant_rent": t["tenant_rent"], "hap": t["hap"],
                "amounts_effective_date": t.get("amounts_effective_date"),
                "source_lease_id": source, "status": t["status"]}
        ids[t["key"]] = _create("tenancies", team_id, body)

    for c in rec["hap_contracts"]:
        body = {"pha_id": ids[c["pha"]] if c["pha"] else None, "contract_type": c["contract_type"],
                "contract_number": c["contract_number"], "form": c["form"], "property_id": ids[c["property"]],
                "unit_id": ids[c["unit"]], "tenancy_id": ids[c["tenancy"]] if c["tenancy"] else None,
                "start_date": c["start_date"], "end_date": c["end_date"],
                "contract_rent": c["contract_rent"], "initial_hap": c["initial_hap"],
                "source_lease_id": leases[c["document"]][0], "status": c["status"]}
        ids[c["key"]] = _create("hap_contracts", team_id, body)

    # Link every document to its unit: lease PDFs and rent-roll rows to
    # the unit (+ tenancy), each HAP contract PDF to every unit it covers.
    links = 0

    def link(lease_id, unit_key, kind, tenancy_key=None, contract_key=None, pha_key=None):
        nonlocal links
        body = {"lease_id": lease_id, "doc_kind": kind,
                "tenancy_id": ids[tenancy_key] if tenancy_key in ids else None,
                "hap_contract_id": ids[contract_key] if contract_key else None,
                "pha_id": ids[pha_key] if pha_key else None}
        _create("unit_documents", team_id, body, {"unit_id": ids[unit_key], "linked_by": "sample"})
        links += 1

    tenancy_pha = {t["key"]: t["pha"] for t in rec["tenancies"]}
    for key, lease_ids in leases.items():
        kind, *rest = key.split(":")
        if kind == "hap_contract":
            continue  # linked per covered unit below
        if kind == "lease":
            prop, unit = rest
            doc_kind = "lease"
        else:  # rent_roll:<RR>:<unit>
            rr, unit = rest
            prop = "JR" if rr == "RR1" else "BT"
            doc_kind = "rent_roll_row"
        tkey = f"tenancy:{prop}:{unit}"
        for lid in lease_ids:
            link(lid, f"unit:{prop}:{unit}", doc_kind, tkey, pha_key=tenancy_pha.get(tkey) if doc_kind == "lease" else None)
    for c in rec["hap_contracts"]:
        link(leases[c["document"]][0], c["unit"], "hap_contract", c["tenancy"], c["key"], c["pha"])

    return {
        "documents": sum(len(v) for v in leases.values()),
        "phas": 1,
        "properties": len(rec["properties"]),
        "units": len(rec["units"]),
        "tenancies": len(rec["tenancies"]),
        "hap_contracts": len(rec["hap_contracts"]),
        "unit_documents": links,
    }
