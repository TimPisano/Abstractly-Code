"""
Tests for concession detection (fix/concession-detection):

  - app/concessions.py: parsing free months, move-in specials, recurring
    discounts and one-time credits out of lease text (with how/when each
    applies), pricing them into net effective / current rent.
  - both extraction engines producing the `concessions` field: the regex
    FieldExtractor, and the AI engine with the Anthropic client MOCKED
    (real anthropic.types objects, no network, no spend -- CLAUDE.md
    rule 5), including the real upload route end to end.
  - rent_roll_import.py's Concession column.
  - app/deal_mismatch.py's detect_concession_missing /
    detect_concession_mismatch / detect_concession_expiring and the
    effective-rent-aware rent_mismatch, plus portfolio.py's
    compute_rent_roll_reconciliation using the same rule.

Every case the brief calls out has its own test: single free month,
recurring discount, full-term discount, STACKED concessions (one
sentence and across pages), and EXPIRING concessions (already used,
active and about to burn off, burned off with a stale rent roll).

The Maple Ridge end-to-end check (all 3 planted concessions caught
through the real routes) is in test_demo_deal_golden.py.

Plain-script convention: `python tests/test_concessions.py`.
"""
import io
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anthropic.types import ToolUseBlock

from app.api import app
from app import ai_extraction, database
from app import concessions as c
from app import deal_mismatch as dm
from app.field_extractor import FieldExtractor
from app.portfolio import FIELD_NAMES, compute_rent_roll_reconciliation
from app.rent_roll_import import parse_rent_roll_rows

AS_OF = date(2026, 8, 31)

A104_TEXT = (
    "3. RENT. Resident shall pay Owner Base Rent of $1,075.00 per month, due in advance.\n"
    "3A. RENT CONCESSION. As a leasing incentive, and notwithstanding Section 3 above: One\n"
    "(1) month of Base Rent (the first full calendar month, October 2025) is abated as a move-in\n"
    "incentive. All other terms of this Lease remain unchanged."
)
E301_TEXT = (
    "3A. RENT CONCESSION. As a leasing incentive, and notwithstanding Section 3 above: Base\n"
    "Rent is reduced by $100.00 per month for the first six (6) months of the Lease Term (April 2026\n"
    "through September 2026) as a renewal incentive."
)
I204_TEXT = (
    "3A. RENT CONCESSION. Base Rent is reduced by $75.00 per month for the full twelve (12) month "
    "Lease Term as a retention incentive."
)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _items(text, page=1):
    return c.parse_concessions([{"page": page, "text": text}])


def _fields(concession_text=None, concession_pages=None, **overrides):
    result = {}
    for name in FIELD_NAMES:
        value = overrides.get(name)
        result[name] = (
            {"value": value, "source": {"page": 1, "quote": f"...{value}..."}, "confidence": "high"}
            if value is not None else {"value": None, "source": None, "confidence": None}
        )
    if concession_pages is not None:
        result["concessions"] = c.build_field_entry(c.parse_concessions(concession_pages))
    elif concession_text is not None:
        result["concessions"] = c.build_field_entry(_items(concession_text))
    if "rr_concessions" in overrides:
        result["concessions"] = {"value": overrides["rr_concessions"], "source": {"row": 2, "file": "rr.csv", "quote": overrides["rr_concessions"]}, "confidence": "high"}
    return result


def _rr(lease_id=1, **f):
    return {"id": lease_id, "filename": "rentroll.csv", "extracted_fields": _fields(**f)}


def _doc(lease_id=2, concession_text=None, concession_pages=None, **f):
    return {"id": lease_id, "filename": "lease.pdf",
            "extracted_fields": _fields(concession_text=concession_text, concession_pages=concession_pages, **f)}


UNIT = "4500 Maple Ridge Trail, Dallas, TX 75248, Suite A104"
TERM_12 = {"lease_start_date": "October 1, 2025", "lease_end_date": "September 30, 2026"}


def _pair(rr_rent, lease_rent, concession_text, rr_extra=None, **doc_extra):
    rr_kwargs = {"property_address": UNIT, "tenant": "Pat Doe", "rent_amount": rr_rent, **(rr_extra or {})}
    doc_kwargs = {"property_address": UNIT, "tenant": "Pat Doe", "rent_amount": lease_rent, **TERM_12, **doc_extra}
    return [_rr(**rr_kwargs), _doc(concession_text=concession_text, **doc_kwargs)]


def _types(rows):
    return sorted(r["discrepancy_type"] for r in rows)


def _all_rows(leases, today=AS_OF):
    rows = []
    for detector in dm._DETECTORS:
        rows.extend(detector(leases, today) if detector in dm._DATE_AWARE_DETECTORS else detector(leases))
    return rows


# ----------------------------------------------------------------------
# Parsing: what concession, how and when it applies
# ----------------------------------------------------------------------

def test_parse_single_free_month_with_trigger_and_calendar_month():
    items = _items(A104_TEXT, page=1)
    assert len(items) == 1, items
    item = items[0]
    assert item["kind"] == "free_rent" and item["free_months"] == 1
    assert item["trigger"] == "move_in"
    assert item["start_month"] == "2025-10" and item["position"] == "explicit"
    assert item["page"] == 1 and "is abated as a move-in incentive" in item["quote"]
    print("✓ test_parse_single_free_month_with_trigger_and_calendar_month: PASS")


def test_parse_recurring_discount_with_duration_and_explicit_range():
    (item,) = _items(E301_TEXT)
    assert item["kind"] == "recurring_discount"
    assert item["monthly_amount"] == 100.0 and item["months"] == 6
    assert item["start_month"] == "2026-04" and item["end_month"] == "2026-09"
    assert item["trigger"] == "renewal" and not item["full_term"]
    print("✓ test_parse_recurring_discount_with_duration_and_explicit_range: PASS")


def test_parse_full_term_discount():
    (item,) = _items(I204_TEXT)
    assert item["kind"] == "recurring_discount" and item["monthly_amount"] == 75.0
    assert item["full_term"] and not item["duration_assumed"]
    assert item["trigger"] == "retention"
    print("✓ test_parse_full_term_discount: PASS")


def test_parse_stacked_concessions_in_one_sentence():
    items = _items("Move-in special: two (2) months free plus $50 off rent each month for 12 months.")
    assert [i["kind"] for i in items] == ["free_rent", "recurring_discount"], items
    assert items[0]["free_months"] == 2
    assert items[1]["monthly_amount"] == 50.0 and items[1]["months"] == 12
    assert all(i["trigger"] == "move_in" for i in items)
    print("✓ test_parse_stacked_concessions_in_one_sentence: PASS")


