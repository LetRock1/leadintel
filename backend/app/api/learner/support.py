"""The website's help assistant and call-back requests."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException, status

from app import db
from app.api.deps import Learner, OptionalLearner
from app.schemas.learner import CallbackRequest, ChatRequest
from app.services import assistant, catalog
from app.services.content import generate_content
from app.services.scoring import save_lead, score_user

router = APIRouter(tags=["Help and call-backs"])
PHONE_RE = re.compile(r"^\+?[0-9][0-9 -]{8,14}$")


@router.post("/chat", summary="Ask the website's help assistant")
def chat(body: ChatRequest, user: OptionalLearner):
    text = (body.message or "").strip()[:1000]
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please type a message.")
    conversation = body.conversation_id or uuid.uuid4().hex
    profile = db.get_profile(user["id"]) if user else None
    purchased = [p["course_slug"] for p in db.get_purchases(user["id"])] if user else []
    res = assistant.answer(text, page_slug=body.course_slug, profile=profile, user=user, purchased_slugs=purchased)
    uid = user["id"] if user else None
    for role, said in (("user", text), ("assistant", res["reply"])):
        db.execute(
            """INSERT INTO chat_messages (user_id, conversation, role, text, intent, course_slug)
                      VALUES (?,?,?,?,?,?)""",
            (uid, conversation, role, said, res["intent"], res["course_slug"]),
        )
    return {"conversation_id": conversation, **res}


@router.post("/callback", summary="Ask a counsellor to call back")
def request_callback(body: CallbackRequest, user: Learner):
    phone = (body.phone or "").strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter a valid phone number.")
    slug = body.course_slug if body.course_slug and catalog.get_course(body.course_slug) else None
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
    # asking for a call is consent to be called on this number
    db.execute(
        "UPDATE user_profiles SET phone=COALESCE(phone, ?), do_not_call='No' WHERE user_id=?", (phone, user["id"])
    )
    callback_id = db.execute(
        """INSERT INTO callback_requests (user_id, phone, course_slug, preferred_time, note)
                                VALUES (?,?,?,?,?)""",
        (user["id"], phone, slug, (body.preferred_time or "")[:60], (body.note or "")[:300]),
    )
    # an explicit, strong signal: recorded like an enquiry and scored at once
    db.execute(
        "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
        (user["id"], slug, "enquiry_submit"),
    )
    pred = score_user(user["id"], source="chat_callback", course=slug, explain=True)
    profile = db.get_profile(user["id"]) or {}
    content = generate_content(
        user["name"],
        profile.get("current_occupation"),
        profile.get("specialization"),
        catalog.title_of(slug, "our programmes"),
        pred["recommended_action"],
        trigger="chat_callback",
        lead_score=pred["lead_score"],
        course_slug=slug,
        offer_pct=0,
    )
    save_lead(user["id"], pred, content, "chat_callback", course_slug=slug)
    return {"callback_id": callback_id, "message": "Thanks. A counsellor will call you soon."}
