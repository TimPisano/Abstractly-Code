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

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SMTPS (implicit TLS) — Gmail's standard port for App Password auth
SMTP_TIMEOUT_SECONDS = 10

FROM_DISPLAY_NAME = "Tim Pisano — Lumen Lease"

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
        "Thanks for reaching out to Lumen Lease.\n\n"
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


def send_waitlist_approval_email(to_email: str) -> bool:
    """Sent when an admin approves a waitlist signup in /admin/waitlist."""
    subject = "You've been approved for access"
    text_body = (
        "Good news — you've been approved for access to Lumen Lease.\n\n"
        "We'll follow up shortly with next steps to get you started.\n\n"
        "Best,\nTim Pisano"
    )
    html_body = _email_html(
        heading="You've been approved for access.",
        paragraphs=[
            "Good news &mdash; you&rsquo;ve been approved for access to Lumen Lease.",
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
              <p style="margin:0 0 24px;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:{_COLOR_ACCENT};">Lumen Lease</p>
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
