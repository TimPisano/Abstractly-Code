"""
How a form mapping is written.

A FormSpec says how to recognise one form (printed phrases, and optionally
fillable-field names) and lists its fields. Each field (Rule) can be read
two ways, tried in order:

  1. `acro`: regexes matched against fillable-field names. Used when the
     PDF still has its form fields (unflattened).
  2. `anchors`: a printed label on the page plus a box relative to it.
     Used for flattened PDFs and scans. The box is in PDF points:

        x from (anchor.x1 if origin == "x1" else anchor.x0) + dx0 ... + dx1
        y from anchor.top + dy0 ... anchor.top + dy1   (y grows downward)

     Words whose centre falls in the box, minus the label's own words,
     are the value. Several anchors can be listed for forms printed in
     more than one layout; the first that yields a valid value wins.

Write mappings by reading the *blank* form (tests/eval/affordable/
inspect_form.py lines|fields), never from sample answer keys.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class Anchor:
    phrase: str
    box: Tuple[float, float, float, float]     # dx0, dy0, dx1, dy1
    origin: str = "x1"                          # "x1" (right of label) or "x0" (under label)
    page: Optional[int] = None                  # 1-based; None = any page
    occurrence: int = 1                         # nth match (in reading order) on the page(s) searched


@dataclass(frozen=True)
class Rule:
    name: str
    type: str                                   # text | money | date | int | pct | checkbox
    acro: Sequence[str] = ()                    # regexes on fillable-field full names
    anchors: Sequence[Anchor] = ()
    strip: Sequence[str] = ()                   # regexes removed from the raw text before parsing
    acro_line: Optional[int] = None             # take only this line (0-based) of a multi-line form field
    label_guard: bool = True                    # reject values made only of label words; off for fields
                                                # whose real values are such words ("Head", "Spouse")
    canonical: Optional[str] = None             # shared meaning across forms, e.g. "contract_rent"


@dataclass
class FormSpec:
    id: str
    name: str
    doc_kind: str                               # hap_contract, rfta, pbra_certification, tic, ...
    program: str                                # HCV, PBV, PBRA, LIHTC
    detect: Sequence[Tuple[str, float]]         # (printed phrase, weight); matched spacing-insensitively
    rules: Sequence[Rule]
    min_score: float = 2.0
    acro_signature: Sequence[str] = ()          # field-name regexes that also identify the form
    # lease field -> rule name, or a tuple of rule names joined with ", "
    lease_map: Dict[str, Union[str, Tuple[str, ...]]] = field(default_factory=dict)
    notes: str = ""

    def label_phrases(self):
        return [a.phrase for r in self.rules for a in r.anchors]
