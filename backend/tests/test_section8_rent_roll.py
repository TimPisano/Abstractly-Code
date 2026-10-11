"""
Section 8 rent rolls: a unit's rent is its CONTRACT rent, which is the
tenant's share plus the housing authority's HAP -- never the tenant's
share alone (fix/section8-tenant-share, 2026-10-11).

Builds on qa/overnight-gauntlet a1cff89 (tenant_portion / hap columns,
rent = portion + HAP when there's no contract-rent column). These tests
cover what that left open: checking a stated contract rent against the
split ($1 tolerance -- HAP and tenant share are whole dollars), flagging
mismatches, never pricing a bare tenant share as the rent, and honest
citations for a derived rent. Each was confirmed failing before the fix.

Pure parsing: no database, no Flask app, no Anthropic calls.
"""
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.rent_roll_import import parse_rent_roll_file

DEMO_RENT_ROLL = os.path.join(os.path.dirname(__file__), "..", "benchmark_data", "demo_deal", "rent_roll",
                              "maple_ridge_rent_roll_demo_subset_16unit.xlsx")


def _csv(text, base="9 Elm St"):
    return parse_rent_roll_file(text.replace("\n", "\r\n").encode(), "rr.csv", base)


def _rents(parsed):
    return [l["extracted_fields"]["rent_amount"]["value"] for l in parsed["leases"]]


def _rent_field(parsed, i=0):
    return parsed["leases"][i]["extracted_fields"]["rent_amount"]


def _checks(parsed, kind=None):
    return [c for c in parsed.get("section8_checks", []) if kind is None or c["kind"] == kind]


def _warning_text(parsed):
    return "\n".join(parsed.get("warnings", []))


# ---------------------------------------------------------------- voucher units
def test_voucher_rent_is_share_plus_hap_with_real_citation():
    got = _csv("Unit,Resident,Tenant Portion,HAP,Lease End\n101,Ann Lee,412.00,988.00,03/31/2027\n")
    assert _rents(got) == ["$1,400.00"], got
    quote = _rent_field(got)["source"]["quote"]
    # The citation names the two cells the rent was built from, not an
    # invented "$1,400.00" that appears nowhere in the file.
    assert "412.00" in quote and "988.00" in quote and "HAP" in quote, quote
    assert not _checks(got), got
    print("✓ test_voucher_rent_is_share_plus_hap_with_real_citation: PASS")


def test_voucher_contract_rent_that_adds_up_is_not_flagged():
    got = _csv("Unit,Resident,Contract Rent,Tenant Rent,HAP\n101,Ann Lee,1400.00,412.00,988.00\n"
               "102,Bo Diaz,1400.00,412.00,988.50\n")  # 50 cents of rounding: within $1
    assert _rents(got) == ["$1,400.00", "$1,400.00"], got
    assert not _checks(got) and not got.get("warnings"), got
    assert _rent_field(got)["confidence"] == "high"
    print("✓ test_voucher_contract_rent_that_adds_up_is_not_flagged: PASS")


def test_voucher_contract_rent_mismatch_is_flagged_with_dollar_gap():
    got = _csv("Unit,Resident,Contract Rent,Tenant Rent,HAP\n101,Ann Lee,1400.00,412.00,900.00\n")
    assert _rents(got) == ["$1,400.00"], got  # the stated contract rent is kept...
    assert _rent_field(got)["confidence"] == "low"  # ...but not trusted
    [c] = _checks(got, "contract_rent_mismatch")
    assert (c["row"], c["unit"], c["rent_column"], c["tenant_share"], c["hap"], c["gap"]) == (2, "101", 1400.0, 412.0, 900.0, 88.0), c
    text = _warning_text(got)
    for piece in ("101", "$1,400.00", "$412.00", "$900.00", "$1,312.00", "$88.00"):
        assert piece in text, (piece, text)
    print("✓ test_voucher_contract_rent_mismatch_is_flagged_with_dollar_gap: PASS")


def test_mismatch_just_over_one_dollar_is_flagged():
    got = _csv("Unit,Resident,Contract Rent,Tenant Rent,HAP\n101,Ann Lee,1400.00,412.00,986.99\n")
    assert len(_checks(got, "contract_rent_mismatch")) == 1, got
    print("✓ test_mismatch_just_over_one_dollar_is_flagged: PASS")


