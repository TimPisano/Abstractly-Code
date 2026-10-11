"""
Section 8 data model (feature/s8-data-model): SECTION8_MODE flag,
roles, CRUD round trips (money in dollars <-> integer cents), input
validation, uniqueness, the one-current-tenancy rule, archive instead
of delete, the unit detail view, and the address backfill.

Cross-team cases live in test_team_isolation.py with the rest of the
isolation suite. Temp SQLite + Flask test client; no network, no
Anthropic.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.section8_mode import FLAG_ENV
from _session_users import sync_session_user


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _client(user_id, team_id, role):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["team_id"] = team_id
        sess["email"] = f"user{user_id}@abstractly.test"
        sess["name"] = f"User {user_id}"
        sess["role"] = role
        sess["is_owner"] = False
        sync_session_user(sess)
    return client


class _Env:
    """Temp DB + SECTION8_MODE on (unless flag=False); restores both."""

    def __init__(self, flag=True):
        self.flag = flag

    def __enter__(self):
        self.db_path = _fresh_temp_db()
        self.old_flag = os.environ.get(FLAG_ENV)
        if self.flag:
            os.environ[FLAG_ENV] = "true"
        else:
            os.environ.pop(FLAG_ENV, None)
        self.team_id = database.create_team("S8 Team")["id"]
        self.admin = _client(9001, self.team_id, "admin")
        self.analyst = _client(9002, self.team_id, "analyst")
        self.viewer = _client(9003, self.team_id, "viewer")
        return self

    def __exit__(self, *exc):
        if self.old_flag is None:
            os.environ.pop(FLAG_ENV, None)
        else:
            os.environ[FLAG_ENV] = self.old_flag
        os.unlink(self.db_path)
        return False


def _post(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json")


def _patch(client, path, body):
    return client.patch(path, data=json.dumps(body), content_type="application/json")


def _make_basics(env):
    """PHA + property + unit, via the API. Returns their ids."""
    pha = _post(env.analyst, "/section8/phas", {"name": "Harrow County Housing Authority", "payment_day": 1})
    assert pha.status_code == 201, pha.get_json()
    prop = _post(env.analyst, "/section8/properties", {"name": "Juniper Row", "address": "400 Juniper Row, Harrow, OH", "program": "HCV"})
    assert prop.status_code == 201, prop.get_json()
    unit = _post(env.analyst, "/section8/units", {"property_id": prop.get_json()["id"], "unit_label": "101", "address": "400 Juniper Row Unit 101, Harrow, OH", "bedrooms": 2})
    assert unit.status_code == 201, unit.get_json()
    return pha.get_json()["id"], prop.get_json()["id"], unit.get_json()["id"]


def _seed_lease(team_id, filename, address, tenant="A Tenant", rent="$1,400.00", extra=None):
    fields = {
        "tenant": {"value": tenant, "confidence": "high"},
        "rent_amount": {"value": rent, "confidence": "high"},
    }
    if address is not None:
        fields["property_address"] = {"value": address, "confidence": "high"}
    fields.update(extra or {})
    return database.insert_lease(filename, fields, team_id=team_id)


ALL_ROUTES = [
    ("GET", "/section8/phas"), ("POST", "/section8/phas"),
    ("GET", "/section8/phas/1"), ("PATCH", "/section8/phas/1"),
    ("GET", "/section8/properties"), ("POST", "/section8/properties"),
    ("GET", "/section8/properties/1"), ("PATCH", "/section8/properties/1"),
    ("GET", "/section8/units"), ("POST", "/section8/units"),
    ("GET", "/section8/units/1"), ("PATCH", "/section8/units/1"),
    ("GET", "/section8/tenancies"), ("POST", "/section8/tenancies"),
    ("GET", "/section8/tenancies/1"), ("PATCH", "/section8/tenancies/1"),
    ("GET", "/section8/hap-contracts"), ("POST", "/section8/hap-contracts"),
    ("GET", "/section8/hap-contracts/1"), ("PATCH", "/section8/hap-contracts/1"),
    ("POST", "/section8/units/1/documents"), ("PATCH", "/section8/unit-documents/1"),
    ("POST", "/section8/backfill"),
]


def _call(client, method, path):
    if method == "GET":
        return client.get(path)
    if method == "POST":
        return _post(client, path, {})
    return _patch(client, path, {})


# ------------------------------------------------------------------ flag

def test_every_route_404s_when_flag_off_even_logged_out():
    with _Env(flag=False) as env:
        anon = app.test_client()
        for method, path in ALL_ROUTES:
            for client in (env.admin, anon):
                resp = _call(client, method, path)
                assert resp.status_code == 404, f"{method} {path} must 404 with SECTION8_MODE off, got {resp.status_code}"
    print("✓ test_every_route_404s_when_flag_off_even_logged_out: PASS")


def test_flag_values():
    from app.section8_mode import section8_mode_enabled
    old = os.environ.get(FLAG_ENV)
    try:
        for value, expected in [("true", True), ("1", True), ("ON", True), ("yes", True),
                                ("", False), ("false", False), ("0", False), ("nope", False)]:
            os.environ[FLAG_ENV] = value
            assert section8_mode_enabled() is expected, value
        os.environ.pop(FLAG_ENV, None)
        assert section8_mode_enabled() is False, "default must be off"
    finally:
        if old is None:
            os.environ.pop(FLAG_ENV, None)
        else:
            os.environ[FLAG_ENV] = old
    print("✓ test_flag_values: PASS")


def test_tables_exist_even_with_flag_off_and_reset_db_works():
    with _Env(flag=False):
        conn = database.get_connection()
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        for table in database.SECTION8_TABLES_DROP_ORDER:
            assert table in names, table
        database.reset_db()  # must not trip a foreign key on teams
    print("✓ test_tables_exist_even_with_flag_off_and_reset_db_works: PASS")


# ----------------------------------------------------------------- roles

def test_roles():
    with _Env() as env:
        anon = app.test_client()
        assert anon.get("/section8/phas").status_code == 401
        assert env.viewer.get("/section8/phas").status_code == 200
        for path in ("/section8/phas", "/section8/properties", "/section8/units", "/section8/tenancies",
                     "/section8/hap-contracts", "/section8/units/1/documents"):
            assert _post(env.viewer, path, {}).status_code == 403, path
        assert _patch(env.viewer, "/section8/phas/1", {}).status_code == 403
        assert _post(env.analyst, "/section8/backfill", {}).status_code == 403, "backfill is admin-only"
        assert _post(env.admin, "/section8/backfill", {}).status_code == 200
    print("✓ test_roles: PASS")


def test_no_delete_routes():
    with _Env() as env:
        pha_id, prop_id, unit_id = _make_basics(env)
        for path in (f"/section8/phas/{pha_id}", f"/section8/properties/{prop_id}", f"/section8/units/{unit_id}"):
            assert env.admin.delete(path).status_code == 405, path
    print("✓ test_no_delete_routes: PASS")


# ------------------------------------------------------------------ CRUD

def test_pha_crud_and_settings():
    with _Env() as env:
        resp = _post(env.analyst, "/section8/phas", {
            "name": "Harrow County Housing Authority", "short_name": "HCHA", "inspection_standard": "NSPIRE-V",
            "payment_day": 3, "rent_increase_notice_days": 60, "settings": {"cure_days_non_lt": 30},
            "team_id": 999, "id": 12345, "created_at": "1999-01-01",
        })
        assert resp.status_code == 201, resp.get_json()
        pha = resp.get_json()
        assert pha["short_name"] == "HCHA" and pha["payment_day"] == 3
        assert pha["settings"] == {"cure_days_non_lt": 30}
        assert "team_id" not in pha and pha["id"] != 12345 and pha["created_at"] != "1999-01-01", "body must not set managed columns"
        assert database.get_section8_record("phas", pha["id"], env.team_id)["team_id"] == env.team_id

        resp = _patch(env.analyst, f"/section8/phas/{pha['id']}", {"payment_day": 5, "notes": "calls back slowly"})
        assert resp.status_code == 200 and resp.get_json()["payment_day"] == 5
        assert env.viewer.get(f"/section8/phas/{pha['id']}").get_json()["notes"] == "calls back slowly"
        assert env.viewer.get("/section8/phas/99999").status_code == 404
    print("✓ test_pha_crud_and_settings: PASS")


def test_tenancy_money_round_trip_in_cents():
    with _Env() as env:
        pha_id, _, unit_id = _make_basics(env)
        resp = _post(env.analyst, "/section8/tenancies", {
            "unit_id": unit_id, "pha_id": pha_id, "program": "HCV", "head_of_household": "R. Brennaway",
            "move_in_date": "2026-03-01", "contract_rent": "1,400.00", "tenant_rent": 412, "hap": "988.00",
            "utility_allowance": "$75.50",
        })
        assert resp.status_code == 201, resp.get_json()
        t = resp.get_json()
        assert (t["contract_rent"], t["tenant_rent"], t["hap"], t["utility_allowance"]) == ("1400.00", "412.00", "988.00", "75.50")
        assert t["status"] == "current"
        row = database.get_section8_record("tenancies", t["id"], env.team_id)
        assert (row["contract_rent_cents"], row["tenant_rent_cents"], row["hap_cents"], row["utility_allowance_cents"]) == (140000, 41200, 98800, 7550)

        # 0.1 + 0.2 style float input must still land on exact cents.
        resp = _patch(env.analyst, f"/section8/tenancies/{t['id']}", {"hap": 988.3})
        assert resp.status_code == 200 and resp.get_json()["hap"] == "988.30"
        assert database.get_section8_record("tenancies", t["id"], env.team_id)["hap_cents"] == 98830
    print("✓ test_tenancy_money_round_trip_in_cents: PASS")


def test_validation_rejects_bad_input():
    with _Env() as env:
        pha_id, prop_id, unit_id = _make_basics(env)
        bad = [
            ("/section8/phas", {}, "name"),
            ("/section8/phas", {"name": "X", "payment_day": 0}, "payment_day"),
            ("/section8/phas", {"name": "X", "payment_day": 32}, "payment_day"),
            ("/section8/phas", {"name": "X", "payment_day": "3"}, "payment_day"),
            ("/section8/phas", {"name": "X", "inspection_standard": "UPCS"}, "inspection_standard"),
            ("/section8/phas", {"name": "X", "settings": [1, 2]}, "settings"),
            ("/section8/phas", {"name": "x" * 501}, "name"),
            ("/section8/properties", {"name": "P", "program": "LIHTC"}, "program"),
            ("/section8/units", {"unit_label": "9"}, "property_id"),
            ("/section8/units", {"property_id": "1", "unit_label": "9"}, "property_id"),
            ("/section8/tenancies", {"unit_id": unit_id, "hap": -1}, "negative"),
            ("/section8/tenancies", {"unit_id": unit_id, "hap": "12.345"}, "decimal"),
            ("/section8/tenancies", {"unit_id": unit_id, "hap": "NaN"}, "hap"),
            ("/section8/tenancies", {"unit_id": unit_id, "hap": "Infinity"}, "hap"),
            ("/section8/tenancies", {"unit_id": unit_id, "hap": True}, "hap"),
            ("/section8/tenancies", {"unit_id": unit_id, "hap": "lots"}, "hap"),
            ("/section8/tenancies", {"unit_id": unit_id, "move_in_date": "03/01/2026"}, "move_in_date"),
            ("/section8/tenancies", {"unit_id": unit_id, "move_in_date": "2026-02-30"}, "move_in_date"),
            ("/section8/tenancies", {"unit_id": unit_id, "move_in_date": "2026-05-01", "move_out_date": "2026-04-01"}, "move_out_date"),
            ("/section8/tenancies", {"unit_id": unit_id, "status": "evicted"}, "status"),
            ("/section8/hap-contracts", {}, "contract_type"),
            ("/section8/hap-contracts", {"contract_type": "HCV", "start_date": "2026-05-01", "end_date": "2025-04-30"}, "end_date"),
        ]
        for path, body, hint in bad:
            resp = _post(env.analyst, path, body)
            assert resp.status_code == 400, f"{path} {body} -> {resp.status_code} {resp.get_json()}"
            assert hint.lower() in resp.get_json()["error"].lower(), f"{path} {body}: {resp.get_json()}"

        # Required field can't be blanked on update; immutable keys can't move.
        assert _patch(env.analyst, f"/section8/phas/{pha_id}", {"name": ""}).status_code == 400
        assert _patch(env.analyst, f"/section8/units/{unit_id}", {"property_id": prop_id}).status_code == 400
        assert _patch(env.analyst, f"/section8/phas/{pha_id}", {"archived": "yes"}).status_code == 400
        # Non-object body.
        resp = env.analyst.post("/section8/phas", data="[1]", content_type="application/json")
        assert resp.status_code == 400
    print("✓ test_validation_rejects_bad_input: PASS")


def test_hap_contract_consistency_checks():
    with _Env() as env:
        pha_id, prop_id, unit_id = _make_basics(env)
        other_prop = _post(env.analyst, "/section8/properties", {"name": "Bellmont Terrace", "address": "9 Bellmont Ter, Harrow, OH"}).get_json()["id"]
        resp = _post(env.analyst, "/section8/hap-contracts", {"contract_type": "HCV", "unit_id": unit_id, "property_id": other_prop})
        assert resp.status_code == 400 and "property" in resp.get_json()["error"]

        resp = _post(env.analyst, "/section8/hap-contracts", {
            "contract_type": "HCV", "pha_id": pha_id, "unit_id": unit_id, "property_id": prop_id,
            "contract_number": "HCHA-2026-0101", "form": "HUD-52641", "start_date": "2026-03-01",
            "end_date": "2027-02-28", "contract_rent": "1400", "initial_hap": "988",
        })
        assert resp.status_code == 201, resp.get_json()
        c = resp.get_json()
        assert c["status"] == "active" and c["contract_rent"] == "1400.00" and c["initial_hap"] == "988.00"
        assert _patch(env.analyst, f"/section8/hap-contracts/{c['id']}", {"end_date": "2026-01-01"}).status_code == 400
        assert _patch(env.analyst, f"/section8/hap-contracts/{c['id']}", {"status": None}).status_code == 400
        assert env.viewer.get(f"/section8/hap-contracts?unit_id={unit_id}").get_json()[0]["id"] == c["id"]
        assert env.viewer.get("/section8/hap-contracts?unit_id=abc").status_code == 400
    print("✓ test_hap_contract_consistency_checks: PASS")


# ------------------------------------------------------- uniqueness rules

def test_uniqueness_conflicts_are_409():
    with _Env() as env:
        pha_id, prop_id, unit_id = _make_basics(env)
        assert _post(env.analyst, "/section8/phas", {"name": "Harrow County Housing Authority"}).status_code == 409
        # Same building, differently written, is still the same property.
        assert _post(env.analyst, "/section8/properties", {"name": "Dup", "address": "400 JUNIPER ROW,  Harrow, OH."}).status_code == 409
        assert _post(env.analyst, "/section8/units", {"property_id": prop_id, "unit_label": "101 again", "address": "400 Juniper Row Unit 101, Harrow, OH"}).status_code == 409
        # Properties/units without an address don't collide with each other.
        assert _post(env.analyst, "/section8/properties", {"name": "No address 1"}).status_code == 201
        assert _post(env.analyst, "/section8/properties", {"name": "No address 2"}).status_code == 201
    print("✓ test_uniqueness_conflicts_are_409: PASS")


def test_one_current_tenancy_per_unit():
    with _Env() as env:
        _, _, unit_id = _make_basics(env)
        first = _post(env.analyst, "/section8/tenancies", {"unit_id": unit_id, "head_of_household": "First", "move_in_date": "2025-01-01"})
        assert first.status_code == 201
        second = _post(env.analyst, "/section8/tenancies", {"unit_id": unit_id, "head_of_household": "Second", "move_in_date": "2026-06-01"})
        assert second.status_code == 409 and "end_current" in second.get_json()["error"]
        assert _post(env.analyst, "/section8/tenancies", {"unit_id": unit_id, "end_current": "yes"}).status_code == 400

        # A past tenancy can always be recorded.
        assert _post(env.analyst, "/section8/tenancies", {"unit_id": unit_id, "status": "past", "head_of_household": "Older"}).status_code == 201

        second = _post(env.analyst, "/section8/tenancies", {"unit_id": unit_id, "head_of_household": "Second", "move_in_date": "2026-06-01", "end_current": True})
        assert second.status_code == 201, second.get_json()
        old = env.viewer.get(f"/section8/tenancies/{first.get_json()['id']}").get_json()
        assert old["status"] == "past" and old["move_out_date"] == "2026-06-01"

        # Flipping the old one back to current while another is current -> 409 (index-enforced).
        resp = _patch(env.analyst, f"/section8/tenancies/{first.get_json()['id']}", {"status": "current"})
        assert resp.status_code == 409
        current = env.viewer.get(f"/section8/tenancies?unit_id={unit_id}&status=current").get_json()
        assert [t["head_of_household"] for t in current] == ["Second"]
    print("✓ test_one_current_tenancy_per_unit: PASS")


# --------------------------------------------------------------- archive

def test_archive_hides_from_lists_and_unarchive_restores():
    with _Env() as env:
        pha_id, _, _ = _make_basics(env)
        resp = _patch(env.analyst, f"/section8/phas/{pha_id}", {"archived": True})
        assert resp.status_code == 200 and resp.get_json()["archived"] is True
        assert env.viewer.get("/section8/phas").get_json() == []
        assert len(env.viewer.get("/section8/phas?include_archived=1").get_json()) == 1
        assert env.viewer.get(f"/section8/phas/{pha_id}").status_code == 200, "by-id read still works"
        resp = _patch(env.analyst, f"/section8/phas/{pha_id}", {"archived": False})
        assert resp.get_json()["archived"] is False
        assert len(env.viewer.get("/section8/phas").get_json()) == 1
    print("✓ test_archive_hides_from_lists_and_unarchive_restores: PASS")


# ----------------------------------------------------- unit detail + links

def test_unit_detail_shows_tenancy_contracts_and_documents():
    with _Env() as env:
        pha_id, prop_id, unit_id = _make_basics(env)
        lease_id = _seed_lease(env.team_id, "lease_101.pdf", "400 Juniper Row Unit 101, Harrow, OH")
        tenancy = _post(env.analyst, "/section8/tenancies", {"unit_id": unit_id, "pha_id": pha_id, "hap": "988"}).get_json()
        contract = _post(env.analyst, "/section8/hap-contracts", {"contract_type": "HCV", "unit_id": unit_id, "tenancy_id": tenancy["id"]}).get_json()

        link = _post(env.analyst, f"/section8/units/{unit_id}/documents", {"lease_id": lease_id, "doc_kind": "lease", "tenancy_id": tenancy["id"]})
        assert link.status_code == 201, link.get_json()
        assert link.get_json()["linked_by"] == "user"
        assert _post(env.analyst, f"/section8/units/{unit_id}/documents", {"lease_id": lease_id, "doc_kind": "lease"}).status_code == 409
        assert _post(env.analyst, f"/section8/units/{unit_id}/documents", {"lease_id": 99999, "doc_kind": "lease"}).status_code == 404
        assert _post(env.analyst, f"/section8/units/{unit_id}/documents", {"lease_id": lease_id, "doc_kind": "deed"}).status_code == 400

        detail = env.viewer.get(f"/section8/units/{unit_id}").get_json()
        assert detail["current_tenancy"]["id"] == tenancy["id"] and detail["current_tenancy"]["hap"] == "988.00"
        assert [c["id"] for c in detail["hap_contracts"]] == [contract["id"]]
        assert detail["documents"][0]["filename"] == "lease_101.pdf" and detail["documents"][0]["doc_kind"] == "lease"
        assert detail["status"] == "unknown"

        resp = _patch(env.analyst, f"/section8/unit-documents/{link.get_json()['id']}", {"doc_kind": "tenancy_addendum"})
        assert resp.status_code == 200 and resp.get_json()["doc_kind"] == "tenancy_addendum"
        assert _patch(env.analyst, f"/section8/unit-documents/{link.get_json()['id']}", {"lease_id": lease_id}).status_code == 400

        # A tenancy from a different unit can't be attached here.
        other_unit = _post(env.analyst, "/section8/units", {"property_id": prop_id, "unit_label": "102"}).get_json()["id"]
        other_tenancy = _post(env.analyst, "/section8/tenancies", {"unit_id": other_unit}).get_json()["id"]
        lease2 = _seed_lease(env.team_id, "lease_102.pdf", "400 Juniper Row Unit 102, Harrow, OH")
        resp = _post(env.analyst, f"/section8/units/{unit_id}/documents", {"lease_id": lease2, "doc_kind": "lease", "tenancy_id": other_tenancy})
        assert resp.status_code == 400

        prop = env.viewer.get(f"/section8/properties/{prop_id}").get_json()
        assert prop["unit_count"] == 2
    print("✓ test_unit_detail_shows_tenancy_contracts_and_documents: PASS")


# ---------------------------------------------------------------- backfill

def _lease_snapshot(team_id):
    conn = database.get_connection()
    try:
        return [tuple(r) for r in conn.execute("SELECT * FROM leases WHERE team_id = ? ORDER BY id", (team_id,))]
    finally:
        conn.close()


def test_backfill_dry_run_apply_idempotent_and_leases_untouched():
    with _Env() as env:
        t = env.team_id
        # Building 1: three units, mix of lease PDFs and rent-roll rows.
        l101 = _seed_lease(t, "lease_101.pdf", "400 Juniper Row, Unit 101, Harrow, OH")
        r101 = _seed_lease(t, "juniper_rent_roll.csv", "400 Juniper Row Unit 101, Harrow, OH")
        _seed_lease(t, "juniper_rent_roll.csv", "400 Juniper Row Unit 104, Harrow, OH")
        _seed_lease(t, "lease_203.pdf", "400 Juniper Row Apt 203, Harrow, OH",
                    extra={"unit_number": {"value": "203", "confidence": "high"}})
        # Building 2: two units.
        _seed_lease(t, "bellmont_roll.xlsx", "9 Bellmont Terrace #2A, Harrow, OH")
        _seed_lease(t, "bellmont_roll.xlsx", "9 Bellmont Terrace #2C, Harrow, OH")
        # No address -> skipped with a reason.
        no_addr = _seed_lease(t, "mystery.pdf", None)
        # Amendment of l101 -> not its own unit document.
        database.insert_lease("amendment.pdf", {"property_address": {"value": "400 Juniper Row Unit 101, Harrow, OH"}},
                              team_id=t, document_type="amendment", base_lease_id=l101)

        before = _lease_snapshot(t)

        dry = _post(env.admin, "/section8/backfill", {})
        assert dry.status_code == 200, dry.get_json()
        d = dry.get_json()
        assert d["applied"] is False
        assert len(d["properties_to_create"]) == 2, d
        assert len(d["units_to_create"]) == 5, d
        assert d["links_to_create"] == 6, d
        assert [s["lease_id"] for s in d["skipped"]] == [no_addr] and d["skipped"][0]["reason"] == "no property address"
        assert database.list_section8_records("properties", t) == [] and database.list_section8_records("units", t) == [], "dry run must write nothing"

        applied = _post(env.admin, "/section8/backfill", {"apply": True}).get_json()
        assert applied["created"] == {"properties": 2, "units": 5, "links": 6}

        units = database.list_section8_records("units", t)
        assert len(units) == 5
        assert {u["status"] for u in units} == {"unknown"}, "backfilled units are always 'unknown' (user decision 2026-10-11)"
        assert "203" in {u["unit_label"] for u in units}, "unit_number field wins for the label"
        assert any(u["unit_label"].lower().startswith("unit 101") for u in units)

        links = database.list_section8_records("unit_documents", t)
        kinds = {l["lease_id"]: l["doc_kind"] for l in links}
        assert kinds[l101] == "lease" and kinds[r101] == "rent_roll_row"
        assert {l["linked_by"] for l in links} == {"backfill"}
        unit_of = {l["lease_id"]: l["unit_id"] for l in links}
        assert unit_of[l101] == unit_of[r101], "lease PDF and rent-roll row for unit 101 land on the same unit"

        again = _post(env.admin, "/section8/backfill", {"apply": True}).get_json()
        assert again["created"] == {"properties": 0, "units": 0, "links": 0}, "re-run must be a no-op"

        assert _lease_snapshot(t) == before, "backfill must never modify a lease row"

        assert _post(env.admin, "/section8/backfill", {"apply": "yes"}).status_code == 400
        activity = env.viewer.get("/activity").get_json()
        assert any("Section 8 backfill" in json.dumps(a) for a in (activity if isinstance(activity, list) else activity.get("activity", [])))
    print("✓ test_backfill_dry_run_apply_idempotent_and_leases_untouched: PASS")


def test_backfill_reuses_manually_created_property_and_unit():
    with _Env() as env:
        t = env.team_id
        _, prop_id, unit_id = _make_basics(env)  # 400 Juniper Row / unit 101 created by hand
        lease_id = _seed_lease(t, "lease_101.pdf", "400 Juniper Row Unit 101, Harrow, OH")
        result = _post(env.admin, "/section8/backfill", {"apply": True}).get_json()
        assert result["created"] == {"properties": 0, "units": 0, "links": 1}, result
        links = database.list_section8_records("unit_documents", t)
        assert links[0]["lease_id"] == lease_id and links[0]["unit_id"] == unit_id
    print("✓ test_backfill_reuses_manually_created_property_and_unit: PASS")


if __name__ == "__main__":
    test_every_route_404s_when_flag_off_even_logged_out()
    test_flag_values()
    test_tables_exist_even_with_flag_off_and_reset_db_works()
    test_roles()
    test_no_delete_routes()
    test_pha_crud_and_settings()
    test_tenancy_money_round_trip_in_cents()
    test_validation_rejects_bad_input()
    test_hap_contract_consistency_checks()
    test_uniqueness_conflicts_are_409()
    test_one_current_tenancy_per_unit()
    test_archive_hides_from_lists_and_unarchive_restores()
    test_unit_detail_shows_tenancy_contracts_and_documents()
    test_backfill_dry_run_apply_idempotent_and_leases_untouched()
    test_backfill_reuses_manually_created_property_and_unit()
    print("\nAll Section 8 data model tests passed.")
