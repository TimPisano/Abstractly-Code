"""
Fictional, internally consistent values for the affordable-housing eval samples.

Everything here is made up: people, owners, PHAs, addresses, contract and
building numbers, and the area income limits. Nothing is a real person or a
real HUD/HFA figure. Names follow the repo's Maple Ridge fixture convention.

The arithmetic follows the published rule shapes so the samples are
internally consistent (an answer key never contradicts itself):

  HCV (24 CFR 982):   TTP = max(30% adjusted monthly, 10% gross monthly, min rent)
                      HAP = min(payment standard, gross rent) - TTP
  PBRA (4350.3 Ex 3-12): HAP = gross rent - TTP; tenant rent = TTP - UA,
                      or a utility reimbursement of UA - TTP when UA > TTP
  LIHTC (IRC 42):     max gross rent = 30% x income limit at 1.5 persons per
                      bedroom / 12; gross rent = tenant rent + UA

The deduction amounts and the area limits are illustrative, not current
HUD figures. Don't reuse them as rules.
"""

import math
from dataclasses import dataclass
from typing import List

# -- fictional area: "Maple Ridge County" ------------------------------------
# 4-person median family income for the fictional area. The per-size
# adjustments are HUD's standard shape (1p 70% ... 8p 132%).
AREA_NAME = "Maple Ridge County"
MFI_4P = 98_000
SIZE_ADJ = {1: 0.70, 2: 0.80, 3: 0.90, 4: 1.00, 5: 1.08, 6: 1.16, 7: 1.24, 8: 1.32}

DEPENDENT_DEDUCTION = 500        # illustrative
ELDERLY_DISABLED_DEDUCTION = 550  # illustrative


def income_limit(household_size: int, ami_pct: int) -> int:
    """Fictional MTSP-style limit, rounded up to the next $50 like HUD tables."""
    raw = MFI_4P * ami_pct / 100 * SIZE_ADJ[household_size]
    return int(math.ceil(raw / 50.0) * 50)


def lihtc_max_gross_rent(bedrooms: int, ami_pct: int) -> int:
    """30% of the limit at the imputed size (1.5 persons per bedroom; 0BR = 1), monthly, rounded down."""
    persons = 1.0 if bedrooms == 0 else 1.5 * bedrooms
    lo, hi = math.floor(persons), math.ceil(persons)
    limit = (income_limit(lo, ami_pct) + income_limit(hi, ami_pct)) / 2
    return int(math.floor(limit * 0.30 / 12))


@dataclass
class Member:
    first: str
    last: str
    relationship: str          # "Head", "Spouse", "Child", "Other adult"
    age: int
    dob: str                   # fictional
    annual_wages: int = 0
    annual_benefits: int = 0   # SS / SSI / pension
    student: bool = False
    disabled: bool = False

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}"


@dataclass
class Household:
    members: List[Member]
    assets_cash_value: int = 0
    imputed_asset_income: int = 0
    childcare_expense: int = 0
    medical_expense: int = 0

    @property
    def head(self) -> Member:
        return self.members[0]

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def annual_income(self) -> int:
        return sum(m.annual_wages + m.annual_benefits for m in self.members) + self.imputed_asset_income

    @property
    def dependents(self) -> int:
        return sum(1 for m in self.members if m.relationship == "Child" and (m.age < 18 or m.student))

    @property
    def elderly_or_disabled_household(self) -> bool:
        return any(m.age >= 62 or m.disabled for m in self.members if m.relationship in ("Head", "Spouse"))

    @property
    def adjusted_income(self) -> int:
        adj = self.annual_income - DEPENDENT_DEDUCTION * self.dependents - self.childcare_expense
        if self.elderly_or_disabled_household:
            adj -= ELDERLY_DISABLED_DEDUCTION
        return max(adj, 0)


def ttp(hh: Household, min_rent: int) -> int:
    return int(round(max(0.30 * hh.adjusted_income / 12, 0.10 * hh.annual_income / 12, min_rent)))


@dataclass
class VoucherTenancy:
    """HCV: the PHA's numbers for one unit."""
    hh: Household
    contract_rent: int
    utility_allowance: int
    payment_standard: int
    min_rent: int = 50

    @property
    def gross_rent(self) -> int:
        return self.contract_rent + self.utility_allowance

    @property
    def total_tenant_payment(self) -> int:
        return ttp(self.hh, self.min_rent)

    @property
    def hap(self) -> int:
        return max(min(self.payment_standard, self.gross_rent) - self.total_tenant_payment, 0)

    @property
    def tenant_rent_to_owner(self) -> int:
        return self.contract_rent - self.hap


@dataclass
class PbraCert:
    """PBRA 50059-style numbers for one unit."""
    hh: Household
    contract_rent: int
    utility_allowance: int
    min_rent: int = 25

    @property
    def gross_rent(self) -> int:
        return self.contract_rent + self.utility_allowance

    @property
    def total_tenant_payment(self) -> int:
        return ttp(self.hh, self.min_rent)

    @property
    def assistance_payment(self) -> int:
        return max(self.gross_rent - self.total_tenant_payment, 0)

    @property
    def tenant_rent(self) -> int:
        return max(self.total_tenant_payment - self.utility_allowance, 0)

    @property
    def utility_reimbursement(self) -> int:
        return max(self.utility_allowance - self.total_tenant_payment, 0)


@dataclass
class LihtcCert:
    """TIC numbers for one unit."""
    hh: Household
    bedrooms: int
    ami_pct: int
    utility_allowance: int
    other_charges: int = 0
    rent_below_max: int = 15        # owners usually set rent a little under the cap
    section8_assistance: int = 0

    @property
    def income_limit(self) -> int:
        return income_limit(self.hh.size, self.ami_pct)

    @property
    def max_gross_rent(self) -> int:
        return lihtc_max_gross_rent(self.bedrooms, self.ami_pct)

    @property
    def tenant_paid_rent(self) -> int:
        return self.max_gross_rent - self.utility_allowance - self.other_charges - self.rent_below_max

    @property
    def gross_rent(self) -> int:
        return self.tenant_paid_rent + self.utility_allowance + self.other_charges

    def check(self) -> None:
        assert self.hh.annual_income <= self.income_limit, "household over the income limit"
        assert self.gross_rent <= self.max_gross_rent, "gross rent over the cap"


def money(n: int, cents: bool = False) -> str:
    return f"${n:,.2f}" if cents else f"${n:,}"


def num(n: int) -> str:
    return f"{n:,}"