def test_generic_rent_column_that_is_really_the_share_becomes_contract_rent():
    got = _csv("Unit,Resident,Rent,Tenant Portion,HAP\n101,Ann Lee,412.00,412.00,988.00\n")
    assert _rents(got) == ["$1,400.00"], got
    assert len(_checks(got, "rent_column_was_tenant_share")) == 1, got
    assert "$1,400.00" in _warning_text(got)
    print("✓ test_generic_rent_column_that_is_really_the_share_becomes_contract_rent: PASS")


def test_generic_rent_column_that_disagrees_with_split_is_flagged():
    got = _csv("Unit,Resident,Rent,Tenant Portion,HAP\n101,Ann Lee,500.00,412.00,988.00\n")
    assert _rents(got) == ["$500.00"], got
    assert len(_checks(got, "contract_rent_mismatch")) == 1, got
    print("✓ test_generic_rent_column_that_disagrees_with_split_is_flagged: PASS")


def test_explicit_tenant_share_alone_is_never_the_rent():
    got = _csv("Unit,Resident,Tenant Share,Lease End\n101,Ann Lee,412.00,03/31/2027\n")
    assert _rents(got) == [None], got
    [c] = _checks(got, "tenant_share_only")
    assert c["tenant_share"] == 412.0, c
    assert "HAP" in _warning_text(got)
    print("✓ test_explicit_tenant_share_alone_is_never_the_rent: PASS")


def test_tenant_share_only_row_without_dates_is_still_imported_and_flagged():
    # It has a real dollar figure -- not a page-break artifact -- so it
    # must not vanish into skipped_rows where the flag would be lost.
    got = _csv("Unit,Resident,Tenant Portion\n101,Ann Lee,412.00\n")
    assert len(got["leases"]) == 1 and _rents(got) == [None], got
    assert len(_checks(got, "tenant_share_only")) == 1, got
    print("✓ test_tenant_share_only_row_without_dates_is_still_imported_and_flagged: PASS")


def test_hap_without_tenant_share_is_flagged():
    got = _csv("Unit,Resident,Tenant Portion,HAP\n101,Ann Lee,,1400.00\n")
    assert _rents(got) == ["$1,400.00"], got  # $0 tenant share is real (zero-income household)...
    assert _rent_field(got)["confidence"] == "low"
    assert len(_checks(got, "tenant_share_missing")) == 1, got  # ...but a blank one is worth a look
    print("✓ test_hap_without_tenant_share_is_flagged: PASS")


def test_unreadable_hap_cell_is_flagged_not_treated_as_zero():
    got = _csv("Unit,Resident,Tenant Portion,HAP\n101,Ann Lee,412.00,pending\n")
    assert _rents(got) == [None], got
    assert len(_checks(got, "hap_unreadable")) == 1, got
    print("✓ test_unreadable_hap_cell_is_flagged_not_treated_as_zero: PASS")


def test_dash_or_na_hap_on_market_unit_is_zero_not_unreadable():
    # Excel accounting format / PMS exports show "-" or "N/A" for no HAP.
    got = _csv("Unit,Resident,Contract Rent,Tenant Rent,HAP\n101,Ann Lee,1250.00,1250.00,-\n"
               "102,Bo Diaz,1310.00,1310.00,N/A\n103,Cy Park,1275.00,1275.00,—\n")
    assert _rents(got) == ["$1,250.00", "$1,310.00", "$1,275.00"], got
    assert not _checks(got) and not got.get("warnings"), got
    assert {l["extracted_fields"]["rent_amount"]["confidence"] for l in got["leases"]} == {"high"}
    print("✓ test_dash_or_na_hap_on_market_unit_is_zero_not_unreadable: PASS")


def test_subsidy_type_column_is_not_a_hap_amount():
    # "Subsidy Type" holds text ("HCV"), not dollars. Read as the HAP
    # column, every voucher unit got rent = tenant share + 0.
    got = _csv("Unit,Resident,Tenant Rent,Subsidy Type\n101,Ann Lee,412.00,HCV\n102,Bo Diaz,1250.00,\n")
    assert "hap" not in got["column_mapping"], got["column_mapping"]
    print("✓ test_subsidy_type_column_is_not_a_hap_amount: PASS")


