# Public sample documents for extraction evals: affordable housing (Section 8, LIHTC)

**Dated:** 2026-10-19
**Scope:** Public, no-login sample documents for testing AI extraction (lease abstraction, rent roll validation). Research only. No documents were saved to the repo.

## How to read the status column

- **reachable 2026-10-19**: WebFetch returned HTTP 200 with a PDF/file body. Our fetch tool cannot decode the compressed PDF text, so for PDFs this only proves the file loads. Field lists and form numbers marked "metadata/search" come from PDF metadata or search snippets, not from reading the page. Confirm by opening the file locally before writing ground truth.
- **could not verify**: 404 at the URL tried, or not reachable.
- **not verified**: found in search results only; not fetched.

## Important caveats found during verification

1. **The hud.gov "50059" PDFs may not be HUD-50059.** `https://www.hud.gov/sites/documents/50059.pdf` and `.../50059-a.pdf` both load as blank fillable forms, but their field names (SubsidyType, TTP, EIV indicator, move-out code, Tenant Signed / Owner Signed) look like the HUD-50058 family report, not the owner certification. A search snippet also describes the 06/2014 50059 as "For Personal Records ONLY." Open these before using them as 50059 layout references. Our synthetic 50059s should be checked against the real 50059 layout, not these URLs alone.
2. **Several HUD forms are only reachable under `dfiles/OCHCO/documents/`.** Guessed `hud.gov/sites/documents/` paths for 52641, 52670, 52530A/B, 52517 and 52580 returned 404. Use the paths listed below.
3. **Editions are stale.** Many copies carry expired OMB dates (2016, 2019, 2022, 2026). Use only as layout references and label the edition in our fixtures.
4. **WebFetch cannot read PDF text.** Any page-count or field claim below marked "metadata" should be re-checked with `pdfinfo` / `pdftotext` on a local copy. Do not download into the repo. Save to a scratch directory outside the repo.

---

## 1. HUD Section 8 / Housing Choice Voucher (HCV)

