"""
Command line for the HUD store. Run from backend/:

  python -m app.section8.hud_data refresh --dataset il --year 2025 --file Section8-FY25.xlsx
  python -m app.section8.hud_data refresh --dataset fmr --year 2026 --url https://www.huduser.gov/...
  python -m app.section8.hud_data status

Requires SECTION8_HUD_DATA_ENABLED=1.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import List, Optional

from . import store
from .config import HudDataDisabled
from .loader import HudRefreshError, refresh
from .models import DATASET_LABELS, DATASETS
from .parsers import HudDataParseError


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.section8.hud_data")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("refresh", help="Load one dataset-year from a HUD file")
    r.add_argument("--dataset", required=True, choices=DATASETS)
    r.add_argument("--year", required=True, type=int, help="Effective (fiscal) year, e.g. 2025")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="Local HUD .csv or .xlsx")
    src.add_argument("--url", help="https://www.huduser.gov/... download link")
    r.add_argument("--effective-date", type=date.fromisoformat,
                   help="YYYY-MM-DD; defaults to Apr 1 (il/mtsp) or Oct 1 of the prior year (fmr)")

    s = sub.add_parser("status", help="Show what is loaded")
    s.add_argument("--dataset", choices=DATASETS)

    args = parser.parse_args(argv)
    try:
        if args.command == "refresh":
            summary = refresh(
                args.dataset, args.year, file_path=args.file, url=args.url,
                effective_date=args.effective_date,
            )
            print(
                f"Loaded {summary['rows']} rows of {summary['label']} for {summary['effective_year']}"
                f" (effective {summary['effective_date']}) from {summary['source']}"
                f" into {summary['db_path']}"
            )
        else:
            _status(args.dataset)
    except (HudDataDisabled, HudDataParseError, HudRefreshError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _status(dataset: Optional[str]) -> None:
    from .config import require_enabled

    require_enabled()
    versions = store.current_versions(dataset)
    if not versions:
        print("No HUD data loaded.")
        return
    for v in versions:
        print(
            f"{DATASET_LABELS[v['dataset']]:<28} {v['effective_year']}  effective {v['effective_date']}"
            f"  {v['row_count']:>6} rows  loaded {v['loaded_at']}  from {v['source']}"
        )
