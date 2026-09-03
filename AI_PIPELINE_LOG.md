# AI Extraction Pipeline — Build & Training Log

Running log for the "wire up real AI extraction + train it" effort.
Newest entries at the bottom of each phase. Written so it can be read
cold on return.

---

## PHASE 1 — Wire up real AI extraction

### 1.0 Honest audit: what was wired vs. stubbed BEFORE this work

Checked by reading the actual code, not assuming.

| Area | State before this work |
|---|---|
| **Lease field extraction** (`app/field_extractor.py`, 1109 lines) | **100% regex / keyword matching.** No model call anywhere. Every field (tenant, rent, dates, CAM, escalation, renewal, exclusivity, …) is a hand-tuned regex with a `high`/`medium`/`low` confidence literal attached to whichever pattern matched. A second "confidence validation" layer (`_apply_confidence_validation`) can only *downgrade* a tier based on range/sanity checks. Genuinely sophisticated for regex, but it is not AI and never was. |
| **Document text extraction** (`app/document_extractor.py`) | Real and format-agnostic (PDF/Excel/CSV/Word/image-OCR/txt → uniform `pages` shape). Not AI, doesn't need to be. Keeps working unchanged underneath the new AI layer. |
| **AI infra in the repo** | One real Anthropic integration already exists: `app/assistant.py` (the in-app portfolio Q&A assistant). It uses `anthropic` SDK, forced tool-use for strict output, `claude-sonnet-5`, a clean `AssistantError`, and per-user in-memory rate limiting. **This work follows that module's conventions closely.** |
| **`anthropic` SDK** | Installed (0.69.0; requirements.txt pins 0.125.0 — minor drift, 0.69 is what runs). |
| **`ANTHROPIC_API_KEY`** | **Present in the environment.** Live calls are possible, so Phase 4 training is real. |
| **Rent roll validation** (Phase 2 target) | Rent-roll *reconciliation* exists (`app/discrepancies.py` `sync_rent_roll_reconciliation`, `app/rent_roll_import.py`) but it is **arithmetic cross-checking** (does row rent match abstracted rent, within tolerance), not a model call. No AI discrepancy analysis. |
| **Plan / account / usage-limit system** | **Not built on `main`.** No `accounts` table, no plans, no per-account scoping, no billing. (There is an in-progress multi-tenant branch in a *separate* worktree — `worktree-agent-ade7619750bfa9a9f` — not merged, not mine.) Phase 1's "enforce plan-based usage limits *if that's already built*" → **skipped, flagged here.** Substitute: added an `ai_extraction_runs` telemetry table (every call logged) so a usage cap has a data source to build on later, and so Phase 5 has real trend data. |
| **Extraction prompts** ("Abstractly — Lease Abstraction Prompts" file) | **Not found in the repo.** Searched `*.md`/`*.py`/`*.txt`. The user offered "pull them from wherever you saved them" — they were never saved here. **Wrote fresh system + extraction prompts** from the field list and the CLAUDE.md quality bar; these are the Phase 4 starting point and should be reviewed against the original when available. |
| **Test suite** | Large (~90 files), split unit vs. live. Unit tests are offline and assert regex-specific behavior. The new AI path is therefore **opt-in per-environment** (see 1.1) so the existing suite stays hermetic and green. |

### 1.1 What was built

