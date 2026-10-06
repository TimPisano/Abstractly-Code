"""
Synthetic multifamily / Section 8 lease corpus with a graded answer key.

Writes, into --out (default: tools/lease_corpus/out/, gitignored):
  - one PDF per case (a lease plus whatever addenda/amendments the case
    carries, all in one file, the way a seller's data room delivers it)
  - manifest.json: for every file, the expected value of every field
    the grader checks, plus how many leases the file really contains.

Everything here is fictional: the people, the properties, the owners,
the housing authorities. Never put real customer data in this file.

Deterministic: the same --seed always produces the same files and
manifest, so a before/after accuracy comparison is apples to apples.

    python tools/lease_corpus/generate.py [--out DIR] [--seed 7] [--only FAMILY]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "out")

# ----------------------------------------------------------------------
# Fictional pools
# ----------------------------------------------------------------------

FIRST = ["Jordan", "Priya", "Marcus", "Alana", "Tomas", "Keisha", "Wen", "Darnell", "Sofia",
         "Ibrahim", "Leah", "Mateo", "Nadia", "Curtis", "Yolanda", "Ravi", "Bethany", "Hector",
         "Imani", "Gregor", "Lucia", "Desmond", "Fatima", "Owen"]
LAST = ["Ellis", "Natarajan", "Whitfield", "Okafor", "Brandvold", "Castellano", "Pruitt",
        "Lindqvist", "Abernathy", "Quintero", "Hollister", "Mbeki", "Varga", "Sandoval",
        "Thistlewood", "Kowalczyk", "Ferreira", "Underhill", "Achebe", "Montclair"]
PROPERTIES = [
    ("Cedar Bend Apartments", "1250 Cedar Bend Lane", "Columbus", "OH", "43215"),
    ("Willow Creek Commons", "88 Willow Creek Drive", "Raleigh", "NC", "27609"),
    ("Harbor Pointe Residences", "4410 Harbor Pointe Blvd", "Tampa", "FL", "33611"),
    ("Juniper Ridge", "730 Juniper Ridge Road", "Boise", "ID", "83702"),
    ("Brookstone Flats", "2200 Brookstone Parkway", "Kansas City", "MO", "64114"),
    ("Sable Oaks Village", "1609 Sable Oaks Circle", "San Antonio", "TX", "78229"),
    ("Larkspur Gardens", "315 Larkspur Avenue", "Tucson", "AZ", "85719"),
    ("Pinehaven Terrace", "9021 Pinehaven Court", "Richmond", "VA", "23233"),
]
OWNER_SUFFIX = ["Owner, LLC", "Holdings LLC", "Apartments LP", "Residential, LLC"]
MANAGERS = ["Tallgrass Property Management, LLC", "Keystone Residential Services, Inc.",
            "Bluefin Multifamily Management LLC", "Copperleaf Living, LLC"]
PHAS = ["Riverbend County Housing Authority", "Granite Valley Public Housing Agency",
        "Lakeshore Metropolitan Housing Authority", "Ashford Regional Housing Commission"]

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
        "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
        "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def words(n: int) -> str:
    """Whole dollars in words, up to 9,999 -- enough for monthly rent."""
    parts = []
    if n >= 1000:
        parts.append(f"{ONES[n // 1000]} Thousand")
        n %= 1000
    if n >= 100:
        parts.append(f"{ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        parts.append(TENS[n // 10] + (f"-{ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(ONES[n])
    return " ".join(parts)


def money(x: float) -> str:
    return f"${x:,.2f}"


def long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def slash_date(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


# ----------------------------------------------------------------------
# Case model
# ----------------------------------------------------------------------

@dataclass
class Case:
    case_id: str
    family: str
    style: str                       # "table" | "prose" | "state"
    residents: List[str]
    owner: str
    manager: Optional[str]
    prop: Tuple[str, str, str, str, str]
    unit: str
    unit_label: str                  # "Apartment No." | "Unit #" | "Apt." | "Unit"
    rent: float
    deposit: float
    start: date
    end: date
    date_fmt: str = "long"           # "long" | "slash"
    rent_in_words_only: bool = False
    pet: Optional[Dict[str, float]] = None       # monthly_rent, fee, deposit
    parking: Optional[Dict[str, Any]] = None     # monthly_fee, space
    utilities: Optional[Dict[str, Any]] = None   # rubs: [..], flat: {name: amt}
    section8: Optional[Dict[str, Any]] = None    # pha, tenant_rent, hap, ua, hap_start
    concession: Optional[str] = None             # concession clause text
    changes: List[Dict[str, Any]] = field(default_factory=list)  # renewal/amendment
    scanned: bool = False
    scanned_attachments: bool = False             # typed lease, attachments are scanned images
    second_lease: Optional["Case"] = None        # a genuinely separate lease in the same file

    # -- derived ------------------------------------------------------
    def d(self, x: date) -> str:
        return slash_date(x) if self.date_fmt == "slash" else long_date(x)

    @property
    def street_line(self) -> str:
        return f"{self.prop[1]}, {self.unit_label} {self.unit}"

    @property
    def full_address(self) -> str:
        _, street, city, st, zp = self.prop
        return f"{street}, {self.unit_label} {self.unit}, {city}, {st} {zp}"

    @property
    def tenant_display(self) -> str:
        return " and ".join(self.residents)

    def expected(self) -> Dict[str, Any]:
        current_rent = self.rent
        current_end = self.end
        for ch in self.changes:
            if ch.get("new_rent") is not None:
                current_rent = ch["new_rent"]
            if ch.get("new_end") is not None:
                current_end = ch["new_end"]
        exp: Dict[str, Any] = {
            "fields": {
                "tenant": self.residents[0],
                "landlord": self.owner,
                "rent_amount": money(self.rent),
                "lease_start_date": long_date(self.start),
                "lease_end_date": long_date(self.end),
                "property_address": self.prop[1],
                "security_deposit": money(self.deposit),
                "unit_number": self.unit,
                "current_rent_amount": money(current_rent),
                "current_lease_end_date": long_date(current_end),
            },
            "pet_charges": self.pet,
            "parking_charges": {"monthly_fee": self.parking["monthly_fee"]} if self.parking else None,
            "utility_charges": None,
            "section_8": None,
            "has_concession": bool(self.concession),
            "lease_changes": [
                {k: (long_date(v) if isinstance(v, date) else v) for k, v in ch.items() if k != "kind"} | {"kind": ch["kind"]}
                for ch in self.changes
            ],
        }
        if self.utilities:
            exp["utility_charges"] = {
                "rubs": bool(self.utilities.get("rubs")),
                "rubs_utilities": sorted(self.utilities.get("rubs") or []),
                "flat_monthly_total": round(sum((self.utilities.get("flat") or {}).values()), 2),
            }
        if self.section8:
            s = self.section8
            exp["section_8"] = {
                "is_section_8": True,
                "pha_name": s["pha"],
                "contract_rent": self.rent,
                "tenant_rent": s["tenant_rent"],
                "hap_amount": s["hap"],
                "utility_allowance": s.get("ua"),
            }
        return exp


# ----------------------------------------------------------------------
# Document text
# ----------------------------------------------------------------------

Para = Tuple[str, str]   # (kind, text): kind in {"title", "h", "p"}
Doc = List[Para]


def _parties_clause(c: Case) -> str:
    res = c.tenant_display
    if c.style == "table":
        return ""
    if c.manager and c.style == "prose":
        return (f'This Apartment Lease Contract is entered into between {c.owner} ("Owner"), '
                f'acting through its managing agent {c.manager} ("Agent"), and {res} '
                f'(collectively, "Resident").')
    if c.style == "state":
        return (f'THIS RESIDENTIAL LEASE AGREEMENT is made by and between {c.owner} ("Landlord") '
                f'and {res} ("Tenant").')
    return f'This Lease is made by and between {c.owner} ("Owner") and {res} ("Resident").'


def _rent_sentence(c: Case, who: str, owner_word: str) -> str:
    r = c.rent
    if c.rent_in_words_only:
        return (f"{who} shall pay {owner_word} the sum of {words(int(r))} Dollars per month as rent, "
                f"due on or before the first (1st) day of each month.")
    if c.style == "state":
        return (f"{who} agrees to pay {owner_word} monthly rent of {words(int(r))} and 00/100 Dollars "
                f"({money(r)}) per month, payable in advance on the first day of each month.")
    return (f"{who} will pay {money(r)} per month as rent for the Apartment, due on or before "
            f"the 1st day of each month without demand.")


def lease_doc(c: Case) -> List[Doc]:
    """The base lease, as a list of pages (each page a list of paras)."""
    owner_word = "Landlord" if c.style == "state" else "Owner"
    who = "Tenant" if c.style == "state" else "Resident"
    prop_name = c.prop[0]
    pages: List[Doc] = []

    p1: Doc = [("title", "RESIDENTIAL LEASE AGREEMENT" if c.style == "state" else "APARTMENT LEASE CONTRACT")]
    if c.style == "table":
        p1 += [
            ("p", f"Community: {prop_name}"),
            ("p", f"Owner: {c.owner}"),
            ("p", f"Resident(s): {c.tenant_display}"),
            ("p", f"Premises Address: {c.full_address}"),
            ("p", f"{c.unit_label} {c.unit}" if c.unit_label != "Unit" else f"Unit: {c.unit}"),
            ("p", f"Lease Start Date: {c.d(c.start)}"),
            ("p", f"Lease End Date: {c.d(c.end)}"),
            ("p", (f"Monthly Rent: {money(c.rent)}" if not c.rent_in_words_only
                   else f"Monthly Rent: {words(int(c.rent))} Dollars")),
            ("p", f"Security Deposit: {money(c.deposit)}"),
        ]
        if c.manager:
            p1.append(("p", f"Managing Agent: {c.manager}"))
        p1 += [
            ("h", "1. PARTIES AND APARTMENT."),
            ("p", f"The Owner and Resident(s) named above agree to the terms of this Lease for the "
                  f"apartment described above (the \"Apartment\") at {prop_name}."),
        ]
    else:
        p1 += [
            ("h", "1. PARTIES."),
            ("p", _parties_clause(c)),
            ("h", "2. PREMISES."),
            ("p", f"{owner_word} leases to {who}, and {who} leases from {owner_word}, the dwelling "
                  f"located at {c.full_address} (the \"Premises\"), at the community known as {prop_name}."),
            ("h", "3. TERM."),
            ("p", (f"The term of this Lease shall commence on {c.d(c.start)} and shall end on "
                   f"{c.d(c.end)}, at 11:59 p.m., unless sooner terminated as provided herein."
                   if c.style == "state" else
                   f"The initial term of the Lease begins on {c.d(c.start)} and ends at 11:59 p.m. on "
                   f"{c.d(c.end)}.")),
            ("h", "4. RENT."),
            ("p", _rent_sentence(c, who, owner_word)),
            ("h", "5. SECURITY DEPOSIT."),
            ("p", f"Upon signing this Lease, {who} shall pay a security deposit of {money(c.deposit)}, "
                  f"which {owner_word} will hold as security for {who}'s performance."),
        ]
    pages.append(p1)

    p2: Doc = []
    n = 6
    if c.concession:
        p2 += [("h", f"{n}. RENT CONCESSION."), ("p", c.concession)]
        n += 1
    p2 += [
        ("h", f"{n}. LATE CHARGES."),
        ("p", f"If rent is not received by 11:59 p.m. on the 3rd day of the month, {who} will pay an "
              f"initial late charge of $50.00 plus $10.00 per day thereafter, not to exceed $150.00."),
    ]
    n += 1
    p2 += [
        ("h", f"{n}. UTILITIES."),
        ("p", (f"{who} shall pay for electricity and gas service directly to the provider. "
               + ("Other utility charges are described in the Utility Addendum." if c.utilities else
                  f"{owner_word} pays for water, sewer, and trash."))),
    ]
    n += 1
    p2 += [
        ("h", f"{n}. ANIMALS."),
        ("p", ("Animals are permitted only as described in the Pet Addendum." if c.pet else
               f"No animals (including mammals, reptiles, birds, fish, and insects) are allowed, even "
               f"temporarily, unless {owner_word} has given written permission.")),
    ]
    n += 1
    p2 += [
        ("h", f"{n}. PARKING."),
        ("p", ("Parking is governed by the Parking Addendum." if c.parking else
               f"{who} may park in unassigned spaces at no additional charge, subject to the community rules.")),
    ]
    n += 1
    p2 += [
        ("h", f"{n}. DEFAULT."),
        ("p", f"If {who} fails to pay rent when due, {owner_word} may end {who}'s right of occupancy by "
              f"giving {who} a 3-day written notice to vacate, as permitted by law."),
        ("h", f"{n + 1}. OCCUPANTS."),
        ("p", f"The Apartment will be occupied only by the persons named in this Lease and their minor children."),
    ]
    pages.append(p2)

    sig: Doc = [
        ("h", "SIGNATURES."),
        ("p", f"{owner_word.upper()}: {c.owner}"),
        ("p", f"By: ______________________ {('as agent, ' + c.manager) if c.manager else 'Authorized Signatory'}"),
    ]
    for r in c.residents:
        sig.append(("p", f"{who.upper()}: ______________________ {r}"))
    sig.append(("p", f"Date signed: {c.d(c.start - timedelta(days=12))}"))
    pages[-1] += sig
    return pages


def pet_addendum(c: Case) -> Doc:
    p = c.pet or {}
    who = "Tenant" if c.style == "state" else "Resident"
    body: Doc = [("title", "PET ADDENDUM"),
                 ("p", f"This Pet Addendum is attached to and part of the Lease for {c.full_address} "
                       f"between {c.owner} and {c.tenant_display}.")]
    lines = []
    if p.get("monthly_rent"):
        lines.append(("p", f"Monthly Pet Rent: {money(p['monthly_rent'])} per month, in addition to rent."
                      if c.case_id[-1] in "02468" else
                      f"{who} agrees to pay additional monthly rent of {money(p['monthly_rent'])} for the animal."))
    if p.get("fee"):
        lines.append(("p", f"{who} shall pay a one-time non-refundable pet fee of {money(p['fee'])}."))
    if p.get("deposit"):
        lines.append(("p", f"Additional Pet Deposit: {money(p['deposit'])}. The pet deposit is refundable "
                           f"and is considered part of the general security deposit."))
    body += lines
    body += [("p", "Animal: one (1) domestic cat, spayed, approximately 9 lbs. No other animals are authorized."),
             ("p", f"{who} is liable for all damage caused by the animal.")]
    return body


def parking_addendum(c: Case) -> Doc:
    pk = c.parking or {}
    who = "Tenant" if c.style == "state" else "Resident"
    return [("title", "PARKING ADDENDUM"),
            ("p", f"Assigned Space: {pk['space']}"),
            ("p", (f"Monthly Parking Fee: {money(pk['monthly_fee'])}" if pk.get("label") != "garage" else
                   f"{who} will pay a garage rental fee of {money(pk['monthly_fee'])} per month for detached garage {pk['space']}.")),
            ("p", "Vehicles without a valid permit are subject to towing at the owner's expense."),
            ("p", f"This addendum is part of the Lease for {c.full_address}.")]


def utility_addendum(c: Case) -> Doc:
    u = c.utilities or {}
    who = "Tenant" if c.style == "state" else "Resident"
    body: Doc = [("title", "UTILITY AND SERVICES ADDENDUM"),
                 ("p", f"This addendum is attached to the Lease for {c.full_address}.")]
    rubs = u.get("rubs") or []
    if rubs:
        names = ", ".join(rubs[:-1]) + (" and " + rubs[-1] if len(rubs) > 1 else rubs[0])
        body.append(("p", f"{names[0].upper() + names[1:]} service to the Apartment will be billed to {who} by "
                          f"Owner using a ratio utility billing system (RUBS) allocation based on the number of "
                          f"occupants and square footage. These charges vary monthly and are additional rent."))
    for name, amt in (u.get("flat") or {}).items():
        body.append(("p", f"{name}: {money(amt)} per month flat fee"))
    body.append(("p", f"{who} is responsible for establishing electric service in {who}'s name before move-in."))
    return body


def tenancy_addendum(c: Case) -> Doc:
    s = c.section8 or {}
    return [
        ("title", "TENANCY ADDENDUM"),
        ("p", "Section 8 Tenant-Based Assistance, Housing Choice Voucher Program"),
        ("p", "(To be attached to Tenant Lease)"),
        ("h", "1. Section 8 Voucher Program"),
        ("p", f"a. The owner is leasing the contract unit to the tenant for occupancy by the tenant's family "
              f"with assistance for a tenancy under the Section 8 housing choice voucher program of the "
              f"United States Department of Housing and Urban Development (HUD)."),
        ("p", f"b. The owner has entered into a Housing Assistance Payments Contract (HAP contract) with "
              f"{s['pha']} (the \"PHA\") under the voucher program. Under the HAP contract, the PHA will make "
              f"housing assistance payments to the owner to assist the tenant in leasing the unit from the owner."),
        ("h", "2. Lease"),
        ("p", "a. The owner has given the PHA a copy of the lease, including any revisions agreed by the owner and the tenant."),
        ("h", "4. Rent to Owner"),
        ("p", f"a. The initial rent to owner may not exceed the amount approved by the PHA in accordance with HUD requirements."),
        ("p", f"b. Changes in the rent to owner shall be determined by the provisions of the lease."),
        ("h", "5. Family Payment to Owner"),
        ("p", "a. The family is responsible for paying the owner any portion of the rent to owner that is not "
              "covered by the PHA housing assistance payment."),
        ("p", f"Tenant Rent: {money(s['tenant_rent'])} per month"),
    ]


def hap_contract(c: Case) -> Doc:
    s = c.section8 or {}
    hap_start = s.get("hap_start", c.start)
    body: Doc = [
        ("title", "HOUSING ASSISTANCE PAYMENTS CONTRACT (HAP CONTRACT)"),
        ("p", "Section 8 Tenant-Based Assistance, Housing Choice Voucher Program"),
        ("h", "Part A of the HAP Contract: Contract Information"),
        ("p", f"1. Contents of Contract. This HAP contract is between {s['pha']} and {c.owner}."),
        ("p", f"2. Tenant: {c.residents[0]}"),
        ("p", f"3. Contract Unit: {c.full_address}"),
        ("p", f"4. Initial Lease Term. The initial lease term begins on: {c.d(c.start)}. "
              f"The initial lease term ends on: {c.d(c.end)}."),
        ("p", f"5. Initial Rent to Owner. The initial rent to owner is: {money(c.rent)}."),
        ("p", f"6. Housing Assistance Payment. The initial housing assistance payment is: {money(s['hap'])} per month."),
    ]
    if s.get("ua") is not None:
        body.append(("p", f"7. Utility Allowance: {money(s['ua'])} per month (tenant-paid electric)."))
    body.append(("p", f"The HAP contract term begins on {c.d(hap_start)} and ends on the last day of the lease term."))
    return body


def change_doc(c: Case, ch: Dict[str, Any]) -> Doc:
    who = "Tenant" if c.style == "state" else "Resident"
    owner_word = "Landlord" if c.style == "state" else "Owner"
    if ch["kind"] == "renewal":
        body: Doc = [
            ("title", "LEASE RENEWAL AGREEMENT"),
            ("p", f'This Renewal Agreement is between {c.owner} ("{owner_word}") and {c.tenant_display} '
                  f'("{who}") for {c.full_address}.'),
            ("p", f"The Lease dated {c.d(c.start)} is renewed for a term beginning {c.d(ch['effective'])} "
                  f"and ending {c.d(ch['new_end'])}."),
        ]
        if ch.get("new_rent") is not None:
            body.append(("p", f"Effective {c.d(ch['effective'])}, the monthly rent shall be {money(ch['new_rent'])}."))
        body.append(("p", "All other terms of the Lease remain in full force and effect."))
        return body
    # mid-term amendment
    body = [
        ("title", "FIRST AMENDMENT TO LEASE"),
        ("p", f"This First Amendment amends the Lease between {c.owner} and {c.tenant_display} for {c.full_address}."),
    ]
    if ch.get("new_rent") is not None:
        body.append(("p", f"Effective {c.d(ch['effective'])}, monthly rent is changed to {money(ch['new_rent'])} per month."))
    if ch.get("new_end") is not None:
        body.append(("p", f"The expiration date of the Lease is extended to {c.d(ch['new_end'])}."))
    body.append(("p", "Except as amended here, the Lease is unchanged."))
    return body


def case_pages(c: Case) -> List[Doc]:
    pages = lease_doc(c)
    if c.section8:
        pages += [tenancy_addendum(c), hap_contract(c)]
    if c.pet:
        pages.append(pet_addendum(c))
    if c.parking:
        pages.append(parking_addendum(c))
    if c.utilities:
        pages.append(utility_addendum(c))
    for ch in c.changes:
        pages.append(change_doc(c, ch))
    if c.second_lease:
        pages += case_pages(c.second_lease)
    return pages


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------

def render_text_pdf(pages: List[Doc], path: str) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=14)
    head = ParagraphStyle("h", parent=styles["Heading4"], spaceBefore=6)
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=10, leading=13)
    story = []
    for i, page in enumerate(pages):
        if i:
            story.append(PageBreak())
        for kind, text in page:
            text = text.replace("&", "&amp;").replace("<", "&lt;")
            story.append(Paragraph(text, {"title": title, "h": head}.get(kind, body)))
            if kind == "title":
                story.append(Spacer(1, 6))
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=inch, rightMargin=inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            title="Synthetic lease (fictional)", author="Abstractly test corpus")
    doc.build(story)


def render_scanned_pdf(pages: List[Doc], path: str, rng: random.Random) -> None:
    """Image-only PDF: each page is a slightly skewed, noisy picture of the text."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
        bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except Exception:  # non-macOS: OCR will be worse, still exercises the path
        font = bold = ImageFont.load_default()
    images = []
    for page in pages:
        img = Image.new("L", (1700, 2200), color=255)
        draw = ImageDraw.Draw(img)
        y = 110
        for kind, text in page:
            f = bold if kind in ("title", "h") else font
            for line in textwrap.wrap(text, width=82 if f is font else 66) or [""]:
                draw.text((120, y), line, fill=rng.randint(0, 50), font=f)
                y += 44
            y += 14
        # scanner artifacts: light speckle, a tiny rotation, a soft blur
        for _ in range(1500):
            img.putpixel((rng.randrange(1700), rng.randrange(2200)), rng.randint(120, 200))
        img = img.rotate(rng.uniform(-0.8, 0.8), fillcolor=255, expand=False)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        images.append(img.convert("RGB"))
    images[0].save(path, "PDF", resolution=200.0, save_all=True, append_images=images[1:])


