"""
Synthetic test corpus generator for the extraction/validation pipeline.

Produces a large, reproducible batch of documents with KNOWN GROUND
TRUTH, deliberately messy in the ways real commercial lease documents
and broker/PMS rent rolls actually are:

  - lease documents (PDF / DOCX / TXT): label-style vs defined-term
    parties, numeric / long-form / legal ("1st day of...") dates,
    annual-with-monthly-parenthetical vs plain monthly rent, whole
    clauses missing by design, light OCR-style character noise on the
    "scanned" ones, single- and multi-page.
  - rent rolls (CSV / XLSX): decorative title/date rows before the real
    header, each vendor's own column terminology, a Market-Rent column
    next to the actual rent, VACANT rows, a trailing Totals row,
    merged-cell-style group values (only the first row of a property
    group carries the property name), mixed date formats, currency with
    and without "$", stray whitespace, a few tenant-name typos, some
    rows missing rent. Every real tenant row is tied back to a lease's
    ground truth so rent-roll-vs-lease validation can be scored too.
  - garbage: a plain business memo, an invoice, a truncated/corrupt
    PDF, an empty file, an image-only page of gibberish -- to exercise
    the "this isn't a lease" / "can't process this" paths.

Output: a directory of files + `manifest.json`. Nothing here touches
the database or the network; it only writes files.

Usage:
    venv/bin/python tests/generate_synthetic_corpus.py \
        --out tests/synthetic_corpus --leases 60 --seed 7

The default output dir (tests/synthetic_corpus/) is gitignored -- this
is a generator, not a committed fixture set. Re-run with the same seed
for the same corpus.
"""

import argparse
import io
import json
import os
import random
import string
from datetime import date, timedelta

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover - docx is a hard dep of the app, but be defensive
    DocxDocument = None

import openpyxl
from PIL import Image, ImageDraw


# ----------------------------------------------------------------------
# Random building blocks
# ----------------------------------------------------------------------

_TENANT_CORES = [
    "Blue Sky Coffee Roasters", "Cascade Apparel", "Ironwood Fitness", "Meridian Dental Group",
    "Northgate Pediatrics", "Riverside Books", "Summit Outdoor Supply", "Golden Spoon Bakery",
    "Harbor Point Insurance", "Cedar & Sage Home", "Lumen Optometry", "Trailhead Bicycle",
    "Vista Physical Therapy", "Copperline Barbers", "Brightwater Cleaners", "Fieldstone Realty",
    "Pinecrest Veterinary", "Anchor Marine Services", "Willow Creek Florist", "Granite State Tax",
]
_TENANT_SUFFIXES = ["Inc.", "LLC", "Co.", "Corp.", "L.L.C.", "LP", "Ltd.", ""]
_LANDLORD_NAMES = [
    "Harborview Retail Partners LP", "Meridian Property Holdings LLC", "Oakmont Commercial Trust",
    "Riverside Plaza Associates", "Summit Ridge Investors LLC", "Beacon Hill Real Estate Co.",
    "Northpoint Asset Management LLC", "Evergreen Property Group",
]
_STREETS = [
    "Riverside Plaza", "Main Street", "Commerce Boulevard", "Market Square", "Industrial Parkway",
    "Lakeview Drive", "Cedar Avenue", "Broadway", "Harbor Way", "Sunset Boulevard",
]
_CITIES = [("Portland", "Oregon", "97201"), ("Austin", "Texas", "78701"), ("Denver", "Colorado", "80202"),
           ("Raleigh", "North Carolina", "27601"), ("Boise", "Idaho", "83702")]
_USE_CLAUSES = [
    "a retail coffee shop and roastery", "a general retail store selling apparel and accessories",
    "a fitness and personal-training studio", "a dental practice and related office use",
    "a bookstore and cafe", "a bicycle sales and repair shop", "a veterinary clinic",
    "professional and administrative offices",
]


