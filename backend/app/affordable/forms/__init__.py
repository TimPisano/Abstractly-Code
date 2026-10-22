"""Registry of known form mappings. Each module exports FORMS: a list of FormSpec."""

import importlib
import pkgutil
from typing import List

from .base import Anchor, FormSpec, Rule  # noqa: F401


def all_forms() -> List[FormSpec]:
    forms: List[FormSpec] = []
    for mod in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if mod.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        forms.extend(getattr(module, "FORMS", []))
    return forms
