"""
Section 8 sample portfolio (feature/s8-sample-data, T13).

With SECTION8_MODE on, "Load Sample Deal" (/sample-deal/load), the
one-lease sample (/leases/sample) and the demo seed use the fictional
Section 8 portfolio in benchmark_data/section8_sample/ instead of Maple
Ridge. With the flag off, nothing changes.

Checks: flag off unchanged; flag on loads the right counts into the
caller's team only, tagged Sample; the fixture set's planted errors
survive into the Section 8 records (so later checks have something to
find); a second load is refused cleanly; viewers can't load; the demo
seed/reset handle the Section 8 tables; no Anthropic call anywhere; and
the precomputed capture still matches the fixture files it came from.

Cross-team isolation lives in test_team_isolation.py
(test_section8_sample_portfolio_isolated_to_calling_team_only).
Temp SQLite + Flask test client; no network, no Anthropic.
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import anthropic

from app.api import app
from app import database, sample_deal
from app.section8_mode import FLAG_ENV
from _session_users import sync_session_user

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CAPTURE_PATH = os.path.join(BACKEND, "benchmark_data", "section8_sample", "precomputed_section8_sample.json")
MAPLE_PATH = os.path.join(BACKEND, "benchmark_data", "demo_deal", "precomputed_sample_deal.json")
FIXTURES = os.path.join(BACKEND, "tests", "fixtures", "section8")

with open(CAPTURE_PATH, encoding="utf-8") as _f:
    CAPTURE = json.load(_f)
with open(os.path.join(FIXTURES, "answer_key.json"), encoding="utf-8") as _f:
    ANSWER_KEY = {e["id"]: e for e in json.load(_f)["errors"]}

S8_TABLES = ["phas", "properties", "units", "tenancies", "hap_contracts", "unit_documents"]


def _no_anthropic(*args, **kwargs):
    raise AssertionError("The sample loaders must never construct an Anthropic client")


class _Env:
    """Temp DB, SECTION8_MODE on/off, one team with an analyst and a viewer, Anthropic booby-trapped. Restores everything."""

    def __init__(self, flag=True):
        self.flag = flag

    def __enter__(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.db_path = tmp.name
        database.configure(tmp.name)
        database.init_db()
        self.old_flag = os.environ.get(FLAG_ENV)
        if self.flag:
            os.environ[FLAG_ENV] = "true"
        else:
            os.environ.pop(FLAG_ENV, None)
        self.old_anthropic = anthropic.Anthropic
        anthropic.Anthropic = _no_anthropic
        self.team_id = database.create_team("Sample Team")["id"]
        self.analyst = self._client("analyst")
        self.viewer = self._client("viewer")
        return self

    def _client(self, role):
        email = f"{role}@abstractly.test"
        from app.auth import hash_password
        user_id = database.create_user(email, role.title(), hash_password("x"), role=role, team_id=self.team_id)["id"]
        client = app.test_client()
        with client.session_transaction() as sess:
            sess.update(user_id=user_id, team_id=self.team_id, email=email, name=role.title(), role=role, is_owner=False)
            sync_session_user(sess)
        return client

    def __exit__(self, *exc):
        anthropic.Anthropic = self.old_anthropic
        if self.old_flag is None:
            os.environ.pop(FLAG_ENV, None)
        else:
            os.environ[FLAG_ENV] = self.old_flag
        os.unlink(self.db_path)
        return False


def _s8_counts(team_id):
    return {t: len(database.list_section8_records(t, team_id, include_archived=True)) for t in S8_TABLES}


def _ai_runs():
    conn = database.get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM ai_extraction_runs").fetchone()[0]
    finally:
        conn.close()


def _by_unit(env, path):
    """GET /section8/<path> keyed by (property name, unit label)."""
    units = {u["id"]: u for u in env.analyst.get("/section8/units").get_json()}
    props = {p["id"]: p["name"] for p in env.analyst.get("/section8/properties").get_json()}
    out = {}
    for row in env.analyst.get(f"/section8/{path}").get_json():
        u = units[row["unit_id"]]
        out.setdefault((props[u["property_id"]], u["unit_label"]), []).append(row)
    return out


def test_flag_off_loads_maple_ridge_unchanged():
    with open(MAPLE_PATH) as f:
        maple_count = len(json.load(f))
    with _Env(flag=False) as env:
        resp = env.analyst.post("/sample-deal/load")
        assert resp.status_code == 201, resp.get_json()
        body = resp.get_json()
        assert body["lease_count"] == maple_count and body["sample_name"] == "Maple Ridge sample deal", body
        assert _s8_counts(env.team_id) == {t: 0 for t in S8_TABLES}
        # A second Maple Ridge load still works exactly as before (fresh copy, no 409).
        assert env.analyst.post("/sample-deal/load").status_code == 201
    print("✓ test_flag_off_loads_maple_ridge_unchanged: PASS")


def test_flag_on_loads_section8_portfolio_into_callers_team():
    rec = CAPTURE["records"]
    with _Env() as env:
        resp = env.analyst.post("/sample-deal/load")
        assert resp.status_code == 201, resp.get_json()
        body = resp.get_json()
        assert body["sample_name"] == CAPTURE["name"]
        assert body["lease_count"] == len(CAPTURE["documents"])
        counts = _s8_counts(env.team_id)
        assert counts["phas"] == 1
        assert counts["properties"] == len(rec["properties"]) == 2
        assert counts["units"] == len(rec["units"]) == 32
        assert counts["tenancies"] == len(rec["tenancies"])
        assert counts["hap_contracts"] == len(rec["hap_contracts"]) == 3 + 6 + 4
        assert counts["unit_documents"] == body["counts"]["unit_documents"] > 0
        leases = env.analyst.get("/leases").get_json()
        assert len(leases) == len(CAPTURE["documents"])
        assert all("Sample" in l.get("tags", []) for l in leases), "every sample document is tagged Sample"
        # Every Section 8 row belongs to the caller's team (nothing landed on Legacy or elsewhere).
        conn = database.get_connection()
        try:
            for t in S8_TABLES:
                teams = {r[0] for r in conn.execute(f"SELECT DISTINCT team_id FROM {t}")}
                assert teams == {env.team_id}, (t, teams)
        finally:
            conn.close()
        assert _ai_runs() == 0
    print("✓ test_flag_on_loads_section8_portfolio_into_callers_team: PASS")


def test_planted_errors_survive_into_the_records():
    with _Env() as env:
        assert env.analyst.post("/sample-deal/load").status_code == 201
        ten = _by_unit(env, "tenancies")
        con = _by_unit(env, "hap-contracts")
        jr, bt = "Juniper Row Apartments", "Bellmont Terrace"

        # S8-06: roll/tenancy rent $1,295 vs HAP contract rent to owner $1,250.
        assert "S8-06" in ANSWER_KEY
        t104 = ten[(jr, "104")][0]
        assert (t104["contract_rent"], t104["tenant_rent"], t104["hap"]) == ("1295.00", "355.00", "940.00"), t104
        assert con[(jr, "104")][0]["contract_rent"] == "1250.00"
        # S8-03: roll still shows the pre-interim split.
        assert "S8-03" in ANSWER_KEY
        t206 = ten[(jr, "206")][0]
        assert (t206["tenant_rent"], t206["hap"]) == ("245.00", "1050.00"), t206
        # S8-17: moved out 08/31/2026 -> a past tenancy, unit vacant.
        assert "S8-17" in ANSWER_KEY
        t112 = ten[(jr, "112")][0]
        assert t112["status"] == "past" and t112["move_out_date"] == "2026-08-31", t112
        # S8-08: PBRA contract ended 08/31/2026 but is still recorded active (what the documents say).
        assert "S8-08" in ANSWER_KEY
        pbra = [c for k, rows in con.items() for c in rows if c["contract_type"] == "PBRA"]
        assert len(pbra) == 4 and {c["end_date"] for c in pbra} == {"2026-08-31"}
        assert {c["status"] for c in pbra} == {"active"}
        # S8-02: tenant share entered as the full rent on the October RealPage roll.
        assert "S8-02" in ANSWER_KEY
        t3b = ten[(bt, "3B")][0]
        assert (t3b["contract_rent"], t3b["hap"]) == ("287.00", "0.00"), t3b
        # S8-20: 3A booked as PBV with HAP, but no PBV contract row for it.
        assert "S8-20" in ANSWER_KEY
        assert ten[(bt, "3A")][0]["hap"] == "840.00" and (bt, "3A") not in con
        # Clean control: JR 214 agrees everywhere.
        t214 = ten[(jr, "214")][0]
        assert (t214["contract_rent"], t214["tenant_rent"], t214["hap"]) == ("1260.00", "355.00", "905.00")
    print("✓ test_planted_errors_survive_into_the_records: PASS")


def test_second_load_is_409_and_inserts_nothing():
    with _Env() as env:
        assert env.analyst.post("/sample-deal/load").status_code == 201
        before = (_s8_counts(env.team_id), len(env.analyst.get("/leases").get_json()))
        resp = env.analyst.post("/sample-deal/load")
        assert resp.status_code == 409, resp.get_json()
        assert "already loaded" in resp.get_json()["error"]
        assert (_s8_counts(env.team_id), len(env.analyst.get("/leases").get_json())) == before
    print("✓ test_second_load_is_409_and_inserts_nothing: PASS")


def test_failure_mid_load_leaves_nothing_behind_and_retry_is_clean():
    """Regression (reviewer FIX FIRST): a failure partway through used to leave 65 orphan Sample documents, and a retry then inserted 65 more."""
    with _Env() as env:
        real_create = database.create_section8_record

        def fail_late(table, team_id, values):
            # The 41st unit-document link: after every document and every
            # other record exists -- so this proves the rollback covers all of them.
            if table == "unit_documents":
                fail_late.calls += 1
                if fail_late.calls == 41:
                    raise RuntimeError("simulated failure mid-load")
            return real_create(table, team_id, values)

        fail_late.calls = 0
        database.create_section8_record = fail_late
        try:
            try:
                sample_deal.load_section8_sample(env.team_id)
                raise AssertionError("expected the simulated failure to propagate")
            except RuntimeError:
                pass
        finally:
            database.create_section8_record = real_create
        assert database.get_all_leases(env.team_id, document_type=None) == [], "orphan sample documents left behind"
        assert _s8_counts(env.team_id) == {t: 0 for t in S8_TABLES}, "partial Section 8 rows left behind"
        resp = env.analyst.post("/sample-deal/load")
        assert resp.status_code == 201, resp.get_json()
        assert len(database.get_all_leases(env.team_id, document_type=None)) == len(CAPTURE["documents"])
    print("✓ test_failure_mid_load_leaves_nothing_behind_and_retry_is_clean: PASS")


def test_concurrent_second_load_is_409_not_500_and_adds_nothing():
    """Regression (reviewer + security-auditor): two loads that both pass the pre-check (double click / two tabs). The loser must get a clean 409 and insert nothing, not a 500 with 65 orphan documents."""
    with _Env() as env:
        assert env.analyst.post("/sample-deal/load").status_code == 201
        before = (_s8_counts(env.team_id), len(database.get_all_leases(env.team_id, document_type=None)))
        real_check = sample_deal.section8_sample_loaded
        calls = []

        def stale_precheck(team_id):
            # The first (pre-)check runs before the other request committed;
            # later checks see the truth.
            calls.append(team_id)
            return False if len(calls) == 1 else real_check(team_id)

        sample_deal.section8_sample_loaded = stale_precheck
        try:
            resp = env.analyst.post("/sample-deal/load")
        finally:
            sample_deal.section8_sample_loaded = real_check
        assert resp.status_code == 409, (resp.status_code, resp.get_json())
        assert (_s8_counts(env.team_id), len(database.get_all_leases(env.team_id, document_type=None))) == before
    print("✓ test_concurrent_second_load_is_409_not_500_and_adds_nothing: PASS")


def test_race_lost_at_the_pha_claim_is_409_not_500():
    """Regression (re-review, low): the other request has created the sample PHA but not its properties yet. The loser's PHA insert hits the unique name -- that must be a 409 and leave nothing behind, not a 500."""
    with _Env() as env:
        sample_pha = CAPTURE["records"]["pha"]["name"]
        database.create_section8_record("phas", env.team_id, {"name": sample_pha})  # the winner's half-done claim
        resp = env.analyst.post("/sample-deal/load")
        assert resp.status_code == 409, (resp.status_code, resp.get_json())
        assert database.get_all_leases(env.team_id, document_type=None) == []
        assert _s8_counts(env.team_id)["properties"] == 0
    print("✓ test_race_lost_at_the_pha_claim_is_409_not_500: PASS")


