"""
Tests for tests/_test_env.py: the suite must never read backend/.env,
touch the real local database, or reach a real service -- in any
checkout, whatever the shell has set.

Regression: in the primary checkout (which has a real backend/.env) 9
test files failed while a worktree without one passed 89/89. Importing
app.api loaded .env, which seeded ADMIN_EMAIL as an extra user into
every test database, re-enabled a real Gmail login (tests sent real
email), turned LEASE_AI_EXTRACTION on, and ran init_db() against the
real backend/lease_portfolio.db.
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import os
import socket
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(TESTS_DIR, '..')))

from app import database

# Run in a fresh interpreter, with a shell environment like a developer's
# (secrets, flags, a DB_PATH aimed at the real database), and dotenv's
# loader replaced by a spy so a .env read is caught even in a checkout
# that has no .env file.
_CHILD = r'''
import os, sys
os.environ.update({
    "ADMIN_EMAIL": "founder@abstractly.test", "ADMIN_PASSWORD_HASH": "x",
    "EMAIL_USER": "founder@abstractly.test", "EMAIL_APP_PASSWORD": "x",
    "ANTHROPIC_API_KEY": "sk-ant-not-real", "LEASE_AI_EXTRACTION": "true",
    "LOCAL_DEV_MODE": "true", "TEAM_INVITES_ENABLED": "true",
    "DB_PATH": sys.argv[1],
})
import dotenv
dotenv_calls = []
dotenv.load_dotenv = lambda *a, **k: dotenv_calls.append(a) or True
sys.path.insert(0, sys.argv[2])
import _test_env
from app import api, database
leaked = sorted(k for k in ("ADMIN_EMAIL", "EMAIL_USER", "EMAIL_APP_PASSWORD", "ANTHROPIC_API_KEY",
                            "LEASE_AI_EXTRACTION", "LOCAL_DEV_MODE", "TEAM_INVITES_ENABLED") if os.environ.get(k))
conn = database.get_connection()
users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
conn.close()
print(repr({"dotenv_calls": len(dotenv_calls), "leaked": leaked, "users": users,
            "db": database._db_path, "temp_db": _test_env.TEST_DB_PATH}))
'''


def test_app_import_skips_dotenv_and_shell_secrets_and_uses_a_temp_db():
    with tempfile.TemporaryDirectory() as d:
        decoy = os.path.join(d, "decoy.db")
        out = subprocess.run([sys.executable, "-c", _CHILD, decoy, TESTS_DIR],
                             capture_output=True, text=True, env=dict(os.environ))
        assert out.returncode == 0, out.stderr[-2000:]
        result = eval(out.stdout.strip().splitlines()[-1])
        assert result["dotenv_calls"] == 0, "app/api.py loaded backend/.env under the test suite"
        assert result["leaked"] == [], f"settings reached the app: {result['leaked']}"
        assert result["users"] == 0, "a fresh test database must not get a seeded admin"
        assert result["db"] == result["temp_db"] and not os.path.exists(decoy), result
        assert not os.path.exists(result["temp_db"]), "the temp database is removed at exit"
    print("✓ test_app_import_skips_dotenv_and_shell_secrets_and_uses_a_temp_db: PASS")


def test_real_local_database_is_refused():
    try:
        database.configure(database.DEFAULT_DB_PATH)
    except RuntimeError as e:
        assert "real local database" in str(e)
    else:
        raise AssertionError("database.configure() accepted the real backend/lease_portfolio.db")
    assert database._db_path == _test_env.TEST_DB_PATH
    print("✓ test_real_local_database_is_refused: PASS")


def test_outbound_network_is_blocked_and_loopback_is_not():
    for target in (("api.anthropic.com", 443), ("smtp.gmail.com", 587), ("8.8.8.8", 53)):
        try:
            socket.create_connection(target, timeout=2)
        except OSError as e:
            assert "network blocked by tests/_test_env.py" in str(e), (target, e)
        else:
            raise AssertionError(f"tests reached {target}")
    try:
        socket.create_connection(("127.0.0.1", 9), timeout=2)
    except OSError as e:
        assert "_test_env" not in str(e), "loopback must stay reachable (local servers in tests)"
    print("✓ test_outbound_network_is_blocked_and_loopback_is_not: PASS")


def test_runner_rejects_a_test_file_without_the_isolation_import():
    import run_all_tests
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=TESTS_DIR, delete=False) as f:
        f.write('"""docstring"""\nimport os\nimport _test_env\n')
    try:
        name = os.path.basename(f.name)
        assert run_all_tests._missing_test_env([name, "test_test_env.py"]) == [name]
    finally:
        os.unlink(f.name)
    assert run_all_tests._missing_test_env(run_all_tests.UNIT_TESTS) == []
    print("✓ test_runner_rejects_a_test_file_without_the_isolation_import: PASS")


if __name__ == "__main__":
    test_app_import_skips_dotenv_and_shell_secrets_and_uses_a_temp_db()
    test_real_local_database_is_refused()
    test_outbound_network_is_blocked_and_loopback_is_not()
    test_runner_rejects_a_test_file_without_the_isolation_import()
    print("\nAll 4 test-environment tests passed.")
