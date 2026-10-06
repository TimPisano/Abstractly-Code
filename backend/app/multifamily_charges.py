"""
Multifamily lease terms beyond base rent: unit number, pet / parking /
utility charges, the Section 8 rent split, and renewals or amendments
inside the same document.

Behind LEASE_MULTIFAMILY_FIELDS (default off). When on, both extraction
engines add these keys to a lease's fields, in the usual entry shape
plus a structured `details` dict the rest of the app can compute with:

    {"value": "<display string>", "source": {"page": N, "quote": "..."},
     "confidence": "high"|"medium"|"low", "details": {...}}

  unit_number            details: {}
  pet_charges            details: {monthly_rent, fee, deposit}
  parking_charges        details: {monthly_fee, space}
  utility_charges        details: {rubs, rubs_utilities, flat_fees, flat_monthly_total}
  section_8              details: {is_section_8, pha_name, contract_rent, tenant_rent,
                                   hap_amount, utility_allowance, hap_contract_start}
  lease_changes          details: {changes: [{kind, effective_date, new_rent, new_end_date, page}]}
  current_rent_amount    the rent after the latest in-document renewal/amendment
                         (the base rent when there is none)
  current_lease_end_date same idea, for the end date

Every figure is read from the text and quoted -- nothing is inferred.
Where the text states numbers that don't add up (tenant rent + HAP !=
contract rent), the entry says so and drops to medium confidence
rather than "fixing" either number.

Like concessions.py, this is pure text -> structure, shared by the regex
engine (on the whole document) and the AI engine (on the clauses the
model quoted), so both produce the same details for the same wording.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .normalize import parse_currency, parse_date

FLAG_ENV = "LEASE_MULTIFAMILY_FIELDS"
_TRUTHY = {"1", "true", "yes", "on"}

MF_FIELDS = [
    "unit_number",
    "pet_charges",
    "parking_charges",
    "utility_charges",
    "section_8",
    "lease_changes",
    "current_rent_amount",
    "current_lease_end_date",
]


def enabled() -> bool:
    return os.environ.get(FLAG_ENV, "").strip().lower() in _TRUTHY


# ----------------------------------------------------------------------
# Shared regex pieces (kept local so this module has no dependency on
# field_extractor's internals; same shapes as there).
# ----------------------------------------------------------------------

_MONTHS = (r"January|February|March|April|May|June|July|August|September|October|November|December|"
           r"Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sept\.?|Sep\.?|Oct\.?|Nov\.?|Dec\.?")
DATE = rf"((?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{2,4}})"
CUR = r"\$\s?([\d,]+(?:\.\d{2})?)"
PER_MONTH = r"(?:per\s+month|/\s*mo(?:nth)?\.?|monthly|a\s+month|each\s+month)"
NEAR = r"[^.$\n]{0,60}?"   # keyword ... amount, same sentence/line, no other amount between

Entry = Dict[str, Any]


def _join(pages: List[Dict[str, Any]]) -> Tuple[str, Callable[[int], int]]:
    parts, spans, off = [], [], 0
    for p in pages:
        t = p.get("text") or ""
        parts.append(t)
        spans.append((off, off + len(t), p["page"]))
        parts.append("\n")
        off += len(t) + 1
    text = "".join(parts)

    def page_at(pos: int) -> int:
        for a, b, pg in spans:
            if a <= pos < b:
                return pg
        return spans[-1][2] if spans else 1

    return text, page_at


def _quote(text: str, a: int, b: int, pad: int = 40) -> str:
    return re.sub(r"\s+", " ", text[max(0, a - pad):min(len(text), b + pad)]).strip()


def _num(digits: Optional[str]) -> Optional[float]:
    """The captured digits of CUR ("1,450.00", no "$") as a number."""
    try:
        return float(digits.replace(",", "")) if digits else None
    except ValueError:
        return None


def _money(x: Optional[float]) -> str:
    return f"${x:,.2f}"


def _not_found() -> Entry:
    return {"value": None, "source": None, "confidence": None}


class _Doc:
    """One document's text plus the helpers every parser below uses."""

    def __init__(self, pages: List[Dict[str, Any]]):
        self.pages = pages
        self.text, self.page_at = _join(pages)

    def first(self, patterns: List[str], flags: int = re.IGNORECASE,
              accept: Optional[Callable[["re.Match"], bool]] = None) -> Optional["re.Match"]:
        for pat in patterns:
            for m in re.finditer(pat, self.text, flags):
                if accept is None or accept(m):
                    return m
        return None

    def amount(self, patterns: List[str], **kw) -> Tuple[Optional[float], Optional["re.Match"]]:
        m = self.first(patterns, **kw)
        return (_num(m.group(1)), m) if m else (None, None)

    def source(self, matches: List[Optional["re.Match"]]) -> Optional[Dict[str, Any]]:
        ms = [m for m in matches if m is not None]
        if not ms:
            return None
        ms.sort(key=lambda m: m.start())
        quote = " ... ".join(_quote(self.text, m.start(), m.end()) for m in ms)
        return {"page": self.page_at(ms[0].start()), "quote": quote}


