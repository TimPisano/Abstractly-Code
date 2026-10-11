"""
Section 8 records: request validation, the same-team reference guard,
API response shaping, and the address backfill. Storage lives in
database.py ("Section 8 records" section); routes in api.py under
/section8/*, all behind SECTION8_MODE (section8_mode.py).

Money comes in and goes out as dollars ("1400.00") and is stored as
integer cents, so arithmetic on it later (HAP reconciliation) never
drifts. Dates are ISO YYYY-MM-DD.
"""

import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from . import database
from .portfolio import (
    _SUITE_DESIGNATOR_RE,
    _is_rent_roll_import,
    _normalize_address,
    _normalize_building_address,
    field_value,
)


class RecordError(Exception):
    """A request the API should refuse: carries the HTTP status (400 / 404 / 409) and a user-facing message."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


PROGRAMS_PROPERTY = ("HCV", "PBV", "PBRA", "mixed", "market")
PROGRAMS_TENANCY = ("HCV", "PBV", "PBRA", "market")
INSPECTION_STANDARDS = ("HQS", "NSPIRE-V", "NSPIRE")
UNIT_STATUSES = ("occupied", "vacant", "down", "unknown")
TENANCY_STATUSES = ("current", "past")
CONTRACT_TYPES = ("HCV", "PBV", "PBRA")
CONTRACT_STATUSES = ("active", "expired", "terminated")
DOC_KINDS = (
    "lease", "tenancy_addendum", "hap_contract", "pha_notice", "inspection_report",
    "payment_register", "rent_roll_row", "other",
)

_MAX_TEXT = 500
_MAX_NOTES = 5000
_MAX_CENTS = 100_000_000_00  # $100M -- far above any real rent/HAP figure; stops absurd values, not real ones.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Body key -> (column, kind, option). kind: text | notes | int | cents | date | enum | ref | lease_ref | json
# A "ref" names the Section 8 table the id must belong to (same team).
FIELD_SPECS: Dict[str, Dict[str, Tuple[str, str, Any]]] = {
    "phas": {
        "name": ("name", "text", None),
        "short_name": ("short_name", "text", None),
        "jurisdiction": ("jurisdiction", "text", None),
        "inspection_standard": ("inspection_standard", "enum", INSPECTION_STANDARDS),
        "payment_day": ("payment_day", "int", (1, 31)),
        "rent_increase_notice_days": ("rent_increase_notice_days", "int", (0, 365)),
        "settings": ("settings_json", "json", None),
        "portal_url": ("portal_url", "text", None),
        "contact_name": ("contact_name", "text", None),
        "contact_email": ("contact_email", "text", None),
        "contact_phone": ("contact_phone", "text", None),
        "notes": ("notes", "notes", None),
    },
    "properties": {
        "name": ("name", "text", None),
        "address": ("address", "text", None),
        "program": ("program", "enum", PROGRAMS_PROPERTY),
        "default_pha_id": ("default_pha_id", "ref", "phas"),
        "notes": ("notes", "notes", None),
    },
    "units": {
        "property_id": ("property_id", "ref", "properties"),
        "unit_label": ("unit_label", "text", None),
        "bedrooms": ("bedrooms", "int", (0, 20)),
        "status": ("status", "enum", UNIT_STATUSES),
    },
    "tenancies": {
        "unit_id": ("unit_id", "ref", "units"),
        "head_of_household": ("head_of_household", "text", None),
        "household_size": ("household_size", "int", (1, 30)),
        "pha_id": ("pha_id", "ref", "phas"),
        "program": ("program", "enum", PROGRAMS_TENANCY),
        "voucher_bedrooms": ("voucher_bedrooms", "int", (0, 20)),
        "move_in_date": ("move_in_date", "date", None),
        "move_out_date": ("move_out_date", "date", None),
        "contract_rent": ("contract_rent_cents", "cents", None),
        "tenant_rent": ("tenant_rent_cents", "cents", None),
        "hap": ("hap_cents", "cents", None),
        "utility_allowance": ("utility_allowance_cents", "cents", None),
        "amounts_effective_date": ("amounts_effective_date", "date", None),
        "source_lease_id": ("source_lease_id", "lease_ref", None),
        "status": ("status", "enum", TENANCY_STATUSES),
    },
    "hap_contracts": {
        "pha_id": ("pha_id", "ref", "phas"),
        "contract_type": ("contract_type", "enum", CONTRACT_TYPES),
        "contract_number": ("contract_number", "text", None),
        "form": ("form", "text", None),
        "property_id": ("property_id", "ref", "properties"),
        "unit_id": ("unit_id", "ref", "units"),
        "tenancy_id": ("tenancy_id", "ref", "tenancies"),
        "start_date": ("start_date", "date", None),
        "end_date": ("end_date", "date", None),
        "contract_rent": ("contract_rent_cents", "cents", None),
        "initial_hap": ("initial_hap_cents", "cents", None),
        "source_lease_id": ("source_lease_id", "lease_ref", None),
        "status": ("status", "enum", CONTRACT_STATUSES),
    },
    "unit_documents": {
        "lease_id": ("lease_id", "lease_ref", None),
        "tenancy_id": ("tenancy_id", "ref", "tenancies"),
        "pha_id": ("pha_id", "ref", "phas"),
        "hap_contract_id": ("hap_contract_id", "ref", "hap_contracts"),
        "doc_kind": ("doc_kind", "enum", DOC_KINDS),
    },
}

REQUIRED_ON_CREATE = {
    "phas": ["name"],
    "properties": ["name"],
    "units": ["property_id", "unit_label"],
    "tenancies": ["unit_id"],
    "hap_contracts": ["contract_type"],
    "unit_documents": ["lease_id", "doc_kind"],
}

# Request body keys that may never be changed after creation (moving a
# tenancy to another unit etc. would silently rewrite history).
IMMUTABLE_ON_UPDATE = {
    "units": ["property_id"],
    "tenancies": ["unit_id"],
    "unit_documents": ["lease_id"],
}

_ENTITY_LABEL = {
    "phas": "PHA", "properties": "Property", "units": "Unit", "tenancies": "Tenancy",
    "hap_contracts": "HAP contract", "unit_documents": "Document link",
}


# ---------------------------------------------------------------- guard

def require_own(table: str, record_id: Any, team_id: int) -> Dict[str, Any]:
    """The same-team reference guard. Returns the row, or raises 404 -- identical for 'another team's id' and 'no such id', so a probe can't learn which ids exist."""
    if isinstance(record_id, bool) or not isinstance(record_id, int):
        raise RecordError(400, f"{_ENTITY_LABEL[table]} id must be an integer")
    row = database.get_section8_record(table, record_id, team_id)
    if row is None:
        raise RecordError(404, f"{_ENTITY_LABEL[table]} not found")
    return row


def _require_own_lease(lease_id: Any, team_id: int) -> Dict[str, Any]:
    if isinstance(lease_id, bool) or not isinstance(lease_id, int):
        raise RecordError(400, "lease_id must be an integer")
    lease = database.get_lease(lease_id, team_id=team_id)
    if lease is None:
        raise RecordError(404, "Lease not found")
    return lease


# ----------------------------------------------------------- validation

def dollars_to_cents(value: Any, key: str) -> Optional[int]:
    """'1,400.00' / 1400 / 1400.5 -> cents. None/'' -> None. Rejects negatives, NaN/inf, more than 2 decimals, and absurd sizes."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise RecordError(400, f"{key} must be a dollar amount")
    if isinstance(value, float) and not math.isfinite(value):
        raise RecordError(400, f"{key} must be a dollar amount")
    text = str(value).strip().replace(",", "").lstrip("$")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise RecordError(400, f"{key} must be a dollar amount")
    if not amount.is_finite():
        raise RecordError(400, f"{key} must be a dollar amount")
    if amount < 0:
        raise RecordError(400, f"{key} cannot be negative")
    # Bound the size BEFORE quantize: "1e400" is a valid Decimal but
    # quantize raises InvalidOperation on it (a 500, not a 400).
    if amount.adjusted() > 12:
        raise RecordError(400, f"{key} is too large")
    if amount != amount.quantize(Decimal("0.01")):
        raise RecordError(400, f"{key} can have at most 2 decimal places")
    cents = int(amount * 100)
    if cents > _MAX_CENTS:
        raise RecordError(400, f"{key} is too large")
    return cents


