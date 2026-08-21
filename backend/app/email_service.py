"""
Real email delivery for the waitlist flow, sent via Gmail SMTP.

Credentials come from environment variables only (EMAIL_USER,
EMAIL_APP_PASSWORD) — never hardcoded, and this module never guesses or
falls back to a default. See ../.env.example for the exact variable
names and how to generate a Gmail App Password; api.py loads a local
.env (if one exists) at startup via python-dotenv, so either a real
.env file or real environment variables both work — this module only
ever reads os.environ, so it doesn't care which supplied the value.

Every send_* function here is best-effort: on any failure (missing
credentials, bad credentials, network error, rate limit, a rejected
recipient) it logs the failure server-side and returns False rather
than raising. This is deliberate, not an oversight — the waitlist
signup flow that calls these functions must never fail, or even show
the person submitting the form an error, because of an email delivery
problem. See the callers in api.py.
"""

import html
import logging
import os
import smtplib
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SMTPS (implicit TLS) — Gmail's standard port for App Password auth
SMTP_TIMEOUT_SECONDS = 10

# Last-resort safety net, independent of anything upstream (a test file
# that forgets to mock, a future retry bug, a route called in a loop,
# a new caller nobody thought to rate-limit at the route layer). Caps
# the blast radius of any such misfire rather than trying to prevent it
# outright -- that's still the callers' job, this is defense in depth.
#
# Added after a real incident: two pre-existing test files called
# POST /waitlist with distinct fixture emails via Flask's in-process
# test client, with no email mocking at all -- harmless while this
# dev environment had no real credentials, but once real EMAIL_USER/
# EMAIL_APP_PASSWORD were configured, every one of those calls (times
# however many suite runs happened during iteration) fired a real
# send to the real ADMIN_EMAIL inbox. See DECISIONS.md for the full
# incident and the test-side fix (those files no longer have real
# credentials available to them regardless of what's in .env). This
# is the send-side backstop: even with real credentials present and a
# caller that misfires repeatedly, no single recipient can receive
# more than _RATE_LIMIT_MAX_PER_WINDOW emails from this module within
# _RATE_LIMIT_WINDOW_SECONDS.
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_PER_WINDOW = 10

_rate_limit_lock = threading.Lock()
_recent_sends = {}  # to_email -> [monotonic timestamps within the current window]


def _rate_limited(to_email: str) -> bool:
    """True if `to_email` has already hit the send cap within the current window."""
    now = time.monotonic()
    with _rate_limit_lock:
        timestamps = [
            t for t in _recent_sends.get(to_email, [])
            if now - t < _RATE_LIMIT_WINDOW_SECONDS
        ]
        if len(timestamps) >= _RATE_LIMIT_MAX_PER_WINDOW:
            _recent_sends[to_email] = timestamps
            return True
        timestamps.append(now)
        _recent_sends[to_email] = timestamps
        return False


def _reset_rate_limit_state_for_tests():
    """Test-only: clears the in-memory rate limit state between test runs that share a process."""
    with _rate_limit_lock:
        _recent_sends.clear()

FROM_DISPLAY_NAME = "Tim Pisano — Abstractly"

# Landing page's luxury palette (see frontend/landing.css), reused here
# so the confirmation email doesn't feel like a different product.
_COLOR_BACKGROUND = "#f6f3ec"
_COLOR_CARD_BORDER = "#e6e0d2"
_COLOR_TEXT_DARK = "#161512"
_COLOR_TEXT_BODY = "#3a3833"
_COLOR_ACCENT = "#b68a4e"


def _credentials():
    """Returns (email_user, app_password), or (None, None) if either is unset."""
    email_user = os.environ.get("EMAIL_USER")
    app_password = os.environ.get("EMAIL_APP_PASSWORD")
    if not email_user or not app_password:
        return None, None
    return email_user, app_password


def _send(to_email: str, subject: str, text_body: str, html_body: str) -> bool:
    email_user, app_password = _credentials()
    if not email_user or not app_password:
        logger.warning(
            "Email not sent to %s (subject: %r): EMAIL_USER/EMAIL_APP_PASSWORD "
            "are not configured. Set them in backend/.env — see backend/.env.example.",
            to_email, subject,
        )
        return False

    if _rate_limited(to_email):
        logger.error(
            "Email to %s (subject: %r) BLOCKED by the send-side rate limit "
            "(more than %d emails to this recipient in the last %d seconds). "
            "This should never happen in normal operation -- something is "
            "calling a send_* function repeatedly. Investigate the caller; "
            "this limit exists to cap damage, not as expected behavior.",
            to_email, subject, _RATE_LIMIT_MAX_PER_WINDOW, _RATE_LIMIT_WINDOW_SECONDS,
        )
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{FROM_DISPLAY_NAME} <{email_user}>"
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.login(email_user, app_password)
            server.sendmail(email_user, [to_email], message.as_string())
        return True
    except Exception:
        # Deliberately broad: smtplib raises several distinct exception
        # types (auth failure, connection error, recipient refused) and
        # a plain socket timeout isn't even an smtplib exception — all
        # of them must degrade the same way. The real exception is
        # logged server-side only, matching this project's established
        # error-handling convention (see api.py's global error handlers
        # from the hardening pass).
        logger.exception("Failed to send email to %s (subject: %r)", to_email, subject)
        return False


