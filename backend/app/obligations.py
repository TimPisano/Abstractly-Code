"""
Forward-looking obligations/deadlines computed from a lease's already-
extracted fields -- the "make sure you never miss a deadline" layer
this pass adds on top of (not instead of) the static field extraction
in field_extractor.py.

Computed live on every call, never persisted -- same reasoning as
alerts.py's underlying metrics (compute_expiration_alerts, compute_
loss_to_lease, ...): an obligation is fully derived from the lease's
own extracted fields, so a persisted snapshot would go stale the
moment a field is corrected, exactly like a cached risk flag would.

RELIABLE-FIRST, BY DESIGN (see the 2026-09 stress-test/obligations
pass writeup): every due_date this module returns is computed from
something the lease text ACTUALLY states -- a real start/end date, a
stated notice period, a stated escalation schedule. Where the
underlying commercial-lease concept is real but the lease is silent on
an actual calendar trigger (insurance certificate renewal timing, CAM
reconciliation timing, holdover, right of first refusal), this module
either reports the obligation as present with due_date=None and a
clear reason (insurance -- see compute_insurance_obligation), or omits
it entirely because there's no extracted signal to gate it on at all
(CAM reconciliation timing, holdover, ROFR -- no field_extractor
extraction exists for any of these yet; see this module's own
end-of-file note). A wrong deadline is worse than no deadline -- this
module never fabricates one to fill out a type list.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.normalize import (
    parse_date, parse_renewal_options, parse_termination_options,
    parse_escalation_schedule, parse_percent,
)
from app.portfolio import field_value


def _add_years(d: date, years: int) -> date:
    """d + N calendar years, landing on Feb 28 (not raising) for a Feb 29 start in a non-leap target year."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + years)


def _lease_identity(lease: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "lease_id": lease.get("id"),
        "tenant": field_value(lease, "tenant"),
        "property_address": field_value(lease, "property_address"),
    }


def _field_source(lease: Dict[str, Any], field_name: str) -> Optional[Dict[str, Any]]:
    entry = (lease.get("extracted_fields") or {}).get(field_name)
    return entry.get("source") if isinstance(entry, dict) else None


def _dated_entry(lease, obligation_type, description, due_date, reference_date, source_field, past_label="overdue") -> Dict[str, Any]:
    """
    `past_label` distinguishes a genuine missed DEADLINE (renewal/
    termination notice -- "overdue", someone needed to act and the
    window may be closing or gone) from a date that simply already
    happened with no action required of anyone (a rent escalation
    triggers automatically per the lease's own terms) -- caught via
    live-data verification against this dev environment's real leases,
    2026-09: a past escalation date was labeled "overdue" the same way
    a missed renewal deadline would be, which reads as "someone messed
    up" for something that was never an action item in the first place.
    """
    days_remaining = (due_date - reference_date).days
    return {
        **_lease_identity(lease),
        "obligation_type": obligation_type,
        "description": description,
        "due_date": due_date.isoformat(),
        "days_remaining": days_remaining,
        "status": past_label if days_remaining < 0 else "upcoming",
        "source": _field_source(lease, source_field),
    }


