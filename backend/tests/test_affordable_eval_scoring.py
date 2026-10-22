"""
Tests for the real-set eval's scoring rules (tests/eval/affordable/run_eval.py).
No AI calls, no documents. Fictional values only.

Run: python backend/tests/test_affordable_eval_scoring.py
"""

import _test_env  # noqa: F401  -- first: temp DB, no .env, no real network (see _test_env.py)
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'eval', 'affordable')))

import run_eval  # noqa: E402

KEY = {"owner_name": {"value": None, "type": "text", "status": "verified"},
       "assignee_name": {"value": "Maple Ridge Holdings LLC", "type": "text", "status": "verified"}}


def test_a_field_the_document_doesnt_state_is_right_when_left_empty():
    """A key field set to null (the letter names a proposed owner, not the
    owner) scores right when nothing is extracted and isn't in the total."""
    assert run_eval.absent_program_fields(KEY, {}) == [
        {"field": "owner_name", "extracted": None, "kind": "correct_absent"}]
    got = run_eval.absent_program_fields(KEY, {"owner_name": {"value": "Maple Ridge Holdings LLC"}})
    assert got[0]["kind"] == "spurious"


def test_an_address_that_differs_only_in_punctuation_is_right():
    """Regression: "Murrieta, CA" scored wrong against a key written "Murrieta CA"."""
    assert run_eval.address_match("24 Example Avenue, Springfield, ZZ 00000", "24 Example Avenue, Springfield ZZ 00000")
    assert not run_eval.address_match("26 Example Avenue, Springfield, ZZ 00000", "24 Example Avenue, Springfield ZZ 00000")
    assert not run_eval.address_match(None, "24 Example Avenue")
    assert not run_eval.address_match("1450. Example Drive, Springfield", "1450 Example Drive, Springfield")


if __name__ == "__main__":
    test_a_field_the_document_doesnt_state_is_right_when_left_empty()
    test_an_address_that_differs_only_in_punctuation_is_right()
    print("\nAll eval scoring tests passed.")
