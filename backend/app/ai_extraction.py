"""
AI lease abstraction: given a lease document's page text, call the
model once and get back the same {field: {value, source, confidence}}
structure the regex FieldExtractor produces -- so everything
downstream (confidence summaries, source citations, portfolio math,
risk analysis, exports) runs completely unchanged regardless of which
engine produced the fields.

Design mirrors app/assistant.py deliberately (same repo conventions):
  - one Claude API call, forced through a single tool
    (`record_lease_abstraction`) so the output is always a strict,
    parseable structure -- never free text whose shape we'd have to
    guess afterward.
  - a dedicated error type (AIExtractionError) for "the call itself
    failed / came back unusable", distinct from a normal successful
    extraction that happens to mark most fields not-found. Callers
    turn AIExtractionError into a clean 502 with a plain-language
    message, never a 500 traceback and never a silently-wrong answer.
  - explicit retry-with-backoff on transient failures and a hard
    per-request timeout so a hung model call can't wedge an upload.

Engine selection (regex vs. AI) lives in resolve_engine() -- the
existing offline test suite keeps using regex so it stays hermetic;
real uploads use AI when a key is configured.
"""

import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("LEASE_EXTRACTION_MODEL", "claude-sonnet-5")

# Generous: a long lease produces a lot of output tokens (15 fields,
# each with a value + a verbatim source quote that can be a full
# sentence or two).
MAX_TOKENS = 4096

# Per-request wall-clock cap. A lease extraction that hasn't come back
# in this long is hung, not slow -- fail it and let the caller show a
# clear error rather than holding the upload request open indefinitely.
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("LEASE_EXTRACTION_TIMEOUT", "90"))

# Retry policy for transient failures (429s, 5xx, connection resets,
# timeouts). Not retried: auth errors, 400s -- those won't fix
# themselves on a retry.
MAX_ATTEMPTS = 4
_BACKOFF_BASE_SECONDS = 1.5

# The document text handed to the model is capped so a pathological
# upload (a 500-page merged file) can't produce an enormous, expensive
# request. ~200k chars is comfortably within context for the models we
# use and far larger than any real single lease. Truncation is flagged
# to the model so it knows its view is partial.
MAX_DOCUMENT_CHARS = 200_000

# The 15 fields, matching app/field_extractor.py's keys exactly so the
# stored structure is engine-independent. Order here is the order the
# tool schema presents them in.
LEASE_FIELDS = [
    "tenant",
    "landlord",
    "rent_amount",
    "lease_start_date",
    "lease_end_date",
    "property_address",
    "security_deposit",
    "cam_charges",
    "rent_escalation",
    "renewal_options",
    "permitted_use",
    "exclusivity_clause",
    "insurance_requirements",
    "default_cure_period",
    "square_footage",
]

CONFIDENCE_LEVELS = ("high", "medium", "low")


class AIExtractionError(Exception):
    """
    The AI extraction call failed or returned something unusable
    (network/auth/rate-limit on Anthropic's side, a hung request that
    hit the timeout, or a malformed tool payload that survived none of
    the parsing/validation below). Callers should surface a clear
    "couldn't process this document" message and a 502 -- never a 500
    with a traceback, and never a silently-wrong extraction.
    """


# ----------------------------------------------------------------------
# Prompts
#
# NOTE: the user has an original "Abstractly -- Lease Abstraction
# Prompts" doc that was not in the repo when this was written. These
# were reconstructed from the field list + CLAUDE.md's quality bar and
# are the Phase 4 tuning starting point. Keep field descriptions and
# the confidence rubric here in sync with any updates to the original.
# ----------------------------------------------------------------------

