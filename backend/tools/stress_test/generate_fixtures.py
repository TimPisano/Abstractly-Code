"""
Generates 50 synthetic, deliberately messy rent-roll fixtures (CSV/XLSX)
plus a ground-truth sidecar JSON per file, for run_stress_test.py to grade
the real parse_csv_rent_roll/parse_xlsx_rent_roll against.

Each fixture is defined as a "recipe": headers, raw rows (exactly as they'd
appear in the messy source file), and a truth row per data row saying what
the importer SHOULD produce for that row (or that it should be skipped, and
why). Truth is written by hand alongside each recipe -- there is no way to
derive ground truth from the messy data itself; that's the whole point of
grading against an independent answer key instead of just checking "did it
run without an exception."

Run: python3 generate_fixtures.py (from this directory, or anywhere -- paths
are relative to this file).
"""
import csv
import io
import json
import os
import random

from openpyxl import Workbook

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(HERE, "fixtures")

random.seed(42)  # reproducible garbling


def write_csv(path, headers, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


def write_csv_raw(path, text):
    """For fixtures that need byte-level control (stray commas, junk lines) beyond what csv.writer would produce."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_xlsx(path, headers, rows, merges=None):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    for merge_range in (merges or []):
        ws.merge_cells(merge_range)
    wb.save(path)


def write_xlsx_multisheet(path, sheets):
    """sheets: [(name, headers_or_None, rows), ...] -- first sheet может be a blank/decorative one."""
    wb = Workbook()
    first = True
    for name, headers, rows in sheets:
        ws = wb.active if first else wb.create_sheet()
        ws.title = name
        first = False
        if headers is not None:
            ws.append(headers)
        for row in rows:
            ws.append(row)
    wb.save(path)


fixtures = []  # list of {"id", "truth": [...], "notes": ...}


def add_truth(fixture_id, truth_rows, notes):
    fixtures.append({"id": fixture_id, "truth": truth_rows, "notes": notes})


def row_truth(tenant=None, rent_amount=None, lease_start_date=None, lease_end_date=None,
              property_address=None, skip=False, skip_reason=None):
    return {
        "tenant": tenant, "rent_amount": rent_amount,
        "lease_start_date": lease_start_date, "lease_end_date": lease_end_date,
        "property_address": property_address,
        "skip": skip, "skip_reason": skip_reason,
    }


BASE_ADDR = "500 Commerce Way"

# ======================================================================
# Category 1: header variance (15 files) -- aliased/unusual/extra columns
# ======================================================================

# 01: standard broker headers, baseline sanity check (should PASS cleanly)
write_csv(os.path.join(FIXTURES_DIR, "01_baseline_clean.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Suite"],
    [["Acme Corp", "$2,500.00", "01/15/2023", "01/14/2028", "Suite 100"]])
add_truth("01_baseline_clean", [
    row_truth("Acme Corp", 2500.0, "2023-01-15", "2028-01-14", f"{BASE_ADDR}, Suite 100"),
], "Sanity baseline -- clean, standard headers, should pass with zero issues.")

# 02: Yardi/AppFolio-style headers ("Resident", "Scheduled Rent", "Unit SF")
write_csv(os.path.join(FIXTURES_DIR, "02_yardi_style_headers.csv"),
    ["Resident", "Scheduled Rent", "Unit SF", "Lease Commencement", "Lease Expiration", "Unit"],
    [["Beta Industries", "3800", "1800", "03/01/2022", "02/28/2027", "204"]])
add_truth("02_yardi_style_headers", [
    row_truth("Beta Industries", 3800.0, "2022-03-01", "2027-02-28", f"{BASE_ADDR}, Suite 204"),
], "Yardi/AppFolio terminology: Resident/Scheduled Rent/Unit SF/Lease Commencement.")

# 03: RealPage/MRI-style with Market Rent + Actual Rent side by side (must pick Actual, not Market)
write_csv(os.path.join(FIXTURES_DIR, "03_realpage_market_vs_actual.csv"),
    ["Tenant Name", "Market Rent", "Actual Rent", "Rent PSF", "Commence", "Expire", "Suite #"],
    [["Gamma LLC", "5000", "4200", "2.75", "06/01/2021", "05/31/2026", "12"]])
add_truth("03_realpage_market_vs_actual", [
    row_truth("Gamma LLC", 4200.0, "2021-06-01", "2026-05-31", f"{BASE_ADDR}, Suite 12"),
], "Market Rent and Rent PSF columns present -- must resolve rent_amount to Actual Rent, not either denylisted column.")

# 04: extra decorative/unmapped columns (Parking Spaces, Notes) should be ignored, not confuse mapping
write_csv(os.path.join(FIXTURES_DIR, "04_extra_unmapped_columns.csv"),
    ["Parking Spaces", "Tenant", "Notes", "Rent", "Start Date", "End Date", "Unit"],
    [["2", "Delta Co", "long-term tenant", "$1,950.00", "09/01/2020", "08/31/2025", "5"]])
add_truth("04_extra_unmapped_columns", [
    row_truth("Delta Co", 1950.0, "2020-09-01", "2025-08-31", f"{BASE_ADDR}, Suite 5"),
], "Unrecognized columns (Parking Spaces, Notes) must be ignored, not misread as tenant/rent.")

# 05: multi-space / irregular whitespace in headers -- known normalize_header gap (doesn't collapse internal whitespace)
write_csv(os.path.join(FIXTURES_DIR, "05_multispace_headers.csv"),
    ["Tenant   Name", "Monthly    Rent", "Lease  Start", "Lease  End", "Suite"],
    [["Epsilon Group", "$2,100.00", "04/01/2023", "03/31/2028", "8"]])
add_truth("05_multispace_headers", [
    row_truth("Epsilon Group", 2100.0, "2023-04-01", "2028-03-31", f"{BASE_ADDR}, Suite 8"),
], "Header cells with multiple internal spaces (\"Tenant   Name\") -- tests whether normalize_header's whitespace handling still matches the alias.")

# 06: PMS canned report with decorative rows before the real header (title + as-of date + blank)
write_csv(os.path.join(FIXTURES_DIR, "06_pms_decorative_rows.csv"),
    ["500 Commerce Way - Rent Roll Report", "", "", ""],
    [["As of 06/30/2024", "", "", ""],
     ["", "", "", ""],
     ["Tenant", "Rent", "Lease From", "Lease To", "Unit"],
     ["Zeta Partners", "$2,750.00", "07/01/2022", "06/30/2027", "3"]])
add_truth("06_pms_decorative_rows", [
    row_truth("Zeta Partners", 2750.0, "2022-07-01", "2027-06-30", f"{BASE_ADDR}, Suite 3"),
], "Decorative title/as-of-date/blank rows before the real header row -- tests _find_header_row's scan window.")

# 07: header row buried right at the edge of the scan window (row 19, within the 20-row bound)
decorative = [[f"decorative row {i}", "", "", ""] for i in range(17)]
write_csv(os.path.join(FIXTURES_DIR, "07_header_deep_in_scan_window.csv"),
    ["ignore", "ignore2", "ignore3", "ignore4"],
    decorative + [["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
                  ["Theta Retail", "$3,000.00", "01/01/2024", "12/31/2028", "20"]])
add_truth("07_header_deep_in_scan_window", [
    row_truth("Theta Retail", 3000.0, "2024-01-01", "2028-12-31", f"{BASE_ADDR}, Suite 20"),
], "Real header row sits deep in the file (within the 20-row scan window) -- boundary test.")

# 08: "Rent Commencement" column must map to lease_start_date, NOT get grabbed by rent_amount's bare "rent" alias
write_csv(os.path.join(FIXTURES_DIR, "08_rent_commencement_column.csv"),
    ["Tenant", "Base Rent", "Rent Commencement", "Lease End", "Unit"],
    [["Iota Systems", "$4,500.00", "02/01/2023", "01/31/2028", "7"]])
add_truth("08_rent_commencement_column", [
    row_truth("Iota Systems", 4500.0, "2023-02-01", "2028-01-31", f"{BASE_ADDR}, Suite 7"),
], "'Rent Commencement' must map to lease_start_date, not collide with rent_amount's bare 'rent' alias.")

# 09: bare "Commence"/"Expire" MRI-style short headers
write_csv(os.path.join(FIXTURES_DIR, "09_mri_short_headers.csv"),
    ["Tenant", "Rent", "Commence", "Expire", "Unit"],
    [["Kappa Foods", "$2,300.00", "05/01/2022", "04/30/2027", "15"]])
add_truth("09_mri_short_headers", [
    row_truth("Kappa Foods", 2300.0, "2022-05-01", "2027-04-30", f"{BASE_ADDR}, Suite 15"),
], "Bare MRI-style 'Commence'/'Expire' headers.")

# 10: Property column present per-row (portfolio-wide export), overrides base address
write_csv(os.path.join(FIXTURES_DIR, "10_per_row_property_column.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit", "Property"],
    [["Lambda Tech", "$5,200.00", "03/01/2021", "02/28/2026", "10", "900 Ocean Blvd"]])
add_truth("10_per_row_property_column", [
    row_truth("Lambda Tech", 5200.0, "2021-03-01", "2026-02-28", "900 Ocean Blvd, Suite 10"),
], "Per-row Property column must override the uploader's base_property_address for that row.")

# 11: "Property Manager" must NOT be mistaken for the property/address column
write_csv(os.path.join(FIXTURES_DIR, "11_property_manager_denylist.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit", "Property Manager"],
    [["Mu Consulting", "$1,800.00", "08/01/2023", "07/31/2028", "22", "Jane Smith"]])
add_truth("11_property_manager_denylist", [
    row_truth("Mu Consulting", 1800.0, "2023-08-01", "2028-07-31", f"{BASE_ADDR}, Suite 22"),
], "'Property Manager' (a person's name) must not be matched as the address/property column.")

# 12: multi-sheet workbook, real data on 2nd sheet, blank Summary sheet first
write_xlsx_multisheet(os.path.join(FIXTURES_DIR, "12_multisheet_summary_then_detail.xlsx"), [
    ("Summary", None, []),
    ("Detail", ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
     [["Nu Holdings", "$3,300.00", "10/01/2022", "09/30/2027", "18"]]),
])
add_truth("12_multisheet_summary_then_detail", [
    row_truth("Nu Holdings", 3300.0, "2022-10-01", "2027-09-30", f"{BASE_ADDR}, Suite 18"),
], "Blank Summary sheet before the real Detail sheet -- must not report 'no usable data'.")

# 13: unit already spells its own designator ("Suite 101", "STE. 12", "#7") -- must not double-prefix
write_csv(os.path.join(FIXTURES_DIR, "13_unit_designator_variants.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Xi Retail A", "$2,000.00", "01/01/2023", "12/31/2027", "Suite 101"],
     ["Xi Retail B", "$2,100.00", "01/01/2023", "12/31/2027", "STE. 12"],
     ["Xi Retail C", "$2,200.00", "01/01/2023", "12/31/2027", "#7"],
     ["Xi Retail D", "$2,300.00", "01/01/2023", "12/31/2027", "14"]])
add_truth("13_unit_designator_variants", [
    row_truth("Xi Retail A", 2000.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, Suite 101"),
    row_truth("Xi Retail B", 2100.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, STE. 12"),
    row_truth("Xi Retail C", 2200.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, #7"),
    row_truth("Xi Retail D", 2300.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, Suite 14"),
], "Unit column already self-designated ('Suite 101', 'STE. 12', '#7') must not get double-prefixed with 'Suite'; a bare number still gets prefixed.")

# 14: square footage column with various unit-label spellings
write_csv(os.path.join(FIXTURES_DIR, "14_sqft_header_variants.xlsx".replace(".xlsx", ".csv")),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit", "RSF"],
    [["Omicron Media", "$2,600.00", "02/01/2024", "01/31/2029", "9", "2,400"]])
add_truth("14_sqft_header_variants", [
    row_truth("Omicron Media", 2600.0, "2024-02-01", "2029-01-31", f"{BASE_ADDR}, Suite 9"),
], "RSF as a square-footage alias.")

# 15: totally novel/unrecognized headers for tenant+rent -> file-level failure (no usable columns at all)
write_csv(os.path.join(FIXTURES_DIR, "15_totally_unrecognized_headers.csv"),
    ["Occupant Entity", "Consideration", "Term Begin", "Term End", "Space"],
    [["Pi Manufacturing", "$4,000.00", "01/01/2023", "12/31/2028", "6"]])
add_truth("15_totally_unrecognized_headers", None,
    "No header alias matches tenant or rent at all ('Occupant Entity', 'Consideration') -- correct behavior is a clean RentRollImportError, not a guess.")

# ======================================================================
# Category 2: date-format chaos (10 files)
# ======================================================================

# 16: unambiguous DD/MM (day > 12) -- current parse_date has no DD/MM handling at all
write_csv(os.path.join(FIXTURES_DIR, "16_unambiguous_ddmm.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Rho Trading", "$2,750.00", "25/03/2023", "24/03/2028", "11"]])
add_truth("16_unambiguous_ddmm", [
    row_truth("Rho Trading", 2750.0, "2023-03-25", "2028-03-24", f"{BASE_ADDR}, Suite 11"),
], "DD/MM/YYYY where day=25 makes it UNAMBIGUOUSLY not US-style MM/DD (month 25 doesn't exist). Correct date is March 25 2023 - March 24 2028.")

# 17: ambiguous DD/MM that looks exactly like a valid MM/DD -- the dangerous silent-misread case
write_csv(os.path.join(FIXTURES_DIR, "17_ambiguous_ddmm_looks_like_mmdd.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Sigma Freight", "$3,100.00", "03/04/2023", "03/04/2028", "16"]])
add_truth("17_ambiguous_ddmm_looks_like_mmdd", [
    row_truth("Sigma Freight", 3100.0, "2023-03-04", "2028-03-04", f"{BASE_ADDR}, Suite 16"),
], "TRULY AMBIGUOUS: '03/04/2023' could mean March 4 (US/MM-DD) or April 3 (DD-MM) with no way to tell from the string alone. This codebase's documented, existing convention is MM/DD-first (see normalize.parse_date's docstring) -- so March 4 is the CORRECT/expected result here, unchanged by the DD/MM fix below. Included specifically to prove the fix (which only kicks in when MM/DD is INVALID, e.g. fixture 16) doesn't also flip this already-correct, merely-ambiguous case.")

# 18: "March 2024" month+year only, no day -- should be a clean 'not found', not a guess
write_csv(os.path.join(FIXTURES_DIR, "18_month_year_only.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Tau Logistics", "$2,900.00", "March 2024", "February 2029", "19"]])
add_truth("18_month_year_only", [
    row_truth("Tau Logistics", 2900.0, None, None, f"{BASE_ADDR}, Suite 19"),
], "Month+year only ('March 2024', no day) has no single correct calendar date -- correct behavior is 'not found', not a guessed day-of-month.")

# 19: abbreviated slash format "Mar-24" / "3/24"
write_csv(os.path.join(FIXTURES_DIR, "19_abbreviated_month_year.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Upsilon Print", "$1,650.00", "Mar-24", "Feb-29", "21"]])
add_truth("19_abbreviated_month_year", [
    row_truth("Upsilon Print", 1650.0, None, None, f"{BASE_ADDR}, Suite 21"),
], "Spreadsheet-style 'Mar-24' abbreviated month-year with no day -- correctly 'not found', same reasoning as #18.")

# 20: ISO 8601 dates (common in PMS system exports)
write_csv(os.path.join(FIXTURES_DIR, "20_iso_dates.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Phi Storage", "$2,400.00", "2023-06-01", "2028-05-31", "23"]])
add_truth("20_iso_dates", [
    row_truth("Phi Storage", 2400.0, None, None, f"{BASE_ADDR}, Suite 23"),
], "ISO 8601 (YYYY-MM-DD) is NOT one of parse_date's recognized shapes at all -- expect a clean 'not found', which is itself a real gap worth knowing about (a very common PMS export format).")

# 21: two-digit year, both century-boundary directions
write_csv(os.path.join(FIXTURES_DIR, "21_two_digit_years.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Chi Apparel", "$2,000.00", "01/01/68", "12/31/98", "24"],
     ["Psi Foods", "$2,150.00", "06/15/22", "06/14/27", "25"]])
add_truth("21_two_digit_years", [
    row_truth("Chi Apparel", 2000.0, "2068-01-01", "1998-12-31", f"{BASE_ADDR}, Suite 24"),
    row_truth("Psi Foods", 2150.0, "2022-06-15", "2027-06-14", f"{BASE_ADDR}, Suite 25"),
], "Two-digit-year century pivot (parse_date: <70 -> 2000s, >=70 -> 1900s). Row 1 deliberately exercises the 68/98 boundary case.")

# 22: full spelled-out month names, various abbreviation styles
write_csv(os.path.join(FIXTURES_DIR, "22_spelled_out_dates.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Omega Health", "$3,600.00", "September 1, 2022", "Aug. 31, 2027", "26"]])
add_truth("22_spelled_out_dates", [
    row_truth("Omega Health", 3600.0, "2022-09-01", "2027-08-31", f"{BASE_ADDR}, Suite 26"),
], "Spelled-out ('September 1, 2022') and abbreviated-with-period ('Aug. 31, 2027') month names.")

# 23: date with trailing/leading annotation text ("01/01/2023 (est.)")
write_csv(os.path.join(FIXTURES_DIR, "23_date_with_annotation.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Alpha Two LLC", "$2,700.00", "01/01/2023 (est.)", "12/31/2027", "27"]])
add_truth("23_date_with_annotation", [
    row_truth("Alpha Two LLC", 2700.0, None, "2027-12-31", f"{BASE_ADDR}, Suite 27"),
], "Trailing annotation text on a date cell ('(est.)') -- parse_date requires a full-string match, so this is correctly 'not found' rather than a partial/wrong parse.")

# 24: dates as real Excel date serials (xlsx date-typed cells, not strings)
wb = Workbook()
ws = wb.active
ws.append(["Tenant", "Rent", "Lease Start", "Lease End", "Unit"])
import datetime as _dt
ws.append(["Beta Two Corp", 2850, _dt.date(2023, 7, 1), _dt.date(2028, 6, 30), "28"])
wb.save(os.path.join(FIXTURES_DIR, "24_excel_real_date_cells.xlsx"))
add_truth("24_excel_real_date_cells", [
    row_truth("Beta Two Corp", 2850.0, "2023-07-01", "2028-06-30", f"{BASE_ADDR}, Suite 28"),
], "Real Excel date-typed cells (not text) -- _cell_to_str formats via strftime('%B %d, %Y') before parse_date sees it.")

# 25: blank date cells (genuinely no lease dates given) -- must be clean 'not found', not crash
write_csv(os.path.join(FIXTURES_DIR, "25_blank_dates.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Gamma Two Inc", "$1,900.00", "", "", "29"]])
add_truth("25_blank_dates", [
    row_truth("Gamma Two Inc", 1900.0, None, None, f"{BASE_ADDR}, Suite 29"),
], "Genuinely blank date cells -- must be 'not found', not a crash or a guessed date.")

# ======================================================================
# Category 3: scattered missing/blank fields (8 files)
# ======================================================================

write_csv(os.path.join(FIXTURES_DIR, "26_missing_sqft.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit", "Sq Ft"],
    [["Delta Two Co", "$2,200.00", "01/01/2023", "12/31/2027", "30", ""]])
add_truth("26_missing_sqft", [
    row_truth("Delta Two Co", 2200.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, Suite 30"),
], "Blank square footage cell -- not a core field, must not block the rest of the row.")

write_csv(os.path.join(FIXTURES_DIR, "27_missing_unit.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Epsilon Two LLC", "$2,300.00", "02/01/2023", "01/31/2028", ""]])
add_truth("27_missing_unit", [
    row_truth("Epsilon Two LLC", 2300.0, "2023-02-01", "2028-01-31", BASE_ADDR),
], "Blank unit cell -- property_address falls back to just the base address with no suite.")

write_csv(os.path.join(FIXTURES_DIR, "28_missing_end_date_only.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Zeta Two Corp", "$2,600.00", "03/01/2023", "", "31"]])
add_truth("28_missing_end_date_only", [
    row_truth("Zeta Two Corp", 2600.0, "2023-03-01", None, f"{BASE_ADDR}, Suite 31"),
], "Blank lease-end date only -- start date must still import correctly.")

write_csv(os.path.join(FIXTURES_DIR, "29_missing_rent.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Eta Two Retail", "", "04/01/2023", "03/31/2028", "32"]])
add_truth("29_missing_rent", [
    row_truth("Eta Two Retail", None, "2023-04-01", "2028-03-31", f"{BASE_ADDR}, Suite 32"),
], "Blank rent cell -- a real tenant name still imports the row (rent just 'not found'), doesn't get skipped as if it were vacant.")

write_csv(os.path.join(FIXTURES_DIR, "30_scattered_blanks_multi_row.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit", "Sq Ft"],
    [["Theta Two Inc", "$3,000.00", "05/01/2023", "", "33", "1500"],
     ["Iota Two LLC", "", "06/01/2023", "05/31/2028", "", ""],
     ["Kappa Two Corp", "$2,750.00", "", "", "35", "2000"]])
add_truth("30_scattered_blanks_multi_row", [
    row_truth("Theta Two Inc", 3000.0, "2023-05-01", None, f"{BASE_ADDR}, Suite 33"),
    row_truth("Iota Two LLC", None, "2023-06-01", "2028-05-31", BASE_ADDR),
    row_truth("Kappa Two Corp", 2750.0, None, None, f"{BASE_ADDR}, Suite 35"),
], "Multiple rows, each missing a different, unpredictable combination of fields -- each row's independent fields must still import correctly.")

write_csv(os.path.join(FIXTURES_DIR, "31_vacant_unit_rows.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["VACANT", "", "", "", "36"],
     ["Lambda Two Co", "$2,850.00", "07/01/2023", "06/30/2028", "37"],
     ["Vacant", "", "", "", "38"]])
add_truth("31_vacant_unit_rows", [
    row_truth(skip=True, skip_reason="vacant unit, not a real tenant"),
    row_truth("Lambda Two Co", 2850.0, "2023-07-01", "2028-06-30", f"{BASE_ADDR}, Suite 37"),
    row_truth(skip=True, skip_reason="vacant unit, not a real tenant"),
], "Vacant-unit rows (both 'VACANT' and 'Vacant' casing) mixed with real tenants -- vacant rows must be skipped, not imported as fake tenants.")

write_csv(os.path.join(FIXTURES_DIR, "32_totals_subtotal_rows.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Mu Two Retail", "$2,950.00", "08/01/2023", "07/31/2028", "39"],
     ["Subtotal Floor 1", "$2,950.00", "", "", ""],
     ["Nu Two Corp", "$3,100.00", "09/01/2023", "08/31/2028", "40"],
     ["Total (2 units)", "$6,050.00", "", "", ""]])
add_truth("32_totals_subtotal_rows", [
    row_truth("Mu Two Retail", 2950.0, "2023-08-01", "2028-07-31", f"{BASE_ADDR}, Suite 39"),
    row_truth(skip=True, skip_reason="subtotal row, not a real tenant"),
    row_truth("Nu Two Corp", 3100.0, "2023-09-01", "2028-08-31", f"{BASE_ADDR}, Suite 40"),
    row_truth(skip=True, skip_reason="total row, not a real tenant"),
], "Subtotal/Total summary rows mixed in with real data rows -- must be skipped, not treated as a fake mega-tenant.")

write_csv(os.path.join(FIXTURES_DIR, "33_completely_blank_row_between_data.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Xi Two Retail", "$2,400.00", "10/01/2023", "09/30/2028", "41"],
     ["", "", "", "", ""],
     ["Omicron Two LLC", "$2,550.00", "11/01/2023", "10/31/2028", "42"]])
add_truth("33_completely_blank_row_between_data", [
    row_truth("Xi Two Retail", 2400.0, "2023-10-01", "2028-09-30", f"{BASE_ADDR}, Suite 41"),
    row_truth("Omicron Two LLC", 2550.0, "2023-11-01", "2028-10-31", f"{BASE_ADDR}, Suite 42"),
], "A fully blank row between two real data rows is dropped entirely before parsing (not even a skipped_rows entry) -- must not shift or corrupt the surrounding rows' row-number citations.")

# ======================================================================
# Category 4: duplicate tenants / typos / inconsistent unit numbering (7 files)
# ======================================================================

write_csv(os.path.join(FIXTURES_DIR, "34_duplicate_tenant_name_two_units.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Pi Two Retail", "$2,000.00", "01/01/2023", "12/31/2027", "43"],
     ["Pi Two Retail", "$1,800.00", "01/01/2023", "12/31/2027", "44"]])
add_truth("34_duplicate_tenant_name_two_units", [
    row_truth("Pi Two Retail", 2000.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, Suite 43"),
    row_truth("Pi Two Retail", 1800.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, Suite 44"),
], "Same tenant name leasing two separate units -- correct behavior is TWO separate lease records (no entity-resolution/merging is attempted, and none should be), distinguished by their different Suite numbers.")

write_csv(os.path.join(FIXTURES_DIR, "35_typo_tenant_names.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Rho Two Corporation", "$2,900.00", "02/01/2023", "01/31/2028", "45"],
     ["Rho Two Corp0ration", "$2,950.00", "03/01/2023", "02/28/2028", "46"]])
add_truth("35_typo_tenant_names", [
    row_truth("Rho Two Corporation", 2900.0, "2023-02-01", "2028-01-31", f"{BASE_ADDR}, Suite 45"),
    row_truth("Rho Two Corp0ration", 2950.0, "2023-03-01", "2028-02-28", f"{BASE_ADDR}, Suite 46"),
], "Near-duplicate tenant names differing by a typo ('Corporation' vs 'Corp0ration') -- correct behavior is to import BOTH verbatim as distinct records; fuzzy-merging different rows on a guess would be worse than keeping them separate.")

write_csv(os.path.join(FIXTURES_DIR, "36_inconsistent_unit_formats.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Sigma Two LLC", "$2,100.00", "04/01/2023", "03/31/2028", "Suite 100"],
     ["Tau Two Inc", "$2,150.00", "04/01/2023", "03/31/2028", "STE 101"],
     ["Upsilon Two Co", "$2,200.00", "04/01/2023", "03/31/2028", "Unit 102"],
     ["Phi Two Corp", "$2,250.00", "04/01/2023", "03/31/2028", "103"]])
add_truth("36_inconsistent_unit_formats", [
    row_truth("Sigma Two LLC", 2100.0, "2023-04-01", "2028-03-31", f"{BASE_ADDR}, Suite 100"),
    row_truth("Tau Two Inc", 2150.0, "2023-04-01", "2028-03-31", f"{BASE_ADDR}, STE 101"),
    row_truth("Upsilon Two Co", 2200.0, "2023-04-01", "2028-03-31", f"{BASE_ADDR}, Unit 102"),
    row_truth("Phi Two Corp", 2250.0, "2023-04-01", "2028-03-31", f"{BASE_ADDR}, Suite 103"),
], "Same file, four different unit-numbering conventions -- each must combine correctly with the base address without double-prefixing.")

write_csv(os.path.join(FIXTURES_DIR, "37_case_variant_vacant_keyword.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["VaCaNt", "", "", "", "104"],
     ["Chi Two Retail", "$2,300.00", "05/01/2023", "04/30/2028", "105"]])
add_truth("37_case_variant_vacant_keyword", [
    row_truth(skip=True, skip_reason="vacant (mixed case)"),
    row_truth("Chi Two Retail", 2300.0, "2023-05-01", "2028-04-30", f"{BASE_ADDR}, Suite 105"),
], "Mixed-case 'VaCaNt' -- keyword matching must be case-insensitive.")

write_csv(os.path.join(FIXTURES_DIR, "38_tenant_name_with_real_word_total.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Totally Awesome Tenant LLC", "$1,700.00", "06/01/2023", "05/31/2028", "106"]])
add_truth("38_tenant_name_with_real_word_total", [
    row_truth("Totally Awesome Tenant LLC", 1700.0, "2023-06-01", "2028-05-31", f"{BASE_ADDR}, Suite 106"),
], "A REAL tenant name that happens to start with 'Total' as a substring of a different word ('Totally') -- must NOT be mistaken for a totals row (word-boundary check, not substring).")

write_csv(os.path.join(FIXTURES_DIR, "39_leading_trailing_whitespace_names.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["  Psi Two Corp  ", "$2,400.00", "07/01/2023", "06/30/2028", "107"]])
add_truth("39_leading_trailing_whitespace_names", [
    row_truth("Psi Two Corp", 2400.0, "2023-07-01", "2028-06-30", f"{BASE_ADDR}, Suite 107"),
], "Tenant name with leading/trailing whitespace -- must be trimmed.")

write_csv(os.path.join(FIXTURES_DIR, "40_zero_as_vacant_marker.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["0", "", "", "", "108"],
     ["Omega Two LLC", "$2,600.00", "08/01/2023", "07/31/2028", "109"]])
add_truth("40_zero_as_vacant_marker", [
    row_truth(skip=True, skip_reason="'0' used as a vacant-unit marker, not a real tenant name"),
    row_truth("Omega Two LLC", 2600.0, "2023-08-01", "2028-07-31", f"{BASE_ADDR}, Suite 109"),
], "A literal '0' in the tenant cell (a real pattern some rent rolls use for vacant units) must not import as a fake tenant literally named '0'.")

# ======================================================================
# Category 5: currency formatting inconsistencies (5 files)
# ======================================================================

write_csv(os.path.join(FIXTURES_DIR, "41_bare_number_no_dollar_sign.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Alpha Three Corp", "1200", "01/01/2023", "12/31/2027", "110"]])
add_truth("41_bare_number_no_dollar_sign", [
    row_truth("Alpha Three Corp", 1200.0, "2023-01-01", "2027-12-31", f"{BASE_ADDR}, Suite 110"),
], "Bare number with no '$' at all -- _parse_import_currency's specific tolerance for spreadsheet cells.")

write_csv(os.path.join(FIXTURES_DIR, "42_currency_format_variants.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Beta Three Inc", "$1,200.00", "02/01/2023", "01/31/2028", "111"],
     ["Gamma Three LLC", "1,200", "02/01/2023", "01/31/2028", "112"],
     ["Delta Three Co", "$1200", "02/01/2023", "01/31/2028", "113"],
     ["Epsilon Three Corp", "1200.00", "02/01/2023", "01/31/2028", "114"]])
add_truth("42_currency_format_variants", [
    row_truth("Beta Three Inc", 1200.0, "2023-02-01", "2028-01-31", f"{BASE_ADDR}, Suite 111"),
    row_truth("Gamma Three LLC", 1200.0, "2023-02-01", "2028-01-31", f"{BASE_ADDR}, Suite 112"),
    row_truth("Delta Three Co", 1200.0, "2023-02-01", "2028-01-31", f"{BASE_ADDR}, Suite 113"),
    row_truth("Epsilon Three Corp", 1200.0, "2023-02-01", "2028-01-31", f"{BASE_ADDR}, Suite 114"),
], "Four different formattings of the exact same $1,200 rent -- all four must resolve to the identical 1200.0 value.")

write_csv(os.path.join(FIXTURES_DIR, "43_currency_with_trailing_text.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Zeta Three LLC", "$2,500.00/mo", "03/01/2023", "02/28/2028", "115"]])
add_truth("43_currency_with_trailing_text", [
    row_truth("Zeta Three LLC", 2500.0, "2023-03-01", "2028-02-28", f"{BASE_ADDR}, Suite 115"),
], "Trailing unit annotation ('/mo') after the dollar amount -- the currency regex should still extract the leading number.")

write_csv(os.path.join(FIXTURES_DIR, "44_non_numeric_rent_placeholder.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Eta Three Corp", "TBD", "04/01/2023", "03/31/2028", "116"]])
add_truth("44_non_numeric_rent_placeholder", [
    row_truth("Eta Three Corp", None, "2023-04-01", "2028-03-31", f"{BASE_ADDR}, Suite 116"),
], "Non-numeric placeholder text ('TBD') in the rent cell -- must be 'not found', never coerced to 0 or some other fabricated number.")

write_csv(os.path.join(FIXTURES_DIR, "45_annual_rent_mislabeled_column.csv"),
    ["Tenant", "Annual Rent", "Lease Start", "Lease End", "Unit"],
    [["Theta Three Inc", "$30,000.00", "05/01/2023", "04/30/2028", "117"]])
add_truth("45_annual_rent_mislabeled_column", None,
    "'Annual Rent' isn't one of rent_amount's monthly-rent aliases (deliberately -- this system's rent_amount is always monthly; treating an annual figure as-is would silently overstate monthly rent 12x). Expect either 'no usable rent column' (file-level failure) or, if some other alias coincidentally matches, WRONG data -- this is specifically testing whether the importer can tell the difference between a real gap and a unit mismatch, which is a known limitation, not a bug this pass fixes.")

# ======================================================================
# Category 6: garbled / OCR-style corruption (5 files)
# ======================================================================

# 46: OCR character substitution inside a currency figure (O for 0)
write_csv(os.path.join(FIXTURES_DIR, "46_ocr_currency_substitution.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Iota Three LLC", "$1,2OO.00", "06/01/2023", "05/31/2028", "118"]])
add_truth("46_ocr_currency_substitution", [
    row_truth("Iota Three LLC", None, "2023-06-01", "2028-05-31", f"{BASE_ADDR}, Suite 118"),
], "OCR-style letter/digit confusion inside a number ('1,2OO.00' with a capital O instead of two zeros) -- correct/safe behavior is failing to find a clean number (None), NOT silently extracting a truncated '1.2' or similar wrong-but-plausible value.")

# 47: OCR substitution inside a date (O for 0, l for 1)
write_csv(os.path.join(FIXTURES_DIR, "47_ocr_date_substitution.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Kappa Three Corp", "$2,000.00", "Ol/l5/2O23", "l2/3l/2O27", "119"]])
add_truth("47_ocr_date_substitution", [
    row_truth("Kappa Three Corp", 2000.0, None, None, f"{BASE_ADDR}, Suite 119"),
], "OCR letter/digit confusion inside dates ('Ol/l5/2O23') -- correct/safe behavior is 'not found' (regex simply won't match letters), not a garbled wrong date.")

# 48: misaligned columns for one row (a stray extra field shifts everything right).
# Uses csv.writer (not raw text) so the $-amounts' internal commas are
# correctly quoted -- an earlier version of this fixture wrote them
# unquoted, which made the CSV *itself* genuinely malformed (a comma
# inside an unquoted field is a real delimiter) and produced garbage
# for reasons having nothing to do with the extra-columns scenario this
# fixture is actually about. Column 5+ (the injected "extra","stray",
# "field" cells) are simply never read -- column_mapping only knows
# about the 5 header-declared indices -- so the row's real rent/dates,
# now sitting past index 4, are honestly "not found" rather than
# fabricated; only the Unit cell (index 4) lands on the wrong data
# (the literal, quoted "$2,300.00" text) since the header's Unit column
# still exists at that position.
write_csv(os.path.join(FIXTURES_DIR, "48_misaligned_row.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Lambda Three Inc", "$2,200.00", "07/01/2023", "06/30/2028", "120"],
     ["Mu Three LLC", "extra", "stray", "field", "$2,300.00", "08/01/2023", "07/31/2028", "121"],
     ["Nu Three Corp", "$2,400.00", "09/01/2023", "08/31/2028", "122"]])
add_truth("48_misaligned_row", [
    row_truth("Lambda Three Inc", 2200.0, "2023-07-01", "2028-06-30", f"{BASE_ADDR}, Suite 120"),
    row_truth(skip=True, skip_reason="extra stray fields shift this row's real rent/dates past the columns the header declared, so none of its MAPPED columns contain a parseable rent or date -- caught by the same 'tenant alone isn't enough' guard added for fixture 49, an unplanned but welcome side benefit: a misaligned row is skipped and reported (visible in skipped_rows) rather than silently imported as a half-populated, garbled record"),
    row_truth("Nu Three Corp", 2400.0, "2023-09-01", "2028-08-31", f"{BASE_ADDR}, Suite 122"),
], "Middle row has extra stray fields injected before its real rent/dates, shifting them past the columns the header declared -- none of its mapped columns end up with a parseable rent or date, so the same guard that catches junk lines (fixture 49) also catches this: skipped and reported by name, not silently imported with a garbled address.")

# 49: junk/non-tabular line injected between data rows (same quoting fix as #48)
write_csv(os.path.join(FIXTURES_DIR, "49_injected_junk_line.csv"),
    ["Tenant", "Rent", "Lease Start", "Lease End", "Unit"],
    [["Xi Three Retail", "$2,100.00", "10/01/2023", "09/30/2028", "123"],
     ["*** END OF PAGE 1 *** CONTINUED ON PAGE 2 ***"],
     ["Omicron Three LLC", "$2,250.00", "11/01/2023", "10/31/2028", "124"]])
add_truth("49_injected_junk_line", [
    row_truth("Xi Three Retail", 2100.0, "2023-10-01", "2028-09-30", f"{BASE_ADDR}, Suite 123"),
    row_truth(skip=True, skip_reason="junk page-break text with no rent/dates at all -- caught by the new 'tenant name alone isn't enough' guard in parse_rent_roll_rows"),
    row_truth("Omicron Three LLC", 2250.0, "2023-11-01", "2028-10-31", f"{BASE_ADDR}, Suite 124"),
], "A junk non-tabular line (page-break marker text, a common artifact of a PDF-to-CSV/OCR conversion) injected between real data rows -- before the fix, its text landed in the tenant column and, having no other data at all, was skipped over by NO existing check (it isn't blank and isn't a known non-tenant keyword), so it silently imported as a fake tenant with no rent or dates.")

# 50: merged cells in xlsx (tenant name merged across two rows -- second row's cell reads as blank)
wb = Workbook()
ws = wb.active
ws.append(["Tenant", "Rent", "Lease Start", "Lease End", "Unit"])
ws.append(["Pi Three Holdings (multi-suite)", "$2,600.00", "12/01/2023", "11/30/2028", "125"])
ws.append([None, "$2,650.00", "12/01/2023", "11/30/2028", "126"])  # merged continuation -- tenant cell genuinely blank
ws.merge_cells("A2:A3")
ws.append(["Rho Three Corp", "$2,700.00", "01/01/2024", "12/31/2028", "127"])
wb.save(os.path.join(FIXTURES_DIR, "50_merged_cell_tenant_column.xlsx"))
add_truth("50_merged_cell_tenant_column", [
    row_truth("Pi Three Holdings (multi-suite)", 2600.0, "2023-12-01", "2028-11-30", f"{BASE_ADDR}, Suite 125"),
    row_truth(skip=True, skip_reason="merged-cell continuation row -- tenant cell is genuinely blank (openpyxl only returns a value on the merge's anchor cell)"),
    row_truth("Rho Three Corp", 2700.0, "2024-01-01", "2028-12-31", f"{BASE_ADDR}, Suite 127"),
], "A tenant cell merged across two rows (e.g. one tenant leasing two adjacent suites, shown once visually) -- openpyxl reports the second physical row's tenant cell as blank. Correct/safe behavior is skipping that row (losing a real second unit) rather than fabricating a tenant name for it; documented as a real, known limitation of the merged-cell case, not silently wrong data.")


# ---------------------------------------------------------------------
# Write the manifest: for every add_truth call, record which physical
# file it corresponds to (same id, whatever extension was written).
# ---------------------------------------------------------------------
def _find_written_file(fixture_id):
    for ext in (".csv", ".xlsx"):
        candidate = os.path.join(FIXTURES_DIR, fixture_id + ext)
        if os.path.exists(candidate):
            return fixture_id + ext
    raise FileNotFoundError(f"No fixture file found on disk for id {fixture_id!r}")


manifest = []
for fx in fixtures:
    filename = _find_written_file(fx["id"])
    truth_path = os.path.join(FIXTURES_DIR, fx["id"] + ".truth.json")
    with open(truth_path, "w") as f:
        json.dump({"notes": fx["notes"], "rows": fx["truth"]}, f, indent=2)
    manifest.append({"id": fx["id"], "file": filename, "notes": fx["notes"]})

with open(os.path.join(FIXTURES_DIR, "_manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)

print(f"Generated {len(manifest)} fixtures + truth files in {FIXTURES_DIR}")
