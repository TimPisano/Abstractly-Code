"""
Tests for the per-team monthly page limit (feature/tester-ready step 4).

Regressions covered (each failed on the code before this step):
- check_team_quota only blocked a team already AT its limit, so one big
  file could take it far past (990 used + 150 pages = allowed).
- Uploads never recorded their page count (usage_events.pages was
  always NULL), so the page limit could never be reached at all.
- check_file_limits never counted PDF pages (extract_pages(..., None)
  raised and was swallowed), so MAX_PAGES_PER_FILE was never enforced.
- POST /leases/batch skipped the quota entirely.
- POST /leases/batch skipped every pre-check single uploads get (per-file
  size and page caps, the per-user rate limit, the early PDF page check),
  so OCR/text extraction ran before the page limit could stop a file.

"Before any AI call" is checked by making every extraction step after
the page count raise if it's reached. Anthropic is never called: the
regex engine is the default, and the blocked paths stop before either.
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import io
import os
import sys
import time
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reportlab.pdfgen import canvas

from app import api as api_module
from app import database, usage_limits, usage_limits_config
from app.api import app
from test_team_invites import _Env, _bearer, _login, _make_admin


def _pdf(pages):
    """A text PDF with `pages` pages of lease-like text."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(1, pages + 1):
        c.drawString(72, 720, f"COMMERCIAL LEASE AGREEMENT - page {n}")
        c.drawString(72, 700, "Tenant: Northwind Outfitters, Inc. Landlord: Maple Ridge Holdings LLC.")
        c.drawString(72, 680, "Monthly base rent: $4,250.00. Security deposit: $8,500.00.")
        c.showPage()
    c.save()
    return buf.getvalue()


def _use_pages(team_id, pages):
    """Pretend the team already used `pages` this month (recorded against its first member)."""
    user_id = database.list_users(team_id)[0]["id"]
    usage_limits.log_usage_event(team_id, user_id, None, pages, None, event_type="extraction")


def _pages_recorded(team_id):
    conn = database.get_connection()
    try:
        return conn.execute("SELECT COALESCE(SUM(pages), 0) FROM usage_events WHERE team_id = ?", (team_id,)).fetchone()[0]
    finally:
        conn.close()


def _upload(client, token, data, name="lease.pdf"):
    return client.post("/leases", data={"file": (io.BytesIO(data), name)}, headers=_bearer(token),
                       content_type="multipart/form-data")


def _no_extraction_allowed():
    """Every step that runs after the page count -- and before/including any model call -- fails the test if reached."""
    boom = AssertionError("extraction ran for an upload that should have been turned away")
    return [
        mock.patch.object(api_module, "_split_and_extract", side_effect=boom),
        mock.patch.object(api_module.FieldExtractor, "detect_lease_boundaries", side_effect=boom),
        mock.patch.object(api_module.ai_extraction, "resolve_engine", side_effect=boom),
    ]


class _Uploads(_Env):
    def __enter__(self):
        client = super().__enter__()
        usage_limits._extraction_rate_limit_window.clear()
        return client


def test_default_monthly_page_limit_is_1000():
    assert usage_limits_config.DEFAULT_MONTHLY_PAGE_QUOTA == 1000
    with _Uploads():
        _, team_id = _make_admin()
        assert usage_limits.get_team_page_usage(team_id) == {"pages_used": 0, "page_limit": 1000, "page_limit_is_default": True}
    print("✓ test_default_monthly_page_limit_is_1000: PASS")


def test_quota_blocks_what_would_go_over_not_only_what_is_already_over():
    with _Uploads():
        _, team_id = _make_admin()
        _use_pages(team_id, 990)
        assert usage_limits.check_team_quota(team_id) is None
        assert usage_limits.check_team_quota(team_id, 10) is None, "exactly reaching the limit is allowed"
        msg = usage_limits.check_team_quota(team_id, 11)
        assert msg and "11 pages" in msg and "10 of its 1,000 monthly pages left" in msg and "Nothing was processed" in msg, msg
        _use_pages(team_id, 10)
        assert "used all 1,000 pages" in usage_limits.check_team_quota(team_id)
    print("✓ test_quota_blocks_what_would_go_over_not_only_what_is_already_over: PASS")


def test_upload_records_its_pages():
    with _Uploads() as client:
        _, team_id = _make_admin()
        token = _login(client, "avery@harbor.test")
        resp = _upload(client, token, _pdf(3))
        assert resp.status_code in (200, 201, 202), resp.get_json()
        assert _pages_recorded(team_id) == 3
        assert usage_limits.get_team_page_usage(team_id)["pages_used"] == 3
    print("✓ test_upload_records_its_pages: PASS")


