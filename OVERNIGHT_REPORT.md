# Overnight report — `fix/concession-detection` (2026-10-02)

**Status: done, pushed, reviewer verdict MERGE. Not merged into `main`; that waits for you.**

- Branch: `fix/concession-detection`, branched from `main` @ `28f2fb9`. Pushed to origin.
- The same commits are also pushed to `claude/nifty-hopper-ss4a7m`, the branch this cloud session was assigned.
- There's no `~/dev/projects/` worktree. This ran in a claude.ai cloud container, so I built it in the container's own checkout.

## What it does, in one paragraph

Concession detection in the Deal Mismatch Report used to be a stub that always returned nothing. It now:
- reads each lease's concessions: free months, move-in specials, recurring $ or % discounts, and one-time credits;
- works out how and when each one applies: what triggered it (move-in, renewal, retention, military, employee), which months it covers, and whether it's repaid on default;
- computes the lease's **net effective rent**;
- flags a rent roll that shows gross rent as if no concession existed.

The dollar impact is the annualized concession value, (gross rent − net effective rent) × 12. Every finding cites the lease page and the clause text.

**Maple Ridge demo:**
- The demo now catches **all 10 planted issues**, including the 3 concessions:
  - A104: 1 month free, $1,075/yr
  - E301: $100/mo off for 6 months, $600/yr
  - I204: $75/mo off for the full term, $900/yr
- The headline is now **$45,355/yr**, matching the README's planted total.

## Phase by phase

| Phase | Result |
|---|---|
| 1. Look for earlier multifamily lease-field work | **Nothing to reuse.** I walked every origin branch (`git ls-remote`, plus a diff against main for "concession"). The only hit was `fix/rent-roll-hardening`, which is already in main. |
| 2. Extract concessions | New `backend/app/concessions.py` (parser + pricing). Both extraction engines now store a `concessions` field with a summary value, a page citation, and structured `items`. **Regex engine** (`field_extractor.py`): parses the lease text directly. **AI engine** (`ai_extraction.py`): the model only finds and quotes the clause, and the same deterministic parser does all the arithmetic on that verbatim quote. That way a dollar figure never comes from the model's own math. `PROMPT_VERSION` bumped to v2. `rent_roll_import.py` recognizes a Concession column, and never reads it as rent. |
| 3. Detectors | `detect_concession_missing` is real now. New `detect_concession_mismatch` compares the rent roll's own concession column against the lease. New `detect_concession_expiring` covers a rent roll showing a discounted rent that will step back up before the lease ends; that's an understatement. All three skip expired leases, because `expired_but_occupied` already counts that unit's full rent. The report also gains a `concession_summary`. |
| 4. Effective rent | `compute_effective_rent` gives net effective rent, this month's rent, and the remaining concession value. `rent_mismatch`, and `portfolio.compute_rent_roll_reconciliation`, no longer flag a rent roll that correctly shows the lease's discounted or net-effective rent. A rent roll *above* gross rent is never suppressed. |
| 5. Demo + tests | Golden test asserts all 10 Maple Ridge findings with exact monthly and annual dollars and citations. `backend/tests/test_concessions.py` has **57 tests**, registered in `run_all_tests.py`, with Anthropic mocked throughout, including one real upload → import → report route run. Every case from the brief is covered: single free month, recurring discount, full-term discount, **stacked** concessions (in one sentence and across pages), and **expiring** concessions (already used / active and burning off / burned off with a stale rent roll). |

## Test results

- **Full suite: 77/78.** The only failure is `test_document_extractor.py`, which needs `tesseract`. It isn't installed in this container, and the test failed the same way before any change (CLAUDE.md rule 9).
- **Corpus false-positive sweep:** I ran the parser over the other 48 lease PDFs in `tests/` and `benchmark_data/`. It found 2 concessions, both genuine commercial free-rent clauses, and **0 false positives**.
- **No real Anthropic calls** were made at any point.

