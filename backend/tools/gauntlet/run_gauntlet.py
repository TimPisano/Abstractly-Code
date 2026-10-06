"""
Overnight gauntlet runner: every fixture in fixtures/manifest.json through the
real Flask routes, graded against the manifest.

    cd backend && venv/bin/python tools/gauntlet/run_gauntlet.py [--only SUBSTR] [--cycle N] [--quiet]

Each case gets a fresh temp SQLite DB and a real analyst session on a real
team. No network: ANTHROPIC_API_KEY is removed from the environment before
the app is imported, and the extraction engine is pinned to regex, so this
never makes an Anthropic API call (CLAUDE.md rule 8).

Writes results/latest.json (+ results/cycle_<N>.json with --cycle) and prints
pass rates by file type.
"""
import argparse
import io
import json
import os
import re
import signal
import sys
import tempfile
import time
import traceback
from collections import defaultdict
from datetime import date

# --- isolation: never touch a real DB, never call the Anthropic API -------
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["LEASE_EXTRACTION_ENGINE"] = "regex"
os.environ["LEASE_AI_EXTRACTION"] = "false"
_BOOT_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DB_PATH"] = _BOOT_DB

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "tests"))
FIX = os.path.join(HERE, "fixtures")
RESULTS = os.path.join(HERE, "results")

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

from app.api import app  # noqa: E402
from app import database, usage_limits  # noqa: E402
from app.normalize import parse_currency, parse_date  # noqa: E402
from _session_users import sync_session_user  # noqa: E402

os.environ.pop("ANTHROPIC_API_KEY", None)  # app import may load backend/.env -- strip again

CASE_TIMEOUT_S = 240


class CaseTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise CaseTimeout()


signal.signal(signal.SIGALRM, _alarm)


