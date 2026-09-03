"""
AI rent-roll validation: cross-check one imported rent-roll line item
against the abstracted lease document on file for that same unit, and
report the disagreements with a severity (high/medium/low) and a
plain-language explanation a human can act on.

This is the model-backed complement to portfolio.compute_rent_roll_
reconciliation (which is pure arithmetic: does the number match within
tolerance). The model catches what arithmetic can't -- a rent-roll
"rent" that's actually gross-including-CAM vs. the lease's base rent, a
DBA vs. legal-entity name that's really the same tenant, a rent-roll
expiration date that predates a renewal the lease grants, a security
deposit that silently drifted. Same call discipline as
app/ai_extraction.py (forced tool, own retry/backoff/timeout, every
failure -> AIExtractionError).

Guardrail: validation only runs against a lease document that has
actually been abstracted. If the matching lease PDF has no usable
extracted fields yet (still processing, or extraction failed), this
returns status "not_abstracted" and the caller skips it -- never an
error, never a comparison against empty data.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from . import database
from .ai_extraction import AIExtractionError, call_forced_tool, tool_payload, DEFAULT_MODEL
from .portfolio import _is_rent_roll_import, _normalize_address, field_value

logger = logging.getLogger(__name__)

# The fields worth comparing between a rent-roll row and a lease. Kept
# to the ones a rent roll actually carries -- a rent roll never states
# an exclusivity clause or a cure period.
COMPARABLE_FIELDS = [
    "tenant",
    "rent_amount",
    "lease_start_date",
    "lease_end_date",
    "security_deposit",
    "square_footage",
    "cam_charges",
]

# A lease document counts as "abstracted" if at least one of these came
# back with a value -- an extraction that found none of them either
# failed or the file wasn't a lease, and there's nothing to validate
# against.
_ABSTRACTION_EVIDENCE_FIELDS = ["tenant", "rent_amount", "lease_start_date", "lease_end_date"]

SEVERITIES = ("high", "medium", "low")


class RentRollValidationError(AIExtractionError):
    """A rent-roll validation call failed or came back unusable. Subclasses AIExtractionError so existing 502 handling catches it too."""


SYSTEM_PROMPT = """You are a commercial real estate analyst doing lease-vs-rent-roll due diligence. You are given one unit's data from two sources: a property manager's rent roll, and the abstracted terms of the actual signed lease on file for that unit. Your job is to find where they disagree and say how much it matters.

For each real disagreement, assign a severity:
- "high": a difference that changes the economics or the legal picture. Rent off by a material amount; a genuinely different tenant entity; a lease-roll expiration that is EARLIER than the lease's actual term (classic stale-rent-roll-after-a-renewal problem); a security deposit materially short. Someone underwriting this deal off the rent roll would be misled.
- "medium": a real disagreement that a person should reconcile but that doesn't by itself change the deal -- a modest rent delta, a date off by days, a square-footage difference within normal remeasurement range, a name that is probably the same tenant but written differently enough to warrant a check.
- "low": cosmetic or almost certainly benign -- rounding, a DBA vs. the legal entity name, a field present on one side and blank on the other, formatting.

