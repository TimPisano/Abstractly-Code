"""
Regression test for a real, confirmed race condition in
database.upsert_discrepancy / database.upsert_alert: both used to
SELECT to check whether a natural_key already existed, then branch
into INSERT or UPDATE. Two concurrent requests recomputing the same
natural_key (e.g. two people uploading the same rent roll at once, or
two browser tabs both hitting /portfolio/risks) could both see "not
found yet" and both attempt to INSERT, and the loser would hit the
natural_key UNIQUE constraint as an uncaught IntegrityError -- which
the global Flask error handler turns into a generic, unhelpful 500
rather than a successful sync. Reproduced directly with a 5-thread
race against a bare SQLite table sharing the same UNIQUE-constrained
pattern before this fix (4 of 5 threads failed). Fixed by rewriting
both functions to use a single atomic
`INSERT ... ON CONFLICT(natural_key) DO UPDATE SET ...` statement, so
SQLite itself serializes the check-and-act instead of two Python
statements racing across connections. See DECISIONS.md.

This file exercises the real database.py functions (not a toy
reproduction) under real thread concurrency, against an isolated temp
SQLite file, same pattern as test_discrepancies.py.
"""

import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import database


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def main():
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✓" if cond else "✗"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    db_path = _fresh_temp_db()
    try:
        # ---- Concurrent upsert_discrepancy on the same natural_key ----
        print("--- Concurrent upsert_discrepancy on the same natural_key ---")
        errors = []
        ids = []
        lock = threading.Lock()

        def race_discrepancy(i):
            try:
                result_id = database.upsert_discrepancy(
                    discrepancy_type="test_type",
                    natural_key="race_key_1",
                    category="cat",
                    message=f"msg from thread {i}",
                    details={"i": i},
                )
                with lock:
                    ids.append(result_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=race_discrepancy, args=(i,)) for i in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check("25 concurrent upsert_discrepancy calls on the same natural_key raise no errors", errors == [], str(errors))
        check("all 25 calls returned the same discrepancy id (one row, not duplicates)", len(set(ids)) == 1, str(set(ids)))

        conn = database.get_connection()
        rows = conn.execute("SELECT * FROM discrepancies WHERE natural_key = ?", ("race_key_1",)).fetchall()
        conn.close()
        check("exactly one discrepancy row exists for the raced natural_key", len(rows) == 1, f"{len(rows)} rows")

        # ---- Concurrent upsert_alert, including the auto_resolved -> active transition ----
        print("\n--- Concurrent upsert_alert on the same natural_key, from auto_resolved ---")
        database.upsert_alert(alert_type="t", natural_key="alert_key_1", severity="high", title="T", message="M", details={})
        conn = database.get_connection()
        conn.execute("UPDATE alerts SET status = 'auto_resolved' WHERE natural_key = ?", ("alert_key_1",))
        conn.commit()
        conn.close()

        alert_errors = []
        alert_ids = []

        def race_alert(i):
            try:
                result_id = database.upsert_alert(
                    alert_type="t", natural_key="alert_key_1", severity="high", title="T",
                    message=f"M{i}", details={"i": i},
                )
                with lock:
                    alert_ids.append(result_id)
            except Exception as e:
                with lock:
                    alert_errors.append(e)

        threads2 = [threading.Thread(target=race_alert, args=(i,)) for i in range(25)]
        for t in threads2:
            t.start()
        for t in threads2:
            t.join()

        check("25 concurrent upsert_alert calls on the same natural_key raise no errors", alert_errors == [], str(alert_errors))
        check("all 25 calls returned the same alert id (one row, not duplicates)", len(set(alert_ids)) == 1, str(set(alert_ids)))

        conn = database.get_connection()
        alert_rows = conn.execute("SELECT status FROM alerts WHERE natural_key = ?", ("alert_key_1",)).fetchall()
        conn.close()
        check("exactly one alert row exists for the raced natural_key", len(alert_rows) == 1, f"{len(alert_rows)} rows")
        check(
            "concurrent re-sync still flips auto_resolved -> active (status-transition rule preserved under the atomic upsert)",
            len(alert_rows) == 1 and alert_rows[0]["status"] == "active",
            str([dict(r) for r in alert_rows]),
        )

        # ---- A resolved discrepancy's status is never touched by a concurrent re-sync ----
        print("\n--- Concurrent re-sync never touches a resolved discrepancy's status ---")
        disc_id = database.upsert_discrepancy(
            discrepancy_type="test_type", natural_key="resolved_key_1", category="cat",
            message="original", details={},
        )
        database.resolve_discrepancy(disc_id, correct_source="lease_document", note="reviewed", resolved_by="Jane")

        resync_errors = []

        def resync(i):
            try:
                database.upsert_discrepancy(
                    discrepancy_type="test_type", natural_key="resolved_key_1", category="cat",
                    message=f"resync {i}", details={"i": i},
                )
            except Exception as e:
                with lock:
                    resync_errors.append(e)

        threads3 = [threading.Thread(target=resync, args=(i,)) for i in range(10)]
        for t in threads3:
            t.start()
        for t in threads3:
            t.join()

        check("concurrent re-sync of a resolved discrepancy raises no errors", resync_errors == [], str(resync_errors))
        conn = database.get_connection()
        row = conn.execute("SELECT status, message FROM discrepancies WHERE id = ?", (disc_id,)).fetchone()
        conn.close()
        check("status stays 'resolved' after concurrent re-sync (never silently reopened)", row["status"] == "resolved", str(dict(row)))
        check("message snapshot still refreshes on re-sync", row["message"].startswith("resync"), str(dict(row)))

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
