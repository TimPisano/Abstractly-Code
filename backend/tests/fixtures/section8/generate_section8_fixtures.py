"""
Generates the synthetic Section 8 fixture set in this folder: 10 voucher
leases with HUD tenancy addenda, 5 HAP contracts, 5 rent rolls, 3 PHA HAP
payment registers and 3 HQS/NSPIRE inspection reports for two fictional
properties, with deliberately planted errors. It also writes
ANSWER_KEY.md and answer_key.json, which list every planted error, the
files that show it, and the flag a correct checker should raise.

Every name, address, entity, case number and dollar figure is invented.
Phone numbers use the reserved 555-01xx range and email addresses use the
reserved .test domain. Forms are simplified, paraphrased models of HUD
forms, not official HUD forms, and rule references are paraphrased (not
practitioner-checked).

Everything is computed from the dicts below (never hand-typed totals),
so the documents, the rent rolls, the registers and the answer key cannot
drift apart. Output is byte-reproducible: test_section8_fixtures.py
regenerates into a temp folder and compares.

Run from backend/:  venv/bin/python tests/fixtures/section8/generate_section8_fixtures.py
"""
import csv
import io
import json
import os
import random
import re
import sys
import zipfile
from datetime import date
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFilter, ImageFont
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Byte-reproducible PDFs: no creation timestamps or random document IDs.
rl_config.invariant = 1

HERE = os.path.dirname(os.path.abspath(__file__))

# The date the buyer's review "happens". Every planted error is defined
# relative to this fixed date, so the set never goes stale.
AS_OF = date(2026, 10, 1)
SEP_1 = date(2026, 9, 1)

FOOTER = ("SYNTHETIC TEST DATA - fictional properties and people; simplified model forms, "
          "not official HUD forms. Abstractly test fixture.")

PHA = {
    "name": "Harrow County Housing Authority",
    "short": "HCHA",
    "address": "1 Civic Plaza, Wexmoor, OH 45000",
    "phone": "(330) 555-0110",
    "email": "hcv@harrowcountyha.test",
}
PBCA = "Tri-County Contract Administration Services (fictional PBCA)"
MGMT = {
    "name": "Larkhaven Property Services LLC",
    "phone": "(330) 555-0142",
    "email": "leasing@larkhaven.test",
    "agent": "Morgan Eddlestone",
}
PROPS = {
    "JR": {
        "name": "Juniper Row Apartments",
        "street": "2400 Quillfeather Lane",
        "city": "Wexmoor, OH 45000",
        "owner": "Juniper Row Holdings LLC",
        "vendor_id": "V-2041",
    },
    "BT": {
        "name": "Bellmont Terrace",
        "street": "77 Tinderbox Court",
        "city": "Wexmoor, OH 45000",
        "owner": "Bellmont Terrace Housing LP",
        "vendor_id": "V-2077",
    },
}

UTIL_ITEMS = ["Electric", "Gas - heating", "Gas - cooking", "Water / sewer", "Trash", "Range & refrigerator"]
UTIL_JR = {"Electric": "Tenant", "Gas - heating": "Owner", "Gas - cooking": "Owner",
           "Water / sewer": "Owner", "Trash": "Owner", "Range & refrigerator": "Owner"}
UTIL_BT = {"Electric": "Tenant", "Gas - heating": "Tenant", "Gas - cooking": "Owner",
           "Water / sewer": "Owner", "Trash": "Owner", "Range & refrigerator": "Owner"}


def d(s):
    return date.fromisoformat(s) if s else None


def fmt_date(x):
    return x.strftime("%m/%d/%Y") if x else ""


def long_date(x):
    return x.strftime("%B %-d, %Y")


def money(x):
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


# --------------------------------------------------------------------------
# Units. `contract`, `ttp` (tenant share) and `hap` are the TRUE current
# figures (what the HAP contract / PHA actually support). What each rent
# roll *shows* is the truth plus the per-file overrides in RR_OVERRIDES,
# which is where most planted errors live.
# --------------------------------------------------------------------------
UNITS = [
    # ---------------- Juniper Row: tenant-based HCV + market ----------------
    {"prop": "JR", "unit": "101", "type": "2BR/1BA", "program": "HCV", "tenant": "Talia Brennaway",
     "members": ["Talia Brennaway (Head)", "Jonah Brennaway (Child)"],
     "contract": 1325, "ttp": 420, "hap": 905, "lease": ("2025-11-01", "2026-10-31"), "move_in": "2025-11-01",
     "recert": "2026-11-01", "client": "C-104417", "deposit": 500},
    {"prop": "JR", "unit": "102", "type": "1BR/1BA", "program": "Market", "tenant": "Corwin Ashgrove",
     "contract": 1195, "lease": ("2026-04-01", "2027-03-31"), "move_in": "2024-04-01"},
    {"prop": "JR", "unit": "103", "type": "1BR/1BA", "program": "Market", "tenant": "Imelda Rostvik",
     "contract": 1175, "lease": ("2026-01-01", "2026-12-31"), "move_in": "2023-01-01"},
    {"prop": "JR", "unit": "104", "type": "2BR/1BA", "program": "HCV", "tenant": "Osric Fenmore",
     "members": ["Osric Fenmore (Head)", "Lisette Fenmore (Spouse)", "Pim Fenmore (Child)"],
     "contract": 1250, "ttp": 310, "hap": 940, "lease": ("2026-03-01", "2027-02-28"), "move_in": "2026-03-01",
     "recert": "2027-03-01", "client": "C-104562", "deposit": 500,
     "lease_rent": 1295, "lease_ttp": 355, "lease_util": {"Gas - heating": "Tenant", "Gas - cooking": "Tenant"}},
    {"prop": "JR", "unit": "105", "type": "2BR/1BA", "program": "HCV", "tenant": "Wren Halloway-Quist",
     "contract": 1240, "ttp": 335, "hap": 905, "lease": ("2026-01-01", "2026-12-31"), "move_in": "2024-01-01",
     "recert": "2027-01-01", "client": "C-103988"},
    {"prop": "JR", "unit": "106", "type": "2BR/1BA", "program": "Market", "tenant": "Bastien Orrel",
     "contract": 1395, "lease": ("2026-06-01", "2027-05-31"), "move_in": "2025-06-01"},
    {"prop": "JR", "unit": "107", "type": "1BR/1BA", "program": "Market", "tenant": None, "contract": 1195},
    {"prop": "JR", "unit": "108", "type": "3BR/2BA", "program": "HCV", "tenant": "Delphine Marrowby",
     "members": ["Delphine Marrowby (Head)", "Aurelio Marrowby (Child)", "Bea Marrowby (Child)"],
     "contract": 1385, "ttp": 412, "hap": 973, "lease": ("2026-01-01", "2026-12-31"), "move_in": "2026-01-01",
     "recert": "2027-01-01", "client": "C-104390", "deposit": 600, "side_payment": 75},
    {"prop": "JR", "unit": "112", "type": "1BR/1BA", "program": "HCV", "tenant": "Anselm Treadwick",
     "members": ["Anselm Treadwick (Head)"],
     "contract": 1180, "ttp": 300, "hap": 880, "lease": ("2025-09-01", "2026-08-31"), "move_in": "2025-09-01",
     "move_out": "2026-08-31", "recert": "2026-09-01", "client": "C-103702", "deposit": 400},
    {"prop": "JR", "unit": "201", "type": "1BR/1BA", "program": "Market", "tenant": "Yusra Kettleby",
     "contract": 1210, "lease": ("2026-02-01", "2027-01-31"), "move_in": "2025-02-01"},
    {"prop": "JR", "unit": "202", "type": "2BR/1BA", "program": "Market", "tenant": "Fennimore Gale",
     "contract": 1425, "lease": ("2026-08-01", "2027-07-31"), "move_in": "2026-08-01"},
    {"prop": "JR", "unit": "203", "type": "2BR/1BA", "program": "HCV", "tenant": "Rosalind Achterberg",
     "members": ["Rosalind Achterberg (Head)", "Matthias Achterberg (Child)"],
     "contract": 1295, "ttp": 410, "hap": 885, "lease": ("2026-02-01", "2027-01-31"), "move_in": "2026-02-01",
     "recert": "2027-02-01", "client": "C-104475", "deposit": 500,
     "hap_effective": "2026-02-10", "increase": {"notice": "2026-08-20", "effective": "2026-09-01", "to": 1350}},
    {"prop": "JR", "unit": "204", "type": "2BR/1BA", "program": "Market", "tenant": "Thaddeus Vinmore",
     "contract": 1440, "lease": ("2025-12-01", "2026-11-30"), "move_in": "2023-12-01"},
    {"prop": "JR", "unit": "205", "type": "1BR/1BA", "program": "Market", "tenant": "Liesl Carrowan",
     "contract": 1185, "lease": ("2026-05-01", "2027-04-30"), "move_in": "2026-05-01"},
    {"prop": "JR", "unit": "206", "type": "2BR/1BA", "program": "HCV", "tenant": "Marisol Pennyworth-Oake",
     "members": ["Marisol Pennyworth-Oake (Head)", "Dov Pennyworth-Oake (Child)"],
     "contract": 1295, "ttp": 383, "hap": 912, "lease": ("2026-05-01", "2026-10-31"), "move_in": "2026-05-01",
     "recert": "2027-05-01", "client": "C-104601", "deposit": 500,
     "prior": {"ttp": 245, "hap": 1050, "until": "2026-08-31"}},
    {"prop": "JR", "unit": "207", "type": "1BR/1BA", "program": "Market", "tenant": "Edgar Sollenby",
     "contract": 1200, "lease": ("2026-03-01", "2027-02-28"), "move_in": "2022-03-01"},
    {"prop": "JR", "unit": "210", "type": "3BR/2BA", "program": "HCV", "tenant": "Kestrel Imbody",
     "contract": 1410, "ttp": 410, "hap": 1000, "lease": ("2025-09-01", "2026-08-31"), "move_in": "2023-09-01",
     "recert": "2026-09-01", "client": "C-103341"},
    {"prop": "JR", "unit": "214", "type": "2BR/1BA", "program": "HCV", "tenant": "Nadia Quellwater",
     "members": ["Nadia Quellwater (Head)", "Oren Quellwater (Child)"],
     "contract": 1260, "ttp": 355, "hap": 905, "lease": ("2026-06-01", "2027-05-31"), "move_in": "2026-06-01",
     "recert": "2027-06-01", "client": "C-104688", "deposit": 500},
    # ---------------- Bellmont Terrace: PBRA (1st floor), PBV, market -------
    {"prop": "BT", "unit": "1A", "type": "1BR/1BA", "program": "PBRA", "tenant": "Gideon Larchmont",
     "contract": 1105, "ttp": 275, "hap": 830, "lease": ("2026-03-01", "2027-02-28"), "move_in": "2019-03-01",
     "recert": "2027-03-01"},
    {"prop": "BT", "unit": "1B", "type": "1BR/1BA", "program": "PBRA", "tenant": "Philippa Durnstone",
     "contract": 1105, "ttp": 240, "hap": 865, "lease": ("2026-01-01", "2026-12-31"), "move_in": "2020-01-01",
     "recert": "2027-01-01"},
    {"prop": "BT", "unit": "1C", "type": "2BR/1BA", "program": "PBRA", "tenant": "Ezra Moffatt-Kell",
     "contract": 1265, "ttp": 390, "hap": 875, "lease": ("2025-12-01", "2026-11-30"), "move_in": "2021-12-01",
     "recert": "2026-12-01"},
    {"prop": "BT", "unit": "1D", "type": "2BR/1BA", "program": "PBRA", "tenant": "Saoirse Benwick",
     "contract": 1265, "ttp": 318, "hap": 947, "lease": ("2026-04-01", "2027-03-31"), "move_in": "2018-04-01",
     "recert": "2027-04-01"},
    {"prop": "BT", "unit": "1E", "type": "1BR/1BA", "program": "Market", "tenant": "Hollis Brandreth",
     "contract": 1150, "lease": ("2026-07-01", "2027-06-30"), "move_in": "2025-07-01"},
    {"prop": "BT", "unit": "2A", "type": "2BR/1BA", "program": "PBV", "tenant": "Abigail Thornquist",
     "members": ["Abigail Thornquist (Head)", "Silas Thornquist (Child)"],
     "contract": 1210, "ttp": 290, "hap": 920, "lease": ("2025-08-01", "2026-07-31"), "move_in": "2024-08-01",
     "recert": "2026-08-01", "client": "C-103120", "deposit": 290},
    {"prop": "BT", "unit": "2B", "type": "2BR/1BA", "program": "PBV", "tenant": "Rufus Elverson",
     "contract": 1210, "ttp": 350, "hap": 860, "lease": ("2026-02-01", "2027-01-31"), "move_in": "2024-08-01",
     "recert": "2027-02-01", "client": "C-103133"},
    {"prop": "BT", "unit": "2C", "type": "2BR/1BA", "program": "PBV", "tenant": "Mireille Vantongeren",
     "members": ["Mireille Vantongeren (Head)", "Cosmo Vantongeren (Child)", "Ines Vantongeren (Child)"],
     "contract": 1210, "ttp": 265, "hap": 945, "lease": ("2026-04-01", "2027-03-31"), "move_in": "2026-04-01",
     "recert": "2027-04-01", "client": "C-104512", "deposit": 265},
    {"prop": "BT", "unit": "2D", "type": "2BR/1BA", "program": "Market", "tenant": "Cassius Wrenfield",
     "contract": 1395, "lease": ("2026-05-01", "2027-04-30"), "move_in": "2025-05-01"},
    {"prop": "BT", "unit": "3A", "type": "3BR/2BA", "program": "PBV", "tenant": "Lorna Glasspool",
     "contract": 1240, "ttp": 400, "hap": 840, "lease": ("2026-03-01", "2027-02-28"), "move_in": "2025-03-01",
     "recert": "2027-03-01", "not_on_exhibit_a": True},
    {"prop": "BT", "unit": "3B", "type": "3BR/2BA", "program": "PBV", "tenant": "Tobias Ferncastle",
     "members": ["Tobias Ferncastle (Head)", "Wilhelmina Ferncastle (Spouse)", "Arlo Ferncastle (Child)"],
     "contract": 1240, "ttp": 287, "hap": 953, "lease": ("2026-07-01", "2027-06-30"), "move_in": "2026-07-01",
     "recert": "2027-07-01", "client": "C-104640", "deposit": 287},
    {"prop": "BT", "unit": "3C", "type": "3BR/2BA", "program": "PBV", "tenant": None, "contract": 1240},
    {"prop": "BT", "unit": "3D", "type": "3BR/2BA", "program": "PBV", "tenant": "Henrietta Quarles-Bain",
     "contract": 1240, "ttp": 330, "hap": 910, "lease": ("2026-01-01", "2026-12-31"), "move_in": "2024-08-01",
     "recert": "2027-01-01", "client": "C-103157"},
    {"prop": "BT", "unit": "3E", "type": "3BR/2BA", "program": "Market", "tenant": "Percival Hartsough",
     "contract": 1495, "lease": ("2026-09-01", "2027-08-31"), "move_in": "2026-09-01"},
]
U = {(u["prop"], u["unit"]): u for u in UNITS}


