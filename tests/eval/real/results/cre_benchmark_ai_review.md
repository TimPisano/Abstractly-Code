# CRE benchmark, AI engine: review of every auto-scored mismatch

Reviewed by Claude on 2026-10-20 against `backend/benchmark_data/ground_truth.json`, and against the lease text where marked. **Not yet checked by you.**

Verdicts: **OK** = the same fact, worded differently (a scorer artifact) · **PARTIAL** = a miss or an incomplete answer · **WRONG** = a wrong value. OK and PARTIAL are counted as correct and wrong respectively in the reviewed score.

```
#1 [wrong] 01_ionetix_office_2026 :: lease_end_date (conf=medium)
  EXP: derived: July 31, 2028 (24 months after the Commencement Date; no explicit calendar expiration date stated)
  GOT: July 31, 2028
```
**OK**

```
#2 [wrong] 01_ionetix_office_2026 :: rent_escalation (conf=high)
  EXP: No escalation during the initial 24-month term; Base Rent increases to $7,500.00/month for the renewal term (months 25-48)
  GOT: Year 1-2 (Months 1-24): $7,250.00/mo; Renewal Term (Months 25-48): $7,500.00/mo
```
**OK**

```
#3 [wrong] 01_ionetix_office_2026 :: renewal_options (conf=high)
  EXP: One 2-year renewal option; exercise by written notice not less than 180 days prior to expiration of the Initial Term; conditioned on no monetary default and no material non-monetary default; renewal rent $7,500.00/month
  GOT: 1 option of 2 years; notice not less than 180 days prior to expiration of Initial Term; renewal rent fixed at $7,500.00/month
```
**OK**

```
#4 [wrong] 01_ionetix_office_2026 :: permitted_use (conf=high)
  EXP: Office/medical/research building activities including development of advanced cyclotron technology, production of medical isotopes, and uses similar or incidental thereto; and any other uses permitted by law
  GOT: Office/medical/research building activities including, but not limited to, the development of advanced cyclotron technology, the production of medical isotopes, and uses similar or incidental thereto, and any other uses permitted by Law
```
**OK**

```
#5 [wrong] 01_ionetix_office_2026 :: insurance_requirements (conf=high)
  EXP: Public liability policy of not less than $3,000,000; Lessor and its lender named as additional insured. Property insurance at not less than 80% of replacement value with Lessor as additional insured.
  GOT: Property insurance at least 80% of replacement value (excluding contents/trade fixtures), and public liability insurance of not less than $3,000,000
```
**OK**

```
#6 [wrong] 02_convera_office_2005 :: lease_start_date (conf=medium)
  EXP: derived: not a fixed calendar date -- the 'Initial Premises Commencement Date' (earlier of possession or 15 days after substantial completion + Target Date). Lease dated June 10, 2005; Target Date August 1, 2005.
  GOT: August 1, 2005
```
**WRONG**: Target Date reported as the start date; the lease has no fixed start date

```
#7 [wrong] 02_convera_office_2005 :: lease_end_date (conf=low)
  EXP: derived: 3 years (plus partial first month) after the Initial Premises Commencement Date; no fixed calendar date stated
  GOT: Not found
```
**PARTIAL**: says not found instead of giving the end-date formula

```
#8 [wrong] 02_convera_office_2005 :: cam_charges (conf=medium)
  EXP: Tenant pays its proportionate share of Building/Project operating expenses and real estate taxes above a 2006 base year; no fixed dollar amount stated
  GOT: Pro-rata share of Building Expenses in excess of Base Year Building Expenses, calculated per rentable square foot of the Premises
```
**OK**

```
#9 [wrong] 02_convera_office_2005 :: renewal_options (conf=high)
  EXP: One 3-year renewal option ('Renewal Term') at the Prevailing Market Rate, provided Tenant is not in default
  GOT: One (1) option to extend for an additional 3 years at Prevailing Market Rate; written notice required not less than 180 days prior to expiration of Initial Term
```
**OK**

```
#10 [wrong] 02_convera_office_2005 :: permitted_use (conf=high)
  EXP: General office purposes in accordance with applicable zoning regulations and for no other purpose (with a continuous-occupancy covenant)
  GOT: General office purposes in accordance with applicable zoning regulations, and for no other purpose
```
**OK**

```
#11 [spurious] 02_convera_office_2005 :: exclusivity_clause (conf=low)
  EXP: None
  GOT: Not found
```
**OK**

```
#12 [wrong] 02_convera_office_2005 :: insurance_requirements (conf=high)
  EXP: Tenant public liability insurance of not less than $2,000,000 combined single limit (per person / per occurrence); all-risk property at replacement cost; business interruption (>=12 months); workers' comp; plate glass. Landlord named as additional insured. Contractors: $200,000 CSL.
  GOT: $2,000,000 combined single limit public liability insurance per person/per occurrence; all-risk property and casualty insurance at replacement cost; workmen's compensation if required by law; business interruption insurance for at least 12 months
```
**OK**

```
#13 [wrong] 02_convera_office_2005 :: default_cure_period (conf=high)
  EXP: Monetary: 10 days after written notice that payment is past due. Non-monetary: 30 days after notice (extended if not curable in 30 days and Tenant is diligently pursuing cure).
  GOT: 10 days after receipt of written notice (monetary default); 30 days after notice for non-monetary default (with extension if default cannot be cured within 30 days and Tenant diligently prosecutes cure)
```
**OK**

