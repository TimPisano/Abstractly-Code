"""
Scoring for the extraction training loop: given what the pipeline
extracted for a document and that document's known ground truth, decide
per field whether the extraction was right, and roll many documents up
into a round summary with the two signals the training loop cares about
most:

  1. HIGH-CONFIDENCE + WRONG -- the dangerous failure mode. The app is
     telling a user to trust a bad value.
  2. FIELD TYPES / DOCUMENT FORMATS that consistently underperform.

Plus a confidence-calibration read: does "high" actually mean more
likely correct than "low"? A confidence score that doesn't track
correctness is worse than none.

Pure functions, no API and no DB -- unit-tested directly
(test_extraction_scoring.py) and called by tools/training_harness.py.
"""

from typing import Any, Dict, List, Optional

from .normalize import parse_currency, parse_date, parse_square_footage

MONEY_FIELDS = {"rent_amount", "security_deposit", "cam_charges"}
DATE_FIELDS = {"lease_start_date", "lease_end_date"}

# How much a single field's outcome tells us, for weighting the
# "which fields are weak" report -- a wrong tenant matters more than a
# missed CAM charge. Not used in the headline accuracy % (every field
# counts once there); used only to rank remediation priority.
FIELD_IMPORTANCE = {
    "tenant": 3, "landlord": 2, "rent_amount": 3,
    "lease_start_date": 3, "lease_end_date": 3, "property_address": 2,
    "security_deposit": 1, "cam_charges": 1, "rent_escalation": 2,
    "renewal_options": 2, "permitted_use": 1, "exclusivity_clause": 1,
    "insurance_requirements": 1, "default_cure_period": 1, "square_footage": 1,
}

ALL_FIELDS = list(FIELD_IMPORTANCE)


def _norm(s: Optional[str]) -> str:
    return " ".join(str(s or "").lower().split())


def _first_percent(s: str) -> Optional[float]:
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", s)
    return float(m.group(1)) if m else None


def _first_int(s: str) -> Optional[int]:
    import re
    m = re.search(r"\d+", s)
    return int(m.group(0)) if m else None


def _year_schedule_amounts(s: str) -> list:
    """Pull the dollar amounts out of a 'Year 1: $6,250; Year 2: $6,438; ...' style escalation string, in order."""
    import re
    return [parse_currency(m) for m in re.findall(r"Year\s+\d+:\s*(\$?[\d,]+(?:\.\d{2})?)", s, re.IGNORECASE) if parse_currency(m)]


def values_match(field: str, extracted: Optional[str], expected: Optional[str]) -> bool:
    """
    Field-aware equality between an extracted display string and the
    ground-truth display string. Both None -> match (correctly not
    found). One None -> no match.
    """
    if expected is None and extracted is None:
        return True
    if expected is None or extracted is None:
        return False

    if field in MONEY_FIELDS:
        a, b = parse_currency(extracted), parse_currency(expected)
        return a is not None and b is not None and abs(a - b) <= 1.0

    if field in DATE_FIELDS:
        a, b = parse_date(extracted), parse_date(expected)
        if a is not None and b is not None:
            return a == b
        # one side didn't parse (an unusual format the model echoed
        # verbatim, e.g. ISO) -- fall back to a string compare so a
        # semantically-right-but-oddly-formatted date isn't scored wrong
        return _norm(extracted) == _norm(expected)

    if field == "square_footage":
        a, b = parse_square_footage(extracted), parse_square_footage(expected)
        return a is not None and b is not None and a == b

    if field == "rent_escalation":
        ea, eb = _first_percent(extracted), _first_percent(expected)
        if ea is not None and eb is not None:
            return abs(ea - eb) < 0.01
        # A year-by-year dollar schedule ("Year 1: $6,250; Year 2: $6,438; ...")
        # is a valid alternative to a "X% annually" rule -- accept it if
        # the implied year-over-year growth matches the expected percent.
        if eb is not None and ea is None:
            schedule = _year_schedule_amounts(extracted)
            if len(schedule) >= 2:
                ratios = [schedule[i + 1] / schedule[i] for i in range(len(schedule) - 1) if schedule[i]]
                if ratios and all(abs((r - 1) * 100 - eb) < 0.4 for r in ratios):
                    return True
        return _norm(expected) in _norm(extracted) or _norm(extracted) in _norm(expected)

    if field == "renewal_options":
        return _first_int(extracted) == _first_int(expected) and _first_int(expected) is not None

    if field in ("tenant", "landlord"):
        # Entity-suffix tolerance: "Acme" vs "Acme, LLC" vs "Acme LLC".
        a = _norm(extracted).rstrip(".").replace(",", "")
        b = _norm(expected).rstrip(".").replace(",", "")
        if a == b:
            return True
        short, long = sorted((a, b), key=len)
        return bool(short) and long.startswith(short)

    # property_address, permitted_use, exclusivity_clause,
    # insurance_requirements, default_cure_period: token-substring either way.
    a, b = _norm(extracted), _norm(expected)
    return a in b or b in a


