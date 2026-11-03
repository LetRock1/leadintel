"""Today's actions (call and WhatsApp tasks) and call-back requests from the website."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Member
from app.schemas.crm import CallbackDone, CallRequest, TaskDone
from app.services import tasks

router = APIRouter(tags=["CRM today's actions"])


@router.get("/actions", summary="Call and WhatsApp tasks: open ones by expected extra profit, closed ones by date")
def list_actions(
    me: Member,
    status: str = "open",
    segment: str = "all",
    owner: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
):
    return tasks.list_tasks(me, status=status, segment=segment, owner=owner, limit=limit)


@router.post("/actions/{task_id}/done", summary="Record what happened on a call or WhatsApp to a real person")
def complete(task_id: int, body: TaskDone, me: Member):
    return tasks.complete(task_id, me, body.outcome, body.note)


@router.post("/actions/{task_id}/call", summary="Call a simulated learner (the simulator answers)")
def call_simulated(task_id: int, me: Member, body: CallRequest | None = None):
    return tasks.call_simulated(task_id, me, body.note if body else None)


@router.get("/callbacks", summary="Call-back requests from the website")
def list_callbacks(me: Member, status: str = "open", owner: str | None = None):
    return tasks.list_callbacks(me, status=status, owner=owner)


@router.post("/callbacks/{callback_id}/done", summary="Mark a call-back request as done")
def close_callback(callback_id: int, me: Member, body: CallbackDone | None = None):
    tasks.close_callback(callback_id, me, body.note if body else None)
    return {"message": "Marked as done."}