def hcv_contract_no(u):
    """Tenant-based HAP contract number: HCHA-HCV-<move-in year>-<unit>."""
    return f"HCHA-HCV-{u['move_in'][2:4]}-{u['unit'].zfill(4)}"

PBV_CONTRACT = "HCHA-PBV-24-0007"
PBRA_CONTRACT = "DEMO-PBRA-0412"
PBV_EXHIBIT_A = ["2A", "2B", "2C", "3B", "3C", "3D"]
PBRA_UNITS = ["1A", "1B", "1C", "1D"]
PBRA_EXPIRES = date(2026, 8, 31)


def status_on(u, on):
    if not u.get("tenant"):
        return "Vacant"
    if u.get("move_out") and d(u["move_out"]) < on:
        return "Vacant"
    return "Occupied"


def split_on(u, on):
    """(contract, tenant share, HAP) the PMS *should* show on date `on`."""
    if u["program"] == "Market":
        return u["contract"], u["contract"], 0
    prior = u.get("prior")
    if prior and on <= d(prior["until"]):
        return u["contract"], prior["ttp"], prior["hap"]
    return u["contract"], u["ttp"], u["hap"]


# --------------------------------------------------------------------------
# Rent rolls. Overrides are what the seller's systems show instead of the
# truth -- each one is a planted error documented in ERRORS.
# --------------------------------------------------------------------------
RENT_ROLLS = {
    "RR1": {"file": "rent_rolls/juniper_row_rent_roll_2026-10-01_appfolio.csv", "prop": "JR",
            "as_of": AS_OF, "style": "appfolio"},
    "RR2": {"file": "rent_rolls/juniper_row_rent_roll_2026-09-01_yardi.xlsx", "prop": "JR",
            "as_of": SEP_1, "style": "yardi"},
    "RR3": {"file": "rent_rolls/bellmont_terrace_rent_roll_2026-10-01_realpage.csv", "prop": "BT",
            "as_of": AS_OF, "style": "realpage"},
    "RR4": {"file": "rent_rolls/bellmont_terrace_rent_roll_2026-09-01_buildium.csv", "prop": "BT",
            "as_of": SEP_1, "style": "buildium"},
    "RR5": {"file": "rent_rolls/seller_portfolio_rent_roll_2026-10-01.xlsx", "prop": None,
            "as_of": AS_OF, "style": "seller"},
}
RR_OVERRIDES = {
    # S8-04: HAP overstated by $100 in every seller system
    ("RR1", "JR", "105"): {"ttp": 235, "hap": 1005},
    ("RR2", "JR", "105"): {"ttp": 235, "hap": 1005},
    ("RR5", "JR", "105"): {"ttp": 235, "hap": 1005},
    # S8-06: lease rent above HAP contract rent, tenant charged the difference
    ("RR1", "JR", "104"): {"contract": 1295, "ttp": 355},
    ("RR2", "JR", "104"): {"contract": 1295, "ttp": 355},
    ("RR5", "JR", "104"): {"contract": 1295, "ttp": 355},
    # S8-03: interim reexam (eff 09/01) never posted
    ("RR1", "JR", "206"): {"ttp": 245, "hap": 1050},
    ("RR2", "JR", "206"): {"ttp": 245, "hap": 1050},
    ("RR5", "JR", "206"): {"ttp": 245, "hap": 1050},
    # S8-18: unapproved rent increase passed to the tenant
    ("RR1", "JR", "203"): {"contract": 1350, "ttp": 465},
    ("RR2", "JR", "203"): {"contract": 1350, "ttp": 465},
    ("RR5", "JR", "203"): {"contract": 1350, "ttp": 465},
    # S8-05: split doesn't sum
    ("RR1", "JR", "210"): {"ttp": 380},
    # S8-01: tenant share entered as the full rent
    ("RR5", "JR", "108"): {"contract": 412, "ttp": 412, "hap": None},
    # S8-23: moved-out unit reported occupied with HAP
    ("RR5", "JR", "112"): {"status": "Occupied", "contract": 1180, "ttp": 300, "hap": 880},
    # S8-02: tenant share entered as the full rent
    ("RR3", "BT", "3B"): {"contract": 287, "ttp": 287, "hap": 0},
}

# --------------------------------------------------------------------------
# PHA HAP payment registers (HCV + PBV only; PBRA is paid by the PBCA).
# --------------------------------------------------------------------------
REGISTERS = {
    "2026-08": {"pay_date": date(2026, 8, 3), "file": "hap_registers/hcha_hap_register_2026-08"},
    "2026-09": {"pay_date": date(2026, 9, 1), "file": "hap_registers/hcha_hap_register_2026-09"},
    "2026-10": {"pay_date": date(2026, 10, 1), "file": "hap_registers/hcha_hap_register_2026-10"},
}
REG_UNITS = [("JR", x) for x in ["101", "104", "105", "108", "112", "203", "206", "210", "214"]] + \
            [("BT", x) for x in ["2A", "2B", "2C", "3B", "3D"]]
ADJ_CODES = {
    "ABT": "HQS abatement - unit failed inspection, HAP withheld until it passes",
    "RTA": "Retroactive HAP adjustment",
    "TRM": "Assistance terminated",
    "HLD": "Payment held pending PHA action",
    "INT": "Interim reexamination processed (memo only)",
}
REG_SPECIAL = {
    # month, unit -> overrides
    ("2026-08", "JR", "101"): {"adj_code": "RTA", "adj": 45,
                               "memo": "One-time correction: July 2026 HAP short-paid $45 (PHA keying error) - repaid; ongoing HAP unchanged"},
    ("2026-08", "BT", "3D"): {"omit": True},                                    # S8-13
    ("2026-09", "JR", "104"): {"adj_code": "ABT", "adj": -940,
                               "memo": "HQS reinspection failed 08/13/2026 - HAP abated eff 09/01/2026"},  # S8-14
    ("2026-10", "JR", "104"): {"adj_code": "ABT", "adj": -940,
                               "memo": "HAP abatement continues - next reinspection 10/08/2026"},
    ("2026-09", "JR", "108"): {"hap": 873},                                     # S8-12 (no code, no memo)
    ("2026-09", "JR", "206"): {"adj_code": "INT", "adj": 0,
                               "memo": "Interim reexam eff 09/01/2026: TTP $245 -> $383; HAP $1,050 -> $912"},
    ("2026-10", "JR", "210"): {"adj_code": "TRM", "adj": -1000,
                               "memo": "Assistance terminated eff 10/01/2026 - family did not complete annual reexam due 09/01/2026"},  # S8-11
    ("2026-10", "BT", "2A"): {"adj_code": "HLD", "adj": -920,
                              "memo": "HAP held - annual reexam due 08/01/2026 not completed"},  # S8-10
}


def register_rows(month):
    reg = REGISTERS[month]
    pay = reg["pay_date"]
    rows = []
    for prop, unit in REG_UNITS:
        u = U[(prop, unit)]
        sp = REG_SPECIAL.get((month, prop, unit), {})
        if sp.get("omit"):
            continue
        _, _, hap = split_on(u, pay)
        hap = sp.get("hap", hap)
        adj = sp.get("adj", 0)
        p = PROPS[prop]
        rows.append({
            "Payment Date": fmt_date(pay),
            "Vendor ID": p["vendor_id"],
            "Payee": p["owner"],
            "Program": "PBV" if u["program"] == "PBV" else "HCV",
            "HAP Contract": PBV_CONTRACT if u["program"] == "PBV" else hcv_contract_no(u),
            "Client ID": u["client"],
            "Head of Household": u["tenant"],
            "Unit Address": f"{p['street']} #{unit}",
            "Unit": unit,
            "Contract Rent": u["contract"],
            "HAP Amount": hap,
            "Adj Code": sp.get("adj_code", ""),
            "Adj Amount": adj,
            "Net Payment": hap + adj,
            "Memo": sp.get("memo", ""),
        })
    return rows


# --------------------------------------------------------------------------
# Leases: 7 HCV (Juniper Row) + 3 PBV (Bellmont Terrace).
# --------------------------------------------------------------------------
LEASES = [
    {"prop": "JR", "unit": "101", "file": "leases/lease_juniper_row_101_brennaway.pdf"},
    {"prop": "JR", "unit": "104", "file": "leases/lease_juniper_row_104_fenmore.pdf"},
    {"prop": "JR", "unit": "108", "file": "leases/lease_juniper_row_108_marrowby.pdf"},
    {"prop": "JR", "unit": "112", "file": "leases/lease_juniper_row_112_treadwick.pdf", "scanned_signatures": True},
    {"prop": "JR", "unit": "203", "file": "leases/lease_juniper_row_203_achterberg.pdf", "rent_notice": True},
    {"prop": "JR", "unit": "206", "file": "leases/lease_juniper_row_206_pennyworth-oake.pdf", "addendum_first": True},
    {"prop": "JR", "unit": "214", "file": "leases/lease_juniper_row_214_quellwater.pdf"},
    {"prop": "BT", "unit": "2A", "file": "leases/lease_bellmont_terrace_2A_thornquist.pdf"},
    {"prop": "BT", "unit": "2C", "file": "leases/lease_bellmont_terrace_2C_vantongeren.pdf", "scanned_signatures": True},
    {"prop": "BT", "unit": "3B", "file": "leases/lease_bellmont_terrace_3B_ferncastle.pdf", "addendum_unsigned": True},
]
HAP_CONTRACTS = {
    "HC1": {"file": "hap_contracts/hap_contract_hcv_juniper_row_101.pdf", "kind": "HCV", "unit": ("JR", "101")},
    "HC2": {"file": "hap_contracts/hap_contract_hcv_juniper_row_104.pdf", "kind": "HCV", "unit": ("JR", "104")},
    "HC3": {"file": "hap_contracts/hap_contract_hcv_juniper_row_203.pdf", "kind": "HCV", "unit": ("JR", "203")},
    "HC4": {"file": "hap_contracts/hap_contract_pbv_bellmont_terrace.pdf", "kind": "PBV"},
    "HC5": {"file": "hap_contracts/hap_contract_pbra_bellmont_terrace.pdf", "kind": "PBRA"},
}
INSPECTIONS = {
    "IN1": {"file": "inspections/hqs_inspection_juniper_row_104.pdf"},
    "IN2": {"file": "inspections/nspire_v_inspection_bellmont_terrace_pbv.pdf"},
    "IN3": {"file": "inspections/nspire_inspection_bellmont_terrace_pbra.pdf"},
}

# Page numbers are fixed by explicit page breaks; the self-check test
# verifies each evidence snippet really is on the page named here.
HCV_LEASE_PAGES = ["terms", "rules", "signatures", "addendum1", "addendum2", "ack"]


def lease_page_order(spec):
    order = list(HCV_LEASE_PAGES)
    if spec.get("addendum_first"):
        order = ["addendum1", "addendum2", "ack", "terms", "rules", "signatures"]
    if spec.get("rent_notice"):
        order.append("notice")
    return order


def lease_page(spec, key):
    return lease_page_order(spec).index(key) + 1


def lease_spec(prop, unit):
    return next(s for s in LEASES if s["prop"] == prop and s["unit"] == unit)


def lease_file(prop, unit):
    return lease_spec(prop, unit)["file"]


# --------------------------------------------------------------------------
# Planted errors. `evidence` items are machine-checked by the self-check
# test: csv/xlsx cells by unit + column, PDF text by page.
# --------------------------------------------------------------------------
def rr_cell(rr, prop, unit, column, value):
    return {"type": "rent_roll_cell", "file": RENT_ROLLS[rr]["file"], "prop": PROPS[prop]["name"],
            "unit": unit, "column": column, "value": value}


def reg_cell(month, unit, column, value):
    return {"type": "register_cell", "file": REGISTERS[month]["file"] + ".csv", "unit": unit,
            "column": column, "value": value}


def reg_absent(month, unit):
    return {"type": "register_absent", "file": REGISTERS[month]["file"] + ".csv", "unit": unit}


def pdf_text(file, page, contains):
    return {"type": "pdf_text", "file": file, "page": page, "contains": contains}


