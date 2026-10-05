"""
Read side: which limits apply to an area for a given year or date.

Every lookup picks an effective year one of three ways:
  year=2025         exactly that year's limits;
  as_of=date(...)   the newest loaded year already in effect on that date
                    (e.g. FMR FY2026 took effect 2025-10-01, so a
                    2025-11-15 lease gets FY2026 FMRs);
  neither           the newest year loaded.
If the chosen year has no row for the area, the lookup fails rather than
falling back to an older year — a stale limit presented as current is
the exact compliance error this data exists to prevent.
"""
from __future__ import annotations

import math
from datetime import date
from fractions import Fraction
from typing import Optional, Tuple

from . import config, store
from .models import (
    DATASET_FMR,
    DATASET_INCOME_LIMITS,
    DATASET_LABELS,
    DATASET_MTSP,
    DATASETS,
    FairMarketRents,
    IncomeLimits,
    LihtcLimits,
)
from .parsers import HudDataParseError, normalize_area_code


class HudDataNotFound(LookupError):
    pass


def lookup_income_limits(area_code, year: Optional[int] = None, as_of: Optional[date] = None) -> IncomeLimits:
    area, eff_year, eff_date, p = _lookup(DATASET_INCOME_LIMITS, area_code, year, as_of)
    return IncomeLimits(
        area=area, effective_year=eff_year, effective_date=eff_date,
        median_income=p.get("median_income"),
        extremely_low=_int_keys(p["extremely_low"]),
        very_low=_int_keys(p["very_low"]),
        low=_int_keys(p["low"]),
    )


def lookup_fmr(area_code, year: Optional[int] = None, as_of: Optional[date] = None) -> FairMarketRents:
    area, eff_year, eff_date, p = _lookup(DATASET_FMR, area_code, year, as_of)
    return FairMarketRents(
        area=area, effective_year=eff_year, effective_date=eff_date,
        by_bedrooms=_int_keys(p["by_bedrooms"]),
    )


def lookup_lihtc_limits(area_code, year: Optional[int] = None, as_of: Optional[date] = None) -> LihtcLimits:
    area, eff_year, eff_date, p = _lookup(DATASET_MTSP, area_code, year, as_of)
    return LihtcLimits(
        area=area, effective_year=eff_year, effective_date=eff_date,
        median_income=p.get("median_income"),
        limit_50=_int_keys(p["limit_50"]),
        limit_60=_int_keys(p["limit_60"]),
    )


def lookup(dataset: str, area_code, year: Optional[int] = None, as_of: Optional[date] = None):
    """Generic entry point: dataset is 'il', 'fmr', or 'mtsp'."""
    fn = {
        DATASET_INCOME_LIMITS: lookup_income_limits,
        DATASET_FMR: lookup_fmr,
        DATASET_MTSP: lookup_lihtc_limits,
    }.get(dataset)
    if fn is None:
        raise ValueError(f"Unknown dataset {dataset!r}; expected one of {', '.join(DATASETS)}")
    return fn(area_code, year=year, as_of=as_of)


# ------------------------------------------------------- LIHTC derivations

AIT_LEVELS = (20, 30, 40, 50, 60, 70, 80)


def lihtc_income_limit(limits: LihtcLimits, household_size: int, ami_pct: int) -> int:
    """
    Income limit for a household at an AMI designation. 50% and 60% are
    HUD's published figures; the other Average Income Test levels
    (20–80%) are the 50% limit scaled by ami_pct/50, to the nearest
    dollar. State agency charts may round differently — confirm.
    """
    if household_size not in limits.limit_50:
        raise ValueError(f"household_size must be 1-8, got {household_size}")
    if ami_pct == 50:
        return limits.limit_50[household_size]
    if ami_pct == 60:
        return limits.limit_60[household_size]
    if ami_pct not in AIT_LEVELS:
        raise ValueError(f"ami_pct must be one of {AIT_LEVELS}, got {ami_pct}")
    return int(_round_half_up(Fraction(limits.limit_50[household_size] * ami_pct, 50)))


def lihtc_rent_limit(limits: LihtcLimits, bedrooms: int, ami_pct: int) -> int:
    """
    Maximum monthly *gross* rent (tenant rent plus utility allowance) for
    a unit under IRC §42(g)(2): 30% of the income limit for the imputed
    household size — 1 person for a studio, 1.5 per bedroom otherwise —
    divided by 12, rounded down to the dollar. A fractional size (1.5,
    4.5) uses the average of the two neighbouring sizes' limits.
    """
    if not 0 <= bedrooms <= 5:
        raise ValueError(f"bedrooms must be 0-5, got {bedrooms}")
    imputed = Fraction(1) if bedrooms == 0 else Fraction(3, 2) * bedrooms
    low, high = math.floor(imputed), math.ceil(imputed)
    income = (_exact_income(limits, low, ami_pct) + _exact_income(limits, high, ami_pct)) / 2
    return math.floor(income * Fraction(3, 10) / 12)


def _exact_income(limits: LihtcLimits, size: int, ami_pct: int) -> Fraction:
    if ami_pct in (50, 60):
        return Fraction(lihtc_income_limit(limits, size, ami_pct))
    if ami_pct not in AIT_LEVELS:
        raise ValueError(f"ami_pct must be one of {AIT_LEVELS}, got {ami_pct}")
    return Fraction(limits.limit_50[size] * ami_pct, 50)


def _round_half_up(value: Fraction) -> int:
    return math.floor(value + Fraction(1, 2))


# --------------------------------------------------------------- internals

def _lookup(dataset: str, area_code, year: Optional[int], as_of: Optional[date]):
    config.require_enabled()
    if year is not None and as_of is not None:
        raise ValueError("Pass year or as_of, not both")
    try:
        code = normalize_area_code(area_code)
    except HudDataParseError:
        # Not a FIPS code — may be a HUD area code like METRO47900M47900.
        code = str(area_code).strip().upper()

    eff_year, eff_date = _resolve_year(dataset, year, as_of)
    found = store.fetch_row(dataset, eff_year, code)
    if found is None:
        raise HudDataNotFound(
            f"No {DATASET_LABELS[dataset]} for area {code} in effective year {eff_year}"
        )
    area, payload = found
    return area, eff_year, eff_date, payload


def _resolve_year(dataset: str, year: Optional[int], as_of: Optional[date]) -> Tuple[int, date]:
    versions = [
        (v["effective_year"], date.fromisoformat(v["effective_date"]))
        for v in store.current_versions(dataset)
    ]
    label = DATASET_LABELS[dataset]
    if not versions:
        raise HudDataNotFound(f"No {label} loaded. Run the refresh command first.")
    if year is not None:
        for v_year, v_date in versions:
            if v_year == year:
                return v_year, v_date
        raise HudDataNotFound(f"No {label} loaded for effective year {year}")
    if as_of is not None:
        in_effect = [v for v in versions if v[1] <= as_of]
        if not in_effect:
            raise HudDataNotFound(f"No {label} loaded that were in effect on {as_of.isoformat()}")
        return max(in_effect, key=lambda v: v[1])
    return max(versions, key=lambda v: v[0])


def _int_keys(d: dict) -> dict:
    # JSON object keys are strings; household sizes and bedroom counts are ints.
    return {int(k): v for k, v in d.items()}