# ---------------------------------------------------------------- bare "Tenant Rent", no HAP column
def test_bare_tenant_rent_on_market_roll_is_the_rent():
    got = _csv("Unit,Resident,Tenant Rent,Lease End\n101,Ann Lee,1250.00,03/31/2027\n102,Bo Diaz,1310.00,03/31/2027\n")
    assert _rents(got) == ["$1,250.00", "$1,310.00"], got
    assert not _checks(got) and not got.get("warnings"), got
    print("✓ test_bare_tenant_rent_on_market_roll_is_the_rent: PASS")


def test_bare_tenant_rent_with_file_level_voucher_indicator_is_ambiguous():
    got = _csv("Unit,Resident,Tenant Rent,Voucher #,Lease End\n"
               "101,Ann Lee,412.00,HCV-55012,03/31/2027\n102,Bo Diaz,1250.00,,03/31/2027\n")
    assert _rents(got) == [None, None], got  # the file says vouchers exist: don't guess for any unit
    checks = _checks(got, "ambiguous_tenant_rent")
    assert [c["unit"] for c in checks] == ["101", "102"], checks
    assert "Voucher" in checks[0]["indicator"], checks[0]
    assert "confirm" in _warning_text(got).lower()
    print("✓ test_bare_tenant_rent_with_file_level_voucher_indicator_is_ambiguous: PASS")


def test_bare_tenant_rent_with_unit_level_voucher_indicator_is_ambiguous_for_that_unit_only():
    got = _csv("Unit,Resident,Tenant Rent,Notes,Lease End\n"
               "101,Ann Lee,412.00,Section 8 - PHA pays balance,03/31/2027\n"
               "102,Bo Diaz,1250.00,,03/31/2027\n"
               "103,Hap Nguyen,1290.00,renewed,03/31/2027\n")  # a tenant NAME is never an indicator
    assert _rents(got) == [None, "$1,250.00", "$1,290.00"], got
    [c] = _checks(got, "ambiguous_tenant_rent")
    assert c["unit"] == "101" and c["tenant_share"] == 412.0, c
    print("✓ test_bare_tenant_rent_with_unit_level_voucher_indicator_is_ambiguous_for_that_unit_only: PASS")


def test_unit_ids_and_addresses_are_not_voucher_indicators():
    # "S8"/"Sec8-2" are unit numbers and "Pha St" is a street -- none of them
    # says the household has a voucher.
    got = _csv("Unit,Resident,Tenant Rent,Address\n"
               "S8,Ann Lee,1250.00,12 Oak Ave\nSec8-2,Bo Diaz,1310.00,40 Pha St\n"
               "103,Cy Park,1275.00,9 Housing Authority Rd\n")
    assert _rents(got) == ["$1,250.00", "$1,310.00", "$1,275.00"], got
    assert not _checks(got), _checks(got)
    print("✓ test_unit_ids_and_addresses_are_not_voucher_indicators: PASS")


# ---------------------------------------------------------------- market units
def test_market_rent_roll_is_unchanged():
    got = _csv("Unit,Tenant,Rent,Lease End\n101,Ann Lee,1250.00,03/31/2027\n102,Bo Diaz,1310.00,03/31/2027\n")
    assert _rents(got) == ["$1,250.00", "$1,310.00"], got
    assert _rent_field(got)["source"]["quote"] == "1250.00"
    assert "section8_checks" not in got and not got.get("warnings"), got
    print("✓ test_market_rent_roll_is_unchanged: PASS")


def test_maple_ridge_demo_rent_roll_has_no_section8_flags():
    with open(DEMO_RENT_ROLL, "rb") as f:
        got = parse_rent_roll_file(f.read(), os.path.basename(DEMO_RENT_ROLL), "Maple Ridge")
    assert got["leases"], got
    assert "section8_checks" not in got and not got.get("warnings"), got.get("warnings")
    assert all(l["extracted_fields"]["rent_amount"]["confidence"] == "high"
               for l in got["leases"] if l["extracted_fields"]["rent_amount"]["value"]), got
    print("✓ test_maple_ridge_demo_rent_roll_has_no_section8_flags: PASS")


