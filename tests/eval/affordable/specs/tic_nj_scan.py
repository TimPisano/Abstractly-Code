"""
NJ HMFA Tenant Income Certification (2025), a scanned and OCR'd copy of the
national TIC layout. Filled with the shared builder in tic_sc.py; positions
come from the OCR text layer, so they are rougher than the born-digital
copies. Pages 3-7 are the form's instructions and stay blank.

Household: move-in certification, 5 people, 3BR income-averaging unit
designated at 80% AMI, a mandatory fee in gross rent, no rental
assistance. All values fictional.
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
        Member("Desmond", "Okafor-Lind", "Head", 44, "06/14/1982", annual_wages=48_500),
        Member("Priya", "Okafor-Lind", "Spouse", 41, "02/27/1985", annual_wages=21_300),
        Member("Rafael", "Okafor-Lind", "Child", 19, "09/05/2007", annual_wages=6_200, student=True),
        Member("Amara", "Okafor-Lind", "Child", 12, "12/11/2013"),
        Member("Teo", "Okafor-Lind", "Child", 8, "05/20/2018"),
    ],
    assets_cash_value=6_400,
    imputed_asset_income=64,
)
_cert = LihtcCert(_hh, bedrooms=3, ami_pct=80, utility_allowance=188, other_charges=25)
_cert.check()

SPEC = _shared.national_tic_spec({
    "id": "tic_nj_scan",
    "source": "tic_nj_scan.pdf",
    "form": "NJ HMFA Tenant Income Certification (2025), scanned/OCR'd copy",
    "notes": "Move-in certification, 5-person household, 3BR income-averaging unit designated at 80% AMI. "
             "Gross rent = tenant rent + UA + $25 mandatory fee. OCR text layer underneath; positions approximate.",
    "hh": _hh,
    "cert_type": "Move-in",
    "effective_date": "10/15/2026",
    "initial_qual_date": "10/15/2026",
    "qual_dx": 10,                                   # step past the printed "I ___I" bracket
    "move_in_date": "10/15/2026",
    "property_name": "Quarry Lane Residences",
    "county": "Maple Ridge County",
    "bin": "NJ-26-00977",
    "address": "75 Quarry Lane, Bramwell, NJ 08999",
    "unit": "3C",
    "bedrooms": 3,
    "income_rows": [(1, (48_500, 0, 0, 0)), (2, (21_300, 0, 0, 0)), (3, (6_200, 0, 0, 0))],
    "income_totals": (76_000, 0, 0, 0),
    "total_e": 76_000,
    "asset_income": _hh.imputed_asset_income,
    "household_signatures": [("Desmond Okafor-Lind", "10/09/2026"), ("Priya Okafor-Lind", "10/09/2026"),
                             ("Rafael Okafor-Lind", "10/09/2026")],
    "income_limit": _cert.income_limit,
    "designated_pct": 80,
    "income_at_move_in": _hh.annual_income,
    "size_at_move_in": _hh.size,
    "tenant_rent": _cert.tenant_paid_rent,
    "ua": _cert.utility_allowance,
    "assistance": 0,
    "other_fees": _cert.other_charges,
    "gross_rent": _cert.gross_rent,
    "max_rent": None,                                # this copy has no Maximum Rent Limit line
    "program_label": "Housing Credit",
    "owner_rep": "Lorna Vandermeer, Compliance Specialist",
    "owner_signed": "10/12/2026",
})
