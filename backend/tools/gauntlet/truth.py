"""
Ground truth for the overnight gauntlet: fictional multifamily properties,
their units, the leases behind them, and the planted discrepancies.

Everything here is FICTIONAL (names, streets, entities) and deterministic
(seeded). The generator (generate.py) renders each property into many
messy file formats; the manifest it writes stores the answers computed
here, which are derived from first principles -- what a correct
diligence product should report -- never from what the app currently
outputs.

As-of date: AS_OF. Leases are placed far from any date boundary so a run
a few weeks later grades the same.
"""
import random
from datetime import date, timedelta

AS_OF = date(2026, 10, 5)

FIRST = ["Avery", "Jordan", "Priya", "Mateo", "Hannah", "Desmond", "Lucia", "Theo", "Imani", "Rafael",
         "Noor", "Callum", "Sofia", "Malik", "Greta", "Tobias", "Ines", "Kenji", "Marisol", "Dante",
         "Odette", "Ezra", "Yara", "Bastian", "Celeste", "Hollis", "Wren", "Anika", "Lorenzo", "Maeve"]
LAST = ["Ashgrove", "Bellweather", "Castellano", "Drummond", "Everhart", "Fairbanks", "Galloway",
        "Holloway", "Ingram", "Juarez", "Kowalczyk", "Lindqvist", "Marchetti", "Nakamura", "Okafor",
        "Pemberton", "Quintero", "Rasmussen", "Sorensen", "Thibodeaux", "Underhill", "Valdivia",
        "Whitlock", "Xenakis", "Yarborough", "Zeller", "Abernathy", "Brightwater", "Calloway", "Dunmore"]
# Names a cp1252/latin-1 export mangles if decoded as UTF-8.
ACCENTED = ["José Peña", "Zoë Lefèvre", "Renée Côté", "Begoña Muñoz", "Søren Ågård", "François Delacroix"]

# (name, street, city, state, zip, suffix_long) -- fictional streets.
PROPERTIES = [
    ("Cedar Bend Flats", "1450 Cedar Bend Dr", "Austin", "TX", "78745", "Drive"),
    ("Juniper Court", "2210 Juniper Ct", "Phoenix", "AZ", "85016", "Court"),
    ("Harbor Lofts", "88 Wharfside Ave", "Tampa", "FL", "33602", "Avenue"),
    ("Sycamore Row", "731 Sycamore Row", "Charlotte", "NC", "28203", "Row"),
    ("Bluebonnet Commons", "4100 Bluebonnet Blvd", "San Antonio", "TX", "78216", "Boulevard"),
    ("Ridgeview Terrace", "915 Ridgeview Ter", "Atlanta", "GA", "30318", "Terrace"),
    ("Magnolia Place", "3302 Magnolia Pl", "Nashville", "TN", "37209", "Place"),
    ("Prairie Wind", "6120 Prairie Wind Rd", "Oklahoma City", "OK", "73132", "Road"),
    ("Copper Canyon", "1777 Copper Canyon Way", "Mesa", "AZ", "85201", "Way"),
    ("Linden Gardens", "245 Linden St", "Columbus", "OH", "43215", "Street"),
    ("Riverbirch", "5008 Riverbirch Ln", "Raleigh", "NC", "27606", "Lane"),
    ("Silverleaf", "1290 Silverleaf Pkwy", "Dallas", "TX", "75252", "Parkway"),
    ("Aspen Hollow", "402 Aspen Hollow Cir", "Denver", "CO", "80219", "Circle"),
    ("Tidewater", "77 Tidewater Dr", "Norfolk", "VA", "23510", "Drive"),
    # Cycle 3 (nastier): garden community, future residents, large file, odd encodings.
    ("Willow Creek Gardens", "3600 Willow Creek Rd", "Houston", "TX", "77064", "Road"),
    ("Brookstone Village", "880 Brookstone Pkwy", "Kansas City", "MO", "64151", "Parkway"),
    ("Highland Crossing", "2500 Highland Ave", "Birmingham", "AL", "35205", "Avenue"),
    ("Cobalt Flats", "19 Cobalt St", "Boise", "ID", "83702", "Street"),
    # Cycle 4 (AUDIT.md §6.11 golden cases): renewal chains, step-ups, first-month % off, name-prefixed addresses.
    ("Fox Run Apartments", "400 Fox Run Dr", "Lexington", "KY", "40509", "Drive"),
    # Cycle 6: one rent-roll file covering two properties (per-row Property column), T-24s, European locale.
    ("Lakeshore Commons", "1200 Lakeshore Blvd", "Madison", "WI", "53703", "Boulevard"),
    ("Pinecrest Villas", "75 Pinecrest Ln", "Spokane", "WA", "99201", "Lane"),
]

