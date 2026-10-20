"""
Measure Abstractly's extraction on the synthetic affordable-housing samples.

  python -I tests/eval/affordable/run_eval.py                  # regex engine (default, offline)
  python -I tests/eval/affordable/run_eval.py --engine ai      # AI engine: calls the Anthropic API
  python -I tests/eval/affordable/run_eval.py --only tic_sc hud_50059

Reads samples/*.answer_key.json, runs each sample PDF through the same steps
as an upload (backend/app/api.py): document_extractor.extract_pages, the
low-text "ocr_needed" gate, the rent-roll-table gate, lease boundary
detection, then field extraction on the first lease range. It does not
change any extraction code; it only measures it.

Each document runs in up to three variants: "clean" (values drawn into the
page and flattened), "acroform" (values typed into the form's own fields,
not flattened), and "scan" (an image-only copy, so OCR runs).

Two scores per document:

  1. Lease fields: our engine's 15 lease fields vs the answer key's
     expected values, using backend/app/extraction_scoring.py (the same
     matcher the training harness uses). Recall = right / fields the
     form actually states; spurious = values asserted where the form
     states nothing.
  2. Program fields (HAP, TTP, AMI limit, household size, contract
     number, ...): the engine has no field for these, so extraction
     accuracy is 0 by construction. What we do measure is whether each
     value survives into the extracted page text ("text-layer recall"),
     i.e. whether a future extractor could find it at all.

Writes results/<engine>.json and prints a summary.

  python -I tests/eval/affordable/run_eval.py --set real --engine affordable+fallback

--set real scores the real public documents in tests/eval/real/ (fetch
them first with tests/eval/real/fetch.py) instead of the synthetic
samples, and writes tests/eval/real/results/<engine>.json. Their answer
keys mark each field "verified" (the document states it and HUD's public
data agrees) or "proposed" (read from the document, awaiting a human
check in REVIEW.md); the two are scored separately.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app import document_extractor  # noqa: E402
from app.extraction_scoring import ALL_FIELDS, MONEY_FIELDS, score_field  # noqa: E402
from app.field_extractor import FieldExtractor, looks_like_rent_roll_table  # noqa: E402
from app.normalize import parse_currency, parse_date  # noqa: E402

SAMPLES = HERE / "samples"
RESULTS = HERE / "results"
REAL = HERE.parent / "real"


# ---------------------------------------------------------------------------
# pipeline (mirrors api.py's upload path)
# ---------------------------------------------------------------------------

ENGINES = ("regex", "regex+acroform", "regex+layout", "affordable", "affordable+fallback", "ai")


def run_pipeline(pdf_path: Path, engine: str):
    """
    regex           today's upload path, unchanged
    regex+acroform  same, but each page's text also gets its fillable-form
                    values (app.affordable.acroform) -- fix 1 on its own
    regex+layout    same regex extractor, fed reading-order text rebuilt
                    from word positions / OCR, plus form values
                    (app.affordable.layout) -- fixes 1 + 2
    affordable      the per-form extractor (app.affordable.extract):
                    recognises the form, reads it whole, and returns
                    program fields too -- fixes 1 + 2 + 3
    affordable+fallback
                    the form reader, and today's upload path for documents
                    it doesn't recognise -- how the plan wires it in
    ai              today's upload path with the AI engine
    """
    data = pdf_path.read_bytes()
    if engine in ("affordable", "affordable+fallback"):
        from app.affordable import extract_document, layout_pages
        res = extract_document(data)
        if res["form_id"] or engine == "affordable":
            return {
                "pages": layout_pages(data, include_acroform=True),
                "status": "ok" if res["form_id"] else "unrecognised",
                "ranges": 1,
                "fields": res["lease_fields"],
                "program_fields": res["program_fields"],
                "form_id": res["form_id"],
            }
        out = run_pipeline(pdf_path, "regex")
        out["status"] = f"fallback:{out['status']}"
        return out
    if engine == "regex+layout":
        from app.affordable import layout_pages
        pages = layout_pages(data, include_acroform=True)
    else:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(data)
            tmp.flush()
            pages = document_extractor.extract_pages(data, pdf_path.name, tmp.name)
        if engine == "regex+acroform":
            from app.affordable import acroform_page_text, read_acroform
            extra = acroform_page_text(read_acroform(data))
            pages = [{**p, "text": (p.get("text") or "") + ("\n" + extra[p["page"]] if p["page"] in extra else "")}
                     for p in pages]

    out = {"pages": pages, "status": "ok", "ranges": 0, "fields": {}}
    low = document_extractor.find_low_text_pages(pages)
    if low:
        # The app saves the document as 'ocr_needed' with all fields empty.
        out.update(status="ocr_needed", low_text_pages=[p["page"] for p in low])
        return out
    if looks_like_rent_roll_table(pages):
        out.update(status="rejected_as_rent_roll")
        return out

    fx = FieldExtractor()
    boundaries = fx.detect_lease_boundaries(pages)
    out["ranges"] = len(boundaries)
    start, end = boundaries[0]
    sub_pages = [p for p in pages if start <= p["page"] <= end]
    if engine == "ai":
        from app import ai_extraction
        try:
            fields = ai_extraction.extract_lease_fields(sub_pages)
        except ai_extraction.AIExtractionError as e:
            # The app shows the upload as failed; score it as nothing extracted.
            out.update(status="ai_error", ai_error=str(e)[:300])
            return out
        out["ai_meta"] = fields.pop("_ai_meta", None)
    else:
        fields = fx.extract_fields(sub_pages)
    out["fields"] = fields
    return out


# ---------------------------------------------------------------------------
# text-layer recall
# ---------------------------------------------------------------------------

MONEY_RE = re.compile(r"\$?\s?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\$?\s?\d+(?:\.\d{1,2})?")
DATE_RES = [
    re.compile(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{4}/\d{1,2}/\d{1,2}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b", re.I),
]


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _as_date(s: str):
    d = parse_date(s)
    if isinstance(d, date):
        return d
    m = re.match(r"^\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*$", s)
    if m:
        try:
            return date(*(int(g) for g in m.groups()))
        except ValueError:
            return None
    m = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})\s*$", s)
    if m:
        mo, dd, yy = (int(g) for g in m.groups())
        yy = yy + 2000 if yy < 100 else yy
        try:
            return date(yy, mo, dd)
        except ValueError:
            return None
    return None


def money_value(s):
    """Numeric value of a money string, with or without "$". The app's
    parse_currency returns None for unsigned amounts ("1,325.00",
    "415,800"), which IRS and HUD forms print all the time, so the eval
    uses its own parse rather than understate what's on the page."""
    if s is None:
        return None
    got = parse_currency(s)
    if got is not None:
        return got
    m = re.fullmatch(r"\s*\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?\s*", str(s))
    return float(m.group(1).replace(",", "") + (m.group(2) or "")) if m else None


