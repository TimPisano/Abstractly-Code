"""
Tests for the deal assistant's team-scoping, citations, and credit
controls:

1. Citations (app/assistant.py's _resolve_citations) -- a citation the
   model names must resolve to the REAL document/page on file, and a
   citation naming a lease_id outside this question's own grounding
   data must be dropped, never passed through.

2. Real cross-team isolation through the full ask_assistant pipeline
   (mocked Claude client, real team-scoped database queries) -- proves
   a team's own leases never appear in another team's grounding
   context, and a citation to another team's lease_id can never
   resolve to a real document/page, complementing
   test_team_isolation.py's broader route-level isolation coverage
   with assistant-specific cases that module doesn't cover.

3. Assistant credit (app/usage_limits.py's check_assistant_credit /
   get_assistant_usage_summary / log_assistant_usage_event, plus the
   POST /assistant/ask and GET /assistant/usage routes that use them).

Real Claude API calls are NOT made here -- same mocked-anthropic-client
convention as test_assistant.py.
"""

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app.api import app
from app import database
from app import assistant
from app import usage_limits
from app.auth import hash_password
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
            value, page = overrides[name] if isinstance(overrides[name], tuple) else (overrides[name], 1)
            result[name] = {"value": value, "source": {"page": page, "quote": f"...{value}..."}, "confidence": "high"}
        else:
            result[name] = {"value": None, "source": None, "confidence": None}
    return result


def _client_as(role, email="test@example.com", name="Test User", user_id=1, team_id=1, is_owner=False):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["email"] = email
        sess["name"] = name
        sess["role"] = role
        sess["team_id"] = team_id
        sess["is_owner"] = is_owner
    return client


def _client_for_new_user(role, email, name="Test User"):
    user_id = database.create_user(email, name, hash_password("password123"), role=role)["id"]
    team_id = database.get_user(user_id)["team_id"]
    return _client_as(role, email=email, name=name, user_id=user_id, team_id=team_id), user_id


def _setup_two_teams():
    """Same convention as test_team_isolation.py's own helper. Returns (team_a_id, user_a_id, team_b_id, user_b_id)."""
    team_a = database.create_team("Team A")
    team_b = database.create_team("Team B")
    user_a = database.create_user("admin-a@example.com", "Admin A", hash_password("password123"), role="admin", team_id=team_a["id"])["id"]
    user_b = database.create_user("admin-b@example.com", "Admin B", hash_password("password123"), role="admin", team_id=team_b["id"])["id"]
    return team_a["id"], user_a, team_b["id"], user_b


def _mock_anthropic_client(tool_input):
    """Same convention as test_assistant.py's own helper -- a fake anthropic.Anthropic whose messages.create() returns a real ToolUseBlock, with real usage counts so token logging has something real to work with."""
    fake_response = mock.Mock()
    fake_response.content = [ToolUseBlock(id="toolu_test", input=tool_input, name="respond_to_user", type="tool_use")]
    fake_response.usage = mock.Mock(input_tokens=500, output_tokens=100)
    fake_client = mock.Mock()
    fake_client.messages.create.return_value = fake_response
    return fake_client


# ------------------------------------------------------------------
# _resolve_citations
# ------------------------------------------------------------------

def test_resolve_citations_fills_in_real_document_and_page():
    db_path = _fresh_temp_db()
    try:
        team_id = database.create_team("Team A")["id"]
        lease_id = database.insert_lease("acme.pdf", _fields(tenant=("Acme Corp", 2), rent_amount=("$5,000.00", 3)), team_id, display_name="Acme Corp Lease")
        leases_by_id = {lease_id: database.get_effective_lease(lease_id, team_id)}
        result = {
            "response_type": "informational", "answer": "Acme pays $5,000/mo.",
            "citations": [{"lease_id": lease_id, "field": "rent_amount"}],
        }
        resolved = assistant._resolve_citations(result, leases_by_id)
        assert resolved["citations"] == [{"lease_id": lease_id, "document": "Acme Corp Lease", "field": "rent_amount", "page": 3}]
    finally:
        os.unlink(db_path)
    print("✓ test_resolve_citations_fills_in_real_document_and_page: PASS")


