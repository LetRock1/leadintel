"""Cart, wishlist, coupons, checkout and enquiries. Prices always come from the server's catalogue."""

from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app import db
from app.api.deps import Learner
from app.ml import features as F
from app.schemas.learner import CartItem, CheckoutRequest, CouponCheck, EnquiryRequest, WishlistItem
from app.services import catalog, mailer, money
from app.services.mailer import ATTRIBUTION_LABELS, send_purchase_confirmation_email
from app.services.playbook import handle_trigger
from app.services.scoring import rescore_latest_lead

router = APIRouter(tags=["Cart and checkout"])
PHONE_RE = re.compile(r"^\+?[0-9][0-9 -]{8,14}$")


def _course_or_404(slug: str) -> dict:
    course = catalog.get_course(slug)
    if not course:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found.")
    return course


@router.get("/cart", summary="The learner's cart")
def get_cart(user: Learner):
    return {"cart": db.get_cart(user["id"])}


@router.post("/cart", summary="Add a course to the cart")
def add_to_cart(item: CartItem, user: Learner):
    course = _course_or_404(item.course_slug)
    if db.fetchone("SELECT id FROM purchases WHERE user_id=? AND course_slug=?", (user["id"], item.course_slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already enrolled in this course.")
    db.execute(
        "INSERT OR IGNORE INTO cart (user_id, course_slug, course_title, price) VALUES (?,?,?,?)",
        (user["id"], course["slug"], course["title"], course["price"]),
    )
    db.execute(
        "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
        (user["id"], item.course_slug, "cart_add"),
    )
    return {"message": f"{course['title']} added to your cart."}


@router.delete("/cart/{course_slug}", summary="Remove a course from the cart")
def remove_from_cart(course_slug: str, user: Learner):
    db.execute("DELETE FROM cart WHERE user_id=? AND course_slug=?", (user["id"], course_slug))
    return {"message": "Removed from your cart."}


@router.get("/wishlist", summary="The learner's wishlist")
def get_wishlist(user: Learner):
    return {"wishlist": db.get_wishlist(user["id"])}


@router.post("/wishlist", summary="Save a course to the wishlist")
def add_to_wishlist(item: WishlistItem, user: Learner):
    course = _course_or_404(item.course_slug)
    db.execute(
        "INSERT OR IGNORE INTO wishlist (user_id, course_slug, course_title) VALUES (?,?,?)",
        (user["id"], course["slug"], course["title"]),
    )
    db.execute(
        "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
        (user["id"], item.course_slug, "wishlist_add"),
    )
    return {"message": f"{course['title']} saved to your wishlist."}


@router.delete("/wishlist/{course_slug}", summary="Remove a course from the wishlist")
def remove_from_wishlist(course_slug: str, user: Learner):
    db.execute("DELETE FROM wishlist WHERE user_id=? AND course_slug=?", (user["id"], course_slug))
    return {"message": "Removed from your wishlist."}


def _cart_total(user_id: int) -> float:
    return sum(catalog.price_of(i["course_slug"]) or i["price"] for i in db.get_cart(user_id))


@router.post("/checkout/start", summary="The learner opened the checkout page")
def checkout_start(user: Learner):
    if not db.get_cart(user["id"]):
        return {"checkout_id": None, "cart_value": 0}  # nothing to abandon
    value = _cart_total(user["id"])
    return {"checkout_id": db.start_checkout_session(user["id"], value), "cart_value": value}


@router.post("/coupons/check", summary="Check a coupon before paying")
def check_coupon(body: CouponCheck, user: Learner):
    code = (body.code or "").strip().upper()
    coupon = db.validate_coupon(user["id"], code)
    if not coupon:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This code is not valid for your account, has expired or was already used."
        )
    total = _cart_total(user["id"])
    pct = coupon["discount_pct"]
    return {
        "code": code,
        "discount_pct": pct,
        "expires_at": coupon["expires_at"],
        "subtotal": total,
        "discount": round(total * pct / 100, 2),
        "total": round(total * (1 - pct / 100), 2),
    }


@router.post("/checkout", summary="Pay for the cart (simulated payment: nothing is charged)")
def checkout(body: CheckoutRequest, background: BackgroundTasks, user: Learner):
    cart = db.get_cart(user["id"])
    if not cart:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your cart is empty.")
    for item in cart:  # priced from the catalogue at the moment of purchase
        item["price"] = catalog.price_of(item["course_slug"]) or item["price"]
    code = (body.coupon_code or "").strip().upper()
    discount_pct, coupon_id = 0, None
    if code:
        coupon = db.validate_coupon(user["id"], code)
        if not coupon:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This coupon is not valid or has expired.")
        discount_pct, coupon_id = coupon["discount_pct"], coupon["id"]
    prior_lead = db.get_attribution_lead(user["id"])  # the last touch that reached the learner
    purchased, total_paid = [], 0.0
    with db.transaction() as con:  # all items, or none
        for item in cart:
            original = item["price"]
            paid = round(original * (1 - discount_pct / 100), 2)
            con.execute(
                """INSERT INTO purchases (user_id, course_slug, course_title, price_paid, coupon_used,
                           discount_amount) VALUES (?,?,?,?,?,?)""",
                (user["id"], item["course_slug"], item["course_title"], paid, code or None, round(original - paid, 2)),
            )
            con.execute(
                "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
                (user["id"], item["course_slug"], "purchase"),
            )
            purchased.append(item["course_title"])
            total_paid += paid
        con.execute("DELETE FROM cart WHERE user_id=?", (user["id"],))
        if coupon_id:
            con.execute(
                "UPDATE coupons_issued SET used=1, used_at=datetime('now','localtime') WHERE id=?", (coupon_id,)
            )
        con.execute("UPDATE checkout_sessions SET completed=1 WHERE user_id=? AND completed=0", (user["id"],))
        # they bought: their open call / WhatsApp tasks leave the team's list
        con.execute(
            """UPDATE sales_tasks SET status='skipped', outcome='bought before the task was done',
                       done_at=datetime('now','localtime') WHERE user_id=? AND status='open'""",
            (user["id"],),
        )
    # the purchase is the outcome the learning loop learns from: re-score the lead now
    _, pred = rescore_latest_lead(user["id"], "purchase_conversion")
    money.reset_cache()  # a customer leaves the open pipeline's totals at once
    channel_label = ATTRIBUTION_LABELS.get(
        prior_lead["trigger_reason"] if prior_lead else None, ATTRIBUTION_LABELS[None]
    )
    background.add_task(
        send_purchase_confirmation_email,
        user["email"],
        user["name"],
        purchased,
        channel_label,
        total_paid,
        discount_pct,
    )  # after the reply: nobody waits for Gmail
    return {
        "message": "You are enrolled. This site takes no real payments: nothing was charged.",
        "courses_purchased": purchased,
        "discount_applied": f"{discount_pct}%" if discount_pct else "None",
        "attributed_to": channel_label,
        "updated_lead_score": pred["lead_score"],
        "demo_payment": True,  # the payment is simulated: nothing is charged and no card details are asked
        # a confirmation goes out only when email is set up (and never to a simulated learner's .test address)
        "confirmation_emailed": mailer.configured() and not mailer.is_simulated_address(user["email"]),
    }


@router.get("/purchases", summary="The learner's enrolments")
def get_purchases(user: Learner):
    return {"purchases": db.get_purchases(user["id"])}


@router.post("/enquiry", summary="Ask about a course (always confirmed by email)")
def submit_enquiry(body: EnquiryRequest, user: Learner):
    """An enquiry always gets a confirmation email; next-best-action decides whether it carries a coupon or
    whether a counsellor should call."""
    course = _course_or_404(body.course_slug)
    if body.phone:
        if not PHONE_RE.match(body.phone.strip()):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter a valid phone number.")
        db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
        db.execute(
            "UPDATE user_profiles SET phone=?, whatsapp_opt_in=? WHERE user_id=?",
            (body.phone.strip(), 1 if body.whatsapp_opt_in else 0, user["id"]),
        )
    if body.lead_source and body.lead_source != "Direct Traffic" and body.lead_source in F.LEAD_SOURCES:
        db.execute(
            "UPDATE user_sessions SET lead_source=? WHERE id=(SELECT MAX(id) FROM user_sessions WHERE user_id=?)",
            (body.lead_source, user["id"]),
        )
    db.execute(
        "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
        (user["id"], body.course_slug, "enquiry_submit"),
    )
    lead_id, prediction, _ = handle_trigger(
        user["id"],
        user["name"],
        user["email"],
        "enquiry",
        course["slug"],
        allowed=["email_info", "email_coupon_10", "email_coupon_20", "call"],
        always_email=True,
    )
    return {
        "lead_id": lead_id,
        "lead_score": prediction["lead_score"],
        "persona": prediction["persona"],
        "action": prediction["recommended_action"],
        "message": "Enquiry sent. Check your email for the next steps.",
    }