```
#14 [wrong] 05_conns_retail_2003 :: tenant (conf=high)
  EXP: C. A. I., L.P. (trade names "Conn's" and "Conn Appliances"); guaranteed by Conn Appliances, Inc.
  GOT: C.A.I., L.P.
```
**OK**

```
#15 [wrong] 05_conns_retail_2003 :: lease_start_date (conf=low)
  EXP: derived: not a fixed calendar date -- Commencement Date is the earlier of (i) 120 days after tender of possession or (ii) 5 days after a certificate of occupancy is issued
  GOT: Not found (Commencement Date is formula-based, not a fixed calendar date)
```
**OK**

```
#16 [wrong] 05_conns_retail_2003 :: lease_end_date (conf=low)
  EXP: derived: last day of the 120th full calendar month after the Commencement Date (10-year term); no fixed calendar date
  GOT: Not found (end date depends on Commencement Date, which is not a fixed calendar date)
```
**OK**

```
#17 [wrong] 05_conns_retail_2003 :: property_address (conf=medium)
  EXP: Beaumont Shopping Center, City of Beaumont, Jefferson County, Texas (specific street/legal description in Exhibit A, not in the lease body)
  GOT: Beaumont Shopping Center, Beaumont, Jefferson County, Texas (approximately 88,283 square feet circumscribed on the Site Plan)
```
**OK**

```
#18 [spurious] 05_conns_retail_2003 :: security_deposit (conf=high)
  EXP: None
  GOT: None
```
**OK**

```
#19 [wrong] 05_conns_retail_2003 :: cam_charges (conf=high)
  EXP: Tenant's Pro Rata Share of Common Area Costs estimated $43,258.18 for the first calendar year ($0.49 per sq ft of Demised Premises floor area; $3,604.89/month). Pro rata share 88,283/137,514. Separate pro rata shares for real estate taxes ($0.34/sq ft) and insurance premiums ($0.06/sq ft).
  GOT: $0.49 per sq ft annually, estimated $43,258.18 for first calendar year, payable in monthly installments of $3,604.89
```
**OK**

```
#20 [wrong] 05_conns_retail_2003 :: rent_escalation (conf=high)
  EXP: Stepped Minimum Guaranteed Rental: $17,722.00/month (months 1-12), $20,232.00/month (months 13-60), $23,910.00/month (months 61-120)
  GOT: Fixed step increases: Months 1-12: $17,722.00/mo; Months 13-60: $20,232.00/mo; Months 61-120: $23,910.00/mo (based on full 88,283 sq ft premises)
```
**OK**

```
#21 [wrong] 05_conns_retail_2003 :: renewal_options (conf=high)
  EXP: Two (2) five-year renewal options, per Exhibit H
  GOT: Two 5-year renewal options; notice 6 months or more prior to expiration of then-current term; First Renewal Term rent = $4.25/sq ft annually; Second Renewal Term rent = $5.25/sq ft annually
```
**OK**

```
#22 [spurious] 05_conns_retail_2003 :: exclusivity_clause (conf=low)
  EXP: None
  GOT: Not found - no tenant exclusive-use protection granted; lease instead restricts subletting of Surrender Space from certain prohibited competing uses
```
**OK**

```
#23 [wrong] 05_conns_retail_2003 :: insurance_requirements (conf=high)
  EXP: Tenant Commercial General Liability insurance of not less than $2,000,000.00 combined single limit, plus a $3,000,000.00 Excess Liability / Commercial Umbrella policy. Landlord maintains CGL of $2,000,000.00 combined single limit for the Common Areas.
  GOT: Commercial General Liability Insurance with limits not less than $2,000,000.00 combined single limit, plus not less than $3,000,000.00 Excess Liability or Commercial Umbrella Policy
```
**OK**

```
#24 [wrong] 05_conns_retail_2003 :: default_cure_period (conf=high)
  EXP: Monetary default: 10 days after written notice. Non-monetary default: 30 days after written notice. Plus an additional 3 days' written notice before Landlord pursues remedies.
  GOT: 10 days after written notice (monetary default); non-monetary/general default cure period is 30 days after written notice
```
**OK**

```
#25 [wrong] 07_growlife_retail_2014 :: lease_start_date (conf=low)
  EXP: derived: not a fixed calendar date -- the Rent Commencement Date is the earlier of (i) the date Tenant opens for business or (ii) 60 days after Landlord's delivery of the premises. Agreement Effective Date: January 23, 2014.
  GOT: Not found (Rent Commencement Date is a floating date tied to earlier of tenant's opening or 60 days after delivery; Effective Date is January 23, 2014)
```
**OK**

```
#26 [wrong] 07_growlife_retail_2014 :: lease_end_date (conf=low)
  EXP: derived: last day of the 39th full calendar month after the Rent Commencement Date (39-month term); no fixed calendar date
  GOT: Not found (expires last day of 39th full calendar month after Rent Commencement Date, which is not a fixed calendar date in the document)
```
**OK**

