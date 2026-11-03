"""The CRM API (``/api/v1/crm``): used by the team's dashboard. Every route needs a team member's token."""

from fastapi import APIRouter

from app.api.crm import actions, auth, campaigns, dashboard, insights, leads, outreach, simulation, team

router = APIRouter(prefix="/crm")
for module in (auth, dashboard, leads, actions, outreach, campaigns, insights, team, simulation):
    router.include_router(module.router)
