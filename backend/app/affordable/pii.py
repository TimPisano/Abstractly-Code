"""Tenant-data guards shared by the affordable extractors."""

import re

SSN_RE = re.compile(r"(?<!\d)\d{3}[- ]?\d{2}[- ]?\d{4}(?!\d)")
SSN_SHAPED_RE = re.compile(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)")    # with separators only
# Fields whose 9-digit values are identifiers (REMS property ID, contract
# and project numbers, a masked TIN), not SSNs. Bank account fields are
# deliberately not in this list.
ID_FIELD_RE = re.compile(r"(?<![a-z])(id|ids|rems|contract|project|proj|fha|bin|pin|tin|ein|no|num|number|voucher)(?![a-z])", re.I)
# (?<![a-z]) rather than \b: field names use underscores ("member_ssn",
# "head_dob"), and \b treats "_" as part of the word.
SSN_FIELD_RE = re.compile(r"(?<![a-z])ssn(?![a-z])|social[\s_]*security|soc\.?[\s_]*sec", re.I)
DOB_FIELD_RE = re.compile(r"(?<![a-z])dob(?![a-z])|date[\s_]*of[\s_]*birth|birth[\s_]*date", re.I)


def mask_ssns(text: str, *, identifier_field: bool = False) -> str:
    """Replace anything shaped like an SSN with a fixed marker. In a field
    known to hold an identifier, a bare 9-digit number is left alone (it's a
    REMS or contract number); "123-45-6789" shapes are masked regardless."""
    rx = SSN_SHAPED_RE if identifier_field else SSN_RE
    return rx.sub("[masked]", text or "")


def is_identifier_field(*names: str) -> bool:
    return any(ID_FIELD_RE.search((n or "").replace("_", " ")) for n in names)


def is_restricted_field(name: str) -> bool:
    """Fields we never read: SSNs and dates of birth."""
    return bool(SSN_FIELD_RE.search(name or "") or DOB_FIELD_RE.search(name or ""))
