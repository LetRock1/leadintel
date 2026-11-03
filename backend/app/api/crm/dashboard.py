"""The dashboard's numbers: headline counts, trends, forecast, model health, next-best-action and call capacity."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import db
from app.api.deps import Marketing, Member
from app.ml import capacity
from app.services import analytics, leads
from app.services import team as T

router = APIRouter(tags=["CRM dashboard"])


@router.get("/stats", summary="Headline numbers")
def stats(_: Member):
    return analytics.stats()


@router.get("/stats/daily", summary="Sign-ups, purchases and revenue per day")
def daily(_: Member, days: int = Query(30, ge=7, le=365)):
    return analytics.daily_series(days)


@router.get("/forecast", summary="Revenue to expect from open leads, with a 90% range")
def forecast(_: Member):
    return analytics.forecast()


@router.get("/priority-queue", summary="Open leads with the highest expected value")
def priority_queue(_: Member, limit: int = Query(20, ge=1, le=200)):
    return {"priority_queue": leads.priority_queue(limit)}


@router.get("/model/health", summary="Calibration of the lead score on people whose outcome is known")
def model_health(_: Member, window_days: int = Query(analytics.WINDOW_DAYS, ge=1, le=90)):
    return analytics.model_health(window_days)


@router.get("/nba/performance", summary="How well next-best-action is doing (off-policy estimates)")
def nba_performance(_: Member, window_days: int = Query(analytics.WINDOW_DAYS, ge=1, le=90)):
    return analytics.nba_performance(window_days)


@router.get("/campaign-influence", summary="Emails, clicks and purchases after a click, per kind of email")
def campaign_influence(_: Member):
    return analytics.campaign_influence()


@router.get("/capacity", summary="What a call slot is worth right now (capacity-aware next-best-action)")
def call_capacity(_: Member):
    return capacity.current()


@router.post("/automations/run", summary="Run every automatic follow-up now instead of waiting for the timer")
def run_automations(me: Marketing):
    from app.jobs import automations

    T.audit(me, "automations_run")
    last = db.fetchone("SELECT COALESCE(MAX(id), 0) AS m FROM nba_decisions")["m"]
    by_job = automations.run_all()
    made = db.fetchall(
        """SELECT d.trigger_reason, d.action, d.policy, u.name FROM nba_decisions d
                          JOIN users u ON u.id = d.user_id WHERE d.id > ? ORDER BY d.id""",
        (last,),
    )
    return {"message": f"Automations ran: {len(made)} new decision(s).", "decisions": made, "by_job": by_job}
