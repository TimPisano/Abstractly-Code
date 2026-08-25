"""
Live, real-scale performance check against the actual 500-unit
synthetic rent roll used to validate this hardening pass (not a
synthetic-in-test fixture like test_performance.py -- this is the
literal file, imported through the real HTTP upload route, then
queried through the real dashboard endpoints on the actually-running
server). See DECISIONS.md for the two N+1 patterns this pass found and
fixed (database.get_all_effective_leases' per-lease connection
overhead, and GET /portfolio/risks' / POST /alerts/generate's
per-flag/per-candidate upsert overhead).

Requires the live backend running at http://localhost:5000. Gracefully
skips (not fails) if the file isn't present at the known local path --
it's a large, user-generated fixture, not something committed to the
repo, so a fresh clone or another machine simply won't have it.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

API_BASE_URL = "http://localhost:5000"
STRESS_TEST_FILE = os.path.expanduser("~/Rent-Roll_AI/input/STRESS_TEST_500pg.xlsx")

# Generous thresholds -- these guard against a REGRESSION back to O(n)
# connections-per-request, not tight performance targets. Anything
# this far over the line means the N+1 pattern (or something just as
# bad) is back.
MAX_UPLOAD_SECONDS = 15
MAX_DASHBOARD_QUERY_SECONDS = 2


def _request(method, path, data=None, headers=None, timeout=120):
    req = urllib.request.Request(f"{API_BASE_URL}{path}", data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "application/json" in content_type:
                return resp.status, json.loads(raw.decode())
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return e.code, raw


def _multipart_body(fields, files):
    boundary = "----PerfApiTestBoundary"
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for field_name, filename, content, content_type in files:
        parts.append((
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def clear_all_leases():
    status, leases = _request("GET", "/leases")
    assert status == 200, f"could not list leases to clear: {status} {leases}"
    for lease in leases:
        _request("DELETE", f"/leases/{lease['id']}")


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    status, health = _request("GET", "/health")
    check("server is reachable", status == 200 and health.get("status") == "healthy")

    if not os.path.exists(STRESS_TEST_FILE):
        check("skipped: STRESS_TEST_500pg.xlsx not found at the known local path (not a repo fixture)", True, STRESS_TEST_FILE)
        print("\n" + "=" * 70)
        print("RESULT: 1/1 checks passed (skipped -- fixture not present on this machine)")
        print("=" * 70)
        return True

    try:
        clear_all_leases()

        with open(STRESS_TEST_FILE, "rb") as f:
            content = f.read()

        print(f"\n--- Importing {STRESS_TEST_FILE} ({len(content)/1024:.0f} KB) ---")
        body, ct = _multipart_body({}, [("file", "STRESS_TEST_500pg.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")])
        t0 = time.time()
        status, result = _request("POST", "/leases/import-rent-roll", data=body, headers={"Content-Type": ct})
        elapsed = time.time() - t0
        check("rent roll import succeeds", status == 201, str(status))
        imported_count = result.get("imported_count", 0) if isinstance(result, dict) else 0
        check(f"import completes in well under {MAX_UPLOAD_SECONDS}s", elapsed < MAX_UPLOAD_SECONDS, f"{elapsed:.2f}s for {imported_count} leases")
        print(f"  imported {imported_count} leases in {elapsed:.2f}s")

        print("\n--- Dashboard queries at real scale ---")
        for path in ["/leases", "/portfolio/summary", "/portfolio/risks", "/portfolio/health-score", "/portfolio/trends"]:
            t0 = time.time()
            status, _ = _request("GET", path)
            elapsed = time.time() - t0
            check(f"GET {path} returns 200 and completes in well under {MAX_DASHBOARD_QUERY_SECONDS}s at {imported_count}-lease scale", status == 200 and elapsed < MAX_DASHBOARD_QUERY_SECONDS, f"{elapsed:.3f}s")

        t0 = time.time()
        status, _ = _request("POST", "/alerts/generate")
        elapsed = time.time() - t0
        check(f"POST /alerts/generate completes in well under {MAX_DASHBOARD_QUERY_SECONDS}s at {imported_count}-lease scale", status == 200 and elapsed < MAX_DASHBOARD_QUERY_SECONDS, f"{elapsed:.3f}s")

    finally:
        print("\nCleaning up test data...")
        clear_all_leases()
        status, remaining = _request("GET", "/leases")
        check("cleanup leaves DB empty", status == 200 and remaining == [], f"{len(remaining) if isinstance(remaining, list) else remaining} leases remain")

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    print("=" * 70)

    failed = [c for c in checks if not c[1]]
    if failed:
        print("\nFAILED:")
        for name, _, detail in failed:
            print(f"  - {name}: {detail}")

    return len(failed) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
