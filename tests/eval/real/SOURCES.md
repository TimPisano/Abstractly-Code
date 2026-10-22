# Real-document eval set: sources

Retrieved 2026-10-20. All documents were downloaded without a login from government, housing-authority or public legal-aid sites. The documents themselves are **not committed**. `fetch.py` downloads each one, checks it against the SHA-256 below, and cuts the page range the answer key covers into `docs/<id>.pdf`. Both `sources/` and `docs/` are git-ignored.

**Personal data rule:** nothing here shows a real tenant's name, income, SSN or date of birth. I scanned every chosen page range for SSN-shaped numbers, dates of birth, phone numbers and email addresses before choosing it. What remains:
- names of public officials and corporate signatories;
- recorder stamps;
- in one letter, business contact details;
- in the two TDHCA samples, a fictitious household made up by the agency (placeholder SSN, "1234 Street").

| id | Document | Publisher | Source URL | Pages used | SHA-256 of source | Personal data check |
|---|---|---|---|---|---|---|
| `lura_ma_olympia_oaks` | Tax Credit Regulatory Agreement and Declaration of Restrictive Covenants, Olympia Oaks, 85 Olympia Dr, Amherst MA (DHCD; execution copy, 2013) | Town of Amherst, MA | https://www.amherstma.gov/DocumentCenter/View/23669/735H-AMHR-Tax-Credit-Regulatory-Agreement-Olympia-Oaks | 1-20 of 20 | `456eaa4a…3e4146` | Town Manager's typed name only; signature blocks blank |
| `lura_ut_amasa` | Low-Income Housing Credit Commitment Agreement and Declaration of Restrictive Covenants, Amasa Apartments, Moab UT (Utah Housing Corp.; 2026 draft) | City of Moab, UT (AgendaCenter) | https://www.moabcity.gov/AgendaCenter/ViewFile/Item/7882?fileID=10144 | 1-17 of 17 | `2aa1ad60…29dfedd` | Names of the owner's member and the UHC officer in signature blocks |
| `lura_co_grand_junction` | Land Use Restriction Agreement, Grand Junction Housing Authority and City of Grand Junction, 674 23¾ Road (recorded Mesa County 10/29/2025, reception 3141336) | City of Grand Junction, CO (WebDrawer) | https://trim22-web.gjcity.org/GJ_WebDrawer/Record/1162307/File/document | 1-7 of 7 | `90070756…783003e` | County clerk's name on the recording stamp; officials' signatures |
| `hap_tx_coppertree_1990` | Section 8 HAP Contract (disposition of HUD-owned project), Parts I and II, Coppertree Village, TX24-E000-008 (1990, scanned) | National Housing Law Project resource library | https://www.nhlp.org/wp-content/uploads/HAP-Original-Contract-1990.pdf | 1-47 of 47 | `d9439764…9a701b5` | Apartment numbers only; no tenant names. The PDF is a compilation: pp.10 and 22-27 name other projects or owners (see REVIEW.md) |
| `hap_tx_coppertree_renewal_2013` | HAP Assignment, Assumption and Amendment (2015, unsigned) with the attached Basic Renewal Contract, Multi-Year Term (2013), TX24E000008 | National Housing Law Project resource library | https://www.nhlp.org/wp-content/uploads/HAP-Assignment-Package-2015.pdf | 1-26 of 26 | `c68764dc…c1649d` | Owner's manager signature (partial, OCR) |
| `hap_il_amanda_brooke_request` | Cover letter to HUD requesting HAP assignment and an Option 1-A 20-year renewal, Amanda Brooke Apartments, Normal IL, IL06H121160 | Illinois Housing Development Authority | https://www.ihda.org/wp-content/uploads/2025/04/AMANDA-BROOKE-HAP-Assignment-_-Rent-Increase-Cover-Letter-04.14.2025.pdf | 1-8 of 8 | `c61c6eee…7fccd90` | Business emails and phone (consultant, title company, HUD inbox) and the HUD addressee's name |
| `pbv_ca_rivco_5th_street` | HUD-52530B PBV HAP Contract, Existing Housing, Part 1 (04/2023) + Exhibit A, 5th Street Housing, Corona CA | Housing Authority of the County of Riverside, board packet 2026-01-13 item 13.1 | https://media.rivcocob.org/proceeds/2026/p2026_01_13_files/13.01001.pdf | 4-13 of 66 | `21a9e538…338064e` | None in range (the packet's cover letter, p.14, names an operator contact) |
| `pbv_ca_rivco_cottonwood2` | HUD-52530A PBV HAP Contract, New Construction, Part 1 (07/2019) + Exhibits A-D, Courtyards at Cottonwood II, Moreno Valley CA | Housing Authority of the County of Riverside, board packet 2023-03-28 item 10.4 | https://media.rivcocob.org/proceeds/2023/p2023_03_28_files/10.04001.pdf | 5-23 of 95 | `a19d12b1…c13aa8` | None. APN 482-16-1026 is SSN-shaped (see below) |
| `pbv_ca_rivco_oak_view` | HUD-52530A PBV HAP Contract, New Construction, Part 1 (04/2023) + Exhibits A-D, Oak View Ranch Senior Apartments, Murrieta CA | Housing Authority of the County of Riverside, board packet 2025-05-06 item 13.1 | https://media.rivcocob.org/proceeds/2025/p2025_05_06_files/13.01001.pdf | 64-85 of 136 | `8aaf7935…53cd1e77` | PHA executive director's name in the signature block |
| `sample_tx_811_50059` | HUD-50059 (06/2014), pages 1-2, filled by TDHCA with a fictitious household | Texas Department of Housing and Community Affairs, Section 811 PRA sample tenant file | https://www.tdhca.texas.gov/sites/default/files/section-811-pra/docs/S811-SampleTenantFile.pdf | 4-5 of 92 | `72385e44…2d6ed9d` | Fictitious (agency sample); the form shows a made-up date of birth and SSN last-four |
| `sample_tx_811_lease` | 811 PRA Lease, HUD-92236-PRA (02/2014), filled by TDHCA with the same fictitious tenant | same file | same URL | 63-72 of 92 | same | Fictitious (agency sample) |