def score_field(field: str, entry: Optional[Dict[str, Any]], expected: Optional[str]) -> Dict[str, Any]:
    """
    One field's outcome.

    kind:
      "correct_found"   -- value present and matches
      "correct_absent"  -- correctly returned not-found
      "wrong"           -- value present but does not match
      "missed"          -- ground truth has a value, extraction returned nothing
      "spurious"        -- ground truth is None, extraction returned a value
    """
    entry = entry or {}
    extracted = entry.get("value")
    confidence = entry.get("confidence")
    match = values_match(field, extracted, expected)

    if match:
        kind = "correct_found" if expected is not None else "correct_absent"
    elif expected is None:
        kind = "spurious"
    elif extracted is None:
        kind = "missed"
    else:
        kind = "wrong"

    return {
        "field": field,
        "expected": expected,
        "extracted": extracted,
        "confidence": confidence,
        "correct": match,
        "kind": kind,
        # a value the model asserted (found) that is wrong -- the
        # dangerous case, especially at high confidence
        "asserted_wrong": kind in ("wrong", "spurious"),
    }


def score_document(extracted_fields: Dict[str, Any], ground_truth: Dict[str, Optional[str]],
                   *, doc_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    field_scores = [score_field(f, extracted_fields.get(f), ground_truth.get(f)) for f in ALL_FIELDS]
    correct = sum(1 for s in field_scores if s["correct"])
    return {
        "doc_meta": doc_meta or {},
        "field_scores": field_scores,
        "fields_total": len(field_scores),
        "fields_correct": correct,
        "accuracy": correct / len(field_scores) if field_scores else 0.0,
    }


def _rate(correct: int, total: int) -> Optional[float]:
    return round(correct / total, 4) if total else None


def aggregate(doc_scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Roll many score_document results into one round summary.

    Headline: overall field accuracy.
    Danger signal 1: high-confidence-but-wrong -- count and the actual
      (doc, field, extracted, expected) list so a human can read them.
    Danger signal 2: per-field and per-format accuracy, worst first.
    Calibration: P(correct | confidence tier) for high/medium/low, and
      a single calibration_gap = P(correct|high) - P(correct|low)
      (want this clearly positive and want P(correct|high) near 1.0).
    """
    by_conf = {c: [0, 0] for c in ("high", "medium", "low", None)}  # [correct, total] over ASSERTED values
    by_field = {f: [0, 0] for f in ALL_FIELDS}
    by_format: Dict[str, List[int]] = {}
    high_conf_wrong: List[Dict[str, Any]] = []
    total_fields = total_correct = 0

    for ds in doc_scores:
        fmt = (ds.get("doc_meta") or {}).get("format", "unknown")
        by_format.setdefault(fmt, [0, 0])
        for s in ds["field_scores"]:
            total_fields += 1
            by_field[s["field"]][1] += 1
            by_format[fmt][1] += 1
            if s["correct"]:
                total_correct += 1
                by_field[s["field"]][0] += 1
                by_format[fmt][0] += 1
            # calibration is measured over ASSERTED values only (the
            # model returned something) -- "not found" has confidence
            # None and isn't a claim whose confidence we can calibrate
            if s["extracted"] is not None:
                tier = s["confidence"] if s["confidence"] in ("high", "medium", "low") else None
                by_conf[tier][1] += 1
                if s["correct"]:
                    by_conf[tier][0] += 1
                elif tier == "high":
                    high_conf_wrong.append({
                        "doc": (ds.get("doc_meta") or {}).get("id"),
                        "format": fmt,
                        "field": s["field"],
                        "extracted": s["extracted"],
                        "expected": s["expected"],
                        "kind": s["kind"],
                    })

    field_accuracy = sorted(
        ({"field": f, "accuracy": _rate(c, t), "n": t, "importance": FIELD_IMPORTANCE[f]}
         for f, (c, t) in by_field.items()),
        key=lambda r: (r["accuracy"] if r["accuracy"] is not None else 1.0, -r["importance"]),
    )
    format_accuracy = sorted(
        ({"format": fmt, "accuracy": _rate(c, t), "n": t} for fmt, (c, t) in by_format.items()),
        key=lambda r: r["accuracy"] if r["accuracy"] is not None else 1.0,
    )

    p_high = _rate(by_conf["high"][0], by_conf["high"][1])
    p_med = _rate(by_conf["medium"][0], by_conf["medium"][1])
    p_low = _rate(by_conf["low"][0], by_conf["low"][1])
    calibration_gap = round(p_high - p_low, 4) if (p_high is not None and p_low is not None) else None

    asserted_total = sum(by_conf[c][1] for c in by_conf)
    asserted_wrong = asserted_total - sum(by_conf[c][0] for c in by_conf)

    return {
        "documents": len(doc_scores),
        "fields_evaluated": total_fields,
        "overall_accuracy": _rate(total_correct, total_fields),
        "asserted_values": asserted_total,
        "asserted_wrong": asserted_wrong,
        "high_conf_wrong_count": len(high_conf_wrong),
        "high_conf_wrong_rate": _rate(len(high_conf_wrong), by_conf["high"][1]) if by_conf["high"][1] else None,
        "high_conf_wrong": high_conf_wrong,
        "calibration": {
            "p_correct_given_high": p_high,
            "p_correct_given_medium": p_med,
            "p_correct_given_low": p_low,
            "calibration_gap": calibration_gap,
            "n_high": by_conf["high"][1],
            "n_medium": by_conf["medium"][1],
            "n_low": by_conf["low"][1],
        },
        "field_accuracy": field_accuracy,
        "format_accuracy": format_accuracy,
        "worst_fields": [r for r in field_accuracy if r["accuracy"] is not None and r["accuracy"] < 0.8][:6],
    }
