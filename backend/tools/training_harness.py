"""
Phase 4 training loop: measure -> refine -> re-measure, against the
REAL, wired-up extraction pipeline (app/ai_extraction.py via the same
document_extractor front door an upload uses) -- not a separate
re-implementation.

Each round:
  1. generate (or reuse) a synthetic corpus with known ground truth
     (tests/generate_synthetic_corpus.py)
  2. run every lease document through the live AI extraction engine
  3. run every matched (rent roll row, lease) pair through the live AI
     rent-roll validation
  4. score against ground truth (app/extraction_scoring.py):
       - overall field accuracy
       - HIGH-CONFIDENCE + WRONG  (the dangerous failure -- listed
         individually so you can read every one)
       - per-field and per-document-format accuracy (what's weak)
       - confidence calibration: P(correct | high) vs P(correct | low)
       - rent-roll validation recall against the deliberately injected
         disagreements in the corpus
  5. persist the round (database.record_training_round) so the owner
     console's Extraction Quality view shows the trend over time, and
     write a markdown report next to it.

Between rounds you edit the prompt in app/ai_extraction.py (bump
PROMPT_VERSION), note what changed with --changed, and re-run. Keep
going until the trend flattens across a couple of rounds.

    LEASE_AI_EXTRACTION=true venv/bin/python tools/training_harness.py \
        --rounds 1 --leases 60 --seed 7 --label "baseline" \
        --changed "initial reconstructed prompt"

Requires a funded ANTHROPIC_API_KEY. With no credit it prints the
billing message and exits 2 -- nothing else needs to change for a real
run once credit is added.
"""

import argparse
import os
import sys
import textwrap
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests")))

from app import database
from app import ai_extraction
from app import ai_rent_roll_validation as rrv
from app import document_extractor
from app import extraction_scoring
from generate_synthetic_corpus import generate_corpus


def _die_if_blocked(exc: Exception):
    msg = str(exc).lower()
    if "credit balance" in msg or "billing" in msg or "credit" in msg:
        print("\n" + "=" * 72)
        print("BLOCKED: the ANTHROPIC_API_KEY has no credit balance.")
        print("Add credit (Plans & Billing) or set a funded key in backend/.env,")
        print("then re-run this command. Nothing else needs to change.")
        print("=" * 72)
        sys.exit(2)


def extract_corpus(corpus_dir, manifest):
    """Run every lease doc through the live AI pipeline. Returns list of score_document results."""
    doc_scores = []
    for entry in manifest["leases"]:
        path = os.path.join(corpus_dir, entry["file"])
        try:
            with open(path, "rb") as f:
                pages = document_extractor.extract_pages(f.read(), entry["file"], path)
        except document_extractor.DocumentExtractionError as e:
            # a doc our own text layer can't read isn't an extraction
            # accuracy problem -- skip, note it
            print(f"  ! {entry['file']}: {e}")
            continue

        try:
            fields = ai_extraction.extract_lease_fields(pages)
        except ai_extraction.AIExtractionError as e:
            _die_if_blocked(e)
            print(f"  ! {entry['file']}: AI extraction failed: {e}")
            continue
        fields.pop("_ai_meta", None)

        doc_scores.append(extraction_scoring.score_document(
            fields, entry["ground_truth"],
            doc_meta={"id": entry["id"], "format": entry["format"], "scanned": entry.get("scanned")},
        ))
        s = doc_scores[-1]
        print(f"  . {entry['file']:20s} {s['fields_correct']:2d}/{s['fields_total']} fields")
    return doc_scores


