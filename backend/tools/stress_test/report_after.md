# Rent roll stress test report

**50 fixtures.** PASS=50  SILENT_WRONG=0  UNDER_EXTRACTED=0  FAILED=0

Pass rate: 50/50 = 100.0%

## SILENT_WRONG (most dangerous -- looked successful, wasn't)

## FAILED

## UNDER_EXTRACTED (safe miss, not dangerous)

## PASS
- 01_baseline_clean
- 02_yardi_style_headers
- 03_realpage_market_vs_actual
- 04_extra_unmapped_columns
- 05_multispace_headers
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
- 16_unambiguous_ddmm
- 17_ambiguous_ddmm_looks_like_mmdd
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
- 45_annual_rent_mislabeled_column
- 46_ocr_currency_substitution
- 47_ocr_date_substitution
- 48_misaligned_row
- 49_injected_junk_line
- 50_merged_cell_tenant_column