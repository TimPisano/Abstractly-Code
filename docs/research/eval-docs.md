# Public sample documents for extraction evals: affordable housing (Section 8, LIHTC)

**Dated:** 2026-10-19 (second pass)
**Scope:** Public, no-login sample documents for testing AI extraction (lease abstraction, rent roll validation). Research only. Nothing saved to the repo.

## How to read this file

- **Verified** = the URL returned HTTP 200 with the file body, with no login, during this pass. WebFetch cannot decode PDF text in this environment, so "verified" means the file loads. Page counts come from PDF metadata (`/N` or `/Count`) and are marked "metadata". Form identity comes from the title/metadata or from search snippets, and is marked when it is search-only. Field lists and blank-vs-filled status still need a local check before we write ground truth.
- **Leads** = found in search results but not fetched, or fetched and failed (404, 403, cert error, denied). These are listed at the end and are not in the v1 eval set.
- **PII list** = documents that may contain real personal data or whose filled/blank status is unknown. These need a human check before use. No personal details are recorded here.

## Resolved: is the hud.gov "50059" PDF really HUD-50059?

Yes, with a caveat. The earlier concern was that its field names looked like the 50058 family report. Two facts now point the other way:
- The hud.gov 50059 PDF's field names include `iREMSPropertyID`, `BasicBMIRRent` and `TTPAtRADConversion`. REMS, BMIR and RAD are multifamily terms, and the 50058 PHA family report does not use them.
- HUD's own instructions file, "Instructions for TRACS 202D form HUD-50059 (06/2014) ... Owner's Certification of Compliance" (https://www.hud.gov/sites/documents/50059ins.doc), confirms the 50059 is the multifamily owner certification.

Caveat: the 06/2014 edition is labeled "For Personal Records ONLY" with an expiration of 06/30/2017. It is an obsolete edition, useful for layout only. The 50058 family report URLs we tried (hud.gov and dfiles/PIH 2024) returned 404 and are in the leads section.

## Counts

- Verified (loads, no login): **31**
- v1 eval set: **18**
- Leads not verified: see section "Leads to check by hand"
- PII / blank-vs-filled check: see section "Needs a human PII check before use"

---

## 1. HUD: HCV, PBV, PBRA, and HQS/NSPIRE