def test_parse_stacked_concessions_across_pages_each_cite_own_page():
    pages = [
        {"page": 1, "text": "3A. One (1) month of Base Rent is abated as a move-in incentive."},
        {"page": 4, "text": "ADDENDUM B. Resident shall receive a one-time move-in credit of $250.00 on the first rent statement."},
    ]
    items = c.parse_concessions(pages)
    assert [(i["kind"], i["page"]) for i in items] == [("free_rent", 1), ("one_time_credit", 4)], items
    assert items[1]["one_time_amount"] == 250.0
    print("✓ test_parse_stacked_concessions_across_pages_each_cite_own_page: PASS")


def test_parse_restated_concession_counted_once():
    pages = [
        {"page": 1, "text": "Base Rent is reduced by $75.00 per month for the full Lease Term."},
        {"page": 3, "text": "SUMMARY OF KEY TERMS. Base Rent is reduced by $75.00 per month for the full Lease Term."},
    ]
    assert len(c.parse_concessions(pages)) == 1
    print("✓ test_parse_restated_concession_counted_once: PASS")


def test_parse_ignores_non_concessions():
    text = (
        "If the Premises are damaged by fire, Rent shall be abated for two (2) months until restored. "
        "Base Rent shall increase by $50.00 per month on each anniversary. "
        "Resident has paid a security deposit of $1,075.00. "
        "A late charge of 10% of one month's Base Rent applies, plus $10.00 per day. "
        "This Lease converts to month-to-month subject to a $75.00 month-to-month premium."
    )
    assert _items(text) == []
    print("✓ test_parse_ignores_non_concessions: PASS")


def test_parse_last_month_free_with_recapture():
    (item,) = _items("The last month's rent is free as a renewal incentive, provided that if Resident "
                     "defaults the abated rent becomes immediately due.")
    assert item["kind"] == "free_rent" and item["position"] == "end"
    assert item["recapture"] is True and item["trigger"] == "renewal"
    print("✓ test_parse_last_month_free_with_recapture: PASS")


def test_parse_percent_discount_reduced_to_and_half_month():
    (pct,) = _items("A 5% military discount off monthly rent applies for the full term.")
    assert pct["percent"] == 5.0 and pct["trigger"] == "military" and pct["full_term"]
    (reduced,) = _items("First month's rent is reduced to $500.00.")
    assert reduced["kind"] == "one_time_credit" and reduced["reduced_to"] == 500.0
    (half,) = _items("One-half (1/2) month free rent as a look-and-lease special.")
    assert half["free_months"] == 0.5 and half["trigger"] == "move_in"
    print("✓ test_parse_percent_discount_reduced_to_and_half_month: PASS")


def test_discount_with_no_stated_duration_assumes_full_term_and_says_so():
    items = _items("Resident receives a $40.00 per month employee discount.")
    assert items[0]["full_term"] and items[0]["duration_assumed"]
    entry = c.build_field_entry(items)
    assert entry["confidence"] == "medium"
    assert "no end date stated" in entry["value"]
    print("✓ test_discount_with_no_stated_duration_assumes_full_term_and_says_so: PASS")


def test_summary_value_round_trips_through_parser():
    """A manual edit or amendment drops the stored items; the display value alone must re-parse to the same schedule."""
    pages = [{"page": 1, "text": A104_TEXT + " " + E301_TEXT}]
    original = c.parse_concessions(pages)
    reparsed = c.parse_concession_text(c.summarize(original))
    keys = ("kind", "free_months", "monthly_amount", "months", "full_term", "start_month", "end_month")
    assert [{k: i[k] for k in keys} for i in reparsed] == [{k: i[k] for k in keys} for i in original], (original, reparsed)
    # ... and concession_items_for_entry falls back to it when items are gone
    edited = {"value": c.summarize(original), "source": None, "confidence": "high", "manually_verified": True}
    assert len(c.concession_items_for_entry(edited)) == 2
    print("✓ test_summary_value_round_trips_through_parser: PASS")


# ----------------------------------------------------------------------
# Effective rent
# ----------------------------------------------------------------------

def test_effective_rent_free_month_twelve_month_lease():
    eff = c.compute_effective_rent(1075.0, _items(A104_TEXT), date(2025, 10, 1), date(2026, 9, 30), AS_OF)
    assert eff["term_months"] == 12 and not eff["term_assumed"]
    assert eff["total_concession_value"] == 1075.0
    assert eff["net_effective_rent"] == 985.42
    assert eff["annualized_concession_value"] == 1075.0
    assert eff["current_rent"] == 1075.0           # Aug 2026: the Oct 2025 free month is long gone
    assert eff["items"][0]["status"] == "expired"
    assert eff["remaining_concession_value"] == 0.0
    print("✓ test_effective_rent_free_month_twelve_month_lease: PASS")


def test_effective_rent_annualizes_short_lease():
    # One month free on a 6-month lease is 2x as big as a share of a year's rent.
    eff = c.compute_effective_rent(1200.0, _items("One (1) month free rent."), date(2026, 1, 1), date(2026, 6, 30))
    assert eff["term_months"] == 6
    assert eff["net_effective_rent"] == 1000.0
    assert eff["annualized_concession_value"] == 2400.0
    print("✓ test_effective_rent_annualizes_short_lease: PASS")


def test_effective_rent_active_concession_current_rent_and_remaining():
    eff = c.compute_effective_rent(1290.0, _items(E301_TEXT), date(2026, 4, 1), date(2027, 3, 31), AS_OF)
    assert eff["net_effective_rent"] == 1240.0 and eff["annualized_concession_value"] == 600.0
    assert eff["current_rent"] == 1190.0
    assert eff["items"][0]["status"] == "active" and eff["items"][0]["end_date"] == "2026-09-30"
    assert eff["remaining_concession_value"] == 100.0  # September is the last discounted month
    print("✓ test_effective_rent_active_concession_current_rent_and_remaining: PASS")


def test_effective_rent_stacked_concessions_sum():
    items = _items("Move-in special: one (1) month free plus $50 off rent each month for 12 months.")
    eff = c.compute_effective_rent(1500.0, items, date(2026, 1, 1), date(2026, 12, 31), date(2026, 1, 15))
    assert eff["total_concession_value"] == 2100.0
    assert eff["annualized_concession_value"] == 2100.0
    assert eff["current_rent"] == 0.0  # January is the free month (and the $50 discount is active too)
    print("✓ test_effective_rent_stacked_concessions_sum: PASS")


