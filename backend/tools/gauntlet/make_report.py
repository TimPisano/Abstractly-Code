"""
Builds QA_REPORT.md (repo root) from:
  - results/latest.json and results/cycle_*.json  (run_gauntlet.py output)
  - report_notes.md                                (hand-written narrative: summary,
                                                    open issues, recommendations)
  - git log of "Fix:" commits on this branch       (fixes + hashes)

    cd backend && venv/bin/python tools/gauntlet/make_report.py
"""
import glob
import json
import os
import re
import subprocess
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RESULTS = os.path.join(HERE, "results")

FILE_TYPE = {
    "csv": "CSV", "txt": "TXT (Excel Unicode Text)", "xlsx": "Excel .xlsx", "xls": "Excel .xls (legacy)",
    "docx": "Word .docx", "pdf": "PDF",
}


def _pct(a, b):
    return f"{a}/{b} ({(100 * a / b):.0f}%)" if b else "0/0"


def _ext(name):
    base = name.split(":")[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else "-"


def tables(latest):
    s = latest["summary"]
    res = latest["results"]
    out = []
    out.append(f"| Metric | Value |\n|---|---|")
    out.append(f"| Cases passed | {_pct(s['passed'], s['cases'])} |")
    out.append(f"| Cases passed, ignoring lease-extraction misses* | {_pct(s.get('passed_excluding_extraction', s['passed']), s['cases'])} |")
    f = s["findings"]
    out.append(f"| Planted mismatches caught (rent-roll + full-deal cases) | {_pct(f['caught'], f['expected'])} |")
    out.append(f"| False alarms | {f['false_alarms']} |")
    out.append(f"| Caught but wrong dollar amount | {f['wrong_amount']} |")
    out.append(f"| Crashes (500 / exception) | {s['crashes']} |")
    out.append(f"| Hangs (> 240 s) | {s['hangs']} |")
    out.append(f"| Wall time | {s.get('wall_seconds')} s |")
    out.append("")
    out.append("\\* Lease extraction is owned by the `feature/lease-intelligence` session; failures it causes are tagged `[extraction-caused]` and not fixed here.")
    out.append("")
    # by case kind
    kinds = {"rr": "Rent roll (upload → parse → report → exports)", "bad_rr": "Bad rent-roll files (clear 400 expected)",
             "t12": "T-12 (parse → report T-12 rows → cross-check route → exports)", "bad_t12": "Bad T-12 files (clear 400 expected)",
             "deal": "Full deal (leases + rent roll + T-12)", "iso": "Team isolation",
             "reimport": "Re-import of an updated rent roll", "multiprop": "One rent-roll file covering two properties"}
    out.append("### Pass rate by case type\n\n| Case type | Passed |\n|---|---|")
    for k, v in s["by_kind"].items():
        out.append(f"| {kinds.get(k, k)} | {_pct(v['pass'], v['total'])} |")
    out.append("")
    # by file type
    by_type = defaultdict(lambda: [0, 0])
    for r in res:
        if r["kind"] not in ("rr", "t12", "bad_rr", "bad_t12"):
            continue
        group = ("Rent roll " if r["kind"] in ("rr", "bad_rr") else "T-12 ") + ("(bad file) " if r["kind"].startswith("bad") else "")
        key = group + FILE_TYPE.get(_ext(r["name"]), _ext(r["name"]))
        by_type[key][1] += 1
        by_type[key][0] += 1 if r["pass"] else 0
    out.append("### Pass rate by file type\n\n| File type | Passed |\n|---|---|")
    for k in sorted(by_type):
        a, b = by_type[k]
        out.append(f"| {k} | {_pct(a, b)} |")
    out.append("")
    out.append("### Pass rate by source format\n\n| Format | Passed |\n|---|---|")
    for k, v in s["by_format"].items():
        out.append(f"| `{k}` | {_pct(v['pass'], v['total'])} |")
    out.append("")
    return "\n".join(out)


def history():
    path = os.path.join(HERE, "history.json")
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        hist = json.load(f)
    rows = []
    for n in sorted(hist, key=int):
        s = hist[n]
        f_ = s["findings"]
        rows.append(f"| {n} | {_pct(s['passed'], s['cases'])} | {_pct(f_['caught'], f_['expected'])} | {f_['false_alarms']} | {s['crashes']} | {s['hangs']} |")
    return ("| Cycle | Cases passed | Mismatches caught | False alarms | Crashes | Hangs |\n|---|---|---|---|---|---|\n"
            + "\n".join(rows) + "\n")


def fixes():
    log = subprocess.run(["git", "log", "--reverse", "--format=%h%x09%s", "main..HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    out = []
    for line in log.splitlines():
        h, subj = line.split("\t", 1)
        if subj.startswith("Fix"):
            what = subj.split(":", 1)[1].strip()
            out.append(f"| `{h}` | {what} |")
    return "| Commit | Fix |\n|---|---|\n" + "\n".join(out) + "\n" if out else "(none yet)\n"


def failing(latest, limit=60):
    out = []
    for r in latest["results"]:
        if r["pass"]:
            continue
        probs = [p for p in r["problems"] if not p.startswith("Traceback")][:3]
        out.append(f"- `{r['name']}` ({r['format']}): " + "; ".join(p.replace("|", "/")[:160] for p in probs))
    more = len(out) - limit
    return "\n".join(out[:limit]) + (f"\n- … {more} more in `backend/tools/gauntlet/results/latest.json`" if more > 0 else "")


def main():
    with open(os.path.join(RESULTS, "latest.json")) as f:
        latest = json.load(f)
    with open(os.path.join(HERE, "report_notes.md")) as f:
        notes = f.read()
    sections = dict(re.findall(r"<!-- (\w+) -->\n(.*?)(?=\n<!-- \w+ -->|\Z)", notes, re.S))
    doc = f"""# QA Report: Overnight Reliability Gauntlet

Branch `qa/overnight-gauntlet` · worktree `~/dev/projects/abstractly-gauntlet` · **not merged, not deployed**.
Generated by `backend/tools/gauntlet/make_report.py` from the latest gauntlet run.
(The previous QA report, for `fix/rent-roll-hardening`, is in git history at `03cebb5`.)

## Summary

{sections.get('SUMMARY', '').strip()}

## Latest run

{tables(latest)}
## Progress by cycle

{history()}
## Fixes (one commit each, each with a regression test in `backend/tests/test_gauntlet_regressions.py`)

{fixes()}
## What I couldn't fix (or chose not to)

{sections.get('OPEN', '').strip()}

## Top 5 recommendations

{sections.get('RECS', '').strip()}

## How to run it

```bash
cd backend
PYTHONPATH=<dir with msoffcrypto-tool + xlwt> venv/bin/python tools/gauntlet/generate.py   # regenerate fixtures (deterministic; optional libs only for the password .xlsx / .xls fixtures, which are committed)
venv/bin/python tools/gauntlet/run_gauntlet.py --cycle N                                   # ~30 s, no network, no Anthropic calls
venv/bin/python tools/gauntlet/make_report.py                                               # rewrite this file
```

What the gauntlet is: {sections.get('ABOUT', '').strip()}

## Remaining failing cases (latest run)

{failing(latest)}
"""
    with open(os.path.join(ROOT, "QA_REPORT.md"), "w") as f:
        f.write(doc)
    print("wrote QA_REPORT.md")


if __name__ == "__main__":
    main()
