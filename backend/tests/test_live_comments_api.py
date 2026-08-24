"""
Live API regression suite for the collaboration layer
(GET/POST /leases/<id>/comments, /discrepancies/<id>/comments) --
follows the exact convention established by test_live_discrepancies_api.py:
runs against the actually-running dev server over real HTTP,
specifically to catch "the route/logic is right in the source file, but
the currently-running server process is stale" (a real bug class this
project has hit before -- see DECISIONS.md).

Simulates two different team members (two independent HTTP clients,
no shared session/cookie state) leaving notes on the same real lease
and the same real discrepancy, confirming both are visible to a third,
completely fresh reader -- the actual point of "visible to the whole
team."
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
    boundary = "----CommentsApiTestBoundary"
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

        print("\n--- Real lease upload + comments from two independent team members ----")
        body, content_type = _multipart_body(
            {}, [("file", "missing_clauses_office.pdf", _read_fixture("missing_clauses_office.pdf"), "application/pdf")]
        )
        status, result = _request("POST", "/leases", data=body, headers={"Content-Type": content_type})
        check("lease upload succeeds", status == 201, str(result))
        lease_id = result["leases"][0]["id"]
        created_lease_ids.append(lease_id)

        status, comments = _request("GET", f"/leases/{lease_id}/comments")
        check("no comments yet on a fresh lease", status == 200 and comments == [], str(comments))

        status, after_first = _request("POST", f"/leases/{lease_id}/comments", json_body={
            "author_name": "Jane Analyst", "author_email": "jane@example.com", "body": "First pass done, looks reasonable.",
        })
        check("first team member's comment succeeds (201)", status == 201, str(after_first))

        status, after_second = _request("POST", f"/leases/{lease_id}/comments", json_body={
            "author_name": "Bob Reviewer", "body": "Agreed, ready to move forward.",
        })
        check("second team member's comment succeeds (201)", status == 201, str(after_second))
        check("both comments visible together, in order", len(after_second) == 2 and after_second[0]["author_name"] == "Jane Analyst" and after_second[1]["author_name"] == "Bob Reviewer", str(after_second))

        status, fresh_read = _request("GET", f"/leases/{lease_id}/comments")
        check("a completely fresh GET (third reader) sees both comments", status == 200 and len(fresh_read) == 2, str(fresh_read))

        status, err = _request("POST", f"/leases/{lease_id}/comments", json_body={"body": "no author name"})
        check("missing author_name returns 400", status == 400, str(err))
        status, err = _request("GET", "/leases/999999/comments")
        check("nonexistent lease returns 404", status == 404, str(err))

        # ---- Discrepancy comments ----
        print("\n--- Real discrepancy comments ----")
        status, flags = _request("GET", f"/leases/{lease_id}/risks")
        check("real flags exist to comment on", status == 200 and len(flags) > 0, str(flags))
        disc_id = flags[0]["discrepancy_id"]

        status, disc_comments = _request("POST", f"/discrepancies/{disc_id}/comments", json_body={
            "author_name": "Jane Analyst", "body": "Confirmed with the broker -- intentional, not an error.",
        })
        check("discrepancy comment succeeds (201)", status == 201, str(disc_comments))

        status, fresh_disc_comments = _request("GET", f"/discrepancies/{disc_id}/comments")
        check("discrepancy comment visible on a fresh read", status == 200 and len(fresh_disc_comments) == 1, str(fresh_disc_comments))

        status, err = _request("GET", "/discrepancies/999999/comments")
        check("nonexistent discrepancy returns 404", status == 404, str(err))
        status, err = _request("POST", "/discrepancies/999999/comments", json_body={"author_name": "x", "body": "y"})
        check("posting to nonexistent discrepancy returns 404", status == 404, str(err))

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
