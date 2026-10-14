# Plan: feature/s8-pii-guard (T0)

## Goal

Testers can upload real voucher leases and tenant documents without Abstractly keeping or forwarding the most sensitive numbers in them:
- **Social Security numbers, dates of birth and bank account or routing numbers are masked** (for example `***-**-1234`) before anything is stored, and before any text goes to Anthropic.
- **Error alert emails stop carrying tracebacks or document text.**
- **A team can switch AI processing off**, so its documents only ever go through the local regex engine.

This implements your Q5 decision (TASKS.md → Section 8 pivot → User decisions) and AUDIT.md §5.2 items 1, 2 and 4. Per the pivot plan, it must merge before testers upload real tenant documents.

## Prior art (searched 2026-10-13)

- **No masking, redaction or PII code exists** on any branch: `git grep` across all refs for ssn, social security, redact, mask, pii, DOB, routing/account number.
- **AUDIT.md §5.1–5.2** (`docs/audit-2026-10-05`) recommends what this plan does: SSN/DOB/bank masking before storage and before Anthropic, a per-team AI-off switch, a traceback scrub, and purging Redis job data. It also confirms uploads are deleted after extraction (`api.py` NamedTemporaryFile → unlink).
- **`docs/BENCHMARK_AND_PRIVACY_AUDIT.md:252-274`**: no file bytes or full text in the DB, but `source.quote` snippets persist. Those quotes are the main thing to mask.
- **`feature/s8-demo-files`** (Oak Hollow) plants fake SSNs (`000-00-00NN`) and DOBs in tenant-file PDFs. This plan reuses those patterns as test inputs, copying the strings rather than depending on that unmerged branch.
- **`feature/s8-data-model`** (T1, unmerged) adds Section 8 `notes` and `head_of_household` columns, with two write choke points: `create_section8_record` and `update_section8_record`.

## Approach

1. **`app/pii.py`: one masking module, pure functions, no I/O.**
   - `mask_text(s) -> (masked, counts)` handles:
     - **SSN** and ITIN: `123-45-6789`, `123 45 6789`, and 9 digits only when next to an SSN keyword. Masked to `***-**-6789`, last 4 kept.
     - **DOB:** a date only when within about 40 characters of a DOB keyword ("DOB", "date of birth", "born", "birth date"). Masked to `**/**/****`. Lease dates such as start, end and notice dates are deliberately left alone.
     - **Bank numbers:** a 4–17 digit number only near a keyword ("account", "acct", "routing", "ABA", "checking", "savings"). Masked except the last 4.
   - `mask_fields(extracted_fields)` walks every field's `value`, `source.quote` and `source_text`, plus `date_candidates[*].source.quote`.
   - It never touches money, unit numbers, phone numbers or ordinary dates. Tests on the Maple Ridge corpus and the Section 8 fixtures prove nothing there changes.
2. **Before storage** (choke points):
   - `database.insert_lease`, `finalize_lease_processing` and `update_lease_field` mask `extracted_fields` and `date_candidates`.
   - Free-text notes are masked on write: `add_comment`, `create_task`/`update_task_fields`, `_add_resolution`, `upsert_assignment`, `dismiss_alert`, `insert_message`, `lease_field_edits` (old/new value + note), and `insert_assistant_conversation` (question and answer).
   - Masking goes inside the `database.py` functions, so every current and future route is covered.
3. **Before Anthropic:**
   - `ai_extraction.call_forced_tool` masks the outgoing page text.
   - `_locate_quote_page` and concession parsing run against the **same masked pages**, so quote-to-page matching still works.
   - `assistant.ask_assistant` masks its question and context.
   - The AI rent-roll validation masks both sides' values.
   - **Redis job args:** `_start_deferred_extraction` enqueues masked `sub_pages`, so Upstash never holds raw SSNs.
4. **Alert emails:** `logging_config.SMTPErrorAlertHandler` sends exception type, module, function and line number, and a request id. It sends no traceback text, no exception message (which can echo document text or an Anthropic error body), and no `getMessage()` in the subject beyond the logger name and a masked, truncated first line. Stdout logs keep full tracebacks for debugging, masked with `mask_text`.
5. **Per-team AI switch:**
   - New nullable column `teams.ai_processing_enabled` (additive; NULL = follow the deployment default).
   - `resolve_engine(team_id=None)` returns `regex` when the team has AI off. It is passed from `_split_and_extract`, the async decision, and the rent-roll-validation gate. `jobs.py` re-checks it before running (a team could switch off mid-queue).
   - `/assistant/ask` returns a clear 403 "AI is turned off for your team" when off.
   - Admin toggles it with `PATCH /teams/<id>` (existing route, `@require_role('admin')`, own team only). The owner console shows it read-only.
   - Pivot constraint 2 is kept: no Render env changes. The deployment-wide default is unchanged.
