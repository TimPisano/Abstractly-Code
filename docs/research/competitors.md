# Affordable housing software: competitors and gaps

**Date:** 2026-10-19 (second pass, same day)
**Scope:** Software and services sold to affordable housing owners, operators, property managers, and compliance staff (HUD PBRA/Section 8, HCV/PBV landlord side, PHA side, LIHTC, HOME, USDA RD). Research only. No accounts created, no demos requested, no code touched, nothing committed.
**Companion brief:** [section8.md](./section8.md), section 7. This document tests several claims from that brief and corrects one of them (see Summary).

**Source quality key.** Vendor pages are marked **(vendor)**. Competitor sites that sell rival products are marked **(competitor)**. Review aggregators, listicles, and SEO-style "best of" pages are marked **(aggregator)**. Job postings are marked **(job post)**. Press releases reprinted on a third-party site are marked **(reprint)**. Pages I read directly are marked **(fetched)**. Items I only saw as search-result snippets are marked **(snippet)**. Where a page returned 403, an empty body, or an unreadable PDF, I say so.

**Mirror warning.** Federal single-audit records cited here come from fac.procurementexpress.com, a **third-party mirror**, not the official Federal Audit Clearinghouse. The official site is [fac.gov](https://www.fac.gov), operated by GSA (fetched). I could not open individual audit records on fac.gov in this session, so every mirror-based finding below is labeled as such.

---

## Summary

- **Most important competitors.** Four big platforms plus MRI: Yardi (Voyager Affordable, RentCafe Affordable, RightSource, Breeze Premier), RealPage (OneSite Affordable), MRI (Bostonpost, plus Tenmast and HAPPY for PHAs), and Entrata (Entrata Affordable). ResMan and AppFolio sell affordable modules. Emphasys is the main PHA-side system. Nan McKay & Associates is a services firm with some software.
- **AI-native entrants that overlap Abstractly's planned features.** EliseAI is the largest and the most important to track: a $250M Series E (lead a16z, August 2025, company primary source), with affordable features in production for reporting and recertification notices, and in-platform income verification still listed as "coming soon" as of July 2025. HousingIntellect is the closest pure-play: its LIHTC page claims paystub and award-letter reading, TIC generation, 8823 risk scoring, and 140% AUR tracking, but no pricing, no funding, no named customers, and several FAQ answers are blank. DEVAL Solutions' PHASE (launched August 14, 2026, vendor claim) automates PBRA MOR preparation across tenant files, EIV, HAP variances, and NSPIRE. Pronto Housing is the older startup with a software-plus-service model, status unclear.
- **Entrants I could not confirm or that do not overlap.** TenantAudit: no site found (see the dropped list). Haven AI and VerbaFlo are AI front-desk and communication products, not compliance; both sites say so (see the profiles). Preferred Compliance Solutions is a human file-review firm; I could not confirm an "eFile" product.
- **Pricing is mostly not public.** The one clear public figure is Yardi's Breeze Premier for affordable housing at **$3 per unit per month with a $400 monthly minimum** (fetched from [Yardi Breeze's pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/)). Every other vendor in this document is quote-only or unconfirmed. Third-party figures conflict, and I do not rely on them. VoucherReady's $49 one-time landlord kit is the only other public price I confirmed, and it is an information product, not software.
- **Correction to the section 7 brief.** The brief says these systems "record certifications; they don't audit them." That is only partly right. ResMan advertises built-in error checking ([ResMan](https://myresman.com/blog/why-conventional-software-wont-cut-it-lihtc-compliance)). RealPage's AI Operations Agent flags missing forms and certification issues in affordable files (vendor case study, fetched). MRI Bostonpost blocks move-ins that fail program eligibility (MRI-cited customer, snippet). The accurate version: incumbents do rule checks inside their own system, and the independent cross-file audit is now claimed by AI vendors and by DEVAL, so it is no longer an open niche.
- **Gap 2 is re-rated: contested.** Checking TICs and 50059s against verification documents is now claimed by HousingIntellect (paystub and award-letter reading, TIC generation), EliseAI (income verification on its roadmap, compliance reviewers on staff), RealPage (discrepancy scans), and Yardi (opt-in Verification Services). It is no longer a wedge on its own.
- **The five most credible gaps, revised** (detail in the gaps section):
  1. **HCV landlord side and small owners.** The price points are low (a $49 kit, free PHA portals) and the enterprise minimums ($400/month on Breeze Premier) are high. No AI-native entrant I found targets a 20–60 unit voucher landlord.
  2. **One-check cross-document verification across rent roll, HAP contract, lease, and certification.** Entrants check certifications against verification documents. I found no public product that also reconciles the HAP contract and rent roll against the lease and cert in one pass. This is an absence in my searches, not proof.
  3. **HOTMA transition check before January 1, 2027.** HUD lets owners compute by hand and enter via TRACS 202D rent override until then. Many vendors claim HOTMA support; few claims are independently checkable. This is a timing window.
  4. **LIHTC and PHA-side 8823 and SEMAP prep.** DEVAL covers PBRA MOR and HousingIntellect claims 8823 prep, but I found no independent evidence either handles PHA SEMAP or state-monitor LIHTC audits end to end.
  5. **Compliance due diligence on affordable portfolios in acquisitions.** The weakest-evidenced of the five. No product for acquisition diligence turned up.
- **Layered-deal rule conflicts are NOT a gap.** Yardi, MRI, ResMan, and Entrata all advertise layered-subsidy handling.
- **Incumbents and entrants can close most gaps.** Yardi already sells a file-review service and an opt-in verification service. RealPage already sells an AI file-audit agent. EliseAI has compliance reviewers and a roadmap. The defensible positions are the ones with small-owner economics, cross-document citations, and neutrality across vendors.

---

## Per-vendor profiles

### Big platforms

#### Yardi (Voyager Affordable, RentCafe Affordable, RightSource, Breeze Premier, Elevate)

- **What it does for affordable.** Voyager is the enterprise system with affordable modules. The Breeze Premier pricing page says it covers HOME, RD, HUD 50058/50059, and LIHTC in all 50 states ([Yardi Breeze pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/), fetched; the 50-state line is from a Yardi-affiliated page, snippet). Yardi's 2020 Breeze Premier release says it covers public housing, HCV, PBV, 50058/50059, and layered subsidies ([Yardi press release](https://yardi.com/?p=308179), snippet). RentCafe Affordable is the resident-facing certification portal. Its April 2026 brochure says it works with Compliance Manager and Voyager 8 and automates initial and recurring certifications ([Yardi brochure](https://www.yardi.com/resources/rentcafe-affordable-housing-brochure/pdf/), snippet). Applicants and residents can opt into Yardi Verification Services for income and asset checks, and can upload bank statements and paychecks (same brochure and a [Yardi blog post](https://www.yardi.com/blog/wp-json/wp/v2/posts/24096), snippet).
- **Programs.** HUD PBRA, HCV/PBV (PHA and owner side), LIHTC, HOME, RD. Yardi also launched an online RFTA tool for HCV landlords inside RentCafe ([Mann Report, 2023](https://www.mannpublications.com/mannreport/2023/03/16/yardi-introduces-solution-to-ease-voucher-acceptance-makes-it-easier-for-landlords-to-accept-vouchers/), snippet).
- **RightSource.** An outsourced file review and TRACS/MINC voucher processing and reconciliation service. Per Yardi's marketing, it works with Voyager and Compliance Manager, and findings show on the Compliance Manager dashboard ([Yardi RightSource page](https://www.yardi.com/product/rightsource/), **snippet only; the page returned 403 on fetch**). Yardi's PDF gives a 9.8-minute average review time and a 96% within-24-hour return rate ([Yardi PDF](https://www.yardi.com/resources/streamlined-affordable-housing-workflows-with-yardi-rightsource/pdf/), snippet, vendor-reported). A search snippet says RightSource requires Voyager and does not work with Breeze Premier. I could not verify this from the Yardi page.
- **System of record or add-on?** System of record (Voyager, Breeze Premier). RightSource is a **service** layered on top.
- **Target customer.** Voyager: mid-size to large affordable portfolios and PHAs. Breeze Premier: smaller operators.
- **Public pricing.**
  - Breeze Premier affordable: **$3/unit/month, $400/month minimum, annual agreement** ([Yardi Breeze pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/), fetched). A Spendbase listing shows $2 for a different tier, treated as an outlier.
  - Yardi reportedly charges no separate onboarding, training, or support fees for Breeze, per [Buildium's review](https://www.buildium.com/blog/yardi-breeze-review/) (aggregator-adjacent, snippet).
  - Voyager, RentCafe Affordable, RightSource, Elevate: **not public.** A third-party estimate puts residential Voyager at $1.50–$3.00 per unit per month, which is not Yardi's figure ([Vendr](https://www.vendr.com/marketplace/yardi), aggregator, snippet). An "Elevate" pricing claim appeared in a search snippet from a source I could not pin down. I do not rely on it.
- **Strengths reported.** Well regarded on compliance depth and layered subsidies (the section 7 brief's claim, not re-verified here). Breeze Premier has published pricing.
- **Complaints reported.** Module-priced, costly as modules accumulate (per the section 7 brief, [DoorLoop comparison](https://www.doorloop.com/blog/realpage-vs-yardi), aggregator/competitor).
- **Integration and partner terms.** The Yardi Interface Partner program charges an **annual license fee per interface**, varying by interface type and sometimes by transaction volume. The page does not publish a dollar figure ([Yardi interface partner page](https://www.yardi.com/?p=359162), **snippet; 403 on fetch**). Eligibility is a company at least two years old. A third-party API review site cites about $25K per interface per year and "3+ mutual Voyager clients." That is **unverified**, and the site is an aggregator ([Supergood](https://supergood.ai/api-report-card/yardi-systems)). The RentCafe API Terms of Use say fees are "identified in the Agreement" ([Yardi RentCafe API ToU](https://resources.yardi.com/?p=18614), snippet).

#### RealPage (OneSite Affordable, AI Operations Agent, Windsor Compliance, Domin-8)

- **What it does for affordable.** OneSite Affordable's own page says: "Seamlessly stay in compliance with HUD, Tax Credits, Rural Housing regulations and the 50058 Public Housing program," plus LIHTC state reporting ([RealPage OneSite Affordable page](https://www.realpage.com/lp/property-management-for-affordable-housing), fetched). That page **does not** mention HOTMA, TRACS, HOME, or AI for affordable. A competitor says RealPage updated OneSite Affordable for TRACS 2.0.3.A and HOTMA ([ExactEstate, Aug 2026](https://www.exactestate.com/blog/best-affordable-housing-software-12-platforms-compared), **competitor, snippet**). I could not confirm that from RealPage or HUD.
- **AI Operations Agent for affordable files (vendor case study, fetched).** The case study is Cambridge Management, which runs LIHTC, HUD, mixed-income, and RD communities on OneSite. The agent "scans files for discrepancies and flags missing forms, certification issues, and skipped audit steps," and gives site teams real-time coaching. Reported results over 90 days: 547 lease and affordable file audit tasks, consistency across 218 units, more than 95 hours of manual review saved for regional supervisors, and "$285K in potential revenue" identified ([RealPage case study](https://www.realpage.com/case-studies/streamline-affordale-housing-compliance-with-ai/), **fetched; vendor-reported; undated page, footer says 2026**). This is the strongest evidence that a major platform already does the within-system file audit.
- **Acquisitions (verified).**
  - **Windsor Compliance, October 2013.** [HousingWire](https://housingwire.com/articles/27670-realpage-acquires-compliance-monitoring-firm), fetched, dated October 28, 2013: "a provider of compliance monitoring services for the affordable housing industry," with more than 30,000 affordable units. The SEC 10-Q gives a $2.7M price ([SEC 10-Q, snippet](https://www.sec.gov/Archives/edgar/data/0001286225/000128622514000030/rp-2014093010q.htm)).
  - **Domin-8, around 2014.** Described as broadening RealPage into small, medium, and affordable managers ([Multi-Housing News](https://www.multihousingnews.com/with-acquisition-of-domin-8-realpage-will-cater-to-small-medium-sized-and-affordable-housing-managers/), snippet).
  - **Notivus, May 2014.** General rental compliance and vendor risk, not affordable-specific ([SEC 10-Q, snippet](https://www.sec.gov/Archives/edgar/data/0001286225/000128622514000030/rp-2014093010q.htm)).
  - I found **no** RealPage affordable-compliance acquisition after 2014. My search was not exhaustive.
- **System of record or add-on?** System of record, with an AI agent on top.
- **Target customer.** Mid-size to large operators. RealPage also has a certified partner tier (AppPartner). A 2022 Grace Hill release says it became a certified AppPartner on RealPage Exchange ([Grace Hill](https://gracehill.com/grace-hill-announces-partnerships-with-yardi-and-realpage/), snippet). The cost of that tier is not public.
- **Public pricing.** **Not public.** G2 says RealPage has not provided pricing ([G2 pricing](https://www.g2.com/products/realpage-onesite/pricing), snippet). The only per-unit number I found is a 2005 review (about $1/unit/month, too old to use). A 2026 third-party estimate puts the category at $1–$5/unit/month, which is not a RealPage quote.
- **Complaints reported.** G2 aggregate ratings conflict across pages (3.8/5 from 107 reviews, 3.9/5 from 40). Support is the most common weak spot (G2 comparison, snippet). Capterra reviews are mostly 2016–2017 (dated).
- **Legal overhang.** The DOJ suit over RealPage's algorithmic pricing is cited in the section 7 brief. It is reputational, not compliance. I did not re-fetch it in this session.

#### MRI Software (Bostonpost / MRI Affordable Housing, Tenmast, HAPPY, HAB, PHA Pro)

- **What it does for affordable.** MRI says its affordable product "automates compliance for HUD Multi-Family, Tax Credit, HOME, and USDA Rural Development," and submits resident certification data to TRACS and MINC ([MRI affordable compliance page](https://mrisoftware.com/products/affordable-housing-compliance-software/), vendor, snippet). Bostonpost handles layered subsidies, including HUD Sec. 8/202/236, USDA RD 515, LIHTC, HOME, public housing, and third-party vouchers ([MRI Bostonpost blog](https://www.mrisoftware.com/blog/bostonpost-property-manager-9-1-affordable-housing-property-management-software/), vendor, snippet). An MRI release says Bostonpost supports TRACS 202D ([MRI news](https://www.mrisoftware.com/news/mri-software-releases-latest-version-bostonpost-ensure-tracs-202d-compliance), vendor, snippet).
- **Tenmast (verified).** MRI acquired Tenmast, a PHA and private affordable housing software firm. The announcement is dated October 10, 2017 ([Software Equity Group](https://softwareequity.com/transactions/tenmast-acquired-by-mri-software), **fetched**). Days later, on October 16, 2017, MRI acquired **HAB, Inc.**, another PHA software firm ([MRI news](https://www.mrisoftware.com/sa/?p=23343), snippet).
- **HAPPY Software (verified, dated).** MRI acquired HAPPY Software in March 2018 for PHA and HCV work ([MRI news](https://www.mrisoftware.com/nz/news/happy-software-public-affordable-housing-tech-powerhouse/), snippet). I did not confirm whether HAPPY is still sold separately.
- **Bostonpost vs Tenmast.** I found no source on whether Tenmast's technology was folded into Bostonpost or PHA Pro (launched May 2024, [Mann Report](https://www.mannpublications.com/mannreport/2024/05/29/mri-software-unveils-pha-pro-for-public-housing-and-voucher-management-compliance/), snippet, MRI's flagship PHA voucher product). Treat the product mapping as **unknown**.
- **System of record or add-on?** System of record.
- **Target customer.** Affordable owners and managers (Bostonpost), and PHAs (PHA Pro, Tenmast, HAPPY).
- **Public pricing.** **Not public.** ITQlick says Bostonpost "starts at $300 per month" on one page and shows a **$2,500–$5,000/month license** in a comparison table on another ([ITQlick pricing](https://www.itqlick.com/mri-bostonpost/pricing), aggregator, snippet). The figures conflict. Use neither as a benchmark.
- **Complaints reported.** Capterra customer service rated 2.0/5 by one reviewer. Another called it relatively inexpensive ([Capterra AU listing](https://www.capterra.com.au/software/1009740/mri-affordable-housing), snippet). Section 7's brief cites a softwarefinder review ("simple functions made convoluted"); I did not re-fetch it. The G2 page shows one review, 3.0/5, dated 2022 ([G2](https://www.g2.com/products/mri-affordable-public-housing/reviews), snippet). That sample is too small to rely on.

#### Entrata (Entrata Affordable)

- **What it does for affordable.** Entrata's product page lists tax credit compliance dashboards, LIHTC reporting and e-reporting, and HUD ledgers that update automatically when income is backdated or certifications overlap. It also says one household can be certified under multiple programs ([Entrata affordable page](https://www.entrata.com/affordable), vendor, snippet). A March 2025 Entrata blog says the platform handles TRACS certification and monthly HAP requests ([Entrata blog](https://www.entrata.com/blog/entrata-affordable-bridging-the-gap-between-affordable-and-traditional-property-management), vendor, snippet).
- **Launch date.** A competitor (ExactEstate) says Entrata Affordable launched in February 2023 ([ExactEstate](https://www.exactestate.com/blog/entrata-vs-exactestate-a-property-management-software-comparison), **competitor, snippet**). Fortress, another competitor, says the affordable functionality is newer and still adding program workflows ([Fortress](https://fortresstech.io/compare/entrata), **competitor**).
- **System of record or add-on?** System of record for conventional plus affordable.
- **Target customer.** Competitor reviews say 1,000+ unit operators ([ExactEstate](https://www.exactestate.com/blog/best-affordable-housing-software-12-platforms-compared), competitor, snippet).
- **Public pricing.** **Not public.** [G2 pricing](https://www.g2.com/products/entrata/pricing) says Entrata has not provided pricing (snippet). Third-party estimates of $4–$8/unit/month are estimates only.
- **Complaints reported.** One G2 reviewer said the software is not helpful for affordable units (G2, snippet, reviewer not pinned). Capterra reviewers say customer service is inconsistent ([Capterra](https://www.capterra.com/p/20372/Entrata/reviews/?page=7), snippet). Ratings are high (G2 4.6 from 817 reviews; Capterra 4.6 from 444 users), but mostly from conventional properties.
- **Verdict.** Entrata does affordable, but its affordable depth is less proven than Yardi's or MRI's. I found no independent compliance audit of it.

#### ResMan (Affordable module)

- **What it does for affordable.** ResMan says its affordable module covers LIHTC, HUD (including RAD), RD, and state and local set-asides ([ResMan affordable page](https://www.myresman.com/affordable/), vendor, snippet). It advertises built-in error checking, user-level permissions, approval workflows, and a "Build-A-Program" feature for layered funding ([ResMan compliance page](https://myresman.com/solutions/affordable-compliance), vendor, snippet). Its blog says the compliance dashboard shows recertifications and program compliance in one place ([ResMan blog](https://myresman.com/blog/why-conventional-software-wont-cut-it-lihtc-compliance), vendor, snippet).
- **Integrations.** Nationwide Compliant for lease compliance and evictions (vendor, snippet).
- **System of record or add-on?** System of record for conventional plus affordable.
- **Target customer.** Mid-size operators.
- **Public pricing.** **Not public.** A third-party FitGap summary is secondary and gives no price.
- **Complaints or strengths.** One 2019 trade-press customer quote says it made voucher and certificate submission more efficient (dated, single customer). A Capterra reviewer praised ease of use and reporting (snippet, single review).

#### AppFolio (affordable tier)

- **What it does for affordable.** AppFolio says users can submit PBRA certifications and vouchers to TRACS, manage HAP requests and subsidy receipts, define unit set-asides, income and rent limits, and utility allowances, and generate TIC forms and XML reports for state portals, where XML upload depends on the state ([AppFolio affordable page](https://www-dyn.appfolio.com/markets/affordable-housing), vendor, snippet). A third-party review says a property-level HOTMA toggle exists ([SoftwareConnect roundup](https://softwareconnect.com/roundups/best-affordable-housing-property-management-software/), aggregator, snippet).
- **Gaps (competitor claim).** ExactEstate says the Plus tier lacks AIT validation and 140% rule automation ([ExactEstate AppFolio alternative](https://www.exactestate.com/appfolio-alternative), **competitor, unverified**).
- **AI.** A "Realm-X" generative AI feature is described as helping with resident outreach and certification milestones, per an aggregator summary (**unverified**).
- **Target customer.** SMB to mid-size. SoftwareConnect reports a 50-unit minimum for the affordable offering (**unverified**).
- **Public pricing.** Not confirmed as public for the affordable tier.

### AI-native and startup entrants (new in this pass)

#### EliseAI (leasing AI with an affordable compliance push)

- **What it is.** An AI company that sells leasing, maintenance, and resident-communication agents to housing operators, with market-rate and affordable customers. Its affordable compliance work is newer and is being built out in product and in staffing.
- **Funding (company primary source).** The company's own announcement says it "announced its Series E raise of $250 million," dated August 16, 2025, and that "the round was led by Andreessen Horowitz (a16z)." The same page says the company passed a $100M ARR milestone "earlier this year" and gives no valuation ([EliseAI announcement](https://eliseai.com/blog/eliseai-raises-250m-series-e), **fetched**). Coverage cites a $2.2B valuation from Reuters via Bisnow, and says Bessemer, Sapphire Ventures, and Navitas Capital participated ([Bisnow](https://www.bisnow.com/national/news/multifamily/proptech-firm-eliseai-secures-250m-series-e-doubles-workforce-130636), snippet). Seedtable lists Navitas as lead; the company's own statement and most coverage name a16z, so I follow the company. The prior round was a $75M Series D in August 2024 (snippet).
- **Affordable features (July 30, 2025 blog, fetched).** [EliseAI blog](https://eliseai.com/blog/eliseai-gets-an-upgrade-new-features-for-affordable-housing-operators), company primary source, three tools:
  1. **Affordable Reporting Dashboard**: shows each prospect's place in pre-qualification and why some do not qualify.
  2. **Recertification Notices**: sends notices "at 120, 90, 60, and 30-day intervals," by email and SMS, and lets teams mark recertifications complete. The post says beta properties saw much less time on recertifications, with no numbers in the excerpt I read.
  3. **Housing Voucher Auto-Qualification**: when a prospect mentions a voucher, the AI asks about approved unit size and qualifies them for matching units.
  - **Listed as "Coming soon":** "In-platform document collection and income verification." This is the piece that overlaps Abstractly most directly. I could not find a later page confirming it shipped.
- **Compliance staffing (job posts, snippet).** EliseAI posts "Affordable Housing Compliance Expert" and "Compliance Analyst" roles to audit LIHTC, HCV, PBV, PBRA, and USDA RD resident files and to "validate automated compliance outputs against program requirements" ([Built In, example posting](https://www.builtinboston.com/job/affordable-housing-compliance-expert-housing/10515908), **job post**). Required experience varies by posting, from 1+ to 3+ years of affordable file review or auditing, and some postings ask for former HFA auditors. **The $125K–$200K salary range** cited in the coordinator's note is **not verified**: I did not see a salary figure on the postings I read.
- **Market report (company-sponsored).** A May 7, 2026 BusinessWire release, "New EliseAI Report Shows AI Is Cutting Costs and Reshaping Operations in Affordable Housing," reports a survey of 400 property management professionals, including 162 executives at affordable portfolios ([BusinessWire](https://www.businesswire.com/news/home/20260507960819/en/New-EliseAI-Report-Shows-AI-Is-Cutting-Costs-and-Reshaping-Operations-in-Affordable-Housing), snippet). Coverage reports that 91% of affordable operators have deployed AI, mostly in leasing and communication rather than compliance, and that 44% name compliance and data privacy as the top barrier. It also says compliance, recertification, and income verification remain "largely manual" ([Housing Finance coverage](https://www.housingfinance.com/data-trends/study-91-affordable-housing-operators-are-using-ai), snippet). I did not access the full report. Read the numbers as a vendor's market survey.
- **Pricing.** Not public.
- **Assessment.** The most important entrant to track. It has capital, a leasing-first customer base, reviewers on staff, and a stated roadmap for exactly the document work Abstractly does. Its compliance product, as of the last public material I found, is a set of notices and a dashboard, with document intake and income verification not yet shipped. Its strength is the leasing funnel, not file audit depth.

#### HousingIntellect (LIHTC and multifamily compliance layer)

- **What it is.** Self-described as "The compliance layer for affordable housing," running alongside a property management system and covering "certifications, document collection, review, corrections, and audit readiness" ([HousingIntellect homepage](https://housingintellect.io), **fetched**).
- **Claims on the LIHTC page (fetched, [HousingIntellect LIHTC page](https://housingintellect.io/lihtc-compliance-software)).**
  - **Document reading:** "Drop in paystubs, award letters, asset statements, and third-party verifications," and "HousingIntellect reads the documents and extracts every data point a Section 42 reviewer needs."
  - **TIC generation:** "Tenant Income Certifications (TIC) generated from source documents."
  - **8823 risk scoring:** "Built-in 8823 risk scoring before the state monitor arrives." The FAQ question "Will HousingIntellect prepare my LIHTC properties for an 8823 audit?" has **no answer on the page**.
  - **AUR tracking:** "The Available Unit Rule clock starts the moment a household crosses 140%." The FAQ on AUR and set-asides also has **no answer**.
  - **Recertifications:** "Annual and interim recertification tracking with resident outreach," and "Annual recertifications schedule themselves."
- **What the pages do not show.**
  - **HOTMA calculation:** not described. HOTMA appears only in navigation keywords.
  - **AI:** the LIHTC page never uses the terms "AI," "artificial intelligence," or "machine learning." It describes "an engine" that "calculates, certifies, and audits itself." The "Compliance Assistant" appears as a navigation label with no description. So the "AI-native" label is my inference from the document-reading claims, not the vendor's own word.
  - **Pricing:** no figures, only "See pricing" links.
  - **Funding, founding date, customers:** none stated. One unnamed testimonial from a "Director of Compliance, National Multifamily Owner," and a "Featured in" link to a MultifamilyExecutive article, which the page describes as sponsored. My search for the company name returned no independent coverage.
- **Programs (homepage, fetched).** LIHTC, HUD Multifamily, HOME, Rural Development, Bond, PBV/RAD, Section 202/811, and layered programs. Keywords include Section 8, PBRA, TRACS reporting, and recertification software.
- **Trust claims.** "SOC 2 Type II audit in progress" and "99.9% platform uptime," per the homepage. Not independently verified.
- **Assessment.** The closest pure-play to Abstractly's planned LIHTC and Section 8 features. The claims line up with what Abstractly plans to build, but they are marketing-level, and I found no customers, pricing, funding, or independent review.

#### DEVAL Solutions, PHASE (PBRA MOR preparation)

- **What it is.** DEVAL Solutions is the technology affiliate of DEVAL LLC, datelined Reston, Virginia. PHASE stands for "Project Housing Accountability & Standards Engine" and is "purpose-built to automate every component of a HUD Management and Occupancy Review" ([PHASE launch release, reprinted on 01net.it](https://www.01net.it/deval-solutions-inc-launches-phase-the-first-centralized-mor-compliance-platform-for-hud-project-based-section-8-housing/), **reprint; vendor claim; fetched**).
- **Launch date.** August 14, 2026 (same release).
- **Scope (vendor claim).** Covers four MOR areas in one platform: tenant files, Enterprise Income Verification findings, HAP payment accuracy, and NSPIRE inspection findings. Sits on top of existing property management systems rather than replacing them. Features claimed: tracking every required tenant file document in real time, missing-document alerts before the reviewer arrives, monthly flagging of HAP payment variances, timestamped proof of NSPIRE corrective actions, and "pre-MOR risk scoring" (the release does not explain the scoring method).
- **Market claim.** More than 26,000 HUD Project-Based Section 8 owners and about 1.3 million assisted units (vendor, unverified).
- **Pricing.** Not stated; the release invites a "customized demo."
- **Evidence.** No independent reviews, customers, or HUD endorsement found.
- **Assessment.** Directly overlaps gap 1 for PBRA owners. Its scope is PBRA MOR, not LIHTC or PHA voucher audits. The release is a vendor claim with no evidence yet.

#### Pronto Housing (software plus compliance service)

- **What it is.** A New York company offering software for leasing and annual compliance across affordable programs, plus a service in which its own team handles compliance ([Pronto Housing site](https://prontohousing.com/), and July 2025 coverage summarized in search, snippet).
- **Funding (conflicting).** $2.5M seed in November 2021, led by Wilshire Lane ([Business Wire](https://www.businesswire.com/news/home/20211102005853/en/Pronto-Housing-Closes-%242.5M-Seed-Round-Led-By-Wilshire-Lane), press release, **fetched**). Total funding is listed at $7.58M by CB Insights and $3.0M by VCBacked, which conflict ([CB Insights](https://www.cbinsights.com/company/pronto-housing), data site, snippet).
- **Other signals.** Co-founders were reportedly invited to join a New York City task force on streamlining housing processes ([Bisnow](https://www.bisnow.com/news/new-york/affordable-housing/nyc-affordable-housing-lottery-broken-this-startup-aims-to-fix-it-134154), snippet).
- **Status.** Active as of July 2025 coverage. 2026 status not confirmed.
- **Pricing.** Not public.
- **Assessment.** The closest older startup to the owner-side compliance product. Its software-plus-service model is the one Abstractly would most resemble.

#### Preferred Compliance Solutions (human file review)

- **What it is.** A compliance consultant and monitoring firm. A search summary describes it as doing compliance training, LIHTC compliance, file review, and state audit assistance ([listing](https://prospeo.io/c/preferred-compliance-solutions), aggregator, snippet). Location conflicts: a listing says St. Cloud, Florida, and a data site says Logan, Utah.
- **Public work.** The Georgia Department of Community Affairs named Preferred Compliance Solutions, with Zeffert and Associates, as compliance file review consultants in an October 2019 selection ([Georgia DCA](https://dca.ga.gov/node/6002), public record, snippet). That contract covers tenant file reviews for GHFA multifamily programs.
- **eFile product.** I searched and found nothing confirming an "eFile" system. Not confirmed, so I do not list it as a product.
- **Assessment.** A services competitor for human file review. Relevant to Abstractly as the manual baseline it would displace.

#### TenantAudit (not confirmed; dropped)

- No site could be confirmed. tenantaudit.com returned an empty page in this session, and tenantaudit.io did not resolve (DNS error).
- The only claims I saw were in a secondary "best of" aggregator summary: plans from $49/month, $0.50–$1.00 per file for automated audits, and $150–$300 for manual review. I did not trace those to a primary source.
- **Action.** Do not use these figures. Drop the company from any competitor list until a primary source appears.

#### Haven AI (not a compliance product)

- [usehaven.ai](https://usehaven.ai) (fetched) sells AI workers for property management: "Maintenance AI" (answers calls, triages emergencies, dispatches vendors, creates work orders) and "Leasing AI" (responds to leads, qualifies prospects, books tours). Collections, renewals, move-ins, and inspections are listed as "coming soon."
- No pricing, only "Book a demo." No income certification, recertification, LIHTC, HOME, or Section 8 features on the page or the roadmap.
- **Action.** Not a competitor for file audit. Do not confuse it with Haven Connect, a different company.

#### VerbaFlo (communication AI; not a compliance product)

- [verbaflo.ai](https://verbaflo.ai) (fetched) is "AI infrastructure for the residential lifecycle," handling inquiries, tours, bookings, and resident support across voice, text, email, and chat, with a CRM and workflow builder. It lists affordable housing as a fit for waitlists, compliance-driven communication, and renewals, and names Seed Group, Vita Student, and Downing (Bay Downing's testimonial). Compliance claims are ISO 27001, GDPR, CCPA, and Fair Housing controls on conversations, not program compliance.
- A September 5, 2026 blog post on its site ([VerbaFlo blog](https://www.verbaflo.ai/blog/ai-for-affordable-housing-compliance-section-8-and-hud-operators), fetched) says "affordable housing compliance is not a product it currently claims." The post is general commentary, and it attributes no compliance or income-verification claims to VerbaFlo.
- **Action.** Not a competitor for file audit. Its "Affordable Housing Compliance Software" page title is misleading.

#### RIOO (NetSuite-native property management, public and social housing)

- **What it is.** "RIOO is a property management system built natively on Oracle NetSuite," covering leasing, rent collection, maintenance, and accounting, with residential (RIOO Home) and commercial (RIOO Professional) products ([RIOO](https://riooapp.com/blog/hotma-nspire-compliance-deadlines-2026), **fetched**). It lists a "Public & social housing" solution for housing authorities and associations.
- **Compliance claims.** The fetched article (dated August 6, 2026) says consistent record-keeping across a portfolio is what its public and social housing tooling is "built around." It does not claim specific HOTMA or NSPIRE features.
- **Dates in the article (not verified against HUD).** HOTMA full compliance for multifamily owners and agents: January 1, 2027. NSPIRE compliance for voucher programs: February 1, 2027. HUD scoring of NSPIRE affirmative requirements: October 1, 2026.
- **Pricing.** Not public: "Request a proposal for your portfolio."
- **Assessment.** A PMS with a public-housing solution, not an AI compliance tool. Relevant as a NetSuite-based competitor for the PHA and social-housing segment.

#### VoucherReady (HCV information publisher and kit)

- **What it is.** "An independent information publisher and planning tool" for Housing Choice Vouchers, which says it is not HUD, a housing authority, a housing counselor, or a law firm ([VoucherReady](https://voucherready.com), **fetched**). Free tools: a landlord assessment, a rent comparison organizer, and drafting tools.
- **Paid product.** The "Section 8 Landlord Kit" at **$49**, "one-time · yours to keep," with a 30-day money-back guarantee.
- **Pricing.** $49 one-time (the only confirmed public price for an HCV landlord product in this document).
- **Assessment.** Not software and not AI. It sets a low price anchor for HCV landlords and is a substitute for the paid-software case in the small-owner segment.

### Mid-size and smaller tools

#### ExactEstate (competitor, cited heavily)

- ExactEstate sells affordable compliance software. Its pages claim HUD-50059 generation, append-only audit logs built for MOR and IRS §42 audits, LIHTC rules including the 140% AUR, state TIC forms, and HAP reconciliation and PHA payment splits for HCV and PBV ([ExactEstate affordable page](https://exactestate.com/markets/affordable-housing), competitor, snippet; [LIHTC software page](https://www.exactestate.com/software/lihtc-compliance-software), competitor, snippet; [HCV page](https://www.exactestate.com/software/section-8-property-management-software), competitor, snippet).
- A secondary aggregator summary cites its pricing at $5 per unit per month (**unverified**).
- Its AI blog cites a May 2026 survey: 44% of operators name compliance and data privacy as the top barrier to more AI, and income certification and recertification remain "painstakingly manual, largely pen and paper" ([ExactEstate AI blog](https://www.exactestate.com/blog/ai-for-affordable-housing-compliance-closing-the-audit-gap), **competitor, fetched; survey not independently verified**).
- **Weight.** High competitor and vendor bias. Useful as a list of what a rival claims to do.

#### Costello Compliance (consulting, not software)

- A 2024 RIHousing board document recommends engaging Costello Compliance for $30,000 to update RIHousing's LIHTC compliance manual ([RIHousing RFA](https://rihousing.com/wp-content/uploads/Costello-Consulting-RFA-2024-08-15.pdf), public record, snippet). I found **no** Costello file-review *service* or software. The section 7 brief's "Costello compliance file review" is not supported.

#### Zeffert & Associates (consulting, with a portal)

- A St. Louis compliance firm founded in 1994, covering utility allowances, tenant file reviews, accessibility, and training ([Zeffert CARH listing](https://www.carh.org/member-directory-training/name/zeffert-associates-inc/), trade listing, snippet). A job posting says audits are run through a secured web portal ([job post](https://recruiting.paylocity.com/Recruiting/Jobs/Details/3393045), **job post**). No Zeffert-branded software product found.

#### Snappt (applicant income and fraud verification)

- Snappt sells AI document fraud detection and income verification (added June 2024), with a payroll connection reported to cover about 90% of the U.S. workforce ([Snappt income verification](https://snappt.com/income-verification), vendor). It is priced per applicant through the TenantCloud partnership, with no public per-applicant figure ([Business Wire, Sept 2025](https://www.businesswire.com/news/home/20250910558211/en), press release). Its 99.8% accuracy claim is vendor-reported.
- **Fit.** Applicant screening for conventional and small landlords. Not a LIHTC or 50059 recertification system. Adjacent, not a direct competitor.

#### Neighborly Software, LandlordAI (HCV-focused)

- Neighborly is a PHA-side voucher platform ([Neighborly](https://www.neighborlysoftware.com/housing-choice-vouchers/), vendor, snippet). LandlordAI says it targets HAP and voucher workflows for landlords in California, Arizona, and Nevada ([Product Hunt](https://www.producthunt.com/products/landlordai), vendor, snippet). I did not verify LandlordAI's product or traction.

#### LeaseLenses (adjacent AI lease audit)

- [LeaseLenses](https://www.leaselenses.com/blog/lease-audit-software-leaselens-ai) markets AI lease audit software for property managers in general (snippet). Not affordable-specific. Adjacent to Abstractly's lease-versus-roll work, not to affordable compliance.

#### HAPPY Software, HAB, Tenmast (MRI-owned PHA tools)

- See the MRI section. These are PHA systems now inside MRI. Public pricing not found.

### Names checked and dropped or reclassified

- **Rioo.** Reclassified: it is RIOO, a NetSuite-native PMS with a public-housing solution (see profile).
- **VoucherReady.** Reclassified: it is an HCV information publisher with a $49 landlord kit (see profile).
- **TenantAudit.** Dropped: no site confirmed; price claims unverified (see profile).
- **Haven AI and VerbaFlo.** Dropped as compliance competitors: both are communication and leasing AI, and both sites say so (see profiles).
- **Foresight (housing) and Ascent.** "Ascent" surfaced only as a regulatory-compliance automation firm, not housing. "Foresight Affordable" not found. Dropped.
- **ApartmentSmart.** No affordable compliance product found. Dropped.
- **HappyCo (NSPIRE).** Its app listing does not mention NSPIRE or affordable housing. Not confirmed. Other NSPIRE inspection tools found were SnapInspect, InspectCheck, and Property Inspect, all vendor marketing with no pricing. Listed as unverified.
- **Spectrum / Aspire, Rent Manager affordable, BlueMoon.** No affordable-compliance product found in searches. Dropped.
- **Boston Post.** This is Bostonpost (MRI), covered above.
- **Syntellect / "HousingIntellect" name collision.** A search for the exact name HousingIntellect returned Syntellect, an unrelated Indian affordable housing fintech. The HousingIntellect profile above is based on housingintellect.io only.
- **HDS / ShofCorp.** Named by ExactEstate as TRACS access channels. Vendor-described, not verified against HUD ([ExactEstate TRACS page](https://www.exactestate.com/software/tracs-software), competitor).

### TRACS, HUD, and audit context

- **NLHA list.** The National Leased Housing Association keeps a list of vendors and service bureaus that offer TRACS and MTCS occupancy software. NLHA says the list is not complete and is not an endorsement ([NLHA](https://hudnlha.com/?p=14099), snippet). This is the closest thing to a TRACS vendor list I found. I found no sign that HUD certifies vendors.
- **HUD guide.** "Choosing TRACS Compliant Software" (January 2023) ([HUD PDF](https://www.hud.gov/sites/dfiles/Housing/documents/Choosing_TRACS_Compliant_Software_Jan_2023.pdf), **could not read: the PDF returned binary only**). I could not confirm what it says about vendor certification or required functions.
- **HOTMA.** HUD's multifamily HOTMA page says full compliance for income certifications is now **January 1, 2027**, moved from January 1, 2026. Owners who want to adopt early can compute incomes and rents manually and enter them in TRACS 202D with the rent override function ([HUD HOTMA page](https://www.hud.gov/hud-partners/multifamily-hotma), **fetched**). A TRACS 203A release is mentioned in competitor blogs, but I found no HUD source on its status. **Unverified.**
- **Single-audit findings (third-party mirror, not fac.gov).** Mirror records show HUD multifamily or Section 8 files where income was not verified through EIV or any other method, a late recertification, a sampled 50059 with no support for reported income, and missing third-party verification in some files (for example, 5 of 20 eligibility certifications, and annual recertifications with no backup). Auditors generally attributed these to property-manager oversight ([FAC audit 20246](https://fac.procurementexpress.com/audits/20246), [finding 549](https://fac.procurementexpress.com/findings/549), and [finding 771](https://fac.procurementexpress.com/findings/771), **third-party mirror; snippets; check each against fac.gov before citing**). An industry review-issues list echoes the same patterns ([The Habitat Group](https://www.thehabitatgroup.com/articles/print/7845), industry article, undated).
- **Public procurement signals for third-party file audits (snippet).** The Chicago Housing Authority's 2025 RFQ for quality-control tenant file audits covers about 2,900 files, with roughly 725 audited per quarter over a 12-month term ([CHA RFQ](https://www.thecha.org/sites/default/files/2025-04/RequestForQuote-QCTenantFileAudits-Rebid_04.25_Procurement.pdf), public record, snippet). Georgia DCA has also issued an RFP for a compliance file review consultant ([Georgia DCA RFP](https://dca.georgia.gov/node/12506), public record, snippet). Bid prices were not in the excerpts I read.

---

## Comparison table

Pricing: "Public" means a figure is on a vendor page I could read. "Quote" means not public. "Unverified" means the only figure came from an aggregator or a competitor. Confidence reflects how well the claims are sourced.

| Vendor / product | Programs (affordable) | Role | AI-native? | Target size | Public price | Main complaints or strengths reported | Confidence |
|---|---|---|---|---|---|---|---|
| Yardi Voyager Affordable | HUD PBRA, HCV/PBV, LIHTC, HOME, RD | System of record | No | Mid to large; PHAs | Quote (third-party est. $1.50–$3/unit/mo, unverified) | Strong compliance depth; module pricing | Medium |
| Yardi Breeze Premier (affordable) | HUD, LIHTC, HOME, RD, 50058/59 | System of record | No | Small operators | **$3/unit/mo, $400/mo min** | Published price; small-operator fit | High (price), Medium (features) |
| Yardi RentCafe Affordable | Online certification for Voyager/CM; Verification Services opt-in | Add-on portal | No | Voyager clients | Quote | Applicant self-service, optional income verification | Medium (vendor brochure) |
| Yardi RightSource | Voyager and CM file review, TRACS/MINC voucher processing | **Service** | No | Voyager clients | Quote | 9.8 min avg review, 96% in 24h (vendor-reported) | Medium (vendor; page 403) |
| RealPage OneSite Affordable | HUD, LIHTC, RD, 50058 (HOTMA/TRACS unconfirmed) | System of record | Partly (AI Operations Agent) | Mid to large | Quote | Discrepancy scans (vendor case study); support weak (G2 snippets) | Medium |
| RealPage / Windsor Compliance | Compliance monitoring, 30k+ affordable units (2013 acquisition) | Service (acquired) | No | Monitoring clients | n/a | Shows compliance monitoring was a service line | High (acquisition), Low (current use) |
| MRI Bostonpost | HUD, LIHTC, HOME, RD, layered subsidies, TRACS 202D | System of record | No | Owners and managers | Quote (conflicting: $300/mo vs $2.5–5k/mo) | Customer service complaints (one Capterra review, 2.0/5) | Medium |
| MRI Tenmast / HAB / HAPPY / PHA Pro | PHA HCV, public housing, FSS | System of record (PHA) | No | PHAs (Tenmast >20k units) | Quote | Acquisitions 2017–2018; product mapping unknown | High (acquisitions), Low (product) |
| Entrata Affordable | LIHTC, HUD, TRACS, HAP requests | System of record (mixed portfolio) | No | 1,000+ unit operators (competitor claim) | Quote | Affordable depth less proven; high conventional ratings | Medium-low |
| ResMan Affordable | LIHTC, HUD incl. RAD, RD, state set-asides | System of record | No | Mid-size | Quote | Error checks, layered funding ("Build-A-Program") | Medium-low (vendor) |
| AppFolio affordable | PBRA TRACS submission, LIHTC TICs | System of record (SMB) | Unverified (Realm-X claim) | SMB (50-unit min, unverified) | Not confirmed | Competitor says lacks AIT and 140% rule | Low-medium |
| Emphasys Elite | HCV, HUD PHA programs, 50059 | System of record (PHA) | No | PHAs | Quote | Sole licensed vendor per county record | Medium |
| Nan McKay & Associates | HCV, LIHTC, PBRA, PBV, RAD | Service + some software | No | PHAs | Quote (one contract: $23,922 / 3 yrs) | DOJ fine 2024; SF Housing Authority suit (news; status unverified) | Medium |
| **EliseAI** | LIHTC, HCV, PBV, PBRA, RD (features in progress) | Leasing AI + compliance build-out | **Yes** | Market-rate and affordable operators | Quote | $250M Series E (a16z lead, Aug 2025); recert notices and reporting live (beta at July 2025); income verification "coming soon" | **High (funding), Medium (product)** |
| **HousingIntellect** | LIHTC, HUD MF, HOME, RD, Bond, PBV/RAD, 202/811, layered; Section 8 keyword only | Compliance layer alongside PMS | Claims document reading; "AI" not used | Owners and managers (unnamed) | Quote ("See pricing," no figures) | Claims 8823 risk scoring, AUR clock, TIC from source docs; FAQ answers blank | Low (marketing only) |
| **DEVAL Solutions PHASE** | HUD PBRA MOR (tenant files, EIV, HAP, NSPIRE) | Compliance layer on PMS | Partly (risk scoring, method not stated) | PBRA owners (26k owners claimed) | Not stated | Launched Aug 14, 2026; vendor release only | Low (vendor claim) |
| **Pronto Housing** | Affordable leasing and annual compliance | Software + service | Not stated | Owners (unknown) | Not public | $2.5M seed 2021; funding totals conflict; 2026 status unconfirmed | Low-medium |
| **RIOO** | Public and social housing (PHA and associations) | PMS (NetSuite-native) | No | Housing authorities and associations | Quote | NetSuite-based PMS; no specific HOTMA or NSPIRE feature claims in article | Low-medium |
| **VoucherReady** | HCV landlords | Information kit | No | Individual HCV landlords | **$49 one-time** | Free planning tools; not HUD or PHA; not software | High (price), Medium (product) |
| **Haven AI** | Maintenance and leasing (no affordable compliance) | AI front desk | Yes (not compliance) | Operators | Not public | No income cert, LIHTC, or Section 8 features | High (not a competitor) |
| **VerbaFlo** | Communication AI (no compliance product claimed) | AI front desk | Yes (not compliance) | Operators, incl. affordable waitlists | Not public | Vendor says affordable compliance is not a claimed product | High (not a competitor) |
| **Preferred Compliance Solutions** | Human file review, LIHTC (GA DCA selection) | Service | No | HFAs, owners | Quote | eFile product not confirmed | Medium (services) |
| Costello Compliance | LIHTC manual update (RIHousing) | Consulting | No | State HFAs | $30k (one RFA) | No file-review software found | Medium (consulting only) |
| Zeffert & Associates | Utility allowances, tenant file reviews | Service (+ portal) | No | Owners | Quote | Web portal per job posting | Low |
| Snappt | Applicant income and fraud verification | Add-on (screening) | Yes (fraud AI) | Small landlords | Per applicant (not published) | 99.8% accuracy (vendor) | Medium |

---

## Gaps a small team could fill

Each gap lists the evidence, what the incumbents and entrants already do, and how easily they could close it. Weak evidence is marked as such.

### 1. Pre-MOR and pre-monitoring audit across systems (contested)

- **The gap.** An audit that takes exports from one or more systems, runs HUD and program rules across them, and produces a findings list before a HUD MOR, a PHA SEMAP review, or a state LIHTC monitoring visit. It also needs to work for owners who are not on one platform.
- **Evidence.** Mirror records of single audits show repeat HUD multifamily file problems (missing verification, unsupported 50059 income, late recertification) ([FAC audit 20246](https://fac.procurementexpress.com/audits/20246), third-party mirror, snippet). The CHA and Georgia DCA RFQs show public buyers paying third parties for file audits ([CHA RFQ](https://www.thecha.org/sites/default/files/2025-04/RequestForQuote-QCTenantFileAudits-Rebid_04.25_Procurement.pdf), snippet).
- **What is already claimed.**
  - RealPage's AI Operations Agent scans affordable files for discrepancies and missing forms, with vendor-reported results (fetched).
  - DEVAL PHASE automates PBRA MOR preparation across four areas, with pre-MOR risk scoring (vendor release, Aug 2026).
  - HousingIntellect claims 8823 risk scoring and audit readiness (vendor page; FAQ blank).
  - Yardi RightSource is a service that does file review for Voyager clients.
  - ExactEstate claims audit logs built for MOR and §42 reviews (competitor).
- **Could incumbents close it?** Yes. RealPage already has the agent, and DEVAL is positioned for the same job on PBRA. The remaining opening is narrower: PHA-side SEMAP and 8823 prep, LIHTC state monitoring for owners not on OneSite, and audits that do not require a PMS migration.

### 2. Checking TICs and 50059s against the underlying verification documents (contested)

- **The gap.** Compare income on a TIC or 50059 with pay stubs, EIV, benefit letters, and bank statements, flag mismatches with citations, and keep an audit trail.
- **Evidence.** A sampled 50059 had no support for its reported income ([FAC audit 20246](https://fac.procurementexpress.com/audits/20246), third-party mirror, snippet). ExactEstate's May 2026 survey says income certification remains "painstakingly manual" (competitor, fetched). EliseAI reviewers check automated compliance outputs against program rules (job post, snippet).
- **What is already claimed.**
  - **HousingIntellect**: "reads the documents and extracts every data point a Section 42 reviewer needs," and generates TICs from source documents (vendor page, fetched; no customers or pricing shown).
  - **EliseAI**: in-platform document collection and income verification "coming soon" as of July 2025 (company blog, fetched).
  - **Yardi**: opt-in Verification Services and document upload in RentCafe Affordable (vendor brochure, snippet).
  - **RealPage**: discrepancy scans on affordable files (vendor case study, fetched).
- **Could incumbents close it?** Already in progress. Yardi and RealPage have the surface; EliseAI has the funding. The narrow version that remains open is the one in the "where Abstractly could still differ" section below.

### 3. HOTMA transition check before January 1, 2027

- **The gap.** Compute HOTMA incomes and rents for each file, flag where the old and new methods differ, and produce TRACS 202D rent-override entries. Support owners while the TRACS 203A status is still unclear.
- **Evidence.** HUD moved full compliance to January 1, 2027, and allows manual computation with TRACS 202D rent override for early adopters ([HUD HOTMA](https://www.hud.gov/hud-partners/multifamily-hotma), fetched). RIOO's August 2026 article and a competitor both name the January 2027 date. The TRACS 203A status is **unverified**.
- **What incumbents have.** RealPage and AppFolio claim HOTMA support (RealPage competitor-reported; AppFolio toggle per aggregator). ExactEstate offers a free HOTMA compliance assessment ([ExactEstate](https://www.exactestate.com/resources/hotma-compliance-assessment), competitor). None independently verified.
- **Could incumbents close it?** Yes. The deadline makes it a must-have for all of them. This is a **timing** window, not a durable moat.

### 4. HCV landlord side and small owners (most open)

- **The gap.** A small landlord (roughly 20–60 voucher units) who is not on Breeze Premier, Voyager, or a PHA portal needs to match monthly HAP remittances to tenants, catch short or late payments, track rent-reasonableness letters, and keep the lease, HAP contract, and cert consistent.
- **Evidence.** Free PHA landlord portals already show HAP history and remittances by tenant and unit ([HUD HCV Landlord Webinar](https://www.hud.gov/sites/dfiles/PIH/documents/HCV_Landlord_Webinar3_Technology.pdf), federal, snippet). VoucherReady sells a $49 one-time kit (vendor, fetched). Breeze Premier's $400/month minimum is a real barrier at small scale (Yardi, fetched). ExactEstate claims HAP reconciliation but aims at multi-program operators (competitor). LandlordAI targets three western states (vendor). The AI-native entrants reviewed here (EliseAI, HousingIntellect, DEVAL, Pronto) are all built for operators with portfolios, not for a single small landlord.
- **Could incumbents close it?** Unlikely to go down-market. Their minimums and sales motion do not fit. Yardi's RFTA tool already covers part of the landlord side.
- **Caution.** The evidence is about price and minimums, not demand. Interview small landlords before building.

### 5. Cross-document verification in one check: rent roll, HAP contract, lease, and cert (partly open)

- **The gap.** A single pass that reconciles the rent roll, the HAP contract (rent and contract terms), the lease, and the certification against each other, with page-cited findings and a dollar impact. This is the same problem Abstractly already solves for lease-versus-roll on commercial deals.
- **Evidence.** The entrants above check certifications against verification documents. None of the public materials I reviewed describe reconciling a HAP contract and rent roll against a lease and cert in one pass. This is an absence in my searches, not proof: I did not check every vendor's feature list.
- **What is already claimed.** RealPage flags file discrepancies (vendor). HousingIntellect reads source documents for certifications (vendor). ExactEstate claims HAP and rent reconciliation (competitor). None claims cross-document rent-roll-to-lease-to-HAP reconciliation with citations.
- **Could incumbents close it?** Possible, but it crosses systems and document types they do not own today.

### 6. Compliance due diligence on affordable portfolios in acquisitions (weakest)

- **The gap.** A buyer or lender reviews a target's LIHTC or HUD portfolio for compliance exposure (recapture risk, late certifications, missing 50059s, rent-limit exposure) before close.
- **Evidence (weak).** RealPage bought Windsor Compliance in 2013 for monitoring of 30k+ affordable units, which shows compliance monitoring has been valued as a service line ([HousingWire](https://housingwire.com/articles/27670-realpage-acquires-compliance-monitoring-firm), fetched). Consulting firms do file reviews. I found no product marketed for acquisition diligence on affordable portfolios.
- **Could incumbents close it?** Possibly, but buyers in diligence are not their current customer. This is a hypothesis to test, not a finding.

### Not a strong gap: layered-deal rule conflicts

- Yardi, MRI (Bostonpost "multi-layered subsidies"), ResMan ("Build-A-Program"), and Entrata (multiple programs per household) all advertise layered-subsidy handling. Keep it as a feature, not a wedge.

### Where Abstractly could still differ

These are the places where I found no equivalent claim in the public materials reviewed. Each is a hypothesis to test in interviews.

1. **Cross-document citations.** Every finding tied to a page and a field in the source document, the way Abstractly's lease extraction already works. Most entrants describe "extraction" or "reading documents" without citations. HousingIntellect says it "extracts every data point," but the page does not describe citations.
2. **One check across rent roll, HAP contract, lease, and certification.** See gap 5.
3. **HCV landlord side.** Small-owner pricing and workflows. The entrants and incumbents above target portfolios, and VoucherReady sells information, not reconciliation.
4. **Portfolio acquisition diligence.** See gap 6. Weakest evidence, but no AI-native entrant I found is marketing it.
5. **Neutrality across vendors.** DEVAL and RealPage sit on their own platform or on top of a PMS they want to own. An audit that accepts exports from several systems and does not require a migration is a different positioning, though I did not verify whether any entrant markets it this way.

---

## Sales cycle and integration realities

- **Who buys.** Owner-side: asset managers, compliance directors at third-party management firms, and regional managers. PHA-side: procurement and the HCV or public housing director, through formal RFPs (for example, the Chicago Housing Authority's 2025 QC file audit RFQ, and a 2025 Miami-Dade extension for Emphasys). Small landlords buy on price and minimums, or use the PHA portal.
- **Integrations needed.**
  - **Yardi.** Interface partners pay an **annual license fee per interface** that varies by interface type and transaction volume (not published). The program requires the company to have existed for at least two years. A third-party aggregator cites about $25K/interface/year and "3+ mutual Voyager clients" (**unverified**; [Supergood](https://supergood.ai/api-report-card/yardi-systems)). A Standard Interface partner gets a sandbox and API access (Yardi page, snippet; 403 on fetch).
  - **RealPage.** Has a certified AppPartner tier (2022 Grace Hill release, snippet). Terms and fees not public.
  - **RentCafe API.** Access terms say pricing is in the contract ([Yardi RentCafe API ToU](https://resources.yardi.com/?p=18614), snippet).
  - **MRI.** No public partner program or fee found in this session. **Not verified.**
  - **TRACS submission.** TRACS access runs through HUD's secure systems and authorized vendors (per ExactEstate, competitor; [HUD secure systems guide](https://www.hud.gov/sites/dfiles/Housing/documents/Guide_to_Accessing_HUD_Secure_Systems_Jan_2023.pdf), not read in this session). Any Abstractly product that touches TRACS needs a real vendor path and HUD access. This is a real cost and timing item I did not size.
- **Implementation.** One Yardi-era source says implementation can equal or exceed the first year of licensing (aggregator, snippet). Yardi's 2020-era fast-track promised about two weeks, capped and likely no longer offered (snippet).
- **Procurement timing.** PHA and HFA contracts run through county boards and RFPs (Miami-Dade item, Georgia DCA RFP, CHA RFQ, snippets). Expect multi-month cycles. **Unverified** as a general rule.

---

## Open questions for interviews

1. Who runs the pre-MOR scrub today: in-house, RightSource or another consultant, Preferred Compliance or Zeffert, or nobody? What does it cost per file?
2. Which systems do you export from, and how often? Does the audit span more than one system?
3. What HOTMA workflow are you using before January 1, 2027? Manual calc, TRACS rent override, or a vendor?
4. For a small landlord with 20–60 voucher units, what do you pay today for HAP tracking? Do you use the PHA portal? Would a $49 kit or a $400/month minimum be the reference point?
5. Have you trialed EliseAI's income verification or HousingIntellect's document reading? What did they miss?
6. Has an acquisition ever stalled on compliance findings? Who did the review?

---

## Sources

Fetched in this session (full page read):
- [Yardi Breeze pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/)
- [RealPage OneSite Affordable page](https://www.realpage.com/lp/property-management-for-affordable-housing)
- [RealPage AI Operations Agent case study, Cambridge Management](https://www.realpage.com/case-studies/streamline-affordale-housing-compliance-with-ai/) (vendor)
- [HousingWire: RealPage acquires Windsor Compliance](https://housingwire.com/articles/27670-realpage-acquires-compliance-monitoring-firm)
- [Software Equity Group: Tenmast acquired by MRI](https://softwareequity.com/transactions/tenmast-acquired-by-mri-software)
- [HUD HOTMA multifamily page](https://www.hud.gov/hud-partners/multifamily-hotma)
- [ExactEstate AI compliance blog](https://www.exactestate.com/blog/ai-for-affordable-housing-compliance-closing-the-audit-gap) (competitor)
- [EliseAI funding announcement](https://eliseai.com/blog/eliseai-raises-250m-series-e) (company)
- [EliseAI affordable features, July 30, 2025](https://eliseai.com/blog/eliseai-gets-an-upgrade-new-features-for-affordable-housing-operators) (company)
- [HousingIntellect homepage](https://housingintellect.io) (vendor)
- [HousingIntellect LIHTC page](https://housingintellect.io/lihtc-compliance-software) (vendor)
- [PHASE launch release, DEVAL, via 01net.it](https://www.01net.it/deval-solutions-inc-launches-phase-the-first-centralized-mor-compliance-platform-for-hud-project-based-section-8-housing/) (reprint; vendor)
- [Pronto Housing Business Wire release, 2021](https://www.businesswire.com/news/home/20211102005853/en/Pronto-Housing-Closes-%242.5M-Seed-Round-Led-By-Wilshire-Lane) (press release)
- [VoucherReady](https://voucherready.com) (vendor)
- [RIOO article, August 2026](https://riooapp.com/blog/hotma-nspire-compliance-deadlines-2026) (vendor)
- [Haven AI](https://usehaven.ai) (vendor)
- [VerbaFlo](https://verbaflo.ai) (vendor)
- [VerbaFlo blog, September 2026](https://www.verbaflo.ai/blog/ai-for-affordable-housing-compliance-section-8-and-hud-operators) (vendor)
- [fac.gov](https://www.fac.gov) (official Federal Audit Clearinghouse, GSA)

Blocked, empty, or unreadable (not verified on the page):
- [Yardi RightSource product page](https://www.yardi.com/product/rightsource/) (403)
- [Yardi interface partner page](https://www.yardi.com/?p=359162) (403)
- [tenantaudit.com](https://www.tenantaudit.com) (empty page); tenantaudit.io (DNS error)
- [HUD Choosing TRACS Compliant Software (PDF)](https://www.hud.gov/sites/dfiles/Housing/documents/Choosing_TRACS_Compliant_Software_Jan_2023.pdf) (binary only)

Search-result snippets (cited inline, not individually fetched):
- [Yardi brochure, RentCafe Affordable](https://www.yardi.com/resources/rentcafe-affordable-housing-brochure/pdf/)
- [Yardi RentCafe API terms](https://resources.yardi.com/?p=18614)
- [Yardi press release, Breeze Premier 2020](https://yardi.com/?p=308179)
- [Yardi PDF, RightSource](https://www.yardi.com/resources/streamlined-affordable-housing-workflows-with-yardi-rightsource/pdf/)
- [Yardi blog, document upload](https://www.yardi.com/blog/wp-json/wp/v2/posts/24096)
- [Mann Report, Yardi RFTA 2023](https://www.mannpublications.com/mannreport/2023/03/16/yardi-introduces-solution-to-ease-voucher-acceptance-makes-it-easier-for-landlords-to-accept-vouchers/)
- [Vendr, Yardi pricing](https://www.vendr.com/marketplace/yardi) (aggregator)
- [Buildium, Yardi Breeze review](https://www.buildium.com/blog/yardi-breeze-review/) (aggregator-adjacent)
- [DoorLoop, RealPage vs Yardi](https://www.doorloop.com/blog/realpage-vs-yardi) (aggregator)
- [Multi-Housing News, Domin-8](https://www.multihousingnews.com/with-acquisition-of-domin-8-realpage-will-cater-to-small-medium-sized-and-affordable-housing-managers/)
- [SEC 10-Q, RealPage 2014](https://www.sec.gov/Archives/edgar/data/0001286225/000128622514000030/rp-2014093010q.htm)
- [G2 RealPage OneSite pricing](https://www.g2.com/products/realpage-onesite/pricing)
- [ExactEstate best-of comparison, Aug 2026](https://www.exactestate.com/blog/best-affordable-housing-software-12-platforms-compared) (competitor; aggregator-style)
- [Grace Hill, RealPage AppPartner](https://gracehill.com/grace-hill-announces-partnerships-with-yardi-and-realpage/)
- [MRI Bostonpost TRACS 202D blog](https://www.mrisoftware.com/blog/bostonpost-property-manager-tracs-202d-affordable-housing-software/)
- [MRI Bostonpost 9.1 blog](https://www.mrisoftware.com/blog/bostonpost-property-manager-9-1-affordable-housing-property-management-software/)
- [MRI affordable compliance page](https://mrisoftware.com/products/affordable-housing-compliance-software/)
- [MRI news, Bostonpost TRACS 202D](https://www.mrisoftware.com/news/mri-software-releases-latest-version-bostonpost-ensure-tracs-202d-compliance)
- [MRI news, HAB acquisition](https://www.mrisoftware.com/sa/?p=23343)
- [MRI news, HAPPY acquisition](https://www.mrisoftware.com/nz/news/happy-software-public-affordable-housing-tech-powerhouse/)
- [Mann Report, MRI PHA Pro 2024](https://www.mannpublications.com/mannreport/2024/05/29/mri-software-unveils-pha-pro-for-public-housing-and-voucher-management-compliance/)
- [ITQlick, Bostonpost pricing](https://www.itqlick.com/mri-bostonpost/pricing) (aggregator; conflicting figures)
- [G2, MRI Affordable & Public Housing](https://www.g2.com/products/mri-affordable-public-housing/reviews)
- [Capterra AU, MRI Affordable Housing](https://www.capterra.com.au/software/1009740/mri-affordable-housing)
- [Entrata affordable page](https://www.entrata.com/affordable) (vendor)
- [Entrata blog, March 2025](https://www.entrata.com/blog/entrata-affordable-bridging-the-gap-between-affordable-and-traditional-property-management) (vendor)
- [ExactEstate, Entrata comparison](https://www.exactestate.com/blog/entrata-vs-exactestate-a-property-management-software-comparison) (competitor)
- [Fortress, Entrata comparison](https://fortresstech.io/compare/entrata) (competitor)
- [G2, Entrata pricing](https://www.g2.com/products/entrata/pricing)
- [Capterra, Entrata reviews](https://www.capterra.com/p/20372/Entrata/reviews/?page=7)
- [ResMan affordable page](https://www.myresman.com/affordable/) (vendor)
- [ResMan compliance solution page](https://myresman.com/solutions/affordable-compliance) (vendor)
- [ResMan blog, LIHTC](https://myresman.com/blog/why-conventional-software-wont-cut-it-lihtc-compliance) (vendor)
- [AppFolio affordable page](https://www-dyn.appfolio.com/markets/affordable-housing) (vendor)
- [ExactEstate, AppFolio alternative](https://www.exactestate.com/appfolio-alternative) (competitor)
- [SoftwareConnect roundup](https://softwareconnect.com/roundups/best-affordable-housing-property-management-software/) (aggregator)
- [Emphasys, myhousing.com](https://myhousing.com/housing-programs/) (vendor)
- [Miami-Dade board memo, 2025](https://www.miamidade.gov/govaction/legistarfiles/MinMatters/Y2025/250968min.pdf) (public record)
- [Apple App Store, Emphasys HQS](https://apps.apple.com/us/app/-/id1616876475)
- [Santa Ana contract record, NMA](https://cc-publicdocs.santa-ana.org/WebLink/1/doc/111028/Page2.aspx) (public record)
- [WOKV, NMA Jacksonville](https://www.wokv.com/news/local/firm-hired-by-jacksonville-housing-authority-run-voucher-program-paid-millions-federal-fines/RRQYGDULO5DYZGJOKFRI2JJQ34/) (news)
- [Georgia DCA contracts, 2019](https://dca.ga.gov/node/6002) (public record)
- [Georgia DCA RFP, compliance file review consultant](https://dca.georgia.gov/node/12506) (public record)
- [CHA RFQ, QC tenant file audits, 2025](https://www.thecha.org/sites/default/files/2025-04/RequestForQuote-QCTenantFileAudits-Rebid_04.25_Procurement.pdf) (public record)
- [RIHousing RFA, Costello](https://rihousing.com/wp-content/uploads/Costello-Consulting-RFA-2024-08-15.pdf) (public record)
- [Zeffert, CARH listing](https://www.carh.org/member-directory-training/name/zeffert-associates-inc/) (trade listing)
- [Zeffert job post](https://recruiting.paylocity.com/Recruiting/Jobs/Details/3393045) (job post)
- [Preferred Compliance Solutions listing](https://prospeo.io/c/preferred-compliance-solutions) (aggregator)
- [EliseAI job post, compliance expert](https://www.builtinboston.com/job/affordable-housing-compliance-expert-housing/10515908) (job post)
- [Bisnow, EliseAI Series E](https://www.bisnow.com/national/news/multifamily/proptech-firm-eliseai-secures-250m-series-e-doubles-workforce-130636) (press coverage)
- [BusinessWire, EliseAI State of AI report, May 2026](https://www.businesswire.com/news/home/20260507960819/en/New-EliseAI-Report-Shows-AI-Is-Cutting-Costs-and-Reshaping-Operations-in-Affordable-Housing) (company-sponsored)
- [Housing Finance, 91% of affordable operators use AI](https://www.housingfinance.com/data-trends/study-91-affordable-housing-operators-are-using-ai) (trade coverage)
- [Snappt income verification](https://snappt.com/income-verification) (vendor)
- [Business Wire, Snappt and TenantCloud, Sept 2025](https://www.businesswire.com/news/home/20250910558211/en) (press release)
- [CB Insights, Pronto Housing](https://www.cbinsights.com/company/pronto-housing) (data site)
- [Bisnow, NYC affordable housing lottery](https://www.bisnow.com/news/new-york/affordable-housing/nyc-affordable-housing-lottery-broken-this-startup-aims-to-fix-it-134154) (trade press)
- [Neighborly Software, HCV](https://www.neighborlysoftware.com/housing-choice-vouchers/) (vendor)
- [Product Hunt, LandlordAI](https://www.producthunt.com/products/landlordai) (vendor)
- [LeaseLenses blog](https://www.leaselenses.com/blog/lease-audit-software-leaselens-ai) (vendor)
- [ExactEstate, section 8 software](https://www.exactestate.com/software/section-8-property-management-software) (competitor)
- [ExactEstate, affordable housing page](https://exactestate.com/markets/affordable-housing) (competitor)
- [ExactEstate, LIHTC software page](https://www.exactestate.com/software/lihtc-compliance-software) (competitor)
- [ExactEstate, TRACS software page](https://www.exactestate.com/software/tracs-software) (competitor)
- [ExactEstate, HOTMA compliance assessment](https://www.exactestate.com/resources/hotma-compliance-assessment) (competitor)
- [NLHA, TRACS vendor list](https://hudnlha.com/?p=14099) (trade group)
- [HUD HCV Landlord Webinar, technology slides](https://www.hud.gov/sites/dfiles/PIH/documents/HCV_Landlord_Webinar3_Technology.pdf) (federal)
- [HUD Guide to Accessing Secure Systems, Jan 2023](https://www.hud.gov/sites/dfiles/Housing/documents/Guide_to_Accessing_HUD_Secure_Systems_Jan_2023.pdf) (federal; not read)
- [FAC audit 20246, third-party mirror](https://fac.procurementexpress.com/audits/20246) (mirror, not fac.gov)
- [FAC finding 549, third-party mirror](https://fac.procurementexpress.com/findings/549) (mirror, not fac.gov)
- [FAC finding 771, third-party mirror](https://fac.procurementexpress.com/findings/771) (mirror, not fac.gov)
- [The Habitat Group, review issues list](https://www.thehabitatgroup.com/articles/print/7845) (industry article, undated)
- [Supergood, Yardi API report card](https://supergood.ai/api-report-card/yardi-systems) (aggregator; unverified fee)
- [CLA, AI in HUD and LIHTC](https://www.claconnect.com/en/resources/articles/26/ai-in-hud-lihtc) (accounting firm)
- [Fortress, Entrata comparison](https://fortresstech.io/compare/entrata) (competitor)
- [DOJ, RealPage suit](https://www.justice.gov/archives/opa/pr/justice-department-sues-realpage-algorithmic-pricing-scheme-harms-millions-american-renters) (cited in section 7 brief; not re-fetched)
- [Section 8 briefing, section 7](./section8.md) (internal)

**Weak-source list for this document:** ExactEstate, Fortress, SoftwareConnect, ITQlick, FitGap, ToolRadar, Spendbase, Vendr, DoorLoop, Supergood, CB Insights, Product Hunt, the 01net.it reprint of DEVAL's release, the "best of" listicles (webpossible, arielsoftwares, wifitalents, terabox), and the Preferred Compliance listing on prospeo.io. Treat all of them as leads, not findings.

**Not verified in this session:** Yardi RightSource and interface-partner terms (403); HUD TRACS vendor guidance (unreadable PDF); RealPage and MRI partner fees; the 2025–2026 status of Pronto Housing, LandlordAI, and HAPPY; the DOJ suit status; the NMA litigation status; any HUD MOR statistic; the EliseAI $125K–$200K salary range; whether EliseAI's income verification has shipped; HousingIntellect's customers, funding, and founding date; DEVAL PHASE's customers and pricing; TenantAudit's existence and prices; the 8823 and SEMAP coverage claims of any vendor.