def send_waitlist_confirmation_email(to_email: str) -> bool:
    """Sent immediately when someone first joins the waitlist (not on a duplicate resubmission — see api.py)."""
    subject = "We've received your request"
    text_body = (
        "Thanks for reaching out to Abstractly.\n\n"
        "We've received your request for access and will be in touch "
        "personally if it's a fit.\n\n"
        "We work with a limited number of real estate firms at a time, "
        "so every request gets a real look — not a place in a queue.\n\n"
        "Best,\nTim Pisano"
    )
    html_body = _email_html(
        heading="We've received your request.",
        paragraphs=[
            "Thanks for reaching out. We&rsquo;ve received your request for "
            "access and will be in touch personally if it&rsquo;s a fit.",
            "We work with a limited number of real estate firms at a time, "
            "so every request gets a real look &mdash; not a place in a queue.",
        ],
    )
    return _send(to_email, subject, text_body, html_body)


def send_admin_new_request_notification(requester_email: str) -> bool:
    """
    Sent to the admin (ADMIN_EMAIL -- see auth.py, the same single
    account the admin dashboard logs into) whenever someone submits the
    landing page's "Request Access" form. Distinct from
    send_waitlist_confirmation_email above, which goes to the requester,
    not the admin -- this is how the admin actually finds out a request
    came in without having to keep the dashboard open and refreshing it.

    If ADMIN_EMAIL isn't set, this is a no-op (returns False) rather
    than an error -- same fail-open-on-missing-config posture as the
    rest of this module.
    """
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
    if not admin_email:
        logger.warning(
            "Admin notification not sent for signup %r: ADMIN_EMAIL is not "
            "configured. Set it in backend/.env — see backend/.env.example.",
            requester_email,
        )
        return False

    subject = f"New access request: {requester_email}"
    text_body = (
        f"{requester_email} just requested access to Abstractly.\n\n"
        "Review and approve or deny it from the admin dashboard."
    )
    html_body = _email_html(
        heading="New access request.",
        paragraphs=[
            # requester_email is user-submitted (the /waitlist form only
            # checks it looks email-shaped, not that it's free of HTML
            # metacharacters) -- escape before embedding, unlike the
            # rest of this module's paragraphs, which are all
            # hardcoded/trusted strings.
            f"<strong>{html.escape(requester_email)}</strong> just requested access to Abstractly.",
            "Review and approve or deny it from the admin dashboard.",
        ],
    )
    return _send(admin_email, subject, text_body, html_body)


def send_waitlist_approval_email(to_email: str) -> bool:
    """Sent when an admin approves a waitlist signup from the admin dashboard."""
    subject = "You've been approved for access"
    text_body = (
        "Good news — you've been approved for access to Abstractly.\n\n"
        "We'll follow up shortly with next steps to get you started.\n\n"
        "Best,\nTim Pisano"
    )
    html_body = _email_html(
        heading="You've been approved for access.",
        paragraphs=[
            "Good news &mdash; you&rsquo;ve been approved for access to Abstractly.",
            "We&rsquo;ll follow up shortly with next steps to get you started.",
        ],
    )
    return _send(to_email, subject, text_body, html_body)


def _email_html(heading: str, paragraphs) -> str:
    """
    A restrained, minimal HTML shell — inline styles only (email clients
    don't reliably support external/embedded stylesheets), no images or
    web fonts (nothing to wait on or fail to load), one card on a flat
    background. Deliberately not a marketing template.
    """
    paragraphs_html = "".join(
        f'<p style="margin:0 0 16px;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:15px;line-height:1.6;color:{_COLOR_TEXT_BODY};">{p}</p>'
        for p in paragraphs
    )
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background-color:{_COLOR_BACKGROUND};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_COLOR_BACKGROUND};padding:48px 24px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:480px;background-color:#ffffff;border:1px solid {_COLOR_CARD_BORDER};">
          <tr>
            <td style="padding:40px;">
              <p style="margin:0 0 24px;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{_COLOR_ACCENT};">Abstractly</p>
              <h1 style="margin:0 0 20px;font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:800;color:{_COLOR_TEXT_DARK};letter-spacing:-0.01em;">{heading}</h1>
              {paragraphs_html}
              <p style="margin:24px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:{_COLOR_TEXT_DARK};">Best,<br>Tim Pisano</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
