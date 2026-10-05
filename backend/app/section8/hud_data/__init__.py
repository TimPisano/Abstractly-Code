"""
HUD reference data for Section 8 / LIHTC checks: income limits, Fair
Market Rents, and MTSP (LIHTC) income limits, by area and effective
year. Behind SECTION8_HUD_DATA_ENABLED (default off): the lookups,
refresh(), and the CLI raise HudDataDisabled while it's off. The
lihtc_* helpers are pure math on a record a lookup already returned,
so they need no gate of their own.

Load data:   python -m app.section8.hud_data refresh --dataset il --year 2025 --file ...
Look it up:  lookup_income_limits("0603799999", as_of=date(2025, 6, 1))

Not wired into any route yet. Plan: docs/plans/feature-s8-hud-data.md.
"""
from .config import HudDataDisabled, is_enabled
from .lookup import (
    AIT_LEVELS,
    HudDataNotFound,
    lihtc_income_limit,
    lihtc_rent_limit,
    lookup,
    lookup_fmr,
    lookup_income_limits,
    lookup_lihtc_limits,
)
from .models import FairMarketRents, IncomeLimits, LihtcLimits
from .parsers import HudDataParseError
from .loader import HudRefreshError, refresh

__all__ = [
    "AIT_LEVELS",
    "FairMarketRents",
    "HudDataDisabled",
    "HudDataNotFound",
    "HudDataParseError",
    "HudRefreshError",
    "IncomeLimits",
    "LihtcLimits",
    "is_enabled",
    "lihtc_income_limit",
    "lihtc_rent_limit",
    "lookup",
    "lookup_fmr",
    "lookup_income_limits",
    "lookup_lihtc_limits",
    "refresh",
]
