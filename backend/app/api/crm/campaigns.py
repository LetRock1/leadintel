"""Campaigns, A/B tests and the A/B winners the CRM adopted."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Marketing, Member
from app.core import rules
from app.schemas.crm import AbTestRequest, ApplyRequest, CampaignRequest
from app.services import abtests, campaigns
from app.services import team as T

router = APIRouter(tags=["CRM campaigns and A/B tests"])
AB = rules.S["ab_testing"]
WINDOW_DAYS = int(rules.S["outcome_window_days"])


# campaigns
@router.get("/campaigns", summary="Every campaign with its delivery and its effect against the hold-out group")
def list_campaigns(_: Member):
    return {
        "campaigns": campaigns.report(),
        "audiences": campaigns.AUDIENCES,
        "default_holdout_share": rules.S["campaigns"]["holdout_share"],
        "window_days": WINDOW_DAYS,
    }


@router.post("/campaigns", summary="Schedule a campaign")
def schedule_campaign(body: CampaignRequest, me: Marketing):
    out = campaigns.schedule(body.name, body.tier, body.subject, body.body, body.scheduled_at, body.holdout_share)
    T.audit(
        me,
        "campaign_scheduled",
        "campaign",
        out["id"],
        f"'{body.name.strip()[:80]}' for {body.tier} at {out['scheduled_at']}",
    )
    return {
        "id": out["id"],
        "message": f"Campaign '{body.name.strip()}' scheduled for {out['scheduled_at']} "
        f"({out['audience_now']} recipient(s) right now).",
    }


@router.post("/campaigns/{campaign_id}/send-now", summary="Send a campaign now")
def send_campaign_now(campaign_id: int, me: Marketing):
    n = campaigns.send_now(campaign_id)
    T.audit(me, "campaign_sent", "campaign", campaign_id, f"sent now to {n} recipient(s)")
    return {"message": f"Sent to {n} recipient(s)."}


@router.post("/campaigns/{campaign_id}/send-failed", summary="Send the emails the mail server did not take, again")
def send_campaign_failed_again(campaign_id: int, me: Marketing):
    out = campaigns.send_failed_again(campaign_id)
    T.audit(me, "campaign_resent", "campaign", campaign_id, f"{out['sent']} sent again, {out['still_failed']} not")
    if out["still_failed"]:
        reason = f" ({out['error']})" if out["error"] else ""
        return {**out, "message": f"Sent {out['sent']}; {out['still_failed']} still could not be sent{reason}."}
    return {**out, "message": f"Sent all {out['sent']} again."}


@router.delete("/campaigns/{campaign_id}", summary="Delete a campaign that has not been sent")
def delete_campaign(campaign_id: int, me: Marketing):
    camp = campaigns.delete(campaign_id)
    T.audit(me, "campaign_deleted", "campaign", campaign_id, f"'{(camp['name'] or '')[:80]}'")
    return {"message": "Campaign deleted."}


# A/B tests
@router.get("/ab-tests", summary="Every A/B test with its verdict")
def list_tests(_: Member):
    return {
        "ab_tests": abtests.listing(),
        "settings": {k: AB[k] for k in ("control_share", "alpha", "power", "min_detectable_effect", "max_variants")},
        "window_days": WINDOW_DAYS,
    }


@router.get("/ab-tests/plan", summary="How many people a test needs, and how many the audience gives")
def plan_test(
    _: Member,
    tier: str = "All leads",
    metric: str = "purchase",
    variants: int = Query(2, ge=1, le=3),
    control_share: float | None = Query(None, ge=0, le=0.5),
    mde: float | None = Query(None, gt=0, le=0.5),
):
    cs = AB["control_share"] if control_share is None else control_share
    return abtests.plan(tier, metric, variants, cs, mde or AB["min_detectable_effect"])


@router.post("/ab-tests", summary="Create an A/B test (a draft until it is sent)")
def create_test(body: AbTestRequest, me: Marketing):
    out = abtests.create(
        body.name,
        body.tier,
        body.hypothesis,
        body.metric,
        body.control_share,
        body.mde,
        [v.model_dump() for v in body.variants],
    )
    T.audit(
        me,
        "ab_test_created",
        "ab_test",
        out["id"],
        f"'{body.name.strip()[:80]}' for {body.tier}, {out['variants']} variants",
    )
    return {
        "id": out["id"],
        "message": f"A/B test '{body.name.strip()}' created.",
        "plan": out["plan"],
        "warning": out["warning"],
    }


@router.post("/ab-tests/{test_id}/send", summary="Send an A/B test")
def send_test(test_id: int, me: Marketing):
    from app.ml import experiments as X

    counts = abtests.send(test_id)
    parts = ", ".join(f"{X.ARM_LABELS.get(k, k)} {n}" for k, n in counts.items())
    T.audit(me, "ab_test_sent", "ab_test", test_id, parts)
    return {"message": f"A/B test sent: {parts}. Results are final after {WINDOW_DAYS} days.", "counts": counts}


@router.get("/ab-tests/{test_id}/results", summary="Results of one A/B test (or its plan, for a draft)")
def test_results(test_id: int, _: Member):
    return abtests.results(test_id)


@router.post("/ab-tests/{test_id}/apply", summary="Turn a variant into a campaign draft")
def apply_winner(test_id: int, body: ApplyRequest, me: Marketing):
    out = abtests.apply_winner(test_id, body.variant, body.tier)
    T.audit(
        me,
        "ab_winner_applied",
        "ab_test",
        test_id,
        f"variant {body.variant} to campaign draft #{out['campaign_id']} for {out['tier']}",
    )
    return {
        "campaign_id": out["campaign_id"],
        "message": f"Campaign draft created for {out['tier']}: open Campaigns to schedule or send it.",
    }


@router.delete("/ab-tests/{test_id}", summary="Delete a draft A/B test")
def delete_test(test_id: int, me: Marketing):
    test = abtests.delete(test_id)
    T.audit(me, "ab_test_deleted", "ab_test", test_id, f"draft '{(test['name'] or '')[:80]}'")
    return {"message": "Draft deleted."}


# adopted winners
@router.get("/adoptions", summary="A/B winners in use as the standard email, and how their check is going")
def list_adoptions(_: Member):
    return {
        "adoptions": abtests.adoption_rows(),
        "auto_adopt": bool(AB.get("auto_adopt", True)),
        "check_share": float(AB.get("adoption_check_share", 0.10)),
    }


@router.post("/adoptions/check", summary="Run the adoption check now")
def check_adoptions(_: Marketing):
    return {"changes": abtests.adoption_job(), "adoptions": abtests.adoption_rows()}


@router.post("/adoptions/{adoption_id}/revert", summary="Switch back to the old standard email")
def revert_adoption(adoption_id: int, me: Marketing):
    abtests.revert_adoption(adoption_id)
    T.audit(me, "adoption_reverted", "adoption", adoption_id)
    return {"ok": True}
