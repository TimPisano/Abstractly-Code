"""
Tests for tests/eval/affordable/ai_cache.py -- the eval's AI response cache.
NO real Claude calls: the call is replaced with a counting fake. Fictional
values only.

Run: python backend/tests/test_affordable_eval_cache.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'eval', 'affordable')))

import ai_cache  # noqa: E402
from app import ai_extraction  # noqa: E402
from app.affordable import ai_fields  # noqa: E402

PAGES = [{"page": 1, "text": "SECTION 8 HOUSING ASSISTANCE PAYMENTS CONTRACT\nContract Number: ZZ99E000001\n"
                             "Owner: Maple Ridge Housing LP."}]


def _install_fake():
    """A stand-in for the real API call that counts calls and answers with an owner name."""
    calls = []

    def fake(*, system, user_content, tool, **_):
        calls.append(tool["name"])
        payload = {"owner_name": {"value": "Maple Ridge Housing LP", "confidence": "high",
                                  "source_text": "Owner: Maple Ridge Housing LP."}}
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=payload)],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200), stop_reason="tool_use")

    ai_extraction.call_forced_tool = fake
    return calls


def _with_cache(fn):
    def run():
        original = ai_extraction.call_forced_tool
        try:
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
        finally:
            ai_extraction.call_forced_tool = original
        print(f"  ok  {fn.__name__}")
    run.__name__ = fn.__name__
    return run


@_with_cache
def test_second_identical_request_is_served_from_the_cache(cache_dir):
    calls = _install_fake()
    stats = ai_cache.install(cache_dir)
    first = ai_fields.extract_program_fields(PAGES, "hap_contract")
    second = ai_fields.extract_program_fields(PAGES, "hap_contract")
    assert calls == [ai_fields.TOOL_NAME], calls
    assert len(stats["misses"]) == 1 and len(stats["hits"]) == 1, stats
    assert first["program_fields"]["owner_name"]["value"] == second["program_fields"]["owner_name"]["value"] \
        == "Maple Ridge Housing LP"
    assert second["_ai_meta"]["input_tokens"] == 1000


@_with_cache
def test_changed_document_or_prompt_is_a_miss(cache_dir):
    calls = _install_fake()
    ai_cache.install(cache_dir)
    ai_fields.extract_program_fields(PAGES, "hap_contract")
    ai_fields.extract_program_fields([{**PAGES[0], "text": PAGES[0]["text"] + " Units: 12."}], "hap_contract")
    original_prompt = ai_fields.SYSTEM_PROMPT
    try:
        ai_fields.SYSTEM_PROMPT = original_prompt + "\n7. A new rule."
        ai_fields.extract_program_fields(PAGES, "hap_contract")
    finally:
        ai_fields.SYSTEM_PROMPT = original_prompt
    assert len(calls) == 3, calls


@_with_cache
def test_estimate_runs_never_store_their_stubbed_answers(cache_dir):
    _install_fake()
    ai_cache.install(cache_dir, write=False)
    ai_fields.extract_program_fields(PAGES, "hap_contract")
    assert list(cache_dir.glob("*.json")) == []


@_with_cache
def test_no_cache_sends_again_but_stores(cache_dir):
    calls = _install_fake()
    ai_cache.install(cache_dir, use_cache=False)
    ai_fields.extract_program_fields(PAGES, "hap_contract")
    ai_fields.extract_program_fields(PAGES, "hap_contract")
    assert len(calls) == 2, calls
    assert len(list(cache_dir.glob("*.json"))) == 1


@_with_cache
def test_offline_miss_fails_without_calling_out(cache_dir):
    calls = _install_fake()
    stats = ai_cache.install(cache_dir, offline=True)
    try:
        ai_fields.extract_program_fields(PAGES, "hap_contract")
    except ai_extraction.AIExtractionError:
        pass
    else:
        raise AssertionError("an uncached request in a cache-only run must fail")
    assert calls == [] and stats["misses"] == [], (calls, stats)


if __name__ == "__main__":
    test_second_identical_request_is_served_from_the_cache()
    test_changed_document_or_prompt_is_a_miss()
    test_estimate_runs_never_store_their_stubbed_answers()
    test_no_cache_sends_again_but_stores()
    test_offline_miss_fails_without_calling_out()
    print("\nAll eval AI cache tests passed.")
