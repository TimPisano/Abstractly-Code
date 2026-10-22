"""
Affordable-housing form extraction (HUD Section 8 and LIHTC forms).

Standalone on purpose: nothing in the upload pipeline imports this yet.
Wiring it in is a separate change, behind AFFORDABLE_FORMS_MODE (default
off; see config.py). Plan and measurements:
docs/plans/affordable-extraction-plan.md, docs/research/eval-baseline.md.

Three pieces, usable on their own:

  acroform.read_acroform()      values typed into a PDF's fillable fields,
                                which pypdf's page text never includes
  layout.read_layout()          words with positions, from the text layer
                                or OCR, and reading-order page text
  extract.extract_document()    recognise a known form and read its fields
                                (program fields like HAP and TTP, plus the
                                lease fields the rest of the app uses)
  route.choose_route()          form reader or AI, from extract_document's result

Tenant data rules: SSN fields are never read, SSN-shaped strings are masked,
dates of birth are not extracted, and no field value is ever logged.
"""

from .acroform import read_acroform, acroform_page_text  # noqa: F401
from .config import is_enabled  # noqa: F401
from .extract import extract_document  # noqa: F401
from .layout import layout_pages, read_layout  # noqa: F401
from .route import choose_route  # noqa: F401