def in_text(value: str, vtype: str, text: str) -> bool:
    if vtype == "money":
        want = money_value(value)
        if want is None:
            return False
        for tok in MONEY_RE.findall(text):
            got = money_value(tok.replace(" ", ""))
            if got is not None and abs(got - want) <= 0.5:
                return True
        return False
    if vtype == "date":
        want = _as_date(value)
        if want is None:
            return _norm_text(value) in _norm_text(text)
        for rx in DATE_RES:
            for tok in rx.findall(text):
                if _as_date(tok) == want:
                    return True
        return False
    if vtype in ("int", "pct"):
        n = re.sub(r"[^\d.]", "", value)
        return re.search(rf"(?<![\d.,]){re.escape(n)}(?![\d])", text.replace(",", "")) is not None
    return _norm_text(value) in _norm_text(text)


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def program_match(vtype: str, got: str, expected: str) -> bool:
    """Strict, type-aware: numbers and dates by value, text by normalised
    equality (allowing only trailing/leading extras up to 20% of length)."""
    if vtype == "money":
        a, b = money_value(got), money_value(expected)
        return a is not None and b is not None and abs(a - b) <= 0.5
    if vtype == "date":
        a, b = _as_date(got), _as_date(expected)
        return a is not None and a == b
    if vtype in ("int", "pct"):
        a = re.sub(r"[^\d.]", "", got).rstrip(".")
        b = re.sub(r"[^\d.]", "", expected).rstrip(".")
        try:
            return a != "" and b != "" and abs(float(a) - float(b)) < 1e-6
        except ValueError:
            return False
    a, b = _norm_text(got), _norm_text(expected)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return short in long_ and len(short) >= 0.8 * len(long_)


VARIANTS = ("clean", "acroform", "scan", "holdout", "holdout_scan")


