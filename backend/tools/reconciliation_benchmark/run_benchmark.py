"""
Lease-vs-rent-roll reconciliation benchmark.

Runs a CONSTRUCTED test portfolio -- lease-document records plus a rent
roll for the same units -- through the REAL reconciliation path
(POST /leases/import-rent-roll + GET /portfolio/rent-roll-reconciliation,
the exact routes the product uses) against an isolated temp database,
then grades what the engine flagged against a hand-authored ground truth.

WHAT THIS IS
------------
A defensible, reproducible measurement of what the arithmetic
reconciliation engine (app/portfolio.compute_rent_roll_reconciliation)
catches, on a portfolio whose discrepancies are modelled on documented
real-world property-management-system drift:

  * escalation drift -- the lease's rent has stepped up per its stated
    annual escalation, the PM system still shows the original figure
  * post-renewal reset -- tenant exercised a renewal option at a new
    rent, PM system still shows the expiring-term rent
  * stale expiration -- lease extended by amendment, rent roll still
    shows the pre-extension end date
  * data-entry error -- rent roll expiration year keyed wrong
  * tenant of record -- lease assigned/subleased, one side not updated
  * name form -- rent roll carries the DBA / trade name, the lease is
    signed by the legal entity (engine flags it; a human triages it)

It also includes control units that MUST NOT flag (a sub-tolerance
rounding difference, a field blank on one side) and one unit whose
address is formatted differently on each side, which the engine cannot
match at all -- a real limitation, reported here as a miss rather than
hidden.

WHAT THIS IS NOT
----------------
Field data. Both sides of every pair were authored here. This measures
"does the engine flag what it is designed to flag, and does it avoid
flagging what it should not" on a realistic-looking set -- not "does it
catch problems a human on a real deal would have missed." Any external
claim built on the output number must say "constructed test portfolio".

Usage:  python3 run_benchmark.py [--out report.md]
"""
import argparse
import csv
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.api import app
from app import database
from app.portfolio import FIELD_NAMES

# Three buildings; the rent roll is uploaded once per building with that
# building's street address as the base, and each row's Unit cell is
# combined into "<base>, Suite <unit>" by the real importer.
BUILDINGS = {
    "A": "1400 Rivermark Plaza, San Jose, CA 95134",
    "B": "88 Harborside Boulevard, Oakland, CA 94607",
    "C": "2250 Foothill Commerce Center, Fremont, CA 94538",
}

# ---------------------------------------------------------------------------
# The constructed portfolio.
#
# Each entry is one unit. `lease` is what the abstracted lease document
# says; `rr` is the rent roll row for the same unit. `expect` is the
# ground truth: the set of fields on which a correct engine SHOULD flag
# a disagreement, each tagged with its real-world cause and whether it is
# `material` (changes the underwriting/legal picture) or a softer
# `name_form` flag. `note` explains anything non-obvious.
#
# rent is monthly. Dates: lease side legal-style, rent roll side MM/DD/YYYY
# -- both are parsed by app.normalize.parse_date, so the format difference
# is deliberate (and itself exercised).
# ---------------------------------------------------------------------------
def U(unit, building, lease, rr, expect=(), note="", lease_suite_override=None):
    return {"unit": unit, "building": building, "lease": lease, "rr": rr,
            "expect": list(expect), "note": note,
            "lease_suite_override": lease_suite_override}


