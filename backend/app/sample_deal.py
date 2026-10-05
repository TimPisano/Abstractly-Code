"""
"Load sample deal" -- copies the fictional Maple Ridge demo deal
(15 real lease PDFs + a 16-unit rent roll, see
backend/benchmark_data/demo_deal/) into a single team's workspace, so a
brand-new team can see what the product does on day one without
uploading their own documents first.

The fixture (precomputed_sample_deal.json) is a static capture of what
the real /leases and /leases/import-rent-roll routes already produced
from these same files, via the non-AI regex/pdfplumber fallback engine
(this environment has no ANTHROPIC_API_KEY) -- see
backend/tests/test_demo_deal_golden.py, which validates that flow
against the deal's own planted expected_findings.json. Loading it here
is a direct database.insert_lease() per row, no extraction call of any
kind -- this is the whole point: a team can click this as often as they
like without ever touching the AI pipeline or a real API.
"""
import json
import os

from . import database

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "benchmark_data", "demo_deal", "precomputed_sample_deal.json")

_cached_fixture = None


def _load_fixture():
    global _cached_fixture
    if _cached_fixture is None:
        with open(_FIXTURE_PATH) as f:
            _cached_fixture = json.load(f)
    return _cached_fixture


def load_sample_deal(team_id: int) -> int:
    """
    Inserts every precomputed Maple Ridge row into `team_id`'s own
    workspace. Safe to call more than once -- each call inserts a fresh
    copy (same convention as a real re-upload), it doesn't check for or
    dedupe against a prior load; the route this backs is intended for a
    genuinely empty workspace, not idempotent syncing. Returns how many
    leases were created.
    """
    fixture = _load_fixture()
    for row in fixture:
        database.insert_lease(
            row["filename"],
            row["extracted_fields"],
            team_id,
            document_type=row["document_type"],
            date_candidates=row.get("date_candidates"),
            display_name=row.get("display_name"),
            source_page_start=row.get("source_page_start"),
            source_page_end=row.get("source_page_end"),
        )
    return len(fixture)
