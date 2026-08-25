"""
Performance regression tests at real portfolio scale. These exist to
catch the two N+1 patterns found and fixed during the reliability
hardening pass -- see DECISIONS.md:

1. database.get_all_effective_leases() used to call get_lease() and
   get_amendments() (each opening its OWN sqlite3 connection) 2x
   each per lease. At 831 leases (the real 500-unit synthetic rent
   roll's actual imported count, most units splitting into one lease
   each plus some skipped/header rows) that was ~1.7s on every single
   call, on nearly every portfolio-wide endpoint (they all read
   through this one function) -- fixed by fetching every lease in one
   query and merging amendments in Python.

2. GET /portfolio/risks and POST /alerts/generate individually
   upserted one discrepancy/alert row per flag/candidate (each its own
   connect()+commit()), which at thousands of flags/candidates was the
   dominant cost (~2.4-2.9s) purely from per-call overhead, not query
   complexity -- fixed by database.upsert_discrepancies_bulk /
   upsert_alerts_bulk, which share one connection and one commit
   across the whole batch.

These thresholds are deliberately generous (not tight benchmarks) --
the point is to catch a REGRESSION back to O(n) connections per
request, not to enforce a specific number. Uses an isolated temp
SQLite file, same pattern as test_discrepancies.py; no live server
required.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import database
from app.portfolio import FIELD_NAMES, portfolio_context_for_risk_analysis, compute_cross_lease_mismatches
from app.risk_analysis import analyze_lease_risks
from app.discrepancies import sync_all_lease_risk_flags_bulk

LEASE_COUNT = 600


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _fields(rent, sqft, tenant, i):
    result = {}
    for name in FIELD_NAMES:
        if name == "rent_amount":
            value = f"${rent:,}/year" if rent is not None else None
        elif name == "square_footage":
            value = f"{sqft:,} sq ft" if sqft is not None else None
        elif name == "tenant":
            value = tenant
        elif name == "property_address":
            # Distinct per lease (unit number baked in), same as a
            # real rent roll's per-unit address -- NOT the same
            # address for every lease. compute_cross_lease_mismatches
            # does an O(group_size^2) pairwise comparison within each
            # shared-address group; giving every synthetic lease the
            # identical address here would create one artificial
            # 600-lease group (~180K pairwise comparisons) that
            # doesn't reflect how a real multi-unit rent roll imports
            # (each unit's address includes its own unit number).
            value = f"100 Main St, Unit {i}"
        else:
            value = None
        if value is None:
            result[name] = {"value": None, "source": None, "confidence": None}
        else:
            result[name] = {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
    return result


def _seed_leases(n):
    for i in range(n):
        # Every fourth lease deliberately omits square_footage so
        # analyze_lease_risks has something realistic to flag (missing
        # field / below-market-rent style checks), same as a real
        # messy portfolio -- an all-clean synthetic dataset wouldn't
        # exercise the discrepancy-sync path this test is timing.
        sqft = None if i % 4 == 0 else 1000 + i
        database.insert_lease(
            filename=f"lease_{i}.pdf",
            extracted_fields=_fields(rent=1500 + i, sqft=sqft, tenant=f"Tenant {i} LLC", i=i),
        )


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    db_path = _fresh_temp_db()
    try:
        # ---- Schema-level regression guard for the O(n^2) import bug ----
        # get_amendments()'s `WHERE base_lease_id = ?` had no index to
        # use (SQLite doesn't auto-index a bare FOREIGN KEY column),
        # so it full-table-scanned `leases` on every call -- and it's
        # called once per row during a rent-roll import (via
        # get_effective_lease). Importing row N did an O(N) scan just
        # to confirm row N has no amendments yet, making an M-row
        # import O(M^2) overall. Measured directly: a 20,000-row
        # synthetic import took over 2 minutes (still climbing) before
        # the index existed, and ~31s after. A timing assertion here
        # would be slow (needs thousands of rows to show the
        # quadratic blowup) and scale-dependent/flaky -- checking the
        # index itself exists is exact and instant.
        conn = database.get_connection()
        indexes = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='leases'"
        ).fetchall()}
        conn.close()
        check("leases.base_lease_id has an index (regression guard against the O(n^2) import bug)", "idx_leases_base_lease_id" in indexes, str(indexes))

        print(f"--- Seeding {LEASE_COUNT} synthetic leases ---")
        _seed_leases(LEASE_COUNT)

        print("\n--- database.get_all_effective_leases() at scale ---")
        t0 = time.time()
        leases = database.get_all_effective_leases()
        elapsed = time.time() - t0
        check(f"get_all_effective_leases returns all {LEASE_COUNT} leases", len(leases) == LEASE_COUNT, f"got {len(leases)}")
        check(f"get_all_effective_leases completes in well under 1s for {LEASE_COUNT} leases (regression guard against the old N+1 pattern)", elapsed < 1.0, f"{elapsed:.3f}s")
        print(f"  time: {elapsed:.3f}s")

        print("\n--- Full /portfolio/risks-equivalent pass (analyze + bulk sync) ---")
        t0 = time.time()
        context = portfolio_context_for_risk_analysis(leases)
        cross_lease_mismatches = compute_cross_lease_mismatches(leases)
        per_lease_flags = []
        total_flags = 0
        for lease in leases:
            flags = analyze_lease_risks(
                lease["extracted_fields"], context, lease.get("date_candidates"),
                cross_lease_mismatches.get(lease["id"], []),
            )
            per_lease_flags.append((lease["id"], flags))
            total_flags += len(flags)
        sync_all_lease_risk_flags_bulk(per_lease_flags)
        elapsed = time.time() - t0
        check(f"risk analysis + bulk discrepancy sync produced flags", total_flags > 0, f"{total_flags} flags")
        check(f"full risk analysis + sync pass completes in well under 2s for {LEASE_COUNT} leases / {total_flags} flags", elapsed < 2.0, f"{elapsed:.3f}s")
        print(f"  time: {elapsed:.3f}s  ({total_flags} flags)")

        # Every flag must actually be annotated (discrepancy_id present) --
        # a silent no-op bulk sync would still be "fast" but wrong.
        annotated = all("discrepancy_id" in flag for _, flags in per_lease_flags for flag in flags)
        check("every flag was annotated with a discrepancy_id by the bulk sync", annotated)

        # Distinct natural_keys, not raw flag count: a cross_lease_mismatch
        # flag is emitted once per lease in the pair (each lease's own
        # perspective) but both share ONE natural_key and therefore
        # collapse to ONE discrepancy row -- same as calling
        # sync_lease_risk_flags per-lease would produce, see
        # sync_all_lease_risk_flags_bulk's docstring.
        distinct_natural_keys = len({
            f["discrepancy_id"] for _, flags in per_lease_flags for f in flags
        })
        conn = database.get_connection()
        disc_count = conn.execute("SELECT COUNT(*) AS n FROM discrepancies").fetchone()["n"]
        conn.close()
        check("discrepancies were actually persisted, one row per distinct natural_key", disc_count == distinct_natural_keys, f"{disc_count} rows vs {distinct_natural_keys} distinct keys ({total_flags} total flags)")

        # ---- Re-running the same sync must be idempotent and still fast ----
        print("\n--- Re-running the same sync (idempotency + repeat-call performance) ---")
        t0 = time.time()
        sync_all_lease_risk_flags_bulk(per_lease_flags)
        elapsed = time.time() - t0
        conn = database.get_connection()
        disc_count_2 = conn.execute("SELECT COUNT(*) AS n FROM discrepancies").fetchone()["n"]
        conn.close()
        check("re-running the sync doesn't create duplicate discrepancy rows", disc_count_2 == disc_count, f"{disc_count} -> {disc_count_2}")
        check("repeat sync is still well under 2s", elapsed < 2.0, f"{elapsed:.3f}s")

    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass

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
