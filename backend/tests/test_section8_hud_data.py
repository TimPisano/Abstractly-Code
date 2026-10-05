"""
Tests for app/section8/hud_data: parsing HUD's bulk files, the
effective-year versioned store, lookups, LIHTC derivations, the refresh
CLI, and the feature flag. No network: the URL path uses a fake fetcher
and a stubbed `requests.get`.

Fixtures (backend/tests/fixtures/hud_data/) carry illustrative numbers,
not real HUD limits -- see the README there.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openpyxl import Workbook

from app.section8 import hud_data
from app.section8.hud_data import (
    HudDataDisabled,
    HudDataNotFound,
    HudDataParseError,
    HudRefreshError,
    lihtc_income_limit,
    lihtc_rent_limit,
    lookup,
    lookup_fmr,
    lookup_income_limits,
    lookup_lihtc_limits,
    refresh,
)
from app.section8.hud_data import cli, config, loader, store
from app.section8.hud_data.parsers import normalize_area_code, parse_file

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "hud_data")


def fx(name):
    return os.path.join(FIXTURES, name)


@contextlib.contextmanager
def hud_env(enabled=True):
    """Fresh temp HUD DB + flag state; restores the environment after."""
    tmp = tempfile.mkdtemp()
    saved = {k: os.environ.get(k) for k in (config.FLAG_ENV, config.DB_PATH_ENV, "DB_PATH")}
    os.environ[config.DB_PATH_ENV] = os.path.join(tmp, "hud.db")
    os.environ.pop("DB_PATH", None)
    if enabled:
        os.environ[config.FLAG_ENV] = "1"
    else:
        os.environ.pop(config.FLAG_ENV, None)
    try:
        yield tmp
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)


def expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__} from {fn.__name__}")


def write_variant(tmp, src, name, transform):
    with open(fx(src)) as fh:
        text = fh.read()
    path = os.path.join(tmp, name)
    with open(path, "w") as fh:
        fh.write(transform(text))
    return path


# ------------------------------------------------------------------ flag

def test_flag_off_by_default_blocks_everything():
    with hud_env(enabled=False):
        assert hud_data.is_enabled() is False
        expect(HudDataDisabled, refresh, "il", 2025, file_path=fx("il_fy2025.csv"))
        expect(HudDataDisabled, lookup_income_limits, "0603799999")
        expect(HudDataDisabled, lookup_fmr, "0603799999")
        expect(HudDataDisabled, lookup_lihtc_limits, "0603799999")
        # Off means nothing was written either.
        assert not os.path.exists(os.environ[config.DB_PATH_ENV])
    for value in ("0", "false", "", "no"):
        os.environ[config.FLAG_ENV] = value
        assert config.is_enabled() is False, value
    os.environ.pop(config.FLAG_ENV, None)
    print("✓ test_flag_off_by_default_blocks_everything: PASS")


def test_db_path_defaults():
    with hud_env():
        os.environ.pop(config.DB_PATH_ENV)
        os.environ["DB_PATH"] = "/app/data/lease_portfolio.db"
        assert config.db_path() == "/app/data/hud_data.db"
        os.environ.pop("DB_PATH")
        assert config.db_path().endswith(os.path.join("backend", "hud_data.db"))
    print("✓ test_db_path_defaults: PASS")


# ---------------------------------------------------------- income limits

def test_income_limits_load_and_lookup():
    with hud_env():
        summary = refresh("il", 2025, file_path=fx("il_fy2025.csv"))
        assert summary["rows"] == 4
        assert summary["effective_date"] == "2025-04-01"

        il = lookup_income_limits("0603799999")
        assert il.effective_year == 2025
        assert il.effective_date == date(2025, 4, 1)
        assert il.area.state == "CA"  # State_Alpha, not the numeric State column
        assert il.area.county_name == "Los Angeles County"
        assert il.area.hud_area_code == "METRO31080M31080"
        assert il.median_income == 101000
        assert il.very_low[1] == 50000 and il.very_low[4] == 71400 and il.very_low[8] == 94250
        assert il.extremely_low[1] == 30000
        assert il.low[1] == 80000
        assert sorted(il.very_low) == list(range(1, 9))

        # 5-digit county FIPS and int input both resolve to the same area.
        assert lookup_income_limits("06037").very_low == il.very_low
        # Leading zero dropped in the file (100199999) is restored.
        al = lookup_income_limits("01001")
        assert al.area.area_code == "0100199999" and al.area.state == "AL"
        assert lookup_income_limits(100199999).area.area_code == "0100199999"
        # Lookup by HUD area code returns a member county's (identical) limits.
        ny = lookup_income_limits("metro35620mm5600")
        assert ny.area.area_code == "3604799999"
        assert ny.very_low == lookup_income_limits("36061").very_low

        expect(HudDataNotFound, lookup_income_limits, "4801399999")
        expect(HudDataNotFound, lookup_income_limits, "NOTANAREA")
        assert il.to_dict()["effective_date"] == "2025-04-01"
    print("✓ test_income_limits_load_and_lookup: PASS")


def test_nothing_loaded_is_not_found():
    with hud_env():
        err = expect(HudDataNotFound, lookup_fmr, "0603799999")
        assert "refresh" in str(err)
    print("✓ test_nothing_loaded_is_not_found: PASS")


# ------------------------------------------------------------- versioning

def test_years_coexist_and_resolve_by_year_and_date():
    with hud_env():
        refresh("il", 2024, file_path=fx("il_fy2024.csv"))   # has a title row above the header
        refresh("il", 2025, file_path=fx("il_fy2025.csv"))

        assert lookup_income_limits("06037", year=2024).very_low[1] == 47500
        assert lookup_income_limits("06037", year=2025).very_low[1] == 50000
        assert lookup_income_limits("06037").effective_year == 2025  # latest

        # 2025 limits take effect 2025-04-01; the day before, 2024's apply.
        assert lookup_income_limits("06037", as_of=date(2025, 3, 31)).effective_year == 2024
        assert lookup_income_limits("06037", as_of=date(2025, 4, 1)).effective_year == 2025
        assert lookup_income_limits("06037", as_of=date(2030, 1, 1)).effective_year == 2025
        expect(HudDataNotFound, lookup_income_limits, "06037", as_of=date(2024, 3, 31))
        expect(HudDataNotFound, lookup_income_limits, "06037", year=2023)
        expect(ValueError, lookup_income_limits, "06037", year=2025, as_of=date(2025, 5, 1))
    print("✓ test_years_coexist_and_resolve_by_year_and_date: PASS")


def test_reload_replaces_only_that_year_and_logs_versions():
    with hud_env() as tmp:
        refresh("il", 2024, file_path=fx("il_fy2024.csv"))
        refresh("il", 2025, file_path=fx("il_fy2025.csv"))

        # A corrected 2025 file: LA's 1-person limit changes, Autauga is dropped.
        corrected = write_variant(
            tmp, "il_fy2025.csv", "il_fy2025_v2.csv",
            lambda t: "\n".join(
                line.replace(",50000,57150,", ",50100,57150,")
                for line in t.splitlines() if not line.startswith("100199999")
            ),
        )
        refresh("il", 2025, file_path=corrected, effective_date=date(2025, 5, 1))

        assert lookup_income_limits("06037", year=2025).very_low[1] == 50100
        expect(HudDataNotFound, lookup_income_limits, "01001", year=2025)  # gone from 2025...
        assert lookup_income_limits("01001", year=2024).very_low[1] > 0     # ...still in 2024
        assert lookup_income_limits("06037", year=2024).very_low[1] == 47500

        history = store.version_history("il", 2025)
        assert [v["row_count"] for v in history] == [4, 3]
        assert history[1]["source"] == "file:il_fy2025_v2.csv"
        assert len(history[1]["sha256"]) == 64 and history[0]["sha256"] != history[1]["sha256"]
        # The newer load's effective date wins for as-of resolution.
        assert lookup_income_limits("06037", as_of=date(2025, 4, 15)).effective_year == 2024
        current = {(v["dataset"], v["effective_year"]): v["row_count"] for v in store.current_versions()}
        assert current == {("il", 2024): 4, ("il", 2025): 3}
    print("✓ test_reload_replaces_only_that_year_and_logs_versions: PASS")


def test_bad_file_leaves_loaded_year_untouched():
    with hud_env() as tmp:
        refresh("il", 2025, file_path=fx("il_fy2025.csv"))
        # Year-stamped headers (median2024) disagree with the year being loaded.
        err = expect(HudDataParseError, refresh, "il", 2025, file_path=fx("il_fy2024.csv"))
        assert "2024" in str(err)
        broken = write_variant(tmp, "il_fy2025.csv", "broken.csv", lambda t: t.replace(",57150,", ",n/a,", 1))
        err = expect(HudDataParseError, refresh, "il", 2025, file_path=broken)
        assert "Row 2" in str(err) and "l50_2" in str(err)

        assert lookup_income_limits("06037", year=2025).very_low[2] == 57150
        assert len(store.version_history("il", 2025)) == 1
    print("✓ test_bad_file_leaves_loaded_year_untouched: PASS")


# ------------------------------------------------------------------ parser

def test_parser_rejects_bad_input():
    good = open(fx("il_fy2025.csv"), "rb").read()
    text = good.decode()

    err = expect(HudDataParseError, parse_file, "il", text.replace("l80_8", "x").encode(), "f.csv", 2025)
    assert "l80_8" in str(err)
    err = expect(HudDataParseError, parse_file, "il", text.replace(",57150,", ",,", 1).encode(), "f.csv", 2025)
    assert "blank" in str(err)
    err = expect(HudDataParseError, parse_file, "il", text.replace(",57150,", ",-5,", 1).encode(), "f.csv", 2025)
    assert "positive" in str(err)
    # Reviewer follow-ups: zero is not a limit; "inf" used to escape as an
    # uncaught OverflowError; a limit that falls as the household grows
    # means shifted columns.
    err = expect(HudDataParseError, parse_file, "il", text.replace(",57150,", ",0,", 1).encode(), "f.csv", 2025)
    assert "positive" in str(err)
    for junk in ("inf", "nan"):
        err = expect(HudDataParseError, parse_file, "il", text.replace(",57150,", f",{junk},", 1).encode(), "f.csv", 2025)
        assert "not a number" in str(err), junk
    err = expect(HudDataParseError, parse_file, "il", text.replace(",57150,", ",49000,", 1).encode(), "f.csv", 2025)
    assert "l50_2" in str(err) and "lower than" in str(err)
    mtsp = open(fx("mtsp_fy2025.csv")).read()
    err = expect(HudDataParseError, parse_file, "mtsp", mtsp.replace(",68580,", ",1,", 1).encode(), "m.csv", 2025)
    assert "lim60_25p2" in str(err)
    lines = text.splitlines()
    err = expect(HudDataParseError, parse_file, "il", "\n".join(lines + [lines[1]]).encode(), "f.csv", 2025)
    assert "duplicate" in str(err)
    err = expect(HudDataParseError, parse_file, "il", text.replace("0603799999", "06037A", 1).encode(), "f.csv", 2025)
    assert "FIPS" in str(err)
    expect(HudDataParseError, parse_file, "il", lines[0].encode(), "f.csv", 2025)       # header only
    expect(HudDataParseError, parse_file, "il", b"a,b\n1,2\n", "f.csv", 2025)           # no FIPS header
    expect(HudDataParseError, parse_file, "il", good, "f.xls", 2025)                    # unsupported type
    expect(HudDataParseError, parse_file, "il", b"not a zip", "f.xlsx", 2025)           # corrupt workbook
    expect(HudDataParseError, parse_file, "nope", good, "f.csv", 2025)
    # MTSP year suffix (lim50_25p1) checked against the load year.
    expect(HudDataParseError, parse_file, "mtsp", open(fx("mtsp_fy2025.csv"), "rb").read(), "m.csv", 2026)
    print("✓ test_parser_rejects_bad_input: PASS")


def test_filename_year_must_match_load_year():
    # FMR headers carry no year, so before this check an FY2026 file
    # loaded as 2027 went in silently under the wrong year.
    fmr = open(fx("fmr_fy2026.csv"), "rb").read()
    for name in ("fmr_fy2026.csv", "FY26_FMRs.csv", "FY_2026.csv", "fmrs.csv"):
        assert len(parse_file("fmr", fmr, name, 2026).rows) == 4, name
    for name in ("fmr_fy2026.csv", "FY26_FMRs.csv", "Section8-FY27.csv"):
        err = expect(HudDataParseError, parse_file, "fmr", fmr, name, 2025)
        assert "File name" in str(err), name
    with hud_env():
        expect(HudDataParseError, refresh, "fmr", 2027, file_path=fx("fmr_fy2026.csv"))
        expect(HudDataNotFound, lookup_fmr, "06037")  # nothing was written
    print("✓ test_filename_year_must_match_load_year: PASS")


def test_normalize_area_code():
    assert normalize_area_code("0603799999") == "0603799999"
    assert normalize_area_code("06037") == "0603799999"
    assert normalize_area_code("6037") == "0603799999"
    assert normalize_area_code(100199999) == "0100199999"
    assert normalize_area_code(100199999.0) == "0100199999"
    assert normalize_area_code("100199999.0") == "0100199999"
    assert normalize_area_code(" 2500112345 ") == "2500112345"  # New England town code kept
    expect(HudDataParseError, normalize_area_code, "12345678901")
    expect(HudDataParseError, normalize_area_code, "")
    print("✓ test_normalize_area_code: PASS")


def test_xlsx_fmr_with_header_variants():
    wb = Workbook()
    ws = wb.active
    ws.append(["FY2026 Fair Market Rents"])  # title row
    ws.append(["FIPS", "State_Alpha", "HUD_Area_Code", "HUD Area Name", "fmr0", "fmr1", "fmr2", "fmr3", "fmr4"])
    ws.append([100199999, "AL", "METRO33860M33860", "Montgomery, AL MSA", 900, 1000.0, "1,100", 1300, 1500])
    ws.append([None] * 9)  # trailing blank row ignored
    buf = io.BytesIO()
    wb.save(buf)

    with hud_env() as tmp:
        path = os.path.join(tmp, "FY26_FMRs.xlsx")
        with open(path, "wb") as fh:
            fh.write(buf.getvalue())
        assert refresh("fmr", 2026, file_path=path)["rows"] == 1
        fmr = lookup_fmr("01001")
        assert fmr.by_bedrooms == {0: 900, 1: 1000, 2: 1100, 3: 1300, 4: 1500}
        assert fmr.area.hud_area_name == "Montgomery, AL MSA"
    print("✓ test_xlsx_fmr_with_header_variants: PASS")


# -------------------------------------------------------------------- FMR

def test_fmr_fiscal_year_effective_date():
    with hud_env():
        summary = refresh("fmr", 2026, file_path=fx("fmr_fy2026.csv"))
        assert summary["effective_date"] == "2025-10-01"  # FY2026 starts Oct 1, 2025
        fmr = lookup("fmr", "06037", as_of=date(2025, 11, 15))
        assert fmr.effective_year == 2026
        assert fmr.by_bedrooms[2] == 1866  # "$1,866" in the file
        assert fmr.by_bedrooms[0] == 1666
        expect(HudDataNotFound, lookup_fmr, "06037", as_of=date(2025, 9, 30))
        expect(ValueError, lookup, "bogus", "06037")
    print("✓ test_fmr_fiscal_year_effective_date: PASS")


# ------------------------------------------------------------------ LIHTC

def test_lihtc_limits_and_derived_rents():
    with hud_env():
        refresh("mtsp", 2025, file_path=fx("mtsp_fy2025.csv"))
        lim = lookup_lihtc_limits("06037", year=2025)
        assert lim.limit_50[1] == 50000 and lim.limit_60[1] == 60000 and lim.limit_60[2] == 68580
        assert lim.median_income == 101000

        assert lihtc_income_limit(lim, 1, 50) == 50000
        assert lihtc_income_limit(lim, 1, 60) == 60000       # published figure, not derived
        assert lihtc_income_limit(lim, 1, 40) == 40000       # 50000 * 40/50
        assert lihtc_income_limit(lim, 2, 80) == 91440       # 57150 * 80/50
        assert lihtc_income_limit(lim, 3, 30) == 38580       # 64300 * 30/50

        # Studio: 1 person.      60000 * 30% / 12 = 1500
        assert lihtc_rent_limit(lim, 0, 60) == 1500
        # 1BR: 1.5 persons -> avg(60000, 68580) = 64290 * 30% / 12 = 1607.25 -> 1607
        assert lihtc_rent_limit(lim, 1, 60) == 1607
        # 2BR: 3 persons.        77160 * 30% / 12 = 1929
        assert lihtc_rent_limit(lim, 2, 60) == 1929
        # 1BR at 40% AIT: avg(40000, 45720) = 42860 * 30% / 12 = 1071.5 -> 1071 (floored)
        assert lihtc_rent_limit(lim, 1, 40) == 1071
        # 5BR: 7.5 persons -> avg of sizes 7 and 8 at 50%: (88550 + 94250)/2 * .3 / 12 = 2285
        assert lihtc_rent_limit(lim, 5, 50) == 2285

        expect(ValueError, lihtc_income_limit, lim, 9, 50)
        expect(ValueError, lihtc_income_limit, lim, 1, 55)
        expect(ValueError, lihtc_rent_limit, lim, 6, 60)
        expect(ValueError, lihtc_rent_limit, lim, 1, 90)
    print("✓ test_lihtc_limits_and_derived_rents: PASS")


# -------------------------------------------------------------- refresh/URL

def test_url_refresh_allow_list_and_fake_fetch():
    for bad in (
        "http://www.huduser.gov/portal/datasets/il/il25/Section8-FY25.xlsx",
        "https://evil.example/Section8-FY25.xlsx",
        "https://www.huduser.gov.evil.example/x.csv",
        "file:///etc/passwd",
    ):
        expect(HudRefreshError, loader.check_url, bad)

    with hud_env():
        calls = []

        def fake_fetch(url):
            calls.append(url)
            return open(fx("mtsp_fy2025.csv"), "rb").read()

        url = "https://www.huduser.gov/portal/datasets/mtsp/mtsp25/mtsp_fy2025.csv"
        summary = refresh("mtsp", 2025, url=url, fetch=fake_fetch)
        assert calls == [url] and summary["rows"] == 4 and summary["source"] == url
        # Disallowed URL is refused before any fetch happens.
        expect(HudRefreshError, refresh, "mtsp", 2025, url="https://evil.example/m.csv", fetch=fake_fetch)
        assert calls == [url]
        expect(HudRefreshError, refresh, "mtsp", 2025)  # neither file nor url
        expect(HudRefreshError, refresh, "mtsp", 2025, file_path=fx("mtsp_fy2025.csv"), url=url)
        expect(HudRefreshError, refresh, "mtsp", 1999, file_path=fx("mtsp_fy2025.csv"))
        expect(HudRefreshError, refresh, "rent", 2025, file_path=fx("mtsp_fy2025.csv"))
    print("✓ test_url_refresh_allow_list_and_fake_fetch: PASS")


class _FakeResponse:
    def __init__(self, status, chunks):
        self.status_code, self._chunks, self.closed = status, chunks, False

    def iter_content(self, chunk_size):
        return iter(self._chunks)

    def close(self):
        self.closed = True


def test_download_refuses_redirects_errors_and_oversize():
    import requests

    original = requests.get
    seen = {}

    def stub(response):
        def get(url, **kwargs):
            seen.update(kwargs)
            return response
        return get

    try:
        requests.get = stub(_FakeResponse(200, [b"ab", b"cd"]))
        assert loader.download("https://www.huduser.gov/x.csv") == b"abcd"
        assert seen["allow_redirects"] is False and seen["timeout"] > 0

        for status in (302, 404):
            resp = _FakeResponse(status, [])
            requests.get = stub(resp)
            expect(HudRefreshError, loader.download, "https://www.huduser.gov/x.csv")
            assert resp.closed

        saved_max = loader.MAX_DOWNLOAD_BYTES
        loader.MAX_DOWNLOAD_BYTES = 3
        try:
            requests.get = stub(_FakeResponse(200, [b"ab", b"cd"]))
            expect(HudRefreshError, loader.download, "https://www.huduser.gov/x.csv")
        finally:
            loader.MAX_DOWNLOAD_BYTES = saved_max
    finally:
        requests.get = original
    print("✓ test_download_refuses_redirects_errors_and_oversize: PASS")


def test_cli_refresh_and_status():
    with hud_env():
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            assert cli.main(["refresh", "--dataset", "fmr", "--year", "2026", "--file", fx("fmr_fy2026.csv")]) == 0
            assert cli.main(["refresh", "--dataset", "il", "--year", "2025", "--file", fx("il_fy2025.csv"),
                             "--effective-date", "2025-05-15"]) == 0
            assert cli.main(["status"]) == 0
            # Errors are reported with exit code 1, not a traceback.
            assert cli.main(["refresh", "--dataset", "il", "--year", "2025", "--file", fx("missing.csv")]) == 1
            assert cli.main(["refresh", "--dataset", "il", "--year", "2025", "--file", fx("il_fy2024.csv")]) == 1
        text = out.getvalue()
        assert "Loaded 4 rows of Fair Market Rents for 2026 (effective 2025-10-01)" in text
        assert "Section 8 income limits" in text and "effective 2025-05-15" in text
        assert err.getvalue().count("error:") == 2
        assert lookup_income_limits("06037").effective_date == date(2025, 5, 15)

    with hud_env(enabled=False):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert cli.main(["status"]) == 1
        assert config.FLAG_ENV in err.getvalue()
    print("✓ test_cli_refresh_and_status: PASS")


if __name__ == "__main__":
    test_flag_off_by_default_blocks_everything()
    test_db_path_defaults()
    test_income_limits_load_and_lookup()
    test_nothing_loaded_is_not_found()
    test_years_coexist_and_resolve_by_year_and_date()
    test_reload_replaces_only_that_year_and_logs_versions()
    test_bad_file_leaves_loaded_year_untouched()
    test_parser_rejects_bad_input()
    test_filename_year_must_match_load_year()
    test_normalize_area_code()
    test_xlsx_fmr_with_header_variants()
    test_fmr_fiscal_year_effective_date()
    test_lihtc_limits_and_derived_rents()
    test_url_refresh_allow_list_and_fake_fetch()
    test_download_refuses_redirects_errors_and_oversize()
    test_cli_refresh_and_status()
    print("\nAll section8 hud_data tests passed.")
