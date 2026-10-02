"""
End-to-end golden test for the Maple Ridge demo deal
(backend/benchmark_data/demo_deal/) -- QA_PLAN.md item 1: upload the real
15 lease PDFs and the real 16-unit rent-roll CSV through the REAL Flask
routes (not internal function calls), run the real Deal Mismatch Report,
and confirm the 7 live-detectable planted findings (of the 10 documented
in expected_findings.json -- the other 3 are concession_missing, a
documented stub, see app/deal_mismatch.py's detect_concession_missing)
come back with the exact unit and dollar amounts the demo deal's own
generator computed.

No fixed dates anywhere in this file. The demo deal's dates are generated
RELATIVE TO THE DAY THE GENERATOR RUNS (see generate_demo_deal.py's
"Dates are RELATIVE" block), so these tests use real wall-clock
date.today() throughout and never pin `today` to a hardcoded anchor.

This file previously did pin it, to 2026-08-31, because the fixture's
dates were hardcoded: two units (C203, H104) are deliberately planted as
expired-but-occupied, but detect_expired_but_occupied (app/deal_mismatch.py)
defaults to date.today() and the real POST /portfolio/deal-mismatch-report
route never overrides it -- so once wall-clock today passed the old
anchor, clean control units started reading as expired too. Pinning hid
that rot instead of catching it.

Two complementary tests now cover the two things that can actually break:

1. The generator's contract -- most tests below REGENERATE the package
   into a temp directory and assert against that. Freshly generated
   output is correct relative to today by construction, so these can
   never go stale no matter when they run.
2. The committed package's freshness -- test_committed_demo_deal_package_
   is_still_fresh runs the real report against the files actually checked
   into benchmark_data/demo_deal/ and fails, with instructions, once they
   have aged out. That's the one that tells a human to re-run the
   generator and commit, which matters because sales demos use the
   committed copy, not a regenerated one.
"""
import io
import os
import sys
import json
import atexit
import shutil
import tempfile
import importlib.util
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.deal_mismatch import build_deal_mismatch_report_data

DEMO_DIR = os.path.join(os.path.dirname(__file__), '..', 'benchmark_data', 'demo_deal')
GENERATOR_PATH = os.path.join(DEMO_DIR, 'generate_demo_deal.py')
PROPERTY_ADDRESS = "4500 Maple Ridge Trail, Dallas, TX 75248"

# The 6 units deliberately planted with no issue at all -- if any of
# these is ever flagged, the fixture (or the detector) has drifted.
CLEAN_CONTROL_UNITS = {"A102", "B303", "D104", "G303", "H204", "J102"}

_REGENERATED_DIR = None


def _demo_package(regenerate=True):
    """Paths to a demo-deal package. regenerate=True builds a fresh one
    (dates relative to today, guaranteed correct) into a temp dir, cached
    for the whole test process since generating 15 PDFs isn't free;
    regenerate=False returns the committed package as checked in."""
    global _REGENERATED_DIR
    if not regenerate:
        root = DEMO_DIR
    else:
        if _REGENERATED_DIR is None:
            spec = importlib.util.spec_from_file_location("_demo_gen", GENERATOR_PATH)
            gen = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gen)
            tmp = tempfile.mkdtemp(prefix="maple_ridge_demo_")
            # quiet=True: this is a test, not the CLI -- don't spray the
            # generator's summary table through the test output.
            gen.main(out_dir=tmp, quiet=True)
            _REGENERATED_DIR = tmp
        root = _REGENERATED_DIR
    return {
        "leases": os.path.join(root, "leases"),
        "rent_roll_16": os.path.join(root, "rent_roll", "maple_ridge_rent_roll_demo_subset_16unit_appfolio.csv"),
        "rent_roll_120": os.path.join(root, "rent_roll", "maple_ridge_rent_roll_120unit_appfolio.csv"),
        "expected": os.path.join(root, "expected_findings.json"),
    }


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    # feature/usage-limits' per-user extraction rate limit is in-memory
    # and keyed by user_id, not by database -- a fresh temp DB per test
    # doesn't reset it, so the 15-upload demo deal flow here would trip
    # the 10/minute cap after whichever earlier test in this file ran
    # first in the same pytest process. Reset explicitly, same as
    # test_usage_limits.py and test_lease_resubmission.py already do.
    from app import usage_limits
    usage_limits._reset_extraction_rate_limit_for_tests()
    return tmp.name