```
#27 [wrong] 07_growlife_retail_2014 :: cam_charges (conf=medium)
  EXP: Tenant's Proportionate Share of Operating Expenses (utilities, real property taxes, Landlord's insurance, management fee up to 4% of gross rents, supervision/admin fee up to 15%, amortized capital improvements); proportionate share = rentable area of Leased Premises / rentable area of all Landlord-owned buildings in the Shopping Center. No fixed dollar amount.
  GOT: Tenant's Proportionate Share of Operating Expenses (pro-rata, calculated by dividing rentable area of Leased Premises by rentable area of all buildings owned by Landlord in the Shopping Center), payable monthly in advance
```
**OK**

```
#28 [wrong] 07_growlife_retail_2014 :: rent_escalation (conf=high)
  EXP: Stepped Minimum Rent, approximately 3% per year: $15.00/sq ft (months 1-12), $15.45/sq ft (months 13-24), and a further step in year 3
  GOT: Months 1-12: $4,051.25/mo ($15.00/sf); Months 13-24: $4,172.79/mo ($15.45/sf); Months 25-36: $4,297.97/mo ($15.91/sf); Months 37-39: $4,426.91/mo ($16.39/sf)
```
**OK**

```
#29 [wrong] 07_growlife_retail_2014 :: renewal_options (conf=high)
  EXP: One option to extend for one additional 36-month period; conditioned on Tenant not being in default and operating per the Permitted Use
  GOT: 1 option of 36 months; written notice at least 120 days prior to expiration of original Term; renewal rent: Months 1-12 $4,559.72/mo ($16.88/sf), Months 13-24 $4,696.51/mo ($17.39/sf), Months 25-36 $4,837.40/mo ($17.91/sf)
```
**OK**

```
#30 [spurious] 07_growlife_retail_2014 :: exclusivity_clause (conf=low)
  EXP: None
  GOT: Not found - lease references an Exhibit D listing exclusive and prohibited uses but the exhibit contents are not provided in the document
```
**OK**

```
#31 [wrong] 07_growlife_retail_2014 :: insurance_requirements (conf=high)
  EXP: Tenant Commercial General Liability insurance, minimum combined single limit $1,000,000 / general aggregate $2,000,000 (aggregate applies per-location); Special Form property insurance at full replacement cost (deductible <= $10,000); automobile liability $1,000,000; workers' compensation + employers' liability $1,000,000. Landlord, Landlord's mortgagee and managing agent named as additional insureds.
  GOT: CGL with $1,000,000 combined single limit / $2,000,000 general aggregate; property insurance for alterations/tenant property at full replacement cost with deductible not more than $10,000; plate glass insurance (may self-insure); automobile liability $1,000,000 each accident; workers comp/employers liability $1,000,000 each accident/disease; business interruption insurance covering 12 months of expenses/loss of income
```
**OK**

```
#32 [wrong] 07_growlife_retail_2014 :: default_cure_period (conf=medium)
  EXP: Monetary default (Rent): immediate, no notice or cure period ('without the necessity of demand therefor or notice thereof'). Non-monetary default: 5 days after written notice.
  GOT: 5 days after written notice (non-monetary default); monetary defaults (failure to pay Rent) have no cure period stated - breach occurs immediately without notice or demand
```
**OK**

```
#33 [wrong] 10_dover_retail_2006 :: rent_amount (conf=medium)
  EXP: $12,523.25 per month (Lease Years 1-3 at $18.34 per sq ft/year on 8,194 sq ft; first 60 days abated)
  GOT: $12,529.08/month (Year 1-3, based on $18.34/sq ft annually on 8,194 sq ft)
```
**WRONG**: monthly rent miscomputed ($18.34 x 8,194 / 12 = $12,523.16); the lease prints no monthly figure

```
#34 [wrong] 10_dover_retail_2006 :: lease_start_date (conf=medium)
  EXP: derived: not a fixed calendar date -- the Commencement Date is when Landlord substantially completes construction, estimated 'on or about July 1, 2006'. Lease dated March 29, 2006.
  GOT: July 1, 2006 (estimated Commencement Date)
```
**OK**

```
#35 [wrong] 10_dover_retail_2006 :: lease_end_date (conf=medium)
  EXP: derived: 11:59 p.m. on the day before the 10th anniversary of the first day of the first full calendar month after the Commencement Date (10-year Original Term); approximately June 30, 2016 if commencement is July 1, 2006
  GOT: Tenth anniversary of the first day of the first full calendar month following the Commencement Date
```
**PARTIAL**: end-date formula drops 'the day before' (one-day error)

```
#36 [wrong] 10_dover_retail_2006 :: cam_charges (conf=medium)
  EXP: Tenant's proportionate share of Annual Operating Costs (real property and similar taxes/assessments, utilities, trash removal, grounds/common area/mechanical-systems maintenance, and other costs of operating and maintaining the Property). No fixed dollar amount.
  GOT: Tenant's proportionate share of Annual Operating Costs (including Park Fund and Retail Pad apportionment), billed as additional rent based on actual costs incurred by Landlord
```
**OK**

