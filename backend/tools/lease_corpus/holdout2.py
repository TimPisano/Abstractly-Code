"""
Blind holdout corpus #2 for lease extraction (30 synthetic lease PDFs).

Written independently of the extractor and of the first two corpora.
Everything here is fictional: people, LLCs, management companies,
properties, streets, cities and housing authorities are invented.

    cd backend && source venv/bin/activate
    python tools/lease_corpus/holdout2.py --out tools/lease_corpus/holdout2_out

Writes B001..B030 PDFs plus manifest.json (the answer key) in the schema
run_corpus.py consumes. Deterministic (seed 424242).

Manifest judgment calls (also summarised in the hand-off report):
  * Addenda signed together with the lease (garage/storage, animal,
    utility) are part of the lease package, not "changes"; only documents
    that change a signed lease (renewal, amendment, notice, recert) count.
  * Section 8 "rent_amount" / "current_rent_amount" = total contract rent.
    A notice/recert that only moves the tenant/HAP split leaves contract
    rent unchanged.
  * A transfer-of-unit amendment keeps the ORIGINAL unit in unit_number
    and the original address; current_rent_amount follows the amendment.
  * Storage lockers and Alternative Deposit Program fees are not parking
    or utility charges.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import textwrap
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

SEED = 424242
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "holdout2_out")


# ---------------------------------------------------------------- blocks
def T(text):
    return ("title", text)


def H(text):
    return ("h", text)


def P(text):
    return ("p", text)


def TBL(rows):
    return ("table", rows)


def PB():
    return ("pb",)


NEUTRAL = [
    "Entry. Landlord may enter the dwelling to inspect, make repairs, or show it to prospective residents "
    "after giving reasonable notice, except in an emergency when no notice is required.",
    "Quiet Enjoyment. Resident shall not disturb the peaceful enjoyment of neighbors. Loud music or gatherings "
    "after 10:00 p.m. are a breach of this lease.",
    "Alterations. Resident shall not paint, install fixtures, or change or add locks without Landlord's "
    "written consent.",
    "Smoke Alarms. Resident will test alarms monthly, replace batteries as needed, and report any "
    "malfunction to the office at once.",
    "Insurance. Landlord's insurance does not cover Resident's belongings. Resident is encouraged to carry "
    "renter's insurance.",
    "Assignment. Resident may not assign this lease or sublet any part of the dwelling without prior "
    "written consent of Landlord.",
    "Move-out. Resident shall return the dwelling clean and in the same condition as received, ordinary wear "
    "and tear excepted, and shall return all keys.",
    "Governing Law. This lease is governed by the laws of the state in which the dwelling is located.",
    "Default. If Resident fails to pay rent when due or violates this lease, Landlord may pursue the "
    "remedies available under applicable law.",
    "Notices. Notices must be in writing and delivered by hand, posted at the dwelling, or sent by mail.",
]


def boil(rng, n=5):
    return [P(s) for s in rng.sample(NEUTRAL, n)]


def sigs(a, b=None):
    rows = [["Resident signature", "Date"], ["/s/ " + a, ""]]
    if b:
        rows.append(["/s/ " + b, ""])
    rows.append(["Landlord / Agent signature", ""])
    return TBL(rows)


# --------------------------------------------------------------- renderers
def render_typed(blocks):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch, invariant=1)
    story = []
    for b in blocks:
        kind = b[0]
        if kind == "title":
            story += [Paragraph(escape(b[1]), ss["Title"]), Spacer(1, 6)]
        elif kind == "h":
            story += [Spacer(1, 6), Paragraph("<b>%s</b>" % escape(b[1]), ss["Heading3"])]
        elif kind == "p":
            story += [Paragraph(escape(b[1]).replace("\n", "<br/>"), ss["BodyText"]), Spacer(1, 3)]
        elif kind == "table":
            data = [[Paragraph(escape(str(c)), ss["BodyText"]) for c in r] for r in b[1]]
            t = Table(data, hAlign="LEFT")
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [t, Spacer(1, 6)]
        elif kind == "pb":
            story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()


def _font(size):
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def render_scanned(blocks, rng, angle=0.7, stain=False):
    """Draw pages with PIL, then rotate, add paper noise and speckles, and
    save as an image-only PDF (no text layer)."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    W, H_ = 1700, 2200
    margin = 150
    body, big = _font(34), _font(46)
    lead = 48
    pages = []
    state = {}

    def new_page():
        img = Image.new("L", (W, H_), 255)
        state["img"], state["d"], state["y"] = img, ImageDraw.Draw(img), margin
        pages.append(img)

    def room(h):
        if state["y"] + h > H_ - margin:
            new_page()

    def wrap_px(text, font, width):
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if state["d"].textlength(trial, font=font) <= width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    new_page()
    for b in blocks:
        kind = b[0]
        if kind == "pb":
            new_page()
            continue
        if kind in ("title", "h"):
            font = big if kind == "title" else body
            for ln in wrap_px(b[1], font, W - 2 * margin):
                room(lead + 14)
                state["d"].text((margin, state["y"]), ln, font=font, fill=10)
                state["y"] += lead + 6
            state["y"] += 10
        elif kind == "p":
            for para in b[1].split("\n"):
                for ln in wrap_px(para, body, W - 2 * margin):
                    room(lead)
                    state["d"].text((margin, state["y"]), ln, font=body, fill=20)
                    state["y"] += lead
            state["y"] += 12
        elif kind == "table":
            rows = b[1]
            ncol = max(len(r) for r in rows)
            colw = (W - 2 * margin) // ncol
            for r in rows:
                cells = [wrap_px(str(c), body, colw - 20) for c in r]
                h = max(len(c) for c in cells) * lead + 10
                room(h)
                for i, lines in enumerate(cells):
                    x = margin + i * colw
                    state["d"].rectangle([x, state["y"], x + colw, state["y"] + h], outline=90, width=2)
                    for j, ln in enumerate(lines):
                        state["d"].text((x + 10, state["y"] + 5 + j * lead), ln, font=body, fill=20)
                state["y"] += h
            state["y"] += 20

    out = []
    for n, img in enumerate(pages):
        if stain and n == 0:
            ov = Image.new("L", (W, H_), 255)
            od = ImageDraw.Draw(ov)
            cx, cy = 1300, 1750
            for k, (rx, ry, v) in enumerate([(230, 200, 205), (190, 165, 175), (120, 100, 150)]):
                od.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=v, outline=120 if k == 0 else None, width=6)
            ov = ov.filter(ImageFilter.GaussianBlur(9))
            img = ImageChops.multiply(img, ov)
        img = img.rotate(rng.uniform(-angle, angle), resample=Image.BICUBIC, fillcolor=255)
        noise = Image.frombytes("L", (W, H_), rng.randbytes(W * H_)).point(lambda v: 228 + v // 10)
        img = ImageChops.multiply(img, noise).filter(ImageFilter.GaussianBlur(0.7))
        dd = ImageDraw.Draw(img)
        for _ in range(140):
            x, y = rng.randrange(W), rng.randrange(H_)
            dd.ellipse([x, y, x + rng.randint(1, 3), y + rng.randint(1, 3)], fill=rng.randint(60, 140))
        out.append(img.convert("L"))
    buf = io.BytesIO()
    out[0].save(buf, format="PDF", save_all=True, append_images=out[1:], resolution=200.0)
    return buf.getvalue()


def merge_pdfs(parts):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for data in parts:
        for page in PdfReader(io.BytesIO(data)).pages:
            w.add_page(page)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ----------------------------------------------------------------- cases
def fields(tenant, landlord, rent, start, end, addr, dep, unit, cur_rent=None, cur_end=None):
    return {"tenant": tenant, "landlord": landlord, "rent_amount": rent, "lease_start_date": start,
            "lease_end_date": end, "property_address": addr, "security_deposit": dep,
            "unit_number": unit, "current_rent_amount": cur_rent or rent,
            "current_lease_end_date": cur_end if cur_end is not None else end}


def case(family, style, blocks, f, scanned=None, pet=None, parking=None, util=None, s8=None,
         conc=False, changes=0, kinds=None, extra_pdf=None):
    return {"family": family, "style": style, "blocks": blocks, "fields": f, "scanned_mode": scanned,
            "pet": pet, "parking": parking, "util": util, "s8": s8, "conc": conc,
            "changes": kinds if kinds is not None else (["amendment"] * changes), "extra": extra_pdf}


def build_cases(rng):
    C = []

    # B001 Florida association form with checkbox lines
    C.append(case("fl_checkbox", "condo association form, [X] checkboxes", [
        T("RESIDENTIAL LEASE - Cypress Landing Condominium Association Form"),
        P("This lease is made between Seabreeze Harbor Holdings, LLC (\"Owner\") and Dolores M. Quintanilla "
          "(\"Tenant\") for the condominium unit described below."),
        H("1. Premises"),
        P("Unit 305, 2750 Cypress Landing Dr, Palmetto Vale, FL 33444."),
        H("2. Term"),
        P("The lease term begins August 1, 2025 and ends July 31, 2026."),
        H("3. Rent and Security"),
        P("Tenant shall pay rent of $1,685.00 per month on or before the first day of each month. "
          "Security deposit held by Owner: $1,500.00."),
        H("4. Elections (mark one in each row)"),
        P("[X] Pets allowed - one (1) cat only. Pet rent $25.00 per month; non-refundable pet fee $250.00.\n"
          "[ ] No pets allowed"),
        P("[X] One assigned space is included in the rent\n[ ] Garage / carport (extra charge)"),
        P("[X] Water, sewer and trash are included in the rent\n[X] Tenant arranges and pays electric and internet "
          "service directly"),
        H("5. General Terms"),
        *boil(rng, 4),
        sigs("Dolores M. Quintanilla"),
    ], fields("Dolores M. Quintanilla", "Seabreeze Harbor Holdings, LLC", "$1,685.00", "August 1, 2025",
              "July 31, 2026", "2750 Cypress Landing Dr", "$1,500.00", "305"),
        pet={"monthly_rent": 25.0, "fee": 250.0, "deposit": None}))

    # B002 concession schedule table
    C.append(case("concession_table", "net-effective rent schedule table", [
        T("APARTMENT LEASE"),
        P("Owner: Whitcomb Flats Owner LLC. Residents: Marcus T. Ellerbee and Ruth Ellerbee."),
        P("Dwelling: Apt 2C, 880 Whitcomb Row, Eastlake Mills, OH 43999."),
        P("Lease term: October 1, 2025 through September 30, 2026. Monthly rent is $1,240.00, due on the first. "
          "Security deposit: $600.00."),
        H("Rent Concession Schedule"),
        P("In consideration of a new-resident offer, Owner agrees to credit the following against rent. "
          "No other concession applies."),
        TBL([["Month", "Scheduled rent", "Concession credit", "Net amount due"],
             ["October 2025", "$1,240.00", "$620.00 (one-half month free)", "$620.00"],
             ["November 2025 - September 2026", "$1,240.00", "none", "$1,240.00"]]),
        *boil(rng, 5),
        sigs("Marcus T. Ellerbee", "Ruth Ellerbee"),
    ], fields("Marcus T. Ellerbee", "Whitcomb Flats Owner LLC", "$1,240.00", "October 1, 2025",
              "September 30, 2026", "880 Whitcomb Row", "$600.00", "2C"), conc=True))

    # B003 LESSOR / LESSEE(S)
    C.append(case("lessor_lessee", "LESSOR:/LESSEE(S): party block", [
        T("LEASE CONTRACT"),
        P("LESSOR: Pinecrest Terrace Partners, Ltd.\nLESSEE(S): Hyun-woo Park; Jasmine R. Cole"),
        P("PREMISES: 1415 Pinecrest Terrace, No. 7, Marlow Heights, TX 76999"),
        P("TERM: Commencing 05/01/2026 and ending 04/30/2027."),
        P("RENTAL: Lessee(s) agree to pay Lessor $1,095.00 monthly, in advance. DEPOSIT: $400.00."),
        P("CARPORT: Covered carport space #44 is assigned to Lessee(s) for $20.00 per month."),
        *boil(rng, 5),
        P("Executed by LESSEE(S): /s/ Hyun-woo Park   /s/ Jasmine R. Cole"),
    ], fields("Hyun-woo Park", "Pinecrest Terrace Partners, Ltd.", "$1,095.00", "May 1, 2026",
              "April 30, 2027", "1415 Pinecrest Terrace", "$400.00", "7"),
        parking={"monthly_fee": 20.0}))

    # B004 Landlord/Agent
    C.append(case("landlord_agent", "Landlord/Agent signing for owner", [
        T("Residential Rental Agreement"),
        P("Landlord/Agent: Tamsin Okafor-Reyes, Community Manager, acting on behalf of the owner, "
          "Brookhaven Glen Investors LLC."),
        P("Resident: Terrence L. Abara"),
        P("Rented premises: Apt 14, 6021 Brookhaven Glen Way, Ashby Crossing, GA 30999."),
        P("Starting on January 15, 2026, and ending on January 14, 2027, Resident will pay monthly rent of "
          "$1,310.00. A security deposit of $650.00 is due at signing."),
        P("Animals: No pets are permitted on the property."),
        P("Resident shall pay a monthly pest-control charge of $6.00 and a package-locker fee of $4.00 "
          "together with rent."),
        *boil(rng, 5),
        sigs("Terrence L. Abara"),
    ], fields("Terrence L. Abara", "Brookhaven Glen Investors LLC", "$1,310.00", "January 15, 2026",
              "January 14, 2027", "6021 Brookhaven Glen Way", "$650.00", "14"),
        util={"rubs": False, "rubs_utilities": [], "flat_monthly_total": 10.0}))

    # B005 Base Monthly Rent + other recurring charges
    C.append(case("base_plus_recurring", "Base Monthly Rent + recurring charges table, RUBS estimate", [
        T("Alder Creek Apartments - Lease Agreement"),
        P("Owner: Alder Creek Residential Fund III, LP. Resident: Priya N. Venkataraman."),
        P("Apartment: Unit 1126, 3300 Alder Creek Pkwy, Cedar Prairie, TX 75999."),
        P("Lease Term: March 1, 2026 to February 28, 2027."),
        H("Charges"),
        P("Base Monthly Rent: $1,455.00. Security Deposit: $500.00."),
        P("Other recurring charges (billed with rent):"),
        TBL([["Charge", "Monthly amount"],
             ["Trash service", "$15.00"],
             ["Pest control", "$5.00"],
             ["Water / Sewer / Stormwater - RUBS estimate (actual bill-back allocated by occupancy)", "$45.00"],
             ["Estimated total due each month", "$1,520.00"]]),
        *boil(rng, 4),
        sigs("Priya N. Venkataraman"),
    ], fields("Priya N. Venkataraman", "Alder Creek Residential Fund III, LP", "$1,455.00", "March 1, 2026",
              "February 28, 2027", "3300 Alder Creek Pkwy", "$500.00", "1126"),
        util={"rubs": True, "rubs_utilities": ["sewer", "stormwater", "water"], "flat_monthly_total": 20.0}))

    # B006 month-to-month
    C.append(case("month_to_month", "month-to-month, no end date", [
        T("MONTH-TO-MONTH RENTAL AGREEMENT"),
        P("Landlord: Gantry Point Rentals LLC\nTenant: Walter J. Brzezinski"),
        P("Premises: 17 Gantry Point Road, Apt D, Lakeshore Falls, OH 43999"),
        P("This tenancy commences August 1, 2025 and continues from month to month until ended by either party "
          "giving thirty (30) days' written notice."),
        P("Rent is $895.00 per month. Security deposit: $450.00."),
        P("One dog is approved. Pet rent of $20.00 per month applies."),
        *boil(rng, 5),
        sigs("Walter J. Brzezinski"),
    ], fields("Walter J. Brzezinski", "Gantry Point Rentals LLC", "$895.00", "August 1, 2025", None,
              "17 Gantry Point Road", "$450.00", "D"),
        pet={"monthly_rent": 20.0, "fee": None, "deposit": None}))

    # B007 term in words, no end date
    C.append(case("term_in_words", "12 months commencing, no explicit end", [
        T("California Residential Lease"),
        P("Landlord: Sutter Oaks Apartments LP. Tenant: Imelda S. Vasquez-Moreno."),
        P("Property: 902 Sutter Oaks Lane, Apt 6, Marisol Bay, CA 94999."),
        P("The term of this lease shall be twelve (12) months commencing on April 1, 2026."),
        P("Monthly rent: $2,150.00, payable in advance. Security deposit: $2,150.00."),
        P("[X] No pets permitted"),
        *boil(rng, 5),
        sigs("Imelda S. Vasquez-Moreno"),
    ], fields("Imelda S. Vasquez-Moreno", "Sutter Oaks Apartments LP", "$2,150.00", "April 1, 2026", None,
              "902 Sutter Oaks Lane", "$2,150.00", "6")))

    # B008 Apt #12B with ZIP+4 address on separate line
    C.append(case("unit_zip4", "Apt #12B, address on its own line, ZIP+4", [
        T("LEASE SUMMARY AND AGREEMENT"),
        TBL([["Landlord", "Harbor Pointe Apartments Owner, LLC"],
             ["Resident", "Lorraine Du Bois-Whitfield"],
             ["Dwelling", "Apt #12B"],
             ["Street", "4410 Harbor Pointe Blvd"],
             ["City / State / ZIP", "Kestrel Bay, FL 33987-4412"],
             ["Lease start", "March 1, 2026"],
             ["Lease end", "February 28, 2027"],
             ["Monthly rent", "$1,350.00"],
             ["Security deposit", "$500.00"]]),
        *boil(rng, 5),
        sigs("Lorraine Du Bois-Whitfield"),
    ], fields("Lorraine Du Bois-Whitfield", "Harbor Pointe Apartments Owner, LLC", "$1,350.00",
              "March 1, 2026", "February 28, 2027", "4410 Harbor Pointe Blvd", "$500.00", "12B")))

    # B009 HCV lease, amounts only in tenancy addendum
    C.append(case("hcv_addendum_only", "HCV lease: 'Rent: see HAP contract', HUD Tenancy Addendum", [
        T("Lease Agreement - Housing Choice Voucher Program"),
        P("Owner: Tulip Row Rentals LLC. Family / Tenant: Delphine A. Marchetti-Owusu."),
        P("Unit: Apt 3F, 245 Tulip Row, Linden Falls, OH 44999."),
        P("Term: September 1, 2025 through August 31, 2026."),
        P("Rent: see HAP contract. Security deposit: $750.00."),
        *boil(rng, 4),
        PB(),
        T("HUD Tenancy Addendum - Section 8 Tenant-Based Assistance"),
        P("Public Housing Agency: Greater Linden County Housing Authority."),
        TBL([["Item", "Amount per month"],
             ["Contract rent to owner", "$1,180.00"],
             ["Family (tenant) share", "$342.00"],
             ["PHA housing assistance payment", "$838.00"],
             ["Utility allowance", "$87.00"]]),
        P("The owner may not charge the family more than the family share. During the term the lease is "
          "subject to the HAP contract between the owner and the PHA."),
        sigs("Delphine A. Marchetti-Owusu"),
    ], fields("Delphine A. Marchetti-Owusu", "Tulip Row Rentals LLC", "$1,180.00", "September 1, 2025",
              "August 31, 2026", "245 Tulip Row", "$750.00", "3F"),
        s8={"is_section_8": True, "pha_name": "Greater Linden County Housing Authority",
            "contract_rent": 1180.0, "tenant_rent": 342.0, "hap_amount": 838.0, "utility_allowance": 87.0}))

    # B010 PBRA model lease Part I
    C.append(case("pbra_model_lease", "project-based Section 8 model lease, Part I table", [
        T("MODEL LEASE FOR SUBSIDIZED PROGRAMS"),
        P("Parties. Owner: Magnolia Court Senior Housing Limited Partnership. Tenant: Estella Rangel."),
        P("Dwelling: Apt 208, 51 Magnolia Court Circle, Harlow, GA 30999."),
        H("Part I - Lease Data"),
        TBL([["Item", "Amount"],
             ["Contract Rent", "$985.00"],
             ["Tenant Rent", "$263.00"],
             ["Assistance Payment", "$722.00"],
             ["Utility Allowance", "$64.00"],
             ["Security Deposit", "$250.00"]]),
        P("Contract administrator: Harlow County Housing Authority. The initial term of this lease is one year "
          "beginning June 1, 2025 and ending May 31, 2026."),
        *boil(rng, 5),
        sigs("Estella Rangel"),
    ], fields("Estella Rangel", "Magnolia Court Senior Housing Limited Partnership", "$985.00", "June 1, 2025",
              "May 31, 2026", "51 Magnolia Court Circle", "$250.00", "208"),
        s8={"is_section_8": True, "pha_name": "Harlow County Housing Authority",
            "contract_rent": 985.0, "tenant_rent": 263.0, "hap_amount": 722.0, "utility_allowance": 64.0}))

    # B011 HCV lease + PHA notice of change (split only)
    C.append(case("pha_notice_change", "lease + PHA notice moving tenant rent / HAP split", [
        T("Lease - Voucher Participant"),
        P("Owner: Obsidian Lane Properties Inc. Participant: Cornelius B. Fairweather."),
        P("Unit 9, 1180 Obsidian Lane, Riverbend, OH 44999. Term July 1, 2025 to June 30, 2026. "
          "Security deposit $400.00."),
        TBL([["Rent breakdown at lease start", "Monthly"],
             ["Contract rent", "$1,260.00"],
             ["Tenant rent", "$380.00"],
             ["HAP paid by Riverbend Metropolitan Housing Authority", "$880.00"],
             ["Utility allowance", "$102.00"]]),
        *boil(rng, 4),
        sigs("Cornelius B. Fairweather"),
        PB(),
        T("NOTICE OF CHANGE IN TENANT RENT AND HAP"),
        P("Riverbend Metropolitan Housing Authority notifies Owner and Participant Cornelius B. Fairweather, "
          "Unit 9, that effective January 1, 2026 the tenant rent is $455.00 and the HAP payment is $805.00. "
          "The contract rent does not change. All other lease terms remain in effect."),
    ], fields("Cornelius B. Fairweather", "Obsidian Lane Properties Inc.", "$1,260.00", "July 1, 2025",
              "June 30, 2026", "1180 Obsidian Lane", "$400.00", "9"),
        s8={"is_section_8": True, "pha_name": "Riverbend Metropolitan Housing Authority",
            "contract_rent": 1260.0, "tenant_rent": 380.0, "hap_amount": 880.0, "utility_allowance": 102.0},
        kinds=["amendment"]))

    # B012 annual recertification summary
    C.append(case("annual_recert", "lease + HUD-50059 style recertification summary", [
        T("Section 8 Lease"),
        P("Owner: Fenwick Green Apartments LLC. Tenant: Bernadette Oyelaran. Premises: Apt 4A, "
          "7 Fenwick Green, Fenwick Mills, GA 30999."),
        P("Lease term: January 1, 2025 to December 31, 2025. Security deposit: $215.00."),
        P("Housing Authority: Fenwick County Housing Authority."),
        TBL([["Contract rent", "$1,040.00"], ["Tenant rent", "$215.00"], ["Assistance payment (HAP)", "$825.00"],
             ["Utility allowance", "$58.00"]]),
        *boil(rng, 4),
        sigs("Bernadette Oyelaran"),
        PB(),
        T("Annual Recertification - Tenant Data Summary"),
        P("Household: Bernadette Oyelaran, Apt 4A. Effective date of recertification: December 1, 2025."),
        TBL([["Item", "Result"],
             ["Total Tenant Payment (new)", "$297.00"],
             ["Assistance payment (new)", "$743.00"],
             ["Contract rent", "$1,040.00 (unchanged)"]]),
    ], fields("Bernadette Oyelaran", "Fenwick Green Apartments LLC", "$1,040.00", "January 1, 2025",
              "December 31, 2025", "7 Fenwick Green", "$215.00", "4A"),
        s8={"is_section_8": True, "pha_name": "Fenwick County Housing Authority",
            "contract_rent": 1040.0, "tenant_rent": 215.0, "hap_amount": 825.0, "utility_allowance": 58.0},
        kinds=["amendment"]))

    # B013 renewal by letter
    C.append(case("renewal_letter", "lease + renewal letter with signed acceptance", [
        T("Apartment Lease Agreement"),
        P("Cobblestone Mews Owner LLC (Landlord) leases Apt 22, 340 Cobblestone Mews, Cedar Prairie, TX 75999 "
          "to Anselm P. Rutherford (Tenant) from June 1, 2025 until May 31, 2026."),
        P("Monthly rent: $1,310.00. Security deposit: $500.00."),
        *boil(rng, 5),
        sigs("Anselm P. Rutherford"),
        PB(),
        P("March 20, 2026"),
        P("Dear Mr. Rutherford,"),
        P("Your lease for Apt 22 expires on May 31, 2026. We would like you to stay. If you renew, your new "
          "monthly rent will be $1,360.00 for a renewal term of June 1, 2026 through May 31, 2027. All other "
          "terms stay the same. Please sign below and return this letter by April 15."),
        P("Sincerely, Cobblestone Mews Leasing Office"),
        P("ACCEPTED: I agree to renew on these terms.  /s/ Anselm P. Rutherford   Date: April 2, 2026"),
    ], fields("Anselm P. Rutherford", "Cobblestone Mews Owner LLC", "$1,310.00", "June 1, 2025",
              "May 31, 2026", "340 Cobblestone Mews", "$500.00", "22",
              cur_rent="$1,360.00", cur_end="May 31, 2027"), kinds=["renewal"]))

    # B014 transfer to a new unit amendment
    C.append(case("unit_transfer", "amendment transferring tenant to Unit 204", [
        T("Lease"),
        P("Landlord: Willow Run Terrace Associates, LLC. Tenant: Gwendolyn Achterberg. Dwelling: Unit 118, "
          "6300 Willow Run Terrace, Dunmore Park, OH 45999. Term: April 1, 2025 to March 31, 2026. "
          "Rent: $1,180.00 monthly. Deposit: $500.00."),
        *boil(rng, 5),
        sigs("Gwendolyn Achterberg"),
        PB(),
        T("Addendum No. 1 - Transfer to Unit 204"),
        P("Landlord and Tenant agree that effective October 1, 2025 Tenant will transfer from Unit 118 to "
          "Unit 204 at the same community. From the transfer date, monthly rent is $1,215.00. The security "
          "deposit carries over. The lease end date does not change."),
        sigs("Gwendolyn Achterberg"),
    ], fields("Gwendolyn Achterberg", "Willow Run Terrace Associates, LLC", "$1,180.00", "April 1, 2025",
              "March 31, 2026", "6300 Willow Run Terrace", "$500.00", "118", cur_rent="$1,215.00"),
        kinds=["amendment"]))

    # B015 roommate addition
    C.append(case("roommate_addition", "amendment adding a roommate, no rent change", [
        T("RESIDENTIAL LEASE"),
        P("Sandpiper Row Realty Trust, as landlord, rents Apt 11, 2201 Sandpiper Row, Whiteoak Landing, TX 75999 "
          "to Kaveh Mohammadi-Reid. The lease runs September 1, 2025 to August 31, 2026 at $1,575.00 per "
          "month. Security deposit: $700.00."),
        *boil(rng, 5),
        sigs("Kaveh Mohammadi-Reid"),
        PB(),
        T("LEASE AMENDMENT - ADDITION OF OCCUPANT"),
        P("The parties amend the lease for Apt 11 to add Sloane Whitlock as a resident. Kaveh Mohammadi-Reid "
          "and Sloane Whitlock are jointly and severally liable. Rent and all other terms are unchanged."),
        sigs("Kaveh Mohammadi-Reid", "Sloane Whitlock"),
    ], fields("Kaveh Mohammadi-Reid", "Sandpiper Row Realty Trust", "$1,575.00", "September 1, 2025",
              "August 31, 2026", "2201 Sandpiper Row", "$700.00", "11"), kinds=["amendment"]))

    # B016 garage + storage addendum
    C.append(case("garage_storage", "lease + garage and storage addendum", [
        T("Lease Agreement"),
        P("Northgate Commons LLC (Landlord) and Octavia L. Lindqvist (Resident). Unit 410, 88 Northgate "
          "Commons Dr, Brightwater, OH 43999. Term: February 1, 2026 - January 31, 2027. Rent: $1,890.00 per "
          "month. Security deposit: $900.00."),
        *boil(rng, 4),
        sigs("Octavia L. Lindqvist"),
        PB(),
        T("Garage and Storage Addendum"),
        P("This addendum is signed with the lease. Resident rents garage space G-14 for $95.00 per month and "
          "storage locker S-6 for $25.00 per month. Both are payable with rent."),
    ], fields("Octavia L. Lindqvist", "Northgate Commons LLC", "$1,890.00", "February 1, 2026",
              "January 31, 2027", "88 Northgate Commons Dr", "$900.00", "410"),
        parking={"monthly_fee": 95.0}))

    # B017 assistance animal addendum
    C.append(case("assistance_animal", "animal addendum, assistance animal, no pet charges", [
        T("Lease Agreement"),
        P("Quillfeather Court Apartments, L.L.C. (Landlord) rents Apt 5, 410 Quillfeather Ct, Pebble Run, GA "
          "30999 to Roderick Halvorsen-Tan from December 1, 2025 to November 30, 2026. Monthly rent $1,120.00. "
          "Security deposit $500.00."),
        *boil(rng, 4),
        sigs("Roderick Halvorsen-Tan"),
        PB(),
        T("Animal Addendum - Assistance Animal"),
        P("Resident has documented a disability-related need for an emotional support animal (one cat). Under "
          "fair housing law an assistance animal is not a pet. Landlord will not charge pet rent, a pet fee, "
          "or a pet deposit for the assistance animal. Resident remains responsible for any damage the "
          "animal causes and must keep it under control."),
    ], fields("Roderick Halvorsen-Tan", "Quillfeather Court Apartments, L.L.C.", "$1,120.00",
              "December 1, 2025", "November 30, 2026", "410 Quillfeather Ct", "$500.00", "5")))

    # B018 utility addendum, submeter + valet trash
    C.append(case("utility_submeter", "utility addendum: submetered water, flat valet trash", [
        T("Barley Mill Lofts - Lease"),
        P("Landlord: Barley Mill Lofts Owner LP. Resident: Yevgenia Sokolovsky. Loft 3B, 2 Barley Mill Lane, "
          "Kettle Run, OH 43999. Term: April 1, 2026 to March 31, 2027. Rent: $1,640.00 per month. Security "
          "deposit: $800.00."),
        *boil(rng, 4),
        sigs("Yevgenia Sokolovsky"),
        PB(),
        T("Utility Addendum"),
        P("Water is submetered. Resident pays for the water used according to the meter reading, billed "
          "monthly. Electric service is placed in Resident's own name. Valet trash pickup is mandatory for a "
          "flat fee of $28.00 per month."),
    ], fields("Yevgenia Sokolovsky", "Barley Mill Lofts Owner LP", "$1,640.00", "April 1, 2026",
              "March 31, 2027", "2 Barley Mill Lane", "$800.00", "3B"),
        util={"rubs": True, "rubs_utilities": ["water"], "flat_monthly_total": 28.0}))

    # B019 alternative deposit program
    C.append(case("alt_deposit", "deposit waived, Alternative Deposit Program fee", [
        T("RESIDENT LEASE"),
        P("Redfern Gate Properties LLC, Landlord. Tobias Nakagawa, Resident. Apt 307, 1900 Redfern Gate, "
          "Stonebridge, TX 75999."),
        P("Term: July 1, 2025 to June 30, 2026. Rent: $1,275.00 per month."),
        P("Security deposit: waived. Resident is enrolled in the Alternative Deposit Program and pays a "
          "non-refundable program fee of $14.00 per month in place of a cash deposit."),
        *boil(rng, 5),
        sigs("Tobias Nakagawa"),
    ], fields("Tobias Nakagawa", "Redfern Gate Properties LLC", "$1,275.00", "July 1, 2025", "June 30, 2026",
              "1900 Redfern Gate", None, "307")))

    # B020 corporate lease
    C.append(case("corporate_llc", "tenant is an LLC, named occupant", [
        T("CORPORATE HOUSING LEASE"),
        P("Landlord: Tidewater Flats Owner LLC.\nTenant: Halyard Staffing Solutions, LLC, a corporate lessee."),
        P("Authorized occupant (not a party to this lease): Ms. Corinne Abbott-Deluca."),
        P("Premises: Unit 702, 515 Tidewater Flats Way, Kestrel Bay, FL 33987."),
        P("Term: February 1, 2026 to July 31, 2026. Tenant shall pay $2,400.00 per month. Security deposit: "
          "$2,400.00."),
        *boil(rng, 5),
        P("Tenant, by its authorized officer: /s/ Dale R. Whitmore, Operations Director"),
    ], fields("Halyard Staffing Solutions, LLC", "Tidewater Flats Owner LLC", "$2,400.00", "February 1, 2026",
              "July 31, 2026", "515 Tidewater Flats Way", "$2,400.00", "702")))

    # B021 owner c/o manager
    C.append(case("owner_c_o", "owner shown c/o management company", [
        T("Lease Agreement"),
        P("OWNER: Larkspur Court Holdings LP, c/o Brightline Residential Management, 400 Commerce Way, "
          "Suite 120, Eastmere, OH 43999."),
        P("RESIDENT: Nadia Kowalczyk"),
        P("RESIDENCE: Apt 18, 1313 Larkspur Court, Eastmere, OH 43999"),
        P("This lease starts November 1, 2025 and expires October 31, 2026. Rent: $1,050.00 per month. "
          "Security deposit: $525.00."),
        *boil(rng, 5),
        sigs("Nadia Kowalczyk"),
    ], fields("Nadia Kowalczyk", "Larkspur Court Holdings LP", "$1,050.00", "November 1, 2025",
              "October 31, 2026", "1313 Larkspur Court", "$525.00", "18")))

    # B022 Texas-style lease contract
    C.append(case("tx_lease_contract", "Texas style: checkboxes, reserved space, RUBS, valet trash", [
        T("APARTMENT LEASE CONTRACT"),
        P("Owner: Mesquite Hollow Apartments, LP. Resident: Brandon K. Whitaker-Ng."),
        P("Apartment No. 2214, 9840 Mesquite Hollow Blvd, Cedar Prairie, TX 75999."),
        P("Lease begins 2/1/2026 and ends 1/31/2027. Monthly rent: $1,235.00. Security deposit: $400.00."),
        P("[X] Pet(s) permitted: one (1) dog. Pet deposit $300.00. Pet rent $40.00 per month.   [ ] No pets"),
        P("[X] Reserved covered space: $30.00 per month   [ ] No vehicle space requested"),
        P("Utilities. Resident pays electric directly to the provider. Water and wastewater are billed back "
          "to Resident by allocation under the Utility Addendum. Trash valet service is a flat $12.00 per "
          "month."),
        *boil(rng, 4),
        sigs("Brandon K. Whitaker-Ng"),
    ], fields("Brandon K. Whitaker-Ng", "Mesquite Hollow Apartments, LP", "$1,235.00", "February 1, 2026",
              "January 31, 2027", "9840 Mesquite Hollow Blvd", "$400.00", "2214"),
        pet={"monthly_rent": 40.0, "fee": None, "deposit": 300.0}, parking={"monthly_fee": 30.0},
        util={"rubs": True, "rubs_utilities": ["sewer", "water"], "flat_monthly_total": 12.0}))

    # B023 Georgia, move-in special
    C.append(case("ga_move_in_special", "one-time move-in special credit in prose", [
        T("Georgia Residential Lease"),
        P("Landlord: Sweetgum Ridge Apartments, LLLP. Tenant: Latoya V. Pendergrass."),
        P("Apt 9H, 3705 Sweetgum Ridge Rd, Ashby Crossing, GA 30999."),
        P("Term: August 15, 2025 to August 14, 2026. Rent: $1,145.00 per month. Security deposit: $575.00."),
        P("Move-in special: Landlord will credit $300.00 against the first full month's rent as a one-time "
          "promotional concession."),
        P("Landlord supplies trash removal for a flat fee of $18.00 per month. Tenant pays for electricity "
          "directly."),
        *boil(rng, 5),
        sigs("Latoya V. Pendergrass"),
    ], fields("Latoya V. Pendergrass", "Sweetgum Ridge Apartments, LLLP", "$1,145.00", "August 15, 2025",
              "August 14, 2026", "3705 Sweetgum Ridge Rd", "$575.00", "9H"),
        util={"rubs": False, "rubs_utilities": [], "flat_monthly_total": 18.0}, conc=True))

    # B024 Ohio plain, numeric dates, rent in words
    C.append(case("oh_plain", "plain Ohio agreement, numeric dates, rent in words", [
        T("RENTAL AGREEMENT"),
        P("This agreement is between Ferncliff Gardens Co., an Ohio general partnership (Landlord), and "
          "Mildred A. Czarnecki (Tenant)."),
        P("Property: Apt 4, 2250 Ferncliff Drive, Kettering Falls, OH 45999."),
        P("Period: 01/01/2026 to 12/31/2026."),
        P("Rent: Eight hundred twenty-five dollars ($825.00) each month. Deposit: $825.00."),
        P("No pets, except as required by law. One unassigned space is provided at no charge."),
        *boil(rng, 6),
        sigs("Mildred A. Czarnecki"),
    ], fields("Mildred A. Czarnecki", "Ferncliff Gardens Co.", "$825.00", "January 1, 2026",
              "December 31, 2026", "2250 Ferncliff Drive", "$825.00", "4")))

    # B025 California, two tenants, pet deposit
    C.append(case("ca_two_tenants", "California form, two tenants, pet deposit", [
        T("RESIDENTIAL LEASE AGREEMENT"),
        P("Landlord: Seacliff Terrace Investors, LLC\nTenants: Rafael A. Montenegro and Beatriz Montenegro"),
        P("Unit 9, 1750 Seacliff Terrace, Marisol Bay, CA 94999"),
        P("Term: May 1, 2026 through April 30, 2027. Monthly rent: $2,675.00. Security deposit: $2,675.00."),
        P("Pets: one cat is approved. Tenants shall pay an additional pet deposit of $300.00."),
        P("Tenants pay gas and electric directly. Landlord pays water, sewer and garbage."),
        *boil(rng, 5),
        sigs("Rafael A. Montenegro", "Beatriz Montenegro"),
    ], fields("Rafael A. Montenegro", "Seacliff Terrace Investors, LLC", "$2,675.00", "May 1, 2026",
              "April 30, 2027", "1750 Seacliff Terrace", "$2,675.00", "9"),
        pet={"monthly_rent": None, "fee": None, "deposit": 300.0}))

    # ---- scanned
    # B026 simple scan
    C.append(case("scan_simple", "image-only scan, simple lease", [
        T("LEASE AGREEMENT"),
        P("Landlord: Pemberton Square Associates\nTenant: Leopold Ashgrove"),
        P("Premises: Apt 6, 1020 Pemberton Square, Rushmere, OH 43999"),
        P("Term: January 1, 2026 to December 31, 2026."),
        P("Monthly rent: $975.00. Security deposit: $975.00."),
        *boil(rng, 6),
        sigs("Leopold Ashgrove"),
    ], fields("Leopold Ashgrove", "Pemberton Square Associates", "$975.00", "January 1, 2026",
              "December 31, 2026", "1020 Pemberton Square", "$975.00", "6"), scanned="all"))

    # B027 scan with coffee stain
    C.append(case("scan_stain", "image-only scan with coffee-stain blob", [
        T("RESIDENTIAL LEASE"),
        P("Owner: Dunmore Lake Estates LLC. Resident: Marisol Etxeberria."),
        P("Apt 12, 56 Dunmore Lake Road, Pebble Run, GA 30999."),
        P("The lease term is 06/01/2025 to 05/31/2026. Rent is $1,505.00 per month. Deposit: $750.00."),
        P("One dog allowed. Pet rent $35.00 per month and pet deposit $250.00."),
        *boil(rng, 8),
        sigs("Marisol Etxeberria"),
    ], fields("Marisol Etxeberria", "Dunmore Lake Estates LLC", "$1,505.00", "June 1, 2025", "May 31, 2026",
              "56 Dunmore Lake Road", "$750.00", "12"),
        pet={"monthly_rent": 35.0, "fee": None, "deposit": 250.0}, scanned="stain"))

    # B028 scanned lease + scanned renewal
    C.append(case("scan_renewal", "image-only scan: lease plus renewal offer", [
        T("APARTMENT LEASE"),
        P("Hollis Brook Holdings LLC leases Apt 31, 700 Hollis Brook Dr, Ironwood Falls, TX 75999 to "
          "Ignatius Fairbairn for the term March 1, 2025 to February 28, 2026 at a rent of $1,220.00 per "
          "month. Security deposit: $600.00."),
        *boil(rng, 4),
        sigs("Ignatius Fairbairn"),
        PB(),
        T("LEASE RENEWAL"),
        P("Ignatius Fairbairn and Hollis Brook Holdings LLC renew the lease for Apt 31. New term: March 1, "
          "2026 to February 28, 2027. New monthly rent: $1,265.00. All other terms continue."),
        sigs("Ignatius Fairbairn"),
    ], fields("Ignatius Fairbairn", "Hollis Brook Holdings LLC", "$1,220.00", "March 1, 2025",
              "February 28, 2026", "700 Hollis Brook Dr", "$600.00", "31",
              cur_rent="$1,265.00", cur_end="February 28, 2027"), scanned="all", kinds=["renewal"]))

    # B029 mixed: typed lease + scanned HUD tenancy addendum
    typed_blocks = [
        T("Lease - Voucher Program"),
        P("Garnet Hill Rentals LLC (Owner) rents Apt 2, 33 Garnet Hill Rd, Eastvale, OH 44999 to Philomena "
          "Okonkwo-Lindgren (Tenant). Term: October 1, 2025 through September 30, 2026."),
        P("Rent: see HAP contract. Security deposit: $600.00."),
        *boil(rng, 5),
        sigs("Philomena Okonkwo-Lindgren"),
    ]
    scan_blocks = [
        T("HUD TENANCY ADDENDUM"),
        P("Section 8 Tenant-Based Assistance, Housing Choice Voucher Program. PHA: Eastvale Housing Authority. "
          "Owner: Garnet Hill Rentals LLC. Tenant: Philomena Okonkwo-Lindgren."),
        TBL([["Item", "Monthly"],
             ["Contract rent to owner", "$1,095.00"],
             ["Tenant share of rent", "$297.00"],
             ["Housing assistance payment", "$798.00"],
             ["Utility allowance", "$74.00"]]),
        P("The lease is subject to the HAP contract."),
    ]
    C.append(case("mixed_typed_scan_hcv", "typed lease + scanned Tenancy Addendum page", typed_blocks,
                  fields("Philomena Okonkwo-Lindgren", "Garnet Hill Rentals LLC", "$1,095.00",
                         "October 1, 2025", "September 30, 2026", "33 Garnet Hill Rd", "$600.00", "2"),
                  scanned="mixed",
                  s8={"is_section_8": True, "pha_name": "Eastvale Housing Authority", "contract_rent": 1095.0,
                      "tenant_rent": 297.0, "hap_amount": 798.0, "utility_allowance": 74.0},
                  extra_pdf=scan_blocks))

    # B030 scan with parking + RUBS
    C.append(case("scan_parking_rubs", "image-only scan: covered parking and RUBS", [
        T("LEASE"),
        P("Landlord: Orchard Gate Multifamily LLC\nResident: Cassius Whitlow-Abernathy"),
        P("Apt 1208, 4500 Orchard Gate Blvd, Ironwood Falls, TX 75999"),
        P("From September 1, 2025 to August 31, 2026. Rent $1,425.00 per month. Security deposit $500.00."),
        P("Covered parking: $45.00 per month."),
        P("Water, sewer and trash charges are billed back to Resident based on occupancy (RUBS)."),
        *boil(rng, 4),
        sigs("Cassius Whitlow-Abernathy"),
    ], fields("Cassius Whitlow-Abernathy", "Orchard Gate Multifamily LLC", "$1,425.00", "September 1, 2025",
              "August 31, 2026", "4500 Orchard Gate Blvd", "$500.00", "1208"),
        parking={"monthly_fee": 45.0},
        util={"rubs": True, "rubs_utilities": ["sewer", "trash", "water"], "flat_monthly_total": None},
        scanned="all"))
    return C


def generate(out_dir: str = DEFAULT_OUT) -> str:
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(SEED)
    cases = build_cases(rng)
    manifest = {"seed": SEED,
                "note": "Blind holdout #2: 30 fictional multifamily lease PDFs (typed, scanned, mixed).",
                "cases": []}
    for i, c in enumerate(cases, 1):
        cid = "B%03d" % i
        fname = "%s_%s.pdf" % (cid, c["family"])
        srng = random.Random(SEED + i)
        mode = c["scanned_mode"]
        if mode in ("all", "stain"):
            data = render_scanned(c["blocks"], srng, stain=(mode == "stain"))
        elif mode == "mixed":
            data = merge_pdfs([render_typed(c["blocks"]), render_scanned(c["extra"], srng)])
        else:
            data = render_typed(c["blocks"])
        with open(os.path.join(out_dir, fname), "wb") as fh:
            fh.write(data)
        manifest["cases"].append({
            "file": fname, "case_id": cid, "family": c["family"], "style": c["style"],
            "scanned": mode is not None, "expected_lease_count": 1, "fields": c["fields"],
            "pet_charges": c["pet"], "parking_charges": c["parking"], "utility_charges": c["util"],
            "section_8": c["s8"], "has_concession": c["conc"],
            "lease_changes": [{"kind": k} for k in c["changes"]],
        })
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return out_dir


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    out = generate(a.out)
    print("wrote %d cases to %s" % (30, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