def pdf_absent(file, page, text):
    return {"type": "pdf_absent", "file": file, "page": page, "text": text}


RR_COLS = {
    # style -> (unit col, contract col, tenant col, hap col, status col, recert col)
    "appfolio": ("Unit", "Rent", "Tenant Portion", "HAP", "Status", "Next Recert"),
    "yardi": ("Unit", "Contract Rent", "Resident Rent", "Subsidy Rent", "Status", "Recert Date"),
    "realpage": ("Bldg/Unit", "Contract Rent", "Tenant Share", "Subsidy Amount", "Status", "Recert Due"),
    "buildium": ("Unit", "Rent", "Tenant Payment", "Housing Assistance Payment", "Status", "Recertification"),
    "seller": ("Unit", "Contract Rent", "Tenant Rent", "HAP", "Status", "Recert Date"),
}


def col(rr, which):
    i = ["unit", "contract", "tenant", "hap", "status", "recert"].index(which)
    return RR_COLS[RENT_ROLLS[rr]["style"]][i]


def pbra_hap_total():
    return sum(U[("BT", x)]["hap"] for x in PBRA_UNITS)


def build_errors():
    hc = HAP_CONTRACTS
    E = []

    def add(**kw):
        kw.setdefault("monthly_impact", None)
        kw.setdefault("impact_to_date", None)
        E.append(kw)

    u108 = U[("JR", "108")]
    add(id="S8-01", category="Tenant share entered as full rent",
        flag="s8_tenant_share_as_contract_rent", severity="high", units=["Juniper Row 108"],
        what=("Seller portfolio rent roll shows Contract Rent $412 (the tenant share) and a blank HAP column for "
              "unit 108. The lease and every PHA register show contract rent $1,385 = tenant $412 + HAP $973."),
        monthly_impact=u108["hap"], impact_note="Gross potential rent understated by the HAP portion.",
        rule="HCV rent to owner = tenant share + HAP (24 CFR 982.451, paraphrased).",
        evidence=[rr_cell("RR5", "JR", "108", col("RR5", "contract"), 412),
                  rr_cell("RR5", "JR", "108", col("RR5", "hap"), None),
                  rr_cell("RR1", "JR", "108", col("RR1", "contract"), 1385),
                  reg_cell("2026-10", "108", "HAP Amount", 973),
                  pdf_text(lease_file("JR", "108"), 1, "Monthly Rent: $1,385.00")])
    u3b = U[("BT", "3B")]
    add(id="S8-02", category="Tenant share entered as full rent",
        flag="s8_tenant_share_as_contract_rent", severity="high", units=["Bellmont Terrace 3B"],
        what=("October RealPage rent roll shows Contract Rent $287 = Tenant Share $287 with Subsidy $0 for PBV unit 3B. "
              "The PBV HAP contract Exhibit A rent is $1,240 and the PHA pays $953 HAP every month; the September "
              "rent roll had it right."),
        monthly_impact=u3b["hap"], impact_note="Rent and HAP income understated by $953/mo.",
        rule="PBV rent to owner is the Exhibit A contract rent; tenant pays only the family share (24 CFR 983.353, paraphrased).",
        evidence=[rr_cell("RR3", "BT", "3B", col("RR3", "contract"), 287),
                  rr_cell("RR3", "BT", "3B", col("RR3", "hap"), 0),
                  rr_cell("RR4", "BT", "3B", col("RR4", "contract"), 1240),
                  reg_cell("2026-10", "3B", "HAP Amount", 953),
                  pdf_text(hc["HC4"]["file"], 1, "3B 3BR/2BA $1,240.00")])
    u206 = U[("JR", "206")]
    add(id="S8-03", category="HAP mismatch (rent roll vs PHA register)",
        flag="s8_hap_mismatch_register", severity="medium", units=["Juniper Row 206"],
        what=("PHA processed an interim reexam effective 09/01/2026 (TTP $245 -> $383, HAP $1,050 -> $912). Both "
              "Juniper Row rent rolls and the seller rent roll still show tenant $245 / HAP $1,050."),
        monthly_impact=u206["prior"]["hap"] - u206["hap"],
        impact_to_date=2 * (u206["prior"]["hap"] - u206["hap"]),
        impact_note="HAP receivable overstated $138/mo (Sep + Oct); the same $138/mo is under-billed to the tenant.",
        rule="Owner must bill the family share the PHA sets; HAP changes take effect on the PHA's notice date.",
        evidence=[rr_cell("RR1", "JR", "206", col("RR1", "hap"), 1050),
                  rr_cell("RR2", "JR", "206", col("RR2", "hap"), 1050),
                  reg_cell("2026-09", "206", "Adj Code", "INT"),
                  reg_cell("2026-10", "206", "HAP Amount", 912)])
    add(id="S8-04", category="HAP mismatch (rent roll vs PHA register)",
        flag="s8_hap_mismatch_register", severity="medium", units=["Juniper Row 105"],
        what=("All three seller rent rolls show HAP $1,005 / tenant $235 for unit 105; the PHA has paid $905 every "
              "month (Aug-Oct) on contract rent $1,240. Rows still sum, so a sum-check alone misses it."),
        monthly_impact=100, impact_to_date=300,
        impact_note="HAP income overstated $100/mo; tenant under-billed $100/mo.",
        rule="HAP amount is set by the PHA; owner records must match the PHA's payment.",
        evidence=[rr_cell("RR1", "JR", "105", col("RR1", "hap"), 1005),
                  rr_cell("RR5", "JR", "105", col("RR5", "hap"), 1005),
                  reg_cell("2026-08", "105", "HAP Amount", 905),
                  reg_cell("2026-10", "105", "HAP Amount", 905)])
    add(id="S8-05", category="Rent split does not sum",
        flag="s8_rent_split_does_not_sum", severity="low", units=["Juniper Row 210"],
        what="October AppFolio rent roll: Rent $1,410 but Tenant Portion $380 + HAP $1,000 = $1,380.",
        monthly_impact=30, impact_note="$30/mo unexplained gap (September Yardi roll shows $410 + $1,000).",
        rule="Contract rent = tenant share + HAP.",
        evidence=[rr_cell("RR1", "JR", "210", col("RR1", "contract"), 1410),
                  rr_cell("RR1", "JR", "210", col("RR1", "tenant"), 380),
                  rr_cell("RR1", "JR", "210", col("RR1", "hap"), 1000),
                  rr_cell("RR2", "JR", "210", col("RR2", "tenant"), 410)])
    u104 = U[("JR", "104")]
    months_104 = 8  # Mar-Oct 2026 rent charges due on or before the as-of date
    add(id="S8-06", category="Lease rent differs from HAP contract rent",
        flag="s8_lease_rent_ne_hap_contract_rent", severity="high", units=["Juniper Row 104"],
        what=("Lease says monthly rent $1,295 (tenant $355 + HAP $940). HAP contract Part A rent to owner is $1,250 "
              "(tenant $310 + HAP $940). Rent rolls bill the tenant $355, i.e. $45/mo above the approved rent."),
        monthly_impact=u104["lease_rent"] - u104["contract"],
        impact_to_date=(u104["lease_rent"] - u104["contract"]) * months_104,
        impact_note="Tenant overcharged $45/mo for Mar-Oct 2026 (8 monthly charges through 10/01/2026) - refundable to the family.",
        rule="Owner may not charge more than the PHA-approved rent to owner; the HAP contract and tenancy addendum prevail over the lease.",
        evidence=[pdf_text(lease_file("JR", "104"), 1, "Monthly Rent: $1,295.00"),
                  pdf_text(hc["HC2"]["file"], 1, "$1,250.00"),
                  rr_cell("RR1", "JR", "104", col("RR1", "contract"), 1295),
                  reg_cell("2026-08", "104", "Contract Rent", 1250)])
    add(id="S8-07", category="Prohibited side payment",
        flag="s8_side_payment", severity="high", units=["Juniper Row 108"],
        what=("Lease section 6 requires a $75/mo 'Supplemental Rent' paid directly to the landlord and 'not reported "
              "to the Housing Authority', on top of the $412 tenant share."),
        monthly_impact=u108["side_payment"], impact_to_date=u108["side_payment"] * 10,
        impact_note="$75/mo for Jan-Oct 2026 (10 monthly charges through 10/01/2026) - must be repaid; PHA may terminate the HAP contract.",
        rule="Owner may not demand or accept any payment from the family beyond the family share (HAP contract Part B; 24 CFR 982.451(b)(4), paraphrased).",
        evidence=[pdf_text(lease_file("JR", "108"), 2, "Supplemental Rent of $75.00 per month"),
                  pdf_text(lease_file("JR", "108"), 2, "not reported to the Housing Authority")])
    add(id="S8-08", category="Expired HAP contract",
        flag="s8_hap_contract_expired", severity="high", units=[f"Bellmont Terrace {x}" for x in PBRA_UNITS],
        what=(f"PBRA HAP contract {PBRA_CONTRACT} term ended 08/31/2026 and the data room has no renewal. Both "
              "Bellmont rent rolls (Sep, Oct) still book HAP on units 1A-1D."),
        monthly_impact=pbra_hap_total(), impact_to_date=2 * pbra_hap_total(),
        impact_note=f"${pbra_hap_total():,}/mo of HAP ({money(pbra_hap_total() * 12)}/yr) has no contract behind it.",
        rule="No HAP is payable after a Section 8 HAP contract expires unless renewed (MAHRAA renewal; owner request due 120 days before expiration, paraphrased).",
        evidence=[pdf_text(hc["HC5"]["file"], 1, "August 31, 2026"),
                  rr_cell("RR3", "BT", "1A", col("RR3", "hap"), U[("BT", "1A")]["hap"]),
                  rr_cell("RR3", "BT", "1D", col("RR3", "hap"), U[("BT", "1D")]["hap"]),
                  rr_cell("RR4", "BT", "1B", col("RR4", "hap"), U[("BT", "1B")]["hap"])])
    u203 = U[("JR", "203")]
    gap = 9
    add(id="S8-09", category="Lease begins before HAP contract effective date",
        flag="s8_lease_precedes_hap_contract", severity="low", units=["Juniper Row 203"],
        what=(f"Lease term begins 02/01/2026; HAP contract {hcv_contract_no(u203)} is effective 02/10/2026 (after the unit "
              "passed HQS). HAP is not payable for 02/01-02/09."),
        monthly_impact=None, impact_to_date=round(u203["hap"] * gap / 28, 2),
        impact_note="One-time: 9/28 of $885 HAP not payable; collectible from no one.",
        rule="PHA pays HAP only from the HAP contract effective date (24 CFR 982.305, paraphrased).",
        evidence=[pdf_text(lease_file("JR", "203"), 1, "February 1, 2026"),
                  pdf_text(hc["HC3"]["file"], 1, "February 10, 2026")])
    u2a = U[("BT", "2A")]
    add(id="S8-10", category="Missed recertification",
        flag="s8_recert_overdue", severity="high", units=["Bellmont Terrace 2A"],
        also_flags=["s8_hap_suspended_but_booked"],
        what=("Annual reexam was due 08/01/2026 (shown as Recert Due on both Bellmont rent rolls). The PHA held "
              "October HAP (code HLD); the October rent roll still books $920 HAP."),
        monthly_impact=u2a["hap"], impact_note="$920/mo HAP at risk until the reexam is completed.",
        rule="PBV families must be reexamined at least annually (24 CFR 983.259, paraphrased).",
        evidence=[rr_cell("RR3", "BT", "2A", col("RR3", "recert"), "08/01/2026"),
                  rr_cell("RR3", "BT", "2A", col("RR3", "hap"), 920),
                  reg_cell("2026-10", "2A", "Adj Code", "HLD"),
                  reg_cell("2026-10", "2A", "Net Payment", 0)])
    add(id="S8-11", category="Missed recertification",
        flag="s8_recert_overdue", severity="high", units=["Juniper Row 210"],
        also_flags=["s8_hap_terminated_but_booked"],
        what=("Annual reexam due 09/01/2026 was not completed; the PHA terminated assistance effective 10/01/2026 "
              "(October register code TRM, net $0). The October rent roll still books $1,000 HAP."),
        monthly_impact=U[("JR", "210")]["hap"], impact_note="$1,000/mo HAP lost; the full $1,410 now falls on the family or the unit turns.",
        rule="HCV assistance may be terminated if the family fails to supply reexam information (24 CFR 982.552, paraphrased).",
        evidence=[rr_cell("RR1", "JR", "210", col("RR1", "recert"), "09/01/2026"),
                  reg_cell("2026-10", "210", "Adj Code", "TRM"),
                  reg_cell("2026-10", "210", "Net Payment", 0)])
    add(id="S8-12", category="PHA payment shortfall",
        flag="s8_hap_shortfall_unexplained", severity="medium", units=["Juniper Row 108"],
        what=("September register pays $873 HAP for unit 108 with no adjustment code or memo; August and October "
              "pay $973 and the rent roll books $973."),
        monthly_impact=None, impact_to_date=100, impact_note="One-time $100 short-pay to chase with the PHA.",
        rule="HAP should equal the PHA-approved amount; any change carries an adjustment notice.",
        evidence=[reg_cell("2026-09", "108", "HAP Amount", 873),
                  reg_cell("2026-09", "108", "Adj Code", ""),
                  reg_cell("2026-08", "108", "HAP Amount", 973)])
    add(id="S8-13", category="PHA payment shortfall",
        flag="s8_hap_payment_missing", severity="medium", units=["Bellmont Terrace 3D"],
        what=("PBV unit 3D (on Exhibit A, occupied, HAP $910 on every rent roll) has no line at all on the August "
              "register, and no retro payment appears in September or October."),
        monthly_impact=None, impact_to_date=U[("BT", "3D")]["hap"],
        impact_note="One-time $910 unpaid HAP.",
        rule="PHA pays HAP monthly for each occupied PBV contract unit (24 CFR 983.351, paraphrased).",
        evidence=[reg_absent("2026-08", "3D"),
                  reg_cell("2026-09", "3D", "HAP Amount", 910),
                  rr_cell("RR4", "BT", "3D", col("RR4", "hap"), 910)])
    add(id="S8-14", category="Abatement after failed inspection",
        flag="s8_hap_abated_but_booked", severity="high", units=["Juniper Row 104"],
        what=("Unit 104 failed the HQS reinspection on 08/13/2026; HAP is abated from 09/01/2026 (September and "
              "October registers: ABT, net $0). The October rent roll still books HAP $940."),
        monthly_impact=u104["hap"], impact_to_date=2 * u104["hap"],
        impact_note="$940/mo HAP not being received; the family may not be charged for it.",
        rule="PHA may not pay HAP for a unit that fails HQS and is not corrected in the cure period (24 CFR 982.404, paraphrased).",
        evidence=[pdf_text(INSPECTIONS["IN1"]["file"], 2, "abated effective 09/01/2026"),
                  reg_cell("2026-09", "104", "Adj Code", "ABT"),
                  reg_cell("2026-10", "104", "Net Payment", 0),
                  rr_cell("RR1", "JR", "104", col("RR1", "hap"), 940)])
    add(id="S8-15", category="Overdue reinspection / repair certification",
        flag="s8_reinspection_overdue", severity="medium", units=["Bellmont Terrace 1B", "Bellmont Terrace (site)"],
        what=("NSPIRE inspection on 08/31/2026 cited moderate deficiencies (unit 1B water-heater leak, sidewalk trip "
              "hazard) with correction and owner certification due 09/30/2026. Status on the 10/01/2026 report: "
              "NOT RECEIVED."),
        impact_note="No direct dollar figure; repeat findings put the (already expired) PBRA renewal at further risk.",
        rule="NSPIRE moderate deficiencies must be corrected within 30 days and certified (24 CFR 5.711, paraphrased).",
        evidence=[pdf_text(INSPECTIONS["IN3"]["file"], 2, "NOT RECEIVED"),
                  pdf_text(INSPECTIONS["IN3"]["file"], 1, "09/30/2026")])
    add(id="S8-16", category="Life-threatening deficiency not cured in 24 hours",
        flag="s8_lt_deficiency_cured_late", severity="medium", units=["Bellmont Terrace 2B"],
        what=("PBV NSPIRE-V inspection 08/20/2026: unit 2B bedroom egress window blocked (Life-Threatening, deadline "
              "08/21/2026). Corrected 08/22/2026 - one day late. Later reinspection passed."),
        impact_note="No dollar figure; PHA could have abated HAP from the missed deadline.",
        rule="Life-threatening deficiencies must be corrected within 24 hours (24 CFR 983.103 / NSPIRE, paraphrased).",
        evidence=[pdf_text(INSPECTIONS["IN2"]["file"], 1, "08/22/2026"),
                  pdf_text(INSPECTIONS["IN2"]["file"], 1, "Life-Threatening")])
    u112 = U[("JR", "112")]
    add(id="S8-17", category="HAP received after move-out",
        flag="s8_hap_paid_after_moveout", severity="high", units=["Juniper Row 112"],
        what=("Tenant moved out 08/31/2026 at lease end (both Juniper Row rent rolls show 112 vacant), but the PHA "
              "paid $880 HAP for unit 112 in September and October."),
        monthly_impact=u112["hap"], impact_to_date=2 * u112["hap"],
        impact_note="$1,760 the owner must repay to the PHA (a liability, not income).",
        rule="Owner is not entitled to HAP after the family moves out and must return it (HAP contract Part B, paraphrased).",
        evidence=[rr_cell("RR1", "JR", "112", col("RR1", "status"), "Vacant"),
                  rr_cell("RR2", "JR", "112", col("RR2", "status"), "Vacant"),
                  reg_cell("2026-09", "112", "Net Payment", 880),
                  reg_cell("2026-10", "112", "Net Payment", 880),
                  pdf_text(lease_file("JR", "112"), 1, "August 31, 2026")])
    inc = u203["increase"]
    add(id="S8-18", category="Rent increase without PHA approval",
        flag="s8_rent_increase_not_approved", severity="high", units=["Juniper Row 203"],
        what=("Notice dated 08/20/2026 raises rent $1,295 -> $1,350 effective 09/01/2026 (12 days' notice, during the "
              "initial lease term, no PHA approval). PHA still pays $885 on $1,295; rent rolls bill the tenant $465 "
              "instead of $410."),
        monthly_impact=inc["to"] - u203["contract"], impact_to_date=2 * (inc["to"] - u203["contract"]),
        impact_note="Tenant overcharged $55/mo (Sep + Oct) - refundable.",
        rule="No rent increase during the initial term; later increases need 60 days' written notice to the PHA and PHA rent-reasonableness approval (tenancy addendum, paraphrased).",
        evidence=[pdf_text(lease_file("JR", "203"), lease_page(lease_spec("JR", "203"), "notice"), "$1,350.00"),
                  pdf_text(lease_file("JR", "203"), lease_page(lease_spec("JR", "203"), "notice"), "August 20, 2026"),
                  rr_cell("RR1", "JR", "203", col("RR1", "tenant"), 465),
                  reg_cell("2026-10", "203", "Contract Rent", 1295)])
    add(id="S8-19", category="Utility responsibility mismatch",
        flag="s8_utility_responsibility_mismatch", severity="medium", units=["Juniper Row 104"],
        what=("HAP contract Part A says the owner pays gas (heating and cooking); the lease makes the tenant pay gas. "
              "The PHA's tenant share assumes no gas utility allowance."),
        impact_note="Tenant bearing a utility cost the PHA's rent calculation assigns to the owner; no fixed $ in the files.",
        rule="Lease utility responsibilities must match the HAP contract (tenancy addendum: lease terms inconsistent with the HAP contract are void, paraphrased).",
        evidence=[pdf_text(lease_file("JR", "104"), 1, "Gas - heating Tenant"),
                  pdf_text(hc["HC2"]["file"], 1, "Gas - heating Owner")])
    add(id="S8-20", category="Unit not on HAP contract",
        flag="s8_unit_not_on_hap_contract", severity="high", units=["Bellmont Terrace 3A"],
        what=("Both Bellmont rent rolls label unit 3A as PBV with $840 HAP, but 3A is not on the PBV HAP contract "
              "Exhibit A (3C is) and the PHA has never paid HAP on it."),
        monthly_impact=U[("BT", "3A")]["hap"], impact_to_date=None,
        impact_note="$840/mo booked HAP with no contract or payment behind it.",
        rule="PHA pays PBV HAP only for units listed on Exhibit A (24 CFR 983.207, paraphrased).",
        evidence=[rr_cell("RR3", "BT", "3A", col("RR3", "hap"), 840),
                  rr_cell("RR4", "BT", "3A", col("RR4", "hap"), 840),
                  reg_absent("2026-10", "3A"),
                  pdf_text(hc["HC4"]["file"], 1, "3C 3BR/2BA $1,240.00"),
                  pdf_absent(hc["HC4"]["file"], 1, "3A 3BR/2BA")])
    add(id="S8-21", category="Tenancy addendum not signed",
        flag="s8_tenancy_addendum_unsigned", severity="medium", units=["Bellmont Terrace 3B"],
        what=("The PBV Tenancy Addendum acknowledgment page for unit 3B is signed by the owner's agent only; the "
              "tenant signature and date lines are blank."),
        impact_note="Documentation gap; no direct dollar figure.",
        rule="The PHA-prescribed tenancy addendum must be part of the lease (24 CFR 983.256, paraphrased).",
        evidence=[pdf_text(lease_file("BT", "3B"), lease_page(lease_spec("BT", "3B"), "ack"), "NOT SIGNED")])
    add(id="S8-22", category="Initial lease term under one year",
        flag="s8_initial_term_under_one_year", severity="low", units=["Juniper Row 206"],
        what="Initial HCV lease term for unit 206 runs 05/01/2026-10/31/2026 (6 months), with no PHA approval of a shorter term in the file.",
        impact_note="Compliance only; renewal falls inside the hold period.",
        rule="Initial HCV lease term must be at least one year unless the PHA approves a shorter term (24 CFR 982.309, paraphrased).",
        evidence=[pdf_text(lease_file("JR", "206"), lease_page(lease_spec("JR", "206"), "terms"), "October 31, 2026")])
    add(id="S8-23", category="Vacant unit reported occupied",
        flag="s8_moved_out_unit_reported_occupied", severity="high", units=["Juniper Row 112"],
        what=("Seller portfolio rent roll shows unit 112 occupied by Anselm Treadwick at $1,180 with $880 HAP. The "
              "tenant moved out 08/31/2026; the AppFolio and Yardi rolls show it vacant."),
        monthly_impact=u112["contract"], impact_note="$1,180/mo of rent that doesn't exist.",
        rule="Rent roll occupancy should match the property's PMS and move-out records.",
        evidence=[rr_cell("RR5", "JR", "112", col("RR5", "status"), "Occupied"),
                  rr_cell("RR5", "JR", "112", col("RR5", "hap"), 880),
                  rr_cell("RR1", "JR", "112", col("RR1", "status"), "Vacant")])
    return E


