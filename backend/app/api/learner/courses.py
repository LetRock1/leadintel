"""The course catalogue, personal recommendations, reviews and questions on course pages."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app import db
from app.api.deps import Learner
from app.schemas.learner import QuestionRequest, ReviewRequest
from app.services import catalog
from app.services.recommendations import recommend

router = APIRouter(tags=["Courses"])


@router.get("/courses", summary="Every course (titles, prices and facts come from the server)")
def list_courses():
    return {"courses": catalog.all_courses()}


FAQ_QUESTIONS = {
    "schedule": "Can I study while I work?",
    "certificate": "Do I get a certificate?",
    "placement": "Do you guarantee a job?",
    "payment": "How do I pay?",
    "refund": "Can I get my money back?",
    "webinar": "What is the free live session?",
}


@router.get("/faq", summary="Answers to common questions (the same text the help assistant uses)")
def faq():
    answers = catalog.faq()
    return {
        "faq": [{"key": k, "question": q, "answer": answers[k]} for k, q in FAQ_QUESTIONS.items() if answers.get(k)]
    }


@router.get("/courses/{slug}", summary="One course")
def course_detail(slug: str):
    c = catalog.get_course(slug)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return c


@router.get("/recommendations", summary="Courses for the signed-in learner")
def recommendations(user: Learner):
    profile = db.get_profile(user["id"]) or {}
    behaviour = db.get_behaviour_summary(user["id"])
    purchased = [p["course_slug"] for p in db.get_purchases(user["id"])]
    viewed = ([behaviour["top_course_slug"]] if behaviour.get("top_course_slug") else []) + [
        w["course_slug"] for w in db.get_wishlist(user["id"])
    ]
    co = {}  # what else did buyers of my courses buy?
    if purchased:
        q = ",".join("?" * len(purchased))
        for r in db.fetchall(
            f"""SELECT p2.course_slug, COUNT(DISTINCT p2.user_id) AS n
                                 FROM purchases p1 JOIN purchases p2 ON p1.user_id=p2.user_id
                                 WHERE p1.course_slug IN ({q}) AND p2.course_slug NOT IN ({q}) AND p1.user_id != ?
                                 GROUP BY p2.course_slug""",
            (*purchased, *purchased, user["id"]),
        ):
            co[r["course_slug"]] = r["n"]
    items = recommend(
        profile.get("current_occupation"),
        profile.get("specialization"),
        viewed,
        purchased,
        co_purchase=co,
        cart_slugs=[c["course_slug"] for c in db.get_cart(user["id"])],
    )
    return {"recommendations": [i["title"] for i in items], "items": items}


def _public_name(name: str | None) -> str:
    """'Riya Sharma' is shown as 'Riya S.' on public pages."""
    parts = (name or "").split()
    if not parts:
        return "A learner"
    return parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")


@router.get("/reviews/{course_slug}", summary="Reviews of a course (by enrolled learners only)")
def get_reviews(course_slug: str):
    return {
        "reviews": [
            {
                "id": r["id"],
                "rating": r["rating"],
                "review_text": r["review_text"],
                "created_at": r["created_at"],
                "name": _public_name(r.get("name")),
            }
            for r in db.get_reviews(course_slug)
        ]
    }


@router.post("/reviews", summary="Review a course you are enrolled in")
def add_review(body: ReviewRequest, user: Learner):
    if not 1 <= body.rating <= 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rating must be between 1 and 5.")
    if not db.fetchone("SELECT id FROM purchases WHERE user_id=? AND course_slug=?", (user["id"], body.course_slug)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only learners enrolled in this course can review it.")
    db.execute(
        """INSERT INTO reviews (user_id, course_slug, rating, review_text) VALUES (?,?,?,?)
                  ON CONFLICT(user_id, course_slug) DO UPDATE SET rating=excluded.rating,
                  review_text=excluded.review_text""",
        (user["id"], body.course_slug, body.rating, (body.review_text or "").strip()),
    )
    db.execute(
        "INSERT INTO behaviour_events (user_id, course_slug, event_type) VALUES (?,?,?)",
        (user["id"], body.course_slug, "review_submit"),
    )
    return {"message": "Review published. Thank you."}


@router.get("/qna/{course_slug}", summary="Questions and answers on a course page")
def get_questions(course_slug: str):
    return {
        "questions": [
            {
                "id": q["id"],
                "question": q["question"],
                "answer": q["answer"],
                "answered_by": q["answered_by"],
                "answered_at": q["answered_at"],
                "created_at": q["created_at"],
                "user_name": _public_name(q.get("user_name")),
            }
            for q in db.get_qna(course_slug)
        ]
    }


@router.post("/qna", summary="Ask a question about a course")
def ask_question(body: QuestionRequest, user: Learner):
    question = (body.question or "").strip()
    if len(question) < 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please write a question (at least 5 characters).")
    if not catalog.get_course(body.course_slug):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    db.execute(
        "INSERT INTO qna (user_id, course_slug, question) VALUES (?,?,?)", (user["id"], body.course_slug, question)
    )
    return {"message": "Question sent. Our team will answer it here and by email."}
