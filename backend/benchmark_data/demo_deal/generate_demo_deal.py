"""
Generates the Maple Ridge Apartments fake demo deal used for sales demos
of the Deal Mismatch Report: a 120-unit multifamily rent roll (AppFolio
export style), a 12-month T-12 operating statement, and 15 sample lease
PDFs for a subset of those units, with specific, deliberately planted
discrepancies between the leases and the rent roll.

Every fictional name, address, and dollar figure below is invented for
this demo -- no real property, tenant, or owner.

All output is computed bottom-up from the unit inventory defined here
(never hand-typed dollar totals) so this script, expected_findings.json,
and README.md can never silently drift out of sync with each other.
Run: venv/bin/python benchmark_data/demo_deal/generate_demo_deal.py
"""
import json
import os
import random
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LEASE_DIR = os.path.join(OUT_DIR, "leases")
RENT_ROLL_DIR = os.path.join(OUT_DIR, "rent_roll")
T12_DIR = os.path.join(OUT_DIR, "t12")

PROPERTY_NAME = "Maple Ridge Apartments"
PROPERTY_ADDRESS = "4500 Maple Ridge Trail, Dallas, TX 75248"
OWNER_ENTITY = "Maple Ridge Apartments Owner, LLC"
MANAGEMENT_CO = "Cordant Residential Management, LLC"

RENT_ROLL_AS_OF = date(2026, 8, 31)
# When the snapshot was actually pulled/printed -- a couple of days after
# the as-of cutoff, like a real PMS month-end rent roll run once the
# books close. Kept as a fixed constant (not date.today()) so the file
# stays byte-reproducible on a re-run, matching this generator's
# determinism contract (see module docstring / README "Regenerating").
RENT_ROLL_GENERATED = date(2026, 9, 2)
T12_MONTHS = [
    (2025, 9), (2025, 10), (2025, 11), (2025, 12),
    (2026, 1), (2026, 2), (2026, 3), (2026, 4),
    (2026, 5), (2026, 6), (2026, 7), (2026, 8),
]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

RNG_SEED = "maple-ridge-demo-2026"

UNIT_TYPES = {
    "studio": {"sqft": 500, "beds": 0, "baths": 1, "market_rent": 1075},
    "1br":    {"sqft": 700, "beds": 1, "baths": 1, "market_rent": 1285},
    "2br":    {"sqft": 1050, "beds": 2, "baths": 2, "market_rent": 1695},
    "3br":    {"sqft": 1250, "beds": 3, "baths": 2, "market_rent": 1975},
}

# Building letter -> unit type. A=studio, B-E=1BR, F-I=2BR, J=3BR.
BUILDING_TYPE = {
    "A": "studio",
    "B": "1br", "C": "1br", "D": "1br", "E": "1br",
    "F": "2br", "G": "2br", "H": "2br", "I": "2br",
    "J": "3br",
}
BUILDINGS = list(BUILDING_TYPE.keys())
FLOOR_PREMIUM = {1: 0, 2: 15, 3: 30}

VACANT_UNITS = {"A203", "C104", "E204", "G102", "I303", "J204"}

FIRST_NAMES = [
    "Jordan", "Priya", "Trevor", "Simone", "Dana", "Marcus", "Yuki", "Camille",
    "Aiden", "Renata", "Omar", "Whitney", "Felix", "Lena", "Harold", "Nadia",
    "Colton", "Briana", "Ezra", "Maritza", "Duncan", "Alexis", "Reuben", "Sable",
    "Percy", "Ingrid", "Malik", "Corinne", "Gideon", "Yolanda", "Trent", "Paloma",
    "Desmond", "Fiona", "Clay", "Rosalind", "Nikolai", "Tessa", "Emmett", "Junie",
    "Silas", "Marguerite", "Otis", "Devika", "Callum", "Serena", "Wyatt", "Anais",
    "Roman", "Delphine", "August", "Marisela", "Cole", "Vivian", "Elton", "Rosario",
    "Booker", "Thea", "Quentin", "Georgia", "Ansel", "Miriam", "Tobias", "Larkin",
    "Zev", "Odalys", "Brecken", "Solveig", "Amos", "Perpetua", "Django", "Wren",
    "Isadora", "Kingsley", "Marisol", "Barrett", "Noor", "Sterling", "Lucienne",
    "Hollis", "Adelina", "Cormac", "Magnolia", "Ellery", "Thaddeus", "Bijou",
    "Ronan", "Cressida", "Everett", "Saoirse", "Miles", "Petra", "Osiel", "Junia",
    "Baxter", "Dorotea", "Armand", "Susanna", "Finnegan", "Alessia", "Cyrus", "Mabry",
    "Loretta", "Vance", "Juniper", "Chester", "Imogen", "Reggie", "Alba", "Sonny",
]
LAST_NAMES = [
    "Whitfield", "Nandakumar", "Aldous", "Kavanagh", "Okafor", "Levine", "Tanaka-Bell",
    "Duarte", "Foss", "Boone", "Slocum", "Kassab", "Ngata", "Dubrovnik", "Petrosyan",
    "Bostwick", "Harrell", "Onwuka", "Castellano", "Fennimore", "Rourke", "Brandvold",
    "Sarkisian", "Whitcomb", "Delgadillo", "Ashworth", "Prewitt", "Yamashiro", "Calloway",
    "Duquette", "Everhart", "Mbeki", "Ostrander", "Fairweather", "Nakashima", "Quimby",
    "Radcliffe", "Solano", "Threlkeld", "Vasilenko", "Winterbourne", "Zaharia",
    "Bellweather", "Crandall", "Doiron", "Estrella", "Fitzharris", "Gutridge",
    "Hollembeak", "Ionescu", "Jernigan", "Kilbride", "Lachance", "Moncrief",
    "Nkemelu", "Ordway", "Pellikaan", "Quesenberry", "Ravensworth", "Stanhope",
    "Tigerstrom", "Underdahl", "Villaverde", "Wexford", "Yaeger", "Zabrinsky",
]


def _rng_for(unit_id):
    return random.Random(f"{RNG_SEED}:{unit_id}")


def _name_for(unit_id):
    r = _rng_for(unit_id + ":name")
    return f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"


def _all_unit_ids():
    ids = []
    for b in BUILDINGS:
        for floor in (1, 2, 3):
            for u in (1, 2, 3, 4):
                ids.append(f"{b}{floor}{u:02d}")
    return ids


def _floor_of(unit_id):
    return int(unit_id[1])


def _building_of(unit_id):
    return unit_id[0]


