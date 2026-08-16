"""
Risk and anomaly detection over an already-extracted lease.

Extraction answers "what does this lease say"; this module answers "what
about that should worry you" — below-market rent versus the rest of the
portfolio, missing standard protections, outlier notice periods,
one-sided terms, and internal contradictions inside a single document.

Every check is a stated rule with a stated threshold rather than a
learned score, for the same reason the Q&A engine is deterministic: a
flag on a lease has to justify itself to a human reviewer. A rule can
say "rent is 28% below the portfolio average of $5,850/mo" and be
checked; a model score can only be believed. Each flag therefore carries
both a one-line `message` and an `explanation` that cites the actual
numbers the rule fired on.

Inputs are the extractor's display strings (parsed via `normalize.py`)
and an optional portfolio context of cross-lease averages. Anything
missing or unparseable means the affected check is skipped — a lease
with no square footage simply doesn't get a per-square-foot comparison,
rather than getting a fabricated one or crashing the analysis.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from .normalize import (
    escalation_rate_consistency,
    parse_currency,
    parse_date,
    parse_days,
    parse_renewal_options,
    parse_square_footage,
    rent_per_sqft,
)


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Rent this far below the portfolio average is treated as a material
# anomaly rather than ordinary variation between spaces.
BELOW_MARKET_HIGH_PCT = 25.0
BELOW_MARKET_MEDIUM_PCT = 10.0

# A renewal notice window shorter than a month leaves no time to plan;
# one longer than ~9 months forces a decision far ahead of the market.
SHORT_NOTICE_DAYS = 30
LONG_NOTICE_DAYS = 270

# Deviation from the portfolio's typical notice period, as a fraction.
NOTICE_DEVIATION_PCT = 50.0

# A lease long enough that a flat rent for its whole term is unusual.
LONG_TERM_YEARS = 2.0

# Cure period beyond which the landlord's remedy is meaningfully delayed.
LONG_CURE_DAYS = 30

# Year-over-year escalation spread, in percentage points, above which the
# schedule stops looking like a single consistent formula.
ESCALATION_SPREAD_MEDIUM = 2.0
ESCALATION_SPREAD_HIGH = 5.0

# Clauses a standard commercial lease is expected to contain; their
# absence is itself a finding, not merely a blank field.
EXPECTED_CLAUSES = [
    (
        "insurance_requirements",
        "insurance requirements",
        "No insurance requirement clause found in this lease — standard "
        "commercial leases specify a minimum coverage amount the tenant "
        "must carry. Either the clause is absent (leaving liability "
        "exposure unallocated) or it was missed by extraction; both are "
        "worth checking against the document.",
    ),
    (
        "default_cure_period",
        "default / cure period",
        "No default or cure period clause found in this lease — standard "
        "commercial leases state how long a tenant has to cure a default "
        "after written notice before the landlord can act. Without it, "
        "the parties' remedies on default are undefined.",
    ),
    (
        "security_deposit",
        "security deposit",
        "No security deposit found in this lease — most commercial leases "
        "require one as protection against tenant default or damage. "
        "Confirm whether the deposit was genuinely waived or simply not "
        "captured by extraction.",
    ),
]


def analyze_lease_risks(
    lease_fields: Dict[str, Any],
    portfolio_context: Optional[Dict[str, Any]] = None,
    date_candidates: Optional[Dict[str, Any]] = None,
    cross_lease_flags: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Runs every risk check against one lease and returns the flags raised,
    highest severity first (checks within a severity tier keep the order
    they ran in, so related findings stay grouped).

    `portfolio_context` supplies cross-lease averages; checks that need a
    benchmark are skipped when it's absent or missing that specific key,
    since a comparison against nothing would be a guess. `date_candidates`
    supplies every start/end date found anywhere in the document (from
    `FieldExtractor.find_all_date_candidates`) and enables the
    cross-section conflict check; without it that one check is skipped.

    `cross_lease_flags` is pre-computed by portfolio.py's
    compute_cross_lease_mismatches() (it needs the whole portfolio's
    leases to find pairs, which this function -- given only one lease's
    fields -- has no way to do itself) and passed in already in the
    standard flag shape; this function just merges them in and sorts
    them alongside everything else rather than treating them as a
    separate category the caller has to display differently.

    Each flag: {"severity", "category", "field", "message", "explanation"}.
    """
    fields = lease_fields or {}
    flags: List[Dict[str, Any]] = []

    flags.extend(_check_below_market_rent(fields, portfolio_context))
    flags.extend(_check_missing_clauses(fields))
    flags.extend(_check_notice_period(fields, portfolio_context))
    flags.extend(_check_one_sided_terms(fields))
    flags.extend(_check_escalation_consistency(fields))
    flags.extend(_check_date_range(fields))
    flags.extend(_check_date_candidate_conflicts(date_candidates))
    flags.extend(cross_lease_flags or [])

    return sorted(flags, key=lambda flag: SEVERITY_ORDER.get(flag["severity"], 99))


