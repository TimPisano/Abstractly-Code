"""
End-to-end golden test for the Maple Ridge demo deal
(backend/benchmark_data/demo_deal/) -- QA_PLAN.md item 1: upload the real
15 lease PDFs and the real 16-unit rent-roll CSV through the REAL Flask
routes (not internal function calls), run the real Deal Mismatch Report,
and confirm all 10 planted findings documented in expected_findings.json
(4 rent_mismatch, 2 expired_but_occupied, 3 concession_missing, 1
unit_no_lease) come back with the exact unit and dollar amounts the demo
deal's own generator computed. (The 3 concession_missing rows were a
documented stub until fix/concession-detection; see app/concessions.py.)

Fixture note: the demo deal's lease dates are hardcoded absolute calendar
dates anchored to RENT_ROLL_AS_OF = 2026-08-31 (see generate_demo_deal.py).
Two units (C203, H104) are DELIBERATELY planted as expired-but-occupied
as of that anchor date. But detect_expired_but_occupied (app/deal_mismatch.py)
defaults to date.today() when no `today` is passed, and the real
POST /portfolio/deal-mismatch-report route never passes one -- so once
real wall-clock "today" passes 2026-08-31, OTHER units whose leases were
only valid "as of" the original anchor date will ALSO start reading as
expired, on top of the 2 intentionally-planted ones. This is a known,
flagged limitation of the fixture's hardcoded dates (see QA_REPORT.md),
not a product bug -- rewriting ~16 units' worth of hand-placed absolute
dates to be relative to generation time would also require resyncing
README.md's prose (which quotes the same absolute dates in sentences),
which is out of scope for this pass. To keep this test meaningful and
stable regardless of which day it runs, the exact-findings assertion
below calls build_deal_mismatch_report_data(today=date(2026, 8, 31))
directly (the demo deal's own documented as-of date) rather than only
through the route for that specific check; a second, separate assertion
confirms the date-independent findings (rent_mismatch, unit_no_lease)
exactly through the real route with real wall-clock today, since those
two discrepancy types don't depend on "today" at all.
"""
import io
import os
import sys
import json
import tempfile
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app.deal_mismatch import build_deal_mismatch_report_data

DEMO_DIR = os.path.join(os.path.dirname(__file__), '..', 'benchmark_data', 'demo_deal')
LEASES_DIR = os.path.join(DEMO_DIR, 'leases')
RENT_ROLL_16 = os.path.join(DEMO_DIR, 'rent_roll', 'maple_ridge_rent_roll_demo_subset_16unit_appfolio.csv')
RENT_ROLL_120 = os.path.join(DEMO_DIR, 'rent_roll', 'maple_ridge_rent_roll_120unit_appfolio.csv')
EXPECTED_FINDINGS_PATH = os.path.join(DEMO_DIR, 'expected_findings.json')
PROPERTY_ADDRESS = "4500 Maple Ridge Trail, Dallas, TX 75248"
DEMO_AS_OF = date(2026, 8, 31)


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
    conn = database.get_connection()
    try:
        legacy_team = conn.execute("SELECT id FROM teams WHERE name='Legacy' LIMIT 1").fetchone()
    finally:
        conn.close()
    # A REAL users row, not a hardcoded user_id=1: every upload writes a
    # usage_events row with a foreign key to users(id), and a fresh temp
    # DB only has a user 1 when the machine's backend/.env happens to set
    # ADMIN_EMAIL (database's bootstrap-admin migration). Without one,
    # every upload here 500'd with "FOREIGN KEY constraint failed" on a
    # clean checkout (found 2026-10-02, fix/concession-detection).
    created = database.create_user(
        "test-analyst@example.com", "Test Analyst", "not-a-real-hash", role="analyst",
        team_id=legacy_team[0] if legacy_team else None,
    )
    user_id = created["id"] if created["status"] == "created" else database.get_user_by_email("test-analyst@example.com")["id"]
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = "test-analyst@example.com"
        sess["name"] = "Test Analyst"
        sess["role"] = "analyst"
        sess["team_id"] = legacy_team[0] if legacy_team else None
    return client


def _upload_all_demo_leases(client):
    from app import usage_limits
    for filename in sorted(os.listdir(LEASES_DIR)):
        # This fixture's 15 leases are one deal's full packet, uploaded
        # back-to-back -- more than feature/usage-limits' 10/minute
        # per-user rate limit, which exists to catch runaway/automated
        # calls, not this legitimate bulk-at-close workflow. This test
        # is about Deal Mismatch Report correctness, not the rate
        # limiter, so reset between uploads rather than spacing them
        # out or weakening the production limit.
        usage_limits._reset_extraction_rate_limit_for_tests()
        path = os.path.join(LEASES_DIR, filename)
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