def score_rent_roll_validation(corpus_dir, manifest):
    """
    Import each synthetic rent roll, pair rows with their source lease's
    abstracted fields (which we re-extract live), run live AI validation,
    and check recall against the injected disagreements the generator
    recorded. Returns a summary dict, or None if AI is blocked.
    """
    from app.rent_roll_import import parse_csv_rent_roll, parse_xlsx_rent_roll

    lease_fields_by_id = {}
    for entry in manifest["leases"]:
        path = os.path.join(corpus_dir, entry["file"])
        try:
            with open(path, "rb") as f:
                pages = document_extractor.extract_pages(f.read(), entry["file"], path)
            lease_fields_by_id[entry["id"]] = ai_extraction.extract_lease_fields(pages)
            lease_fields_by_id[entry["id"]].pop("_ai_meta", None)
        except ai_extraction.AIExtractionError as e:
            _die_if_blocked(e)
            return None
        except document_extractor.DocumentExtractionError:
            continue

    injected_total = caught = false_positives = pairs = 0
    for rr in manifest["rent_rolls"]:
        for row_gt in rr["ground_truth"]["rows"]:
            lease_id = row_gt["lease_id"]
            if lease_id not in lease_fields_by_id:
                continue
            pairs += 1
            rr_fields = {name: {"value": None} for name in extraction_scoring.ALL_FIELDS}
            rr_fields["tenant"]["value"] = row_gt["tenant"]
            rr_fields["rent_amount"]["value"] = f"${row_gt['rent_roll_rent_monthly']:,.2f}"
            rr_lease = {"id": None, "filename": rr["file"], "extracted_fields": rr_fields}
            doc_lease = {"id": None, "filename": "lease.pdf", "extracted_fields": lease_fields_by_id[lease_id]}
            try:
                result = rrv.validate_rent_roll_against_lease(rr_lease, doc_lease)
            except ai_extraction.AIExtractionError as e:
                _die_if_blocked(e)
                continue
            flagged_fields = {d["field"] for d in result["discrepancies"]}
            inj = row_gt.get("injected_disagreement")
            if inj:
                injected_total += 1
                if inj["field"] in flagged_fields:
                    caught += 1
            else:
                false_positives += len(flagged_fields)

    return {
        "pairs": pairs,
        "injected_disagreements": injected_total,
        "caught": caught,
        "recall": round(caught / injected_total, 4) if injected_total else None,
        "false_positive_flags_on_clean_rows": false_positives,
    }


def render_report_md(round_label, report, rr_summary, changed):
    cal = report["calibration"]
    lines = [
        f"# Training round: {round_label}",
        f"_generated {datetime.now(timezone.utc).isoformat()} · model {ai_extraction.DEFAULT_MODEL} · prompt {ai_extraction.PROMPT_VERSION}_",
        "",
        f"**Changed this round:** {changed or '(nothing noted)'}",
        "",
        "## Headline",
        f"- Overall field accuracy: **{report['overall_accuracy']}** over {report['fields_evaluated']} (doc, field) pairs, {report['documents']} documents",
        f"- Asserted values wrong: {report['asserted_wrong']} / {report['asserted_values']}",
        "",
        "## Danger signal 1 — high confidence + wrong",
        f"- Count: **{report['high_conf_wrong_count']}**  (rate among high-confidence assertions: {report['high_conf_wrong_rate']})",
    ]
    for hw in report["high_conf_wrong"][:40]:
        lines.append(f"  - `{hw['doc']}` [{hw['format']}] **{hw['field']}**: got {hw['extracted']!r}, expected {hw['expected']!r} ({hw['kind']})")
    lines += [
        "",
        "## Danger signal 2 — weak fields / formats",
        "| field | accuracy | n | importance |",
        "|---|---|---|---|",
    ]
    for r in report["field_accuracy"]:
        lines.append(f"| {r['field']} | {r['accuracy']} | {r['n']} | {r['importance']} |")
    lines += ["", "| format | accuracy | n |", "|---|---|---|"]
    for r in report["format_accuracy"]:
        lines.append(f"| {r['format']} | {r['accuracy']} | {r['n']} |")
    lines += [
        "",
        "## Confidence calibration",
        f"- P(correct | high) = **{cal['p_correct_given_high']}**  (n={cal['n_high']})",
        f"- P(correct | medium) = {cal['p_correct_given_medium']}  (n={cal['n_medium']})",
        f"- P(correct | low) = {cal['p_correct_given_low']}  (n={cal['n_low']})",
        f"- calibration gap (high − low) = **{cal['calibration_gap']}**  (want clearly positive, and P(correct|high) near 1.0)",
    ]
    if rr_summary:
        lines += [
            "",
            "## Rent-roll validation",
            f"- Injected disagreements caught: **{rr_summary['caught']} / {rr_summary['injected_disagreements']}** (recall {rr_summary['recall']})",
            f"- False-positive flags on clean rows: {rr_summary['false_positive_flags_on_clean_rows']} over {rr_summary['pairs']} pairs",
        ]
    return "\n".join(lines)


