"""
Grade lease extraction against the synthetic corpus (see generate.py).

Every file goes through the same helper the upload route uses
(api._extract_leases_from_file_storage): page text extraction with the
OCR fallback, the "unreadable page" gate, lease boundary detection, and
the configured engine (regex unless LEASE_EXTRACTION_ENGINE says
otherwise; the AI engine is never called here without the user's OK).

Each expected value is one "check". A check is:
  correct  -- extracted value matches the answer key
  missed   -- nothing extracted where the key has a value
  wrong    -- a value was extracted and it doesn't match
  spurious -- a value was extracted where the key says there is none
  correct  -- also when both sides are empty (correctly not found)

    python tools/lease_corpus/run_corpus.py [--corpus DIR] [--regenerate] [--only FAMILY] [--json OUT]

Writes tools/lease_corpus/results/latest.json and prints a summary.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tempfile
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

# Never touch a real database from a grading run.
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(prefix="lease_corpus_"), "corpus.db"))
os.environ.setdefault("LEASE_EXTRACTION_ENGINE", "regex")
os.environ.setdefault("LEASE_MULTIFAMILY_FIELDS", "1")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from werkzeug.datastructures import FileStorage  # noqa: E402

from app import api  # noqa: E402
from app.extraction_scoring import values_match  # noqa: E402
from app.normalize import parse_currency, parse_date  # noqa: E402

import generate  # noqa: E402

DEFAULT_CORPUS = generate.DEFAULT_OUT
RESULTS_DIR = os.path.join(HERE, "results")

BASE_FIELDS = ["tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date",
               "property_address", "security_deposit"]
MF_FIELDS = ["unit_number", "current_rent_amount", "current_lease_end_date"]
_MONEY = {"current_rent_amount"}
_DATES = {"current_lease_end_date"}


def _value(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(entry, dict):
        return None
    v = entry.get("value")
    return None if v in (None, "", "Not Found") else str(v)


def _details(fields: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    entry = fields.get(key)
    if not isinstance(entry, dict) or entry.get("value") in (None, ""):
        return None
    return entry.get("details") or {}


def _norm_unit(u: Optional[str]) -> str:
    u = (u or "").lower()
    u = re.sub(r"^(?:apartment|apt|unit|suite|ste|no|number)\.?\s*(?:no\.?|number|#)?\s*", "", u.strip())
    return re.sub(r"[\s#.]", "", u)


def _match(field: str, got: Optional[str], want: Optional[str]) -> bool:
    if field in _MONEY:
        a, b = parse_currency(got), parse_currency(want)
        return a is not None and b is not None and abs(a - b) <= 1.0
    if field in _DATES:
        return parse_date(got) is not None and parse_date(got) == parse_date(want)
    if field == "unit_number":
        return bool(got) and _norm_unit(got) == _norm_unit(want)
    return values_match(field, got, want)


def _kind(got: Any, want: Any, ok: bool) -> str:
    empty_got = got in (None, "", [], {}, False) if not isinstance(got, (int, float)) or isinstance(got, bool) else False
    empty_want = want in (None, "", [], {}, False) if not isinstance(want, (int, float)) or isinstance(want, bool) else False
    if empty_want and empty_got:
        return "correct"
    if ok:
        return "correct"
    if empty_got:
        return "missed"
    if empty_want:
        return "spurious"
    return "wrong"


def _num_eq(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) <= 0.5
    except (TypeError, ValueError):
        return False


def ok_value(v: Any) -> bool:
    return v not in (None, "", [], {}, False, 0, 0.0)


def grade_case(case: Dict[str, Any], leases: List[Dict[str, Any]], status: Optional[str]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    def add(group: str, name: str, got: Any, want: Any, ok: bool, conf: Optional[str] = None):
        # A charge/Section 8 sub-check where the lease has none AND none was
        # extracted is not evidence of anything -- skip it rather than let
        # dozens of "correctly absent" pet deposits inflate the score.
        # Spurious extractions (got something, key says none) still count.
        if group in ("charges", "section_8") and not ok_value(got) and not ok_value(want):
            return
        checks.append({"group": group, "check": name, "got": got, "want": want,
                       "kind": _kind(got, want, ok), "confidence": conf})

    add("structure", "lease_count", len(leases), case["expected_lease_count"],
        len(leases) == case["expected_lease_count"])
    add("structure", "processed", status or "ok", "ok", status in (None, "ok", "completed"))

    fields = leases[0]["fields"] if leases else {}
    exp = case["fields"]
    for name in BASE_FIELDS + MF_FIELDS:
        entry = fields.get(name)
        got = _value(entry)
        add("base" if name in BASE_FIELDS else "multifamily", name, got, exp.get(name),
            _match(name, got, exp.get(name)), (entry or {}).get("confidence") if isinstance(entry, dict) else None)

    # --- structured multifamily charges -------------------------------
    pet = _details(fields, "pet_charges") or {}
    want_pet = case.get("pet_charges") or {}
    for k in ("monthly_rent", "fee", "deposit"):
        add("charges", f"pet.{k}", pet.get(k), want_pet.get(k), _num_eq(pet.get(k), want_pet.get(k)))

    park = _details(fields, "parking_charges") or {}
    want_park = case.get("parking_charges") or {}
    add("charges", "parking.monthly_fee", park.get("monthly_fee"), want_park.get("monthly_fee"),
        _num_eq(park.get("monthly_fee"), want_park.get("monthly_fee")))

    util = _details(fields, "utility_charges") or {}
    want_util = case.get("utility_charges") or {}
    add("charges", "utility.rubs", bool(util.get("rubs")), bool(want_util.get("rubs")),
        bool(util.get("rubs")) == bool(want_util.get("rubs")))
    got_u = sorted(util.get("rubs_utilities") or [])
    want_u = sorted(want_util.get("rubs_utilities") or [])
    add("charges", "utility.rubs_utilities", got_u, want_u, got_u == want_u)
    got_flat = util.get("flat_monthly_total") or None
    want_flat = want_util.get("flat_monthly_total") or None
    add("charges", "utility.flat_monthly_total", got_flat, want_flat, _num_eq(got_flat, want_flat))

    s8 = _details(fields, "section_8") or {}
    want_s8 = case.get("section_8") or {}
    add("section_8", "s8.is_section_8", bool(s8.get("is_section_8")), bool(want_s8.get("is_section_8")),
        bool(s8.get("is_section_8")) == bool(want_s8.get("is_section_8")))
    for k in ("contract_rent", "tenant_rent", "hap_amount", "utility_allowance"):
        add("section_8", f"s8.{k}", s8.get(k), want_s8.get(k), _num_eq(s8.get(k), want_s8.get(k)))
    got_pha = s8.get("pha_name")
    want_pha = want_s8.get("pha_name")
    add("section_8", "s8.pha_name", got_pha, want_pha,
        (got_pha is None and want_pha is None) or bool(got_pha and want_pha and want_pha.lower() in got_pha.lower()))

    conc = fields.get("concessions") or {}
    has_conc = bool(_value(conc))
    add("charges", "concession_present", has_conc, case.get("has_concession"), has_conc == bool(case.get("has_concession")))

    changes = (_details(fields, "lease_changes") or {}).get("changes") or []
    want_changes = case.get("lease_changes") or []
    add("multifamily", "lease_changes.count", len(changes), len(want_changes), len(changes) == len(want_changes))

    if case.get("second_lease") and len(leases) > 1:
        f2 = leases[1]["fields"]
        for name in ("tenant", "rent_amount"):
            got = _value(f2.get(name))
            want = case["second_lease"].get(name)
            add("structure", f"second_lease.{name}", got, want, _match(name, got, want))
    return checks


def run(corpus: str, only: Optional[str] = None) -> Dict[str, Any]:
    with open(os.path.join(corpus, "manifest.json")) as fh:
        manifest = json.load(fh)
    results = []
    for case in manifest["cases"]:
        if only and not case["family"].startswith(only):
            continue
        path = os.path.join(corpus, case["file"])
        with open(path, "rb") as fh:
            data = fh.read()
        t0 = time.time()
        fs = FileStorage(stream=io.BytesIO(data), filename=case["file"], content_type="application/pdf")
        leases, err = api._extract_leases_from_file_storage(fs, defer_ai=False)
        elapsed = round(time.time() - t0, 2)
        leases = leases or []
        status = err[0] if err else (leases[0].get("processing_status") if leases else "no_leases")
        checks = grade_case(case, leases, status)
        results.append({"file": case["file"], "family": case["family"], "scanned": case["scanned"],
                        "seconds": elapsed, "status": status, "checks": checks})
    return summarize(results)


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_check: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_group: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_family: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    high_conf_wrong = []
    total = correct = 0
    for r in results:
        for c in r["checks"]:
            total += 1
            correct += c["kind"] == "correct"
            by_check[c["check"]][c["kind"]] += 1
            by_group[c["group"]][c["kind"]] += 1
            by_family[r["family"]][c["kind"]] += 1
            if c["kind"] in ("wrong", "spurious") and c.get("confidence") == "high":
                high_conf_wrong.append({"file": r["file"], "check": c["check"], "got": c["got"], "want": c["want"]})

    def pct(d):
        n = sum(d.values())
        return round(100.0 * d.get("correct", 0) / n, 1) if n else None

    return {
        "overall_pct": round(100.0 * correct / total, 1) if total else None,
        "checks_total": total,
        "by_group": {k: {"pct": pct(v), **v} for k, v in sorted(by_group.items())},
        "by_check": {k: {"pct": pct(v), **v} for k, v in sorted(by_check.items())},
        "by_family": {k: {"pct": pct(v), **v} for k, v in sorted(by_family.items())},
        "high_confidence_wrong": high_conf_wrong,
        "files": results,
    }


def print_summary(s: Dict[str, Any]) -> None:
    print(f"\nOVERALL: {s['overall_pct']}% of {s['checks_total']} checks correct\n")
    print("By group:")
    for k, v in s["by_group"].items():
        print(f"  {k:<14} {v['pct']:>5}%  " + " ".join(f"{kk}={vv}" for kk, vv in v.items() if kk != "pct"))
    print("\nBy check:")
    for k, v in s["by_check"].items():
        print(f"  {k:<28} {v['pct']:>5}%  " + " ".join(f"{kk}={vv}" for kk, vv in v.items() if kk != "pct"))
    print("\nBy family:")
    for k, v in s["by_family"].items():
        print(f"  {k:<24} {v['pct']:>5}%")
    print(f"\nHigh-confidence wrong/spurious: {len(s['high_confidence_wrong'])}")
    for h in s["high_confidence_wrong"][:25]:
        print(f"  {h['file']}: {h['check']} got={h['got']!r} want={h['want']!r}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--json", default=os.path.join(RESULTS_DIR, "latest.json"))
    ap.add_argument("--failures", action="store_true", help="print every non-correct check")
    a = ap.parse_args(argv)
    if a.regenerate or not os.path.exists(os.path.join(a.corpus, "manifest.json")):
        generate.generate(a.corpus)
    s = run(a.corpus, a.only)
    os.makedirs(os.path.dirname(a.json), exist_ok=True)
    with open(a.json, "w") as fh:
        json.dump(s, fh, indent=2, default=str)
    print_summary(s)
    if a.failures:
        print("\nFailures:")
        for r in s["files"]:
            for c in r["checks"]:
                if c["kind"] != "correct":
                    print(f"  {r['file']:<34} {c['check']:<26} {c['kind']:<8} got={c['got']!r} want={c['want']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