CLEAN_CONTROLS = [
    {"prop": "JR", "unit": "101", "note": ("Fully documented (lease, addendum, HCV HAP contract, 3 registers, 3 rent rolls). "
                                           "Trap: August register has a coded +$45 RTA one-time correction of a July short-pay; HAP stays $905 - must not flag.")},
    {"prop": "JR", "unit": "214", "note": "Fully documented HCV unit (lease, addendum, registers, rent rolls); everything agrees."},
    {"prop": "BT", "unit": "2C", "note": ("Fully documented PBV unit. Trap: NSPIRE-V cited a moderate deficiency that was corrected "
                                          "inside 30 days and passed reinspection - must not flag. Lease has a scanned-image signature page.")},
]


# --------------------------------------------------------------------------
# PDF helpers
# --------------------------------------------------------------------------
SS = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=15, spaceAfter=6, alignment=1)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=11.5, spaceBefore=6, spaceAfter=3)
BODY = ParagraphStyle("body", parent=SS["BodyText"], fontSize=9.2, leading=11.8, spaceAfter=4)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10)
CENTER = ParagraphStyle("center", parent=BODY, alignment=1)


def P(text, style=BODY):
    return Paragraph(text, style)


def kv_table(rows, widths=(2.1 * inch, 4.9 * inch)):
    t = Table([[P(f"<b>{escape(k)}</b>", SMALL), P(escape(str(v)), SMALL)] for k, v in rows], colWidths=widths)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f1ee"))]))
    return t


def grid(header, rows, widths=None, font=8):
    data = [header] + rows
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("FONTSIZE", (0, 0), (-1, -1), font),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4e8ee")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def footer_cb(title):
    def cb(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.8)
        w, h = doc.pagesize
        canvas.drawString(0.6 * inch, 0.4 * inch, FOOTER)
        canvas.drawRightString(w - 0.6 * inch, h - 0.35 * inch, f"{title} - page {doc.page}")
        canvas.restoreState()
    return cb