def render_mixed_pdf(pages: List[Doc], n_text: int, path: str, rng: random.Random) -> None:
    """The lease's own pages as text, every attachment after them as a scanned image page."""
    from pypdf import PdfReader, PdfWriter

    tmp_text, tmp_scan = path + ".text.pdf", path + ".scan.pdf"
    render_text_pdf(pages[:n_text], tmp_text)
    render_scanned_pdf(pages[n_text:], tmp_scan, rng)
    writer = PdfWriter()
    for part in (tmp_text, tmp_scan):
        for page in PdfReader(part).pages:
            writer.add_page(page)
    with open(path, "wb") as fh:
        writer.write(fh)
    os.remove(tmp_text)
    os.remove(tmp_scan)


# ----------------------------------------------------------------------
# Case factory
# ----------------------------------------------------------------------

CONCESSIONS = [
    "One (1) month of rent is free as a move-in special: Resident's rent for the first full month of the Lease is waived.",
    "Rent is reduced by $100.00 per month for the first six (6) months of the Lease term as a move-in concession.",
    "As a look-and-lease special, Resident will receive a one-time rent credit of $500.00 applied to the second month's rent.",
]


class Factory:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.n = 0

    def person(self) -> str:
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    def base(self, family: str, **kw) -> Case:
        r = self.rng
        self.n += 1
        prop = r.choice(PROPERTIES)
        start = date(r.choice([2025, 2026]), r.randint(1, 12), 1)
        months = r.choice([12, 12, 12, 13, 6, 15])
        end = add_months(start, months) - timedelta(days=1)
        rent = float(r.randrange(850, 2400, 5))
        unit_label = r.choice(["Apartment No.", "Unit #", "Apt.", "Unit"])
        unit = r.choice([str(r.randint(101, 428)), f"{r.randint(1, 9)}{r.choice('ABCD')}",
                         f"{r.choice('ABCDE')}-{r.randint(101, 320)}"])
        c = Case(
            case_id=f"L{self.n:03d}",
            family=family,
            style=r.choice(["table", "prose", "state"]),
            residents=[self.person()] + ([self.person()] if r.random() < 0.35 else []),
            owner=f"{prop[0]} {r.choice(OWNER_SUFFIX)}",
            manager=r.choice(MANAGERS) if r.random() < 0.5 else None,
            prop=prop, unit=unit, unit_label=unit_label,
            rent=rent, deposit=r.choice([rent, 500.0, 300.0, round(rent / 2, 2)]),
            start=start, end=end,
            date_fmt=r.choice(["long", "long", "slash"]),
        )
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    def section8(self, c: Case) -> None:
        r = self.rng
        tenant_rent = float(r.randrange(0, int(c.rent * 0.45), 1))
        c.section8 = {"pha": r.choice(PHAS), "tenant_rent": tenant_rent,
                      "hap": round(c.rent - tenant_rent, 2),
                      "ua": float(r.choice([None, 64, 88, 112, 135]) or 0) or None}

    def pet(self, c: Case) -> None:
        r = self.rng
        c.pet = {"monthly_rent": float(r.choice([25, 35, 40, 50])),
                 "fee": float(r.choice([0, 250, 300, 400])) or None,
                 "deposit": float(r.choice([0, 200, 250, 500])) or None}

    def parking(self, c: Case) -> None:
        r = self.rng
        garage = r.random() < 0.4
        c.parking = {"monthly_fee": float(r.choice([125, 150, 95]) if garage else r.choice([35, 50, 75])),
                     "space": f"G-{r.randint(1, 40)}" if garage else f"P-{r.randint(1, 220)}",
                     "label": "garage" if garage else "space"}

    def utilities(self, c: Case, rubs: bool, flat: bool) -> None:
        r = self.rng
        u: Dict[str, Any] = {}
        if rubs:
            u["rubs"] = r.choice([["water", "sewer", "trash"], ["water", "sewer"], ["water", "sewer", "trash", "gas"]])
        if flat:
            u["flat"] = dict(r.sample([("Valet Trash", 25.0), ("Pest Control", 3.0), ("Trash", 15.0),
                                       ("Cable and Internet Package", 65.0)], r.choice([1, 2])))
        c.utilities = u

    def renewal(self, c: Case, rent_change: bool = True) -> None:
        eff = c.end + timedelta(days=1)
        c.changes.append({"kind": "renewal", "effective": eff,
                          "new_end": add_months(eff, 12) - timedelta(days=1),
                          "new_rent": round(c.rent * 1.04 / 5) * 5.0 if rent_change else None})

    def amendment(self, c: Case) -> None:
        eff = add_months(c.start, self.rng.randint(3, 6))
        c.changes.append({"kind": "amendment", "effective": eff,
                          "new_end": None, "new_rent": c.rent - self.rng.choice([25, 50, 75])})


