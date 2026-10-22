"""
Project-based Section 8 (PBRA) owner forms:

  HUD-50059  Owner's Certification of Compliance with HUD's Tenant
             Eligibility and Rent Procedures  -- 06/2014 edition
  HUD-52670  Housing Owner's Certification and Application for Housing
             Assistance Payments (monthly voucher) -- 05/2014 edition

Both ship as fillable PDFs, so every rule maps the form's own field name
first. The layout boxes were derived from the blank forms: each box is the
fillable widget's rectangle measured relative to its printed label, with a
few points of slack. On the 50059's dense Section B/F grids (9pt row
pitch) boxes are kept to +/-4.2pt around the widget's centre so a value
never bleeds into the next row.

Page 1 of the 50059 repeats the key figures from page 2 (project, effective
date, certification type, TTP, HAP, tenant rent, unit); those are listed as
second anchors so a value is still found if page 2 is hard to read.
"""

from .base import Anchor, FormSpec, Rule


def _r(name, vtype, acro, *anchors, canonical=None):
    return Rule(name, vtype, acro=(rf"^{acro}$",) if acro else (), anchors=anchors, canonical=canonical)


# ---------------------------------------------------------------------------
# HUD-50059
# ---------------------------------------------------------------------------

P1_BELOW_WIDE = (0.3, 4.5, 292.1, 25.5)       # page-1 summary: full-width cells under a label
P1_BELOW_COL = (-9.8, 4.5, 86.2, 25.5)        # page-1 summary: 86pt cells under a label