# Unit-id styles: function(building_idx, floor, n) -> canonical id
UNIT_STYLES = {
    "plain": lambda b, f, n: f"{f}{n:02d}",               # 101
    "bldg_dash": lambda b, f, n: f"{'ABC'[b]}-{f}{n:02d}",  # A-101
    "bldg_plain": lambda b, f, n: f"{'ABC'[b]}{f}{n:02d}",  # A101
    "four": lambda b, f, n: f"{b + 1}{f}{n:02d}",          # 1101
}

ISSUE_TYPES = [
    "rent_mismatch_over", "rent_mismatch_under", "expired_but_occupied", "unit_no_lease",
    "lease_no_unit", "concession_missing", "tenant_mismatch", "dates_mismatch",
]


def _month_add(d, months):
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    import calendar
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _end_for(start, months):
    return _month_add(start, months) - timedelta(days=1)


def term_months(start, end):
    return (end.year * 12 + end.month) - (start.year * 12 + start.month) + 1


def build_property(idx, cfg):
    """
    cfg keys:
      n_units, unit_style, issues (list of ISSUE_TYPES), vacant (int), down (int),
      s8 (int: # Section 8 units), reflected_concessions (int: concessions the RR shows correctly),
      name_order_traps (int: RR shows "Last, First" -- must NOT be a tenant mismatch),
      accented (int), co_tenants (int), lease_address_style ("suite_suffix"|"apt_inline"|"unit_inline"),
      typed_address_style ("same"|"long_suffix")
    """
    rng = random.Random(1000 + idx)
    name, street, city, st, zip_, suffix_long = PROPERTIES[idx]
    base = f"{street}, {city}, {st} {zip_}"
    prop = {
        "id": f"p{idx:02d}",
        "name": name,
        "street": street,
        "city": city, "state": st, "zip": zip_,
        "base_address": base,
        "typed_address": base,
        "lease_address_style": cfg.get("lease_address_style", "suite_suffix"),
        "units": [],
        "as_of": AS_OF.isoformat(),
    }
    if cfg.get("typed_address_style") == "long_suffix":
        # The uploader types "Drive" where the leases say "Dr" -- same building.
        abbrev = street.rsplit(" ", 1)
        prop["typed_address"] = f"{abbrev[0]} {suffix_long}, {city}, {st} {zip_}"

    style = UNIT_STYLES[cfg.get("unit_style", "plain")]
    n = cfg["n_units"]
    ids = []
    b = 0
    floor = 1
    k = 1
    per_floor = 4
    while len(ids) < n:
        ids.append(style(b, floor, k))
        k += 1
        if k > per_floor:
            k = 1
            floor += 1
            if floor > 3:
                floor = 1
                b += 1
    used_names = set()

    def person():
        while True:
            nm = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if nm not in used_names:
                used_names.add(nm)
                return nm

    units = []
    for uid in ids:
        beds = rng.choice([1, 1, 2, 2, 3])
        market = {1: 1150, 2: 1475, 3: 1825}[beds] + rng.choice([0, 25, 50, 75, 100])
        start = date(2026, rng.choice([1, 2, 3, 4, 5]), 1)
        end = _end_for(start, 12)
        rent = market - rng.choice([0, 25, 50])
        u = {
            "uid": uid, "beds": beds, "baths": 1 if beds == 1 else 2,
            "sqft": {1: 690, 2: 980, 3: 1240}[beds] + rng.choice([0, 15, 30]),
            "market_rent": float(market),
            "status": "occupied",
            "tenant": person(),
            "lease_rent": float(rent), "rr_rent": float(rent),
            "start": start.isoformat(), "end": end.isoformat(),
            "rr_start": start.isoformat(), "rr_end": end.isoformat(),
            "has_lease": True, "on_rent_roll": True,
            "concession": None, "rr_concession": 0.0, "rr_rent_shows_net": False,
            "s8": None, "issue": None, "trap": None,
        }
        u["rr_tenant"] = u["tenant"]
        units.append(u)

    pool = list(range(len(units)))
    rng.shuffle(pool)

    def take():
        return units[pool.pop()]

    for _ in range(cfg.get("vacant", 0)):
        u = take()
        u.update(status="vacant", tenant=None, rr_tenant=None, has_lease=False, lease_rent=None,
                 rr_rent=None, start=None, end=None, rr_start=None, rr_end=None)
    for _ in range(cfg.get("down", 0)):
        u = take()
        u.update(status="down", tenant=None, rr_tenant=None, has_lease=False, lease_rent=None,
                 rr_rent=None, start=None, end=None, rr_start=None, rr_end=None)

    for issue in cfg.get("issues", []):
        u = take()
        u["issue"] = issue
        if issue == "rent_mismatch_over":
            u["rr_rent"] = u["lease_rent"] + rng.choice([75, 100, 150, 225])
        elif issue == "rent_mismatch_under":
            u["rr_rent"] = u["lease_rent"] - rng.choice([60, 90, 120])
        elif issue == "expired_but_occupied":
            s = date(2025, 7, 1)
            e = _end_for(s, 12)  # 2026-06-30, well before AS_OF
            u.update(start=s.isoformat(), end=e.isoformat(), rr_start=s.isoformat(), rr_end=e.isoformat())
        elif issue == "unit_no_lease":
            u["has_lease"] = False
        elif issue == "lease_no_unit":
            u["on_rent_roll"] = False
        elif issue == "concession_missing":
            if rng.random() < 0.5:
                u["concession"] = {"kind": "free_month", "months": 1}
            else:
                u["concession"] = {"kind": "recurring", "amount": float(rng.choice([50, 75, 100])), "months": 6}
            u["rr_concession"] = 0.0
        elif issue == "tenant_mismatch":
            u["rr_tenant"] = person()
        elif issue == "dates_mismatch":
            # Stale renewal: rent roll still shows the old expiration.
            e = date.fromisoformat(u["end"])
            u["rr_end"] = _month_add(e + timedelta(days=1), -2).isoformat()
            u["rr_end"] = (date.fromisoformat(u["rr_end"]) - timedelta(days=1)).isoformat()

    for _ in range(cfg.get("reflected_concessions", 0)):
        u = take()
        amt = float(rng.choice([50, 75, 100]))
        # Full-term recurring discount, shown correctly in the RR concession column.
        u["concession"] = {"kind": "recurring", "amount": amt, "months": 12}
        u["rr_concession"] = amt
        u["trap"] = "reflected_concession"
    for _ in range(cfg.get("net_rent_concessions", 0)):
        u = take()
        amt = float(rng.choice([50, 75, 100]))
        u["concession"] = {"kind": "recurring", "amount": amt, "months": 12}
        u["rr_rent"] = u["lease_rent"] - amt  # RR shows the discounted rent -> reflected, no finding
        u["rr_rent_shows_net"] = True
        u["trap"] = "net_rent_concession"
    for _ in range(cfg.get("s8", 0)):
        u = take()
        hap = float(round(u["lease_rent"] * rng.choice([0.6, 0.7, 0.75]) / 5) * 5)
        u["s8"] = {"hap": hap, "tenant_portion": u["lease_rent"] - hap}
        u["trap"] = "section8"
    for _ in range(cfg.get("name_order_traps", 0)):
        u = take()
        first, last = u["tenant"].split(" ", 1)
        u["rr_tenant"] = f"{last.upper()}, {first.upper()}"
        u["trap"] = "last_first_name"
    for _ in range(cfg.get("co_tenants", 0)):
        u = take()
        other = person()
        u["tenant"] = f"{u['tenant']} and {other}"
        u["rr_tenant"] = u["tenant"].replace(" and ", " & ")
        u["trap"] = "co_tenant_ampersand"
    for i in range(cfg.get("accented", 0)):
        u = take()
        nm = ACCENTED[(idx + i) % len(ACCENTED)]
        u["tenant"] = nm
        u["rr_tenant"] = nm
        u["trap"] = "accented_name"

    for _ in range(cfg.get("future_residents", 0)):
        # A pre-leased applicant shown on a unit that is still occupied by
        # its current resident: the future lease is not current rent.
        u = next(x for x in units if x["status"] == "occupied" and x["issue"] is None and x["trap"] is None)
        u["future_resident"] = {"tenant": person(), "rent": u["rr_rent"] + 50.0, "start": "2026-11-01", "end": "2027-10-31"}
        u["trap"] = "future_resident"
    def clean_unit():
        return next(x for x in units if x["status"] == "occupied" and x["issue"] is None and x["trap"] is None and x["has_lease"])

    for _ in range(cfg.get("renewals", 0)):
        # The folder holds the expired original AND the current renewal;
        # the rent roll correctly shows the renewal. Must not be flagged.
        u = clean_unit()
        u["prior_lease"] = {"rent": u["lease_rent"] - 150.0, "start": "2025-01-01", "end": "2025-12-31"}
        u.update(start="2026-01-01", end="2026-12-31", rr_start="2026-01-01", rr_end="2026-12-31")
        u["trap"] = "renewal_chain"
    for _ in range(cfg.get("step_ups", 0)):
        # 2-year lease, scheduled step in year 2 (in effect on AS_OF); rent roll shows the stepped-up rent.
        u = clean_unit()
        base = u["lease_rent"]
        u["step_up"] = {"year1": base, "year2": base + 45.0}
        u.update(start="2025-06-01", end="2027-05-31", rr_start="2025-06-01", rr_end="2027-05-31", rr_rent=base + 45.0)
        u["trap"] = "step_up"
    for _ in range(cfg.get("pct_first_month", 0)):
        # "First month 50% off", rent roll shows gross rent and no concession -> concession_missing for ONE month.
        u = clean_unit()
        u["concession"] = {"kind": "pct_first_month", "percent": 50.0, "months": 1}
        u["issue"] = "concession_missing"
    keep = cfg.get("lease_only_for")
    if keep is not None:
        # Big file: only the issue units plus `keep` clean units have lease PDFs.
        clean = [u for u in units if u["status"] == "occupied" and u["issue"] is None and u["has_lease"]]
        for u in clean[keep:]:
            u["has_lease"] = False
    prop["units"] = units
    return prop


