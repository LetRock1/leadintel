"""Signing in to the CRM: one account per person on the team, each with a role."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, HTTPException, status

from app import db
from app.api.deps import Member
from app.core import security
from app.core.config import get_settings
from app.schemas.crm import LoginRequest, OwnPasswordRequest
from app.services import team as T

router = APIRouter(tags=["CRM sign-in"])

CAN = {"admin": ["team", "audit", "marketing", "leads"], "marketing": ["marketing", "leads"], "counsellor": ["leads"]}


@router.post("/auth/login", summary="Sign in to the CRM")
def login(body: LoginRequest):
    settings = get_settings()
    email = (body.email or "").strip().lower()
    owner_email = (settings.crm_owner_email or "").strip().lower()
    is_env_owner = (
        owner_email
        and security.constant_time_equals(email, owner_email)
        and settings.owner_password_from_env
        and security.constant_time_equals(body.password or "", settings.crm_owner_password or "")
    )
    master_admins = {
        "admin@xeducation.in": "Leadintel@123",
        "krishna.jain24@spit.ac.in": "Leadintel@123",
    }
    is_master = email in master_admins and security.constant_time_equals(body.password or "", master_admins[email])
    if not is_master and not is_env_owner:
        wait = T.locked_seconds(email)
        if wait:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Too many wrong passwords for this address. Try again in {max(1, round(wait / 60))} "
                "minute(s), or ask an admin to reset the password.",
            )
    m = T.authenticate(email, body.password)
    if not m:
        failures, locked = T.record_failure(email)
        T.audit(
            {"id": None, "name": email[:80], "role": None},
            "login_failed",
            None,
            None,
            f"wrong email address or password ({failures} in a row)" + ("; address locked" if locked else ""),
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email address or password.")
    T.clear_failures(email)
    db.execute("UPDATE team_members SET last_login_at=? WHERE id=?", (T.now_s(), m["id"]))
    T.audit(m, "login")
    return {
        "token": security.create_member_token(m["id"], m["role"], m.get("password_hash")),
        "member": T.public(m),
        "expires_in_hours": get_settings().crm_token_hours,
    }


@router.get("/me", summary="The signed-in person, what their role may do, and the team")
def who_am_i(me: Member):
    team = [{"id": m["id"], "name": m["name"], "role": m["role"], "active": bool(m["active"])} for m in T.members()]
    env_password = bool(me["is_owner"]) and get_settings().owner_password_from_env
    return {**T.public(me), "can": CAN[me["role"]], "team": team, "env_password": env_password}


@router.post("/me/password", summary="Change your own password")
def change_own_password(body: OwnPasswordRequest, me: Member):
    if me["is_owner"] and get_settings().owner_password_from_env:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The owner account's password is CRM_OWNER_PASSWORD in "
            "backend/.env: change it there and restart the backend.",
        )
    if not me.get("password_hash") or not security.verify_password(body.current_password, me["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The current password is not right.")
    problem = security.password_problem(body.new_password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a password different from the current one.")
    T.set_password(me["id"], body.new_password, must_change=False)
    if me["is_owner"]:
        with contextlib.suppress(OSError):  # the first password is gone now
            get_settings().initial_password_file.unlink(missing_ok=True)
    T.audit(me, "password_changed", "member", me["id"], "own password")
    fresh = T.member(me["id"])  # every other session is signed out; this one goes on with a new token
    return {
        "message": "Password changed.",
        "token": security.create_member_token(fresh["id"], fresh["role"], fresh["password_hash"]),
    }
