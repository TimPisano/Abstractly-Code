# Plan: feature/affordable-real-accuracy

**Base:** stacked on `feature/affordable-forms` `c6a14ff` (unmerged). Merge only after it.
**Approved:** approach approved by the user in chat, 2026-10-21. This file writes it down.

## Goal

Raise the score on the 11 real affordable-housing documents (`tests/eval/real/`) from **85 / 159 fields (53%)** toward **90% (144)**. Do the free work first: OCR and value cleanup, deterministic readers for fixed formats, and arithmetic cross-checks. Spend API money only where nothing free can reach the value. The user has about $14 of API credit in total. Every paid run gets a cost estimate first and waits for the user's OK. AI responses are cached, so a rerun only pays for documents whose request changed.

## Prior art

Searches run: TASKS.md for `coppertree|affordable-real|eval cache|response cache`; `git log --all --grep` for `coppertree|exhibit a|request hash|eval cache`; the worktree list.
- `feature/affordable-forms` (this branch's base) has the form reader, the router, the HAP/LURA field lists and the eval harness. Everything here builds on it.
- `feature/large-files-any-type` has per-page OCR in the shared upload path. This branch does **not** touch the shared "needs OCR" gate, to avoid a conflict. It changes only the affordable router, which already makes OCR text (`layout_pages`).
- `feature/lease-accuracy` (CRE leases, paused) is separate. It doesn't touch the affordable module.
- `claude/coppertree-1990-paths-f47123` is a clean worktree at `main` with no commits. No overlap.
- No eval response cache exists anywhere. Raw AI responses were never saved, so the first paid run has to re-send the 6 documents the AI already reads.

## Approach

0. **Eval response cache.** In `tests/eval/affordable/run_eval.py` (eval only, not app code), wrap `ai_extraction.call_forced_tool`. The key is sha256 of model + system prompt + user content + tool schema + max_tokens. Each entry is stored as `tests/eval/real/cache/<key>.json`, holding the raw tool input plus usage. Entries are committed: they come from public documents and hold no PII, so other worktrees can reuse them.
   - A cache hit costs $0 and is shown as "cached".
   - `--estimate` lists only the misses and prices only those.
   - `--no-cache` forces a fresh call.
   - Cleanup code that runs after the response reruns on the cached copy.
1. **OCR and value cleanup** (`app/affordable/values.py`, applied to form-reader and AI values alike):
   - a lone `ll` / `Il` after a capitalized word becomes `II` ("Cottonwood ll" → "Cottonwood II");
   - vulgar fractions are spelled out ("23¾" → "23 3/4");
   - HUD contract numbers matching the state + digits + letter + digits shape lose their hyphens ("TX24-E000-008" → "TX24E000008");
   - text-layer pages with a low share of real words are OCR'd again with tesseract (Oak View's "HdusisiggMuttionityyastttre").
2. **HUD-50059 mapping.** Find out why the TDHCA sample loses 7 fields (project, certification type, effective date, unit, TTP, tenant rent, assistance payment), and fix the mapping without breaking the synthetic 50059.
3. **Arithmetic cross-checks** (new `app/affordable/checks.py`). They **flag and never change a value**:
   - **Per unit-mix row:** contract rent + utility allowance = gross rent. The HAP field list's unit-mix table gets `utility_allowance` and `gross_rent` columns.
   - **50059:** tenant rent = TTP − utility allowance, and assistance payment = gross rent − TTP.
   - **Bedroom counts:** the sum of the bedroom-size rows = contract units.
   - **On a mismatch:** the field's confidence drops to `low`, and a `checks` entry is added, for example: "The document's row doesn't add up: contract rent $250 + utility allowance $35 = $285, but gross rent shows $295. Verify with your PHA." Each entry cites the document's own columns. For the definition of gross rent it cites HUD Handbook 4350.3 (Glossary) and 24 CFR 982.4.
   - **Filling a gap:** a missing value is filled only when every other value in the identity was read. It is marked `method: "derived"` at `medium` confidence and labelled "Verify with your PHA".
   - **Coppertree 1990, 1BR row:** the user checked it by hand. It prints $250 + $35 vs gross $295, and a handwritten 2-11-91 note flags the error. It must be flagged, and $250 must stay $250. This is the regression test.