def test_effective_rent_unpriceable_is_none_not_zero():
    eff = c.compute_effective_rent(None, _items(A104_TEXT), date(2025, 10, 1), date(2026, 9, 30), AS_OF)
    assert eff["quantified"] is False
    assert eff["total_concession_value"] is None and eff["annualized_concession_value"] is None
    print("✓ test_effective_rent_unpriceable_is_none_not_zero: PASS")


def test_effective_rent_missing_dates_assumes_twelve_months_and_flags_it():
    eff = c.compute_effective_rent(1720.0, _items(I204_TEXT))
    assert eff["term_assumed"] and eff["term_months"] == 12
    assert eff["annualized_concession_value"] == 900.0
    print("✓ test_effective_rent_missing_dates_assumes_twelve_months_and_flags_it: PASS")


# ----------------------------------------------------------------------
# Extraction engines
# ----------------------------------------------------------------------

def test_regex_engine_extracts_concessions_field():
    pages = [{"page": 1, "text": "TEXAS APARTMENT LEASE AGREEMENT\n" + A104_TEXT}, {"page": 2, "text": "8. RENTER'S INSURANCE."}]
    fields = FieldExtractor().extract_fields(pages)
    entry = fields["concessions"]
    assert entry["value"] == "1 month free (move-in, Oct 2025)", entry["value"]
    assert entry["source"]["page"] == 1 and entry["confidence"] == "high"
    assert entry["items"][0]["kind"] == "free_rent"
    # no concession -> honest not-found
    assert FieldExtractor().extract_fields([{"page": 1, "text": "Base Rent: $900.00 per month."}])["concessions"]["value"] is None
    print("✓ test_regex_engine_extracts_concessions_field: PASS")


def _payload(**overrides):
    payload = {name: {"value": None, "confidence": None, "source_text": None} for name in ai_extraction.LEASE_FIELDS}
    for name, (value, confidence, quote) in overrides.items():
        payload[name] = {"value": value, "confidence": confidence, "source_text": quote}
    return payload


def _mock_client(tool_input):
    response = mock.Mock()
    response.content = [ToolUseBlock(id="toolu_x", input=tool_input, name="record_lease_abstraction", type="tool_use")]
    response.usage = mock.Mock(input_tokens=10, output_tokens=5)
    response.stop_reason = "tool_use"
    client = mock.Mock()
    client.messages.create.return_value = response
    return client


AI_PAGES = [
    {"page": 1, "text": "Base Rent of $1,500.00 per month. The Lease Term begins on January 1, 2026 and ends on December 31, 2026.\n"
                        "3A. One (1) month of Base Rent (January 2026) is abated as a move-in incentive."},
    {"page": 2, "text": "ADDENDUM. Base Rent is reduced by $50.00 per month for the first six (6) months as a leasing special."},
]


def test_ai_engine_concessions_parsed_from_verbatim_quote_with_pages():
    quote = ("One (1) month of Base Rent (January 2026) is abated as a move-in incentive ... "
             "Base Rent is reduced by $50.00 per month for the first six (6) months as a leasing special")
    client = _mock_client(_payload(
        rent_amount=("$1,500.00", "high", "Base Rent of $1,500.00 per month"),
        # The model's own paraphrase gets the arithmetic WRONG ("$2,000
        # total") on purpose: the stored schedule must come from the
        # verbatim quote, never from the model's numbers.
        concessions=("1 month free + $50/mo off for 6 months ($2,000 total)", "high", quote),
    ))
    fields = ai_extraction.extract_lease_fields(AI_PAGES, client=client)
    tool = client.messages.create.call_args.kwargs["tools"][0]
    assert "concessions" in tool["input_schema"]["required"]
    entry = fields["concessions"]
    assert [(i["kind"], i["page"]) for i in entry["items"]] == [("free_rent", 1), ("recurring_discount", 2)], entry
    eff = c.compute_effective_rent(1500.0, entry["items"], date(2026, 1, 1), date(2026, 12, 31))
    assert eff["total_concession_value"] == 1800.0  # 1,500 + 6 x 50 -- not the model's "$2,000"
    print("✓ test_ai_engine_concessions_parsed_from_verbatim_quote_with_pages: PASS")


def test_ai_engine_unparseable_concession_kept_low_confidence_never_priced_zero():
    client = _mock_client(_payload(
        concessions=("Reduced rent during renovation", "medium", "Landlord may offer reduced rent during renovation at its discretion"),
    ))
    entry = ai_extraction.extract_lease_fields(AI_PAGES, client=client)["concessions"]
    assert entry["value"] == "Reduced rent during renovation"
    assert entry["confidence"] == "low" and "verify" in entry["validation_note"]
    assert "items" not in entry
    # ...and the Deal Mismatch Report treats it as found-but-unpriced
    leases = [
        _rr(property_address=UNIT, tenant="Pat Doe", rent_amount="$1,500.00"),
        {"id": 2, "filename": "lease.pdf", "extracted_fields": {
            **_fields(property_address=UNIT, tenant="Pat Doe", rent_amount="$1,500.00", **TERM_12),
            "concessions": entry,
        }},
    ]
    # Found-but-unreadable is reported with NO dollar figure -- never as
    # "no concession", never as $0 (review finding #4).
    (row,) = dm.detect_concession_missing(leases, AS_OF)
    assert row["annual_dollar_impact"] is None and row["monthly_dollar_impact"] is None
    assert "couldn't be read" in row["lease_value"]
    # ...and a rent roll concession column is NOT compared against "No concession in lease"
    leases[0] = _rr(property_address=UNIT, tenant="Pat Doe", rent_amount="$1,500.00", rr_concessions="$125.00/mo")
    (row,) = dm.detect_concession_mismatch(leases, AS_OF)
    assert row["lease_value"] != "No concession in lease" and "couldn't be read" in row["lease_value"]
    assert row["annual_dollar_impact"] is None and row["income_direction"] is None
    assert dm.detect_concession_missing(leases, AS_OF) == []
    print("✓ test_ai_engine_unparseable_concession_kept_low_confidence_never_priced_zero: PASS")


def test_ai_engine_no_concession_is_not_found():
    entry = ai_extraction.extract_lease_fields(AI_PAGES, client=_mock_client(_payload()))["concessions"]
    assert entry["value"] is None and "items" not in entry
    print("✓ test_ai_engine_no_concession_is_not_found: PASS")


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    from app import usage_limits
    usage_limits._reset_extraction_rate_limit_for_tests()
    created = database.create_user("concession-analyst@example.com", "Analyst", "x", role="analyst")
    return tmp.name, created["id"]


