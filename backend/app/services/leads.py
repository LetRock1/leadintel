"""
Leads as the CRM team sees them.

A learner gets a new contact record (a row in ``leads``) for every enquiry, abandoned cart or other trigger, so
every list, count and campaign here works on each person's LATEST record: one row per person. That record is
kept re-scored by the model (``app.services.scoring``), so it always shows the person's current state.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from app import db
from app.core import rules
from app.core.errors import BadRequest, NotFound
from app.services import team as T
from app.services.content import speaker
from app.services.outreach import lead_slug

LATEST = "(SELECT * FROM leads WHERE id IN (SELECT MAX(id) FROM leads GROUP BY user_id))"
CUSTOMERS = "(SELECT DISTINCT user_id FROM purchases)"
SIM_LIKE = f"%@{rules.SIMULATED_DOMAIN}"
WINDOW_DAYS = int(rules.S["outcome_window_days"])
ACTION_LABEL = {k: v.get("label", k) for k, v in rules.S["actions"].items()}
POLICY_TEXT = {
    "model": "chosen by the model",
    "explore": f"random pick ({rules.S['exploration_rate'] * 100:.0f}% learning sample)",
    "holdout": "control group: decided for the record, nothing sent",
    "manual": "chosen by hand",
    "experiment": "campaign or A/B test",
}
TS = "%Y-%m-%d %H:%M:%S"


def is_simulated(email: str | None) -> bool:
    return rules.is_simulated_email(email)


def segment_sql(segment: str | None, col: str = "u.email") -> str:
    """'all' (default): everyone; 'real': people who signed up themselves; 'simulated': simulated learners."""
    if segment == "simulated":
        return f" AND {col} LIKE '{SIM_LIKE}'"
    if segment == "real":
        return f" AND {col} NOT LIKE '{SIM_LIKE}'"
    return ""


def owner_sql(owner: str | None, me: dict | None, col: str = "l.user_id") -> tuple[str, list]:
    """SQL filter and parameters for an owner choice: 'all', 'me', 'unassigned' or a team member's id."""
    if owner in (None, "", "all"):
        return "", []
    if owner == "me":
        return f" AND {col} IN (SELECT user_id FROM lead_owners WHERE member_id=?)", [me["id"] if me else -1]
    if owner == "unassigned":
        return f" AND {col} NOT IN (SELECT user_id FROM lead_owners)", []
    try:
        return f" AND {col} IN (SELECT user_id FROM lead_owners WHERE member_id=?)", [int(owner)]
    except (TypeError, ValueError):
        raise BadRequest("owner must be all, me, unassigned or a team member's number.") from None


def add_owner_names(rows: list[dict], user_col: str = "user_id") -> list[dict]:
    """Each row gets owner_id and owner: the person on the team who looks after the lead, or 'Unassigned'."""
    ids = [r[user_col] for r in rows if r.get(user_col) is not None]
    owners = {}
    for i in range(0, len(ids), 900):
        chunk = ids[i : i + 900]
        for o in db.fetchall(
            f"SELECT user_id, member_id FROM lead_owners WHERE user_id IN ({','.join('?' * len(chunk))})", chunk
        ):
            owners[o["user_id"]] = o["member_id"]
    names = T.names()
    for r in rows:
        r["owner_id"], r["owner"] = T.owner_label(owners.get(r.get(user_col)), names)
    return rows


def person_of_lead(lead_id: int) -> tuple[int, str]:
    """(user id, email) of the person behind a contact record."""
    r = db.fetchone("SELECT l.user_id, u.email FROM leads l JOIN users u ON u.id = l.user_id WHERE l.id=?", (lead_id,))
    if not r:
        raise NotFound("Lead not found")
    return r["user_id"], r["email"]


def latest_lead_id(user_id: int) -> int | None:
    return (db.fetchone("SELECT MAX(id) AS m FROM leads WHERE user_id=?", (user_id,)) or {}).get("m")