def lease_units(prop):
    return [u for u in prop["units"] if u["status"] == "occupied" and u["has_lease"]]


def rr_occupied(prop):
    return [u for u in prop["units"] if u["status"] == "occupied" and u["on_rent_roll"]]


def rr_units(prop):
    return [u for u in prop["units"] if u["on_rent_roll"]]


def concession_value(u):
    """(total concession $, term months) for a lease's concession, first principles."""
    c = u["concession"]
    if not c:
        return 0.0, None
    tm = term_months(date.fromisoformat(u["start"]), date.fromisoformat(u["end"]))
    if c["kind"] == "free_month":
        return u["lease_rent"] * c["months"], tm
    if c["kind"] == "pct_first_month":
        return u["lease_rent"] * c["percent"] / 100.0, tm
    return c["amount"] * c["months"], tm


def expected_findings(prop, carries):
    """
    What a correct Deal Mismatch Report says for this property, given a rent
    roll that carries the fields in `carries` (subset of {"start", "end", "concession"}).
    Returns list of {unit, type, annual, direction}.
    """
    out = []
    for u in prop["units"]:
        if u["status"] != "occupied":
            continue
        uid = u["uid"]
        if not u["on_rent_roll"]:
            if u["has_lease"]:
                out.append({"unit": uid, "type": "lease_no_unit", "annual": round(u["lease_rent"] * 12, 2), "direction": "understate"})
            continue
        if not u["has_lease"]:
            out.append({"unit": uid, "type": "unit_no_lease", "annual": round(u["rr_rent"] * 12, 2), "direction": None})
            continue
        end = date.fromisoformat(u["end"])
        if end < AS_OF:
            out.append({"unit": uid, "type": "expired_but_occupied", "annual": round(u["rr_rent"] * 12, 2), "direction": "overstate"})
            continue
        if u["issue"] in ("rent_mismatch_over", "rent_mismatch_under"):
            in_effect = u["step_up"]["year2"] if u.get("step_up") else u["lease_rent"]
            diff = u["rr_rent"] - in_effect
            out.append({"unit": uid, "type": "rent_mismatch", "annual": round(abs(diff) * 12, 2),
                        "direction": "overstate" if diff > 0 else "understate"})
        if u["issue"] == "concession_missing" or (u["trap"] == "reflected_concession" and "concession" not in carries):
            # A full-term discount the rent roll only shows in a concession
            # column: a format without that column shows gross rent and
            # nothing else, which genuinely overstates income.
            total, tm = concession_value(u)
            out.append({"unit": uid, "type": "concession_missing", "annual": round(total / tm * 12, 2), "direction": "overstate"})
        if u["issue"] == "tenant_mismatch":
            out.append({"unit": uid, "type": "tenant_mismatch", "annual": None, "direction": None})
        if u["issue"] == "dates_mismatch" and "end" in carries:
            out.append({"unit": uid, "type": "dates_mismatch", "annual": None, "direction": None})
    return out


