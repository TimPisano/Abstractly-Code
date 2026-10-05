"""
Record types for the three HUD datasets.

Household-size keyed values use dicts {1: amount, ..., 8: amount};
bedroom-keyed values use {0: studio, 1: one-bedroom, ..., 4}. Amounts
are whole dollars (HUD publishes integers). Every record carries the
effective year and date it was loaded under, so a caller can always
say which year's limits a figure came from.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Dict, Optional

DATASET_INCOME_LIMITS = "il"
DATASET_FMR = "fmr"
DATASET_MTSP = "mtsp"
DATASETS = (DATASET_INCOME_LIMITS, DATASET_FMR, DATASET_MTSP)

DATASET_LABELS = {
    DATASET_INCOME_LIMITS: "Section 8 income limits",
    DATASET_FMR: "Fair Market Rents",
    DATASET_MTSP: "MTSP (LIHTC) income limits",
}


@dataclass(frozen=True)
class AreaInfo:
    area_code: str            # 10-digit HUD FIPS (state+county+subdivision)
    hud_area_code: str = ""   # e.g. METRO47900M47900 — shared by several counties
    hud_area_name: str = ""
    state: str = ""           # 2-letter postal code
    county_name: str = ""


@dataclass(frozen=True)
class IncomeLimits:
    area: AreaInfo
    effective_year: int
    effective_date: date
    median_income: Optional[int]
    extremely_low: Dict[int, int]   # 30% AMI (ELI)
    very_low: Dict[int, int]        # 50% AMI
    low: Dict[int, int]             # 80% AMI

    def to_dict(self) -> dict:
        return _to_dict(self)


@dataclass(frozen=True)
class FairMarketRents:
    area: AreaInfo
    effective_year: int
    effective_date: date
    by_bedrooms: Dict[int, int]

    def to_dict(self) -> dict:
        return _to_dict(self)


@dataclass(frozen=True)
class LihtcLimits:
    """MTSP income limits, which are the LIHTC (and bond deal) limits."""
    area: AreaInfo
    effective_year: int
    effective_date: date
    median_income: Optional[int]
    limit_50: Dict[int, int]
    limit_60: Dict[int, int]

    def to_dict(self) -> dict:
        return _to_dict(self)


def _to_dict(record) -> dict:
    out = asdict(record)
    out["effective_date"] = record.effective_date.isoformat()
    return out


@dataclass
class ParsedDataset:
    """What a parser hands the store: one effective year's rows."""
    dataset: str
    rows: list = field(default_factory=list)   # list of (AreaInfo, payload dict)
