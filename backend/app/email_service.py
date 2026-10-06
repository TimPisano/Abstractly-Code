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
from typing import Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

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

# Where replies go, regardless of which mailbox EMAIL_USER happens to be.
# "From" has to stay EMAIL_USER (Gmail's SMTP rejects a From it doesn't own),
# so Reply-To is what actually routes a customer's reply to the public
# contact address shown in the site footer.
REPLY_TO_EMAIL = "tim@getabstractly.com"

# Where Book a Demo notifications go: ADMIN_EMAIL, the founder's own
# inbox. Not REPLY_TO_EMAIL -- tim@getabstractly.com forwards to the same
# Gmail account that sends these, and Gmail hides a message that arrives
# back at the mailbox it was sent from, so the notification was never seen.
def _demo_notify_email() -> Optional[str]:
    return os.environ.get("ADMIN_EMAIL", "").strip() or None


# The founder's booking page, sent to everyone who requests a demo and
# served to the marketing site's "Book a call" links (GET /public-config).
# CALENDLY_URL is the only source -- no hard-coded fallback, so a missing
# or mistyped value shows up as an error instead of quietly sending people
# to a stale link. Only an https:// URL counts: the value ends up in an
# href, so anything else (a typo, a javascript: URL) is treated as unset.
def calendly_url() -> Optional[str]:
    url = os.environ.get("CALENDLY_URL", "").strip()
    return url if url.lower().startswith("https://") else None

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