def print_trend():
    rounds = database.list_training_rounds()
    if not rounds:
        return
    print("\n" + "=" * 96)
    print("TREND (all recorded rounds)")
    print(f"{'when':20s} {'label':22s} {'prompt':7s} {'acc':>6s} {'hi-wrong':>9s} {'P(c|hi)':>8s} {'calib gap':>10s}")
    print("-" * 96)
    for r in rounds:
        print(f"{(r['created_at'] or '')[:19]:20s} {(r['round_label'] or '')[:22]:22s} "
              f"{(r['prompt_version'] or '-')[:7]:7s} {str(r['overall_accuracy']):>6s} "
              f"{str(r['high_conf_wrong_count']):>9s} {str(r['p_correct_given_high']):>8s} {str(r['calibration_gap']):>10s}")
        if r["changed_this_round"]:
            print(f"{'':20s} └─ changed: {r['changed_this_round']}")
    print("=" * 96)


def run_round(args, round_idx):
    seed = args.seed + round_idx  # fresh cases each round on top of the base corpus
    label = f"{args.label} (round {round_idx + 1})" if args.rounds > 1 else args.label
    corpus_dir = os.path.join(args.corpus_dir, f"round_{round_idx + 1}_seed_{seed}")

    print(f"\n{'#' * 72}\n# {label}  ·  seed {seed}  ·  prompt {ai_extraction.PROMPT_VERSION}\n{'#' * 72}")
    print("Generating corpus...")
    manifest = generate_corpus(corpus_dir, n_leases=args.leases, n_garbage=args.garbage,
                               n_rent_rolls=args.rent_rolls, seed=seed)

    print("Extracting (live AI)...")
    doc_scores = extract_corpus(corpus_dir, manifest)
    if not doc_scores:
        print("No documents scored -- aborting round.")
        return
    report = extraction_scoring.aggregate(doc_scores)

    rr_summary = None
    if args.rent_rolls:
        print("Validating rent rolls (live AI)...")
        rr_summary = score_rent_roll_validation(corpus_dir, manifest)

    round_id = database.record_training_round(
        round_label=label, report=report, model=ai_extraction.DEFAULT_MODEL,
        prompt_version=ai_extraction.PROMPT_VERSION, corpus_seed=seed, corpus_size=args.leases,
        changed_this_round=args.changed,
    )

    md = render_report_md(label, report, rr_summary, args.changed)
    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"round_{round_id:03d}_{ai_extraction.PROMPT_VERSION}.md")
    with open(out_path, "w") as f:
        f.write(md)

    print("\n" + md)
    print(f"\nSaved: {out_path}  (training_rounds id {round_id})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=1, help="how many measure/re-measure rounds to run now")
    ap.add_argument("--leases", type=int, default=60)
    ap.add_argument("--garbage", type=int, default=8)
    ap.add_argument("--rent-rolls", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--label", default="run")
    ap.add_argument("--changed", default="", help="what you changed in the prompt since the last round")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "training_reports"))
    ap.add_argument("--corpus-dir", default=os.path.join(os.path.dirname(__file__), "..", "tests", "synthetic_corpus_training"))
    args = ap.parse_args()

    db_override = os.environ.get("DB_PATH", "").strip()
    if db_override:
        database.configure(db_override)
    database.init_db()

    if ai_extraction.resolve_engine() != "ai":
        print("AI engine is not enabled. Set LEASE_AI_EXTRACTION=true and a funded ANTHROPIC_API_KEY, then re-run.")
        sys.exit(2)

    try:
        for i in range(args.rounds):
            run_round(args, i)
    except ai_extraction.AIExtractionError as e:
        _die_if_blocked(e)
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    print_trend()


if __name__ == "__main__":
    main()
