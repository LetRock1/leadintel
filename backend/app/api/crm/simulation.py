"""The simulated learners: what they did recently, pause and resume them, send one to the website now."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Marketing, Member
from app.core.errors import Conflict, Unavailable
from app.schemas.crm import SimSwitchRequest, SimVisitRequest
from app.services import team as T

router = APIRouter(prefix="/simulation", tags=["CRM simulated learners"])


@router.get("", summary="What the simulated learners did recently")
def status(_: Member):
    from app.simulation import live

    return live.get_world().status()


@router.post("/visit", summary="Send a simulated learner to the website now (or let a new one sign up)")
def visit(body: SimVisitRequest, _: Marketing):
    from app.simulation import live

    try:
        return live.get_world().visit_now(kind=body.kind)
    except live.Paused as e:
        raise Conflict(str(e)) from None
    except live.Offline as e:
        raise Unavailable(f"The website's API did not answer: {e}") from None


@router.post("/enabled", summary="Pause or resume the simulated learners")
def switch(body: SimSwitchRequest, me: Marketing):
    from app.simulation import live

    try:
        out = live.get_world().set_enabled(body.enabled)
    except live.Paused as e:
        raise Conflict(str(e)) from None
    T.audit(me, "simulation_" + ("resumed" if body.enabled else "paused"))
    return out
