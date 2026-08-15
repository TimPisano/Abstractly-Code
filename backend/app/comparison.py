"""
Lease-vs-lease comparison and single-lease-vs-portfolio benchmarking.

Two different questions, deliberately answered in two different formats:

`compare_leases` answers "how do these specific leases differ?" and keeps
the extractor's original display strings verbatim — no parsing, no
rounding, no normalization. A side-by-side review is exactly where a
human is checking the tool's work, so showing them anything other than
what was actually extracted (and what the source quote will corroborate)
would defeat the purpose.

`benchmark_lease` answers "is this lease unusual for our book?" and does
need real numbers, so it parses through `normalize.py` and reports a
signed percentage difference from the portfolio average.
"""

from typing import Any, Dict, List, Optional

from .normalize import parse_currency
from .portfolio import (
    FIELD_NAMES,
    compute_portfolio_metrics,
    escalation_pct,
    field_value,
)


# A lease within this percentage of the portfolio average is reported as
# ordinary rather than as an outlier. Wide enough that normal variation
# between comparable properties doesn't generate noise the user learns to
# ignore.
IN_LINE_TOLERANCE_PCT = 10.0

UNKNOWN_BENCHMARK = {
    "value": None,
    "portfolio_avg": None,
    "diff_pct": None,
    "assessment": "unknown",
}


def compare_leases(leases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Side-by-side view of 2+ leases, shaped for direct table rendering:
    one row per field, one column per lease, columns in the given order.

    Values are the extractor's display strings as-is, with None for
    fields that weren't found — rendering "not found" is the caller's
    presentation choice, and collapsing it to an empty string here would
    make a genuinely missing clause indistinguishable from a blank one.
    """
    if len(leases) < 2:
        raise ValueError("compare_leases requires at least 2 leases to compare")

    return {
        "lease_ids": [lease.get("id") for lease in leases],
        "filenames": [lease.get("filename") for lease in leases],
        "display_names": [lease.get("display_name") or lease.get("filename") for lease in leases],
        "fields": {
            name: [field_value(lease, name) for lease in leases]
            for name in FIELD_NAMES
        },
    }


def _benchmark(value: Optional[float], portfolio_avg: Optional[float]) -> Dict[str, Any]:
    """
    One benchmarked metric.

    Returns the "unknown" shape whenever either side of the comparison is
    missing, or when the average is zero (no meaningful percentage
    difference exists against a zero baseline). The key is always present
    with that shape rather than omitted, so callers can render a complete
    table without special-casing absence.
    """
    if value is None or not portfolio_avg:
        return dict(UNKNOWN_BENCHMARK)

    diff_pct = round(((value - portfolio_avg) / portfolio_avg) * 100, 1)

    if abs(diff_pct) <= IN_LINE_TOLERANCE_PCT:
        assessment = "in_line"
    elif diff_pct > 0:
        assessment = "above_average"
    else:
        assessment = "below_average"

    return {
        "value": value,
        "portfolio_avg": portfolio_avg,
        "diff_pct": diff_pct,
        "assessment": assessment,
    }


def benchmark_lease(
    lease: Dict[str, Any],
    portfolio_leases: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compares one lease's key economic terms against the portfolio average.

    Whether `portfolio_leases` includes this lease is the caller's call
    and is not corrected for here: benchmarking against the whole book
    (lease included) and against its peers (lease excluded) are both
    legitimate questions, and silently picking one would surprise the
    caller who wanted the other.

    Averages come from compute_portfolio_metrics so a benchmark and the
    portfolio dashboard can never quote different averages for the same
    book of leases.
    """
    metrics = compute_portfolio_metrics(portfolio_leases)

    return {
        "rent_amount": _benchmark(
            parse_currency(field_value(lease, "rent_amount")),
            metrics["avg_monthly_rent"],
        ),
        "cam_charges": _benchmark(
            parse_currency(field_value(lease, "cam_charges")),
            metrics["avg_cam"],
        ),
        "security_deposit": _benchmark(
            parse_currency(field_value(lease, "security_deposit")),
            metrics["avg_security_deposit"],
        ),
        "rent_escalation_pct": _benchmark(
            escalation_pct(field_value(lease, "rent_escalation")),
            metrics["avg_escalation_pct"],
        ),
    }