# ----------------------------------------------------------------------
# Unit number
# ----------------------------------------------------------------------

# "204", "3B", "14-C", "B-215", "A-12", "C-5", "11-B" -- or a lone letter
# ("Unit B"), allowed only right after an explicit unit label.
_UNIT_ID = r"((?:[A-Z]{1,2}-?)?\d{1,5}(?:-?[A-Z]{1,2})?(?![\w-])|[A-Z](?=[,.\s]|$))"
_UNIT_PATTERNS = [
    # Labels: "Unit: 3B", "Apartment No. 204", "Unit # 111", "Apt. 12"
    rf"(?m)^\s*(?:Apartment\s+Unit|Apartment|Apt\.?|Unit)\s*(?:No\.?|Number|#)?\s*[:#]?\s*{_UNIT_ID}",
    # Inside an address: "1250 Cedar Bend Lane, Apt. 204, Columbus"
    rf"\d+\s+[A-Za-z0-9 .'\-]+?,\s*(?:Apartment|Apt\.?|Unit|Suite|Ste\.?)\s*(?:No\.?|Number|#)?\s*#?\s*{_UNIT_ID}\b",
    # Comma-delimited unit inside a wrapped address line: "...Parkway, Apt. 412, Kansas City"
    rf",\s*(?:Apartment|Apt\.?|Unit|Suite|Ste\.?)\s*(?:No\.?|Number|#)?\s*#?\s*{_UNIT_ID}\s*,",
    rf"\b(?:Apartment|Apt\.?|Unit)\s*(?:No\.?|Number|#)\s*#?\s*{_UNIT_ID}",
    # "...Way, #204." / "Road, #11-B to"
    rf",\s*#\s*{_UNIT_ID}",
    # Any explicit unit label followed by an ID: "Unit 418, 1015 Mariner Walk", "Apartment Unit 14-C"
    rf"\b(?:Apartment\s+Unit|Apartment|Apt\.?|Unit)\s+{_UNIT_ID}",
]


def parse_unit_number(doc: _Doc) -> Entry:
    m = doc.first(_UNIT_PATTERNS, flags=0)
    if not m:
        m = doc.first(_UNIT_PATTERNS)
    if not m:
        return _not_found()
    return {"value": m.group(1), "source": doc.source([m]), "confidence": "high", "details": {}}


# ----------------------------------------------------------------------
# Pet charges
# ----------------------------------------------------------------------

_PET = r"(?:pet|animal)"