def _client(user_id):
    conn = database.get_connection()
    try:
        team = conn.execute("SELECT id FROM teams WHERE name='Legacy' LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess.update({"user_id": user_id, "email": "concession-analyst@example.com", "name": "Analyst",
                     "role": "analyst", "team_id": team})
    return client


def _lease_pdf(lines):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    y = 720
    for line in lines:
        pdf.drawString(54, y, line)
        y -= 16
    pdf.save()
    return buf.getvalue()


@contextmanager
def _sync_ai_engine(client):
    prev = os.environ.get("LEASE_ASYNC_EXTRACTION")
    os.environ["LEASE_ASYNC_EXTRACTION"] = "false"
    try:
        with mock.patch.object(ai_extraction, "resolve_engine", return_value="ai"), \
             mock.patch.object(ai_extraction, "_make_client", return_value=client):
            yield
    finally:
        if prev is None:
            os.environ.pop("LEASE_ASYNC_EXTRACTION", None)
        else:
            os.environ["LEASE_ASYNC_EXTRACTION"] = prev


def test_upload_route_ai_engine_end_to_end_concession_reaches_report():
    """Real POST /leases with the AI engine on and the Anthropic client mocked, then a real rent roll import and the real report route."""
    db_path, user_id = _fresh_temp_db()
    try:
        address = "77 Birch Way, Austin, TX 78701"
        quote = "Base Rent is reduced by $100.00 per month for the first six (6) months as a renewal incentive"
        client = _mock_client(_payload(
            tenant=("Robin Vale", "high", 'Robin Vale ("Resident")'),
            rent_amount=("$1,400.00", "high", "Base Rent of $1,400.00 per month"),
            property_address=(f"{address}, Suite 12", "high", f"{address}, Suite 12"),
            lease_start_date=("January 1, 2026", "high", "begins on January 1, 2026"),
            lease_end_date=("December 31, 2026", "high", "ends on December 31, 2026"),
            concessions=("$100.00/mo off for the first 6 months (renewal)", "high", quote),
        ))
        pdf = _lease_pdf([
            'Lease between Birch Owner LLC ("Owner") and Robin Vale ("Resident").',
            f"Premises: {address}, Suite 12. Base Rent of $1,400.00 per month.",
            "The Lease Term begins on January 1, 2026 and ends on December 31, 2026.",
            quote + ".",
        ])
        http = _client(user_id)
        with _sync_ai_engine(client):
            resp = http.post("/leases", data={"file": (io.BytesIO(pdf), "vale.pdf")}, content_type="multipart/form-data")
        assert resp.status_code == 201, resp.get_json()
        stored = resp.get_json()["leases"][0]["extracted_fields"]["concessions"]
        assert stored["items"][0]["monthly_amount"] == 100.0 and stored["engine"] == "ai"

        csv = "Unit,Tenant,Rent,Lease From,Lease To\n12,Robin Vale,1400.00,01/01/2026,12/31/2026\n"
        resp = http.post("/leases/import-rent-roll",
                         data={"file": (io.BytesIO(csv.encode()), "rr.csv"), "property_address": address},
                         content_type="multipart/form-data")
        assert resp.status_code == 201, resp.get_json()

        data = dm.build_deal_mismatch_report_data(team_id=1, today=date(2026, 3, 15))
        rows = [r for r in data["discrepancies"] if r["discrepancy_type"] == "concession_missing"]
        assert len(rows) == 1, data["discrepancies"]
        assert rows[0]["annual_dollar_impact"] == 600.0 and rows[0]["monthly_dollar_impact"] == 50.0
        assert rows[0]["source"]["page"] == 1 and "reduced by $100.00" in rows[0]["source"]["quote"]

        route = http.post("/portfolio/deal-mismatch-report", data={})
        assert route.status_code == 200
        assert any(r["discrepancy_type"] == "concession_missing" for r in route.get_json()["discrepancies"])
    finally:
        os.unlink(db_path)
    print("✓ test_upload_route_ai_engine_end_to_end_concession_reaches_report: PASS")


# ----------------------------------------------------------------------
# Rent roll import: Concession column
# ----------------------------------------------------------------------

def test_rent_roll_concession_column_parsed_and_never_read_as_rent():
    headers = ["Unit", "Tenant", "Rent Concession", "Rent", "Lease To"]
    rows = [["101", "Pat Doe", "-100.00", "1290.00", "03/31/2027"], ["102", "Lee Roe", "0", "1200", "03/31/2027"]]
    result = parse_rent_roll_rows(headers, rows, "rr.csv", "1 Elm St")
    assert result["column_mapping"]["rent_amount"] == 3, result["column_mapping"]
    assert result["column_mapping"]["concessions"] == 2
    first, second = (l["extracted_fields"] for l in result["leases"])
    assert first["rent_amount"]["value"] == "$1,290.00"
    assert first["concessions"]["value"] == "$100.00/mo"
    assert second["concessions"]["value"] == "$0.00/mo"  # explicit $0 is kept: "shows no concession" != "no column"
    # A file with ONLY a concession column and no real rent column must not import the concession as rent
    only = parse_rent_roll_rows(["Tenant", "Concession", "Base Rent"], [["Pat", "50", "1000"]], "rr.csv")
    assert only["leases"][0]["extracted_fields"]["rent_amount"]["value"] == "$1,000.00"
    print("✓ test_rent_roll_concession_column_parsed_and_never_read_as_rent: PASS")


# ----------------------------------------------------------------------
# Detectors
# ----------------------------------------------------------------------

def test_concession_missing_free_month_annualized_with_citation():
    rows = _all_rows(_pair("$1,075.00", "$1,075.00", A104_TEXT))
    assert _types(rows) == ["concession_missing"], rows
    row = rows[0]
    assert row["annual_dollar_impact"] == 1075.0 and row["monthly_dollar_impact"] == 89.58
    assert row["income_direction"] == "overstate" and row["severity"] == "low"
    assert row["source"]["page"] == 1 and "abated" in row["source"]["quote"]
    assert row["rent_roll_value"] == "$1,075.00 (no concession shown)"
    assert row["lease_value"] == "1 month free (move-in, Oct 2025)"
    assert row["effective_rent"]["net_effective_rent"] == 985.42
    assert "already used" in row["note"]
    print("✓ test_concession_missing_free_month_annualized_with_citation: PASS")


