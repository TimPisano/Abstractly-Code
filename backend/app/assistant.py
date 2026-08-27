"""
AI portfolio assistant: a chat-style helper that answers real
questions about a real, uploaded portfolio (grounded in the caller's
actual leases/discrepancies/alerts, never generic filler) and can
recognize when the user wants to be TAKEN somewhere in the app rather
than told something, returning structured navigation data the
frontend can act on directly.

Architecture: one Claude API call per question, forced through a
single tool (`respond_to_user`) so the model's output is always a
strict, parseable structure -- never free text we'd have to guess the
shape of afterward. The three response_type values map directly to
the three things this feature is asked to do:
  - "informational": answers the question using the grounded context.
  - "navigational":  names a real view (and, for a specific lease,
    a real lease id) the frontend should route to.
  - "clarifying":    the question is genuinely ambiguous given the
    real data (e.g. "the 4th floor lease" when several leases could
    match) -- asks back rather than guessing, per the same "flag
    missing/ambiguous rather than fabricate" standard the extraction
    pipeline itself is held to.

Grounding is "stuff a compact portfolio summary into the system
prompt," not a real vector-search retrieval system -- a deliberate,
documented scope choice (see build_portfolio_context's docstring) for
a codebase whose portfolios top out in the low thousands of leases,
where the full compact summary still fits comfortably in one context
window. A real embedding-based retrieval layer would be the natural
next step if portfolios grow past what fits in-context.
"""

import json
import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import anthropic

from . import database
from .normalize import parse_currency
from .portfolio import field_value

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("ASSISTANT_MODEL", "claude-sonnet-5")
MAX_TOKENS = 1024

# Every view the client-facing sidebar actually renders (see
# frontend/app/index.html's data-view attributes) -- the only
# destinations a navigational response is allowed to name. "detail"
# additionally requires a real lease_id (validated against the actual
# portfolio, not trusted from the model output as-is -- see
# _validate_navigation).
VALID_ROUTES = {
    "dashboard", "alerts", "discrepancies", "trends", "upload", "timeline",
    "rentroll", "comparison", "qa", "report", "teamnotes", "team", "detail",
}

# Caps how many leases get a full line in the compact summary -- see
# build_portfolio_context's docstring for why this exists and what
# happens past the cap.
MAX_LEASES_IN_CONTEXT = 500

RESPOND_TOOL = {
    "name": "respond_to_user",
    "description": (
        "Send your reply to the user. Always call this tool -- never respond with plain text. "
        "Choose response_type based on what the user actually wants: 'informational' to answer a "
        "question using the portfolio data provided, 'navigational' if they want to be taken "
        "somewhere in the app, or 'clarifying' if the question is genuinely ambiguous given the "
        "real data available (e.g. it could refer to more than one lease, or you don't have enough "
        "information to answer confidently) -- ask a specific clarifying question rather than guessing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "response_type": {
                "type": "string",
                "enum": ["informational", "navigational", "clarifying"],
            },
            "answer": {
                "type": "string",
                "description": (
                    "The natural-language reply to show the user. For informational, the actual "
                    "answer grounded in the data provided. For navigational, a short confirmation "
                    "of where you're taking them. For clarifying, the specific question to ask back."
                ),
            },
            "route": {
                "type": "string",
                "enum": sorted(VALID_ROUTES),
                "description": "Only set when response_type is 'navigational' -- which view to open.",
            },
            "lease_id": {
                "type": "integer",
                "description": "Only set when route is 'detail' -- the id of the specific lease to open, from the portfolio data provided. Never invent an id.",
            },
        },
        "required": ["response_type", "answer"],
    },
}


def _fmt_money(value) -> str:
    parsed = parse_currency(value) if isinstance(value, str) else value
    return f"${parsed:,.2f}" if parsed is not None else "not found"