# ----------------------------------------------------------------------
# The 16 documented units: 10 carrying a planted issue, 6 clean negative
# controls. These are the only units with a hand-authored lease PDF (15
# of them -- unit_no_lease deliberately has none) and the only ones this
# demo's dollar-impact narrative is built around. Every field below is
# the SOURCE OF TRUTH: the lease PDF, both rent-roll CSVs, and
# expected_findings.json are all generated from these dicts, never typed
# separately, so they cannot disagree with each other by accident --
# only the disagreements defined here on purpose.
# ----------------------------------------------------------------------
DOCUMENTED_UNITS = [
    # -- rent_mismatch: rent roll shows MORE rent than the signed lease --
    {
        "unit_id": "B104", "issue": "rent_mismatch",
        "lease_start": date(2025, 9, 1), "lease_end": date(2026, 8, 31),
        "lease_rent": 1285.00, "rent_roll_rent": 1360.00,
        "rr_lease_to": date(2026, 8, 31),
        "note": "Rent roll was bumped for a renewal offer that was never countersigned; the signed lease still controls at the lower rate.",
    },
    {
        "unit_id": "D203", "issue": "rent_mismatch",
        "lease_start": date(2026, 3, 1), "lease_end": date(2027, 2, 28),
        "lease_rent": 1300.00, "rent_roll_rent": 1420.00,
        "rr_lease_to": date(2027, 2, 28),
        "note": "Rent roll figure appears to be the unit's market/asking rent, mistakenly entered into the actual-rent column.",
    },
    {
        "unit_id": "G204", "issue": "rent_mismatch",
        "lease_start": date(2025, 11, 1), "lease_end": date(2026, 10, 31),
        "lease_rent": 1695.00, "rent_roll_rent": 1955.00,
        "rr_lease_to": date(2026, 10, 31),
        "note": "Largest rent overstatement in the file -- looks like a transposed rent roll row from a different unit type.",
    },
    {
        "unit_id": "J303", "issue": "rent_mismatch",
        "lease_start": date(2026, 6, 1), "lease_end": date(2027, 5, 31),
        "lease_rent": 1975.00, "rent_roll_rent": 2075.00,
        "rr_lease_to": date(2027, 5, 31),
        "note": "Rent roll wasn't corrected after a $100/month concession-expiration date was miscalculated.",
    },
    # -- expired_but_occupied: lease has ended, rent roll still shows a paying tenant --
    {
        "unit_id": "C203", "issue": "expired_but_occupied",
        "lease_start": date(2025, 3, 1), "lease_end": date(2026, 2, 28),
        "lease_rent": 1290.00, "rent_roll_rent": 1290.00,
        "rr_lease_to": None,
        "note": "No renewal or new lease on file since the original term ended February 28, 2026; rent roll still carries the tenant as current.",
    },
    {
        "unit_id": "H104", "issue": "expired_but_occupied",
        "lease_start": date(2025, 6, 1), "lease_end": date(2026, 5, 31),
        "lease_rent": 1720.00, "rent_roll_rent": 1720.00,
        "rr_lease_to": None,
        "note": "No renewal or new lease on file since the original term ended May 31, 2026; rent roll still carries the tenant as current.",
    },
    # -- concession_missing: lease grants a concession the rent roll doesn't reflect --
    {
        "unit_id": "A104", "issue": "concession_missing",
        "lease_start": date(2025, 10, 1), "lease_end": date(2026, 9, 30),
        "lease_rent": 1075.00, "rent_roll_rent": 1075.00,
        "rr_lease_to": date(2026, 9, 30),
        "concession": "One (1) month of Base Rent (the first full calendar month, October 2025) is abated as a move-in incentive.",
        "concession_annual_value": 1075.00,
        "note": "Rent roll shows the full $1,075 scheduled rent with no notation of the one-month move-in concession the lease actually grants.",
    },
    {
        "unit_id": "E301", "issue": "concession_missing",
        "lease_start": date(2026, 4, 1), "lease_end": date(2027, 3, 31),
        "lease_rent": 1290.00, "rent_roll_rent": 1290.00,
        "rr_lease_to": date(2027, 3, 31),
        "concession": "Base Rent is reduced by $100.00 per month for the first six (6) months of the Lease Term (April 2026 through September 2026) as a renewal incentive.",
        "concession_annual_value": 600.00,
        "note": "Rent roll shows the full $1,290 scheduled rent with no notation of the six-month, $100/month renewal concession.",
    },
    {
        "unit_id": "I204", "issue": "concession_missing",
        "lease_start": date(2026, 1, 1), "lease_end": date(2026, 12, 31),
        "lease_rent": 1720.00, "rent_roll_rent": 1720.00,
        "rr_lease_to": date(2026, 12, 31),
        "concession": "Base Rent is reduced by $75.00 per month for the full twelve (12) month Lease Term as a retention incentive.",
        "concession_annual_value": 900.00,
        "note": "Rent roll shows the full $1,720 scheduled rent with no notation of the twelve-month, $75/month retention concession.",
    },
    # -- clean negative controls: rent roll and lease agree exactly --
    {
        "unit_id": "A102", "issue": "clean",
        "lease_start": date(2026, 7, 1), "lease_end": date(2027, 6, 30),
        "lease_rent": 1075.00, "rent_roll_rent": 1075.00, "rr_lease_to": date(2027, 6, 30),
    },
    {
        "unit_id": "B303", "issue": "clean",
        "lease_start": date(2026, 2, 1), "lease_end": date(2027, 1, 31),
        "lease_rent": 1310.00, "rent_roll_rent": 1310.00, "rr_lease_to": date(2027, 1, 31),
    },
    {
        "unit_id": "D104", "issue": "clean",
        "lease_start": date(2025, 12, 1), "lease_end": date(2026, 11, 30),
        "lease_rent": 1285.00, "rent_roll_rent": 1285.00, "rr_lease_to": date(2026, 11, 30),
    },
    {
        "unit_id": "G303", "issue": "clean",
        "lease_start": date(2026, 5, 1), "lease_end": date(2027, 4, 30),
        "lease_rent": 1725.00, "rent_roll_rent": 1725.00, "rr_lease_to": date(2027, 4, 30),
    },
    {
        "unit_id": "H204", "issue": "clean",
        "lease_start": date(2025, 9, 1), "lease_end": date(2026, 8, 31),
        "lease_rent": 1710.00, "rent_roll_rent": 1710.00, "rr_lease_to": date(2026, 8, 31),
    },
    {
        "unit_id": "J102", "issue": "clean",
        "lease_start": date(2026, 4, 1), "lease_end": date(2027, 3, 31),
        "lease_rent": 1990.00, "rent_roll_rent": 1990.00, "rr_lease_to": date(2027, 3, 31),
    },
]

# -- unit_no_lease: on the rent roll, occupied, paying rent -- and
# deliberately has NO lease PDF anywhere in this package.
NO_LEASE_UNIT = {
    "unit_id": "F203",
    "tenant": "Marcus Boone",
    "lease_from": date(2026, 5, 1),
    "lease_to": date(2027, 4, 30),
    "rent_roll_rent": 1710.00,
}