def build_cases(seed: int) -> List[Case]:
    f = Factory(seed)
    cases: List[Case] = []

    def add(c: Case) -> Case:
        cases.append(c)
        return c

    # Standard multifamily, every style
    for _ in range(8):
        add(f.base("standard"))
    # Odd formats
    add(f.base("standard_rent_in_words", rent_in_words_only=True, style="prose"))
    add(f.base("standard_slash_dates", date_fmt="slash"))
    # Concessions
    for text in CONCESSIONS:
        add(f.base("concession", concession=text))
    # Pets / parking / utilities
    for _ in range(3):
        c = add(f.base("pet")); f.pet(c)
    for _ in range(3):
        c = add(f.base("parking")); f.parking(c)
    for rubs, flat in [(True, False), (False, True), (True, True), (True, False)]:
        c = add(f.base("utilities")); f.utilities(c, rubs, flat)
    # Kitchen sink: pet + parking + utilities + concession
    for _ in range(2):
        c = add(f.base("all_charges", concession=f.rng.choice(CONCESSIONS)))
        f.pet(c); f.parking(c); f.utilities(c, True, True)
    # Section 8
    for _ in range(5):
        c = add(f.base("section8")); f.section8(c)
    c = add(f.base("section8_with_charges")); f.section8(c); f.pet(c); f.utilities(c, False, True)
    c = add(f.base("section8_renewal")); f.section8(c); f.renewal(c)
    # Renewals / amendments
    for _ in range(3):
        c = add(f.base("renewal")); f.renewal(c)
    c = add(f.base("renewal_same_rent")); f.renewal(c, rent_change=False)
    for _ in range(2):
        c = add(f.base("amendment")); f.amendment(c)
    # Two genuinely separate leases in one file (must still split)
    c = add(f.base("two_leases"))
    c.second_lease = f.base("two_leases_second")
    f.n -= 0  # second lease keeps its own id for readability
    # Scanned: image-only versions of several families
    for fam, setup in [("scanned_standard", None), ("scanned_section8", f.section8),
                       ("scanned_pet", f.pet), ("scanned_renewal", f.renewal),
                       ("scanned_standard", None), ("scanned_parking", f.parking)]:
        c = add(f.base(fam, scanned=True))
        if setup:
            setup(c)
    # Typed lease, scanned attachments (a signed HUD addendum / HAP contract
    # or renewal faxed back): only those pages need OCR.
    for fam, setup in [("mixed_scan_section8", f.section8), ("mixed_scan_renewal", f.renewal),
                       ("mixed_scan_pet", f.pet)]:
        c = add(f.base(fam, scanned_attachments=True))
        setup(c)
    return cases