| Document | Issuer | Verified link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| HUD-50059 Owner's Certification of Compliance (06/2014) | HUD | https://www.hud.gov/sites/documents/50059.pdf | Fillable PDF (AcroForm) | Blank | 3 (metadata) | Project and unit header, rent, subsidy, TTP, signatures | Multifamily core form. Obsolete edition (expired 2017). | verified (loads); identity resolved above | US federal, public domain (17 USC 105) |
| HUD-50059-A (partial certification addendum) | HUD | https://www.hud.gov/sites/documents/50059-a.pdf | Fillable PDF | Blank | ~3 (metadata, uncertain) | Move-out, unit transfer and partial cert fields | Companion to 50059 | verified (loads) | US federal |
| HUD-50059 instructions (TRACS 202D, 06/2014) | HUD | https://www.hud.gov/sites/documents/50059ins.doc | Word .doc (221 KB) | n/a | n/a | Definitions for ground truth | Text reference for 50059 field meanings | verified (loads) | US federal |
| HUD-52670 voucher, owner billing (TRACS 202D family; embedded title HUD52670-202D) | HUD | https://www.hud.gov/sites/documents/52670.pdf | Fillable PDF | Blank | 1 (metadata) | Project and contract numbers, unit counts 6a to 6e, exceptions 7a to 7e, voucher amounts 9 to 10 | Dense numbered-field, one-page form | verified (loads); identity from metadata | US federal |
| HUD-52641 HCV HAP contract, 2023 edition (Parts A, B, C) | Rhode Island Housing copy of HUD form | https://rhanc.gov/wp-content/uploads/2025/01/HUD-52641_2023_HAP_CONTRACT.pdf | PDF (re-saved) | Blank | 4 (metadata) | Contract number, owner, unit, contract rent, dates, signatures | Multi-part contract with signature blocks | verified (loads) | US federal; PHA copy public |
| HUD-52641 complete HAP contract, Parts A/B/C (exp. 04/30/2026) | Tarrant County (TX) Housing Assistance | https://www.tarrantcountytx.gov/content/dam/main/housing-assistance/Documents/HUD-52641CompleteHAPContract_Parts%20A_B_C-EXP04-30-2026.pdf | PDF | Blank | ~13 (metadata) | As above plus tenancy addendum terms | Full contract in one file, long | verified (loads); expired OMB date | US federal |
| HUD-52530B PBV HAP contract, existing housing, Part 1 (07/2019) | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52530Bpt1.pdf | PDF | Blank | 11 (metadata) | Contract number, units, exhibit list, effective date, term | Multi-page, exhibits list | verified (loads) | US federal |
| HUD-52530A PBV HAP contract, new construction / rehab | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52530A_PBV.pdf | Fillable PDF (AcroForm, ZapfDingbats checkboxes) | Blank | not counted (~2 per metadata, unconfirmed) | Header fields, unit list, rent schedule | Fillable PBV new construction contract, different from 52530B | verified (loads) | US federal |
| HUD-52580 HQS / Housing Quality Standards inspection checklist (dfiles/OCHCO copy, 04/2023 per search) | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52580.pdf | PDF checklist | Blank | ~8 (metadata; A4 page size is unusual for HUD, so confirm the copy) | Item pass/fail checkboxes, inspector notes | Checkbox-heavy | verified (loads); edition per search | US federal |
| HUD-9834 Management and Occupancy Review (06/2016) | HUD | https://www.hud.gov/sites/documents/9834.pdf | Fillable PDF (AcroForm), ~1.1 MB | Blank | not counted | Desk review, on-site review, addenda, summary | Multi-section, checkbox and addenda test | verified (loads) | US federal |
| HUD-52517 Request for Tenancy Approval (RFTA), 04/2023 per search | San Francisco Housing Authority copy | https://sfha.org/files/documents/52517ENG.pdf | Fillable PDF (AcroForm, checkboxes) | Blank | not counted | Family, unit address, rent, owner, dates, signatures | Fillable form with checkboxes | verified (loads); edition per search | US federal; PHA copy public |
| HUD-9639 renewal HAP contract (Section 8 renewal) | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/9639.pdf | PDF (324.7 KB) | Blank (per search; content not readable) | not counted | Renewal contract fields (to confirm by reading) | Renewal contract template, Section 8 renewal exhibit family | verified (loads); identity from search only | US federal |
| HUD-9626 automatic OCAF rent increase letter template (with HUD-92458 reference) | HUD | https://hud.gov/sites/dfiles/OCHCO/documents/9626.pdf | PDF (306 KB) | Blank template (per search; content not readable) | not counted | Rent increase factor, debt service, effective date, Exhibit A reference | Template letter with blanks, good for template-letter extraction | verified (loads); identity from search only | US federal |
| NSPIRE Inspection Protocol Guide | HUD PIH | https://hud.gov/sites/dfiles/PIH/documents/NSPIRE_Inspection_Protocol_Guide.pdf | PDF guide | n/a (not a form) | 20 (metadata) | Not an extraction target; use for defect taxonomy | Reference for synthetic NSPIRE reports | verified (loads) | US federal |
| HUD Handbook 4350.3 REV-1 appendices table of contents | HUD | https://hud.gov/sites/documents/43503a-tochsgh.pdf | PDF (69 KB) | n/a | 2 (metadata) | Appendix titles (not readable here) | Index only | verified (loads); text not readable | US federal |
| HUD Handbook 4350.3 REV-1 exhibits table of contents | HUD | https://www.hud.gov/sites/documents/43503e-tochsgh.pdf | PDF (79 KB) | n/a | ~3 (metadata) | Exhibit titles (not readable here) | Index only | verified (loads); metadata title shows "Chapter 1", so confirm | US federal |

**Note on 50059 and 50058:** the 2024 family report (50058) was not reachable (both URLs 404). Use the 50059 for the multifamily set, and treat the 50058 as a lead.

---

## 2. Utility allowances (HUD-52667 PHA schedules)

