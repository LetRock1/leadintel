"""
What the team changes about a lead by hand: its pipeline stage, closing it as lost (with a reason) and re-opening it,
the contact channels the person asked the team not to use, notes, and who on the team looks after the lead.
Every change is checked against the person's role (app.services.team.can_change) and written to the audit log.
"""

from __future__ import annotations

from app import db
from app.core.errors import BadRequest, Forbidden, NotFound
from app.services import team as T
from app.services.scoring import rescore_latest_lead

PIPELINE_STAGES = ["Lead", "Engaged", "MQL", "SQL", "Lost"]  # Customer comes only from buying
NOTE_KINDS = ("note", "call", "whatsapp", "meeting")
CHANNELS = {"email": "does not want emails", "call": "does not want calls", "whatsapp": "does not want WhatsApp"}


def require_change(me: dict, user_id: int, email: str | None = None) -> None:
    ok, why = T.can_change(me, user_id, email)
    if not ok:
        raise Forbidden(why)


def _user(user_id: int) -> dict:
    user = db.fetchone("SELECT id, email FROM users WHERE id=?", (user_id,))
    if not user:
        raise NotFound("Lead not found")
    return user


def add_note(user_id: int, me: dict, kind: str, text: str) -> int:
    return db.execute(
        "INSERT INTO lead_notes (user_id, member_id, author, kind, text) VALUES (?,?,?,?,?)",
        (user_id, me.get("id"), me.get("name"), kind, text),
    )


def close_open_tasks(user_id: int, why: str) -> None:
    """The lead's open call and WhatsApp tasks leave Today's actions."""
    db.execute(
        """UPDATE sales_tasks SET status='skipped', outcome=?, done_at=datetime('now','localtime')
                  WHERE user_id=? AND status='open'""",
        (why[:60], user_id),
    )


def restrict_contact(user_id: int, channels: tuple[str, ...]) -> None:
    """The person asked not to be contacted on these channels (only they can switch a channel back on, in their
    settings on the website). The flags are model inputs too, so the lead is re-scored."""
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,))
    if "email" in channels:
        db.execute("UPDATE user_profiles SET do_not_email='Yes' WHERE user_id=?", (user_id,))
    if "call" in channels:
        db.execute("UPDATE user_profiles SET do_not_call='Yes' WHERE user_id=?", (user_id,))
    if "whatsapp" in channels:
        db.execute("UPDATE user_profiles SET whatsapp_opt_in=0 WHERE user_id=?", (user_id,))
    tasks = [c for c in channels if c in ("call", "whatsapp")]
    if tasks:
        db.execute(
            f"""UPDATE sales_tasks SET status='skipped', outcome='asked not to be contacted',
                       done_at=datetime('now','localtime')
                       WHERE user_id=? AND status='open' AND task_type IN ({','.join('?' * len(tasks))})""",
            (user_id, *tasks),
        )
    rescore_latest_lead(user_id, "consent_changed")


def set_stage(me: dict, user_id: int, stage: str, note: str | None = None, reason: str | None = None) -> dict:
    """Move a lead to a stage by hand, or close it as Lost with a reason. Purchases always win over a manual stage."""
    if stage not in PIPELINE_STAGES:
        raise BadRequest("Stage must be Lead, Engaged, MQL, SQL or Lost (customers come from purchases).")
    user = _user(user_id)
    require_change(me, user_id, user["email"])
    reasons = T.get_settings().get("lost_reasons") or []
    if stage == "Lost":
        if db.fetchone("SELECT 1 AS x FROM purchases WHERE user_id=? LIMIT 1", (user_id,)):
            raise BadRequest("This person has bought: customers cannot be closed as lost.")
        if not reason or (reasons and reason not in reasons):
            raise BadRequest("Choose why the lead is lost: " + ", ".join(reasons) + ".")
    db.execute(
        """INSERT INTO pipeline_overrides (user_id, stage, note, moved_at, lost_reason, moved_by)
                  VALUES (?, ?, ?, datetime('now','localtime'), ?, ?)
                  ON CONFLICT(user_id) DO UPDATE SET stage=excluded.stage, note=excluded.note,
                  moved_at=excluded.moved_at, lost_reason=excluded.lost_reason, moved_by=excluded.moved_by""",
        (user_id, stage, (note or "")[:200] or None, reason if stage == "Lost" else None, me["name"]),
    )
    if stage == "Lost":
        close_open_tasks(user_id, "lead closed as lost")
        if reason == "Asked not to be contacted":
            restrict_contact(user_id, ("email", "call", "whatsapp"))
        add_note(
            user_id,
            me,
            "status",
            f"Closed as lost: {reason}." + (f" {note.strip()[:200]}" if note and note.strip() else ""),
        )
        T.audit(me, "lead_lost", "person", user_id, reason)
    else:
        T.audit(me, "stage_moved", "person", user_id, stage)
    return {"ok": True, "user_id": user_id, "stage": stage, "reason": reason if stage == "Lost" else None}


