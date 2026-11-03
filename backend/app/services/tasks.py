"""
Today's actions: the call and WhatsApp tasks next-best-action created for the team, and the call-back requests
learners sent from the website. A real person's outcome is typed in by whoever made the call; a simulated
learner's phone is not real, so pressing Call lets the simulated learner answer or not (app.simulation).
"""

from __future__ import annotations

import json
from datetime import datetime

from app import db
from app.core.errors import BadRequest, Conflict, NotFound
from app.ml import nba_core as N
from app.services import team as T
from app.services.content import speaker
from app.services.leads import add_owner_names, is_simulated, owner_sql, segment_sql
from app.services.lifecycle import add_note, require_change

STATUSES = ("open", "closed", "done", "skipped", "all")
OUTCOMES = {
    "reached": "Spoke to them",
    "no_answer": "No answer",
    "not_interested": "Not interested",
    "sent": "WhatsApp sent",
    "skipped": "Skipped",
}
TS = "%Y-%m-%d %H:%M:%S"


def overdue(created_at, hours: float) -> bool:
    try:
        t = datetime.strptime(str(created_at)[:19], TS)
    except (TypeError, ValueError):
        return False
    return (datetime.now() - t).total_seconds() > float(hours) * 3600


def list_tasks(
    me: dict, status: str = "open", segment: str = "all", owner: str | None = None, limit: int = 500
) -> dict:
    """Open tasks first, highest expected extra profit first; closed ones most recent first.
    status: open | closed (done or skipped) | done | skipped | all."""
    if status not in STATUSES:
        raise BadRequest("status must be open, closed, done, skipped or all.")
    own_sql, params = owner_sql(owner, me, col="t.user_id")
    status_sql = " AND t.status!='open'" if status == "closed" else ("" if status == "all" else " AND t.status=?")
    status_params = [status] if status in ("open", "done", "skipped") else []
    rows = db.fetchall(
        """
        SELECT t.*, u.name, u.email, up.phone, up.whatsapp_opt_in, l.lead_score, l.recommended_action,
               l.course_type, l.course_slug, l.tips_json, d.policy, d.model_best, d.slot_price, d.call_value,
               d.options_json, d.price AS course_price
        FROM sales_tasks t JOIN users u ON u.id = t.user_id
        LEFT JOIN user_profiles up ON up.user_id = t.user_id
        LEFT JOIN leads l ON l.id = t.lead_id
        LEFT JOIN nba_decisions d ON d.id = t.decision_id
        WHERE 1=1"""
        + status_sql
        + segment_sql(segment)
        + own_sql
        + f"""
        ORDER BY CASE WHEN t.status='open' THEN 0 ELSE 1 END,
                 CASE WHEN t.status='open' THEN -t.expected_gain END,
                 COALESCE(t.done_at, t.created_at) DESC, t.id DESC
        LIMIT {max(1, min(int(limit), 5000))}""",
        status_params + params,
    )
    conf = T.get_settings()
    sla = float(conf.get("task_sla_hours", 24))
    for r in rows:
        try:
            r["tips"] = json.loads(r.pop("tips_json") or "[]")
        except ValueError:
            r["tips"] = []
        try:
            r["options"] = json.loads(r.pop("options_json") or "[]")
        except ValueError:
            r["options"] = []
        for o in r["options"]:  # labels as they are called today
            o["label"] = N.ACTIONS.get(o.get("action"), {}).get("label", o.get("label"))
        r["detail"] = speaker(r.get("detail"), me["name"])  # the script, as said by the person signed in
        r["simulated"] = is_simulated(r["email"])
        r["overdue"] = r["status"] == "open" and overdue(r["created_at"], sla)
    add_owner_names(rows)
    hidden = (
        0
        if segment == "all"
        else db.fetchone(
            """SELECT COUNT(*) AS c FROM sales_tasks t JOIN users u ON u.id = t.user_id WHERE 1=1"""
            + status_sql
            + segment_sql("simulated" if segment != "simulated" else "real")
            + own_sql,
            status_params + params,
        )["c"]
    )
    return {
        "actions": rows,
        "segment": segment,
        "owner": owner or "all",
        "other_segment_count": hidden,
        "sla_hours": sla,
        "expiry_days": float(conf.get("task_expiry_days", 7) or 0),
    }


def open_task(task_id: int, me: dict) -> dict:
    """The task (with the learner's email) if this person may close it now."""
    task = db.fetchone(
        "SELECT t.*, u.email FROM sales_tasks t JOIN users u ON u.id = t.user_id WHERE t.id=?", (task_id,)
    )
    if not task:
        raise NotFound("Task not found")
    require_change(me, task["user_id"], task["email"])
    if task["status"] != "open":
        by = f" by {task['done_by']}" if task.get("done_by") else ""
        raise Conflict(f"This task is closed already ({task['status']}{by}: {task.get('outcome') or 'no outcome'}).")
    return task


