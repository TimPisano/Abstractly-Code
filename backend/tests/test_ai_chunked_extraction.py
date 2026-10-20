"""
Tests for chunked AI extraction (ai_extraction.plan_chunks /
merge_chunk_fields / extract_lease_fields_chunked). No real Claude calls:
the client is a fake "faithful reader" that only reports a term if the
text it was actually sent contains it, quoting that text verbatim -- so a
term on page 431 can only come back if page 431 reached the model.
"""
import os
import re
import sys
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from anthropic.types import ToolUseBlock  # noqa: E402

from create_large_fixtures import PLANTED_TERMS, TEXT_LEASE, ensure_large_fixtures, path_of  # noqa: E402
from app import ai_extraction  # noqa: E402
from app.document_extractor import extract_pages_from_path  # noqa: E402

_PAGES_CACHE = {}


def _fixture_pages():
    if "pages" not in _PAGES_CACHE:
        ensure_large_fixtures(only=[TEXT_LEASE])
        _PAGES_CACHE["pages"] = extract_pages_from_path(path_of(TEXT_LEASE), "pdf")
    return _PAGES_CACHE["pages"]


def _payload(**found):
    payload = {name: {"value": None, "confidence": None, "source_text": None} for name in ai_extraction.LEASE_FIELDS}
    for name, (value, confidence, quote) in found.items():
        payload[name] = {"value": value, "confidence": confidence, "source_text": quote}
    return payload


def _response(payload, input_tokens=1000, output_tokens=200):
    r = mock.Mock()
    r.content = [ToolUseBlock(id="toolu_x", input=payload, name="record_lease_abstraction", type="tool_use")]
    r.usage = mock.Mock(input_tokens=input_tokens, output_tokens=output_tokens)
    r.stop_reason = "tool_use"
    return r


# What the fake reader looks for, and the value it reports when it finds it.
_READER_RULES = {
    "tenant": (r"and (Northwind Outfitters, Inc\.)", "high"),
    "rent_amount": (r"Base Rent of (\$[\d,]+\.\d\d) per month", "high"),
    "security_deposit": (r"security deposit in the amount of (\$[\d,]+\.\d\d)", "high"),
    "square_footage": (r"approximately ([\d,]+) rentable square feet", "high"),
    "renewal_options": (r"(two \(2\) options to renew)", "medium"),
    "exclusivity_clause": (r"(selling outdoor apparel and camping equipment)", "medium"),
}


class FaithfulReader:
    """Fake messages API: reports a field only if its sentence is in the prompt it received."""

    def __init__(self):
        self.prompts = []
        self.messages = self

    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        self.prompts.append(prompt)
        flat = re.sub(r"\s+", " ", prompt)
        found = {}
        for field, (pattern, confidence) in _READER_RULES.items():
            m = re.search(pattern, flat)
            if m:
                sentence_start = flat.rfind(". ", 0, m.start()) + 2
                quote = flat[sentence_start:m.end()]
                found[field] = (m.group(1), confidence, quote)
        return _response(_payload(**found))


def _pages_sent(prompts):
    return [int(n) for p in prompts for n in re.findall(r"===== PAGE (\d+) =====", p)]


