"""
Live API regression suite for GET /portfolio/health-score -- follows
the exact convention established by test_live_discrepancies_api.py:
runs against the actually-running dev server over real HTTP,
specifically to catch "the route/logic is right in the source file,
but the currently-running server process is stale" (a real bug class
this project has hit before -- see DECISIONS.md).

Uses real fixture uploads (not synthetic in-memory field dicts, unlike
the unit test suite) to confirm the score responds to real, live data:
an empty portfolio, a clean well-extracted lease, and a real messy
fixture that produces real open discrepancies -- then confirms
resolving those discrepancies live measurably improves the score.
"""
import os
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

API_BASE_URL = "http://localhost:5000"
FIXTURES_DIR = os.path.dirname(__file__)


def _request(method, path, data=None, json_body=None, headers=None):
    url = f"{API_BASE_URL}{path}"
    body = None
    req_headers = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body).encode()
        req_headers["Content-Type"] = "application/json"
    elif data is not None:
        body = data

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
    boundary = "----HealthScoreApiTestBoundary"
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


def _read_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    status, health_check = _request("GET", "/health")
    check("server is reachable", status == 200 and health_check.get("status") == "healthy")

    created_lease_ids = []
    try:
        clear_all_leases()

        # ---- Empty portfolio: honest "No Data", not a fabricated 0 ----
        print("\n--- Empty portfolio ----")
        status, empty_result = _request("GET", "/portfolio/health-score")
        check("route returns 200 for an empty portfolio", status == 200, str(status))
        check("empty portfolio is 'No Data', not score 0", empty_result.get("score") is None and empty_result.get("rating") == "No Data", str(empty_result))

        # ---- A real, well-extracted lease ----
        print("\n--- Real clean lease upload ----")
        body, ct = _multipart_body({}, [("file", "sample_lease_commercial.pdf", _read_fixture("sample_lease_commercial.pdf"), "application/pdf")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        check("clean lease upload succeeds", status == 201, str(result))
        created_lease_ids.append(result["leases"][0]["id"])

        status, clean_score = _request("GET", "/portfolio/health-score")
        check("score route returns 200", status == 200, str(clean_score))
        check("a real well-extracted lease scores reasonably high", clean_score["score"] is not None and clean_score["score"] >= 60, str(clean_score))
        check("source_verification is 100 for a fully-extracted lease", clean_score["components"]["source_verification"]["score"] == 100.0, str(clean_score["components"]["source_verification"]))
        check("data_freshness is 100 for a just-uploaded lease", clean_score["components"]["data_freshness"]["score"] == 100.0, str(clean_score["components"]["data_freshness"]))

        # ---- A real messy fixture that produces real discrepancies ----
        print("\n--- Real messy lease + real discrepancies ----")
        body, ct = _multipart_body({}, [("file", "missing_clauses_office.pdf", _read_fixture("missing_clauses_office.pdf"), "application/pdf")])
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": ct})
        check("messy lease upload succeeds", status == 201, str(result))
        messy_lease_id = result["leases"][0]["id"]
        created_lease_ids.append(messy_lease_id)

        status, flags = _request("GET", f"/leases/{messy_lease_id}/risks")
        check("real risk flags exist (become open discrepancies)", status == 200 and len(flags) > 0, str(flags))
        disc_ids = [f["discrepancy_id"] for f in flags]

        status, messy_score = _request("GET", "/portfolio/health-score")
        check("score reflects the new open discrepancies", messy_score["components"]["unresolved_discrepancies"]["open_count"] >= len(disc_ids), str(messy_score["components"]["unresolved_discrepancies"]))
        check("score dropped after adding real open discrepancies", messy_score["score"] < clean_score["score"], f"{messy_score['score']} vs {clean_score['score']}")

        # ---- Resolving the discrepancies must measurably improve the score ----
        print("\n--- Resolving real discrepancies improves the score ----")
        for disc_id in disc_ids:
            _request("POST", f"/discrepancies/{disc_id}/resolve", json_body={
                "correct_source": "lease_document", "note": "Reviewed and accepted.", "resolved_by": "Jane Analyst",
            })

        status, resolved_score = _request("GET", "/portfolio/health-score")
        check("open_count drops to what it was before (0 new ones)", resolved_score["components"]["unresolved_discrepancies"]["open_count"] < messy_score["components"]["unresolved_discrepancies"]["open_count"], str(resolved_score["components"]["unresolved_discrepancies"]))
        check("score improves after resolving the discrepancies", resolved_score["score"] > messy_score["score"], f"{resolved_score['score']} vs {messy_score['score']}")

        # ---- Custom staleness threshold + validation ----
        print("\n--- Query param handling ----")
        status, custom = _request("GET", "/portfolio/health-score?staleness_threshold_months=1")
        check("custom staleness_threshold_months accepted", status == 200 and custom["components"]["data_freshness"]["threshold_months"] == 1.0, str(custom))

        status, err = _request("GET", "/portfolio/health-score?staleness_threshold_months=not_a_number")
        check("invalid staleness_threshold_months returns 400", status == 400, str(err))

        status, err = _request("GET", "/portfolio/health-score?staleness_threshold_months=-3")
        check("negative staleness_threshold_months returns 400", status == 400, str(err))

    finally:
        print("\nCleaning up test data...")
        for lease_id in created_lease_ids:
            _request("DELETE", f"/leases/{lease_id}")
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
