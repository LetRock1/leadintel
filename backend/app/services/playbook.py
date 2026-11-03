"""
What happens when a trigger fires (cart left, checkout left, wishlist, visit ended, enquiry, by hand):

    score the lead -> record a contact record -> next-best-action decides -> carry it out
    (an email with or without a coupon, or a call / WhatsApp task for the team) -> log everything,
    so the outcome can be learned from.

The uplift model decides whether to contact at all, how, and whether a discount is worth it; 15% of
decisions are random so the CRM keeps learning which steps really work (see nba.py).
"""

import logging
import time

from app import db
from app.core import perf
from app.ml import nba
from app.services import adopted as AD
from app.services import catalog
from app.services.content import generate_content
from app.services.outreach import send_tracked_email
from app.services.scoring import save_lead, score_user

log = logging.getLogger(__name__)


def handle_trigger(
    user_id, name, email, trigger, course_slug=None, allowed=None, always_email=False, force_action=None
):
    """Returns (lead_id, prediction, decision). force_action: a step chosen by hand ("Do it now" on the lead
    page, trigger 'manual'); it is carried out and logged exactly like an automatic one."""
    started = time.perf_counter()
    profile = db.get_profile(user_id) or {}
    pred = score_user(user_id, source=trigger, course=course_slug, explain=True)
    decision = nba.decide(user_id, trigger, pred, course_slug=course_slug, allowed=allowed, force_action=force_action)
    action = decision["action"]
    title = catalog.title_of(course_slug, "our programmes") if course_slug else "our programmes"
    is_email = action.startswith("email")

    content = generate_content(
        name=name,
        occupation=profile.get("current_occupation"),
        specialization=profile.get("specialization"),
        course=title,
        action=("Target Immediately" if action == "call" else pred["recommended_action"]),
        trigger=trigger,
        past_purchases=pred["raw"]["past_purchases"],
        lead_score=pred["lead_score"],
        course_slug=course_slug,
        offer_pct=nba.offer_pct(action) if is_email else 0,
    )
    # an adopted A/B winner replaces the standard information email (check group keeps the old one)
    adoption = AD.current_for(pred["recommended_action"]) if action == "email_info" else None
    arm = prob = None
    if adoption:
        arm, prob = AD.arm(adoption, user_id)
        if arm == "adopted":
            first = (name or "").split()[0] if name else None
            content["email_subject"] = AD.personalise(adoption["subject"], first, title)
            content["email_body"] = AD.personalise(adoption["body"], first, title)
    chosen = next((o for o in decision["options"] if o["action"] == action), {})
    coupon_cost = chosen.get("expected_discount") if action in ("email_coupon_10", "email_coupon_20") else None
    lead_id = save_lead(user_id, pred, content, trigger, course_slug=course_slug, coupon_cost=coupon_cost)
    nba.attach_to_lead(lead_id, decision)
    if adoption:
        AD.record(
            adoption,
            user_id,
            lead_id,
            arm,
            prob,
            tier=pred["recommended_action"],
            occupation=profile.get("current_occupation"),
            device=pred["features"].get("DeviceType"),
            source=pred["features"].get("LeadSource"),
        )

    if is_email or always_email:
        ok, _ = send_tracked_email(
            user_id,
            lead_id,
            email,
            content["email_subject"],
            content["email_body"],
            course_slug=course_slug,
            adoption=(adoption["id"], arm) if adoption else None,
        )
        if ok and is_email:
            nba.mark_executed(decision["decision_id"])
    if action in ("call", "whatsapp"):
        verb = "Call" if action == "call" else "WhatsApp"
        nba.create_task(
            user_id,
            lead_id,
            decision,
            f"{verb} {name} about {title}",
            content.get("call_script") if action == "call" else content.get("whatsapp_message"),
        )
    perf.record("trigger_to_action", (time.perf_counter() - started) * 1000)
    log.info(
        "Decision for user %s at '%s': score %.0f, %s (%s)",
        user_id,
        trigger,
        pred["lead_score"],
        decision["label"],
        decision["policy"],
    )
    return lead_id, pred, decision
