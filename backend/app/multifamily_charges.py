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
NEAR = r"[^.$]{0,60}?"   # keyword ... amount: same sentence (line wraps allowed), no other amount between
DATE_NC = "(?:" + DATE[1:]
RANGE_SEP = r"\s*(?:to|through|thru|until|[-\u2013\u2014])\s*"

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

    def without_changes(self) -> "_Doc":
        """
        The same pages minus renewal / amendment / rent-change documents,
        so the lease's own terms (Section 8 split, charges) aren't replaced
        by a later notice's "New tenant rent". Those changes are reported
        separately in lease_changes.
        """
        change_pages = {p["page"] for _kind, ps in _change_docs(self.pages) for p in ps}
        kept = [p for p in self.pages if p["page"] not in change_pages]
        return _Doc(kept) if kept and len(kept) < len(self.pages) else self

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
        # Merge clauses whose padded quote windows overlap, so two charges
        # in adjacent sentences are quoted once, not twice.
        pad = 40
        spans: List[List[int]] = []
        for m in ms:
            a, b = max(0, m.start() - pad), min(len(self.text), m.end() + pad)
            if spans and a <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], b)
            else:
                spans.append([a, b])
        quote = " ... ".join(re.sub(r"\s+", " ", self.text[a:b]).strip() for a, b in spans)
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
    rf"\d+\s+[A-Za-z0-9 .'\-]+?,\s*(?:Apartment|Apt\.?|Unit)\s*(?:No\.?|Number|#)?\s*#?\s*{_UNIT_ID}\b",
    # Comma-delimited unit inside a wrapped address line: "...Parkway, Apt. 412, Kansas City"
    rf",\s*(?:Apartment|Apt\.?|Unit|No\.)\s*(?:No\.?|Number|#)?\s*#?\s*{_UNIT_ID}\s*,",
    rf"\b(?:Apartment|Apt\.?|Unit)\s*(?:No\.?|Number|#)\s*#?\s*{_UNIT_ID}",
    # "...Way, #204." / "Road, #11-B to"
    rf",\s*#\s*{_UNIT_ID}",
    # Any explicit unit label followed by an ID: "Unit 418, 1015 Mariner Walk", "Apartment Unit 14-C"
    rf"\b(?:Apartment\s+Unit|Apartment|Apt\.?|Unit|Loft|Townhome|Villa)\s+{_UNIT_ID}",
    # A "Suite" only last: in an apartment lease it's usually the management
    # office's address ("c/o ... 400 Commerce Way, Suite 120").
    rf"(?:,|\bat)\s*(?:Suite|Ste\.?)\s*#?\s*{_UNIT_ID}(?=\s*[,(.]|\s*$)",
]
# Context that makes a "Suite" an office, not the apartment.
_OFFICE_CONTEXT = re.compile(r"\bc/o\b|management|notices?\b|office|remit|payments?\s+to|mail", re.IGNORECASE)


def parse_unit_number(doc: _Doc) -> Entry:
    def not_an_office(m: "re.Match") -> bool:
        if not re.search(r"\b(?:Suite|Ste)\b", m.group(0), re.IGNORECASE):
            return True
        return not _OFFICE_CONTEXT.search(doc.text[max(0, m.start() - 120):m.start()])

    m = doc.first(_UNIT_PATTERNS, flags=0, accept=not_an_office)
    if not m:
        m = doc.first(_UNIT_PATTERNS, accept=not_an_office)
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
        # "an additional $50.00 is added to the monthly rent while the animals reside"
        rf"additional\s+{CUR}\s+(?:is\s+)?(?:added\s+to\s+(?:the\s+)?monthly\s+rent|per\s+month)[^.]{{0,60}}?\b{_PET}",
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

_PARK = r"(?:parking|garage|carport|covered\s+parking|reserved\s+parking|parking\s+space|(?:reserved|covered|assigned)(?:\s+covered)?\s+space)"


