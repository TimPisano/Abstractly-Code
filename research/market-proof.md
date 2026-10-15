# Proof of Market — Abstractly (United States)

Date: 2026-10-14
Author: Patrick Pisano (draft)

Purpose
-------
This memo provides a concise, evidence-backed proof-of-market for Abstractly: a lease-abstraction, rent-roll reconciliation, and portfolio analytics product targeted at U.S. commercial real-estate (CRE) acquirers, asset managers, and due-diligence advisors. It includes a TAM/SAM/SOM model, customer archetypes, a savings/value model with worked examples, competitor landscape, trends, assumptions, and next steps.

Executive summary
-----------------
Abstractly solves an expensive, error-prone task in CRE underwriting: reconciling the rent roll and accounting data against source lease documents. Conservatively targeting institutional and mid-market owners in the U.S., a realistic near-term serviceable obtainable market (SOM) is $30M–$150M ARR within three years, driven by subscriptions and per-upload fees. Customer economics (time saved per analyst, faster deal throughput, fewer pricing errors) justify ACVs in the $15k–$45k range for teams managing 100–1,000 units. Key risks: market education, integration friction with legacy workflows, and reliance on back-office document availability. Recommended next steps: populate the TAM model with primary sources and run 8 buyer interviews to validate ACV and adoption friction.

Market sizing (TAM / SAM / SOM)
-------------------------------
Definitions used:
- TAM (Total Addressable Market): annual spend on lease-extraction, verification, and portfolio analytics across the U.S. CRE sector, including property-management SaaS adjacencies and due-diligence services.
- SAM (Serviceable Addressable Market): subset of TAM reachable by Abstractly's product-market fit (institutional owners, PE rollups, third-party asset managers, due-diligence firms).
- SOM (Serviceable Obtainable Market): realistic share of SAM within a 3-year window under conservative, base, and upside scenarios.

High-level assumptions (conservative basis shown):
- Estimated number of U.S. commercial buildings: ~5.9M (U.S. EIA CBECS / market references).
- Addressable institutional properties (buildings/units managed by professional owners with formal lease documents): 200k–500k buildings (conservative 200k).
- Typical institutional customer manages 100–500 units; treat an average institutional customer as 200 units for modeling.
- ACV per customer (subscription + per-upload/usage fees + support): conservative $15k, base $30k, upside $45k.

Scenario math (conservative / base / upside):
- Addressable customers = Addressable properties / 200 units per customer
  - Conservative: 200,000 / 200 = 1,000 customers
  - Base: 350,000 / 200 = 1,750 customers
  - Upside: 500,000 / 200 = 2,500 customers

- TAM (illustrative): if the full addressable property base spent an equivalent of $1B annually across PMS + verification services, the niche for lease abstraction & verification (software + services) plausibly sits in the $0.5B–$3.5B range depending on product breadth and bundling assumptions (see Appendix for sensitivity).

- SOM (3-year target ARR = customers × ACV):
  - Conservative: 1,000 customers × $15k = $15M ARR
  - Base: 1,750 customers × $30k = $52.5M ARR
  - Upside: 2,500 customers × $45k = $112.5M ARR

These numbers map to the tam.csv template. Replace placeholders with primary sources (CoStar, CBRE, Trepp, CBECS) and run sensitivity rows for units/customer, ACV, and penetration.

Customer archetypes
-------------------
1. Acquisitions teams at private-equity and institutional owners (primary)
   - Size: 50–2,500 properties; typical acquisitions team: 2–8 analysts
   - Buying trigger: need to validate deal-level numbers quickly across many leases; reduce time in due diligence and avoid pricing mistakes
2. Third-party asset managers and regional owners (secondary)
   - Need operational validations and recurring portfolio checks; value proposition centers on continual verification and portfolio risk detection
3. Due-diligence/transaction advisory firms and lenders (adjacent)
   - Short-term, high-value engagements (per-deal fees) — attractive go-to-market channel and early revenue source

Value / savings model (worked examples)
---------------------------------------
Key inputs (example assumptions):
- Analyst fully-loaded rate: $80/hr (including overhead and benefits)
- Manual lease review time per lease in diligence: 12 hours (reading, cross-checking, re-typing, citation)
- Abstractly-assisted review time: 2 hours (validation + judgement) — saves 10 hours per lease
- Deals per year per acquisitions team: 10
- Portfolio re-verification cadence (ongoing): 2 hours/week saved on portfolio maintenance per analyst

Example A — Acquisitions team (10 deals/year)
- Hours saved per deal: 10
- Annual deal-hours saved: 10 deals × 10 hours = 100 hours
- Dollar savings (deal-review): 100 × $80 = $8,000/year
- Portfolio maintenance saving: 2 hours/week × 52 = 104 hours → 104 × $80 ≈ $8,320/year
- Total annual savings per team ≈ $16,320

