"""
IHDA Tenant Income Certification (revised 11-2025). AcroForm, 7 pages
(pages 4-7 are instructions).

Note: despite the "in" in this id (from eval-docs.md), IHDA here is the
Illinois Housing Development Authority; the form is a joint IHDA / City of
Chicago / Cook County form. The sample uses a fictional Illinois address.

Household: initial certification, 1 person in a studio designated at 70%
AMI (income averaging), two bank accounts under the asset threshold so
actual asset income is used. All values fictional.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from world import Household, LihtcCert, Member, num  # noqa: E402

_head = Member("Noor", "Vasquez-Hale", "Head", 29, "07/08/1997", annual_wages=41_250, annual_benefits=1_800)
_hh = Household(members=[_head], assets_cash_value=7_750, imputed_asset_income=24)
_cert = LihtcCert(_hh, bedrooms=0, ami_pct=70, utility_allowance=74)
_cert.check()

_GIG = 1_800                      # self-employment side income, column (D); world counts it in benefits
_ASSETS = [("Checking account", 2_150, 2), ("Savings account", 5_600, 22)]
assert sum(a[2] for a in _ASSETS) == _hh.imputed_asset_income
assert sum(a[1] for a in _ASSETS) == _hh.assets_cash_value

ADDRESS = "1717 North Larchmere Avenue"
NAME = _head.name

_P = [
    {"acro": "Check Box1", "text": "X"},                       # Initial Certification
    {"acro": "Effective Date", "text": "12/01/2026"},
    {"acro": "Movein Date", "text": "12/01/2026"},
    {"acro": "Property Name", "text": "Larchmere Lofts"},
    {"acro": "TC", "text": "TC-26-118"},
    {"acro": "Property Address", "text": ADDRESS},
    {"acro": "City", "text": "Fernwood Grove", "size": 8},
    {"acro": "State", "text": "IL"},
    {"acro": "Zip", "text": "60999"},
    {"acro": "BIN", "text": "IL-26-00342"},
    {"acro": "County", "text": "Maple Ridge", "size": 8},
    {"acro": "Unit Number", "text": "107"},
    {"acro": "Bedrooms", "text": "0"},
    # Part II
    {"acro": "Last Name1", "text": _head.last},
    {"acro": "First Name  Middle Initial1", "text": _head.first},
    {"acro": "Gender MFHEAD", "text": "F"},
    {"acro": "Date of Birth MMDDYYYYHEAD", "text": _head.dob, "size": 8},
    {"acro": "FT Student Y N NAHEAD", "text": "N"},
    # Part III
    {"acro": "HH Mbr Row1", "text": "1"},
    {"acro": "A Employment or WagesRow1", "text": num(41_250)},
    {"acro": "D Other IncomeRow1", "text": num(_GIG)},
    {"acro": "fill_122", "text": num(41_250)},
    {"acro": "fill_123", "text": "0"},
    {"acro": "fill_124", "text": "0"},
    {"acro": "fill_125", "text": num(_GIG)},
    {"acro": "fill_126", "text": num(41_250 + _GIG)},
    # Part IV
    *[p for i, (kind, value, income) in enumerate(_ASSETS, start=1) for p in (
        {"acro": f"HH Mbr Row{i}_2", "text": "1"},
        {"acro": f"F Type of AssetRow{i}", "text": kind},
        {"acro": f"G CDRow{i}", "text": "C"},
        {"acro": f"H Cash Value of AssetRow{i}", "text": num(value)},
        {"acro": f"I AIRow{i}", "text": "A"},
        {"acro": f"J Annual Income from AssetRow{i}", "text": num(income)},
    )],
    {"acro": "H Cash Value of Asset Total", "text": num(_hh.assets_cash_value)},
    {"acro": "Rate", "text": "0.40%"},
    {"acro": "fill_127", "text": num(_hh.imputed_asset_income)},
    {"acro": "fill_128", "text": num(_hh.annual_income), "size": 10},
    # Part V
    {"acro": "fill_40", "text": num(_hh.annual_income), "size": 10},
    {"acro": "Check Box5", "text": "X"},                       # meets income restriction at 70%
    {"acro": "Text1", "text": num(_cert.income_limit)},
    {"acro": "Text2", "text": num(_hh.annual_income)},
    {"acro": "Text7", "text": "1"},
    # Part VI
    {"acro": "Text3", "text": num(_cert.tenant_paid_rent)},
    {"acro": "Rental Assistance", "text": "0"},
    {"acro": "Text4", "text": num(_cert.utility_allowance)},
    {"acro": "undefined_6", "text": "0"},
    {"acro": "fill_41", "text": num(_cert.gross_rent), "size": 10},
    {"acro": "Text5", "text": num(_cert.max_gross_rent)},
    {"acro": "Check Box15", "text": "X"},                      # unit meets rent restriction at 70%
    # Part VII / VIII / IX
    {"acro": "Check Box23", "text": "X"},                      # not all full-time students
    {"acro": "Check Box24", "text": "X"},                      # a. Tax Credit
    {"acro": "Did Not Disclose1", "text": "X"},
    {"acro": "Disabled YN1", "text": "N"},
    # Signatures (page 3)
    {"acro": "Signature", "text": NAME},
    {"acro": "Date", "text": "11/20/2026"},
    {"acro": "SIGNATURE OF OWNERREPRESENTATIVE", "text": "Hollis Brandt-Ivey, Property Manager"},
    {"acro": "DATE", "text": "11/24/2026"},
]

SPEC = {
    "id": "tic_il_ihda",
    "source": "tic_il_ihda.pdf",
    "form": "IHDA (Illinois) / City of Chicago / Cook County Tenant Income Certification (rev. 11-2025)",
    "program": "LIHTC",
    "doc_type": "tic",
    "notes": "Initial certification, 1-person household, studio designated at 70% AMI (income averaging). "
             "Assets under the threshold, actual asset income used. Id says 'in' but the issuer is Illinois.",
    "placements": _P,
    "lease_fields": {
        "tenant": NAME,
        "landlord": None,                 # no owner-name field on the TIC
        "rent_amount": f"${_cert.tenant_paid_rent:,}",
        "lease_start_date": None,         # move-in date is not a lease term
        "lease_end_date": None,
        "property_address": ADDRESS,
        "security_deposit": None,
    },
    "program_fields": {
        "certification_type": {"value": "Initial Certification", "type": "checkbox"},
        "effective_date": {"value": "12/01/2026", "type": "date"},
        "move_in_date": {"value": "12/01/2026", "type": "date"},
        "property_name": {"value": "Larchmere Lofts", "type": "text"},
        "tc_number": {"value": "TC-26-118", "type": "text"},
        "building_address": {"value": ADDRESS, "type": "text"},
        "city": {"value": "Fernwood Grove", "type": "text"},
        "zip": {"value": "60999", "type": "int"},
        "bin": {"value": "IL-26-00342", "type": "text"},
        "county": {"value": "Maple Ridge", "type": "text"},
        "unit_number": {"value": "107", "type": "text"},
        "bedrooms": {"value": "0", "type": "int"},
        "head_of_household": {"value": NAME, "type": "text"},
        "member_1_last_name": {"value": _head.last, "type": "text"},
        "member_1_first_name": {"value": _head.first, "type": "text"},
        "member_1_dob": {"value": _head.dob, "type": "date"},
        "total_employment_income": {"value": "$41,250", "type": "money"},
        "total_other_income": {"value": f"${_GIG:,}", "type": "money"},
        "total_income_e": {"value": f"${41_250 + _GIG:,}", "type": "money"},
        "asset_1_type": {"value": _ASSETS[0][0], "type": "text"},
        "asset_1_cash_value": {"value": f"${_ASSETS[0][1]:,}", "type": "money"},
        "asset_2_type": {"value": _ASSETS[1][0], "type": "text"},
        "asset_2_cash_value": {"value": f"${_ASSETS[1][1]:,}", "type": "money"},
        "total_asset_cash_value": {"value": f"${_hh.assets_cash_value:,}", "type": "money"},
        "passbook_rate": {"value": "0.40%", "type": "pct"},
        "asset_income": {"value": f"${_hh.imputed_asset_income:,}", "type": "money"},
        "total_annual_income": {"value": f"${_hh.annual_income:,}", "type": "money"},
        "income_limit": {"value": f"${_cert.income_limit:,}", "type": "money"},
        "designated_income_restriction_pct": {"value": "70%", "type": "checkbox"},
        "household_income_at_move_in": {"value": f"${_hh.annual_income:,}", "type": "money"},
        "household_size_at_move_in": {"value": "1", "type": "int"},
        "tenant_paid_rent": {"value": f"${_cert.tenant_paid_rent:,}", "type": "money"},
        "utility_allowance": {"value": f"${_cert.utility_allowance:,}", "type": "money"},
        "gross_rent": {"value": f"${_cert.gross_rent:,}", "type": "money"},
        "maximum_rent_limit": {"value": f"${_cert.max_gross_rent:,}", "type": "money"},
        "program": {"value": "Tax Credit", "type": "checkbox"},
        "household_signature_date": {"value": "11/20/2026", "type": "date"},
        "owner_signature_date": {"value": "11/24/2026", "type": "date"},
    },
}
