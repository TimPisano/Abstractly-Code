"""
Read the PHA's Exhibit A of a project-based voucher (PBV) HAP contract.

HUD-52530A/B Part 1 doesn't print the facts that matter: the PHA attaches
them as Exhibit A, in its own layout. HUD fixes what the exhibit must say
(24 CFR 983.203, which the form cites): the total number of contract units,
the units in the project, the contract units by size, and the initial rent
to owner by size. This reader looks for those statements by their labels,
not by any one PHA's wording, and works out a rent line's contract rent
from its own arithmetic ("$2,002 - $65 (Utility Allowance) = $1,937").

    fields = read_exhibit_a(pages)    # pages: [{"page", "text"}], e.g. layout_pages()
    fields["contract_units"]          # {"value", "source", "confidence", "method": "exhibit"}

Values the exhibit doesn't state are left out. Nothing here applies a HUD
or PHA rule; it reads what the exhibit says.
"""

import re
from typing import Dict, List, Optional

from .values import parse_money

SIZE_WORDS = {"studio": 0, "efficiency": 0, "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_SIZE = r"(studio|efficiency|zero|one|two|three|four|five|\d)"
NUM_UNITS = re.compile(rf"(\d+)\s+{_SIZE}\s*-?\s*(?:bedroom|br)\b", re.I)       # "16 2-bedroom", "4 one-bedroom"
SIZE_UNITS = re.compile(rf"\b{_SIZE}\s*-?\s*bedroom units?\s+(\d+)(?:\s*\((\d+)\s*PBV)?", re.I)  # "1 -bedroom units 72 (35 PBV Units)"
TABLE_ROW = re.compile(rf"^\s*{_SIZE}\s+bedroom\s*/?\s*(\d{{1,3}})\s*%\s+(\d+)", re.I)     # "Two Bedroom/ 30% 2 ..."
TABLE_CONT = re.compile(r"^\s*(\d{1,3})\s*%\s+(\d+)\b")                                     # "40% 1 6201"
RENT_LINE = re.compile(rf"\b{_SIZE}\s*-?\s*(?:br|bedroom)\b", re.I)
AMOUNT = re.compile(r"\$\s?\d[\d ,]*(?:\.\d{2})?")


def _size(token: str) -> int:
    return int(token) if token.isdigit() else SIZE_WORDS[token.lower()]


def _exhibit_pages(pages: List[Dict]) -> List[Dict]:
    """Pages that are an Exhibit A with figures in it (not Part 1's list of exhibits)."""
    out = []
    for p in pages:
        text = p.get("text") or ""
        if re.search(r"^\s*exhibit\s+a\b", text, re.I | re.M) and re.search(
                r"covered by (?:the |this )?hap contract\s*:?\s*\d", text, re.I):
            out.append(p)
    return out


def _entry(value, page: int, quote: str) -> Dict:
    return {"value": str(value), "source": {"page": page, "quote": quote.strip()[:200]},
            "confidence": "medium", "method": "exhibit"}


def _line_value(text: str, label: str) -> Optional[re.Match]:
    return re.search(rf"^\s*{label}\s*:\s*(.+?)\s*$", text, re.I | re.M)


UA_TAG = re.compile(r"^\W{0,3}(?:ua\b|\(?utility allowance)", re.I)
STD_TAG = re.compile(r"^\W{0,3}payment st(?:andar)?d", re.I)
RENT_TAG = re.compile(r"^\W{0,3}contract rent", re.I)


def _rent_from_line(line: str) -> Optional[Dict]:
    """The contract rent on one rent line, as {"rent", "allowance", "standard",
    "adds_up"}. Amounts are told apart by the label after them ("$67 UA",
    "$1,659 payment std", "$1,937 Contract Rent"). An unlabelled amount is the
    rent if the line has no labelled rent, else the payment standard. "adds_up"
    says whether the line's own arithmetic (standard - allowance = rent) holds,
    None if the line has none. The rent is reported as printed either way."""
    rent = allowance = standard = None
    untagged = []
    for m in AMOUNT.finditer(line):
        amount = parse_money(m.group(0).replace(" ", ""))
        if amount is None:
            continue
        after = line[m.end():m.end() + 25]
        if UA_TAG.match(after):
            allowance = amount
        elif STD_TAG.match(after):
            standard = amount
        elif RENT_TAG.match(after):
            rent = amount
        else:
            untagged.append(amount)
    if rent is None:
        if len(untagged) != 1:
            return None          # none, or two unlabelled amounts: can't tell which is the rent
        rent = untagged.pop()
    if standard is None and len(untagged) == 1:
        standard = untagged.pop()
    if untagged:
        return None
    adds_up = None
    if allowance is not None and standard is not None:
        adds_up = abs(standard - allowance - rent) <= 1.0
    return {"rent": rent, "allowance": allowance, "standard": standard, "adds_up": adds_up}


def _put_rent(fields: Dict, size: int, read: Dict, page: int, line: str) -> None:
    name = f"contract_rent_{size}br"
    if name in fields:
        return
    fields[name] = _entry(f"${read['rent']:,.2f}", page, line)
    if read["adds_up"] is False:
        fields[name]["confidence"] = "low"
        fields[name]["check_note"] = (
            f"The exhibit's rent line doesn't add up: {_fmt(read['standard'])} - {_fmt(read['allowance'])} = "
            f"{_fmt(read['standard'] - read['allowance'])}, but the contract rent shows {_fmt(read['rent'])}. "
            "Verify with your PHA.")


def _fmt(v: float) -> str:
    return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"


def read_exhibit_a(pages: List[Dict]) -> Dict[str, Dict]:
    fields: Dict[str, Dict] = {}

    def put(name, value, page, quote):
        if value is not None and name not in fields:
            fields[name] = _entry(value, page, quote)

    for p in _exhibit_pages(pages):
        text, page = p["text"], p["page"]
        m = _line_value(text, r"project name")
        if m:
            put("project_name", m.group(1), page, m.group(0))
        m = _line_value(text, r"(?:project )?address")
        if m:
            put("property_address", m.group(1), page, m.group(0))
        m = re.search(r"covered by (?:the |this )?hap contract\s*:?\s*(\d+)", text, re.I)
        if m:
            put("contract_units", int(m.group(1)), page, m.group(0))
        m = re.search(r"total number (?:of )?units in (?:the )?project\s*:?\s*(\d+)", text, re.I)
        if m:
            put("total_units", int(m.group(1)), page, m.group(0))

        # units by size: "PBV units: 4 one-bedroom, ..." / "Total units: 16 2-bedroom, ..."
        for label, prefix in ((r"pbv units", "contract_units"), (r"total units", "units")):
            m = _line_value(text, label)
            if m:
                for n, size in NUM_UNITS.findall(m.group(1)):
                    put(f"{prefix}_{_size(size)}br", int(n), page, m.group(0))
        for m in SIZE_UNITS.finditer(text):           # "1 -bedroom units 72 (35 PBV Units)"
            put(f"units_{_size(m.group(1))}br", int(m.group(2)), page, m.group(0))
            if m.group(3):
                put(f"contract_units_{_size(m.group(1))}br", int(m.group(3)), page, m.group(0))

        # the bedroom / AMI / quantity table; continuation rows belong to the size above
        by_size: Dict[int, int] = {}
        amis: List[float] = []
        size = None
        broken = False   # a size row OCR garbled ("3Oo/o"): its rows would land under the size above
        for line in text.splitlines():
            row = TABLE_ROW.match(line)
            cont = TABLE_CONT.match(line) if row is None else None
            if row is None and re.match(rf"^\s*{_SIZE}\s+bedroom\s*/", line, re.I):
                broken = True
            if row:
                size = _size(row.group(1))
                ami, qty = float(row.group(2)), int(row.group(3))
            elif cont and size is not None:
                ami, qty = float(cont.group(1)), int(cont.group(2))
            else:
                if re.match(r"^\s*total\b", line, re.I):
                    size = None
                continue
            by_size[size] = by_size.get(size, 0) + qty
            amis.append(ami)
        if not broken:
            for s, qty in by_size.items():
                put(f"contract_units_{s}br", qty, page, "unit table: " + ", ".join(f"{k}BR {v}" for k, v in by_size.items()))
            if amis and max(amis) <= 100:
                put("ami_limit_pct", f"{max(amis):g}%", page, "unit table AMI column")

        # initial rent to owner, one line per size
        for line in text.splitlines():
            if not re.search(r"contract rent", line, re.I):
                continue
            sm = RENT_LINE.search(line)
            read = _rent_from_line(line)
            if sm and read is not None:
                _put_rent(fields, _size(sm.group(1)), read, page, line)
        # wrapped layout: "Contract rent for" on one line, "1br $2,002 - $65 ... = $1,937" on the next
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(r"contract rent for\s*$", line, re.I):
                for nxt in lines[i + 1:i + 6]:
                    sm = re.match(rf"^\W*{_SIZE}\s*-?\s*(?:br|bedroom)\b", nxt, re.I)
                    read = _rent_from_line(nxt) if sm else None
                    if sm and read is not None:
                        _put_rent(fields, _size(sm.group(1)), read, page, nxt)
    return fields
