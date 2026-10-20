"""HUD-50059 Owner's Certification of Compliance (06/2014 edition, obsolete; layout test). PBRA annual recert. AcroForm.

Fictional household at fictional "Oakmont Terrace". Rent figures come from
world.PbraCert, so contract rent = tenant rent + assistance payment and
gross rent = contract rent + UA hold. Codes HUD defines in the MAT guide
(race, ethnicity, income status, eligibility universe) are left blank rather
than guessed. No SSNs are written.
"""

from world import Household, Member, PbraCert, income_limit, num

HH = Household(
    members=[
        Member("Marisol", "Penhallow", "Head", 38, "03/14/1988", annual_wages=26_520),
        Member("Elias", "Penhallow", "Child", 12, "07/02/2014"),
        Member("Nora", "Penhallow", "Child", 7, "11/23/2018"),
    ],
    assets_cash_value=1_200,
    imputed_asset_income=6,      # actual income from the savings account
    childcare_expense=1_800,
)
CERT = PbraCert(hh=HH, contract_rent=1_045, utility_allowance=96)

PROJECT = "Oakmont Terrace"
OWNER = "Oakmont Terrace Housing Associates LP"
HEAD = HH.head.name
DEP_DEDUCTION = 500 * HH.dependents
TOTAL_DEDUCTIONS = DEP_DEDUCTION + HH.childcare_expense
WAGES = HH.head.annual_wages
LOW, VLOW, XLOW = income_limit(3, 80), income_limit(3, 50), income_limit(3, 30)

assert HH.adjusted_income == HH.annual_income - TOTAL_DEDUCTIONS
assert CERT.tenant_rent + CERT.assistance_payment == CERT.contract_rent


def m(n):
    return f"{n:,}.00"


placements = [
    # page 1 summary block
    {"acro": "ProjectName", "index": 0, "text": PROJECT},
    {"acro": "EffectiveDate", "index": 0, "text": "11/01/2026"},
    {"acro": "TransactionType", "index": 0, "text": "AR"},
    {"acro": "VoucherDate", "index": 0, "text": "11/01/2026"},
    {"acro": "HeadOfHousehold", "index": 0, "text": HEAD},
    {"acro": "TTP", "index": 0, "text": m(CERT.total_tenant_payment)},
    {"acro": "AssistancePayment", "index": 0, "text": m(CERT.assistance_payment)},
    {"acro": "TenantRent", "index": 0, "text": m(CERT.tenant_rent)},
    {"acro": "UnitNumber", "index": 0, "text": "3C"},
    {"acro": "TenantSigned", "text": "10/18/2026"},
    {"acro": "OwnerSigned", "text": "10/20/2026"},
    # printed name in the owner/agent signature box (no widget there)
    {"anchor": "Owner/Agent", "page": 1, "occurrence": 2, "where": "below", "dx": 20, "dy": 1, "text": OWNER},
    {"acro": "Page1ofN", "text": "Page 1 of 2"},
    # page 2, section A: project and unit
    {"acro": "ProjectName", "index": 1, "text": PROJECT},
    {"acro": "SubsidyType", "text": "Section 8"},
    {"acro": "iREMSPropertyID", "text": "800091733"},
    {"acro": "ProjectNumber", "text": "073-35412"},
    {"acro": "ContractNumber", "text": "IN36L991417"},
    {"acro": "iMAXID", "text": "OAKMTERR"},
    {"acro": "HUDOwned", "text": "N"},
    {"acro": "EffectiveDate", "index": 1, "text": "11/01/2026"},
    {"acro": "VoucherDate", "index": 1, "text": "11/01/2026"},
    {"acro": "NextRecert", "text": "11/01/2027"},
    {"acro": "MoveInDate", "text": "11/01/2019"},
    {"acro": "TransactionType", "index": 1, "text": "AR"},
    {"acro": "EIVIndicator", "text": "Y"},
    {"acro": "UnitNumber", "index": 1, "text": "3C"},
    {"acro": "NumBedrooms", "text": "2"},
    {"acro": "SecurityDeposit", "text": m(CERT.total_tenant_payment)},
    {"acro": "ContractRent", "text": m(CERT.contract_rent)},
    {"acro": "UtilityAllowance", "text": m(CERT.utility_allowance)},
    {"acro": "GrossRent", "text": m(CERT.gross_rent)},
    # section C: household (no SSNs)
    {"acro": "NumFamily", "text": str(HH.size)},
    {"acro": "NumNonFamily", "text": "0"},
    {"acro": "NumDependents", "text": str(HH.dependents)},
    {"acro": "NumEligible", "text": str(HH.size)},
]
REL_CODE = {"Head": "H", "Child": "D"}
SEX = {"Marisol": "F", "Elias": "M", "Nora": "F"}
for i, mem in enumerate(HH.members, start=1):
    placements += [
        {"acro": f"LastName.{i}", "text": mem.last},
        {"acro": f"FirstName.{i}", "text": mem.first},
        {"acro": f"Relationship.{i}", "text": REL_CODE[mem.relationship]},
        {"acro": f"Sex.{i}", "text": SEX[mem.first]},
        {"acro": f"DOB.{i}", "text": mem.dob, "size": 7},
        {"acro": f"Citizenship.{i}", "text": "EC", "size": 7},
        {"acro": f"Age.{i}", "text": str(mem.age)},
    ]