def parse_pet_charges(doc: _Doc) -> Entry:
    rent, m_rent = doc.amount([
        rf"{_PET}\s+rent{NEAR}{CUR}",
        rf"(?:additional\s+)?monthly\s+rent\s+of\s+{CUR}\s+for\s+the\s+{_PET}",
        rf"{CUR}\s*{PER_MONTH}\s+(?:in\s+)?{_PET}\s+rent",
        rf"monthly\s+{_PET}\s+fee{NEAR}{CUR}",
    ])
    fee, m_fee = doc.amount([
        rf"one[- ]time\s+(?:non-?refundable\s+)?{_PET}\s+fee{NEAR}{CUR}",
        rf"non-?refundable\s+{_PET}\s+fee{NEAR}{CUR}",
        rf"(?<!monthly\s){_PET}\s+fee(?!\s*{PER_MONTH}){NEAR}{CUR}(?!\s*{PER_MONTH})",
    ])
    deposit, m_dep = doc.amount([rf"(?:additional\s+)?{_PET}\s+(?:security\s+)?deposit{NEAR}{CUR}"])
    if not any((rent, fee, deposit)):
        return _not_found()
    parts = []
    if rent:
        parts.append(f"{_money(rent)}/mo pet rent")
    if fee:
        parts.append(f"{_money(fee)} pet fee (one-time)")
    if deposit:
        parts.append(f"{_money(deposit)} pet deposit")
    return {
        "value": "; ".join(parts),
        "source": doc.source([m_rent, m_fee, m_dep]),
        "confidence": "high",
        "details": {"monthly_rent": rent, "fee": fee, "deposit": deposit},
    }


# ----------------------------------------------------------------------
# Parking
# ----------------------------------------------------------------------

_PARK = r"(?:parking|garage|carport|covered\s+parking|reserved\s+parking|parking\s+space)"


def parse_parking_charges(doc: _Doc) -> Entry:
    fee, m = doc.amount([
        rf"(?:monthly\s+)?{_PARK}\s+(?:rental\s+)?(?:fee|rent|charge){NEAR}{CUR}",
        rf"{_PARK}{NEAR}{CUR}\s*{PER_MONTH}",
        rf"{CUR}\s*{PER_MONTH}\s+for\s+(?:the\s+|a\s+|one\s+)?(?:detached\s+|assigned\s+|reserved\s+|covered\s+)?{_PARK}",
    ])
    if not fee:
        return _not_found()
    space_m = doc.first([
        r"(?:assigned\s+space|space\s+(?:no\.?|number|#)|garage\s+(?:no\.?|number|#)?)[:\s]*([A-Z]{0,2}-?\d{1,4}[A-Z]?)\b",
        r"\bdetached\s+garage\s+([A-Z]{0,2}-?\d{1,4})\b",
    ])
    space = space_m.group(1) if space_m else None
    return {
        "value": f"{_money(fee)}/mo parking" + (f" (space {space})" if space else ""),
        "source": doc.source([m]),
        "confidence": "high",
        "details": {"monthly_fee": fee, "space": space},
    }


# ----------------------------------------------------------------------
# Utilities: RUBS / bill-back, and flat monthly fees
# ----------------------------------------------------------------------

_UTILITY_WORDS = [
    ("water", r"\bwater\b"),
    ("sewer", r"\b(?:sewer|wastewater)\b"),
    ("trash", r"\b(?:trash|garbage|refuse)\b"),
    ("gas", r"\bgas\b"),
    ("electric", r"\belectric(?:ity)?\b"),
    ("stormwater", r"\bstorm\s?water\b"),
]
_RUBS_CUE = re.compile(
    r"\bRUBS\b|ratio\s+utility\s+billing|bill(?:ed|s)?\s+back|allocat\w+\s+(?:formula|method|based)|"
    r"pro[- ]rata\s+(?:share|basis|portion)|based\s+on\s+(?:the\s+)?(?:number\s+of\s+occupants|square\s+footage|occupancy)",
    re.IGNORECASE,
)
_FLAT_SERVICE = (r"(?:valet\s+trash|trash(?:\s+removal)?|pest\s+control|cable(?:\s+and\s+internet)?(?:\s+package)?|"
                 r"internet|technology\s+package|water(?:\s+and\s+sewer)?|sewer|gas|electric(?:ity)?|"
                 r"stormwater|utility|utilities|package\s+locker)")


