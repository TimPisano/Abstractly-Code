# Homepage claim prep — benchmark + privacy audit

Working document for the accuracy / speed / privacy statement intended
for the Abstractly homepage. Last updated 2026-09-09.

**Nothing here is approved for publication.** No number goes on the site
until it has been measured on the shipping engine and confirmed with the
user.

## Status of the 5-step checklist

| Step | State |
|---|---|
| 1. Demo data prep | **Corpus ready** — 12 real SEC-filed commercial leases in `backend/benchmark_data/leases/`. Loading into a clean demo account is gated on the AI key (regex end-to-end already verified). |
| 2. Accuracy benchmark | **Ground truth complete** (12 leases × 15 fields, hand-recorded from the documents). **Benchmark not yet run** — gated on a funded `ANTHROPIC_API_KEY`; per decision, it must be measured on the AI engine only, not the regex fallback. |
| 3. Speed benchmark | **Not started.** Needs the AI key (pipeline timing) + one honest manual timed pass on a full-length lease. |
| 4. Privacy audit | **Complete** — findings below. |
| 5. Update the site | Not started. Gated on 2–4 being done and the numbers confirmed. |

---

## ⛔ Blocker: the AI extraction pipeline cannot run in this environment

The `ANTHROPIC_API_KEY` here has **no credit balance**. Re-verified
2026-09-09 with a live one-token call:

```
400 invalid_request_error —
"Your credit balance is too low to access the Anthropic API."
```

Same blocker recorded in `AI_PIPELINE_LOG.md` on 2026-09-03.
`backend/.env` currently pins `LEASE_EXTRACTION_ENGINE=regex` so uploads
keep working.

**Decision on file (2026-09-09):** the user is funding the key so the
benchmark and the product real testers use this week are the same thing.
The accuracy and speed benchmarks are **paused** until the user confirms
the key is funded and working, then run against the **AI engine only**.
Do not publish a regex number as a stand-in.

One caveat for when it runs: the "Abstractly — Lease Abstraction Prompts"
document has never been in the repo; `app/ai_extraction.py`'s prompt is a
reconstruction. If the real prompt exists elsewhere, load it before
measuring.

---

## Step 1 — Demo data (real leases)

**`backend/benchmark_data/` — 12 real commercial leases**, each a public
SEC EDGAR filing exhibit. Full provenance (filer, CIK, URL, selection
criteria) in `benchmark_data/SOURCES.md`.

- Type mix: 5 office, 1 office/medical, 1 medical, 4 retail, 1 industrial.
- Lease dates 1998–2026. Rent structures: flat, stepped, CPI-indexed,
  percentage rent, triple-net.