def test_concession_missing_stacked_concessions_sum_and_cite_each_clause():
    pages = [
        {"page": 1, "text": "One (1) month of Base Rent is abated as a move-in incentive."},
        {"page": 2, "text": "Base Rent is reduced by $50.00 per month for the full Lease Term."},
    ]
    leases = [
        _rr(property_address=UNIT, tenant="Pat Doe", rent_amount="$1,500.00"),
        _doc(concession_pages=pages, property_address=UNIT, tenant="Pat Doe", rent_amount="$1,500.00", **TERM_12),
    ]
    (row,) = dm.detect_concession_missing(leases, AS_OF)
    assert row["annual_dollar_impact"] == 2100.0  # 1,500 free month + 12 x 50
    assert [s["page"] for s in row["sources"]] == [1, 2]
    assert "; " in row["lease_value"]
    print("✓ test_concession_missing_stacked_concessions_sum_and_cite_each_clause: PASS")


def test_expiring_concession_rent_roll_shows_gross_flags_missing_and_expiring_soon():
    leases = _pair("$1,290.00", "$1,290.00", E301_TEXT, lease_start_date="April 1, 2026", lease_end_date="March 31, 2027")
    rows = _all_rows(leases)
    assert _types(rows) == ["concession_missing"], rows
    assert rows[0]["annual_dollar_impact"] == 600.0
    assert "active, ends 2026-09-30 (expiring soon)" in rows[0]["note"], rows[0]["note"]
    print("✓ test_expiring_concession_rent_roll_shows_gross_flags_missing_and_expiring_soon: PASS")


def test_expiring_concession_rent_roll_shows_discounted_rent_flags_burn_off_not_rent_mismatch():
    leases = _pair("$1,190.00", "$1,290.00", E301_TEXT, lease_start_date="April 1, 2026", lease_end_date="March 31, 2027")
    rows = _all_rows(leases)
    # Before Phase 4 this was a $100/mo "understate" rent_mismatch; the rent
    # roll is actually right for this month -- the real issue is the step-up.
    assert _types(rows) == ["concession_expiring"], rows
    row = rows[0]
    assert row["income_direction"] == "understate"
    assert row["monthly_dollar_impact"] == 100.0
    assert row["annual_dollar_impact"] == 600.0  # Oct 2026 - Mar 2027 at full rent, all inside the next 12 months
    assert "steps up to $1,290.00" in row["lease_value"]
    print("✓ test_expiring_concession_rent_roll_shows_discounted_rent_flags_burn_off_not_rent_mismatch: PASS")


def test_expiring_concession_annual_capped_to_twelve_month_window():
    text = "Base Rent is reduced by $100.00 per month for the first three (3) months as a move-in incentive."
    leases = _pair("$1,900.00", "$2,000.00", text, lease_start_date="August 1, 2026", lease_end_date="July 31, 2028")
    (row,) = dm.detect_concession_expiring(leases, AS_OF)
    # Discount ends Oct 2026; full rent Nov 2026 onward, but only Nov 2026 - Jul 2027 fall in the next 12 months
    assert row["annual_dollar_impact"] == 900.0, row
    print("✓ test_expiring_concession_annual_capped_to_twelve_month_window: PASS")


def test_burned_off_concession_with_stale_discounted_rent_roll_is_rent_mismatch():
    leases = _pair("$1,190.00", "$1,290.00", E301_TEXT, lease_start_date="April 1, 2026", lease_end_date="March 31, 2027")
    rows = _all_rows(leases, today=date(2026, 11, 15))  # discount ended Sep 30
    assert _types(rows) == ["rent_mismatch"], rows
    assert rows[0]["income_direction"] == "understate" and rows[0]["monthly_dollar_impact"] == 100.0
    assert rows[0]["effective_rent"]["current_rent"] == 1290.0
    print("✓ test_burned_off_concession_with_stale_discounted_rent_roll_is_rent_mismatch: PASS")


def test_rent_roll_showing_net_effective_rent_is_not_a_mismatch():
    rows = _all_rows(_pair("$1,645.00", "$1,720.00", I204_TEXT))
    assert rows == [], rows
    print("✓ test_rent_roll_showing_net_effective_rent_is_not_a_mismatch: PASS")


def test_rent_roll_above_base_reports_rent_mismatch_and_concession_separately():
    rows = _all_rows(_pair("$1,800.00", "$1,720.00", I204_TEXT))
    assert _types(rows) == ["concession_missing", "rent_mismatch"], rows
    total = sum(r["annual_dollar_impact"] for r in rows)
    assert total == 960.0 + 900.0  # (1,800-1,720) x 12 + 75 x 12: the full gap to effective rent
    print("✓ test_rent_roll_above_base_reports_rent_mismatch_and_concession_separately: PASS")


def test_rent_roll_unexplained_below_base_is_rent_mismatch_only():
    rows = _all_rows(_pair("$1,500.00", "$1,720.00", I204_TEXT))
    assert _types(rows) == ["rent_mismatch"], rows
    print("✓ test_rent_roll_unexplained_below_base_is_rent_mismatch_only: PASS")


def test_rent_roll_concession_column_matching_lease_is_clean():
    rows = _all_rows(_pair("$1,720.00", "$1,720.00", I204_TEXT, rr_extra={"rr_concessions": "$75.00/mo"}))
    assert rows == [], rows
    # matching the CURRENT month's discount (not the amortized one) also counts
    leases = _pair("$1,290.00", "$1,290.00", E301_TEXT, rr_extra={"rr_concessions": "$100.00/mo"},
                   lease_start_date="April 1, 2026", lease_end_date="March 31, 2027")
    assert _all_rows(leases) == []
    print("✓ test_rent_roll_concession_column_matching_lease_is_clean: PASS")


def test_rent_roll_concession_column_smaller_than_lease_is_mismatch_overstate():
    (row,) = _all_rows(_pair("$1,720.00", "$1,720.00", I204_TEXT, rr_extra={"rr_concessions": "$25.00/mo"}))
    assert row["discrepancy_type"] == "concession_mismatch"
    assert row["income_direction"] == "overstate"
    assert row["monthly_dollar_impact"] == 50.0 and row["annual_dollar_impact"] == 600.0
    print("✓ test_rent_roll_concession_column_smaller_than_lease_is_mismatch_overstate: PASS")


def test_rent_roll_concession_lease_does_not_support_is_mismatch_understate():
    (row,) = _all_rows(_pair("$1,720.00", "$1,720.00", None, rr_extra={"rr_concessions": "$60.00/mo"}))
    assert row["discrepancy_type"] == "concession_mismatch"
    assert row["lease_value"] == "No concession in lease"
    assert row["income_direction"] == "understate" and row["annual_dollar_impact"] == 720.0
    print("✓ test_rent_roll_concession_lease_does_not_support_is_mismatch_understate: PASS")