def _authed_client():
    # feature/usage-limits (merged into main after this fixture was
    # written) gates /leases uploads on the caller having a real
    # team_id (app/api.py's "Your account isn't assigned to a team
    # yet" 403) -- current_user() reads team_id straight off the
    # session (app/auth.py), so a faked session needs one set
    # explicitly, same as a real login would populate it. Every fresh
    # database gets a 'Legacy' team from init_db() (see
    # database._migrate_teams_create_legacy_team), so it's always
    # there to look up by the time this runs (after _fresh_temp_db()).
    #
    # The user row is CREATED here rather than assuming user_id=1 already
    # exists. init_db() only seeds an admin when ADMIN_EMAIL and
    # ADMIN_PASSWORD_HASH are set, and those come from backend/.env --
    # which is correctly gitignored, so it exists in a normal checkout
    # but NOT in a fresh `git worktree add` directory. usage_events has
    # FOREIGN KEY (user_id) REFERENCES users(id), so a session pointing
    # at a nonexistent user id made every /leases upload 500 with
    # "FOREIGN KEY constraint failed" in a worktree while passing on the
    # machine's main checkout. Owning the row removes that dependency.
    conn = database.get_connection()
    try:
        legacy_team = conn.execute("SELECT id FROM teams WHERE name='Legacy' LIMIT 1").fetchone()
        team_id = legacy_team[0] if legacy_team else None
        email = "test-analyst@example.com"
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            user_id = row[0]
        else:
            cur = conn.execute(
                "INSERT INTO users (email, name, password_hash, role, status, created_at, team_id) "
                "VALUES (?, ?, ?, ?, 'active', datetime('now'), ?)",
                (email, "Test Analyst", "x-unusable-hash", "analyst", team_id),
            )
            user_id = cur.lastrowid
            conn.commit()
    finally:
        conn.close()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = "Test Analyst"
        sess["role"] = "analyst"
        sess["team_id"] = team_id
    return client