Willingness-to-pay framing:
- If Abstractly captures 25–75% of realized analyst efficiency gains in its pricing (via subscription + per-upload fees), willingness-to-pay range ≈ $4k–$12k per team annually for a small acquisitions-only shopper; larger teams with portfolio monitoring needs justify ACVs well above $15k.
- For a 200-unit asset manager, extra risk-avoidance (fewer pricing errors, faster closings) can push perceived annual value > $30k, supporting higher ACVs.

Enterprise economics (multiples):
- ACV = (annual analyst-labor-savings × capture rate) + value of avoided mispricing (conservative estimate: 0.1% of deal size avoided per material error) + recurring value from portfolio monitoring.

Competitor landscape
---------------------
- Direct competitors: firms and platforms offering lease abstraction + citation (OCR + rules engines). Traditional players include specialized document abstraction consultancies and some emerging software vendors that package extraction pipelines.
- Adjacent incumbents: Yardi, MRI, AppFolio, RealPage (property management suites) — provide PMS and some document storage/automation but typically do not deliver document-linked discrepancy reporting at scale.
- Differentiation for Abstractly: rigorous citation (page + quote), portfolio-level discrepancy reporting, and a focus on underwriting workflows rather than pure operations.

Go-to-market (GTM) and channels
-------------------------------
- Early GTM: sell into advisory firms and boutique due-diligence shops (per-deal revenue, faster sales cycle). Use them as references to reach institutional buyers.
- Mid GTM: direct sales to acquisitions teams at regional owners and asset managers; pilot projects (1–3 months) with sample of 1–2 properties + onboarding fee.
- Partnerships: integrate with PMS vendors as a verification plugin; channel with consultancies and broker networks.
- Pricing model: base subscription (tiered by portfolio size) + per-upload/processing fee + optional professional services for integration and custom reports.

Market trends & timing
----------------------
- Growing institutionalization of CRE and data-driven underwriting increases demand for auditable, traceable source data.
- Rising regulatory and lender scrutiny in the lending/syndication pipeline favors verified documentation and citation traces.
- Adoption of cloud PMS and centralized document repositories facilitates integration and lowers friction for automated abstraction tools.

Risks & mitigations
-------------------
- Data availability: many owners lack clean lease repositories. Mitigation: offer onboarding services and per-deal intake flows; partnerships with document-management vendors.
- Sales cycle length: enterprise buyers require proof and audits. Mitigation: prioritize advisory channel for early revenue and reference accounts.
- Accuracy expectations: customers expect near-perfect extraction. Mitigation: expose confidence, show page-level citations, and design a fast human-in-the-loop correction UI.

Recommendations & next steps
----------------------------
1. Populate the tam.csv with sourced counts: CBECS building counts, CoStar/CBRE estimates of institutional properties, and Trepp/industry transaction volumes. (Assigned to: research)
2. Conduct 8 buyer interviews across archetypes (acquisitions, asset managers, advisory) to validate ACV, expected capture rates of savings, and friction points. (Assigned to: founder/CEO)
3. Build a short ROI calculator (spreadsheet) embedded on the site to let prospective customers model their own savings (inputs: units managed, analyst rate, deals/year, hours saved).
4. Draft a 2-page investor memo (cleaned summary + 1 sensitivity chart) and a one-page GTM plan with initial target accounts.

Appendix A — Sensitivity table (key levers)
-------------------------------------------
- Units per customer (100 / 200 / 500)
- ACV ($15k / $30k / $45k)
- Penetration (0.5% / 1% / 2% of addressable customers)

Appendix B — Sources & notes
----------------------------
- Public statistics and benchmarking to collect: EIA CBECS (building counts), Grand View Research (property-management software market sizing), CBRE and JLL market outlooks (institutional ownership and transaction volumes), Trepp (CMBS exposure), NAIOP and industry whitepapers. Paid reports will be used for precise counts; publicly available proxies suffice for conservative estimates.
- Internal model: research/tam.csv in this repo contains the working assumptions and simple calculated outputs; update it as sources are collected.

Appendix C — Worked example (200-unit portfolio)
------------------------------------------------
Inputs:
- Units: 200
- Analysts supporting asset: 1 (0.5 FTE)
- Analyst rate: $80/hr
- Deals/year: 10
- Hours saved per lease review: 10

Outputs:
- Deal-hours saved: 10 deals × 10 hours = 100 hours
- Portfolio maintenance saved: 2 hrs/week × 52 = 104 hours
- Annual hours saved: 204 → $16,320 annual savings
- Pricing implication: capturing 50% of savings → willingness-to-pay ≈ $8k/year (per team). Bundling across portfolio analytics and multi-team use case justifies higher ACVs.

Notes
-----
This memo is an automated draft based on public benchmarks and conservative assumptions. Next iteration: replace placeholders with exact sourced numbers (links and page citations) and insert real quotes from buyer interviews. Once validated, produce a 2-page investor-ready PDF and a website research page that features the memo plus downloadable data and an ROI calculator.