## Review

I ran the `reviewer` subagent four times. The issues it found got smaller each round:

1. **Round 1: fix first.** It found 5 ways ordinary wording produced wrong findings:
   - "one month's rent as a deposit, credited toward the last month" read as a free month. That invented a $1,500/yr overstatement **and** hid a real rent gap.
   - A "credit card" fee read as a rent credit.
   - Rent-roll "Concession End Date" columns read as dollars: 2026-03-31 became $2,026/mo.
   - An AI concession it couldn't read was treated as "no concession".
   - The AI path counted a restated clause twice.
2. **Round 2: fix first.** My round-1 guards were too broad and dropped real concessions: "fee waived" specials, "payable in advance" boilerplate, conditional "not in default" wording, and "Concession Per Month" headers.
3. **Round 3: fix first.** Two narrow holes: interest-free deposits, and forfeiture clauses ("if Tenant defaults, Tenant shall not receive one month free").
4. **Round 4: MERGE.** I fixed its remaining small cleanups anyway (`1f8ec14`).

Each finding has a regression test that failed before its fix.

## Things you should know

1. **Pre-existing test bug fixed.** `test_demo_deal_golden.py` hardcoded `user_id=1`, which only exists on machines whose `.env` sets `ADMIN_EMAIL`. On a clean checkout every upload returned a 500 (`FOREIGN KEY constraint failed`). The fixture now creates a real user.
2. **Demo date caveat.** The Maple Ridge lease dates are anchored to 08/31/2026. A104's lease ends 09/30/2026, so a *live* demo run after that reports A104 as `expired_but_occupied` instead of a concession. That's by design: the concession isn't counted again on top of the full lost rent. The golden test pins today to 08/31/2026. The demo README says this now. The fix would be regenerating the demo with relative dates, which is the same pre-existing drift that affects other units.
3. **Concessions aren't editable in the lease-detail UI yet.** The field-edit and citation routes only accept `FIELD_NAMES`. Adding `concessions` there would also change "missing field" counts everywhere, and would touch existing routes that have no team scoping yet. I left it out on purpose. The Deal Mismatch rows show the citation inline, so the report itself is complete.
4. **Merge overlap with `feature/team-isolation`.** That branch makes `team_id` a required argument of `build_deal_mismatch_report_data` and `insert_lease`. Whichever lands second must update `tests/test_concessions.py`. Both branches also touch `deal_mismatch.py`, `test_deal_mismatch.py` and `run_all_tests.py`, but those merges are mechanical. This is recorded in TASKS.md.
5. **Team isolation (rule 3).** No route or query was added or changed. The detectors read the same unscoped `get_all_effective_leases()` list the report already used. The document-level isolation gap is pre-existing on main, and these checks inherit scoping automatically once `feature/team-isolation` lands.
6. **UI change** is limited to two label strings in `frontend/app/deal-mismatch-view.js`. I syntax-checked it with `node --check` and ran no Playwright pass, because there's no layout change.

## Known limitations (non-blocking, reviewer agreed)

- A non-rent charge mentioned more than ~60 characters before a discount can still be read as a rent discount. Example: "The monthly storage charge of $40 per month is subject to a $10 per month discount".
- A default phrase inserted right after "not" ("Tenant shall not, while in default, receive…") reads as a condition. This wording is rare.
- `compute_rent_roll_reconciliation` uses today's date; the Deal Mismatch Report takes an explicit as-of date.
- The parser handles lease prose. A concession described only in a rent-ledger table isn't extracted.

## Suggested next steps

1. Review and merge `fix/concession-detection` when you're ready (merge-branch skill). Smoke test the demo deployment afterwards.
2. Decide the merge order with `feature/team-isolation` (see note 4).
3. Follow-up: make `concessions` editable and citeable in the lease-detail UI. Best done once team scoping exists for those routes.
4. Optional: regenerate the Maple Ridge demo with dates relative to today so live demos never drift.
