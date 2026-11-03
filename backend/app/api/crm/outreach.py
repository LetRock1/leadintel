"""Emails and WhatsApp messages written by the team, the email coach, and personal coupons."""

from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, status

from app import db
from app.api.deps import Marketing, Member
from app.core.errors import NotFound
from app.schemas.crm import CouponRequest, ImproveRequest, SendEmailRequest, WhatsAppRequest
from app.services import catalog, coach, lifecycle, money
from app.services import team as T
from app.services.content import personal_suffix
from app.services.outreach import lead_slug, personalise, send_tracked_email

router = APIRouter(tags=["CRM outreach"])


def _wa_number(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        digits = "91" + digits  # an Indian mobile number without the country code
    return digits if 11 <= len(digits) <= 15 else None


@router.post("/emails", summary="Send an email written on the lead page")
def send_email(body: SendEmailRequest, me: Member):
    lead = db.fetchone(
        "SELECT l.*, u.email, u.name FROM leads l JOIN users u ON l.user_id = u.id WHERE l.id=?", (body.lead_id,)
    )
    if not lead:
        raise NotFound("Lead not found")
    lifecycle.require_change(me, lead["user_id"], lead["email"])
    if not body.subject.strip() or not body.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Subject and message are required.")
    slug = lead_slug(lead)
    ok, msg = send_tracked_email(
        lead["user_id"],
        body.lead_id,
        lead["email"],
        personalise(body.subject, lead["name"], slug, me["name"]),
        personalise(body.body, lead["name"], slug, me["name"]),
        course_slug=slug,
    )
    if ok:
        T.audit(me, "email_sent", "person", lead["user_id"], "email written on the lead page")
    return {"success": ok, "message": msg}


@router.post("/emails/improve", summary="Check or rewrite a draft (Gemini when configured, else rule-based)")
def improve_email(body: ImproveRequest, _: Member):
    slug = body.course_slug or catalog.slug_for_title(body.course)
    out = coach.improve(body.subject, body.draft, body.name, body.tier, slug, body.occupation)
    out["note"] = (
        "Rewritten by Gemini: review it before sending."
        if out["engine"] == "gemini"
        else "Checked by the rule-based email coach (set GEMINI_API_KEY in backend/.env for rewriting)."
    )
    return out


@router.post("/whatsapp", summary="Open WhatsApp with the message for this lead (click-to-chat)")
def whatsapp_link(body: WhatsAppRequest, me: Member):
    lead = db.fetchone(
        """SELECT l.*, u.name, u.email, up.phone, up.whatsapp_opt_in FROM leads l
                          JOIN users u ON l.user_id = u.id LEFT JOIN user_profiles up ON up.user_id = l.user_id
                          WHERE l.id=?""",
        (body.lead_id,),
    )
    if not lead:
        raise NotFound("Lead not found")
    lifecycle.require_change(me, lead["user_id"], lead["email"])
    if not lead.get("whatsapp_opt_in"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This lead has not opted in to WhatsApp messages.")
    number = _wa_number(lead.get("phone"))
    if not number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No valid phone number on this lead's profile.")
    text = personalise(body.message, lead["name"], lead_slug(lead), me["name"])
    db.execute(
        "INSERT INTO sms_queue (user_id, lead_id, phone, message, status, channel) VALUES (?,?,?,?,?,?)",
        (lead["user_id"], body.lead_id, number, text, "opened", "whatsapp"),
    )
    T.audit(me, "whatsapp_opened", "person", lead["user_id"])
    return {
        "url": f"https://wa.me/{number}?text={quote(text)}",
        "message": "WhatsApp opened with the message. Press send there.",
    }


@router.get("/whatsapp/log", summary="WhatsApp messages opened from the CRM")
def whatsapp_log(_: Marketing, limit: int = Query(200, ge=1, le=2000)):
    return {"messages": db.fetchall("SELECT * FROM sms_queue ORDER BY created_at DESC LIMIT ?", (limit,))}


@router.get("/coupons/check", summary="The coupon guard: what a personal coupon would do for this learner")
def check_coupon(_: Marketing, user_id: int, discount_pct: int = Query(..., ge=5, le=50)):
    try:
        return money.coupon_check(user_id, discount_pct)
    except LookupError:
        raise NotFound("Learner not found") from None


@router.post("/coupons", summary="Give one learner a personal coupon (the coupon guard checks it first)")
def create_coupon(body: CouponRequest, me: Marketing):
    if not 5 <= body.discount_pct <= 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The discount must be between 5% and 50%.")
    if not 1 <= body.expires_hours <= 720:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The expiry must be between 1 hour and 30 days.")
    if not db.fetchone("SELECT id FROM users WHERE id=?", (body.user_id,)):
        raise NotFound("Learner not found")
    guard = money.coupon_check(body.user_id, body.discount_pct)
    if guard["verdict"] in ("control", "has_coupon"):  # never, even when confirmed
        raise HTTPException(status.HTTP_409_CONFLICT, guard["message"])
    if not guard["allowed"] and guard["verdict"] != "customer" and not body.override:
        raise HTTPException(status.HTTP_409_CONFLICT, guard["message"] + " Confirm to give it anyway.")
    code = f"XE{body.discount_pct}-{personal_suffix()}"
    db.execute(
        """INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, expires_at, expected_cost, source)
                  VALUES (?,?,?,?,datetime('now','localtime',?),?,'manual')""",
        (
            body.user_id,
            code,
            body.discount_pct,
            body.tier,
            f"+{body.expires_hours} hours",
            guard.get("expected_discount"),
        ),
    )
    T.audit(
        me,
        "coupon_created",
        "person",
        body.user_id,
        f"{body.discount_pct}% for {body.expires_hours} h" + (" (guard overridden)" if not guard["allowed"] else ""),
    )
    money.reset_cache()
    return {
        "coupon_code": code,
        "discount_pct": body.discount_pct,
        "guard": guard,
        "message": f"Personal coupon {code} ({body.discount_pct}% off for {body.expires_hours} hours) assigned.",
    }


@router.get("/coupons", summary="Every coupon issued, newest first, with the true totals")
def list_coupons(
    _: Member,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    show: str = Query("all", pattern="^(all|used|open)$", description="all, used, or open (not used yet)"),
):
    """One page of coupons (newest first) and the counts over all of them, so the page never reports the size of a
    page as the number of coupons."""
    where = {"all": "", "used": " WHERE ci.used = 1", "open": " WHERE COALESCE(ci.used, 0) = 0"}[show]
    issued = "FROM coupons_issued ci JOIN users u ON ci.user_id = u.id"
    counts = db.fetchone(f"SELECT COUNT(*) AS n, COALESCE(SUM(ci.used = 1), 0) AS used {issued}") or {}
    total = db.fetchone(f"SELECT COUNT(*) AS n {issued}{where}") or {}
    return {
        "coupons": db.fetchall(
            f"SELECT ci.*, u.name, u.email {issued}{where} ORDER BY ci.created_at DESC, ci.id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ),
        "total": int(total.get("n") or 0),
        "all": int(counts.get("n") or 0),
        "used": int(counts.get("used") or 0),
    }


@router.delete("/coupons/{coupon_id}", summary="Withdraw a coupon")
def delete_coupon(coupon_id: int, me: Marketing):
    c = db.fetchone("SELECT id, user_id, discount_pct, used FROM coupons_issued WHERE id=?", (coupon_id,))
    if not c:
        raise NotFound("Coupon not found")
    if c["used"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This coupon was used for a purchase and is kept.")
    db.execute("DELETE FROM coupons_issued WHERE id=?", (coupon_id,))
    T.audit(me, "coupon_deleted", "person", c["user_id"], f"coupon #{coupon_id} ({c['discount_pct']}%)")
    return {"message": "Coupon withdrawn."}