def test_pdf_that_would_go_over_is_turned_away_before_any_extraction():
    with _Uploads() as client:
        _, team_id = _make_admin()
        token = _login(client, "avery@harbor.test")
        _use_pages(team_id, 995)
        patches = _no_extraction_allowed() + [
            mock.patch.object(api_module.document_extractor, "extract_pages",
                              side_effect=AssertionError("a PDF over the limit must be stopped before text extraction/OCR")),
        ]
        for p in patches:
            p.start()
        try:
            resp = _upload(client, token, _pdf(6))
        finally:
            for p in reversed(patches):
                p.stop()
        assert resp.status_code == 403, resp.get_json()
        assert "6 pages" in resp.get_json()["error"] and "5 of its 1,000" in resp.get_json()["error"]
        assert _pages_recorded(team_id) == 995, "a refused upload uses no pages"
        assert database.get_all_leases(team_id, document_type=None) == []
    print("✓ test_pdf_that_would_go_over_is_turned_away_before_any_extraction: PASS")


def test_batch_upload_respects_the_page_limit_before_any_extraction():
    with _Uploads() as client:
        _, team_id = _make_admin()
        token = _login(client, "avery@harbor.test")
        _use_pages(team_id, 998)
        patches = _no_extraction_allowed()
        for p in patches:
            p.start()
        try:
            resp = client.post("/leases/batch", data={"files": [(io.BytesIO(_pdf(4)), "a.pdf")]},
                               headers=_bearer(token), content_type="multipart/form-data")
        finally:
            for p in reversed(patches):
                p.stop()
        body = resp.get_json()
        assert body["succeeded"] == 0 and body["failed"] == 1, body
        assert "4 pages" in body["results"][0]["error"]
        assert _pages_recorded(team_id) == 998
    print("✓ test_batch_upload_respects_the_page_limit_before_any_extraction: PASS")


def _batch(client, token, files):
    return client.post("/leases/batch", data={"files": [(io.BytesIO(data), name) for name, data in files]},
                       headers=_bearer(token), content_type="multipart/form-data").get_json()


def _count_text_extraction():
    """Wraps document_extractor.extract_pages (where OCR runs) so a test can count how many files reached it."""
    return mock.patch.object(api_module.document_extractor, "extract_pages",
                             side_effect=api_module.document_extractor.extract_pages)


def test_batch_pdf_over_the_limit_is_stopped_before_text_extraction():
    with _Uploads() as client:
        _, team_id = _make_admin()
        token = _login(client, "avery@harbor.test")
        _use_pages(team_id, 998)
        with _count_text_extraction() as extract:
            body = _batch(client, token, [("a.pdf", _pdf(4))])
        assert body["succeeded"] == 0 and "4 pages" in body["results"][0]["error"], body
        assert extract.call_count == 0, "a batch PDF over the limit must be stopped before text extraction/OCR"
        assert _pages_recorded(team_id) == 998
    print("✓ test_batch_pdf_over_the_limit_is_stopped_before_text_extraction: PASS")


def test_batch_counts_earlier_files_toward_the_limit():
    with _Uploads() as client:
        _, team_id = _make_admin()
        token = _login(client, "avery@harbor.test")
        _use_pages(team_id, 995)
        with _count_text_extraction() as extract:
            body = _batch(client, token, [("first.pdf", _pdf(3)), ("second.pdf", _pdf(3))])
        first, second = body["results"]
        assert first["success"], first
        assert not second["success"] and "3 pages" in second["error"] and "2 of its 1,000" in second["error"], second
        assert extract.call_count == 1, "only the file that fit may reach text extraction"
        assert _pages_recorded(team_id) == 998
    print("✓ test_batch_counts_earlier_files_toward_the_limit: PASS")


def test_batch_enforces_the_per_file_page_and_size_caps():
    with _Uploads() as client:
        _make_admin()
        token = _login(client, "avery@harbor.test")
        too_long = usage_limits_config.MAX_PAGES_PER_FILE + 1
        with _count_text_extraction() as extract:
            long_result = _batch(client, token, [("long.pdf", _pdf(too_long))])["results"][0]
            with mock.patch.object(usage_limits, "MAX_FILE_SIZE_MB", 0.01):
                big_result = _batch(client, token, [("big.txt", b"Monthly base rent: $4,250.00.\n" * 1000)])["results"][0]
        assert not long_result["success"] and f"{too_long} exceeds limit" in long_result["error"], long_result
        assert not big_result["success"] and "File too large" in big_result["error"], big_result
        assert extract.call_count == 0
    print("✓ test_batch_enforces_the_per_file_page_and_size_caps: PASS")


