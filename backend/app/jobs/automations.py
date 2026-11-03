"""
The automatic follow-ups. Every few minutes the CRM looks for learners who left something unfinished and lets
next-best-action decide, for each one, whether to do anything at all (and what):

    checkout left    a checkout page was opened and nothing was bought
    cart left        a course sat in the cart
    wishlist         a course was saved to the wishlist a while ago
    visit ended      a visit ended (no activity for a while) without any of the above

Strongest signal first, so the weaker jobs see the fresh contact record and skip the person (cool-downs in
crm_settings.json). Timings differ between demo mode (minutes) and live mode.
"""

from __future__ import annotations

import logging

from app import db
from app.core import rules
from app.services.playbook import handle_trigger

log = logging.getLogger(__name__)

_COOL = rules.S["cooldown_hours"]
_MIN = rules.by_mode("automation_minutes")
VISIT_ENDED_MINUTES = _MIN["visit_ended"]
CART_MINUTES = _MIN["cart_abandoned"]
WISHLIST_MINUTES = _MIN["wishlist"]
CHECKOUT_MINUTES = _MIN["checkout_abandoned"]
EVERY_MINUTES = _MIN["job_every"]
# Touchpoints that count for cool-downs. "signup" is not one: creating the contact at sign-up sends nothing, so it
# must not block the first follow-up.
TOUCH_TRIGGERS = ("enquiry", "chat_callback", "cart_abandon", "checkout_abandon", "wishlist", "session_end", "manual")


def checkout_left() -> int:
    n = 0
    for item in db.get_abandoned_checkouts(CHECKOUT_MINUTES):
        user_id = item["user_id"]
        try:
            if not db.recent_lead_exists(user_id, "checkout_abandon", _COOL["checkout"]):
                cart = db.get_cart(user_id)
                handle_trigger(
                    user_id, item["name"], item["email"], "checkout_abandon", cart[0]["course_slug"] if cart else None
                )
                n += 1
        finally:
            db.mark_checkout_email_sent(item["checkout_id"])
    return n


def cart_left() -> int:
    n = 0
    for item in db.get_abandoned_carts(CART_MINUTES):
        user_id = item["user_id"]
        try:
            if not db.recent_lead_exists(user_id, ("cart_abandon", "checkout_abandon"), _COOL["cart"]):
                handle_trigger(user_id, item["name"], item["email"], "cart_abandon", item.get("course_slug"))
                n += 1
        finally:
            db.mark_cart_email_sent(item["cart_id"])  # one follow-up per cart item
    return n


def wishlist() -> int:
    """Information or a modest nudge, never the deepest discount."""
    n = 0
    for user in db.get_users_with_old_wishlist(WISHLIST_MINUTES):
        user_id = user["user_id"]
        if db.recent_lead_exists(user_id, ("wishlist", "cart_abandon", "checkout_abandon"), _COOL["wishlist"]):
            continue  # stays pending until the cool-down has passed
        handle_trigger(
            user_id,
            user["name"],
            user["email"],
            "wishlist",
            user.get("course_slug"),
            allowed=["none", "email_info", "email_coupon_10", "whatsapp"],
        )
        db.mark_wishlist_reminded(user_id)  # one reminder per wishlist item
        n += 1
    return n


def visit_ended() -> int:
    n = 0
    for user in db.get_inactive_users(VISIT_ENDED_MINUTES):
        user_id = user["user_id"]
        try:
            if db.recent_lead_exists(user_id, TOUCH_TRIGGERS, _COOL["visit"]):
                continue  # already covered by another touchpoint
            if db.get_purchases(user_id) and not db.get_cart(user_id):
                continue  # customers browsing their own course are not chased
            slug = db.get_behaviour_summary(user_id).get("top_course_slug")
            if not slug:
                continue  # nothing they looked at: nothing useful to say
            handle_trigger(user_id, user["name"], user["email"], "session_end", slug)
            n += 1
        finally:
            db.mark_visit_handled(user_id, user["session_id"])  # one decision per visit
    return n


def run_all() -> dict:
    """Every follow-up job once, strongest signal first. Returns how many decisions each made."""
    out = {}
    for name, job in (
        ("checkout_left", checkout_left),
        ("cart_left", cart_left),
        ("wishlist", wishlist),
        ("visit_ended", visit_ended),
    ):
        try:
            out[name] = job()
        except Exception:  # noqa: BLE001 - one job failing must not stop the rest
            log.exception("Automation '%s' failed", name)
            out[name] = None
    made = sum(v or 0 for v in out.values())
    if made:
        log.info("Automations made %d decision(s): %s", made, out)
    return out
