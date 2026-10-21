"""
Tests for app/affordable/ -- reading HUD / LIHTC forms. No API, no DB.

Fixtures are built in-test with reportlab (fictional values only), plus the
synthetic eval samples in tests/eval/affordable/samples/ for end-to-end
checks. Run: python backend/tests/test_affordable_forms.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from app.affordable import acroform_page_text, extract_document, is_enabled, layout_pages, read_acroform
from app.affordable.layout import Word, chains
from app.affordable.pii import is_restricted_field, mask_ssns
from app.affordable.values import coerce, looks_like_label, parse_date, parse_money

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
EVAL = os.path.join(REPO, "tests", "eval", "affordable")


def _pdf(draw) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    draw(c)
    c.save()
    return buf.getvalue()


def _fillable_pdf(values) -> bytes:
    """A one-page form with three text fields and a checkbox, filled via pypdf and NOT flattened."""
    def draw(c):
        c.setFont("Helvetica", 10)
        c.drawString(72, 700, "Head of Household Name")
        c.acroForm.textfield(name="head_name", tooltip="Head of Household Name", x=72, y=670, width=250, height=20)
        c.drawString(72, 640, "Contract Rent")
        c.acroForm.textfield(name="contract_rent", x=72, y=610, width=120, height=20)
        c.drawString(72, 580, "Social Security Number")
        c.acroForm.textfield(name="member_ssn", x=72, y=550, width=120, height=20)
        c.drawString(72, 520, "Notes")
        c.acroForm.textfield(name="notes", x=72, y=490, width=250, height=20)
        c.acroForm.checkbox(name="elderly", x=72, y=460, size=12, checked=False)
    reader = PdfReader(io.BytesIO(_pdf(draw)))
    writer = PdfWriter(clone_from=reader)
    writer.update_page_form_field_values(writer.pages[0], values, auto_regenerate=False)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ----------------------------------------------------------------------
# values
# ----------------------------------------------------------------------

def test_money_without_dollar_sign():
    # HUD/IRS forms print the "$" in the label and leave it off the value
    assert parse_money("1,325") == 1325.0
    assert parse_money("415,800") == 415800.0
    assert parse_money("$1,325.00") == 1325.0
    assert parse_money("712.00") == 712.0
    assert coerce("1,325", "money") == "$1,325.00"
    assert coerce("no amount here", "money") is None
    print("✓ test_money_without_dollar_sign: PASS")


def test_dates_in_form_formats():
    for raw in ("12/01/2026", "12/1/2026", "December 1, 2026", "Dec. 1, 2026", "2026-12-01", "2026/12/01"):
        assert coerce(raw, "date") == "12/01/2026", raw
    assert parse_date("13/45/2026") is None
    print("✓ test_dates_in_form_formats: PASS")


def test_label_text_is_not_a_value():
    # Values the regex engine returned at "high" confidence in the baseline eval
    for junk in ("Income Certification", "Unit Number: #Bedrooms:", "City or town, state, and ZIP code",
                 "Enter", "_______________", "of unit, including apartment number, if any."):
        assert looks_like_label(junk), junk
        assert coerce(junk, "text") is None, junk
    assert coerce("Renata Quillfeather", "text") == "Renata Quillfeather"
    assert coerce("1450 Maple Ridge Drive, Apt 2B", "text") == "1450 Maple Ridge Drive, Apt 2B"
    # a form's own printed phrase is rejected even when its words aren't generic
    assert looks_like_label("Request for Tenancy Approval", ["Request for Tenancy Approval"])
    print("✓ test_label_text_is_not_a_value: PASS")


def test_pii_guards():
    assert mask_ssns("SSN 123-45-6789 on file") == "SSN [masked] on file"
    assert mask_ssns("123456789") == "[masked]"
    assert mask_ssns("Rent $1,325.00") == "Rent $1,325.00"
    assert is_restricted_field("member_ssn") and is_restricted_field("Date of Birth") and is_restricted_field("head_dob")
    assert not is_restricted_field("contract_rent")
    print("✓ test_pii_guards: PASS")


def test_identifier_fields_keep_nine_digit_numbers():
    # regression: a REMS property ID ("800091733") was masked as an SSN
    assert mask_ssns("800091733", identifier_field=True) == "800091733"
    assert mask_ssns("123-45-6789", identifier_field=True) == "[masked]", "dashed SSN shapes are always masked"
    assert mask_ssns("800091733") == "[masked]", "outside ID fields a bare 9-digit number is treated as an SSN"
    from app.affordable.pii import is_identifier_field
    assert is_identifier_field("REMS Property ID") and is_identifier_field("contract_number")
    assert not is_identifier_field("Notes") and not is_identifier_field("bank account")
    print("✓ test_identifier_fields_keep_nine_digit_numbers: PASS")


def test_a_date_is_not_a_name():
    # regression: signatory fields on unflattened PBV contracts returned their dates
    assert coerce("06/24/2027", "text") is None
    assert coerce("June 24, 2027", "text") is None
    assert coerce("800091733", "text") == "800091733", "digit-only IDs are still valid text"
    assert coerce("Cedar Hollow: Housing LP", "text") == "Cedar Hollow Housing LP", "stray OCR colon removed"
    print("✓ test_a_date_is_not_a_name: PASS")


def test_values_typed_over_underscore_blanks():
    # regression: "Name ________" filled with a value came out as "C ed a r H o ll ow"
    def draw(c):
        c.setFont("Helvetica", 10)
        c.drawString(72, 700, "Property Name: ______________________________")
        c.drawString(160, 701, "Cedar Hollow Apartments")
    words = [w.text for w in __import__("app.affordable.layout", fromlist=["read_layout"]).read_layout(_pdf(draw))[0].words]
    assert "Cedar" in words and "Hollow" in words and "Apartments" in words, words
    print("✓ test_values_typed_over_underscore_blanks: PASS")


def test_flag_defaults_off():
    old = os.environ.pop("AFFORDABLE_FORMS_MODE", None)
    try:
        assert is_enabled() is False
        os.environ["AFFORDABLE_FORMS_MODE"] = "true"
        assert is_enabled() is True
    finally:
        os.environ.pop("AFFORDABLE_FORMS_MODE", None)
        if old is not None:
            os.environ["AFFORDABLE_FORMS_MODE"] = old
    print("✓ test_flag_defaults_off: PASS")


# ----------------------------------------------------------------------
# fillable (AcroForm) fields
# ----------------------------------------------------------------------

def test_reads_unflattened_form_values():
    data = _fillable_pdf({"head_name": "Dana Example", "contract_rent": "1,045.00",
                          "member_ssn": "123-45-6789", "notes": "Call 987-65-4321 first"})
    # The bug this fixes: pypdf's page text (what document_extractor uses) has none of the values
    text = PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "Dana Example" not in text and "1,045.00" not in text

    values = {v.name: v for v in read_acroform(data)}
    assert values["head_name"].value == "Dana Example"
    assert values["head_name"].label == "Head of Household Name"   # tooltip is used as the label
    assert values["contract_rent"].value == "1,045.00"
    assert "member_ssn" not in values, "SSN fields are never read"
    assert values["notes"].value == "Call [masked] first", "SSN-shaped values are masked"
    assert "elderly" not in values, "unticked boxes are skipped"

    page_text = acroform_page_text(list(values.values()))[1]
    assert "Head of Household Name: Dana Example" in page_text
    print("✓ test_reads_unflattened_form_values: PASS")


def test_layout_pages_include_form_values():
    data = _fillable_pdf({"head_name": "Dana Example", "contract_rent": "1,045.00"})
    text = layout_pages(data)[0]["text"]
    assert "Dana Example" in text and "1,045.00" in text
    assert "Dana Example" not in layout_pages(data, include_acroform=False)[0]["text"]
    print("✓ test_layout_pages_include_form_values: PASS")


# ----------------------------------------------------------------------
# layout
# ----------------------------------------------------------------------

def test_reading_order_puts_value_beside_label():
    def draw(c):
        c.setFont("Helvetica", 10)
        # labels first, values last in the content stream -- how filled forms are built
        c.drawString(72, 700, "Tenant Name:")
        c.drawString(72, 680, "Contract Rent:")
        c.drawString(160, 700, "Jordan Example")
        c.drawString(160, 680, "$1,325.00")
    data = _pdf(draw)
    lines = [" ".join(line.split()) for line in layout_pages(data)[0]["text"].splitlines()]
    assert "Tenant Name: Jordan Example" in lines, lines
    assert "Contract Rent: $1,325.00" in lines, lines
    print("✓ test_reading_order_puts_value_beside_label: PASS")


def test_chains_follow_a_skewed_line():
    # one label drifting 1.5pt per word, like a scan tilted ~0.6 degrees
    words = [Word(t, 100 + 50 * i, 140 + 50 * i, 300 + 1.5 * i, 310 + 1.5 * i)
             for i, t in enumerate(["Print", "or", "Type", "Name", "of", "Household", "Head"])]
    words.append(Word("Elsewhere", 100, 160, 400, 410))
    found = [c for c in chains(words) if c[0].text == "Print"]
    assert found and [w.text for w in found[0]] == ["Print", "or", "Type", "Name", "of", "Household", "Head"]
    print("✓ test_chains_follow_a_skewed_line: PASS")


# ----------------------------------------------------------------------
# end to end
# ----------------------------------------------------------------------

def test_unrecognised_document_returns_nothing():
    def draw(c):
        c.setFont("Helvetica", 11)
        c.drawString(72, 700, "COMMERCIAL LEASE AGREEMENT")
        c.drawString(72, 680, "This Lease is made between Landlord and Tenant for the Premises.")
    res = extract_document(_pdf(draw))
    assert res["form_id"] is None
    assert all(v["value"] is None for v in res["lease_fields"].values())
    assert res["program_fields"] == {}
    print("✓ test_unrecognised_document_returns_nothing: PASS")


def _key(doc_id):
    with open(os.path.join(EVAL, "samples", f"{doc_id}.answer_key.json")) as f:
        return json.load(f)


def test_rfta_sample_flattened_and_unflattened():
    key = _key("hud_52517_rfta")
    for name in ("hud_52517_rfta.pdf", "hud_52517_rfta.acroform.pdf"):
        res = extract_document(os.path.join(EVAL, "samples", name))
        assert res["form_id"] == "hud_52517", name
        lf = res["lease_fields"]
        assert lf["tenant"]["value"] == key["lease_fields"]["tenant"], name
        assert lf["landlord"]["value"] == key["lease_fields"]["landlord"], name
        assert lf["rent_amount"]["value"] == "$1,325.00", name
        assert lf["security_deposit"]["value"] == "$1,000.00", name
        assert lf["lease_start_date"]["value"] == "12/01/2026", name
        assert lf["property_address"]["value"] == key["lease_fields"]["property_address"], name
        assert lf["lease_end_date"]["value"] is None, "the RFTA states no lease end"
        assert res["program_fields"]["pha_name"]["value"] == "Riverbend Housing Authority", name
    acro = extract_document(os.path.join(EVAL, "samples", "hud_52517_rfta.acroform.pdf"))
    assert acro["had_form_fields"] and acro["program_fields"]["proposed_rent"]["method"] == "acroform"
    print("✓ test_rfta_sample_flattened_and_unflattened: PASS")


if __name__ == "__main__":
    test_money_without_dollar_sign()
    test_dates_in_form_formats()
    test_label_text_is_not_a_value()
    test_pii_guards()
    test_identifier_fields_keep_nine_digit_numbers()
    test_a_date_is_not_a_name()
    test_values_typed_over_underscore_blanks()
    test_flag_defaults_off()
    test_reads_unflattened_form_values()
    test_layout_pages_include_form_values()
    test_reading_order_puts_value_beside_label()
    test_chains_follow_a_skewed_line()
    test_unrecognised_document_returns_nothing()
    test_rfta_sample_flattened_and_unflattened()
    print("\nAll affordable form tests passed.")