4. **Amasa unit mix.** Add the per-building rows for each bedroom size together; today only the first row per size is kept. A LURA's unit-mix rows are summed only when they repeat a bedroom size.
5. **Unblock the 4 OCR-gated documents (the router only).** When the AI path stops at "needs OCR" or the rent-roll check, use the router's own layout/OCR pages instead of giving up. Add a deterministic reader for PBV Exhibit A tables (bedroom size / units / contract rent). It finds the table by its column headers, not by Riverside-specific wording. The AI field list is used only for what the tables don't hold.
6. **One combined paid run** of `--set real --engine routed`: the 6 documents the AI already reads (re-sent once, to fill the cache), plus the 2013 renewal and the PBVs. **Run `--estimate` first, show it to the user, and wait for OK.** Expected cost is about $0.75–0.90.
7. *(Done 2026-10-22, free: the 811 lease got a deterministic form reader instead of an AI field list; the Amanda Brooke owner turned out to be an answer-key question, REVIEW.md Q7; 5th Street's renamed form field is read by its label. 156 / 165.)* **Small follow-ups, only if needed to reach 90%:** an 811 lease field list (HAP / tenant rent / utility allowance), and the Amanda Brooke owner. Each one gets its own estimate and approval (~$0.10–0.30).

After each step: rerun the free engines (`affordable`, `routed` from the cache), record the score in `docs/research/eval-baseline.md`, and run the synthetic set to catch regressions.

## Files to change
- `backend/app/affordable/values.py`, `ai_fields.py`, `route.py`, `layout.py` (re-OCR of garbled pages), `forms/hud_pbra.py` (50059), `forms/hud_pbv.py` (Exhibit A), new `checks.py`, `extract.py` / `__init__.py` (calling the checks)
- `tests/eval/affordable/run_eval.py` (cache, scoring of `checks`), new `tests/eval/real/cache/`
- `tests/eval/real/REVIEW.md` (the user's hand check of Coppertree 1990 Exhibit 1)
- `docs/research/eval-baseline.md` (scores per step)
- New tests: `backend/tests/test_affordable_checks.py`, `test_affordable_eval_cache.py`, plus cases in the existing affordable tests; each registered in `run_all_tests.py` and starting with `import _test_env`

## Files not to touch
- The shared upload path: `api.py`, `document_extractor.py`, `field_extractor.py`'s OCR gate, `ai_extraction.py` behavior (its helpers are reused as they are)
- `usage_limits.py`, pricing, legal pages, signup, routes, `render.yaml`, `.env`
- Answer-key values. Coppertree stays at $250 / $350. Changing a key needs the user's say-so.

## Team isolation & roles
No routes, tables or queries change. The module stays unwired from uploads. The eval cache is a local file store keyed by request content, for the eval harness only. The app never reads it. Before this goes into uploads, the AI call has to go through `check_team_quota`, and any cache there would need the `team_id` in its key. That's out of scope here.

## Feature flag
`AFFORDABLE_FORMS_MODE` (default off), unchanged. Nothing new runs in the app.

## Verification
- **Regression tests that fail before their fix:**
  - The Coppertree 1BR row is flagged, its confidence drops to low, the note includes "Verify with your PHA", and the value stays $250. Built from a mocked AI response with the document's printed rows. No real PDF and no API.
  - "Cottonwood ll" → "II"; "23¾" → "23 3/4"; the contract number loses its hyphens.
  - Amasa-shaped rows add up to 27 / 11 / 12.
  - The 50059 fields from a fixture of the sample's layout text.
  - An Exhibit A table fixture.
  - The router uses OCR pages when the AI path is gated.
- **Cache tests:** a hit doesn't call the client; a changed prompt or document is a miss; `--estimate` prices only the misses.
- **The checks never change values:** an assertion over every document in the real and synthetic sets that each extracted value is identical with the checks on and off.
- **Eval:** real-set score after each step; the synthetic set must not drop below 94% lease / 92% program (clean) or 89% program (holdout).
- **Full suite** (`run_all_tests.py`, offline, Anthropic mocked); count quoted.
- No UI changes, so no screenshots.

## Out of scope
- Wiring the module into uploads, storing program fields, and the S8 data model.
- Changing the shared OCR gate (that belongs to large-files).
- New answer keys or documents. Adding the Coppertree utility and gross-rent values to the key would grow the denominator, so it's only done if the user asks.
- Any HUD or PHA rule beyond the stated arithmetic identities.

## Open questions
1. **Amasa address:** the key says "109 Kane Creek Blvd."; the agreement lists six building addresses. Keep the key, or score the list as right? Until answered: keep the key (the conservative choice).
2. **Holdout:** 90% here is tuned on the same 11 documents. Should we score 2–3 documents outside this set before calling it done? Default: yes, if the user can name sources. Otherwise it's listed as not verified.