def _rand_date(rng, start_year=2022, end_year=2027):
    start = date(start_year, 1, 1)
    return start + timedelta(days=rng.randint(0, (date(end_year, 12, 31) - start).days))


def _fmt_date(d, style):
    if style == "numeric_slash":
        return d.strftime("%m/%d/%Y")
    if style == "numeric_dash":
        return d.strftime("%-m-%-d-%y")
    if style == "long":
        return d.strftime("%B %-d, %Y")
    if style == "long_abbr":
        return d.strftime("%b %-d, %Y")
    if style == "legal":
        day = d.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}{suffix} day of {d.strftime('%B')}, {d.year}"
    if style == "iso":
        return d.strftime("%Y-%m-%d")
    return d.strftime("%m/%d/%Y")


def _money(n, *, cents=True, dollar=True):
    s = f"{n:,.2f}" if cents else f"{n:,.0f}"
    return f"${s}" if dollar else s


def _ocr_noise(text, rng, rate):
    """Light, realistic scan noise: l<->1, O<->0, occasional dropped/dup char."""
    if rate <= 0:
        return text
    swaps = {"l": "1", "I": "1", "O": "0", "o": "0", "S": "5", "B": "8"}
    out = []
    for ch in text:
        r = rng.random()
        if r < rate and ch in swaps:
            out.append(swaps[ch])
        elif r < rate * 0.3:
            continue  # dropped char
        else:
            out.append(ch)
    return "".join(out)


# ----------------------------------------------------------------------
# Lease spec + ground truth
# ----------------------------------------------------------------------

def make_lease_spec(rng, index):
    core = rng.choice(_TENANT_CORES)
    suffix = rng.choice(_TENANT_SUFFIXES)
    tenant = f"{core}, {suffix}".rstrip(", ") if suffix else core
    landlord = rng.choice(_LANDLORD_NAMES)
    street_num = rng.randint(100, 9999)
    street = rng.choice(_STREETS)
    city, state, zip_code = rng.choice(_CITIES)
    unit = rng.choice(["", f", Suite {rng.randint(100, 950)}", f", Unit {rng.randint(1, 40)}"])
    address = f"{street_num} {street}{unit}"
    full_address = f"{address}, {city}, {state} {zip_code}"

    start = _rand_date(rng)
    term_years = rng.choice([3, 5, 7, 10])
    end = date(start.year + term_years, start.month, max(1, start.day - 1))

    monthly_rent = rng.choice([1800, 2500, 3250, 4000, 5500, 6250, 7800, 9500, 12000])
    sqft = rng.choice([850, 1200, 1800, 2400, 3200, 4500, 6000])
    has_deposit = rng.random() < 0.75
    deposit = monthly_rent * rng.choice([1, 1, 2])
    has_cam = rng.random() < 0.55
    cam = rng.choice([250, 350, 500, 1200])
    has_escalation = rng.random() < 0.7
    escalation_pct = rng.choice([2, 2.5, 3, 3.5])
    has_renewal = rng.random() < 0.65
    renewal_count = rng.choice([1, 1, 2])
    renewal_years = rng.choice([3, 5])
    renewal_notice = rng.choice([90, 120, 180, 270])
    has_exclusivity = rng.random() < 0.35
    has_insurance = rng.random() < 0.7
    insurance_limit = rng.choice([1_000_000, 2_000_000, 3_000_000])
    cure_days = rng.choice([5, 10, 15, 30])
    use_clause = rng.choice(_USE_CLAUSES)

    date_style = rng.choice(["numeric_slash", "numeric_dash", "long", "long_abbr", "legal", "iso"])
    party_style = rng.choice(["label", "defined_term"])
    fmt = rng.choices(["pdf", "pdf", "pdf", "docx", "txt"], k=1)[0]
    scanned = fmt == "pdf" and rng.random() < 0.25
    pages = rng.choice([1, 1, 2, 3])

    gt = {
        "tenant": tenant,
        "landlord": landlord,
        "rent_amount": _money(monthly_rent),
        "lease_start_date": _fmt_date(start, "long"),
        "lease_end_date": _fmt_date(end, "long"),
        "property_address": address,
        "security_deposit": _money(deposit) if has_deposit else None,
        "cam_charges": _money(cam) if has_cam else None,
        "rent_escalation": f"{escalation_pct}% annually" if has_escalation else None,
        "renewal_options": f"{renewal_count} option(s) of {renewal_years} year(s)" if has_renewal else None,
        "permitted_use": use_clause,
        "exclusivity_clause": "exclusive use" if has_exclusivity else None,
        "insurance_requirements": _money(insurance_limit, cents=False) if has_insurance else None,
        "default_cure_period": f"{cure_days} days after written notice",
        "square_footage": f"{sqft:,} sq ft",
    }

    spec = {
        "id": f"lease_{index:04d}",
        "kind": "lease",
        "format": fmt,
        "scanned": scanned,
        "pages": pages,
        "style": {"date_style": date_style, "party_style": party_style},
        "ground_truth": gt,
        # raw values kept for the rent-roll cross-reference
        "_raw": {
            "tenant": tenant, "monthly_rent": monthly_rent, "sqft": sqft,
            "start": start.isoformat(), "end": end.isoformat(),
            "full_address": full_address, "address": address,
            "deposit": deposit if has_deposit else None,
        },
        "_body": {
            "start": start, "end": end, "monthly_rent": monthly_rent, "sqft": sqft,
            "deposit": deposit, "has_deposit": has_deposit, "has_cam": has_cam, "cam": cam,
            "has_escalation": has_escalation, "escalation_pct": escalation_pct,
            "has_renewal": has_renewal, "renewal_count": renewal_count, "renewal_years": renewal_years,
            "renewal_notice": renewal_notice, "has_exclusivity": has_exclusivity,
            "has_insurance": has_insurance, "insurance_limit": insurance_limit,
            "cure_days": cure_days, "use_clause": use_clause, "full_address": full_address,
            "tenant": tenant, "landlord": landlord, "date_style": date_style, "party_style": party_style,
        },
    }
    return spec


