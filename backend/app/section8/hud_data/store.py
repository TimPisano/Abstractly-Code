"""
SQLite storage for HUD reference data, in its own file (config.db_path()).

Two tables:
  hud_data_rows      the current numbers: one row per (dataset, effective
                     year, area). Loading a year replaces exactly that
                     year's rows, in one transaction; other years stay.
  hud_data_versions  append-only log of every load: which file, its
                     sha256, how many rows, which effective date. This is
                     what answers "which limits were in force when?" and
                     "where did this number come from?".

HUD limits are public and identical for every team, so nothing here is
team-scoped, and nothing here touches the app's portfolio database.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from typing import List, Optional, Tuple

from . import config
from .models import AreaInfo, ParsedDataset

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hud_data_rows (
    dataset         TEXT NOT NULL,
    effective_year  INTEGER NOT NULL,
    area_code       TEXT NOT NULL,
    hud_area_code   TEXT NOT NULL DEFAULT '',
    hud_area_name   TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT '',
    county_name     TEXT NOT NULL DEFAULT '',
    payload         TEXT NOT NULL,
    PRIMARY KEY (dataset, effective_year, area_code)
);
CREATE INDEX IF NOT EXISTS idx_hud_rows_hud_area
    ON hud_data_rows (dataset, effective_year, hud_area_code);

CREATE TABLE IF NOT EXISTS hud_data_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset         TEXT NOT NULL,
    effective_year  INTEGER NOT NULL,
    effective_date  TEXT NOT NULL,
    source          TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    row_count       INTEGER NOT NULL,
    loaded_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hud_versions_dataset
    ON hud_data_versions (dataset, effective_year);
"""


def connect() -> sqlite3.Connection:
    path = config.db_path()
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def replace_year(
    parsed: ParsedDataset,
    effective_year: int,
    effective_date: date,
    source: str,
    sha256: str,
) -> int:
    """Swap in one dataset-year's rows atomically and log the load."""
    rows = [
        (
            parsed.dataset, effective_year, area.area_code, area.hud_area_code,
            area.hud_area_name, area.state, area.county_name, json.dumps(payload),
        )
        for area, payload in parsed.rows
    ]
    conn = connect()
    try:
        with conn:  # one transaction: readers never see a half-loaded year
            conn.execute(
                "DELETE FROM hud_data_rows WHERE dataset = ? AND effective_year = ?",
                (parsed.dataset, effective_year),
            )
            conn.executemany(
                "INSERT INTO hud_data_rows (dataset, effective_year, area_code, hud_area_code,"
                " hud_area_name, state, county_name, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.execute(
                "INSERT INTO hud_data_versions (dataset, effective_year, effective_date, source,"
                " sha256, row_count, loaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    parsed.dataset, effective_year, effective_date.isoformat(), source,
                    sha256, len(rows), datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
    finally:
        conn.close()
    return len(rows)


def current_versions(dataset: Optional[str] = None) -> List[sqlite3.Row]:
    """The latest load of each (dataset, year), newest year first."""
    sql = """
        SELECT v.* FROM hud_data_versions v
        JOIN (SELECT dataset, effective_year, MAX(id) AS id
              FROM hud_data_versions GROUP BY dataset, effective_year) latest
          ON latest.id = v.id
    """
    params: Tuple = ()
    if dataset:
        sql += " WHERE v.dataset = ?"
        params = (dataset,)
    sql += " ORDER BY v.dataset, v.effective_year DESC"
    conn = connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def version_history(dataset: str, effective_year: int) -> List[sqlite3.Row]:
    conn = connect()
    try:
        return conn.execute(
            "SELECT * FROM hud_data_versions WHERE dataset = ? AND effective_year = ? ORDER BY id",
            (dataset, effective_year),
        ).fetchall()
    finally:
        conn.close()


def fetch_row(dataset: str, effective_year: int, area_code: str) -> Optional[Tuple[AreaInfo, dict]]:
    """
    One area's row. `area_code` matches the 10-digit FIPS first, then a
    HUD area code (several counties share one; they carry identical
    limits, so the first is returned).
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM hud_data_rows WHERE dataset = ? AND effective_year = ? AND area_code = ?",
            (dataset, effective_year, area_code),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM hud_data_rows WHERE dataset = ? AND effective_year = ?"
                " AND hud_area_code = ? ORDER BY area_code LIMIT 1",
                (dataset, effective_year, area_code),
            ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    area = AreaInfo(
        area_code=row["area_code"],
        hud_area_code=row["hud_area_code"],
        hud_area_name=row["hud_area_name"],
        state=row["state"],
        county_name=row["county_name"],
    )
    return area, json.loads(row["payload"])