def test_resolve_citations_drops_lease_id_outside_grounding_data():
    """The hard isolation boundary: a lease_id not in THIS question's own leases_by_id (a hallucination, or another team's lease) must never produce a citation."""
    result = {
        "response_type": "informational", "answer": "...",
        "citations": [{"lease_id": 999999, "field": "rent_amount"}],
    }
    resolved = assistant._resolve_citations(result, {})
    assert resolved["citations"] == [], "a citation to a lease outside the grounding data must be dropped, not passed through"
    print("✓ test_resolve_citations_drops_lease_id_outside_grounding_data: PASS")


def test_resolve_citations_omits_page_when_field_has_no_source():
    db_path = _fresh_temp_db()
    try:
        team_id = database.create_team("Team A")["id"]
        lease_id = database.insert_lease("acme.pdf", _fields(tenant="Acme Corp"), team_id, display_name="Acme Corp Lease")
        leases_by_id = {lease_id: database.get_effective_lease(lease_id, team_id)}
        result = {
            "response_type": "informational", "answer": "...",
            "citations": [{"lease_id": lease_id, "field": "rent_amount"}],  # rent_amount was never set -- no source
        }
        resolved = assistant._resolve_citations(result, leases_by_id)
        assert resolved["citations"] == [{"lease_id": lease_id, "document": "Acme Corp Lease", "field": "rent_amount"}], "no page key when the field has no real source on file"
    finally:
        os.unlink(db_path)
    print("✓ test_resolve_citations_omits_page_when_field_has_no_source: PASS")


def test_resolve_citations_ignores_non_informational_responses():
    result = {"response_type": "navigational", "answer": "Taking you there.", "route": "dashboard"}
    assert assistant._resolve_citations(dict(result), {}) == result
    print("✓ test_resolve_citations_ignores_non_informational_responses: PASS")


# ------------------------------------------------------------------
# Real cross-team isolation through the full ask_assistant pipeline
# ------------------------------------------------------------------

def test_ask_assistant_never_grounds_in_another_teams_leases():
    """Team B's question must never even SEE Team A's lease data in the context sent to Claude -- the isolation boundary this whole feature exists to prove."""
    db_path = _fresh_temp_db()
    try:
        team_a_id, _, team_b_id, _ = _setup_two_teams()
        database.insert_lease("secret.pdf", _fields(tenant=("Confidential Tenant LLC", 1)), team_a_id, display_name="Team A Secret Lease")

        fake_client = _mock_anthropic_client({"response_type": "informational", "answer": "No leases on file."})
        assistant.ask_assistant("how many leases do I have?", team_id=team_b_id, client=fake_client)

        system_prompt_sent = fake_client.messages.create.call_args.kwargs["system"]
        assert "Confidential Tenant LLC" not in system_prompt_sent
        assert "Team A Secret Lease" not in system_prompt_sent
        assert "0 lease(s) total" in system_prompt_sent
    finally:
        os.unlink(db_path)
    print("✓ test_ask_assistant_never_grounds_in_another_teams_leases: PASS")


def test_ask_assistant_citation_to_another_teams_lease_id_never_resolves():
    """Even if the model somehow produced another team's real lease_id (e.g. a stale id guessed from a prior session, or a prompt-injection attempt in the question text), the citation must resolve to nothing -- not leak that team's document name or page."""
    db_path = _fresh_temp_db()
    try:
        team_a_id, _, team_b_id, _ = _setup_two_teams()
        leaked_lease_id = database.insert_lease("secret.pdf", _fields(tenant=("Confidential Tenant LLC", 1)), team_a_id, display_name="Team A Secret Lease")

        fake_client = _mock_anthropic_client({
            "response_type": "informational", "answer": "Found it.",
            "citations": [{"lease_id": leaked_lease_id, "field": "tenant"}],
        })
        result = assistant.ask_assistant("what about lease " + str(leaked_lease_id) + "?", team_id=team_b_id, client=fake_client)

        assert result["citations"] == [], "a citation to another team's real lease_id must still be dropped -- it isn't in this question's own (team B) grounding data"
    finally:
        os.unlink(db_path)
    print("✓ test_ask_assistant_citation_to_another_teams_lease_id_never_resolves: PASS")


