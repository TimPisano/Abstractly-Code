"""
Tests for filled form boxes saved as a drawing only: a widget with an
appearance stream showing the value but no field name and no value of its
own. A real agency HUD-50059 sample saves project name, effective date,
certification type, unit, TTP, tenant rent and assistance payment this way,
so neither the field reader nor the page text saw them. Fixtures are built
in-test with reportlab + pypdf; fictional values only.

Run: python backend/tests/test_affordable_drawn_widgets.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, TextStringObject
from reportlab.pdfgen import canvas

from app.affordable.acroform import appearance_words, read_acroform
from app.affordable.layout import layout_pages


def _widget(writer, rect, shown, name=None):
    ap = DecodedStreamObject()
    ap.set_data(f"/Tx BMC q BT /Helv 8 Tf 0 g 2 2 Td ({shown}) Tj ET Q EMC".encode("latin-1"))
    ap.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
               NameObject("/BBox"): ArrayObject([FloatObject(0), FloatObject(0),
                                                 FloatObject(rect[2] - rect[0]), FloatObject(rect[3] - rect[1])])})
    annot = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): writer._add_object(ap)}),
    })
    if name:
        annot[NameObject("/T")] = TextStringObject(name)
        annot[NameObject("/FT")] = NameObject("/Tx")
    return writer._add_object(annot)


def _pdf(widgets):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 8)
    c.drawString(31.6, 792 - 100, "1. Project Name")
    c.drawString(400, 792 - 650, "108. Total Tenant Payment")
    c.save()
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(buf.getvalue())))
    page = writer.pages[0]
    page[NameObject("/Annots")] = ArrayObject([_widget(writer, *w) for w in widgets])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_nameless_drawn_values_reach_the_page_layout():
    """Regression: these values were invisible to every reader."""
    data = _pdf([((40, 792 - 112, 220, 792 - 102), "Maple Ridge Apartments"),
                 ((516, 792 - 657, 582, 792 - 647), "400")])
    assert read_acroform(data) == []
    drawn = appearance_words(data)
    assert [t for t, _ in drawn[1]] == ["Maple Ridge Apartments", "400"]
    text = layout_pages(data, ocr=False, include_acroform=True)[0]["text"]
    assert "Maple Ridge Apartments" in text and "400" in text


def test_named_fields_and_restricted_fields_are_not_duplicated_or_read():
    data = _pdf([((40, 792 - 112, 220, 792 - 102), "Maple Ridge Apartments"),
                 ((300, 792 - 112, 380, 792 - 102), "01/02/1990", "BirthDate"),
                 ((300, 792 - 130, 380, 792 - 120), "000-00-0001", "SSN")])
    assert [t for t, _ in appearance_words(data)[1]] == ["Maple Ridge Apartments"]


def test_ssn_shaped_drawn_text_is_masked():
    data = _pdf([((40, 792 - 112, 220, 792 - 102), "000-00-0001")])
    assert "000-00-0001" not in appearance_words(data)[1][0][0]


if __name__ == "__main__":
    test_nameless_drawn_values_reach_the_page_layout()
    test_named_fields_and_restricted_fields_are_not_duplicated_or_read()
    test_ssn_shaped_drawn_text_is_masked()
    print("\nAll drawn-widget tests passed.")
