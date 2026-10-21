# Real-document eval: answers to check by hand

Each answer key in `answer_keys/` tags every field one of two ways:

- **verified**: the document states the value *and* a HUD public database row agrees (HUD LIHTC Database, or HUD's Multifamily Assistance & Section 8 Contracts database). These are scored as ground truth.
- **proposed**: I read the value from the document myself, with no public data to check it against. These need your check. `run_eval.py --set real` scores them separately ("proposed") so they never mix with verified scores.

**How to review:** open the document (`python -I tests/eval/real/fetch.py`, then `tests/eval/real/docs/<id>.pdf`).
- If a value is right, tick the box.
- If it's wrong, fix the value in `answer_keys/<id>.answer_key.json`.
- To promote a checked field, change its `"status"` to `"verified"` and add "checked by hand" to its `basis`.

In the tables, "p." means a page of the cut document in `docs/`, not of the original packet.

**Totals:** 11 documents, 159 answer fields: 27 verified, 132 proposed (below).

## Questions worth a look first

1. **`hap_tx_coppertree_renewal_2013`, 1-bedroom units.** The OCR text says 158; HUD's database says 156. Page 1's total (263) only adds up with 156. I put 156.
2. **`hap_il_amanda_brooke_request`, letter date.** It's printed "April 14, 2024", but the file name says 2025 and the letter cites 2025 FMRs. The key keeps the printed date.
3. *(Exhibit 1 stage 2 rents and units checked by hand 2026-10-21; the compilation question below is still open.)* **`hap_tx_coppertree_1990` is a compilation.** Page 10 is headed "HUNTINGTON FOREST". Pages 22-27 are a HAP addendum signed for "Owner Shannon Place, Ltd." in July 1986. Are those earlier names of Coppertree, or other projects' pages? The stage unit counts (114 + 90) also don't reach today's 263.
4. **`pbv_ca_rivco_cottonwood2`, address.** Exhibit A says "24550 & 24570 Cottonwood"; HUD's LIHTC database says "24580 Cottonwood Ave". I used Exhibit A.
5. **`sample_tx_811_*`, rent.** I used contract rent ($841) as `rent_amount`, which matches the synthetic HUD-form keys. The tenant pays $350 of it.
6. **`pbv_ca_rivco_5th_street`, owner name: changed after the first run.** I first keyed page 1's "Mercy Housing Living Centers". The form reader returned "Mercy House Living Centers" from the execution page. That is what the execution page prints, and it matches the cover letter ("Mercy House"), so I changed the key. The PDF disagrees with itself; please confirm the legal name. Also, what is the fillable-field value "7"?

### `hap_il_amanda_brooke_request`

Consultant's cover letter to HUD requesting HAP assignment and an Option 1-A 20-year renewal with rent increase. Source pages 1-8; [source](https://www.ihda.org/wp-content/uploads/2025/04/AMANDA-BROOKE-HAP-Assignment-_-Rent-Increase-Cover-Letter-04.14.2025.pdf).

A letter, not a contract: tests whether contract facts are read from prose. The letter is dated 'April 14, 2024' but the file name says 04.14.2025 and it cites 2025 FMRs, so the printed year looks like a typo; the key uses the printed date. HUD's database shows the renewal took effect 2026-04-01 for 240 months with FH Amanda Brooke LLC as owner. Contains business contact emails and a phone number (consultant, title company, HUD inbox); no tenant data.

Verified against HUD data (no action needed): `contract_number`, `rems_property_id`, `project_name`, `city`, `total_units`, `contract_units`, `owner_name`, `renewal_term_years`.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `letter_date` | April 14, 2024 | p.1 (probably 2025; see notes) |
| [ ] | `current_rent_1br` | 740 | p.3 table |
| [ ] | `current_rent_2br` | 838 | p.3 table |
| [ ] | `current_rent_3br` | 945 | p.3 table |
| [ ] | `proposed_rent_1br` | 1035 | p.3 table |
| [ ] | `proposed_rent_2br` | 1285 | p.3 table |
| [ ] | `proposed_rent_3br` | 1530 | p.3 table |

### `hap_tx_coppertree_1990`

HUD Section 8 HAP Contract, Disposition of HUD-Owned Projects, Parts I and II (1990, typewritten, scanned). Source pages 1-47; [source](https://www.nhlp.org/wp-content/uploads/HAP-Original-Contract-1990.pdf).

Heavy OCR noise in the text layer. Two stages: Exhibit 1 lists 114 units (stage 1) and 90 units (stage 2) by OCR. HUD's database shows 263 assisted units today, after later renewals, so the 1990 unit counts are not checkable against it. The PDF is a compilation: page 10 is headed 'HUNTINGTON FOREST', and pages 22-27 are a HAP addendum whose signature block reads 'Owner Shannon Place, Ltd.', 'Russell E. Lomax', dated July 1986. These may be earlier names of the same project or other projects' pages; unresolved. The key only uses pages 1-14 and 28, which name Coppertree / TX24-E000-008.

Verified against HUD data (no action needed): `contract_number`, `rems_property_id`.

**Checked by hand by the user, 2026-10-21 (p.11, Exhibit 1, stage 2).** The typed values are:

| Bedrooms | Units | Contract rent | Utility allowance | Gross rent |
|---|---|---|---|---|
| 1 | 49 | $250 | $35 | $295 |
| 2 | 39 | $350 | $45 | $395 |
| 3 | 2 | $395 | $53 | $448 |

Total: 90 units. The key is correct; the AI's earlier read of $260 / $305 was wrong. **The 1BR row doesn't add up on the document itself:** $250 + $35 = $285, not the $295 printed. A handwritten note dated 2-11-91 flags it as a known error needing correction. The key keeps the printed $250. The extractor must keep $250 too, flag the row as inconsistent at low confidence with "Verify with your PHA", and never change a value to make the arithmetic work (regression test on `feature/affordable-real-accuracy`). The ticked rows below are hand-checked. Their `status` in the answer key is still `proposed`, since nobody has asked for it to change.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.landlord` | Texas-Coppertree Village Limited Partnership | p.2 (OCR: 'TFXAS- CnPPgRTP.F.E VIT,LAGE LIMITED PARTNERSHIP') |
| [ ] | `lease.lease_start_date` | November 3, 1990 | p.2 s.1.1(a) stage 1 effective date |
| [ ] | `owner_name` | Texas-Coppertree Village Limited Partnership | p.2 |
| [ ] | `effective_date` | 11/03/1990 | p.2 s.1.1(a) stage 1 |
| [ ] | `stage1_units` | 114 | p.8 Exhibit 1 stage 1: 64 + 49 + 1 |
| [x] | `stage2_units` | 90 | p.11 Exhibit 1 stage 2: 49 + 39 + 2 (checked by hand 2026-10-21) |
| [x] | `contract_rent_1br` | 250 | p.11 Exhibit 1 (checked by hand 2026-10-21; row doesn't add up on the document, see note) |
| [x] | `contract_rent_2br` | 350 | p.11 Exhibit 1 (checked by hand 2026-10-21) |
| [x] | `contract_rent_3br` | 395 | p.8/p.11 Exhibit 1 (checked by hand 2026-10-21 on p.11) |

### `hap_tx_coppertree_renewal_2013`

HUD Assignment, Assumption and Amendment of Section 8 HAP Contract (03/14) with attached Basic Renewal Contract, Multi-Year Term (REV 11-05-2007). Source pages 1-26; [source](https://www.nhlp.org/wp-content/uploads/HAP-Assignment-Package-2015.pdf).

Unsigned 2015 assignment (seller 2005 West Gulf Complex, L.P. to buyer Coppertree Village Holdings LLC) with the executed 2013 renewal contract as Exhibit A. Exhibit A's 1-bedroom count reads 158 in the OCR layer; HUD's database has 156, and 156 + 102 + 5 = 263 matches page 1, so 156 is likely right but is left for review.

Verified against HUD data (no action needed): `lease.property_address`, `contract_number`, `contract_units`, `units_2br`, `units_3br`.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.landlord` | 2005 West Gulf Complex, L.P. | p.1 seller / p.9 'Name of Owner' (the 2015 assignment would replace it with the buyer) |
| [ ] | `lease.lease_start_date` | April 1, 2013 | p.9 s.2a 'begins on April 1, 2013' |
| [ ] | `project_name` | Texas Coppertree aka Coppertree Village | p.8 (HUD DB name: 'Coppertree Village Apartments') |
| [ ] | `units_1br` | 156 | p.20 Exhibit A (OCR reads 158); HUD Multifamily Assistance & Section 8 Contracts DB, contracts table (current as of 2026-10-06): 1BR_count 156 |
| [ ] | `contract_rent_1br` | 767 | p.20 Exhibit A |
| [ ] | `contract_rent_2br` | 979 | p.20 Exhibit A |
| [ ] | `contract_rent_3br` | 1130 | p.20 Exhibit A |
| [ ] | `effective_date` | 04/01/2013 | p.9 s.2a |
| [ ] | `initial_term` | 20 years | p.9 s.2a 'a period of Twenty years' |
| [ ] | `contract_administrator` | Southwest Housing Compliance Corporation | p.9 |
| [ ] | `owner_name` | 2005 West Gulf Complex, L.P. | p.9 |
| [ ] | `buyer_name` | Coppertree Village Holdings LLC | p.1 |

### `lura_co_grand_junction`

Land Use Restriction Agreement (city land sale to a housing authority), recorded Mesa County, CO. Source pages 1-7; [source](https://trim22-web.gjcity.org/GJ_WebDrawer/Record/1162307/File/document).

Recorded scan with the recorder's OCR text layer. Not an HFA tax-credit LURA: a city covenant that borrows Section 42 definitions. No unit count stated. Not found in HUD's LIHTC database (searched '674 23' and the housing authority's name).

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.property_address` | 674 23 3/4 Road, Grand Junction, Colorado 81505 | recital A (printed '23¾'; OCR may differ) |
| [ ] | `owner_name` | Grand Junction Housing Authority | p.1 parties |
| [ ] | `agency_name` | City of Grand Junction | p.1 parties |
| [ ] | `street_address` | 674 23 3/4 Road | recital A |
| [ ] | `city` | Grand Junction | recital A |
| [ ] | `county` | Mesa | recital A |
| [ ] | `term_years` | 40 | Terms s.2 |
| [ ] | `ami_limit_pct` | 80% | Terms s.3(a) |
| [ ] | `recording_date` | 10/29/2025 | p.1 recording stamp |
| [ ] | `reception_number` | 3141336 | p.1 recording stamp |

### `lura_ma_olympia_oaks`

Massachusetts DHCD Tax Credit Regulatory Agreement and Declaration of Restrictive Covenants (MHP 2006 template), unsigned execution copy. Source pages 1-20; [source](https://www.amherstma.gov/DocumentCenter/View/23669/735H-AMHR-Tax-Credit-Regulatory-Agreement-Olympia-Oaks).

Execution copy posted by the Town (dated 'August __, 2013', signature blocks blank except the Town Manager's typed name). The AMI percentage in the Low-Income Tenant definition is left blank in the document, so it is not in the key. HUD's database lists the project under the owner's name ('OLYMPIA AMHERST LP') with 42 units and allocation year 2012; low-income units and bedroom mix are blank there.

Verified against HUD data (no action needed): `lease.property_address`, `owner_name`, `street_address`, `city`, `total_units`.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `project_name` | Olympia Oaks | p.1 recital C |
| [ ] | `agency_name` | Department of Housing and Community Development | p.1 |
| [ ] | `low_income_units` | 42 | s.5.1: 'no less than 100 percent of the residential units', 'all of the units' |
| [ ] | `min_applicable_fraction` | 100% | s.2 'Applicable Fraction ... 100%' |
| [ ] | `units_1br` | 8 | s.5.1 |
| [ ] | `units_2br` | 21 | s.5.1 |
| [ ] | `units_3br` | 13 | s.5.1 |
| [ ] | `units_at_30_pct_ami` | 8 | s.5.1 'no less than 8 ... 30% or less' |
| [ ] | `extended_use_years` | 99 | s.2 'Low-Income Tenant Rental Period ... ninety-nine (99) years' |
| [ ] | `area` | Springfield, MA HMFA | s.2 'Area' |

### `lura_ut_amasa`

Utah Housing Corporation Low-Income Housing Credit Commitment Agreement and Declaration of Restrictive Covenants (2026 draft for a council agenda). Source pages 1-17; [source](https://www.moabcity.gov/AgendaCenter/ViewFile/Item/7882?fileID=10144).

Draft attached to a City of Moab agenda item; effective date blank ('____ day of _________, 2026'). Three BINs; UT-93-18004 is in HUD's building table under Kane Creek Apts (1993 allocation, 36 units in HUD's data), so this looks like a resyndication plus two new buildings (UT-25-25001/2, too new for HUD's data). The 50-unit count is not in HUD's data.

Verified against HUD data (no action needed): `bin`.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.property_address` | 109 Kane Creek Blvd., Moab, Utah 84532 | s.1 first building address (the project has three) |
| [ ] | `project_name` | Amasa Apartments | p.1 recitals |
| [ ] | `owner_name` | Amasa Apartments LLC | p.1 |
| [ ] | `agency_name` | Utah Housing Corporation | p.1 |
| [ ] | `bin_2` | UT-25-25001 | s.1 table |
| [ ] | `bin_3` | UT-25-25002 | s.1 table |
| [ ] | `street_address` | 109 Kane Creek Blvd. | s.1 table, first building |
| [ ] | `city` | Moab | s.1 |
| [ ] | `county` | Grand | Exhibit A 'situated in Grand County' |
| [ ] | `total_units` | 50 | s.2 'all 50 of the units' |
| [ ] | `low_income_units` | 50 | s.13 '50 units of the Project will be leased' |
| [ ] | `min_applicable_fraction` | 100% | s.1 |
| [ ] | `ami_limit_pct` | 60% | s.2 '60% or less of the area median gross income' |
| [ ] | `extended_use_years` | 50 | s.9 'total extended use period of 50 years' |
| [ ] | `units_2br` | 27 | s.13 table: 1+20+1+5 |
| [ ] | `units_3br` | 11 | s.13 table: 1+7+3 |
| [ ] | `units_4br` | 12 | s.13 table: 8+3+1 |
| [ ] | `units_at_30_pct_ami` | 5 | s.13 table |

### `pbv_ca_rivco_5th_street`

HUD-52530B PBV HAP Contract for Existing Housing, Part 1 (04/2023), with the PHA's Exhibit A. Source pages 4-13; [source](https://media.rivcocob.org/proceeds/2026/p2026_01_13_files/13.01001.pdf).

Form of contract approved by the board; effective date blank. The owner's name is spelled three ways in the packet: 'Mercy Housing Living Centers' (contract p.1), 'Mercy House Living Centers' (execution page, typed) and 'Mercy Housing Leasing Centers' (staff report); the cover letter says 'Mercy House'. The PDF keeps three fillable-field values that are not in its printed text: owner name, '20 years' and '7' (meaning of '7' unclear). PBV contracts are not in HUD's multifamily Section 8 database, and the project is not in the LIHTC database.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.landlord` | Mercy House Living Centers | p.8 execution page (p.1 s.1a prints 'Mercy Housing Living Centers') |
| [ ] | `lease.property_address` | 926 and 932 W. 5th Street, Corona, CA 92882 | Exhibit A |
| [ ] | `pha_name` | Housing Authority of the County of Riverside | Part 1 s.1a |
| [ ] | `owner_name` | Mercy House Living Centers | p.8 execution page and the packet's cover letter ('Mercy House'); p.1 s.1a prints 'Mercy Housing Living Centers'. Corrected after the first run, see REVIEW.md |
| [ ] | `initial_term` | 20 years | fillable form field 'Textfield-2' on Part 1 (the value is in the PDF's form fields, not its printed text) |
| [ ] | `project_name` | 5th Street Housing | Exhibit A |
| [ ] | `street_address` | 926 and 932 W. 5th Street, Corona, CA 92882 | Exhibit A |
| [ ] | `contract_units` | 11 | Exhibit A |
| [ ] | `total_units` | 12 | Exhibit A |
| [ ] | `pbv_units_1br` | 4 | Exhibit A |
| [ ] | `pbv_units_2br` | 7 | Exhibit A |
| [ ] | `ami_limit_pct` | 30% | Exhibit A table |

### `pbv_ca_rivco_cottonwood2`

HUD-52530A PBV HAP Contract for New Construction/Rehab, Part 1 (07/2019), with the PHA's Exhibits A-D. Source pages 5-23; [source](https://media.rivcocob.org/proceeds/2023/p2023_03_28_files/10.04001.pdf).

Form of contract approved by the board (stamped MAR 28 2023). HUD's LIHTC database lists Courtyards at Cottonwood II at '24580 COTTONWOOD AVE' with 32 units (16 2BR, 12 3BR, 4 4BR, placed in service 2024); Exhibit A's address reads '24550 & 24570 Cottonwood', so the address is left for review. The APN 482-16-1026 has an SSN shape.

Verified against HUD data (no action needed): `project_name`, `city`, `total_units`, `units_2br`, `units_3br`, `units_4br`.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.landlord` | Courtyards at Cottonwood II, L.P. | Part 1 s.1a |
| [ ] | `lease.property_address` | 24550 & 24570 Cottonwood Ave., Moreno Valley, CA 92553 | Exhibit A (HUD DB: 24580 Cottonwood Ave) |
| [ ] | `pha_name` | Housing Authority of the County of Riverside | Part 1 s.1a |
| [ ] | `owner_name` | Courtyards at Cottonwood II, L.P. | Part 1 s.1a |
| [ ] | `contract_units` | 8 | Exhibit A |
| [ ] | `contract_rent_2br` | 1592 | Exhibit A |
| [ ] | `contract_rent_3br` | 2041 | Exhibit A |

### `pbv_ca_rivco_oak_view`

HUD-52530A PBV HAP Contract for New Construction/Rehab, Part 1 (04/2023), with the PHA's Exhibits A-D. Source pages 64-85; [source](https://media.rivcocob.org/proceeds/2025/p2025_05_06_files/13.01001.pdf).

Form of contract approved by the board; dates blank. Not in HUD's LIHTC database (too new or under another name).

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.landlord` | NCRC Murrieta Senior Housing LP | Part 1 s.1a |
| [ ] | `lease.property_address` | 24960 Adams Avenue, Murrieta CA 92562 | Exhibit A |
| [ ] | `pha_name` | Housing Authority of the County of Riverside | Part 1 s.1a |
| [ ] | `owner_name` | NCRC Murrieta Senior Housing LP | Part 1 s.1a |
| [ ] | `project_name` | Oak View Ranch Senior Apartments | Exhibit A |
| [ ] | `street_address` | 24960 Adams Avenue, Murrieta CA 92562 | Exhibit A |
| [ ] | `total_units` | 81 | Exhibit A |
| [ ] | `contract_units` | 40 | Exhibit A |
| [ ] | `pbv_units_1br` | 35 | Exhibit A |
| [ ] | `pbv_units_2br` | 5 | Exhibit A |
| [ ] | `contract_rent_1br` | 1937 | Exhibit A |
| [ ] | `contract_rent_2br` | 2226 | Exhibit A |

### `sample_tx_811_50059`

HUD-50059 Owner's Certification of Compliance (06/2014), pages 1-2, filled by TDHCA as a training sample. Source pages 4-5; [source](https://www.tdhca.texas.gov/sites/default/files/section-811-pra/docs/S811-SampleTenantFile.pdf).

Agency sample with a fictitious household (the standard placeholder SSN elsewhere in the file, street '1234 Street'). The date of birth on the form is never extracted by design. Values are internally consistent: 841 = 491 + 350; gross rent 891 = 841 + 50; TTP 400 = tenant rent 350 + UA 50.

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.tenant` | Charlie R Cole | p.1 summary |
| [ ] | `lease.rent_amount` | $841 | p.2 item 29 Contract Rent |
| [ ] | `lease.security_deposit` | $400 | p.2 item 26 |
| [ ] | `project_name` | Lorena Springs | p.1-2 |
| [ ] | `head_of_household` | Charlie R Cole | p.1 |
| [ ] | `certification_type` | MI | p.2 item 16 |
| [ ] | `effective_date` | 12/01/2021 | p.2 item 12 |
| [ ] | `next_recert_date` | 12/01/2022 | p.2 item 14 |
| [ ] | `move_in_date` | 12/01/2021 | p.2 item 15 |
| [ ] | `unit_number` | 2 | p.2 item 21 |
| [ ] | `bedrooms` | 1 | p.2 item 22 |
| [ ] | `project_number` | TX59RDD0000 | p.2 item 5 |
| [ ] | `contract_number` | TX59RDD0001 | p.2 item 6 |
| [ ] | `household_size` | 1 | p.2 item 53 |
| [ ] | `annual_income` | 16400 | p.2 item 86 |
| [ ] | `extremely_low_income_limit` | 16650 | p.2 item 89 |
| [ ] | `total_deductions` | 400 | p.2 item 106 |
| [ ] | `adjusted_income` | 16000 | p.2 item 107 |
| [ ] | `security_deposit` | 400 | p.2 item 26 |
| [ ] | `contract_rent` | 841 | p.2 item 29 |
| [ ] | `utility_allowance` | 50 | p.2 item 30 |
| [ ] | `gross_rent` | 891 | p.2 item 31 |
| [ ] | `total_tenant_payment` | 400 | p.2 item 108 |
| [ ] | `tenant_rent` | 350 | p.2 item 110 |
| [ ] | `assistance_payment` | 491 | p.2 item 112 |

### `sample_tx_811_lease`

811 Project Rental Assistance Lease, form HUD-92236-PRA (02/2014), filled by TDHCA as a training sample. Source pages 63-72; [source](https://www.tdhca.texas.gov/sites/default/files/section-811-pra/docs/S811-SampleTenantFile.pdf).

Typed values sit above the printed blanks, so text order interleaves values and underscores ('1st ____ day of December ____, 21'). Year printed as '21' / '22' in the '20__' blanks. No street address in the lease itself (the rent ledger elsewhere in the file has '5678 Street, Unit 2').

| OK? | Field | Proposed value | Where it comes from |
|---|---|---|---|
| [ ] | `lease.tenant` | Charlie Cole | p.1 |
| [ ] | `lease.landlord` | Lorena Springs | p.1 |
| [ ] | `lease.rent_amount` | $841 | p.1 s.2 Contract Rent |
| [ ] | `lease.lease_start_date` | December 1, 2021 | p.1 s.1 |
| [ ] | `lease.lease_end_date` | November 30, 2022 | p.1 s.1 |
| [ ] | `lease.security_deposit` | $400 | p.2 s.6 |
| [ ] | `assistance_payment` | 491 | p.2 s.4 |
| [ ] | `tenant_rent` | 350 | p.2 s.4 |
| [ ] | `utility_allowance` | 50 | p.1 s.3a |
| [ ] | `project_name` | Lorena Springs | p.1 s.1 |

## Commercial leases on SEC EDGAR: not downloaded, no answer keys yet

SEC EDGAR only answers requests whose User-Agent names a contact, usually an email address ([SEC fair-access policy](https://www.sec.gov/os/accessing-edgar-data)). My request with a descriptive agent and no email got HTTP 403. I didn't put your email into requests without asking.

To add these four, run:

```
SEC_USER_AGENT="Abstractly <your email>" python -I tests/eval/real/fetch.py
```

Then add their answer keys. The terms below come from a research helper's *web summary* of each exhibit. They were **not read from the files** and are leads, not answers.

| id | Draft terms to confirm in the file |
|---|---|
| `lease_edgar_sharps_houston` | Landlord Warehouse Associates Corporate Centre Kirby II, Ltd.; tenant Sharps Compliance, Inc.; 9220 Kirby, Suite 500, Houston TX 77054; ~18,231 RSF; commencement Oct 1, 2006; expiration Sept 30, 2011; base rent $16,773/mo; deposit $20,054; use: general office, distribution, product assembly and warehousing (Art. 1) |
| `lease_edgar_nurix_woodlands` | Landlord 8800 Technology Forest PL, LLC; tenant Nurix Therapeutics, Inc.; Suite 200, Bldg 100, 8800 Technology Forest Place, The Woodlands TX 77381; 46,434 RSF; $53.00/RSF/yr; 3% annual increases; LC $615,250.50; 144-month term (Basic Lease Provisions, ss.3-6) |
| `lease_edgar_oncosec_sandiego` | Landlord 3535/3565 General Atomics Court, LLC; tenant OncoSec Medical Incorporated; Suite 100B, 3565 General Atomics Court, San Diego; 12,442 RSF; $4.50/RSF/mo = $55,989/mo; 3% increases; LC $55,989; 36 months (cover page, ss.2-6) |
| `lease_edgar_bnl_austin_retail` | Landlord Kimco Austin L.P.; tenant Brokers National Life Assurance Company; Center of the Hills, Austin TX; 20,337 sf; lease dated Dec 1, 2004; rent commencement June 1, 2006; $157,611.75/yr year 1, stepping up; no deposit; use: insurance office (Art. 1) |