def _upload_all_demo_leases(client, leases_dir):
    from app import usage_limits
    for filename in sorted(os.listdir(leases_dir)):
        # This fixture's 15 leases are one deal's full packet, uploaded
        # back-to-back -- more than feature/usage-limits' 10/minute
        # per-user rate limit, which exists to catch runaway/automated
        # calls, not this legitimate bulk-at-close workflow. This test
        # is about Deal Mismatch Report correctness, not the rate
        # limiter, so reset between uploads rather than spacing them
        # out or weakening the production limit.
        usage_limits._reset_extraction_rate_limit_for_tests()
        path = os.path.join(leases_dir, filename)
        with open(path, "rb") as f:
            resp = client.post(
                "/leases",
                data={"file": (io.BytesIO(f.read()), filename)},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 201, (filename, resp.status_code, resp.get_json())


def _upload_rent_roll(client, path):
    with open(path, "rb") as f:
        resp = client.post(
            "/leases/import-rent-roll",
            data={"file": (io.BytesIO(f.read()), os.path.basename(path)), "property_address": PROPERTY_ADDRESS},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 201, (path, resp.status_code, resp.get_json())
    return resp.get_json()


def _expected(path):
    with open(path) as f:
        return json.load(f)


def _by_type(discrepancies):
    out = {}
    for row in discrepancies:
        out.setdefault(row["discrepancy_type"], []).append(row)
    return out


def _unit_of(row):
    return row["unit"].split("Suite ")[-1]


def test_demo_deal_16unit_subset_matches_expected_findings_exactly():
    """
    The headline demo flow the README recommends: 15 lease PDFs + the
    16-unit rent-roll subset -> exactly the 10 planted issues, 7 of which
    are live-detected today (4 rent_mismatch, 2 expired_but_occupied, 1
    unit_no_lease; the 3 concession_missing rows are NOT live yet, a
    documented stub -- see module docstring).
    """
    pkg = _demo_package()
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client, pkg["leases"])
        rr_result = _upload_rent_roll(client, pkg["rent_roll_16"])
        assert rr_result["imported_count"] == 16, rr_result

        # Real wall-clock today, no pinned anchor: the package was just
        # generated, so its planted expired/current split is correct now
        # by construction.
        data = build_deal_mismatch_report_data(today=date.today())
        by_type = _by_type(data["discrepancies"])

        expected = _expected(pkg["expected"])
        expected_by_type = {}
        for finding in expected["findings"]:
            expected_by_type.setdefault(finding["discrepancy_type"], []).append(finding)

        # 4 rent_mismatch, exact unit + exact annual dollar impact
        assert len(by_type.get("rent_mismatch", [])) == 4, by_type.get("rent_mismatch")
        got_rent_mismatch = {(_unit_of(r), r["annual_dollar_impact"]) for r in by_type["rent_mismatch"]}
        want_rent_mismatch = {(f["unit_id"], f["annual_dollar_impact"]) for f in expected_by_type["rent_mismatch"]}
        assert got_rent_mismatch == want_rent_mismatch, (got_rent_mismatch, want_rent_mismatch)
        for r in by_type["rent_mismatch"]:
            assert r["income_direction"] == "overstate"

        # 2 expired_but_occupied, exact unit + exact annual dollar impact
        assert len(by_type.get("expired_but_occupied", [])) == 2, by_type.get("expired_but_occupied")
        got_expired = {(_unit_of(r), r["annual_dollar_impact"]) for r in by_type["expired_but_occupied"]}
        want_expired = {(f["unit_id"], f["annual_dollar_impact"]) for f in expected_by_type["expired_but_occupied"]}
        assert got_expired == want_expired, (got_expired, want_expired)

        # 1 unit_no_lease (F203), exact annual dollar impact, no direction asserted (null)
        assert len(by_type.get("unit_no_lease", [])) == 1, by_type.get("unit_no_lease")
        no_lease = by_type["unit_no_lease"][0]
        assert no_lease["unit"].endswith("Suite F203"), no_lease["unit"]
        assert no_lease["annual_dollar_impact"] == 20520.0, no_lease
        assert no_lease["income_direction"] is None

        # concession_missing is a documented stub -- must NOT appear live
        assert "concession_missing" not in by_type, "detect_concession_missing fired; it's supposed to be a stub returning []"

        # The 6 clean negative controls must never appear in ANY finding
        flagged_units = {_unit_of(r) for r in data["discrepancies"]}
        leaked_clean = CLEAN_CONTROL_UNITS & flagged_units
        assert not leaked_clean, f"clean negative-control unit(s) incorrectly flagged: {leaked_clean}"

        # Live dollar exposure: 4 rent_mismatch + 2 expired_but_occupied, signed overstate
        assert data["annual_income_overstatement"] == 42780.0, data["annual_income_overstatement"]

        # No false positives at all: exactly 7 findings, nothing extra
        assert data["total_discrepancies"] == 7, data["total_discrepancies"]
        assert data["total_units_checked"] == 16, data["total_units_checked"]

        # PDF + Excel export must both succeed against this real data
        pdf_resp = client.post("/portfolio/deal-mismatch-report.pdf", data={"property_address": PROPERTY_ADDRESS})
        assert pdf_resp.status_code == 200, pdf_resp.status_code
        assert pdf_resp.content_type == "application/pdf"
        assert len(pdf_resp.data) > 1000

        xlsx_resp = client.post("/portfolio/deal-mismatch-report.xlsx", data={"property_address": PROPERTY_ADDRESS})
        assert xlsx_resp.status_code == 200, xlsx_resp.status_code
        assert "spreadsheetml" in xlsx_resp.content_type
        assert len(xlsx_resp.data) > 1000
    finally:
        os.unlink(db_path)
    print("✓ test_demo_deal_16unit_subset_matches_expected_findings_exactly: PASS")


def test_demo_deal_findings_stable_through_real_route_regardless_of_todays_date():
    """
    The same 7 findings, but end-to-end through the REAL
    POST /portfolio/deal-mismatch-report route, which passes no `today`
    at all and so uses the detector's own date.today() default. The test
    above calls build_deal_mismatch_report_data() directly; this one
    proves the route a customer actually hits agrees with it, including
    the two date-sensitive expired_but_occupied findings.
    """
    pkg = _demo_package()
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client, pkg["leases"])
        _upload_rent_roll(client, pkg["rent_roll_16"])

        resp = client.post("/portfolio/deal-mismatch-report", data={"property_address": PROPERTY_ADDRESS})
        assert resp.status_code == 200, resp.status_code
        data = resp.get_json()
        by_type = _by_type(data["discrepancies"])

        rent_mismatch = by_type.get("rent_mismatch", [])
        assert len(rent_mismatch) == 4
        assert {r["annual_dollar_impact"] for r in rent_mismatch} == {900.0, 1440.0, 3120.0, 1200.0}

        unit_no_lease = by_type.get("unit_no_lease", [])
        assert len(unit_no_lease) == 1
        assert unit_no_lease[0]["annual_dollar_impact"] == 20520.0

        # Date-sensitive half: exactly the 2 planted holdovers, no more.
        # Through the route this is only assertable because the fixture's
        # dates are relative -- it was the assertion the old hardcoded
        # fixture could not make.
        expired = by_type.get("expired_but_occupied", [])
        assert {_unit_of(r) for r in expired} == {"C203", "H104"}, [_unit_of(r) for r in expired]

        assert data["total_discrepancies"] == 7, data["total_discrepancies"]
        leaked_clean = CLEAN_CONTROL_UNITS & {_unit_of(r) for r in data["discrepancies"]}
        assert not leaked_clean, f"clean negative-control unit(s) incorrectly flagged: {leaked_clean}"
    finally:
        os.unlink(db_path)
    print("✓ test_demo_deal_findings_stable_through_real_route_regardless_of_todays_date: PASS")


