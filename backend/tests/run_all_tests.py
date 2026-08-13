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
    "test_multipage_field.py",
    "test_ocr_fallback.py",
    "test_real_ocr.py",
    "test_risk_analysis.py",
    "test_qa_engine.py",
    "test_portfolio.py",
    "test_comparison.py",
    "test_rent_roll_export.py",
    "test_report.py",
]

LIVE_API_TESTS = [
    "test_live_api.py",
    "test_live_portfolio_api.py",
    "test_security_hardening.py",
]


def run_test(filename):
    result = subprocess.run(
        [sys.executable, filename],
        cwd=TESTS_DIR,
        capture_output=True,
        text=True,
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