def sample_path(key: dict, variant: str) -> Path:
    if key.get("real"):
        return REAL / key["doc_file"]      # one copy: the document as published
    clean = HERE / key["sample_file"]
    return clean if variant == "clean" else clean.with_name(f"{clean.stem}.{variant}.pdf")


def evaluate(key: dict, engine: str, variant: str = "clean") -> dict:
    result = run_pipeline(sample_path(key, variant), engine)
    text = "\n".join(p.get("text") or "" for p in result["pages"])
    ocr = [p["ocr_confidence"] for p in result["pages"] if p.get("ocr_confidence") is not None]

    lease_scores = []
    for field in ALL_FIELDS:
        expected = key["lease_fields"].get(field)
        s = score_field(field, result["fields"].get(field), expected)
        s["app_matcher_correct"] = s["correct"]
        if field in MONEY_FIELDS and not s["correct"] and s["extracted"] is not None and expected is not None:
            a, b = money_value(s["extracted"]), money_value(expected)
            if a is not None and b is not None and abs(a - b) <= 1.0:
                s.update(correct=True, kind="correct_found", asserted_wrong=False)
        s["in_text_layer"] = None if expected is None else in_text(
            expected, "money" if field in MONEY_FIELDS else "date" if field.endswith("_date") else "text", text)
        if key.get("real") and expected is not None:
            s["status"] = key["lease_field_status"][field]["status"]
        lease_scores.append(s)

    program_scores = []
    extracted_program = result.get("program_fields") or {}
    for name, entry in key["program_fields"].items():
        if entry["type"] == "checkbox":
            continue
        shown = entry.get("shown_as", entry["value"])
        got = (extracted_program.get(name) or {}).get("value")
        correct = got is not None and program_match(entry["type"], got, str(entry["value"]))
        program_scores.append({
            "field": name,
            "type": entry["type"],
            "expected": entry["value"],
            "extracted": got,               # None for engines without program fields
            "method": (extracted_program.get(name) or {}).get("method"),
            "correct": correct,
            "kind": "correct" if correct else ("missed" if got is None else "wrong"),
            "in_text_layer": in_text(str(shown), entry["type"], text),
            **({"status": entry["status"]} if "status" in entry else {}),
        })

    stated = [s for s in lease_scores if s["expected"] is not None]
    return {
        "id": key["id"],
        "form": key["form"],
        "program": key["program"],
        "doc_type": key["doc_type"],
        "variant": variant,
        "pipeline_status": result["status"],
        "form_id": result.get("form_id"),
        "low_text_pages": result.get("low_text_pages", []),
        "lease_ranges": result["ranges"],
        "pages": len(result["pages"]),
        "mean_ocr_confidence": round(sum(ocr) / len(ocr), 1) if ocr else None,
        "ai_meta": result.get("ai_meta"),
        "ai_error": result.get("ai_error"),
        "lease_fields": {
            "stated": len(stated),
            "correct": sum(1 for s in stated if s["correct"]),
            "wrong": sum(1 for s in stated if s["kind"] == "wrong"),
            "missed": sum(1 for s in stated if s["kind"] == "missed"),
            "spurious": sum(1 for s in lease_scores if s["kind"] == "spurious"),
            "in_text_layer": sum(1 for s in stated if s["in_text_layer"]),
            "scores": lease_scores,
        },
        "program_fields": {
            "total": len(program_scores),
            "correct": sum(1 for s in program_scores if s["correct"]),
            "in_text_layer": sum(1 for s in program_scores if s["in_text_layer"]),
            "scores": program_scores,
        },
    }


def _pct(a, b):
    return None if not b else round(100.0 * a / b, 1)