Full hashes are in `manifest.json`.

## Public data used for the answer keys

- **HUD LIHTC Database**: https://www.huduser.gov/lihtc/lihtcpub.zip, linked from https://www.huduser.gov/portal/datasets/lihtc/property.html. Downloaded 2026-10-20; `LIHTCPUB.xlsx` dated 2026-04-30 (55,345 projects) and `LIHTCPUB_BIN.xlsx` (161,715 buildings).
  - Olympia Oaks: hud_id MAC00000077.
  - Courtyards at Cottonwood II: CAA20240032.
  - The Moab BIN UT-93-18004: UTA19950917.
- **HUD Multifamily Assistance & Section 8 Contracts Database**: https://www.hud.gov/sites/dfiles/Housing/documents/MF-Assistance-Sec8-Contracts1.xlsx and https://www.hud.gov/sites/dfiles/Housing/documents/MF-Properties-with-Assistance-Sec8-Contracts1.xlsx, linked from https://www.hud.gov/hud-partners/multifamily-assist-section8-database. Current as of 10/06/2026.
  - Coppertree Village: contract TX24E000008, property 800020793.
  - Amanda Brooke: contract IL06H121160, property 800005699.
  - Not committed (about 37 MB); re-download from the links above.
- PBV contracts (the Riverside documents) are administered by PHAs and are not in HUD's multifamily database. Only the Cottonwood II project matched the LIHTC database.

## SEC EDGAR leases (listed, not downloaded)

`manifest.json` lists four lease exhibits:
- Sharps Compliance (Houston, warehouse/office);
- Nurix Therapeutics (The Woodlands, lab/office);
- OncoSec Medical (San Diego, lab/office);
- BNL / Kimco (Austin, retail).

SEC returned HTTP 403 to a request without a contact email in the User-Agent. Set `SEC_USER_AGENT` to fetch them (see REVIEW.md). `fetch.py` converts the HTML or text exhibits to a text PDF.

## Considered and left out

| Candidate | Why left out |
|---|---|
| St. Paul/Minneapolis "Exhibit R" declarations (2017, 2018), St. Paul 2021 LIHTC declaration, Minnesota Housing, Arkansas, Oregon, Rhode Island, TDHCA, NY DHCR and CTCAC LURA/regulatory-agreement templates, NHLP copy of the 2000 TCAC regulatory agreement | Blank templates, not agreements for a real project |
| Reading (PA) HA HUD-52641 and HUD-52517 "sample" PDFs | Blank forms with a SAMPLE watermark |
| Tucson HAP contract example | HTTP 403 |
| HUD Handbook 7465.1 ch.3 "example of completed HUD-50058" | The file has the chapter text only; the appendix with the example isn't at that URL |
| San Leandro (Lorenzo Creek), Hall County NE recorder, Santa Ana WebLink documents | Laserfiche viewers that need a browser session; no direct PDF |
| Redmond WSHFC regulatory agreement (Emerald Heights, 2003) | Bond regulatory agreement for a retirement community, not LIHTC |
| Riverside HA packets 2024-04-02, 2025-02-25, 2025-07-29 | More of the same PHA's PBV contract template; three Riverside contracts are already in |
| TDHCA board LURA items (95022, 853338-1000358), CTCAC compliance manual appendices | HTTP 404 |

## Notes for the extractor

- **Parcel numbers look like SSNs.** California APNs are printed `482-16-1026`. `app.affordable.pii.mask_ssns` masks any dashed 3-2-4 number, so APNs in Riverside exhibits are masked in quotes.
- **Board packets wrap the contract.** Each Riverside contract sits inside a 66-136-page packet (staff report, AHAP, plans, rent study). The eval cuts out the contract pages, as if the user uploaded just the contract. Finding those pages inside a packet is a separate, unsolved problem.
