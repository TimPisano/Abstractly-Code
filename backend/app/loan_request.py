"""
Persistence for the loan underwriting module: loan requests, their
editable assumptions, and the T-12 snapshot each request underwrites
against.

A loan request is keyed to a DEAL, and a deal in this codebase is a
building identified by its normalized address -- the same
`_normalize_building_address` convention compute_t12_reconciliation,
compute_loss_to_lease and investment_memo._scoped_leases already use for
"this one property." There is no `deals` table, deliberately: inventing
one would add a core entity the other 38 modules know nothing about, and
the address key already works with every existing scoping function.

TENANCY: there is none here, and that is deliberate on this branch. No
query below filters by team, because `main`'s data model has no team
column to filter by -- a separate branch owns the team data model and
merges independently. This module therefore inherits the app's current
single-tenant posture: one deployment is one customer, and every
logged-in user sees every loan request on it.

That is a real limitation, not a detail, so it's stated here, in
database._migrate_loan_underwriting_tables, and in SUMMARY.md rather
than left for someone to discover.

WHERE ISOLATION PLUGS IN: every read of a single request goes through
`_require_request()`, and every list goes through `list_loan_requests()`.
Those two functions are the only places that build a WHERE clause
against `loan_requests`. Adding tenancy is therefore: add the column
(see database.py), add a `team_id` parameter to those two functions, add
`AND team_id = ?` to their queries, and pass the caller's team from
api.py. Nothing else moves. The funnel exists specifically so that
change is a reviewable diff instead of an audit of every call site --
please keep new queries going through it rather than writing a third
one alongside.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import database
from .loan_underwriting import default_assumptions, default_constraints, underwrite
from .portfolio import _normalize_building_address

# The three editable assumptions and three configurable constraints, with
# a display label and unit for each -- this is what makes them "visible
# and editable" in the API response rather than magic numbers buried in
# the engine. `source` is always None for these: they are judgments a
# human makes, not figures read out of a document, and giving them a
# fabricated citation would be worse than giving them none.
ASSUMPTION_FIELDS = {
    "vacancy_pct": {"label": "Vacancy", "unit": "percent"},
    "management_fee_pct": {"label": "Management fee", "unit": "percent_of_egi"},
    "replacement_reserves_per_unit": {"label": "Replacement reserves", "unit": "dollars_per_unit_per_year"},
}
CONSTRAINT_FIELDS = {
    "target_dscr": {"label": "Target DSCR", "unit": "ratio"},
    "max_ltv_pct": {"label": "Maximum LTV", "unit": "percent"},
    "min_debt_yield_pct": {"label": "Minimum debt yield", "unit": "percent"},
}

# Columns a client may set on create/update. Deliberately an allow-list
# rather than "whatever keys the request body had": without it, a client
# could set created_at, created_by_user_id, or id by including them in
# the JSON body, which is how an audit field silently becomes
# client-controlled.
EDITABLE_TERM_FIELDS = {
    "deal_name", "property_address", "loan_amount", "annual_rate_pct",
    "amortization_years", "term_years", "interest_only_months",
    "purchase_price", "appraised_value", "unit_count",
}

REQUIRED_TERM_FIELDS = {"property_address", "loan_amount", "annual_rate_pct", "amortization_years"}


class LoanRequestError(Exception):
    """Raised for a request a caller got wrong (missing/invalid field, unknown id) -- api.py turns this into a 400/404, never a 500."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_deal_key(property_address: Optional[str]) -> Optional[str]:
    """The deal key for an address: same building-level normalization the rest of the app uses, so a loan request and an investment memo agree on what 'this property' means."""
    return _normalize_building_address(property_address)


def _coerce_number(value: Any, field: str, *, allow_none: bool = True) -> Optional[float]:
    """
    Numbers arriving from JSON or a form may be strings. Converts, or
    raises LoanRequestError naming the field -- never silently coerces a
    garbage value to 0.0, which would produce a confidently wrong ratio
    rather than an error a caller can fix.
    """
    if value is None or value == "":
        if allow_none:
            return None
        raise LoanRequestError(f"{field} is required.")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise LoanRequestError(f"{field} must be a number (got {value!r}).")