def test_rent_roll_concession_column_zero_is_concession_missing():
    (row,) = _all_rows(_pair("$1,720.00", "$1,720.00", I204_TEXT, rr_extra={"rr_concessions": "$0.00/mo"}))
    assert row["discrepancy_type"] == "concession_missing"
    assert row["rent_roll_value"] == "$1,720.00 (concession column shows $0.00)"
    print("✓ test_rent_roll_concession_column_zero_is_concession_missing: PASS")


def test_expired_lease_concession_not_double_counted():
    leases = _pair("$1,075.00", "$1,075.00", A104_TEXT)
    rows = _all_rows(leases, today=date(2026, 10, 15))  # lease ended Sep 30, 2026
    assert _types(rows) == ["expired_but_occupied"], rows
    print("✓ test_expired_lease_concession_not_double_counted: PASS")


def test_unpriceable_concession_reported_with_no_dollar_figure():
    leases = [
        _rr(property_address=UNIT, tenant="Pat Doe", rent_amount="$1,075.00"),
        _doc(concession_text=A104_TEXT, property_address=UNIT, tenant="Pat Doe", **TERM_12),  # lease rent not extracted
    ]
    (row,) = dm.detect_concession_missing(leases, AS_OF)
    assert row["annual_dollar_impact"] is None and row["monthly_dollar_impact"] is None
    assert row["severity"] == "medium"
    print("✓ test_unpriceable_concession_reported_with_no_dollar_figure: PASS")


def test_reconciliation_uses_effective_rent_too():
    leases = _pair("$1,645.00", "$1,720.00", I204_TEXT)
    assert [m for m in compute_rent_roll_reconciliation(leases)["mismatches"] if m["field"] == "rent_amount"] == []
    leases = _pair("$1,500.00", "$1,720.00", I204_TEXT)
    assert [m["field"] for m in compute_rent_roll_reconciliation(leases)["mismatches"]] == ["rent_amount"]
    print("✓ test_reconciliation_uses_effective_rent_too: PASS")


def test_report_totals_net_concession_rows_and_summary():
    """build_deal_mismatch_report_data over a real DB: an overstate concession_missing and an understate concession_expiring net out in the headline."""
    db_path, _ = _fresh_temp_db()
    try:
        u1 = "9 Oak Ct, Suite 1"
        u2 = "9 Oak Ct, Suite 2"
        database.insert_lease("rr.csv", _fields(property_address=u1, tenant="A One", rent_amount="$1,720.00"), display_name="A", team_id=1)
        database.insert_lease("a.pdf", _fields(I204_TEXT, property_address=u1, tenant="A One", rent_amount="$1,720.00", **TERM_12), display_name="A", team_id=1)
        database.insert_lease("rr.csv", _fields(property_address=u2, tenant="B Two", rent_amount="$1,190.00"), display_name="B", team_id=1)
        database.insert_lease("b.pdf", _fields(E301_TEXT, property_address=u2, tenant="B Two", rent_amount="$1,290.00",
                                               lease_start_date="April 1, 2026", lease_end_date="March 31, 2027"), display_name="B", team_id=1)
        data = dm.build_deal_mismatch_report_data(team_id=1, today=AS_OF)
        assert _types(data["discrepancies"]) == ["concession_expiring", "concession_missing"], data["discrepancies"]
        assert data["annual_income_overstatement"] == 900.0 - 600.0
        assert data["concession_summary"] == {"leases_with_concessions": 2, "annualized_concession_value": 1500.0}

        from app.deal_mismatch_export import generate_deal_mismatch_report_excel, generate_deal_mismatch_report_pdf
        assert len(generate_deal_mismatch_report_pdf(data)) > 1000
        assert len(generate_deal_mismatch_report_excel(data)) > 1000
    finally:
        os.unlink(db_path)
    print("✓ test_report_totals_net_concession_rows_and_summary: PASS")


# ----------------------------------------------------------------------
# Reviewer findings (fix-first round) -- each one reproduced, then fixed
# ----------------------------------------------------------------------

def test_review_deposit_credited_to_last_month_is_not_free_rent():
    for text in (
        "Tenant shall pay one month's rent as a security deposit, which will be credited toward the last month's rent.",
        "Upon execution of this Lease, one month's rent shall be credited against the final month of the Term.",
        "Resident has prepaid one (1) month of rent, to be applied toward the last month of the Lease Term.",
    ):
        assert _items(text) == [], (text, _items(text))
    # ...and the hidden-mismatch consequence: a real $125/mo gap must still surface
    deposit = "Tenant shall pay one month's rent as a security deposit, which will be credited toward the last month's rent."
    rows = _all_rows(_pair("$1,375.00", "$1,500.00", deposit))
    assert _types(rows) == ["rent_mismatch"], rows
    print("✓ test_review_deposit_credited_to_last_month_is_not_free_rent: PASS")


def test_review_credit_card_fee_is_not_a_credit():
    assert _items("A $35 credit card processing fee applies to card payments.") == []
    assert _items("Payments by credit card of $500 or more incur a 3% fee.") == []
    print("✓ test_review_credit_card_fee_is_not_a_credit: PASS")


def test_review_rent_roll_concession_date_and_count_columns_not_read_as_dollars():
    headers = ["Unit", "Tenant", "Rent", "Concession End Date", "Concession Months", "Lease End"]
    result = parse_rent_roll_rows(headers, [["101", "Pat", "1200", "2026-03-31", "1", "2026-12-31"]], "rr.csv", "1 Elm St")
    assert "concessions" not in result["column_mapping"], result["column_mapping"]
    assert "concessions" not in result["leases"][0]["extracted_fields"]
    # the amount column still wins when both are present
    headers = ["Unit", "Tenant", "Rent", "Concession Type", "Concession", "Concession Start"]
    result = parse_rent_roll_rows(headers, [["101", "Pat", "1200", "Move-in", "-75", "2026-01-01"]], "rr.csv", "1 Elm St")
    assert result["column_mapping"]["concessions"] == 4
    assert result["leases"][0]["extracted_fields"]["concessions"]["value"] == "$75.00/mo"
    print("✓ test_review_rent_roll_concession_date_and_count_columns_not_read_as_dollars: PASS")


def test_review_ai_restated_concession_counted_once():
    pages = [
        {"page": 1, "text": "Base Rent is reduced by $100.00 per month for the first six (6) months as a renewal incentive."},
        {"page": 4, "text": "KEY TERMS: Base Rent is reduced by $100.00 per month for the first six (6) months as a renewal incentive."},
    ]
    quote = ("Base Rent is reduced by $100.00 per month for the first six (6) months as a renewal incentive ... "
             "Base Rent is reduced by $100.00 per month for the first six (6) months as a renewal incentive")
    entry = ai_extraction.extract_lease_fields(pages, client=_mock_client(_payload(
        concessions=("$100.00/mo off for the first 6 months (renewal)", "high", quote))))["concessions"]
    assert len(entry["items"]) == 1, entry["items"]
    assert len(c.parse_concessions(pages)) == 1  # same answer as the regex engine
    print("✓ test_review_ai_restated_concession_counted_once: PASS")