# ---------------------------------------------------------------- harness
class Env:
    """One fresh DB + one or more authed clients (one per team)."""

    def __init__(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        database.configure(self.db)
        database.init_db()
        usage_limits._reset_extraction_rate_limit_for_tests()
        try:
            from app.api import _invalidate_lease_derived_caches
            _invalidate_lease_derived_caches()
        except Exception:
            pass
        self._next_uid = 100

    def client(self, team_id):
        self._next_uid += 1
        uid = self._next_uid
        c = app.test_client()
        with c.session_transaction() as s:
            s["user_id"] = uid
            s["email"] = f"gauntlet{uid}@abstractly.test"
            s["name"] = f"Gauntlet {uid}"
            s["role"] = "analyst"
            s["team_id"] = team_id
            sync_session_user(s)
        return c

    def close(self):
        try:
            os.unlink(self.db)
        except OSError:
            pass


def read(rel):
    with open(os.path.join(FIX, rel), "rb") as f:
        return f.read()


def post_file(client, url, field, rel, form=None, name=None):
    data = dict(form or {})
    data[field] = (io.BytesIO(read(rel)), name or os.path.basename(rel).split("__", 1)[-1])
    return client.post(url, data=data, content_type="multipart/form-data")


_UNIT_RE = re.compile(r"(?:\b(?:suite|ste|unit|apt|apartment)\b\.?|#)\s*(?:no\.?\s*)?([A-Za-z0-9][\w-]*)", re.I)


_BLDG_RE = re.compile(r"\b(?:building|bldg)\.?\s*([A-Za-z0-9]+)\b", re.I)


def unit_of(address):
    """Unit id as the manifest writes it ("101", "A-101"); "Building A, Apartment 101" -> "A-101"."""
    if not address:
        return None
    m = _UNIT_RE.search(address)
    if not m:
        return None
    unit = m.group(1).upper()
    b = _BLDG_RE.search(address)
    if b and "-" not in unit:
        unit = f"{b.group(1).upper()}-{unit}"
    return unit


def norm_name(s):
    if not s:
        return ""
    s = s.lower().replace("&", " and ")
    toks = re.sub(r"[^\w\s]", " ", s).split()
    return " ".join(sorted(toks))


def fval(lease, name):
    f = (lease.get("extracted_fields") or lease.get("fields") or {}).get(name) or {}
    return f.get("value") if isinstance(f, dict) else f


def get_all_leases(client):
    r = client.get("/leases?limit=1000")
    body = r.get_json()
    items = body if isinstance(body, list) else (body.get("leases") or body.get("items") or [])
    out = []
    for it in items:
        full = client.get(f"/leases/{it['id']}").get_json()
        out.append(full)
    return out


def money_eq(a, b, tol=0.011):
    return a is not None and b is not None and abs(a - b) <= tol


# ---------------------------------------------------------------- grading pieces
def upload_leases(client, prop):
    """Uploads every lease PDF; returns (failures, extraction_scores)."""
    failures, scores = [], []
    for L in prop["leases"]:
        usage_limits._reset_extraction_rate_limit_for_tests()
        r = post_file(client, "/leases", "file", L["file"], name=f"{prop['id']}_{L['unit']}.pdf")
        if r.status_code not in (200, 201):
            failures.append(f"lease upload {L['file']} -> {r.status_code} {str(r.get_json())[:200]}")
            continue
        lease = r.get_json()["leases"][0]
        full = client.get(f"/leases/{lease['id']}").get_json()
        got = {
            "tenant": norm_name(fval(full, "tenant")) == norm_name(L["tenant"]),
            "rent": money_eq(parse_currency(fval(full, "rent_amount") or ""), L["rent"]),
            "start": parse_date(fval(full, "lease_start_date") or "") == date.fromisoformat(L["start"]),
            "end": parse_date(fval(full, "lease_end_date") or "") == date.fromisoformat(L["end"]),
            "unit": unit_of(fval(full, "property_address")) == L["unit"].upper(),
        }
        scores.append({"file": L["file"], **got})
    return failures, scores


def grade_rent_roll_parse(client, rr, rr_filename):
    exp = rr["expected_rent_roll"]
    problems = []
    leases = [l for l in get_all_leases(client) if (l.get("filename") or "") == rr_filename]
    by_unit = defaultdict(list)
    for l in leases:
        by_unit[unit_of(fval(l, "property_address")) or f"?{fval(l, 'property_address')}"].append(l)
    want = {k.upper(): v for k, v in exp["occupied"].items()}
    for uid, rows in by_unit.items():
        if uid not in want:
            problems.append(f"phantom row imported: unit={uid} tenant={fval(rows[0], 'tenant')!r} rent={fval(rows[0], 'rent_amount')}")
        elif len(rows) > 1:
            problems.append(f"unit {uid} imported {len(rows)} times")
    field_hits = defaultdict(lambda: [0, 0])
    for uid, w in want.items():
        rows = by_unit.get(uid)
        if not rows:
            problems.append(f"missing unit {uid} ({w['tenant']})")
            continue
        l = rows[0]
        checks = {
            "tenant": norm_name(fval(l, "tenant")) == norm_name(w["tenant"]) or
                      set(norm_name(fval(l, "tenant")).split()) == set(norm_name(w["tenant"]).split()),
            "rent": money_eq(parse_currency(fval(l, "rent_amount") or ""), w["rent"]),
        }
        if "start" in w:
            checks["start"] = parse_date(fval(l, "lease_start_date") or "") == date.fromisoformat(w["start"])
        if "end" in w:
            checks["end"] = parse_date(fval(l, "lease_end_date") or "") == date.fromisoformat(w["end"])
        if "concession" in w:
            got_c = parse_currency((fval(l, "concessions") or "").replace("/mo", ""))
            checks["concession"] = money_eq(abs(got_c) if got_c is not None else (0.0 if w["concession"] == 0 else None), w["concession"])
        for k, ok in checks.items():
            field_hits[k][1] += 1
            if ok:
                field_hits[k][0] += 1
            else:
                gotv = {"tenant": fval(l, "tenant"), "rent": fval(l, "rent_amount"), "start": fval(l, "lease_start_date"),
                        "end": fval(l, "lease_end_date"), "concession": fval(l, "concessions")}[k]
                problems.append(f"unit {uid} {k}: got {gotv!r} want {w.get(k)!r}")
    return problems, dict(field_hits)


def grade_findings(rows, expected):
    exp = {(f["unit"].upper(), f["type"]): f for f in expected}
    got = {}
    dupes = []
    for r in rows:
        key = (unit_of(r.get("unit")) or str(r.get("unit")), r["discrepancy_type"])
        if key in got:
            dupes.append(key)
        got[key] = r
    missed = sorted(set(exp) - set(got))
    false = sorted(set(got) - set(exp))
    wrong_amt, wrong_dir = [], []
    for k in set(exp) & set(got):
        e, g = exp[k], got[k]
        if e["annual"] is not None and not money_eq(g.get("annual_dollar_impact"), e["annual"], 0.05):
            wrong_amt.append((k, g.get("annual_dollar_impact"), e["annual"]))
        if e["direction"] is not None and g.get("income_direction") != e["direction"]:
            wrong_dir.append((k, g.get("income_direction"), e["direction"]))
    problems = []
    problems += [f"MISSED {k[1]} unit {k[0]}" for k in missed]
    problems += [f"FALSE ALARM {k[1]} unit {k[0]}: rr={got[k].get('rent_roll_value')!r} lease={got[k].get('lease_value')!r}" for k in false]
    problems += [f"WRONG $ {k[1]} unit {k[0]}: got {g} want {w}" for k, g, w in wrong_amt]
    problems += [f"WRONG DIRECTION {k[1]} unit {k[0]}: got {g} want {w}" for k, g, w in wrong_dir]
    problems += [f"DUPLICATE row {k[1]} unit {k[0]}" for k in dupes]
    return problems, {"expected": len(exp), "caught": len(set(exp) & set(got)), "false": len(false),
                      "wrong_amount": len(wrong_amt)}


def _tag_extraction(problem, lscores):
    """
    Marks a report problem on a unit whose LEASE extraction was wrong (tenant/
    rent/dates/unit misread from the PDF). Lease extraction is owned by the
    feature/lease-intelligence session, so these are reported, not fixed here.
    """
    bad_units = {s["file"].rsplit("/", 1)[-1][:-4].upper() for s in lscores
                 if not all(s[k] for k in ("tenant", "rent", "start", "end", "unit"))}
    m = re.search(r"unit ([A-Z0-9-]+)", problem)
    if m and m.group(1).upper() in bad_units:
        return "[extraction-caused] " + problem
    return problem


def check_exports(client, form, t12_rel=None):
    problems = []
    for ext, magic in (("pdf", b"%PDF"), ("xlsx", b"PK")):
        data = dict(form)
        if t12_rel:
            data["t12_file"] = (io.BytesIO(read(t12_rel)), os.path.basename(t12_rel).split("__", 1)[-1])
        r = client.post(f"/portfolio/deal-mismatch-report.{ext}", data=data, content_type="multipart/form-data")
        if r.status_code != 200 or not r.data.startswith(magic):
            problems.append(f"export .{ext} -> {r.status_code} {r.data[:120]!r}")
    return problems


def error_is_clear(body, keywords):
    msg = ""
    if isinstance(body, dict):
        msg = str(body.get("error") or body.get("message") or "")
    low = msg.lower()
    if not msg or "traceback" in low or "internal server error" in low:
        return False, msg
    for group in keywords:
        if not any(alt in low for alt in group.lower().split("|")):
            return False, msg
    return True, msg


# ---------------------------------------------------------------- case types
def run_rr_case(m, props, rr):
    prop = props[rr["property"]]
    env = Env()
    out = {"problems": [], "metrics": {}}
    try:
        c = env.client(team_id=1)
        lf, lscores = upload_leases(c, prop)
        out["problems"] += lf
        out["metrics"]["lease_extraction"] = lscores
        fname = os.path.basename(rr["file"]).split("__", 1)[-1]
        fname = f"{rr['property']}_{fname}"
        r = post_file(c, "/leases/import-rent-roll", "file", rr["file"], {"property_address": prop["typed_address"]}, name=fname)
        out["metrics"]["import_status"] = r.status_code
        if r.status_code != 201:
            out["problems"].append(f"rent roll import -> {r.status_code}: {str(r.get_json())[:300]}")
            out["stage_fail"] = "import"
            return out
        body = r.get_json()
        out["metrics"]["warnings"] = body.get("warnings")
        p, hits = grade_rent_roll_parse(c, rr, fname)
        out["problems"] += [f"[parse] {x}" for x in p]
        out["metrics"]["parse_fields"] = hits
        out["parse_ok"] = not p
        form = {"property_address": prop["typed_address"]}
        r = c.post("/portfolio/deal-mismatch-report", data=form, content_type="multipart/form-data")
        if r.status_code != 200:
            out["problems"].append(f"report -> {r.status_code}: {r.data[:300]!r}")
            out["stage_fail"] = "report"
            return out
        rep = r.get_json()
        fp, fm = grade_findings(rep["discrepancies"], rr["expected_findings"])
        out["problems"] += [_tag_extraction(f"[report] {x}", lscores) for x in fp]
        out["metrics"]["findings"] = fm
        out["report_ok"] = not fp
        ep = check_exports(c, form)
        out["problems"] += [f"[export] {x}" for x in ep]
    finally:
        env.close()
    return out


def run_bad_rr_case(m, props, bad):
    env = Env()
    out = {"problems": [], "metrics": {}}
    try:
        c = env.client(team_id=1)
        r = post_file(c, "/leases/import-rent-roll", "file", bad["file"], {"property_address": "1 Test Way, Testville, TX 75001"})
        body = r.get_json(silent=True)
        out["metrics"]["status"] = r.status_code
        out["metrics"]["message"] = (body or {}).get("error") if isinstance(body, dict) else None
        if r.status_code >= 500:
            out["problems"].append(f"CRASH {r.status_code}: {r.data[:300]!r}")
        elif r.status_code != bad["expect_status"]:
            out["problems"].append(f"status {r.status_code} (want {bad['expect_status']}): {str(body)[:300]}")
        else:
            ok, msg = error_is_clear(body, bad["expect_keywords"])
            if not ok:
                out["problems"].append(f"UNCLEAR error (want words {bad['expect_keywords']}): {msg[:300]!r}")
    finally:
        env.close()
    return out


def _parse_t12_direct(rel, ext):
    from app.t12_statement import parse_csv_t12_statement, parse_xlsx_t12_statement, parse_pdf_t12_statement
    b = read(rel)
    fn = os.path.basename(rel)
    if ext == "csv":
        return parse_csv_t12_statement(b, fn)
    if ext in ("xlsx", "xls"):
        return parse_xlsx_t12_statement(b, fn)
    return parse_pdf_t12_statement(b, fn)


def run_t12_case(m, props, t, canonical_rr, with_leases=False, rr_expected_findings=None):
    prop = props[t["property"]]
    env = Env()
    out = {"problems": [], "metrics": {}}
    try:
        c = env.client(team_id=1)
        # 1. direct parse vs expected values
        try:
            parsed = _parse_t12_direct(t["file"], t["ext"])
            for k, want in t["expected_parse"].items():
                got = (parsed.get(k) or {}).get("annual") if parsed.get(k) else None
                if got is None:
                    out["problems"].append(f"[t12 parse] {k}: not found (want {want:,.2f})")
                elif abs(abs(got) - want) > 1.0:
                    out["problems"].append(f"[t12 parse] {k}: got {got:,.2f} want {want:,.2f}")
        except Exception as e:
            out["problems"].append(f"[t12 parse] raised {type(e).__name__}: {str(e)[:200]}")
        out["parse_ok"] = not out["problems"]
        # 2. full pipeline
        lscores = []
        if with_leases:
            lf, lscores = upload_leases(c, prop)
            out["problems"] += lf
        rname = f"{prop['id']}_rent_roll.csv"
        r = post_file(c, "/leases/import-rent-roll", "file", canonical_rr["file"], {"property_address": prop["typed_address"]}, name=rname)
        if r.status_code != 201:
            out["problems"].append(f"canonical rent roll import -> {r.status_code}")
            return out
        form = {"property_address": prop["typed_address"]}
        data = dict(form)
        data["t12_file"] = (io.BytesIO(read(t["file"])), f"{prop['id']}_t12.{t['ext']}")
        r = c.post("/portfolio/deal-mismatch-report", data=data, content_type="multipart/form-data")
        if r.status_code != 200:
            out["problems"].append(f"[t12 report] -> {r.status_code}: {r.data[:300]!r}")
            out["stage_fail"] = "report"
            return out
        rep = r.get_json()
        rows = rep.get("rent_roll_vs_actual_collections") or []
        got = {row["discrepancy_type"]: row for row in rows}
        want = {row["type"]: row for row in t["expected_t12_rows"]}
        for k in sorted(set(want) - set(got)):
            out["problems"].append(f"[t12 report] MISSED {k}")
        for k in sorted(set(got) - set(want)):
            g = got[k]
            out["problems"].append(f"[t12 report] FALSE ALARM {k}: rr={g.get('rent_roll_value')!r} t12={g.get('lease_value')!r}")
        for k in set(want) & set(got):
            if want[k]["annual"] is not None and not money_eq(got[k].get("annual_dollar_impact"), want[k]["annual"], 1.0):
                out["problems"].append(f"[t12 report] WRONG $ {k}: got {got[k].get('annual_dollar_impact')} want {want[k]['annual']}")
        out["metrics"]["t12_rows"] = {"expected": len(want), "caught": len(set(want) & set(got)), "false": len(set(got) - set(want))}
        if with_leases and rr_expected_findings is not None:
            fp, fm = grade_findings(rep["discrepancies"], rr_expected_findings)
            out["problems"] += [_tag_extraction(f"[report] {x}", lscores) for x in fp]
            out["metrics"]["findings"] = fm
        # 3. the standalone T-12 cross-check route (csv/xlsx only by design)
        if t["ext"] in ("csv", "xlsx"):
            r = post_file(c, "/portfolio/t12-reconciliation", "file", t["file"], form, name=f"t12.{t['ext']}")
            if r.status_code != 200:
                out["problems"].append(f"[t12-reconciliation] -> {r.status_code}: {str(r.get_json())[:200]}")
            else:
                b = r.get_json()
                if not money_eq(b.get("t12_annual_rental_income"), t["expected_parse"]["rental_income_collected"], 1.0):
                    out["problems"].append(f"[t12-reconciliation] rental income got {b.get('t12_annual_rental_income')} want {t['expected_parse']['rental_income_collected']}")
                if not money_eq(b.get("rent_roll_annual_rent"), t["rent_roll_annual"], 1.0):
                    out["problems"].append(f"[t12-reconciliation] rent roll annual got {b.get('rent_roll_annual_rent')} want {t['rent_roll_annual']}")
        out["problems"] += [f"[export] {x}" for x in check_exports(c, form, t["file"])]
    finally:
        env.close()
    return out


def run_bad_t12_case(m, props, bad, canonical_rr):
    prop = props[bad["property"]]
    env = Env()
    out = {"problems": [], "metrics": {}}
    try:
        c = env.client(team_id=1)
        post_file(c, "/leases/import-rent-roll", "file", canonical_rr["file"], {"property_address": prop["typed_address"]}, name="rr.csv")
        data = {"property_address": prop["typed_address"],
                "t12_file": (io.BytesIO(read(bad["file"])), os.path.basename(bad["file"]).split("__", 1)[-1])}
        r = c.post("/portfolio/deal-mismatch-report", data=data, content_type="multipart/form-data")
        body = r.get_json(silent=True)
        out["metrics"]["status"] = r.status_code
        if r.status_code >= 500:
            out["problems"].append(f"CRASH {r.status_code}: {r.data[:300]!r}")
        elif r.status_code != 400:
            rows = (body or {}).get("rent_roll_vs_actual_collections")
            out["problems"].append(f"status {r.status_code} (want 400) -- bad T-12 accepted silently; T-12 rows={rows!r}"[:400])
        else:
            ok, msg = error_is_clear(body, bad["expect_keywords"])
            if not ok:
                out["problems"].append(f"UNCLEAR error (want words {bad['expect_keywords']}): {msg[:300]!r}")
    finally:
        env.close()
    return out


def run_reimport_case(m, props, ri):
    """Stale rent roll, then the updated one: the report must equal the updated file alone (AUDIT.md §6.11)."""
    prop = props[ri["property"]]
    env = Env()
    out = {"problems": [], "metrics": {}}
    try:
        c = env.client(team_id=1)
        lf, lscores = upload_leases(c, prop)
        out["problems"] += lf
        for rel, name in ((ri["first"], f"{prop['id']}_v1.csv"), (ri["second"], f"{prop['id']}_v2.csv")):
            r = post_file(c, "/leases/import-rent-roll", "file", rel, {"property_address": prop["typed_address"]}, name=name)
            if r.status_code != 201:
                out["problems"].append(f"import {rel} -> {r.status_code}")
                return out
        p, _ = grade_rent_roll_parse(c, {"expected_rent_roll": ri["expected_rent_roll"]}, f"{prop['id']}_v2.csv")
        out["problems"] += [f"[parse] {x}" for x in p]
        stale = [l for l in get_all_leases(c) if l.get("filename") == f"{prop['id']}_v1.csv"]
        if stale:
            out["problems"].append(f"[reimport] {len(stale)} stale v1 rows still active after importing v2")
        r = c.post("/portfolio/deal-mismatch-report", data={"property_address": prop["typed_address"]}, content_type="multipart/form-data")
        fp, fm = grade_findings(r.get_json()["discrepancies"], ri["expected_findings"])
        out["problems"] += [_tag_extraction(f"[report] {x}", lscores) for x in fp]
        out["metrics"]["findings"] = fm
    finally:
        env.close()
    return out


def run_isolation_case(m, props, canonical_rr):
    """Team 2 loads a whole deal; team 1 must see none of it."""
    prop = props["p00"]
    env = Env()
    out = {"problems": [], "metrics": {}}
    try:
        b = env.client(team_id=2)
        a = env.client(team_id=1)
        upload_leases(b, prop)
        post_file(b, "/leases/import-rent-roll", "file", canonical_rr["file"], {"property_address": prop["typed_address"]}, name="rr.csv")
        b_ids = [l["id"] for l in get_all_leases(b)]
        if not b_ids:
            out["problems"].append("setup: team 2 has no leases")
        if get_all_leases(a):
            out["problems"].append("team 1 can list team 2's leases")
        for lid in b_ids[:3]:
            if a.get(f"/leases/{lid}").status_code != 404:
                out["problems"].append(f"team 1 can read team 2 lease {lid}")
        for form in ({"property_address": prop["typed_address"]}, {}):
            r = a.post("/portfolio/deal-mismatch-report", data=form, content_type="multipart/form-data")
            if r.status_code != 200 or r.get_json()["total_discrepancies"] != 0:
                out["problems"].append(f"team 1 report shows team 2 data: {r.status_code} {str(r.get_json())[:200]}")
        r = post_file(a, "/portfolio/t12-reconciliation", "file", m["t12s"][0]["file"], {"property_address": prop["typed_address"]}, name="t.xlsx")
        if r.status_code == 200 and (r.get_json() or {}).get("matched_lease_count"):
            out["problems"].append("team 1's T-12 cross-check counted team 2's rent roll")
    finally:
        env.close()
    return out


# ---------------------------------------------------------------- driver
def timed(fn, *a, **k):
    t0 = time.time()
    signal.alarm(CASE_TIMEOUT_S)
    try:
        res = fn(*a, **k)
    except CaseTimeout:
        res = {"problems": [f"HANG: exceeded {CASE_TIMEOUT_S}s"], "metrics": {}, "stage_fail": "hang"}
    except Exception as e:
        res = {"problems": [f"HARNESS/APP EXCEPTION {type(e).__name__}: {e}", traceback.format_exc()[-1500:]], "metrics": {}, "stage_fail": "exception"}
    finally:
        signal.alarm(0)
    res["seconds"] = round(time.time() - t0, 2)
    res["pass"] = not res["problems"]
    res["pass_excluding_extraction"] = all(p.startswith("[extraction-caused]") for p in res["problems"])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--cycle", default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--skip", default="", help="comma list of case kinds to skip: rr,bad_rr,t12,bad_t12,deal,iso")
    args = ap.parse_args()
    skip = set(filter(None, args.skip.split(",")))
    with open(os.path.join(FIX, "manifest.json")) as f:
        m = json.load(f)
    props = {p["id"]: p for p in m["properties"]}
    canonical = {r["property"]: r for r in m["rent_rolls"] if r["canonical"]}
    cases = []
    if "rr" not in skip:
        cases += [("rr", r["file"], r["format"], (lambda r=r: run_rr_case(m, props, r))) for r in m["rent_rolls"]]
    if "bad_rr" not in skip:
        cases += [("bad_rr", b["file"], "bad_rent_roll", (lambda b=b: run_bad_rr_case(m, props, b))) for b in m["bad_rent_rolls"]]
    if "t12" not in skip:
        cases += [("t12", t["file"], t["format"], (lambda t=t: run_t12_case(m, props, t, canonical[t["property"]]))) for t in m["t12s"]]
    if "bad_t12" not in skip:
        cases += [("bad_t12", b["file"], "bad_t12", (lambda b=b: run_bad_t12_case(m, props, b, canonical[b["property"]]))) for b in m["bad_t12s"]]
    if "deal" not in skip:
        firsts = {}
        for t in m["t12s"]:
            firsts.setdefault(t["property"], t)
        for pid, t in firsts.items():
            cases.append(("deal", f"deal:{pid}", "full_deal", (lambda t=t, pid=pid: run_t12_case(
                m, props, t, canonical[pid], with_leases=True, rr_expected_findings=canonical[pid]["expected_findings"]))))
    if "reimport" not in skip:
        cases += [("reimport", f"reimport:{ri['property']}", "reimport_updated_rent_roll",
                   (lambda ri=ri: run_reimport_case(m, props, ri))) for ri in m.get("reimports", [])]
    if "iso" not in skip:
        cases.append(("iso", "isolation:p00", "team_isolation", lambda: run_isolation_case(m, props, canonical["p00"])))
    if args.only:
        cases = [c for c in cases if args.only in c[1] or args.only == c[2]]

    results = []
    t0 = time.time()
    for kind, name, fmt, fn in cases:
        res = timed(fn)
        res.update(kind=kind, name=name, format=fmt)
        results.append(res)
        if not args.quiet:
            mark = "PASS" if res["pass"] else "FAIL"
            print(f"{mark} {res['seconds']:6.1f}s {kind:7s} {name}")
            if not res["pass"]:
                for p in res["problems"][:12]:
                    print(f"        - {p}")
                if len(res["problems"]) > 12:
                    print(f"        ... +{len(res['problems']) - 12} more")
    summary = summarize(results)
    summary["wall_seconds"] = round(time.time() - t0, 1)
    os.makedirs(RESULTS, exist_ok=True)
    payload = {"summary": summary, "results": results}
    with open(os.path.join(RESULTS, "latest.json"), "w") as f:
        json.dump(payload, f, indent=1, default=str)
    if args.cycle:
        with open(os.path.join(RESULTS, f"cycle_{args.cycle}.json"), "w") as f:
            json.dump(payload, f, indent=1, default=str)
        hist_path = os.path.join(HERE, "history.json")  # tracked in git; results/ is not
        hist = {}
        if os.path.exists(hist_path):
            with open(hist_path) as f:
                hist = json.load(f)
        hist[str(args.cycle)] = summary
        with open(hist_path, "w") as f:
            json.dump(hist, f, indent=1, sort_keys=True)
    print_summary(summary)