- Every one is a **clean single unamended lease** — screened out
  amendments, assignments, guaranties, subleases, and (the hard part)
  leases with their amendments bundled into the same document. Five
  earlier candidates were dropped for exactly that during ground-truth
  review (Credence had an internal date contradiction; Velodyne,
  McCormick, PTEK, Saxon, Ukrop's, Imperium bundled amendments).
- Unredacted economic terms. Modern filings increasingly redact rent/term
  with `[***]`, which is why the corpus skews 2001–2006.

**Ground truth:** `benchmark_data/ground_truth.json` (+ `.csv`). All 15
fields for all 12 leases, recorded by hand from the source text. Nothing
guessed. Where a lease defines commencement/expiration by a construction
milestone rather than a calendar date, the value is prefixed `derived:`
and states what the document actually says (this is the correct
extraction target and a fair test of the tool). `null` = the lease does
not address that field, so the correct extraction result is "not found"
(e.g. 4 of 12 leases have an explicit "Security Deposit: None"; 10 of 12
have no tenant exclusivity clause).

**Rent rolls:** 3 synthesized exports (`benchmark_data/rent_rolls/` —
broker CSV, Yardi-style, AppFolio-style) covering the 12 units, each
built from the real lease terms with a few deliberately planted
lease-vs-rent-roll disagreements + one phantom vacant unit
(`ground_truth.json['rent_rolls']`). A rent roll is a management-system
export, so synthesizing a plausible one from known lease terms is
legitimate; it is clearly labelled FABRICATED and is not used for any
accuracy number.

**End-to-end flow** (`load_demo_and_verify.py`, isolated temp DB, real
`document_extractor` → engine → rent-roll import → reconciliation),
2026-09-09:

| Mode | Flow completes | Reconciliation vs. 5 planted disagreements |
|---|---|---|
| regex extraction (real pipeline) | **no errors** | 0/5 (regex mis-extracts the lease side — see Step 2) |
| ground-truth-quality fields | **no errors** | 1/5 |

**The flow runs clean end-to-end** — 12 leases + 3 rent rolls import,
reconciliation computes, no exceptions. That is the Step 1 bar and it is
met.

**But reconciliation caught only 1 of 5 planted disagreements even fed
demo-quality fields** — because it pairs a lease record to a rent-roll
row by **exact address string match**, and the corpus's real addresses
carry suite numbers, county names, and shopping-center names that the
rent roll writes differently ("10 Fila Way, Sparks, MD 21152 (Lot 7,
Sparks Corporate Center)" vs "10 Fila Way, Sparks, Maryland 21152"). The
one it caught had byte-identical addresses on both sides. This is the
same exact-match brittleness the reconciliation benchmark already
documented, now confirmed on real-world address formatting.
**Implication:** a recorded demo needs either (a) normalized addresses on
both sides, or (b) fuzzy address matching in `compute_rent_roll_
reconciliation` — the latter is the real fix. Flag for the user.

---

## Step 2 — Accuracy

### Not yet measured on the shipping engine

The benchmark harness is built and ready
(`benchmark_data/run_accuracy_benchmark.py`): it runs all 12 leases
through the real pipeline front door, then the AI engine, and scores
field-by-field against `ground_truth.json` via `app/extraction_scoring.py`
(per-field accuracy, one overall %, high-confidence-and-wrong list,
confidence calibration, per-lease timing).

**Run it the moment the key is confirmed:**
```
LEASE_AI_EXTRACTION=true PYTHONPATH=. venv/bin/python benchmark_data/run_accuracy_benchmark.py --dump
```

### Scoring caveat that must travel with the number

`extraction_scoring.values_match()` substring/parse-matches the free-text
fields (`property_address`, `permitted_use`, `exclusivity_clause`,
`insurance_requirements`, `default_cure_period`). The ground-truth values
are full human-verified descriptions, so a semantically-correct
extraction phrased differently can auto-score as WRONG. The script prints
the full expected-vs-extracted text for every field for this reason.
**Record both** the raw auto-score and the human-reviewed accuracy here
when the run happens; only the reviewed number can be quoted.

### Reference: regex engine on this corpus (NOT for publication)

A plumbing run of the harness with the regex fallback on the 12 real
leases: **36.7% auto-score** overall (n=12, 180 pairs; 43
high-confidence-and-wrong; P(correct|high)=0.49). This number is dragged
down by the substring-match caveat above and is the *fallback* engine, so
it is a floor for "how bad unreviewed regex looks on real leases," not a
claim. It is consistent with the earlier finding that regex scores ~51%
on realistic leases vs ~78–81% on the synthetic corpus it was tuned
against.

### Reference: the retired synthetic attempt

`benchmark_data/archive/` holds an earlier pass — 10 machine-generated
fictional leases with machine-generated ground truth. Regex scored 50.7%
(n=10) on those and 81.1% (n=60) on a larger synthetic set. **Retired**
because machine-generated documents + machine-generated answer key is not
"realistic leases with human-verified ground truth," which is what a
public claim needs. Kept only as context for the synthetic-vs-real gap.

### The homepage's current position

The live FAQ argues *against* an accuracy percentage: *"We're not going to
hand you a made-up accuracy percentage — anyone can print a number, and
it means nothing without knowing what it was measured against."* Adding a
number reverses a published stance — a deliberate choice for the user to
make, not a silent edit. If a number does go up, it should carry n=12 and
name the engine and the corpus (real SEC leases), per the checklist's own
instruction not to hide a small sample.

### Reconciliation stat (`[STAT PENDING]` slot) — dropped for now

`tools/reconciliation_benchmark/` measures the comparison engine (14/15
planted discrepancies caught, 0 false positives) on **hand-authored,
already-correct** field data — not end-to-end from uploaded documents.
**Per decision 2026-09-09, this is not going on the homepage** — hold all
homepage numbers until the real AI extraction accuracy benchmark is done
and confirmed.

---

## Step 3 — Speed

### Not yet measured

- **AI pipeline:** cannot be timed until the key is funded. The code's
  timeout config and comments put it at ~5–15 s per lease.
- **Regex pipeline:** the harness measured a mean of ~116 ms per lease
  across the 12 real leases (20–90 pages each) — extraction call only,
  not upload-to-result. (An earlier run on the ~1-page synthetic
  fixtures showed ~6 ms; the homepage's "0.06 seconds on a 40-page
  lease" is a regex figure that has not been reproduced at 40 pages.)

### Manual baseline — still owed

A genuine timed pass of a human filling the same 15 fields from a
full-length lease has **not** been done (an earlier attempt used ~1-page
synthetic docs, ~3 min, which understates a real lease). Published
industry norm for a full lease abstract is 1–3 hours; a focused
15-field pull is more like 20–45 minutes. Do this honestly on one of the
12 corpus leases before quoting a time-saved multiple.

### Time-saved framing (when both numbers exist)

A raw multiple (30 min ÷ 0.06 s = "30,000×") is technically true and
useless. The defensible statement:

> A person spends [X] minutes reading a lease to pull these terms. The
> software returns a first-pass abstract in [Y], with every field linked
> to the page and quote it came from — so the person is verifying, not
> transcribing.

Fill X and Y from the real timed passes; name the engine.

---

## Step 4 — Privacy audit (COMPLETE)

Traced by reading the code, not the docs.

### What happens to an uploaded lease file

1. **Received** by an upload route (`POST /leases`, `/leases/batch`,
   `/leases/<id>/resubmit`, `/leases/<id>/amendments`, `/extract`,
   `/leases/sample`), all funnelling into
   `_extract_leases_from_file_storage` (`backend/app/api.py:503`).
2. **Written to disk once**, to a `tempfile.NamedTemporaryFile(
   delete=False)` in the OS temp dir (`api.py:540`). This is the *only*
   place in `backend/app/` that writes an upload to disk — verified by
   grepping every `NamedTemporaryFile`/`mkstemp`/`mkdtemp`. The
   rent-roll and T12 import routes read into memory and never touch disk.
3. **Text extracted locally** — `pdf_extractor.py` /
   `document_extractor.py` via `pypdf`, plus `pytesseract` OCR for
   scanned pages (OCR shells out to `pdf2image`, which uses its own
   auto-cleaned temp dir for page images). **No network calls** in this
   path.
4. **Field extraction:** regex (`field_extractor.py`, 100% local) by
   default; the AI engine sends page text to Anthropic (see Third
   parties).
5. **Temp file deleted** via `os.unlink` in a `finally` block
   (`api.py:666–668`) that runs on the success path, the
   extraction-error path, and the unexpected-exception path.

**→ The uploaded document file is auto-deleted immediately after
processing.** The checklist's "auto-delete after processing" item is
already implemented *for the file itself*. Only failure mode: a hard
process kill in the milliseconds between save and unlink could orphan a
temp file in the OS temp dir until the OS clears it; on the Render free
tier the container filesystem is ephemeral and reset every deploy, which
bounds that.

### What persists

The `leases` table (`database.py:342`) stores `filename`, `uploaded_at`,
`extracted_fields` (JSON), `display_name`, `date_candidates`,
`source_page_start/end`, versioning columns.

- **No raw file bytes. No full-document-text column.** Confirmed against
  the schema and every migration.
- `extracted_fields` **does contain verbatim lease text** — one short
  source quote per found field, plus its page number (the product's
  "every value traces to a quote" promise). So short verbatim snippets,
  including party names and the property address, persist in the DB. The
  full document does not.
- `filename` persists as uploaded (may itself contain a tenant name).
- Extracted data persists **until a user deletes it** (delete + bulk
  delete endpoints exist; the homepage promises this). **No time-based
  auto-purge of extracted data.**
- **Production note:** the Render deployment is free tier with **no
  persistent disk** (`render.yaml` — the `disk:` block is commented out),
  so the production SQLite file is wiped on every redeploy/restart.
  Extracted data is not durably stored in production today.

### Third parties

- **Current configuration (regex engine): nothing is sent anywhere.**
  Extraction is 100% local Python. No LLM call, no external API.
- **If AI extraction is enabled** (`LEASE_AI_EXTRACTION=true` + funded
  key):
  - Each upload sends the document's page text (capped 200,000 chars) to
    the **Anthropic API** (`claude-sonnet-5`) — `ai_extraction.py`.
  - The portfolio Q&A assistant (`assistant.py`) and rent-roll AI
    validation (`ai_rent_roll_validation.py`) also send lease-derived
    data to Anthropic when enabled.
  - Telemetry (`ai_extraction_runs` table, `_record_ai_run` in
    `api.py:406`) records only model / status / latency / token counts /
    confidence tallies — **not** document text and **not** field values.
    Logs are stdout-only (`logging_config.py:159`); `logger.info("AI
    extraction ok: …")` logs the same counts, no content.
- **Google Sheets export** (`sheets_export.py`, optional, user-initiated):
  extracted field data (not the PDF) goes to a Sheet; scopes
  `spreadsheets` + `drive.file`. The FAQ already discloses this.
- **Linked email accounts** (`email_accounts.py`, optional): OAuth scope
  is **send-only** (`gmail.send` / `Mail.Send`) — no inbox read. Tokens
  stored Fernet-encrypted (`token_encryption.py`, `TOKEN_ENCRYPTION_KEY`).
  Lease content leaves only if the user emails a generated report.
- **SMTP** (Gmail app password): waitlist/admin/error emails — addresses
  and metadata. See error-alert note below.

### Anthropic data handling — verified against current published policy (2026-09-09)

Per Anthropic's Commercial Terms of Service and the retention article
(anthropic.com/legal/commercial-terms; privacy.claude.com):

- **API inputs and outputs are not used to train models.**
- Retained **up to 30 days** by default, then deleted; **up to 2 years**
  if an input is flagged for a Usage Policy violation.
- **Zero-retention agreements are available on request.**

**This is Anthropic's published policy — it is not enforced or verifiable
from inside this codebase, and no zero-retention agreement is in place.**
Re-confirm against the then-current Terms + DPA before any site copy
mentions "not used for training" or a retention window.

### ⚠️ No per-account data isolation

The `leases` table has **no `user_id` / `account_id` column**
(`database.py:342`). Every logged-in user on a deployment reads and
writes the same shared `leases` table. Acknowledged in the code —
`render.yaml` ("this app has no per-account data isolation, so a demo
login in the production database would see every real customer's leases")
and `demo_seed.py`'s docstring.

**Consequence for the site:** the homepage says extracted data is "stored
under your account" (lines 340, 358), implying a per-customer boundary
that does not exist. On any shared deployment, one customer with a login
can see every other customer's leases. This is the single biggest gap
between the code and the site's privacy implication — bigger than the
Anthropic question — and should be resolved (or the wording softened to
match reality) before onboarding a second real customer onto one
deployment.

### Error-alert emails carry tracebacks

`render.yaml` sets `ERROR_ALERT_EMAILS: "true"`: ERROR/CRITICAL log lines
email `ADMIN_EMAIL` with the full traceback (`logging_config.py:180`).
Nothing logs document text deliberately, but a parser exception's
traceback could in rare cases embed a fragment of lease text. Low risk,
noted for completeness.

### Homepage claims vs. reality (today)

| Homepage line | Status |
|---|---|
| "every extracted value carries a source citation" | **True** |
| "corrupted / password-protected / unreadable file fails with a clear message" | **True** (`document_extractor.py`) |
| "No credentials or secrets are ever stored in our codebase" | **True** for the repo (`.env` gitignored; no `*.db` or key tracked) |
| "You can delete any uploaded document and its extracted data at any time" | **True** (delete + bulk-delete endpoints exist) |
| "stored under your account" (lines 340, 358) | **Misleading** — no per-account isolation |
| "never shared with … a third party" (line 358) | **True today (regex).** Becomes **false** when the AI engine is switched on, unless updated to name Anthropic as a sub-processor |
| "a genuine 40-page lease document processed in 0.06 seconds" (line 362) | **Regex engine, small fixtures.** Not re-verified at 40 pages; not the AI pipeline |
| `[ STAT PENDING — backend benchmark ]` (line 230) | Placeholder — no number yet |

### Auto-delete decision — still owed

The uploaded **file** is already auto-deleted after processing. What is
*not* implemented is a retention limit on the **extracted data** (fields
+ source quotes) in the DB. Product decision, not a bug:

- **Option A** — leave as is (user-initiated delete only; matches current
  homepage wording).
- **Option B** — add a configurable retention window (auto-purge
  extracted data N days after upload unless the user pins it).

No code change made pending that decision. (User deferred it 2026-09-09.)

---

## Recommendation

1. **Fund the key, run the AI-engine benchmark on the 12 real leases,
   review the free-text scoring by hand, bring the user the reviewed
   overall % + per-field table + n=12.** Only then decide whether a
   number goes on the site — and if it does, name the engine and corpus.
2. **Do the honest manual timed pass** on one full-length corpus lease
   so the time-saved statement is real.
3. **Fix "stored under your account"** — there is no per-account
   isolation. Build it or soften the wording before a second customer
   shares a deployment.
4. **Before any AI rollout:** update the third-party wording to disclose
   Anthropic as a sub-processor; ideally get a zero-retention agreement.
5. **Retention window** — get the user's Option A / Option B decision.
6. **Fix the "0.06 seconds" line** so it doesn't read as an AI-pipeline
   figure — restate as "in seconds" or name the engine, once the AI
   speed number exists.
