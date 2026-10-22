"""
Read values typed into a PDF's fillable (AcroForm) fields.

A form filled in Acrobat or Preview and saved without flattening keeps its
values in the form fields, not in the page content. pypdf's extract_text()
(what document_extractor uses today) never sees them, so a filled TIC or
HUD-50059 reads as an empty form. In the eval, 79% of values on
unflattened forms were invisible that way.
"""

import io
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from pypdf import PdfReader

from .pii import is_identifier_field, is_restricted_field, mask_ssns

Source = Union[bytes, str]


@dataclass
class FormFieldValue:
    name: str                 # fully qualified field name, e.g. "topmostSubform[0].Page1[0].f1_1[0]"
    label: str                # the field's tooltip (/TU) if it has one, else its name
    value: str                # text value, or "X" for a ticked box
    kind: str                 # "text" or "checkbox"
    page: int                 # 1-based
    rect: Tuple[float, float, float, float]  # x0, top, x1, bottom (from the page's top-left)


def _reader(source: Source) -> PdfReader:
    if isinstance(source, (bytes, bytearray)):
        return PdfReader(io.BytesIO(source))
    return PdfReader(source)


def _inherited(annot, key):
    node = annot
    for _ in range(12):
        if node is None:
            return None
        if key in node:
            return node[key]
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return None


def _full_name(annot) -> Optional[str]:
    parts = []
    node = annot
    for _ in range(12):
        if node is None:
            break
        if "/T" in node:
            parts.append(str(node["/T"]))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return ".".join(reversed(parts)) if parts else None


def read_acroform(source: Source) -> List[FormFieldValue]:
    """Every filled field, in page order. Empty fields and unticked boxes are
    skipped. SSN and date-of-birth fields are never read, and SSN-shaped
    values in other fields are masked."""
    try:
        reader = _reader(source)
        if reader.is_encrypted and reader.decrypt("") == 0:
            return []
    except Exception:
        return []

    out: List[FormFieldValue] = []
    seen = set()
    for page_no, page in enumerate(reader.pages, start=1):
        height = float(page.mediabox.height)
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            name = _full_name(annot)
            if not name:
                continue
            tooltip = _inherited(annot, "/TU")
            label = str(tooltip) if tooltip else name
            if is_restricted_field(name) or is_restricted_field(label):
                continue
            ftype = _inherited(annot, "/FT")
            x0, y0, x1, y1 = (float(v) for v in annot["/Rect"])
            rect = (min(x0, x1), height - max(y0, y1), max(x0, x1), height - min(y0, y1))

            if ftype == "/Btn":
                state = annot.get("/AS")
                if state is None or str(state) == "/Off":
                    continue
                value, kind = "X", "checkbox"
                key = (name, page_no, rect)
            else:
                raw = _inherited(annot, "/V")
                if raw is None:
                    continue
                value = str(raw).strip()
                if not value or value.startswith("/"):
                    continue
                value, kind = mask_ssns(value, identifier_field=is_identifier_field(name, label)), "text"
                key = (name, page_no)   # one value per text field per page
            if key in seen:
                continue
            seen.add(key)
            out.append(FormFieldValue(name=name, label=label, value=value, kind=kind, page=page_no, rect=rect))
    return out


def acroform_page_text(values: List[FormFieldValue]) -> Dict[int, str]:
    """Per page, one "label: value" line per filled field, top to bottom.
    Appending this to a page's text makes form values visible to any
    text-based extractor."""
    by_page: Dict[int, List[FormFieldValue]] = {}
    for v in values:
        by_page.setdefault(v.page, []).append(v)
    out = {}
    for page_no, vals in by_page.items():
        vals.sort(key=lambda v: (round(v.rect[1]), v.rect[0]))
        out[page_no] = "\n".join(f"{v.label}: {v.value}" for v in vals)
    return out