def cents_to_dollars(cents: Optional[int]) -> Optional[str]:
    if cents is None:
        return None
    return f"{Decimal(cents) / 100:.2f}"


def _clean_text(value: Any, key: str, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecordError(400, f"{key} must be text")
    value = value.strip()
    if len(value) > max_len:
        raise RecordError(400, f"{key} is too long (max {max_len} characters)")
    return value or None


def _clean_date(value: Any, key: str) -> Optional[str]:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise RecordError(400, f"{key} must be a date in YYYY-MM-DD format")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise RecordError(400, f"{key} is not a real date")
    return value


def _clean_int(value: Any, key: str, bounds: Tuple[int, int]) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecordError(400, f"{key} must be a whole number")
    low, high = bounds
    if not low <= value <= high:
        raise RecordError(400, f"{key} must be between {low} and {high}")
    return value


def clean_body(table: str, body: Dict[str, Any], team_id: int, creating: bool) -> Dict[str, Any]:
    """
    Request body -> {column: value} for database.create/update_section8_record.
    Unknown keys are ignored (never written). Every ref is checked
    against the caller's team before it's returned.
    """
    if not isinstance(body, dict):
        raise RecordError(400, "Request body must be a JSON object")
    specs = FIELD_SPECS[table]
    if creating:
        missing = [k for k in REQUIRED_ON_CREATE[table] if body.get(k) in (None, "")]
        if missing:
            raise RecordError(400, f"Missing required field: {missing[0]}")
    else:
        for key in IMMUTABLE_ON_UPDATE.get(table, []):
            if key in body:
                raise RecordError(400, f"{key} cannot be changed after creation")

    values: Dict[str, Any] = {}
    for key, (column, kind, option) in specs.items():
        if key not in body:
            continue
        raw = body[key]
        if kind == "text":
            values[column] = _clean_text(raw, key, _MAX_TEXT)
        elif kind == "notes":
            values[column] = _clean_text(raw, key, _MAX_NOTES)
        elif kind == "int":
            values[column] = _clean_int(raw, key, option)
        elif kind == "cents":
            values[column] = dollars_to_cents(raw, key)
        elif kind == "date":
            values[column] = _clean_date(raw, key)
        elif kind == "enum":
            if raw is None:
                values[column] = None
            elif raw not in option:
                raise RecordError(400, f"{key} must be one of: {', '.join(option)}")
            else:
                values[column] = raw
        elif kind == "json":
            if raw is None:
                values[column] = None
            elif not isinstance(raw, dict):
                raise RecordError(400, f"{key} must be a JSON object")
            else:
                encoded = json.dumps(raw)
                if len(encoded) > 20_000:
                    raise RecordError(400, f"{key} is too large")
                values[column] = encoded
        elif kind in ("ref", "lease_ref"):
            if raw is None:
                values[column] = None
                continue
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise RecordError(400, f"{key} must be an integer")
            if kind == "ref":
                require_own(option, raw, team_id)
            else:
                _require_own_lease(raw, team_id)
            values[column] = raw

    # A required field explicitly nulled out on update is still missing.
    for key in REQUIRED_ON_CREATE[table]:
        column = specs[key][0]
        if column in values and values[column] in (None, ""):
            raise RecordError(400, f"{key} cannot be empty")
    return values


def check_date_order(start: Optional[str], end: Optional[str], start_key: str, end_key: str) -> None:
    if start and end and end < start:
        raise RecordError(400, f"{end_key} cannot be before {start_key}")


# --------------------------------------------------------------- shaping

_CENTS_COLUMNS = {
    "contract_rent_cents": "contract_rent", "tenant_rent_cents": "tenant_rent", "hap_cents": "hap",
    "utility_allowance_cents": "utility_allowance", "initial_hap_cents": "initial_hap",
}


def to_api(row: Dict[str, Any]) -> Dict[str, Any]:
    """DB row -> API JSON: cents as dollar strings under the request key, settings_json as a dict, archived as a bool; team_id dropped."""
    out: Dict[str, Any] = {}
    for column, value in row.items():
        if column == "team_id":
            continue
        if column in _CENTS_COLUMNS:
            out[_CENTS_COLUMNS[column]] = cents_to_dollars(value)
        elif column == "settings_json":
            out["settings"] = json.loads(value) if value else {}
        else:
            out[column] = value
    out["archived"] = bool(row.get("archived_at"))
    return out


# --------------------------------------------------------------- backfill

def _unit_label(lease: Dict[str, Any], address: str) -> str:
    label = field_value(lease, "unit_number")
    if label:
        return label
    match = _SUITE_DESIGNATOR_RE.search(address)
    if match:
        return match.group(0).strip(" ,")
    return address.strip()


def _building_name(address: str) -> str:
    return _SUITE_DESIGNATOR_RE.sub("", address).strip(" ,") or address.strip()


def backfill_units(team_id: int, apply: bool) -> Dict[str, Any]:
    """
    Groups the team's live uploads (base leases + rent-roll rows; no
    amendments, no superseded versions) into properties and units by
    address, and links each upload to its unit.

    Dry run (apply=False) writes nothing. apply=True creates only what's
    missing, so re-running is a no-op. Never modifies a `leases` row.
    Creates no PHAs, tenancies or HAP contracts (those need extraction).

    Every unit it creates gets status 'unknown': main's rent-roll
    importer skips vacant rows, so a rent-roll row isn't proof of
    occupancy (user decision 2026-10-11; revisit once
    fix/section8-tenant-share records vacant/down units).
    """
    leases = database.get_all_leases(team_id)

    existing_properties = {
        p["normalized_address"]: p
        for p in database.list_section8_records("properties", team_id, include_archived=True)
        if p["normalized_address"]
    }
    existing_units = {
        u["normalized_address"]: u
        for u in database.list_section8_records("units", team_id, include_archived=True)
        if u["normalized_address"]
    }
    existing_links = {
        (d["lease_id"], d["unit_id"])
        for d in database.list_section8_records("unit_documents", team_id, include_archived=True)
    }

    planned_properties: Dict[str, Dict[str, Any]] = {}
    planned_units: Dict[str, Dict[str, Any]] = {}
    planned_links: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for lease in leases:
        address = field_value(lease, "property_address")
        unit_key = _normalize_address(address) if address else None
        building_key = _normalize_building_address(address) if address else None
        if not unit_key or not building_key:
            skipped.append({"lease_id": lease["id"], "filename": lease.get("filename"), "reason": "no property address"})
            continue

        if building_key not in existing_properties and building_key not in planned_properties:
            planned_properties[building_key] = {
                "name": _building_name(address), "address": _building_name(address),
                "normalized_address": building_key,
            }
        if unit_key not in existing_units and unit_key not in planned_units:
            planned_units[unit_key] = {
                "property_key": building_key, "unit_label": _unit_label(lease, address),
                "normalized_address": unit_key,
            }
        existing_unit = existing_units.get(unit_key)
        if existing_unit is not None and (lease["id"], existing_unit["id"]) in existing_links:
            continue
        planned_links.append({
            "lease_id": lease["id"], "unit_key": unit_key,
            "doc_kind": "rent_roll_row" if _is_rent_roll_import(lease) else "lease",
        })

    summary = {
        "applied": bool(apply),
        "properties_to_create": [
            {"name": p["name"], "normalized_address": key} for key, p in planned_properties.items()
        ],
        "units_to_create": [
            {"unit_label": u["unit_label"], "normalized_address": key, "property_normalized_address": u["property_key"]}
            for key, u in planned_units.items()
        ],
        "links_to_create": len(planned_links),
        "skipped": skipped,
    }
    if not apply:
        return summary

    property_ids = {key: p["id"] for key, p in existing_properties.items()}
    for key, p in planned_properties.items():
        property_ids[key] = database.create_section8_record("properties", team_id, p)

    unit_ids = {key: u["id"] for key, u in existing_units.items()}
    for key, u in planned_units.items():
        unit_ids[key] = database.create_section8_record("units", team_id, {
            "property_id": property_ids[u["property_key"]], "unit_label": u["unit_label"],
            "normalized_address": key, "status": "unknown",
        })

    for link in planned_links:
        database.create_section8_record("unit_documents", team_id, {
            "lease_id": link["lease_id"], "unit_id": unit_ids[link["unit_key"]],
            "doc_kind": link["doc_kind"], "linked_by": "backfill",
        })

    summary["created"] = {
        "properties": len(planned_properties), "units": len(planned_units), "links": len(planned_links),
    }
    return summary
