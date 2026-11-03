"""Leads: the list, one person's page, what the CRM would do now, and what the team changes by hand."""

from __future__ import annotations

import csv
import io
import json
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app import db
from app.api.deps import Marketing, Member
from app.core.errors import NotFound
from app.ml import nba, paths
from app.ml import nba_core as N
from app.schemas.crm import ActRequest, ConsentRequest, NoteRequest, OwnerRequest, StatusRequest
from app.services import leads, lifecycle, money
from app.services import team as T
from app.services.playbook import handle_trigger
from app.services.scoring import rescore_latest_lead

router = APIRouter(tags=["CRM leads"])
_act_lock = threading.Lock()

DONE_TEXT = {
    "email_info": "Information email sent",
    "email_coupon_10": "Email with a 10% coupon sent",
    "email_coupon_20": "Email with a 20% coupon sent",
    "call": "Call task added to Today's actions",
    "whatsapp": "WhatsApp task added to Today's actions",
}


def _user_of(lead_id: int) -> int:
    row = db.fetchone("SELECT user_id FROM leads WHERE id=?", (lead_id,))
    if not row:
        raise NotFound("Lead not found")
    return row["user_id"]


@router.get("/leads", summary="Leads, one row per person")
def list_leads(
    me: Member,
    tier: str | None = None,
    search: str | None = Query(None, max_length=100),
    sort: str | None = None,
    segment: str = "all",
    owner: str | None = None,
    limit: int = Query(300, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    return leads.list_leads(
        me, tier=tier, search=search, sort=sort, segment=segment, limit=limit, owner=owner, offset=offset
    )


@router.get("/leads/export.csv", summary="Every lead as CSV (one row per person)")
def export_leads(me: Marketing):
    rows = leads.export_rows()
    T.audit(me, "leads_exported", None, None, f"{len(rows)} people (CSV)")
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    name = f"leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"}
    )


@router.get("/leads/{lead_id}", summary="One person's page (any of their records opens their current state)")
def lead_page(lead_id: int, me: Member):
    return leads.lead_page(lead_id, me)


@router.get("/leads/{lead_id}/now", summary="What the CRM would do for this person right now (nothing is sent)")
def lead_now(lead_id: int, _: Member):
    user_id = _user_of(lead_id)
    out = nba.recommend_now(user_id)
    if out is None:
        raise NotFound("Lead not found")
    out.pop("features", None)
    out["recent"] = nba.recent_steps(user_id)  # steps that cannot be taken by hand again yet, and why
    return out