def test_review_non_rent_discounts_and_negations_ignored():
    for text in (
        "Owner provides a utility credit of $50 per month.",
        "Resident may rent a parking space for $50 per month, discounted by $10 per month for a second vehicle.",
        "Resident qualifies for a 10% reduction in the security deposit.",
        "A 5% discount applies for early payment.",
        "Resident shall not receive one month free or any other concession.",
        "Resident is not entitled to a $50 per month discount.",
    ):
        assert _items(text) == [], (text, _items(text))
    # "not in default" is a condition on a real concession, not a negation
    (item,) = _items("Provided Tenant is not then in default under this Agreement, Minimum Rent shall be abated "
                     "for the first three (3) full calendar months following the Rent Commencement Date.")
    assert item["free_months"] == 3
    # a discount that IS about rent still counts even with a fee word nearby
    assert len(_items("Base Rent is reduced by $25.00 per month for the full term; the $10 pet fee is unchanged.")) == 1
    print("✓ test_review_non_rent_discounts_and_negations_ignored: PASS")


def test_review_late_starting_discount_priced_from_its_start():
    items = _items("Base Rent is reduced by $50.00 per month starting in April 2026 as a retention incentive.")
    eff = c.compute_effective_rent(1500.0, items, date(2026, 1, 1), date(2026, 12, 31), AS_OF)
    assert eff["total_concession_value"] == 450.0, eff  # Apr-Dec = 9 months, not 12
    print("✓ test_review_late_starting_discount_priced_from_its_start: PASS")


def test_review_half_month_free_current_rent_is_half():
    items = _items("One-half (1/2) month free rent as a look-and-lease special.")
    eff = c.compute_effective_rent(1200.0, items, date(2026, 8, 1), date(2027, 7, 31), AS_OF)
    assert eff["current_rent"] == 600.0
    print("✓ test_review_half_month_free_current_rent_is_half: PASS")


def test_review_same_shape_different_trigger_not_collapsed():
    pages = [
        {"page": 1, "text": "One (1) month of Base Rent is abated as a move-in incentive."},
        {"page": 2, "text": "RENEWAL ADDENDUM. One (1) month of Base Rent is abated as a renewal incentive."},
    ]
    assert [i["trigger"] for i in c.parse_concessions(pages)] == ["move_in", "renewal"]
    print("✓ test_review_same_shape_different_trigger_not_collapsed: PASS")


# ----------------------------------------------------------------------
# Reviewer round 2 -- the round-1 guards must not drop real concessions
# ----------------------------------------------------------------------

def test_review2_guards_keep_real_concessions():
    cases = {
        "Resident receives a $500 move-in special, and the $150 application fee is waived.": ("one_time_credit", 500.0),
        "Rent is payable in advance on the first day of each month, and a $500 move-in concession will be applied to the first month's rent.": ("one_time_credit", 500.0),
        "The $1,000 concession shall be credited against the last month's rent.": ("one_time_credit", 1000.0),
        "As a move-in incentive, a concession of $600 will be credited toward the final month of the term.": ("one_time_credit", 600.0),
        "The security deposit is $500, and Base Rent is reduced by $50.00 per month for the full term.": ("recurring_discount", 50.0),
    }
    for text, (kind, amount) in cases.items():
        items = _items(text)
        assert len(items) == 1 and items[0]["kind"] == kind, (text, items)
        assert amount in (items[0].get("one_time_amount"), items[0].get("monthly_amount")), (text, items)
    print("✓ test_review2_guards_keep_real_concessions: PASS")


def test_review2_conditional_not_is_a_condition_not_a_negation():
    for text, months in (
        ("Provided Tenant does not default, Tenant shall receive one month free.", 1),
        ("So long as Tenant is not in material default, Base Rent shall be abated for the first two (2) months.", 2),
        ("Provided Tenant is not then in breach of this Lease, Base Rent shall be abated for the first two (2) months.", 2),
        ("Provided Tenant shall not have defaulted, Base Rent shall be abated for the first three (3) months.", 3),
    ):
        items = _items(text)
        assert len(items) == 1 and items[0]["free_months"] == months, (text, items)
    assert _items("Resident shall not receive one month free.") == []
    print("✓ test_review2_conditional_not_is_a_condition_not_a_negation: PASS")


def test_review2_remaining_non_rent_discounts_ignored():
    for text in (
        "Rent paid by the 1st receives a 5% discount; otherwise a late fee applies.",
        "Monthly rent is $1,200 and parking is $50 per month, discounted by $10 per month for a second car.",
        "Pet rent of $25 per month is discounted by $10 per month.",
    ):
        assert _items(text) == [], (text, _items(text))
    print("✓ test_review2_remaining_non_rent_discounts_ignored: PASS")


def test_review2_concession_per_month_header_is_the_amount():
    for header in ("Concession Per Month", "Concession Amt Per Month", "Concession / Mo", "Monthly Concession"):
        result = parse_rent_roll_rows(["Unit", "Tenant", "Rent", header], [["101", "Pat", "1200", "75"]], "rr.csv", "1 Elm St")
        assert result["column_mapping"].get("concessions") == 3, (header, result["column_mapping"])
    print("✓ test_review2_concession_per_month_header_is_the_amount: PASS")


def test_review2_summary_is_none_when_a_concession_is_unreadable():
    unreadable = {"value": "Reduced rent during renovation", "source": None, "confidence": "low"}
    leases = [
        _doc(1, concession_text=I204_TEXT, property_address="1 A St, Suite 1", rent_amount="$1,720.00", **TERM_12),
        {"id": 2, "filename": "b.pdf", "extracted_fields": {**_fields(property_address="1 A St, Suite 2", rent_amount="$1,500.00", **TERM_12), "concessions": unreadable}},
    ]
    assert dm._concession_summary(leases, AS_OF) == {"leases_with_concessions": 2, "annualized_concession_value": None}
    print("✓ test_review2_summary_is_none_when_a_concession_is_unreadable: PASS")


# ----------------------------------------------------------------------
# Reviewer round 3
# ----------------------------------------------------------------------

