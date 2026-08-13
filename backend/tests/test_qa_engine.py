"""
Tests for the grounded Q&A engine (app/qa_engine.py).

Fixtures are hand-built lease records rather than real PDF extractions, so
the expected answers can be checked against exact known values (no
dependence on extraction accuracy, which test_synthetic_accuracy.py covers
separately). Expiration dates are computed relative to date.today() so the
"expiring in the next N months" tests stay correct whenever they are run.

The most important assertion in this file is the grounding check: every
citation returned by every answered question must match, byte for byte, the
`source` dict actually stored on the field it claims to cite. That is the
property that makes this a rule engine rather than a text generator.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.qa_engine import answer_question


def _field(value, page=None, quote=None, confidence=None):
    """A field entry in the extracted_fields shape; source omitted when null."""
    if value is None:
        return {"value": None, "source": None, "confidence": None}
    return {
        "value": value,
        "source": {"page": page, "quote": quote},
        "confidence": confidence or "high",
    }


def _days_out(days):
    """A display-string date N days from today, in the extractor's format."""
    target = date.today() + timedelta(days=days)
    return f"{target.strftime('%B')} {target.day}, {target.year}"


def _lease(lease_id, filename, fields):
    """Wraps a partial field dict into a full 15-field lease record."""
    all_keys = [
        "tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date",
        "property_address", "security_deposit", "cam_charges", "rent_escalation",
        "renewal_options", "permitted_use", "exclusivity_clause",
        "insurance_requirements", "default_cure_period", "square_footage",
    ]
    extracted = {key: fields.get(key, _field(None)) for key in all_keys}
    return {
        "id": lease_id,
        "filename": filename,
        "uploaded_at": "2026-08-01T10:00:00Z",
        "document_type": "lease",
        "base_lease_id": None,
        "amendment_count": 0,
        "extracted_fields": extracted,
    }


# --- Fixtures -------------------------------------------------------------
# retail: expires in ~3 months, has CAM + exclusivity + square footage
RETAIL = _lease(1, "retail_lease.pdf", {
    "tenant": _field("Blue Sky Coffee Roasters, Inc.", 1, 'Blue Sky Coffee Roasters, Inc. ("Tenant")'),
    "landlord": _field("Marketplace Holdings LLC", 1, 'Marketplace Holdings LLC ("Landlord")'),
    "rent_amount": _field("$6,250.00", 2, "base rent in the sum of $6,250.00 per month"),
    "lease_end_date": _field(_days_out(90), 2, f"shall terminate on {_days_out(90)}"),
    "cam_charges": _field("$850.00", 3, "common area maintenance charges of $850.00 per month"),
    "security_deposit": _field("$12,500.00", 3, "deposit of $12,500.00 upon execution"),
    "exclusivity_clause": _field(
        "Landlord shall not lease to another coffee retailer in the center", 4,
        "Landlord shall not lease to another coffee retailer in the center",
        "medium",
    ),
    "square_footage": _field("2,400 sq ft", 1, "approximately 2,400 sq ft of retail space"),
})

# office: expires in ~18 months (outside a 12-month window), no exclusivity
OFFICE = _lease(2, "office_lease.pdf", {
    "tenant": _field("Harborview Analytics LLC", 1, 'Harborview Analytics LLC ("Tenant")'),
    "rent_amount": _field("$9,000.00", 2, "monthly rent of $9,000.00"),
    "lease_end_date": _field(_days_out(540), 2, f"expiring {_days_out(540)}"),
    "cam_charges": _field("$1,200.00", 3, "CAM charges estimated at $1,200.00 per month"),
    "insurance_requirements": _field("$2,000,000 per occurrence", 5, "not less than $2,000,000 per occurrence"),
    "square_footage": _field("3,000 sq ft", 1, "3,000 sq ft on the fourth floor"),
})

# sublease: expires in ~200 days (inside a 12-month window), no CAM, no sqft
SUBLEASE = _lease(3, "casual_sublease.pdf", {
    "tenant": _field("Jordan Blake", 1, "the tenant is Jordan Blake", "medium"),
    "rent_amount": _field("$2,000.00", 1, "rent is $2,000.00 a month"),
    "lease_end_date": _field(_days_out(200), 1, f"through {_days_out(200)}"),
})

# warehouse: no expiration date on file at all, no CAM
WAREHOUSE = _lease(4, "warehouse_lease.pdf", {
    "tenant": _field("Ridgeline Logistics LP", 1, 'Ridgeline Logistics LP ("Tenant")'),
    "rent_amount": _field("$4,000.00", 2, "the sum of $4,000.00 per month"),
    "square_footage": _field("5,000 sq ft", 1, "5,000 sq ft warehouse"),
})

PORTFOLIO = [RETAIL, OFFICE, SUBLEASE, WAREHOUSE]
BY_ID = {lease["id"]: lease for lease in PORTFOLIO}


