"""The learner's own account: profile, contact preferences, their dashboard, and deleting everything."""

from __future__ import annotations

import logging
import re
import sqlite3

from fastapi import APIRouter, HTTPException, status

from app import db
from app.api.deps import Learner
from app.schemas.learner import PreferencesRequest, ProfileRequest
from app.services.scoring import score_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["Learner profile and privacy"])

PHONE_RE = re.compile(r"^\+?[0-9][0-9 -]{8,14}$")


@router.get("/profile/options", summary="The choices the profile form offers (the lead model's own vocabulary)")
def profile_options():
    from app.ml import features as F

    def known(values):
        return [v for v in values if v != "Unknown"]

    return {
        "occupations": known(F.OCCUPATIONS),
        "specializations": known(F.SPECIALIZATIONS),
        "age_brackets": known(F.AGE_BRACKETS),
        "how_heard": known(F.HOW_HEARD),
    }


@router.post("/profile/complete", summary="Save the profile (occupation, specialisation, city, phone)")
def complete_profile(body: ProfileRequest, user: Learner):
    if body.phone and not PHONE_RE.match(body.phone.strip()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter a valid phone number.")
    db.execute(
        """
        INSERT INTO user_profiles (user_id, current_occupation, specialization, age_bracket, city, country, phone,
                                   how_did_you_hear, profile_complete)
        VALUES (?,?,?,?,?,?,?,?,1)
        ON CONFLICT(user_id) DO UPDATE SET
          current_occupation=excluded.current_occupation, specialization=excluded.specialization,
          age_bracket=excluded.age_bracket, city=excluded.city, country=excluded.country,
          phone=COALESCE(excluded.phone, user_profiles.phone), how_did_you_hear=excluded.how_did_you_hear,
          profile_complete=1, updated_at=datetime('now','localtime')""",
        (
            user["id"],
            body.current_occupation,
            body.specialization,
            body.age_bracket,
            body.city,
            body.country,
            (body.phone or "").strip() or None,
            body.how_did_you_hear,
        ),
    )
    return {"message": "Profile saved. Your course suggestions now use it."}


@router.put("/profile/preferences", summary="Contact preferences: email, calls, WhatsApp, phone number")
def update_preferences(body: PreferencesRequest, user: Learner):
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
    if body.do_not_email is not None:
        db.execute(
            "UPDATE user_profiles SET do_not_email=? WHERE user_id=?",
            ("Yes" if body.do_not_email else "No", user["id"]),
        )
    if body.do_not_call is not None:
        db.execute(
            "UPDATE user_profiles SET do_not_call=? WHERE user_id=?", ("Yes" if body.do_not_call else "No", user["id"])
        )
    if body.whatsapp_opt_in is not None:
        db.execute(
            "UPDATE user_profiles SET whatsapp_opt_in=? WHERE user_id=?", (1 if body.whatsapp_opt_in else 0, user["id"])
        )
    if body.phone is not None:
        phone = body.phone.strip()
        if phone and not PHONE_RE.match(phone):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter a valid phone number.")
        db.execute("UPDATE user_profiles SET phone=? WHERE user_id=?", (phone or None, user["id"]))
    return {"message": "Preferences saved.", "profile": db.get_profile(user["id"])}


@router.get("/dashboard", summary="Everything on the learner's own dashboard")
def learner_dashboard(user: Learner):
    from app.ml import recourse

    lead = db.get_user_lead(user["id"])
    return {
        "user": db.public_user(user),
        "profile": db.get_profile(user["id"]),
        "cart": db.get_cart(user["id"]),
        "wishlist": db.get_wishlist(user["id"]),
        "purchases": db.get_purchases(user["id"]),
        "coupons": db.fetchall("SELECT * FROM coupons_issued WHERE user_id=? AND used=0", (user["id"],)),
        "lead_score": lead["lead_score"] if lead else None,
        "persona": lead["persona"] if lead else None,
        "next_steps": recourse.learner_steps(user["id"]),
    }


@router.get("/coupons", summary="The learner's coupons")
def my_coupons(user: Learner):
    return {
        "coupons": db.fetchall("SELECT * FROM coupons_issued WHERE user_id=? ORDER BY created_at DESC", (user["id"],))
    }


@router.get("/me/insights", summary="What the CRM currently thinks about the signed-in learner (demo view)")
def my_insights(user: Learner):
    from app.ml import recourse

    pred = score_user(user["id"], source="insights", explain=True, snapshot_gap_minutes=60)
    return {
        "lead_score": pred["lead_score"],
        "persona": pred["persona"],
        "tier": pred["recommended_action"],
        "probability": pred["conversion_probability"],
        "factors": pred.get("factors", []),
        "model_version": pred["model_version"],
        "tips": recourse.tips_for(pred["features"], pred["lead_score"]),
    }


@router.get("/live-score", summary="The learner's current score")
def live_score(user: Learner):
    row = db.fetchone("SELECT live_score, persona FROM live_user_state WHERE user_id=?", (user["id"],))
    if row and row["live_score"] is not None:
        return {"lead_score": row["live_score"], "persona": row["persona"]}
    pred = score_user(user["id"], source="live_score", snapshot_gap_minutes=60)
    return {"lead_score": pred["lead_score"], "persona": pred["persona"]}


@router.delete("/me", summary="Delete the account and every record linked to it (right to erasure)")
def delete_my_account(user: Learner):
    """Deletes the person and everything linked to them: contact records, events, emails, decisions, purchases,
    tasks, notes, WhatsApp log, questions to the CRM assistant about them. Cannot be undone. The audit log keeps
    only numbers, so it stays."""
    con = db.get_conn()
    removed = 0
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            if "user_id" in cols and t != "users":
                removed += con.execute(f"DELETE FROM {t} WHERE user_id=?", (user["id"],)).rowcount
        con.execute("DELETE FROM otp_tokens WHERE email=?", (user["email"],))
        con.execute("DELETE FROM simulated_inbox WHERE email=?", (user["email"],))
        con.execute("DELETE FROM login_attempts WHERE email=?", ("learner:" + user["email"],))
        try:
            for v in {user["email"], (user.get("name") or "").strip()} - {""}:
                removed += con.execute(
                    """DELETE FROM copilot_log WHERE question LIKE ? OR answer LIKE ?
                                          OR tools_json LIKE ? OR drafts_json LIKE ?""",
                    (f"%{v}%",) * 4,
                ).rowcount
        except sqlite3.Error:
            pass
        con.execute("DELETE FROM users WHERE id=?", (user["id"],))
        con.commit()
    finally:
        con.close()
    from app.services import money

    money.reset_cache()  # they leave the pipeline's totals at once
    log.info("Deleted user %s and %d linked records at their request", user["id"], removed)
    return {"message": "Your account and all data linked to it have been deleted."}