DOCUMENTED_IDS = {u["unit_id"] for u in DOCUMENTED_UNITS} | {NO_LEASE_UNIT["unit_id"]}


def _fmt_money(x):
    return f"${x:,.2f}"


def _fmt_date_mdY(d):
    return d.strftime("%m/%d/%Y")


def _fmt_date_long(d):
    return d.strftime("%B %-d, %Y") if os.name != "nt" else d.strftime("%B %d, %Y").replace(" 0", " ")


# ----------------------------------------------------------------------
# Build the full 120-unit inventory: the 16 documented units above, plus
# 104 deterministically-generated "background" units that fill out the
# rest of the rent roll for realism/scale. Background units are never
# referenced by name in the README and never get a lease PDF in this
# package (see README's "how to run the demo" section for why).
# ----------------------------------------------------------------------
def build_units():
    units = {}

    for doc in DOCUMENTED_UNITS:
        unit_id = doc["unit_id"]
        utype = UNIT_TYPES[BUILDING_TYPE[_building_of(unit_id)]]
        units[unit_id] = {
            "unit_id": unit_id,
            "unit_type": BUILDING_TYPE[_building_of(unit_id)],
            "sqft": utype["sqft"],
            "beds": utype["beds"],
            "baths": utype["baths"],
            "market_rent": utype["market_rent"] + FLOOR_PREMIUM[_floor_of(unit_id)],
            "status": "occupied",
            "tenant": _name_for(unit_id),
            "lease_start": doc["lease_start"],
            "lease_end": doc["lease_end"],
            "lease_rent": doc["lease_rent"],
            "rent_roll_rent": doc["rent_roll_rent"],
            "rr_lease_to": doc["rr_lease_to"],
            "documented": True,
            "issue": doc["issue"],
        }

    nl = NO_LEASE_UNIT
    utype = UNIT_TYPES[BUILDING_TYPE[_building_of(nl["unit_id"])]]
    units[nl["unit_id"]] = {
        "unit_id": nl["unit_id"],
        "unit_type": BUILDING_TYPE[_building_of(nl["unit_id"])],
        "sqft": utype["sqft"],
        "beds": utype["beds"],
        "baths": utype["baths"],
        "market_rent": utype["market_rent"] + FLOOR_PREMIUM[_floor_of(nl["unit_id"])],
        "status": "occupied",
        "tenant": nl["tenant"],
        "lease_start": nl["lease_from"],
        "lease_end": nl["lease_to"],
        "lease_rent": None,
        "rent_roll_rent": nl["rent_roll_rent"],
        "rr_lease_to": nl["lease_to"],
        "documented": True,
        "issue": "unit_no_lease",
    }

    for unit_id in _all_unit_ids():
        if unit_id in units:
            continue
        utype_name = BUILDING_TYPE[_building_of(unit_id)]
        utype = UNIT_TYPES[utype_name]
        market_rent = utype["market_rent"] + FLOOR_PREMIUM[_floor_of(unit_id)]

        if unit_id in VACANT_UNITS:
            units[unit_id] = {
                "unit_id": unit_id, "unit_type": utype_name, "sqft": utype["sqft"],
                "beds": utype["beds"], "baths": utype["baths"], "market_rent": market_rent,
                "status": "vacant", "tenant": None, "lease_start": None, "lease_end": None,
                "lease_rent": None, "rent_roll_rent": None, "rr_lease_to": None,
                "documented": False, "issue": None,
            }
            continue

        r = _rng_for(unit_id)
        loss_to_lease = r.randint(0, 60)
        contract_rent = round((market_rent - loss_to_lease) / 5.0) * 5.0
        term_months = r.choice([12, 12, 12, 13, 15])
        start_month_offset = r.randint(-14, 1)  # months relative to RENT_ROLL_AS_OF
        year = RENT_ROLL_AS_OF.year
        month = RENT_ROLL_AS_OF.month + start_month_offset
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        lease_start = date(year, month, 1)
        end_month = month + term_months
        end_year = year
        while end_month > 12:
            end_month -= 12
            end_year += 1
        # last day of the month before end_month/end_year
        if end_month == 1:
            lease_end = date(end_year - 1, 12, 31)
        else:
            import calendar
            last_day = calendar.monthrange(end_year, end_month - 1)[1]
            lease_end = date(end_year, end_month - 1, last_day)

        units[unit_id] = {
            "unit_id": unit_id, "unit_type": utype_name, "sqft": utype["sqft"],
            "beds": utype["beds"], "baths": utype["baths"], "market_rent": market_rent,
            "status": "occupied", "tenant": _name_for(unit_id),
            "lease_start": lease_start, "lease_end": lease_end,
            "lease_rent": contract_rent, "rent_roll_rent": contract_rent,
            "rr_lease_to": lease_end,
            "documented": False, "issue": None,
        }

    assert len(units) == 120, f"expected 120 units, got {len(units)}"
    return units


# ----------------------------------------------------------------------
# Rent roll: a clean, professional PMS-style export (xlsx + a matching
# print-ready landscape PDF). Deliberately no per-row "Property" column
# -- a single-property PMS export states the building once, in the
# header block, not per row (see README's "set the uploader's base
# property address" instructions, which already assume exactly this).
# ----------------------------------------------------------------------
RENT_ROLL_COLUMNS = [
    "Unit", "Unit Type", "Sq Ft", "Tenant", "Status", "Move-In",
    "Lease Start", "Lease End", "Market Rent", "Lease Rent",
    "Concessions", "Other Charges", "Total Monthly", "Deposit", "Balance",
]

_BED_BATH_LABEL = {"studio": "Studio/1BA", "1br": "1BR/1BA", "2br": "2BR/2BA", "3br": "3BR/2BA"}

# 0-indexed column positions within RENT_ROLL_COLUMNS, used by both the
# xlsx and PDF writers so number/date formatting stays in exactly one
# place.
_RR_DATE_COLS = {5, 6, 7}  # Move-In, Lease Start, Lease End
_RR_MONEY_COLS = {8, 9, 10, 11, 12, 13, 14}  # Market Rent .. Balance
_RR_SQFT_COL = 2