def summarize(results):
    by = defaultdict(lambda: [0, 0])
    by_kind = defaultdict(lambda: [0, 0])
    fexp = fcaught = ffalse = famt = 0
    lease_tot = defaultdict(lambda: [0, 0])
    crashes = hangs = 0
    for r in results:
        key = f"{r['kind']}:{r['format']}"
        by[key][1] += 1
        by_kind[r["kind"]][1] += 1
        if r["pass"]:
            by[key][0] += 1
            by_kind[r["kind"]][0] += 1
        f = r["metrics"].get("findings")
        if f:
            fexp += f["expected"]
            fcaught += f["caught"]
            ffalse += f["false"]
            famt += f["wrong_amount"]
        for s in r["metrics"].get("lease_extraction") or []:
            for k in ("tenant", "rent", "start", "end", "unit"):
                lease_tot[k][1] += 1
                lease_tot[k][0] += 1 if s[k] else 0
        for p in r["problems"]:
            if p.startswith("CRASH") or "-> 500" in p or "EXCEPTION" in p:
                crashes += 1
            if p.startswith("HANG"):
                hangs += 1
    return {
        "cases": len(results), "passed": sum(1 for r in results if r["pass"]),
        "passed_excluding_extraction": sum(1 for r in results if r["pass_excluding_extraction"]),
        "by_kind": {k: {"pass": v[0], "total": v[1]} for k, v in sorted(by_kind.items())},
        "by_format": {k: {"pass": v[0], "total": v[1]} for k, v in sorted(by.items())},
        "findings": {"expected": fexp, "caught": fcaught, "false_alarms": ffalse, "wrong_amount": famt},
        "lease_extraction_field_accuracy": {k: {"ok": v[0], "total": v[1]} for k, v in lease_tot.items()},
        "crashes": crashes, "hangs": hangs,
    }


def print_summary(s):
    print("\n==== GAUNTLET SUMMARY ====")
    print(f"cases passed: {s['passed']}/{s['cases']} ({s['passed_excluding_extraction']} if lease-extraction misses are excluded)   crashes={s['crashes']} hangs={s['hangs']}  wall={s.get('wall_seconds')}s")
    for k, v in s["by_kind"].items():
        print(f"  {k:8s} {v['pass']}/{v['total']}")
    print("  by format:")
    for k, v in s["by_format"].items():
        print(f"    {k:32s} {v['pass']}/{v['total']}")
    f = s["findings"]
    print(f"  findings: caught {f['caught']}/{f['expected']}, false alarms {f['false_alarms']}, wrong $ {f['wrong_amount']}")
    print(f"  lease extraction (owned by feature/lease-intelligence): {s['lease_extraction_field_accuracy']}")


if __name__ == "__main__":
    main()