def build_pdf(path, pages, title, pagesize=letter):
    """`pages` is a list of flowable lists; each becomes exactly one page."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = SimpleDocTemplate(path, pagesize=pagesize, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.55 * inch, bottomMargin=0.65 * inch, title=title,
                            author="Abstractly synthetic fixtures", subject=FOOTER)
    story = []
    for i, flow in enumerate(pages):
        if i:
            story.append(PageBreak())
        story.extend(flow)
    doc.build(story, onFirstPage=footer_cb(title), onLaterPages=footer_cb(title))
    from pypdf import PdfReader
    n = len(PdfReader(path).pages)
    if n != len(pages):
        raise RuntimeError(f"{path}: expected {len(pages)} pages, got {n} (a page overflowed)")


def scanned_page_image(lines, seed):
    """A grey, slightly rotated, speckled raster page: looks like a fax/scan. No text layer."""
    rnd = random.Random(seed)
    W, H = 1275, 1500  # 150 dpi, 8.5 x 10 in
    img = PILImage.new("L", (W, H), 250)
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=26)
        big = ImageFont.load_default(size=34)
    except TypeError:  # Pillow without FreeType
        font = big = ImageFont.load_default()
    y = 90
    for i, line in enumerate(lines):
        f = big if i == 0 else font
        if line.startswith("~sig~"):
            name = line[5:]
            # scribbled "signature"
            x0 = 160
            pts = [(x0 + k * 14, y + 18 + rnd.randint(-14, 14)) for k in range(18)]
            dr.line(pts, fill=40, width=3)
            dr.text((x0 + 300, y + 8), f"/s/ {name}", fill=60, font=font)
            y += 64
            continue
        dr.text((110, y), line, fill=35, font=f)
        y += 48 if i == 0 else 40
    for _ in range(2600):
        x, yy = rnd.randrange(W), rnd.randrange(H)
        dr.point((x, yy), fill=rnd.randint(90, 200))
    img = img.rotate(0.9, resample=PILImage.BICUBIC, fillcolor=245, expand=False)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    buf.seek(0)
    return Image(buf, width=7.1 * inch, height=7.1 * inch * H / W)


# --------------------------------------------------------------------------
# Leases
# --------------------------------------------------------------------------
def util_table(util):
    rows = [[item, util[item]] for item in UTIL_ITEMS]
    return grid(["Utility / appliance", "Paid or supplied by"], rows, widths=[2.6 * inch, 2.2 * inch], font=8)


def lease_terms_page(spec):
    u = U[(spec["prop"], spec["unit"])]
    p = PROPS[spec["prop"]]
    start, end = d(u["lease"][0]), d(u["lease"][1])
    rent = u.get("lease_rent", u["contract"])
    ttp = u.get("lease_ttp", u.get("prior", {}).get("ttp", u["ttp"]))
    hap = rent - ttp
    prog = "Housing Choice Voucher (tenant-based)" if u["program"] == "HCV" else "Project-Based Voucher"
    util = dict(UTIL_JR if spec["prop"] == "JR" else UTIL_BT)
    util.update(u.get("lease_util", {}))
    flow = [
        P("RESIDENTIAL LEASE AGREEMENT", H1),
        P(f"{escape(p['name'])} - {escape(p['street'])}, Unit {u['unit']}, {escape(p['city'])}", CENTER),
        Spacer(1, 6),
        P("1. Parties and Premises", H2),
        kv_table([
            ("Landlord", p["owner"]),
            ("Managing agent", f"{MGMT['name']}, {MGMT['phone']}, {MGMT['email']}"),
            ("Tenant(s)", u["tenant"]),
            ("Household members", "; ".join(u["members"])),
            ("Premises", f"{p['street']}, Unit {u['unit']}, {p['city']} ({u['type']})"),
            ("Assistance program", f"{prog} - {PHA['name']}"),
        ]),
        P("2. Term", H2),
        P(f"The lease term begins on {long_date(start)} and ends on {long_date(end)}. After the initial term "
          "this lease continues month to month unless either party gives 30 days' written notice."),
        P("3. Rent", H2),
        P(f"<b>Monthly Rent: {money(rent)}</b>, due on the first day of each month. While the Tenant receives "
          f"{prog} assistance, rent is paid as follows: <b>Tenant portion {money(ttp)}</b>; <b>Housing assistance "
          f"payment (HAP) paid by the Housing Authority {money(hap)}</b>. The Tenant portion and HAP change only "
          "when the Housing Authority sends written notice of a new amount."),
        P(f"4. Security Deposit: {money(u['deposit'])}, held in accordance with Ohio law.", H2),
        P("5. Utilities and Appliances", H2),
        util_table(util),
    ]
    return flow


def lease_rules_page(spec):
    u = U[(spec["prop"], spec["unit"])]
    if u.get("side_payment"):
        charges = (f"<b>Supplemental Rent.</b> In addition to the Tenant portion, Tenant agrees to pay Landlord a "
                   f"Supplemental Rent of {money(u['side_payment'])} per month, payable directly to Landlord in cash or "
                   "money order on the first of the month. This amount is a private arrangement between Landlord and "
                   "Tenant and is not reported to the Housing Authority.")
    else:
        charges = ("No charges are payable by Tenant other than the Tenant portion of rent, the late fee in "
                   "section 7, and charges for damage beyond normal wear and tear.")
    return [
        P("6. Other Charges", H2), P(charges),
        P("7. Late Fee", H2),
        P("If the Tenant portion is not received by the 5th day of the month, a late fee of $25.00 is due. No late "
          "fee is charged on any amount owed by the Housing Authority."),
        P("8. Use and Occupancy", H2),
        P("The premises shall be used only as a private residence by the household members listed in section 1. "
          "Additional occupants require the written approval of Landlord and the Housing Authority."),
        P("9. Maintenance and Repairs", H2),
        P("Landlord shall maintain the premises in decent, safe and sanitary condition and in compliance with "
          "applicable housing quality standards. Tenant shall promptly report needed repairs in writing or through "
          "the resident portal."),
        P("10. Entry", H2),
        P("Landlord may enter at reasonable times with 24 hours' notice, or without notice in an emergency."),
        P("11. Pets and Smoking", H2),
        P("No pets other than assistance animals without a signed pet addendum. Smoking is prohibited inside units "
          "and within 25 feet of buildings."),
        P("12. Termination by Landlord", H2),
        P("Landlord may terminate the tenancy only for serious or repeated violation of the lease, violation of law, "
          "or other good cause, and only by court action, as further limited by the HUD Tenancy Addendum."),
        P("13. Tenancy Addendum", H2),
        P("The HUD Tenancy Addendum attached to this lease is part of the lease. If any provision of this lease "
          "conflicts with the Tenancy Addendum, the Tenancy Addendum controls."),
    ]


def signatures_lines(spec):
    u = U[(spec["prop"], spec["unit"])]
    p = PROPS[spec["prop"]]
    signed = d(u["lease"][0])
    return [
        "SIGNATURES",
        f"Lease: {p['name']}, Unit {u['unit']}",
        "Landlord: " + p["owner"],
        f"By its managing agent {MGMT['name']}",
        "~sig~" + MGMT["agent"],
        f"Date: {fmt_date(signed)}",
        "",
        "Tenant:",
        "~sig~" + u["tenant"],
        f"Date: {fmt_date(signed)}",
        "",
        "Each tenant acknowledges receiving a copy of this lease",
        "and the HUD Tenancy Addendum.",
    ]


def lease_signatures_page(spec, idx):
    lines = signatures_lines(spec)
    if spec.get("scanned_signatures"):
        return [scanned_page_image(lines, seed=f"sig-{spec['prop']}-{spec['unit']}")]
    u = U[(spec["prop"], spec["unit"])]
    p = PROPS[spec["prop"]]
    flow = [P("14. Signatures", H2),
            P("By signing, each party agrees to this lease, including the HUD Tenancy Addendum."), Spacer(1, 10)]
    rows = [["Landlord", f"{p['owner']}, by {MGMT['name']}", f"/s/ {MGMT['agent']}", fmt_date(d(u["lease"][0]))],
            ["Tenant", u["tenant"], f"/s/ {u['tenant']}", fmt_date(d(u["lease"][0]))]]
    flow.append(grid(["Party", "Name", "Signature", "Date"], rows,
                     widths=[0.9 * inch, 2.8 * inch, 2.0 * inch, 1.0 * inch], font=8.5))
    return flow


ADDENDUM_HCV = [
    ("1. Section 8 Voucher Program", "The owner is leasing the contract unit to the tenant for occupancy by the "
     "tenant's family with assistance for a tenancy under the Section 8 housing choice voucher program. The owner "
     "has entered into a Housing Assistance Payments Contract (HAP contract) with the PHA, under which the PHA makes "
     "housing assistance payments to the owner to assist the tenant in leasing the unit."),
    ("2. Lease", "The owner must give the PHA a copy of the lease, including any changes agreed to by owner and "
     "tenant. The owner certifies that the terms of the lease are in accordance with all provisions of the HAP "
     "contract and that the lease includes this tenancy addendum."),
    ("3. Use of Contract Unit", "The family must reside in the contract unit, which must be the family's only "
     "residence. Composition of the household must be approved by the PHA."),
    ("4. Rent to Owner", "The initial rent to owner may not exceed the amount approved by the PHA. During the initial "
     "lease term the owner may not raise the rent to owner. Any later change must be in accordance with the lease, "
     "and the owner must give the tenant and the PHA at least sixty (60) days' written notice; the PHA must approve "
     "the new rent as reasonable."),
    ("5. Family Payment to Owner", "The family is responsible for paying the owner any portion of the rent to owner "
     "not covered by the PHA housing assistance payment. The family is not responsible for the portion covered by "
     "the PHA payment. The owner may not charge or accept any payment from the family in excess of the family's "
     "share, and must immediately return any excess."),
    ("6. Other Fees and Charges", "Rent to owner includes all housing services, maintenance, utilities and "
     "appliances to be supplied by the owner under the HAP contract. The owner may not charge for items customarily "
     "included in rent in the locality."),
    ("7. Maintenance, Utilities and Other Services", "The owner must maintain the unit in accordance with HQS and "
     "provide all utilities needed to comply with HQS that the HAP contract assigns to the owner."),
    ("8. Termination of Tenancy by Owner", "The owner may only terminate the tenancy in accordance with the lease "
     "and HUD requirements, for serious or repeated violation of the lease, violation of law, or other good cause."),
    ("9. Lease: Relation to HAP Contract", "If the HAP contract terminates for any reason, the lease terminates "
     "automatically."),
    ("10. Family Move Out", "The tenant must notify the PHA and the owner before the family moves out of the unit."),
    ("11. Security Deposit", "The owner may collect a security deposit from the tenant in an amount not more than "
     "permitted under State law and the PHA's policies."),
    ("12. Prohibition of Discrimination", "The owner may not discriminate against any person on the grounds of race, "
     "color, religion, sex, national origin, age, familial status or disability in connection with the lease."),
    ("13. Conflict With Other Provisions of Lease", "In case of any conflict between the provisions of this tenancy "
     "addendum and any other provisions of the lease, the language of the tenancy addendum shall control."),
    ("14. Changes in Lease or Rent", "The tenant and the owner may not make any change in the tenancy addendum. The "
     "owner must notify the PHA of any change in the amount of the rent to owner at least sixty days before the "
     "change goes into effect."),
    ("15. Notices", "Any notice under the lease by the tenant to the owner or by the owner to the tenant must be in "
     "writing."),
]
ADDENDUM_PBV_TITLE = "TENANCY ADDENDUM - Section 8 Project-Based Voucher Program"
ADDENDUM_HCV_TITLE = "TENANCY ADDENDUM - Section 8 Tenant-Based Assistance, Housing Choice Voucher Program"


def addendum_pages(spec):
    u = U[(spec["prop"], spec["unit"])]
    pbv = u["program"] == "PBV"
    title = ADDENDUM_PBV_TITLE if pbv else ADDENDUM_HCV_TITLE
    form = "HUD-52530-c" if pbv else "HUD-52641-A"
    items = list(ADDENDUM_HCV)
    if pbv:
        items[0] = ("1. Section 8 Project-Based Voucher Program", "The owner is leasing the contract unit to the "
                    "tenant for occupancy by the tenant's family with assistance for a tenancy under the Section 8 "
                    "project-based voucher program. The owner has entered into a HAP contract with the PHA for the "
                    "project; the PHA pays housing assistance payments to the owner for the contract unit.")
        items[9] = ("10. Family Move Out", "A family may move with continued tenant-based assistance after the first "
                    "year of occupancy, as provided in the PBV program rules.")
    head = [P(title, H1),
            P(f"(Simplified model of form {form} - paraphrased for test purposes; not an official HUD form)", CENTER),
            P(f"Contract unit: {escape(PROPS[spec['prop']]['street'])}, Unit {u['unit']} - Tenant: "
              f"{escape(u['tenant'])} - PHA: {PHA['name']}", CENTER), Spacer(1, 4)]
    p1 = head + [P(f"<b>{t}</b>. {escape(b)}") for t, b in items[:8]]
    p2 = [P(f"{title} (continued)", H2)] + [P(f"<b>{t}</b>. {escape(b)}") for t, b in items[8:]]
    return p1, p2


def ack_page(spec):
    u = U[(spec["prop"], spec["unit"])]
    p = PROPS[spec["prop"]]
    signed = fmt_date(d(u["lease"][0]))
    tenant_sig = "" if spec.get("addendum_unsigned") else f"/s/ {u['tenant']}"
    tenant_date = "" if spec.get("addendum_unsigned") else signed
    flow = [P("ACKNOWLEDGMENT OF HUD TENANCY ADDENDUM", H1),
            P(f"{escape(p['name'])}, Unit {u['unit']}", CENTER), Spacer(1, 6),
            P("The undersigned acknowledge that the HUD Tenancy Addendum is attached to and made part of the lease "
              "for the contract unit, and that the Tenancy Addendum controls over any conflicting lease term."),
            Spacer(1, 8),
            grid(["Party", "Name", "Signature", "Date"],
                 [["Owner / agent", MGMT["agent"], f"/s/ {MGMT['agent']}", signed],
                  ["Tenant (head of household)", u["tenant"], tenant_sig, tenant_date]],
                 widths=[1.6 * inch, 2.2 * inch, 2.0 * inch, 1.0 * inch], font=8.5)]
    if spec.get("addendum_unsigned"):
        flow += [Spacer(1, 10), P("<i>Compliance review stamp: TENANT SIGNATURE - NOT SIGNED</i>", SMALL)]
    return flow


def notice_page(spec):
    u = U[(spec["prop"], spec["unit"])]
    p = PROPS[spec["prop"]]
    inc = u["increase"]
    return [P("NOTICE OF RENT INCREASE", H1),
            P(f"Date: {long_date(d(inc['notice']))}"),
            P(f"To: {escape(u['tenant'])}, {escape(p['street'])}, Unit {u['unit']}, {escape(p['city'])}"),
            P(f"From: {MGMT['name']}, on behalf of {escape(p['owner'])}"), Spacer(1, 6),
            P(f"Effective {long_date(d(inc['effective']))}, your monthly rent will increase from "
              f"<b>{money(u['contract'])}</b> to <b>{money(inc['to'])}</b>. Your Housing Authority payment is not "
              f"affected; the increase of {money(inc['to'] - u['contract'])} will be added to your Tenant portion "
              "beginning with the September rent."),
            P("All other terms of your lease remain in effect. Please contact the leasing office with any questions."),
            Spacer(1, 10),
            P(f"/s/ {MGMT['agent']}, Community Manager"),
            P("Delivered by: posting on door and resident portal. cc: tenant file", SMALL)]


def make_lease(spec, out):
    builders = {
        "terms": lambda: lease_terms_page(spec),
        "rules": lambda: lease_rules_page(spec),
        "signatures": lambda: lease_signatures_page(spec, None),
        "addendum1": lambda: addendum_pages(spec)[0],
        "addendum2": lambda: addendum_pages(spec)[1],
        "ack": lambda: ack_page(spec),
        "notice": lambda: notice_page(spec),
    }
    pages = [builders[k]() for k in lease_page_order(spec)]
    u = U[(spec["prop"], spec["unit"])]
    build_pdf(os.path.join(out, spec["file"]), pages, f"Lease - {PROPS[spec['prop']]['name']} Unit {u['unit']}")


# --------------------------------------------------------------------------
# HAP contracts
# --------------------------------------------------------------------------
HAP_PART_B = [
    ("Term of HAP contract", "The HAP contract terminates automatically if the lease is terminated by the owner or "
     "the tenant, if the PHA terminates program assistance for the family, or 180 calendar days after the last "
     "housing assistance payment to the owner."),
    ("Maintenance and HQS", "The owner must maintain the contract unit in accordance with HQS. The PHA shall not make "
     "any housing assistance payments if the contract unit does not meet HQS, unless the owner corrects the defect "
     "within the period specified by the PHA and the PHA verifies the correction."),
    ("Housing assistance payments", "Each month the PHA pays the owner a housing assistance payment on behalf of the "
     "family. Payments begin on the effective date of this contract. The owner is not entitled to housing "
     "assistance payments for any month after the month in which the family moves out, and must promptly return "
     "any payment received for a period after move-out."),
    ("Owner may not demand excess payment", "The owner may not demand or accept any rent payment from the tenant in "
     "excess of the family's share as determined by the PHA, or any other payment for rent of the unit, and must "
     "immediately return any excess rent payment to the tenant."),
    ("Rent to owner", "Rent to owner may not exceed the amount approved by the PHA. The owner must notify the PHA at "
     "least 60 days before any change in rent to owner."),
    ("Prohibition of discrimination; access to records", "The owner must comply with all equal opportunity "
     "requirements and must give the PHA and HUD access to the premises and records."),
]


def hcv_contract_pages(key):
    spec = HAP_CONTRACTS[key]
    u = U[spec["unit"]]
    p = PROPS[spec["unit"][0]]
    start, end = d(u["lease"][0]), d(u["lease"][1])
    eff = d(u.get("hap_effective") or u["lease"][0])
    util = dict(UTIL_JR)
    p1 = [P("HOUSING ASSISTANCE PAYMENTS CONTRACT (HAP CONTRACT)", H1),
          P("Section 8 Tenant-Based Assistance - Housing Choice Voucher Program", CENTER),
          P("(Simplified model of form HUD-52641 - paraphrased for test purposes; not an official HUD form)", CENTER),
          P("Part A of the HAP Contract: Contract Information", H2),
          kv_table([
              ("HAP contract number", hcv_contract_no(u)),
              ("PHA", f"{PHA['name']}, {PHA['address']}"),
              ("Owner", f"{p['owner']} (vendor {p['vendor_id']})"),
              ("Tenant", f"{u['tenant']} (client {u['client']})"),
              ("Contract unit", f"{p['street']}, Unit {u['unit']}, {p['city']}"),
              ("Household members", "; ".join(u["members"])),
              ("Initial lease term", f"Begins {long_date(start)}; ends {long_date(end)}"),
              ("Effective date of HAP contract", long_date(eff)),
              ("Initial rent to owner", f"{money(u['contract'])} per month"),
              ("Initial housing assistance payment", f"{money(u['hap'])} per month, beginning on the effective date"),
              ("Family share (initial)", f"{money(u['contract'] - u['hap'])} per month"),
          ]),
          P("Utilities and appliances (paid or supplied by)", H2),
          grid(["Item", "Paid / supplied by"], [[k, util[k]] for k in UTIL_ITEMS],
               widths=[2.6 * inch, 2.8 * inch], font=8)]
    p2 = [P("Part B of the HAP Contract: Body of Contract (paraphrased)", H2)] + \
         [P(f"<b>{i + 1}. {t}</b>. {escape(b)}") for i, (t, b) in enumerate(HAP_PART_B)] + \
         [P("Part C of the HAP Contract: Tenancy Addendum", H2),
          P("The tenancy addendum (Part C) is incorporated in this contract and must be attached to the lease."),
          Spacer(1, 8),
          grid(["Party", "Signed by", "Date"],
               [["PHA", f"/s/ Ilse Varnham, HCV Program Manager, {PHA['name']}", fmt_date(eff)],
                ["Owner", f"/s/ {MGMT['agent']}, agent for {p['owner']}", fmt_date(eff)]],
               widths=[0.9 * inch, 4.6 * inch, 1.2 * inch], font=8.5)]
    return [p1, p2]


def pbv_contract_pages():
    p = PROPS["BT"]
    rows = []
    for unit in PBV_EXHIBIT_A:
        u = U[("BT", unit)]
        rows.append([unit, u["type"], money(u["contract"]), "Tenant: electric, gas heat; Owner: all other"])
    p1 = [P("HOUSING ASSISTANCE PAYMENTS CONTRACT", H1),
          P("Section 8 Project-Based Voucher Program - Existing Housing", CENTER),
          P("(Simplified model of form HUD-52530-A - paraphrased for test purposes; not an official HUD form)", CENTER),
          kv_table([
              ("HAP contract number", PBV_CONTRACT),
              ("PHA", f"{PHA['name']}, {PHA['address']}"),
              ("Owner", f"{p['owner']} (vendor {p['vendor_id']})"),
              ("Project", f"{p['name']}, {p['street']}, {p['city']}"),
              ("Effective date", "July 1, 2024"),
              ("Term", "20 years: July 1, 2024 through June 30, 2044"),
              ("Number of contract units", str(len(PBV_EXHIBIT_A))),
          ]),
          P("EXHIBIT A - Contract Units and Rent to Owner (as amended effective July 1, 2026)", H2),
          grid(["Unit", "Type", "Rent to owner", "Utilities"], rows,
               widths=[0.7 * inch, 1.0 * inch, 1.2 * inch, 3.8 * inch], font=8.5),
          P("Units may be added or substituted only by written amendment of this Exhibit A signed by the PHA.", SMALL)]
    p2 = [P("Body of Contract (paraphrased)", H2),
          P("<b>1. Payments.</b> The PHA pays housing assistance payments to the owner only for contract units "
            "listed on Exhibit A that are leased to and occupied by eligible families. Payment is due on the first "
            "day of the month."),
          P("<b>2. Reexaminations.</b> The PHA reexamines family income and composition at least annually. If a "
            "family fails to complete a reexamination, the PHA may hold or terminate assistance."),
          P("<b>3. Housing quality.</b> Contract units must comply with the PHA's inspection standard (NSPIRE-V). "
            "Life-threatening deficiencies must be corrected within 24 hours and other deficiencies within 30 days, "
            "or the PHA may abate payments."),
          P("<b>4. Vacancies.</b> No vacancy payments are made under this contract."),
          P("<b>5. Rent adjustments.</b> Rent to owner is redetermined at the owner's request or annually on the "
            "contract anniversary, subject to rent reasonableness."),
          Spacer(1, 8),
          grid(["Party", "Signed by", "Date"],
               [["PHA", f"/s/ Ilse Varnham, HCV Program Manager, {PHA['name']}", "06/20/2024"],
                ["Owner", f"/s/ Garrick Haldane, Managing Member, GP of {p['owner']}", "06/18/2024"]],
               widths=[0.9 * inch, 4.6 * inch, 1.2 * inch], font=8.5)]
    return [p1, p2]


def pbra_contract_pages():
    p = PROPS["BT"]
    rows = [[x, U[("BT", x)]["type"], money(U[("BT", x)]["contract"])] for x in PBRA_UNITS]
    p1 = [P("SECTION 8 HOUSING ASSISTANCE PAYMENTS CONTRACT - RENEWAL", H1),
          P("Project-Based Rental Assistance (Multifamily) - Mark-Up-To-Market renewal", CENTER),
          P("(Simplified model of a HUD multifamily HAP renewal contract - paraphrased; not an official HUD form)", CENTER),
          kv_table([
              ("Contract number", PBRA_CONTRACT),
              ("Contract administrator", PBCA),
              ("Owner", p["owner"]),
              ("Project", f"{p['name']} (Section 8 units: first floor), {p['street']}, {p['city']}"),
              ("Renewal term", "Five years: September 1, 2021 through August 31, 2026"),
              ("Contract expiration date", long_date(PBRA_EXPIRES)),
              ("Number of contract units", str(len(PBRA_UNITS))),
              ("Renewal request deadline", "Owner must submit a renewal request at least 120 days before expiration (by May 3, 2026)"),
          ]),
          P("EXHIBIT A - Contract Rents (after 09/01/2025 annual adjustment)", H2),
          grid(["Unit", "Type", "Contract rent"], rows, widths=[0.8 * inch, 1.2 * inch, 1.4 * inch], font=8.5),
          P("Housing assistance payments are paid monthly through TRACS vouchers submitted to the contract "
            "administrator. No payment is due for any month after the contract expiration date unless the contract "
            "is renewed.", SMALL)]
    p2 = [P("Owner Obligations (paraphrased)", H2),
          P("<b>1.</b> Recertify each assisted family's income annually and process interim changes (HUD Handbook 4350.3)."),
          P("<b>2.</b> Maintain the project in decent, safe and sanitary condition and correct NSPIRE deficiencies within "
            "the required time frames; certify corrections to the contract administrator."),
          P("<b>3.</b> Give tenants a one-year notice before the contract expires if the owner does not intend to renew."),
          Spacer(1, 8),
          grid(["Party", "Signed by", "Date"],
               [["Contract administrator", "/s/ Delia Vossberg, Contract Specialist", "08/16/2021"],
                ["Owner", f"/s/ Garrick Haldane, Managing Member, GP of {p['owner']}", "08/12/2021"]],
               widths=[1.5 * inch, 4.1 * inch, 1.1 * inch], font=8.5),
          Spacer(1, 10),
          P("<i>Data room note: no renewal contract, extension or opt-out notice was provided with this file.</i>", SMALL)]
    return [p1, p2]


# --------------------------------------------------------------------------
# Inspections
# --------------------------------------------------------------------------
def inspection_hqs_pages():
    u = U[("JR", "104")]
    p = PROPS["JR"]
    rows = [["1", "Hallway", "Smoke detector inoperable", "24-Hour", "07/15/2026", "Corrected 07/15/2026 (owner cert + photo)"],
            ["2", "Bedroom 1", "Window pane cracked, does not lock", "30-Day", "08/13/2026", "Open"],
            ["3", "Kitchen", "Outlet cover missing - exposed wiring", "30-Day", "08/13/2026", "Open"]]
    p1 = [P("HOUSING QUALITY STANDARDS (HQS) INSPECTION REPORT", H1),
          P(f"{PHA['name']} - Housing Choice Voucher Program", CENTER),
          P("(Simplified model of form HUD-52580 - not an official HUD form)", CENTER),
          kv_table([("Unit", f"{p['street']}, Unit {u['unit']}, {p['city']}"),
                    ("Tenant", f"{u['tenant']} (client {u['client']})"),
                    ("Owner", p["owner"]),
                    ("Inspection type", "Annual"),
                    ("Inspection date", "07/14/2026"),
                    ("Inspector", "R. Calloway-Pike, HQS Inspector"),
                    ("Result", "FAIL")]),
          P("Deficiencies", H2),
          grid(["#", "Area", "Deficiency", "Category", "Cure by", "Status"], rows,
               widths=[0.3 * inch, 0.9 * inch, 2.2 * inch, 0.8 * inch, 0.9 * inch, 2.0 * inch]),
          P("24-hour items must be corrected within 24 hours. All other items must be corrected by the cure date. "
            "If the unit does not pass reinspection, housing assistance payments will be abated beginning the first "
            "of the following month.", SMALL)]
    p2 = [P("REINSPECTION RESULT", H1),
          kv_table([("Reinspection date", "08/13/2026"), ("Inspector", "R. Calloway-Pike"),
                    ("Result", "FAIL - item 2 not corrected; item 3 corrected")]),
          Spacer(1, 6),
          P("<b>Notice of HAP abatement.</b> Housing assistance payments for this unit are abated effective "
            "09/01/2026 and will remain abated until the unit passes inspection. Abated amounts will not be paid "
            "retroactively. The owner may not charge the family for any abated amount."),
          P("Next reinspection scheduled: 10/08/2026."),
          P(f"Notice sent to {escape(p['owner'])} c/o {MGMT['name']} and to the tenant on 08/14/2026.", SMALL)]
    return [p1, p2]


def inspection_pbv_pages():
    p = PROPS["BT"]
    rows = [["2A", "-", "-", "-", "-", "-"],
            ["2B", "Bedroom 2", "Egress - window blocked by fixed security bar", "Life-Threatening", "08/21/2026", "08/22/2026"],
            ["2C", "Kitchen", "Cabinet door missing", "Moderate", "09/19/2026", "09/05/2026"],
            ["3B", "Hall", "Smoke alarm missing battery", "Life-Threatening", "08/21/2026", "08/20/2026"],
            ["3D", "-", "-", "-", "-", "-"]]
    p1 = [P("NSPIRE-V INSPECTION REPORT", H1),
          P(f"{PHA['name']} - Project-Based Voucher Program", CENTER),
          P("(Simplified model - not an official HUD form)", CENTER),
          kv_table([("Project", f"{p['name']}, {p['street']}, {p['city']}"),
                    ("HAP contract", PBV_CONTRACT),
                    ("Inspection type", "Biennial (sample of contract units)"),
                    ("Inspection date", "08/20/2026"),
                    ("Units inspected", "2A, 2B, 2C, 3B, 3D"),
                    ("Inspector", "T. Okonedo-Marsh, NSPIRE-V Inspector")]),
          P("Deficiencies", H2),
          grid(["Unit", "Location", "Deficiency", "Severity", "Correct by", "Corrected"], rows,
               widths=[0.45 * inch, 0.8 * inch, 2.4 * inch, 1.1 * inch, 0.9 * inch, 0.9 * inch]),
          P("Life-Threatening deficiencies must be corrected within 24 hours of the inspection; all other "
            "deficiencies within 30 days.", SMALL)]
    p2 = [P("REINSPECTION", H1),
          kv_table([("Reinspection date", "09/18/2026"), ("Units", "2B, 2C, 3B"),
                    ("Result", "PASS - all cited deficiencies verified corrected")]),
          P("No abatement applied. Correction dates are as reported by the owner and verified on site.", SMALL)]
    return [p1, p2]


def inspection_pbra_pages():
    p = PROPS["BT"]
    rows = [["1B", "Unit - utility closet", "Water heater - leaking into drip pan", "Moderate", "09/30/2026", "-"],
            ["1D", "Unit - bathroom", "GFCI outlet inoperable", "Severe", "09/01/2026", "09/01/2026"],
            ["Site", "Walkway, bldg entry", "Sidewalk trip hazard (3/4 in. vertical)", "Moderate", "09/30/2026", "-"],
            ["1A", "-", "No deficiencies", "-", "-", "-"],
            ["1C", "-", "No deficiencies", "-", "-", "-"]]
    p1 = [P("NSPIRE PHYSICAL INSPECTION REPORT", H1),
          P("Multifamily (Project-Based Rental Assistance)", CENTER),
          P("(Simplified model of a REAC NSPIRE report - not an official HUD form)", CENTER),
          kv_table([("Property", f"{p['name']}, {p['street']}, {p['city']}"),
                    ("Contract", PBRA_CONTRACT),
                    ("Inspection date", "08/31/2026"),
                    ("Score", "74"),
                    ("Units inspected", "1A, 1B, 1C, 1D + site and common areas")]),
          P("Deficiencies", H2),
          grid(["Unit", "Location", "Deficiency", "Severity", "Correct by", "Corrected"], rows,
               widths=[0.45 * inch, 1.2 * inch, 2.2 * inch, 0.8 * inch, 0.9 * inch, 0.9 * inch]),
          P("Owner must correct Severe deficiencies within 24 hours and Moderate deficiencies within 30 days, and "
            "certify all corrections to the contract administrator by the correction date.", SMALL)]
    p2 = [P("OWNER CERTIFICATION OF REPAIRS - STATUS", H1),
          kv_table([("Certification due", "09/30/2026"),
                    ("Report printed", "10/01/2026"),
                    ("Status", "NOT RECEIVED"),
                    ("Items outstanding", "1B water heater; site sidewalk trip hazard")]),
          P("Failure to certify may result in a follow-up inspection and referral for enforcement.", SMALL)]
    return [p1, p2]


# --------------------------------------------------------------------------
# Rent rolls
# --------------------------------------------------------------------------
def rr_rows(rr):
    spec = RENT_ROLLS[rr]
    on = spec["as_of"]
    rows = []
    for u in UNITS:
        if spec["prop"] and u["prop"] != spec["prop"]:
            continue
        status = status_on(u, on)
        if status == "Vacant":
            contract, ttp, hap = u["contract"], 0, 0
        else:
            contract, ttp, hap = split_on(u, on)
        r = {"prop": u["prop"], "unit": u["unit"], "type": u["type"], "program": u["program"],
             "tenant": u["tenant"] if status != "Vacant" else "VACANT", "status": status,
             "contract": contract, "ttp": ttp, "hap": hap,
             "start": d(u["lease"][0]) if status != "Vacant" and u.get("lease") else None,
             "end": d(u["lease"][1]) if status != "Vacant" and u.get("lease") else None,
             "move_in": d(u["move_in"]) if status != "Vacant" and u.get("move_in") else None,
             "recert": d(u["recert"]) if status != "Vacant" and u.get("recert") else None,
             "market": u["contract"]}
        ov = RR_OVERRIDES.get((rr, u["prop"], u["unit"]), {})
        if ov.get("status") == "Occupied" and status == "Vacant":
            r.update(tenant=u["tenant"], start=d(u["lease"][0]), end=d(u["lease"][1]),
                     move_in=d(u["move_in"]), recert=d(u["recert"]))
        r.update(ov)
        rows.append(r)
    return rows


def num(x):
    return "" if x is None else f"{x:.2f}"


def write_csv(path, title_rows, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        for t in title_rows:
            w.writerow(t)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def program_label(r, style):
    prog = r["program"]
    if prog == "HCV" and r["status"] == "Vacant":
        return ""  # a tenant-based voucher leaves with the tenant
    if prog == "Market":
        return "" if style in ("appfolio", "buildium") else "Market"
    return {"HCV": "HCV Voucher", "PBV": "PBV", "PBRA": "Sec 8 PBRA"}[prog] if style != "seller" else prog


def make_rr_appfolio(out):
    rows = rr_rows("RR1")
    header = ["Unit", "BD/BA", "Tenant", "Status", "Move-in", "Lease From", "Lease To", "Market Rent", "Rent",
              "Tenant Portion", "HAP", "Subsidy", "Next Recert"]
    data = []
    for r in rows:
        data.append([r["unit"], r["type"], r["tenant"], r["status"], fmt_date(r["move_in"]), fmt_date(r["start"]),
                     fmt_date(r["end"]), num(r["market"]), num(r["contract"] if r["status"] != "Vacant" else 0),
                     num(r["ttp"]), num(r["hap"]), program_label(r, "appfolio"), fmt_date(r["recert"])])
    occ = [r for r in rows if r["status"] != "Vacant"]
    data.append(["Total", "", f"{len(occ)} occupied / {len(rows)} units", "", "", "", "",
                 num(sum(r["market"] for r in rows)), num(sum(r["contract"] for r in occ)),
                 num(sum(r["ttp"] or 0 for r in occ)), num(sum(r["hap"] or 0 for r in occ)), "", ""])
    write_csv(os.path.join(out, RENT_ROLLS["RR1"]["file"]),
              [["Rent Roll"], [f"Properties: {PROPS['JR']['name']} - {PROPS['JR']['street']} {PROPS['JR']['city']}"],
               [f"As of: {fmt_date(AS_OF)}"], []], header, data)


def make_rr_realpage(out):
    rows = rr_rows("RR3")
    header = ["Bldg/Unit", "Floorplan", "Resident", "Program", "Status", "Move In", "Lease Start", "Lease End",
              "Contract Rent", "Tenant Share", "Subsidy Amount", "Recert Due"]
    data = []
    for r in rows:
        data.append([r["unit"], r["type"], r["tenant"], program_label(r, "realpage"), r["status"],
                     fmt_date(r["move_in"]), fmt_date(r["start"]), fmt_date(r["end"]),
                     num(r["contract"] if r["status"] != "Vacant" else 0), num(r["ttp"]), num(r["hap"]),
                     fmt_date(r["recert"])])
    write_csv(os.path.join(out, RENT_ROLLS["RR3"]["file"]),
              [[f"{PROPS['BT']['name']} - Rent Roll with Lease Charges"], [f"As Of = {fmt_date(AS_OF)}"],
               ["Month Year = 10/2026"]], header, data)


def make_rr_buildium(out):
    rows = rr_rows("RR4")
    header = ["Property", "Unit", "Tenants", "Status", "Lease Start", "Lease End", "Rent", "Tenant Payment",
              "Housing Assistance Payment", "Program", "Recertification"]
    data = []
    for r in rows:
        data.append([PROPS["BT"]["name"], r["unit"], "" if r["status"] == "Vacant" else r["tenant"], r["status"],
                     fmt_date(r["start"]), fmt_date(r["end"]), num(r["contract"] if r["status"] != "Vacant" else 0),
                     num(r["ttp"]), num(r["hap"]), program_label(r, "buildium"), fmt_date(r["recert"])])
    write_csv(os.path.join(out, RENT_ROLLS["RR4"]["file"]), [], header, data)


def _fixed_xlsx(wb, path):
    """openpyxl stamps the current time into docProps and zip entries; pin both."""
    from datetime import datetime
    fixed = datetime(2026, 10, 1, 8, 0, 0)
    wb.properties.created = fixed
    wb.properties.modified = fixed
    wb.properties.creator = "Abstractly synthetic fixtures"
    buf = io.BytesIO()
    wb.save(buf)
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl re-stamps <dcterms:modified> with "now" on save.
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2026-10-01T08:00:00Z", data)
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 10, 1, 8, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(zi, data)


BOLD = Font(bold=True)
HEAD_FILL = PatternFill("solid", fgColor="DDE3EA")


def make_rr_yardi(out):
    rows = rr_rows("RR2")
    wb = Workbook()
    ws = wb.active
    ws.title = "Rent Roll"
    ws.append([f"{PROPS['JR']['name']} (junrow)"])
    ws.append(["Rent Roll - Affordable"])
    ws.append([f"As Of = {fmt_date(SEP_1)}"])
    ws.append(["Month Year = 09/2026"])
    ws.append([])
    ws["A1"].font = Font(bold=True, size=13)
    header = ["Unit", "Unit Type", "Resident", "Status", "Move In", "Lease Start", "Lease Expiration",
              "Market Rent", "Contract Rent", "Resident Rent", "Subsidy Rent", "Subsidy Type", "Recert Date"]
    ws.append(header)
    for c in ws[6]:
        c.font = BOLD
        c.fill = HEAD_FILL
    for r in rows:
        ws.append([r["unit"], r["type"], r["tenant"], r["status"], fmt_date(r["move_in"]) or None,
                   fmt_date(r["start"]) or None, fmt_date(r["end"]) or None, r["market"],
                   r["contract"] if r["status"] != "Vacant" else 0, r["ttp"], r["hap"],
                   program_label(r, "yardi"), fmt_date(r["recert"]) or None])
    occ = [r for r in rows if r["status"] != "Vacant"]
    ws.append([])
    ws.append(["Total Occupied", None, f"{len(occ)} units", None, None, None, None, None,
               sum(r["contract"] for r in occ), sum(r["ttp"] for r in occ), sum(r["hap"] for r in occ)])
    ws.append(["Total Vacant", None, f"{len(rows) - len(occ)} units", None, None, None, None,
               sum(r["market"] for r in rows if r["status"] == "Vacant")])
    for row in ws.iter_rows(min_row=7):
        for c in row[7:11]:
            c.number_format = "#,##0.00"
    for i, w in enumerate([7, 10, 26, 10, 11, 11, 15, 12, 13, 13, 12, 12, 12], start=1):
        ws.column_dimensions[ws.cell(row=6, column=i).column_letter].width = w
    _fixed_xlsx(wb, os.path.join(out, RENT_ROLLS["RR2"]["file"]))


def make_rr_seller(out):
    rows = rr_rows("RR5")
    wb = Workbook()
    ws = wb.active
    ws.title = "Rent Roll"
    ws.append(["Seller Rent Roll - Juniper Row Apartments & Bellmont Terrace"])
    ws.append([f"Prepared by seller for buyer due diligence - as of {fmt_date(AS_OF)}"])
    ws.append([])
    ws["A1"].font = Font(bold=True, size=13)
    header = ["Property", "Unit", "Type", "Tenant", "Program", "Status", "Lease Start", "Lease End",
              "Contract Rent", "Tenant Rent", "HAP", "Recert Date", "Notes"]
    ws.append(header)
    for c in ws[4]:
        c.font = BOLD
        c.fill = HEAD_FILL
        c.alignment = Alignment(wrap_text=True)
    for r in rows:
        ws.append([PROPS[r["prop"]]["name"], r["unit"], r["type"], r["tenant"], r["program"], r["status"],
                   fmt_date(r["start"]) or None, fmt_date(r["end"]) or None,
                   r["contract"] if r["status"] != "Vacant" else 0, r["ttp"], r["hap"],
                   fmt_date(r["recert"]) or None, None])
    for row in ws.iter_rows(min_row=5):
        for c in row[8:11]:
            c.number_format = "#,##0.00"
    for i, w in enumerate([24, 6, 9, 26, 8, 10, 11, 11, 13, 12, 10, 12, 18], start=1):
        ws.column_dimensions[ws.cell(row=4, column=i).column_letter].width = w
    s = wb.create_sheet("Summary")
    s.append(["Property", "Units", "Occupied", "Monthly Contract Rent", "Monthly Tenant Rent", "Monthly HAP"])
    for c in s[1]:
        c.font = BOLD
    for key in ("JR", "BT"):
        pr = [r for r in rows if r["prop"] == key]
        occ = [r for r in pr if r["status"] != "Vacant"]
        s.append([PROPS[key]["name"], len(pr), len(occ), sum(r["contract"] for r in occ),
                  sum(r["ttp"] or 0 for r in occ), sum(r["hap"] or 0 for r in occ)])
    _fixed_xlsx(wb, os.path.join(out, RENT_ROLLS["RR5"]["file"]))


# --------------------------------------------------------------------------
# Registers
# --------------------------------------------------------------------------
REG_HEADER = ["Payment Date", "Vendor ID", "Payee", "Program", "HAP Contract", "Client ID", "Head of Household",
              "Unit Address", "Unit", "Contract Rent", "HAP Amount", "Adj Code", "Adj Amount", "Net Payment", "Memo"]


def make_register(month, out):
    rows = register_rows(month)
    base = os.path.join(out, REGISTERS[month]["file"])
    money_cols = {"Contract Rent", "HAP Amount", "Adj Amount", "Net Payment"}
    write_csv(base + ".csv", [], REG_HEADER,
              [[f"{r[h]:.2f}" if h in money_cols else r[h] for h in REG_HEADER] for r in rows])
    # PDF statement
    label = date.fromisoformat(month + "-01").strftime("%B %Y")
    flows = [P(f"{PHA['name'].upper()}", H1),
             P(f"Housing Assistance Payments Register - {label} (payment date "
               f"{fmt_date(REGISTERS[month]['pay_date'])})", CENTER), Spacer(1, 4)]
    for key in ("JR", "BT"):
        pr = [r for r in rows if r["Vendor ID"] == PROPS[key]["vendor_id"]]
        flows.append(P(f"Payee: {escape(PROPS[key]['owner'])} - vendor {PROPS[key]['vendor_id']}", H2))
        body = [[r["Program"], r["HAP Contract"], r["Client ID"], r["Head of Household"], r["Unit"],
                 money(r["Contract Rent"]), money(r["HAP Amount"]), r["Adj Code"],
                 money(r["Adj Amount"]) if r["Adj Code"] else "", money(r["Net Payment"]),
                 P(escape(r["Memo"]), SMALL)] for r in pr]
        body.append(["", "", "", "Payee total", "", "", money(sum(r["HAP Amount"] for r in pr)), "",
                     money(sum(r["Adj Amount"] for r in pr)), money(sum(r["Net Payment"] for r in pr)), ""])
        flows.append(grid(["Prog", "HAP contract", "Client", "Head of household", "Unit", "Contract rent",
                           "HAP", "Code", "Adj", "Net paid", "Memo"], body,
                          widths=[0.45 * inch, 1.25 * inch, 0.75 * inch, 1.55 * inch, 0.4 * inch, 0.85 * inch,
                                  0.75 * inch, 0.45 * inch, 0.7 * inch, 0.75 * inch, 2.1 * inch], font=7.2))
    flows.append(Spacer(1, 6))
    flows.append(P("Adjustment codes: " + "; ".join(f"<b>{k}</b> = {escape(v)}" for k, v in ADJ_CODES.items()), SMALL))
    build_pdf(base + ".pdf", [flows], f"{PHA['short']} HAP Register {label}", pagesize=landscape(letter))


# --------------------------------------------------------------------------
# Answer key
# --------------------------------------------------------------------------
def fmt_impact(x):
    return "" if x is None else money(x)


def describe_evidence(ev):
    t = ev["type"]
    if t == "rent_roll_cell":
        v = "(blank)" if ev["value"] is None else ev["value"]
        return f"`{ev['file']}` unit {ev['unit']}, column \"{ev['column']}\" = {v}"
    if t == "register_cell":
        v = "(blank)" if ev["value"] == "" else ev["value"]
        return f"`{ev['file']}` unit {ev['unit']}, column \"{ev['column']}\" = {v}"
    if t == "register_absent":
        return f"`{ev['file']}` has no row for unit {ev['unit']}"
    if t == "pdf_absent":
        return f"`{ev['file']}` page {ev['page']} does NOT contain \"{ev['text']}\""
    return f"`{ev['file']}` page {ev['page']}: \"{ev['contains']}\""


def write_answer_key(out, errors):
    flags = sorted({e["flag"] for e in errors} | {f for e in errors for f in e.get("also_flags", [])})
    key = {
        "as_of": AS_OF.isoformat(),
        "properties": {k: {"name": v["name"], "owner": v["owner"]} for k, v in PROPS.items()},
        "files": {
            "leases": [s["file"] for s in LEASES],
            "hap_contracts": [v["file"] for v in HAP_CONTRACTS.values()],
            "rent_rolls": [v["file"] for v in RENT_ROLLS.values()],
            "hap_registers": [v["file"] + ext for v in REGISTERS.values() for ext in (".csv", ".pdf")],
            "inspections": [v["file"] for v in INSPECTIONS.values()],
        },
        "scanned_image_pages": [{"file": s["file"], "page": lease_page(s, "signatures")}
                                for s in LEASES if s.get("scanned_signatures")],
        "errors": errors,
        "clean_controls": [{"property": PROPS[c["prop"]]["name"], "unit": c["unit"], "note": c["note"]}
                           for c in CLEAN_CONTROLS],
        "flags": flags,
    }
    with open(os.path.join(out, "answer_key.json"), "w", encoding="utf-8") as f:
        json.dump(key, f, indent=2, sort_keys=False)
        f.write("\n")

    L = []
    a = L.append
    a("# Section 8 fixture set - ANSWER KEY")
    a("")
    a("> Generated by `generate_section8_fixtures.py` - do not edit by hand; change the generator and re-run.")
    a("> Machine-readable copy: `answer_key.json` (same content; `evidence` items are checked by")
    a("> `backend/tests/test_section8_fixtures.py`).")
    a("")
    a(f"**Review as-of date: {fmt_date(AS_OF)}.** All \"overdue\", \"expired\" and \"to date\" figures are measured")
    a("against this fixed date, so the set never goes stale. **\"To date\" counts every monthly charge or payment due")
    a("on or before 10/01/2026**, so the October 1 rent charge and HAP payment are included. Everything here is fictional; rule references are")
    a("paraphrased and **not practitioner-checked**. Flag codes are *proposals* for a future checker - nothing in")
    a("the app emits them yet.")
    a("")
    a("## The deal")
    a("")
    a(f"- **{PROPS['JR']['name']}** ({PROPS['JR']['owner']}): 18 units, tenant-based Housing Choice Voucher")
    a(f"  households + market units. PHA: {PHA['name']} (fictional).")
    a(f"- **{PROPS['BT']['name']}** ({PROPS['BT']['owner']}): 14 units. First floor (1A-1D) under PBRA contract")
    a(f"  `{PBRA_CONTRACT}` (paid by a contract administrator, so **not** on the PHA registers); 2A/2B/2C/3B/3C/3D")
    a(f"  under PBV contract `{PBV_CONTRACT}` (Exhibit A); the rest market.")
    a("")
    a("## Files")
    a("")
    a("| Kind | File | Notes |")
    a("|---|---|---|")
    for s in LEASES:
        u = U[(s["prop"], s["unit"])]
        notes = [f"{u['program']}", f"{len(lease_page_order(s))} pp"]
        if s.get("scanned_signatures"):
            notes.append(f"p{lease_page(s, 'signatures')} is a scanned image (no text layer)")
        if s.get("addendum_first"):
            notes.append("addendum comes before the lease body")
        if s.get("rent_notice"):
            notes.append(f"rent-increase notice on p{lease_page(s, 'notice')}")
        a(f"| Lease + tenancy addendum | `{s['file']}` | {'; '.join(notes)} |")
    for k, v in HAP_CONTRACTS.items():
        a(f"| HAP contract ({v['kind']}) | `{v['file']}` | |")
    for k, v in RENT_ROLLS.items():
        a(f"| Rent roll ({v['style']}) | `{v['file']}` | as of {fmt_date(v['as_of'])} |")
    for k, v in REGISTERS.items():
        a(f"| PHA HAP register | `{v['file']}.csv` + `.pdf` | paid {fmt_date(v['pay_date'])}; HCV + PBV only |")
    for k, v in INSPECTIONS.items():
        a(f"| Inspection | `{v['file']}` | |")
    a("")
    a("## Planted errors")
    a("")
    a(f"{len(errors)} planted errors. Severity: **high** = money or contract at risk, **medium** = money to chase")
    a("or a compliance breach, **low** = minor / one-time.")
    a("")
    a("| ID | Category | Unit(s) | Expected flag | Severity | Monthly $ | To date $ |")
    a("|---|---|---|---|---|---|---|")
    for e in errors:
        fl = f"`{e['flag']}`" + "".join(f" + `{x}`" for x in e.get("also_flags", []))
        a(f"| {e['id']} | {e['category']} | {', '.join(e['units'])} | {fl} | {e['severity']} | "
          f"{fmt_impact(e['monthly_impact'])} | {fmt_impact(e['impact_to_date'])} |")
    a("")
    for e in errors:
        a(f"### {e['id']} - {e['category']}")
        a("")
        a(f"- **Unit(s):** {', '.join(e['units'])}")
        fl = f"`{e['flag']}`" + "".join(f", also `{x}`" for x in e.get("also_flags", []))
        a(f"- **Expected flag:** {fl} (severity {e['severity']})")
        a(f"- **What's wrong:** {e['what']}")
        imp = []
        if e["monthly_impact"] is not None:
            imp.append(f"{money(e['monthly_impact'])}/mo")
        if e["impact_to_date"] is not None:
            imp.append(f"{money(e['impact_to_date'])} to date")
        a(f"- **Dollar impact:** {'; '.join(imp) + ' - ' if imp else ''}{e['impact_note']}")
        a(f"- **Rule:** {e['rule']}")
        a("- **Evidence:**")
        for ev in e["evidence"]:
            a(f"  - {describe_evidence(ev)}")
        a("")
    a("## Clean controls (must raise NO flag)")
    a("")
    for c in CLEAN_CONTROLS:
        a(f"- **{PROPS[c['prop']]['name']} {c['unit']}** - {c['note']}")
    a("")
    a("Every market-rate unit and the vacant units (Juniper Row 107, Bellmont Terrace 3C) should also raise no")
    a("Section 8 flag. Bellmont 3C is a vacant PBV Exhibit A unit: no HAP is expected (the contract has no vacancy")
    a("payments), so its absence from the registers is correct.")
    a("")
    a("## Not errors (traps)")
    a("")
    a("- Juniper Row 101, Aug register: `RTA` +$45 one-time correction of a July short-pay, with a memo; the ongoing")
    a("  HAP stays $905 in every month and document - a coded, explained adjustment.")
    a("- Juniper Row 206, Sep register: `INT` memo line - the PHA's notice of the new split (the error is the rent")
    a("  roll not following it, S8-03).")
    a("- Juniper Row 104 HQS item 1 (smoke detector, 24-hour) was corrected within 24 hours.")
    a("- Bellmont 3B smoke alarm (Life-Threatening) corrected the same day; 2C cabinet door (Moderate) corrected")
    a("  within 30 days.")
    a("- Bellmont 1D Severe GFCI item corrected on its 24-hour deadline.")
    a("- PBRA units are absent from the PHA registers by design (paid via TRACS by the contract administrator).")
    a("- No HAP for vacant PBV unit 3C: this fixture's PBV contract says no vacancy payments. That is a term of")
    a("  *this* contract, not a general rule; real PBV contracts may allow limited vacancy payments.")
    a("- Juniper Row 210 and Bellmont 2A show lease end dates before the as-of date: both continue month to month")
    a("  under their lease terms. Their real problems are the missed recerts (S8-11, S8-10), not lease expiry.")
    a("")
    a("## Modelling caveats")
    a("")
    a("- Juniper Row 104 is inspected under legacy **HQS** while the PBV project uses **NSPIRE-V**. That models a PHA")
    a("  still inside HUD's NSPIRE-V transition window for its HCV program; check the current compliance date before")
    a("  treating either standard as the only valid one in 2026.")
    a("- Cure periods used: Life-Threatening 24 hours, other deficiencies 30 days (HCV/PBV); Severe 24 hours and")
    a("  Moderate 30 days (multifamily NSPIRE). Paraphrased, not practitioner-checked.")
    a("")
    a("## Regenerating")
    a("")
    a("```bash")
    a("cd backend && venv/bin/python tests/fixtures/section8/generate_section8_fixtures.py")
    a("venv/bin/python tests/test_section8_fixtures.py   # byte-identical regenerate + evidence checks")
    a("```")
    with open(os.path.join(out, "ANSWER_KEY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# --------------------------------------------------------------------------
def generate(out=HERE):
    for spec in LEASES:
        make_lease(spec, out)
    for key, spec in HAP_CONTRACTS.items():
        pages = {"HCV": lambda: hcv_contract_pages(key), "PBV": pbv_contract_pages,
                 "PBRA": pbra_contract_pages}[spec["kind"]]()
        build_pdf(os.path.join(out, spec["file"]), pages, f"HAP contract - {os.path.basename(spec['file'])[:-4]}")
    build_pdf(os.path.join(out, INSPECTIONS["IN1"]["file"]), inspection_hqs_pages(), "HQS inspection - Juniper Row 104")
    build_pdf(os.path.join(out, INSPECTIONS["IN2"]["file"]), inspection_pbv_pages(), "NSPIRE-V inspection - Bellmont PBV")
    build_pdf(os.path.join(out, INSPECTIONS["IN3"]["file"]), inspection_pbra_pages(), "NSPIRE inspection - Bellmont PBRA")
    make_rr_appfolio(out)
    make_rr_yardi(out)
    make_rr_realpage(out)
    make_rr_buildium(out)
    make_rr_seller(out)
    for month in REGISTERS:
        make_register(month, out)
    errors = build_errors()
    write_answer_key(out, errors)
    return errors


def generated_files():
    """Every file the generator writes, relative to the fixture folder."""
    files = [s["file"] for s in LEASES] + [v["file"] for v in HAP_CONTRACTS.values()] + \
            [v["file"] for v in INSPECTIONS.values()] + [v["file"] for v in RENT_ROLLS.values()] + \
            [v["file"] + ext for v in REGISTERS.values() for ext in (".csv", ".pdf")] + \
            ["ANSWER_KEY.md", "answer_key.json"]
    return sorted(files)


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else HERE
    errs = generate(out_dir)
    print(f"Wrote {len(generated_files())} files and {len(errs)} planted errors to {out_dir}")