def _lease_paragraphs(spec, rng):
    b = spec["_body"]
    ds = b["date_style"]
    start_s, end_s = _fmt_date(b["start"], ds), _fmt_date(b["end"], ds)

    if b["party_style"] == "label":
        parties = [f"LANDLORD: {b['landlord']}", f"TENANT: {b['tenant']}"]
    else:
        parties = [
            f"This Lease Agreement is entered into by and between {b['landlord']} "
            f'("Landlord") and {b["tenant"]} ("Tenant").'
        ]

    paras = ["COMMERCIAL LEASE AGREEMENT", ""]
    paras += parties
    paras += [
        f"PREMISES: The Landlord leases to Tenant the premises located at {b['full_address']} "
        f'(the "Premises"), consisting of approximately {b["sqft"]:,} square feet of rentable area.',
        "",
    ]
    if ds == "legal":
        paras.append(f"TERM: The term of this Lease shall commence on the {start_s} and shall "
                     f"expire on the {end_s}, unless sooner terminated as provided herein.")
    else:
        paras.append(f"TERM: The Lease term shall commence on {start_s} and end on {end_s}.")
    paras.append("")

    if rng.random() < 0.5:
        annual = b["monthly_rent"] * 12
        paras.append(f"RENT. Base Rent shall be {_money(annual)} per annum "
                     f"({_money(b['monthly_rent'])} per month), payable in advance on the first day of each month.")
    else:
        paras.append(f"RENT. Tenant shall pay Base Rent of {_money(b['monthly_rent'])} per month, "
                     f"due on the first day of each calendar month.")
    paras.append("")

    if b["has_escalation"]:
        if rng.random() < 0.5:
            r = b["monthly_rent"]
            yr_lines = []
            for yr in range(1, 4):
                yr_lines.append(f"Year {yr}: {_money(r)}")
                r = round(r * (1 + b["escalation_pct"] / 100), 2)
            paras.append("RENT ESCALATION. Base Rent shall increase according to the following schedule: "
                         + "; ".join(yr_lines) + f", with the same {b['escalation_pct']}% increase applied each year thereafter.")
        else:
            paras.append(f"RENT ESCALATION. On each anniversary of the Commencement Date, Base Rent shall "
                         f"increase by {b['escalation_pct']}% ({b['escalation_pct']}%) over the prior year's Base Rent.")
        paras.append("")

    if b["has_deposit"]:
        paras.append(f"SECURITY DEPOSIT. Upon execution of this Lease, Tenant shall deposit with Landlord "
                     f"the sum of {_money(b['deposit'])} as security for Tenant's performance.")
        paras.append("")

    if b["has_cam"]:
        paras.append(f"COMMON AREA MAINTENANCE. Tenant's CAM contribution shall be {_money(b['cam'])} per month, "
                     f"subject to annual reconciliation against actual operating costs.")
        paras.append("")

    if b["has_renewal"]:
        paras.append(f"RENEWAL. Tenant shall have {b['renewal_count']} option(s) to renew this Lease, each for "
                     f"an additional term of {b['renewal_years']} years, upon not less than {b['renewal_notice']} days' "
                     f"prior written notice; renewal Base Rent shall be the then-prevailing fair market rate.")
        paras.append("")

    paras.append(f"PERMITTED USE. Tenant shall use the Premises solely for the operation of {b['use_clause']}, "
                 f"and for no other purpose without Landlord's prior written consent.")
    paras.append("")

    if b["has_exclusivity"]:
        paras.append("EXCLUSIVE USE. Landlord covenants that, so long as Tenant is not in default, Landlord shall "
                     "not lease any other premises in the shopping center to a tenant whose primary use is the same "
                     "as Tenant's permitted use.")
        paras.append("")

    if b["has_insurance"]:
        paras.append(f"INSURANCE. Tenant shall maintain commercial general liability insurance of not less than "
                     f"{_money(b['insurance_limit'], cents=False)} per occurrence, naming Landlord as additional insured.")
        paras.append("")

    paras.append(f"DEFAULT. If Tenant fails to cure any default within {b['cure_days']} days after written notice "
                 f"from Landlord, Tenant shall be in default under this Lease.")
    return paras