@router.post("/leads/{lead_id}/act", summary="Take one step now (logged like an automatic decision)")
def lead_act(lead_id: int, body: ActRequest, me: Member):
    user_id, email = leads.person_of_lead(lead_id)
    lifecycle.require_change(me, user_id, email)
    user = db.get_user_by_id(user_id)
    if body.action not in N.ACTIONS or body.action == "none":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a step to take (an email, a call or WhatsApp).")
    now = nba.recommend_now(user_id)
    if not now or now.get("recommendation") is None:
        raise HTTPException(status.HTTP_409_CONFLICT, (now or {}).get("message") or "Nothing to do for this person.")
    if now["control_group"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This person is in the control group: the CRM never contacts "
            "them, so their outcome shows what happens without us. "
            "Contacting them by hand would spoil that check.",
        )
    with _act_lock:  # two clicks at the same moment: the second one sees the first step
        again = nba.recent_steps(user_id).get(body.action)
        if again:  # the same email twice in a row, or a second call while the first is still waiting
            raise HTTPException(status.HTTP_409_CONFLICT, again)
        try:
            new_lead, _, decision = handle_trigger(
                user_id, user["name"], user["email"], "manual", now["course"]["slug"], force_action=body.action
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    T.audit(me, "step_taken", "person", user_id, f"by hand: {body.action}")
    money.reset_cache()  # the pipeline shows the person's next best step at once
    act = decision["action"]
    return {
        "ok": True,
        "message": DONE_TEXT.get(act, "Done"),
        "action": act,
        "lead_id": new_lead,
        "decision_id": decision["decision_id"],
        "model_pick": decision["model_best"],
        "why": decision["why"],
    }


@router.get("/leads/{lead_id}/attribution", summary="The person's timeline, first touch and last touch before buying")
def attribution(lead_id: int, _: Member):
    return leads.attribution(lead_id)


@router.get("/leads/{lead_id}/explain", summary="Why this score: what each signal added or took away")
def explain(lead_id: int, _: Member):
    lead = db.fetchone("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise NotFound("Lead not found")
    try:
        factors = json.loads(lead.get("score_factors") or "[]") or []
    except ValueError:
        factors = []
    score, version, note = lead["lead_score"], lead.get("model_version"), None
    now = nba.recommend_now(lead["user_id"])  # fresh reasons from the current model
    if now and now.get("recommendation") is None:  # a customer: the score is not about them any more
        factors, note = [], now.get("message")
    elif now and now.get("factors"):
        factors, score, version = now["factors"], now.get("score", score), now.get("lead_model") or version
    if not factors and not note:
        note = "No reasons yet: the person has not done anything on the website."
    return {
        "lead_id": lead_id,
        "lead_score": score,
        "recommended_action": lead["recommended_action"],
        "model_version": version,
        "factors": factors,
        "note": note,
    }


@router.post("/leads/{lead_id}/rescore", summary="Score this lead again with the current model")
def rescore(lead_id: int, _: Member):
    user_id = _user_of(lead_id)
    lead, pred = rescore_latest_lead(user_id, "manual_rescore")
    return {
        "user_id": user_id,
        "lead_id": lead["id"] if lead else None,
        "lead_score": pred["lead_score"],
        "tier": pred["recommended_action"],
    }


@router.get("/leads/{lead_id}/paths", summary="What-if paths: each step now, the likely reaction, the best follow-up")
def lead_paths(lead_id: int, _: Member, depth: int = Query(2, ge=2, le=3)):
    out = paths.plan(_user_of(lead_id), depth=depth)
    if out is None:
        raise NotFound("Lead not found")
    return out


@router.put("/leads/{lead_id}/owner", summary="Give the lead to someone on the team (or take an unassigned one)")
def set_owner(lead_id: int, body: OwnerRequest, me: Member):
    user_id, _ = leads.person_of_lead(lead_id)
    return lifecycle.set_owner(me, user_id, body.member_id)


@router.post("/leads/{lead_id}/notes", summary="Add a note to the lead")
def add_note(lead_id: int, body: NoteRequest, me: Member):
    user_id, email = leads.person_of_lead(lead_id)
    lifecycle.require_change(me, user_id, email)
    return {"note": lifecycle.new_note(me, user_id, body.text, body.kind)}


@router.delete("/notes/{note_id}", summary="Delete a note (its author or an admin)")
def delete_note(note_id: int, me: Member):
    lifecycle.delete_note(me, note_id)
    return {"message": "Note deleted."}


@router.post("/leads/{lead_id}/status", summary="Close the lead as lost (with a reason), or re-open it")
def set_status(lead_id: int, body: StatusRequest, me: Member):
    user_id, _ = leads.person_of_lead(lead_id)
    if body.status == "lost":
        return lifecycle.set_stage(me, user_id, "Lost", body.note, body.reason)
    if body.status == "open":
        return lifecycle.reopen(me, user_id)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Status must be lost or open.")


@router.post("/leads/{lead_id}/consent", summary="Record that the person does not want emails, calls or WhatsApp")
def record_consent(lead_id: int, body: ConsentRequest, me: Member):
    """The team can only switch contact off; switching it on again is the person's own choice, in their settings on
    the website."""
    user_id, email = leads.person_of_lead(lead_id)
    lifecycle.require_change(me, user_id, email)
    label = lifecycle.record_consent(me, user_id, body.channel)
    return {"message": f"Recorded: {label}. The CRM will not use this channel for them."}
