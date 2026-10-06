"""
Regression guard for the Maple Ridge demo deal's 10 planted discrepancies,
driven directly off benchmark_data/demo_deal/expected_findings.json (the
generator's own ground truth) rather than literal numbers re-typed in this
file -- unlike test_demo_deal_golden.py's hardcoded assertions, regenerating
the demo deal with different planted values (different units, different
dollar amounts) updates expected_findings.json and this test automatically
re-derives its expectations from it, so the two can never silently drift
apart. The point of this file specifically is "if a planted issue ever
stops being caught, or a caught dollar amount ever changes, this test
fails" -- every assertion below exists for exactly that purpose.

Same fixture/upload approach as test_demo_deal_golden.py: real Flask
routes, real HTTP uploads of the real 15 lease PDFs and the real 16-unit
rent-roll .xlsx, a fresh temp SQLite DB per test. See that file's own
docstring for why the exact-findings assertion pins `today` to the demo
deal's documented as-of date (2026-08-31) rather than real wall-clock
"today" -- the same date-drift reasoning applies here unchanged.
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
from _session_users import sync_session_user
from app.deal_mismatch import build_deal_mismatch_report_data

DEMO_DIR = os.path.join(os.path.dirname(__file__), '..', 'benchmark_data', 'demo_deal')
LEASES_DIR = os.path.join(DEMO_DIR, 'leases')
RENT_ROLL_16 = os.path.join(DEMO_DIR, 'rent_roll', 'maple_ridge_rent_roll_demo_subset_16unit.xlsx')
EXPECTED_FINDINGS_PATH = os.path.join(DEMO_DIR, 'expected_findings.json')
PROPERTY_ADDRESS = "4500 Maple Ridge Trail, Dallas, TX 75248"
DEMO_AS_OF = date(2026, 8, 31)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    from app import usage_limits
    usage_limits._reset_extraction_rate_limit_for_tests()
    return tmp.name


def _legacy_team_id():
    conn = database.get_connection()
    try:
        legacy_team = conn.execute("SELECT id FROM teams WHERE name='Legacy' LIMIT 1").fetchone()
    finally:
        conn.close()
    return legacy_team[0] if legacy_team else None


def _authed_client():
    team_id = _legacy_team_id()
    # A real users row, same as test_demo_deal_golden.py's fixture: a
    # hardcoded user_id=1 only existed when the machine's backend/.env
    # seeded an admin, so on a clean checkout every upload failed (500 on
    # the usage_events foreign key, then 401 once sessions were checked
    # against real users). TASKS.md "Waiting on you" #10.
    from app.auth import hash_password
    created = database.create_user(
        "regression-test@example.com", "Regression Test", hash_password("x"), role="analyst",
        team_id=team_id,
    )
    user_id = created["id"] if created["status"] == "created" else database.get_user_by_email("regression-test@example.com")["id"]
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = "regression-test@example.com"
        sess["name"] = "Regression Test"
        sess["role"] = "analyst"
        sess["team_id"] = team_id
        sync_session_user(sess)
    return client


def _upload_all_demo_leases(client):
    from app import usage_limits
    for filename in sorted(os.listdir(LEASES_DIR)):
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


def test_every_live_planted_finding_is_still_caught_with_the_right_dollar_amount():
    """
    The core regression guard: every finding expected_findings.json marks
    as "-- live" (not the documented concession_missing stub) must still
    come back from a real Deal Mismatch Report run, for the right unit,
    with the exact annual dollar impact and income direction the
    generator computed -- derived from the JSON, never re-typed here.
    """
    expected = _expected()
    live_findings = [f for f in expected["findings"] if "-- live" in f["detected_by"]]
    stub_findings = [f for f in expected["findings"] if "NOT YET DETECTED" in f["detected_by"]]
    assert live_findings, "expected_findings.json has no live-tagged findings -- fixture may be malformed"

    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client)
        _upload_rent_roll(client, RENT_ROLL_16)

        data = build_deal_mismatch_report_data(team_id=_legacy_team_id(), today=DEMO_AS_OF)
        got_by_key = {
            (row["unit"].split("Suite ")[-1], row["discrepancy_type"]): row
            for row in data["discrepancies"]
        }

        missing = []
        wrong_amount = []
        wrong_direction = []
        for finding in live_findings:
            key = (finding["unit_id"], finding["discrepancy_type"])
            got = got_by_key.get(key)
            if got is None:
                missing.append(key)
                continue
            if got["annual_dollar_impact"] != finding["annual_dollar_impact"]:
                wrong_amount.append((key, got["annual_dollar_impact"], finding["annual_dollar_impact"]))
            if finding["income_direction"] is not None and got["income_direction"] != finding["income_direction"]:
                wrong_direction.append((key, got["income_direction"], finding["income_direction"]))

        assert not missing, f"planted finding(s) no longer detected at all: {missing}"
        assert not wrong_amount, f"planted finding(s) now report the wrong dollar amount (got, want): {wrong_amount}"
        assert not wrong_direction, f"planted finding(s) now report the wrong income direction (got, want): {wrong_direction}"

        # Every live finding accounted for above, and nothing MORE than
        # that plus the documented stub count showed up as a false
        # positive among the 16 documented units -- the stub findings
        # must still be absent (see the next assertion), and the clean
        # negative controls must never appear (see
        # test_clean_negative_controls_never_flagged below), so the
        # total count of discrepancies found must equal exactly the
        # live-tagged count.
        assert data["total_discrepancies"] == len(live_findings), (
            f"expected exactly {len(live_findings)} discrepancies (the live-tagged findings in "
            f"expected_findings.json), got {data['total_discrepancies']}"
        )

        # The stub (concession_missing) findings are documented as NOT
        # yet live -- if detect_concession_missing is ever wired up
        # without updating expected_findings.json's "detected_by" text,
        # this is the assertion that will catch the mismatch and demand
        # a conscious update here, rather than silently starting to pass
        # a check that is no longer true.
        for finding in stub_findings:
            key = (finding["unit_id"], finding["discrepancy_type"])
            assert key not in got_by_key, (
                f"{key} is documented as NOT YET DETECTED in expected_findings.json but a live "
                "finding was returned for it -- update expected_findings.json's detected_by text "
                "(and this test's expectations) now that detection is live"
            )

        # Total dollar exposure across the live findings, derived from
        # the JSON rather than hardcoded, must match the report's own
        # signed total.
        want_total = round(sum(
            f["annual_dollar_impact"] for f in live_findings
            if f["income_direction"] == "overstate"
        ), 2)
        assert data["annual_income_overstatement"] == want_total, (
            data["annual_income_overstatement"], want_total,
        )
    finally:
        os.unlink(db_path)
    print("✓ test_every_live_planted_finding_is_still_caught_with_the_right_dollar_amount: PASS")


def test_clean_negative_controls_never_flagged():
    """
    The 6 units expected_findings.json's generator deliberately left
    clean (lease and rent roll agree exactly) must never appear in any
    finding -- a false positive here would be exactly as serious a
    regression as a missed true positive above.
    """
    expected = _expected()
    documented_ids = {f["unit_id"] for f in expected["findings"]}
    # DOCUMENTED_UNITS in generate_demo_deal.py has 16 total unit entries
    # (10 planted-issue + 6 clean); expected_findings.json only lists the
    # 10 with an actual finding, so the clean 6 are whatever's left of
    # the 16-unit subset's units once the documented (planted) ones are
    # excluded. Read the rent-roll subset itself rather than
    # hardcoding the clean unit IDs, so this stays correct even if the
    # generator's clean-unit set ever changes.
    from openpyxl import load_workbook
    wb = load_workbook(RENT_ROLL_16)
    ws = wb.active
    header_row = None
    for row in ws.iter_rows(min_row=1, max_row=20):
        values = [c.value for c in row]
        if values and values[0] == "Unit":
            header_row = row[0].row
            break
    assert header_row is not None, "could not find the rent roll's header row"
    all_unit_ids = {
        row[0].value for row in ws.iter_rows(min_row=header_row + 1)
        if row[0].value
    }
    clean_unit_ids = all_unit_ids - documented_ids
    assert clean_unit_ids, "expected at least one clean negative-control unit in the 16-unit subset"

    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        _upload_all_demo_leases(client)
        _upload_rent_roll(client, RENT_ROLL_16)

        data = build_deal_mismatch_report_data(team_id=_legacy_team_id(), today=DEMO_AS_OF)
        flagged_units = {row["unit"].split("Suite ")[-1] for row in data["discrepancies"]}
        leaked = clean_unit_ids & flagged_units
        assert not leaked, f"clean negative-control unit(s) incorrectly flagged: {leaked}"
    finally:
        os.unlink(db_path)
    print("✓ test_clean_negative_controls_never_flagged: PASS")


if __name__ == "__main__":
    test_every_live_planted_finding_is_still_caught_with_the_right_dollar_amount()
    test_clean_negative_controls_never_flagged()
    print("\nAll demo deal regression tests passed.")