# ---------------------------------------------------------------- mixed rolls
_MIXED = ("Unit,Resident,Contract Rent,Tenant Rent,HAP,Lease End\n"
          "101,Ann Lee,1400.00,412.00,988.00,03/31/2027\n"     # voucher, adds up
          "102,Bo Diaz,1250.00,1250.00,,03/31/2027\n"          # market, HAP blank
          "103,Cy Park,1310.00,1310.00,0.00,03/31/2027\n"      # market, HAP 0
          "104,Di Moss,1450.00,300.00,1050.00,03/31/2027\n"    # voucher, $100 short
          "105,Ed Kahn,1275.00,1275.00,,03/31/2027\n")         # market


def test_mixed_roll_flags_only_the_bad_voucher_unit():
    got = _csv(_MIXED)
    assert _rents(got) == ["$1,400.00", "$1,250.00", "$1,310.00", "$1,450.00", "$1,275.00"], got
    checks = _checks(got)
    assert [(c["unit"], c["kind"], c["gap"]) for c in checks] == [("104", "contract_rent_mismatch", 100.0)], checks
    assert [l["extracted_fields"]["rent_amount"]["confidence"] for l in got["leases"]] == ["high", "high", "high", "low", "high"]
    assert len(got["warnings"]) == 1 and "104" in got["warnings"][0] and "102" not in got["warnings"][0], got["warnings"]
    print("✓ test_mixed_roll_flags_only_the_bad_voucher_unit: PASS")


def test_mixed_roll_without_contract_column():
    got = _csv("Unit,Resident,Tenant Portion,HAP\n101,Ann Lee,412.00,988.00\n102,Bo Diaz,1250.00,\n103,Cy Park,1310.00,0\n")
    assert _rents(got) == ["$1,400.00", "$1,250.00", "$1,310.00"], got
    assert not _checks(got), got
    # A market unit with a blank HAP cell cites its own cell, not a "+ HAP $0.00" sum.
    assert [_rent_field(got, i)["source"]["quote"] for i in range(3)] == [
        "Tenant share $412.00 + HAP $988.00", "1250.00", "Tenant share $1,310.00 + HAP $0.00"], got
    print("✓ test_mixed_roll_without_contract_column: PASS")


def test_mixed_roll_xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for line in _MIXED.strip().split("\n"):
        ws.append([float(c) if c.replace(".", "").isdigit() and "." in c else (c or None) for c in line.split(",")])
    buf = io.BytesIO()
    wb.save(buf)
    got = parse_rent_roll_file(buf.getvalue(), "rr.xlsx", "9 Elm St")
    assert _rents(got) == ["$1,400.00", "$1,250.00", "$1,310.00", "$1,450.00", "$1,275.00"], got
    assert [c["unit"] for c in _checks(got)] == ["104"], _checks(got)
    assert len(got["warnings"]) == 1, got["warnings"]
    print("✓ test_mixed_roll_xlsx: PASS")


def test_many_flagged_units_make_one_capped_warning():
    rows = "".join(f"{100 + i},Res {chr(65 + i)} Smith,1400.00,412.00,900.00\n" for i in range(14))
    got = _csv("Unit,Resident,Contract Rent,Tenant Rent,HAP\n" + rows)
    assert len(_checks(got, "contract_rent_mismatch")) == 14
    assert len(got["warnings"]) == 1, got["warnings"]
    assert "+4 more" in got["warnings"][0] and "14 unit" in got["warnings"][0], got["warnings"][0]
    print("✓ test_many_flagged_units_make_one_capped_warning: PASS")


def test_ocr_table_warnings_are_merged_not_overwritten():
    from unittest import mock
    from app import rent_roll_table_extract as rte

    class _Table:
        rows = [["Unit", "Resident", "Contract Rent", "Tenant Rent", "HAP"], ["101", "Ann Lee", "1400.00", "412.00", "900.00"]]
        source_kind = "pdf-text"
        warnings = ["Read from a PDF table -- spot-check a few rows."]
        ocr_confidence = None

    with mock.patch.object(rte, "extract_rent_roll_table", return_value=_Table()):
        got = parse_rent_roll_file(b"%PDF-1.4 fake", "rr.pdf", "9 Elm St")
    assert got["warnings"][0] == _Table.warnings[0], got["warnings"]
    assert any("$88.00" in w for w in got["warnings"]), got["warnings"]
    print("✓ test_ocr_table_warnings_are_merged_not_overwritten: PASS")


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:  # report every failure, not just the first
                failures += 1
                print(f"✗ {name}: FAIL -- {type(exc).__name__}: {str(exc)[:300]}")
    sys.exit(1 if failures else 0)
