# Lease-vs-rent-roll reconciliation benchmark

**Constructed test portfolio.** Both the lease-document side and the rent-roll
side of every unit were authored for this benchmark; the discrepancies are
modelled on documented PM-system drift patterns. This measures what the
engine flags and what it correctly leaves alone -- not field performance on
a real deal. See this script's module docstring.

## Portfolio

- **31 units** across 3 buildings
- Rent roll rows imported: **31**
- Lease documents on file: **31**
- Unit pairs the engine could match and compare: **30**
  (of 31 units; 1 not compared -- see limitations below)

## Headline result

- Discrepancies flagged by the engine: **14** across **13** units
- Ground-truth discrepancies in the portfolio: **15** across **14** units
- Correctly flagged: **14** / 15
- Material discrepancies (rent gap, wrong expiration, wrong tenant of record) caught: **12** / 13
- Missed: **1**
- False positives (flagged where truth says agree): **0**

## Correctly flagged

- **Unit 102** (A) - `rent_amount` [material]: rent roll `$8,900.00` vs lease `$9,724.00`
  - Escalation drift: 3%/yr since 2020 has stepped rent to $9,724; PM system still shows the original $8,900.
- **Unit 104** (A) - `tenant` [name-form]: rent roll `Sunrise Bagel Co.` vs lease `Sunrise Bagel Company, LLC`
  - Name form: rent roll carries the trade name 'Sunrise Bagel Co.', lease is signed 'Sunrise Bagel Company, LLC'.
- **Unit 106** (A) - `lease_end_date` [material]: rent roll `01/31/2027` vs lease `January 31, 2030`
  - Lease extended to 2030 by a 2024 amendment; rent roll still shows the original 2027 expiration.
- **Unit 110** (A) - `lease_end_date` [material]: rent roll `12/31/2029` vs lease `December 31, 2031`
  - Lease extended to 2031 by amendment; rent roll shows the original 2029 date.
- **Unit 110** (A) - `rent_amount` [material]: rent roll `$7,500.00` vs lease `$8,100.00`
  - Escalation drift: two annual 4% steps taken; PM system shows Year-1 rent.
- **Unit 111** (A) - `rent_amount` [material]: rent roll `$3,000.00` vs lease `$3,180.00`
  - Escalation drift: annual CPI steps since 2020; PM system not updated.
- **Unit 200** (B) - `rent_amount` [material]: rent roll `$22,000.00` vs lease `$23,600.00`
  - Escalation drift: 2.5%/yr since 2022; PM system shows original rent.
- **Unit 220** (B) - `lease_end_date` [material]: rent roll `08/31/2026` vs lease `August 31, 2027`
  - Lease renewed for a further year (amendment); rent roll shows the pre-renewal 2026 expiration.
- **Unit 230** (B) - `rent_amount` [material]: rent roll `$15,000.00` vs lease `$16,750.00`
  - Post-renewal reset: 2024 renewal option exercised at 95% of FMV ($16,750); rent roll still shows the expiring-term $15,000.
- **Unit 245** (B) - `tenant` [name-form]: rent roll `Alder & Finch` vs lease `Alder & Finch Accountancy Corporation`
  - Name form: rent roll shows 'Alder & Finch', lease is 'Alder & Finch Accountancy Corporation'.
- **Unit C-2** (C) - `rent_amount` [material]: rent roll `$16,700.00` vs lease `$18,000.00`
  - Escalation drift: annual 3.75% steps; PM system shows original rent.
- **Unit C-4** (C) - `lease_end_date` [material]: rent roll `08/31/2027` vs lease `August 31, 2026`
  - Rent roll expiration keyed as 2027; lease says 2026 (data-entry error -- overstates remaining term).
- **Unit C-6** (C) - `tenant` [material]: rent roll `Redwood Cold Storage Partners, LLC` vs lease `Redwood Cold Storage, LLC`
  - Tenant of record: lease was assigned to 'Redwood Cold Storage Partners, LLC' (assignment on file with PM); the lease document on hand is the original, pre-assignment entity.
- **Unit C-8** (C) - `rent_amount` [material]: rent roll `$12,000.00` vs lease `$12,750.00`
  - Escalation drift: fixed $250/yr steps in the lease; PM system not updated.

## Missed (ground truth said flag, engine did not)

- **Unit 210** (B) - `rent_amount`: Real escalation-drift rent gap -- BUT the address is 'Ste. 210' on the lease and 'Suite 210' on the rent roll, which the engine's exact normalized-address match does not reconcile, so this pair is never compared.

## False positives

_None. Every control unit (sub-tolerance rounding, blank fields) was correctly left unflagged._

## Controls (must not flag)

- Unit 105: $4/mo difference -- inside the $5 abs / 1% pct tolerance, must NOT flag. -> correctly not flagged
- Unit 108: rent blank on the rent roll side -- not comparable, must NOT flag. -> correctly not flagged
- Unit 240: same end date on both sides, written legal-style on the lease ('February 28, 2028') and MM/DD/YYYY on the rent roll ('02/28/2028') -- format difference only, must NOT flag. -> correctly not flagged

## Known limitations exercised here

- **Exact-address matching only.** Unit 210 (Building B) has a real rent
  discrepancy, but the lease says `Ste. 210` and the rent roll says
  `Suite 210`. The engine normalizes case and punctuation but does not
  expand abbreviations, so the two never match and the unit is never
  compared. Counted as a miss above.
- **Three fields only.** tenant, rent_amount, lease_end_date. A drifted
  security deposit, CAM, or lease *start* date is not checked by the
  arithmetic engine.
- **Any tenant-name difference flags.** DBA-vs-legal-entity name forms
  (units 104, 245) are flagged the same as a genuinely wrong tenant of
  record (unit C-6). The engine surfaces the difference; a human decides
  which kind it is.

## Reproduce

```
cd backend && python3 tools/reconciliation_benchmark/run_benchmark.py
```
Runs against a throwaway temp database through the real import +
reconciliation routes. Deterministic -- no AI, no network.