| Document | Issuer | Verified link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| Utility Allowance Schedules 2026 (effective 06/01/2026) | Housing Opportunities Commission of Montgomery County, MD | https://www.hocmc.org/wp-content/uploads/2025/05/Utility-Allowance-Schedules-2026.pdf | PDF (199 KB), table-heavy | Filled (real allowance amounts; no personal data) | not counted | Utility type by bedroom count (0 to 9 BR), by building type | Dense multi-column table, best table test available | verified (loads). The 2025 copy at the same host returned 404 (see leads). | Public PHA record |

---

## 3. LIHTC: federal and tax forms

| Document | Issuer | Verified link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| HUD-52697 LIHTC Tenant Data Collection Form (metadata title "LIHTC Tenant Data Form 2022") | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52697.pdf | PDF (57 KB) | Blank | not counted | Household demographics, income, rent, unit data (coded) | Federal LIHTC reporting form with coded fields. Expired OMB approval 2528-0320 (10/31/2025) per search. | verified (loads) | US federal |
| IRS Form 8609, Low-Income Housing Credit Allocation and Certification (Rev. Dec 2021) | IRS | https://www.irs.gov/pub/irs-pdf/f8609.pdf | PDF (85 KB) | Blank | not counted (metadata unclear) | BIN, allocation dates, credit percentages, owner info | Checkbox-heavy tax form | verified (loads) | US federal, public domain |
| IRS Form 8609-A, Annual Statement for Low-Income Housing Credit (metadata Rev. 12-2008) | IRS | https://www.irs.gov/pub/irs-access/f8609a_accessible.pdf | PDF (82 KB) | Blank | 1 (metadata) | Building ID, annual compliance figures | Replaced Schedule A for annual filing. The metadata shows an old 12-2008 revision, so check the current revision on irs.gov. | verified (loads) | US federal |
| IRS Form 8586, Low-Income Housing Credit (Rev. Dec 2023) | IRS | https://www.IRS.GOV/pub/irs-access/f8586_accessible.pdf | PDF (72 KB, accessible) | Blank | 1 (metadata) | Building credit figures, line items | Short tax form, numeric fields | verified (loads) | US federal |
| IRS Form 8823, Low-Income Housing Credit Agencies Report of Noncompliance (Dec 2019 revision) | IRS | https://www.irs.gov/pub/irs-access/f8823_accessible.pdf | PDF accessible (128 KB) | Blank | 4 (metadata) | Building ID, noncompliance codes, dates, agency info | Code tables | verified (loads) | US federal |
| HUD MTSP FY2026 income limits (CA HCD copy, "2026 MTSP regular limits") | California HCD | https://www.hcd.ca.gov/sites/default/files/docs/grants-and-funding/2026-mtsp-regular-limits.pdf | PDF (713 KB), table | Data | not counted | Income limits by household size | Printed-table income limits | verified (loads); table not readable here | State public document |

---

## 4. LIHTC: state agency forms and documents