def test_demo_deal_120unit_file_adds_only_background_no_lease_rows():
    """
    Uploading the FULL 120-unit rent roll against only the 15 sample
    leases should produce the same 4 rent_mismatch findings plus a flood
    of additional unit_no_lease rows for the ~104 background units with
    no sample lease PDF in this package -- see the demo deal's README
    ("Why there are two rent-roll files"). Not a bug: a known, documented
    artifact of shipping a 15-lease sample against a 120-row rent roll.
    Range-based assertion (not an exact count) since this isn't the
    fixture's primary documented contract the way the 16-unit subset is.
    """
    pkg = _demo_package()
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client, pkg["leases"])
        rr_result = _upload_rent_roll(client, pkg["rent_roll_120"])
        # 120 rows minus 6 deliberately-vacant units, which the importer
        # correctly skips rather than importing as a fake tenant lease
        # (see rent_roll_import.py's _NON_TENANT_KEYWORDS / vacant-row
        # handling) -- not a bug, confirmed by inspecting the fixture.
        assert rr_result["imported_count"] == 114, rr_result

        data = build_deal_mismatch_report_data(today=date.today())
        by_type = _by_type(data["discrepancies"])

        assert len(by_type.get("rent_mismatch", [])) == 4
        assert {r["annual_dollar_impact"] for r in by_type["rent_mismatch"]} == {900.0, 1440.0, 3120.0, 1200.0}
        # Still exactly the 2 planted holdovers. Background units can have
        # lease ends in the past too, but expired_but_occupied only fires
        # for a rent-roll row matched to a real lease PDF, and only the 15
        # documented units have one.
        assert {_unit_of(r) for r in by_type.get("expired_but_occupied", [])} == {"C203", "H104"}

        no_lease_units = {r["unit"].split("Suite ")[-1] for r in by_type.get("unit_no_lease", [])}
        assert "F203" in no_lease_units, "the one deliberately-planted no-lease unit (F203) must still be present"
        assert 95 <= len(no_lease_units) <= 110, (
            f"expected ~104 background no-lease units (105 undocumented of 120 total, "
            f"minus overlap), got {len(no_lease_units)}"
        )
    finally:
        os.unlink(db_path)
    print("✓ test_demo_deal_120unit_file_adds_only_background_no_lease_rows: PASS")