SYSTEM_PROMPT = """You are a commercial real estate lease abstraction specialist. You read a lease document and extract a fixed set of structured fields, each with a confidence rating and a verbatim source quote a human can use to verify it.

Non-negotiable rules:
1. GROUND EVERY VALUE IN THE TEXT. Only report a value you can point to a specific quote for. Never infer, calculate, or "fill in" a plausible-looking value. If the document does not state a field, return it as not found (value null) -- that is a correct, expected answer, not a failure.
2. SOURCE EVERYTHING. For every field you DO find, give source_text: the exact span of document text (a phrase or a sentence, copied verbatim, not paraphrased) that establishes the value. This is what a human reviewer reads to confirm you are right.
3. CONFIDENCE MEANS WHAT IT SAYS. Calibrate honestly:
   - "high": the document states this explicitly and unambiguously; a careful human would read it exactly the way you did. You would be surprised to be wrong.
   - "medium": the value is supported by the text but required some interpretation -- prose rather than a labeled field, a figure stated once, mild ambiguity about which of two numbers applies, or a value assembled from more than one sentence.
   - "low": you found something plausible but the support is weak -- a loose keyword match, a figure that might belong to a different concept, an OCR-garbled area, or a partial clause. A human should double-check this before relying on it.
   Do not use "high" as a default. If you are reporting a value mainly because you expect the field to exist, that is "low" at best.
4. NEVER GUESS BETWEEN CANDIDATES. If two different values could each be "the rent" (e.g. an initial rate and a later escalated rate), report the one the lease establishes as the current/base value and note the ambiguity in source_text context; lower the confidence accordingly.
5. NORMALIZE VALUES to clean display strings (details per field below). Keep source_text raw.

You will always call the record_lease_abstraction tool exactly once. Never reply with prose."""


# Per-field guidance injected into the tool description block. Kept
# compact but specific -- these are the descriptions Phase 4 tuning
# will sharpen against observed failures.
FIELD_GUIDANCE = {
    "tenant": "The tenant / lessee / renter party. The entity or person leasing the space, not the owner. Full legal name including entity suffix (\"Blue Sky Coffee Roasters, Inc.\"). Exclude defined-term boilerplate like \"a Delaware corporation\".",
    "landlord": "The landlord / lessor party. The owner/grantor of the leasehold. Full legal name as above.",
    "rent_amount": "The base / minimum monthly rent for the initial term, as a monthly figure. Display as \"$6,250.00\". If the lease states an annual figure, convert to monthly and say so in source_text context. Do NOT return a later escalated year's rent here -- that belongs in rent_escalation.",
    "lease_start_date": "The commencement date of the lease term (not the execution/signing date unless they are the same). Display as \"April 1, 2025\".",
    "lease_end_date": "The expiration date of the initial term (before any renewal options). Display as \"March 31, 2030\".",
    "property_address": "The street address of the leased premises. Include suite/unit if given. Exclude the \"(the “Premises”)\" defined-term tail.",
    "security_deposit": "The security deposit amount held by the landlord. Display as \"$12,500.00\". Not the first month's rent unless the lease explicitly equates them.",
    "cam_charges": "Common Area Maintenance / operating expense contribution. The amount or the basis (e.g. \"$3.50 per sq ft annually\", \"$1,200.00 per month\", \"pro-rata share of 12.5%\"). Verbatim enough that a human can price it.",
    "rent_escalation": "How base rent increases over the term. Prefer a compact schedule (\"Year 1: $6,250/mo; Year 2: $6,438/mo; ...\") or a rule (\"3% annually on each anniversary\", \"CPI, capped at 4%\"). If rent is flat for the whole term, value is \"None\" only if the lease says so explicitly; otherwise not found.",
    "renewal_options": "Extension/renewal rights: number of options, length of each, notice window, and how renewal rent is set. E.g. \"2 options of 5 years each; 9 months prior written notice; renewal rent at fair market value\".",
    "permitted_use": "The use clause -- what the tenant is allowed to operate the premises as. Quote the operative restriction.",
    "exclusivity_clause": "Any exclusive-use protection granted to the tenant (landlord won't lease to a competing use). Summarize the protected category and any carve-outs. Not found if the lease has none.",
    "insurance_requirements": "Tenant's required insurance coverage -- the key limits (e.g. \"$2,000,000 per occurrence CGL\"). The headline requirement, not every sub-clause.",
    "default_cure_period": "The time the defaulting party has to cure after written notice of a monetary/general default. Display as \"10 days after written notice\". If monetary and non-monetary differ, report the general/non-monetary one and note the split.",
    "square_footage": "Rentable/leasable area of the premises. Display as \"2,400 sq ft\".",
}


