"""
Tests for the Section 811 PRA lease reader (forms/hud_811.py, form
HUD-92236-PRA): the rent blanks are printed in fixed places, so the form
reader reads them and the AI reads the rest of the lease. The fixture is
drawn in-test with reportlab at the form's own label positions. Fictional
values only. NO real Claude calls (the lease AI is replaced with a stub).

Run: python backend/tests/test_affordable_forms_811.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'eval', 'affordable')))

from reportlab.pdfgen import canvas

from app import ai_extraction
from app.affordable import choose_route, extract_document

FILLER = "The parties agree to the terms and conditions of this Agreement set out below in full."

# (page, top, x, text): label positions as printed on HUD-92236-PRA (02/2014)
PAGE_TEXT = [
    (1, 92.7, 180.0, "811 Project Rental Assistance Lease"),
    (1, 110.8, 136.1, "SUPPORTIVE HOUSING FOR PERSONS WITH DISABILITIES"),
    (1, 463.1, 90.0, "the LANDLORD dwelling unit in the project known as"),
    (1, 473.8, 110.0, "Maple Ridge Commons"),
    (1, 474.4, 311.8, "for a term of one year commencing on"),
    (1, 519.7, 159.0, "The total rent (Contract Rent) shall be"),
    (1, 519.7, 398.8, "$"),
    (1, 518.4, 414.7, "900"),
    (1, 519.7, 470.8, "per"),
    (1, 667.1, 90.0, "following utility service(s), for which the Utility Allowance is"),
    (1, 678.4, 90.0, "$"),
    (1, 677.5, 99.5, "60"),
    (1, 678.4, 120.0, "."),
    (2, 140.7, 150.0, "Of the total rent,"),
    (2, 140.7, 263.9, "$"),
    (2, 140.3, 280.1, "$520"),
    (2, 140.7, 329.9, "shall be payable by or at the"),
    (2, 152.3, 90.0, "direction of HUD as project rental assistance payments on behalf of the"),
    (2, 163.7, 90.0, "TENANT, and"),
    (2, 163.7, 162.0, "$"),
    (2, 164.4, 180.7, "380"),
    (2, 163.7, 245.9, "shall be payable by the TENANT. These amounts"),
    (2, 344.7, 90.0, "deposit of"),
    (2, 344.7, 156.0, "$"),
    (2, 343.5, 182.2, "400"),
    (2, 344.7, 275.9, "against any damage except reasonable wear"),
    (2, 735.0, 391.4, "form HUD-92236-PRA (02/2014)"),
]


def _pdf(page_text=PAGE_TEXT):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    for page in (1, 2):
        c.setFont("Courier", 10)
        for p, top, x, text in page_text:
            if p == page:
                c.drawString(x, 792 - top - 6.3, text)
        for i in range(12):        # body text, so no page reads as a blank scan
            c.drawString(90, 792 - 200 - 11.3 * i, FILLER)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_811_lease_rent_blanks_are_read():
    res = extract_document(_pdf())
    assert res["form_id"] == "hud_92236_pra"
    got = {k: v["value"] for k, v in res["program_fields"].items()}
    assert got["project_name"] == "Maple Ridge Commons"
    assert got["contract_rent"] == "$900.00"
    assert got["utility_allowance"] == "$60.00"
    assert got["assistance_payment"] == "$520.00"
    assert got["tenant_rent"] == "$380.00"
    assert got["security_deposit"] == "$400.00"
    assert res["lease_fields"]["rent_amount"]["value"] == "$900.00"
    # HUD pays part of the contract rent and the tenant the rest: the split adds up
    assert any(c["status"] == "ok" and "tenant_rent" in c["fields"] for c in res["checks"])


def test_811_lease_still_goes_to_the_ai_for_the_lease_terms():
    """Parties, dates and clauses are prose; the form reader only reads the blanks."""
    assert choose_route(extract_document(_pdf())) == "ai"


def test_a_split_that_doesnt_add_up_is_flagged_not_changed():
    text = [t if t[3] != "380" else (2, 164.4, 180.7, "330") for t in PAGE_TEXT]
    res = extract_document(_pdf(text))
    f = res["program_fields"]
    assert f["tenant_rent"]["value"] == "$330.00"
    assert f["tenant_rent"]["confidence"] == "low"
    assert "Verify with your PHA" in f["tenant_rent"]["check_note"]


def test_routed_eval_keeps_the_form_reads_beside_the_lease_ai():
    """Regression: on the AI lease path the eval dropped the form reader's
    program fields, so the 811 lease scored 0 / 4 on tenant rent, HUD's
    payment, utility allowance and project."""
    import run_eval
    calls = []

    def fake_lease_ai(pages):
        calls.append(len(pages))
        return {"tenant": {"value": "Alex Example", "source": None, "confidence": "high"},
                "_ai_meta": {"model": "stub"}}

    real = ai_extraction.extract_lease_fields
    ai_extraction.extract_lease_fields = fake_lease_ai
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "lease.pdf"
            path.write_bytes(_pdf())
            out = run_eval.run_pipeline(path, "routed")
    finally:
        ai_extraction.extract_lease_fields = real
    assert calls, out.get("status")
    assert out["fields"]["tenant"]["value"] == "Alex Example"
    assert out["fields"]["rent_amount"]["value"] == "$900.00"        # gap filled from the form reader
    assert out["program_fields"]["tenant_rent"]["value"] == "$380.00"
    assert out["program_fields"]["project_name"]["value"] == "Maple Ridge Commons"


if __name__ == "__main__":
    test_811_lease_rent_blanks_are_read()
    test_811_lease_still_goes_to_the_ai_for_the_lease_terms()
    test_a_split_that_doesnt_add_up_is_flagged_not_changed()
    test_routed_eval_keeps_the_form_reads_beside_the_lease_ai()
    print("\nAll 811 PRA lease tests passed.")