| Document | Issuer | Link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| HUD-50059 Owner's Certification of Compliance (06/2014 copy) | HUD | https://www.hud.gov/sites/documents/50059.pdf | Fillable PDF (AcroForm), 1 to 3 pages | Blank | 3 (metadata) | Project/contract header, unit, rent, subsidy, signatures | Good form-field test. **Field names look like 50058 family, see caveat 1.** | reachable 2026-10-19 (metadata); identity uncertain | US federal work, public domain (17 USC 105) |
| HUD-50059-A (50059 addendum) | HUD | https://www.hud.gov/sites/documents/50059-a.pdf | Fillable PDF | Blank | 3 (metadata, uncertain) | Same family as 50059; check contents | Same caveat as 50059. | reachable 2026-10-19; identity uncertain | US federal work, public domain |
| HUD-50059 instructions (TRACS 202D, 06/2014) | HUD via WV Housing Dev Fund | https://www.wvhdf.com/wp-content/uploads/2018/06/Form-HUD-50059-Instructions-6.2014.pdf | PDF text (instructions) | n/a | not checked | Instruction text, not a form | Good for building field-definition ground truth for the 50059 | not verified (found in search) | Federal instructions, public domain; host is a state agency partner |
| HUD-50059 Word template (owner's certification) | HUD | https://hud.gov/sites/dfiles/Housing/documents/50059.docx | DOCX | Blank template, marked "not for submission" | n/a | Same as 50059 | Non-PDF format test (DOCX parsing) | not verified (search result) | US federal, public domain |
| HUD-52641 HAP contract, Parts A/B/C (2023 edition) | HUD form; Rhode Island Housing Authority copy | https://rhanc.gov/wp-content/uploads/2025/01/HUD-52641_2023_HAP_CONTRACT.pdf | PDF, Ghostscript re-saved, 4 pages (metadata) | Blank | 4 (metadata) | Contract number, owner, unit, rent to owner, contract dates, signatures | Clean, multi-page contract with signature blocks. Good for part-to-part structure. | reachable 2026-10-19 | Federal form, public domain; PHA copy is public |
| HUD-52641 complete HAP contract, Parts A/B/C (exp. 04/30/2026) | Tarrant County (TX) Housing Assistance | https://www.tarrantcountytx.gov/content/dam/main/housing-assistance/Documents/HUD-52641CompleteHAPContract_Parts%20A_B_C-EXP04-30-2026.pdf | PDF, about 13 pages (metadata) | Blank | ~13 | Contract header, rent, dates, tenancy addendum terms | Full contract in one file, long multi-page. Expired OMB date, so use as a layout reference only. | reachable 2026-10-19 | Federal form, public domain |
| HUD-52641 HAP contract 2023 (Part A) | Tarrant County, TX | https://devweb65.tarrantcountytx.gov/content/dam/main/housing-assistance/Documents/HUDForm-52641_HAPContract_Part-A_EXP04-30-2026.pdf | PDF | Blank | not checked | Part A header fields | Part-by-part split file | not verified (search result) | Federal form |
| HUD-52641 HAP contract 2023 | Home Forward (Portland, OR) | https://homeforward.org/wp-content/uploads/2025/03/HUD-52641-HAP-Contract-2023.pdf | PDF | Blank | not checked | Same as above | Second 2023 edition copy for cross-check | not verified (search result) | Federal form |
| HAP contract example (2015 era, filled?) | City of Tucson, AZ | https://www.tucsonaz.gov/files/sharedassets/public/v/1/hcd/s8-landlords/hap_contract-example.pdf | PDF, about 1.1 MB, possibly 13 pages | Unknown: could not confirm whether filled | ~13 (metadata) | If filled: owner, tenant, rent, dates | Only example we found that might be filled in. **Check for real tenant names before use (CLAUDE.md: no PII).** | reachable 2026-10-19; blank vs filled unknown | US city document; public record; PII check required |
| HUD-52641-A Tenancy Addendum | HUD | Listed at OMB info-collection page; URL not confirmed (file name 52641-a.pdf) | PDF | Blank | n/a | Tenancy addendum terms | Complements the 52641 contract | could not verify (no direct hud.gov URL found) | Federal form |
| HUD-52517 Request for Tenancy Approval (RFTA) | HUD | Guessed https://www.hud.gov/sites/documents/52517.PDF returned 404 | PDF | Blank | n/a | Family, unit address, rent, owner, dates | Standard checkbox and table form | could not verify (404 on guess; search not run) | Federal form |
| HUD-52670 family (Housing Owner's Certification / voucher; Part 1, Part 2) | HUD | https://www.hud.gov/sites/documents/52670.pdf (1 page, metadata) and 52670-A Part 1 https://www.hud.gov/sites/documents/52670a-1.pdf (09/2008 edition) | Fillable PDF | Blank | 1 (52670); unknown for 52670-A | Project number, contract number, unit counts, voucher amounts, signatures | Table-heavy voucher form. The 52670 file's embedded title says HUD52670-202D (TRACS). | reachable 2026-10-19 (52670); 52670-A not verified | Federal, public domain |
| HUD-52670 Part 1, Part 2, Part 3 instructions | HUD | https://www.hud.gov/sites/documents/52670ins.doc (05/2014); https://www.hud.gov/sites/documents/52670a1-ins.doc (09/2009); https://www.hud.gov/sites/documents/52670a3-ins.doc (05/2014) | DOC (Word) | n/a | n/a | Instruction text | Non-PDF test; good for ground-truth field definitions | not verified (search result) | Federal, public domain |
| HUD-52667 Utility Allowance Schedule (04/2023) | HUD template, used by PHAs | Example PHA copies: Montgomery County, MD https://www.hocmc.org/wp-content/uploads/2025/05/Utility-Allowance-Schedules-2025.pdf (fetch returned 404 on 2026-10-19; search snippet only, could not verify). Berkeley HA https://bha.berkeleyca.gov/sites/default/files/legislative-body-meeting-attachments/BHA%2010%2016%2025%20Item%2010B%20Attachment%204%20Berkeley%2C%20CA_HCV%20Utility%20Allowances_2025.pdf | PDF tables | Filled (real allowance tables, no personal data) | not checked | Utility type by bedroom count, dollar amounts | Table-heavy grids, many columns and bedroom sizes. Best table test available. Same HUD template, different PHAs. | Montgomery could not verify (404 on fetch). Berkeley not verified. | Federal template; PHA publications are public records |
| HUD-52580 HQS / Housing Quality Standards inspection checklist (04/2023) | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52580.pdf | PDF checklist, multi-page checkboxes | Blank | not checked | Item pass/fail checkboxes, inspector notes | Checkbox-heavy, good for checkbox detection. Older 3/2001 copy at https://www.hud.gov/sites/documents/hqsinspectionchklist.pdf (outdated). | not verified (search result on dfiles path) | Federal, public domain |
| HUD-52580 HQS checklist, filled examples | Kentucky DLG, PA DCED, Montana Commerce, NYC HRA, Macon (GA) Housing | e.g. https://www.maconhousing.com/mha/forms/hud_52580-sampleandexceptionstds.pdf; https://commerce.mt.gov/_shared/housing/Rental-Assistance/Inspection-Checklist.pdf | PDF | Mixed; several may be filled | not checked | Checkboxes, notes, inspector signature | Real-world varied layouts from different agencies; check whether any are filled with real addresses | not verified | State/local public records; PII check needed |
| HUD-9887 / 9887-A tenant consent forms | HUD | not found in search | n/a | n/a | n/a | n/a | Not found | could not verify (no search hit) | n/a |
| HUD-9834 Management and Occupancy Review (06/2016) | HUD | https://www.hud.gov/sites/documents/9834.pdf | Fillable PDF, about 1.1 MB, AcroForm | Blank | not checked | Review items, desk review, on-site review, addenda | Multi-part multi-addenda form. Good for section-navigation tests. | reachable 2026-10-19 (form ID from search snippet) | Federal, public domain |
| HUD-92458 / OCAF notice | HUD | not found | n/a | n/a | n/a | n/a | Not found | not searched | n/a |
| NSPIRE Inspection Protocol Guide | HUD PIH | https://hud.gov/sites/dfiles/PIH/documents/NSPIRE_Inspection_Protocol_Guide.pdf | PDF, 20 pages, tagged, has images | n/a (guide, not form) | 20 (metadata) | Not an extraction target; useful for NSPIRE deficiency categories | Guide, not a form; use to build NSPIRE deficiency taxonomy for our synthetic reports | reachable 2026-10-19 | Federal, public domain |
| NSPIRE sample inspection report (official HUD) | HUD | not found | n/a | n/a | n/a | n/a | No official sample found; vendor sample only: Property Inspect "NSPIRE Unit Pre-Inspection Lite" https://propertyinspect.com/sample-reports/nspire-unit-pre-inspection-lite/ (5 pages, commercial, not verified) | could not verify (official) | Vendor sample; check terms before reuse |

**Section 8 notes:** The PBRA-specific HAP contract and renewal guide exhibits, TRACS MAT sample records, and HUD Handbook 4350.3 worked examples were searched only in part. The Handbook 4350.3 exhibit table of contents (https://www.hud.gov/sites/documents/43503e-tochsgh.pdf, 2013 edition, metadata only) and the Exhibit 3-4 family summary sheet (https://www.hud.gov/sites/documents/doc_35685.pdf, REV-1 6/07) were found in search but not verified by fetch.

---

## 2. Project-Based Voucher (PBV)

| Document | Issuer | Link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| HUD-52530B PBV HAP contract for existing housing, Part 1 (07/2019, copy) | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52530Bpt1.pdf | PDF, 11 pages (metadata) | Blank | 11 | Contract number, units, exhibits list, effective date, term | Multi-page contract with exhibits. Good for effective-date and term extraction. | reachable 2026-10-19 (11 pages per metadata) | Federal, public domain |
| HUD-52530B PBV HAP contract, Part 2 (existing housing) | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52530BPt2.pdf | PDF | Blank | not checked | Definitions and general terms | Long legal text, cross-references | not verified (search result) | Federal, public domain |
| HUD-52530B Part 1 (04/2023 edition) | NYC HPD | https://www.nyc.gov/assets/hpd/downloads/pdfs/services/hud-52530B_Pt1.pdf | PDF | Blank | not checked | Same as above, newer edition | Edition comparison test (2019 vs 2023) | not verified (search result) | NYC public document; federal form |
| HUD-52530A PBV HAP contract, new construction / rehab | HUD | https://www.hud.gov/sites/dfiles/OCHCO/documents/52530A_PBV.pdf | Fillable PDF (AcroForm) | Blank | not checked | Contract header, unit list, rent schedule | Fillable new-construction PBV contract, distinct from 52530B | reachable 2026-10-19 (form ID per search snippet) | Federal, public domain |
| HUD-52530C PBV tenancy addendum | HUD | Listed in Feb 2026 HUD information-collection listing (omb.report/icr/202602-2577-002/ic/27839); direct URL not confirmed | PDF | Blank | n/a | Tenancy addendum terms | Companion to 52530B/A | could not verify (no direct URL) | Federal |
| PBV utility allowance / voucher examples | PHA examples | see HUD-52667 entries above | PDF | n/a | n/a | n/a | Reuse the utility-table PDFs | see above | see above |

---

## 3. Project-Based Rental Assistance (PBRA) / Multifamily

| Document | Issuer | Link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| HUD-52670 voucher (owner billing; TRACS 202D family) | HUD | https://www.hud.gov/sites/documents/52670.pdf | Fillable, 1 page | Blank | 1 | Project/contract number, unit counts 6a to 6e, exceptions 7a to 7e, voucher amounts 9 to 10 | Dense numbered-field form, good for field-ID mapping. Metadata shows XLSX export. | reachable 2026-10-19 | Federal, public domain |
| HUD-9834 Management and Occupancy Review | HUD | https://www.hud.gov/sites/documents/9834.pdf | Fillable PDF | Blank | not checked | Review sections, checkboxes, comments | Good for checkbox and multi-addendum tests | reachable 2026-10-19 | Federal, public domain |
| HUD-9834 review sample (filled) | State agencies (e.g. SC Housing, CHFA) | Landing pages: https://www.schousing.sc.gov/business-and-community-partners/management-and-occupancy-reviews ; https://www.chfainfo.com/rental-housing/asset-management/section8/management-and-occupancy-review | Web pages (links to PDFs) | n/a | n/a | n/a | Pointers to real review files, not verified | not verified | State public records; check for PII |
| PBRA HAP contract / renewal contract templates (Section 8 Renewal Guide exhibits) | HUD | not searched | n/a | n/a | n/a | n/a | Not searched in this pass | not searched | n/a |
| OCAF / Operating Cost Adjustment Factor notice | HUD | not searched | n/a | n/a | n/a | n/a | Not searched in this pass | not searched | n/a |

---

## 4. LIHTC (Low-Income Housing Tax Credit)

### 4a. Federal forms

| Document | Issuer | Link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| HUD-52697 LIHTC Tenant Data Collection Form (OMB 2528-0320, exp. 10/31/2025) | HUD; LHC copy | https://www.hud.gov/sites/dfiles/OCHCO/documents/52697.pdf (404 on guessed path); Louisiana LHC copy: https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Compliance/HUD%20Reporting%20for%20LIHTC/HUD%20LIHTC%20Tenant%20Data%20Collection%20Form%20(exp%2010-31-2025).pdf | PDF | Blank | not checked | Household demographics, income, rent, unit data | Federal LIHTC reporting form, coded fields. Use the LHC copy. | hud.gov path 404; LHC copy not verified | Federal, public domain |
| HUD LIHTC Tenant Data Form 2019 (XML validate) | HUD via huduser | https://apps.huduser.gov/XMLValidate/docs/LIHTC-Tenant-Data-Form-2019.pdf | PDF | Blank | not checked | Same as 52697 | Older edition for comparison | not verified (search result) | Federal, public domain |
| IRS Form 8609, Low-Income Housing Credit Allocation and Certification (Rev. Dec 2021) | IRS | Metadata-confirmed copy: https://www.irs.gov/pub/irs-pdf/f8609.pdf (85 KB, Rev. December 2021). Current instructions: https://www.irs.gov/zh-hant/instructions/i8609 (12/2025) | PDF | Blank | not checked, metadata suggests 2 to 4 pages | BIN, allocation dates, credit percentages, owner info | Federal, public domain. Tests checkbox-heavy tax form. | reachable 2026-10-19 (IRS PDF metadata) | Federal, public domain (IRS forms, 17 USC 105) |
| IRS Form 8823, Low-Income Housing Credit Agencies Report of Noncompliance (Dec 2019 revision) | IRS | https://www.irs.gov/pub/irs-access/f8823_accessible.pdf | Accessible PDF, 4 pages (metadata) | Blank | 4 | Building ID, noncompliance codes, dates, agency info | Table of noncompliance codes. Good for code-table mapping. | reachable 2026-10-19 | Federal, public domain |
| IRS Form 8586 (Low-Income Housing Credit) | IRS | not searched | n/a | n/a | n/a | n/a | Not searched | not searched | n/a |
| HUD MTSP income limits (FY 2026, Excel) | HUD User | https://www.huduser.gov/portal/datasets/mtsp.html (page returned empty text) | Excel (XLSX) | Data tables, not forms | n/a | Area median income, 30 to 140 percent limits by household size | Excel with merged headers and multi-sheet structure: strong spreadsheet-parsing test. Effective date conflict: May 1 2026 (Novoco, MN Housing) vs April 1 2026 (Atlanta). | page reachable; file not decoded | Federal, public domain |
| HUD MTSP Income Averaging Data (FY 2026) | HUD User | https://www.huduser.gov/portal/datasets/mtsp.html | Excel | Data | n/a | Averaging rules, income limits | Second Excel file for layout comparison | page reachable; file not decoded | Federal |
| HCD California 2026 MTSP regular limits | California HCD | https://www.hcd.ca.gov/sites/default/files/docs/grants-and-funding/2026-mtsp-regular-limits.pdf | PDF, 713 KB, table | Data | not checked | Income limits by household size | Printed-table PDF for income limits (state variation) | reachable 2026-10-19 | State public document |

### 4b. State agency Tenant Income Certification (TIC) forms

| Document | Issuer | Link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| Tenant Income Certification, Indiana (rev. 11/2025) | IHDA | https://www.ihda.org/wp-content/uploads/2025/11/Tenant-Income-Certification-11-2025-FINAL.pdf | Fillable PDF (text fields, checkboxes, tables) | Blank | not checked | Household members, income by source, assets, signatures | Fillable TIC with a companion instruction section. Table and checkbox test. | reachable 2026-10-19 (fillable per metadata; content not decoded) | Indiana state publication; public |
| Tenant Income Certification, South Carolina (2024) | SC Housing | https://www.schousing.sc.gov/sites/schousing/files/Documents/Development/Manuals%20and%20Forms/Tenant-Income-Certification-FINAL-2024.pdf | PDF, 2 pages | Blank | 2 | Program checkboxes (LIHTC, HOME etc.), household info | Short, checkbox-heavy, multi-program form | reachable 2026-10-19 (2 pages per metadata) | State public document |
| Tenant Income Certification, New Jersey (compliance TIC) | NJ DCA / HMFA | https://www.nj.gov/dca/hmfa/developers/docs/lihtc/compliance/compliance_forms/tc_comp_tenant_income_cert.pdf | PDF, 653 KB, scanned or OCR'd (Acrobat paper capture) | Blank | not checked | Household, income, verification source | Scanned-with-OCR layout: strong OCR-quality test | reachable 2026-10-19 | State public document |
| Tenant Income Certification, Texas (HOTMA, rev. 11/25/2025) | TDHCA | https://www.tdhca.texas.gov/sites/default/files/pmcdocs/HOTMA-IncomeCer.pdf (also HOTMA-IncomeCert_1.pdf, and a DOCX at .../HOTMA-IncomeCert.docx) | PDF and DOCX | Blank | not checked | Household composition, income, demographics, owner signature | Post-HOTMA form; DOCX variant for format testing | not verified (search result) | State public document |
| TDHCA Annual Eligibility Certification instructions (rev. 04/29/2020) | TDHCA | https://www.tdhca.texas.gov/sites/default/files/pmcdocs/AnnualEligibilityCertificationInst.pdf | PDF, instructions | n/a | not checked | Instructions only | Instructions text for ground-truth field definitions | not verified (search result) | State public document |
| TDHCA Section 811 PRA sample tenant file | TDHCA | https://www.tdhca.texas.gov/sites/default/files/section-811-pra/docs/S811-SampleTenantFile.pdf | PDF | Possibly filled sample | not checked | Full tenant file: TIC, lease, recert | **Highest-value candidate if it is a sample with fictional data. Verify it has no real names before use.** | not verified (search result) | State public document; PII check required |
| Tenant Income Certification, California (CTCAC, Jan 2025 and Apr 2021 versions) | CTCAC / CA Treasurer | https://www.treasurer.ca.gov/ctcac/compliance/tic.pdf (not fetched); HOTMA version https://www.treasurer.ca.gov/CTCAC/compliance/hotma_tic.pdf (not fetched); compliance manual https://www.treasurer.ca.gov/CTCAC/compliance/manual/manual.pdf (not fetched) | PDF | Blank | not checked | Household info, income, Part IX demographic supplement | Supplemental-information part with opt-out text. Good for mixed field types. | not verified (search results only; the Form 8823 copy under appendix4 returned 404) | State public document; manual disclaims being legal authority |
| CTCAC Form 8823 copy (appendix 4) | CA Treasurer | https://www.treasurer.ca.gov/CTCAC/compliance/manual/appendix4/8823.pdf | PDF | Blank | n/a | n/a | Duplicates the IRS 8823 | 404 on fetch | State public document |
| TIC-1 Tenant Income Certification, Florida Housing | Florida Housing Finance Corp | Form not located as PDF. Completion guide Appendix R: https://floridahousing.org/docs/default-source/developers-and-property-managers/compliance/forms/compliance-guidebook/090_appendix_r_-_tenant_income_certification_completion_(8-2016).pdf?sfvrsn=2 | PDF (instructions) | n/a | n/a | Instructions only | Instructions for completing a TIC | Appendix R reachable per search only; TIC-1 not found | could not verify (TIC-1 PDF) | State public document |
| AHAP-360 Tenant Income Certification (MHDC, eff. 06/03/2024) | Massachusetts Housing Dev Corp (MHDC) | https://mhdc.com/media/fwbl2uop/ci_ahap-360_tenant_income_certification_06032024.pdf | PDF | Blank | not checked | TIC fields | Multi-program TIC, older than the Indiana and Texas forms | not verified (search result) | State public document |
| Tenant Income Certification, Delaware (DSHA, 2026 upload) | DSHA | https://www.destatehousing.com/wp-content/uploads/2026/06/Tenant-Income-Certification.pdf | PDF | Blank | not checked | TIC fields | Most recent edition found; updates the HUD 52697 data | not verified (search result) | State public document |
| Annual Household Self-Certification, North Dakota (04/2025) | NDHFA | https://www.ndhfa.org/wp-content/uploads/2025/05/LIHTCAnnualHouseholdSelf-Certification.pdf | PDF | Blank | not checked | Short self-cert | Short form, low extraction complexity baseline | not verified (search result) | State public document |
| Louisiana LHC HOTMA-era TIC | LHC | https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Compliance/HOTMA%20Forms/Tenant%20Income%20Certification.pdf | PDF, 2 pages (metadata) | Blank | 2 | Household, income, assets | Compact HOTMA form | reachable 2026-10-19 (2 pages per metadata) | State public document |

**Not found in this pass:** TIC forms from MSHDA (Michigan), OHFA (Ohio), Georgia DCA and WSHFC (Washington). Search returned none. Try each agency's compliance page directly.

### 4c. LIHTC rent, income, utility, and LURA documents

| Document | Issuer | Link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| Utility allowance schedules: Gary Housing (single-family and multi-family, 2025) | Gary Housing Authority | https://garyhousing.org/wp-content/uploads/sites/8/2025/07/2025-Allowances-Muli-Family.pdf ; https://garyhousing.org/wp-content/uploads/sites/8/2025/07/2025-Allowances-Single-Family.pdf | PDF tables | Filled data | not checked | Utility type by bedroom count | Two tables from same agency, different structure | not verified (search result) | Public PHA records |
| Utility allowance: Kenosha (2026), Santa Fe County (2025) | Kenosha Housing Authority; Santa Fe County | https://kenosha.org/Document%20Center/Departments/Housing%20Authority/Current%20Section%208%20Participant%20Resources/2026%20Utility%20Allowances%20-%20all.pdf ; https://housingnm.org/uploads/documents/Santa_Fe_County_2025.pdf | PDF | Filled data | not checked | Same | More state variation (NM, WI) | not verified (search result) | Public PHA records |
| Utility allowance: LHC Louisiana (SWIDE SF) | Louisiana Housing Corp | https://www.lhc.la.gov/hubfs/Document%20Libraries/Rental%20Opportunities/Utility%20Allowances/SWIDE%20SF.pdf | PDF | Filled data | not checked | Same | Louisiana variation | not verified (search result) | Public |
| Utility allowance: Massachusetts HAC low-rise 2026 and NHS Garden Row house 2026 | Mass. (state) | https://www.mass.gov/doc/hac-low-rise-2026/download ; https://www.mass.gov/doc/nhs-garden-row-house-or-low-rise-2026/download | PDF | Filled data | not checked | Same | Newer 2026 editions | not verified (search result) | State public document |
| Income limit tables: Atlanta MTSP FY 2026 | City of Atlanta | https://www.atlantaga.gov/home/showpublisheddocument/70068/639208304929270000 ; https://www.atlantaga.gov/home/showpublisheddocument/70066/639208304926230000 | PDF tables | Data | not checked | Limits by household size, 30 to 140 percent AMI | Real MTSP-derived limit tables from a city. Check the effective date. | not verified (search result) | City public document |
| LURA / extended use agreement templates | not searched | n/a | n/a | n/a | n/a | n/a | Not searched | not searched | n/a |
| LIHTC state QAP / compliance manuals | CTCAC manual (see 4b), others not searched | see 4b | PDF | n/a | n/a | n/a | Manual text, not forms | partially verified | State public documents; CTCAC disclaims legal authority |

**Louisiana board resolutions** (LHC, e.g. https://www.lhc.la.gov/hubfs/Document%20Libraries/Board%20Meeting%20Archives/2024/October/Resolutions/Resolution%20issuing%20$98M%20MHRB%20for%20The%20Batture%20Apartments%20located%20in%20New%20Orleans.pdf): public resolutions that include unit-mix tables, total units, development cost and funding sources. Not verified by fetch. Good for narrative and table extraction. Not rent rolls.

---

## 5. Rent rolls and bond documents

| Document | Issuer | Link | Format | Blank / filled | Pages | Fields to extract | Why it is a good test | Status | License |
|---|---|---|---|---|---|---|---|---|---|
| EMMA official statements for affordable bond deals | MSRB EMMA | not found in search | n/a | n/a | n/a | n/a | No EMMA official statement surfaced in search. Needs a targeted search on emma.msrb.org by issuer name. | could not verify | Public; verify no login needed |
| HUD 223(f) application exhibits (rent roll exhibits) | HUD | not searched | n/a | n/a | n/a | n/a | Not searched | not searched | n/a |

**Gap:** We did not find a public, filled-in affordable rent roll. Options: (a) EMMA official statements (manual search needed); (b) HFA board packets that include unit mix and rent tables; (c) our own synthetic rent rolls.

---

## Proposed eval set v1

Ordered by priority. Ground truth is what we would hand-label. "Synthetic counterpart" means the real public form used to check that our synthetic fixture has the same layout.

| # | Document | Program | Why | Ground truth to hand-label | Synthetic counterpart check |
|---|---|---|---|---|---|
| 1 | HUD-52641 HAP contract, 2023 (rhanc.gov copy) | HCV | Clean multi-part contract | Contract number, owner, unit address, contract rent, dates, signatures present | Our synthetic HCV HAP contract vs Parts A/B/C structure |
| 2 | HUD-52641 complete, Parts A/B/C (Tarrant County, exp. 2026) | HCV | Full contract, ~13 pages | Same as 1, plus Part C tenancy addendum terms | Page-break and part-boundary handling |
| 3 | HUD-52530B Part 1 (11 pages) | PBV | Multi-page, exhibits list | Contract number, effective date, term, exhibit list | Our synthetic PBV HAP contract |
| 4 | HUD-52530A PBV new construction (fillable) | PBV | Fillable form, distinct from 52530B | Contract header fields and unit list | Compare with synthetic PBV new construction |
| 5 | HUD-52667 utility schedule: Montgomery County (MD) | All | Dense table, many bedroom columns | Each allowance cell value for 2 to 3 bedroom rows | Table extraction in our rent logic |
| 6 | HUD-52667 utility schedule: Berkeley HA (CA) | All | Second PHA, different layout | Same | Cross-agency variation |
| 7 | HUD-52580 HQS checklist (dfiles/OCHCO, 04/2023) | HCV | Checkbox-heavy | Each pass/fail box and notes | Synthetic HQS report checkboxes |
| 8 | HUD-52580 filled PHA copy (Macon or Montana) | HCV | Real-world filled checklist (check for PII first) | Pass/fail per item, inspector and date | Real vs synthetic layout |
| 9 | HUD-9834 Management and Occupancy Review | PBRA | Multi-addendum, checkboxes | Section headers, checkbox states, comments | Our PBRA review fixtures (if any) |
| 10 | HUD-52670 (TRACS 202D) voucher | PBRA | Numbered fields, 1 page, dense | Project number, unit counts 6a to 6e, voucher amounts 9 to 10 | Our PBRA voucher or HAP register fixtures |
| 11 | Indiana (IHDA) TIC, rev. 11/2025 | LIHTC | Current fillable TIC | Household count, income by source, assets, dates, signatures | Our LIHTC TIC fixtures |
| 12 | South Carolina TIC, 2024 (2 pages) | LIHTC | Program checkboxes | LIHTC checkbox, household rows, income total | Compact baseline |
| 13 | New Jersey TIC (scanned/OCR'd) | LIHTC | OCR quality test | Same as 11, plus OCR error rate | No synthetic equivalent; use for OCR-quality eval |
| 14 | Texas HOTMA TIC (PDF and DOCX) | LIHTC | Post-HOTMA form, DOCX variant | Same as 11, DOCX table extraction | DOCX parsing path |
| 15 | HUD-52697 LIHTC Tenant Data Collection (LHC copy) | LIHTC | Coded federal fields | Coded values for each household field | Federal data field mapping |
| 16 | IRS Form 8609 (Rev. Dec 2021) | LIHTC | Tax form checkboxes and BIN | BIN, allocation dates, credit percentages, owner name and EIN | No synthetic counterpart; checkbox eval |
| 17 | IRS Form 8823 (accessible, 4 pages) | LIHTC | Code tables | Building ID, noncompliance codes, dates | Code-to-description mapping |
| 18 | HUD MTSP FY2026 income limits (Excel) | LIHTC | Spreadsheet, merged headers | Limits for 30, 50, 60, 80 percent by household size, one MSA | Excel parsing path |
| 19 | California HCD 2026 MTSP regular limits (PDF) | LIHTC | Printed income table | Same as 18, from PDF | PDF table parsing |
| 20 | Atlanta FY2026 limits (city PDF) | LIHTC | Local reproduction of MTSP | Same as 18, plus effective date | Cross-check against HUD Excel |
| 21 | TDHCA S811 sample tenant file (only if fictional) | PBRA / Section 811 | Full tenant file: TIC, lease, recert | Household data, rent, signatures | Compare with our 10-file 40-unit PBRA demo |
| 22 | HUD-50059 (after confirming it is not HUD-50058) | PBRA | Core owner certification | Header, unit, rent, subsidy, signatures | Our synthetic 50059s (direct layout check) |
| 23 | HUD Handbook 4350.3 Exhibit 3-4 family summary sheet | Occupancy | Blank grid, table | Empty grid structure only | Check our family summary fixtures |
| 24 | NSPIRE Inspection Protocol Guide (20 pages) | PBRA / HCV | Taxonomy source, not a form | Defect category names | Synthetic NSPIRE report categories |
| 25 | Montgomery or Berkeley utility schedule (filled) | HCV | Duplicate of 5 and 6 with different tables | Column alignment check | Table regression |

### How to make filled synthetic versions of blank forms

Use blank public forms (hud.gov, PHA copies) as the layout template. Fill them with fictional data from our generator, not real tenant data. Steps:

1. Download the blank form to a scratch directory outside the repo. Do not commit it.
2. Use the form's AcroForm fields where present (50059, 52530A, 9834, IHDA TIC, Louisiana TIC, Texas HOTMA TIC): write fictional values with pypdf, then flatten to a second PDF.
3. For non-fillable forms (HQS 52580, some state TICs), overlay fictional text at the field coordinates with reportlab, or fill a DOCX copy (Texas HOTMA DOCX).
4. Use fake names, addresses (e.g. 555-style numbers), SSN-format strings that are not real (000-00-0000 is invalid; use obviously fake values), and invented contract numbers.
5. Label every synthetic file with its source form, edition, and the fact that it is synthetic. Keep the fixtures in `backend/tests/` or `backend/benchmark_data/demo_deal/` only, per CLAUDE.md.
6. Compare each synthetic layout to the real form: same field order, same table columns, same section headers. Record any differences in a checklist.

---

## Licensing note

- **US federal works** (HUD forms, IRS forms, HUD MTSP data, HUD Handbook 4350.3): not copyrighted in the US under 17 USC 105 ("Subject matter of copyright: United States Government works"), so they are public domain in the US. Note that some third-party reproductions (Novoco, pdfFiller, gocodebook, Property Inspect) are not federal works. Use the original federal or agency copy.
- **State housing finance agencies and state agencies** (IHDA, SC Housing, NJ HMFA, TDHCA, CTCAC, DSHA, NDHFA, LHC, MHDC, Florida Housing): documents are public but not necessarily public domain. Usage terms vary by agency. Check each agency's website terms before republishing. For internal eval use, public availability without login is the working standard, but keep attribution and do not redistribute the files in the repo.
- **City and county PHA documents** (Tarrant County, Tucson, Berkeley, Montgomery, Gary, Kenosha, NYC HPD, Atlanta): public records. Check for real tenant names, addresses, or SSNs before use. Strip or replace any PII (CLAUDE.md).
- **Vendor samples** (Property Inspect, pdfFiller templates): commercial; check their terms before reuse. Use only as a reference for layout.
- **Louisiana board resolutions and EMMA official statements**: public records; EMMA requires no login but its terms of use apply.

---

## Gaps (could not find or verify publicly)

1. Official HUD sample NSPIRE inspection report.
2. Filled-in HUD-50059 or HUD-50058 with fictional data from HUD (none found). The Tucson HAP example is the only possibly filled sample, and its PII status is unknown.
3. HUD-9887 and HUD-9887-A tenant consent forms (no hits).
4. HUD-92458 / OCAF notice (not searched).
5. HUD-52517 RFTA (guessed URL 404; not searched).
6. HUD-52530C PBV tenancy addendum direct URL.
7. PBRA HAP and renewal contract templates from the Section 8 Renewal Guide (not searched).
8. HUD Handbook 4350.3 exhibits with filled sample calculations (only blank exhibits found).
9. HUD HOTMA worked examples on HUD Exchange (not found; search returned secondary sources only).
10. TRACS MAT sample records (not searched).
11. EMMA official statements with rent rolls (none found in search).
12. TIC forms from MSHDA (Michigan), OHFA (Ohio), Georgia DCA and WSHFC (Washington) (none found).
13. Florida Housing TIC-1 PDF (only completion guide found).
14. LURA / extended use agreement templates (not searched).
15. IRS Form 8586 (not searched).
16. Public 223(f) application exhibits with rent rolls (not searched).
17. Verification gap for all PDFs: WebFetch cannot decode PDF text, so page counts and field lists are from metadata. Open files locally (outside the repo) before writing ground truth.

---

## Sources

- HUD 50059 PDF: https://www.hud.gov/sites/documents/50059.pdf
- HUD 50059-A PDF: https://www.hud.gov/sites/documents/50059-a.pdf
- HUD 50059 instructions (WV Housing Development Fund copy): https://www.wvhdf.com/wp-content/uploads/2018/06/Form-HUD-50059-Instructions-6.2014.pdf
- HUD 52670 PDF: https://www.hud.gov/sites/documents/52670.pdf
- HUD 52670-A Part 1: https://www.hud.gov/sites/documents/52670a-1.pdf
- HUD 52530B Part 1: https://www.hud.gov/sites/dfiles/OCHCO/documents/52530Bpt1.pdf
- HUD 52530A PBV: https://www.hud.gov/sites/dfiles/OCHCO/documents/52530A_PBV.pdf
- HUD 52580 PDF: https://www.hud.gov/sites/dfiles/OCHCO/documents/52580.pdf
- HUD 9834 PDF: https://www.hud.gov/sites/documents/9834.pdf
- HUD 52697 (LHC copy): https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Compliance/HUD%20Reporting%20for%20LIHTC/HUD%20LIHTC%20Tenant%20Data%20Collection%20Form%20(exp%2010-31-2025).pdf
- HUD MTSP data page: https://www.huduser.gov/portal/datasets/mtsp.html
- HUD NSPIRE Inspection Protocol Guide: https://hud.gov/sites/dfiles/PIH/documents/NSPIRE_Inspection_Protocol_Guide.pdf
- HUD Handbook 4350.3 TOC: https://www.hud.gov/sites/documents/43503e-tochsgh.pdf
- Rhode Island Housing HAP 52641 (2023): https://rhanc.gov/wp-content/uploads/2025/01/HUD-52641_2023_HAP_CONTRACT.pdf
- Tarrant County HAP 52641: https://www.tarrantcountytx.gov/content/dam/main/housing-assistance/Documents/HUD-52641CompleteHAPContract_Parts%20A_B_C-EXP04-30-2026.pdf
- City of Tucson HAP example: https://www.tucsonaz.gov/files/sharedassets/public/v/1/hcd/s8-landlords/hap_contract-example.pdf
- Montgomery County MD UA schedule 2025: https://www.hocmc.org/wp-content/uploads/2025/05/Utility-Allowance-Schedules-2025.pdf
- Berkeley HA UA 2025: https://bha.berkeleyca.gov/sites/default/files/legislative-body-meeting-attachments/BHA%2010%2016%2025%20Item%2010B%20Attachment%204%20Berkeley%2C%20CA_HCV%20Utility%20Allowances_2025.pdf
- IRS Form 8609 metadata copy: https://www.irs.gov/pub/irs-pdf/f8609.pdf ; About Form 8609: https://www.irs.gov/ht/forms-pubs/about-form-8609
- IRS Form 8823 accessible: https://www.irs.gov/pub/irs-access/f8823_accessible.pdf
- IHDA TIC 11/2025: https://www.ihda.org/wp-content/uploads/2025/11/Tenant-Income-Certification-11-2025-FINAL.pdf
- SC Housing TIC 2024: https://www.schousing.sc.gov/sites/schousing/files/Documents/Development/Manuals%20and%20Forms/Tenant-Income-Certification-FINAL-2024.pdf
- NJ HMFA TIC: https://www.nj.gov/dca/hmfa/developers/docs/lihtc/compliance/compliance_forms/tc_comp_tenant_income_cert.pdf
- TDHCA HOTMA TIC: https://www.tdhca.texas.gov/sites/default/files/pmcdocs/HOTMA-IncomeCer.pdf
- TDHCA S811 sample tenant file: https://www.tdhca.texas.gov/sites/default/files/section-811-pra/docs/S811-SampleTenantFile.pdf
- CTCAC TIC and manual: https://www.treasurer.ca.gov/ctcac/compliance/tic.pdf ; https://www.treasurer.ca.gov/CTCAC/compliance/manual/manual.pdf
- Florida Housing Appendix R: https://floridahousing.org/docs/default-source/developers-and-property-managers/compliance/forms/compliance-guidebook/090_appendix_r_-_tenant_income_certification_completion_(8-2016).pdf?sfvrsn=2
- HCD California 2026 MTSP limits: https://www.hcd.ca.gov/sites/default/files/docs/grants-and-funding/2026-mtsp-regular-limits.pdf
- Louisiana LHC TIC: https://www.lhc.la.gov/hubfs/Document%20Libraries/Housing%20Development/Compliance/HOTMA%20Forms/Tenant%20Income%20Certification.pdf
- Property Inspect NSPIRE sample (vendor): https://propertyinspect.com/sample-reports/nspire-unit-pre-inspection-lite/
- 17 USC 105 (US government works): https://www.law.cornell.edu/uscode/text/17/105