# the Leads list
def list_leads(
    me: dict,
    tier: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    segment: str = "all",
    limit: int = 300,
    owner: str | None = None,
    offset: int = 0,
) -> dict:
    """Only the columns the list shows: the drafts and model details stay on the lead page."""
    sql = f"""
        SELECT l.id, l.user_id, l.lead_score, l.conversion_probability, l.plv, l.persona, l.customer_segment,
               l.recommended_action, l.trigger_reason, l.course_type, l.course_slug, l.email_sent,
               l.created_at, COALESCE(s.last_seen, u.created_at) AS last_active_at, l.nba_action, l.model_version,
               u.name, u.email, up.phone, up.whatsapp_opt_in, up.do_not_email, up.do_not_call,
               up.current_occupation, up.specialization, up.city,
               COALESCE(t.n, 0) AS touches, COALESCE(p.n, 0) AS purchases, COALESCE(p.spent, 0) AS spent,
               p.first_course, p.first_purchase_at, COALESCE(cb.n, 0) AS open_callbacks,
               (po.stage = 'Lost') AS lost, po.lost_reason
        FROM {LATEST} l
        JOIN users u ON l.user_id = u.id
        LEFT JOIN user_profiles up ON up.user_id = l.user_id
        LEFT JOIN (SELECT user_id, COUNT(*) AS n FROM leads GROUP BY user_id) t ON t.user_id = l.user_id
        LEFT JOIN (SELECT user_id, COUNT(*) AS n, SUM(price_paid) AS spent, MIN(purchased_at) AS first_purchase_at,
                          MIN(course_title) AS first_course FROM purchases GROUP BY user_id) p ON p.user_id = l.user_id
        LEFT JOIN (SELECT user_id, COUNT(*) AS n FROM callback_requests WHERE status='open' GROUP BY user_id) cb
               ON cb.user_id = l.user_id
        LEFT JOIN pipeline_overrides po ON po.user_id = l.user_id
        LEFT JOIN (SELECT user_id, MAX(COALESCE(last_active, login_at)) AS last_seen FROM user_sessions
                   GROUP BY user_id) s ON s.user_id = l.user_id
        WHERE 1=1""" + segment_sql(segment)
    own_sql, params = owner_sql(owner, me)
    sql += own_sql
    if tier == "Customers":
        sql += f" AND l.user_id IN {CUSTOMERS}"
    elif tier:
        sql += f" AND l.recommended_action=? AND l.user_id NOT IN {CUSTOMERS}"
        params.append(tier)
    if search:
        sql += " AND (u.name LIKE ? OR u.email LIKE ? OR l.course_type LIKE ?)"
        params += [f"%{search.strip()}%"] * 3
    matching = db.fetchone(f"SELECT COUNT(*) AS c FROM ({sql})", params)["c"]
    sql += {
        "plv": " ORDER BY l.plv DESC",
        "score": " ORDER BY (p.n IS NOT NULL), l.lead_score DESC",
        "name": " ORDER BY u.name COLLATE NOCASE",
        "added": " ORDER BY l.created_at DESC, l.id DESC",
    }.get(sort or "", " ORDER BY last_active_at DESC, l.id DESC")  # the person's own last visit to the website
    sql += f" LIMIT {max(1, min(int(limit), 5000))} OFFSET {max(0, int(offset))}"
    rows = db.fetchall(sql, params)
    for r in rows:
        r["simulated"] = is_simulated(r["email"])
        r["customer"] = bool(r["purchases"])
        r["lost"] = bool(r["lost"]) and not r["customer"]
    add_owner_names(rows)
    counts = {
        seg: db.fetchone(
            f"SELECT COUNT(*) AS c FROM {LATEST} l JOIN users u ON u.id = l.user_id WHERE 1=1" + segment_sql(seg)
        )["c"]
        for seg in ("all", "real", "simulated")
    }
    counts["mine"] = db.fetchone("SELECT COUNT(*) AS c FROM lead_owners WHERE member_id=?", (me["id"],))["c"]
    counts["unassigned"] = db.fetchone("""SELECT COUNT(*) AS c FROM users u WHERE u.id IN (SELECT user_id FROM leads)
                                          AND u.id NOT IN (SELECT user_id FROM lead_owners)""")["c"]
    return {
        "leads": rows,
        "segment": segment,
        "owner": owner or "all",
        "counts": counts,
        "matching": matching,
        "offset": max(0, int(offset)),
    }