def expected_rent_roll(prop, carries):
    occ = {}
    for u in rr_occupied(prop):
        row = {"tenant": u["rr_tenant"], "rent": u["rr_rent"]}
        if "start" in carries:
            row["start"] = u["rr_start"]
        if "end" in carries:
            row["end"] = u["rr_end"]
        if "concession" in carries:
            row["concession"] = u["rr_concession"]
        occ[u["uid"]] = row
    return {
        "occupied": occ,
        "vacant": [u["uid"] for u in rr_units(prop) if u["status"] == "vacant"],
        "down": [u["uid"] for u in rr_units(prop) if u["status"] == "down"],
        "total_units": len(rr_units(prop)),
    }


# One config per property. Sizes kept small (8-12 units) so a full cycle
# runs in minutes; the planted issue mix rotates so each detector is hit
# on several properties and several formats.
CONFIGS = [
    dict(n_units=10, unit_style="plain", issues=["rent_mismatch_over", "expired_but_occupied", "unit_no_lease", "concession_missing"], vacant=1, reflected_concessions=1),
    dict(n_units=9, unit_style="plain", issues=["rent_mismatch_under", "tenant_mismatch", "lease_no_unit"], vacant=1, down=1, name_order_traps=2),
    dict(n_units=10, unit_style="bldg_dash", issues=["rent_mismatch_over", "dates_mismatch", "concession_missing"], vacant=2, s8=2, lease_address_style="apt_inline"),
    dict(n_units=8, unit_style="plain", issues=["expired_but_occupied", "tenant_mismatch"], vacant=0, co_tenants=1, net_rent_concessions=1),
    dict(n_units=12, unit_style="four", issues=["rent_mismatch_over", "rent_mismatch_under", "unit_no_lease", "lease_no_unit"], vacant=2, accented=2),
    dict(n_units=10, unit_style="plain", issues=["concession_missing", "concession_missing", "dates_mismatch"], vacant=1, reflected_concessions=2, lease_address_style="unit_inline"),
    dict(n_units=9, unit_style="bldg_plain", issues=["rent_mismatch_over", "expired_but_occupied"], vacant=1, s8=3),
    dict(n_units=10, unit_style="plain", issues=["tenant_mismatch", "rent_mismatch_over", "lease_no_unit"], vacant=0, name_order_traps=3, typed_address_style="long_suffix"),
    dict(n_units=11, unit_style="plain", issues=["unit_no_lease", "concession_missing", "rent_mismatch_under"], vacant=2, down=1, accented=1),
    dict(n_units=8, unit_style="plain", issues=["rent_mismatch_over", "dates_mismatch"], vacant=0),
    dict(n_units=10, unit_style="bldg_dash", issues=["expired_but_occupied", "concession_missing", "tenant_mismatch"], vacant=1, net_rent_concessions=1, lease_address_style="apt_inline"),
    dict(n_units=12, unit_style="plain", issues=["rent_mismatch_over", "rent_mismatch_over", "unit_no_lease", "dates_mismatch"], vacant=3, s8=2),
    dict(n_units=9, unit_style="plain", issues=["lease_no_unit", "rent_mismatch_under"], vacant=1, co_tenants=1, reflected_concessions=1),
    dict(n_units=10, unit_style="four", issues=["rent_mismatch_over", "expired_but_occupied", "concession_missing"], vacant=0, name_order_traps=1),
]


