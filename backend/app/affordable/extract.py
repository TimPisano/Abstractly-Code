"""
Recognise a known HUD / LIHTC form and read its fields.

    result = extract_document(pdf_bytes)
    result["form_id"]          # e.g. "hud_52641", or None if unrecognised
    result["program_fields"]   # {name: {"value", "source", "confidence", "method"}}
    result["lease_fields"]     # the 15 lease fields, same shape as FieldExtractor's

Values come from fillable-form fields when the PDF still has them, otherwise
from the printed label's position on the page (text layer or OCR). A
recognised form is read as one document: no lease splitting, no rent-roll
gate. Unrecognised documents return form_id None and no fields, so callers
fall back to the existing lease extractor.
"""

import difflib
import re
from typing import Dict, List, Optional, Tuple, Union

from .acroform import FormFieldValue, read_acroform
from .forms import all_forms
from .forms.base import Anchor, FormSpec, Rule
from .layout import PageLayout, Word, chains, group_lines, ocr_region, read_layout
from .pii import is_restricted_field, mask_ssns
from .values import coerce

Source = Union[bytes, str]

# Same keys and order as extraction_scoring.ALL_FIELDS (kept local so this
# module doesn't import the scoring code).
LEASE_FIELDS = [
    "tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date", "property_address",
    "security_deposit", "cam_charges", "rent_escalation", "renewal_options", "permitted_use",
    "exclusivity_clause", "insurance_requirements", "default_cure_period", "square_footage",
]
FUZZY_MIN_RATIO = 0.84
SHORT_LABEL = 8          # normalised length at or below which a label must match whole words


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------

def _doc_text(pages: List[PageLayout], limit: int = 4) -> str:
    return _norm(" ".join(w.text for p in pages[:limit] for w in p.words))


def detect_form(pages: List[PageLayout], acro: List[FormFieldValue],
                forms: Optional[List[FormSpec]] = None) -> Tuple[Optional[FormSpec], float]:
    text = _doc_text(pages)
    names = [v.name for v in acro]
    best, best_score = None, 0.0
    for spec in forms or all_forms():
        score = sum(w for phrase, w in spec.detect if _norm(phrase) in text)
        if names and spec.acro_signature:
            score += sum(1.0 for rx in spec.acro_signature if any(re.search(rx, n) for n in names))
        if score >= spec.min_score and score > best_score:
            best, best_score = spec, score
    return best, best_score


# ---------------------------------------------------------------------------
# anchors and boxes
# ---------------------------------------------------------------------------

def _find_phrase(page: PageLayout, phrase: str, fuzzy: bool) -> List[Tuple[float, float, float, float, List[Word]]]:
    """All single-line matches of `phrase` on the page, as (x0, x1, top, bottom, words)."""
    target = _norm(phrase)
    if not target:
        return []
    scored = []   # (ratio, span)
    for line in chains(page.words):
        joined, owner = "", []
        for idx, w in enumerate(line):
            n = _norm(w.text)
            joined += n
            owner.extend([idx] * len(n))
        # A short label must start and end on word boundaries, so "TC" doesn't
        # match inside "TC-26-118" or "County" inside "Maple Ridge County".
        # Longer labels don't need it (and some forms print labels without
        # spaces, "2.AddressofUnit(street", so a boundary rule would miss them).
        word_starts = {i for i in range(len(owner)) if i == 0 or owner[i] != owner[i - 1]}
        word_ends = {i for i in range(len(owner)) if i == len(owner) - 1 or owner[i] != owner[i + 1]}
        strict = len(target) <= SHORT_LABEL
        start = joined.find(target)
        used_exact = False
        while start != -1:
            end = start + len(target) - 1
            if not strict or (start in word_starts and end in word_ends):
                used_exact = True
                first, last = owner[start], owner[end]
                scored.append((1.0, _span(line[first:last + 1])))
            start = joined.find(target, start + 1)
        if fuzzy and not used_exact and len(target) >= 6:
            best = None
            # Window sizes by word count *and* by length: OCR may split or merge
            # words, and a label can be written squashed ("22.No.ofBedrooms").
            n_words = len(phrase.split())
            sizes = set(range(max(1, n_words - 2), n_words + 3)) | set(range(1, 4))
            for size in sorted(sizes):
                for i in range(0, max(0, len(line) - size) + 1):
                    cand = "".join(_norm(w.text) for w in line[i:i + size])
                    if not cand or len(cand) > 2 * len(target):
                        continue
                    ratio = difflib.SequenceMatcher(None, cand, target).ratio()
                    if ratio >= FUZZY_MIN_RATIO and (best is None or ratio > best[0]):
                        best = (ratio, i, size)
            if best:
                ratio, i, size = best
                scored.append((ratio, _span(line[i:i + size])))
    if not scored:
        return []
    # Keep only the best matches: near-identical labels ("...abated under this
    # contract" / "...vacant under this contract") must not win on position alone.
    top = max(r for r, _ in scored)
    hits = [h for r, h in scored if r >= top - 0.03]
    hits.sort(key=lambda h: (h[2], h[0]))
    return hits


