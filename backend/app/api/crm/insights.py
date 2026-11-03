"""The learning loop, customer journeys, the pipeline board, the Ask-the-CRM assistant and course questions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app import db
from app.api.deps import Admin, Marketing, Member
from app.core import perf
from app.core.errors import NotFound
from app.ml import journeys, learning
from app.schemas.crm import AnswerRequest, AskRequest, PlannerSettings, StageRequest
from app.services import analytics, catalog, copilot, gemini, leads, lifecycle, money, planner
from app.services import team as T
from app.services.mailer import send_simple_email
from app.services.outreach import course_url

router = APIRouter(tags=["CRM insights"])


# the learning loop
@router.get("/learning/overview", summary="Everything the Learning loop page shows")
def learning_overview(_: Member):
    return analytics.learning_overview()


@router.post("/learning/run", summary="Run the learning loop now")
def learning_run(me: Marketing, dry_run: bool = False):
    try:
        out = learning.run(reason="manual", force=True, dry_run=dry_run)
    except RuntimeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    out.pop("_new_live", None)
    T.audit(
        me,
        "learning_run",
        None,
        None,
        ("dry run" if dry_run else "retrain now")
        + (f": lead model {out.get('lead_decision')}" if out.get("lead_decision") else ""),
    )
    return out


@router.get("/latency", summary="Response times of the real-time loop (median and 95th percentile)")
def latency(_: Member):
    return perf.summary()


# journeys and the pipeline
@router.get("/journeys", summary="Lifecycle funnel, journey map, converting paths and drop-offs")
def journey_map(_: Member, days: int = Query(180, ge=7, le=3650), tier: str | None = None):
    return journeys.summary(days=days, tier=tier or None)


@router.get("/pipeline", summary="The pipeline board: every lead in its lifecycle stage")
def pipeline(
    me: Member,
    limit: int = Query(40, ge=1, le=500),
    search: str | None = Query(None, max_length=100),
    include_simulated: bool = True,
    owner: str | None = None,
    sort: str = Query("money", pattern="^(money|score)$"),
):
    member, unassigned = None, False
    if owner == "me":
        member = me["id"]
    elif owner == "unassigned":
        unassigned = True
    elif owner not in (None, "", "all"):
        try:
            member = int(owner)
        except ValueError:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "owner must be all, me, unassigned or a team member's number."
            ) from None
    with perf.timer("pipeline_board"):
        board = journeys.pipeline(
            limit=limit,
            search=search,
            include_simulated=include_simulated,
            owner_member=member,
            unassigned=unassigned,
            sort=sort,
        )
    for col in board.get("columns", []):
        leads.add_owner_names(col["cards"])
    board["owner"] = owner or "all"
    board["lost_reasons"] = T.get_settings().get("lost_reasons") or []
    return board


@router.put("/pipeline/{user_id}", summary="Move a lead to a stage by hand (Lost needs a reason)")
def move_card(user_id: int, body: StageRequest, me: Member):
    return lifecycle.set_stage(me, user_id, body.stage, body.note, body.reason)


@router.delete("/pipeline/{user_id}", summary="Back to automatic: the stage follows the learner's behaviour again")
def reset_card(user_id: int, me: Member):
    return lifecycle.reopen(me, user_id)


# the owner's planner
@router.get("/planner", summary="The month in rupees, what the team adds, what more counsellors or budget would add")
def planner_overview(_: Member):
    return planner.overview()


@router.put("/planner/settings", summary="The monthly discount budget and what a counsellor costs (admin)")
def planner_settings(body: PlannerSettings, me: Admin):
    planner.save_settings(body.monthly_discount_budget, body.counsellor_monthly_cost)
    T.audit(
        me,
        "planner_settings",
        None,
        None,
        "discount budget "
        + ("off" if body.monthly_discount_budget is None else f"{body.monthly_discount_budget:,.0f} a month")
        + (f"; counsellor {body.counsellor_monthly_cost:,.0f} a month" if body.counsellor_monthly_cost else ""),
    )
    return planner.overview()


@router.get("/money", summary="The open pipeline in rupees and the discount the coupon decisions kept this week")
def money_view(_: Member):
    return {"pipeline": money.totals(), "kept": money.kept()}


# Start here
@router.get("/start", summary="What the Start here page needs: is everything set up, and the rules it explains")
def start_here(_: Member):
    from app.core import rules
    from app.ml import budget, capacity, nba
    from app.services import mailer

    # learners who confirmed their address, as on the Overview (a sign-up without the code is not a learner yet)
    people = db.fetchone(
        """SELECT COUNT(*) AS n, COALESCE(SUM(email LIKE '%@demo.xeducation.test'), 0) AS simulated
             FROM users WHERE is_verified = 1"""
    )
    team = db.fetchone("SELECT COUNT(*) AS n FROM team_members WHERE active = 1")
    return {
        "email_sending": mailer.configured(),
        "gemini": gemini.enabled(),
        "team_members": int(team["n"] or 0),
        "learners": {"real": int(people["n"] - people["simulated"]), "simulated": int(people["simulated"])},
        "rules": {
            "control_share": float(rules.S["global_control"]["share"]),
            "learning_steps": float(nba.EXPLORE_RATE),
            "daily_calls": capacity.capacity(),
            "outcome_window_days": int(rules.S["outcome_window_days"]),
        },
        "discount_budget": budget.monthly_budget(),
    }


# Ask the CRM
@router.post("/copilot", summary="Ask a question about the CRM's live data (answers only from the data)")
def ask(body: AskRequest, _: Member):
    if not (body.question or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ask a question.")
    return copilot.ask(body.question)


@router.get("/copilot", summary="Suggested questions, the data tools and recent questions")
def copilot_info(_: Member):
    return {
        "suggestions": copilot.SUGGESTIONS,
        "tools": copilot.TOOLS,
        "gemini": gemini.enabled(),
        "recent": copilot.recent(10),
    }


# questions on course pages
@router.get("/qna", summary="Unanswered questions from course pages")
def unanswered(_: Member):
    return {
        "questions": db.fetchall("""SELECT q.*, u.name AS user_name FROM qna q JOIN users u ON q.user_id = u.id
                                        WHERE q.answer IS NULL ORDER BY q.created_at DESC""")
    }


@router.post("/qna/answer", summary="Answer a question (published on the course page and emailed)")
def answer(body: AnswerRequest, me: Member):
    text = (body.answer or "").strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The answer cannot be empty.")
    q = db.fetchone(
        "SELECT q.*, u.email, u.name FROM qna q JOIN users u ON q.user_id = u.id WHERE q.id=?", (body.qna_id,)
    )
    if not q:
        raise NotFound("Question not found")
    db.execute("UPDATE qna SET answer=?, answered_at=datetime('now','localtime') WHERE id=?", (text, body.qna_id))
    T.audit(me, "question_answered", "question", body.qna_id)
    first = (q["name"] or "").split()[0] if q["name"] else "there"
    send_simple_email(
        q["email"],
        f"Your question about {catalog.title_of(q['course_slug'])} was answered",
        f"Hi {first},\n\nYou asked: {q['question']}\n\nOur answer: {text}\n\nSee it on the course page: "
        f"{course_url(q['course_slug'])}\n\nThe X Education team",
        title="Your question was answered",
    )
    return {"message": "Answer published and emailed to the learner."}
