"""
Arithmetic cross-checks on extracted program fields.

    checks = run_checks(program_fields)    # edits confidence in place, returns the check list

A check compares numbers the document itself states. It never changes an
extracted value:
  - a mismatch drops every field involved to "low" confidence and attaches
    the check's note (`check_note`), so a person looks at it;
  - a value the document doesn't state is filled in only when every other
    number in the identity was read and none of them is in doubt. It is
    marked method "derived", "medium" confidence, and says how it was worked out.

Identities (the document's own columns, and the definitions they rest on;
practitioner check pending, so every note says "Verify with your PHA"):
  - gross rent = contract rent + utility allowance
    (HUD Handbook 4350.3 REV-1, Glossary; 24 CFR 982.4 "gross rent")
  - tenant rent = total tenant payment - utility allowance, or $0 when the
    allowance is larger (24 CFR 5.634; the excess is a utility reimbursement)
  - assistance payment = gross rent - total tenant payment
    (the HUD-50059 rent computation lines)
  - units per bedroom size add up to the contract's units (a use agreement's
    to its total or low-income units)
"""

import re
from typing import Dict, List, Optional

from .values import parse_money, parse_int

VERIFY = "Verify with your PHA."
TOLERANCE = 1.0    # dollars; forms round to whole dollars
CITE_GROSS = "HUD Handbook 4350.3 REV-1, Glossary; 24 CFR 982.4"
CITE_TENANT_RENT = "24 CFR 5.634"
CITE_HAP = "HUD-50059 rent computation"

BR_SUFFIX = re.compile(r"^(contract_rent|utility_allowance|gross_rent)_(\d+)br$")


def _money(fields: Dict[str, Dict], name: str) -> Optional[float]:
    entry = fields.get(name)
    return parse_money(str(entry["value"])) if entry and entry.get("value") not in (None, "") else None


def _int(fields: Dict[str, Dict], name: str) -> Optional[int]:
    entry = fields.get(name)
    return parse_int(str(entry["value"])) if entry and entry.get("value") not in (None, "") else None


def _fmt(v: float) -> str:
    return f"${v:,.0f}" if v == int(v) else f"${v:,.2f}"


def _flag(fields: Dict[str, Dict], names: List[str], message: str, citation: str, checks: List[Dict]) -> None:
    note = f"{message} {VERIFY}"
    for n in names:
        entry = fields[n]
        entry["confidence"] = "low"
        if note not in (entry.get("check_note") or ""):
            entry["check_note"] = note if not entry.get("check_note") else f"{entry['check_note']} {note}"
    checks.append({"status": "mismatch", "fields": names, "message": note, "citation": citation})


def _derive(fields: Dict[str, Dict], name: str, value: float, inputs: List[str], how: str,
            citation: str, checks: List[Dict]) -> None:
    if any(fields[n].get("confidence") == "low" for n in inputs):
        return
    note = f"Not stated on the document; worked out as {how}. {VERIFY}"
    fields[name] = {
        "value": _fmt(value),
        "source": {"page": (fields[inputs[0]].get("source") or {}).get("page"), "quote": f"derived: {how}"},
        "confidence": "medium",
        "method": "derived",
        "check_note": note,
    }
    checks.append({"status": "derived", "fields": [name, *inputs], "message": note, "citation": citation})


def _rent_identity(fields, contract, ua, gross, label, checks):
    c, u, g = _money(fields, contract), _money(fields, ua), _money(fields, gross)
    if c is not None and u is not None and g is not None:
        if abs(c + u - g) > TOLERANCE:
            _flag(fields, [contract, ua, gross],
                  f"The document's {label} doesn't add up: contract rent {_fmt(c)} + utility allowance {_fmt(u)} "
                  f"= {_fmt(c + u)}, but gross rent shows {_fmt(g)}.", CITE_GROSS, checks)
        else:
            checks.append({"status": "ok", "fields": [contract, ua, gross], "citation": CITE_GROSS})
    elif c is not None and u is not None and g is None:
        _derive(fields, gross, c + u, [contract, ua],
                f"contract rent {_fmt(c)} + utility allowance {_fmt(u)}", CITE_GROSS, checks)