Rules:
- Only report an ACTUAL disagreement. If the two sources agree (exactly, or trivially -- "$6,250" vs "$6,250.00", "Acme LLC" vs "Acme, LLC"), do not report it.
- If a field is missing on one side, that is at most "low" (nothing to disagree with), and only worth reporting if the missing side is the rent roll and the field is rent or a date.
- Be specific in the explanation: name both values and why the gap matters (or doesn't). The recommendation should be a concrete next step ("confirm against the executed renewal amendment", "no action needed").
- Do not invent fields. Use the field names given. Use "other" only for a genuine issue that doesn't fit one of the named fields.
- Always call the record_rent_roll_validation tool exactly once."""

RECORD_TOOL = {
    "name": "record_rent_roll_validation",
    "description": (
        "Record every real disagreement between the rent roll and the lease for this unit. "
        "An empty discrepancies list is a valid, meaningful result -- it means the two sources agree."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "discrepancies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": [*COMPARABLE_FIELDS, "other"],
                        },
                        "severity": {"type": "string", "enum": list(SEVERITIES)},
                        "rent_roll_value": {"type": ["string", "null"]},
                        "lease_value": {"type": ["string", "null"]},
                        "explanation": {"type": "string", "description": "What disagrees and why it does or doesn't matter. Name both values."},
                        "recommendation": {"type": "string", "description": "Concrete next step."},
                    },
                    "required": ["field", "severity", "explanation", "recommendation"],
                },
            },
            "overall_assessment": {
                "type": "string",
                "description": "One or two sentences: do these two records tell the same story about this unit?",
            },
        },
        "required": ["discrepancies", "overall_assessment"],
    },
}


def is_abstracted(lease_document: Dict[str, Any]) -> bool:
    fields = lease_document.get("extracted_fields") or {}
    return any((fields.get(name) or {}).get("value") for name in _ABSTRACTION_EVIDENCE_FIELDS)


def _render_side(label: str, lease: Dict[str, Any]) -> str:
    lines = [f"{label}:"]
    for name in COMPARABLE_FIELDS:
        entry = (lease.get("extracted_fields") or {}).get(name) or {}
        value = entry.get("value")
        conf = entry.get("confidence")
        if value is None:
            lines.append(f"  - {name}: (not stated)")
        else:
            suffix = f"  [lease-abstraction confidence: {conf}]" if conf and label.startswith("LEASE") else ""
            lines.append(f"  - {name}: {value}{suffix}")
    return "\n".join(lines)


def _user_message(rent_roll_lease: Dict[str, Any], lease_document: Dict[str, Any], address: Optional[str]) -> str:
    return (
        f"Unit: {address or 'address not stated'}\n\n"
        f"{_render_side('RENT ROLL (property manager system)', rent_roll_lease)}\n\n"
        f"{_render_side('LEASE ON FILE (abstracted from the signed document)', lease_document)}\n\n"
        "Report every real disagreement with its severity. If they agree, return an empty discrepancies list."
    )


def _coerce_discrepancy(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    field = raw.get("field")
    if field not in (*COMPARABLE_FIELDS, "other"):
        field = "other"
    severity = raw.get("severity")
    if severity not in SEVERITIES:
        # An un-graded disagreement is still a disagreement -- keep it,
        # at the lowest actionable tier, rather than dropping it.
        severity = "low"
    explanation = (raw.get("explanation") or "").strip()
    if not explanation:
        return None
    return {
        "field": field,
        "severity": severity,
        "rent_roll_value": raw.get("rent_roll_value"),
        "lease_value": raw.get("lease_value"),
        "explanation": explanation,
        "recommendation": (raw.get("recommendation") or "").strip() or "Reconcile against the source documents.",
    }


def validate_rent_roll_against_lease(
    rent_roll_lease: Dict[str, Any],
    lease_document: Dict[str, Any],
    *,
    client: Optional[anthropic.Anthropic] = None,
) -> Dict[str, Any]:
    """
    Validate one rent-roll row against one abstracted lease document for
    the same unit.

    Returns:
      {"status": "validated" | "not_abstracted",
       "discrepancies": [{field, severity, rent_roll_value, lease_value,
                          explanation, recommendation}, ...],
       "assessment": str,
       "rent_roll_lease_id": int, "lease_document_id": int,
       "address": str | None,
       "_ai_meta": {...}}

    status "not_abstracted" (no model call made) when the lease document
    has no usable extracted fields yet -- the caller should skip it.

    Raises RentRollValidationError on a genuine call failure.
    """
    address = field_value(rent_roll_lease, "property_address") or field_value(lease_document, "property_address")
    base = {
        "rent_roll_lease_id": rent_roll_lease.get("id"),
        "lease_document_id": lease_document.get("id"),
        "address": address,
    }

    if not is_abstracted(lease_document):
        return {**base, "status": "not_abstracted", "discrepancies": [], "assessment":
                "The lease document for this unit hasn't been successfully abstracted yet, so there's nothing to validate the rent roll against."}

    started = time.monotonic()
    response = call_forced_tool(
        system=SYSTEM_PROMPT,
        user_content=_user_message(rent_roll_lease, lease_document, address),
        tool=RECORD_TOOL,
        client=client,
        max_tokens=2048,
        unavailable_message="Rent-roll validation is temporarily unavailable. Please try again in a moment.",
        bad_input_message="This rent-roll row couldn't be validated automatically.",
    )
    payload = tool_payload(response, bad_input_message="This rent-roll row couldn't be validated automatically.")

    discrepancies = [d for d in (_coerce_discrepancy(x) for x in (payload.get("discrepancies") or [])) if d]
    usage = getattr(response, "usage", None)
    meta = {
        "model": DEFAULT_MODEL,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "discrepancy_count": len(discrepancies),
    }
    return {
        **base,
        "status": "validated",
        "discrepancies": discrepancies,
        "assessment": (payload.get("overall_assessment") or "").strip(),
        "_ai_meta": meta,
    }


# ----------------------------------------------------------------------
# Unit matching + portfolio-wide sweep
# ----------------------------------------------------------------------

def find_unit_pairs(leases: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any], str]]:
    """
    Every (rent_roll_row, lease_document) pair that refers to the same
    unit -- exact normalized address match, the same conservative
    same-UNIT matching compute_rent_roll_reconciliation uses. A rent
    roll row with no matching lease PDF (the common case) yields no
    pair. Returns (rent_roll_lease, lease_document, address) tuples.
    """
    by_address: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for lease in leases:
        if not _is_rent_roll_import(lease):
            continue
        addr = _normalize_address(field_value(lease, "property_address"))
        if addr:
            by_address.setdefault(addr, {"rr": [], "doc": []})["rr"].append(lease)
    for lease in leases:
        if _is_rent_roll_import(lease):
            continue
        addr = _normalize_address(field_value(lease, "property_address"))
        if addr and addr in by_address:
            by_address[addr]["doc"].append(lease)

    pairs = []
    for group in by_address.values():
        for rr in group["rr"]:
            for doc in group["doc"]:
                address = field_value(rr, "property_address") or field_value(doc, "property_address")
                pairs.append((rr, doc, address))
    return pairs


def sync_validation_result(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Persist a validate_rent_roll_against_lease result's discrepancies to
    the discrepancies table (type "rent_roll_ai_validation"), one row
    per (pair, field), using the MODEL's severity. Stable natural_key so
    re-running updates the same rows instead of duplicating. Returns the
    discrepancies list, each annotated in place with discrepancy_id /
    resolution_status.
    """
    from .discrepancies import _annotate

    rr_id = result.get("rent_roll_lease_id")
    doc_id = result.get("lease_document_id")
    out = []
    for d in result.get("discrepancies", []):
        natural_key = f"rent_roll_ai:{rr_id}:{doc_id}:{d['field']}"
        message = (
            f"Rent roll vs. lease disagree on {d['field']} at {result.get('address') or 'this unit'}: "
            f"{d.get('rent_roll_value')!r} (rent roll) vs. {d.get('lease_value')!r} (lease). {d['explanation']}"
        )
        discrepancy_id = database.upsert_discrepancy(
            discrepancy_type="rent_roll_ai_validation",
            natural_key=natural_key,
            category="rent_roll_ai_validation",
            field=d["field"],
            severity=d["severity"],
            message=message,
            details={**d, "address": result.get("address"), "assessment": result.get("assessment")},
            lease_id=rr_id,
            related_lease_id=doc_id,
        )
        _annotate(d, discrepancy_id)
        out.append(d)
    return out