def _check_below_market_rent(
    fields: Dict[str, Any], portfolio: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compares this lease's rent to the portfolio average, preferring a
    per-square-foot comparison whenever both this lease and the portfolio
    have square footage data — comparing raw monthly rent across spaces
    of different sizes mostly measures size, not price.
    """
    if not portfolio:
        return []

    avg_psf = portfolio.get("avg_rent_per_sqft")
    lease_psf = rent_per_sqft(_value(fields, "rent_amount"), _value(fields, "square_footage"))
    if avg_psf and avg_psf > 0 and lease_psf is not None:
        return _below_market_flag(
            lease_psf, avg_psf,
            f"${lease_psf:,.2f}/sq ft/mo", f"${avg_psf:,.2f}/sq ft/mo",
            "rent per square foot",
        )

    avg_rent = portfolio.get("avg_rent")
    lease_rent = parse_currency(_value(fields, "rent_amount"))
    if avg_rent and avg_rent > 0 and lease_rent is not None:
        return _below_market_flag(
            lease_rent, avg_rent,
            f"{_money(lease_rent)}/mo", f"{_money(avg_rent)}/mo",
            "monthly rent",
        )

    return []


def _below_market_flag(
    lease_value: float, avg_value: float, lease_display: str, avg_display: str, basis: str
) -> List[Dict[str, Any]]:
    pct_below = ((avg_value - lease_value) / avg_value) * 100
    if pct_below >= BELOW_MARKET_HIGH_PCT:
        severity = "high"
    elif pct_below >= BELOW_MARKET_MEDIUM_PCT:
        severity = "medium"
    else:
        return []

    return [{
        "severity": severity,
        "category": "below_market_rent",
        "field": "rent_amount",
        "message": f"Rent ({lease_display}) is {pct_below:.0f}% below the portfolio average ({avg_display})",
        "explanation": (
            f"Comparing on {basis}, this lease is at {lease_display} against a "
            f"portfolio average of {avg_display} — {pct_below:.1f}% below. "
            "Below-market rent may mean the space is underpriced against the "
            "rest of the portfolio, or that a concession, different lease "
            "vintage, or misextracted figure is behind the gap; verify against "
            "the source quote before acting on it."
        ),
    }]


def _check_missing_clauses(fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flags standard commercial clauses that this lease does not contain."""
    flags = []
    for field_name, label, explanation in EXPECTED_CLAUSES:
        if _value(fields, field_name) is None:
            flags.append({
                "severity": "medium",
                "category": "missing_clause",
                "field": field_name,
                "message": f"No {label} clause found in this lease",
                "explanation": explanation,
            })
    return flags


def _check_notice_period(
    fields: Dict[str, Any], portfolio: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Checks the renewal notice window against both absolute bounds and, if
    available, the portfolio's typical notice period — a window that's
    reasonable in isolation can still be an outlier for this portfolio.
    """
    notice_days = parse_renewal_options(_value(fields, "renewal_options")).get("notice_days")
    if notice_days is None:
        return []

    flags = []
    if notice_days < SHORT_NOTICE_DAYS:
        flags.append({
            "severity": "medium",
            "category": "notice_period_outlier",
            "field": "renewal_options",
            "message": f"Renewal notice period of {notice_days} days is unusually short",
            "explanation": (
                f"This lease requires only {notice_days} days' notice to exercise a "
                f"renewal option (typical commercial leases require 90-180). That is "
                "unusually short — may not leave enough lead time to plan a renewal "
                "or re-lease the space if the tenant declines."
            ),
        })
    elif notice_days > LONG_NOTICE_DAYS:
        flags.append({
            "severity": "low",
            "category": "notice_period_outlier",
            "field": "renewal_options",
            "message": f"Renewal notice period of {notice_days} days is unusually long",
            "explanation": (
                f"This lease requires {notice_days} days' notice to exercise a renewal "
                f"option — over {notice_days // 30} months ahead of expiration. That is "
                "unusually long — favors the landlord with an early decision point, "
                "committing the tenant well before market conditions at renewal are known."
            ),
        })

    avg_notice = (portfolio or {}).get("avg_notice_days")
    if avg_notice and avg_notice > 0:
        deviation = (abs(notice_days - avg_notice) / avg_notice) * 100
        if deviation > NOTICE_DEVIATION_PCT:
            direction = "longer" if notice_days > avg_notice else "shorter"
            flags.append({
                "severity": "low",
                "category": "notice_period_outlier",
                "field": "renewal_options",
                "message": (
                    f"Renewal notice period ({notice_days} days) differs from the "
                    f"portfolio average ({avg_notice:.0f} days) by {deviation:.0f}%"
                ),
                "explanation": (
                    f"This lease's {notice_days}-day renewal notice window is "
                    f"{deviation:.0f}% {direction} than the portfolio average of "
                    f"{avg_notice:.0f} days. Inconsistent notice windows across a "
                    "portfolio make renewal deadlines easy to miss, since no single "
                    "lead time applies to every lease."
                ),
            })

    return flags


def _check_one_sided_terms(fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flags terms that sit noticeably in one party's favor: a long term with
    no rent escalation (tenant-favorable), and an unusually long cure
    period (tenant-favorable, delaying the landlord's remedy).
    """
    flags = []

    if _value(fields, "rent_escalation") is None:
        term_years = _term_years(fields)
        if term_years is not None and term_years > LONG_TERM_YEARS:
            flags.append({
                "severity": "medium",
                "category": "one_sided_terms",
                "field": "rent_escalation",
                "message": f"No rent escalation clause for a {_years(term_years)}-year lease term",
                "explanation": (
                    f"No rent escalation clause found for a {_years(term_years)}-year "
                    "lease term — unusual, and may favor the tenant with a static rate "
                    "over time, since the real value of a flat rent erodes across a "
                    "multi-year term. Confirm the lease genuinely has no escalation "
                    "rather than the clause being missed."
                ),
            })

    cure_days = parse_days(_value(fields, "default_cure_period"))
    if cure_days is not None and cure_days > LONG_CURE_DAYS:
        flags.append({
            "severity": "medium",
            "category": "one_sided_terms",
            "field": "default_cure_period",
            "message": f"Cure period of {cure_days} days is unusually long",
            "explanation": (
                f"Cure period of {cure_days} days is unusually long (commercial leases "
                f"typically allow 10-30), giving the tenant significant time to cure a "
                "default before the landlord can act — including on non-payment, where "
                "the landlord carries the shortfall for the whole window."
            ),
        })

    return flags


def _check_escalation_consistency(fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Checks a year-by-year escalation table against itself: a schedule
    generated from one stated formula should step up at a near-constant
    rate, so a wide spread means either the table or the stated formula
    is wrong.
    """
    consistency = escalation_rate_consistency(_value(fields, "rent_escalation"))
    if not consistency or consistency["spread"] <= ESCALATION_SPREAD_MEDIUM:
        return []

    spread = consistency["spread"]
    severity = "high" if spread > ESCALATION_SPREAD_HIGH else "medium"
    rates_display = ", ".join(f"{rate:.2f}%" for rate in consistency["rates"])

    return [{
        "severity": severity,
        "category": "escalation_inconsistency",
        "field": "rent_escalation",
        "message": (
            f"Escalation schedule increases are inconsistent: year-over-year rate "
            f"ranges from {consistency['min_rate']:.2f}% to {consistency['max_rate']:.2f}%"
        ),
        "explanation": (
            f"Year-over-year increases in the escalation schedule are "
            f"[{rates_display}] — a spread of {spread:.2f} percentage points between "
            f"the smallest ({consistency['min_rate']:.2f}%) and largest "
            f"({consistency['max_rate']:.2f}%). Verify this matches the lease's stated "
            "escalation formula; a consistent formula should produce near-identical "
            "year-over-year rates, so a spread this wide suggests a transcription "
            "error in the table or a step the formula doesn't describe."
        ),
    }]


def _check_date_range(fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flags a lease term that doesn't move forward in time."""
    start = parse_date(_value(fields, "lease_start_date"))
    end = parse_date(_value(fields, "lease_end_date"))
    if start is None or end is None or end > start:
        return []

    return [{
        "severity": "high",
        "category": "date_inconsistency",
        "field": "lease_end_date",
        "message": f"Lease end date ({_date(end)}) is not after the start date ({_date(start)})",
        "explanation": (
            f"Lease end date ({_date(end)}) is not after the start date "
            f"({_date(start)}) — one of these may be misextracted, or the lease terms "
            "conflict. Every downstream calculation that depends on the term "
            "(expiration timeline, term length, escalation schedule) is unreliable "
            "until this is resolved."
        ),
    }]


def _check_date_candidate_conflicts(
    date_candidates: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Compares every date the document states for the same role. The
    single-best-match extractors stop at their first hit, so a second,
    conflicting date stated elsewhere in the lease is invisible to them —
    this is the check that surfaces it.
    """
    if not date_candidates:
        return []

    flags = []
    for role, label in (("start", "start"), ("end", "end")):
        distinct = _distinct_candidate_dates(date_candidates.get(role))
        if len(distinct) < 2:
            continue

        listed = ", ".join(_date(parsed) for parsed, _ in distinct)
        located = "; ".join(
            f"{_date(parsed)} (page {_pages(sources)})" for parsed, sources in distinct
        )
        flags.append({
            "severity": "high",
            "category": "date_inconsistency",
            "field": f"lease_{role}_date",
            "message": f"Multiple different {label} dates appear in this document: {listed} — please verify which is correct",
            "explanation": (
                f"The document states more than one {label} date: {located}. The "
                f"extracted lease_{role}_date reflects only the first match found, so "
                "the others were not surfaced — review the cited pages to determine "
                "which date actually governs before relying on the extracted term."
            ),
        })

    return flags


def _distinct_candidate_dates(candidates: Optional[List[Dict[str, Any]]]):
    """
    Groups candidates by their parsed date, preserving first-appearance
    order and collecting every source that stated each date. Deduplicates
    on the parsed value, not the raw string, so "04/01/2025" and
    "April 1, 2025" are correctly treated as agreement, not conflict.
    Unparseable candidates are dropped rather than counted as a distinct
    date, since an unreadable string is no evidence of a conflict.
    """
    grouped: List = []
    index: Dict[date, int] = {}
    for candidate in candidates or []:
        parsed = parse_date((candidate or {}).get("value"))
        if parsed is None:
            continue
        if parsed not in index:
            index[parsed] = len(grouped)
            grouped.append((parsed, []))
        grouped[index[parsed]][1].append((candidate or {}).get("source"))
    return grouped


def _value(fields: Dict[str, Any], name: str) -> Optional[str]:
    """Reads a field's value, tolerating a missing key or a None field entry."""
    field = fields.get(name)
    if not isinstance(field, dict):
        return None
    return field.get("value")


def _term_years(fields: Dict[str, Any]) -> Optional[float]:
    """Lease term in years, or None if either endpoint is missing/unparseable."""
    start = parse_date(_value(fields, "lease_start_date"))
    end = parse_date(_value(fields, "lease_end_date"))
    if start is None or end is None or end <= start:
        return None
    return (end - start).days / 365.25


def _pages(sources: List[Optional[Dict[str, Any]]]) -> str:
    pages = []
    for source in sources:
        page = (source or {}).get("page")
        if page is not None and page not in pages:
            pages.append(page)
    return ", ".join(str(page) for page in pages) if pages else "unknown"


def _money(amount: float) -> str:
    """Whole dollars read cleaner in a one-line flag; cents shown only when they exist."""
    if amount == int(amount):
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def _years(years: float) -> str:
    rounded = round(years, 1)
    return str(int(rounded)) if rounded == int(rounded) else str(rounded)


def _date(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"