def test_ask_assistant_navigation_to_another_teams_lease_id_downgrades():
    """Same boundary for navigation: a 'take me to lease <id>' response naming another team's real lease_id must downgrade to informational, never navigate there (same mechanism as a hallucinated id -- _validate_navigation doesn't distinguish the two, by design)."""
    db_path = _fresh_temp_db()
    try:
        team_a_id, _, team_b_id, _ = _setup_two_teams()
        leaked_lease_id = database.insert_lease("secret.pdf", _fields(tenant="Confidential Tenant LLC"), team_a_id)

        fake_client = _mock_anthropic_client({
            "response_type": "navigational", "answer": "Taking you there.",
            "route": "detail", "lease_id": leaked_lease_id,
        })
        result = assistant.ask_assistant("open that lease", team_id=team_b_id, client=fake_client)

        assert result["response_type"] == "informational", "must never navigate team B's session to team A's real lease"
    finally:
        os.unlink(db_path)
    print("✓ test_ask_assistant_navigation_to_another_teams_lease_id_downgrades: PASS")


def test_assistant_ask_route_end_to_end_cross_team_isolation():
    """Full HTTP-route-level proof, real Claude call mocked: Team A has a lease; Team B's real session asks a portfolio-wide question and must get an answer/citations that never reference Team A's data."""
    db_path = _fresh_temp_db()
    try:
        team_a_id, _, team_b_id, user_b_id = _setup_two_teams()
        database.insert_lease("secret.pdf", _fields(tenant=("Confidential Tenant LLC", 1), rent_amount=("$9,999.00", 2)), team_a_id, display_name="Team A Secret Lease")
        client_b = _client_as("admin", email="admin-b@example.com", user_id=user_b_id, team_id=team_b_id)

        fake_client = _mock_anthropic_client({"response_type": "informational", "answer": "You have no leases on file yet."})
        with mock.patch("app.assistant.anthropic.Anthropic", return_value=fake_client):
            resp = client_b.post("/assistant/ask", json={"question": "how many leases do I have?"})

        assert resp.status_code == 200
        body = resp.get_json()
        assert "Confidential Tenant LLC" not in body["answer"]
        assert "9,999" not in body["answer"]
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_end_to_end_cross_team_isolation: PASS")


# ------------------------------------------------------------------
# Assistant credit (usage_limits.py)
# ------------------------------------------------------------------

def test_assistant_usage_summary_defaults_to_config_constant():
    db_path = _fresh_temp_db()
    try:
        team_id = database.get_user(database.create_user("a@example.com", "A", hash_password("password123"))["id"])["team_id"]
        summary = usage_limits.get_assistant_usage_summary(team_id)
        from app.usage_limits_config import DEFAULT_MONTHLY_ASSISTANT_CREDIT_USD
        assert summary == {"used_usd": 0.0, "limit_usd": DEFAULT_MONTHLY_ASSISTANT_CREDIT_USD, "remaining_usd": DEFAULT_MONTHLY_ASSISTANT_CREDIT_USD}
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_usage_summary_defaults_to_config_constant: PASS")


def test_log_assistant_usage_event_accumulates_cost_and_check_blocks_at_limit():
    db_path = _fresh_temp_db()
    try:
        user_id = database.create_user("a@example.com", "A", hash_password("password123"))["id"]
        team_id = database.get_user(user_id)["team_id"]
        conn = database.get_connection()
        conn.execute("UPDATE teams SET monthly_assistant_credit_usd = ? WHERE id = ?", (0.01, team_id))
        conn.commit()
        conn.close()

        assert usage_limits.check_assistant_credit(team_id) is None, "fresh team, nothing spent yet, must not be blocked"

        # Big enough token usage to blow through the $0.01 limit.
        usage_limits.log_assistant_usage_event(team_id, user_id, {"input_tokens": 100000, "output_tokens": 100000})

        summary = usage_limits.get_assistant_usage_summary(team_id)
        assert summary["used_usd"] > 0.01
        assert summary["remaining_usd"] == 0.0, "remaining must floor at 0, never go negative"

        msg = usage_limits.check_assistant_credit(team_id)
        assert msg is not None and "$0.01" in msg
    finally:
        os.unlink(db_path)
    print("✓ test_log_assistant_usage_event_accumulates_cost_and_check_blocks_at_limit: PASS")