placements += [
    # sections D and E: income and assets
    {"acro": "IncMbr.1", "text": "1"},
    {"acro": "IncTypeCode.1", "text": "W"},
    {"acro": "IncAmount.1", "text": num(WAGES)},
    {"acro": "AstMbr.1", "text": "1"},
    {"acro": "AstDescription.1", "text": "Savings account", "size": 8},
    {"acro": "AstStatus.1", "text": "C"},
    {"acro": "AstCashValue.1", "text": num(HH.assets_cash_value)},
    {"acro": "AstIncome.1", "text": num(HH.imputed_asset_income)},
    {"acro": "TotEmployment", "text": m(WAGES)},
    {"acro": "TotPension", "text": "0.00"},
    {"acro": "TotPublicAssist", "text": "0.00"},
    {"acro": "TotOtherIncome", "text": "0.00"},
    {"acro": "TotNonAssetIncome", "text": m(WAGES)},
    {"acro": "AssetCashValue", "text": m(HH.assets_cash_value)},
    {"acro": "ActualAssetIncome", "text": m(HH.imputed_asset_income)},
    {"acro": "AssetIncome", "text": m(HH.imputed_asset_income)},
    # section F: income limits and deductions; section G: rent calculation
    {"acro": "AnnualIncome", "text": m(HH.annual_income)},
    {"acro": "LowLimit", "text": m(LOW)},
    {"acro": "VLLimit", "text": m(VLOW)},
    {"acro": "XLLimit", "text": m(XLOW)},
    {"acro": "DependentDeduction", "text": m(DEP_DEDUCTION)},
    {"acro": "ChildCareWork", "text": m(HH.childcare_expense)},
    {"acro": "TotalDeductions", "text": m(TOTAL_DEDUCTIONS)},
    {"acro": "AdjustedIncome", "text": m(HH.adjusted_income)},
    {"acro": "TTP", "index": 1, "text": m(CERT.total_tenant_payment)},
    {"acro": "TenantRent", "index": 1, "text": m(CERT.tenant_rent)},
    {"acro": "UtilityReimbursement", "text": m(CERT.utility_reimbursement)},
    {"acro": "AssistancePayment", "index": 1, "text": m(CERT.assistance_payment)},
    {"acro": "Page2ofN", "text": "Page 2 of 2"},
]