def _assert_citations_grounded(result):
    """
    Every citation must trace back to a real stored source on the exact field
    it names — the anti-hallucination guarantee this module exists to provide.
    """
    for citation in result["citations"]:
        lease = BY_ID[citation["lease_id"]]
        assert citation["filename"] == lease["filename"], "citation filename mismatch"
        stored = lease["extracted_fields"][citation["field"]]["source"]
        assert stored is not None, f"citation cites a field with no stored source: {citation}"
        assert citation["page"] == stored["page"], f"fabricated page in {citation}"
        assert citation["quote"] == stored["quote"], f"fabricated quote in {citation}"


def test_list_expiring_next_year():
    result = answer_question("which leases expire in the next year", PORTFOLIO)

    assert result["matched_intent"] == "list_expiring"
    assert result["confidence"] == "answered"
    assert "retail_lease.pdf" in result["answer"]
    assert "casual_sublease.pdf" in result["answer"]
    assert "office_lease.pdf" not in result["answer"], "18-month lease should be outside a 12-month window"
    assert len(result["citations"]) == 2
    assert {c["lease_id"] for c in result["citations"]} == {1, 3}
    assert all(c["field"] == "lease_end_date" for c in result["citations"])
    # The lease with no end date must be reported as excluded, not silently dropped
    assert "1 lease(s) excluded" in result["answer"]
    _assert_citations_grounded(result)
    print("✓ test_list_expiring_next_year: PASS")


def test_list_expiring_six_months():
    """A tighter window must drop the ~200-day lease but keep the ~90-day one."""
    result = answer_question("which leases are expiring in the next 6 months", PORTFOLIO)

    assert result["matched_intent"] == "list_expiring"
    assert "retail_lease.pdf" in result["answer"]
    assert "casual_sublease.pdf" not in result["answer"]
    assert len(result["citations"]) == 1
    _assert_citations_grounded(result)
    print("✓ test_list_expiring_six_months: PASS")


def test_total_cam_exposure():
    result = answer_question("what's our total CAM exposure", PORTFOLIO)

    assert result["matched_intent"] == "aggregate_sum"
    assert result["confidence"] == "answered"
    assert "$2,050.00" in result["answer"], result["answer"]
    assert "2 of 4" in result["answer"], result["answer"]
    # Leases missing CAM are excluded from the math but named in the answer
    assert "casual_sublease.pdf" in result["answer"]
    assert "warehouse_lease.pdf" in result["answer"]
    assert {c["lease_id"] for c in result["citations"]} == {1, 2}
    assert all(c["field"] == "cam_charges" for c in result["citations"])
    _assert_citations_grounded(result)
    print("✓ test_total_cam_exposure: PASS")


def test_aggregate_with_no_data_does_not_fabricate_zero():
    """A field null on every lease must read as missing data, never as $0.00."""
    result = answer_question("what's our total CAM exposure", [SUBLEASE, WAREHOUSE])

    assert result["matched_intent"] == "aggregate_sum"
    assert result["confidence"] == "partial"
    assert "$0" not in result["answer"], result["answer"]
    assert "not a value of zero" in result["answer"]
    assert result["citations"] == []
    print("✓ test_aggregate_with_no_data_does_not_fabricate_zero: PASS")


def test_average_rent():
    result = answer_question("what is the average rent across the portfolio", PORTFOLIO)

    assert result["matched_intent"] == "aggregate_avg"
    assert result["confidence"] == "answered"
    # (6250 + 9000 + 2000 + 4000) / 4 = 5312.50
    assert "$5,312.50" in result["answer"], result["answer"]
    assert "4 of 4" in result["answer"]
    assert len(result["citations"]) == 4
    _assert_citations_grounded(result)
    print("✓ test_average_rent: PASS")


def test_average_rent_per_square_foot():
    result = answer_question("what's the average rent per square foot", PORTFOLIO)

    assert result["matched_intent"] == "aggregate_avg"
    # (6250/2400 + 9000/3000 + 4000/5000) / 3 = 2.1348...
    assert "$2.13/sq ft" in result["answer"], result["answer"]
    assert "3 of 4" in result["answer"], result["answer"]
    # Both inputs of the ratio are cited so a human can verify the math
    cited_fields = {c["field"] for c in result["citations"]}
    assert cited_fields == {"rent_amount", "square_footage"}
    _assert_citations_grounded(result)
    print("✓ test_average_rent_per_square_foot: PASS")