def _rent_roll_raw_row(u):
    """
    One unit's rent-roll row as raw Python values (real date/float
    objects, not pre-formatted strings) in RENT_ROLL_COLUMNS order --
    shared by both the xlsx writer (keeps real typed cells) and the PDF
    writer (formats them for display). "Concessions"/"Other Charges"/
    "Balance" are always 0.00 and "Move-In" always equals the lease
    start date -- this demo deal doesn't model any of those as varying
    per unit, and critically, leaving Concessions at 0.00 rather than
    blank is itself the point of the concession_missing planted issue
    (see README): on its face this looks like a complete, populated
    column, but it's wrong for the 3 units whose lease actually grants
    a concession the rent roll never notes.
    """
    bed_bath = _BED_BATH_LABEL[u["unit_type"]]
    if u["status"] == "vacant":
        return [
            u["unit_id"], bed_bath, u["sqft"], "VACANT", "Vacant",
            None, None, None, u["market_rent"], None, None, None, None, None, None,
        ]
    return [
        u["unit_id"], bed_bath, u["sqft"], u["tenant"], "Occupied",
        u["lease_start"], u["lease_start"], u["rr_lease_to"],
        u["market_rent"], u["rent_roll_rent"],
        0.0, 0.0, round(u["rent_roll_rent"], 2), u["rent_roll_rent"], 0.0,
    ]


def _rent_roll_summary(units, unit_ids):
    occupied = [units[uid] for uid in unit_ids if units[uid]["status"] == "occupied"]
    vacant = [units[uid] for uid in unit_ids if units[uid]["status"] == "vacant"]
    total = len(unit_ids)
    total_market_rent = round(sum(units[uid]["market_rent"] for uid in unit_ids), 2)
    occupied_market_rent = sum(u["market_rent"] for u in occupied)
    total_lease_rent = round(sum(u["rent_roll_rent"] for u in occupied), 2)
    loss_to_lease = round(occupied_market_rent - total_lease_rent, 2)
    return {
        "total_units": total,
        "occupied": len(occupied),
        "vacant": len(vacant),
        "physical_occupancy_pct": round(len(occupied) / total * 100, 1) if total else 0.0,
        "total_market_rent": total_market_rent,
        "total_lease_rent": total_lease_rent,
        "loss_to_lease": loss_to_lease,
    }


_RR_COL_WIDTHS = [9, 11, 8, 20, 10, 11, 12, 12, 12, 12, 12, 13, 13, 11, 11]
_RR_MONEY_FMT = '"$"#,##0.00'
_RR_DATE_FMT = "mm/dd/yyyy"
_RR_THIN = Side(style="thin", color="B7B7B7")
_RR_BORDER = Border(left=_RR_THIN, right=_RR_THIN, top=_RR_THIN, bottom=_RR_THIN)
_RR_HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")


