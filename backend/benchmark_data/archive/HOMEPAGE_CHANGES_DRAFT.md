# Homepage changes — DRAFT for sign-off

Target file: `frontend/index.html`. **Nothing below is applied.** Every
number here traces to `BENCHMARK_AND_PRIVACY_AUDIT.md`.

Three edits proposed. Edit 3 needs your exact wording.

---

## Edit 1 — the `[ STAT PENDING ]` band (index.html ~line 228-233)

### Current
```html
<span class="stat-pending">[ STAT PENDING — backend benchmark ]</span>
<p class="stat-caption">A measured count of discrepancies caught across a test set of leases and units — published here once the benchmark run is complete and the number is verified.</p>
```

### Proposed
```html
<span class="stat-number">14 / 15</span>
<p class="stat-caption">Planted lease-vs-rent-roll discrepancies caught — 0 false positives — on a constructed 31-unit test portfolio run through the real import and reconciliation engine. The one miss was an address written two different ways on the two documents, which the exact-match logic can't pair; it's reported as a miss, not hidden. This measures the comparison engine on verified data, not extraction from scratch. Reproduce: <code>backend/tools/reconciliation_benchmark/</code>.</p>
```

### Why this exact wording
- **"constructed test portfolio"** — both sides of every unit pair were
  authored in the benchmark. It is not real deal data and the caption
  must not let a reader think it is.
- **"comparison engine on verified data, not extraction from scratch"**
  — the 14/15 is the reconciliation logic scored on correct field
  inputs. End-to-end from an uploaded PDF, today's regex extraction
  can't feed it reliably (see Step 1 of the audit). Overstating this as
  an upload-to-result number would be the exact "print a number" move
  the FAQ warns against.
- **the miss is stated** — 14/15 with the one miss explained reads as
  more honest than a rounded "93%".

### Alternative if 14/15 feels too in-the-weeds
```html
<span class="stat-number">0</span>
<p class="stat-caption">False positives across a 31-unit constructed test portfolio: every discrepancy the reconciliation engine flagged was a real planted disagreement between the lease and the rent roll. It also caught 14 of the 15 planted discrepancies — the one miss was an address written two ways it couldn't pair. Not real deal data; it measures the comparison logic. Reproduce: <code>backend/tools/reconciliation_benchmark/</code>.</p>
```

---

## Edit 2 — the speed sentence in the accuracy FAQ (index.html ~line 362)

### Current
> We're not going to hand you a made-up accuracy percentage — anyone can
> print a number, and it means nothing without knowing what it was
> measured against. What we do instead: every extracted value shows a
> confidence level and links back to the exact page and quote it came
> from, so you (or your analyst) can verify any figure in seconds rather
> than trusting a black box. **In our own internal testing, a genuine
> 40-page lease document processed in 0.06 seconds — extraction speed
> isn't the bottleneck; verifiability is the point.**

### Problem
"0.06 seconds" is the regex `FieldExtractor` on small test files. It has
not been reproduced on a 40-page lease, and it sits next to language
about "extraction" as if it were the headline capability. If the
model-backed engine ships (5–15 s/lease) the sentence is wrong.

### Proposed replacement for the bolded sentence
> The bottleneck was never speed — a lease is read and its fields laid
> out in seconds either way. It's verification: our analysts spend 20–45
> minutes reading a lease to pull these terms by hand, and the point of
> the tool is that every value it surfaces links to the page and quote
> it came from, so that review is a check rather than a re-read.

(Keeps the "we won't print an accuracy %" framing — which the
benchmark now supports more strongly, not less. Drops the unverifiable
0.06s figure. States the manual baseline honestly.)

---

## Edit 3 — "stored under your account" / "third party" (index.html line 358, and line 340)

### Current (line 358)
> Your documents and the data extracted from them are **stored under your
> account** and are **never shared with, or resold to, a third party**.
> You can delete any document and its extracted data at any time. If you
> export to Google Sheets, that data leaves our system…

### Two separate problems
1. **"stored under your account"** implies a per-customer boundary. There
   is none — the `leases` table has no account column; every login on a
   deployment sees every lease (`render.yaml:142`, `demo_seed.py`). This
   is true regardless of the AI question.
2. **"never shared with a third party"** is true only while extraction is
   the local regex engine. If `LEASE_AI_EXTRACTION` is turned on, lease
   text goes to the Anthropic API.

### What needs to happen before this line is safe
- Decide whether to **build per-account isolation** or **soften the
  claim** to what's true (e.g. "stored in your team's workspace" only if
  one deployment = one customer, and say that).
- If AI extraction will ship, **name Anthropic**: e.g. "Lease text is
  sent to our AI provider (Anthropic) solely to extract the fields; they
  do not train on it and delete it within 30 days per their commercial
  terms."

### → Your call on exact wording. Give me the sentence(s) you want and I'll place them.

---

## Not proposed / left alone

- Line 340 trust-item ("You can delete any uploaded document and its
  extracted data at any time") — accurate, keep. (Same "your account"
  softening applies if you change the model in Edit 3.)
- The "What's Actually True Today" section — accurate as written.
- Nothing published until you confirm Edits 1 and 2 and give wording for
  Edit 3.