```
#37 [wrong] 10_dover_retail_2006 :: rent_escalation (conf=high)
  EXP: Stepped Base Rent over the 10-year Original Term: $18.34/sq ft (Years 1-3), $19.99 (Years 4-6), $21.79 (Years 7-9), $23.75 (Year 10)
  GOT: Year 1-3: $18.34/sq ft; Year 4-6: $19.99/sq ft; Year 7-9: $21.79/sq ft; Year 10: $23.75/sq ft; Renewal Term 1 (Yr 1-2): $23.75/sq ft; Renewal Term 1 (Yr 3-5): $25.89/sq ft; Renewal Term 2 (Yr 1-3): $28.22/sq ft; Renewal Term 2 (Yr 4-5): $30.76/sq ft
```
**OK**

```
#38 [wrong] 10_dover_retail_2006 :: renewal_options (conf=high)
  EXP: Two successive 5-year Renewal Terms; written notice at least 180 days before the Renewal Term begins; Landlord may void the renewal if an uncured material default exists at the end of the prior Term. Renewal Base Rent: $23.75 then $25.89/sq ft (First Renewal); $28.22 then $30.76/sq ft (Second Renewal).
  GOT: 2 options of 5 years each; written notice not less than 180 days before expiration of previous term; renewal rent at fixed escalated per-sq-ft rates specified in lease (not FMV)
```
**OK**

```
#39 [wrong] 10_dover_retail_2006 :: permitted_use (conf=high)
  EXP: For and only for an 'upscale specialty retailer and direct marketer of equestrian products' similar to other Dover Saddlery stores in the United States
  GOT: Upscale specialty retailer and direct marketer of equestrian products, similar to other Dover Saddlery stores
```
**OK**

```
#40 [wrong] 10_dover_retail_2006 :: exclusivity_clause (conf=high)
  EXP: Landlord shall not enter into any lease with a tenant new to the Property allowing space to be used for retail sale of tack, riding apparel, boots, shoes, leather products, medications and ointments related to horse care, saddles, and items related to the care and keeping of horses (subject to carve-outs for unavoidable overlap; enforcement mechanics in Section 3.5)
  GOT: Landlord will not lease to new tenants for retail sale of tack, riding apparel, boots, shoes, leather products, medications/ointments for horse care, saddles, or horse-care items; carve-out allows other tenants limited overlapping use (no more than 7% of revenue, reasonable business relation, not advertised) and disputes resolved via arbitration with specific limitations on damages
```
**OK**

```
#41 [wrong] 10_dover_retail_2006 :: insurance_requirements (conf=high)
  EXP: Tenant general public liability insurance of not less than $1,000,000 for bodily injury/death of any one person per occurrence, $1,000,000 for all persons per occurrence, and $500,000 for property damage per occurrence, plus full replacement cost of contents. Landlord (and, on request, any mortgagee) named as additional insured; primary and non-contributory; 30 days' cancellation notice.
  GOT: General public liability insurance: $1,000,000 per occurrence bodily injury/death (any one person), $1,000,000 per occurrence (all persons), $500,000 property damage per occurrence, plus full replacement cost coverage for Tenant's contents; Landlord named as additional insured
```
**OK**

```
#42 [wrong] 10_dover_retail_2006 :: default_cure_period (conf=high)
  EXP: Monetary default: 5 days after written notice. Non-monetary default: 30 days after written notice to begin curing, with full cure within 90 days. No grace period more than twice in any 12-month period.
  GOT: 5 days after written notice for monetary default; 30 days to begin cure (completed within 90 days) for non-monetary default
```
**OK**

```
#43 [wrong] 13_altiris_office_2001 :: property_address (conf=high)
  EXP: Canopy Office Building III, 588 West 400 South, Lindon, Utah (Suites 250, 300, 350 plus storage space adjacent to the receiving dock)
  GOT: 588 West 400 South, Lindon, Utah (Suites 250, 300, 350, and certain storage space adjacent to the receiving dock)
```
**OK**

```
#44 [wrong] 13_altiris_office_2001 :: cam_charges (conf=high)
  EXP: Tenant's Percentage Share of Operating Costs = 53.78%; Basic Operating Costs and Taxes adjusted over a Base Year of 1/1/2002 - 12/31/2002. No fixed dollar amount.
  GOT: Tenant's Percentage Share of Operating Costs: 53.78%, with Base Year 1/1/2002-12/31/2002
```
**OK**

```
#45 [wrong] 13_altiris_office_2001 :: rent_escalation (conf=medium)
  EXP: Base Rent escalates annually at the Wall Street Journal published CPI rate each year of the term
  GOT: Base rent escalates annually at the Wall Street Journal published CPI rate; separately, Basic Rent is adjusted each January beginning January 1, 2003 for Tenant's share of increases/decreases in Basic Operating Costs over the Base Year.
```
**OK**

```
#46 [wrong] 13_altiris_office_2001 :: renewal_options (conf=high)
  EXP: Two 5-year options to renew, upon 6 months' prior written notice; renewal rate not to exceed market rate, or a maximum 3%/year increase from the initial term, whichever is less
  GOT: 2 options of 5 years each; 6 months prior written notice; renewal rent at rates not to exceed market rates at the time, or at maximum increases of 3% per year from the initial lease term, whichever is less.
```
**OK**