def parse_parking_charges(doc: _Doc) -> Entry:
    fee, m = doc.amount([
        rf"(?:monthly\s+)?{_PARK}\s+(?:rental\s+)?(?:fee|rent|charge){NEAR}{CUR}",
        rf"{_PARK}{NEAR}{CUR}\s*{PER_MONTH}",
        rf"{CUR}\s*{PER_MONTH}\s+for\s+(?:the\s+|a\s+|one\s+)?(?:detached\s+|assigned\s+|reserved\s+|covered\s+)?{_PARK}",
        # "The monthly fee for the space is $60.00." (after "assigned covered space #44")
        rf"(?:monthly\s+)?(?:fee|charge|rent)\s+for\s+the\s+(?:parking\s+|garage\s+)?(?:space|stall|garage|carport)(?:\s+is)?[:\s]+{CUR}",
    ])
    if not fee:
        return _not_found()
    space_m = doc.first([
        r"(?:assigned\s+space|space\s+(?:no\.?|number|#)|garage\s+(?:no\.?|number|#)?)[:\s]*([A-Z]{0,2}-?\d{1,4}[A-Z]?)\b",
        r"\bdetached\s+garage\s+([A-Z]{0,2}-?\d{1,4})\b",
        r"\b(?:stall|space)\s*#?\s*([A-Z]{0,2}-?\d{1,4})\b",
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
    r"pro[- ]rata\s+(?:share|basis|portion)|based\s+on\s+(?:the\s+)?(?:number\s+of\s+occupants|square\s+footage|occupancy)|"
    r"ratio\s+billing|\ballocates?\b|\ballocation\b|not\s+separately\s+metered|sub-?meter(?:ed|ing|s)?\b|"
    r"share\s+of\s+the\s+(?:community|property|building)'?s?",
    re.IGNORECASE,
)
_FLAT_SERVICE = (r"(?:valet[\s-]+trash|trash[\s-]+valet|trash(?:[\s-]+(?:removal|service))?|pest[\s-]+control|"
                 r"cable(?:\s+and\s+internet)?(?:\s+package)?|internet|technology\s+package|water(?:\s+and\s+sewer)?|"
                 r"sewer|gas|electric(?:ity)?|stormwater|utility|utilities|package[\s-]+locker)")


def _sentence_around(text: str, a: int, b: int) -> str:
    # Sentence ends at ". " only -- a PDF line wrap is not a sentence
    # break ("...the community's water, sewer, stormwater and trash
    # expenses will be determined\nby square footage ratio billing").
    # Capped so a table with no periods can't become one huge "sentence".
    start = max(text.rfind(". ", max(0, a - 300), a) + 1, a - 300, 0)
    end = text.find(". ", b)
    end = min(end if end != -1 else len(text), b + 300)
    return text[start:end]


def _rubs_clause(text: str, a: int, b: int) -> str:
    """
    The sentence around a bill-back cue, cut at any dollar amount on either
    side: in a charges table ("Trash service | $15.00 | Pest control | $5.00 |
    Water / Sewer / Stormwater - RUBS estimate | $45.00") only the cue's own
    row names the RUBS-billed utilities -- trash there is a flat fee.
    """
    sentence = _sentence_around(text, a, b)
    start = max(text.rfind(". ", max(0, a - 300), a) + 1, a - 300, 0)
    offset_a, offset_b = a - start, b - start
    before = re.split(r"\$\s?[\d,]+(?:\.\d{2})?", sentence[:offset_a])[-1]
    after = re.split(r"\$\s?[\d,]+(?:\.\d{2})?", sentence[offset_b:])[0]
    return before + sentence[offset_a:offset_b] + after


def parse_utility_charges(doc: _Doc) -> Entry:
    matches: List["re.Match"] = []
    rubs_utils: List[str] = []
    for m in _RUBS_CUE.finditer(doc.text):
        sentence = _rubs_clause(doc.text, m.start(), m.end())
        found = [name for name, pat in _UTILITY_WORDS if re.search(pat, sentence, re.IGNORECASE)]
        # A bill-back cue with no utility named in its sentence (e.g. "pro
        # rata share of operating expenses") isn't a utility bill-back.
        if found:
            matches.append(m)
            rubs_utils += [u for u in found if u not in rubs_utils]

    flat: Dict[str, float] = {}
    # Lists and tables of fixed services: "Flat monthly services: valet trash
    # collection $25.00; pest control $5.00", "fixed monthly charges: pest
    # control, $3.00", a "Monthly Charges" table row "Valet Trash\n$28.00".
    # Counted only when "monthly"/"per month" is stated for them.
    for m in re.finditer(
        rf"({_FLAT_SERVICE})(?:\s+(?:collection|service|services|pickup|fee|charge))?(?:\s+of)?\s*[,:\-|]?\s*\n?\s*{CUR}(\s*{PER_MONTH})?|"
        # "Valet trash pickup is mandatory for a flat fee of $28.00",
        # "Trash valet service is a flat $12.00 per month"
        rf"({_FLAT_SERVICE})[^.$]{{0,50}}?\bflat\s+(?:monthly\s+)?(?:fee\s+|charge\s+|rate\s+)?(?:of\s+)?{CUR}()",
        doc.text, re.IGNORECASE,
    ):
        context = doc.text[max(0, m.start() - 200):m.end() + 20]
        flat_wording = m.group(4) is not None
        if m.group(3) or flat_wording or re.search(
                r"\bmonthly\b|per\s+month|\brecurring\b|billed\s+with\s+(?:the\s+)?rent|each\s+month", context, re.IGNORECASE):
            amount = _num(m.group(2) if m.group(1) else m.group(5))
            name = re.sub(r"[\s-]+", " ", m.group(1) or m.group(4)).strip().title()
            if amount and name not in flat:
                flat[name] = amount
                matches.append(m)
    for m in re.finditer(
        rf"(?m)^\s*({_FLAT_SERVICE})(?:\s+fee)?\s*[:\-]\s*{CUR}\s*{PER_MONTH}|"
        rf"flat\s+(?:monthly\s+)?(?:fee|charge|rate)\s+of\s+{CUR}\s*(?:{PER_MONTH}\s+)?for\s+({_FLAT_SERVICE})|"
        rf"({_FLAT_SERVICE})\s+(?:fee|charge)\s+of\s+{CUR}\s*{PER_MONTH}",
        doc.text, re.IGNORECASE,
    ):
        g = m.groups()
        name, amt = (g[0], g[1]) if g[0] else ((g[3], g[2]) if g[2] else (g[4], g[5]))
        amount = _num(amt)
        name = re.sub(r"\s+", " ", name).strip().title()
        if amount and name not in flat:
            flat[name] = amount
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
    r"Tenancy\s+Addendum|HUD-?\s?52641|\bPBRA\b|project[- ]based\s+(?:rental\s+)?assistance|"
    r"\bvoucher\b|Housing\s+Authority|housing\s+assistance\s+payment|Total\s+Tenant\s+Payment|"
    r"Contract\s+Administrator|subsidized\s+program",
    re.IGNORECASE,
)
_PHA_RE = re.compile(
    r"((?:[A-Z][A-Za-z.'&\-]+\s+){1,6}(?:Housing\s+(?:Authority|Commission|Agency|Department)|"
    r"Public\s+Housing\s+Agency|Redevelopment\s+(?:and\s+Housing\s+)?(?:Authority|Agency)))"
)