def _send(to_email: str, subject: str, text_body: str, html_body: str, reply_to: Optional[str] = None) -> bool:
    email_user, app_password = _credentials()
    if not email_user or not app_password:
        missing = [name for name in ("EMAIL_USER", "EMAIL_APP_PASSWORD") if not os.environ.get(name)]
        logger.error(
            "Email NOT sent to %s (subject: %r): %s not set. Set %s on this "
            "service (Render dashboard > Environment) or in backend/.env locally "
            "-- see backend/.env.example.",
            to_email, subject, " and ".join(missing), "it" if len(missing) == 1 else "them",
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
    # Subjects can carry user-submitted text (a demo request's company);
    # the stdlib refuses a header with a line break in it, which would
    # silently drop the email, so flatten any to spaces.
    message["Subject"] = " ".join(subject.splitlines())
    # formataddr, not an f-string: the display name has an em dash, and a
    # non-ASCII header written as one string gets encoded WHOLE --
    # address included -- leaving no parseable sender address at all.
    message["From"] = formataddr((FROM_DISPLAY_NAME, email_user))
    # A CR/LF in a header value would let the caller add headers (Bcc...),
    # so anything containing one falls back to the default address.
    if not reply_to or "\r" in reply_to or "\n" in reply_to:
        reply_to = REPLY_TO_EMAIL
    message["Reply-To"] = reply_to
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.login(email_user, app_password)
            refused = server.sendmail(email_user, [to_email], message.as_string())
    except Exception as exc:
        # Deliberately broad: smtplib raises several distinct exception
        # types (auth failure, connection error, recipient refused) and
        # a plain socket timeout isn't even an smtplib exception — all
        # of them must degrade the same way. The real exception is
        # logged server-side only, matching this project's established
        # error-handling convention (see api.py's global error handlers
        # from the hardening pass) -- and named in the log line itself,
        # not just the traceback, so it shows up in a one-line log search.
        logger.exception(
            "Email FAILED to %s (subject: %r): %s: %s",
            to_email, subject, type(exc).__name__, exc,
        )
        return False

    # sendmail returns {recipient: (code, reason)} for any recipient the
    # server refused without raising.
    if isinstance(refused, dict) and refused:
        logger.error("Email FAILED to %s (subject: %r): server refused recipient: %s", to_email, subject, refused)
        return False
    # Gmail accepting the message is as far as SMTP can see: a later
    # bounce from the recipient's provider lands in EMAIL_USER's inbox,
    # not here.
    logger.info("Email sent to %s (subject: %r) via %s", to_email, subject, SMTP_HOST)
    return True


def send_operational_alert(to_email: str, subject: str, body: str) -> bool:
    """
    Operator-facing alert (not customer-facing): used by the
    email-on-error logging handler (app/logging_config.py). Plain text
    only, wrapped in the same minimal HTML shell as the other emails so
    it renders fine in any client. Fail-open like every send here.
    """
    import html as _html
    lines = [_html.escape(line) for line in body.splitlines() if line.strip()] or [_html.escape(body)]
    return _send(to_email, subject, body, _email_html("System alert", lines))


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


def _first_name(name: str) -> str:
    """First word of the form's name field; 'there' if it's blank. An
    all-lowercase entry gets its first letter capitalized ("jacinta" ->
    "Jacinta"); anything else is left exactly as the person typed it."""
    words = (name or "").split()
    if not words:
        return "there"
    first = words[0]
    return first[:1].upper() + first[1:] if first.islower() else first


def send_demo_request_confirmation(to_email: str, name: str, company: str = "") -> bool:
    """
    Sent immediately when someone submits the landing page's Book a Demo
    form: a short personal note from the founder with the CALENDLY_URL
    booking link. Reply-To is tim@getabstractly.com (set in _send).
    """
    first_name = _first_name(name)
    company = (company or "").strip()
    whose = company if company else "your team"
    subject = f"Thanks for reaching out, {first_name}"
    booking_url = calendly_url()

    intro = ("Thanks for requesting a demo of Abstractly. I'm Tim, the founder, "
             "and I read every request that comes in personally.")
    pitch = (f"I'd love to hear how {whose} handles leases and rent rolls today, then "
             "show you how Abstractly catches the mismatches before they cost you "
             "money. It only takes about 20 minutes.")
    if booking_url:
        closing = "If none of those times fit, just reply here and I'll work around your schedule."
    else:
        # Still a complete, sensible note -- just no link. The error below
        # says exactly why.
        logger.error(
            "CALENDLY_URL is not set (or isn't an https:// URL): the demo "
            "confirmation to %s goes out WITHOUT a booking link. Set "
            "CALENDLY_URL on this service (Render dashboard > Environment).",
            to_email,
        )
        closing = "Just reply here with a few times that work for you and I'll set something up."

    text_lines = [f"Hi {first_name},", "", intro, "", pitch, ""]
    if booking_url:
        text_lines += [f"Grab a time that works for you: {booking_url}", ""]
    text_lines += [closing, "", "Talk soon,", "Tim Pisano", "Founder, Abstractly"]
    text_body = "\n".join(text_lines)

    paragraphs = [f"Hi {html.escape(first_name)},", html.escape(intro), html.escape(pitch)]
    if booking_url:
        paragraphs.append(
            f'<a href="{html.escape(booking_url)}" style="color:{_COLOR_ACCENT};'
            'font-weight:bold;text-decoration:underline;">Grab a time that works for you &rarr;</a>'
        )
    paragraphs += [html.escape(closing), "Talk soon,<br>Tim Pisano<br>Founder, Abstractly"]
    return _send(to_email, subject, text_body, _personal_email_html(paragraphs))


def send_demo_request_notification(name: str, work_email: str, company: str, units: int, message: Optional[str]) -> bool:
    """
    Sent to the founder (ADMIN_EMAIL) whenever someone submits the landing page's
    Book a Demo form, with every field it collects. Reply-To is the
    visitor, so hitting Reply in Gmail answers them directly.
    """
    subject = f"New demo request: {company}"
    text_lines = [
        f"{name} at {company} requested a demo.",
        "",
        f"Work email: {work_email}",
        f"Units in portfolio: {units}",
    ]
    if message:
        text_lines += ["", f"Message: {message}"]
    text_body = "\n".join(text_lines)

    # Every value here is user-submitted -- escape all of it before
    # embedding in the HTML part, same reasoning as the waitlist admin
    # notification above.
    paragraphs = [
        f"<strong>{html.escape(name)}</strong> at <strong>{html.escape(company)}</strong> requested a demo.",
        f"Work email: {html.escape(work_email)}<br>Units in portfolio: {units}",
    ]
    if message:
        paragraphs.append(f"Message: {html.escape(message)}")
    html_body = _email_html(heading="New demo request.", paragraphs=paragraphs)

    recipient = _demo_notify_email()
    if not recipient:
        logger.error(
            "Demo request notification NOT sent (request from %s at %r): ADMIN_EMAIL "
            "is not set. Set it on this service (Render dashboard > Environment).",
            work_email, company,
        )
        return False
    return _send(recipient, subject, text_body, html_body, reply_to=work_email)


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


# ---- Account emails (self-serve signup, forgot password) -------------
#
# Written to read like a short note from Tim, not a branded template:
# _personal_email_html (white, no logo, ordinary text), one clear
# button that's easy to hit with a thumb, the raw link underneath for
# anyone whose mail app breaks buttons, and a plain-text part that says
# the same thing. No user-typed text goes in a subject line.

_SIGN_OFF_TEXT = ["Thanks,", "Tim", "Founder, Abstractly"]
_SIGN_OFF_HTML = "Thanks,<br>Tim<br>Founder, Abstractly"


def _greeting_name(name: str) -> str:
    """
    The first name to greet someone by, or "there". Stricter than
    _first_name on purpose: on the signup form the name is typed by
    whoever submits it -- not necessarily the inbox's owner -- and it's
    then put in an email that comes from Tim. Anything that isn't
    plainly a first name (a URL, "Click here", 40 characters of
    whatever) is replaced with "there" rather than repeated back.
    """
    first = _first_name(name)
    if first == "there" or len(first) > 30:
        return "there"
    if not all(ch.isalpha() or ch in "-'" for ch in first):
        return "there"
    return first


def _email_button(url: str, label: str) -> str:
    """A link styled as a button: big enough to tap, no images, works without CSS support (it's still a link)."""
    return (
        f'<a href="{html.escape(url, quote=True)}" style="display:inline-block;'
        'background-color:#17171a;color:#ffffff;text-decoration:none;font-weight:bold;'
        'padding:13px 22px;border-radius:6px;font-size:16px;">'
        f'{html.escape(label)}</a>'
    )


def _raw_link_note(url: str) -> str:
    return (
        '<span style="font-size:13px;color:#6b6760;">Button not working? Paste this into your browser:<br>'
        f'<a href="{html.escape(url, quote=True)}" style="color:#6b6760;word-break:break-all;">'
        f'{html.escape(url)}</a></span>'
    )


def send_signup_link_email(to_email: str, name: str, setup_url: str) -> bool:
    """
    The "Finish setting up your account" email for a self-serve signup.
    No account exists yet -- the link (72 hours, single use) is what
    creates it. Sent again, with a fresh link, each time the person
    signs up again or asks for a new link; only the newest one works.
    """
    first = _greeting_name(name)
    subject = "Finish setting up your Abstractly account"
    text_body = "\n".join([
        f"Hi {first},",
        "",
        "Thanks for signing up for Abstractly. Choose a password here and you're in:",
        "",
        setup_url,
        "",
        "The link works for 72 hours, and only once. If you didn't sign up, "
        "you can ignore this email and nothing will happen.",
        "",
        *_SIGN_OFF_TEXT,
    ])
    html_body = _personal_email_html([
        f"Hi {html.escape(first)},",
        "Thanks for signing up for Abstractly. Choose a password here and you&rsquo;re in:",
        _email_button(setup_url, "Finish setting up your account"),
        "The link works for 72 hours, and only once. If you didn&rsquo;t sign up, "
        "you can ignore this email and nothing will happen.",
        _SIGN_OFF_HTML,
        _raw_link_note(setup_url),
    ])
    return _send(to_email, subject, text_body, html_body)


def send_account_exists_email(to_email: str, name: str, login_url: str, forgot_url: str) -> bool:
    """
    Sent instead of a signup link when someone signs up with an email
    that already has an account. The signup page shows the same "check
    your inbox" either way -- only the inbox's owner learns the account
    exists, which is exactly who should.
    """
    first = _greeting_name(name)
    subject = "You already have an Abstractly account"
    text_body = "\n".join([
        f"Hi {first},",
        "",
        "Someone (hopefully you) just tried to sign up for Abstractly with this "
        "email, but you already have an account. You can sign in here:",
        "",
        login_url,
        "",
        f"Forgot your password? Reset it here: {forgot_url}",
        "",
        "If this wasn't you, you can ignore this email. Nothing has changed.",
        "",
        *_SIGN_OFF_TEXT,
    ])
    html_body = _personal_email_html([
        f"Hi {html.escape(first)},",
        "Someone (hopefully you) just tried to sign up for Abstractly with this "
        "email, but you already have an account.",
        _email_button(login_url, "Sign in"),
        f'Forgot your password? <a href="{html.escape(forgot_url, quote=True)}" '
        'style="color:#17171a;">Reset it here</a>.',
        "If this wasn&rsquo;t you, you can ignore this email. Nothing has changed.",
        _SIGN_OFF_HTML,
    ])
    return _send(to_email, subject, text_body, html_body)


def send_password_reset_email(to_email: str, reset_url: str, name: str = "") -> bool:
    """
    Sent when someone uses "Forgot password?" on a login page. The URL
    carries a single-use, one-hour token (see
    database.create_password_reset_token). Never reveals whether the
    address actually has an account -- the route that calls this
    returns the same generic response either way, and only calls this
    at all for a real, active user.
    """
    first = _greeting_name(name)
    subject = "Reset your Abstractly password"
    text_body = "\n".join([
        f"Hi {first},",
        "",
        "Here's the link to choose a new password:",
        "",
        reset_url,
        "",
        "It works for 1 hour, and only once. If you didn't ask for this, you can "
        "ignore this email. Your password won't change.",
        "",
        *_SIGN_OFF_TEXT,
    ])
    html_body = _personal_email_html([
        f"Hi {html.escape(first)},",
        "Here&rsquo;s the link to choose a new password:",
        _email_button(reset_url, "Choose a new password"),
        "It works for 1 hour, and only once. If you didn&rsquo;t ask for this, you can "
        "ignore this email. Your password won&rsquo;t change.",
        _SIGN_OFF_HTML,
        _raw_link_note(reset_url),
    ])
    return _send(to_email, subject, text_body, html_body)


def send_password_changed_email(to_email: str, name: str, forgot_url: str) -> bool:
    """
    Security notice after a password reset: if it wasn't them, they
    find out now instead of the next time they can't sign in. Every
    other session was signed out as part of the reset (see
    database.update_user_password), so it says so.
    """
    first = _greeting_name(name)
    subject = "Your Abstractly password was changed"
    text_body = "\n".join([
        f"Hi {first},",
        "",
        "Your Abstractly password was just changed, and any other devices "
        "signed in to your account were signed out.",
        "",
        "If that was you, you're all set. If it wasn't, reset your password "
        f"right away ({forgot_url}) and reply to this email so I can help.",
        "",
        *_SIGN_OFF_TEXT,
    ])
    html_body = _personal_email_html([
        f"Hi {html.escape(first)},",
        "Your Abstractly password was just changed, and any other devices "
        "signed in to your account were signed out.",
        "If that was you, you&rsquo;re all set. If it wasn&rsquo;t, "
        f'<a href="{html.escape(forgot_url, quote=True)}" style="color:#17171a;">reset your password</a> '
        "right away and reply to this email so I can help.",
        _SIGN_OFF_HTML,
    ])
    return _send(to_email, subject, text_body, html_body)


def send_team_setup_email(to_email: str, name: str, firm_name: str, setup_url: str) -> bool:
    """
    Sent when the owner creates a new team via POST /owner/teams. The
    URL carries a single-use, 7-day token (see
    database.create_password_reset_token -- reused as-is for this
    longer-lived "first login" flow, not just forgot-password) that the
    invited admin uses to set their own password -- the owner never
    sees or sets it. If sending fails (or isn't configured), the caller
    falls back to showing the raw URL in the owner console for manual
    sharing -- this function's return value is exactly that signal.
    """
    subject = f"You're set up on Abstractly, {name}"
    text_body = (
        f"Hi {name},\n\n"
        f"An Abstractly workspace for {firm_name} is ready. Set your password "
        f"to finish setting up your login (this link expires in 7 days and can "
        f"only be used once):\n{setup_url}\n\n"
        "Best,\nTim Pisano"
    )
    html_body = _email_html(
        heading=f"You're set up on Abstractly, {name}.",
        paragraphs=[
            f"An Abstractly workspace for {firm_name} is ready.",
            f'<a href="{setup_url}" style="color:{_COLOR_ACCENT};">Set your password</a> '
            "to finish setting up your login &mdash; this link expires in 7 days "
            "and can only be used once.",
        ],
    )
    return _send(to_email, subject, text_body, html_body)


def _personal_email_html(paragraphs) -> str:
    """
    Reads like a normal email from a person, not a branded template: white
    background, no card, no heading, no logo, ordinary body text, left
    aligned. Fluid up to 560px so it fits a phone without zooming; inline
    styles only (email clients ignore most stylesheets).
    """
    paragraphs_html = "".join(
        f'<p style="margin:0 0 16px;">{p}</p>' for p in paragraphs
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#ffffff;">
  <div style="max-width:560px;padding:24px 20px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.55;color:#222222;">
    {paragraphs_html}
  </div>
</body>
</html>"""


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