HUD_50059 = FormSpec(
    id="hud_50059",
    name="HUD-50059 Owner's Certification of Compliance",
    doc_kind="pbra_certification",
    program="PBRA",
    detect=(("Owner's Certification of Compliance", 1.5), ("HUD's Tenant Eligibility and Rent Procedures", 1.5),
            ("HUD-50059", 2.0)),
    acro_signature=(r"^iREMSPropertyID$", r"^TTPAtRADConversion$"),
    rules=(
        _r("project_name", "text", "ProjectName",
           Anchor("1. Project Name", (-14.5, 7.7, 188.8, 16.7), origin="x0", page=2),
           Anchor("Name of Project", P1_BELOW_WIDE, origin="x0", page=1), canonical="project_name"),
        Rule("owner_name", "text", strip=(r"^\W+",),
             anchors=(Anchor("Owner/Agent", (-6.0, 5.7, 400.0, 25.7), origin="x0", page=1, occurrence=2),),
             canonical="owner_name"),
        _r("head_of_household", "text", "HeadOfHousehold",
           Anchor("Head of Household", P1_BELOW_WIDE, origin="x0", page=1, occurrence=1),
           canonical="head_of_household"),
        _r("certification_type", "text", "TransactionType",
           Anchor("16. Certification Type", (7.9, 0.5, 105.7, 8.9), page=2),
           Anchor("Certification Type", P1_BELOW_COL, origin="x0", page=1)),
        _r("effective_date", "date", "EffectiveDate",
           Anchor("12. Effective Date", (19.9, 0.0, 117.7, 8.4), page=2),
           Anchor("Effective Date", P1_BELOW_COL, origin="x0", page=1), canonical="effective_date"),
        _r("next_recert_date", "date", "NextRecert",
           Anchor("14. Next Recertification Date", (-18.9, 0.3, 78.9, 8.7), page=2), canonical="next_recert_date"),
        _r("move_in_date", "date", "MoveInDate",
           Anchor("15. Project Move-In Date", (-5.5, 0.2, 92.2, 8.6), page=2), canonical="move_in_date"),
        _r("unit_number", "text", "UnitNumber",
           Anchor("21. Unit Number", (19.4, 0.4, 122.3, 8.8), page=2),
           Anchor("Unit Number", P1_BELOW_WIDE, origin="x0", page=1), canonical="unit_number"),
        _r("bedrooms", "int", "NumBedrooms",
           Anchor("22. No. of Bedrooms", (4.3, 0.5, 107.2, 8.9), page=2),
           # OCR often garbles this tiny label; the row under "21. Unit Number" is the same widget column
           Anchor("21. Unit Number", (19.4, 9.4, 122.3, 17.8), page=2), canonical="bedrooms"),
        _r("rems_property_id", "text", "iREMSPropertyID",
           Anchor("4. Property ID", (1.1, 0.5, 134.5, 8.9), page=2)),
        _r("project_number", "text", "ProjectNumber",
           Anchor("5. Project Number", (-14.0, 0.6, 119.4, 9.0), page=2)),
        _r("contract_number", "text", "ContractNumber",
           Anchor("6. Contract Number", (-19.3, 0.7, 114.0, 9.1), page=2), canonical="contract_number"),
        _r("household_size", "int", "NumFamily",
           Anchor("53. Number of Family Members", (-2.8, -0.4, 56.6, 8.0), page=2),
           Anchor("56. Number of Eligible Members", (-5.1, -27.2, 54.3, -18.8), page=2), canonical="household_size"),
        _r("dependents", "int", "NumDependents",
           Anchor("55. Number of Dependents", (13.3, -0.1, 72.7, 8.3), page=2),
           Anchor("56. Number of Eligible Members", (-5.1, -9.0, 54.3, -0.6), page=2)),
        _r("member_2_first_name", "text", r"FirstName\.2",
           Anchor("First Name", (-26.8, 26.5, 67.7, 34.9), origin="x0", page=2)),
        _r("member_3_first_name", "text", r"FirstName\.3",
           Anchor("First Name", (-26.8, 35.5, 67.7, 43.9), origin="x0", page=2)),
        _r("employment_income", "money", "TotEmployment",
           Anchor("70. Total Employment Income", (7.9, 0.4, 88.3, 8.8), page=2)),
        _r("asset_cash_value", "money", "AssetCashValue",
           Anchor("81. Total Cash Value of Assets", (-4.0, 0.4, 76.4, 8.8), page=2)),
        _r("asset_income", "money", "AssetIncome",
           Anchor("85. Asset Income", (42.2, -0.8, 122.5, 7.6), page=2)),
        _r("annual_income", "money", "AnnualIncome",
           Anchor("86. Total Annual Income", (21.0, -0.7, 101.4, 7.7), page=2), canonical="annual_income"),
        _r("low_income_limit", "money", "LowLimit",
           Anchor("87. Low Income Limit", (30.7, -0.7, 111.1, 7.7), page=2)),
        _r("very_low_income_limit", "money", "VLLimit",
           Anchor("88. Very Low Income Limit", (12.5, -0.7, 92.9, 7.7), page=2)),
        _r("extremely_low_income_limit", "money", "XLLimit",
           Anchor("89. Extremely Low Income Limit", (-7.1, -0.6, 73.3, 7.8), page=2)),
        _r("dependent_deduction", "money", "DependentDeduction",
           Anchor("97. Deduction for Dependents", (-2.8, -0.7, 77.6, 7.7), page=2)),
        _r("childcare_deduction", "money", "ChildCareWork",
           Anchor("98. Child Care Expense (work)", (-5.5, -0.7, 74.8, 7.7), page=2)),
        _r("total_deductions", "money", "TotalDeductions",
           Anchor("106. Total Deductions", (31.0, -0.4, 111.4, 8.0), page=2)),
        _r("adjusted_income", "money", "AdjustedIncome",
           Anchor("107. Adjusted Annual Income", (3.8, -0.4, 84.1, 8.0), page=2), canonical="adjusted_income"),
        _r("contract_rent", "money", "ContractRent",
           Anchor("29. Contract Rent", (15.0, 1.2, 117.9, 9.6), page=2), canonical="contract_rent"),
        _r("utility_allowance", "money", "UtilityAllowance",
           Anchor("30. Utility Allowance", (6.5, 1.3, 109.4, 9.7), page=2), canonical="utility_allowance"),
        _r("gross_rent", "money", "GrossRent",
           Anchor("31. Gross Rent", (23.9, 1.4, 126.8, 9.8), page=2), canonical="gross_rent"),
        _r("total_tenant_payment", "money", "TTP",
           Anchor("108. Total Tenant Payment", (14.8, -0.7, 95.2, 7.7), page=2),
           Anchor("Total Tenant Payment", P1_BELOW_COL, origin="x0", page=1), canonical="total_tenant_payment"),
        _r("tenant_rent", "money", "TenantRent",
           Anchor("110. Tenant Rent", (48.4, -0.7, 128.8, 7.7), page=2),
           Anchor("Tenant Rent", P1_BELOW_COL, origin="x0", page=1), canonical="tenant_rent"),
        _r("utility_reimbursement", "money", "UtilityReimbursement",
           Anchor("111. Utility Reimbursement", (13.3, -0.6, 93.7, 7.8), page=2), canonical="utility_reimbursement"),
        _r("assistance_payment", "money", "AssistancePayment",
           Anchor("112. Assistance Payment", (19.2, -0.6, 99.5, 7.8), page=2),
           Anchor("Assistance Payment", P1_BELOW_COL, origin="x0", page=1, occurrence=2), canonical="hap"),
        _r("security_deposit", "money", "SecurityDeposit",
           Anchor("26. Security Deposit", (6.1, 0.9, 109.0, 9.3), page=2), canonical="security_deposit"),
        _r("tenant_signed_date", "date", "TenantSigned",
           Anchor("Head of Household", (181.2, 4.9, 277.9, 23.7), origin="x0", page=1, occurrence=2)),
        _r("owner_signed_date", "date", "OwnerSigned",
           Anchor("Owner/Agent", (458.8, 4.9, 555.5, 23.7), origin="x0", page=1, occurrence=2)),
    ),
    lease_map={
        "tenant": "head_of_household",
        "landlord": "owner_name",
        "rent_amount": "contract_rent",
        "security_deposit": "security_deposit",
    },
    notes="Contract rent (not tenant rent) is the unit's rent for lease purposes, as on Section 8 leases.",
)