# ----------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------

def _write_pdf(path, paragraphs, rng, *, pages=1, noise=0.0):
    c = canvas.Canvas(path, pagesize=letter, invariant=1)
    width, height = letter
    left, right = 1 * inch, width - 1 * inch
    max_w = right - left

    def wrap(text, font, size):
        words, lines, cur = text.split(" "), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if c.stringWidth(trial, font, size) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    y = height - 1 * inch
    per_page_break = max(1, len(paragraphs) // pages)
    para_count = 0
    c.setFont("Helvetica", 11)
    for para in paragraphs:
        para = _ocr_noise(para, rng, noise)
        if para == "":
            y -= 0.16 * inch
            continue
        bold = para.isupper() and len(para) < 60
        font = "Helvetica-Bold" if bold else "Helvetica"
        for line in wrap(para, font, 11):
            if y < 1 * inch:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - 1 * inch
            c.setFont(font, 11)
            c.drawString(left, y, line)
            y -= 0.22 * inch
        para_count += 1
        if pages > 1 and para_count % per_page_break == 0 and y < height - 2 * inch:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - 1 * inch
    c.save()


def _write_docx(path, paragraphs):
    doc = DocxDocument()
    for para in paragraphs:
        if para == "":
            continue
        doc.add_paragraph(para)
    doc.save(path)


def _write_txt(path, paragraphs):
    with open(path, "w") as f:
        f.write("\n".join(p for p in paragraphs if p != "") + "\n")


def render_lease(spec, out_dir, rng):
    paragraphs = _lease_paragraphs(spec, rng)
    fmt = spec["format"]
    if fmt == "docx" and DocxDocument is not None:
        path = os.path.join(out_dir, f"{spec['id']}.docx")
        _write_docx(path, paragraphs)
    elif fmt == "txt":
        path = os.path.join(out_dir, f"{spec['id']}.txt")
        _write_txt(path, paragraphs)
    else:
        spec["format"] = "pdf"
        path = os.path.join(out_dir, f"{spec['id']}.pdf")
        _write_pdf(path, paragraphs, rng, pages=spec["pages"], noise=0.05 if spec["scanned"] else 0.0)
    return os.path.basename(path)


# ----------------------------------------------------------------------
# Rent rolls
# ----------------------------------------------------------------------

_VENDOR_HEADERS = {
    "broker_a": ["Suite", "Tenant Name", "SF", "Lease Start", "Lease End", "Monthly Rent", "Security Dep", "Notes"],
    "yardi": ["Unit", "Resident", "Sq Ft", "Move In", "Lease To", "Market Rent", "Rent Charge", "Deposit"],
    "appfolio": ["Unit", "Tenant", "Property", "Sqft", "Start", "End", "Rent", "Deposit Held"],
    "realpage": ["Bldg-Unit", "Resident Name", "SqFt", "Lease Begin", "Lease Expire", "Scheduled Rent", "Dep"],
    "generic": ["unit", "tenant", "sf", "start date", "end date", "rent", "deposit"],
}


def _rr_date(iso, rng):
    d = date.fromisoformat(iso)
    return _fmt_date(d, rng.choice(["numeric_slash", "iso", "long_abbr", "numeric_dash"]))


def render_rent_roll(lease_specs, out_dir, rng, *, name, vendor, mess=True, as_xlsx=False):
    """
    Build one rent roll covering a sample of the given leases (plus a
    few phantom units with no lease on file). Returns (filename,
    ground_truth) where ground_truth maps each real row to the lease id
    it came from and any DELIBERATE injected disagreement.
    """
    headers = list(_VENDOR_HEADERS[vendor])
    chosen = rng.sample(lease_specs, min(len(lease_specs), rng.randint(4, 9)))

    title_rows = []
    if mess:
        title_rows = [
            [f"SYNTHETIC RENT ROLL - {vendor.upper()} STYLE (FABRICATED TEST DATA)"],
            [f"As of {_fmt_date(date.today(), 'long')}"],
            [],
        ]

    rows = []
    gt_rows = []
    property_name = rng.choice(["Riverside Plaza", "Meridian Commons", "Oakmont Center"])
    for i, spec in enumerate(chosen):
        raw = spec["_raw"]
        rr_rent = raw["monthly_rent"]
        rr_end = raw["end"]
        injected = None
        if mess and rng.random() < 0.35:
            kind = rng.choice(["rent_low", "rent_high", "stale_end", "tenant_typo"])
            if kind == "rent_low":
                rr_rent = round(rr_rent * rng.uniform(0.85, 0.97)); injected = {"field": "rent_amount", "kind": kind}
            elif kind == "rent_high":
                rr_rent = round(rr_rent * rng.uniform(1.03, 1.15)); injected = {"field": "rent_amount", "kind": kind}
            elif kind == "stale_end":
                rr_end = (date.fromisoformat(raw["end"]) - timedelta(days=rng.randint(365, 1460))).isoformat()
                injected = {"field": "lease_end_date", "kind": kind}
            else:
                injected = {"field": "tenant", "kind": kind}

        tenant_str = raw["tenant"]
        if injected and injected["kind"] == "tenant_typo":
            tenant_str = _ocr_noise(tenant_str, rng, 0.15) + rng.choice(["", " ", "  "])

        unit = f"{rng.randint(100, 950)}" if vendor != "realpage" else f"B{rng.randint(1,4)}-{rng.randint(100,400)}"
        rent_cell = _money(rr_rent, cents=rng.random() < 0.5, dollar=rng.random() < 0.7)
        market_rent = _money(round(rr_rent * rng.uniform(1.0, 1.1)), dollar=False)
        dep_cell = _money(raw["deposit"], cents=False) if raw["deposit"] else ""

        row_by_header = {
            "Suite": unit, "Unit": unit, "Bldg-Unit": unit, "unit": unit,
            "Tenant Name": tenant_str, "Resident": tenant_str, "Tenant": tenant_str,
            "Resident Name": tenant_str, "tenant": tenant_str,
            "Property": property_name if i == 0 or not mess else "",  # merged-cell style: only first row carries it
            "SF": raw["sqft"], "Sq Ft": raw["sqft"], "Sqft": raw["sqft"], "SqFt": raw["sqft"], "sf": raw["sqft"],
            "Lease Start": _rr_date(raw["start"], rng), "Move In": _rr_date(raw["start"], rng),
            "Start": _rr_date(raw["start"], rng), "Lease Begin": _rr_date(raw["start"], rng),
            "start date": _rr_date(raw["start"], rng),
            "Lease End": _rr_date(rr_end, rng), "Lease To": _rr_date(rr_end, rng), "End": _rr_date(rr_end, rng),
            "Lease Expire": _rr_date(rr_end, rng), "end date": _rr_date(rr_end, rng),
            "Monthly Rent": rent_cell, "Rent Charge": rent_cell, "Rent": rent_cell,
            "Scheduled Rent": rent_cell, "rent": rent_cell, "Market Rent": market_rent,
            "Security Dep": dep_cell, "Deposit": dep_cell, "Deposit Held": dep_cell, "Dep": dep_cell, "deposit": dep_cell,
            "Notes": rng.choice(["", "", "renewed 2024", "MTM holdover"]),
        }
        rows.append([row_by_header.get(h, "") for h in headers])
        gt_rows.append({
            "row_index": len(title_rows) + 1 + i,  # +1 for header
            "lease_id": spec["id"],
            "tenant": raw["tenant"],
            "rent_roll_rent_monthly": rr_rent,
            "lease_rent_monthly": raw["monthly_rent"],
            "injected_disagreement": injected,
        })

    # a couple of phantom units with no lease on file
    if mess:
        for _ in range(rng.randint(1, 3)):
            rows.append([rng.choice(["VACANT", f"Unit {rng.randint(100,950)}"]) if h in ("Suite", "Unit", "Bldg-Unit", "unit")
                         else ("VACANT" if h in ("Tenant Name", "Resident", "Tenant", "Resident Name", "tenant") else "")
                         for h in headers])

    all_rows = title_rows + [headers] + rows
    if mess:
        all_rows.append(["TOTAL"] + [""] * (len(headers) - 1))

    if as_xlsx:
        filename = f"{name}.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        for r in all_rows:
            ws.append(r if r else [None])
        wb.save(os.path.join(out_dir, filename))
    else:
        filename = f"{name}.csv"
        import csv
        with open(os.path.join(out_dir, filename), "w", newline="") as f:
            w = csv.writer(f)
            for r in all_rows:
                w.writerow(r if r else [])

    return filename, {"vendor": vendor, "property": property_name, "rows": gt_rows}


# ----------------------------------------------------------------------
# Garbage
# ----------------------------------------------------------------------

def render_garbage(out_dir, rng, index):
    kind = ["memo_pdf", "invoice_pdf", "corrupt_pdf", "empty_file", "gibberish_image"][index % 5]
    fid = f"garbage_{index:04d}"
    if kind == "memo_pdf":
        fn = f"{fid}.pdf"
        _write_pdf(os.path.join(out_dir, fn), [
            "INTEROFFICE MEMORANDUM", "",
            "TO: All Staff", "FROM: Facilities", f"DATE: {_fmt_date(date.today(), 'long')}",
            "RE: Parking lot resurfacing", "",
            "The north parking lot will be closed next Tuesday and Wednesday for resurfacing. "
            "Please use the visitor lot on Cedar Avenue during this time. Normal access resumes Thursday.",
        ], rng)
    elif kind == "invoice_pdf":
        fn = f"{fid}.pdf"
        _write_pdf(os.path.join(out_dir, fn), [
            "INVOICE #48213", "", "Bill To: Meridian Property Holdings", "Amount Due: $4,182.55",
            "Due Date: Net 30", "", "Description: HVAC quarterly maintenance, 3 rooftop units.",
        ], rng)
    elif kind == "corrupt_pdf":
        fn = f"{fid}.pdf"
        with open(os.path.join(out_dir, fn), "wb") as f:
            f.write(b"%PDF-1.4\n" + bytes(rng.randint(0, 255) for _ in range(400)))
    elif kind == "empty_file":
        fn = f"{fid}.pdf"
        open(os.path.join(out_dir, fn), "wb").close()
    else:
        fn = f"{fid}.png"
        img = Image.new("RGB", (900, 500), "white")
        d = ImageDraw.Draw(img)
        for _ in range(60):
            xy = (rng.randint(0, 880), rng.randint(0, 480))
            d.text(xy, "".join(rng.choice(string.ascii_letters) for _ in range(rng.randint(2, 8))), fill="black")
        img.save(os.path.join(out_dir, fn))
    return fn, kind


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------

def generate_corpus(out_dir, *, n_leases=60, n_garbage=10, n_rent_rolls=8, seed=7):
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)

    manifest = {"seed": seed, "generated": date.today().isoformat(), "leases": [], "rent_rolls": [], "garbage": []}

    lease_specs = []
    for i in range(1, n_leases + 1):
        spec = make_lease_spec(rng, i)
        filename = render_lease(spec, out_dir, rng)
        lease_specs.append(spec)
        manifest["leases"].append({
            "id": spec["id"], "file": filename, "format": spec["format"],
            "scanned": spec["scanned"], "pages": spec["pages"], "style": spec["style"],
            "ground_truth": spec["ground_truth"],
        })

    vendors = list(_VENDOR_HEADERS)
    for i in range(1, n_rent_rolls + 1):
        vendor = vendors[(i - 1) % len(vendors)]
        as_xlsx = i % 3 == 0
        fn, gt = render_rent_roll(lease_specs, out_dir, rng, name=f"rent_roll_{i:03d}", vendor=vendor,
                                  mess=(i % 7 != 0), as_xlsx=as_xlsx)
        manifest["rent_rolls"].append({"file": fn, "vendor": vendor, "ground_truth": gt})

    for i in range(1, n_garbage + 1):
        fn, kind = render_garbage(out_dir, rng, i)
        manifest["garbage"].append({"file": fn, "kind": kind})

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def main():
    ap = argparse.ArgumentParser(description="Generate a synthetic messy lease/rent-roll test corpus.")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "synthetic_corpus"))
    ap.add_argument("--leases", type=int, default=60)
    ap.add_argument("--garbage", type=int, default=10)
    ap.add_argument("--rent-rolls", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    manifest = generate_corpus(args.out, n_leases=args.leases, n_garbage=args.garbage,
                               n_rent_rolls=args.rent_rolls, seed=args.seed)
    print(f"Wrote {len(manifest['leases'])} leases, {len(manifest['rent_rolls'])} rent rolls, "
          f"{len(manifest['garbage'])} garbage files to {args.out}")
    print(f"Ground truth: {os.path.join(args.out, 'manifest.json')}")


if __name__ == "__main__":
    main()