def _sentence_around(text: str, a: int, b: int) -> str:
    start = max(text.rfind(". ", 0, a), text.rfind("\n", 0, a)) + 1
    ends = [i for i in (text.find(". ", b), text.find("\n", b)) if i != -1]
    return text[start:min(ends) if ends else len(text)]


def parse_utility_charges(doc: _Doc) -> Entry:
    matches: List["re.Match"] = []
    rubs_utils: List[str] = []
    for m in _RUBS_CUE.finditer(doc.text):
        sentence = _sentence_around(doc.text, m.start(), m.end())
        found = [name for name, pat in _UTILITY_WORDS if re.search(pat, sentence, re.IGNORECASE)]
        # A bill-back cue with no utility named in its sentence (e.g. "pro
        # rata share of operating expenses") isn't a utility bill-back.
        if found:
            matches.append(m)
            rubs_utils += [u for u in found if u not in rubs_utils]

    flat: Dict[str, float] = {}
    for m in re.finditer(
        rf"(?m)^\s*({_FLAT_SERVICE})(?:\s+fee)?\s*[:\-]\s*{CUR}\s*{PER_MONTH}|"
        rf"flat\s+(?:monthly\s+)?(?:fee|charge|rate)\s+of\s+{CUR}\s*(?:{PER_MONTH}\s+)?for\s+({_FLAT_SERVICE})|"
        rf"({_FLAT_SERVICE})\s+(?:fee|charge)\s+of\s+{CUR}\s*{PER_MONTH}",
        doc.text, re.IGNORECASE,
    ):
        g = m.groups()
        name, amt = (g[0], g[1]) if g[0] else ((g[3], g[2]) if g[2] else (g[4], g[5]))
        amount = _num(amt)
        if amount:
            flat[re.sub(r"\s+", " ", name).strip().title()] = amount
            matches.append(m)

    if not rubs_utils and not flat:
        return _not_found()
    parts = []
    if rubs_utils:
        parts.append("RUBS bill-back: " + ", ".join(rubs_utils))
    for name, amt in flat.items():
        parts.append(f"{name} {_money(amt)}/mo")
    return {
        "value": "; ".join(parts),
        "source": doc.source(matches[:4]),
        # A RUBS clause has no fixed figure, so it can't be priced from the
        # lease alone -- still high: the text states it explicitly.
        "confidence": "high",
        "details": {
            "rubs": bool(rubs_utils),
            "rubs_utilities": rubs_utils,
            "flat_fees": flat,
            "flat_monthly_total": round(sum(flat.values()), 2) if flat else None,
        },
    }


# ----------------------------------------------------------------------
# Section 8
# ----------------------------------------------------------------------

_S8_CUE = re.compile(
    r"\bSection\s+8\b|Housing\s+Choice\s+Voucher|\bHAP\s+contract|Housing\s+Assistance\s+Payments?\s+Contract|"
    r"Tenancy\s+Addendum|HUD-?\s?52641|\bPBRA\b|project[- ]based\s+(?:rental\s+)?assistance",
    re.IGNORECASE,
)
_PHA_RE = re.compile(
    r"((?:[A-Z][A-Za-z.'&\-]+\s+){1,6}(?:Housing\s+(?:Authority|Commission|Agency|Department)|"
    r"Public\s+Housing\s+Agency|Redevelopment\s+(?:and\s+Housing\s+)?(?:Authority|Agency)))"
)