def generate(out: str, seed: int = 7, only: Optional[str] = None) -> Dict[str, Any]:
    os.makedirs(out, exist_ok=True)
    rng = random.Random(seed + 1)
    manifest: Dict[str, Any] = {"seed": seed, "note": "Synthetic, fictional leases. Not customer data.", "cases": []}
    for c in build_cases(seed):
        if only and not c.family.startswith(only):
            continue
        fname = f"{c.case_id}_{c.family}.pdf"
        path = os.path.join(out, fname)
        pages = case_pages(c)
        if c.scanned:
            render_scanned_pdf(pages, path, rng)
        elif c.scanned_attachments:
            render_mixed_pdf(pages, len(lease_doc(c)), path, rng)
        else:
            render_text_pdf(pages, path)
        exp = c.expected()
        entry = {"file": fname, "case_id": c.case_id, "family": c.family, "style": c.style,
                 "scanned": c.scanned or c.scanned_attachments, "expected_lease_count": 2 if c.second_lease else 1, **exp}
        if c.second_lease:
            entry["second_lease"] = c.second_lease.expected()["fields"]
        manifest["cases"].append(entry)
    with open(os.path.join(out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default=None, help="only families starting with this prefix")
    a = ap.parse_args(argv)
    m = generate(a.out, a.seed, a.only)
    print(f"Wrote {len(m['cases'])} synthetic leases + manifest.json to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
