# HUD data test fixtures

Small CSVs in the shape of HUD's annual bulk files, used by
`test_section8_hud_data.py`. **The numbers are illustrative, not real HUD
limits** — never use them for a compliance answer. Area codes, county
names and HUD area names are real public identifiers.

- `il_fy2025.csv`, `il_fy2024.csv` — Section 8 income limits (`l50_*`,
  `ELI_*`, `l80_*`). The 2024 file has a title row above the header,
  as some HUD exports do.
- `fmr_fy2026.csv` — Fair Market Rents (`fmr_0`..`fmr_4`); the 2-bedroom
  column is `$1,234`-formatted text.
- `mtsp_fy2025.csv` — MTSP / LIHTC limits (`lim50_25p*`, `lim60_25p*`);
  60% limits are exactly 1.2 × the 50% limits.

Every file includes Autauga County, AL as `100199999` — its leading
zero dropped, the way Excel saves it — and two New York counties that
share one HUD area code.