def test_committed_demo_deal_package_is_still_fresh():
    """
    The other tests regenerate the package, so they pass forever. This
    one checks the copy actually COMMITTED to benchmark_data/demo_deal/
    -- the one sales demos and the "Load sample deal" button use -- still
    tells the right story as of today.

    Lease terms are finite, so a committed package does eventually age
    out: its earliest current lease ends MIN_LIVE_END_OFFSET months after
    the as-of date it was built with. When that happens this test fails
    with instructions. That is the intended behavior -- a loud, dated
    reminder to re-run the generator, rather than a demo that silently
    starts reporting expired leases it shouldn't.
    """
    pkg = _demo_package(regenerate=False)
    expected = _expected(pkg["expected"])
    as_of = expected["rent_roll_as_of"]
    stale_hint = (
        f"The committed demo deal (generated with rent_roll_as_of={as_of}) has aged out "
        f"as of today ({date.today().isoformat()}). Re-run it and commit the result:\n"
        f"    cd backend && venv/bin/python benchmark_data/demo_deal/generate_demo_deal.py\n"
        f"See benchmark_data/demo_deal/README.md -> 'Regenerating'."
    )

    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client, pkg["leases"])
        _upload_rent_roll(client, pkg["rent_roll_16"])

        data = build_deal_mismatch_report_data(today=date.today())
        by_type = _by_type(data["discrepancies"])

        got_expired = {_unit_of(r) for r in by_type.get("expired_but_occupied", [])}
        assert got_expired == {"C203", "H104"}, (
            f"expected exactly the 2 planted expired-but-occupied units, got {sorted(got_expired)}.\n"
            + stale_hint
        )
        leaked_clean = CLEAN_CONTROL_UNITS & {_unit_of(r) for r in data["discrepancies"]}
        assert not leaked_clean, (
            f"clean negative-control unit(s) now flagged: {sorted(leaked_clean)}.\n" + stale_hint
        )
        assert data["total_discrepancies"] == 7, (
            f"expected 7 live findings, got {data['total_discrepancies']}.\n" + stale_hint
        )
    finally:
        os.unlink(db_path)
    print("✓ test_committed_demo_deal_package_is_still_fresh: PASS")


def _cleanup_regenerated_dir():
    # Registered with atexit as well as called from __main__, so the
    # regenerated package is cleaned up under pytest too (where nothing
    # runs the __main__ block).
    global _REGENERATED_DIR
    if _REGENERATED_DIR and os.path.isdir(_REGENERATED_DIR):
        shutil.rmtree(_REGENERATED_DIR, ignore_errors=True)
    _REGENERATED_DIR = None


atexit.register(_cleanup_regenerated_dir)


if __name__ == "__main__":
    try:
        test_demo_deal_16unit_subset_matches_expected_findings_exactly()
        test_demo_deal_findings_stable_through_real_route_regardless_of_todays_date()
        test_demo_deal_120unit_file_adds_only_background_no_lease_rows()
        test_committed_demo_deal_package_is_still_fresh()
    finally:
        _cleanup_regenerated_dir()
    print("\nAll demo deal golden tests passed.")