def parse_section_8(doc: _Doc, base_rent: Optional[float] = None) -> Entry:
    cue = _S8_CUE.search(doc.text)
    if not cue:
        return _not_found()
    pha_m = None
    pha = None
    for m in _PHA_RE.finditer(doc.text):
        name = re.sub(r"^(?:The|with|between|and|by)\s+", "", m.group(1).strip())
        if name.lower() not in ("public housing agency",):
            pha, pha_m = re.sub(r"\s+", " ", name), m
            break
    contract, m_c = doc.amount([
        rf"(?:contract\s+rent|(?:initial\s+)?rent\s+to\s+(?:the\s+)?owner|gross\s+rent\s+to\s+owner)(?:\s+(?:is|shall\s+be))?[:\s]+{CUR}",
    ])
    tenant, m_t = doc.amount([
        rf"(?:tenant\s+rent|tenant'?s?\s+(?:portion|share)(?:\s+of\s+(?:the\s+)?rent)?|family\s+(?:share|portion|rent\s+to\s+owner)|"
        rf"resident\s+(?:portion|share))(?:\s+(?:is|shall\s+be))?[:\s]+{CUR}",
    ])
    hap, m_h = doc.amount([
        rf"housing\s+assistance\s+payment(?!s?\s+contract)(?:\s+(?:is|shall\s+be))?{NEAR}{CUR}",
        rf"\b(?:HAP|PHA)\s+(?:portion|payment|amount|share)(?:\s+(?:is|shall\s+be))?[:\s]+{CUR}",
    ])
    ua, m_ua = doc.amount([rf"utility\s+allowance(?:\s+(?:is|of))?[:\s]+{CUR}"])
    start_m = doc.first([rf"HAP\s+contract\s+term\s+begins\s+on\s+{DATE}"])
    details = {
        "is_section_8": True,
        "pha_name": pha,
        "contract_rent": contract if contract is not None else base_rent,
        "tenant_rent": tenant,
        "hap_amount": hap,
        "utility_allowance": ua,
        "hap_contract_start": start_m.group(1) if start_m else None,
    }
    confidence = "high"
    note = None
    c = details["contract_rent"]
    if c is not None and tenant is not None and hap is not None and abs((tenant + hap) - c) > 1.0:
        confidence = "medium"
        note = (f"Tenant rent {_money(tenant)} + HAP {_money(hap)} = {_money(tenant + hap)}, "
                f"not the contract rent {_money(c)}. Check which figure is current.")
    bits = ["Section 8 (HCV)"]
    if pha:
        bits.append(f"PHA: {pha}")
    if c is not None:
        split = " = ".join(filter(None, [
            f"contract rent {_money(c)}",
            " + ".join(filter(None, [
                f"tenant {_money(tenant)}" if tenant is not None else None,
                f"HAP {_money(hap)}" if hap is not None else None,
            ])) or None,
        ]))
        bits.append(split)
    if ua is not None:
        bits.append(f"utility allowance {_money(ua)}")
    entry: Entry = {
        "value": "; ".join(bits),
        "source": doc.source([cue, pha_m, m_c, m_t, m_h, m_ua]),
        "confidence": confidence,
        "details": details,
    }
    if note:
        entry["validation_note"] = note
    return entry


# ----------------------------------------------------------------------
# Renewals / amendments inside the document
# ----------------------------------------------------------------------

_CHANGE_TITLE = re.compile(
    r"\b(?:(?P<renewal>renewal|extension)\b|(?P<amend>amendment|lease\s+modification|notice\s+of\s+rent\s+(?:change|increase)))",
    re.IGNORECASE,
)