def build_portfolio_context(leases: List[Dict[str, Any]], discrepancies: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> str:
    """
    A compact, token-efficient text summary of the real portfolio --
    one line per lease (id, tenant, address, rent, sqft, dates), plus
    discrepancy/alert counts by severity. This is the "retrieval" step
    for this feature: rather than a real embedding search over
    documents, the whole compact portfolio is put in context and the
    model itself finds what's relevant to the question, which is
    simpler, has zero extra infrastructure, and is completely accurate
    (no retrieval-recall failure mode) as long as the compact summary
    fits in one context window.

    Caps at MAX_LEASES_IN_CONTEXT leases (in upload order) and says so
    explicitly in the output -- an honest "the model was only shown
    the first N leases" beats a silent truncation the model has no way
    to know about and might otherwise answer a portfolio-wide question
    as if it saw everything.
    """
    lines = [f"PORTFOLIO: {len(leases)} lease(s) total."]
    if len(leases) > MAX_LEASES_IN_CONTEXT:
        lines.append(
            f"NOTE: only the first {MAX_LEASES_IN_CONTEXT} of {len(leases)} leases are listed below "
            "(portfolio too large to fit all of them). If the question needs the full portfolio, say so in your answer."
        )
    lines.append("")
    lines.append("LEASES (id | tenant | address | monthly rent | sq ft | start | end):")
    for lease in leases[:MAX_LEASES_IN_CONTEXT]:
        fields = lease.get("extracted_fields", lease)
        tenant = field_value(lease, "tenant") or "not found"
        address = field_value(lease, "property_address") or "not found"
        rent = _fmt_money(field_value(lease, "rent_amount"))
        sqft = field_value(lease, "square_footage") or "not found"
        start = field_value(lease, "lease_start_date") or "not found"
        end = field_value(lease, "lease_end_date") or "not found"
        lines.append(f"  {lease['id']} | {tenant} | {address} | {rent}/mo | {sqft} | starts {start} | ends {end}")

    open_discrepancies = [d for d in discrepancies if d["status"] == "open"]
    by_severity: Dict[str, int] = {}
    for d in open_discrepancies:
        by_severity[d.get("severity") or "unspecified"] = by_severity.get(d.get("severity") or "unspecified", 0) + 1
    lines.append("")
    lines.append(f"OPEN DISCREPANCIES: {len(open_discrepancies)} total ({', '.join(f'{v} {k}' for k, v in sorted(by_severity.items())) or 'none'}).")
    for d in open_discrepancies[:100]:
        lines.append(f"  discrepancy #{d['id']} (lease {d.get('lease_id')}): [{d.get('severity')}] {d.get('category')}: {d.get('message')}")
    if len(open_discrepancies) > 100:
        lines.append(f"  ...and {len(open_discrepancies) - 100} more open discrepancies not listed individually.")

    active_alerts = [a for a in alerts if a["status"] == "active"]
    alert_by_severity: Dict[str, int] = {}
    for a in active_alerts:
        alert_by_severity[a["severity"]] = alert_by_severity.get(a["severity"], 0) + 1
    lines.append("")
    lines.append(f"ACTIVE ALERTS: {len(active_alerts)} total ({', '.join(f'{v} {k}' for k, v in sorted(alert_by_severity.items())) or 'none'}).")
    for a in active_alerts[:50]:
        lines.append(f"  alert #{a['id']} [{a['severity']}] {a['title']}")

    return "\n".join(lines)


def _system_prompt(portfolio_context: str, reference_date: date) -> str:
    return f"""You are the in-app assistant for Abstractly, a commercial lease abstraction and portfolio intelligence tool. You answer questions about the user's REAL, currently-uploaded lease portfolio, or navigate them somewhere in the app.

Today's date is {reference_date.isoformat()}.

RULES:
- Ground every informational answer in the actual data below. Never invent a number, date, tenant, or clause -- if the data doesn't show it, say it isn't found rather than guessing (this app's whole design principle is "flag missing, don't fabricate" -- your answers must hold to the same standard).
- If a question could refer to more than one lease, or you don't have enough information in the data below to answer confidently, use response_type "clarifying" and ask a specific question back -- do not guess which lease/record they mean.
- If the user wants to be taken somewhere ("show me...", "take me to...", "open...", "go to..."), use response_type "navigational" with the matching route. For a specific lease, route must be "detail" and lease_id must be a real id from the LEASES list below -- never invent one.
- Keep answers concise and specific -- cite the actual number/date/name, not a vague summary.
- You must always call the respond_to_user tool. Never reply with plain text.

{portfolio_context}
"""


class AssistantError(Exception):
    """Raised when the Claude API call itself fails (network, auth, rate limit on Anthropic's side) -- distinct from a normal clarifying/informational response, which is never an error."""


def _validate_navigation(result: Dict[str, Any], valid_lease_ids: set) -> Dict[str, Any]:
    """
    Never trust the model's route/lease_id blindly -- a hallucinated
    route name or a lease_id that isn't actually in this portfolio
    must not reach the frontend as if it were valid. Downgrades to a
    safe informational fallback rather than passing through something
    that would 404 or silently do nothing client-side.
    """
    if result.get("response_type") != "navigational":
        return result
    route = result.get("route")
    if route not in VALID_ROUTES:
        logger.warning("assistant produced an invalid route %r, downgrading to informational", route)
        return {"response_type": "informational", "answer": result.get("answer", "I couldn't find that page.")}
    if route == "detail":
        lease_id = result.get("lease_id")
        if lease_id not in valid_lease_ids:
            logger.warning("assistant produced a lease_id %r not in the real portfolio, downgrading to informational", lease_id)
            return {"response_type": "informational", "answer": result.get("answer", "I couldn't find that specific lease.")}
    return result


def ask_assistant(question: str, client: Optional[anthropic.Anthropic] = None, reference_date: Optional[date] = None) -> Dict[str, Any]:
    """
    The whole pipeline: pull the real portfolio, build the compact
    grounding context, call Claude with the forced respond_to_user
    tool, validate the result, return a plain dict ready to persist
    and return from the route. Raises AssistantError if the API call
    itself fails -- callers should turn that into a 502/503, never a
    500 with a raw traceback.
    """
    leases = database.get_all_effective_leases()
    discrepancies = database.list_discrepancies()
    alerts = database.list_alerts()
    context = build_portfolio_context(leases, discrepancies, alerts)
    system_prompt = _system_prompt(context, reference_date or date.today())

    anthropic_client = client or anthropic.Anthropic()
    try:
        response = anthropic_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": question}],
            tools=[RESPOND_TOOL],
            tool_choice={"type": "tool", "name": "respond_to_user"},
        )
    except anthropic.APIError as e:
        logger.exception("Anthropic API call failed")
        raise AssistantError(str(e)) from e

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        # Shouldn't happen with tool_choice forcing this exact tool,
        # but fail into a clean clarifying response rather than a
        # KeyError/None-access crash if the API ever returns something
        # unexpected.
        return {"response_type": "clarifying", "answer": "Sorry, I didn't understand that -- could you rephrase your question?"}

    result = dict(tool_use.input)
    valid_lease_ids = {lease["id"] for lease in leases}
    return _validate_navigation(result, valid_lease_ids)


# ----------------------------------------------------------------------
# Per-user rate limiting -- in-memory, per-process, fixed window, same
# pattern already established for POST /waitlist in api.py (see that
# code's own comment for why this style was chosen over a new
# dependency). Keyed by user_id, not IP, since this is an
# authenticated endpoint -- IP would let one abusive account behind a
# shared IP throttle everyone else on it, and wouldn't stop the same
# account switching IPs.
# ----------------------------------------------------------------------
_rate_limit_state: Dict[int, tuple] = {}
RATE_LIMIT_MAX = 20
RATE_LIMIT_WINDOW_SECONDS = 60


def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    window_start, count = _rate_limit_state.get(user_id, (now, 0))
    if now - window_start >= RATE_LIMIT_WINDOW_SECONDS:
        window_start, count = now, 0
    count += 1
    _rate_limit_state[user_id] = (window_start, count)
    return count > RATE_LIMIT_MAX


def _reset_rate_limit_state_for_tests():
    _rate_limit_state.clear()
