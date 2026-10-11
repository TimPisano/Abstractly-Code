# fix/section8-tenant-share

## Goal

When a syndicator uploads a rent roll for a property with Section 8 voucher
units, each unit's rent must be the **contract rent** (tenant share + HAP),
never the tenant's share alone. Where a rent roll gives the contract rent
*and* the split, Abstractly checks that they add up and tells the user,
unit by unit, when they don't. Market-rate units and market-only rent rolls
behave exactly as before.

## Prior art

Searches: `TASKS.md` for section 8 / HAP / tenant share / voucher;
`git log --all --grep` for section 8 / tenant share / hap / voucher;
`git grep tenant_portion|hap_amount|tenant_share` across every branch;
stash list.

- **`qa/overnight-gauntlet` `a1cff89`** (reviewed MERGE, not merged yet,
  waiting on 3 user decisions in its QA_REPORT): added the
  `tenant_portion` and `hap` column aliases, plus `rent = portion + HAP`
  when there's no contract-rent column. It also reads a "Rent" column that
  equals the portion as the portion + HAP. Plus one regression test. **This
  branch builds on it** (branched off its tip `906eaab`). Building off
  `main` instead would mean redoing that commit next to it. The branch
  also changes `rent_roll_import.py` by +402/−20 vs. main, so the two
  copies would conflict.
- `feature/lease-intelligence`: the *lease* side (`multifamily_charges.py`
  reads contract/tenant/HAP from the lease PDF, flag
  `LEASE_MULTIFAMILY_FIELDS`). Not touched here.
- `feature/s8-demo-files`, `qa/section8-fixtures` (claimed today, fixtures
  only): generate S8 rent rolls with Contract Rent / Tenant Rent / HAP
  columns. No code overlap. Their files can later be run through this
  validation.
- No stashes relevant.

Gaps still open on the gauntlet base, each reproduced with a probe script:

| Rent roll | Today (main and gauntlet) | Should be |
|---|---|---|
| Only a `Tenant Portion`/`Tenant Share` column, no HAP, no rent | tenant share imported as the rent ($412) | not used as rent; flagged |
| `Contract Rent 1400, Tenant Rent 412, HAP 900` | $1,400, silently | $1,400, flagged: off by $88 |
| `Rent 500, Tenant Portion 412, HAP 988` | $500, silently | flagged: Rent ≠ 412 + 988 |
| `Tenant Portion 412, HAP 988` | $1,400 but citation quote is a made-up "$1,400.00" | quote shows the two real cells |
| OCR/PDF rent roll | `result["warnings"] = table.warnings` would wipe any parse warning | warnings merged |

## Approach

All changes are in `backend/app/rent_roll_import.py`, in the per-row rent
block of `parse_rent_roll_rows`. I'll pull it out into one helper,
`_resolve_section8_rent(...)`, that returns `(rent, quote, issue)`.

1. **Rule:** contract rent = tenant share + HAP. A blank HAP cell on a
   unit counts as 0, so a market unit in a mixed roll gets rent = its share.
