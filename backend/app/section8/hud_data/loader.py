"""
Write side: load one dataset-year from a HUD file on disk or from
huduser.gov. Parsing happens fully before the store is touched, so a
bad file leaves the previously loaded year in place.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import date
from typing import Callable, Optional
from urllib.parse import urlparse

from . import config, store
from .models import DATASET_FMR, DATASET_LABELS, DATASETS
from .parsers import parse_file

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = ("www.huduser.gov", "huduser.gov")
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60


class HudRefreshError(RuntimeError):
    pass


def default_effective_date(dataset: str, year: int) -> date:
    """
    When a year's numbers take effect, absent an explicit date:
    - FMRs are fiscal-year figures effective October 1 of the prior
      calendar year (FY2026 → 2025-10-01).
    - Income Limits and MTSP (LIHTC) limits are typically effective around
      April 1 of their calendar year.

    HUD sets the actual effective date in each release; the 45-day LIHTC
    applicability rule and hold-harmless provisions are NOT modeled here.
    Pass --effective-date when the real date differs from the default.
    """
    if dataset == DATASET_FMR:
        return date(year - 1, 10, 1)
    return date(year, 4, 1)


def refresh(
    dataset: str,
    year: int,
    *,
    file_path: Optional[str] = None,
    url: Optional[str] = None,
    effective_date: Optional[date] = None,
    fetch: Optional[Callable[[str], bytes]] = None,
) -> dict:
    """Load `dataset` for effective `year`; returns a summary dict."""
    config.require_enabled()
    if dataset not in DATASETS:
        raise HudRefreshError(f"Unknown dataset {dataset!r}; expected one of {', '.join(DATASETS)}")
    if not 2000 <= year <= 2100:
        raise HudRefreshError(f"Implausible effective year {year}")
    if (file_path is None) == (url is None):
        raise HudRefreshError("Give exactly one of a file path or a URL")

    if file_path is not None:
        with open(file_path, "rb") as fh:
            content = fh.read()
        filename, source = os.path.basename(file_path), f"file:{os.path.basename(file_path)}"
    else:
        check_url(url)
        content = (fetch or download)(url)
        filename, source = os.path.basename(urlparse(url).path), url

    parsed = parse_file(dataset, content, filename, year)
    eff_date = effective_date or default_effective_date(dataset, year)

    # FMR's Oct 1 is the fiscal-year start; IL/MTSP dates are set per HUD
    # release, so a defaulted one is a guess worth flagging.
    if effective_date is None and dataset != DATASET_FMR:
        msg = (
            f"Effective date defaulted to {eff_date.isoformat()} for {dataset} {year}. "
            f"HUD sets the real date in each release -- check it and pass "
            f"--effective-date if it differs."
        )
        print(f"⚠️  {msg}")
        logger.warning(msg)

    count = store.replace_year(
        parsed, year, eff_date, source, hashlib.sha256(content).hexdigest()
    )
    return {
        "dataset": dataset,
        "label": DATASET_LABELS[dataset],
        "effective_year": year,
        "effective_date": eff_date.isoformat(),
        "rows": count,
        "source": source,
        "db_path": config.db_path(),
    }


def check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise HudRefreshError(f"Only https://www.huduser.gov URLs are allowed, got {url!r}")


def download(url: str) -> bytes:
    import requests

    # No redirects: following one could leave huduser.gov.
    resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, stream=True, allow_redirects=False)
    try:
        if resp.status_code != 200:
            raise HudRefreshError(f"Download failed: HTTP {resp.status_code} from {url}")
        chunks, total = [], 0
        for chunk in resp.iter_content(chunk_size=1 << 16):
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise HudRefreshError(f"Download exceeded {MAX_DOWNLOAD_BYTES} bytes: {url}")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        resp.close()
