"""
Outbound email over SMTP (Gmail by default): sign-up and reset codes, marketing emails and receipts.

Without GMAIL_USER / GMAIL_APP_PASSWORD in backend/.env, nothing is sent and each email is written to the
log instead, so the project runs anywhere. Another mail server is set with SMTP_HOST, SMTP_PORT and SMTP_SECURITY
(``ssl``, ``starttls``, or ``none`` for a local relay that needs no password). Addresses on the reserved
``.test`` domain (simulated learners) are never mailed; their sign-up and reset codes are put in the
simulated_inbox table, where the simulator reads them. A network failure pauses sending for five minutes, so an
offline demo does not wait ten seconds on every email; a refused address or a wrong password does not pause the
others.
"""

from __future__ import annotations

import html as _html
import logging
import re
import smtplib
import sqlite3
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

log = logging.getLogger(__name__)

_cfg = get_settings()
GMAIL_USER = _cfg.gmail_user
GMAIL_PASS = (_cfg.gmail_app_password or "").replace(" ", "").strip()
SMTP_SECURITY = (_cfg.smtp_security or "ssl").strip().lower()
if SMTP_SECURITY not in ("ssl", "starttls", "none"):
    log.error("SMTP_SECURITY must be ssl, starttls or none (not %r): using ssl", SMTP_SECURITY)
    SMTP_SECURITY = "ssl"
SMTP_HOST = (_cfg.smtp_host or "smtp.gmail.com").strip()
SMTP_PORT = int(_cfg.smtp_port or (465 if SMTP_SECURITY == "ssl" else 587))
SERVER = "Gmail" if SMTP_HOST == "smtp.gmail.com" else "The mail server"
BRAND = "X Education"
BRAND_FOOTER = "X Education, Mumbai, India"
SMTP_TIMEOUT_SECONDS = 10
PAUSE_AFTER_NETWORK_ERROR = 300
_paused_until = {"t": 0.0}

# colours of the email template (the same brand colours as the website)
INK, MUTED, LINE, CANVAS, BRAND_COLOR = "#1F2430", "#5B6170", "#E3E5EA", "#F5F6F8", "#5B2C83"


NOT_CONFIGURED = "Recorded (configure Gmail in backend/.env to send it)"


def configured() -> bool:
    """True when email is set up in backend/.env, so emails and sign-up codes are really sent (a local relay with
    SMTP_SECURITY=none needs only the sender's address)."""
    return bool(GMAIL_USER and (GMAIL_PASS or SMTP_SECURITY == "none"))


def paused() -> bool:
    """True for a few minutes after the mail server could not be reached (nothing is tried until then)."""
    return time.time() < _paused_until["t"]


def paused_until() -> float:
    return _paused_until["t"]


def mailer_not_configured(message: str) -> bool:
    """True when _send only recorded the email because Gmail is not set up."""
    return message == NOT_CONFIGURED


def is_simulated_address(to: str | None) -> bool:
    """Addresses on the reserved .test domain belong to simulated learners: they are never mailed."""
    return (to or "").strip().lower().endswith(".test")


def _to_simulated_inbox(to: str, subject: str, body: str) -> None:
    from app import db

    try:
        db.execute(
            "INSERT INTO simulated_inbox (email, subject, body) VALUES (?,?,?)", (to.strip().lower(), subject, body)
        )
    except sqlite3.Error:
        log.warning("Could not put an email in the simulated inbox of %s", to, exc_info=True)