**`backend/app/ai_extraction.py`** — the model-backed abstraction engine, modeled on `app/assistant.py`:
- `extract_lease_fields(pages) -> {field: {value, source, confidence, source_text, engine}}` for the same 15 field keys `FieldExtractor` uses, so **everything downstream is unchanged** (confidence summaries, source citations, portfolio math, risk analysis, exports).
- **One API call, forced tool-use** (`record_lease_abstraction`) → output is always a strict, parseable object. No "parse free text and hope".
- **Retry with backoff + jitter** (4 attempts) on transient failures (429/5xx/connection/timeout). **No retry** on auth/400s. **Hard per-request timeout** (`LEASE_EXTRACTION_TIMEOUT`, default 90s) so a hung call can't wedge an upload.
- **Every failure path → `AIExtractionError`** with a plain-language message. Never a raw SDK exception, never a partial dict.
- **Degrade-don't-drop** on a single bad field: a value with no verbatim quote is kept but forced to `low` + `validation_note`; a garbled confidence becomes `low`. A verbatim quote is located back to its source page so `source` still matches the `{page, quote}` shape every citation consumer expects; `source_text` keeps the raw quote too.
- **Document cap** (200k chars) with a visible truncation marker so a pathological upload can't produce a runaway request.
- Reconstructed **system prompt + per-field guidance + confidence rubric** (the original "Abstractly" prompts weren't in the repo). This is the Phase 4 tuning surface.

**Wiring** (`backend/app/api.py`):
- New `_split_and_extract(pages, field_extractor)` — regex boundary detection (cheap, structural), then per-lease extraction via `ai_extraction.resolve_engine()`. `date_candidates` stays regex-derived (it's a separate consistency signal, not a user value).
- Used by **every** upload path: `POST /leases`, `/leases/batch`, `/leases/<id>/resubmit`, `/leases/<id>/amendments`, `/extract`, `/leases/sample`.
- `AIExtractionError` → **502 with the plain message, no regex fallback, nothing persisted**. (User's explicit instruction: honest failure over silent wrong answer.)
- Telemetry: `_record_ai_run` writes one `ai_extraction_runs` row per call; `_persist_split_leases` / resubmit / amendment link it to the created lease id.

**`backend/app/database.py`**:
- New `ai_extraction_runs` table (append-only): `created_at, kind, engine, model, status, lease_id, field_count, found_count, high/medium/low/not_found_count, latency_ms, input_tokens, output_tokens, error_message, detail`. Indexed on `created_at` and `lease_id`. Added to `reset_db()`.
- `record_ai_extraction_run(...)`, `link_ai_extraction_run_to_lease(...)`, `list_ai_extraction_runs(...)`.

**Engine selection** — `resolve_engine()`:
- `LEASE_EXTRACTION_ENGINE=ai|regex` explicit override wins.
- else `LEASE_AI_EXTRACTION` truthy + `ANTHROPIC_API_KEY` present → `ai`.
- else `regex`.
- **Default off** — deliberate: the ~90-file offline unit suite stays hermetic with zero fragile "am I in a test" detection. `run_all_tests.py` also force-sets `LEASE_EXTRACTION_ENGINE=regex` for every subprocess (same defense-in-depth pattern the email-storm fix established). Turning AI on is one visible config line (`backend/.env` sets it for the running app; Phase 4's harness sets it; documented in `.env.example`).

**Tests** — `backend/tests/test_ai_extraction.py` (13 cases, all green, mocked client — real end-to-end call is Phase 4 / a `--live` test):
payload→shape mapping + page-locating; degrade-don't-drop rules; retry-then-raise; no-retry on auth/400; no-tool-use → clean error; empty pages; `resolve_engine` flag matrix; upload route uses AI + writes linked telemetry; upload route 502s cleanly with nothing persisted.

### 1.2 Plan-based usage limits — SKIPPED (not built on `main`), flagged

No `accounts`/plans/billing exists on `main` (the multi-tenant branch is unmerged, in another worktree). Per the user's own conditional ("*if that's already built*"), skipped. Substitute in place: the `ai_extraction_runs` table is the count source a per-account monthly cap would read from once accounts land — the hook is `_record_ai_run` in `api.py`.

### 1.3 Follow-ups / open items
- **Prompts**: replace the reconstructed prompts in `ai_extraction.py` with the original "Abstractly — Lease Abstraction Prompts" when available; re-run Phase 4 to confirm no regression.
- **"Unusual/non-standard terms"** (a CLAUDE.md core requirement) is not yet its own field — regex never had it. Candidate to add in Phase 4/5 as an AI-only field once the 15 core fields are calibrated.
- `requirements.txt` pins `anthropic==0.125.0`; installed is `0.69.0`. Not touched here (out of scope), but the pin should be reconciled.