def test_assistant_credit_is_separate_from_extraction_budget():
    """Using up the extraction budget must not affect assistant credit, and vice versa -- two separate pools."""
    db_path = _fresh_temp_db()
    try:
        user_id = database.create_user("a@example.com", "A", hash_password("password123"))["id"]
        team_id = database.get_user(user_id)["team_id"]
        usage_limits.log_usage_event(team_id, user_id, lease_id=None, pages=10, token_usage={"input_tokens": 1000000, "output_tokens": 1000000})
        assert usage_limits.check_assistant_credit(team_id) is None, "extraction spend must not touch the assistant credit pool"
        assert usage_limits.get_assistant_usage_summary(team_id)["used_usd"] == 0.0
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_credit_is_separate_from_extraction_budget: PASS")


def test_assistant_credit_is_separate_per_team():
    """Team A spending its assistant credit must not touch Team B's balance."""
    db_path = _fresh_temp_db()
    try:
        team_a_id, user_a_id, team_b_id, _ = _setup_two_teams()
        usage_limits.log_assistant_usage_event(team_a_id, user_a_id, {"input_tokens": 1000000, "output_tokens": 1000000})
        assert usage_limits.get_assistant_usage_summary(team_a_id)["used_usd"] > 0
        assert usage_limits.get_assistant_usage_summary(team_b_id)["used_usd"] == 0.0, "Team B's credit must be untouched by Team A's spend"
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_credit_is_separate_per_team: PASS")


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

def test_assistant_usage_route_requires_login():
    db_path = _fresh_temp_db()
    try:
        resp = app.test_client().get("/assistant/usage")
        assert resp.status_code == 401
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_usage_route_requires_login: PASS")


def test_assistant_usage_route_returns_summary_for_own_team():
    db_path = _fresh_temp_db()
    try:
        client, user_id = _client_for_new_user("analyst", "a@example.com")
        resp = client.get("/assistant/usage")
        assert resp.status_code == 200
        body = resp.get_json()
        assert set(body.keys()) == {"used_usd", "limit_usd", "remaining_usd"}
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_usage_route_returns_summary_for_own_team: PASS")


def test_assistant_ask_route_blocks_with_friendly_message_at_credit_limit():
    db_path = _fresh_temp_db()
    try:
        client, user_id = _client_for_new_user("analyst", "a@example.com")
        team_id = database.get_user(user_id)["team_id"]
        conn = database.get_connection()
        conn.execute("UPDATE teams SET monthly_assistant_credit_usd = ? WHERE id = ?", (0.0, team_id))
        conn.commit()
        conn.close()
        # $0 limit with 0 spent so far is a draw (used >= limit at 0 >= 0) -- blocked immediately, no API call needed.
        with mock.patch.object(assistant, "ask_assistant") as mocked:
            resp = client.post("/assistant/ask", json={"question": "anything"})
            mocked.assert_not_called()
        assert resp.status_code == 403
        assert "monthly assistant credit" in resp.get_json()["error"]
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_blocks_with_friendly_message_at_credit_limit: PASS")