```
#47 [wrong] 13_altiris_office_2001 :: permitted_use (conf=high)
  EXP: General office purposes and for no other use or purpose without Landlord's prior written consent (no retail sales without Landlord's prior written consent)
  GOT: General office purposes and no other use or purpose without prior written consent of Landlord
```
**OK**

```
#48 [wrong] 13_altiris_office_2001 :: insurance_requirements (conf=high)
  EXP: Tenant liability insurance of $1,000,000 for property damage and $2,000,000 per occurrence for personal injuries or deaths occurring on the Premises
  GOT: $1,000,000 property damage, $500,000 per person, and $2,000,000 per occurrence for personal injuries or deaths, naming Landlord as additional insured
```
**OK**: key omits $500,000 per person; the lease states it (checked in leases_txt)

```
#49 [wrong] 13_altiris_office_2001 :: default_cure_period (conf=high)
  EXP: Monetary default (rent): Landlord gives one written notice per calendar year; after that, no further notice required before exercising remedies. Non-monetary default: 10 days from written notice (extended if the default cannot reasonably be cured in 10 days and Tenant commences and diligently pursues cure).
  GOT: 10 days after written notice (non-monetary default); monetary default notice is limited to one written notice per calendar year with no further notice required thereafter
```
**OK**

```
#50 [wrong] 14_bareescentuals_office_2006 :: lease_start_date (conf=high)
  EXP: June 1, 2005 (the 22nd/23rd Floor Commencement Date, which is the Lease Commencement Date; Suites 1825/1815 Commencement Date is July 1, 2005)
  GOT: June 1, 2005
```
**OK**

```
#51 [wrong] 14_bareescentuals_office_2006 :: lease_end_date (conf=medium)
  EXP: derived: the last day of the calendar month in which the 10th anniversary of the Suites 1825/1815 Commencement Date (July 1, 2005) falls -- i.e. July 31, 2015
  GOT: The last day of the calendar month in which the tenth (10th) anniversary of the Suites 1825/1815 Commencement Date (July 1, 2005) falls
```
**OK**

```
#52 [wrong] 14_bareescentuals_office_2006 :: property_address (conf=high)
  EXP: 71 Stevenson Street, San Francisco, California 94105 (Suites 2200, 2300, 1825 and 1815 in a 23-story, approximately 323,275 rentable sq ft office building)
  GOT: 71 Stevenson Street, San Francisco, California 94105 (Suites 2200, 2300, 1825, and 1815)
```
**OK**

```
#53 [wrong] 14_bareescentuals_office_2006 :: cam_charges (conf=high)
  EXP: Tenant's Share approximately 10.96%; Direct Expenses adjusted over a Base Year of calendar year 2005. No fixed dollar amount.
  GOT: Tenant's Share (approximately 10.96%) of Direct Expenses (Operating Expenses and Tax Expenses) in excess of Base Year (calendar year 2005) amounts
```
**OK**

```
#54 [wrong] 14_bareescentuals_office_2006 :: rent_escalation (conf=high)
  EXP: Stepped Base Rent: $30.75/rentable sq ft (Years 1-3), $32.75 (Years 4-7), $34.75 (Year 8 to end of Term); increases occur on the anniversary of the Suites 1825/1815 Commencement Date
  GOT: Year 1-3: $90,781.69/mo ($30.75/sf); Year 4-7: $96,686.19/mo ($32.75/sf); Year 8-end of Term: $102,590.69/mo ($34.75/sf)
```
**OK**

```
#55 [wrong] 14_bareescentuals_office_2006 :: renewal_options (conf=high)
  EXP: One 5-year Extension Option at Fair Market Base Rental; written notice at least 12 months but not more than 15 months before the initial Term expires; personal to MD Beauty and its Permitted Transferees; Tenant not in default
  GOT: 1 option of 5 years; written notice at least 12 months but not more than 15 months prior to expiration of initial Term; renewal rent at Fair Market Base Rental, not less than Base Rent in effect immediately prior to Extension Period
```
**OK**

```
#56 [spurious] 14_bareescentuals_office_2006 :: exclusivity_clause (conf=low)
  EXP: None
  GOT: Not found
```
**OK**

```
#57 [wrong] 14_bareescentuals_office_2006 :: insurance_requirements (conf=high)
  EXP: Tenant Commercial General Liability insurance with limits not less than: bodily injury and property damage liability $3,000,000 each occurrence / $3,000,000 annual aggregate; personal injury liability $3,000,000 each occurrence / $3,000,000 annual aggregate
  GOT: Commercial General Liability: $3,000,000 per occurrence / $3,000,000 annual aggregate (Bodily Injury and Property Damage Liability, and Personal Injury Liability each); plus Physical Damage (all-risk, full replacement cost) and Worker's Compensation/Employer's Liability
```
**OK**

```
#58 [wrong] 14_bareescentuals_office_2006 :: default_cure_period (conf=high)
  EXP: Monetary default (Rent): 5 business days after notice. Non-monetary default: 30 days after written notice (up to 60 days if the default cannot reasonably be cured in 30 days and Tenant diligently pursues cure).
  GOT: 30 days after written notice (non-monetary default; extendable to 60 days if diligently pursued); monetary default cure period is 5 business days after notice
```
**OK**