def _field_property_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "value": {
                "type": ["string", "null"],
                "description": "The normalized display value, or null if the document does not state this field.",
            },
            "confidence": {
                "type": ["string", "null"],
                "enum": [*CONFIDENCE_LEVELS, None],
                "description": "high / medium / low per the rubric. null only when value is null.",
            },
            "source_text": {
                "type": ["string", "null"],
                "description": "Verbatim quote from the document that establishes the value. null only when value is null.",
            },
        },
        "required": ["value", "confidence", "source_text"],
    }


def _build_tool() -> Dict[str, Any]:
    field_lines = "\n".join(f"  - {name}: {FIELD_GUIDANCE[name]}" for name in LEASE_FIELDS)
    return {
        "name": "record_lease_abstraction",
        "description": (
            "Record the abstracted lease fields. Call exactly once. Provide every field key; "
            "for a field the document does not state, set value, confidence, and source_text all to null.\n\n"
            "FIELDS:\n" + field_lines
        ),
        "input_schema": {
            "type": "object",
            "properties": {name: _field_property_schema() for name in LEASE_FIELDS},
            "required": list(LEASE_FIELDS),
        },
    }


# ----------------------------------------------------------------------
# Document preparation
# ----------------------------------------------------------------------

def _pages_to_prompt_text(pages: List[Dict[str, Any]]) -> str:
    """
    Render the uniform `pages` shape into a single string with explicit
    page markers, so the model can (and is asked to) tie each source
    quote back to a page number. Truncates very large documents with a
    visible marker.
    """
    chunks = []
    running = 0
    truncated = False
    for page in pages:
        text = (page.get("text") or "").strip()
        header = f"\n===== PAGE {page.get('page')} =====\n"
        if running + len(header) + len(text) > MAX_DOCUMENT_CHARS:
            remaining = max(0, MAX_DOCUMENT_CHARS - running - len(header))
            chunks.append(header + text[:remaining])
            truncated = True
            break
        chunks.append(header + text)
        running += len(header) + len(text)

    body = "".join(chunks).strip()
    if truncated:
        body += "\n\n[DOCUMENT TRUNCATED HERE -- pages beyond this point were not included. If a field is not visible above, return it as not found rather than guessing.]"
    return body


def _user_message(pages: List[Dict[str, Any]]) -> str:
    return (
        "Abstract the following commercial lease. Page markers are shown as "
        "\"===== PAGE N =====\". Extract each field per the tool's field guidance and "
        "the confidence rubric in your instructions. For every field you find, source_text "
        "must be copied verbatim from the text below.\n\n"
        "--- BEGIN LEASE DOCUMENT ---\n"
        f"{_pages_to_prompt_text(pages)}\n"
        "--- END LEASE DOCUMENT ---"
    )


# ----------------------------------------------------------------------
# Response parsing / validation -> the engine-independent field shape
# ----------------------------------------------------------------------

def _locate_quote_page(quote: Optional[str], pages: List[Dict[str, Any]]) -> Optional[int]:
    """
    Best-effort: find which page a verbatim source quote came from, so
    the stored `source` matches the {"page": N, "quote": ...} shape the
    regex engine produces and every citation consumer already expects.
    Falls back through progressively looser matching; returns None if
    the quote can't be located at all (the quote is still kept as
    source_text either way).
    """
    if not quote:
        return None
    needle = re.sub(r"\s+", " ", quote).strip().lower()
    if not needle:
        return None
    candidates = [needle]
    if len(needle) > 60:
        candidates.append(needle[:60])
    for cand in candidates:
        for page in pages:
            haystack = re.sub(r"\s+", " ", (page.get("text") or "")).lower()
            if cand in haystack:
                return page.get("page")
    # Loosest: first handful of distinctive words.
    words = [w for w in re.findall(r"[a-z0-9$%.,-]+", needle) if len(w) > 2][:6]
    if words:
        probe = " ".join(words)
        for page in pages:
            haystack = re.sub(r"\s+", " ", (page.get("text") or "")).lower()
            if probe in haystack:
                return page.get("page")
    return None


def _not_found_entry() -> Dict[str, Any]:
    return {"value": None, "source": None, "confidence": None}