def _send(to: str, subject: str, body: str, html: str | None = None, headers: dict | None = None) -> tuple[bool, str]:
    if is_simulated_address(to):
        log.info("Email recorded, not sent (simulated learner): %s / %s", to, subject)
        return True, "Simulated learner: recorded, not sent"
    if not configured():
        log.info("Email recorded, not sent (Gmail not configured): %s / %s", to, subject)
        return True, NOT_CONFIGURED
    if time.time() < _paused_until["t"]:
        log.warning("Email not sent (%s was unreachable a moment ago): %s / %s", SERVER, to, subject)
        return False, "Email is paused for a few minutes after a network error"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{BRAND} <{GMAIL_USER}>"
        msg["To"] = to
        for k, v in (headers or {}).items():
            msg[k] = v
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))
        if SMTP_SECURITY == "ssl":
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
        with server as s:
            if SMTP_SECURITY == "starttls":
                s.starttls()
            if GMAIL_PASS:
                s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to, msg.as_string())
        return True, f"Sent to {to}"
    except smtplib.SMTPAuthenticationError:
        log.error("%s refused the login: check GMAIL_USER and GMAIL_APP_PASSWORD in backend/.env", SERVER)
        return False, f"{SERVER} refused the login (check the app password in backend/.env)"
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as e:
        return _network_error(e)
    except smtplib.SMTPException as e:  # e.g. one address refused: no reason to pause the others
        log.error("Email to %s failed: %s: %s", to, type(e).__name__, e)
        return False, str(e)
    except OSError as e:  # no internet, DNS failure, timeout
        return _network_error(e)
    except Exception as e:  # noqa: BLE001 - an email problem must never fail the request that sent it
        log.exception("Email to %s failed", to)
        return False, str(e)


def _network_error(e: Exception) -> tuple[bool, str]:
    _paused_until["t"] = time.time() + PAUSE_AFTER_NETWORK_ERROR
    log.error(
        "%s could not be reached (%s: %s); email paused for %d minutes",
        SERVER,
        type(e).__name__,
        e,
        PAUSE_AFTER_NETWORK_ERROR // 60,
    )
    return False, f"Could not reach {SERVER.lower() if SERVER != 'Gmail' else SERVER} ({type(e).__name__})"


def _shell(title: str, inner_html: str, footer_extra: str = "") -> str:
    """The one HTML layout every email uses: brand bar, white card, quiet footer."""
    return f"""<!doctype html><html><body style="margin:0;background:{CANVAS};padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;
  font-family:'IBM Plex Sans','Segoe UI',Arial,sans-serif;color:{INK}">
<tr><td style="background:{BRAND_COLOR};padding:18px 28px;border-radius:10px 10px 0 0">
  <span style="color:#FFFFFF;font-size:18px;font-weight:600">{BRAND}</span>
  <span style="color:#E7DDF2;font-size:13px;padding-left:10px">{_html.escape(title)}</span></td></tr>
<tr><td style="background:#FFFFFF;padding:28px;border:1px solid {LINE};border-top:none;border-radius:0 0 10px 10px;
  font-size:15px;line-height:1.65">{inner_html}</td></tr>
<tr><td style="padding:16px 8px;color:{MUTED};font-size:12px;text-align:center">{BRAND_FOOTER}{footer_extra}</td></tr>
</table></td></tr></table></body></html>"""


def send_otp_email(to: str, otp: str, name: str, purpose: str = "signup") -> tuple[bool, str]:
    minutes = get_settings().otp_expiry_minutes
    if purpose == "reset":
        subject, intro = f"Your {BRAND} password reset code: {otp}", "Use this code to reset your password"
    else:
        subject, intro = f"Your {BRAND} verification code: {otp}", "Your verification code is"
    body = (
        f"Hi {name},\n\n{intro}:\n\n  {otp}\n\nThis code expires in {minutes} minutes. Do not share it with "
        f"anyone.\nIf you did not request it, you can ignore this email.\n\nThe {BRAND} team"
    )
    inner = (
        f'<p style="margin:0 0 12px">Hi {_html.escape(name)}, {intro.lower()}:</p>'
        f'<p style="font-size:34px;font-weight:600;letter-spacing:8px;margin:18px 0;color:{INK}">{otp}</p>'
        f'<p style="color:{MUTED};font-size:13px;margin:0">It expires in {minutes} minutes. '
        f"Do not share this code with anyone.</p>"
    )
    if is_simulated_address(to):
        _to_simulated_inbox(to, subject, body)
    return _send(to, subject, body, _shell("Account security", inner))


# The website's checkout is a demonstration: the receipt says so, so nobody takes it for a real payment.
DEMO_PAYMENT_NOTE = "This site takes no real payments: nothing was charged."