def _span(words: List[Word]):
    # The label's top is its words' median top: OCR boxes vary in height
    # ("of" vs "Address"), and the minimum would let the label's own row
    # leak into a box that starts just below it.
    tops = sorted(w.top for w in words)
    return (min(w.x0 for w in words), max(w.x1 for w in words),
            tops[len(tops) // 2], max(w.bottom for w in words), words)


SAME_ROW = 4.0   # points; words this close to the label's centre line are on the label's row


def _box_text(page: PageLayout, anchor: Anchor, hit) -> Tuple[str, Tuple[float, float, float, float]]:
    x0a, x1a, topa, bottoma, label_words = hit
    xref = x1a if anchor.origin == "x1" else x0a
    dx0, dy0, dx1, dy1 = anchor.box
    bx0, bx1, by0, by1 = xref + dx0, xref + dx1, topa + dy0, topa + dy1
    label_ids = {id(w) for w in label_words}
    label_mid = sum(w.mid_y for w in label_words) / len(label_words)
    below_only = dy0 >= SAME_ROW
    inside = [w for w in page.words
              if id(w) not in label_ids and bx0 <= w.mid_x <= bx1 and by0 <= w.mid_y <= by1
              and not (below_only and abs(w.mid_y - label_mid) <= SAME_ROW)]
    text = " ".join(" ".join(w.text for w in line) for line in group_lines(inside))
    return text, (bx0, max(by0, bottoma + 1 if below_only else by0), bx1, by1)


def _from_anchors(rule: Rule, pages: List[PageLayout], phrases, data: bytes) -> Optional[Tuple[str, int, str]]:
    for anchor in rule.anchors:
        candidates = [p for p in pages if anchor.page is None or p.page == anchor.page]
        hits = []
        for p in candidates:
            for h in _find_phrase(p, anchor.phrase, fuzzy=(p.source == "ocr")):
                hits.append((p, h))
        if len(hits) < anchor.occurrence:
            continue
        page, hit = hits[anchor.occurrence - 1]
        raw, box = _box_text(page, anchor, hit)
        value = _parse(rule, raw, phrases)
        if value is None and page.source == "ocr":
            # whole-page OCR can drop short values beside table rules; re-read the box alone
            raw = ocr_region(data, page.page, box)
            value = _parse(rule, raw, phrases)
        if value is not None:
            return value, page.page, raw
    return None


def _parse(rule: Rule, raw: str, phrases) -> Optional[str]:
    for rx in rule.strip:
        raw = re.sub(rx, " ", raw, flags=re.I)
    return coerce(raw, rule.type, phrases, label_guard=rule.label_guard)


def _from_acro(rule: Rule, acro: List[FormFieldValue]) -> Optional[Tuple[str, int, str]]:
    for rx in rule.acro:
        for v in acro:
            if re.search(rx, v.name):
                raw = v.value
                if rule.acro_line is not None:
                    lines = [ln for ln in re.split(r"[\r\n]+", raw) if ln.strip()]
                    raw = lines[rule.acro_line] if len(lines) > rule.acro_line else ""
                value = _parse(rule, raw, ())
                if value is not None:
                    return value, v.page, raw
    return None


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def _empty_lease_fields() -> Dict[str, Dict]:
    return {f: {"value": None, "source": None, "confidence": None} for f in LEASE_FIELDS}


def extract_document(source: Source, *, use_acroform: bool = True, ocr: bool = True,
                     forms: Optional[List[FormSpec]] = None) -> Dict:
    data = source if isinstance(source, (bytes, bytearray)) else open(source, "rb").read()
    pages = read_layout(data, ocr=ocr)
    acro = read_acroform(data) if use_acroform else []
    spec, score = detect_form(pages, acro, forms)

    result = {
        "form_id": spec.id if spec else None,
        "form_name": spec.name if spec else None,
        "doc_kind": spec.doc_kind if spec else None,
        "program": spec.program if spec else None,
        "detect_score": score,
        "had_form_fields": bool(acro),
        "ocr_pages": [p.page for p in pages if p.source == "ocr"],
        "program_fields": {},
        "lease_fields": _empty_lease_fields(),
        "warnings": [],
    }
    if spec is None:
        result["warnings"].append("Not a recognised affordable-housing form; use the lease extractor.")
        return result

    phrases = spec.label_phrases()
    for rule in spec.rules:
        if is_restricted_field(rule.name):
            continue
        found, method = _from_acro(rule, acro), "acroform"
        if found is None:
            found = _from_anchors(rule, pages, phrases, data)
            method = "ocr" if found and any(p.page == found[1] and p.source == "ocr" for p in pages) else "layout"
        if found is None:
            continue
        value, page_no, raw = found
        result["program_fields"][rule.name] = {
            "value": value,
            "source": {"page": page_no, "quote": mask_ssns(raw)[:200]},
            "confidence": "high" if method == "acroform" else "medium",
            "method": method,
            "canonical": rule.canonical,
        }

    for lease_field, ref in spec.lease_map.items():
        names = (ref,) if isinstance(ref, str) else tuple(ref)
        parts = [result["program_fields"][n] for n in names if n in result["program_fields"]]
        if not parts:
            continue
        result["lease_fields"][lease_field] = {
            "value": ", ".join(p["value"] for p in parts),
            "source": parts[0]["source"],
            "confidence": parts[0]["confidence"],
        }
    return result