# This form's widget boxes start underneath the printed labels; shift the
# page-2 values right so they don't overprint the label text.
DX = {
    "SubsidyType": 30, "iREMSPropertyID": 30, "ProjectNumber": 30, "ContractNumber": 30,
    "iMAXID": 30, "HUDOwned": 40,
    "EffectiveDate": 40, "VoucherDate": 40, "NextRecert": 40, "MoveInDate": 40,
    "TransactionType": 40, "EIVIndicator": 40,
    "NumFamily": 30, "NumNonFamily": 30, "NumDependents": 30, "NumEligible": 30,
    "TotEmployment": 10, "TotPension": 10, "TotPublicAssist": 10, "TotOtherIncome": 10, "TotNonAssetIncome": 10,
    "AssetCashValue": 12, "ActualAssetIncome": 12, "AssetIncome": 12,
    "AnnualIncome": 8, "LowLimit": 8, "VLLimit": 8, "XLLimit": 8,
    "DependentDeduction": 12, "ChildCareWork": 12, "TotalDeductions": 12, "AdjustedIncome": 12,
}
_PAGE2_INDEX = {"EffectiveDate": 1, "VoucherDate": 1, "TransactionType": 1}
for p in placements:
    name = p.get("acro")
    if name in DX and p.get("index", 0) == _PAGE2_INDEX.get(name, 0):
        p["dx"] = DX[name]
        if name in ("EffectiveDate", "VoucherDate", "NextRecert", "MoveInDate"):
            p["size"] = 8


def money(n):
    return {"value": f"${n:,}.00", "type": "money", "shown_as": m(n)}


SPEC = {
    "id": "hud_50059",
    "source": "hud_50059.pdf",
    "form": "HUD-50059 Owner's Certification of Compliance (06/2014 edition)",
    "program": "PBRA",
    "doc_type": "pbra_certification",
    "notes": ("Annual recertification. Same fictional project as the hud_52670 voucher sample. "
              "Continuation page 3 left blank (3-person household fits on page 2). "
              "Owner name printed in the owner/agent signature box. The form has no street address, "
              "so property_address is None."),
    "placements": placements,
    "lease_fields": {
        "tenant": HEAD,
        "landlord": OWNER,
        "rent_amount": f"${CERT.contract_rent:,}.00",
        "lease_start_date": None,
        "lease_end_date": None,
        "property_address": None,
        "security_deposit": f"${CERT.total_tenant_payment:,}.00",
    },
    "program_fields": {
        "project_name": {"value": PROJECT, "type": "text"},
        "owner_name": {"value": OWNER, "type": "text"},
        "head_of_household": {"value": HEAD, "type": "text"},
        "certification_type": {"value": "AR", "type": "text"},
        "effective_date": {"value": "11/01/2026", "type": "date"},
        "next_recert_date": {"value": "11/01/2027", "type": "date"},
        "move_in_date": {"value": "11/01/2019", "type": "date"},
        "unit_number": {"value": "3C", "type": "text"},
        "bedrooms": {"value": "2", "type": "int"},
        "rems_property_id": {"value": "800091733", "type": "text"},
        "project_number": {"value": "073-35412", "type": "text"},
        "contract_number": {"value": "IN36L991417", "type": "text"},
        "household_size": {"value": str(HH.size), "type": "int"},
        "dependents": {"value": str(HH.dependents), "type": "int"},
        "employment_income": money(WAGES),
        "asset_cash_value": money(HH.assets_cash_value),
        "asset_income": money(HH.imputed_asset_income),
        "annual_income": money(HH.annual_income),
        "low_income_limit": money(LOW),
        "very_low_income_limit": money(VLOW),
        "extremely_low_income_limit": money(XLOW),
        "dependent_deduction": money(DEP_DEDUCTION),
        "childcare_deduction": money(HH.childcare_expense),
        "total_deductions": money(TOTAL_DEDUCTIONS),
        "adjusted_income": money(HH.adjusted_income),
        "contract_rent": money(CERT.contract_rent),
        "utility_allowance": money(CERT.utility_allowance),
        "gross_rent": money(CERT.gross_rent),
        "total_tenant_payment": money(CERT.total_tenant_payment),
        "tenant_rent": money(CERT.tenant_rent),
        "utility_reimbursement": money(CERT.utility_reimbursement),
        "assistance_payment": money(CERT.assistance_payment),
        "security_deposit": money(CERT.total_tenant_payment),
        "tenant_signed_date": {"value": "10/18/2026", "type": "date"},
        "owner_signed_date": {"value": "10/20/2026", "type": "date"},
        # members 2-3: first and last names sit in separate cells on the form
        "member_2_first_name": {"value": "Elias", "type": "text"},
        "member_3_first_name": {"value": "Nora", "type": "text"},
        "member_2_dob": {"value": "07/02/2014", "type": "date"},
    },
}