def summarize(docs):
    by_type = defaultdict(lambda: defaultdict(int))
    field_misses = defaultdict(lambda: {"stated": 0, "correct": 0, "text": 0, "docs_wrong": []})
    for d in docs:
        t = by_type[d["doc_type"]]
        t["docs"] += 1
        t["ocr_needed"] += d["pipeline_status"] == "ocr_needed"
        for k in ("stated", "correct", "wrong", "missed", "spurious", "in_text_layer"):
            t[f"lease_{k}"] += d["lease_fields"][k]
        t["program_total"] += d["program_fields"]["total"]
        t["program_in_text"] += d["program_fields"]["in_text_layer"]
        t["program_correct"] += d["program_fields"]["correct"]
        for s in d["lease_fields"]["scores"]:
            if s["expected"] is None:
                continue
            f = field_misses[f"lease.{s['field']}"]
            f["stated"] += 1
            f["correct"] += s["correct"]
            f["text"] += bool(s["in_text_layer"])
            if not s["correct"]:
                f["docs_wrong"].append(f"{d['id']} ({s['kind']}: got {s['extracted']!r})")
        for s in d["program_fields"]["scores"]:
            f = field_misses[f"program.{s['field']}"]
            f["stated"] += 1
            f["text"] += bool(s["in_text_layer"])
            f["correct"] += bool(s["correct"])
            if not s["correct"]:
                f["docs_wrong"].append(f"{d['id']} ({s['kind']}: got {s['extracted']!r})")
    types = {}
    for name, t in sorted(by_type.items()):
        types[name] = dict(t)
        types[name]["lease_recall_pct"] = _pct(t["lease_correct"], t["lease_stated"])
        types[name]["lease_text_layer_pct"] = _pct(t["lease_in_text_layer"], t["lease_stated"])
        types[name]["program_text_layer_pct"] = _pct(t["program_in_text"], t["program_total"])
        types[name]["program_extraction_pct"] = _pct(t["program_correct"], t["program_total"])
    fields = {k: {**v, "recall_pct": _pct(v["correct"], v["stated"]), "text_layer_pct": _pct(v["text"], v["stated"])}
              for k, v in field_misses.items()}
    tot = lambda k: sum(t[k] for t in by_type.values())  # noqa: E731
    overall = {
        "docs": len(docs),
        "lease_recall_pct": _pct(tot("lease_correct"), tot("lease_stated")),
        "lease_spurious": tot("lease_spurious"),
        "lease_text_layer_pct": _pct(tot("lease_in_text_layer"), tot("lease_stated")),
        "program_extraction_pct": _pct(tot("program_correct"), tot("program_total")),
        "program_text_layer_pct": _pct(tot("program_in_text"), tot("program_total")),
    }
    return {"overall": overall, "by_doc_type": types, "by_field": fields}