6. **Section 8 tables (T1):** this branch is off `main`, where those tables don't exist yet. Whichever of T0/T1 merges second adds `mask_text` to `create_section8_record` and `update_section8_record` for `notes` and `head_of_household`. That one-line follow-up goes in TASKS.md for whichever lands second.

## Files to change

- New: `backend/app/pii.py`, `backend/tests/test_pii_guard.py`.
- Edit: `database.py` (the masking calls listed above, plus the `teams` column migration), `ai_extraction.py`, `assistant.py`, `ai_rent_roll_validation.py`, `api.py` (engine resolution per team, assistant gate, `PATCH /teams` field, masked Redis args), `jobs.py`, `logging_config.py`.
- Edit tests: `test_team_isolation.py` (a case for the AI switch), `test_logging_and_health.py` (new email body), `run_all_tests.py`.
- Possibly: 1–2 lines in the admin team settings UI to show the switch (screenshots if so).

## Files not to touch

- Extraction logic itself (`field_extractor.py` patterns).
- Brand files, `render.yaml` and Render env.
- The Section 8 branches.
- Golden fixtures. If a golden quote changes, that is a bug in the masker, not a fixture update.

## Team isolation & roles

- `PATCH /teams/<id>` keeps `@require_role('admin')` and own-team scoping. A team-isolation test covers this: an admin of team A can't flip team B's switch.
- Masking is team-agnostic, a pure function.
- The engine check reads the **caller's** `team_id`.

## Feature flag

None, on purpose. Masking protects every deployment and changes no behaviour except replacing SSN/DOB/bank digits. The AI switch defaults to the current behaviour (NULL = deployment default). Flagging masking off would defeat its purpose.

## Verification

`test_pii_guard.py` covers:
- **Unit tests for `mask_text`.**
  - True positives: Oak Hollow-style `000-00-0001`, an SSN with spaces, "DOB: 03/14/1992", "Date of Birth March 14, 1992", "Routing 021000021 / Account 123456789".
  - True negatives: rent `$1,295.00`, "Unit 104", lease dates, phone `(330) 555-0142`, ZIP codes, HAP contract numbers, `C-104417`.
- **Storage.** An upload of a generated PDF containing an SSN and DOB stores only masked text in `extracted_fields` and `date_candidates`, checked by reading the raw DB row. A comment, task or field edit containing an SSN is stored masked.
- **Anthropic.** With a mocked client, the captured request text contains no SSN, DOB or account number. Quote-to-page location still works.
- **Redis.** The enqueued job args are masked (stubbed queue).
- **Alert email.** A raised exception whose message contains an SSN produces an email with no traceback and no SSN.
- **AI switch.** With AI off, an upload uses regex even with `LEASE_EXTRACTION_ENGINE=ai` and a key set (mocked), and `/assistant/ask` returns 403. The isolation case is covered.
- **No regressions.** Maple Ridge golden test, Section 8 fixture answer-key text and extraction tests unchanged. The full suite runs in the worktree.

## Out of scope

- Encryption at rest, MFA, team export/delete (Q5 says these are tracked separately).
- Anthropic ZDR/DPA and privacy/terms pages (legal work, yours).
- Purging Redis job data on lease delete (AUDIT §5.2). Masking the job args removes the sensitive part; full purge is a follow-up.
- "Income-verification documents must not be kept as uploads": uploads are already never kept (unlinked after extraction). A separate "don't even extract" rule for income documents needs a document-type classifier and belongs to T7b (PBRA recerts).
- Masking names or addresses. They are needed by every feature (Q5 allow-list).

## Open questions

1. **Mask format: keep the last 4 digits** (`***-**-6789`) so an operator can still tell two tenants apart, **or remove them entirely**? I'd keep the last 4; it's the common practice and is useful for matching.
2. **DOB detection is keyword-gated**, so a birth date with no "DOB/born/birth" label nearby slips through. Gating avoids masking lease dates. Is that the right trade-off, or should *every* date that falls more than 16 years before the upload be masked as a likely birth date? That's more aggressive, and could hit old lease dates in long histories.
3. **Existing rows:** should a one-time backfill re-mask `extracted_fields` already in the prod database? It's admin-only and dry-run by default. Prod data is small, and tester and demo are wiped on deploy.
4. **Who can flip the AI switch:** team admins (my default), or only you via the owner console?