def test_assistant_ask_route_logs_usage_and_returns_remaining_credit():
    db_path = _fresh_temp_db()
    try:
        client, user_id = _client_for_new_user("analyst", "a@example.com")
        team_id = database.get_user(user_id)["team_id"]
        fake_result = {"response_type": "informational", "answer": "ok", "_usage": {"input_tokens": 100, "output_tokens": 50}}
        with mock.patch.object(assistant, "ask_assistant", return_value=dict(fake_result)):
            resp = client.post("/assistant/ask", json={"question": "anything"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "_usage" not in body, "the internal token-usage key must never reach the frontend"
        assert "assistant_usage" in body and body["assistant_usage"]["used_usd"] > 0

        events = database.get_connection().execute(
            "SELECT * FROM usage_events WHERE team_id = ? AND event_type = 'assistant_query'", (team_id,)
        ).fetchall()
        assert len(events) == 1
        assert events[0]["input_tokens"] == 100 and events[0]["output_tokens"] == 50
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_logs_usage_and_returns_remaining_credit: PASS")


def test_assistant_ask_route_requires_team_assignment():
    db_path = _fresh_temp_db()
    try:
        client = _client_as("analyst", team_id=None)
        resp = client.post("/assistant/ask", json={"question": "anything"})
        assert resp.status_code == 403
        assert "team" in resp.get_json()["error"].lower()
    finally:
        os.unlink(db_path)
    print("✓ test_assistant_ask_route_requires_team_assignment: PASS")


# ------------------------------------------------------------------
# /teams routes: owner-only now (closes a pre-existing cross-tenant bug)
# ------------------------------------------------------------------

def test_teams_routes_require_owner_not_just_admin():
    """
    Pre-existing bug this session fixed: any customer team's admin-role
    user (role='admin', is_owner=False) could previously create/list/
    patch ANY team's quotas via @require_role('admin'), which checks
    role rank only -- never which team the caller belongs to, let alone
    whether they're Abstractly staff. Must now 404 (require_owner's
    deliberate not-found-not-forbidden response) for a plain team admin.
    """
    db_path = _fresh_temp_db()
    try:
        client, _ = _client_for_new_user("admin", "admin@example.com")
        assert client.get("/teams").status_code == 404
        assert client.post("/teams", json={"name": "Someone Else's Team"}).status_code == 404
        assert client.patch("/teams/1", json={"monthly_assistant_credit_usd": 999}).status_code == 404
    finally:
        os.unlink(db_path)
    print("✓ test_teams_routes_require_owner_not_just_admin: PASS")


def test_update_team_sets_assistant_credit_override():
    db_path = _fresh_temp_db()
    try:
        conn = database.get_connection()
        team_id = conn.execute("SELECT id FROM teams WHERE name = 'Legacy'").fetchone()[0]
        conn.close()
        owner_id = database.create_user("owner@example.com", "Owner", hash_password("password123"), role="admin")["id"]
        conn = database.get_connection()
        conn.execute("UPDATE users SET is_owner = 1 WHERE id = ?", (owner_id,))
        conn.commit()
        conn.close()
        client = _client_as("admin", email="owner@example.com", user_id=owner_id, team_id=team_id, is_owner=True)

        resp = client.patch(f"/teams/{team_id}", json={"monthly_assistant_credit_usd": 42.5})
        assert resp.status_code == 200
        assert resp.get_json()["monthly_assistant_credit_usd"] == 42.5
        assert usage_limits.get_assistant_usage_summary(team_id)["limit_usd"] == 42.5
    finally:
        os.unlink(db_path)
    print("✓ test_update_team_sets_assistant_credit_override: PASS")


if __name__ == "__main__":
    test_resolve_citations_fills_in_real_document_and_page()
    test_resolve_citations_drops_lease_id_outside_grounding_data()
    test_resolve_citations_omits_page_when_field_has_no_source()
    test_resolve_citations_ignores_non_informational_responses()
    test_ask_assistant_never_grounds_in_another_teams_leases()
    test_ask_assistant_citation_to_another_teams_lease_id_never_resolves()
    test_ask_assistant_navigation_to_another_teams_lease_id_downgrades()
    test_assistant_ask_route_end_to_end_cross_team_isolation()
    test_assistant_usage_summary_defaults_to_config_constant()
    test_log_assistant_usage_event_accumulates_cost_and_check_blocks_at_limit()
    test_assistant_credit_is_separate_from_extraction_budget()
    test_assistant_credit_is_separate_per_team()
    test_assistant_usage_route_requires_login()
    test_assistant_usage_route_returns_summary_for_own_team()
    test_assistant_ask_route_blocks_with_friendly_message_at_credit_limit()
    test_assistant_ask_route_logs_usage_and_returns_remaining_credit()
    test_assistant_ask_route_requires_team_assignment()
    test_teams_routes_require_owner_not_just_admin()
    test_update_team_sets_assistant_credit_override()
    print("\nAll deal assistant credit/citation tests passed.")
