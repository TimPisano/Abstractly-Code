"""
Decide who reads an affordable-housing document: the form reader or the AI.

    res = extract_document(pdf_bytes)
    choose_route(res)    # "form" or "ai"

Tenant-level forms (HUD-50059, TICs, RFTA, HUD-52641, ...) are standard,
filled by software, and read well by the form reader, so they go there
first and never cost an AI call. The AI is the fallback when the reader
doesn't recognise the document, when the form is one whose facts live in
prose or exhibits (FormSpec.route == "ai": PBV HAP contracts, LURAs), or
when a recognised form yields too little to trust (a different edition,
a bad scan). On the AI route, HAP contracts and LURAs get their own field
lists (ai_fields.py); anything else goes to the lease engine.

Not wired into uploads yet; see __init__.py.
"""

import re
from typing import Dict, List, Optional

# A recognised form whose reader filled fewer than this share of the form's
# fields is treated as misread and goes to the AI instead.
MIN_FORM_FIELD_SHARE = 0.25


def choose_route(form_result: Dict) -> str:
    if not form_result.get("form_id") or form_result.get("route") != "form":
        return "ai"
    possible = form_result.get("fields_possible") or 0
    found = len(form_result.get("program_fields") or {})
    if possible and found / possible < MIN_FORM_FIELD_SHARE:
        return "ai"
    return "form"


def ai_doc_kind(form_result: Dict, pages: List[Dict]) -> Optional[str]:
    """Which AI field list to use: "hap_contract", "lura", or None for the
    lease engine. A recognised form's own kind wins; otherwise the title."""
    from .ai_fields import FIELD_LISTS, classify_doc_kind
    kind = form_result.get("doc_kind")
    return kind if kind in FIELD_LISTS else classify_doc_kind(pages)


def fill_low_text_pages(pages: List[Dict], data: bytes, low_pages: List[int]) -> List[Dict]:
    """The upload path stops a whole document at "needs OCR" when one page
    has almost no text (a scanned signature page, an exhibit cover sheet).
    For the affordable reader, swap just those pages for this module's own
    layout / OCR text and carry on."""
    from .layout import layout_pages
    if not low_pages:
        return pages
    rebuilt = {p["page"]: p for p in layout_pages(data, ocr=True, include_acroform=True)}
    return [rebuilt.get(p["page"], p) if p["page"] in set(low_pages) else p for p in pages]


def merge_reads(ai_fields: Dict[str, Dict], form_fields: Dict[str, Dict]) -> Dict[str, Dict]:
    """The AI's program fields, with gaps filled from the form reader (form
    fields, Exhibit A tables). Where both read a number and disagree, both
    are kept visible: the AI's value stays, at low confidence, with a note
    naming the other reading. Values are never changed."""
    from .checks import VERIFY
    from .values import parse_money
    merged = {k: dict(v) for k, v in ai_fields.items()}
    for name, entry in form_fields.items():
        if name not in merged:
            merged[name] = dict(entry)
            continue
        a, b = parse_money(str(merged[name]["value"])), parse_money(str(entry["value"]))
        if a is not None and b is not None and abs(a - b) > 1.0 and re.search(r"(rent|units|payment|allowance)", name):
            note = (f"The form reader read {entry['value']} (p.{(entry.get('source') or {}).get('page')}) "
                    f"where the AI read {merged[name]['value']}. {VERIFY}")
            merged[name]["confidence"] = "low"
            merged[name]["check_note"] = f"{merged[name].get('check_note', '')} {note}".strip()
    return merged
