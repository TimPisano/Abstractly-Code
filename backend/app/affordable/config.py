"""Feature flag for the affordable-forms extraction path. Default off."""

import os

_TRUTHY = {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    """True when AFFORDABLE_FORMS_MODE is set to a truthy value. Callers that
    wire this module into uploads must check it; the module itself doesn't."""
    return (os.environ.get("AFFORDABLE_FORMS_MODE") or "").strip().lower() in _TRUTHY
