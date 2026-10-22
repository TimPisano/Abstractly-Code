# Affordable-housing extraction eval

Measures how well Abstractly's extraction reads Section 8 and LIHTC documents. Results and findings: [docs/research/eval-baseline.md](../../../docs/research/eval-baseline.md).

## What's here

| Path | What |
|---|---|
| `sources/` | 16 blank public forms (HUD, IRS, state HFAs), unmodified. URLs in `MANIFEST.json`, checksums in `SHA256SUMS`. |
| `specs/<id>.py` | What to write on each blank form, and the answer key. All values fictional. |
| `world.py` | Fictional area limits and the rent math (HCV, PBRA, LIHTC), so every answer key is internally consistent. |
| `fill_lib.py` | Draws values onto a form (by AcroForm field or next to a printed label) and writes the answer key. |
| `samples/<id>.pdf` | Filled and flattened (values in the page content). |
| `samples/<id>.acroform.pdf` | Same values left in unflattened form fields (AcroForm documents only). |
| `samples/<id>.scan.pdf` | Image-only "scanned" copy. Gitignored; rebuild with `make_scans.py`. |
| `samples/<id>.answer_key.json` | Expected values: `lease_fields` (our 15 lease fields) and `program_fields` (HAP, TTP, limits...). |
| `run_eval.py` | Runs our extraction and scores it. Writes `results/<engine>.json`. |
| `inspect_form.py` | Spec-writing helper: list form fields, dump text positions, render pages. |

## Run it

Use the backend venv (nothing extra to install), from the repo root:

```
PY=backend/venv/bin/python          # or the primary checkout's venv
$PY -I tests/eval/affordable/build_samples.py      # rebuild samples + answer keys (deterministic)
$PY -I tests/eval/affordable/make_scans.py         # rebuild the scanned copies (~2 min)
$PY -I tests/eval/affordable/run_eval.py           # regex engine, all variants (~8 min with OCR)
$PY -I tests/eval/affordable/run_eval.py --variants clean acroform   # skip OCR (seconds)
```

The AI engine sends each document to the Anthropic API, so it's opt-in and costs money:

```
ANTHROPIC_API_KEY=... $PY -I tests/eval/affordable/run_eval.py --engine ai --variants clean
```

Real public documents (LURAs, HAP contracts, agency samples) live in `tests/eval/real/` and are scored separately. Their answers are split into "verified" (backed by HUD's public data) and "proposed" (awaiting review in `tests/eval/real/REVIEW.md`):

```
$PY -I tests/eval/real/fetch.py                                    # download + check hashes (not committed)
$PY -I tests/eval/affordable/run_eval.py --set real --engine affordable+fallback   # -> tests/eval/real/results/
```

## Rules for adding a document

- Public, no-login government documents only. Never a real tenant file.
- Fictional values only: no SSNs (leave blank or "On file"), masked tax IDs, `555` phone numbers.
- Every value in the answer key must actually be written on the page (`fill_lib` checks this and refuses to build otherwise).
- Look at the rendered pages before committing: `inspect_form.py render samples/<id>.pdf <out_dir_outside_repo>`.
- The state forms are public agency documents, not necessarily public domain. Fine in this private repo; check each agency's terms before publishing them anywhere.
