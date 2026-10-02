"""
Credit memo assembly: takes a complete underwriting result from
app/loan_underwriting.py, asks Claude for the narrative sections only,
and returns one data structure that app/credit_memo_export.py renders
to .docx.

THE DIVISION OF LABOUR, which is the whole point of this module:

    numbers  ->  loan_underwriting.py   (plain Python arithmetic)
    prose    ->  Claude, here
    layout   ->  credit_memo_template.py
    document ->  credit_memo_export.py

The model is never asked to compute, round, restate or total anything. It
receives already-computed figures as read-only context and is asked to
write prose that refers to them. That boundary is why a credit officer
can check this document: every number in it is reproducible by hand from
the cited source rows, and no number passed through a model on its way to
the page.

The model is also explicitly forbidden from stating a recommendation --
see credit_memo_template.RECOMMENDATION_PLACEHOLDER for why that belongs
to a human, and tests/test_credit_memo.py for the assertion that enforces
it rather than trusting the prompt.

Follows app/cre_qa.py's call pattern exactly, including the injectable
`client` parameter, which is what makes every test mock the API instead
of spending money on it.

DEGRADES GRACEFULLY, BY DESIGN. If there's no ANTHROPIC_API_KEY, or the
call fails, or the response can't be parsed, each narrative section falls
back to a clearly-marked placeholder and the memo still renders with all
of its tables intact. This is not defensive padding: the numbers are the
part a lender needs, the prose is a drafting convenience, and a missing
API key should not block a credit memo. (It is also the project's current
reality -- the Anthropic key on this account has no credit, so the
fallback path is the one that runs today.)
"""
import logging
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional

import anthropic

from .credit_memo_template import (
    MEMO_FOOTER,
    MEMO_PREAMBLE,
    MEMO_TITLE,
    RECOMMENDATION_PLACEHOLDER,
    SPONSOR_PLACEHOLDER,
    SECTIONS,
    narrative_sections,
)
from .normalize import format_currency

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("CREDIT_MEMO_MODEL", "claude-sonnet-5")
MAX_TOKENS = 2048

# The model must emit sections behind this sentinel so they can be split
# apart deterministically. A sentinel beats asking for JSON here: prose
# containing quotes, newlines and dollar figures is exactly what breaks
# naive JSON emission, and a failed split degrades to one placeholder
# section rather than losing the whole response.
_SECTION_PATTERN = re.compile(r"<<<SECTION:([a-z_]+)>>>\s*(.*?)(?=<<<SECTION:|\Z)", re.DOTALL)

CREDIT_MEMO_SYSTEM_PROMPT = """You are drafting narrative sections of a commercial real estate credit memorandum for a multifamily loan, inside Abstractly, a lease abstraction and underwriting platform. A bank credit analyst will review and edit what you write before it reaches a credit committee.

## The one rule that matters most

Every number has already been computed for you and is supplied in the user message. You must NEVER compute, derive, total, re-express, round, or estimate a number. Refer to the figures you are given, exactly as given. If you want to make a point that would require a figure you were not given, make the point qualitatively or omit it. Do not write "approximately", "roughly", or "about" in front of a supplied figure -- the supplied figures are exact.

If a figure you need is marked "not available" or is absent, say plainly that it is not available. Never fill a gap with a plausible-sounding number. A fabricated figure in a credit memo is the worst possible failure mode of this tool.

## You must not state a recommendation

Do not recommend approval, denial, or approval with conditions. Do not write "we recommend", "the loan should be approved", "this is a sound credit", "declining is advised", or any equivalent. Do not imply a verdict through framing such as "this deal clearly works". The credit decision belongs to the credit officer, who has borrower relationship, portfolio concentration and market context that you do not have. A separate placeholder in the document carries the recommendation line; your job is to give the officer the analysis they need to write it themselves.

Section 7 (Risks and Mitigants) is where you are candid about what is wrong with the deal. Being candid there is not the same as recommending denial -- state the risk and its mitigant, and stop.

## Tone and form

- Write for a credit committee: precise, plain, unhedged. No marketing language, no filler, no restating the heading.
- Two to four short paragraphs per section unless the section asks for a list. Prose, not bullet soup, except where a list is genuinely the right form (conditions).
- Lead with what matters to a lender's downside, not with description for its own sake.
- Do not invent facts about the sponsor, the market, comparable properties, the submarket, local employment, or anything else not supplied to you. You know only the figures given.
- Where a data gap exists, name it as a gap. That is useful to a lender, not an embarrassment to hide.

## Output format

Emit each requested section exactly once, in the order requested, each preceded by its sentinel on its own line:

<<<SECTION:section_key>>>
Your prose for that section.

Emit nothing before the first sentinel and nothing after the last section's prose. No headings, no preamble, no commentary about your output."""


