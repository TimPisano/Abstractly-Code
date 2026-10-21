"""
AI extraction for affordable-housing contracts and agreements: HAP contracts
(PBRA, PBV, renewals) and LURAs / regulatory agreements.

The lease engine (app.ai_extraction) only has slots for the 15 CRE lease
fields, so on these documents it was never asked for a contract number, unit
count or rent. Here each document kind has its own field list, and the lease
fields the rest of the app shows are filled from those values (owner ->
landlord, effective date -> lease start), the way the form reader does it.

    kind = classify_doc_kind(pages)            # "hap_contract", "lura" or None
    out = extract_program_fields(pages, kind)
    out["program_fields"]    # {name: {"value", "source", "confidence", "method": "ai"}}
    out["checks"]            # arithmetic cross-checks (checks.py): flags, never changes values
    out["lease_fields"]      # the 15 lease fields, same shape as the lease engine's
    out["_ai_meta"]          # model, tokens, latency

One call per document, through ai_extraction.call_forced_tool (same retry,
timeout and error handling as lease extraction). Values are what the
document states; no HUD or agency rule is applied here.
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .. import ai_extraction
from .checks import run_checks
from .values import fill_address_parts, tidy

PROMPT_VERSION = "affordable-v1"
MAX_TOKENS = 8192
TOOL_NAME = "record_affordable_abstraction"

# Title phrases, matched near the start (first pages, first characters: a .txt
# upload is one long "page"); the earliest one decides. Kept to full titles:
# "restrictive covenant" alone appears in ordinary retail leases, and a retail
# lease's subordination clause names a "declaration of restrictive covenants"
# deep in the body.
KIND_PHRASES = {
    "hap_contract": ("housing assistance payments contract", "housing assistance payment contract",
                     "hap contract"),
    "lura": ("regulatory agreement", "declaration of restrictive covenants", "land use restriction agreement",
             "extended use agreement", "housing credit commitment", "extended low-income housing commitment"),
}
CLASSIFY_PAGES = 3
CLASSIFY_CHARS = 5_000

# (name, type, guidance). Types: text | money | date | int | pct.
_COMMON = [
    ("project_name", "text", "Name of the property or project."),
    ("owner_name", "text", "The owner entity (the party that owns the property), full legal name."),
    ("property_address", "text", "Full address of the property as written: street, city, state, ZIP."),
    ("street_address", "text", "Street address only (no city, state or ZIP)."),
    ("city", "text", "City where the property is."),
    ("state", "text", "State where the property is, as written."),
    ("zip", "text", "ZIP code of the property."),
    ("building_addresses", "text", "Every street address the document lists for the property's buildings, as written (e.g. \"57, 81 and 101 Main St\"), if it lists more than one; otherwise null."),
    ("county", "text", "County where the property is, without the word \"County\"."),
    ("total_units", "int", "Total number of units in the whole property, assisted or not."),
]

HAP_CONTRACT_FIELDS = _COMMON + [
    ("contract_number", "text", "The HAP contract number (e.g. \"TX24E000008\")."),
    ("rems_property_id", "text", "HUD's property ID number (iREMS / REMS / Property ID), if stated."),
    ("program_type", "text", "The rental assistance program: PBRA (project-based Section 8), PBV (project-based voucher), Section 811 PRA, Mod Rehab, or as named."),
    ("pha_name", "text", "The public housing agency that is party to the contract (PBV contracts)."),
    ("contract_administrator", "text", "The contract administrator, if named (HUD, a state agency or a PBCA)."),
    ("assignee_name", "text", "The new owner taking over the contract, if this document assigns it."),
    ("contract_units", "int", "Number of units covered by the contract (assisted / contract units)."),
    ("effective_date", "date", "Date the contract (or this renewal) takes effect: start of its term."),
    ("expiration_date", "date", "Date the contract term ends, if stated."),
    ("initial_term", "text", "Length of the contract term, e.g. \"20 years\"."),
    ("renewal_term_years", "int", "Length of the renewal term requested or granted, in years."),
    ("renewal_option", "text", "The renewal option, if this is a renewal or a renewal request (e.g. \"Option 1-A, Mark-Up-To-Market\")."),
    ("document_date", "date", "The date the document itself is dated (a letter's date, or the execution date)."),
    ("ami_limit_pct", "pct", "Income limit for assisted households as a percent of area median income, if stated (e.g. \"30%\")."),
]
HAP_TABLES = {
    "unit_mix": (
        "One row per bedroom size listed in the contract or its exhibits (unit schedule, rent schedule).",
        [("bedrooms", "int", "Bedrooms: 0 for studio / efficiency / SRO."),
         ("total_units", "int", "Units of this size in the whole property, if stated separately."),
         ("contract_units", "int", "Units of this size covered by the contract."),
         ("contract_rent", "money", "Current monthly contract rent for this size."),
         ("utility_allowance", "money", "Monthly utility allowance for this size, if the table gives one."),
         ("gross_rent", "money", "Monthly gross rent for this size, if the table gives one. Copy it as printed, even if it doesn't equal rent plus allowance."),
         ("proposed_rent", "money", "New monthly contract rent the document requests or sets, if any.")],
    ),
}

LURA_FIELDS = _COMMON + [
    ("agency_name", "text", "The agency, city or other party the owner makes the agreement with (e.g. the state housing finance agency)."),
    ("low_income_units", "int", "Number of units that must be low-income / rent-restricted."),
    ("min_applicable_fraction", "pct", "Minimum share of units that must stay low-income (the applicable fraction), as a percent."),
    ("ami_limit_pct", "pct", "The highest income limit for restricted units, as a percent of area median income (e.g. \"60%\")."),
    ("income_limit_area", "text", "The area whose median income sets the limits (MSA / HMFA / county), if named."),
    ("compliance_period_years", "int", "Length of the compliance period in years."),
    ("extended_use_years", "int", "How long the restrictions last in total, in years (the extended use period, or the agreement's term)."),
    ("effective_date", "date", "Date the agreement takes effect or is made."),
    ("recording_date", "date", "Date the agreement was recorded, if a recording stamp or line shows it."),
    ("recording_number", "text", "Recording / reception / instrument number, if shown."),
]
LURA_TABLES = {
    "unit_mix": (
        "One row per bedroom size, if the agreement lists the unit mix.",
        [("bedrooms", "int", "Bedrooms: 0 for studio / efficiency."),
         ("units", "int", "Number of units of this size.")],
    ),
    "set_asides": (
        "One row per income tier the agreement reserves units for (e.g. 5 units at 30% of AMI).",
        [("ami_pct", "pct", "The income limit, as a percent of area median income."),
         ("units", "int", "Number of units reserved at this limit, if stated as a count."),
         ("pct_of_units", "pct", "Share of units reserved at this limit, if stated as a percent.")],
    ),
    "bins": (
        "One row per building identification number (BIN) listed.",
        [("bin", "text", "The BIN exactly as written (e.g. \"UT-93-18004\").")],
    ),
}

FIELD_LISTS = {"hap_contract": (HAP_CONTRACT_FIELDS, HAP_TABLES), "lura": (LURA_FIELDS, LURA_TABLES)}

# lease field -> program field, so the app's lease views and checks still work
LEASE_MAP = {"landlord": "owner_name", "property_address": "property_address",
             "lease_start_date": "effective_date", "lease_end_date": "expiration_date"}

KIND_LABELS = {"hap_contract": "a Section 8 Housing Assistance Payments (HAP) contract, renewal, or related HUD filing",
               "lura": "an affordable-housing use agreement (LURA, regulatory agreement, or declaration of restrictive covenants)"}

SYSTEM_PROMPT = """You are an affordable housing compliance analyst. You read a HUD Section 8 or LIHTC document and record a fixed set of structured fields, each with a confidence rating and a verbatim source quote a human can use to verify it.

