"""
Tests for the AI assistant: app/assistant.py's grounding context
builder, navigation validation, rate limiting, and the
POST /assistant/ask + GET /assistant/conversations routes.

Real Claude API calls are NOT made here (that would make this suite
slow, costly, and non-deterministic to run) -- the anthropic client is
mocked with real anthropic.types objects (not bare dicts/MagicMocks)
so the mock's shape is verified against the actual SDK types, not just
assumed. A small number of REAL live API calls exist separately in
test_live_assistant_api.py, run only with --live against the running
server, specifically to prove the real integration works end to end.

Uses Flask's in-process test_client() against an isolated temp SQLite
file, same pattern as test_discrepancies.py.
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app.api import app
from app import database
from app.auth import hash_password
from app import assistant
from app.portfolio import FIELD_NAMES


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    assistant._reset_rate_limit_state_for_tests()
    return tmp.name


def _fields(**overrides):
    result = {}
    for name in FIELD_NAMES:
        if name in overrides:
            value = overrides[name]
            result[name] = {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


def _client_as(role, email="test@example.com", name="Test User", user_id=1):
    """
    Fake session, no real `users` row behind it -- fine for routes
    that only ever READ the session (role checks, validation that
    fails before any DB write). assistant_conversations.user_id has a
    real FOREIGN KEY constraint (deliberately -- a conversation should
    never be orphaned, unlike e.g. discrepancies.lease_id), so any
    test that actually reaches insert_assistant_conversation() must
    use _client_for_new_user() below instead, not this.
    """
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = name
        sess["role"] = role
    return client


def _client_for_new_user(role, email, name="Test User"):
    """A real `users` row (so FK-constrained writes like assistant_conversations succeed) plus a matching session."""
    user_id = database.create_user(email, name, hash_password("password123"), role=role)["id"]
    return _client_as(role, email=email, name=name, user_id=user_id), user_id


def _mock_anthropic_client(tool_input):
    """A fake anthropic.Anthropic whose messages.create() returns a real ToolUseBlock with the given input -- not a bare dict, so this exercises the exact same .content / .type / .input access ask_assistant() does against the real SDK."""
    fake_response = mock.Mock()
    fake_response.content = [ToolUseBlock(id="toolu_test", input=tool_input, name="respond_to_user", type="tool_use")]
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = fake_response
    return fake_client


# ------------------------------------------------------------------
# build_portfolio_context
# ------------------------------------------------------------------

def test_build_portfolio_context_includes_real_lease_data():
    db_path = _fresh_temp_db()
    try:
        database.insert_lease("lease.pdf", _fields(tenant="Acme Corp", rent_amount="$5,000.00", square_footage="2,000 sq ft"))
        leases = database.get_all_effective_leases()
        context = assistant.build_portfolio_context(leases, [], [])
        assert "Acme Corp" in context
        assert "$5,000.00" in context
        assert "2,000 sq ft" in context
        assert "1 lease(s) total" in context
    finally:
        os.unlink(db_path)
    print("✓ test_build_portfolio_context_includes_real_lease_data: PASS")


def test_build_portfolio_context_caps_large_portfolios_and_says_so():
    db_path = _fresh_temp_db()
    try:
        original_cap = assistant.MAX_LEASES_IN_CONTEXT
        assistant.MAX_LEASES_IN_CONTEXT = 3
        try:
            for i in range(5):
                database.insert_lease(f"lease{i}.pdf", _fields(tenant=f"Tenant {i}"))
            leases = database.get_all_effective_leases()
            context = assistant.build_portfolio_context(leases, [], [])
            assert "Tenant 0" in context and "Tenant 1" in context and "Tenant 2" in context
            assert "Tenant 4" not in context, "must not exceed the cap"
            assert "only the first 3 of 5 leases" in context, "must say it truncated, not silently drop leases"
        finally:
            assistant.MAX_LEASES_IN_CONTEXT = original_cap
    finally:
        os.unlink(db_path)
    print("✓ test_build_portfolio_context_caps_large_portfolios_and_says_so: PASS")


def test_build_portfolio_context_summarizes_discrepancies_and_alerts_by_severity():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("lease.pdf", _fields(tenant="Acme"))
        database.upsert_discrepancy(discrepancy_type="lease_risk_flag", natural_key="k1", category="missing_clause", message="m", details={}, lease_id=lease_id, severity="high")
        database.upsert_discrepancy(discrepancy_type="lease_risk_flag", natural_key="k2", category="missing_clause", message="m2", details={}, lease_id=lease_id, severity="medium")
        database.upsert_alert(alert_type="lease_expiration", natural_key="a1", severity="high", title="Expiring soon", message="m", details={})

        leases = database.get_all_effective_leases()
        context = assistant.build_portfolio_context(leases, database.list_discrepancies(), database.list_alerts())
        assert "OPEN DISCREPANCIES: 2 total" in context
        assert "1 high" in context and "1 medium" in context
        assert "ACTIVE ALERTS: 1 total" in context
        assert "Expiring soon" in context
    finally:
        os.unlink(db_path)
    print("✓ test_build_portfolio_context_summarizes_discrepancies_and_alerts_by_severity: PASS")


# ------------------------------------------------------------------
# Navigation validation
# ------------------------------------------------------------------

def test_validate_navigation_rejects_invalid_route():
    result = assistant._validate_navigation(
        {"response_type": "navigational", "answer": "Taking you there.", "route": "not_a_real_route"}, {1, 2, 3},
    )
    assert result["response_type"] == "informational", "an invalid route must be downgraded, never passed through"
    print("✓ test_validate_navigation_rejects_invalid_route: PASS")


def test_validate_navigation_rejects_lease_id_not_in_portfolio():
    result = assistant._validate_navigation(
        {"response_type": "navigational", "answer": "Taking you there.", "route": "detail", "lease_id": 999999}, {1, 2, 3},
    )
    assert result["response_type"] == "informational", "a hallucinated lease_id must never reach the frontend as valid navigation"
    print("✓ test_validate_navigation_rejects_lease_id_not_in_portfolio: PASS")


def test_validate_navigation_accepts_real_lease_id():
    original = {"response_type": "navigational", "answer": "Taking you there.", "route": "detail", "lease_id": 2}
    result = assistant._validate_navigation(original, {1, 2, 3})
    assert result == original
    print("✓ test_validate_navigation_accepts_real_lease_id: PASS")


def test_validate_navigation_leaves_informational_and_clarifying_untouched():
    info = {"response_type": "informational", "answer": "The average rent is $5,000."}
    assert assistant._validate_navigation(info, set()) == info
    clarifying = {"response_type": "clarifying", "answer": "Which lease do you mean?"}
    assert assistant._validate_navigation(clarifying, set()) == clarifying
    print("✓ test_validate_navigation_leaves_informational_and_clarifying_untouched: PASS")


# ------------------------------------------------------------------
# ask_assistant (mocked Claude call)
# ------------------------------------------------------------------

def test_ask_assistant_returns_informational_grounded_in_real_data():
    db_path = _fresh_temp_db()
    try:
        database.insert_lease("lease.pdf", _fields(tenant="Acme Corp", rent_amount="$5,000.00"))
        fake_client = _mock_anthropic_client({"response_type": "informational", "answer": "Acme Corp pays $5,000/month."})
        result = assistant.ask_assistant("what's the rent on the Acme lease?", client=fake_client)
        assert result["response_type"] == "informational"
        assert "5,000" in result["answer"]

        # the real portfolio data was actually sent to the model, not a stub
        call_kwargs = fake_client.messages.create.call_args.kwargs
        assert "Acme Corp" in call_kwargs["system"]
        assert "$5,000.00" in call_kwargs["system"]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "respond_to_user"}
    finally:
        os.unlink(db_path)
    print("✓ test_ask_assistant_returns_informational_grounded_in_real_data: PASS")


def test_ask_assistant_api_failure_raises_assistant_error():
    db_path = _fresh_temp_db()
    try:
        import anthropic
        fake_client = mock.Mock()
        fake_client.messages.create.side_effect = anthropic.APIConnectionError(request=mock.Mock())
        try:
            assistant.ask_assistant("anything", client=fake_client)
            assert False, "must raise AssistantError, not let the raw SDK exception propagate"
        except assistant.AssistantError:
            pass
    finally:
        os.unlink(db_path)
    print("✓ test_ask_assistant_api_failure_raises_assistant_error: PASS")


# ------------------------------------------------------------------
# Rate limiting
# ------------------------------------------------------------------

def test_rate_limiting_blocks_after_the_limit():
    assistant._reset_rate_limit_state_for_tests()
    try:
        for i in range(assistant.RATE_LIMIT_MAX):
            assert assistant.is_rate_limited(user_id=42) is False, f"call {i} should not be limited yet"
        assert assistant.is_rate_limited(user_id=42) is True, "the call past the limit must be blocked"
    finally:
        assistant._reset_rate_limit_state_for_tests()
    print("✓ test_rate_limiting_blocks_after_the_limit: PASS")


def test_rate_limiting_is_per_user():
    assistant._reset_rate_limit_state_for_tests()
    try:
        for i in range(assistant.RATE_LIMIT_MAX):
            assistant.is_rate_limited(user_id=1)
        assert assistant.is_rate_limited(user_id=1) is True
        assert assistant.is_rate_limited(user_id=2) is False, "a different user must have their own independent limit"
    finally:
        assistant._reset_rate_limit_state_for_tests()
    print("✓ test_rate_limiting_is_per_user: PASS")


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

def test_assistant_ask_route_requires_login():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.post("/assistant/ask", json={"question": "hi"})
        assert resp.status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_requires_login: PASS")


def test_assistant_ask_route_validates_question():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("viewer")
        resp = client.post("/assistant/ask", json={})
        assert resp.status_code == 400

        resp = client.post("/assistant/ask", json={"question": "x" * 2001})
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_validates_question: PASS")


def test_assistant_ask_route_persists_conversation():
    db_path = _fresh_temp_db()
    try:
        client, user_id = _client_for_new_user("analyst", "persist@example.com")
        with mock.patch.object(assistant, "ask_assistant", return_value={"response_type": "informational", "answer": "The answer is 42."}):
            resp = client.post("/assistant/ask", json={"question": "what is the answer?"})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["answer"] == "The answer is 42."

        history = database.get_assistant_conversations(user_id)
        assert len(history) == 1
        assert history[0]["question"] == "what is the answer?"
        assert history[0]["answer"] == "The answer is 42."
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_persists_conversation: PASS")


def test_assistant_ask_route_persists_navigational_route_params():
    db_path = _fresh_temp_db()
    try:
        client, user_id = _client_for_new_user("analyst", "nav@example.com")
        fake_result = {"response_type": "navigational", "answer": "Taking you there.", "route": "detail", "lease_id": 7}
        with mock.patch.object(assistant, "ask_assistant", return_value=fake_result):
            resp = client.post("/assistant/ask", json={"question": "take me to lease 7"})
        assert resp.status_code == 200
        assert resp.get_json()["route"] == "detail"
        assert resp.get_json()["lease_id"] == 7

        history = database.get_assistant_conversations(user_id)
        assert history[0]["route"] == "detail"
        assert history[0]["route_params"] == {"lease_id": 7}
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_persists_navigational_route_params: PASS")


def test_assistant_ask_route_502s_cleanly_on_api_failure():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("analyst")
        with mock.patch.object(assistant, "ask_assistant", side_effect=assistant.AssistantError("boom")):
            resp = client.post("/assistant/ask", json={"question": "anything"})
        assert resp.status_code == 502
        assert "Traceback" not in str(resp.get_json())
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_502s_cleanly_on_api_failure: PASS")


def test_assistant_ask_route_rate_limited_after_too_many_calls():
    db_path = _fresh_temp_db()
    try:
        client, _user_id = _client_for_new_user("analyst", "ratelimit@example.com")
        with mock.patch.object(assistant, "ask_assistant", return_value={"response_type": "informational", "answer": "ok"}):
            for i in range(assistant.RATE_LIMIT_MAX):
                resp = client.post("/assistant/ask", json={"question": f"question {i}"})
                assert resp.status_code == 200, f"call {i} should succeed"
            resp = client.post("/assistant/ask", json={"question": "one too many"})
            assert resp.status_code == 429
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_rate_limited_after_too_many_calls: PASS")


def test_conversations_route_requires_login():
    db_path = _fresh_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/assistant/conversations")
        assert resp.status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_conversations_route_requires_login: PASS")


def test_conversations_route_is_strictly_isolated_per_account():
    """The explicit requirement: no cross-account leakage, at all."""
    db_path = _fresh_temp_db()
    try:
        client_a, _ = _client_for_new_user("analyst", "a@example.com")
        client_b, _ = _client_for_new_user("analyst", "b@example.com")

        with mock.patch.object(assistant, "ask_assistant", return_value={"response_type": "informational", "answer": "answer for A"}):
            client_a.post("/assistant/ask", json={"question": "question from A"})
        with mock.patch.object(assistant, "ask_assistant", return_value={"response_type": "informational", "answer": "answer for B"}):
            client_b.post("/assistant/ask", json={"question": "question from B"})

        resp_a = client_a.get("/assistant/conversations")
        assert resp_a.status_code == 200
        questions_a = [c["question"] for c in resp_a.get_json()]
        assert questions_a == ["question from A"], f"user A must see only their own conversation, got {questions_a}"

        resp_b = client_b.get("/assistant/conversations")
        questions_b = [c["question"] for c in resp_b.get_json()]
        assert questions_b == ["question from B"], f"user B must see only their own conversation, got {questions_b}"
    finally:
        os.unlink(db_path)
    print("✓ test_conversations_route_is_strictly_isolated_per_account: PASS")


if __name__ == "__main__":
    test_build_portfolio_context_includes_real_lease_data()
    test_build_portfolio_context_caps_large_portfolios_and_says_so()
    test_build_portfolio_context_summarizes_discrepancies_and_alerts_by_severity()
    test_validate_navigation_rejects_invalid_route()
    test_validate_navigation_rejects_lease_id_not_in_portfolio()
    test_validate_navigation_accepts_real_lease_id()
    test_validate_navigation_leaves_informational_and_clarifying_untouched()
    test_ask_assistant_returns_informational_grounded_in_real_data()
    test_ask_assistant_api_failure_raises_assistant_error()
    test_rate_limiting_blocks_after_the_limit()
    test_rate_limiting_is_per_user()
    test_assistant_ask_route_requires_login()
    test_assistant_ask_route_validates_question()
    test_assistant_ask_route_persists_conversation()
    test_assistant_ask_route_persists_navigational_route_params()
    test_assistant_ask_route_502s_cleanly_on_api_failure()
    test_assistant_ask_route_rate_limited_after_too_many_calls()
    test_conversations_route_requires_login()
    test_conversations_route_is_strictly_isolated_per_account()
    print("\nAll assistant tests passed.")
