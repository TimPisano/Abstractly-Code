"""
A minimal in-process cache for the genuinely expensive, repeatedly-hit
computations (portfolio trends, the health score) -- NOT a general-
purpose cache for every route. Most of this app's reads are already
cheap (a handful of SQLite rows, a pass over a small in-memory list);
caching those too would add complexity for no real benefit. Trends and
the health score are different: both walk the full lease history
(trends re-derives a timeline per building; the health score re-runs
confidence/verification/staleness tallies across every lease) on every
call, and a sidebar that lets someone switch tabs back and forth would
otherwise recompute the same answer from scratch each time.

A plain in-process dict is the right, least-invasive choice here --
this app has only ever run as a single Flask dev-server process (see
the pre-sale audit's "running on Flask's built-in development server,
not fit for production traffic" finding in PROGRESS.md), so there's no
multi-worker/multi-machine cache-consistency problem to solve for. If
that ever changes, this module is the one place that would need to
become a real shared cache (e.g. Redis) -- nothing above it would need
to change, since callers only see get_or_compute()/invalidate().

Two invalidation mechanisms, deliberately layered:
  1. Explicit invalidation at the exact mutation points that change
     the underlying data -- a lease upload/delete/amendment/rent-roll
     import, or a discrepancy resolve/reopen (see the call sites in
     api.py, each with a comment naming which cache prefix it clears
     and why).
  2. A short TTL as a safety net, so any mutation path that isn't
     explicitly wired to invalidate (or a direct DB write from a test)
     self-heals within a bounded time rather than serving stale data
     indefinitely.
"""
import time
from typing import Any, Callable, Dict, Tuple

_store: Dict[str, Tuple[float, Any]] = {}  # key -> (expires_at_monotonic, value)

DEFAULT_TTL_SECONDS = 60.0


def get_or_compute(key: str, compute_fn: Callable[[], Any], ttl_seconds: float = DEFAULT_TTL_SECONDS) -> Any:
    """Returns the cached value for `key` if present and not yet expired; otherwise calls compute_fn(), caches, and returns the fresh result."""
    now = time.monotonic()
    cached = _store.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]

    value = compute_fn()
    _store[key] = (now + ttl_seconds, value)
    return value


def invalidate(prefix: str) -> None:
    """Removes every cached entry whose key starts with `prefix` -- e.g. invalidate("trends") clears the portfolio-wide trends cache AND every individual property's cached trends in one call, since they all share that prefix."""
    for key in [k for k in _store if k.startswith(prefix)]:
        del _store[key]


def invalidate_all() -> None:
    """Used by tests to guarantee a clean cache between runs -- production code should prefer the targeted invalidate(prefix) above."""
    _store.clear()