# A lead's trigger_reason as the attribution line of the purchase receipt (the touchpoint that reached them).
ATTRIBUTION_LABELS = {
    "cart_abandon": "your cart reminder email",
    "session_end": "a follow-up after your last visit",
    "wishlist": "your wishlist email",
    "checkout_abandon": "your checkout reminder email",
    "behaviour_snapshot": "your browsing on our website",
    "enquiry": "your course enquiry",
    "campaign": "one of our email campaigns",
    "ab_test": "one of our email campaigns",
    "manual_send": "an email from our admissions team",
    "next_best_action": "a personal follow-up from our team",
    "chat_callback": "your callback request",
    "manual": "a personal follow-up from our admissions team",
    "email_click": "an email you opened",
    "decay": "your ongoing interest on our website",
    None: f"your visit to {BRAND}",
}


def send_purchase_confirmation_email(
    to: str, name: str, courses: list, channel_label: str, total_paid: float, discount_pct: int = 0
) -> tuple[bool, str]:
    course_list = ", ".join(courses)
    subject = f"Enrolment confirmed: {course_list}"
    discount_note = f" (after a {discount_pct}% discount)" if discount_pct else ""
    body = (
        f"Hi {name},\n\nYour enrolment is confirmed for:\n\n  {course_list}\n\nAmount: Rs {total_paid:,.2f}"
        f"{discount_note}\n{DEMO_PAYMENT_NOTE}\n\nYou can open your courses any time from My learning on the "
        f"website.\n\nThe {BRAND} team"
    )
    discount_html = f' <span style="color:#15803D">({discount_pct}% discount applied)</span>' if discount_pct else ""
    inner = (
        f'<p style="margin:0 0 12px">Hi {_html.escape(name)},</p>'
        f'<p style="margin:0 0 6px">Your enrolment is confirmed for:</p>'
        f'<p style="font-weight:600;font-size:17px;margin:0 0 16px">{_html.escape(course_list)}</p>'
        f'<p style="margin:0 0 6px"><strong>Amount:</strong> &#8377;{total_paid:,.2f}{discount_html}</p>'
        f'<p style="color:{MUTED};font-size:13px;margin:0 0 6px">{DEMO_PAYMENT_NOTE}</p>'
        f'<p style="color:{MUTED};font-size:13px;margin:16px 0 0">This enrolment is credited to '
        f"{_html.escape(channel_label)}. You can open your courses any time from My learning on the website.</p>"
    )
    return _send(to, subject, body, _shell("Enrolment confirmed", inner))


def _body_to_html(body: str) -> str:
    """Escape the text, turn **bold** into <strong>, keep line breaks."""
    safe = _html.escape(body or "")
    safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe, flags=re.S)
    return safe.replace("\n", "<br>")


def send_marketing_email(
    to: str,
    subject: str,
    body: str,
    cta_url: str | None = None,
    cta_label: str = "View course",
    unsubscribe_url: str | None = None,
) -> tuple[bool, str]:
    """A marketing email with a tracked call to action and a one-click unsubscribe (RFC 8058 headers)."""
    cta_html = (
        (
            f'<p style="margin:24px 0 4px"><a href="{_html.escape(cta_url)}" style="background:{BRAND_COLOR};'
            f"color:#FFFFFF;padding:11px 22px;border-radius:8px;text-decoration:none;font-weight:600;"
            f'display:inline-block">{_html.escape(cta_label)}</a></p>'
        )
        if cta_url
        else ""
    )
    unsub_html = (
        f' | <a href="{_html.escape(unsubscribe_url)}" style="color:{MUTED}">Unsubscribe</a>' if unsubscribe_url else ""
    )
    text = body
    if cta_url:
        text += f"\n\n{cta_label}: {cta_url}"
    if unsubscribe_url:
        text += f"\n\nDo not want these emails? Unsubscribe: {unsubscribe_url}"
    headers = {}
    if unsubscribe_url:
        headers["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    return _send(
        to,
        subject,
        text,
        _shell("Courses for working professionals", _body_to_html(body) + cta_html, unsub_html),
        headers,
    )


def send_simple_email(to: str, subject: str, body: str, title: str = f"A message from {BRAND}") -> tuple[bool, str]:
    """A transactional notification (for example: your question was answered)."""
    return _send(to, subject, body, _shell(title, _body_to_html(body)))