def compute_renewal_notice_deadline(lease: Dict[str, Any], reference_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """
    The deadline to give notice of intent to renew: lease_end_date minus
    the notice period stated in renewal_options. Same core arithmetic
    portfolio.compute_expiration_alerts already uses for its 90-day-
    window renewal_deadlines list (`deadline = end_date - timedelta(
    days=notice_days)`) -- factored out here so it's directly testable
    and not bounded to that dashboard widget's 90-day window.

    Returns None if lease_end_date is missing/unparseable, or if
    renewal_options doesn't state a notice period -- never a guessed
    default notice period.
    """
    reference_date = reference_date or date.today()
    end_date = parse_date(field_value(lease, "lease_end_date"))
    if end_date is None:
        return None
    notice_days = parse_renewal_options(field_value(lease, "renewal_options")).get("notice_days")
    if notice_days is None:
        return None

    due_date = end_date - timedelta(days=notice_days)
    entry = _dated_entry(
        lease, "renewal_notice_deadline",
        f"Deadline to give notice of intent to renew ({notice_days} days before the lease ends on {end_date.isoformat()})",
        due_date, reference_date, "renewal_options",
    )
    # Whether the option is CURRENTLY exercisable -- not a fabricated
    # "window open" date. Real leases essentially never state when a
    # renewal option starts being exercisable, only the notice-before-
    # expiration requirement, so this reports the one boundary the text
    # actually supports (today vs. the deadline), not an invented start.
    entry["currently_exercisable"] = reference_date <= due_date
    return entry


def compute_termination_notice_deadline(lease: Dict[str, Any], reference_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """
    The deadline to give notice of an early termination: lease_start_date
    plus the stated "years into the Term" the option becomes effective,
    minus the stated notice period -- same shape as the renewal deadline
    above, just anchored to the termination-effective date instead of
    lease end. Returns None unless BOTH the trigger year and the notice
    period are stated (see field_extractor._extract_termination_options)
    -- no default notice period is ever assumed.
    """
    reference_date = reference_date or date.today()
    start_date = parse_date(field_value(lease, "lease_start_date"))
    if start_date is None:
        return None
    parsed = parse_termination_options(field_value(lease, "termination_options"))
    years_into_term, notice_days = parsed.get("years_into_term"), parsed.get("notice_days")
    if years_into_term is None or notice_days is None:
        return None

    # "The last day of the Nth year of the Term" is the day BEFORE the
    # N-year anniversary, not the anniversary itself -- the 5th year of
    # a Term starting 2022-07-01 runs 2026-07-01 through 2027-06-30, so
    # its last day is 2027-06-30, not 2027-07-01. Caught by hand-
    # verifying this exact fixture's arithmetic independently before
    # trusting the code -- see the obligations-engine writeup.
    effective_date = _add_years(start_date, years_into_term) - timedelta(days=1)
    due_date = effective_date - timedelta(days=notice_days)
    return _dated_entry(
        lease, "termination_notice_deadline",
        f"Deadline to give notice of early termination ({notice_days} days before the option becomes effective on {effective_date.isoformat()})",
        due_date, reference_date, "termination_options",
    )


# Sanity bound on how many future escalation anniversaries a flat
# percentage clause can generate -- guards against an unreasonably
# distant or missing lease_end_date turning into an unbounded loop.
_MAX_ESCALATION_YEARS_AHEAD = 40


def compute_escalation_trigger_dates(lease: Dict[str, Any], reference_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Every future rent-escalation trigger date this lease's own data
    supports -- computed, not guessed, from lease_start_date's calendar
    anniversaries:
      - A year-by-year schedule ("Year 1: $X; Year 2: $Y; ..." --
        normalize.parse_escalation_schedule) triggers Year N's amount on
        the lease's (N-1)-year anniversary (Year 1 is the starting rent
        itself, not a future trigger).
      - A flat annual percentage ("3% annually"/"...anniversary...") --
        normalize.parse_percent, gated on the same "annual"/"anniversary"
        wording field_extractor._extract_rent_escalation already only
        attaches to a genuinely annual clause -- triggers every
        anniversary through lease_end_date (or a bounded horizon if
        lease_end_date is missing/unparseable).

    Returns [] (never a single guessed date) if lease_start_date is
    missing, or rent_escalation doesn't match either recognized shape.
    """
    reference_date = reference_date or date.today()
    start_date = parse_date(field_value(lease, "lease_start_date"))
    if start_date is None:
        return []
    escalation_text = field_value(lease, "rent_escalation")
    if not escalation_text:
        return []

    entries = []
    schedule = parse_escalation_schedule(escalation_text)
    if schedule:
        for year, amount in schedule:
            if year <= 1:
                continue  # Year 1 is the starting rent, not a future trigger
            trigger_date = _add_years(start_date, year - 1)
            entries.append(_dated_entry(
                lease, "rent_escalation",
                f"Rent increases to ${amount:,.2f}/mo (Year {year} of the schedule stated in the lease)",
                trigger_date, reference_date, "rent_escalation", past_label="already_in_effect",
            ))
        return entries

    pct = parse_percent(escalation_text)
    lowered = escalation_text.lower()
    if pct is not None and ("annual" in lowered or "anniversary" in lowered):
        end_date = parse_date(field_value(lease, "lease_end_date"))
        horizon = end_date or _add_years(reference_date, 5)
        for year_n in range(1, _MAX_ESCALATION_YEARS_AHEAD + 1):
            trigger_date = _add_years(start_date, year_n)
            if trigger_date > horizon:
                break
            entries.append(_dated_entry(
                lease, "rent_escalation",
                f"Rent increases {pct:g}% (annual escalation, anniversary of the {start_date.isoformat()} lease start)",
                trigger_date, reference_date, "rent_escalation", past_label="already_in_effect",
            ))
    return entries


def compute_insurance_obligation(lease: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Insurance is a REQUIREMENT stated in the lease (a coverage type and
    limit), not a calendar date -- a certificate of insurance is a
    real-world document renewed on its own schedule, which the lease's
    text never states. Reported as present-but-not-date-computable
    (due_date=None) rather than either fabricating a date or silently
    dropping a real, known obligation just because it has no due date.
    Returns None only if the lease has no insurance_requirements text
    at all (nothing to report).
    """
    text = field_value(lease, "insurance_requirements")
    if not text:
        return None
    return {
        **_lease_identity(lease),
        "obligation_type": "insurance_certificate",
        "description": f"Insurance coverage requirement on file ({text}) -- an ongoing requirement, not a fixed lease-stated date. Track the actual certificate-of-insurance expiration separately.",
        "due_date": None,
        "days_remaining": None,
        "status": "not_date_computable",
        "source": _field_source(lease, "insurance_requirements"),
    }


def compute_lease_obligations(lease: Dict[str, Any], reference_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """Every obligation this module can compute for ONE lease, flattened into one list."""
    reference_date = reference_date or date.today()
    entries = []
    renewal = compute_renewal_notice_deadline(lease, reference_date)
    if renewal:
        entries.append(renewal)
    termination = compute_termination_notice_deadline(lease, reference_date)
    if termination:
        entries.append(termination)
    entries.extend(compute_escalation_trigger_dates(lease, reference_date))
    insurance = compute_insurance_obligation(lease)
    if insurance:
        entries.append(insurance)
    return entries


def compute_portfolio_obligations(leases: List[Dict[str, Any]], reference_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Every obligation across the whole portfolio, in one prioritized
    list -- the "single prioritized task list" GET /portfolio/
    obligations exposes. Sorted soonest-due first; entries with no
    computable due_date (insurance) sort last, grouped there rather
    than interspersed at an arbitrary position.
    """
    reference_date = reference_date or date.today()
    all_entries = []
    for lease in leases:
        all_entries.extend(compute_lease_obligations(lease, reference_date))

    all_entries.sort(key=lambda e: (e["due_date"] is None, e["due_date"] or ""))
    return all_entries


# ----------------------------------------------------------------------
# Deliberately NOT implemented in this pass, and NOT represented as
# "always present, always null" placeholder entries above (that would
# be noise -- every lease would show a hollow row for a clause it may
# not even have): CAM/operating-expense reconciliation deadlines,
# holdover provisions, right of first refusal windows. None of these
# have ANY extraction today (no field_extractor method reads them at
# all, unlike insurance_requirements above, which at least has real
# text to gate an entry on) -- adding a fabricated "obligation type"
# with no underlying signal would be worse than not mentioning them.
# Real future work: add extraction for these (same pattern as
# _extract_termination_options), THEN wire a compute_* function here
# the same way, gated on that extraction actually finding something.
# ----------------------------------------------------------------------
