"""
What the website reports while a learner uses it: visits, page and step events, "still here" pings,
and the email links (click and unsubscribe). Every event re-scores the person at once.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status

from app import db
from app.api.deps import Learner
from app.core import perf
from app.ml import features as F
from app.schemas.learner import BehaviourEvent, EmailToken, SessionPing, SessionStart
from app.services.scoring import rescore_latest_lead

router = APIRouter(tags=["Learner activity"])

TRACKED_EVENTS = {
    "page_view",
    "video_play",
    "brochure_dl",
    "chat",
    "pricing_view",
    "testimonial_view",
    "webinar_view",
    "webinar_register",
    "cart_add",
    "wishlist_add",
    "checkout_start",
    "enquiry_submit",
}
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


@router.post("/session/start", summary="Start a visit (a new tab, or after 30 minutes idle)")
def start_session(body: SessionStart, user: Learner):
    device = body.device_type if body.device_type in F.DEVICE_TYPES else "Desktop"
    source = body.lead_source if body.lead_source in F.LEAD_SOURCES else "Direct Traffic"
    sid = db.execute(
        "INSERT INTO user_sessions (user_id, device_type, lead_source) VALUES (?,?,?)", (user["id"], device, source)
    )
    return {"session_id": sid}


@router.post("/session/ping", summary="Still here (every 30 s while the page is in use)")
def session_ping(body: SessionPing, user: Learner):
    """Nothing is recorded as an event; only the visit's last-active time moves, so the CRM does not mistake a
    long read for a visit that has ended (its 'visit ended' follow-up waits until the learner has really left)."""
    db.execute(
        "UPDATE user_sessions SET last_active=datetime('now','localtime') WHERE id=? AND user_id=?",
        (body.session_id, user["id"]),
    )
    return {"ok": True}


@router.post("/track", summary="Record one event and re-score the learner")
def track_event(body: BehaviourEvent, user: Learner):
    if body.event_type not in TRACKED_EVENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown event type '{body.event_type}'")
    # a visit id from another account (a stale browser tab) must not be counted
    sess = db.fetchone("SELECT id FROM user_sessions WHERE id=? AND user_id=?", (body.session_id, user["id"]))
    session_id = sess["id"] if sess else None
    seconds = max(0, min(int(body.time_spent_sec or 0), 1800))  # at most 30 minutes per page
    db.execute(
        """INSERT INTO behaviour_events (user_id, session_id, course_slug, event_type, time_spent_sec)
                  VALUES (?,?,?,?,?)""",
        (user["id"], session_id, body.course_slug, body.event_type, seconds),
    )
    if session_id:
        db.execute("UPDATE user_sessions SET last_active=datetime('now','localtime') WHERE id=?", (session_id,))
    # re-score live; a snapshot for the learning loop is kept at most every 30 minutes
    with perf.timer("event_to_score"):
        _, pred = rescore_latest_lead(user["id"], "activity", snapshot_gap_minutes=30)
    return {
        "tracked": True,
        "live_score": pred["lead_score"],
        "persona": pred["persona"],
        "tier": pred["recommended_action"],
    }


# Every marketing email's button opens <site>/courses/<slug>?ref=<token>: the course the person looked at, on our
# own website. The page reports the click here, signed in or not (the token identifies the email).
@router.post("/email/click", summary="An email's button was opened (reported by the course page)")
def email_click(body: EmailToken):
    token = (body.token or "").strip().lower()
    if not TOKEN_RE.match(token):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid link.")
    send = db.get_email_send_by_token(token)
    if not send:
        return {"ok": False, "message": "Unknown email link."}
    first = not send.get("first_clicked_at")
    db.execute(
        """UPDATE email_sends SET click_count = click_count + 1, open_count = open_count + 1,
                  opened_at = COALESCE(opened_at, datetime('now','localtime')),
                  first_clicked_at = COALESCE(first_clicked_at, datetime('now','localtime'))
                  WHERE token=?""",
        (token,),
    )
    if send.get("user_id"):
        rescore_latest_lead(send["user_id"], "email_click")
    return {"ok": True, "first_click": first}


@router.post("/email/unsubscribe", summary="One-click unsubscribe from marketing emails")
def email_unsubscribe(body: EmailToken):
    token = (body.token or "").strip().lower()
    send = db.get_email_send_by_token(token) if TOKEN_RE.match(token) else None
    if not send or not send.get("user_id"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This unsubscribe link is not valid any more.")
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (send["user_id"],))
    db.execute("UPDATE user_profiles SET do_not_email='Yes' WHERE user_id=?", (send["user_id"],))
    return {"ok": True, "message": "You have been unsubscribed from X Education marketing emails."}