```
#59 [wrong] 15_formfactor_industrial_2002 :: landlord (conf=high)
  EXP: Richard K. and Pamela Corbett, Robert and Cheryl Rumberger, and Connie Duke (individuals)
  GOT: Richard K. and Pamela Corbett, Robert and Cheryl Rumberger, Connie Duke
```
**OK**

```
#60 [wrong] 15_formfactor_industrial_2002 :: property_address (conf=high)
  EXP: 2020 Research Drive, Livermore, California (County of Alameda; APN 99A-1500-6-23)
  GOT: 2020 Research Drive, Livermore, CA (Alameda County)
```
**OK**

```
#61 [wrong] 15_formfactor_industrial_2002 :: rent_escalation (conf=high)
  EXP: Scheduled Base Rent step-ups: $8,551.00/month, increasing to $9,149.57 on April 1, 2000 and to $9,790.04 on April 1, 2002
  GOT: Year 1-2 (4/1/1998): $8,551.00/mo; from 4/1/2000: $9,149.57/mo; from 4/1/2002: $9,790.04/mo
```
**OK**

```
#62 [wrong] 15_formfactor_industrial_2002 :: renewal_options (conf=high)
  EXP: Two options to extend, 3 years each; written notice at least 6 months before the current term expires; rent at then-current market rent, but not less than the rent being paid at the end of the current term
  GOT: 2 options of 3 years each; notice at least 6 months prior to expiration of current term; rent at then current market rent but not less than rent being paid at end of then current term
```
**OK**

```
#63 [wrong] 15_formfactor_industrial_2002 :: insurance_requirements (conf=high)
  EXP: Lessee Commercial General Liability policy with single-limit coverage of not less than $1,000,000 per occurrence. Lessor is the Insuring Party for property insurance.
  GOT: Commercial General Liability policy, occurrence basis, single limit coverage not less than $1,000,000 per occurrence, with Lessor as additional insured
```
**OK**

```
#64 [wrong] 15_formfactor_industrial_2002 :: default_cure_period (conf=high)
  EXP: Monetary default (Base Rent / other monetary payment / evidence of insurance): 3 days following written notice. Failure to provide required documentation: 10 days following written notice. Other non-monetary default: 30 days after written notice (extended if the cure reasonably requires more than 30 days and Lessee commences and diligently prosecutes it).
  GOT: 30 days after written notice (general default); monetary/life-safety defaults have a 3-day cure period
```
**OK**

```
#65 [wrong] 16_dialysis_medical_2001 :: lease_start_date (conf=high)
  EXP: derived: not a fixed calendar date -- the Commencement Date is the earlier of (a) the date Tenant takes possession or (b) 15 days after substantial completion and related conditions. Target Date June 15, 2001; Lease dated June 11, 2001.
  GOT: July 2, 2001
```
**WRONG**: date appears nowhere in the lease (invented, high confidence)

```
#66 [wrong] 16_dialysis_medical_2001 :: lease_end_date (conf=high)
  EXP: derived: 5 years (plus partial first month) after the Commencement Date; no fixed calendar date stated
  GOT: July 31, 2006
```
**WRONG**: date appears nowhere in the lease (invented, high confidence)

```
#67 [wrong] 16_dialysis_medical_2001 :: property_address (conf=high)
  EXP: 1344 Ashton Road, Suite 201, Hanover, Maryland (Fifth Election District, Anne Arundel County)
  GOT: 1344 Ashton Road, Suite 201, Hanover, Maryland 21076
```
**OK**

```
#68 [wrong] 16_dialysis_medical_2001 :: cam_charges (conf=medium)
  EXP: Tenant's Proportionate Share (approximately 2,330/16,865 = 13.8%) of Building Expenses over a 2000 Base Year and of Taxes over a 2000-2001 Base Year. No fixed dollar amount.
  GOT: Tenant pays its proportionate share (13.82%) of increases in Building Expenses over Base Year Building Expenses (2000 calendar year), billed as additional rent
```
**OK**

```
#69 [wrong] 16_dialysis_medical_2001 :: renewal_options (conf=high)
  EXP: One 5-year Renewal Term (Option to Extend), at the Prevailing Market Rate; provided Tenant is not in default
  GOT: 1 option of 5 years; notice not less than 180 days prior to expiration of Initial Term; renewal rent at Prevailing Market Rate (then-prevailing market rate for comparable space within 10 miles, including annual adjustments)
```
**OK**

```
#70 [wrong] 16_dialysis_medical_2001 :: permitted_use (conf=high)
  EXP: Solely for general office purposes in accordance with applicable zoning regulations and for no other purpose (with a continuous-occupancy covenant)
  GOT: General office purposes in accordance with applicable zoning regulations, continuous occupancy required, no other purpose
```
**OK**

```
#71 [spurious] 16_dialysis_medical_2001 :: exclusivity_clause (conf=low)
  EXP: None
  GOT: Not found
```
**OK**

```
#72 [wrong] 16_dialysis_medical_2001 :: insurance_requirements (conf=high)
  EXP: Tenant public liability insurance of not less than $2,000,000 combined single limit (per person and per occurrence) for personal injury, death and property damage; all-risk property/casualty at replacement cost. Contractors: $200,000 combined single limit. Landlord named as additional insured.
  GOT: $2,000,000 combined single limit public liability insurance per person/occurrence; all-risk property/casualty insurance at replacement cost covering Tenant's personal property and improvements; workers' compensation as required by law; plate/interior glass coverage
```
**OK**

