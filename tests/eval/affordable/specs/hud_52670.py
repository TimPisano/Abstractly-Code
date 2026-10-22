"""HUD-52670 Housing Owner's Certification and Application for HAP (05/2014 edition). PBRA monthly voucher. AcroForm.

Same fictional project as the hud_50059 sample (Oakmont Terrace, 48 units).
Counts satisfy the form's own rule (6a = 6b + 6c + 6d + 6e) and the total
(10f) is the sum of the lines above it. Exceptions (Part II item 7) are left
blank: they only apply to contracts effective on or after 10/1/81.
"""

PROJECT = "Oakmont Terrace"
AGENT = "Oakmont Property Management LLC"

TOTAL_UNITS, SUBSIDIZED, ABATED, VACANT, MARKET = 48, 45, 0, 2, 1
assert TOTAL_UNITS == SUBSIDIZED + ABATED + VACANT + MARKET

REGULAR_COUNT, REGULAR_AMOUNT = SUBSIDIZED, 31_486
ADJ_COUNT, ADJ_AMOUNT = 2, 412
VACANCY_COUNT, VACANCY_AMOUNT = 1, 1_104
MISC_AMOUNT, REPAY_AMOUNT = 0, 0
TOTAL = REGULAR_AMOUNT + ADJ_AMOUNT + VACANCY_AMOUNT + MISC_AMOUNT + REPAY_AMOUNT


def m(n):
    return f"{n:,}.00"


def money(n):
    return {"value": f"${n:,}.00", "type": "money", "shown_as": m(n)}


SPEC = {
    "id": "hud_52670",
    "source": "hud_52670.pdf",
    "form": "HUD-52670 Housing Owner's Certification & Application for Housing Assistance Payments (05/2014)",
    "program": "PBRA",
    "doc_type": "pbra_voucher",
    "notes": ("December 2026 voucher for the fictional 48-unit Oakmont Terrace (same project as hud_50059). "
              "No tenant, owner, unit rent or address on this form, so every lease field is None."),
    "placements": [
        {"acro": "ProjectName", "text": PROJECT},
        {"acro": "ProjectNumber", "text": "073-35412"},
        {"acro": "ContractNumber", "text": "IN36L991417"},
        {"acro": "SubsidyType", "text": "Section 8"},
        {"acro": "ManagementAgentName", "text": AGENT},
        {"acro": "ContractCount6a", "text": str(TOTAL_UNITS)},
        {"acro": "SubsidyCount6b", "text": str(SUBSIDIZED)},
        {"acro": "AbatedCount6c", "text": str(ABATED)},
        {"acro": "VacantCount6d", "text": str(VACANT)},
        {"acro": "MarketCount6e", "text": str(MARKET)},
        {"acro": "VoucherMonth", "text": "12/2026", "size": 8},
        {"acro": "RegularCount9a", "text": str(REGULAR_COUNT)},
        {"acro": "RegularAmount10a", "text": m(REGULAR_AMOUNT)},
        {"acro": "AdjustmentCount9b", "text": str(ADJ_COUNT)},
        {"acro": "AdjustmentAmount10b", "text": m(ADJ_AMOUNT)},
        {"acro": "SCVacancy9c3", "text": str(VACANCY_COUNT)},
        {"acro": "SCVacancyAmount10c3", "text": m(VACANCY_AMOUNT)},
        {"acro": "MiscAcctRqstAmount10d", "text": m(MISC_AMOUNT)},
        {"acro": "RepAgrAmount10e", "text": m(REPAY_AMOUNT)},
        {"acro": "TotalAmount10f", "text": m(TOTAL)},
        # signature box (widget spans top 680-738); printed name/title/phone, then date
        {"at": (313, 688), "page": 1, "text": "Dana Kessler-Moore, Compliance Manager, (317) 555-0164", "size": 8},
        {"at": (313, 700), "page": 1, "text": "12/10/2026", "size": 8},
    ],
    "lease_fields": {
        "tenant": None,
        "landlord": None,
        "rent_amount": None,
        "lease_start_date": None,
        "lease_end_date": None,
        "property_address": None,
        "security_deposit": None,
    },
    "program_fields": {
        "project_name": {"value": PROJECT, "type": "text"},
        "project_number": {"value": "073-35412", "type": "text"},
        "contract_number": {"value": "IN36L991417", "type": "text"},
        "subsidy_type": {"value": "Section 8", "type": "text"},
        "management_agent": {"value": AGENT, "type": "text"},
        "total_units": {"value": str(TOTAL_UNITS), "type": "int"},
        "units_subsidized": {"value": str(SUBSIDIZED), "type": "int"},
        "units_abated": {"value": str(ABATED), "type": "int"},
        "units_vacant": {"value": str(VACANT), "type": "int"},
        "units_market": {"value": str(MARKET), "type": "int"},
        "voucher_month": {"value": "12/2026", "type": "text"},
        "regular_units_billed": {"value": str(REGULAR_COUNT), "type": "int"},
        "regular_assistance": money(REGULAR_AMOUNT),
        "adjustment_units": {"value": str(ADJ_COUNT), "type": "int"},
        "adjustment_amount": money(ADJ_AMOUNT),
        "vacancy_claim_units": {"value": str(VACANCY_COUNT), "type": "int"},
        "vacancy_claim_amount": money(VACANCY_AMOUNT),
        "total_requested": money(TOTAL),
        "signer_date": {"value": "12/10/2026", "type": "date"},
    },
}