PORTFOLIO = [
    # ---- Building A : retail, 12 units -------------------------------------
    U("101", "A",
      lease=dict(tenant="Rivermark Coffee Roasters, LLC", rent="$6,180.00",
                 start="March 1, 2021", end="February 28, 2027"),
      rr=dict(tenant="Rivermark Coffee Roasters, LLC", rent="$6,180.00",
              start="03/01/2021", end="02/28/2027")),  # clean

    U("102", "A",
      lease=dict(tenant="Bright Path Dental Group, P.C.", rent="$9,724.00",
                 start="June 15, 2020", end="June 14, 2028"),
      rr=dict(tenant="Bright Path Dental Group, P.C.", rent="$8,900.00",
              start="06/15/2020", end="06/14/2028"),
      expect=[dict(field="rent_amount", material=True,
                   cause="Escalation drift: 3%/yr since 2020 has stepped rent to $9,724; "
                         "PM system still shows the original $8,900.")]),

    U("103", "A",
      lease=dict(tenant="Golden State Nails & Spa, LLC", rent="$4,300.00",
                 start="January 1, 2022", end="December 31, 2026"),
      rr=dict(tenant="Golden State Nails & Spa, LLC", rent="$4,300.00",
              start="01/01/2022", end="12/31/2026")),  # clean

    U("104", "A",
      lease=dict(tenant="Sunrise Bagel Company, LLC", rent="$5,568.00",
                 start="September 1, 2021", end="August 31, 2027"),
      rr=dict(tenant="Sunrise Bagel Co.", rent="$5,568.00",
              start="09/01/2021", end="08/31/2027"),
      expect=[dict(field="tenant", material=False,
                   cause="Name form: rent roll carries the trade name 'Sunrise Bagel Co.', "
                         "lease is signed 'Sunrise Bagel Company, LLC'.")],
      note="DBA vs legal entity -- engine flags any normalized name difference; a human triages."),

    U("105", "A",
      lease=dict(tenant="The Corner Bookshop, LLC", rent="$3,900.00",
                 start="May 1, 2023", end="April 30, 2028"),
      rr=dict(tenant="The Corner Bookshop, LLC", rent="$3,904.00",
              start="05/01/2023", end="04/30/2028"),
      note="CONTROL: $4/mo difference -- inside the $5 abs / 1% pct tolerance, must NOT flag."),

    U("106", "A",
      lease=dict(tenant="Pacific Tide Surf Shop, Inc.", rent="$4,120.00",
                 start="February 1, 2022", end="January 31, 2030"),
      rr=dict(tenant="Pacific Tide Surf Shop, Inc.", rent="$4,120.00",
              start="02/01/2022", end="01/31/2027"),
      expect=[dict(field="lease_end_date", material=True,
                   cause="Lease extended to 2030 by a 2024 amendment; rent roll still shows "
                         "the original 2027 expiration.")]),

    U("107", "A",
      lease=dict(tenant="Verde Juice Bar, LLC", rent="$3,600.00",
                 start="August 1, 2024", end="July 31, 2029"),
      rr=dict(tenant="Verde Juice Bar, LLC", rent="$3,600.00",
              start="08/01/2024", end="07/31/2029")),  # clean

    U("108", "A",
      lease=dict(tenant="Harbor Cleaners & Tailoring, LLC", rent="$2,850.00",
                 start="April 1, 2021", end="March 31, 2026"),
      rr=dict(tenant="Harbor Cleaners & Tailoring, LLC", rent="",
              start="04/01/2021", end="03/31/2026"),
      note="CONTROL: rent blank on the rent roll side -- not comparable, must NOT flag."),

    U("109", "A",
      lease=dict(tenant="Old Town Barbers, LLC", rent="$2,400.00",
                 start="July 1, 2022", end="June 30, 2027"),
      rr=dict(tenant="Old Town Barbers, LLC", rent="$2,400.00",
              start="07/01/2022", end="06/30/2027")),  # clean

    U("110", "A",
      lease=dict(tenant="Meridian Fitness Studio, LLC", rent="$8,100.00",
                 start="January 1, 2024", end="December 31, 2031"),
      rr=dict(tenant="Meridian Fitness Studio, LLC", rent="$7,500.00",
              start="01/01/2024", end="12/31/2029"),
      expect=[dict(field="rent_amount", material=True,
                   cause="Escalation drift: two annual 4% steps taken; PM system shows Year-1 rent."),
              dict(field="lease_end_date", material=True,
                   cause="Lease extended to 2031 by amendment; rent roll shows the original 2029 date.")],
      note="Multi-issue unit: stale rent AND stale expiration on the same lease."),

    U("111", "A",
      lease=dict(tenant="Loomis & Park Stationers, LLC", rent="$3,180.00",
                 start="October 1, 2020", end="September 30, 2028"),
      rr=dict(tenant="Loomis & Park Stationers, LLC", rent="$3,000.00",
              start="10/01/2020", end="09/30/2028"),
      expect=[dict(field="rent_amount", material=True,
                   cause="Escalation drift: annual CPI steps since 2020; PM system not updated.")]),

    U("112", "A",
      lease=dict(tenant="Cascade Pet Supply, LLC", rent="$4,750.00",
                 start="March 15, 2023", end="March 14, 2028"),
      rr=dict(tenant="Cascade Pet Supply, LLC", rent="$4,750.00",
              start="03/15/2023", end="03/14/2028")),  # clean

    # ---- Building B : office, 11 units -----------------------------------
    U("200", "B",
      lease=dict(tenant="Northbridge Analytics, Inc.", rent="$23,600.00",
                 start="July 1, 2022", end="June 30, 2027"),
      rr=dict(tenant="Northbridge Analytics, Inc.", rent="$22,000.00",
              start="07/01/2022", end="06/30/2027"),
      expect=[dict(field="rent_amount", material=True,
                   cause="Escalation drift: 2.5%/yr since 2022; PM system shows original rent.")]),

    U("210", "B",
      lease=dict(tenant="Cobalt Design Partners, LLC", rent="$14,200.00",
                 start="February 1, 2023", end="January 31, 2028"),
      rr=dict(tenant="Cobalt Design Partners, LLC", rent="$13,100.00",
              start="02/01/2023", end="01/31/2028"),
      expect=[dict(field="rent_amount", material=True, engine_will_miss=True,
                   cause="Real escalation-drift rent gap -- BUT the address is 'Ste. 210' on the "
                         "lease and 'Suite 210' on the rent roll, which the engine's exact "
                         "normalized-address match does not reconcile, so this pair is never "
                         "compared.")],
      lease_suite_override="Ste. 210",
      note="LIMITATION CASE: suite formatting differs between the two sources; engine cannot match."),

    U("215", "B",
      lease=dict(tenant="Cedarline Legal Services, LLP", rent="$18,900.00",
                 start="April 1, 2021", end="March 31, 2029"),
      rr=dict(tenant="Cedarline Legal Services, LLP", rent="$18,900.00",
              start="04/01/2021", end="03/31/2029")),  # clean

    U("220", "B",
      lease=dict(tenant="Hallmark Wealth Advisors, LLC", rent="$11,400.00",
                 start="September 1, 2020", end="August 31, 2027"),
      rr=dict(tenant="Hallmark Wealth Advisors, LLC", rent="$11,400.00",
              start="09/01/2020", end="08/31/2026"),
      expect=[dict(field="lease_end_date", material=True,
                   cause="Lease renewed for a further year (amendment); rent roll shows the "
                         "pre-renewal 2026 expiration.")]),

    U("225", "B",
      lease=dict(tenant="Trellis HR Consulting, Inc.", rent="$7,800.00",
                 start="June 1, 2023", end="May 31, 2028"),
      rr=dict(tenant="Trellis HR Consulting, Inc.", rent="$7,800.00",
              start="06/01/2023", end="05/31/2028")),  # clean

    U("230", "B",
      lease=dict(tenant="Vantage Point Architecture, LLC", rent="$16,750.00",
                 start="November 1, 2019", end="October 31, 2029"),
      rr=dict(tenant="Vantage Point Architecture, LLC", rent="$15,000.00",
              start="11/01/2019", end="10/31/2029"),
      expect=[dict(field="rent_amount", material=True,
                   cause="Post-renewal reset: 2024 renewal option exercised at 95% of FMV "
                         "($16,750); rent roll still shows the expiring-term $15,000.")]),

    U("235", "B",
      lease=dict(tenant="Kestrel Biotech, Inc.", rent="$21,300.00",
                 start="January 1, 2022", end="December 31, 2028"),
      rr=dict(tenant="Kestrel Biotech, Inc.", rent="$21,300.00",
              start="01/01/2022", end="12/31/2028")),  # clean

    U("240", "B",
      lease=dict(tenant="Summit Ridge Ventures, LLC", rent="$9,600.00",
                 start="March 1, 2023", end="February 28, 2028"),
      rr=dict(tenant="Summit Ridge Ventures, LLC", rent="$9,600.00",
              start="03/01/2023", end="02/28/2028"),
      note="CONTROL: same end date on both sides, written legal-style on the lease "
           "('February 28, 2028') and MM/DD/YYYY on the rent roll ('02/28/2028') -- "
           "format difference only, must NOT flag."),

    U("245", "B",
      lease=dict(tenant="Alder & Finch Accountancy Corporation", rent="$8,250.00",
                 start="August 1, 2021", end="July 31, 2026"),
      rr=dict(tenant="Alder & Finch", rent="$8,250.00",
              start="08/01/2021", end="07/31/2026"),
      expect=[dict(field="tenant", material=False,
                   cause="Name form: rent roll shows 'Alder & Finch', lease is 'Alder & Finch "
                         "Accountancy Corporation'.")]),

    U("250", "B",
      lease=dict(tenant="Brightwater Media Group, LLC", rent="$12,000.00",
                 start="October 1, 2022", end="September 30, 2027"),
      rr=dict(tenant="Brightwater Media Group, LLC", rent="$12,000.00",
              start="10/01/2022", end="09/30/2027")),  # clean

    U("255", "B",
      lease=dict(tenant="Quill & Co. Public Relations, LLC", rent="$6,900.00",
                 start="May 1, 2024", end="April 30, 2029"),
      rr=dict(tenant="Quill & Co. Public Relations, LLC", rent="$6,900.00",
              start="05/01/2024", end="04/30/2029")),  # clean

    # ---- Building C : flex / light industrial, 8 units -------------------
    U("C-1", "C",
      lease=dict(tenant="Ironwood Fabrication, Inc.", rent="$13,400.00",
                 start="January 1, 2021", end="December 31, 2027"),
      rr=dict(tenant="Ironwood Fabrication, Inc.", rent="$13,400.00",
              start="01/01/2021", end="12/31/2027")),  # clean

    U("C-2", "C",
      lease=dict(tenant="Delta Logistics Solutions, LLC", rent="$18,000.00",
                 start="June 1, 2022", end="May 31, 2029"),
      rr=dict(tenant="Delta Logistics Solutions, LLC", rent="$16,700.00",
              start="06/01/2022", end="05/31/2029"),
      expect=[dict(field="rent_amount", material=True,
                   cause="Escalation drift: annual 3.75% steps; PM system shows original rent.")]),

    U("C-3", "C",
      lease=dict(tenant="Copperline Electric Supply, LLC", rent="$9,250.00",
                 start="March 1, 2023", end="February 28, 2028"),
      rr=dict(tenant="Copperline Electric Supply, LLC", rent="$9,250.00",
              start="03/01/2023", end="02/28/2028")),  # clean

    U("C-4", "C",
      lease=dict(tenant="Harbor Freight Restoration, LLC", rent="$7,300.00",
                 start="September 1, 2020", end="August 31, 2026"),
      rr=dict(tenant="Harbor Freight Restoration, LLC", rent="$7,300.00",
              start="09/01/2020", end="08/31/2027"),
      expect=[dict(field="lease_end_date", material=True,
                   cause="Rent roll expiration keyed as 2027; lease says 2026 (data-entry error "
                         "-- overstates remaining term).")]),

    U("C-5", "C",
      lease=dict(tenant="Pinnacle Powdercoating, Inc.", rent="$8,800.00",
                 start="November 1, 2021", end="October 31, 2028"),
      rr=dict(tenant="Pinnacle Powdercoating, Inc.", rent="$8,800.00",
              start="11/01/2021", end="10/31/2028")),  # clean

    U("C-6", "C",
      lease=dict(tenant="Redwood Cold Storage, LLC", rent="$15,600.00",
                 start="February 1, 2022", end="January 31, 2032"),
      rr=dict(tenant="Redwood Cold Storage Partners, LLC", rent="$15,600.00",
              start="02/01/2022", end="01/31/2032"),
      expect=[dict(field="tenant", material=True,
                   cause="Tenant of record: lease was assigned to 'Redwood Cold Storage "
                         "Partners, LLC' (assignment on file with PM); the lease document on "
                         "hand is the original, pre-assignment entity.")]),

    U("C-7", "C",
      lease=dict(tenant="Alloy Works Manufacturing, LLC", rent="$11,000.00",
                 start="July 1, 2023", end="June 30, 2028"),
      rr=dict(tenant="Alloy Works Manufacturing, LLC", rent="$11,000.00",
              start="07/01/2023", end="06/30/2028")),  # clean

    U("C-8", "C",
      lease=dict(tenant="Summit Crane & Rigging, Inc.", rent="$12,750.00",
                 start="April 1, 2021", end="March 31, 2029"),
      rr=dict(tenant="Summit Crane & Rigging, Inc.", rent="$12,000.00",
              start="04/01/2021", end="03/31/2029"),
      expect=[dict(field="rent_amount", material=True,
                   cause="Escalation drift: fixed $250/yr steps in the lease; PM system not updated.")]),
]