def write_rent_roll_xlsx(path, units, unit_ids, as_of, generated):
    wb = Workbook()
    ws = wb.active
    ws.title = "Rent Roll"

    ws["A1"] = PROPERTY_NAME
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = PROPERTY_ADDRESS
    ws["A2"].font = Font(size=11)
    ws["A3"] = "Rent Roll"
    ws["A3"].font = Font(bold=True, size=13)
    ws["A4"] = "FABRICATED DEMO DATA -- not a real property"
    ws["A4"].font = Font(italic=True, size=9, color="808080")
    ws["A5"] = f"As of {as_of.strftime('%m/%d/%Y')}"
    ws["A6"] = f"Generated {generated.strftime('%m/%d/%Y')}"

    header_row = 7
    for col, name in enumerate(RENT_ROLL_COLUMNS, start=1):
        c = ws.cell(row=header_row, column=col, value=name)
        c.font = Font(bold=True)
        c.fill = _RR_HEADER_FILL
        c.border = _RR_BORDER
        c.alignment = Alignment(horizontal="center", vertical="center")

    row = header_row + 1
    for unit_id in unit_ids:
        values = _rent_roll_raw_row(units[unit_id])
        for col_idx, value in enumerate(values):
            c = ws.cell(row=row, column=col_idx + 1, value=value)
            c.border = _RR_BORDER
            if col_idx in _RR_DATE_COLS:
                c.number_format = _RR_DATE_FMT
                c.alignment = Alignment(horizontal="right")
            elif col_idx in _RR_MONEY_COLS:
                c.number_format = _RR_MONEY_FMT
                c.alignment = Alignment(horizontal="right")
            elif col_idx == _RR_SQFT_COL:
                c.number_format = "#,##0"
                c.alignment = Alignment(horizontal="right")
            else:
                c.alignment = Alignment(horizontal="left")
        row += 1
    last_data_row = row - 1

    row += 1  # blank spacer row before the summary block
    summary = _rent_roll_summary(units, unit_ids)
    ws.cell(row=row, column=1, value="Summary").font = Font(bold=True, size=11)
    row += 1
    summary_lines = [
        ("Total Units", summary["total_units"], None),
        ("Occupied", summary["occupied"], None),
        ("Vacant", summary["vacant"], None),
        ("Physical Occupancy", summary["physical_occupancy_pct"] / 100, "0.0%"),
        ("Total Market Rent (Monthly)", summary["total_market_rent"], _RR_MONEY_FMT),
        ("Total Lease Rent (Monthly)", summary["total_lease_rent"], _RR_MONEY_FMT),
        ("Loss to Lease (Monthly)", summary["loss_to_lease"], _RR_MONEY_FMT),
    ]
    for label, value, number_format in summary_lines:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        value_cell = ws.cell(row=row, column=2, value=value)
        if number_format:
            value_cell.number_format = number_format
        row += 1

    for col_idx, width in enumerate(_RR_COL_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.freeze_panes = f"A{header_row + 1}"
    wb.save(path)


def _fmt_rent_roll_cell(col_idx, value):
    if value is None or value == "":
        return ""
    if col_idx in _RR_DATE_COLS:
        return _fmt_date_mdY(value)
    if col_idx in _RR_MONEY_COLS:
        return _fmt_money(value)
    if col_idx == _RR_SQFT_COL:
        return f"{value:,}"
    return str(value)


def write_rent_roll_pdf(path, units, unit_ids, as_of, generated):
    doc = SimpleDocTemplate(
        path, pagesize=landscape(letter),
        leftMargin=0.4 * inch, rightMargin=0.4 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        title=f"{PROPERTY_NAME} Rent Roll",
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(PROPERTY_NAME, ParagraphStyle("rr_name", fontSize=16, leading=19, fontName="Helvetica-Bold")),
        Paragraph(PROPERTY_ADDRESS, styles["Normal"]),
        Paragraph("Rent Roll", ParagraphStyle("rr_title", fontSize=13, leading=16, fontName="Helvetica-Bold", spaceBefore=4)),
        Paragraph("FABRICATED DEMO DATA -- not a real property", ParagraphStyle("rr_disclaimer", fontSize=8, textColor=colors.grey, fontName="Helvetica-Oblique")),
        Paragraph(
            f"As of {as_of.strftime('%m/%d/%Y')} &nbsp;&nbsp;|&nbsp;&nbsp; Generated {generated.strftime('%m/%d/%Y')}",
            styles["Normal"],
        ),
        Spacer(1, 10),
    ]

    table_data = [RENT_ROLL_COLUMNS]
    for unit_id in unit_ids:
        raw = _rent_roll_raw_row(units[unit_id])
        table_data.append([_fmt_rent_roll_cell(i, v) for i, v in enumerate(raw)])

    page_width = landscape(letter)[0] - 0.8 * inch
    # Relative weights, not pre-normalized fractions -- normalizing by
    # their own sum here (rather than requiring them to already add up
    # to exactly 1.0) avoids a real bug hit during review: an earlier
    # version of these numbers summed to 1.185, not 1.0, so the table's
    # total width came out ~19% wider than the page's content frame.
    # Table defaults to hAlign="CENTER", so that overflow split evenly
    # left/right -- clipping the entire "Unit" column off the left edge
    # and most of "Balance" off the right, invisibly (no error, just a
    # silently broken-looking PDF). Explicit hAlign="LEFT" below is a
    # second, independent guard against the same failure mode.
    col_weights = [0.9, 1.1, 0.75, 2.1, 1.0, 1.05, 1.05, 1.05, 1.1, 1.1, 1.1, 1.15, 1.2, 1.0, 0.95]
    total_weight = sum(col_weights)
    col_widths = [page_width * w / total_weight for w in col_weights]

    table = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FB")]),
        ("ALIGN", (_RR_SQFT_COL, 1), (_RR_SQFT_COL, -1), "RIGHT"),
    ]
    for col_idx in _RR_DATE_COLS | _RR_MONEY_COLS:
        style.append(("ALIGN", (col_idx, 1), (col_idx, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    elements.append(table)
    elements.append(Spacer(1, 12))

    summary = _rent_roll_summary(units, unit_ids)
    elements.append(Paragraph("Summary", ParagraphStyle("rr_summary_title", fontSize=11, fontName="Helvetica-Bold")))
    summary_text = (
        f"Total Units: {summary['total_units']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Occupied: {summary['occupied']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Vacant: {summary['vacant']} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Physical Occupancy: {summary['physical_occupancy_pct']:.1f}%<br/>"
        f"Total Market Rent (Monthly): {_fmt_money(summary['total_market_rent'])} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Total Lease Rent (Monthly): {_fmt_money(summary['total_lease_rent'])} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Loss to Lease (Monthly): {_fmt_money(summary['loss_to_lease'])}"
    )
    elements.append(Paragraph(summary_text, styles["Normal"]))

    def _draw_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 8)
        page_w, _ = landscape(letter)
        canvas_obj.drawString(0.4 * inch, 0.3 * inch, f"{PROPERTY_NAME} -- Rent Roll -- FABRICATED DEMO DATA")
        canvas_obj.drawRightString(page_w - 0.4 * inch, 0.3 * inch, f"Page {doc_obj.page}")
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=_draw_footer, onLaterPages=_draw_footer)


# ----------------------------------------------------------------------
# Lease PDFs
# ----------------------------------------------------------------------
def _wrap(c, text, font, size, max_w):
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


def _render_pdf(path, paragraphs):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    left, right = 1 * inch, width - 1 * inch
    max_w = right - left
    y = height - 1 * inch
    for para in paragraphs:
        if para == "":
            y -= 0.16 * inch
            continue
        bold = para.isupper() and len(para) < 70
        font = "Helvetica-Bold" if bold else "Helvetica"
        for line in _wrap(c, para, font, 11, max_w):
            if y < 1 * inch:
                c.showPage()
                y = height - 1 * inch
            c.setFont(font, 11)
            c.drawString(left, y, line)
            y -= 0.22 * inch
        y -= 0.08 * inch
    c.save()


def _lease_paragraphs(unit_id, u, doc):
    bed_bath = {"studio": "a studio apartment", "1br": "a one-bedroom, one-bath apartment",
                "2br": "a two-bedroom, two-bath apartment", "3br": "a three-bedroom, two-bath apartment"}[u["unit_type"]]
    # Must read as "<PROPERTY_ADDRESS>, Suite <unit_id>" -- this is what
    # app/rent_roll_import.py actually builds for a rent-roll row whose
    # Unit cell is a bare identifier with no designator (see
    # _UNIT_DESIGNATOR_RE / parse_rent_roll_rows: "Suite " is prepended,
    # not "Unit "). The lease PDF's stated address has to come out the
    # same after _normalize_address's lowercase/punctuation-only
    # normalization (it does NOT map "unit" to "suite"), or the rent
    # roll row and this lease would never group into the same unit and
    # none of the matched-pair Deal Mismatch Report checks would fire.
    unit_address = f"{PROPERTY_ADDRESS}, Suite {unit_id}"
    term_months = round((doc["lease_end"].year * 12 + doc["lease_end"].month
                          - (doc["lease_start"].year * 12 + doc["lease_start"].month)) + 1)

    paras = [
        "TEXAS APARTMENT LEASE AGREEMENT",
        "",
        f"This Lease Agreement (\"Lease\") is entered into by and between {OWNER_ENTITY} "
        f"(\"Owner\"), acting through its agent {MANAGEMENT_CO} (\"Management\"), and "
        f"{u['tenant']} (\"Resident\"), for the apartment home described below.",
        "",
        "1. PREMISES. Owner leases to Resident, and Resident leases from Owner, "
        f"Suite {unit_id} at {PROPERTY_NAME}, located at {unit_address} (the \"Premises\"), "
        f"consisting of {bed_bath}, approximately {u['sqft']:,} square feet.",
        "",
        "2. LEASE TERM. The Lease Term begins on "
        f"{_fmt_date_long(doc['lease_start'])} and ends on {_fmt_date_long(doc['lease_end'])} "
        f"({term_months} months). Unless either party gives written notice of intent to vacate "
        "or renew at least sixty (60) days before the end of the Lease Term, this Lease "
        "automatically converts to a month-to-month tenancy at the same Base Rent, subject to "
        "a $75.00 month-to-month premium.",
        "",
        f"3. RENT. Resident shall pay Owner Base Rent of {_fmt_money(doc['lease_rent'])} per "
        "month, due in advance on or before the 1st day of each month, without demand, offset, "
        "or deduction, payable to Management at its designated payment portal or office.",
    ]

    if "concession" in doc:
        paras += [
            "",
            "3A. RENT CONCESSION. As a leasing incentive, and notwithstanding Section 3 above: "
            f"{doc['concession']} All other terms of this Lease, including the Base Rent stated "
            "in Section 3 for all other months of the Lease Term, remain unchanged.",
        ]

    paras += [
        "",
        "4. SECURITY DEPOSIT. Resident has paid Owner a security deposit of "
        f"{_fmt_money(doc['lease_rent'])}, refundable in accordance with Texas Property Code "
        "Chapter 92, less any lawful deductions for unpaid rent, damage beyond normal wear and "
        "tear, or other charges due under this Lease.",
        "",
        "5. LATE CHARGES. If rent is not received by the 3rd day of the month, Resident shall "
        "pay a late charge of 10% of one month's Base Rent, plus $10.00 per day thereafter until "
        "paid in full, as permitted under Texas Property Code Section 92.019.",
        "",
        "6. UTILITIES. Resident is responsible for electricity and internet/cable service in "
        "Resident's own name. Owner provides and bills back water, wastewater, and trash removal "
        "on a pro-rata basis each month as additional rent (\"Utility Reimbursement\").",
        "",
        "7. USE OF PREMISES. The Premises shall be used solely as a private residence for "
        "Resident and Resident's immediate household as disclosed on the Rental Application, and "
        "for no commercial or business purpose.",
        "",
        "8. RENTER'S INSURANCE. Resident shall maintain a renter's liability insurance policy "
        "with minimum liability coverage of $100,000 throughout the Lease Term and shall provide "
        "Management proof of coverage naming Owner as an interested party upon request.",
        "",
        "9. PETS. No animal of any kind may be brought onto the Premises without Management's "
        "prior written consent and execution of a separate Animal Addendum, including payment of "
        "any applicable pet rent and non-refundable pet fee stated in that addendum.",
        "",
        "10. DEFAULT; NOTICE TO VACATE. If Resident fails to pay rent when due, Owner may, after "
        "delivering the written notice to vacate required under Texas Property Code Section "
        "24.005 (not less than three (3) days unless this Lease authorizes a shorter period), "
        "terminate Resident's right of occupancy and pursue eviction and all other remedies "
        "available at law.",
        "",
        "11. RENEWAL. Resident may request to renew this Lease for an additional term by "
        "notifying Management in writing not later than sixty (60) days before the end of the "
        "Lease Term. Renewal is subject to Owner's approval and a new Base Rent to be quoted by "
        "Management at that time; this Lease itself creates no obligation on Owner to offer a "
        "renewal at any particular rate.",
        "",
        "12. COMMUNITY POLICIES. Resident agrees to comply with the Community Rules and "
        "Regulations attached as Exhibit A, as may be reasonably amended by Management from time "
        "to time on notice to Resident.",
        "",
        f"IN WITNESS WHEREOF, the parties have executed this Lease as of {_fmt_date_long(doc['lease_start'])}.",
        "",
        f"OWNER: {OWNER_ENTITY}, by {MANAGEMENT_CO}, as authorized agent",
        f"RESIDENT: {u['tenant']}",
    ]
    return paras


def write_lease_pdfs(units):
    manifest = []
    for doc in DOCUMENTED_UNITS:
        unit_id = doc["unit_id"]
        u = units[unit_id]
        slug = u["tenant"].lower().replace(" ", "_").replace(".", "").replace("-", "_")
        filename = f"{unit_id}_{slug}.pdf"  # unit_id itself stays as-is for filenames; only in-document prose switched to "Suite" wording above
        path = os.path.join(LEASE_DIR, filename)
        _render_pdf(path, _lease_paragraphs(unit_id, u, doc))
        manifest.append({
            "unit_id": unit_id, "file": f"leases/{filename}", "tenant": u["tenant"],
            "issue": doc["issue"], "lease_rent": doc["lease_rent"],
        })
    return manifest


# ----------------------------------------------------------------------
# T-12 operating statement
# ----------------------------------------------------------------------
EXPENSE_LINES_PER_UNIT_ANNUAL = [
    ("Payroll & Benefits", 1150.00),
    ("Repairs & Maintenance", 800.00),
    ("Turnover / Make-Ready", 375.00),
    ("Contract Services (Landscaping, Pest, Trash, Pool)", 400.00),
    ("Utilities (Common Area)", 300.00),
    ("Marketing & Leasing", 200.00),
    ("General & Administrative", 250.00),
    ("Insurance", 525.00),
    ("Property Taxes (Dallas County / TX)", 1900.00),
]
OTHER_INCOME_PER_UNIT_ANNUAL = [
    ("Utility Reimbursement (RUBS)", 420.00),
    ("Application & Administrative Fees", 85.00),
    ("Pet Rent & Fees", 90.00),
    ("Late Fees", 55.00),
    ("Parking & Storage Income", 40.00),
    ("Other / Miscellaneous Income", 30.00),
]
MANAGEMENT_FEE_PCT_OF_EGI = 0.03


def _monthly_noise(r, base, pct=0.06):
    return base * (1 + r.uniform(-pct, pct))


def build_t12(units):
    unit_list = list(units.values())
    occupied = [u for u in unit_list if u["status"] == "occupied"]
    vacant = [u for u in unit_list if u["status"] == "vacant"]

    gpr_annual = sum(u["market_rent"] for u in unit_list) * 12
    vacancy_loss_annual = sum(u["market_rent"] for u in vacant) * 12
    loss_to_lease_annual = sum(u["market_rent"] - u["rent_roll_rent"] for u in occupied) * 12
    scheduled_rent_annual = sum(u["rent_roll_rent"] for u in occupied) * 12  # "what the rent roll implies"

    r = random.Random(f"{RNG_SEED}:t12")

    concessions_annual_total = 11200.00
    bad_debt_pct = 0.06  # ~6% collection shortfall vs. scheduled/rent-roll-implied rent, per the demo brief
    bad_debt_annual_total = round(scheduled_rent_annual * bad_debt_pct, 2)

    months = []
    running_net_billed = 0.0
    running_bad_debt = 0.0
    running_concessions = 0.0
    for idx, (yr, mo) in enumerate(T12_MONTHS):
        is_last = idx == len(T12_MONTHS) - 1
        gpr_m = gpr_annual / 12.0
        vac_m = round(_monthly_noise(r, vacancy_loss_annual / 12.0), 2)
        ltl_m = round(_monthly_noise(r, loss_to_lease_annual / 12.0), 2)
        net_billed_m = round(gpr_m - vac_m - ltl_m, 2)
        running_net_billed += net_billed_m

        if is_last:
            conc_m = round(concessions_annual_total - running_concessions, 2)
            bad_debt_m = round(bad_debt_annual_total - running_bad_debt, 2)
        else:
            conc_m = round(_monthly_noise(r, concessions_annual_total / 12.0, pct=0.5), 2)
            bad_debt_m = round(_monthly_noise(r, bad_debt_annual_total / 12.0), 2)
        running_concessions += conc_m
        running_bad_debt += bad_debt_m

        collected_rent_m = round(net_billed_m - conc_m - bad_debt_m, 2)

        other_income = {}
        for label, per_unit in OTHER_INCOME_PER_UNIT_ANNUAL:
            other_income[label] = round(_monthly_noise(r, per_unit * 120 / 12.0), 2)
        total_other_income = round(sum(other_income.values()), 2)

        total_income = round(collected_rent_m + total_other_income, 2)

        expenses = {}
        for label, per_unit in EXPENSE_LINES_PER_UNIT_ANNUAL:
            expenses[label] = round(_monthly_noise(r, per_unit * 120 / 12.0), 2)
        mgmt_fee = round(total_income * MANAGEMENT_FEE_PCT_OF_EGI, 2)
        expenses["Management Fee"] = mgmt_fee
        total_expenses = round(sum(expenses.values()), 2)

        noi = round(total_income - total_expenses, 2)

        months.append({
            "year": yr, "month": mo, "label": f"{MONTH_NAMES[mo - 1][:3]}-{str(yr)[2:]}",
            "gpr": round(gpr_m, 2), "vacancy_loss": vac_m, "loss_to_lease": ltl_m,
            "net_rent_billed": net_billed_m, "concessions": conc_m, "bad_debt": bad_debt_m,
            "collected_rent": collected_rent_m, "other_income": other_income,
            "total_other_income": total_other_income, "total_income": total_income,
            "expenses": expenses, "total_expenses": total_expenses, "noi": noi,
        })

    totals = {
        "gpr": round(sum(m["gpr"] for m in months), 2),
        "vacancy_loss": round(sum(m["vacancy_loss"] for m in months), 2),
        "loss_to_lease": round(sum(m["loss_to_lease"] for m in months), 2),
        "net_rent_billed": round(sum(m["net_rent_billed"] for m in months), 2),
        "concessions": round(sum(m["concessions"] for m in months), 2),
        "bad_debt": round(sum(m["bad_debt"] for m in months), 2),
        "collected_rent": round(sum(m["collected_rent"] for m in months), 2),
        "total_other_income": round(sum(m["total_other_income"] for m in months), 2),
        "total_income": round(sum(m["total_income"] for m in months), 2),
        "total_expenses": round(sum(m["total_expenses"] for m in months), 2),
        "noi": round(sum(m["noi"] for m in months), 2),
    }
    totals["other_income"] = {
        label: round(sum(m["other_income"][label] for m in months), 2)
        for label, _ in OTHER_INCOME_PER_UNIT_ANNUAL
    }
    totals["expenses"] = {
        label: round(sum(m["expenses"][label] for m in months), 2)
        for label, _ in EXPENSE_LINES_PER_UNIT_ANNUAL
    }
    totals["expenses"]["Management Fee"] = round(sum(m["expenses"]["Management Fee"] for m in months), 2)

    bad_debt_pct_actual = round(totals["bad_debt"] / totals["net_rent_billed"] * 100, 1)

    return {
        "months": months, "totals": totals,
        "gpr_annual": round(gpr_annual, 2),
        "vacancy_loss_annual": round(vacancy_loss_annual, 2),
        "loss_to_lease_annual": round(loss_to_lease_annual, 2),
        "scheduled_rent_annual": round(scheduled_rent_annual, 2),
        "bad_debt_pct_target": bad_debt_pct,
        "bad_debt_pct_actual": bad_debt_pct_actual,
        "concessions_annual_total": concessions_annual_total,
        "bad_debt_annual_total": bad_debt_annual_total,
    }


def write_t12_xlsx(path, t12):
    wb = Workbook()
    ws = wb.active
    ws.title = "T-12"

    bold = Font(bold=True)
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    section_fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
    money_fmt = "#,##0"

    ws["A1"] = PROPERTY_NAME
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Trailing 12-Month Operating Statement (T-12) -- FABRICATED DEMO DATA, not a real property"
    ws["A3"] = f"{MONTH_NAMES[T12_MONTHS[0][1]-1]} {T12_MONTHS[0][0]} through {MONTH_NAMES[T12_MONTHS[-1][1]-1]} {T12_MONTHS[-1][0]}"

    header_row = 5
    ws.cell(row=header_row, column=1, value="Line Item")
    for i, m in enumerate(t12["months"]):
        ws.cell(row=header_row, column=2 + i, value=m["label"])
    ws.cell(row=header_row, column=2 + len(t12["months"]), value="Total")
    for col in range(1, 3 + len(t12["months"])):
        c = ws.cell(row=header_row, column=col)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    row = header_row + 1

    def write_line(label, key_or_values, bold_line=False, section=False, is_total=False):
        nonlocal row
        c0 = ws.cell(row=row, column=1, value=label)
        if bold_line or is_total:
            c0.font = bold
        if section:
            for col in range(1, 3 + len(t12["months"])):
                ws.cell(row=row, column=col).fill = section_fill
            ws.cell(row=row, column=1).font = bold
            row += 1
            return
        for i, m in enumerate(t12["months"]):
            val = m[key_or_values] if isinstance(key_or_values, str) else key_or_values[i]
            c = ws.cell(row=row, column=2 + i, value=val)
            c.number_format = money_fmt
            if bold_line or is_total:
                c.font = bold
        total_val = sum((m[key_or_values] if isinstance(key_or_values, str) else key_or_values[i]) for i, m in enumerate(t12["months"]))
        ct = ws.cell(row=row, column=2 + len(t12["months"]), value=round(total_val, 2))
        ct.number_format = money_fmt
        ct.font = bold
        row += 1

    write_line("INCOME", None, section=True)
    write_line("Gross Potential Rent", "gpr")
    write_line("Vacancy Loss", [-m["vacancy_loss"] for m in t12["months"]])
    write_line("Loss to Lease", [-m["loss_to_lease"] for m in t12["months"]])
    write_line("Net Rental Income Billed (ties to current rent roll)", "net_rent_billed", bold_line=True)
    write_line("Concessions", [-m["concessions"] for m in t12["months"]])
    write_line("Bad Debt / Collection Loss", [-m["bad_debt"] for m in t12["months"]])
    write_line("Total Rent Collected", "collected_rent", bold_line=True)
    write_line("", None, section=True)
    write_line("Other Income", None, section=True)
    for label, _ in OTHER_INCOME_PER_UNIT_ANNUAL:
        write_line(label, [m["other_income"][label] for m in t12["months"]])
    write_line("Total Other Income", "total_other_income", bold_line=True)
    write_line("TOTAL INCOME", "total_income", is_total=True)
    write_line("", None, section=True)
    write_line("OPERATING EXPENSES", None, section=True)
    for label, _ in EXPENSE_LINES_PER_UNIT_ANNUAL:
        write_line(label, [m["expenses"][label] for m in t12["months"]])
    write_line("Management Fee (3% of Total Income)", [m["expenses"]["Management Fee"] for m in t12["months"]])
    write_line("TOTAL OPERATING EXPENSES", "total_expenses", is_total=True)
    write_line("", None, section=True)
    write_line("NET OPERATING INCOME (NOI)", "noi", is_total=True)

    ws.column_dimensions["A"].width = 46
    for i in range(len(t12["months"]) + 1):
        ws.column_dimensions[get_column_letter(2 + i)].width = 12

    ws.freeze_panes = "B6"
    wb.save(path)


# ----------------------------------------------------------------------
# Expected findings (ground truth for verifying the Deal Mismatch Report)
# ----------------------------------------------------------------------
def build_expected_findings(units, t12):
    findings = []
    for doc in DOCUMENTED_UNITS:
        unit_id = doc["unit_id"]
        u = units[unit_id]
        if doc["issue"] == "rent_mismatch":
            diff = round(doc["rent_roll_rent"] - doc["lease_rent"], 2)
            findings.append({
                "discrepancy_type": "rent_mismatch", "unit_id": unit_id,
                "rent_roll_value": _fmt_money(doc["rent_roll_rent"]),
                "lease_value": _fmt_money(doc["lease_rent"]),
                "monthly_dollar_impact": diff, "annual_dollar_impact": round(diff * 12, 2),
                "income_direction": "overstate",
                "detected_by": "Deal Mismatch Report (detect_rent_mismatch) -- live",
            })
        elif doc["issue"] == "expired_but_occupied":
            findings.append({
                "discrepancy_type": "expired_but_occupied", "unit_id": unit_id,
                "rent_roll_value": f"Occupied ({u['tenant']})",
                "lease_value": f"Expired {doc['lease_end'].strftime('%B %d, %Y')}",
                "monthly_dollar_impact": doc["rent_roll_rent"],
                "annual_dollar_impact": round(doc["rent_roll_rent"] * 12, 2),
                "income_direction": "overstate",
                "detected_by": "Deal Mismatch Report (detect_expired_but_occupied) -- live",
            })
        elif doc["issue"] == "concession_missing":
            findings.append({
                "discrepancy_type": "concession_missing", "unit_id": unit_id,
                "rent_roll_value": _fmt_money(doc["rent_roll_rent"]) + " (no concession shown)",
                "lease_value": doc["concession"],
                "monthly_dollar_impact": None,
                "annual_dollar_impact": doc["concession_annual_value"],
                "income_direction": "overstate",
                "detected_by": "NOT YET DETECTED -- detect_concession_missing is a stub pending Phase 2 (multifamily `concessions` field); see README",
            })

    nl = NO_LEASE_UNIT
    findings.append({
        "discrepancy_type": "unit_no_lease", "unit_id": nl["unit_id"],
        "rent_roll_value": nl["tenant"], "lease_value": None,
        "monthly_dollar_impact": nl["rent_roll_rent"],
        "annual_dollar_impact": round(nl["rent_roll_rent"] * 12, 2),
        "income_direction": None,
        "detected_by": "Deal Mismatch Report (detect_unit_no_lease) -- live",
    })

    total_annual_overstatement = round(sum(
        f["annual_dollar_impact"] for f in findings
        if f["income_direction"] == "overstate" and f["annual_dollar_impact"] is not None
    ), 2)

    return {
        "property": PROPERTY_NAME, "property_address": PROPERTY_ADDRESS,
        "rent_roll_as_of": RENT_ROLL_AS_OF.isoformat(),
        "total_units": 120, "total_documented_units": len(DOCUMENTED_IDS),
        "findings": findings,
        "total_planted_annual_income_overstatement": total_annual_overstatement,
        "t12_summary": {
            "net_rental_income_billed_annual": t12["totals"]["net_rent_billed"],
            "bad_debt_annual": t12["totals"]["bad_debt"],
            "bad_debt_pct_of_billed_rent": t12["bad_debt_pct_actual"],
            "total_rent_collected_annual": t12["totals"]["collected_rent"],
            "noi_annual": t12["totals"]["noi"],
        },
    }


def main():
    os.makedirs(LEASE_DIR, exist_ok=True)
    os.makedirs(RENT_ROLL_DIR, exist_ok=True)
    os.makedirs(T12_DIR, exist_ok=True)

    units = build_units()
    all_ids = sorted(units.keys())

    write_rent_roll_xlsx(
        os.path.join(RENT_ROLL_DIR, "maple_ridge_rent_roll_120unit.xlsx"),
        units, all_ids, RENT_ROLL_AS_OF, RENT_ROLL_GENERATED,
    )
    write_rent_roll_pdf(
        os.path.join(RENT_ROLL_DIR, "maple_ridge_rent_roll_120unit.pdf"),
        units, all_ids, RENT_ROLL_AS_OF, RENT_ROLL_GENERATED,
    )
    documented_ids_sorted = sorted(DOCUMENTED_IDS)
    write_rent_roll_xlsx(
        os.path.join(RENT_ROLL_DIR, "maple_ridge_rent_roll_demo_subset_16unit.xlsx"),
        units, documented_ids_sorted, RENT_ROLL_AS_OF, RENT_ROLL_GENERATED,
    )
    write_rent_roll_pdf(
        os.path.join(RENT_ROLL_DIR, "maple_ridge_rent_roll_demo_subset_16unit.pdf"),
        units, documented_ids_sorted, RENT_ROLL_AS_OF, RENT_ROLL_GENERATED,
    )

    lease_manifest = write_lease_pdfs(units)

    t12 = build_t12(units)
    write_t12_xlsx(os.path.join(T12_DIR, "maple_ridge_t12.xlsx"), t12)

    expected = build_expected_findings(units, t12)
    expected["lease_manifest"] = lease_manifest
    with open(os.path.join(OUT_DIR, "expected_findings.json"), "w") as f:
        json.dump(expected, f, indent=2, default=str)

    print(f"Units generated: {len(units)}")
    print(f"Lease PDFs written: {len(lease_manifest)}")
    print(f"GPR (annual): {_fmt_money(t12['gpr_annual'])}")
    print(f"Scheduled/rent-roll-implied rent (annual): {_fmt_money(t12['scheduled_rent_annual'])}")
    print(f"T-12 net rent billed (annual): {_fmt_money(t12['totals']['net_rent_billed'])}")
    print(f"T-12 bad debt (annual): {_fmt_money(t12['totals']['bad_debt'])} "
          f"({t12['bad_debt_pct_actual']}% of billed rent)")
    print(f"T-12 total rent collected (annual): {_fmt_money(t12['totals']['collected_rent'])}")
    print(f"T-12 NOI (annual): {_fmt_money(t12['totals']['noi'])}")
    print(f"Total planted annual income overstatement: {_fmt_money(expected['total_planted_annual_income_overstatement'])}")


if __name__ == "__main__":
    main()