def _coerce_field_entry(raw: Any, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Turn one field object from the tool payload into the stored shape:
      {"value": str|None,
       "source": {"page": int, "quote": str} | None,
       "confidence": "high"|"medium"|"low"|None,
       "source_text": str | None,   # raw verbatim quote, kept as-is
       "engine": "ai"}
    Anything malformed for a single field degrades that field to
    not-found rather than failing the whole extraction.
    """
    if not isinstance(raw, dict):
        return {**_not_found_entry(), "engine": "ai"}

    value = raw.get("value")
    if isinstance(value, str):
        value = value.strip() or None
    elif value is not None:
        value = str(value)

    if value is None:
        return {**_not_found_entry(), "engine": "ai"}

    confidence = raw.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        # A value with no/garbled confidence is exactly the "found
        # something but unsure" case -- treat it as low, don't drop it.
        confidence = "low"

    source_text = raw.get("source_text")
    if isinstance(source_text, str):
        source_text = source_text.strip() or None
    else:
        source_text = None

    source = None
    if source_text:
        page = _locate_quote_page(source_text, pages)
        source = {"page": page if page is not None else (pages[0]["page"] if pages else 1),
                  "quote": source_text}

    entry = {
        "value": value,
        "source": source,
        "confidence": confidence,
        "source_text": source_text,
        "engine": "ai",
    }
    if source_text is None:
        # A value with no verbatim support violates the prompt's own
        # rule -- keep the value (the model still believes it) but make
        # the weak grounding explicit and never let it read as "high".
        entry["confidence"] = "low"
        entry["validation_note"] = "Model returned a value without a verbatim source quote -- verify against the document."
    return entry


def _parse_tool_payload(payload: Dict[str, Any], pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    result = {}
    for name in LEASE_FIELDS:
        result[name] = _coerce_field_entry(payload.get(name), pages)
    return result


# ----------------------------------------------------------------------
# The call
# ----------------------------------------------------------------------

def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError, anthropic.InternalServerError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in (408, 409, 425, 429, 500, 502, 503, 504, 529)
    return False


def _make_client(client: Optional[anthropic.Anthropic]) -> anthropic.Anthropic:
    if client is not None:
        return client
    # max_retries=0: we do our own retry loop below (with logging and
    # our own backoff schedule) rather than letting the SDK retry
    # opaquely underneath the timeout.
    return anthropic.Anthropic(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)


def call_forced_tool(
    *,
    system: str,
    user_content: str,
    tool: Dict[str, Any],
    client: Optional[anthropic.Anthropic] = None,
    model: Optional[str] = None,
    max_tokens: int = MAX_TOKENS,
    unavailable_message: str = "The document-extraction service is temporarily unavailable. Please try again in a moment.",
    bad_input_message: str = "This document couldn't be processed automatically.",
) -> Any:
    """
    One `messages.create` forced through exactly `tool`, wrapped in this
    module's retry/backoff/timeout policy. Shared by lease abstraction
    and rent-roll validation so both get identical failure handling.

    Returns the raw SDK response. Raises AIExtractionError on every
    failure path -- transient-exhausted, auth, bad request, hang. Never
    lets a raw SDK exception escape.
    """
    anthropic_client = _make_client(client)
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return anthropic_client.messages.create(
                model=model or DEFAULT_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            logger.error("AI call auth/permission failure: %s", e)
            raise AIExtractionError("The AI service is not configured correctly.") from e
        except anthropic.BadRequestError as e:
            logger.error("AI call rejected as a bad request: %s", e)
            raise AIExtractionError(bad_input_message) from e
        except anthropic.APIError as e:
            last_exc = e
            if not _is_retryable(e) or attempt == MAX_ATTEMPTS:
                logger.warning("AI call failed on attempt %d/%d (giving up): %s", attempt, MAX_ATTEMPTS, e)
                raise AIExtractionError(unavailable_message) from e
            sleep_s = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.75)
            logger.warning("AI call transient failure on attempt %d/%d, retrying in %.1fs: %s", attempt, MAX_ATTEMPTS, sleep_s, e)
            time.sleep(sleep_s)

    raise AIExtractionError(unavailable_message) from last_exc


def tool_payload(response: Any, *, bad_input_message: str = "This document couldn't be processed automatically.") -> Dict[str, Any]:
    """Pull the single forced tool_use block's input out of a response as a dict, or raise AIExtractionError if it isn't there / isn't an object."""
    tool_use = next((b for b in getattr(response, "content", []) if getattr(b, "type", None) == "tool_use"), None)
    if tool_use is None:
        logger.error("AI response had no tool_use block; stop_reason=%s", getattr(response, "stop_reason", None))
        raise AIExtractionError(bad_input_message)
    payload = tool_use.input
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError) as e:
            logger.error("AI tool payload was an unparseable string")
            raise AIExtractionError(bad_input_message) from e
    if not isinstance(payload, dict):
        logger.error("AI tool payload was not an object: %r", type(payload))
        raise AIExtractionError(bad_input_message)
    return payload