def test_viewer_cannot_load_either_sample():
    with _Env() as env:
        assert env.viewer.post("/sample-deal/load").status_code == 403
        assert env.viewer.post("/leases/sample").status_code == 403
        assert _s8_counts(env.team_id)["units"] == 0
    print("✓ test_viewer_cannot_load_either_sample: PASS")


def test_single_sample_lease_is_the_voucher_control_when_flag_on():
    with _Env() as env:
        resp = env.analyst.post("/leases/sample")
        assert resp.status_code == 201, resp.get_json()
        body = resp.get_json()
        assert body["split_count"] == len(CAPTURE["single_lease"])
        names = [l.get("display_name") or "" for l in body["leases"]]
        assert all("quellwater" in n.lower() for n in names), names
        assert all(l["tags"] == ["Sample"] for l in body["leases"])
        # Loading it twice works (it's a fresh copy, like today) and the cached fixture isn't mutated.
        assert env.analyst.post("/leases/sample").status_code == 201
        assert all("lease_id" not in x for x in sample_deal.section8_single_lease())
    with _Env(flag=False) as env:
        resp = env.analyst.post("/leases/sample")
        # Flag off: today's behaviour (the commercial sample, or 503 where that fixture isn't installed).
        assert resp.status_code in (201, 503)
        if resp.status_code == 201:
            assert not any("quellwater" in (l.get("display_name") or "").lower() for l in resp.get_json()["leases"])
    print("✓ test_single_sample_lease_is_the_voucher_control_when_flag_on: PASS")