class CreditMemoError(Exception):
    """Raised only for a genuinely unusable request (e.g. an underwriting result missing its NOI build-up). API failure is NOT this -- that degrades to placeholder prose."""


def _fmt_money(value: Optional[float]) -> str:
    """Currency for display, or an explicit not-available marker -- never a blank cell or a 0 standing in for an unknown."""
    if value is None:
        return "not available"
    return format_currency(value)


def _fmt_pct(value: Optional[float], places: int = 2) -> str:
    if value is None:
        return "not available"
    return f"{value:.{places}f}%"


def _fmt_ratio(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    return f"{value:.2f}x"


def _narrative_context(underwriting: Dict[str, Any]) -> str:
    """
    The computed figures handed to the model as read-only context.

    Deliberately pre-formatted strings, not raw floats: the model is less
    likely to "tidy up" a figure it receives as "$1,198,744.84" than one
    it receives as 1198744.84, and if it does echo a figure, it echoes the
    exact string the document itself prints. Nothing here asks for, or
    leaves room for, a calculation.
    """
    build_up = underwriting["noi_build_up"]
    ratios = underwriting["ratios"]
    sizing = underwriting["sizing"]
    terms = underwriting["loan_terms"]
    request = underwriting.get("loan_request") or {}
    snapshot = underwriting.get("t12_snapshot") or {}

    lines: List[str] = [
        "## Computed figures (exact -- use as given, never recompute)",
        "",
        "### Loan request",
        f"- Property: {request.get('property_address', 'not available')}",
        f"- Deal name: {request.get('deal_name') or 'not provided'}",
        f"- Units: {terms.get('unit_count') or 'not available'}",
        f"- Loan amount: {_fmt_money(terms.get('loan_amount'))}",
        f"- Interest rate: {_fmt_pct(terms.get('annual_rate_pct'))}",
        f"- Amortization: {terms.get('amortization_years')} years",
        f"- Term: {terms.get('term_years') or 'not provided'} years",
        f"- Interest-only period: {terms.get('interest_only_months') or 0} months",
        f"- Purchase price: {_fmt_money(terms.get('purchase_price'))}",
        f"- Appraised value: {_fmt_money(terms.get('appraised_value'))}",
        f"- LTV measured against: {underwriting['value_basis'].get('value_basis_source') or 'not available'}"
        f" ({_fmt_money(underwriting['value_basis'].get('value_basis'))})",
        "",
        "### Underwritten NOI build-up",
        f"- Gross potential rent: {_fmt_money(build_up['gross_potential_rent'])}",
        f"- Less vacancy at {_fmt_pct(build_up['vacancy_pct'])}: {_fmt_money(build_up['vacancy_amount'])}",
        f"- Less loss to lease: {_fmt_money(build_up['loss_to_lease'])}",
        f"- Less concessions: {_fmt_money(build_up['concessions'])}",
        f"- Less bad debt / collection loss: {_fmt_money(build_up['bad_debt'])}",
        f"- Effective rental income: {_fmt_money(build_up['effective_rental_income'])}",
        f"- Plus other income: {_fmt_money(build_up['other_income'])}",
        f"- Effective gross income: {_fmt_money(build_up['effective_gross_income'])}",
        f"- Less operating expenses (excluding management fee): {_fmt_money(build_up['operating_expenses_ex_management'])}",
        f"- Less management fee at {_fmt_pct(build_up['management_fee_pct'])} of EGI: {_fmt_money(build_up['management_fee'])}",
        f"- Less replacement reserves ({_fmt_money(build_up['replacement_reserves_per_unit'])}/unit): {_fmt_money(build_up['replacement_reserves'])}",
        f"- **Underwritten NOI: {_fmt_money(build_up['underwritten_noi'])}**",
        f"- Historical T-12 NOI as stated on the operating statement: {_fmt_money(underwriting.get('historical_noi'))}",
        "",
        "### Ratios",
        f"- DSCR on fully amortizing debt service: {_fmt_ratio(ratios.get('dscr'))}",
        f"- DSCR in year one (as the loan actually pays): {_fmt_ratio(ratios.get('dscr_year_one'))}",
        f"- DSCR during the interest-only period: {_fmt_ratio(ratios.get('dscr_interest_only'))}",
        f"- LTV: {_fmt_pct(ratios.get('ltv_pct'))}",
        f"- Debt yield: {_fmt_pct(ratios.get('debt_yield_pct'))}",
        f"- Breakeven occupancy: {_fmt_pct(ratios.get('breakeven_occupancy_pct'))}",
        f"- Annual debt service (amortizing): {_fmt_money(underwriting['debt_service'].get('annual_debt_service_amortizing'))}",
        "",
        "### Loan sizing by constraint",
        f"- Maximum loan at target DSCR {underwriting['constraints_used']['target_dscr']}x: {_fmt_money(sizing.get('max_loan_by_dscr'))}",
        f"- Maximum loan at {_fmt_pct(underwriting['constraints_used']['max_ltv_pct'])} LTV: {_fmt_money(sizing.get('max_loan_by_ltv'))}",
        f"- Maximum loan at {_fmt_pct(underwriting['constraints_used']['min_debt_yield_pct'])} minimum debt yield: {_fmt_money(sizing.get('max_loan_by_debt_yield'))}",
        f"- **Binding constraint: {sizing.get('binding_constraint_label') or 'not available'}**",
        f"- **Maximum supportable loan: {_fmt_money(sizing.get('maximum_loan'))}** "
        f"(versus {_fmt_money(terms.get('loan_amount'))} requested)",
        "",
        "### Stress tests",
    ]

    for case in underwriting.get("stress_tests", []):
        lines.append(
            f"- {case['label']}: NOI {_fmt_money(case['underwritten_noi'])}, "
            f"DSCR {_fmt_ratio(case['dscr'])}, debt yield {_fmt_pct(case['debt_yield_pct'])}, "
            f"breakeven occupancy {_fmt_pct(case['breakeven_occupancy_pct'])}, "
            f"maximum loan {_fmt_money(case['maximum_loan'])}"
        )

    warnings = snapshot.get("warnings") or []
    if warnings:
        lines += ["", "### Data gaps recorded while parsing the T-12 (name these as gaps)"]
        lines += [f"- {warning}" for warning in warnings]

    if snapshot.get("management_fee_removed") is not None:
        lines += [
            "",
            f"Note: the T-12's own management fee of {_fmt_money(snapshot['management_fee_removed'])} "
            "was removed from the expense total before the underwritten management fee above was "
            "applied, so the fee is charged once rather than twice.",
        ]

    return "\n".join(lines)


def _placeholder_narrative(reason: str) -> str:
    """What a narrative section contains when the model didn't produce one. Says why, so a reader isn't left guessing whether the section was forgotten."""
    return (
        f"[ NARRATIVE NOT GENERATED -- {reason}. The computed figures in this memorandum are "
        f"unaffected and complete; this section's prose needs to be written by the analyst. ]"
    )


def generate_narratives(
    underwriting: Dict[str, Any],
    client: Optional[anthropic.Anthropic] = None,
) -> Dict[str, Any]:
    """
    Asks the model for every narrative section in one call and returns
    `{"narratives": {section_key: prose}, "generated": bool, "reason": str|None}`.

    One call rather than one per section: the figures context is the bulk
    of the prompt and is identical for every section, so four calls would
    pay for it four times. The frozen system prompt above is also marked
    for prompt caching, same as cre_qa.py does, since it's byte-identical
    on every call.

    Never raises on API failure. A missing key, a network error, a rate
    limit, or an unparseable response all return `generated: False` with
    placeholder prose per section and a reason -- the caller renders the
    memo regardless, because the tables are the part that matters and
    they don't come from here.
    """
    sections = narrative_sections()
    requested = {key: heading for key, heading, _ in sections}

    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        reason = "no Anthropic API key is configured"
        return {
            "narratives": {key: _placeholder_narrative(reason) for key in requested},
            "generated": False,
            "reason": reason,
        }

    brief_lines = [
        f"<<<SECTION:{key}>>> -- {heading}\n{brief}" for key, heading, brief in sections
    ]
    user_message = (
        f"{_narrative_context(underwriting)}\n\n"
        "## Sections to write\n\n"
        "Write each of the following, in this order, each behind its sentinel exactly as "
        "shown. Remember: refer to the figures above as given, never compute a new one, and "
        "never state a recommendation.\n\n"
        + "\n\n".join(brief_lines)
    )

    anthropic_client = client or anthropic.Anthropic()
    try:
        response = anthropic_client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=MAX_TOKENS,
            system=[{
                "type": "text",
                "text": CREDIT_MEMO_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        logger.exception("Credit memo: Anthropic API call failed")
        reason = f"the narrative generation request failed ({exc.__class__.__name__})"
        return {
            "narratives": {key: _placeholder_narrative(reason) for key in requested},
            "generated": False,
            "reason": reason,
        }

    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    parsed = {key: prose.strip() for key, prose in _SECTION_PATTERN.findall(text)}

    narratives: Dict[str, str] = {}
    missing: List[str] = []
    for key in requested:
        prose = parsed.get(key)
        if prose:
            narratives[key] = prose
        else:
            missing.append(key)
            narratives[key] = _placeholder_narrative(
                "the model's response did not include this section"
            )

    if missing and len(missing) == len(requested):
        reason = "the model's response could not be parsed into sections"
        logger.warning("Credit memo: %s (response began %r)", reason, text[:200])
        return {"narratives": narratives, "generated": False, "reason": reason}

    if missing:
        logger.warning("Credit memo: missing narrative section(s) %s", ", ".join(missing))

    return {
        "narratives": narratives,
        "generated": True,
        "reason": None if not missing else f"missing section(s): {', '.join(missing)}",
    }


def build_credit_memo_data(
    underwriting: Dict[str, Any],
    client: Optional[anthropic.Anthropic] = None,
    narratives: Optional[Dict[str, str]] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """
    The single structure credit_memo_export.py renders -- template
    sections resolved against the engine's figures, with narrative prose
    attached to the sections that take it.

    `narratives` may be supplied directly to skip the model call
    entirely (used by tests, and by any caller that already has prose).

    Raises CreditMemoError if the underwriting result is missing the NOI
    build-up -- that means the caller passed something that isn't an
    underwriting result, and rendering a memo with no financials would
    produce an authoritative-looking document with nothing in it.
    """
    if "noi_build_up" not in underwriting or "ratios" not in underwriting:
        raise CreditMemoError(
            "This doesn't look like an underwriting result -- expected 'noi_build_up' and "
            "'ratios' keys (see loan_underwriting.underwrite)."
        )

    if narratives is None:
        narrative_result = generate_narratives(underwriting, client=client)
    else:
        narrative_result = {"narratives": narratives, "generated": True, "reason": None}

    request = underwriting.get("loan_request") or {}

    return {
        "title": MEMO_TITLE,
        "preamble": MEMO_PREAMBLE,
        "footer": MEMO_FOOTER,
        "generated_date": (today or date.today()).isoformat(),
        "property_address": request.get("property_address"),
        "deal_name": request.get("deal_name"),
        "sections": SECTIONS,
        "recommendation_placeholder": RECOMMENDATION_PLACEHOLDER,
        "sponsor_placeholder": SPONSOR_PLACEHOLDER,
        "narratives": narrative_result["narratives"],
        "narratives_generated": narrative_result["generated"],
        "narratives_reason": narrative_result["reason"],
        "underwriting": underwriting,
    }