def test_review3_interest_free_deposit_is_still_not_free_rent():
    for text in (
        "Tenant shall deposit one month's rent, which shall be held interest-free and credited toward the last month's rent.",
        "Tenant shall pay one month's rent as a security deposit, free of interest, to be applied to the last month's rent.",
    ):
        assert _items(text) == [], (text, _items(text))
    print("✓ test_review3_interest_free_deposit_is_still_not_free_rent: PASS")


def test_review3_forfeiture_clauses_are_negations():
    for text in (
        "If Tenant defaults, Tenant shall not be entitled to one month of free rent.",
        "If Resident breaks the lease, Resident will not receive two months free.",
        "Upon any default, Tenant shall not receive the $500 move-in credit.",
        "If this Lease is renewed, Resident will not receive a $50 per month renewal discount.",
        "Even if Resident renews, Resident will not receive two months free.",
    ):
        assert _items(text) == [], (text, _items(text))
    print("✓ test_review3_forfeiture_clauses_are_negations: PASS")


def test_review3_and_clause_and_deposit_credit():
    for text, amount in (
        ("The $150 application fee is waived and residents receive a $50 per month discount for six (6) months.", 50.0),
        ("Resident pays a reduced deposit of $200 and receives $50 per month off for the first six (6) months.", 50.0),
    ):
        (item,) = _items(text)
        assert item["monthly_amount"] == amount and item["months"] == 6, (text, item)
    assert _items("Resident receives a $200 move-in credit, applied toward the security deposit.") == []
    result = parse_rent_roll_rows(["Unit", "Tenant", "Rent", "Concession/Month"], [["101", "Pat", "1200", "75"]], "rr.csv", "1 Elm St")
    assert result["column_mapping"].get("concessions") == 3, result["column_mapping"]
    print("✓ test_review3_and_clause_and_deposit_credit: PASS")


# ----------------------------------------------------------------------
# Reviewer round 4 (non-blocking cleanups)
# ----------------------------------------------------------------------

def test_review4_cleanups():
    for text in (
        "Parking is $50 per month and is discounted by $10 per month for a second car.",
        "Utilities are billed at $100 per month and will be discounted by $20 per month for autopay.",
        "Storage is available and is offered at a $10 per month discount.",
    ):
        assert _items(text) == [], (text, _items(text))
    for text in (
        "Resident receives $50 off rent each month, and any pet fee will be applied toward the security deposit.",
        "Resident receives a $500 move-in credit, and any overpayment will be credited to the deposit.",
        "So long as Tenant is not then in monetary or material non-monetary default, Base Rent shall be abated for the first two (2) months.",
        "Provided Resident is not late with rent, Base Rent is reduced by $50.00 per month for the full term.",
    ):
        assert len(_items(text)) == 1, (text, _items(text))
    result = parse_rent_roll_rows(["Unit", "Tenant", "Rent", "Concessions/Month"], [["101", "Pat", "1200", "75"]], "rr.csv", "1 Elm St")
    assert result["column_mapping"].get("concessions") == 3
    print("✓ test_review4_cleanups: PASS")


if __name__ == "__main__":
    test_parse_single_free_month_with_trigger_and_calendar_month()
    test_parse_recurring_discount_with_duration_and_explicit_range()
    test_parse_full_term_discount()
    test_parse_stacked_concessions_in_one_sentence()
    test_parse_stacked_concessions_across_pages_each_cite_own_page()
    test_parse_restated_concession_counted_once()
    test_parse_ignores_non_concessions()
    test_parse_last_month_free_with_recapture()
    test_parse_percent_discount_reduced_to_and_half_month()
    test_discount_with_no_stated_duration_assumes_full_term_and_says_so()
    test_summary_value_round_trips_through_parser()
    test_effective_rent_free_month_twelve_month_lease()
    test_effective_rent_annualizes_short_lease()
    test_effective_rent_active_concession_current_rent_and_remaining()
    test_effective_rent_stacked_concessions_sum()
    test_effective_rent_unpriceable_is_none_not_zero()
    test_effective_rent_missing_dates_assumes_twelve_months_and_flags_it()
    test_regex_engine_extracts_concessions_field()
    test_ai_engine_concessions_parsed_from_verbatim_quote_with_pages()
    test_ai_engine_unparseable_concession_kept_low_confidence_never_priced_zero()
    test_ai_engine_no_concession_is_not_found()
    test_upload_route_ai_engine_end_to_end_concession_reaches_report()
    test_rent_roll_concession_column_parsed_and_never_read_as_rent()
    test_concession_missing_free_month_annualized_with_citation()
    test_concession_missing_stacked_concessions_sum_and_cite_each_clause()
    test_expiring_concession_rent_roll_shows_gross_flags_missing_and_expiring_soon()
    test_expiring_concession_rent_roll_shows_discounted_rent_flags_burn_off_not_rent_mismatch()
    test_expiring_concession_annual_capped_to_twelve_month_window()
    test_burned_off_concession_with_stale_discounted_rent_roll_is_rent_mismatch()
    test_rent_roll_showing_net_effective_rent_is_not_a_mismatch()
    test_rent_roll_above_base_reports_rent_mismatch_and_concession_separately()
    test_rent_roll_unexplained_below_base_is_rent_mismatch_only()
    test_rent_roll_concession_column_matching_lease_is_clean()
    test_rent_roll_concession_column_smaller_than_lease_is_mismatch_overstate()
    test_rent_roll_concession_lease_does_not_support_is_mismatch_understate()
    test_rent_roll_concession_column_zero_is_concession_missing()
    test_expired_lease_concession_not_double_counted()
    test_unpriceable_concession_reported_with_no_dollar_figure()
    test_reconciliation_uses_effective_rent_too()
    test_report_totals_net_concession_rows_and_summary()
    test_review_deposit_credited_to_last_month_is_not_free_rent()
    test_review_credit_card_fee_is_not_a_credit()
    test_review_rent_roll_concession_date_and_count_columns_not_read_as_dollars()
    test_review_ai_restated_concession_counted_once()
    test_review_non_rent_discounts_and_negations_ignored()
    test_review_late_starting_discount_priced_from_its_start()
    test_review_half_month_free_current_rent_is_half()
    test_review_same_shape_different_trigger_not_collapsed()
    test_review2_guards_keep_real_concessions()
    test_review2_conditional_not_is_a_condition_not_a_negation()
    test_review2_remaining_non_rent_discounts_ignored()
    test_review2_concession_per_month_header_is_the_amount()
    test_review2_summary_is_none_when_a_concession_is_unreadable()
    test_review3_interest_free_deposit_is_still_not_free_rent()
    test_review3_forfeiture_clauses_are_negations()
    test_review3_and_clause_and_deposit_credit()
    test_review4_cleanups()
    print("\nAll concession tests passed.")