def priority_queue(limit: int = 20) -> list[dict]:
    """People most worth contacting now: expected value = P(buy) x course price (PLV), customers excluded."""
    return db.fetchall(
        f"""
        SELECT l.id, l.user_id, l.lead_score, l.conversion_probability, l.plv, l.recommended_action,
               l.course_type, l.course_slug, u.name, u.email, up.current_occupation, up.phone
        FROM {LATEST} l JOIN users u ON l.user_id = u.id
        LEFT JOIN user_profiles up ON up.user_id = l.user_id
        WHERE l.recommended_action != 'Low Priority' AND l.user_id NOT IN {CUSTOMERS}
          AND l.user_id NOT IN (SELECT user_id FROM pipeline_overrides WHERE stage='Lost')
        ORDER BY COALESCE(l.plv, 0) DESC LIMIT ?""",
        (max(1, min(int(limit), 200)),),
    )


# the lead page
def _json(v, default=None):
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def relabel(options: list | None) -> list:
    """Receipt lines with the step names used today (a decision stores the names of its own time)."""
    for o in options or []:
        o["label"] = ACTION_LABEL.get(o.get("action"), o.get("label"))
    return options or []


def lead_page(lead_id: int, me: dict) -> dict:
    """The person's page. Any of their contact records opens their CURRENT state (the latest record); older records
    are listed as touchpoints with the score they had then."""
    owner = db.fetchone("SELECT user_id FROM leads WHERE id=?", (lead_id,))
    if not owner:
        raise NotFound("Lead not found")
    lead = db.fetchone(
        """
        SELECT l.*, u.name, u.email, u.created_at AS signed_up_at, up.phone, up.whatsapp_opt_in, up.do_not_email,
               up.do_not_call, up.current_occupation, up.specialization, up.city, up.age_bracket
        FROM leads l JOIN users u ON l.user_id = u.id
        LEFT JOIN user_profiles up ON up.user_id = l.user_id
        WHERE l.id = (SELECT MAX(id) FROM leads WHERE user_id=?)""",
        (owner["user_id"],),
    )
    if not lead:
        raise NotFound("Lead not found")
    uid = lead["user_id"]
    seen = db.fetchone("SELECT MAX(COALESCE(last_active, login_at)) AS t FROM user_sessions WHERE user_id=?", (uid,))
    # the person's own last visit to the website (the leads table's column of that name was never filled)
    lead["last_active_at"] = (seen or {}).get("t") or lead["signed_up_at"]
    lead["opened_record"] = lead_id
    lead["course_slug"] = lead_slug(lead)
    lead["behaviour_events"] = db.fetchall(
        "SELECT * FROM behaviour_events WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,)
    )
    lead["coupons"] = db.fetchall("SELECT * FROM coupons_issued WHERE user_id=? ORDER BY created_at DESC", (uid,))
    lead["global_control"] = rules.in_global_control(uid)
    lead["touches"] = db.fetchall(
        """SELECT id, trigger_reason, lead_score, recommended_action, email_sent, created_at
                                     FROM leads WHERE user_id=? ORDER BY id DESC""",
        (uid,),
    )
    lead["score_history"] = db.fetchall(
        "SELECT * FROM lead_score_history WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,)
    )
    lead["emails"] = db.fetchall(
        """SELECT id, subject, sent_at, click_count, first_clicked_at, campaign_name, ab_test_id,
                                           variant, error FROM email_sends WHERE user_id=? ORDER BY id DESC LIMIT 20""",
        (uid,),
    )
    lead["purchases"] = db.fetchall("SELECT * FROM purchases WHERE user_id=? ORDER BY purchased_at DESC", (uid,))
    lead["chat"] = db.fetchall(
        """SELECT role, text, intent, created_at FROM chat_messages WHERE user_id=?
                                  ORDER BY id DESC LIMIT 30""",
        (uid,),
    )[::-1]
    lead["callbacks"] = db.fetchall("SELECT * FROM callback_requests WHERE user_id=? ORDER BY id DESC", (uid,))
    lead["tasks"] = db.fetchall("SELECT * FROM sales_tasks WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    lead["nba"] = _json(lead.get("nba_json"))
    if lead["nba"]:
        nb = lead["nba"]
        nb["label"] = ACTION_LABEL.get(nb.get("action"), nb.get("label"))
        if nb.get("model_best"):
            nb["model_best_label"] = ACTION_LABEL.get(nb["model_best"], nb.get("model_best_label"))
        relabel(nb.get("options"))
    lead["tips"] = _json(lead.get("tips_json"))
    lead["factors"] = _json(lead.get("score_factors"), [])
    if not lead.get("nba"):
        latest = db.fetchone(
            """SELECT options_json, action, policy, model_version, trigger_reason FROM nba_decisions
                                WHERE user_id=? ORDER BY id DESC LIMIT 1""",
            (uid,),
        )
        if latest:
            lead["nba"] = {
                "action": latest["action"],
                "label": ACTION_LABEL.get(latest["action"], latest["action"]),
                "policy": latest["policy"],
                "why": f"Decided at the '{latest['trigger_reason']}' trigger.",
                "detail": f"model {latest['model_version']}",
                "options": relabel(_json(latest["options_json"], [])),
            }
    lead["simulated"] = is_simulated(lead.get("email"))
    lead["customer"] = bool(lead["purchases"])
    lead["spent"] = round(sum(p.get("price_paid") or 0 for p in lead["purchases"]), 2)
    for k in ("call_script", "whatsapp_message", "email_body"):  # said by the person signed in
        lead[k] = speaker(lead.get(k), me["name"])
    for t in lead["tasks"]:
        t["detail"] = speaker(t.get("detail"), me["name"])
    lead["latest_lead_id"] = latest_lead_id(uid)
    lead["decisions"] = decision_history(uid)
    own = db.fetchone("SELECT member_id, assigned_at, how FROM lead_owners WHERE user_id=?", (uid,))
    oid, oname = T.owner_label(own["member_id"] if own else None, T.names())
    lead["owner"] = {
        "id": oid,
        "name": oname,
        "assigned_at": own["assigned_at"] if own else None,
        "how": own["how"] if own else None,
    }
    lead["notes"] = db.fetchall(
        """SELECT id, member_id, author, kind, text, created_at FROM lead_notes WHERE user_id=?
                                   ORDER BY id DESC LIMIT 100""",
        (uid,),
    )
    st = db.fetchone(
        "SELECT stage, lost_reason, note, moved_at, moved_by FROM pipeline_overrides WHERE user_id=?", (uid,)
    )
    lost = bool(st and st["stage"] == "Lost")
    lead["status"] = {
        "lost": lost and not lead["customer"],
        "reason": st["lost_reason"] if lost else None,
        "note": st["note"] if lost else None,
        "since": st["moved_at"] if lost else None,
        "by": st["moved_by"] if lost else None,
    }
    ok, why = T.can_change(me, uid, lead.get("email"))
    lead["can_change"], lead["can_change_why"] = ok, why
    lead["lost_reasons"] = T.get_settings().get("lost_reasons") or []
    lead["team"] = [{"id": m["id"], "name": m["name"], "role": m["role"]} for m in T.members(active_only=True)]
    for k in ("nba_json", "tips_json", "score_factors"):
        lead.pop(k, None)
    return lead


def _ts(v) -> datetime | None:
    try:
        return datetime.strptime(str(v)[:19], TS)
    except (TypeError, ValueError):
        return None


def decision_history(uid: int, limit: int = 20) -> list[dict]:
    """Every step the CRM took (or decided not to take) for this person, with its receipt and what happened next:
    email sent and clicked, call outcome, next visit, bought within the outcome window."""
    window = timedelta(days=WINDOW_DAYS)
    now = datetime.now()
    decs = db.fetchall(
        """SELECT id, lead_id, created_at, trigger_reason, action, model_best, policy, propensity,
                                 base_probability, price, options_json, model_version, executed_at, slot_price,
                                 call_value
                          FROM nba_decisions WHERE user_id=? ORDER BY id DESC LIMIT ?""",
        (uid, int(limit)),
    )
    emails = db.fetchall(
        """SELECT lead_id, campaign_id, ab_test_id, subject, sent_at, first_clicked_at, click_count
                            FROM email_sends WHERE user_id=? ORDER BY id""",
        (uid,),
    )
    by_lead = {}
    for e in emails:
        if e["lead_id"] and not e["campaign_id"] and not e["ab_test_id"]:
            by_lead.setdefault(e["lead_id"], e)
    tasks = {
        t["decision_id"]: t
        for t in db.fetchall(
            """SELECT decision_id, task_type, status, outcome, done_at, done_by
               FROM sales_tasks WHERE user_id=? AND decision_id IS NOT NULL""",
            (uid,),
        )
    }
    events = [
        t
        for t in (
            _ts(r["created_at"])
            for r in db.fetchall("SELECT created_at FROM behaviour_events WHERE user_id=? ORDER BY created_at", (uid,))
        )
        if t
    ]
    buys = [
        (_ts(r["purchased_at"]), r)
        for r in db.fetchall(
            "SELECT course_title, purchased_at, price_paid FROM purchases WHERE user_id=? ORDER BY purchased_at", (uid,)
        )
    ]

    def after(t: datetime, email: dict | None = None) -> dict:
        out = {}
        if email:
            out["email"] = {
                "subject": email["subject"],
                "sent_at": email["sent_at"],
                "clicked_at": email["first_clicked_at"],
                "clicks": email["click_count"] or 0,
            }
        nxt = next((e for e in events if e > t + timedelta(minutes=2)), None)
        out["next_visit"] = nxt.strftime(TS) if nxt and nxt <= t + window else None
        b = next((r for bt, r in buys if bt and t <= bt <= t + window), None)
        if b:
            out["outcome"] = "bought"
            out["bought"] = {"course": b["course_title"], "at": b["purchased_at"], "paid": b["price_paid"]}
        elif now >= t + window:
            out["outcome"] = "did_not_buy"
        else:
            out["outcome"] = "waiting"
            out["days_left"] = max(0, (t + window - now).days)
        return out

    adopted = {
        a["lead_id"]: a
        for a in db.fetchall(
            """SELECT x.lead_id, x.arm, e.variant_label, e.test_name FROM experiment_assignments x
           JOIN adopted_emails e ON e.id = x.experiment_id WHERE x.user_id=? AND x.experiment_type='adoption'""",
            (uid,),
        )
    }
    items = []
    for d in decs:
        t = _ts(d["created_at"])
        if not t:
            continue
        task = tasks.get(d["id"])
        items.append(
            {
                "kind": "decision",
                "id": d["id"],
                "at": d["created_at"],
                "trigger": d["trigger_reason"],
                "action": d["action"],
                "label": ACTION_LABEL.get(d["action"], d["action"]),
                "model_best": d["model_best"],
                "model_best_label": ACTION_LABEL.get(d["model_best"], d["model_best"]),
                "policy": d["policy"],
                "policy_text": POLICY_TEXT.get(d["policy"] or "model", d["policy"]),
                "propensity": d["propensity"],
                "base_probability": d["base_probability"],
                "price": d["price"],
                "model_version": d["model_version"],
                "options": relabel(_json(d["options_json"], [])),
                "slot_price": d["slot_price"],
                "call_value": d["call_value"],
                "task": (
                    {
                        "type": task["task_type"],
                        "status": task["status"],
                        "outcome": task["outcome"],
                        "done_at": task["done_at"],
                        "done_by": task["done_by"],
                    }
                    if task
                    else None
                ),
                "adopted_email": (
                    {
                        "arm": adopted[d["lead_id"]]["arm"],
                        "variant": adopted[d["lead_id"]]["variant_label"],
                        "test": adopted[d["lead_id"]]["test_name"],
                    }
                    if d["lead_id"] in adopted
                    else None
                ),
                **after(t, by_lead.get(d["lead_id"])),
            }
        )
    names = {("campaign", c["id"]): c["name"] for c in db.fetchall("SELECT id, name FROM campaign_schedules")}
    names.update({("ab", a["id"]): a["name"] for a in db.fetchall("SELECT id, name FROM ab_tests")})
    for a in db.fetchall(
        """SELECT experiment_type, experiment_id, arm, probability, assigned_at FROM experiment_assignments
                            WHERE user_id=? AND experiment_type IN ('campaign', 'ab')
                            ORDER BY assigned_at DESC LIMIT 10""",
        (uid,),
    ):
        t = _ts(a["assigned_at"])
        if not t:
            continue
        sent = a["arm"] not in ("control", "holdout")
        key = "campaign_id" if a["experiment_type"] == "campaign" else "ab_test_id"
        mail = next((e for e in emails if e[key] == a["experiment_id"]), None) if sent else None
        items.append(
            {
                "kind": a["experiment_type"],
                "at": a["assigned_at"],
                "name": names.get((a["experiment_type"], a["experiment_id"]), f"#{a['experiment_id']}"),
                "arm": a["arm"],
                "sent": sent,
                "probability": a["probability"],
                **after(t, mail),
            }
        )
    items.sort(key=lambda x: x["at"] or "", reverse=True)
    return items


def attribution(lead_id: int) -> dict:
    """The person's timeline (behaviour, emails, clicks, contact records, purchases), first touch and the last
    touch before the first purchase."""
    lead = db.fetchone("SELECT user_id FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise NotFound("Lead not found")
    uid = lead["user_id"]
    events = db.fetchall(
        """SELECT 'behaviour' AS kind, event_type AS label, course_slug, created_at
                            FROM behaviour_events WHERE user_id=?""",
        (uid,),
    )
    emails = db.fetchall(
        """SELECT 'email' AS kind, 'email_sent' AS label, NULL AS course_slug, sent_at AS created_at
                            FROM email_sends WHERE user_id=?""",
        (uid,),
    )
    clicks = db.fetchall(
        """SELECT 'email' AS kind, 'email_clicked' AS label, NULL AS course_slug,
                                   first_clicked_at AS created_at
                            FROM email_sends WHERE user_id=? AND first_clicked_at IS NOT NULL""",
        (uid,),
    )
    purchases = db.fetchall(
        """SELECT 'purchase' AS kind, course_title AS label, course_slug, purchased_at AS created_at
                               FROM purchases WHERE user_id=?""",
        (uid,),
    )
    touches = db.fetchall(
        """SELECT 'lead_created' AS kind, trigger_reason AS label, course_slug, created_at
                             FROM leads WHERE user_id=?""",
        (uid,),
    )
    timeline = sorted(
        [e for e in events + emails + clicks + purchases + touches if e["created_at"]], key=lambda e: e["created_at"]
    )
    first_purchase_at = min((p["created_at"] for p in purchases if p["created_at"]), default=None)
    last_touch = None
    if first_purchase_at:
        before = [e for e in timeline if e["created_at"] < first_purchase_at and e["kind"] != "purchase"]
        last_touch = before[-1] if before else None
    return {
        "lead_id": lead_id,
        "user_id": uid,
        "timeline": timeline,
        "first_touch": timeline[0] if timeline else None,
        "last_touch_before_purchase": last_touch,
        "converted": first_purchase_at is not None,
    }


def export_rows() -> list[dict]:
    """One row per person for the CSV export (no internal ids)."""
    rows = db.fetchall(f"""
        SELECT l.id AS lead_id, l.user_id, u.name, u.email, up.phone, l.course_type, up.current_occupation, up.city,
               l.lead_score, l.conversion_probability, l.recommended_action, l.persona, l.plv,
               l.trigger_reason, l.email_sent, l.model_version, l.created_at,
               COALESCE(s.last_seen, u.created_at) AS last_on_website,
               CASE WHEN po.stage='Lost' THEN 'lost' ELSE '' END AS status, po.lost_reason,
               up.do_not_email, up.do_not_call,
               CASE WHEN u.email LIKE '{SIM_LIKE}' THEN 'yes' ELSE 'no' END AS simulated
        FROM {LATEST} l JOIN users u ON l.user_id = u.id
        LEFT JOIN user_profiles up ON up.user_id = l.user_id
        LEFT JOIN pipeline_overrides po ON po.user_id = l.user_id
        LEFT JOIN (SELECT user_id, MAX(COALESCE(last_active, login_at)) AS last_seen FROM user_sessions
                   GROUP BY user_id) s ON s.user_id = l.user_id
        ORDER BY l.lead_score DESC""")
    add_owner_names(rows)
    for r in rows:
        r.pop("owner_id", None)
        r.pop("user_id", None)
    return rows
