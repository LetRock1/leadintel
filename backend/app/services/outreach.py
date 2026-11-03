"""
Every marketing email the CRM sends goes through here: automatic next-best-action emails, campaigns,
A/B tests and emails written by a person on the team.

* It respects the person's "do not email" choice.
* The button opens the course the person looked at, on our own website: ``<site>/courses/<slug>?ref=<token>``.
  The course page reports the click itself (``POST /api/v1/email/click``), so the link works from any device
  that can open the website, and the click is tied to that exact email.
* Every email has a working one-click unsubscribe link (``<site>/unsubscribe?t=<token>``) and the
  List-Unsubscribe headers.

Where the links point: PUBLIC_SITE_URL in backend/.env (for example http://192.168.1.5:5173, so a phone on the
same Wi-Fi can open them); by default http://localhost:5173, which works on this computer.
"""

from __future__ import annotations

import logging
import threading
import uuid

from app import db
from app.core.config import get_settings
from app.services import catalog, mailer
from app.services.content import TEAM_SIGNATURE, speaker
from app.services.mailer import send_marketing_email

log = logging.getLogger(__name__)

SITE_URL = get_settings().public_site_url


def course_url(slug: str | None = None) -> str:
    return f"{SITE_URL}/courses/{slug}" if slug and catalog.get_course(slug) else f"{SITE_URL}/courses"


def tracked_link(token: str, slug: str | None = None) -> str:
    """The email's button: the course page itself, carrying the email's token."""
    return f"{course_url(slug)}?ref={token}"


def unsubscribe_link(token: str) -> str:
    return f"{SITE_URL}/unsubscribe?t={token}"


def lead_slug(lead: dict) -> str | None:
    """The course a contact record is about (older records stored only the title)."""
    return lead.get("course_slug") or catalog.slug_for_title(lead.get("course_type"))


def personalise(text: str | None, name: str | None, slug: str | None, sender: str | None = None) -> str:
    """Fill {first_name}, {name} and {course}; {my_name} is the person on the team who sends it (else the team)."""
    first = (name or "there").split()[0]
    text = (
        (text or "")
        .replace("{first_name}", first)
        .replace("{name}", name or first)
        .replace("{course}", catalog.title_of(slug, "our programmes"))
    )
    return speaker(text, sender) if sender else text.replace("{my_name}", TEAM_SIGNATURE)


def send_tracked_email(
    user_id: int,
    lead_id: int | None,
    to_email: str,
    subject: str,
    body: str,
    course_slug: str | None = None,
    cta_label: str = "View course",
    campaign_id: int | None = None,
    campaign_name: str | None = None,
    ab_test_id: int | None = None,
    variant: str = "A",
    adoption: tuple[int, str] | None = None,
) -> tuple[bool, str]:
    """Record and send one marketing email. adoption: (adopted email id, 'adopted' | 'check'), see adopted.py."""
    profile = db.get_profile(user_id) or {}
    if profile.get("do_not_email") == "Yes":
        log.info("Email skipped for user %s: they opted out of email", user_id)
        return False, "User opted out of emails"
    token = uuid.uuid4().hex
    db.execute(
        """INSERT INTO email_sends (lead_id, user_id, campaign_id, campaign_name, ab_test_id, variant,
                  adoption_id, adoption_arm, token, subject, body) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            lead_id,
            user_id,
            campaign_id,
            campaign_name,
            ab_test_id,
            variant,
            adoption[0] if adoption else None,
            adoption[1] if adoption else None,
            token,
            subject,
            body,
        ),
    )
    ok, msg = send_marketing_email(
        to_email,
        subject,
        body,
        cta_url=tracked_link(token, course_slug),
        cta_label=cta_label,
        unsubscribe_url=unsubscribe_link(token),
    )
    if not ok:  # kept, marked as not sent: the team sees why, and a campaign can send it again
        db.execute("UPDATE email_sends SET error=? WHERE token=?", (msg[:300], token))
    elif lead_id:
        db.execute("UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE id=?", (lead_id,))
    return ok, msg


def send_again(row: dict, course_slug: str | None, cta_label: str = "View course") -> tuple[bool, str]:
    """Send an email that could not be sent before (same token, so its links and its place in an experiment stay)."""
    profile = db.get_profile(row["user_id"]) or {}
    if profile.get("do_not_email") == "Yes":
        db.execute("UPDATE email_sends SET error=? WHERE id=?", ("They have opted out of emails since", row["id"]))
        return False, "User opted out of emails"
    user = db.get_user_by_id(row["user_id"])
    if not user:
        return False, "The account was deleted"
    ok, msg = send_marketing_email(
        user["email"],
        row["subject"],
        row["body"],
        cta_url=tracked_link(row["token"], course_slug),
        cta_label=cta_label,
        unsubscribe_url=unsubscribe_link(row["token"]),
    )
    if ok:
        db.execute(
            """UPDATE email_sends SET error=NULL, sent_at=datetime('now','localtime'),
                      attempts=COALESCE(attempts, 1) + 1 WHERE id=?""",
            (row["id"],),
        )
    else:
        db.execute(
            "UPDATE email_sends SET error=?, attempts=COALESCE(attempts, 1) + 1 WHERE id=?", (msg[:300], row["id"])
        )
    return ok, msg


RETRY_HOURS = 24
RETRY_ATTEMPTS = 6
# one sender of failed emails at a time (the every-10-minutes job and a campaign's "send again" share the API's one
# process), so no email goes out twice
resend_lock = threading.Lock()


def retry_failed(limit: int = 200) -> dict:
    """Every 10 minutes: emails the mail server did not take (no connection, a daily limit) are tried again, for a
    day and at most six times in all. Nothing is tried while sending is paused after a network error, and never to
    someone who has opted out of emails since."""
    if mailer.paused() or not mailer.configured():
        return {"tried": 0, "sent": 0}
    if not resend_lock.acquire(blocking=False):
        return {"tried": 0, "sent": 0}  # a campaign is sending its failed emails again right now
    try:
        return _retry_failed(limit)
    finally:
        resend_lock.release()


def _retry_failed(limit: int) -> dict:
    rows = db.fetchall(
        """SELECT es.id, es.user_id, es.token, es.subject, es.body, es.lead_id FROM email_sends es
           JOIN users u ON u.id = es.user_id
           LEFT JOIN user_profiles up ON up.user_id = es.user_id
           WHERE es.error IS NOT NULL AND COALESCE(es.attempts, 1) < ?
             AND es.sent_at >= datetime('now','localtime', ?) AND COALESCE(up.do_not_email, 'No') != 'Yes'
           ORDER BY es.id LIMIT ?""",
        (RETRY_ATTEMPTS, f"-{RETRY_HOURS} hours", limit),
    )
    sent = 0
    for r in rows:
        if mailer.paused():  # the server went away again: the next run goes on
            break
        lead = db.fetchone("SELECT course_slug, course_type FROM leads WHERE id=?", (r["lead_id"],)) or {}
        ok, _ = send_again(r, lead_slug(lead))
        sent += 1 if ok else 0
    if rows:
        log.info("Emails tried again: %d of %d sent", sent, len(rows))
    return {"tried": len(rows), "sent": sent}