def parse_section_8(doc: _Doc, base_rent: Optional[float] = None, require_cue: bool = True) -> Entry:
    cue = _S8_CUE.search(doc.text)
    if not cue and require_cue:
        return _not_found()
    doc = doc.without_changes()
    pha_m = None
    pha = None
    # A specific authority name beats the generic phrase "... Public Housing
    # Agency" that HUD forms use as a label ("Tenant-Based Assistance Public
    # Housing Agency: Greater Linden County Housing Authority").
    candidates = sorted(_PHA_RE.finditer(doc.text),
                        key=lambda m: bool(re.search(r"Public\s+Housing\s+Agency$", m.group(1))))
    for m in candidates:
        raw = m.group(1).strip()
        # A name may wrap ("...HAP contract with Granite\nValley Public Housing
        # Agency"), but a whole line of its own before the wrap is a label
        # ("Contract Administrator\nCalloway Valley Housing Authority").
        line_start = doc.text.rfind("\n", 0, m.start()) + 1
        if "\n" in raw and not doc.text[line_start:m.start()].strip():
            raw = raw.split("\n", 1)[1]
        name = re.sub(r"^(?:The|with|between|and|by)\s+", "", raw.strip())
        if name.lower() not in ("public housing agency",):
            pha, pha_m = re.sub(r"\s+", " ", name), m
            break
    contract, m_c = doc.amount([
        rf"(?:contract\s+rent(?:\s+to\s+owner)?|(?:initial\s+)?rent\s+to\s+(?:the\s+)?owner|gross\s+rent\s+to\s+owner)(?:\s+(?:is|shall\s+be))?[:\s]+{CUR}",
        rf"contract\s+rent{NEAR}{CUR}",
    ])
    tenant, m_t = doc.amount([
        rf"(?:tenant\s+rent|tenant'?s?\s+(?:portion|share)(?:\s+of\s+(?:the\s+)?rent)?|family\s+(?:share|portion|rent\s+to\s+owner)|"
        rf"resident\s+(?:portion|share))(?:\s+to\s+owner)?(?:\s+(?:is|shall\s+be))?[:\s]+{CUR}",
        rf"total\s+tenant\s+payment(?:\s+(?:is|of))?[:\s]+{CUR}",
        rf"family\s*(?:\(\s*tenant\s*\)\s*)?(?:share|portion)(?:\s+of\s+rent)?[:\s]+{CUR}",
        # "...of which the PHA pays $1,050.00 and Resident pays $350.00"
        rf"\b(?:tenant|resident|family)\s+(?:pays|will\s+pay|shall\s+pay)\s+{CUR}",
    ])
    hap, m_h = doc.amount([
        # "the Housing Authority pays $880.00 as the housing assistance payment
        # and the tenant pays $300.00" -- the payer-first form goes first, or
        # the phrase-first pattern below would reach on to the tenant's $300.
        rf"\b(?:PHA|Housing\s+Authority|Contract\s+Administrator|agency)\s+(?:pays|will\s+pay)\s+{CUR}",
        rf"\bHAP\s+paid\s+by[^$]{{0,80}}?{CUR}",
        rf"(?:housing\s+)?assistance\s+payment\s*[:\-]?\s*\n\s*{CUR}",
        # "The assistance payment made by the Contract Administrator on behalf
        # of the Tenant is $853.00" -- a longer reach than NEAR.
        rf"(?:housing\s+)?assistance\s+payment(?!s?\s+contract)(?:\s+(?:is|shall\s+be))?[^.$]{{0,90}}?{CUR}",
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
    r"\b(?:(?P<renewal>renewal|extension)\b|(?P<amend>amendment|lease\s+modification|notice\s+of\s+rent\s+(?:change|increase)|"
    r"rent\s+(?:change|increase|adjustment)\s+notice|notice\s+of\s+(?:change|adjustment)|recertification|"
    r"transfer\s+to\s+(?:unit|apartment|apt)|addition\s+of\s+(?:occupant|resident|roommate)))",
    re.IGNORECASE,
)


def _change_docs(pages: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Group pages after the first into (kind, pages) per renewal/amendment document."""
    out: List[Tuple[str, List[Dict[str, Any]]]] = []
    current: Optional[Tuple[str, List[Dict[str, Any]]]] = None
    for i, p in enumerate(pages):
        head = re.sub(r"\s+", " ", (p.get("text") or "").strip())[:160]
        m = _CHANGE_TITLE.search(head) if i > 0 else None
        # A renewal offer or rent notice written as a LETTER ("March 20, 2026
        # Dear Mr. Rutherford, Your lease ... If you renew, your new monthly
        # rent will be ...") has no title -- its subject is in the body.
        letter = i > 0 and re.search(r"\bdear\b", head[:80], re.IGNORECASE)
        if letter and not (m and m.start() < 60):
            body = re.sub(r"\s+", " ", (p.get("text") or ""))[:400]
            if re.search(r"\brenew", body, re.IGNORECASE):
                m = re.search(r"(?P<renewal>renew)(?P<amend>)?", body, re.IGNORECASE)
            elif re.search(r"\brent\b.{0,80}\b(?:change|increase|adjust)", body, re.IGNORECASE):
                m = re.search(r"(?P<renewal>(?!))?(?P<amend>rent)", body, re.IGNORECASE)
            if m:
                current = ("renewal" if m.group("renewal") else "amendment", [p])
                out.append(current)
                continue
        # Only a page whose OPENING names it (the document title), and not
        # a lease page that merely mentions "renewal options" -- or opens with
        # a numbered lease clause ("12. RENEWAL. Resident may renew ...").
        numbered_clause = re.match(r"\s*(?:\d{1,3}|[A-Z])[.)]\s", head)
        if m and m.start() < 60 and not numbered_clause:
            current = ("renewal" if m.group("renewal") else "amendment", [p])
            out.append(current)
        elif current is not None and not _is_other_attachment(head):
            current[1].append(p)
        else:
            current = None
    return out


def _is_other_attachment(head: str) -> bool:
    return bool(re.search(r"\b(?:addendum|exhibit|rider|hap\s+contract|housing\s+assistance|dear)\b", head[:80], re.IGNORECASE))


def parse_lease_changes(pages: List[Dict[str, Any]]) -> Entry:
    changes = []
    sources = []
    for kind, doc_pages in _change_docs(pages):
        d = _Doc(doc_pages)
        eff = d.first([rf"[Ee]ffective\s+(?:as\s+of\s+)?(?:on\s+)?{DATE}", rf"term\s+beginning\s+(?:on\s+)?{DATE}",
                       rf"commenc\w+\s+(?:on\s+)?{DATE}", rf"\bfrom\s+{DATE}(?={RANGE_SEP}{DATE_NC})"])
        rent, m_rent = d.amount([
            # Section 8 notices: the contract rent (total), not "New tenant rent".
            rf"contract\s+rent(?:\s+to\s+owner)?{NEAR}{CUR}",
            rf"(?:monthly\s+)?rent\s+(?:shall\s+be|will\s+be|is\s+(?:changed|increased|decreased|reduced|adjusted)\s+to|"
            rf"is|of)[:\s]*{CUR}",
            rf"new\s+(?:monthly\s+)?rent[:\s]+{CUR}",
            rf"new\s+(?:monthly\s+)?rent\s+(?:will\s+be|is|of)\s+{CUR}",
            rf"(?:monthly\s+)?rent[:\s]+{CUR}",
        ], accept=lambda m: not re.search(r"\b(?:pet|parking|garage|tenant\s+rent|tenant\s+portion)\b",
                                          d.text[max(0, m.start() - 25):m.end()], re.IGNORECASE))
        tenant_rent, m_tr = d.amount([
            rf"new\s+tenant\s+(?:rent|portion|share)[:\s]+{CUR}",
            rf"your\s+(?:portion|share)\s+of\s+(?:the\s+)?rent\s+will\s+be\s+{CUR}",
            rf"tenant\s+rent\s+(?:is|will\s+be|becomes)\s+{CUR}",
            rf"total\s+tenant\s+payment\s*(?:\(\s*new\s*\))?[:\s|]+{CUR}",
        ])
        hap, m_hap = d.amount([
            rf"new\s+(?:housing\s+)?assistance\s+payment[:\s]+{CUR}",
            rf"our\s+payment\s+to\s+(?:your\s+)?(?:landlord|owner)\s+will\s+be\s+{CUR}",
            rf"\b(?:HAP|assistance)\s+payment\s+(?:is|will\s+be|becomes)\s+{CUR}",
            rf"assistance\s+payment\s*(?:\(\s*new\s*\))?[:\s|]+{CUR}",
        ])
        end = d.first([rf"{DATE_NC}{RANGE_SEP}{DATE}", rf"and\s+ending\s+(?:on\s+)?{DATE}", rf"expiration\s+date[^.$]{{0,40}}?(?:extended\s+to|is|shall\s+be)\s+{DATE}",
                       rf"(?:new\s+)?(?:lease\s+)?end(?:ing)?\s+date[:\s]+{DATE}", rf"\bthrough\s+{DATE}",
                       rf"\bends?\s+(?:on\s+)?{DATE}"])
        # A change document with no new figures (a roommate added, "the
        # contract rent does not change") is still a change to the lease --
        # recorded with no figures rather than dropped. Only when its title
        # says so explicitly, though: a page merely headed "Renewal" with no
        # new term or rent isn't evidence of a change.
        no_figures = rent is None and end is None and tenant_rent is None and hap is None
        title = re.sub(r"\s+", " ", (doc_pages[0].get("text") or ""))[:120]
        if no_figures and not re.search(
            r"amendment|modification|addition\s+of|transfer|recertification|notice\s+of\s+change|rent\s+change",
            title, re.IGNORECASE,
        ):
            continue
        changes.append({
            "kind": kind,
            "effective_date": eff.group(1) if eff else None,
            "new_rent": rent,
            "new_end_date": end.group(1) if end else None,
            "new_tenant_rent": tenant_rent,
            "new_hap_amount": hap,
            "page": doc_pages[0]["page"],
        })
        # No figures to quote (e.g. "add Sloane Whitlock as a resident") --
        # cite the change document's own opening instead.
        sources.append(d.source([eff, m_rent, end, m_tr, m_hap]) or {
            "page": doc_pages[0]["page"],
            "quote": re.sub(r"\s+", " ", (doc_pages[0].get("text") or "").strip())[:200],
        })
    if not changes:
        return _not_found()
    value = "; ".join(
        f"{c['kind'].capitalize()}" + (f" effective {c['effective_date']}" if c["effective_date"] else "")
        + ("" if any(c[k] is not None for k in ("new_rent", "new_end_date", "new_tenant_rent", "new_hap_amount"))
           else " (no rent or term change stated)")
        + (f": rent {_money(c['new_rent'])}" if c["new_rent"] is not None else "")
        + (f", ends {c['new_end_date']}" if c["new_end_date"] else "")
        + (f", tenant rent {_money(c['new_tenant_rent'])}" if c["new_tenant_rent"] is not None else "")
        + (f", HAP {_money(c['new_hap_amount'])}" if c["new_hap_amount"] is not None else "")
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
                "source": {"page": c.get("page"), "quote": (changes_entry.get("source") or {}).get("quote")},
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


# ----------------------------------------------------------------------
# AI engine: the model finds and quotes; this module computes the numbers
# ----------------------------------------------------------------------

_UNIT_PREFIX = re.compile(r"^(?:apartment|apt\.?|unit|suite|ste\.?|no\.?|number|#)\s*", re.IGNORECASE)
_QUOTE_PARSERS = {
    "pet_charges": parse_pet_charges,
    "parking_charges": parse_parking_charges,
    "utility_charges": parse_utility_charges,
}
AI_FIELDS = ("unit_number", "pet_charges", "parking_charges", "utility_charges", "section_8", "lease_changes")


def _quote_doc(entry: Entry) -> _Doc:
    """The model's verbatim quote as a one-page document (" ... "-joined clauses on their own lines)."""
    quote = entry.get("source_text") or (entry.get("source") or {}).get("quote") or ""
    clauses = [c.strip() for c in re.split(r"\s*(?:\.\.\.|\u2026)\s*", quote) if c.strip()]
    return _Doc([{"page": (entry.get("source") or {}).get("page") or 1, "text": "\n".join(clauses)}])


def attach_ai_details(fields: Dict[str, Entry], pages: List[Dict[str, Any]]) -> Dict[str, Entry]:
    """
    Give the AI engine's multifamily entries the same `details` the regex
    engine produces -- parsed from the model's verbatim quote, never from
    the model's own arithmetic -- and derive current_rent_amount /
    current_lease_end_date. A field the model reported as not found stays
    not found (the regex engine doesn't second-guess it). When the quote
    alone doesn't parse, the full document is parsed instead; when that
    fails too, the value is kept but marked low confidence.
    """
    out: Dict[str, Entry] = {}
    full: Optional[Dict[str, Entry]] = None

    def from_document(name: str) -> Optional[Dict[str, Any]]:
        nonlocal full
        if full is None:
            full = extract(pages, fields)
        return full[name].get("details")

    base_rent = parse_currency((fields.get("rent_amount") or {}).get("value"))
    for name in AI_FIELDS:
        entry = dict(fields.get(name) or _not_found())
        if entry.get("value") is None:
            out[name] = entry
            continue
        details: Optional[Dict[str, Any]] = None
        if name == "unit_number":
            entry["value"] = _UNIT_PREFIX.sub("", entry["value"]).strip() or entry["value"]
            details = {}
        elif name in _QUOTE_PARSERS:
            details = _QUOTE_PARSERS[name](_quote_doc(entry)).get("details")
        elif name == "section_8":
            # The quote may be just the figures ("Rent to owner: $1,450.00 ...
            # Tenant Rent: $312.00") with no "Section 8" wording in it -- the
            # model already judged the tenancy subsidized.
            details = parse_section_8(_quote_doc(entry), base_rent, require_cue=False).get("details")
        if not details and name != "unit_number":
            # lease_changes always lands here: it needs page structure
            # (which document a sentence belongs to), not just the quote.
            details = from_document(name)
        if details is None:
            entry["details"] = {}
            entry["confidence"] = "low"
            entry["validation_note"] = ("Found by the model, but its figures couldn't be read automatically -- "
                                        "verify against the document.")
        else:
            entry["details"] = details
        out[name] = entry

    changes = out["lease_changes"] if out["lease_changes"].get("details") else _not_found()
    out["current_rent_amount"] = _current(fields.get("rent_amount"), changes, "new_rent", _money)
    out["current_lease_end_date"] = _current(fields.get("lease_end_date"), changes, "new_end_date", _display_date)
    return out
