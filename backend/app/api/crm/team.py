"""The team: accounts and roles, how leads are given out, performance, and the audit log (admins)."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Query, status

from app import db
from app.api.deps import Admin, Member
from app.core import security
from app.core.config import get_settings
from app.core.errors import NotFound
from app.schemas.crm import MemberRequest, MemberUpdate, PasswordRequest, TeamSettingsRequest
from app.services import team as T

log = logging.getLogger(__name__)
router = APIRouter(tags=["CRM team"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _member_or_404(member_id: int) -> dict:
    m = T.member(member_id)
    if not m:
        raise NotFound("No such team member.")
    return m


def _assign_after_release() -> None:
    try:
        T.auto_assign()
    except Exception:  # noqa: BLE001 - the every-minute run tries again
        log.warning("Giving out released leads failed; the every-minute run tries again", exc_info=True)


@router.get("/team", summary="Every account, the team settings and the roles")
def list_team(_: Admin):
    return {
        "members": [T.public(m) for m in T.members()],
        "settings": T.get_settings(),
        "roles": [{"key": r, "label": T.ROLE_LABEL[r]} for r in T.ROLES],
        "rules": list(T.RULES),
    }


@router.post("/team", summary="Add an account (they choose their own password at the first sign-in)")
def add_member(body: MemberRequest, me: Admin):
    name, email = (body.name or "").strip(), (body.email or "").strip().lower()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a name (up to 80 characters).")
    if not EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a valid email address.")
    if body.role not in T.ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role must be admin, marketing or counsellor.")
    if email == get_settings().crm_owner_email.strip().lower() or T.member_by_email(email):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is already an account with this email address.")
    problem = security.password_problem(body.password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    m = T.create_member(name, email, body.role, body.password)
    T.audit(me, "member_created", "member", m["id"], f"{name} ({T.ROLE_LABEL[body.role]})")
    return {
        "member": T.public(m),
        "message": f"{name} can now sign in; they choose their own password at the first sign-in.",
    }


@router.put("/team/{member_id}", summary="Change an account's name, role, status or lead intake")
def update_member(member_id: int, body: MemberUpdate, me: Admin):
    m = _member_or_404(member_id)
    changes, sets, params = [], [], []
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a name (up to 80 characters).")
        sets.append("name=?")
        params.append(name)
        changes.append(f"name: {name}")
    if body.role is not None and body.role != m["role"]:
        if body.role not in T.ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role must be admin, marketing or counsellor.")
        if m["is_owner"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The owner account stays an admin.")
        sets.append("role=?")
        params.append(body.role)
        changes.append(f"role: {T.ROLE_LABEL[body.role]}")
    if body.active is not None and bool(body.active) != bool(m["active"]):
        if m["is_owner"] or m["id"] == me["id"]:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "You cannot switch off the owner account or your own account."
            )
        sets.append("active=?")
        params.append(1 if body.active else 0)
        changes.append("switched on" if body.active else "switched off")
    if body.takes_new_leads is not None and bool(body.takes_new_leads) != bool(m["takes_new_leads"]):
        sets.append("takes_new_leads=?")
        params.append(1 if body.takes_new_leads else 0)
        changes.append("takes new leads" if body.takes_new_leads else "takes no new leads")
    if not sets:
        return {"member": T.public(m), "message": "Nothing changed."}
    db.execute(f"UPDATE team_members SET {', '.join(sets)} WHERE id=?", params + [member_id])
    released = 0
    if body.active is False:
        released = T.release_leads(member_id)  # their leads go back to the pool (and to the others)
        changes.append(f"{released} lead(s) unassigned")
    T.audit(me, "member_updated", "member", member_id, "; ".join(changes))
    if released:
        _assign_after_release()
    return {"member": T.public(T.member(member_id)), "message": "Saved: " + "; ".join(changes) + "."}


@router.post("/team/{member_id}/password", summary="Set a new password (they choose their own at the next sign-in)")
def reset_password(member_id: int, body: PasswordRequest, me: Admin):
    m = _member_or_404(member_id)
    if m["is_owner"] and get_settings().owner_password_from_env:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The owner account's password is CRM_OWNER_PASSWORD in backend/.env."
        )
    problem = security.password_problem(body.password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    T.set_password(member_id, body.password, must_change=True)
    T.clear_failures(m["email"])
    T.audit(me, "password_reset", "member", member_id, m["name"])
    return {"message": f"New password set for {m['name']}; they choose their own at the next sign-in."}


@router.delete("/team/{member_id}", summary="Delete an account (its leads become unassigned)")
def delete_member(member_id: int, me: Admin):
    """For an account made by mistake. Notes keep the name and the audit log keeps what it did; switching an account
    off keeps it in the list instead."""
    m = _member_or_404(member_id)
    if m["is_owner"] or m["id"] == me["id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete the owner account or your own account.")
    released = T.release_leads(member_id)
    db.execute("DELETE FROM team_members WHERE id=?", (member_id,))
    T.clear_failures(m["email"])
    T.audit(me, "member_deleted", "member", member_id, f"{m['name']}; {released} lead(s) unassigned")
    if released:
        _assign_after_release()
    return {"message": f"{m['name']} deleted; {released} lead(s) unassigned."}


@router.put("/team-settings", summary="How leads are given out, service levels and task expiry")
def update_team_settings(body: TeamSettingsRequest, me: Admin):
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    if "assignment_rule" in values and values["assignment_rule"] not in T.RULES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The rule must be round_robin or least_loaded.")
    for k in ("task_sla_hours", "callback_sla_hours"):
        if k in values and not 0.25 <= float(values[k]) <= 720:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Service levels must be between 0.25 and 720 hours.")
    if "task_expiry_days" in values and not 0 <= float(values["task_expiry_days"]) <= 90:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Task expiry must be between 1 and 90 days (0 = never).")
    out = T.put_settings(values)
    T.audit(me, "team_settings", None, None, ", ".join(f"{k}={v}" for k, v in values.items()))
    return {"settings": out}


@router.post("/team/assign-now", summary="Give out leads now (backlog=true: also older open leads)")
def assign_now(me: Admin, backlog: bool = False):
    made = []
    while True:  # in batches of 500
        batch = T.auto_assign(actor=me, backlog=backlog, force=True)
        made += batch
        if len(batch) < 500:
            break
    names = T.names()
    counts: dict[str, int] = {}
    for _, mid in made:
        counts[names.get(mid, str(mid))] = counts.get(names.get(mid, str(mid)), 0) + 1
    if not T.eligible_counsellors():
        msg = "Nobody takes new leads yet: add a counsellor (Team page) or switch on 'takes new leads'."
    else:
        msg = f"{len(made)} lead(s) assigned" + (
            ": " + ", ".join(f"{n} to {k}" for k, n in counts.items()) if made else "."
        )
    return {"assigned": len(made), "by_member": counts, "message": msg}


@router.get("/team/performance", summary="One row per counsellor: leads, tasks, speed, purchases and revenue")
def performance(_: Member, days: int = Query(30, ge=1, le=365)):
    return T.performance(days)


@router.get("/audit", summary="Who changed what (people on the team; leads by number only)")
def audit_log(
    _: Admin,
    member_id: int | None = None,
    action: str | None = None,
    person: int | None = None,
    limit: int = Query(200, ge=1, le=2000),
):
    sql, params = "SELECT * FROM audit_log WHERE 1=1", []
    if member_id is not None:
        sql += " AND member_id=?"
        params.append(member_id)
    if action:
        sql += " AND action=?"
        params.append(action)
    if person is not None:
        sql += " AND target_type='person' AND target_id=?"
        params.append(person)
    rows = db.fetchall(sql + " ORDER BY id DESC LIMIT ?", params + [limit])
    people = sorted({r["target_id"] for r in rows if r["target_type"] == "person" and r["target_id"]})
    lead_of = {}
    for i in range(0, len(people), 900):
        chunk = people[i : i + 900]
        for r in db.fetchall(
            f"""SELECT user_id, MAX(id) AS lead_id FROM leads
                                 WHERE user_id IN ({','.join('?' * len(chunk))}) GROUP BY user_id""",
            chunk,
        ):
            lead_of[r["user_id"]] = r["lead_id"]
    for r in rows:
        r["lead_id"] = lead_of.get(r["target_id"]) if r["target_type"] == "person" else None
    actions = [r["action"] for r in db.fetchall("SELECT DISTINCT action FROM audit_log ORDER BY action")]
    return {"entries": rows, "actions": actions}
