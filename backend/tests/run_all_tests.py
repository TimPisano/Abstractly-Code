"""
Runs the full automated test suite in one shot and reports a pass/fail
summary. This is the "can be re-run to catch regressions in future
sessions" entry point the project's quality bar calls for.

Two categories:
  - Unit tests: self-contained, no running server needed.
  - Live API tests: require the backend already running at
    http://localhost:5000 (e.g. `cd backend && python run.py`) — these
    exercise the real HTTP layer, not just the underlying functions.

Usage: `python run_all_tests.py` (unit tests only) or
       `python run_all_tests.py --live` (unit tests + live API tests,
       backend must already be running).
"""
import subprocess
import sys
import os

TESTS_DIR = os.path.dirname(__file__)

UNIT_TESTS = [
    "test_extraction.py",
    "test_synthetic_accuracy.py",
    "test_confidence_validation.py",
    "test_summary_memo.py",
    "test_multipage_field.py",
    "test_ocr_fallback.py",
    "test_real_ocr.py",
    "test_risk_analysis.py",
    "test_qa_engine.py",
    "test_portfolio.py",
    "test_comparison.py",
    "test_rent_roll_export.py",
    "test_report.py",
    "test_dashboard_features.py",
    "test_waitlist_email.py",
    "test_access_gate.py",
    "test_admin_auth.py",
    "test_multi_lease_detection.py",
    "test_multi_lease_structural_variation.py",
    "test_sheets_export.py",
    "test_lease_naming_and_tags.py",
    "test_tenant_concentration_api.py",
    "test_rollover_api.py",
    "test_loss_to_lease_api.py",
    "test_rent_roll_import.py",
    "test_rent_roll_import_api.py",
    "test_rent_roll_reconciliation_api.py",
    "test_pms_synthetic_fixtures.py",
    "test_t12_import.py",
    "test_t12_reconciliation_api.py",
    "test_t12_synthetic_fixture.py",
    "test_audit_trail.py",
    "test_discrepancies.py",
    "test_portfolio_history.py",
    "test_comments.py",
    "test_alerts.py",
    "test_investment_memo.py",
    "test_portfolio_health_score.py",
    "test_document_extractor.py",
    "test_cache.py",
    "test_concurrency.py",
    "test_performance.py",
    "test_rent_roll_shape_detection.py",
    "test_teams_and_assignments.py",
    "test_assistant.py",
]

LIVE_API_TESTS = [
    "test_live_api.py",
    "test_live_portfolio_api.py",
    "test_security_hardening.py",
    "test_live_dashboard_api.py",
    "test_live_multi_lease_api.py",
    "test_live_composition_api.py",
    "test_live_t12_api.py",
    "test_live_audit_trail_api.py",
    "test_live_discrepancies_api.py",
    "test_live_portfolio_history_api.py",
    "test_live_comments_api.py",
    "test_live_alerts_api.py",
    "test_live_investment_memo_api.py",
    "test_live_health_score_api.py",
    "test_live_multiformat_upload_api.py",
    "test_live_sidebar_endpoints_api.py",
    "test_live_performance_api.py",
    "test_live_assistant_api.py",
]


def run_test(filename):
    # EMAIL_USER/EMAIL_APP_PASSWORD are stripped for every test subprocess,
    # not just the two files known (as of this writing) to hit /waitlist
    # unmocked -- a real incident sent thousands of real Gmail emails to
    # the real ADMIN_EMAIL inbox because two test files exercised
    # /waitlist through app.test_client() with no email mocking at all.
    # Those two files now also strip these vars themselves (defense in
    # depth for anyone running one directly with `python3 <file>.py`),
    # but stripping them centrally here means any *future* test file that
    # touches /waitlist can't repeat this by omission -- it fails safe by
    # default rather than depending on every new test file remembering to
    # mock email_service itself. See DECISIONS.md for the full incident.
    env = dict(os.environ)
    env.pop("EMAIL_USER", None)
    env.pop("EMAIL_APP_PASSWORD", None)

    result = subprocess.run(
        [sys.executable, filename],
        cwd=TESTS_DIR,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode == 0, result.stdout, result.stderr


def main():
    run_live = "--live" in sys.argv
    suite = UNIT_TESTS + (LIVE_API_TESTS if run_live else [])

    print("=" * 70)
    print(f"Running {len(suite)} test file(s){' (including live API tests)' if run_live else ' (unit tests only — pass --live to also run live API tests)'}")
    print("=" * 70)

    results = []
    for filename in suite:
        print(f"\n--- {filename} ---")
        passed, stdout, stderr = run_test(filename)
        results.append((filename, passed))
        # Print only the tail of output to keep this readable; full output
        # is available by running the file directly if something fails.
        output = (stdout + stderr).strip().split("\n")
        print("\n".join(output[-8:]) if output else "(no output)")
        print("PASSED" if passed else "FAILED")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for filename, passed in results:
        print(f"{'✓' if passed else '✗'} {filename}")

    failed = [f for f, p in results if not p]
    print(f"\n{len(results) - len(failed)}/{len(results)} test files passed")
    if failed:
        print(f"Failed: {', '.join(failed)}")

    if not run_live:
        print("\n(Live API tests skipped — run with --live and the backend running to include them.)")

    return len(failed) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
