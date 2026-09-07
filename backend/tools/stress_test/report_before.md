# Rent roll stress test report

**50 fixtures.** PASS=43  SILENT_WRONG=4  UNDER_EXTRACTED=2  FAILED=1

Pass rate: 43/50 = 86.0%

## SILENT_WRONG (most dangerous -- looked successful, wasn't)
- **17_ambiguous_ddmm_looks_like_mmdd**: row 0 field=lease_start_date: expected='2023-04-03' actual='2023-03-04' (SILENT_WRONG); row 0 field=lease_end_date: expected='2028-04-03' actual='2028-03-04' (SILENT_WRONG)
- **46_ocr_currency_substitution**: row 0 field=rent_amount: expected=None actual=12.0 (SILENT_WRONG)
- **48_misaligned_row**: row 0 field=rent_amount: expected=2200.0 actual=2.0 (SILENT_WRONG); row 0 field=lease_start_date: expected='2023-07-01' actual=None (UNDER_EXTRACTED); row 0 field=lease_end_date: expected='2028-06-30' actual='2023-07-01' (SILENT_WRONG); row 0 field=property_address: expected='500 Commerce Way, Suite 120' actual='500 Commerce Way, Suite 06/30/2028' (SILENT_WRONG); row 2 field=tenant: expected='Nu Three Corp' actual='Mu Three LLC' (SILENT_WRONG); row 2 field=rent_amount: expected=2400.0 actual=None (UNDER_EXTRACTED); row 2 field=lease_start_date: expected='2023-09-01' actual=None (UNDER_EXTRACTED); row 2 field=lease_end_date: expected='2028-08-31' actual=None (UNDER_EXTRACTED); row 2 field=property_address: expected='500 Commerce Way, Suite 122' actual='500 Commerce Way, Suite $2' (SILENT_WRONG); row - field=(skip count): expected='1 skipped row(s)' actual='0 skipped row(s)' (SILENT_WRONG)
- **49_injected_junk_line**: row 0 field=rent_amount: expected=2100.0 actual=2.0 (SILENT_WRONG); row 0 field=lease_start_date: expected='2023-10-01' actual=None (UNDER_EXTRACTED); row 0 field=lease_end_date: expected='2028-09-30' actual='2023-10-01' (SILENT_WRONG); row 0 field=property_address: expected='500 Commerce Way, Suite 123' actual='500 Commerce Way, Suite 09/30/2028' (SILENT_WRONG); row 2 field=tenant: expected='Omicron Three LLC' actual='*** END OF PAGE 1 *** CONTINUED ON PAGE 2 ***' (SILENT_WRONG); row 2 field=rent_amount: expected=2250.0 actual=None (UNDER_EXTRACTED); row 2 field=lease_start_date: expected='2023-11-01' actual=None (UNDER_EXTRACTED); row 2 field=lease_end_date: expected='2028-10-31' actual=None (UNDER_EXTRACTED); row 2 field=property_address: expected='500 Commerce Way, Suite 124' actual='500 Commerce Way' (SILENT_WRONG); row - field=(skip count): expected='1 skipped row(s)' actual='0 skipped row(s)' (SILENT_WRONG)

## FAILED
- **45_annual_rent_mislabeled_column**: expected a clean rejection, but it succeeded and imported 1 row(s)

## UNDER_EXTRACTED (safe miss, not dangerous)
- **05_multispace_headers**: row 0 field=lease_start_date: expected='2023-04-01' actual=None (UNDER_EXTRACTED); row 0 field=lease_end_date: expected='2028-03-31' actual=None (UNDER_EXTRACTED)
- **16_unambiguous_ddmm**: row 0 field=lease_start_date: expected='2023-03-25' actual=None (UNDER_EXTRACTED); row 0 field=lease_end_date: expected='2028-03-24' actual=None (UNDER_EXTRACTED)

## PASS
- 01_baseline_clean
- 02_yardi_style_headers
- 03_realpage_market_vs_actual
- 04_extra_unmapped_columns
- 06_pms_decorative_rows
- 07_header_deep_in_scan_window
- 08_rent_commencement_column
- 09_mri_short_headers
- 10_per_row_property_column
- 11_property_manager_denylist
- 12_multisheet_summary_then_detail
- 13_unit_designator_variants
- 14_sqft_header_variants
- 15_totally_unrecognized_headers
- 18_month_year_only
- 19_abbreviated_month_year
- 20_iso_dates
- 21_two_digit_years
- 22_spelled_out_dates
- 23_date_with_annotation
- 24_excel_real_date_cells
- 25_blank_dates
- 26_missing_sqft
- 27_missing_unit
- 28_missing_end_date_only
- 29_missing_rent
- 30_scattered_blanks_multi_row
- 31_vacant_unit_rows
- 32_totals_subtotal_rows
- 33_completely_blank_row_between_data
- 34_duplicate_tenant_name_two_units
- 35_typo_tenant_names
- 36_inconsistent_unit_formats
- 37_case_variant_vacant_keyword
- 38_tenant_name_with_real_word_total
- 39_leading_trailing_whitespace_names
- 40_zero_as_vacant_marker
- 41_bare_number_no_dollar_sign
- 42_currency_format_variants
- 43_currency_with_trailing_text
- 44_non_numeric_rent_placeholder
- 47_ocr_date_substitution
- 50_merged_cell_tenant_column