| Document | Issuer | Verified link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| Tenant Income Certification (rev. 11/2025) | Indiana Housing and Community Development Authority (IHDA) | https://www.ihda.org/wp-content/uploads/2025/11/Tenant-Income-Certification-11-2025-FINAL.pdf | Fillable PDF (text fields) | Blank form (per title) | not counted | Household members, income by source, assets, signatures | Fillable TIC with a companion instructions section | verified (loads) | State public document |
| Tenant Income Certification (2024) | South Carolina Housing | https://www.schousing.sc.gov/sites/schousing/files/Documents/Development/Manuals%20and%20Forms/Tenant-Income-Certification-FINAL-2024.pdf | PDF | Blank form (per title) | 2 (metadata) | Program checkboxes (LIHTC, HOME), household rows | Short, checkbox-heavy, multi-program | verified (loads) | State public document |
| Tenant Income Certification, NJ compliance form | NJ DCA / HMFA | https://www.nj.gov/dca/hmfa/developers/docs/lihtc/compliance/compliance_forms/tc_comp_tenant_income_cert.pdf | PDF (653 KB), scanned / OCR'd (Acrobat paper capture) | Blank form (per title) | not counted | Household, income, verification source | OCR-quality test on a scanned form | verified (loads) | State public document |
| Tenant Income Certification, Louisiana (HOTMA-era) | Louisiana Housing Corporation (LHC) | https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Compliance/HOTMA%20Forms/Tenant%20Income%20Certification.pdf | PDF (220 KB) | Blank form (per title) | 2 (metadata) | Household, gross income, assets | Compact HOTMA form | verified (loads) | State public document |
| Tenant Income Certification, New York City (TIC form, HPD) | NYC Dept. of Housing Preservation and Development | https://www.nyc.gov/assets/hpd/downloads/pdfs/services/TIC-form.pdf | PDF (85 KB), spreadsheet-exported, no fillable fields | Blank form (per title) | 2 (metadata) | Household, income, unit | Non-fillable spreadsheet-style form, tests table reconstruction | verified (loads) | City public document |
| Tenant Income Certification and Directions (2024) | NYS Homes and Community Renewal (HCR) | https://hcr.ny.gov/tenant-income-certification-and-directions-2024 | PDF (336 KB); the page URL serves the PDF | Blank form (per title) | not counted | Development data, household, gross income, owner signature block | NY state form with directions | verified (loads) | State public document |
| Annual Household Self-Certification, LIHTC (Idaho Housing) | Idaho Housing and Finance Association | https://www.idahohousing.com/documents/lihtc-annual-tenant-income-self-certification.pdf | Fillable PDF (1.8 MB), 1 page (metadata) | Blank form (per title) | 1 (metadata) | Household, income, certification | Short fillable self-cert | verified (loads) | State public document |
| LURA sample (Extended Low-Income Housing Commitment), 24 pages | Colorado Housing and Finance Authority (CHFA) | https://www.chfainfo.com/getattachment/65a277c7-954c-4ca9-840d-c3df67c11c44/LURA-sample.pdf | PDF (353 KB), no AcroForm | Unknown, may be a template with brackets | 24 (metadata) | Parties, property description, Extended Use Period, definitions | Long legal document for section-heavy extraction. Blank-vs-filled not confirmed, so it is excluded from v1. | verified (loads) | State public document |

---

## 5. Eval set v1 (18 documents: verified-load, with form identity confirmed from title or metadata)