def summarize_real(docs):
    """Real documents: recall per answer status (verified against HUD data
    vs proposed, awaiting review), for lease and program fields, overall
    and per document type. Wrong = a value asserted that doesn't match."""
    def tally(scores):
        out = {}
        for status in ("verified", "proposed"):
            ss = [s for s in scores if s.get("status") == status]
            ok = sum(1 for s in ss if s["correct"])
            wrong = sum(1 for s in ss if s["kind"] == "wrong")
            out[status] = {"stated": len(ss), "correct": ok, "wrong": wrong, "recall_pct": _pct(ok, len(ss))}
        return out

    def block(ds):
        lease = [s for d in ds for s in d["lease_fields"]["scores"] if s["expected"] is not None]
        prog = [s for d in ds for s in d["program_fields"]["scores"]]
        return {
            "docs": len(ds),
            "recognised": sum(1 for d in ds if d.get("form_id")),
            "lease": tally(lease),
            "lease_spurious": sum(d["lease_fields"]["spurious"] for d in ds),
            "program": tally(prog),
        }

    by_type = defaultdict(list)
    for d in docs:
        by_type[d["doc_type"]].append(d)
    return {"overall": block(docs), "by_doc_type": {t: block(ds) for t, ds in sorted(by_type.items())}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--engine", choices=ENGINES, default="regex")
    ap.add_argument("--set", dest="doc_set", choices=("synthetic", "real"), default="synthetic",
                    help="synthetic = the filled samples in samples/ (default); real = the public documents "
                         "in tests/eval/real/, scored separately (variants don't apply)")
    ap.add_argument("--only", nargs="*", help="answer-key ids to run")
    ap.add_argument("--variants", nargs="*", choices=VARIANTS, default=list(VARIANTS),
                    help="clean = filled and flattened; acroform = values left in unflattened form fields "
                         "(AcroForm documents only); scan = image-only copy from make_scans.py. "
                         "A variant with no file for a document is skipped and listed.")
    ap.add_argument("--out", help="results file name (default: results/<engine>.json)")
    args = ap.parse_args(argv)

    if args.engine == "ai" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("--engine ai needs ANTHROPIC_API_KEY in the environment. Nothing was sent.", file=sys.stderr)
        return 2

    real = args.doc_set == "real"
    key_dir = REAL / "answer_keys" if real else SAMPLES
    keys = [json.loads(p.read_text()) for p in sorted(key_dir.glob("*.answer_key.json"))]
    if args.only:
        keys = [k for k in keys if k["id"] in set(args.only)]
    if real:
        args.variants = ["original"]
    docs, skipped = [], []
    for variant in args.variants:
        for k in keys:
            if not sample_path(k, variant).exists():
                skipped.append(f"{k['id']} ({variant})")
                continue
            docs.append(evaluate(k, args.engine, variant))
    if real:
        summary = {"original": summarize_real(docs)}
    else:
        summary = {v: summarize([d for d in docs if d["variant"] == v]) for v in args.variants
                   if any(d["variant"] == v for d in docs)}
    report = {"engine": args.engine, "set": args.doc_set, "run_date": date.today().isoformat(), "summary": summary,
              "skipped": skipped, "documents": docs}
    if args.engine == "ai":
        from app import ai_extraction
        metas = [d["ai_meta"] for d in docs if d.get("ai_meta")]
        report["ai"] = {
            "model": ai_extraction.DEFAULT_MODEL,
            "prompt_version": ai_extraction.PROMPT_VERSION,
            "calls": len(metas),
            "errors": sum(1 for d in docs if d.get("ai_error")),
            "input_tokens": sum(m.get("input_tokens") or 0 for m in metas),
            "output_tokens": sum(m.get("output_tokens") or 0 for m in metas),
        }

    results_dir = REAL / "results" if real else RESULTS
    results_dir.mkdir(exist_ok=True)
    out = results_dir / (args.out or f"{args.engine}.json")
    out.write_text(json.dumps(report, indent=2, default=str) + "\n")

    print(f"engine={args.engine}  set={args.doc_set}  runs={len(docs)}  -> {out.relative_to(REPO)}")
    if skipped:
        print(f"skipped (no file): {', '.join(skipped)}")
    if real:
        print(f"{'document':32} {'status':28} {'form':14} {'lease ver':>9} {'lease prop':>10} {'spur':>4} {'prog ver':>8} {'prog prop':>9}")
        for d in docs:
            def ok(scores, status):
                ss = [s for s in scores if s.get("status") == status]
                return f"{sum(s['correct'] for s in ss)}/{len(ss)}"
            lease = [s for s in d["lease_fields"]["scores"] if s["expected"] is not None]
            prog = d["program_fields"]["scores"]
            print(f"{d['id']:32} {d['pipeline_status']:28} {str(d.get('form_id') or '-'):14} {ok(lease, 'verified'):>9} "
                  f"{ok(lease, 'proposed'):>10} {d['lease_fields']['spurious']:>4} {ok(prog, 'verified'):>8} {ok(prog, 'proposed'):>9}")
        o = summary["original"]["overall"]
        for part in ("lease", "program"):
            print(f"OVERALL {part}: verified {o[part]['verified']['correct']}/{o[part]['verified']['stated']} "
                  f"({o[part]['verified']['recall_pct']}%), proposed {o[part]['proposed']['correct']}/"
                  f"{o[part]['proposed']['stated']} ({o[part]['proposed']['recall_pct']}%)")
        print(f"recognised {o['recognised']}/{o['docs']}, lease spurious {o['lease_spurious']}")
        return 0
    print(f"{'document':22} {'variant':12} {'status':21} {'rng':>3} {'lease ok/stated':>15} {'spur':>4} {'lease txt':>9} {'prog txt':>9} {'prog ok':>9} {'ocr':>5}")
    for d in docs:
        lf, pf = d["lease_fields"], d["program_fields"]
        print(f"{d['id']:22} {d['variant']:12} {d['pipeline_status']:21} {d['lease_ranges']:>3} "
              f"{lf['correct']:>7}/{lf['stated']:<7} {lf['spurious']:>4} "
              f"{lf['in_text_layer']:>4}/{lf['stated']:<4} {pf['in_text_layer']:>4}/{pf['total']:<4} {pf['correct']:>4}/{pf['total']:<4} "
              f"{d['mean_ocr_confidence'] if d['mean_ocr_confidence'] is not None else '':>5}")
    for variant, s in summary.items():
        o = s["overall"]
        print(f"\nOVERALL [{variant}] lease recall {o['lease_recall_pct']}%  spurious {o['lease_spurious']}  "
              f"lease text-layer {o['lease_text_layer_pct']}%  program text-layer {o['program_text_layer_pct']}%  "
              f"program extraction {o['program_extraction_pct']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