# ---------------------------------------------------------------------------
# HUD-52670 (monthly voucher)
# ---------------------------------------------------------------------------

REGULAR = "a. Regular Tenant Assistance Payments for (mo./yr.):"
ADJUST = "b. Adjustments to Regular Tenant Assistance Payments"
VACANCY = "iii. Section 8 Special Claims for Vacancies"

HUD_52670 = FormSpec(
    id="hud_52670",
    name="HUD-52670 Housing Owner's Certification and Application for HAP (monthly voucher)",
    doc_kind="pbra_voucher",
    program="PBRA",
    detect=(("Housing Owner's Certification", 1.0), ("Application for Housing", 0.5),
            ("Breakdown of Assistance Payment Requested", 1.0), ("HUD-52670", 2.0)),
    acro_signature=(r"^RegularAmount10a$", r"^TotalAmount10f$"),
    rules=(
        _r("project_name", "text", "ProjectName",
           Anchor("1. Project Name:", (-9.1, 10.2, 236.0, 29.3), origin="x0", page=1), canonical="project_name"),
        _r("project_number", "text", "ProjectNumber",
           Anchor("2. FHA/EH/Non-Insured No.", (-5.5, 10.2, 116.0, 29.3), origin="x0", page=1)),
        _r("contract_number", "text", "ContractNumber",
           Anchor("3. Sec. 8/PAC/PRAC/Contract No.", (-7.0, 10.2, 141.0, 29.3), origin="x0", page=1),
           canonical="contract_number"),
        _r("subsidy_type", "text", "SubsidyType",
           Anchor("4. Type of Subsidy:", (-9.1, 11.7, 121.0, 30.8), origin="x0", page=1)),
        _r("management_agent", "text", "ManagementAgentName",
           Anchor("5a. Management Agent's Name:", (-7.9, 11.6, 368.2, 30.7), origin="x0", page=1)),
        _r("total_units", "int", "ContractCount6a",
           Anchor("a. Total Units in contract", (121.6, -0.9, 189.6, 13.1), page=1)),
        # 6b-6e labels all end "... under this contract", so on a scan a fuzzy match on the
        # full label can land on the neighbouring row; the distinctive words go first.
        _r("units_subsidized", "int", "SubsidyCount6b",
           Anchor("Units receiving subsidy", (78.5, -1.0, 146.6, 13.0), page=1),
           Anchor("b. Number of Units receiving subsidy under this contract", (12.2, -1.0, 80.2, 13.0), page=1)),
        _r("units_abated", "int", "AbatedCount6c",
           Anchor("units abated", (115.9, -1.2, 183.9, 12.8), page=1),
           Anchor("c. Number of units abated under this contract", (49.4, -1.2, 117.4, 12.8), page=1)),
        _r("units_vacant", "int", "VacantCount6d",
           Anchor("Units vacant", (115.4, -1.3, 183.4, 12.7), page=1),
           Anchor("d. Number of Units vacant under this contract", (48.9, -1.3, 116.9, 12.7), page=1)),
        _r("units_market", "int", "MarketCount6e",
           Anchor("Market Rent Tenants", (50.6, -1.4, 118.6, 12.6), page=1)),
        _r("voucher_month", "text", "VoucherMonth",
           Anchor(REGULAR, (39.6, -3.9, 94.5, 10.1), page=1)),
        _r("regular_units_billed", "int", "RegularCount9a",
           Anchor(REGULAR, (93.6, -3.9, 155.6, 10.1), page=1)),
        _r("regular_assistance", "money", "RegularAmount10a",
           Anchor(REGULAR, (156.4, -3.9, 241.1, 10.1), page=1), canonical="hap_total"),
        _r("adjustment_units", "int", "AdjustmentCount9b",
           Anchor(ADJUST, (84.2, -3.6, 146.2, 10.4), page=1)),
        _r("adjustment_amount", "money", "AdjustmentAmount10b",
           Anchor(ADJUST, (147.1, -3.6, 231.7, 10.4), page=1)),
        _r("vacancy_claim_units", "int", "SCVacancy9c3",
           Anchor(VACANCY, (118.8, -2.8, 180.8, 11.2), page=1)),
        _r("vacancy_claim_amount", "money", "SCVacancyAmount10c3",
           Anchor(VACANCY, (181.6, -2.8, 266.3, 11.2), page=1)),
        _r("total_requested", "money", "TotalAmount10f",
           Anchor("f. Total Subsidy Authorized under instructions in Handbook 4350.3 Rev. 1",
                  (82.0, -1.3, 169.7, 12.7), page=1), canonical="voucher_total"),
        _r("signer_date", "date", "SignerInfo",
           Anchor("Printed Name, Date, Title & Phone No.", (-3.7, 10.6, 282.3, 74.2), origin="x0", page=1)),
    ),
    lease_map={},   # property-level form: no single tenancy
)

FORMS = [HUD_50059, HUD_52670]
