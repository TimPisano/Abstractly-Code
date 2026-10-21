"""
Test helper (not a test file -- leading underscore, not registered in
run_all_tests.py). Every offline test file imports this FIRST, before
anything from `app`, so the suite behaves the same in every checkout:

- No backend/.env. The real one sets ADMIN_EMAIL (seeded as an extra
  user into every fresh test database), a real Gmail login (tests sent
  real emails), and LEASE_AI_EXTRACTION. ABSTRACTLY_TESTS=1 makes
  app/api.py skip load_dotenv(), and every environment variable that
  isn't a generic system one (PATH, HOME, locale, ...) is removed, so
  neither .env nor the shell (ANTHROPIC_API_KEY, feature flags) leaks
  in. Tests that need a flag set it themselves (mock.patch.dict).
- A throwaway database. Importing app.api runs init_db() at import time,
  which used to open backend/lease_portfolio.db -- the developer's real
  local database. DB_PATH now points at a fresh temp file (deleted at
  exit), and database.configure() refuses the real default path.
- No real network. Connections and DNS lookups to anything but this
  machine raise OSError, so an unmocked Anthropic, SMTP or Google call
  fails the way it would offline instead of reaching a real service.
  Each blocked attempt is reported on stderr at exit.
"""
import atexit
import ipaddress
import os
import socket
import sys
import tempfile

_KEEP = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR", "TEMP", "TMP", "PWD", "TZ",
    "LANG", "LANGUAGE", "SYSTEMROOT", "VIRTUAL_ENV", "TESSDATA_PREFIX", "LOG_LEVEL",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
}
_KEEP_PREFIXES = ("LC_", "PYTHON", "__CF", "OMP_", "OPENBLAS_")

for _key in list(os.environ):
    if _key not in _KEEP and not _key.startswith(_KEEP_PREFIXES):
        del os.environ[_key]

os.environ["ABSTRACTLY_TESTS"] = "1"
os.environ["LEASE_EXTRACTION_ENGINE"] = "regex"
# Belt and braces: even a test that sets a fake key and forgets to mock
# the client can only reach a closed local port.
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:9"

_fd, TEST_DB_PATH = tempfile.mkstemp(prefix="abstractly-test-", suffix=".db")
os.close(_fd)
os.environ["DB_PATH"] = TEST_DB_PATH


@atexit.register
def _remove_test_db():
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.unlink(TEST_DB_PATH + suffix)
        except OSError:
            pass


# ---- the real database is off limits
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import database  # noqa: E402  (app.database never loads .env)

_REAL_DB_PATH = os.path.realpath(database.DEFAULT_DB_PATH)
_configure = database.configure


def _guarded_configure(db_path):
    if os.path.realpath(db_path) == _REAL_DB_PATH:
        raise RuntimeError(f"tests may not use the real local database ({database.DEFAULT_DB_PATH})")
    _configure(db_path)


database.configure = _guarded_configure
database.configure(TEST_DB_PATH)


# ---- no real network
_blocked = []


def _is_local(host):
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _refuse(host):
    _blocked.append(str(host))
    raise OSError(f"tests may not reach {host} (network blocked by tests/_test_env.py)")


_getaddrinfo = socket.getaddrinfo
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def _guarded_getaddrinfo(host, *args, **kwargs):
    host_str = host.decode() if isinstance(host, bytes) else host
    if not _is_local(host_str):
        _refuse(host_str)
    return _getaddrinfo(host, *args, **kwargs)


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        _refuse(address[0])
    return _connect(self, address)


def _guarded_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        _refuse(address[0])
    return _connect_ex(self, address)


socket.getaddrinfo = _guarded_getaddrinfo
socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex


@atexit.register
def _report_blocked():
    if _blocked:
        sys.stderr.write(f"_test_env: blocked {len(_blocked)} outbound connection attempt(s): {sorted(set(_blocked))}\n")