```
#73 [wrong] 16_dialysis_medical_2001 :: default_cure_period (conf=high)
  EXP: Monetary default: 10 days after receipt of written notice that the amount is past due. Non-monetary default: 30 days after notice (extended if the default cannot be cured in 30 days and Tenant is diligently pursuing cure).
  GOT: 30 days after notice for non-monetary default (with extension if diligently pursued); 10 days after written notice for monetary default
```
**OK**

```
#74 [missed] 17_familysteak_retail_2002 :: lease_start_date (conf=None)
  EXP: derived: not a fixed calendar date -- the Commencement Date is 150 days after Landlord delivers the building pad, or the opening for business, whichever occurs first. Lease dated 2002 (day/month left blank in the document).
  GOT: None
```
**PARTIAL**: returned nothing; the key has a start-date formula

```
#75 [missed] 17_familysteak_retail_2002 :: lease_end_date (conf=None)
  EXP: derived: 11:59 p.m. on the last day of the 15th Lease Year (15-year term); no fixed calendar date
  GOT: None
```
**PARTIAL**: returned nothing; the key has an end-date formula

```
#76 [spurious] 17_familysteak_retail_2002 :: security_deposit (conf=high)
  EXP: None
  GOT: None
```
**OK**

```
#77 [wrong] 17_familysteak_retail_2002 :: renewal_options (conf=high)
  EXP: Two successive 10-year renewal option terms (Section 33)
  GOT: 2 successive renewal options of 10 years each; written notice required not less than 180 days prior to expiration of the Lease Term (or preceding Renewal Term); renewal rent = Base Rent per Subsection 1.3 plus Percentage Rent per Subsection 5.7 (same formula continues)
```
**OK**

```
#78 [wrong] 17_familysteak_retail_2002 :: permitted_use (conf=high)
  EXP: Initially only as a Ryan's Grill, Buffet and Bakery serving breakfast, lunch and dinner (and as a Tourist Information Attraction Ticket outlet and any use permitted under the Timeshare Lease); may later convert to a sit-down family restaurant or dinner house (not fast food) if not competing with another tenant on the Property
  GOT: Initial use as a Ryan's Grill, Buffet and Bakery, serving breakfast, lunch and dinner; may later change to a sit-down family restaurant or dinner house (not fast food) under certain conditions; no other use permitted
```
**OK**

```
#79 [wrong] 17_familysteak_retail_2002 :: exclusivity_clause (conf=high)
  EXP: Section 4.4 'Tenant's Exclusive': while Tenant is not in default and is operating as a Ryan's Grill, Buffet and Bakery, Landlord will not lease to another operator, or operate itself, the uses listed on Exhibit G ('Prohibited Uses'); does not preclude other restaurants not on Exhibit G. Any Phase II free-standing restaurant is limited to 6,500 leasable sq ft unless Landlord adds parking.
  GOT: While Tenant operates as a Ryan's Grill, Buffet and Bakery and is not in default, Landlord will not lease to or operate itself the uses listed as "Prohibited Uses" on Exhibit G; does not preclude leasing to other restaurants not on Exhibit G or permitting other tenants to sell similar products; Phase II free-standing restaurant building capped at 6,500 sq ft unless additional parking provided
```
**OK**

```
#80 [wrong] 17_familysteak_retail_2002 :: insurance_requirements (conf=high)
  EXP: 'Minimum Coverage': bodily injury and property damage of not less than $2,000,000 per person and $2,000,000 per occurrence, with umbrella coverage of $10,000,000 per occurrence, and $1,000,000 for property damage
  GOT: Minimum Coverage: $2,000,000 per person / $2,000,000 per occurrence bodily injury and property damage liability, with $10,000,000 umbrella coverage per occurrence, and $1,000,000 for property damage; plus full replacement cost fire and extended coverage on Tenant's personal property
```
**OK**

```
#81 [wrong] 17_familysteak_retail_2002 :: default_cure_period (conf=high)
  EXP: Monetary default (rent/money): 3 days after written notice. Non-monetary default: 10 days after written notice (extendable to 30 days if not a health/safety threat, more than 10 days is reasonably required, and Tenant commences within 10 days and diligently cures). No notice/cure right after 2 or more compliance failures in any 12-month period.
  GOT: 10 days after written notice (general default); monetary default (failure to pay rent) has a 3-day cure period after written notice
```
**OK**

```
#82 [wrong] 18_cuyamacabank_retail_2002 :: property_address (conf=high)
  EXP: 8002 La Mesa Boulevard, La Mesa, San Diego County, CA 91941
  GOT: 8002 La Mesa Boulevard, La Mesa, San Diego, CA 91941
```
**OK**

```
#83 [spurious] 18_cuyamacabank_retail_2002 :: security_deposit (conf=high)
  EXP: None
  GOT: None
```
**OK**

```
#84 [wrong] 18_cuyamacabank_retail_2002 :: cam_charges (conf=medium)
  EXP: Tenant pays its proportionate (pro rata) share of real property taxes, insurance, and the cost to maintain the common areas. No fixed dollar amount.
  GOT: Pro-rata share of CAM, insurance, and taxes, calculated as square footage of Demised Premises divided by gross leasable area of Shopping Center
```
**OK**

