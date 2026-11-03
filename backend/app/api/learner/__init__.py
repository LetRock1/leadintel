"""The learner API (``/api/v1``): used by the public website, and by the simulated learners exactly like a browser."""

from fastapi import APIRouter

from app.api.learner import account, activity, auth, commerce, courses, support

router = APIRouter()
for module in (auth, account, activity, courses, commerce, support):
    router.include_router(module.router)
