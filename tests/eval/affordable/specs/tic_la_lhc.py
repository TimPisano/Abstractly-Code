"""
Louisiana Housing Corporation Tenant Income Certification (HOTMA forms
page; national TIC layout, 2024). Filled with the shared builder in
tic_sc.py.

Household: annual recertification, elderly 2-person household, 1BR at
50% AMI, with an HCV voucher. The rent to owner sits at the LIHTC cap;
the voucher pays part of it, so the TIC's Tenant Rent is the tenant's
portion and Gross Rent = tenant portion + UA (Section 8 payments are
excluded from LIHTC gross rent). All values fictional.
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from world import Household, LihtcCert, Member  # noqa: E402

_spec = importlib.util.spec_from_file_location("tic_sc_shared", Path(__file__).with_name("tic_sc.py"))
_shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_shared)

_hh = Household(
    members=[
        Member("Augustin", "Delacroix-Pell", "Head", 68, "03/09/1958", annual_benefits=15_600),
        Member("Celestine", "Delacroix-Pell", "Spouse", 66, "11/30/1959", annual_benefits=12_240),
    ],
    assets_cash_value=4_300,
    imputed_asset_income=31,
)
_cert = LihtcCert(_hh, bedrooms=1, ami_pct=50, utility_allowance=96, section8_assistance=520)
_cert.check()

_rent_to_owner = _cert.tenant_paid_rent                 # at the cap
_tenant_portion = _rent_to_owner - _cert.section8_assistance
_gross = _tenant_portion + _cert.utility_allowance + _cert.other_charges
assert _gross <= _cert.max_gross_rent

SPEC = _shared.national_tic_spec({
    "id": "tic_la_lhc",
    "source": "tic_la_lhc.pdf",
    "form": "Louisiana Housing Corporation Tenant Income Certification (HOTMA forms, 2024 layout)",
    "notes": f"Annual recertification, elderly 2-person household, 1BR at 50% AMI, HCV voucher pays "
             f"${_cert.section8_assistance} of ${_rent_to_owner} rent to owner. Recert-only 140% line filled; "
             f"not over income.",
    "hh": _hh,
    "cert_type": "Recertification",
    "effective_date": "09/01/2026",
    "initial_qual_date": "09/01/2023",
    "move_in_date": "09/01/2023",
    "property_name": "Bayou Cypress Commons",
    "county": "Maple Ridge Parish",
    "bin": "LA-23-00418",
    "address": "2250 Magnolia Ferry Road, Port Allard, LA 70999",
    "unit": "114",
    "bedrooms": 1,
    # Social Security for both members, column (B)
    "income_rows": [(1, (0, 15_600, 0, 0)), (2, (0, 12_240, 0, 0))],
    "income_totals": (0, 27_840, 0, 0),
    "total_e": 27_840,
    "asset_income": _hh.imputed_asset_income,
    "household_signatures": [("Augustin Delacroix-Pell", "08/12/2026"), ("Celestine Delacroix-Pell", "08/12/2026")],
    "income_limit": _cert.income_limit,
    "designated_pct": 50,
    "income_at_move_in": 26_118,
    "size_at_move_in": 2,
    "recert_140": int(_cert.income_limit * 1.4),
    "tenant_rent": _tenant_portion,
    "ua": _cert.utility_allowance,
    "assistance": _cert.section8_assistance,
    "assistance_source": "HUD Housing Choice Voucher",
    "other_fees": _cert.other_charges,
    "gross_rent": _gross,
    "max_rent": None,                                    # this copy has no Maximum Rent Limit line
    "program_label": "LIHTC",
    "owner_rep": "Rosalind Theriot, Site Manager",
    "owner_signed": "08/15/2026",
})
