"""
Extraction quality observability (Phase 5): turn the raw telemetry
(ai_extraction_runs), the training-round history (training_rounds), and
the human corrections (lease_field_edits) into two things:

  1. compute_quality_trend() -- the owner-console view: how accuracy,
     high-confidence-wrong rate, and confidence calibration have moved
     across training rounds, plus live production volume / latency /
     error rate. So you can tell if quality is drifting on real user
     documents, not just see a one-time report.

  2. compute_field_reliability() -- per FIELD TYPE, how much to trust
     it: from the latest training round's per-field accuracy and from
     how often humans have had to correct that field on real
     AI-extracted leases. The lease detail view uses this to tag
     historically-weak fields with a "double-check by eye" hint.

Pure functions given already-fetched rows -- unit-tested directly, no
DB access here.
"""

from typing import Any, Dict, List, Optional

from .extraction_scoring import ALL_FIELDS, FIELD_IMPORTANCE

# Thresholds for the per-field reliability tier. Deliberately blunt --
# this drives a soft "worth an extra look" UI hint, not a hard gate.
_WEAK_TRAINING_ACCURACY = 0.80
_WEAK_CORRECTION_RATE = 0.15
_MIXED_TRAINING_ACCURACY = 0.92
_MIN_PRODUCTION_SAMPLE = 5


def _has_value(entry: Optional[Dict[str, Any]]) -> bool:
    return bool((entry or {}).get("value"))


def compute_field_reliability(
    *,
    latest_training_report: Optional[Dict[str, Any]],
    ai_extracted_leases: List[Dict[str, Any]],
    field_edits: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    latest_training_report: the `report` JSON of the most recent
        training_rounds row (or None if the loop hasn't run yet).
    ai_extracted_leases: lease dicts (with extracted_fields) that were
        produced by the AI engine -- i.e. have an ai_extraction_runs row.
    field_edits: all lease_field_edits rows (each has lease_id,
        field_name), used as the "humans keep fixing this" signal.

    Returns {field: {reliability, training_accuracy, production_samples,
    production_correction_rate, importance, advice}} for every field.
    """
    training_acc = {}
    if latest_training_report:
        for row in latest_training_report.get("field_accuracy", []):
            training_acc[row["field"]] = row.get("accuracy")

    ai_lease_ids = {l["id"] for l in ai_extracted_leases}
    had_value = {f: 0 for f in ALL_FIELDS}
    for lease in ai_extracted_leases:
        fields = lease.get("extracted_fields") or {}
        for f in ALL_FIELDS:
            if _has_value(fields.get(f)):
                had_value[f] += 1

    edited = {f: set() for f in ALL_FIELDS}
    for edit in field_edits:
        if edit.get("field_name") in edited and edit.get("lease_id") in ai_lease_ids:
            edited[edit["field_name"]].add(edit["lease_id"])

    out = {}
    for f in ALL_FIELDS:
        samples = had_value[f]
        corrections = len(edited[f])
        correction_rate = round(corrections / samples, 3) if samples else None
        t_acc = training_acc.get(f)

        weak = (t_acc is not None and t_acc < _WEAK_TRAINING_ACCURACY) or \
               (samples >= _MIN_PRODUCTION_SAMPLE and correction_rate is not None and correction_rate > _WEAK_CORRECTION_RATE)
        mixed = (not weak) and (
            (t_acc is not None and t_acc < _MIXED_TRAINING_ACCURACY) or
            (samples >= _MIN_PRODUCTION_SAMPLE and correction_rate is not None and correction_rate > 0)
        )
        reliability = "weak" if weak else ("mixed" if mixed else "strong")

        advice = {
            "weak": "The pipeline gets this field wrong or misses it often -- verify it against the source quote every time.",
            "mixed": "Mostly reliable, but check this one against the source quote before you rely on it.",
            "strong": None,
        }[reliability]

        out[f] = {
            "reliability": reliability,
            "training_accuracy": t_acc,
            "production_samples": samples,
            "production_corrections": corrections,
            "production_correction_rate": correction_rate,
            "importance": FIELD_IMPORTANCE[f],
            "advice": advice,
        }
    return out


def _run_bucket(run: Dict[str, Any]) -> str:
    return (run.get("created_at") or "")[:10]  # YYYY-MM-DD


def compute_quality_trend(
    *,
    training_rounds: List[Dict[str, Any]],
    ai_runs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    training_rounds: rows from database.list_training_rounds() (oldest first).
    ai_runs: rows from database.list_ai_extraction_runs() (any order).
    """
    round_trend = [
        {
            "label": r.get("round_label"),
            "at": r.get("created_at"),
            "prompt_version": r.get("prompt_version"),
            "model": r.get("model"),
            "overall_accuracy": r.get("overall_accuracy"),
            "high_conf_wrong_count": r.get("high_conf_wrong_count"),
            "high_conf_wrong_rate": r.get("high_conf_wrong_rate"),
            "calibration_gap": r.get("calibration_gap"),
            "p_correct_given_high": r.get("p_correct_given_high"),
            "changed_this_round": r.get("changed_this_round"),
        }
        for r in training_rounds
    ]

    # live production signal, bucketed by day
    daily: Dict[str, Dict[str, Any]] = {}
    for run in ai_runs:
        day = _run_bucket(run)
        b = daily.setdefault(day, {"day": day, "runs": 0, "errors": 0, "latency_ms_total": 0,
                                   "latency_n": 0, "high": 0, "medium": 0, "low": 0, "not_found": 0})
        b["runs"] += 1
        if run.get("status") != "ok":
            b["errors"] += 1
        if run.get("latency_ms"):
            b["latency_ms_total"] += run["latency_ms"]
            b["latency_n"] += 1
        for tier in ("high", "medium", "low", "not_found"):
            b[tier] += run.get(f"{tier}_count") or 0

    production_daily = []
    for day in sorted(daily):
        b = daily[day]
        graded = b["high"] + b["medium"] + b["low"]
        production_daily.append({
            "day": day,
            "runs": b["runs"],
            "error_rate": round(b["errors"] / b["runs"], 3) if b["runs"] else None,
            "avg_latency_ms": round(b["latency_ms_total"] / b["latency_n"]) if b["latency_n"] else None,
            "confidence_mix": {
                "high": round(b["high"] / graded, 3) if graded else None,
                "medium": round(b["medium"] / graded, 3) if graded else None,
                "low": round(b["low"] / graded, 3) if graded else None,
            },
            "fields_found": graded,
            "fields_not_found": b["not_found"],
        })

    latest = round_trend[-1] if round_trend else None
    previous = round_trend[-2] if len(round_trend) > 1 else None
    delta = None
    if latest and previous and latest["overall_accuracy"] is not None and previous["overall_accuracy"] is not None:
        delta = round(latest["overall_accuracy"] - previous["overall_accuracy"], 4)

    return {
        "training_rounds": round_trend,
        "latest_round": latest,
        "accuracy_delta_vs_previous_round": delta,
        "production_daily": production_daily,
        "total_production_runs": sum(d["runs"] for d in production_daily),
        "has_training_data": bool(round_trend),
    }