Rules:
1. Ground every value in the text. Only report a value you can point to a quote for. Never infer, calculate, or fill in a plausible value. If the document does not state a field, return it as not found (value null). That is a correct answer.
2. For every value you report, give source_text: the exact span of document text that establishes it, copied verbatim.
3. Confidence: "high" when the document states the value explicitly and unambiguously; "medium" when it needed interpretation (prose rather than a labeled field, or two candidate numbers); "low" when the support is weak or the text is OCR-garbled. Do not default to "high".
4. Report what the document says. Do not apply or assume any HUD or agency rule.
5. Normalize values: money as "$1,035", dates as "April 1, 2013", counts as plain digits ("120"), percents as "60%". Keep source_text raw.
6. Tables (unit mix, set-asides, BINs): one row per line of the document's own table or list; leave a column null when the document does not give it.

You will always call the record_affordable_abstraction tool exactly once. Never reply with prose."""


def classify_doc_kind(pages: List[Dict[str, Any]]) -> Optional[str]:
    """"hap_contract", "lura" or None, from title phrases in the first pages."""
    text = re.sub(r"\s+", " ", " ".join((p.get("text") or "") for p in pages[:CLASSIFY_PAGES]).lower())[:CLASSIFY_CHARS]
    best: Optional[Tuple[int, str]] = None
    for kind, phrases in KIND_PHRASES.items():
        for phrase in phrases:
            at = text.find(phrase)
            if at != -1 and (best is None or at < best[0]):
                best = (at, kind)
    return best[1] if best else None


def _row_schema(columns) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": ["string", "null"], "description": guidance} for name, _, guidance in columns},
        "required": [name for name, _, _ in columns],
    }


def _build_tool(kind: str) -> Dict[str, Any]:
    fields, tables = FIELD_LISTS[kind]
    props = {name: ai_extraction._field_property_schema() for name, _, _ in fields}
    for name, (guidance, columns) in tables.items():
        props[name] = {
            "type": "object",
            "description": guidance,
            "properties": {
                "rows": {"type": "array", "items": _row_schema(columns)},
                "confidence": {"type": ["string", "null"], "enum": [*ai_extraction.CONFIDENCE_LEVELS, None]},
                "source_text": {"type": ["string", "null"], "description": "Verbatim quote of the table or list."},
            },
            "required": ["rows", "confidence", "source_text"],
        }
    lines = [f"  - {name}: {guidance}" for name, _, guidance in fields]
    lines += [f"  - {name} (table): {guidance} Columns: " + "; ".join(f"{c} = {g}" for c, _, g in columns)
              for name, (guidance, columns) in tables.items()]
    return {
        "name": TOOL_NAME,
        "description": ("Record the abstracted fields. Call exactly once. Provide every key; for a field the "
                        "document does not state, set value, confidence and source_text to null (for a table, "
                        "an empty rows list).\n\nFIELDS:\n" + "\n".join(lines)),
        "input_schema": {"type": "object", "properties": props, "required": list(props)},
    }


def _user_message(pages: List[Dict[str, Any]], kind: str) -> str:
    return (f"The document below is {KIND_LABELS[kind]}. Page markers are shown as \"===== PAGE N =====\". "
            "Record each field per the tool's field list and the rules in your instructions.\n\n"
            "--- BEGIN DOCUMENT ---\n"
            f"{ai_extraction._pages_to_prompt_text(pages)}\n"
            "--- END DOCUMENT ---")


def _number(value: Optional[str]) -> Optional[str]:
    """Digits of a count or percent ("27 units" -> "27", "30% of AMI" -> "30"), else None."""
    m = re.search(r"\d+(?:\.\d+)?", value or "")
    return m.group(0) if m else None


def _program_entry(entry: Dict[str, Any], name: str = "") -> Dict[str, Any]:
    return {"value": tidy(name, entry["value"]), "source": entry["source"], "confidence": entry["confidence"],
            "method": "ai"}


def _flatten_tables(payload: Dict[str, Any], kind: str, pages) -> Dict[str, Dict[str, Any]]:
    """Table rows -> flat fields: units_2br, contract_rent_1br, units_at_30_pct_ami, bin, bin_2, ..."""
    out: Dict[str, Dict[str, Any]] = {}
    for table in FIELD_LISTS[kind][1]:
        raw = payload.get(table)
        if not isinstance(raw, dict) or not isinstance(raw.get("rows"), list):
            continue
        source = ai_extraction._coerce_field_entry(
            {"value": "table", "confidence": raw.get("confidence"), "source_text": raw.get("source_text")}, pages)

        def put(name, value):
            if value not in (None, "") and name not in out:
                out[name] = _program_entry({**source, "value": str(value).strip()}, name)

        def add(name, value):
            """Unit counts: rows that repeat a bedroom size (one row per building
            or stage) add up; rents and other values keep the first row."""
            if value in (None, ""):
                return
            if name in out:
                out[name]["value"] = str(int(float(out[name]["value"])) + int(float(value)))
            else:
                put(name, value)

        for i, row in enumerate(r for r in raw["rows"] if isinstance(r, dict)):
            if table == "bins":
                put("bin" if i == 0 else f"bin_{i + 1}", row.get("bin"))
                continue
            if table == "set_asides":
                ami = _number(row.get("ami_pct"))
                if ami:
                    put(f"units_at_{ami}_pct_ami", _number(row.get("units")))
                    put(f"pct_units_at_{ami}_pct_ami", row.get("pct_of_units"))
                continue
            beds = _number(row.get("bedrooms"))
            if beds is None:
                continue
            if kind == "lura":
                add(f"units_{beds}br", _number(row.get("units")))
                continue
            total, contract = _number(row.get("total_units")), _number(row.get("contract_units"))
            add(f"units_{beds}br", total or contract)
            add(f"contract_units_{beds}br", contract)
            put(f"contract_rent_{beds}br", row.get("contract_rent"))
            put(f"utility_allowance_{beds}br", row.get("utility_allowance"))
            put(f"gross_rent_{beds}br", row.get("gross_rent"))
            put(f"proposed_rent_{beds}br", row.get("proposed_rent"))
    return out


def extract_program_fields(pages: List[Dict[str, Any]], kind: str, *, client=None) -> Dict[str, Any]:
    """One AI call for a HAP contract or LURA. Raises ai_extraction.AIExtractionError
    on failure, like the lease engine."""
    if kind not in FIELD_LISTS:
        raise ValueError(f"no field list for document kind {kind!r}")
    if not pages:
        raise ai_extraction.AIExtractionError("This document has no readable content to extract.")
    started = time.monotonic()
    response = ai_extraction.call_forced_tool(system=SYSTEM_PROMPT, user_content=_user_message(pages, kind),
                                              tool=_build_tool(kind), client=client, max_tokens=MAX_TOKENS)
    payload = ai_extraction.tool_payload(response)

    program: Dict[str, Dict[str, Any]] = {}
    for name, _, _ in FIELD_LISTS[kind][0]:
        entry = ai_extraction._coerce_field_entry(payload.get(name), pages)
        if entry["value"] is not None:
            program[name] = _program_entry(entry, name)
    program.update({k: v for k, v in _flatten_tables(payload, kind, pages).items() if k not in program})
    fill_address_parts(program)
    checks = run_checks(program)

    lease = {f: {"value": None, "source": None, "confidence": None} for f in ai_extraction.LEASE_FIELDS}
    for lease_field, name in LEASE_MAP.items():
        if name in program:
            p = program[name]
            lease[lease_field] = {"value": p["value"], "source": p["source"], "confidence": p["confidence"], "engine": "ai"}

    usage = getattr(response, "usage", None)
    meta = {
        "model": ai_extraction.DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "doc_kind": kind,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "found_count": len(program),
    }
    return {"program_fields": program, "lease_fields": lease, "doc_kind": kind, "checks": checks, "_ai_meta": meta}
