"""
South Carolina Housing Tenant Income Certification (2024), the national
two-page TIC layout. No AcroForm: every position is found on the blank
source PDF (labels, table rows, checkbox squares), so the same builder
also fills the Louisiana (tic_la_lhc) and New Jersey (tic_nj_scan) copies
of this layout, which shift it by a few points.

Household: initial certification, 3 people, 2BR at 60% AMI, no rental
assistance. All people, places and numbers are fictional (see world.py).
"""

import sys
from pathlib import Path

import pdfplumber

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from world import Household, LihtcCert, Member, num  # noqa: E402


# ---------------------------------------------------------------------------
# locating things on the blank national-TIC layout
# ---------------------------------------------------------------------------

def _pick(page, phrase, xmin=0, xmax=9999, ymin=0, ymax=9999):
    hits = [m for m in page.search(phrase, regex=False, case=True)
            if xmin <= m["x0"] <= xmax and ymin <= m["top"] <= ymax]
    if not hits:
        raise LookupError(f"{phrase!r} not found on page {page.page_number} in x[{xmin},{xmax}] y[{ymin},{ymax}]")
    return hits[0]


def _box_near(page, label, side="left"):
    """Checkbox square (drawn rect or a '□' glyph) just left/right of a label."""
    mid = (label["top"] + label["bottom"]) / 2
    cands = [(r["x0"], r["top"], r["x1"] - r["x0"], r["bottom"] - r["top"])
             for r in page.rects
             if 6 < r["width"] < 14 and 6 < r["height"] < 14 and abs(r["width"] - r["height"]) < 2.5]
    # An OCR'd '□' glyph's box runs lower than the visible square on the scan:
    # treat it as a 9pt square starting 2.5pt above the glyph's top.
    cands += [(c["x0"], c["top"] - 2.5, c["x1"] - c["x0"], 9.0) for c in page.chars if c["text"] == "□"]
    def ok(c):
        x0, top, w, h = c
        if not (top - 4 <= mid <= top + h + 4):
            return False
        if side == "left":
            return label["x0"] - 26 <= x0 + w <= label["x0"] + 1
        return label["x1"] - 1 <= x0 <= label["x1"] + 22
    cands = [c for c in cands if ok(c)]
    if not cands:
        # fall back to the usual offset of this layout
        x0 = label["x0"] - 14.5 if side == "left" else label["x1"] + 3
        return x0, label["top"] - 0.5, 8.8, 8.8
    cands.sort(key=lambda c: abs((c[0] + c[2]) - label["x0"]) if side == "left" else abs(c[0] - label["x1"]))
    return cands[0]


def _x_in(box):
    x0, top, w, h = box
    return (x0 + (w - 5.3) / 2, top + (h - 8) / 2 - 0.5)


def _dollar_after(page, label):
    """The '$' printed after a rent label (same row, or offset a few points on wrapped labels)."""
    mid = (label["top"] + label["bottom"]) / 2
    ds = [c for c in page.chars if c["text"] == "$" and label["x1"] - 2 <= c["x0"] <= label["x1"] + 60
          and abs((c["top"] + c["bottom"]) / 2 - mid) < 10]
    if not ds:
        raise LookupError(f"no '$' after {label}")
    ds.sort(key=lambda c: c["x0"])
    return ds[0]


