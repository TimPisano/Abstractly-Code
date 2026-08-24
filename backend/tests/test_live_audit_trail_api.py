"""
Live API regression suite for GET /leases/<id>/fields/<field_name>/source
-- follows the exact convention established by test_live_t12_api.py /
test_live_composition_api.py: runs against the actually-running dev
server over real HTTP, not Flask's test_client(), specifically because
test_client() re-imports the app fresh every run and so can never catch
"the route/logic is right in the source file, but the currently-running
server process is stale" -- a real bug class this project has hit
before (see DECISIONS.md).

Covers: a real PDF upload's field source chain (page + quote), a real
amendment overriding a field and the chain showing both the base
lease's original value and the amendment's, the 400/404 error paths,
and that a rent-roll-imported lease's source cites row/file instead of
page.
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
    boundary = "----AuditTrailApiTestBoundary"
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

        # ---- Real PDF upload: page + quote citation ----
        print("\n--- Real PDF upload ----")
        body, content_type = _multipart_body(
            {}, [("file", "sample_lease_commercial.pdf", _read_fixture("sample_lease_commercial.pdf"), "application/pdf")]
        )
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
        check("lease upload succeeds", status == 201, str(result))
        base_id = result["leases"][0]["id"]
        created_lease_ids.append(base_id)

        status, chain = _request("GET", f"/leases/{base_id}/fields/tenant/source")
        check("field source route returns 200", status == 200, str(chain))
        check(
            "effective value matches the real extracted tenant",
            chain.get("effective_value") == "Blue Sky Coffee Roasters, Inc.",
            str(chain.get("effective_value")),
        )
        check("source cites a real page number", isinstance((chain.get("effective_source") or {}).get("page"), int), str(chain.get("effective_source")))
        check("source cites a real quote", bool((chain.get("effective_source") or {}).get("quote")), str(chain.get("effective_source")))
        check("history has exactly 1 entry (no amendments yet)", len(chain.get("history", [])) == 1, str(chain.get("history")))

        # ---- Error paths ----
        print("\n--- Error paths ----")
        status, err = _request("GET", f"/leases/{base_id}/fields/not_a_real_field/source")
        check("unknown field returns 400", status == 400 and "error" in err, f"{status} {err}")
        status, err = _request("GET", "/leases/999999/fields/tenant/source")
        check("nonexistent lease returns 404", status == 404 and "error" in err, f"{status} {err}")

        # ---- Amendment override: full history, not just the winner ----
        print("\n--- Real amendment overriding rent_amount ----")
        amendment_body, amendment_content_type = _multipart_body(
            {}, [("file", "retail_lease.pdf", _read_fixture("retail_lease.pdf"), "application/pdf")]
        )
        status, amend_result = _request(
            "POST", f"/leases/{base_id}/amendments", data=amendment_body, headers={"Content-Type": amendment_content_type}
        )
        check("amendment upload succeeds", status == 201, str(amend_result))

        status, chain = _request("GET", f"/leases/{base_id}/fields/tenant/source")
        check("chain now has 2 history entries (base + amendment)", len(chain.get("history", [])) == 2, str(chain.get("history")))
        check("effective document is now the amendment, not the base lease", chain.get("effective_document_id") != base_id, str(chain))
        history = chain.get("history", [])
        if len(history) == 2:
            check("first history entry is the base lease's original value, marked non-effective", history[0]["value"] == "Blue Sky Coffee Roasters, Inc." and history[0]["is_effective"] is False, str(history[0]))
            check("second history entry is the amendment's value, marked effective", history[1]["is_effective"] is True, str(history[1]))

        # ---- Rent-roll-imported lease: row/file citation, not page ----
        print("\n--- Real rent roll import ----")
        rr_body, rr_content_type = _multipart_body(
            {}, [("file", "synthetic_yardi_rent_roll.csv", _read_fixture("synthetic_yardi_rent_roll.csv"), "text/csv")]
        )
        status, rr_result = _request("POST", "/leases/import-rent-roll", data=rr_body, headers={"Content-Type": rr_content_type})
        check("rent roll import succeeds", status == 201, str(rr_result))
        rr_lease_ids = [l["id"] for l in rr_result.get("leases", [])]
        created_lease_ids.extend(rr_lease_ids)
        check("rent roll import created at least 1 lease", len(rr_lease_ids) > 0, str(rr_result))

        if rr_lease_ids:
            status, chain = _request("GET", f"/leases/{rr_lease_ids[0]}/fields/tenant/source")
            check("rent-roll field source returns 200", status == 200, str(chain))
            source = chain.get("effective_source") or {}
            check("rent-roll source cites a row number, not a page", source.get("row") is not None and source.get("page") is None, str(source))
            check("rent-roll source cites the source file", source.get("file") == "synthetic_yardi_rent_roll.csv", str(source))

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
