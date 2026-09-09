# Lease-vs-rent-roll reconciliation benchmark

Measures what `compute_rent_roll_reconciliation` (the arithmetic
lease-document ↔ rent-roll cross-check) actually catches, on a
**constructed** test portfolio whose discrepancies are modelled on
documented property-management-system drift.

## Run it

```
cd backend && python3 tools/reconciliation_benchmark/run_benchmark.py
```

Deterministic. Spins up a throwaway temp DB, imports the rent roll and
inserts the lease records through the real routes
(`POST /leases/import-rent-roll`, `GET /portfolio/rent-roll-reconciliation`),
grades the flags against `run_benchmark.py`'s inline ground truth, and
writes `report.md`.

## Latest result

| | |
|---|---|
| Units in portfolio | 31 (3 buildings) |
| Unit pairs matched & compared | 30 |
| Ground-truth discrepancies | 15 across 14 units |
| **Flagged by the engine** | **14 across 13 units** |
| Correctly flagged | 14 / 15 |
| Material discrepancies caught (rent gap / stale expiration / wrong tenant of record) | 12 / 13 |
| Missed | 1 |
| False positives | 0 |

The one miss is a **matching** limitation, not a comparison one: that
unit's address is `Ste. 210` on the lease and `Suite 210` on the rent
roll, and the engine's normalized-address match does not expand
abbreviations, so the pair is never compared.

## What this number is — and is not

- **Is:** a reproducible measure that the engine flags the disagreements
  it is designed to flag (tenant, rent, lease-end-date), across a
  realistic mix of drift causes, without firing on sub-tolerance
  rounding or blank fields.
- **Is not:** field data. Both sides of every pair were authored here.
  It does **not** show the engine catching problems a human on a real
  deal would have missed.

Any external / marketing use of the number must carry the phrase
"constructed test portfolio" (or equivalent). See the module docstring
in `run_benchmark.py` for the full drift-pattern rationale and the
engine's known limitations.