def _call_model(pages: List[Dict[str, Any]], client: Optional[anthropic.Anthropic]) -> Any:
    return call_forced_tool(
        system=SYSTEM_PROMPT,
        user_content=_user_message(pages),
        tool=_build_tool(),
        client=client,
    )


def _extract_tool_input(response: Any) -> Dict[str, Any]:
    return tool_payload(response)


def extract_lease_fields(
    pages: List[Dict[str, Any]],
    *,
    client: Optional[anthropic.Anthropic] = None,
) -> Dict[str, Any]:
    """
    Run one AI abstraction over `pages` (the uniform shape from
    document_extractor / pdf_extractor) and return the
    engine-independent field structure:

        {field_name: {"value": str|None,
                      "source": {"page": int, "quote": str} | None,
                      "confidence": "high"|"medium"|"low"|None,
                      "source_text": str | None,
                      "engine": "ai"}}

    with exactly the 15 keys in LEASE_FIELDS. Raises AIExtractionError
    (never a raw exception, never a partial/empty dict) if the call
    fails or the response is unusable.
    """
    if not pages:
        raise AIExtractionError("This document has no readable content to extract.")

    started = time.monotonic()
    response = _call_model(pages, client)
    payload = _extract_tool_input(response)
    fields = _parse_tool_payload(payload, pages)

    usage = getattr(response, "usage", None)
    telemetry = {
        "model": DEFAULT_MODEL,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "found_count": sum(1 for e in fields.values() if e.get("value") is not None),
    }
    logger.info("AI extraction ok: %s", telemetry)
    # Stashed under a private key so callers that want it (the upload
    # path, for telemetry logging) can read it, and json.dumps of the
    # whole structure still round-trips. Downstream field consumers
    # iterate LEASE_FIELDS explicitly and never see this.
    fields["_ai_meta"] = telemetry
    return fields


# ----------------------------------------------------------------------
# Engine selection
# ----------------------------------------------------------------------

def ai_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


_TRUTHY = {"1", "true", "yes", "on"}


def resolve_engine() -> str:
    """
    Decide which extraction engine a real upload should use.

      - LEASE_EXTRACTION_ENGINE=ai|regex  -> explicit override, always wins.
      - LEASE_AI_EXTRACTION truthy         -> ai, provided a key is set.
      - otherwise                          -> regex.

    Default-off (regex) is deliberate: it keeps the large offline unit
    suite hermetic with no fragile "am I in a test" detection, and
    makes turning the model on a single, visible config change
    (set in backend/.env for the running app; set by the Phase 4
    training harness; documented in .env.example / DEPLOYMENT.md).
    If the flag is on but no ANTHROPIC_API_KEY is configured, falls
    back to regex rather than failing every upload.
    """
    override = (os.environ.get("LEASE_EXTRACTION_ENGINE") or "").strip().lower()
    if override in ("ai", "regex"):
        if override == "ai" and not ai_available():
            logger.warning("LEASE_EXTRACTION_ENGINE=ai but ANTHROPIC_API_KEY is unset -- using regex.")
            return "regex"
        return override
    if (os.environ.get("LEASE_AI_EXTRACTION") or "").strip().lower() in _TRUTHY:
        if not ai_available():
            logger.warning("LEASE_AI_EXTRACTION is on but ANTHROPIC_API_KEY is unset -- using regex.")
            return "regex"
        return "ai"
    return "regex"