def _pdf_fields(tenant, address, rent, start, end):
    def f(v):
        return {"value": v or None,
                "source": {"page": 1, "quote": str(v)} if v else None,
                "confidence": "high" if v else None}
    fields = {name: f(None) for name in FIELD_NAMES}
    fields.update(tenant=f(tenant), property_address=f(address), rent_amount=f(rent),
                  lease_start_date=f(start), lease_end_date=f(end))
    return fields


def _lease_address(u):
    suite = u.get("lease_suite_override") or f"Suite {u['unit']}"
    return f"{BUILDINGS[u['building']]}, {suite}"


def _build_rent_roll_csv(building_key):
    rows = [
        ["SYNTHETIC BENCHMARK FIXTURE -- fabricated, not a real export"],
        ["Property: " + BUILDINGS[building_key]],
        [],
        ["Unit", "Tenant", "Lease From", "Lease To", "Monthly Rent"],
    ]
    for u in PORTFOLIO:
        if u["building"] != building_key:
            continue
        rr = u["rr"]
        rows.append([f"Suite {u['unit']}", rr["tenant"], rr["start"], rr["end"], rr["rent"]])
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def _authed_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=1, email="benchmark@example.com", name="Benchmark", role="analyst")
    return client


def _norm(s):
    import re
    if not s:
        return None
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s.lower())).strip() or None