def _change_docs(pages: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Group pages after the first into (kind, pages) per renewal/amendment document."""
    out: List[Tuple[str, List[Dict[str, Any]]]] = []
    current: Optional[Tuple[str, List[Dict[str, Any]]]] = None
    for i, p in enumerate(pages):
        head = re.sub(r"\s+", " ", (p.get("text") or "").strip())[:160]
        m = _CHANGE_TITLE.search(head) if i > 0 else None
        # Only a page whose OPENING names it (the document title), and not
        # a lease page that merely mentions "renewal options".
        if m and m.start() < 60:
            current = ("renewal" if m.group("renewal") else "amendment", [p])
            out.append(current)
        elif current is not None and not _is_other_attachment(head):
            current[1].append(p)
        else:
            current = None
    return out


def _is_other_attachment(head: str) -> bool:
    return bool(re.search(r"\b(?:addendum|exhibit|rider|hap\s+contract|housing\s+assistance)\b", head[:80], re.IGNORECASE))


def parse_lease_changes(pages: List[Dict[str, Any]]) -> Entry:
    changes = []
    sources = []
    for kind, doc_pages in _change_docs(pages):
        d = _Doc(doc_pages)
        eff = d.first([rf"[Ee]ffective\s+(?:as\s+of\s+)?(?:on\s+)?{DATE}", rf"term\s+beginning\s+(?:on\s+)?{DATE}",
                       rf"commenc\w+\s+(?:on\s+)?{DATE}"])
        rent, m_rent = d.amount([
            rf"(?:monthly\s+)?rent\s+(?:shall\s+be|will\s+be|is\s+(?:changed|increased|decreased|reduced|adjusted)\s+to|"
            rf"is|of)[:\s]*{CUR}",
            rf"new\s+(?:monthly\s+)?rent[:\s]+{CUR}",
            rf"(?:monthly\s+)?rent[:\s]+{CUR}",
        ], accept=lambda m: not re.search(r"\b(?:pet|parking|garage|tenant\s+rent)\b",
                                          d.text[max(0, m.start() - 25):m.start()], re.IGNORECASE))
        end = d.first([rf"and\s+ending\s+(?:on\s+)?{DATE}", rf"expiration\s+date[^.$]{{0,40}}?(?:extended\s+to|is|shall\s+be)\s+{DATE}",
                       rf"(?:new\s+)?(?:lease\s+)?end(?:ing)?\s+date[:\s]+{DATE}", rf"\bthrough\s+{DATE}",
                       rf"\bends?\s+(?:on\s+)?{DATE}"])
        if rent is None and end is None:
            continue
        changes.append({
            "kind": kind,
            "effective_date": eff.group(1) if eff else None,
            "new_rent": rent,
            "new_end_date": end.group(1) if end else None,
            "page": doc_pages[0]["page"],
        })
        sources.append(d.source([eff, m_rent, end]))
    if not changes:
        return _not_found()
    value = "; ".join(
        f"{c['kind'].capitalize()}" + (f" effective {c['effective_date']}" if c["effective_date"] else "")
        + (f": rent {_money(c['new_rent'])}" if c["new_rent"] is not None else "")
        + (f", ends {c['new_end_date']}" if c["new_end_date"] else "")
        for c in changes
    )
    return {
        "value": value,
        "source": {"page": sources[0]["page"], "quote": " ... ".join(s["quote"] for s in sources if s)},
        "confidence": "high",
        "details": {"changes": changes},
    }


def _current(base: Optional[Entry], changes_entry: Entry, key: str, display) -> Entry:
    """The latest in-document value for `key`, else the base lease's own entry."""
    for c in reversed((changes_entry.get("details") or {}).get("changes") or []):
        if c.get(key) is not None:
            return {
                "value": display(c[key]),
                "source": {"page": c["page"], "quote": changes_entry["source"]["quote"]},
                "confidence": "high",
                "details": {"from": c["kind"], "effective_date": c.get("effective_date")},
            }
    if base and base.get("value") is not None:
        out = {k: base.get(k) for k in ("value", "source", "confidence")}
        out["details"] = {"from": "lease"}
        return out
    return _not_found()


def _display_date(v: str) -> str:
    d = parse_date(v)
    return f"{d.strftime('%B')} {d.day}, {d.year}" if d else v


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def extract(pages: List[Dict[str, Any]], base_fields: Dict[str, Entry]) -> Dict[str, Entry]:
    """All multifamily fields for one lease's pages (regex engine)."""
    doc = _Doc(pages)
    base_rent = parse_currency((base_fields.get("rent_amount") or {}).get("value"))
    changes = parse_lease_changes(pages)
    return {
        "unit_number": parse_unit_number(doc),
        "pet_charges": parse_pet_charges(doc),
        "parking_charges": parse_parking_charges(doc),
        "utility_charges": parse_utility_charges(doc),
        "section_8": parse_section_8(doc, base_rent),
        "lease_changes": changes,
        "current_rent_amount": _current(base_fields.get("rent_amount"), changes, "new_rent", _money),
        "current_lease_end_date": _current(base_fields.get("lease_end_date"), changes, "new_end_date", _display_date),
    }