def test_plan_chunks_respects_both_caps_and_keeps_every_page_once():
    pages = _fixture_pages()
    chunks = ai_extraction.plan_chunks(pages)
    flat = [p["page"] for c in chunks for p in c]
    assert flat == list(range(1, 501)), "every page exactly once, in order"
    for chunk in chunks:
        assert len(chunk) <= ai_extraction.CHUNK_MAX_PAGES
        assert sum(len((p["text"] or "").strip()) + 24 for p in chunk) <= ai_extraction.CHUNK_MAX_CHARS
    # Greedy packing at page boundaries: at least ceil(chars / cap) chunks, at most one more.
    total_chars = sum(len((p["text"] or "").strip()) + 24 for p in pages)
    lower = -(-total_chars // ai_extraction.CHUNK_MAX_CHARS)
    assert lower <= len(chunks) <= lower + 1, (len(chunks), lower)

    # The page cap binds on short pages, too.
    tiny = [{"page": n, "text": "x"} for n in range(1, 251)]
    assert [len(c) for c in ai_extraction.plan_chunks(tiny)] == [100, 100, 50]
    # One page bigger than the char cap is its own chunk, never dropped.
    huge = [{"page": 1, "text": "a"}, {"page": 2, "text": "b" * 500_000}, {"page": 3, "text": "c"}]
    assert [[p["page"] for p in c] for c in ai_extraction.plan_chunks(huge)] == [[1], [2], [3]]
    print("✓ test_plan_chunks_respects_both_caps_and_keeps_every_page_once: PASS")


def test_500_page_lease_every_page_reaches_the_model_and_late_terms_come_back_cited():
    pages = _fixture_pages()

    # Before: the single-call path cuts the prompt off around page 71.
    old = FaithfulReader()
    old_fields = ai_extraction.extract_lease_fields(pages, client=old)
    assert max(_pages_sent(old.prompts)) < 100 and "DOCUMENT TRUNCATED" in old.prompts[0]
    assert old_fields["security_deposit"]["value"] is None, "the old path cannot see page 262"

    chunk_count = len(ai_extraction.plan_chunks(pages))
    reader = FaithfulReader()
    progress = []
    fields = ai_extraction.extract_lease_fields_chunked(pages, client=reader, progress=lambda d, t: progress.append((d, t)))

    assert sorted(_pages_sent(reader.prompts)) == list(range(1, 501)), "every page sent exactly once"
    assert not any("DOCUMENT TRUNCATED" in p for p in reader.prompts)
    assert len(reader.prompts) == chunk_count
    assert progress == [(n, chunk_count) for n in range(1, chunk_count + 1)]
    assert f"part 1 of {chunk_count}" in reader.prompts[0] and "pages 1-" in reader.prompts[0]

    assert fields["tenant"]["value"] == "Northwind Outfitters, Inc." and fields["tenant"]["source"]["page"] == 1
    assert fields["rent_amount"]["value"] == "$18,750.00"
    expected_pages = {name: page for page, (name, _) in PLANTED_TERMS.items()}
    assert fields["security_deposit"]["value"] == "$56,250.00"
    for name, page in expected_pages.items():
        assert fields[name]["value"], f"{name} not recovered"
        assert fields[name]["source"]["page"] == page, f"{name} cited page {fields[name]['source']['page']}, expected {page}"
        assert fields[name]["source"]["quote"], name

    meta = fields["_ai_meta"]
    assert meta["chunk_count"] == chunk_count
    assert meta["input_tokens"] == 1000 * chunk_count and meta["output_tokens"] == 200 * chunk_count
    assert meta["prompt_version"].endswith("-chunked")
    print("✓ test_500_page_lease_every_page_reaches_the_model_and_late_terms_come_back_cited: PASS")


def _entry(value, page, confidence="high", quote=None):
    return {"value": value, "source": {"page": page, "quote": quote or value}, "confidence": confidence,
            "source_text": quote or value, "engine": "ai"}


def _empty():
    return {name: {"value": None, "source": None, "confidence": None, "engine": "ai"} for name in ai_extraction.LEASE_FIELDS}


def test_conflicting_values_across_parts_are_flagged_not_silently_picked():
    a, b = _empty(), _empty()
    a["rent_amount"] = _entry("$18,750.00", 1)
    b["rent_amount"] = _entry("$21,000.00", 301, confidence="high")
    merged = ai_extraction.merge_chunk_fields([a, b])["rent_amount"]
    assert merged["value"] == "$18,750.00", "tie on confidence -> earliest page"
    assert merged["confidence"] == "low"
    assert [(x["value"], x["source"]["page"]) for x in merged["alternatives"]] == [("$18,750.00", 1), ("$21,000.00", 301)]
    assert "page 301" in merged["validation_note"] and "page 1" in merged["validation_note"]

    # A higher-confidence later value wins the display slot, but is still flagged.
    a["rent_amount"] = _entry("$18,750.00", 1, confidence="low")
    merged = ai_extraction.merge_chunk_fields([a, b])["rent_amount"]
    assert merged["value"] == "$21,000.00" and merged["confidence"] == "low" and len(merged["alternatives"]) == 2
    print("✓ test_conflicting_values_across_parts_are_flagged_not_silently_picked: PASS")


def test_same_value_in_several_parts_keeps_confidence_and_lists_pages():
    a, b, c = _empty(), _empty(), _empty()
    a["tenant"] = _entry("Northwind Outfitters, Inc.", 1, "medium")
    b["tenant"] = _entry("Northwind Outfitters, Inc", 250, "high")  # punctuation differs only
    c["tenant"] = _entry("NORTHWIND OUTFITTERS, INC.", 500, "high")
    merged = ai_extraction.merge_chunk_fields([a, b, c])["tenant"]
    assert merged["confidence"] == "high" and merged["source"]["page"] == 250
    assert merged["found_on_pages"] == [1, 250, 500]
    assert "alternatives" not in merged
    print("✓ test_same_value_in_several_parts_keeps_confidence_and_lists_pages: PASS")


def test_concessions_from_different_parts_are_combined():
    a, b = _empty(), _empty()
    a["concessions"] = {**_entry("1 month free (move-in)", 3, "high", "Tenant shall receive one (1) month of free rent."),
                        "items": [{"kind": "free_months", "free_months": 1, "page": 3}]}
    b["concessions"] = {**_entry("$100.00/mo off for 6 months (renewal)", 410, "medium",
                                 "Base Rent shall be reduced by $100.00 per month for the first six (6) months."),
                        "items": [{"kind": "monthly_discount", "monthly_amount": 100.0, "months": 6, "page": 410}]}
    merged = ai_extraction.merge_chunk_fields([a, b])["concessions"]
    assert merged["value"] == "1 month free (move-in); $100.00/mo off for 6 months (renewal)"
    assert len(merged["items"]) == 2 and merged["confidence"] == "medium"
    assert merged["found_on_pages"] == [3, 410] and " ... " in merged["source_text"]
    print("✓ test_concessions_from_different_parts_are_combined: PASS")


def test_one_failed_part_fails_the_whole_document():
    pages = [{"page": n, "text": f"Section {n}. " + "word " * 50} for n in range(1, 251)]
    reader = FaithfulReader()
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ai_extraction.AIExtractionError("The document-extraction service is temporarily unavailable.")
        return FaithfulReader.create(reader, **kwargs)

    reader.create = flaky
    try:
        ai_extraction.extract_lease_fields_chunked(pages, client=reader)
    except ai_extraction.AIExtractionError:
        pass
    else:
        raise AssertionError("a failed part must not produce a partial result")
    assert calls["n"] == 2, "stops at the failed part"
    print("✓ test_one_failed_part_fails_the_whole_document: PASS")


def test_short_document_is_one_call_identical_to_the_old_path():
    pages = [{"page": 1, "text": "This Commercial Lease is entered into by and between Harborline Commons LLC "
                                 "(\"Landlord\") and Northwind Outfitters, Inc. (\"Tenant\")."}]
    old, new = FaithfulReader(), FaithfulReader()
    old_fields = ai_extraction.extract_lease_fields(pages, client=old)
    new_fields = ai_extraction.extract_lease_fields_chunked(pages, client=new)
    assert len(new.prompts) == 1 and new.prompts == old.prompts, "same single message, no part note"
    assert "part 1 of" not in new.prompts[0]
    old_fields.pop("_ai_meta"), new_fields.pop("_ai_meta")
    assert old_fields == new_fields
    print("✓ test_short_document_is_one_call_identical_to_the_old_path: PASS")


def test_formatting_only_differences_are_not_conflicts():
    """Review finding: "$5,000" vs "5,000.00" or "ABC, LLC" vs "ABC LLC" dropped the field to low with spurious alternatives."""
    a, b = _empty(), _empty()
    a["security_deposit"] = _entry("$5,000", 3)
    b["security_deposit"] = _entry("5,000.00", 300)
    a["landlord"] = _entry("Harborline Commons, LLC", 1)
    b["landlord"] = _entry("Harborline Commons LLC", 500)
    merged = ai_extraction.merge_chunk_fields([a, b])
    for name in ("security_deposit", "landlord"):
        assert merged[name]["confidence"] == "high" and "alternatives" not in merged[name], merged[name]
    # A real difference is still a conflict, and a non-string value can't crash the merge.
    b["security_deposit"] = _entry("$5,500.00", 300)
    a["square_footage"] = _entry(12500, 3)
    b["square_footage"] = _entry("12,500", 4)
    merged = ai_extraction.merge_chunk_fields([a, b])
    assert merged["security_deposit"]["confidence"] == "low"
    assert "alternatives" not in merged["square_footage"]
    print("✓ test_formatting_only_differences_are_not_conflicts: PASS")


if __name__ == "__main__":
    test_plan_chunks_respects_both_caps_and_keeps_every_page_once()
    test_500_page_lease_every_page_reaches_the_model_and_late_terms_come_back_cited()
    test_conflicting_values_across_parts_are_flagged_not_silently_picked()
    test_same_value_in_several_parts_keeps_confidence_and_lists_pages()
    test_concessions_from_different_parts_are_combined()
    test_one_failed_part_fails_the_whole_document()
    test_short_document_is_one_call_identical_to_the_old_path()
    test_formatting_only_differences_are_not_conflicts()
    print("\nAll chunked AI extraction tests passed!")