def _note(task: dict, me: dict, outcome: str, note: str | None) -> str:
    note = (note or "").strip()
    if note or outcome == "not_interested":
        add_note(
            task["user_id"],
            me,
            task["task_type"] or "call",
            f"{OUTCOMES[outcome]}." + (f" {note[:2000]}" if note else ""),
        )
    return note


def complete(task_id: int, me: dict, outcome: str, note: str | None) -> dict:
    """Record what happened on a call or WhatsApp to a real person, or skip a task (nothing is sent)."""
    if outcome not in OUTCOMES:
        raise BadRequest("Unknown outcome.")
    task = open_task(task_id, me)
    if is_simulated(task["email"]) and outcome != "skipped":
        raise BadRequest(
            "This is a simulated learner: press Call (or Send WhatsApp) and the learner answers as the "
            "simulator decides. Only skipping is recorded by hand."
        )
    if not db.claim(
        """UPDATE sales_tasks SET status=?, outcome=?, done_at=datetime('now','localtime'), done_by=?
                  WHERE id=? AND status='open'""",
        ("skipped" if outcome == "skipped" else "done", outcome, me["name"][:40], task_id),
    ):  # someone else closed it a moment ago: their outcome stands
        open_task(task_id, me)  # raises "closed already (by ...)"
        raise Conflict("This task was closed a moment ago by someone else.")
    if task["decision_id"] and outcome in ("reached", "sent", "not_interested"):
        db.execute(
            "UPDATE nba_decisions SET executed_at=COALESCE(executed_at, datetime('now','localtime')) WHERE id=?",
            (task["decision_id"],),
        )
    note = _note(task, me, outcome, note)
    T.audit(
        me,
        "task_skipped" if outcome == "skipped" else "task_done",
        "person",
        task["user_id"],
        f"{task['task_type']} #{task_id}: {outcome}" + (" with a note" if note else ""),
    )
    return {"message": "Skipped." if outcome == "skipped" else "Saved.", "suggest_lost": outcome == "not_interested"}


def call_simulated(task_id: int, me: dict, note: str | None) -> dict:
    """Someone on the team calls a simulated learner (or sends them the WhatsApp message): the learner answers or not
    with the documented chances, and the outcome is saved under this person's name."""
    from app.simulation import live

    task = open_task(task_id, me)
    if not is_simulated(task["email"]):
        raise BadRequest("This is a real person: call them on the phone (or open WhatsApp), then record what happened.")
    try:
        r = live.get_world().phone_call(task_id, me["name"][:40])
    except LookupError as e:
        raise NotFound(str(e)) from None
    except PermissionError as e:
        raise BadRequest(str(e)) from None
    except live.Paused as e:
        raise Conflict(str(e)) from None
    if not r.get("ok"):
        raise Conflict(r.get("message") or "This task is closed already.")
    note = _note(task, me, r["outcome"], note)
    T.audit(
        me,
        "task_done",
        "person",
        task["user_id"],
        f"{task['task_type']} #{task_id}: {r['outcome']} (simulated learner)" + (" with a note" if note else ""),
    )
    return {
        "message": r["message"],
        "outcome": r["outcome"],
        "learner": r.get("learner"),
        "suggest_lost": r["outcome"] == "not_interested",
    }


# call-back requests
def list_callbacks(me: dict, status: str = "open", owner: str | None = None) -> dict:
    own_sql, params = owner_sql(owner, me, col="cb.user_id")
    rows = db.fetchall(
        """
        SELECT cb.*, u.name, u.email, (SELECT MAX(id) FROM leads l WHERE l.user_id = cb.user_id) AS lead_id
        FROM callback_requests cb JOIN users u ON u.id = cb.user_id
        WHERE (?='all' OR cb.status=?)"""
        + own_sql
        + " ORDER BY cb.id DESC",
        [status, status] + params,
    )
    sla = float(T.get_settings().get("callback_sla_hours", 4))
    for r in rows:
        r["overdue"] = r["status"] == "open" and overdue(r["created_at"], sla)
        r["simulated"] = is_simulated(r["email"])
    add_owner_names(rows)
    return {"callbacks": rows, "sla_hours": sla}


def close_callback(callback_id: int, me: dict, note: str | None) -> None:
    cb = db.fetchone(
        """SELECT cb.id, cb.user_id, cb.status, u.email FROM callback_requests cb
                        JOIN users u ON u.id = cb.user_id WHERE cb.id=?""",
        (callback_id,),
    )
    if not cb:
        raise NotFound("Call-back request not found")
    require_change(me, cb["user_id"], cb["email"])
    if cb["status"] != "open" or not db.claim(
        """UPDATE callback_requests SET status='done', closed_at=datetime('now','localtime'), done_by=?
                  WHERE id=? AND status='open'""",
        (me["name"], callback_id),
    ):  # a second person pressing "Mark as done" at the same moment gets told, not a second note
        raise Conflict("This call-back request is closed already.")
    note = (note or "").strip()
    if note:
        add_note(cb["user_id"], me, "callback", f"Called back: {note[:2000]}")
    T.audit(me, "callback_done", "person", cb["user_id"], f"callback #{callback_id}" + (" with a note" if note else ""))
