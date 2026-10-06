"""
Regression test: extraction time must stay roughly linear in document size.

Found in review (2026-10-05): the new party-name pattern had no anchor,
so a long unbroken token -- OCR garbage, a base64 blob, a dot-leader run --
was retried from every character inside it. 16,000 "A"s took 75s, past
gunicorn's 120s worker timeout for a bigger upload. Two older digit-run
patterns (cure period, square footage) had the same shape (~6s on 20,000
digits). Each adversarial token below must now extract in well under the
bound, with every engine path on (multifamily flag on).
"""

import os
import sys
import time
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import multifamily_charges as mf
from app.field_extractor import FieldExtractor

TOKENS = {
    "uppercase": "A",
    "mixed case + digit": "Ab1",
    "initial-like": "A.",
    "hyphenated": "A-",
    "digits": "1",
    "digit groups": "1,",
    "dollar-ish": "$1",
    "base64-ish": "QmFzZTY0+/=",
    "dot leader": ". ",
}
LENGTH = 20_000
BOUND_SECONDS = 3.0  # each case runs in ~0.1s after the fix; minutes before it


def test_long_tokens_extract_in_linear_time():
    fe = FieldExtractor()
    with mock.patch.dict(os.environ, {mf.FLAG_ENV: "1"}):
        for label, unit in TOKENS.items():
            token = unit * (LENGTH // len(unit))
            pages = [{"page": 1, "text": f"Tenant: {token} Owner\nRent: {token} per month"}]
            started = time.monotonic()
            fe.detect_lease_boundaries(pages)
            fe.extract_fields(pages)
            elapsed = time.monotonic() - started
            assert elapsed < BOUND_SECONDS, f"{label}: {elapsed:.1f}s on a {LENGTH}-char token"
            print(f"  {label:<20} {elapsed:5.2f}s")
    print(f"✓ {LENGTH:,}-char adversarial tokens each extract in < {BOUND_SECONDS}s: PASS")


if __name__ == "__main__":
    test_long_tokens_extract_in_linear_time()