def test_demo_seed_and_reset_with_section8_mode():
    from app import demo_seed
    with _Env() as env:
        legacy = database.get_team_by_name("Legacy")["id"]
        demo_seed.seed_demo_data()
        first = _s8_counts(legacy)
        assert first["units"] == 32 and first["hap_contracts"] == 13, first
        assert len(database.get_all_leases(legacy, document_type=None)) == len(CAPTURE["documents"])
        demo_seed.seed_demo_data()  # restart: no-op
        assert _s8_counts(legacy) == first
        demo_seed.reset_demo_data()  # wipes (Section 8 tables included) and reseeds
        assert _s8_counts(legacy) == first
        assert len(database.get_all_leases(legacy, document_type=None)) == len(CAPTURE["documents"])
        assert _ai_runs() == 0
    with _Env(flag=False) as env:
        legacy = database.get_team_by_name("Legacy")["id"]
        demo_seed.seed_demo_data()
        assert len(database.get_all_leases(legacy, document_type=None)) == 4  # today's 2 leases + 2 roll rows
        assert _s8_counts(legacy)["units"] == 0
    print("✓ test_demo_seed_and_reset_with_section8_mode: PASS")


def test_demo_reset_clears_section8_rows_children_first():
    """Demo reset deletes every Section 8 row (it's the demo DB), in FK-safe order -- no IntegrityError, nothing left behind."""
    from app import demo_seed
    with _Env() as env:
        assert env.analyst.post("/sample-deal/load").status_code == 201
        demo_seed.reset_demo_data()
        assert _s8_counts(env.team_id) == {t: 0 for t in S8_TABLES}
    print("✓ test_demo_reset_clears_section8_rows_children_first: PASS")


