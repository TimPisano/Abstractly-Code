"""
Tests for app/cache.py itself (get_or_compute, prefix-based
invalidate, TTL expiry) and for the REAL invalidation hooks wired into
api.py's mutation routes -- proving that uploading a lease, deleting
one, or resolving a discrepancy through the real API actually busts
the cached health-score/trends result, not just that the cache
primitive works in isolation.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_portfolio_health_score.py. Every test calls
cache.invalidate_all() itself where it matters (in addition to
database.configure()'s own automatic clear -- see that function's
docstring) to keep each test's cache state fully self-contained.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api import app
from app import database
from app import cache
from app.portfolio import FIELD_NAMES


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _fields(**overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            result[name] = {"value": overrides[name], "source": {"page": 1, "quote": "q"}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


# ------------------------------------------------------------------
# app/cache.py primitives
# ------------------------------------------------------------------

def test_get_or_compute_returns_cached_value_without_recomputing():
    cache.invalidate_all()
    try:
        calls = []

        def compute():
            calls.append(1)
            return "the answer"

        first = cache.get_or_compute("k1", compute)
        second = cache.get_or_compute("k1", compute)
        assert first == "the answer"
        assert second == "the answer"
        assert len(calls) == 1, "compute_fn must only run once -- the second call should be served from cache"
    finally:
        cache.invalidate_all()
    print("✓ test_get_or_compute_returns_cached_value_without_recomputing: PASS")


def test_invalidate_by_prefix_clears_only_matching_keys():
    cache.invalidate_all()
    try:
        cache.get_or_compute("trends:portfolio", lambda: "A")
        cache.get_or_compute("trends:property:1 Main St", lambda: "B")
        cache.get_or_compute("health_score:6.0", lambda: "C")

        cache.invalidate("trends")

        recompute_calls = []
        assert cache.get_or_compute("trends:portfolio", lambda: recompute_calls.append(1) or "A2") == "A2", "trends:* must have been cleared"
        assert cache.get_or_compute("trends:property:1 Main St", lambda: recompute_calls.append(1) or "B2") == "B2"
        assert len(recompute_calls) == 2, "both trends: keys must have been recomputed"

        # health_score:* must NOT have been touched by invalidate("trends")
        untouched_calls = []
        assert cache.get_or_compute("health_score:6.0", lambda: untouched_calls.append(1) or "C2") == "C", "health_score:6.0 must still be the original cached value"
        assert len(untouched_calls) == 0
    finally:
        cache.invalidate_all()
    print("✓ test_invalidate_by_prefix_clears_only_matching_keys: PASS")


def test_ttl_expiry_recomputes_after_expiring():
    cache.invalidate_all()
    try:
        calls = []
        cache.get_or_compute("short_lived", lambda: calls.append(1) or "v1", ttl_seconds=0.05)
        time.sleep(0.1)
        result = cache.get_or_compute("short_lived", lambda: calls.append(1) or "v2", ttl_seconds=0.05)
        assert result == "v2", "an expired entry must be recomputed, not served stale"
        assert len(calls) == 2
    finally:
        cache.invalidate_all()
    print("✓ test_ttl_expiry_recomputes_after_expiring: PASS")


def test_database_configure_clears_the_cache():
    """The exact bug this test guards against: a fresh temp DB per test function must not inherit a cached result computed against a PREVIOUS test's (or a previous call's) database."""
    cache.get_or_compute("some_key", lambda: "stale_value_from_before_configure")
    _fresh_temp_db()  # calls database.configure() internally
    result = cache.get_or_compute("some_key", lambda: "fresh_value_after_configure")
    assert result == "fresh_value_after_configure", "configure() must clear the cache"
    print("✓ test_database_configure_clears_the_cache: PASS")


# ------------------------------------------------------------------
# Real invalidation hooks, through the real API routes
# ------------------------------------------------------------------

def test_uploading_a_lease_through_the_api_busts_the_health_score_cache():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()

        resp = client.get("/portfolio/health-score")
        assert resp.get_json()["rating"] == "No Data", "must start with an empty, cached 'No Data' result"

        database.insert_lease("a.pdf", _fields(tenant="Acme", rent_amount="$5,000.00", landlord="L", lease_start_date="Jan 1, 2025", lease_end_date="Jan 1, 2030"))
        # NOT calling cache.invalidate_all() here -- the whole point of
        # this test is that a REAL API route (below) does the
        # invalidation itself. A direct database.insert_lease() (like
        # the line above) does NOT trigger it -- confirmed first,
        # deliberately, so the next assertion actually proves something.
        resp = client.get("/portfolio/health-score")
        assert resp.get_json()["rating"] == "No Data", "a direct DB insert (bypassing the API) must NOT bust the cache -- confirms the cache is real, not a no-op"

        # Now do it through the real POST /leases route, which DOES have the invalidation hook
        with open(os.path.join(os.path.dirname(__file__), "sample_lease_commercial.pdf"), "rb") as f:
            content = f.read()
        resp = client.post("/leases", data={"file": (__import__("io").BytesIO(content), "sample_lease_commercial.pdf")}, content_type="multipart/form-data")
        assert resp.status_code == 201

        resp = client.get("/portfolio/health-score")
        assert resp.get_json()["rating"] != "No Data", "the real upload route must have busted the cache -- this must now reflect 2 real leases, not the stale 'No Data' result"
    finally:
        os.unlink(db_path)
    print("✓ test_uploading_a_lease_through_the_api_busts_the_health_score_cache: PASS")


def test_deleting_a_lease_through_the_api_busts_the_trends_cache():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("a.pdf", _fields(tenant="Acme", rent_amount="$5,000.00", property_address="1 Main St"))

        resp = client.get("/portfolio/trends")
        assert resp.get_json()["property_count"] == 1

        resp = client.delete(f"/leases/{lease_id}")
        assert resp.status_code == 200

        resp = client.get("/portfolio/trends")
        assert resp.get_json()["property_count"] == 0, "the real DELETE route must have busted the trends cache"
    finally:
        os.unlink(db_path)
    print("✓ test_deleting_a_lease_through_the_api_busts_the_trends_cache: PASS")


def test_resolving_a_discrepancy_through_the_api_busts_the_health_score_cache():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        lease_id = database.insert_lease("a.pdf", _fields())  # missing everything -> real flags
        flags = client.get(f"/leases/{lease_id}/risks").get_json()
        assert flags, "fixture must produce at least one real discrepancy"
        disc_id = flags[0]["discrepancy_id"]

        first = client.get("/portfolio/health-score").get_json()
        open_count_before = first["components"]["unresolved_discrepancies"]["open_count"]
        assert open_count_before > 0

        resp = client.post(f"/discrepancies/{disc_id}/resolve", json={
            "correct_source": "lease_document", "note": "confirmed fine", "resolved_by": "Jane",
        })
        assert resp.status_code == 200

        second = client.get("/portfolio/health-score").get_json()
        assert second["components"]["unresolved_discrepancies"]["open_count"] == open_count_before - 1, "resolving through the real route must have busted the cache"
    finally:
        os.unlink(db_path)
    print("✓ test_resolving_a_discrepancy_through_the_api_busts_the_health_score_cache: PASS")


def test_health_score_cache_key_is_scoped_by_staleness_threshold():
    """Two different staleness_threshold_months values must not collide onto the same cache entry -- confirmed with values chosen so the answer is actually different for each."""
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        old_timestamp = "2020-01-01T00:00:00+00:00"
        lease_id = database.insert_lease("a.pdf", _fields(tenant="Acme", rent_amount="$5,000.00", landlord="L", lease_start_date="Jan 1, 2025", lease_end_date="Jan 1, 2030"))
        conn = database.get_connection()
        conn.execute("UPDATE leases SET uploaded_at = ? WHERE id = ?", (old_timestamp, lease_id))
        conn.commit()
        conn.close()
        cache.invalidate_all()

        resp_1mo = client.get("/portfolio/health-score?staleness_threshold_months=1")
        resp_1200mo = client.get("/portfolio/health-score?staleness_threshold_months=1200")
        assert resp_1mo.get_json()["components"]["data_freshness"]["score"] == 0.0
        assert resp_1200mo.get_json()["components"]["data_freshness"]["score"] == 100.0
    finally:
        os.unlink(db_path)
    print("✓ test_health_score_cache_key_is_scoped_by_staleness_threshold: PASS")


if __name__ == "__main__":
    test_get_or_compute_returns_cached_value_without_recomputing()
    test_invalidate_by_prefix_clears_only_matching_keys()
    test_ttl_expiry_recomputes_after_expiring()
    test_database_configure_clears_the_cache()
    test_uploading_a_lease_through_the_api_busts_the_health_score_cache()
    test_deleting_a_lease_through_the_api_busts_the_trends_cache()
    test_resolving_a_discrepancy_through_the_api_busts_the_health_score_cache()
    test_health_score_cache_key_is_scoped_by_staleness_threshold()
    print("\nAll cache tests passed.")