def national_tic_spec(d):
    """Build a SPEC from household data `d` for any copy of the national TIC layout."""
    src = HERE / "sources" / d["source"]
    P = []                       # placements
    with pdfplumber.open(str(src)) as pdf:
        p1, p2 = pdf.pages[0], pdf.pages[1]

        def at(page_no, x, top, text, size=9):
            P.append({"at": (round(x, 1), round(top, 1)), "page": page_no, "text": text, "size": size})

        def right_of(page_no, page, phrase, text, dx=0, **kw):
            m = _pick(page, phrase, **kw)
            at(page_no, m["x1"] + 4 + dx, m["top"] - 2.5, text)

        def check(page_no, page, phrase, side="left", **kw):
            x, top = _x_in(_box_near(page, _pick(page, phrase, **kw), side))
            at(page_no, x, top, "X", size=8)

        # -- header ----------------------------------------------------------
        check(1, p1, d["cert_type"], ymax=60)
        right_of(1, p1, "Effective Date:", d["effective_date"])
        right_of(1, p1, "Initial LIHTC Qualification Date:", d["initial_qual_date"], dx=d.get("qual_dx", 0))
        right_of(1, p1, "Move-in Date:", d["move_in_date"])
        # -- Part I ----------------------------------------------------------
        right_of(1, p1, "Property Name:", d["property_name"])
        right_of(1, p1, "County:", d["county"])
        right_of(1, p1, "BIN #:", d["bin"])
        right_of(1, p1, "Address:", d["address"], ymax=120)
        right_of(1, p1, "Unit Number:", d["unit"])
        right_of(1, p1, "#Bedrooms:", str(d["bedrooms"]))
        # -- Part II: household rows ----------------------------------------
        rows = p1.search("FT / PT", regex=False)
        x_last = _pick(p1, "Last Name")["x0"] - 36
        x_first = _pick(p1, "First Name")["x0"] - 2
        x_rel = _pick(p1, "Relationship")["x0"] - 5
        x_dob = _pick(p1, "(MM/DD/YYYY)")["x0"] + 2
        for i, m in enumerate(d["hh"].members):
            top = rows[i]["top"] - 0.5
            at(1, x_last, top, m.last, 8)
            at(1, x_first, top, m.first, 8)
            at(1, x_rel, top, m.relationship, 8)
            at(1, x_dob, top, m.dob, 8)
        # -- Part III: income rows and totals --------------------------------
        totals = _pick(p1, "TOTALS")
        dollars = sorted((c for c in p1.chars if c["text"] == "$" and abs(c["top"] - totals["top"]) < 2),
                         key=lambda c: c["x0"])
        cols = [c["x0"] + 9 for c in dollars]       # (A) (B) (C) (D)
        first_row = _pick(p1, "Security/Pensions")["bottom"] + 2.0
        for r, (mbr, amounts) in enumerate(d["income_rows"]):
            top = first_row + 11.25 * r
            at(1, totals["x0"] + 8, top, str(mbr), 8)
            for col, amt in zip(cols, amounts):
                if amt:
                    at(1, col, top, num(amt), 8)
        for col, amt in zip(cols, d["income_totals"]):
            at(1, col, totals["top"] - 1.5, num(amt), 8)
        right_of(1, p1, "Total Income (E): $", num(d["total_e"]))
        right_of(1, p1, "Assets (F) $", num(d["asset_income"]))
        right_of(1, p1, "(E) + (M)] $", num(d["hh"].annual_income))
        # -- household signatures (typed names stand in for signatures) ----
        sigs = [m for m in p1.search("Signature", regex=False) if m["top"] > 650]
        dates = [m for m in p1.search("Date", regex=False) if m["top"] > 650]
        sigs.sort(key=lambda m: (round(m["top"]), m["x0"]))
        dates.sort(key=lambda m: (round(m["top"]), m["x0"]))
        for (name, signed), sig, date_lbl in zip(d["household_signatures"], sigs, dates):
            at(1, sig["x0"] + 3, sig["top"] - 17, name)
            at(1, date_lbl["x0"] + 3, date_lbl["top"] - 17, signed)

        # -- Part VI ----------------------------------------------------------
        right_of(2, p2, "FROM ALL SOURCES: $", num(d["hh"].annual_income))
        right_of(2, p2, "Family Size: $", num(d["income_limit"]))
        right_of(2, p2, "Household Income at Move-in: $", num(d["income_at_move_in"]))
        right_of(2, p2, "Household Size at Move-in:", str(d["size_at_move_in"]), dx=6)
        check(2, p2, f"{d['designated_pct']}%", xmin=260, xmax=370, ymin=80, ymax=170)
        if d.get("recert_140") is not None:
            right_of(2, p2, "Deep Rent Skewing): $", num(d["recert_140"]))
            check(2, p2, "No", xmin=420, ymin=160, ymax=190)
        # -- Part VII: rent ---------------------------------------------------
        for phrase, amount in (("Tenant Rent:", d["tenant_rent"]), ("Utility Allowance:", d["ua"]),
                               ("Rental Assistance:", d["assistance"]), ("fees:", d["other_fees"]),
                               ("Instructions):", d["gross_rent"])):
            dollar = _dollar_after(p2, _pick(p2, phrase, xmax=260, ymin=190, ymax=350))
            at(2, dollar["x1"] + 3, dollar["top"] - 2.5, num(amount))
        if d.get("max_rent") is not None:
            right_of(2, p2, "Maximum Rent Limit $", num(d["max_rent"]))
        check(2, p2, f"{d['designated_pct']}%", xmin=380, ymin=200, ymax=340)
        if d["assistance"]:
            check(2, p2, "Yes", xmin=150, xmax=330, ymin=340, ymax=365)
            check(2, p2, d["assistance_source"], ymin=360, ymax=430)
        # -- Part VIII / IX / owner signature ---------------------------------
        check(2, p2, "No", xmin=80, xmax=200, ymin=470, ymax=500)
        check(2, p2, d["program_label"], side="right", xmax=150, ymin=540, ymax=575)
        owner_sig = _pick(p2, "Owner/representative Signature")
        at(2, owner_sig["x0"] + 3, owner_sig["top"] - 17, d["owner_rep"])
        owner_date = _pick(p2, "Date", ymin=owner_sig["top"] - 3, ymax=owner_sig["top"] + 3)
        at(2, owner_date["x0"] + 3, owner_date["top"] - 17, d["owner_signed"])

    hh = d["hh"]
    head = hh.head
    program_fields = {
        "certification_type": {"value": d["cert_type"], "type": "checkbox"},
        "effective_date": {"value": d["effective_date"], "type": "date"},
        "initial_qualification_date": {"value": d["initial_qual_date"], "type": "date"},
        "move_in_date": {"value": d["move_in_date"], "type": "date"},
        "property_name": {"value": d["property_name"], "type": "text"},
        "county": {"value": d["county"], "type": "text"},
        "bin": {"value": d["bin"], "type": "text"},
        "building_address": {"value": d["address"], "type": "text"},
        "unit_number": {"value": d["unit"], "type": "text"},
        "bedrooms": {"value": str(d["bedrooms"]), "type": "int"},
        "household_size": {"value": str(hh.size), "type": "int"},
        "head_of_household": {"value": head.name, "type": "text"},
        "total_employment_income": {"value": f"${d['income_totals'][0]:,}", "type": "money"},
        "total_ss_pension_income": {"value": f"${d['income_totals'][1]:,}", "type": "money"},
        "total_other_income": {"value": f"${d['income_totals'][3]:,}", "type": "money"},
        "asset_income": {"value": f"${d['asset_income']:,}", "type": "money"},
        "total_annual_income": {"value": f"${hh.annual_income:,}", "type": "money"},
        "income_limit": {"value": f"${d['income_limit']:,}", "type": "money"},
        "designated_income_restriction_pct": {"value": f"{d['designated_pct']}%", "type": "checkbox"},
        "household_income_at_move_in": {"value": f"${d['income_at_move_in']:,}", "type": "money"},
        "household_size_at_move_in": {"value": str(d["size_at_move_in"]), "type": "int"},
        "tenant_paid_rent": {"value": f"${d['tenant_rent']:,}", "type": "money"},
        "utility_allowance": {"value": f"${d['ua']:,}", "type": "money"},
        "rental_assistance": {"value": f"${d['assistance']:,}", "type": "money"},
        "other_non_optional_fees": {"value": f"${d['other_fees']:,}", "type": "money"},
        "gross_rent": {"value": f"${d['gross_rent']:,}", "type": "money"},
        "program": {"value": d["program_label"], "type": "checkbox"},
    }
    # Members' names are split across Last / First columns, so the key holds
    # the parts as printed; the head's full name is covered by the signature.
    for i, m in enumerate(hh.members, start=1):
        program_fields[f"member_{i}_last_name"] = {"value": m.last, "type": "text"}
        program_fields[f"member_{i}_first_name"] = {"value": m.first, "type": "text"}
        program_fields[f"member_{i}_relationship"] = {"value": m.relationship, "type": "text"}
        program_fields[f"member_{i}_dob"] = {"value": m.dob, "type": "date"}
    # A $0 line is real on the form but proves nothing in a text search.
    for k in [k for k, v in program_fields.items() if v["type"] == "money" and v["value"] == "$0"]:
        del program_fields[k]
    if d.get("max_rent") is not None:
        program_fields["maximum_rent_limit"] = {"value": f"${d['max_rent']:,}", "type": "money"}
    if d.get("recert_140") is not None:
        program_fields["designated_limit_x_140"] = {"value": f"${d['recert_140']:,}", "type": "money"}
    if d["assistance"]:
        program_fields["assistance_source"] = {"value": d["assistance_source"], "type": "checkbox"}

    return {
        "id": d["id"],
        "source": d["source"],
        "form": d["form"],
        "program": "LIHTC",
        "doc_type": "tic",
        "notes": d["notes"],
        "placements": P,
        "lease_fields": {
            "tenant": head.name,
            "landlord": None,               # the TIC has no owner-name field
            "rent_amount": f"${d['tenant_rent']:,}",
            "lease_start_date": None,       # move-in date is not a lease term
            "lease_end_date": None,
            "property_address": d["address"],
            "security_deposit": None,
        },
        "program_fields": program_fields,
    }