def test_capture_matches_current_fixture_files():
    for rel, digest in CAPTURE["fixture_sha256"].items():
        with open(os.path.join(FIXTURES, rel), "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == digest, (
                f"{rel} changed since the sample was captured -- re-run "
                "benchmark_data/section8_sample/capture_section8_sample.py and commit")
    # Every planted unit the tests above rely on is in the capture's records.
    unit_keys = {u["key"] for u in CAPTURE["records"]["units"]}
    for key in ("unit:JR:104", "unit:JR:206", "unit:JR:112", "unit:JR:214", "unit:BT:3B", "unit:BT:3A", "unit:BT:1A"):
        assert key in unit_keys, key
    print("✓ test_capture_matches_current_fixture_files: PASS")


if __name__ == "__main__":
    test_flag_off_loads_maple_ridge_unchanged()
    test_flag_on_loads_section8_portfolio_into_callers_team()
    test_planted_errors_survive_into_the_records()
    test_second_load_is_409_and_inserts_nothing()
    test_failure_mid_load_leaves_nothing_behind_and_retry_is_clean()
    test_concurrent_second_load_is_409_not_500_and_adds_nothing()
    test_race_lost_at_the_pha_claim_is_409_not_500()
    test_viewer_cannot_load_either_sample()
    test_single_sample_lease_is_the_voucher_control_when_flag_on()
    test_demo_seed_and_reset_with_section8_mode()
    test_demo_reset_clears_section8_rows_children_first()
    test_capture_matches_current_fixture_files()
    print("\nAll Section 8 sample data tests passed.")