def test_batch_applies_the_per_user_extraction_rate_limit():
    with _Uploads() as client:
        _make_admin()
        token = _login(client, "avery@harbor.test")
        user_id = database.get_user_by_email("avery@harbor.test")["id"]
        usage_limits._extraction_rate_limit_window[user_id] = [time.time()] * (usage_limits.EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE - 1)
        with _count_text_extraction() as extract:
            body = _batch(client, token, [("one.pdf", _pdf(1)), ("two.pdf", _pdf(1))])
        one, two = body["results"]
        assert one["success"], one
        assert not two["success"] and "Rate limit exceeded" in two["error"], two
        assert extract.call_count == 1
    print("✓ test_batch_applies_the_per_user_extraction_rate_limit: PASS")


def test_team_limit_override_applies_and_other_teams_are_unaffected():
    with _Uploads() as client:
        _, team_a = _make_admin()
        _, team_b = _make_admin(email="lee@otherfirm.test", name="Lee Park", team_name="Other Firm")
        conn = database.get_connection()
        try:
            conn.execute("UPDATE teams SET monthly_page_quota = 5 WHERE id = ?", (team_a,))
            conn.commit()
        finally:
            conn.close()
        a_token = _login(client, "avery@harbor.test")
        b_token = _login(client, "lee@otherfirm.test")
        assert _upload(client, a_token, _pdf(6)).status_code == 403
        assert _upload(client, b_token, _pdf(6)).status_code in (200, 201, 202)
        assert _pages_recorded(team_a) == 0 and _pages_recorded(team_b) == 6
    print("✓ test_team_limit_override_applies_and_other_teams_are_unaffected: PASS")


def test_pdf_over_the_per_file_page_cap_is_rejected():
    over = usage_limits_config.MAX_PAGES_PER_FILE + 1
    data = _pdf(over)
    assert usage_limits.count_pdf_pages(data) == over
    msg = usage_limits.check_file_limits(data, "long.pdf")
    assert msg and f"{over} exceeds limit of {usage_limits_config.MAX_PAGES_PER_FILE}" in msg, msg
    assert usage_limits.check_file_limits(_pdf(2), "short.pdf") is None
    assert usage_limits.check_file_limits(b"not really a pdf", "broken.pdf") is None, "unreadable PDFs are left to the extractor's specific error"
    print("✓ test_pdf_over_the_per_file_page_cap_is_rejected: PASS")


def test_owner_can_view_and_change_a_teams_page_limit():
    with _Uploads() as client:
        owner_id, _ = _make_admin(email="tim@abstractly.test", name="Owner", team_name="Legacy")
        conn = database.get_connection()
        try:
            conn.execute("UPDATE users SET is_owner = 1 WHERE id = ?", (owner_id,))
            conn.commit()
        finally:
            conn.close()
        _, team_id = _make_admin()
        owner = _bearer(_login(client, "tim@abstractly.test"))
        admin = _bearer(_login(client, "avery@harbor.test"))
        _use_pages(team_id, 12)

        detail = client.get(f"/owner/teams/{team_id}", headers=owner).get_json()
        assert detail["page_usage"] == {"pages_used": 12, "page_limit": 1000, "page_limit_is_default": True}

        assert client.patch(f"/teams/{team_id}", json={"monthly_page_quota": 2500}, headers=owner).status_code == 200
        assert usage_limits.get_team_page_usage(team_id) == {"pages_used": 12, "page_limit": 2500, "page_limit_is_default": False}
        for bad in ("2500", -1, 1.5, True, 1_000_001):
            assert client.patch(f"/teams/{team_id}", json={"monthly_page_quota": bad}, headers=owner).status_code == 400, bad
        assert client.patch(f"/teams/{team_id}", json={"monthly_page_quota": None}, headers=owner).status_code == 200
        assert usage_limits.get_team_page_usage(team_id)["page_limit_is_default"] is True

        # A team admin can't change their own limit.
        assert client.patch(f"/teams/{team_id}", json={"monthly_page_quota": 999999}, headers=admin).status_code == 404
    print("✓ test_owner_can_view_and_change_a_teams_page_limit: PASS")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} monthly page limit tests passed.")
