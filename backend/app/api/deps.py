"""
Request dependencies: who is calling, and may they do this?

Two kinds of caller, two kinds of token (app.core.security): learners on the website (audience "learner")
and people on the CRM team (audience "crm"). Team roles are checked here on every request, so a role cannot
do more than it should even if someone calls the API directly; the dashboard only hides what a role cannot use.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app import db
from app.core import security
from app.core.config import get_settings
from app.services import team as T


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


# learners
def current_learner(authorization: Annotated[str | None, Header()] = None) -> dict:
    token = _bearer(authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    claims = security.decode_token(token, security.AUD_LEARNER)
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    user = db.get_user_by_id(int(claims["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found")
    if not security.token_is_current(claims, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your password was changed. Please sign in again.")
    return user


def optional_learner(authorization: Annotated[str | None, Header()] = None) -> dict | None:
    try:
        return current_learner(authorization)
    except HTTPException:
        return None


Learner = Annotated[dict, Depends(current_learner)]
OptionalLearner = Annotated[dict | None, Depends(optional_learner)]


# people on the CRM team
# what an account that still has the password an admin gave it may do: choose its own password
_FIRST_LOGIN_PATHS = ("/api/v1/crm/me", "/api/v1/crm/me/password")


def current_member(request: Request, authorization: Annotated[str | None, Header()] = None) -> dict:
    token = _bearer(authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    claims = security.decode_token(token, security.AUD_CRM)
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    m = T.member(claims.get("mid"))
    if not m or not m["active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account is switched off. Ask an admin.")
    if not security.token_is_current(claims, m.get("password_hash")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your password was changed. Please sign in again.")
    if m["is_owner"]:
        settings = get_settings()
        m = {**m, "name": m["name"] or settings.crm_owner_name}
    if m.get("must_change_password") and request.url.path not in _FIRST_LOGIN_PATHS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Choose your own password first (Account page).")
    return m


def need(*roles: str):
    """Dependency factory: the signed-in person must have one of these roles."""

    def dep(me: Annotated[dict, Depends(current_member)]) -> dict:
        if me["role"] not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your role ({T.ROLE_LABEL.get(me['role'], me['role'])}) cannot do this. Ask an admin.",
            )
        return me

    return dep


Member = Annotated[dict, Depends(current_member)]
Admin = Annotated[dict, Depends(need("admin"))]
Marketing = Annotated[dict, Depends(need("admin", "marketing"))]


def require_change(me: dict, user_id: int, email: str | None = None) -> None:
    """Record-level access: counsellors change only their own leads and unassigned ones."""
    ok, why = T.can_change(me, user_id, email)
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, why)