def reopen(me: dict, user_id: int) -> dict:
    """Back to automatic: the stage follows the learner's behaviour again (a lost lead is re-opened)."""
    user = _user(user_id)
    require_change(me, user_id, user["email"])
    was = db.fetchone("SELECT stage FROM pipeline_overrides WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM pipeline_overrides WHERE user_id=?", (user_id,))
    if was and was["stage"] == "Lost":
        add_note(user_id, me, "status", "Re-opened: the CRM may take steps for this lead again.")
        T.audit(me, "lead_reopened", "person", user_id)
    elif was:
        T.audit(me, "stage_auto", "person", user_id)
    return {"ok": True, "user_id": user_id}


def record_consent(me: dict, user_id: int, channel: str) -> str:
    if channel not in CHANNELS:
        raise BadRequest("Channel must be email, call or whatsapp.")
    restrict_contact(user_id, (channel,))
    label = CHANNELS[channel]
    add_note(user_id, me, "consent", f"Recorded: {label} (as the person asked).")
    T.audit(me, "consent_recorded", "person", user_id, label)
    return label


def new_note(me: dict, user_id: int, text: str, kind: str | None) -> dict:
    text = (text or "").strip()
    if not text:
        raise BadRequest("Write the note first.")
    if len(text) > 4000:
        raise BadRequest("Keep a note under 4,000 characters.")
    kind = kind if kind in NOTE_KINDS else "note"
    nid = add_note(user_id, me, kind, text)
    T.audit(me, "note_added", "person", user_id, f"note #{nid} ({kind}, {len(text)} characters)")
    return db.fetchone("SELECT id, member_id, author, kind, text, created_at FROM lead_notes WHERE id=?", (nid,))


def delete_note(me: dict, note_id: int) -> None:
    n = db.fetchone("SELECT id, user_id, member_id, kind FROM lead_notes WHERE id=?", (note_id,))
    if not n:
        raise NotFound("Note not found")
    if me["role"] != "admin" and n["member_id"] != me["id"]:
        raise Forbidden("Only the author or an admin can delete a note.")
    if n["kind"] in ("status", "consent") and me["role"] != "admin":
        raise Forbidden("Status and consent records are kept (an admin can remove them).")
    db.execute("DELETE FROM lead_notes WHERE id=?", (note_id,))
    T.audit(me, "note_deleted", "person", n["user_id"], f"note #{note_id}")


def set_owner(me: dict, user_id: int, member_id: int | None) -> dict:
    """Admins give a lead to anyone on the team (or unassign it); others can take an unassigned lead themselves."""
    current = T.owner_of(user_id)
    if me["role"] != "admin" and (member_id != me["id"] or current is not None):
        raise Forbidden("Only an admin can give a lead to someone else. You can take an unassigned lead.")
    if member_id is None:
        T.clear_owner(user_id)
        T.audit(me, "lead_unassigned", "person", user_id)
        return {"owner": None, "message": "The lead is unassigned now."}
    m = T.member(member_id)
    if not m:
        raise NotFound("No such team member.")
    if not m["active"]:
        raise BadRequest(f"{m['name']}'s account is switched off.")
    if current == m["id"]:
        return {"owner": {"id": m["id"], "name": m["name"]}, "message": f"{m['name']} already looks after this lead."}
    T.set_owner(user_id, m["id"], "claimed" if m["id"] == me["id"] and me["role"] != "admin" else "manual")
    before = T.member(current)["name"] if current and T.member(current) else "nobody"
    T.audit(me, "lead_assigned", "person", user_id, f"by hand from {before} to {m['name']}")
    return {"owner": {"id": m["id"], "name": m["name"]}, "message": f"{m['name']} looks after this lead now."}