| # | Document (section ref) | Program | Why | Ground truth to hand-label |
|---|---|---|---|---|
| 1 | HUD-52641 HAP contract, 2023 (rhanc.gov) | HCV | Clean multi-part contract | Contract number, owner name field, unit address, contract rent, dates, signature fields |
| 2 | HUD-52641 complete, Parts A/B/C (Tarrant County) | HCV | Full contract in one file | Same as #1, plus tenancy addendum terms |
| 3 | HUD-52530B Part 1 (11 pages) | PBV | Multi-page, exhibits | Contract number, effective date, term, exhibit list |
| 4 | HUD-52530A PBV new construction (fillable) | PBV | Fillable, different from 52530B | Header fields, unit list |
| 5 | Montgomery HOC Utility Allowance 2026 | HCV | Dense table | Each allowance cell for 0 to 3 BR rows, one building type |
| 6 | HUD-9834 Management and Occupancy Review | PBRA | Addenda and checkboxes | Section headers, checkbox states |
| 7 | HUD-52670 voucher (TRACS 202D family) | PBRA | Numbered fields, 1 page | Project number, unit counts 6a to 6e, voucher amounts 9 to 10 |
| 8 | HUD-50059 owner certification (2014 edition) | PBRA | Core multifamily cert (obsolete edition) | Header, unit, rent, subsidy, TTP, signatures |
| 9 | HUD-52697 LIHTC Tenant Data (2022 metadata title) | LIHTC | Coded federal fields | Coded value for each household field |
| 10 | HUD-52517 RFTA (SFHA copy) | HCV | Fillable checkboxes | Family, unit, rent, owner, dates |
| 11 | IRS Form 8609 (Rev. Dec 2021) | LIHTC | Tax form, checkboxes, BIN | BIN, allocation dates, credit percentages |
| 12 | IRS Form 8823 (accessible, 4 pages) | LIHTC | Noncompliance code tables | Building ID, codes, dates |
| 13 | IRS Form 8586 (Rev. Dec 2023) | LIHTC | Short numeric tax form | Credit line items |
| 14 | IHDA Indiana TIC (11/2025, fillable) | LIHTC | Current fillable TIC | Household count, income by source, dates, signatures |
| 15 | SC Housing TIC (2024, 2 pages) | LIHTC | Program checkboxes | LIHTC checkbox, household rows, income total |
| 16 | NJ HMFA TIC (OCR'd scan) | LIHTC | OCR quality test | Same as #16, plus OCR error rate |
| 17 | LHC Louisiana TIC (2 pages) | LIHTC | Compact HOTMA form | Household, gross income, assets |
| 18 | CA HCD 2026 MTSP regular limits (PDF table) | LIHTC | Printed income table | Limits for 30, 50, 60 percent by household size, one area |

Dropped from v1 because form identity or blank status could not be read from the file (identity from search only): HUD-52580 HQS checklist and HUD-9626 OCAF letter template (both still in the main tables), and HUD-9639 renewal contract. Also dropped on purpose: NYC TIC, NYS HCR TIC, Idaho self-cert and the CHFA LURA (verified to load, but their blank-vs-filled status is not confirmed or they are not the best use of v1 slots). They remain available for a v2 set. Also dropped: the Tucson HAP example, the TDHCA S811 sample tenant file and filled HQS checklists, all of which are on the PII list.

### Building synthetic filled versions of blank forms

1. Download the blank form to a scratch directory outside the repo. Do not commit it.
2. Where AcroForm fields exist (50059, 52530A, 9834, 52517, IHDA TIC, Idaho self-cert), fill them with fictional values using pypdf, then flatten to a second PDF.
3. For non-fillable forms (HQS 52580, NYC TIC, the NJ scan), overlay fictional text at field coordinates with reportlab, or use the DOCX variant if one exists.
4. Use obviously fake names and addresses, fake SSN-format strings (never a real or valid-looking SSN), and invented contract numbers.
5. Label every synthetic file with its source form, edition, and that it is synthetic. Keep fixtures in `backend/tests/` or `backend/benchmark_data/demo_deal/` per CLAUDE.md.
6. Compare each synthetic layout to the real form: field order, table columns, section headers, and differences recorded in a checklist.

---

## Needs a human PII check before use

These are not in v1. Each may contain real personal data, or we could not tell whether it is blank or filled. No details are recorded here.

| Document | Link | Reason |
|---|---|---|
| City of Tucson HAP contract example | https://www.tucsonaz.gov/files/sharedassets/public/v/1/hcd/s8-landlords/hap_contract-example.pdf | Blank or filled unknown; text not readable here |
| TDHCA Section 811 PRA sample tenant file | https://www.tdhca.texas.gov/sites/default/files/section-811-pra/docs/S811-SampleTenantFile.pdf | Described as a sample, but its contents were not checked |
| Filled HQS (52580) checklists from PHAs: Macon (GA), Montana Commerce, Kentucky DLG, Pennsylvania DCED, NYC HRA, Reading (PA) | e.g. https://www.maconhousing.com/mha/forms/hud_52580-sampleandexceptionstds.pdf ; https://commerce.mt.gov/_shared/housing/Rental-Assistance/Inspection-Checklist.pdf | Mixed blank and filled; possible real addresses |
| MOR review files from state agency pages (landing pages only, not opened) | https://www.schousing.sc.gov/business-and-community-partners/management-and-occupancy-reviews ; https://www.chfainfo.com/rental-housing/asset-management/section8/management-and-occupancy-review | Pointers to real review files, not opened |

---

## Leads to check by hand (not verified)

Found in search results or fetch attempts that failed. Not in the main tables or in v1.

**Fetch failed (404, 403, cert error, or denied):**
- HUD-50058 family report (2024): https://www.hud.gov/sites/dfiles/PIH/documents/50058_Family_Report-2024_9-29-23.pdf and https://www.hud.gov/sites/documents/50058.pdf (both 404). Also 50058 instructions https://www.hud.gov/sites/documents/50058i.pdf (not fetched).
- TRACS MAT user guide (matchap02): https://hud.gov/sites/documents/matchap02.pdf (404). TRACS Chapter 2 MAT draft (2023): https://www.hud.gov/sites/dfiles/Housing/documents/Chapter_2_Understanding_the_MAT_Post2_Draft_V1_05252023.pdf (fetch denied by the auto-mode classifier this session, not retried).
- Montgomery HOC Utility Allowance 2025: https://www.hocmc.org/wp-content/uploads/2025/05/Utility-Allowance-Schedules-2025.pdf (404).
- Section 8 Renewal Guidebook (March 2023): https://www.hud.gov/sites/dfiles/Housing/documents/Section_8_Renewal_Guidebook-%20March_2023.pdf (404). Earlier 2017 edition via nhlp.org (not fetched).
- MSHDA compliance forms (TIC, PDF and Word dated 01/24): https://www.michigan.gov/mshda/rental/property-managers/compliance/compliance-forms (403).
- Arizona LURA amendment template: https://housing.az.gov/sites/default/files/2024-08/%5BTemplate%5D%20Amendment%20to%20LURA%20-%20LIHTC%20%26%20Bond%20%284-6-20%29%20_0.pdf (403).
- Georgia DCA HOTMA TIC (02/29/2024): https://www.dca.ga.gov/sites/default/files/hotma_tic_2024-1.pdf (TLS certificate mismatch on www.dca.ga.gov; try dca.georgia.gov).
- CTCAC Form 8823 copy under appendix 4: https://www.treasurer.ca.gov/CTCAC/compliance/manual/appendix4/8823.pdf (404). Use IRS 8823 above.
- Tenant Income Certification, CTCAC (TIC, Jan 2025): https://www.treasurer.ca.gov/ctcac/compliance/tic.pdf ; CTCAC HOTMA TIC: https://www.treasurer.ca.gov/CTCAC/compliance/hotma_tic.pdf ; CTCAC compliance manual: https://www.treasurer.ca.gov/CTCAC/compliance/manual/manual.pdf (not fetched).
- HUD-9887 / 9887-A consent package (Word): https://hud.gov/sites/dfiles/Housing/documents/9887%20%26%209887A.docx (not fetched). A fillable PDF 9887.pdf is listed under OMB 2501-0014 at omb.report (not fetched).
- HUD-52517 at hud.gov (404 on guessed path). Use the SFHA copy above.
- HUD-52641-A tenancy addendum: no hud.gov URL confirmed (file name 52641-a.pdf per OMB listing).
- HUD-52530C PBV tenancy addendum: listed in a Feb 2026 OMB listing (https://omb.report/icr/202602-2577-002/ic/27839), no direct URL.
- HUD-52670-A Part 1 (09/2008): https://www.hud.gov/sites/documents/52670a-1.pdf (not fetched).
- HUD-52530B Part 2: https://www.hud.gov/sites/dfiles/OCHCO/documents/52530BPt2.pdf (not fetched); NYC HPD 52530B Part 1 (04/2023): https://www.nyc.gov/assets/hpd/downloads/pdfs/services/hud-52530B_Pt1.pdf (not fetched).
- HUD-52670 instructions: https://www.hud.gov/sites/documents/52670ins.doc (not fetched).
- 50059 DOCX templates: https://hud.gov/sites/dfiles/Housing/documents/50059.docx (not fetched).
- Texas HOTMA TIC: https://www.tdhca.texas.gov/sites/default/files/pmcdocs/HOTMA-IncomeCer.pdf and DOCX variant (not fetched). TDHCA annual eligibility instructions: https://www.tdhca.texas.gov/sites/default/files/pmcdocs/AnnualEligibilityCertificationInst.pdf (not fetched).
- Indiana/Mass.: MHDC AHAP-360 TIC: https://mhdc.com/media/fwbl2uop/ci_ahap-360_tenant_income_certification_06032024.pdf (not fetched). Delaware DSHA TIC (2026): https://www.destatehousing.com/wp-content/uploads/2026/06/Tenant-Income-Certification.pdf (not fetched). North Dakota annual self-cert: https://www.ndhfa.org/wp-content/uploads/2025/05/LIHTCAnnualHouseholdSelf-Certification.pdf (not fetched).
- Louisiana HUD LIHTC Tenant Data form (exp 10/31/2025): https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Compliance/HUD%20Reporting%20for%20LIHTC/HUD%20LIHTC%20Tenant%20Data%20Collection%20Form%20(exp%2010-31-2025).pdf (fetch denied by classifier this session, not retried).
- Florida Housing TIC-1: not found. Appendix R completion guide: https://floridahousing.org/docs/default-source/developers-and-property-managers/compliance/forms/compliance-guidebook/090_appendix_r_-_tenant_income_certification_completion_(8-2016).pdf?sfvrsn=2 (not fetched).
- OHFA: forms page https://ohiohome.org/compliance/forms.aspx (not fetched; lists PC-E01, PC-E03, PC-E05, PC-E42 tenant file forms).
- Georgia DCA: 2022 recommended TIC https://www.dca.ga.gov/sites/default/files/recommendedtic.2022.pdf (not fetched); 2016 LIHTC compliance manual https://dca.georgia.gov/document/manuals/2016lihtccompliancemanualpdf/download (not fetched).
- Arizona/Minnesota/Illinois LURA-related: IHDA "Decoding Regulatory Agreements" training https://www.ihda.org/wp-content/uploads/2026/03/Decoding-Regulatory-Agreements-and-Other-Legal-Documents.pdf (not fetched); MHDC EUP-4 notice of change of ownership https://mhdc.com/media/hn0jbjk2/exhibit_eup-4_notice_change_of_ownership.pdf (not fetched); Georgia DCA extended use notification policy https://dca.georgia.gov/document/document/extended-use-period-eup-notification-policy/download (not fetched).
- MTSP Excel files: HUD User page https://www.huduser.gov/portal/datasets/mtsp.html (loaded but text empty on fetch); Atlanta FY2026 limits: https://www.atlantaga.gov/home/showpublisheddocument/70068/639208304929270000 (not fetched).
- Utility allowance PHA PDFs not fetched: Berkeley HA 2025 https://bha.berkeleyca.gov/sites/default/files/legislative-body-meeting-attachments/BHA%2010%2016%2025%20Item%2010B%20Attachment%204%20Berkeley%2C%20CA_HCV%20Utility%20Allowances_2025.pdf ; Gary Housing 2025 (single-family and multi-family) ; Kenosha 2026 ; Santa Fe County 2025 ; Louisiana SWIDE SF ; Mass. HAC low-rise 2026.
- NSPIRE sample (vendor): https://propertyinspect.com/sample-reports/nspire-unit-pre-inspection-lite/ (not fetched; commercial).
- HOTMA worksheets: no HUD Exchange sample worksheet with worked calculation found. Secondary sources only (NAHRO participant guide; Pinellas handout; Ohio resident fact sheet).
- Georgia DCA preliminary audit checklist (rent roll fields): https://dca.georgia.gov/document/forms/preliminary-audit-checklist/download (not fetched).
- Vendor/third-party copies (Novoco, pdfFiller, gocodebook, procorem): not fetched; not authoritative.

**Searched, nothing usable found:**
- HUD-9887 PDF on hud.gov (only docx and state copies).
- HUD-92458 blank or filled exemplar (only the 9626 letter template, above).
- Filled PBRA renewal HAP contracts or OCAF letters with real figures.
- TRACS MAT10/MAT30 sample records (only older guides and error appendices).
- EMMA official statements with rent rolls (only Louisiana LHC board resolutions, not fetched).
- MSHDA, OHFA, Georgia DCA TIC as current PDFs (leads above).
- Florida TIC-1 PDF.
- LURA templates from MSHDA, WSHFC, Texas (not searched).
- IRS Form 8609 Schedule A: superseded by Form 8609-A (2006 instructions say so).

---

## Licensing note

- **US federal works** (HUD forms, HUD handbooks, HUD MTSP data, IRS forms) are not copyrighted in the US under 17 USC 105 ("Subject matter of copyright: United States Government works"), so they are public domain in the US. Third-party copies (Novoco, pdfFiller, gocodebook, Property Inspect) are not federal works. Use original agency copies where possible.
- **State HFAs and state agencies** (IHDA, SC Housing, NJ DCA, LHC, NYS HCR, Idaho Housing, CHFA, TDHCA, MSHDA, DCA Georgia, OHFA): public documents with no login, but not necessarily public domain. Check each agency's terms before redistribution. For internal evals, keep attribution and keep the files out of the repo.
- **City and county PHAs** (Montgomery HOC, Rhode Island Housing copy, Tarrant County, SFHA, NYC HPD, Tucson, Berkeley, Gary, Kenosha): public records. Check for real personal data before use.
- **Vendor samples** (Property Inspect, pdfFiller): commercial. Check terms before reuse.

---

## Sources (verified-load URLs in this pass)

- https://www.hud.gov/sites/documents/50059.pdf ; https://www.hud.gov/sites/documents/50059-a.pdf ; https://www.hud.gov/sites/documents/50059ins.doc
- https://www.hud.gov/sites/documents/52670.pdf
- https://rhanc.gov/wp-content/uploads/2025/01/HUD-52641_2023_HAP_CONTRACT.pdf
- https://www.tarrantcountytx.gov/content/dam/main/housing-assistance/Documents/HUD-52641CompleteHAPContract_Parts%20A_B_C-EXP04-30-2026.pdf
- https://www.hud.gov/sites/dfiles/OCHCO/documents/52530Bpt1.pdf ; https://www.hud.gov/sites/dfiles/OCHCO/documents/52530A_PBV.pdf
- https://www.hud.gov/sites/dfiles/OCHCO/documents/52580.pdf
- https://www.hud.gov/sites/documents/9834.pdf
- https://sfha.org/files/documents/52517ENG.pdf
- https://www.hud.gov/sites/dfiles/OCHCO/documents/9639.pdf
- https://hud.gov/sites/dfiles/OCHCO/documents/9626.pdf
- https://hud.gov/sites/dfiles/PIH/documents/NSPIRE_Inspection_Protocol_Guide.pdf
- https://hud.gov/sites/documents/43503a-tochsgh.pdf ; https://www.hud.gov/sites/documents/43503e-tochsgh.pdf
- https://www.hocmc.org/wp-content/uploads/2025/05/Utility-Allowance-Schedules-2026.pdf
- https://www.hud.gov/sites/dfiles/OCHCO/documents/52697.pdf
- https://www.irs.gov/pub/irs-pdf/f8609.pdf ; https://www.irs.gov/pub/irs-access/f8609a_accessible.pdf ; https://www.IRS.GOV/pub/irs-access/f8586_accessible.pdf ; https://www.irs.gov/pub/irs-access/f8823_accessible.pdf
- https://www.hcd.ca.gov/sites/default/files/docs/grants-and-funding/2026-mtsp-regular-limits.pdf
- https://www.ihda.org/wp-content/uploads/2025/11/Tenant-Income-Certification-11-2025-FINAL.pdf
- https://www.schousing.sc.gov/sites/schousing/files/Documents/Development/Manuals%20and%20Forms/Tenant-Income-Certification-FINAL-2024.pdf
- https://www.nj.gov/dca/hmfa/developers/docs/lihtc/compliance/compliance_forms/tc_comp_tenant_income_cert.pdf
- https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Compliance/HOTMA%20Forms/Tenant%20Income%20Certification.pdf
- https://www.nyc.gov/assets/hpd/downloads/pdfs/services/TIC-form.pdf
- https://hcr.ny.gov/tenant-income-certification-and-directions-2024
- https://www.idahohousing.com/documents/lihtc-annual-tenant-income-self-certification.pdf
- https://www.chfainfo.com/getattachment/65a277c7-954c-4ca9-840d-c3df67c11c44/LURA-sample.pdf
- https://www.hud.gov/sites/documents/50059ins.doc (above)
- 17 USC 105: https://www.law.cornell.edu/uscode/text/17/105