def _expected():
    with open(EXPECTED_FINDINGS_PATH) as f:
        return json.load(f)


def test_demo_deal_16unit_subset_matches_expected_findings_exactly():
    """
    The headline demo flow the README recommends: 15 lease PDFs + the
    16-unit rent-roll subset -> exactly the 10 planted issues, all live:
    4 rent_mismatch, 2 expired_but_occupied, 3 concession_missing, 1
    unit_no_lease.
    """
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client)
        rr_result = _upload_rent_roll(client, RENT_ROLL_16)
        assert rr_result["imported_count"] == 16, rr_result

        # Exact-findings assertion, anchored to the demo deal's own
        # documented as-of date (see module docstring re: date drift).
        data = build_deal_mismatch_report_data(today=DEMO_AS_OF)
        by_type = {}
        for row in data["discrepancies"]:
            by_type.setdefault(row["discrepancy_type"], []).append(row)

        expected = _expected()
        expected_by_type = {}
        for finding in expected["findings"]:
            expected_by_type.setdefault(finding["discrepancy_type"], []).append(finding)

        # 4 rent_mismatch, exact unit + exact annual dollar impact
        assert len(by_type.get("rent_mismatch", [])) == 4, by_type.get("rent_mismatch")
        got_rent_mismatch = {(r["unit"].split("Suite ")[-1], r["annual_dollar_impact"]) for r in by_type["rent_mismatch"]}
        want_rent_mismatch = {(f["unit_id"], f["annual_dollar_impact"]) for f in expected_by_type["rent_mismatch"]}
        assert got_rent_mismatch == want_rent_mismatch, (got_rent_mismatch, want_rent_mismatch)
        for r in by_type["rent_mismatch"]:
            assert r["income_direction"] == "overstate"

        # 2 expired_but_occupied, exact unit + exact annual dollar impact
        assert len(by_type.get("expired_but_occupied", [])) == 2, by_type.get("expired_but_occupied")
        got_expired = {(r["unit"].split("Suite ")[-1], r["annual_dollar_impact"]) for r in by_type["expired_but_occupied"]}
        want_expired = {(f["unit_id"], f["annual_dollar_impact"]) for f in expected_by_type["expired_but_occupied"]}
        assert got_expired == want_expired, (got_expired, want_expired)

        # 1 unit_no_lease (F203), exact annual dollar impact, no direction asserted (null)
        assert len(by_type.get("unit_no_lease", [])) == 1, by_type.get("unit_no_lease")
        no_lease = by_type["unit_no_lease"][0]
        assert no_lease["unit"].endswith("Suite F203"), no_lease["unit"]
        assert no_lease["annual_dollar_impact"] == 20520.0, no_lease
        assert no_lease["income_direction"] is None

        # 3 concession_missing (A104 free month, E301 6-month renewal
        # discount, I204 full-term retention discount), exact unit + exact
        # annualized dollar impact, each citing the lease's concession
        # clause on the page it's on.
        assert len(by_type.get("concession_missing", [])) == 3, by_type.get("concession_missing")
        got_concessions = {(r["unit"].split("Suite ")[-1], r["annual_dollar_impact"]) for r in by_type["concession_missing"]}
        want_concessions = {(f["unit_id"], f["annual_dollar_impact"]) for f in expected_by_type["concession_missing"]}
        assert got_concessions == want_concessions, (got_concessions, want_concessions)
        for r in by_type["concession_missing"]:
            assert r["income_direction"] == "overstate"
            assert r["source"] and r["source"]["page"] == 1, r["source"]
            assert "RENT CONCESSION" not in r["source"]["quote"] and ("abated" in r["source"]["quote"] or "reduced by" in r["source"]["quote"]), r["source"]
            assert r["rent_roll_value"].endswith("(no concession shown)"), r["rent_roll_value"]
        # Effective rent is reported alongside the concession
        e301 = next(r for r in by_type["concession_missing"] if r["unit"].endswith("E301"))
        assert e301["effective_rent"]["net_effective_rent"] == 1240.0, e301["effective_rent"]
        assert e301["effective_rent"]["current_rent"] == 1190.0, e301["effective_rent"]  # Aug 2026 is inside the Apr-Sep discount window
        assert "active" in e301["note"], e301["note"]
        a104 = next(r for r in by_type["concession_missing"] if r["unit"].endswith("A104"))
        assert "already used" in a104["note"], a104["note"]  # the Oct 2025 free month is behind us
        # No other concession checks fire on this rent roll (it has no
        # concession column, and shows gross rent everywhere)
        assert "concession_mismatch" not in by_type and "concession_expiring" not in by_type

        # The 6 clean negative controls must never appear in ANY finding
        clean_units = {"A102", "B303", "D104", "G303", "H204", "J102"}
        flagged_units = {r["unit"].split("Suite ")[-1] for r in data["discrepancies"]}
        leaked_clean = clean_units & flagged_units
        assert not leaked_clean, f"clean negative-control unit(s) incorrectly flagged: {leaked_clean}"

        # Live dollar exposure: 4 rent_mismatch + 2 expired_but_occupied
        # + 3 concession_missing, signed overstate -- the README's
        # $45,355.00 headline, now fully live
        assert data["annual_income_overstatement"] == expected["total_planted_annual_income_overstatement"] == 45355.0, data["annual_income_overstatement"]
        assert data["concession_summary"] == {"leases_with_concessions": 3, "annualized_concession_value": 2575.0}, data["concession_summary"]

        # No false positives at all: exactly the 10 planted findings, nothing extra
        assert data["total_discrepancies"] == 10, data["total_discrepancies"]
        assert data["total_discrepancies"] == len(expected["findings"])
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
    rent_mismatch and unit_no_lease don't depend on "today" at all (no
    expiry check involved; none of the demo's rent_mismatch units has a
    concession, so rent_mismatch's effective-rent check doesn't depend on
    "today" here either) -- confirm these 5 of the 10 findings come
    back correctly through the REAL route (real wall-clock today, no
    override), so this test stays meaningful no matter what day it runs,
    unlike the exact-match test above which pins today to the fixture's
    documented as-of date specifically to sidestep expired_but_occupied's
    date-drift issue (see module docstring).
    """
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client)
        _upload_rent_roll(client, RENT_ROLL_16)

        resp = client.post("/portfolio/deal-mismatch-report", data={"property_address": PROPERTY_ADDRESS})
        assert resp.status_code == 200, resp.status_code
        data = resp.get_json()

        rent_mismatch = [r for r in data["discrepancies"] if r["discrepancy_type"] == "rent_mismatch"]
        assert len(rent_mismatch) == 4
        assert {r["annual_dollar_impact"] for r in rent_mismatch} == {900.0, 1440.0, 3120.0, 1200.0}

        unit_no_lease = [r for r in data["discrepancies"] if r["discrepancy_type"] == "unit_no_lease"]
        assert len(unit_no_lease) == 1
        assert unit_no_lease[0]["annual_dollar_impact"] == 20520.0
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
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client)
        rr_result = _upload_rent_roll(client, RENT_ROLL_120)
        # 120 rows minus 6 deliberately-vacant units, which the importer
        # correctly skips rather than importing as a fake tenant lease
        # (see rent_roll_import.py's _NON_TENANT_KEYWORDS / vacant-row
        # handling) -- not a bug, confirmed by inspecting the fixture.
        assert rr_result["imported_count"] == 114, rr_result

        data = build_deal_mismatch_report_data(today=DEMO_AS_OF)
        by_type = {}
        for row in data["discrepancies"]:
            by_type.setdefault(row["discrepancy_type"], []).append(row)

        assert len(by_type.get("rent_mismatch", [])) == 4
        assert {r["annual_dollar_impact"] for r in by_type["rent_mismatch"]} == {900.0, 1440.0, 3120.0, 1200.0}
        assert len(by_type.get("expired_but_occupied", [])) == 2

        no_lease_units = {r["unit"].split("Suite ")[-1] for r in by_type.get("unit_no_lease", [])}
        assert "F203" in no_lease_units, "the one deliberately-planted no-lease unit (F203) must still be present"
        assert 95 <= len(no_lease_units) <= 110, (
            f"expected ~104 background no-lease units (105 undocumented of 120 total, "
            f"minus overlap), got {len(no_lease_units)}"
        )
    finally:
        os.unlink(db_path)
    print("✓ test_demo_deal_120unit_file_adds_only_background_no_lease_rows: PASS")


if __name__ == "__main__":
    test_demo_deal_16unit_subset_matches_expected_findings_exactly()
    test_demo_deal_findings_stable_through_real_route_regardless_of_todays_date()
    test_demo_deal_120unit_file_adds_only_background_no_lease_rows()
    print("\nAll demo deal golden tests passed.")