def _tenant_rent(fields, checks):
    ttp, ua, rent = _money(fields, "total_tenant_payment"), _money(fields, "utility_allowance"), _money(fields, "tenant_rent")
    if ttp is None or ua is None:
        return
    expected = max(ttp - ua, 0.0)
    how = f"total tenant payment {_fmt(ttp)} - utility allowance {_fmt(ua)}" + (" (floored at $0)" if ttp < ua else "")
    if rent is None:
        _derive(fields, "tenant_rent", expected, ["total_tenant_payment", "utility_allowance"], how,
                CITE_TENANT_RENT, checks)
    elif abs(rent - expected) > TOLERANCE:
        _flag(fields, ["total_tenant_payment", "utility_allowance", "tenant_rent"],
              f"Tenant rent {_fmt(rent)} doesn't match {how} = {_fmt(expected)}.", CITE_TENANT_RENT, checks)
    else:
        checks.append({"status": "ok", "fields": ["total_tenant_payment", "utility_allowance", "tenant_rent"],
                       "citation": CITE_TENANT_RENT})


def _assistance(fields, checks):
    gross, ttp, hap = _money(fields, "gross_rent"), _money(fields, "total_tenant_payment"), _money(fields, "assistance_payment")
    if gross is None or ttp is None:
        return
    expected = gross - ttp
    how = f"gross rent {_fmt(gross)} - total tenant payment {_fmt(ttp)}"
    if hap is None:
        if expected >= 0:
            _derive(fields, "assistance_payment", expected, ["gross_rent", "total_tenant_payment"], how, CITE_HAP, checks)
    elif abs(hap - expected) > TOLERANCE:
        _flag(fields, ["gross_rent", "total_tenant_payment", "assistance_payment"],
              f"Assistance payment {_fmt(hap)} doesn't match {how} = {_fmt(expected)}.", CITE_HAP, checks)
    else:
        checks.append({"status": "ok", "fields": ["gross_rent", "total_tenant_payment", "assistance_payment"],
                       "citation": CITE_HAP})


def _bedroom_sum(fields, checks):
    rows = sorted(n for n in fields if re.fullmatch(r"contract_units_\d+br", n))
    total = _int(fields, "contract_units")
    if len(rows) < 2 or total is None:
        return
    counts = [_int(fields, n) for n in rows]
    if any(c is None for c in counts):
        return
    if sum(counts) != total:
        _flag(fields, [*rows, "contract_units"],
              f"The contract units by bedroom size add up to {sum(counts)}, but the contract says {total}.",
              "the document's own unit counts", checks)
    else:
        checks.append({"status": "ok", "fields": [*rows, "contract_units"], "citation": "the document's own unit counts"})


def _lura_bedroom_sum(fields, checks):
    """A use agreement's unit mix may list every unit or only the restricted
    ones, so it is flagged only when it matches neither count."""
    if any(re.fullmatch(r"contract_units_\d+br", n) for n in fields):
        return
    rows = sorted(n for n in fields if re.fullmatch(r"units_\d+br", n))
    totals = {n: _int(fields, n) for n in ("total_units", "low_income_units") if _int(fields, n) is not None}
    counts = [_int(fields, n) for n in rows]
    if len(rows) < 2 or not totals or any(c is None for c in counts):
        return
    named = list(totals)
    if sum(counts) in totals.values():
        checks.append({"status": "ok", "fields": [*rows, *named], "citation": "the document's own unit counts"})
        return
    said = " and ".join(f"{n.replace('_', ' ')} {v}" for n, v in totals.items())
    _flag(fields, [*rows, *named], f"The units by bedroom size add up to {sum(counts)}, but the document says {said}.",
          "the document's own unit counts", checks)


def run_checks(fields: Dict[str, Dict]) -> List[Dict]:
    """Run every check that has its numbers present. Edits confidence and
    adds derived fields in place; never changes an extracted value."""
    checks: List[Dict] = []
    _rent_identity(fields, "contract_rent", "utility_allowance", "gross_rent", "rent", checks)
    sizes = sorted({int(m.group(2)) for m in map(BR_SUFFIX.match, list(fields)) if m})
    for n in sizes:
        label = "studio row" if n == 0 else f"{n}-bedroom row"
        _rent_identity(fields, f"contract_rent_{n}br", f"utility_allowance_{n}br", f"gross_rent_{n}br", label, checks)
    _tenant_rent(fields, checks)
    _assistance(fields, checks)
    _bedroom_sum(fields, checks)
    _lura_bedroom_sum(fields, checks)
    return checks