def run():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    try:
        client = _authed_client()

        # 1. Import the rent roll, one upload per building (the real route).
        for bkey in BUILDINGS:
            resp = client.post(
                "/leases/import-rent-roll",
                data={"file": (io.BytesIO(_build_rent_roll_csv(bkey)), f"rent_roll_{bkey}.csv"),
                      "property_address": BUILDINGS[bkey]},
                content_type="multipart/form-data",
            )
            assert resp.status_code in (200, 201), (bkey, resp.status_code, resp.get_data(as_text=True))

        # 2. Insert the lease-document side (ordinary .pdf records).
        for u in PORTFOLIO:
            L = u["lease"]
            database.insert_lease(
                f"lease_{u['building']}_{u['unit']}.pdf".replace(" ", "_"),
                _pdf_fields(L["tenant"], _lease_address(u), L["rent"], L["start"], L["end"]),
            )

        # 3. Run the real reconciliation route.
        data = client.get("/portfolio/rent-roll-reconciliation").get_json()

    finally:
        os.unlink(tmp.name)

    # ---- Grade -----------------------------------------------------------
    # Map each flagged mismatch back to a unit by normalized address.
    addr_to_unit = {_norm(_lease_address(u)): u for u in PORTFOLIO}
    flagged = {}  # (unit_key, field) -> mismatch dict
    unmapped = []
    for m in data["mismatches"]:
        u = addr_to_unit.get(_norm(m["address"]))
        if u is None:
            unmapped.append(m)
            continue
        flagged[(u["unit"], m["field"])] = m

    expected = {}  # (unit_key, field) -> expect dict
    for u in PORTFOLIO:
        for e in u["expect"]:
            expected[(u["unit"], e["field"])] = {**e, "unit": u["unit"], "building": u["building"]}

    expected_keys = set(expected)
    flagged_keys = set(flagged)

    true_pos = sorted(expected_keys & flagged_keys)
    missed = sorted(k for k in expected_keys - flagged_keys)
    false_pos = sorted(flagged_keys - expected_keys)

    material_expected = {k for k, v in expected.items() if v.get("material")}
    material_caught = material_expected & flagged_keys
    material_missed = material_expected - flagged_keys

    units_total = len(PORTFOLIO)
    units_with_expected_flag = len({k[0] for k in expected_keys})
    units_flagged = len({k[0] for k in flagged_keys})

    lines = []
    P = lines.append
    P("# Lease-vs-rent-roll reconciliation benchmark")
    P("")
    P("**Constructed test portfolio.** Both the lease-document side and the rent-roll")
    P("side of every unit were authored for this benchmark; the discrepancies are")
    P("modelled on documented PM-system drift patterns. This measures what the")
    P("engine flags and what it correctly leaves alone -- not field performance on")
    P("a real deal. See this script's module docstring.")
    P("")
    P("## Portfolio")
    P("")
    P(f"- **{units_total} units** across {len(BUILDINGS)} buildings")
    P(f"- Rent roll rows imported: **{data['rent_roll_lease_count']}**")
    P(f"- Lease documents on file: **{data['lease_document_count']}**")
    P(f"- Unit pairs the engine could match and compare: **{data['compared_pair_count']}**")
    P(f"  (of {units_total} units; {units_total - data['compared_pair_count']} not compared -- "
      f"see limitations below)")
    P("")
    P("## Headline result")
    P("")
    P(f"- Discrepancies flagged by the engine: **{len(flagged_keys)}**"
      f" across **{units_flagged}** units")
    P(f"- Ground-truth discrepancies in the portfolio: **{len(expected_keys)}**"
      f" across **{units_with_expected_flag}** units")
    P(f"- Correctly flagged: **{len(true_pos)}** / {len(expected_keys)}")
    P(f"- Material discrepancies (rent gap, wrong expiration, wrong tenant of record) "
      f"caught: **{len(material_caught)}** / {len(material_expected)}")
    P(f"- Missed: **{len(missed)}**")
    P(f"- False positives (flagged where truth says agree): **{len(false_pos)}**")
    if unmapped:
        P(f"- Flagged rows that did not map back to a benchmark unit: {len(unmapped)}")
    P("")
    P("## Correctly flagged")
    P("")
    for k in true_pos:
        e = expected[k]
        m = flagged[k]
        tag = "material" if e.get("material") else "name-form"
        P(f"- **Unit {k[0]}** ({e['building']}) - `{k[1]}` [{tag}]: "
          f"rent roll `{m['rent_roll_value']}` vs lease `{m['lease_document_value']}`")
        P(f"  - {e['cause']}")
    P("")
    P("## Missed (ground truth said flag, engine did not)")
    P("")
    if not missed:
        P("_None._")
    for k in missed:
        e = expected[k]
        P(f"- **Unit {k[0]}** ({e['building']}) - `{k[1]}`: {e['cause']}")
    P("")
    P("## False positives")
    P("")
    if not false_pos:
        P("_None. Every control unit (sub-tolerance rounding, blank fields) was correctly left unflagged._")
    for k in false_pos:
        m = flagged[k]
        P(f"- **Unit {k[0]}** - `{k[1]}`: rent roll `{m['rent_roll_value']}` vs lease `{m['lease_document_value']}`")
    P("")
    P("## Controls (must not flag)")
    P("")
    for u in PORTFOLIO:
        if u["note"].startswith("CONTROL"):
            hit = any(kk[0] == u["unit"] for kk in flagged_keys)
            P(f"- Unit {u['unit']}: {u['note'][9:].strip()} -> "
              f"{'FLAGGED (unexpected)' if hit else 'correctly not flagged'}")
    P("")
    P("## Known limitations exercised here")
    P("")
    P("- **Exact-address matching only.** Unit 210 (Building B) has a real rent")
    P("  discrepancy, but the lease says `Ste. 210` and the rent roll says")
    P("  `Suite 210`. The engine normalizes case and punctuation but does not")
    P("  expand abbreviations, so the two never match and the unit is never")
    P("  compared. Counted as a miss above.")
    P("- **Three fields only.** tenant, rent_amount, lease_end_date. A drifted")
    P("  security deposit, CAM, or lease *start* date is not checked by the")
    P("  arithmetic engine.")
    P("- **Any tenant-name difference flags.** DBA-vs-legal-entity name forms")
    P("  (units 104, 245) are flagged the same as a genuinely wrong tenant of")
    P("  record (unit C-6). The engine surfaces the difference; a human decides")
    P("  which kind it is.")
    P("")
    P("## Reproduce")
    P("")
    P("```")
    P("cd backend && python3 tools/reconciliation_benchmark/run_benchmark.py")
    P("```")
    P("Runs against a throwaway temp database through the real import +")
    P("reconciliation routes. Deterministic -- no AI, no network.")

    report = "\n".join(lines)
    return report, dict(
        units_total=units_total, compared=data["compared_pair_count"],
        flagged=len(flagged_keys), flagged_units=units_flagged,
        expected=len(expected_keys), expected_units=units_with_expected_flag,
        true_pos=len(true_pos), missed=len(missed), false_pos=len(false_pos),
        material_expected=len(material_expected), material_caught=len(material_caught),
        material_missed=sorted(material_missed),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="report.md")
    args = ap.parse_args()
    report, summary = run()
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
    with open(out_path, "w") as f:
        f.write(report + "\n")
    print(report)
    print("\n---\nmachine summary:", summary)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