# ---------------------------------------------------------------------------
# South Carolina sample
# ---------------------------------------------------------------------------

_hh = Household(
    members=[
        Member("Marguerite", "Ashdown", "Head", 34, "04/17/1992", annual_wages=33_800),
        Member("Felix", "Ashdown", "Child", 9, "08/02/2017"),
        Member("Iris", "Ashdown", "Child", 6, "01/23/2020"),
    ],
    assets_cash_value=1_850,
    imputed_asset_income=9,
)
_child_support = 2_400
# child support goes in column (D); world.Household counts it as benefits so totals match
_hh.members[0].annual_benefits = _child_support
_cert = LihtcCert(_hh, bedrooms=2, ami_pct=60, utility_allowance=142)
_cert.check()

SPEC = national_tic_spec({
    "id": "tic_sc",
    "source": "tic_sc.pdf",
    "form": "SC Housing Tenant Income Certification (2024)",
    "notes": "Initial certification, 3-person household, 2BR at 60% AMI, no rental assistance. "
             "Gross rent = tenant rent + UA; max rent = 30% of the 60% limit at 3 persons / 12.",
    "hh": _hh,
    "cert_type": "Initial Certification",
    "effective_date": "11/01/2026",
    "initial_qual_date": "11/01/2026",
    "move_in_date": "11/01/2026",
    "property_name": "Palmetto Bend Apartments",
    "county": "Maple Ridge County",
    "bin": "SC-26-00123",
    "address": "410 Wren Hollow Road, Greenfield, SC 29640",
    "unit": "C-204",
    "bedrooms": 2,
    "income_rows": [(1, (33_800, 0, 0, _child_support))],
    "income_totals": (33_800, 0, 0, _child_support),
    "total_e": 33_800 + _child_support,
    "asset_income": _hh.imputed_asset_income,
    "household_signatures": [("Marguerite Ashdown", "10/28/2026")],
    "income_limit": _cert.income_limit,
    "designated_pct": 60,
    "income_at_move_in": _hh.annual_income,
    "size_at_move_in": _hh.size,
    "tenant_rent": _cert.tenant_paid_rent,
    "ua": _cert.utility_allowance,
    "assistance": 0,
    "other_fees": _cert.other_charges,
    "gross_rent": _cert.gross_rent,
    "max_rent": _cert.max_gross_rent,
    "program_label": "Housing Credit",
    "owner_rep": "Kendra Bellweather, Agent for Owner",
    "owner_signed": "10/30/2026",
})
