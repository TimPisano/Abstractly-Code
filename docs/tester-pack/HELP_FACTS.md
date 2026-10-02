# Where the help articles' facts come from

`frontend/app/help-content.js` makes specific claims (limits, thresholds,
error text). Each one is listed here with its source in the code, as of
`main` @ `28f2fb9` (2026-10-01). When one of these changes, update the
article in the same branch.

## Deal Mismatch Report

| Claim | Source |
|---|---|
| 11 type keys and their UI labels | `backend/app/deal_mismatch.py:82-94`, `frontend/app/deal-mismatch-view.js:15-27` |
| Rent mismatch only if diff > $5 **and** > 1% of the larger rent | `deal_mismatch.py:142-174`, `portfolio.py:1398-1399` |
| Rent mismatch impact = monthly diff, ×12 annual; overstate if rent roll higher | `deal_mismatch.py:157-170` |
| Expired but occupied = lease end < today and rent roll row has a tenant; impact = rent roll rent; always overstate | `deal_mismatch.py:177-216` |
| Unit on rent roll, no lease: impact = rent roll rent, no direction, no citation | `deal_mismatch.py:219-250` |
| Lease on file, not on rent roll: impact = lease rent, understate | `deal_mismatch.py:253-281` |
| Concession missing: never produced yet | `deal_mismatch.py:284-292` |
| Dates mismatch: zero tolerance, start and end, medium, no $ | `deal_mismatch.py:295-333` |
| Tenant mismatch: any normalized difference, always high, no $ | `deal_mismatch.py:336-370` |
| Severity: High ≥ $1,000/mo, Medium ≥ $250/mo or unknown, Low < $250 | `discrepancies.py:40-51` |
| Units matched on normalized address incl. suite | `portfolio.py:269-279`, `deal_mismatch.py:116-139` |
| Report needs Analyst role | `api.py:3893-3894, 3965-3966, 4023-4024` |
| Default materiality 3% | `deal_mismatch.py:96` |
| T-12 box on the report fails without property_address (UI never sends it) | `deal-mismatch-view.js:42-44`, `api.js:700-705`, `api.py` "t12_file requires property_address". **Reproduced** against a local server, 2026-10-01 |

## Uploads

| Claim | Source |
|---|---|
| Effective max 16 MB per file (Flask limit; the 25 MB usage limit can't be reached) | `api.py:213, 289-292`; `usage_limits_config.py` `MAX_FILE_SIZE_MB = 25` |
| 150 pages per file | `usage_limits_config.py` `MAX_PAGES_PER_FILE`, `usage_limits.py` |
| 10 extractions per user per minute | `usage_limits_config.py`, `api.py:707` |
| 200 documents / month per team default | `usage_limits_config.py`, message `usage_limits.py` `check_team_quota` |
| "No team" 403 message | `api.py:715` |
| Lease accepted types | `frontend/app/index.html` `#fileInput` accept list; `document_extractor.py:48-56` |
| Rent roll accepted types | `index.html` `#rentRollFileInput`; `rent_roll_table_extract.py:61-74` |
| Only .csv/.xlsx imports count as rent-roll rows in the report | `portfolio.py:1383-1388` (`_is_rent_roll_import`) |
| Header row within first 20 rows; every sheet scanned; market/asking rent ignored | `rent_roll_import.py:54-128, 291-322` |
| Vacant/total/subtotal rows skipped and listed | `rent_roll_import.py:222, 390-404`; `upload-view.js:441-453` |
| Scanned rent-roll PDFs OCR'd up to 15 pages | `rent_roll_table_extract.py` |
| Duplicate upload reuses existing lease (UI doesn't say so) | `api.py:1048-1061`; `upload-view.js` ignores `reused_existing_upload` |
| Error message texts in the troubleshooting table | `api.py:605-610, 676-721, 1406-1408`; `document_extractor.py`; `ai_extraction.py:368-419`; `upload-view.js:324`; `database.py:1056` |

## T-12 (Upload page)

| Claim | Source |
|---|---|
| .csv/.xlsx only; property address required | `index.html` `#t12FileInput`; `api.py:3862-3874` |
| Flagged when gap > 5% and > $3,000/yr | `portfolio.py:1536-1537` |
| Needs an actual-rental-income line; GPR alone rejected | `t12_import.py:270-276` |
| Not stored | `index.html` T12 subtitle "checked in one pass, never stored" |

## Leases, exports, roles

| Claim | Source |
|---|---|
| 15 displayed fields in 4 groups | `frontend/app/app.js:17-40` |
| Badges, Not Found, Needs OCR, Manually Edited / Verified | `app.js:720-729`; `detail-view.js:210-283` |
| Export buttons and contents | `deal_mismatch_export.py:129-289`; `rent_roll_export.py:44-63`; `export-modal.js:63-90`; `index.html` |
| Role capabilities | `auth.py:31, 162-188`; `@require_role` on routes in `api.py` |