```
#85 [wrong] 18_cuyamacabank_retail_2002 :: renewal_options (conf=high)
  EXP: Two options to extend, 5 years each; written notice at least 90 days and not more than 270 days before the option period commences; Tenant not in default. First year of each option at prevailing market rate (appraiser mechanism), then 3%/year increases thereafter.
  GOT: 2 options of 5 years each; notice 90-270 days prior to option commencement; renewal rent at prevailing market rate in first year (determined by appraisal if parties disagree), then increasing 3% annually thereafter
```
**OK**

```
#86 [wrong] 18_cuyamacabank_retail_2002 :: permitted_use (conf=high)
  EXP: Only as a full service bank branch and for no other purpose whatsoever
  GOT: Full service bank branch only
```
**OK**

```
#87 [spurious] 18_cuyamacabank_retail_2002 :: exclusivity_clause (conf=low)
  EXP: None
  GOT: Not found
```
**OK**

```
#88 [wrong] 18_cuyamacabank_retail_2002 :: insurance_requirements (conf=high)
  EXP: Broad form comprehensive general liability insurance with limits of not less than $1,000,000 combined single limit for bodily injury and property damage (property-damage coverage to include plate glass)
  GOT: $1,000,000 combined single limit CGL (bodily injury and property damage, including plate glass, vandalism, malicious mischief) naming Landlord as additional insured; plus Fixture Insurance covering 100% of full insurable value of Tenant's improvements, fixtures, equipment and merchandise
```
**OK**

```
#89 [wrong] 18_cuyamacabank_retail_2002 :: default_cure_period (conf=high)
  EXP: Monetary default (rent): continues more than 3 days after written notice. Non-monetary default: continues more than 15 days after written notice. (Separate 5-day late-charge trigger with no notice required.)
  GOT: 15 days after written notice (non-monetary default); monetary default cure period is 3 days after written notice
```
**OK**

```
#90 [wrong] 19_saflink_office_2003 :: lease_start_date (conf=medium)
  EXP: derived: Commencement Date 'on or about February 1, 2004', upon substantial completion of tenant improvements and receipt of the Certificate of Occupancy. Deed of Lease dated November 10, 2003.
  GOT: February 1, 2004
```
**OK**

```
#91 [wrong] 19_saflink_office_2003 :: lease_end_date (conf=high)
  EXP: January 31, 2009 (stated; five years after the Rent Commencement Date)
  GOT: January 31, 2009
```
**OK**

```
#92 [wrong] 19_saflink_office_2003 :: property_address (conf=high)
  EXP: 1875 Campus Commons Drive, Suite 301, Reston, Virginia 20191 (Building: 'Campus South')
  GOT: 1875 Campus Commons Drive, Suite 301, Reston, VA 20191
```
**OK**

```
#93 [wrong] 19_saflink_office_2003 :: cam_charges (conf=high)
  EXP: Tenant's Proportionate Share (10.8%) of increases in Operating Expenses over the Base Operating Expense Amount (Operating Expenses for calendar year 2004). No fixed dollar amount.
  GOT: Tenant's Proportionate Share (10.8%) of increases in operating expenses over the Base Operating Expense Amount (Operating Expenses incurred for Calendar year 2004)
```
**OK**

```
#94 [wrong] 19_saflink_office_2003 :: renewal_options (conf=high)
  EXP: One 3-year extension term; provided the Lease is in effect, Tenant is not and has not been in default, and Tenant occupies at least 95% of the Demised Premises. Initial Term Renewal Request at least 9 months before expiration; rent at 100% of prevailing market rent (mutual agreement or MAI Appraisal Process), not less than the rent paid in the last Lease Year of the initial term.
  GOT: 1 option of 3 years; written request (Initial Term Renewal Request) not less than 9 months prior to expiration of initial term; renewal rent at 100% of then-prevailing market rent determined by mutual agreement or MAI Appraisal Process, but not less than rent paid during last Lease Year of initial term
```
**OK**

```
#95 [spurious] 19_saflink_office_2003 :: exclusivity_clause (conf=low)
  EXP: None
  GOT: Not found
```
**OK**

```
#96 [wrong] 19_saflink_office_2003 :: insurance_requirements (conf=high)
  EXP: Tenant broad form commercial general liability policy of not less than $1,000,000 per occurrence and $2,000,000 in the aggregate; insures Tenant's performance of the Section 18(c) indemnity
  GOT: Commercial general liability insurance with limits not less than $1,000,000 per occurrence and $2,000,000 in the aggregate; also all-risk property insurance on tenant improvements/alterations/personal property, builder's risk insurance during construction, and workers' compensation insurance as required by law
```
**OK**

```
#97 [wrong] 19_saflink_office_2003 :: default_cure_period (conf=high)
  EXP: Monetary default (Base Annual Rent / Additional Rent): 5 days after written notice that the amount is overdue (or, if Tenant received 2 or more such notices in the preceding 12 months, 5 days after the due date with no further notice). Non-monetary default: 10 days after written notice.
  GOT: 10 days after written notice (general default); monetary default: 5 days after written notice
```
**OK**
