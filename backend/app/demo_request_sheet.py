"""
Optional: forward each new Book a Demo submission to a Google Sheet via
a Google Apps Script web app (setup: docs/DEMO_REQUESTS_SHEET.md).

Off unless DEMO_REQUEST_SHEET_WEBHOOK_URL is set. Strictly best-effort,
same guarantee as the demo-request emails: the row is already committed
to the database before this runs, nothing here ever raises, and it runs
on a background thread so a slow or down Google never delays the public
form's response. A failed forward is logged; the request is still in
the owner console and its CSV export.
"""
import logging
import os
import threading
from typing import Any, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

WEBHOOK_URL_ENV = "DEMO_REQUEST_SHEET_WEBHOOK_URL"
SECRET_ENV = "DEMO_REQUEST_SHEET_SECRET"
TIMEOUT_SECONDS = 10

_FIELDS = ("id", "name", "work_email", "company", "units", "message", "created_at")


def webhook_url() -> str:
    return os.environ.get(WEBHOOK_URL_ENV, "").strip()


def is_allowed_url(url: str) -> bool:
    """Only a deployed Apps Script web app: https://script.google.com/macros/s/<id>/exec."""
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "script.google.com"
        and parsed.path.startswith("/macros/s/")
        and parsed.path.endswith("/exec")
    )


def forward(record: Dict[str, Any]) -> bool:
    """POST one demo request to the Sheet webhook. Returns True if delivered; never raises."""
    url = webhook_url()
    if not url:
        return False
    if not is_allowed_url(url):
        logger.error("%s is not an Apps Script /exec URL; not forwarding demo requests", WEBHOOK_URL_ENV)
        return False

    payload = {field: record.get(field) for field in _FIELDS}
    secret = os.environ.get(SECRET_ENV, "").strip()
    if secret:
        # In the body, not a header: Apps Script's doPost(e) can't read
        # request headers.
        payload["secret"] = secret

    try:
        import requests

        # No redirects: Apps Script runs doPost, then answers 302 to a
        # googleusercontent.com URL holding the script's output. The row
        # is already written by then, and following the 302 would turn
        # the request into a GET against another host.
        resp = requests.post(url, json=payload, timeout=TIMEOUT_SECONDS, allow_redirects=False)
    except Exception:
        logger.exception("Forwarding demo request %s to the Google Sheet failed", record.get("id"))
        return False

    if resp.status_code in (200, 302):
        return True
    logger.error(
        "Google Sheet webhook returned HTTP %s for demo request %s", resp.status_code, record.get("id")
    )
    return False


def forward_in_background(record: Dict[str, Any]) -> None:
    """Fire-and-forget forward() on a daemon thread. No-op when the webhook is off."""
    if not webhook_url():
        return
    try:
        threading.Thread(target=forward, args=(dict(record),), daemon=True,
                         name="demo-request-sheet").start()
    except Exception:
        logger.exception("Could not start the demo-request Sheet forwarding thread")