def test_exclusivity_lookup_single_lease_yes():
    result = answer_question("does this lease have an exclusivity clause", [RETAIL])

    assert result["matched_intent"] == "field_lookup"
    assert result["confidence"] == "answered"
    assert result["answer"].startswith("Yes"), result["answer"]
    assert "another coffee retailer" in result["answer"]
    assert "medium" in result["answer"], "extraction confidence should be surfaced"
    assert len(result["citations"]) == 1
    assert result["citations"][0]["field"] == "exclusivity_clause"
    assert result["citations"][0]["page"] == 4
    _assert_citations_grounded(result)
    print("✓ test_exclusivity_lookup_single_lease_yes: PASS")


def test_exclusivity_lookup_single_lease_no():
    result = answer_question("does this lease have an exclusivity clause", [OFFICE])

    assert result["matched_intent"] == "field_lookup"
    assert result["confidence"] == "partial"
    assert result["answer"].startswith("No"), result["answer"]
    assert "does not have an exclusivity clause on file" in result["answer"]
    assert result["citations"] == [], "a not-found answer must not carry a citation"
    print("✓ test_exclusivity_lookup_single_lease_no: PASS")


def test_field_lookup_by_tenant_name_across_portfolio():
    result = answer_question("what is the rent for Blue Sky Coffee", PORTFOLIO)

    assert result["matched_intent"] == "field_lookup"
    assert result["confidence"] == "answered"
    assert "$6,250.00" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["lease_id"] == 1
    assert result["citations"][0]["field"] == "rent_amount"
    _assert_citations_grounded(result)
    print("✓ test_field_lookup_by_tenant_name_across_portfolio: PASS")


def test_field_lookup_ambiguous_scope_asks_rather_than_guesses():
    result = answer_question("what is the security deposit", PORTFOLIO)

    assert result["matched_intent"] == "field_lookup"
    assert result["confidence"] == "partial"
    assert "couldn't tell which" in result["answer"]
    assert result["citations"] == []
    print("✓ test_field_lookup_ambiguous_scope_asks_rather_than_guesses: PASS")


def test_counts():
    total = answer_question("how many leases do we have", PORTFOLIO)
    assert total["matched_intent"] == "count"
    assert "4 lease(s)" in total["answer"], total["answer"]
    _assert_citations_grounded(total)

    expiring = answer_question("how many leases expire in the next 12 months", PORTFOLIO)
    assert expiring["matched_intent"] == "count"
    assert expiring["answer"].startswith("2 of 4"), expiring["answer"]
    assert "no expiration date on file" in expiring["answer"]
    _assert_citations_grounded(expiring)
    print("✓ test_counts: PASS")


def test_unsupported_questions_are_honest():
    for question in [
        "should we renegotiate before the market shifts?",
        "what is the cap rate on this portfolio?",
        "",
    ]:
        result = answer_question(question, PORTFOLIO)
        assert result["confidence"] == "unsupported", f"{question!r} -> {result}"
        assert result["matched_intent"] is None
        assert result["citations"] == []
        assert result["answer"] == "I don't have a way to answer that question yet."
    print("✓ test_unsupported_questions_are_honest: PASS")


def test_no_citation_is_ever_fabricated_across_all_intents():
    """Sweep every supported phrasing and re-verify grounding on each answer."""
    questions = [
        "which leases expire in the next year",
        "which leases expire this year",
        "what's our total CAM exposure",
        "total monthly rent",
        "average security deposit",
        "average rent per square foot",
        "how many leases do we have",
        "how many leases have CAM charges",
        "what is the rent for Blue Sky Coffee",
        "when does the retail_lease.pdf lease expire",
        "what is the insurance requirement for Harborview Analytics",
        "does Ridgeline Logistics have an exclusivity clause",
    ]
    for question in questions:
        result = answer_question(question, PORTFOLIO)
        assert result["confidence"] in ("answered", "partial"), f"{question!r} -> {result}"
        _assert_citations_grounded(result)
    print("✓ test_no_citation_is_ever_fabricated_across_all_intents: PASS")


def test_empty_portfolio_does_not_crash():
    for question in ["which leases expire in the next year", "total rent", "how many leases do we have"]:
        result = answer_question(question, [])
        assert isinstance(result["answer"], str) and result["answer"]
        assert result["citations"] == []
    print("✓ test_empty_portfolio_does_not_crash: PASS")


if __name__ == "__main__":
    test_list_expiring_next_year()
    test_list_expiring_six_months()
    test_total_cam_exposure()
    test_aggregate_with_no_data_does_not_fabricate_zero()
    test_average_rent()
    test_average_rent_per_square_foot()
    test_exclusivity_lookup_single_lease_yes()
    test_exclusivity_lookup_single_lease_no()
    test_field_lookup_by_tenant_name_across_portfolio()
    test_field_lookup_ambiguous_scope_asks_rather_than_guesses()
    test_counts()
    test_unsupported_questions_are_honest()
    test_no_citation_is_ever_fabricated_across_all_intents()
    test_empty_portfolio_does_not_crash()
    print("\nAll Q&A engine tests passed.")