def _validate_terms(terms: Dict[str, Any], *, require_all: bool) -> Dict[str, Any]:
    """
    Validates and normalizes loan terms. Rejects values that are not
    merely unusual but arithmetically meaningless, with a message saying
    which field and why:

      * loan_amount <= 0            -- nothing to underwrite
      * annual_rate_pct < 0         -- negative interest isn't modelled
      * amortization_years <= 0     -- can never amortize
      * interest_only_months < 0    -- meaningless

    A 0% rate IS allowed (seller financing and some affordable structures
    are genuinely 0%; the engine handles it with an explicit zero-rate
    branch). Purchase price and appraised value are both optional --
    an appraisal often isn't back yet -- but at least one is required,
    because with neither there is no LTV and no LTV-bound loan size, and
    a lender request with no value basis at all is almost certainly a
    mistake rather than an intention.
    """
    cleaned: Dict[str, Any] = {}

    unknown = set(terms) - EDITABLE_TERM_FIELDS
    if unknown:
        raise LoanRequestError(f"Unknown field(s): {', '.join(sorted(unknown))}.")

    if require_all:
        missing = REQUIRED_TERM_FIELDS - set(terms)
        if missing:
            raise LoanRequestError(f"Missing required field(s): {', '.join(sorted(missing))}.")

    if "property_address" in terms:
        address = (terms.get("property_address") or "").strip()
        if not address:
            raise LoanRequestError("property_address is required.")
        cleaned["property_address"] = address
        cleaned["normalized_property_address"] = normalize_deal_key(address)
        if not cleaned["normalized_property_address"]:
            raise LoanRequestError(
                "property_address could not be normalized into a building key -- "
                "check it's a real street address."
            )

    if "deal_name" in terms:
        cleaned["deal_name"] = (terms.get("deal_name") or "").strip() or None

    for field in ("loan_amount", "annual_rate_pct", "amortization_years", "term_years",
                  "purchase_price", "appraised_value"):
        if field in terms:
            cleaned[field] = _coerce_number(
                terms[field], field, allow_none=field not in REQUIRED_TERM_FIELDS
            )

    if "interest_only_months" in terms:
        io = _coerce_number(terms["interest_only_months"], "interest_only_months")
        cleaned["interest_only_months"] = int(io) if io is not None else 0

    if "unit_count" in terms:
        units = _coerce_number(terms["unit_count"], "unit_count")
        cleaned["unit_count"] = int(units) if units is not None else None

    if cleaned.get("loan_amount") is not None and cleaned["loan_amount"] <= 0:
        raise LoanRequestError("loan_amount must be greater than 0.")
    if cleaned.get("annual_rate_pct") is not None and cleaned["annual_rate_pct"] < 0:
        raise LoanRequestError("annual_rate_pct cannot be negative.")
    if cleaned.get("amortization_years") is not None and cleaned["amortization_years"] <= 0:
        raise LoanRequestError("amortization_years must be greater than 0.")
    if cleaned.get("interest_only_months") is not None and cleaned["interest_only_months"] < 0:
        raise LoanRequestError("interest_only_months cannot be negative.")
    for field in ("purchase_price", "appraised_value"):
        if cleaned.get(field) is not None and cleaned[field] <= 0:
            raise LoanRequestError(f"{field} must be greater than 0 when provided.")

    if require_all and cleaned.get("purchase_price") is None and cleaned.get("appraised_value") is None:
        raise LoanRequestError(
            "Provide purchase_price or appraised_value (or both) -- without a value basis "
            "there is no LTV and no LTV-constrained loan amount."
        )

    return cleaned


