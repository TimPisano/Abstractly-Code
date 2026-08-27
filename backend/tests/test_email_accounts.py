"""
Tests for OAuth email account linking: token_encryption.py's
encrypt/decrypt, email_accounts.py's authorize-URL construction,
callback token exchange, refresh, send, and disconnect logic (all with
a fake HTTP client standing in for Google/Microsoft, since no real
OAuth app registration exists yet), and the /email-accounts* routes'
ownership isolation.

Same conventions as test_messaging.py: _fresh_temp_db() + Flask
test_client(), real database.create_user()-backed sessions.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())

from app.api import app
from app import database
from app.auth import hash_password
from app import email_accounts
from app import token_encryption


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _make_user(email, name="Test User", role="analyst"):
    return database.create_user(email, name, hash_password("password123"), role=role)["id"]


def _client_for(user_id, role="analyst"):
    user = database.get_user(user_id)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = user["email"]
        sess["name"] = user["name"]
        sess["role"] = role
    return client


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or str(json_body)

    def json(self):
        return self._json


class FakeHttp:
    """Records calls and returns pre-scripted responses keyed by URL substring, in call order per URL."""

    def __init__(self):
        self.calls = []
        self._responses = {}

    def script(self, url_substring, response):
        self._responses.setdefault(url_substring, []).append(response)

    def _respond(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for substring, queue in self._responses.items():
            if substring in url and queue:
                return queue.pop(0)
        raise AssertionError(f"No scripted response for {method} {url}")

    def post(self, url, **kwargs):
        return self._respond("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._respond("GET", url, **kwargs)


def _set_google_env():
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"] = "http://localhost:5000/email-accounts/callback/google"


def _clear_google_env():
    for k in ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"]:
        os.environ.pop(k, None)


# ------------------------------------------------------------------
# token_encryption.py
# ------------------------------------------------------------------

def test_encrypt_decrypt_round_trip():
    ciphertext = token_encryption.encrypt_token("super-secret-refresh-token")
    assert ciphertext != "super-secret-refresh-token"
    assert token_encryption.decrypt_token(ciphertext) == "super-secret-refresh-token"
    print("✓ test_encrypt_decrypt_round_trip: PASS")


def test_decrypt_garbage_returns_none_not_raise():
    assert token_encryption.decrypt_token("not-a-real-fernet-token") is None
    print("✓ test_decrypt_garbage_returns_none_not_raise: PASS")


def test_missing_key_raises_clear_error():
    saved = os.environ.pop("TOKEN_ENCRYPTION_KEY", None)
    try:
        try:
            token_encryption.encrypt_token("x")
            assert False, "should have raised"
        except token_encryption.TokenEncryptionNotConfigured as e:
            assert "TOKEN_ENCRYPTION_KEY" in str(e)
    finally:
        if saved:
            os.environ["TOKEN_ENCRYPTION_KEY"] = saved
    print("✓ test_missing_key_raises_clear_error: PASS")


# ------------------------------------------------------------------
# email_accounts.py -- authorize URL + callback exchange
# ------------------------------------------------------------------

def test_build_authorize_url_requires_provider_config():
    db_path = _fresh_temp_db()
    _clear_google_env()
    try:
        a = _make_user("a@example.com")
        try:
            email_accounts.build_authorize_url("google", a)
            assert False, "should have raised ProviderNotConfigured"
        except email_accounts.ProviderNotConfigured:
            pass
    finally:
        os.unlink(db_path)
    print("✓ test_build_authorize_url_requires_provider_config: PASS")


def test_build_authorize_url_contains_expected_params_and_persists_state():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        a = _make_user("a@example.com")
        url = email_accounts.build_authorize_url("google", a)
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=test-client-id" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "state=" in url
        state = url.split("state=")[1].split("&")[0]
        row = database.consume_oauth_state(state)
        assert row is not None and row["user_id"] == a and row["provider"] == "google"
        assert database.consume_oauth_state(state) is None, "state must be single-use"
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_build_authorize_url_contains_expected_params_and_persists_state: PASS")


def test_handle_oauth_callback_invalid_state_rejected():
    db_path = _fresh_temp_db()
    try:
        try:
            email_accounts.handle_oauth_callback("google", "some-code", "bogus-state", http=FakeHttp())
            assert False, "should have raised"
        except email_accounts.EmailAccountError as e:
            assert "connecting again" in str(e).lower()
    finally:
        os.unlink(db_path)
    print("✓ test_handle_oauth_callback_invalid_state_rejected: PASS")


def test_handle_oauth_callback_success_stores_encrypted_tokens():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        a = _make_user("a@example.com")
        state = "test-state-123"
        database.create_oauth_state(state, a, "google")

        http = FakeHttp()
        http.script("oauth2.googleapis.com/token", FakeResponse(200, {
            "access_token": "raw-access-token",
            "refresh_token": "raw-refresh-token",
            "expires_in": 3600,
        }))
        http.script("googleapis.com/oauth2/v2/userinfo", FakeResponse(200, {"email": "alice@gmail.com"}))

        result = email_accounts.handle_oauth_callback("google", "auth-code", state, http=http)
        assert result["provider_email"] == "alice@gmail.com"
        assert "access_token" not in result and "refresh_token" not in result, "raw tokens must never be returned"
        assert "access_token_encrypted" not in result

        stored = database.list_linked_email_accounts_for_user(a)
        assert len(stored) == 1
        assert stored[0]["access_token_encrypted"] != "raw-access-token"
        assert token_encryption.decrypt_token(stored[0]["access_token_encrypted"]) == "raw-access-token"
        assert token_encryption.decrypt_token(stored[0]["refresh_token_encrypted"]) == "raw-refresh-token"

        # re-linking the same provider replaces, doesn't duplicate
        state2 = "test-state-456"
        database.create_oauth_state(state2, a, "google")
        http.script("oauth2.googleapis.com/token", FakeResponse(200, {
            "access_token": "second-access-token", "refresh_token": "second-refresh-token", "expires_in": 3600,
        }))
        http.script("googleapis.com/oauth2/v2/userinfo", FakeResponse(200, {"email": "alice@gmail.com"}))
        email_accounts.handle_oauth_callback("google", "auth-code-2", state2, http=http)
        assert len(database.list_linked_email_accounts_for_user(a)) == 1, "relinking replaces, not duplicates"
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_handle_oauth_callback_success_stores_encrypted_tokens: PASS")


def test_handle_oauth_callback_missing_refresh_token_errors_clearly():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        a = _make_user("a@example.com")
        state = "test-state-no-refresh"
        database.create_oauth_state(state, a, "google")
        http = FakeHttp()
        http.script("oauth2.googleapis.com/token", FakeResponse(200, {"access_token": "tok", "expires_in": 3600}))
        try:
            email_accounts.handle_oauth_callback("google", "code", state, http=http)
            assert False, "should have raised"
        except email_accounts.EmailAccountError as e:
            assert "refresh token" in str(e).lower()
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_handle_oauth_callback_missing_refresh_token_errors_clearly: PASS")


def test_handle_oauth_callback_provider_rejection_surfaces_error():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        a = _make_user("a@example.com")
        state = "test-state-reject"
        database.create_oauth_state(state, a, "google")
        http = FakeHttp()
        http.script("oauth2.googleapis.com/token", FakeResponse(400, {"error": "invalid_grant"}, text="invalid_grant"))
        try:
            email_accounts.handle_oauth_callback("google", "bad-code", state, http=http)
            assert False, "should have raised"
        except email_accounts.EmailAccountError as e:
            assert "invalid_grant" in str(e)
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_handle_oauth_callback_provider_rejection_surfaces_error: PASS")


# ------------------------------------------------------------------
# refresh + send
# ------------------------------------------------------------------

def test_refresh_skipped_when_token_not_near_expiry():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        account_id = database.upsert_linked_email_account(
            a, "google", "alice@gmail.com",
            token_encryption.encrypt_token("still-valid-access"),
            token_encryption.encrypt_token("refresh-tok"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "gmail.send",
        )
        account = database.get_linked_email_account(account_id)
        http = FakeHttp()  # no scripted responses -- must not be called
        token = email_accounts._refresh_access_token(account, http=http)
        assert token == "still-valid-access"
        assert http.calls == [], "must not refresh a token that isn't near expiry"
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_refresh_skipped_when_token_not_near_expiry: PASS")


def test_refresh_happens_when_token_expired_and_updates_db():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        account_id = database.upsert_linked_email_account(
            a, "google", "alice@gmail.com",
            token_encryption.encrypt_token("expired-access"),
            token_encryption.encrypt_token("refresh-tok"),
            (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "gmail.send",
        )
        account = database.get_linked_email_account(account_id)
        http = FakeHttp()
        http.script("oauth2.googleapis.com/token", FakeResponse(200, {"access_token": "fresh-access", "expires_in": 3600}))
        token = email_accounts._refresh_access_token(account, http=http)
        assert token == "fresh-access"
        updated = database.get_linked_email_account(account_id)
        assert token_encryption.decrypt_token(updated["access_token_encrypted"]) == "fresh-access"
        assert token_encryption.decrypt_token(updated["refresh_token_encrypted"]) == "refresh-tok", "unrotated refresh token stays as-is"
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_refresh_happens_when_token_expired_and_updates_db: PASS")


def test_send_email_as_gmail_uses_valid_token():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        account_id = database.upsert_linked_email_account(
            a, "google", "alice@gmail.com",
            token_encryption.encrypt_token("access-tok"),
            token_encryption.encrypt_token("refresh-tok"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "gmail.send",
        )
        http = FakeHttp()
        http.script("gmail.googleapis.com/gmail/v1/users/me/messages/send", FakeResponse(200, {"id": "msg-1"}))
        email_accounts.send_email_as(account_id, "tenant@example.com", "Lease Summary", "See attached.", http=http)
        send_calls = [c for c in http.calls if "messages/send" in c[1]]
        assert len(send_calls) == 1
        assert send_calls[0][2]["headers"]["Authorization"] == "Bearer access-tok"
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_send_email_as_gmail_uses_valid_token: PASS")


def test_send_email_provider_failure_raises_clean_error():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        account_id = database.upsert_linked_email_account(
            a, "google", "alice@gmail.com",
            token_encryption.encrypt_token("access-tok"),
            token_encryption.encrypt_token("refresh-tok"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "gmail.send",
        )
        http = FakeHttp()
        http.script("gmail.googleapis.com/gmail/v1/users/me/messages/send", FakeResponse(403, {"error": "insufficient scope"}, text="insufficient scope"))
        try:
            email_accounts.send_email_as(account_id, "tenant@example.com", "Subj", "Body", http=http)
            assert False, "should have raised"
        except email_accounts.EmailAccountError as e:
            assert "insufficient scope" in str(e)
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_send_email_provider_failure_raises_clean_error: PASS")


def test_disconnect_deletes_row_even_if_revoke_call_throws():
    db_path = _fresh_temp_db()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        account_id = database.upsert_linked_email_account(
            a, "google", "alice@gmail.com",
            token_encryption.encrypt_token("access-tok"),
            token_encryption.encrypt_token("refresh-tok"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "gmail.send",
        )
        account = database.get_linked_email_account(account_id)

        class ExplodingHttp:
            def post(self, *a, **k):
                raise ConnectionError("network down")

        email_accounts.disconnect_account(account, http=ExplodingHttp())
        assert database.get_linked_email_account(account_id) is None
    finally:
        os.unlink(db_path)
    print("✓ test_disconnect_deletes_row_even_if_revoke_call_throws: PASS")


# ------------------------------------------------------------------
# Routes -- ownership isolation
# ------------------------------------------------------------------

def test_routes_require_login():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        assert client.get("/email-accounts").status_code == 401
        assert client.get("/email-accounts/connect/google").status_code == 401
        assert client.delete("/email-accounts/1").status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_routes_require_login: PASS")


def test_connect_route_503_when_not_configured():
    db_path = _fresh_temp_db()
    _clear_google_env()
    try:
        a = _make_user("a@example.com")
        client = _client_for(a)
        resp = client.get("/email-accounts/connect/google")
        assert resp.status_code == 503, resp.status_code
    finally:
        os.unlink(db_path)
    print("✓ test_connect_route_503_when_not_configured: PASS")


def test_connect_route_redirects_when_configured():
    db_path = _fresh_temp_db()
    _set_google_env()
    try:
        a = _make_user("a@example.com")
        client = _client_for(a)
        resp = client.get("/email-accounts/connect/google")
        assert resp.status_code == 302
        assert "accounts.google.com" in resp.headers["Location"]
    finally:
        _clear_google_env()
        os.unlink(db_path)
    print("✓ test_connect_route_redirects_when_configured: PASS")


def test_list_route_only_shows_own_accounts():
    db_path = _fresh_temp_db()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        b = _make_user("b@example.com")
        database.upsert_linked_email_account(
            a, "google", "alice@gmail.com",
            token_encryption.encrypt_token("x"), token_encryption.encrypt_token("y"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "gmail.send",
        )
        database.upsert_linked_email_account(
            b, "google", "bob@gmail.com",
            token_encryption.encrypt_token("x"), token_encryption.encrypt_token("y"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "gmail.send",
        )
        client_a = _client_for(a)
        resp = client_a.get("/email-accounts")
        data = resp.get_json()
        assert len(data) == 1 and data[0]["provider_email"] == "alice@gmail.com"
        assert "access_token_encrypted" not in data[0], "raw encrypted token must never be exposed over the API"
    finally:
        os.unlink(db_path)
    print("✓ test_list_route_only_shows_own_accounts: PASS")


def test_delete_route_isolation_a_cannot_disconnect_bs_account():
    db_path = _fresh_temp_db()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        b = _make_user("b@example.com")
        bs_account_id = database.upsert_linked_email_account(
            b, "google", "bob@gmail.com",
            token_encryption.encrypt_token("x"), token_encryption.encrypt_token("y"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "gmail.send",
        )
        client_a = _client_for(a)
        resp = client_a.delete(f"/email-accounts/{bs_account_id}")
        assert resp.status_code == 404, "must not be able to disconnect someone else's linked account"
        assert database.get_linked_email_account(bs_account_id) is not None, "b's account must be untouched"

        client_b = _client_for(b)
        resp = client_b.delete(f"/email-accounts/{bs_account_id}")
        assert resp.status_code == 200
        assert database.get_linked_email_account(bs_account_id) is None
    finally:
        os.unlink(db_path)
    print("✓ test_delete_route_isolation_a_cannot_disconnect_bs_account: PASS")


def test_send_route_validation_and_isolation():
    db_path = _fresh_temp_db()
    try:
        from datetime import datetime, timedelta, timezone
        a = _make_user("a@example.com")
        b = _make_user("b@example.com")
        bs_account_id = database.upsert_linked_email_account(
            b, "google", "bob@gmail.com",
            token_encryption.encrypt_token("x"), token_encryption.encrypt_token("y"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "gmail.send",
        )
        client_a = _client_for(a)
        resp = client_a.post(f"/email-accounts/{bs_account_id}/send", json={"to": "x@example.com", "subject": "s", "body": "b"})
        assert resp.status_code == 404, "must not be able to send-as through someone else's linked account"

        as_account_id = database.upsert_linked_email_account(
            a, "google", "alice@gmail.com",
            token_encryption.encrypt_token("x"), token_encryption.encrypt_token("y"),
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "gmail.send",
        )
        resp = client_a.post(f"/email-accounts/{as_account_id}/send", json={"to": "", "subject": "s", "body": "b"})
        assert resp.status_code == 400, "missing recipient must be rejected"
    finally:
        os.unlink(db_path)
    print("✓ test_send_route_validation_and_isolation: PASS")


if __name__ == "__main__":
    test_encrypt_decrypt_round_trip()
    test_decrypt_garbage_returns_none_not_raise()
    test_missing_key_raises_clear_error()
    test_build_authorize_url_requires_provider_config()
    test_build_authorize_url_contains_expected_params_and_persists_state()
    test_handle_oauth_callback_invalid_state_rejected()
    test_handle_oauth_callback_success_stores_encrypted_tokens()
    test_handle_oauth_callback_missing_refresh_token_errors_clearly()
    test_handle_oauth_callback_provider_rejection_surfaces_error()
    test_refresh_skipped_when_token_not_near_expiry()
    test_refresh_happens_when_token_expired_and_updates_db()
    test_send_email_as_gmail_uses_valid_token()
    test_send_email_provider_failure_raises_clean_error()
    test_disconnect_deletes_row_even_if_revoke_call_throws()
    test_routes_require_login()
    test_connect_route_503_when_not_configured()
    test_connect_route_redirects_when_configured()
    test_list_route_only_shows_own_accounts()
    test_delete_route_isolation_a_cannot_disconnect_bs_account()
    test_send_route_validation_and_isolation()
    print("\nAll email account tests passed.")