2. **Rent column + share + HAP all present** (any `rent_amount` alias:
   Contract Rent, Gross Rent, Rent…): compare. If they differ by more than
   **$1.00** (HAP and tenant share are rounded to whole dollars; user
   decision 2026-10-11):
   - if the rent column equals the share (within $1) (the "Rent" column is really
     the tenant's share), use share + HAP. Same as today, but now it's
     reported.
   - otherwise keep the stated contract rent, mark the field
     `confidence: "low"`, and flag the row with all three numbers and the
     gap.
3. **Share column with no HAP column and no rent column:**
   - unambiguous Section 8 labels (`tenant portion`, `tenant share`,
     `resident portion`, `tenant paid/pays/payment`): **do not** use it as
     rent. Leave rent blank and flag it ("this file shows only the tenant's
     share; contract rent can't be determined without the HAP").
   - generic labels (`tenant rent`, `resident rent`): treat as the rent
     on a market-rate roll. **But** if the file (any header naming
     voucher / Section 8 / HCV / PBV / PBRA / HAP / subsidy / PHA /
     housing authority / utility allowance) or the unit's own row (a cell
     saying Section 8, S8, HCV, voucher, PBV, PBRA, HAP, PHA, housing
     authority) shows a voucher indicator, **don't guess**. Leave that
     unit's rent blank and flag it as ambiguous, with the figure the file
     showed, for the user to confirm. With a file-level indicator, every
     unit is flagged. With only a row-level one, just that unit is.
     (Decided by the user 2026-10-11.)
4. **HAP present but share blank** on a row: rent = HAP, flagged ("tenant
   share missing").
5. **Citations:** a derived rent gets the quote `"Tenant share $412.00 +
   HAP $988.00"` with that row's number. No more invented quote.
6. **Flags:** `parse_rent_roll_rows` returns a `warnings` list. The
   upload screen already shows it word for word, with no UI change. To
   avoid 200 lines on a big file, each kind of issue is one warning
   listing its units, capped at 10 and then "+N more". Mismatch warnings
   also give each unit's dollar gap. The full per-row detail goes in a new
   `section8_checks` list in the result. The import route passes it
   through untouched, and it's handy for tests and later report work.
7. Fix the OCR path so it merges table warnings with parse warnings
   instead of overwriting them. Make sure the xlsx multi-sheet path keeps
   the warnings too.

## Files to change

- `backend/app/rent_roll_import.py`: the logic above.
- `backend/app/api.py`: at most one line, to pass `section8_checks` into
  the import response next to `warnings` (only if it isn't already passed
  through generically). No route, role, or query changes.
- `backend/tests/test_section8_rent_roll.py` (new; registered in
  `run_all_tests.py`).

## Files not to touch

Frontend (no styling or markup changes; existing warnings box only),
`deal_mismatch*.py`, lease extraction (`multifamily_charges.py`,
`ai_extraction.py`), database schema, T-12.

## Team isolation & roles

No route or document query is added or changed. If `api.py` needs that
one pass-through line, it's inside the existing rent-roll import route.
That route keeps its current `@require_role`. Its document scoping is the
same as `main` (per-deployment, see CLAUDE.md "Tenancy"), and this branch
doesn't change it.

## Feature flag

None. This is a correctness fix to existing import behavior. Market-only
rent rolls produce byte-identical results (a test asserts it on Maple
Ridge).

## Verification

New `test_section8_rent_roll.py`. Each test was failing before the fix
where it applies:
- **Voucher units:** portion + HAP → contract rent with a correct citation;
  matching Contract Rent → no flag; mismatched Contract Rent → $ gap flagged
  with low confidence; "Rent" equal to the share → share + HAP plus a flag;
  share-only column → no rent plus a flag; HAP with no share → flag.
- **Market units:** plain `Rent` roll → unchanged, no warnings, no
  `section8_checks`; Maple Ridge demo rent roll → identical output to the
  base branch.
- **Mixed roll:** voucher + market rows in one file (HAP blank or 0 on
  market rows) → each row correct, flags only on the bad voucher rows,
  warning lists the right units, cap + "+N more" works.
- XLSX version of the mixed roll, and the OCR warnings merge (mocked
  table).
- Full `python backend/tests/run_all_tests.py`. No Anthropic calls.

## Out of scope

- A Section 8 discrepancy type in the Deal Mismatch Report (dollar impact,
  PDF/Excel export). It's the natural next step, and goes in TASKS.md
  "Up next".
- Comparing the rent roll's HAP to the lease/HAP contract or the PHA
  register.
- Utility allowance / utility reimbursement checks.
- Any UI change, including new styling for the warnings.

## Decisions (user, 2026-10-11)

1. Base branch: build on `qa/overnight-gauntlet` (`a1cff89`). This branch
   merges after it.
2. Bare "Tenant Rent" with no HAP column: rent on market-rate rolls;
   flagged as ambiguous (rent left blank) when the file or unit shows any
   voucher/HAP indicator.
3. Mismatch tolerance: $1.00.

Known limit: title rows *above* the header row ("Section 8 Rent Roll")
don't reach `parse_rent_roll_rows`, so they don't count as a file-level
indicator. Only headers and row cells do.