def _validate_overrides(values: Dict[str, Any], allowed: Dict[str, Any], kind: str) -> Dict[str, float]:
    """Validates an assumptions or constraints patch against its allow-list, rejecting unknown keys by name so a typo'd key is an error rather than a silently ignored edit."""
    unknown = set(values) - set(allowed)
    if unknown:
        raise LoanRequestError(
            f"Unknown {kind}: {', '.join(sorted(unknown))}. Valid: {', '.join(sorted(allowed))}."
        )
    cleaned: Dict[str, float] = {}
    for key, value in values.items():
        number = _coerce_number(value, key, allow_none=False)
        if number < 0:
            raise LoanRequestError(f"{key} cannot be negative.")
        cleaned[key] = number
    return cleaned


def _row_to_request(row: sqlite3.Row) -> Dict[str, Any]:
    request = dict(row)
    request["assumptions"] = json.loads(request.pop("assumptions_json"))
    request["constraints"] = json.loads(request.pop("constraints_json"))
    return request


def create_loan_request(
    terms: Dict[str, Any],
    assumptions: Optional[Dict[str, Any]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    created_by_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Saves a new loan request and returns it. Assumptions and constraints
    not supplied fall back to the documented engine defaults, stored
    explicitly on the row rather than left NULL -- so a request
    underwritten today and re-opened after a defaults change still shows
    the numbers it was actually underwritten with.
    """
    cleaned = _validate_terms(terms, require_all=True)
    stored_assumptions = {**default_assumptions(), **_validate_overrides(assumptions or {}, ASSUMPTION_FIELDS, "assumption")}
    stored_constraints = {**default_constraints(), **_validate_overrides(constraints or {}, CONSTRAINT_FIELDS, "constraint")}

    conn = database.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO loan_requests ("
            "  deal_name, property_address, normalized_property_address, loan_amount,"
            "  annual_rate_pct, amortization_years, term_years, interest_only_months,"
            "  purchase_price, appraised_value, unit_count, assumptions_json,"
            "  constraints_json, created_at, created_by_user_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cleaned.get("deal_name"), cleaned["property_address"],
                cleaned["normalized_property_address"], cleaned["loan_amount"],
                cleaned["annual_rate_pct"], cleaned["amortization_years"],
                cleaned.get("term_years"), cleaned.get("interest_only_months") or 0,
                cleaned.get("purchase_price"), cleaned.get("appraised_value"),
                cleaned.get("unit_count"), json.dumps(stored_assumptions),
                json.dumps(stored_constraints), _now(), created_by_user_id,
            ),
        )
        conn.commit()
        request_id = cur.lastrowid
    finally:
        conn.close()
    return get_loan_request(request_id)


def get_loan_request(request_id: int) -> Optional[Dict[str, Any]]:
    """One loan request, or None. Returns None (not an exception) for a missing id -- api.py decides the status code."""
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM loan_requests WHERE id = ?", (request_id,)).fetchone()
        return _row_to_request(row) if row else None
    finally:
        conn.close()


def _require_request(request_id: int) -> Dict[str, Any]:
    """
    Single-request read funnel. Every route that operates on one request
    goes through here, which is what makes tenancy a one-function change
    later (add a team_id parameter and an `AND team_id = ?` predicate --
    see this module's docstring).
    """
    request = get_loan_request(request_id)
    if request is None:
        raise LoanRequestError(f"Loan request {request_id} not found.")
    return request


def list_loan_requests(property_address: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Every saved loan request, newest first, optionally narrowed to one
    building by normalized address. The list read funnel -- see
    _require_request's note on tenancy.
    """
    conn = database.get_connection()
    try:
        if property_address:
            key = normalize_deal_key(property_address)
            rows = conn.execute(
                "SELECT * FROM loan_requests WHERE normalized_property_address = ? "
                "ORDER BY created_at DESC, id DESC",
                (key,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM loan_requests ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [_row_to_request(r) for r in rows]
    finally:
        conn.close()


def update_loan_request(
    request_id: int, terms: Dict[str, Any], updated_by_user_id: Optional[int] = None
) -> Dict[str, Any]:
    """Patches loan terms on an existing request. Only the fields supplied change; everything else keeps its stored value."""
    _require_request(request_id)
    cleaned = _validate_terms(terms, require_all=False)
    if not cleaned:
        raise LoanRequestError("No editable fields supplied.")

    columns = list(cleaned)
    assignments = ", ".join(f"{column} = ?" for column in columns)
    values = [cleaned[column] for column in columns]

    conn = database.get_connection()
    try:
        conn.execute(
            f"UPDATE loan_requests SET {assignments}, updated_at = ?, updated_by_user_id = ? WHERE id = ?",
            (*values, _now(), updated_by_user_id, request_id),
        )
        conn.commit()
    finally:
        conn.close()
    return _require_request(request_id)


def update_assumptions(
    request_id: int,
    assumptions: Optional[Dict[str, Any]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    updated_by_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Edits the stored assumptions and/or constraints. Merges onto what's
    already stored rather than replacing the whole set, so editing
    vacancy alone doesn't silently reset the management fee to its
    default.
    """
    request = _require_request(request_id)
    if not assumptions and not constraints:
        raise LoanRequestError("Supply at least one assumption or constraint to change.")

    merged_assumptions = {
        **request["assumptions"],
        **_validate_overrides(assumptions or {}, ASSUMPTION_FIELDS, "assumption"),
    }
    merged_constraints = {
        **request["constraints"],
        **_validate_overrides(constraints or {}, CONSTRAINT_FIELDS, "constraint"),
    }

    conn = database.get_connection()
    try:
        conn.execute(
            "UPDATE loan_requests SET assumptions_json = ?, constraints_json = ?, "
            "updated_at = ?, updated_by_user_id = ? WHERE id = ?",
            (json.dumps(merged_assumptions), json.dumps(merged_constraints),
             _now(), updated_by_user_id, request_id),
        )
        conn.commit()
    finally:
        conn.close()
    return _require_request(request_id)


def save_t12_snapshot(
    request_id: int, parsed: Dict[str, Any], filename: str, uploaded_by_user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Stores the PARSED figures from a T-12 (as produced by
    t12_import.parse_t12_financials) against a loan request, so the
    request stays reproducible after the uploaded file is gone.

    Deliberately stores no file bytes -- see
    database._migrate_loan_underwriting_tables for why. A re-upload
    inserts a NEW row rather than overwriting the old one: a corrected
    T-12 is normal, and keeping the superseded snapshot means a memo
    generated last week can still be explained. Reads always take the
    newest (see get_latest_t12_snapshot).
    """
    _require_request(request_id)
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO t12_snapshots ("
            "  loan_request_id, filename, uploaded_at, uploaded_by_user_id,"
            "  t12_inputs_json, sources_json, line_items_json, warnings_json,"
            "  management_fee_removed"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id, filename, _now(), uploaded_by_user_id,
                json.dumps(parsed["t12_inputs"]), json.dumps(parsed["sources"]),
                json.dumps(parsed["line_items"]), json.dumps(parsed["warnings"]),
                parsed.get("management_fee_removed"),
            ),
        )
        conn.commit()
        snapshot_id = cur.lastrowid
    finally:
        conn.close()
    return get_t12_snapshot(snapshot_id)


def _row_to_snapshot(row: sqlite3.Row) -> Dict[str, Any]:
    snapshot = dict(row)
    snapshot["t12_inputs"] = json.loads(snapshot.pop("t12_inputs_json"))
    snapshot["sources"] = json.loads(snapshot.pop("sources_json"))
    snapshot["line_items"] = json.loads(snapshot.pop("line_items_json"))
    snapshot["warnings"] = json.loads(snapshot.pop("warnings_json"))
    return snapshot


def get_t12_snapshot(snapshot_id: int) -> Optional[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM t12_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        return _row_to_snapshot(row) if row else None
    finally:
        conn.close()


def get_latest_t12_snapshot(request_id: int) -> Optional[Dict[str, Any]]:
    """The most recently uploaded T-12 snapshot for a request, or None if no T-12 has been uploaded yet."""
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM t12_snapshots WHERE loan_request_id = ? "
            "ORDER BY uploaded_at DESC, id DESC LIMIT 1",
            (request_id,),
        ).fetchone()
        return _row_to_snapshot(row) if row else None
    finally:
        conn.close()


def describe_assumptions(request: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Every assumption and constraint as a displayable, editable row:
    `{key, label, value, unit, kind, source, is_default}`.

    This is what satisfies "every assumption is visible and editable" --
    the API returns the full set with labels and units, not just the
    three numbers, so a UI can render an editable list without hardcoding
    what the assumptions are. `is_default` flags which ones nobody has
    touched, which is exactly what a reviewer wants to know first.

    `source` is None for all of these by construction: they are human
    judgments, not figures from a document. Figures that DO come from a
    document carry their citation separately (see describe_inputs).
    """
    rows: List[Dict[str, Any]] = []
    defaults = {**default_assumptions(), **default_constraints()}
    for key, meta in {**ASSUMPTION_FIELDS, **CONSTRAINT_FIELDS}.items():
        kind = "assumption" if key in ASSUMPTION_FIELDS else "constraint"
        stored = request["assumptions"] if kind == "assumption" else request["constraints"]
        value = stored.get(key, defaults.get(key))
        rows.append({
            "key": key,
            "label": meta["label"],
            "value": value,
            "unit": meta["unit"],
            "kind": kind,
            "source": None,
            "is_default": value == defaults.get(key),
        })
    return rows


def describe_inputs(request: Dict[str, Any], snapshot: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Every INPUT NUMBER with its source document, satisfying "every input
    number links to its source document and page where one exists."

    Two populations, and the distinction is the point:

      * T-12-derived figures carry a real citation --
        `{"file", "row", "quote"}`. A T-12 is a spreadsheet, so the
        citation is a ROW, not a page; this module does not invent a page
        number for a worksheet. `page` is therefore present and None for
        these, rather than absent, so a consumer can tell "this came from
        a document that has no pages" apart from "this has no source."
      * Loan terms the user typed (loan amount, rate, price) have
        `source: None`. They came from a term sheet this app has never
        seen. Attaching a citation to them would be a fabrication.
    """
    rows: List[Dict[str, Any]] = []

    for key, label in [
        ("loan_amount", "Loan amount"),
        ("annual_rate_pct", "Interest rate"),
        ("amortization_years", "Amortization"),
        ("term_years", "Term"),
        ("interest_only_months", "Interest-only period"),
        ("purchase_price", "Purchase price"),
        ("appraised_value", "Appraised value"),
        ("unit_count", "Units"),
    ]:
        rows.append({
            "key": key, "label": label, "value": request.get(key),
            "origin": "user_entered", "source": None,
        })

    if snapshot:
        sources = snapshot["sources"]
        for key, label in [
            ("gross_potential_rent", "Gross potential rent"),
            ("loss_to_lease", "Loss to lease"),
            ("concessions", "Concessions"),
            ("bad_debt", "Bad debt / collection loss"),
            ("other_income", "Other income"),
            ("operating_expenses_ex_management", "Operating expenses (ex. management fee)"),
            ("historical_noi", "Historical T-12 NOI"),
            ("total_rent_collected", "Total rent collected"),
        ]:
            source = sources.get(key)
            rows.append({
                "key": key,
                "label": label,
                "value": snapshot["t12_inputs"].get(key),
                "origin": "t12_document",
                "source": (
                    {"file": source["file"], "row": source["row"], "page": None, "quote": source["quote"]}
                    if source else None
                ),
            })

    return rows


def build_underwriting(request_id: int) -> Dict[str, Any]:
    """
    The complete underwriting result for a saved request: runs the engine
    against the request's stored terms, its stored assumptions and
    constraints, and its latest T-12 snapshot.

    Raises LoanRequestError when no T-12 has been uploaded yet, or when
    the uploaded one was missing a line the build-up genuinely requires
    (gross potential rent, total operating expenses). That's a refusal,
    not a zero: an underwriting result built from absent income figures
    would be a confidently wrong document, and this is the feature whose
    whole point is not producing those.
    """
    request = _require_request(request_id)
    snapshot = get_latest_t12_snapshot(request_id)
    if snapshot is None:
        raise LoanRequestError(
            "No T-12 has been uploaded for this loan request yet -- underwritten NOI "
            "is built from the T-12's verified figures, so there's nothing to underwrite from."
        )

    t12_inputs = dict(snapshot["t12_inputs"])
    if t12_inputs.get("gross_potential_rent") is None or t12_inputs.get("operating_expenses_ex_management") is None:
        raise LoanRequestError(
            "The uploaded T-12 is missing a line the NOI build-up requires "
            f"(warnings: {'; '.join(snapshot['warnings']) or 'none recorded'})."
        )

    # The request's own unit count wins over the snapshot's when set --
    # replacement reserves are per unit, and the operator editing the
    # request is a better authority on the unit count than whatever was
    # passed when the file was parsed.
    if request.get("unit_count"):
        t12_inputs["unit_count"] = request["unit_count"]

    loan_terms = {
        "loan_amount": request["loan_amount"],
        "annual_rate_pct": request["annual_rate_pct"],
        "amortization_years": request["amortization_years"],
        "term_years": request.get("term_years"),
        "interest_only_months": request.get("interest_only_months") or 0,
        "purchase_price": request.get("purchase_price"),
        "appraised_value": request.get("appraised_value"),
        "unit_count": request.get("unit_count"),
    }

    result = underwrite(
        loan_terms=loan_terms,
        t12_inputs=t12_inputs,
        assumptions=request["assumptions"],
        constraints=request["constraints"],
        sources=snapshot["sources"],
    )
    result["loan_request"] = request
    result["t12_snapshot"] = {
        "id": snapshot["id"],
        "filename": snapshot["filename"],
        "uploaded_at": snapshot["uploaded_at"],
        "management_fee_removed": snapshot["management_fee_removed"],
        "warnings": snapshot["warnings"],
        "line_items": snapshot["line_items"],
        # Carried through so the memo can show billed-vs-collected. These
        # two figures aren't part of the NOI build-up (the build-up starts
        # from gross potential rent), but the gap between what a property
        # BILLED and what it actually COLLECTED is one of the most
        # load-bearing facts in a multifamily credit file -- on the demo
        # statement it's ~6% of billed rent that never converts to cash,
        # and underwriting off the rent roll alone makes it invisible.
        "t12_inputs": t12_inputs,
    }
    result["assumption_rows"] = describe_assumptions(request)
    result["input_rows"] = describe_inputs(request, snapshot)
    result["rent_roll_analysis"] = _rent_roll_analysis(request["property_address"])
    return result


def _rent_roll_analysis(property_address: str) -> Dict[str, Any]:
    """
    The rent-roll-versus-lease picture for the credit memo's section 4,
    reusing the app's existing Deal Mismatch engine rather than
    recomputing anything -- deal_mismatch.build_deal_mismatch_report_data
    already scopes by property address with the same normalization this
    module uses for its deal key, so the two agree on "this building" by
    construction.

    This is the integration that makes the memo worth more than a
    spreadsheet: a lender gets the rent roll's claimed income checked
    against the actual signed leases, with each discrepancy's dollar
    impact and source page, in the same document as the ratios.

    Imported locally, not at module scope: deal_mismatch imports
    investment_memo, which imports portfolio and summary_memo -- a
    module-level import here would pull that whole chain into every
    loan-request read, including ones that never build a memo.

    Honest about the empty case. If no lease documents are on file for
    this address, this returns `has_lease_data: False` and the memo says
    so plainly, rather than printing "0 discrepancies found" -- which
    would read as "we checked and the rent roll is clean" when in fact
    nothing was checked at all. Those are completely different statements
    to put in front of a credit officer.
    """
    from .deal_mismatch import build_deal_mismatch_report_data

    report = build_deal_mismatch_report_data(property_address=property_address)
    return {
        "has_lease_data": report["total_units_checked"] > 0,
        "total_units_checked": report["total_units_checked"],
        "total_discrepancies": report["total_discrepancies"],
        "annual_income_overstatement": report["annual_income_overstatement"],
        "discrepancies": report["discrepancies"],
    }