# Cycle 3 configs (appended to CONFIGS below):
#  p14 garden community: rent roll "A-101", leases "Building A, Apartment 101"
#  p15 rent roll with FUTURE residents listed on occupied units (must not import)
#  p16 600-unit property, leases for 30 units only (performance + unit_no_lease volume)
#  p17 semicolon CSV / deep header / merged two-row header / Excel serial dates
CONFIGS += [
    dict(n_units=12, unit_style="bldg_dash", issues=["rent_mismatch_over", "expired_but_occupied", "tenant_mismatch"], vacant=1,
         lease_address_style="bldg_apt"),
    dict(n_units=10, unit_style="plain", issues=["rent_mismatch_under", "dates_mismatch"], vacant=1, future_residents=2),
    dict(n_units=600, unit_style="four", issues=["rent_mismatch_over", "rent_mismatch_under", "expired_but_occupied", "lease_no_unit"],
         vacant=30, down=6, lease_only_for=30),
    dict(n_units=10, unit_style="plain", issues=["rent_mismatch_over", "dates_mismatch", "unit_no_lease"], vacant=1, down=1),
]


CONFIGS += [
    dict(n_units=10, unit_style="plain", issues=["rent_mismatch_over", "expired_but_occupied"], vacant=1,
         renewals=3, step_ups=2, pct_first_month=1, lease_address_style="name_prefix"),
]


CONFIGS += [
    dict(n_units=8, unit_style="plain", issues=["rent_mismatch_over", "expired_but_occupied", "unit_no_lease"], vacant=1),
    dict(n_units=8, unit_style="plain", issues=["rent_mismatch_under", "tenant_mismatch", "lease_no_unit"], vacant=1),
]


def all_properties():
    return [build_property(i, cfg) for i, cfg in enumerate(CONFIGS)]
