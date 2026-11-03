"""
The people who use the CRM: accounts with roles, who looks after which lead, the audit log.

Roles (checked by the API on every request, not only hidden in the dashboard):
  admin       everything, including the team, the assignment rule and the audit log
  marketing   campaigns, A/B tests, coupons, journeys, the learning loop, exports, and every lead
  counsellor  leads, today's actions, callbacks, pipeline, Q&A; changes only their own leads and unassigned
              ones (record-level access)

Signing in. The first admin (the "owner") is the account named by CRM_OWNER_EMAIL in backend/.env. With
CRM_OWNER_PASSWORD set there, that password signs the owner in and stays managed in .env. Without it, a random
password is made at the first start and written once to backend/data/initial-admin-password.txt (never to the log),
and the owner must choose a new one at the first sign-in, like any other account. Every other account has its own
password, stored as a salted PBKDF2-SHA256 hash (app.core.security), never in clear text. An account made or reset by
an admin has to choose its own password at the first sign-in. After 5 wrong passwords an address is locked for 15
minutes (crm_settings.json team.login_lockout).

Lead owners. Every lead has at most one owner on the team. Leads that arrive after the team was set up
(assign_from: the first start of this database) and any lead with work waiting for the team (an open call / WhatsApp
task or callback request) are given to an active counsellor automatically (round_robin: in turn;
least_loaded: whoever has the fewest open tasks and callbacks). Older leads without open work stay unassigned
until an admin hands them out (Team page, "also older open leads") or a counsellor takes one.

Only the learners are simulated. A simulated learner is a lead like any other: it gets an owner, its call and
WhatsApp tasks wait in Today's actions for the team, and when someone on the team presses Call, the simulated
learner answers or not (app.simulation.live, World.phone_call). Nobody on the team is simulated.

Open call / WhatsApp tasks that nobody does within task_expiry_days (7) close themselves as "expired", so the
list shows what is still worth doing.

The audit log names the people on the team and refers to leads only by number (it keeps no notes, email
addresses or phone numbers), so it can be kept after a learner deletes their account.
"""

import contextlib
import json
import logging
import sqlite3
from datetime import datetime, timedelta

from app import db
from app.core import rules, security

log = logging.getLogger(__name__)

ROLES = ("admin", "marketing", "counsellor")
ROLE_LABEL = {"admin": "Admin", "marketing": "Marketing", "counsellor": "Counsellor"}
RULES = ("round_robin", "least_loaded")
FMT = "%Y-%m-%d %H:%M:%S"
SYSTEM = {"id": None, "name": "CRM (automatic)", "role": "system"}
SIM_LIKE = f"%@{rules.SIMULATED_DOMAIN}"
EDITABLE_SETTINGS = ("auto_assign", "assignment_rule", "task_sla_hours", "callback_sla_hours", "task_expiry_days")

LOCK_NS = "crm:"  # login_attempts keys of the team (learners use "learner:")


def now_s():
    return datetime.now().strftime(FMT)


def _parse(v):
    try:
        return datetime.strptime(str(v)[:19], FMT)
    except (TypeError, ValueError):
        return None


# passwords (app.core.security)
hash_password = security.hash_password
verify_password = security.verify_password
password_problem = security.password_problem


# accounts
def _one(sql, params=()):
    return db.fetchone(sql, params)


def member(member_id):
    return _one("SELECT * FROM team_members WHERE id=?", (member_id,)) if member_id is not None else None


def member_by_email(email):
    return _one("SELECT * FROM team_members WHERE lower(email)=lower(?)", ((email or "").strip(),))


def members(active_only=False):
    return db.fetchall(
        "SELECT * FROM team_members"
        + (" WHERE active=1" if active_only else "")
        + " ORDER BY is_owner DESC, active DESC, name COLLATE NOCASE, id"
    )


def names():
    """{member id: name} for everyone who ever had an account (also switched-off ones)."""
    return {m["id"]: m["name"] for m in members()}


def public(m):
    if not m:
        return None
    return {
        "id": m["id"],
        "name": m["name"],
        "email": m["email"],
        "role": m["role"],
        "role_label": ROLE_LABEL.get(m["role"], m["role"]),
        "is_owner": bool(m["is_owner"]),
        "active": bool(m["active"]),
        "takes_new_leads": bool(m["takes_new_leads"]),
        "must_change_password": bool(m.get("must_change_password")),
        "created_at": m.get("created_at"),
        "last_login_at": m.get("last_login_at"),
    }


def owner_account():
    return _one("SELECT * FROM team_members WHERE is_owner=1")


def ensure_owner(email, name="Admin"):
    """The account named by CRM_OWNER_EMAIL is the owner, an admin. Without CRM_OWNER_PASSWORD in .env it gets a random
    first password (see the module docstring)."""
    from app.core.config import get_settings

    settings = get_settings()
    email = (email or "").strip().lower()
    owner = owner_account()
    if owner is None:
        clash = member_by_email(email)
        if clash:
            db.execute("""UPDATE team_members SET is_owner=1, role='admin', active=1 WHERE id=?""", (clash["id"],))
        else:
            db.execute(
                """INSERT INTO team_members (name, email, role, is_owner, takes_new_leads)
                          VALUES (?, ?, 'admin', 1, 0)""",
                (name, email),
            )
    elif (owner["email"] or "").lower() != email:
        clash = member_by_email(email)
        if clash and clash["id"] != owner["id"]:
            log.warning(
                "CRM_OWNER_EMAIL now belongs to another account (#%s); the owner account keeps its old "
                "address in the team list. Signing in with CRM_OWNER_EMAIL still opens the owner account.",
                clash["id"],
            )
        else:
            db.execute("UPDATE team_members SET email=? WHERE id=?", (email, owner["id"]))
    owner = owner_account()
    if owner and not settings.owner_password_from_env and not owner.get("password_hash"):
        first = security.generate_password()
        set_password(owner["id"], first, must_change=True)
        path = settings.initial_password_file
        try:
            path.write_text(
                "X Education CRM: the first password of the owner account\n\n"
                f"   email     {email}\n"
                f"   password  {first}\n\n"
                "Sign in to the CRM with these and choose your own password; this file is then deleted.\n",
                encoding="utf-8",
            )
        except OSError:
            log.warning("Could not write %s", path)
        log.warning(
            "Owner account created for %s. Its first password is in %s; you choose your own at the first sign-in.",
            email,
            path,
        )
        owner = owner_account()
    return owner


def create_member(name, email, role, password):
    db.execute(
        """INSERT INTO team_members (name, email, role, password_hash, takes_new_leads, must_change_password,
                                            password_changed_at)
                  VALUES (?, ?, ?, ?, ?, 1, ?)""",
        (name.strip(), email.strip().lower(), role, hash_password(password), 1 if role == "counsellor" else 0, now_s()),
    )
    return member_by_email(email)


def set_password(member_id, password, must_change):
    db.execute(
        "UPDATE team_members SET password_hash=?, must_change_password=?, password_changed_at=? WHERE id=?",
        (hash_password(password), 1 if must_change else 0, now_s(), member_id),
    )


# signing in: lock-out after repeated wrong passwords
def _lock_conf():
    c = (rules.S.get("team") or {}).get("login_lockout") or {}
    return max(1, int(c.get("max_failures", 5))), max(1, int(c.get("minutes", 15)))


def _lock_key(email, ns):
    return ns + (email or "").strip().lower()


def locked_seconds(email, ns=LOCK_NS):
    """How long this address is still locked (0 = it may try)."""
    r = _one("SELECT locked_until FROM login_attempts WHERE email=?", (_lock_key(email, ns),))
    until = _parse(r["locked_until"]) if r else None
    return max(0, int((until - datetime.now()).total_seconds())) if until else 0


def record_failure(email, ns=LOCK_NS):
    """Counts a wrong password. Returns (failures in this window, locked until or None)."""
    mx, minutes = _lock_conf()
    email = _lock_key(email, ns)
    r = _one("SELECT * FROM login_attempts WHERE email=?", (email,))
    now = datetime.now()
    first = _parse(r["first_failed_at"]) if r else None
    until = _parse(r["locked_until"]) if r else None
    if r is None or first is None or now - first > timedelta(minutes=minutes) or (until and until <= now):
        failures, first = 1, now
    else:
        failures = int(r["failures"] or 0) + 1
    locked = now + timedelta(minutes=minutes) if failures >= mx else None
    db.execute(
        """INSERT INTO login_attempts (email, failures, first_failed_at, locked_until) VALUES (?,?,?,?)
                  ON CONFLICT(email) DO UPDATE SET failures=excluded.failures, first_failed_at=excluded.first_failed_at,
                  locked_until=excluded.locked_until""",
        (email, failures, first.strftime(FMT), locked.strftime(FMT) if locked else None),
    )
    return failures, locked


def clear_failures(email, ns=LOCK_NS):
    db.execute("DELETE FROM login_attempts WHERE email=?", (_lock_key(email, ns),))


def authenticate(email, password):
    """The account for these credentials, or None. Same answer (and about the same time) for a wrong address, a wrong
    password and a switched-off account."""
    from app.core.config import get_settings

    settings = get_settings()
    email = (email or "").strip().lower()
    password = password or ""
    owner_email = (settings.crm_owner_email or "").strip().lower()
    if owner_email and security.constant_time_equals(email, owner_email) and settings.owner_password_from_env:
        if security.constant_time_equals(password, settings.crm_owner_password or ""):
            return ensure_owner(owner_email, settings.crm_owner_name)
        security.waste_time(password)
        return None
    m = member_by_email(email)
    if m is None and owner_email and security.constant_time_equals(email, owner_email):
        m = ensure_owner(owner_email, settings.crm_owner_name)
    if not m or not m["active"] or not m["password_hash"]:
        security.waste_time(password)
        return None
    return m if verify_password(password, m["password_hash"]) else None


# settings the admin can change (kept in the database, over crm_settings.json)
def _setting(key):
    return db.app_setting("team." + key)


def _put_setting(key, value):
    db.put_app_setting("team." + key, value)


def get_settings():
    out = {k: v for k, v in (rules.S.get("team") or {}).items() if not k.startswith("_")}
    for k in EDITABLE_SETTINGS:
        raw = _setting(k)
        if raw is not None:
            with contextlib.suppress(ValueError):  # a broken value keeps the default
                out[k] = json.loads(raw)
    if out.get("assignment_rule") not in RULES:
        out["assignment_rule"] = "round_robin"
    return out


def put_settings(values):
    for k, v in values.items():
        if k in EDITABLE_SETTINGS and v is not None:
            _put_setting(k, json.dumps(v))
    return get_settings()


def assign_from():
    """When the team was set up (the first start of this database): leads that arrive from then on are given out
    automatically; older ones only when they have work waiting for the team, or when an admin asks."""
    v = _setting("_assign_from")
    if not v:
        v = now_s()
        _put_setting("_assign_from", v)
    return v


# audit log
def audit(actor, action, target_type=None, target_id=None, detail=None):
    actor = actor or SYSTEM
    try:
        db.execute(
            """INSERT INTO audit_log (member_id, member_name, role, action, target_type, target_id, detail)
                      VALUES (?,?,?,?,?,?,?)""",
            (
                actor.get("id"),
                actor.get("name"),
                actor.get("role"),
                action,
                target_type,
                target_id,
                (str(detail)[:500] if detail else None),
            ),
        )
    except sqlite3.Error as e:
        log.warning("Could not record %s in the audit log: %s", action, e)


# lead owners
def owner_of(user_id):
    try:
        r = db.fetchone("SELECT member_id FROM lead_owners WHERE user_id=?", (user_id,))
    except sqlite3.OperationalError:
        return None
    return r["member_id"] if r else None


def set_owner(user_id, member_id, how):
    db.execute(
        """INSERT INTO lead_owners (user_id, member_id, assigned_at, how) VALUES (?, ?, ?, ?)
                  ON CONFLICT(user_id) DO UPDATE SET member_id=excluded.member_id, assigned_at=excluded.assigned_at,
                  how=excluded.how""",
        (user_id, member_id, now_s(), how),
    )


def clear_owner(user_id):
    db.execute("DELETE FROM lead_owners WHERE user_id=?", (user_id,))


def owner_label(member_id, team_names):
    """(owner id or None, name shown): the person on the team, or 'Unassigned'."""
    if member_id is None:
        return None, "Unassigned"
    return member_id, team_names.get(member_id, f"#{member_id}")


def can_change(me, user_id, email=None):
    """(True, None) if this person on the team may change this lead, else (False, why). Counsellors change their own
    leads and unassigned ones; admins and marketing change any lead. The same for real and simulated learners."""
    if me.get("role") in ("admin", "marketing"):
        return True, None
    owner = owner_of(user_id)
    if owner is None or owner == me.get("id"):
        return True, None
    m = member(owner)
    return False, f"This lead belongs to {m['name'] if m else 'another counsellor'}. Ask an admin to reassign it."


def eligible_counsellors():
    return db.fetchall("""SELECT * FROM team_members WHERE role='counsellor' AND active=1 AND takes_new_leads=1
                        ORDER BY id""")


def _open_work():
    """{member id: open call/WhatsApp tasks + open callback requests of their leads, number of leads}."""
    out = {}
    for sql, k in (
        (
            """SELECT lo.member_id AS m, COUNT(*) AS n FROM lead_owners lo
               JOIN sales_tasks t ON t.user_id = lo.user_id AND t.status = 'open' GROUP BY lo.member_id""",
            0,
        ),
        (
            """SELECT lo.member_id AS m, COUNT(*) AS n FROM lead_owners lo
               JOIN callback_requests c ON c.user_id = lo.user_id AND c.status = 'open' GROUP BY lo.member_id""",
            0,
        ),
        ("SELECT member_id AS m, COUNT(*) AS n FROM lead_owners GROUP BY member_id", 1),
    ):
        for r in db.fetchall(sql):
            out.setdefault(r["m"], [0, 0])[k] += r["n"]
    return out


def auto_assign(limit=500, actor=None, backlog=False, force=False):
    """Give leads without an owner to active counsellors. Returns [(user id, member id), ...].
    Every minute (and from "Assign now"): leads that arrived since the team was set up (assign_from) and any
    lead with work waiting for the team (an open call / WhatsApp task or callback request).
    backlog=True (an admin, Team page): also every older open lead (not a customer, not closed as lost).
    Nothing happens while nobody takes new leads, or while auto_assign is off (force=True: an admin's "Assign
    now" works even then)."""
    conf = get_settings()
    if not conf.get("auto_assign", True) and not force:
        return []
    team = eligible_counsellors()
    if not team:
        return []
    older = (
        """OR (NOT EXISTS (SELECT 1 FROM purchases p WHERE p.user_id = u.id)
                    AND NOT EXISTS (SELECT 1 FROM pipeline_overrides o WHERE o.user_id = u.id AND o.stage = 'Lost'))"""
        if backlog
        else ""
    )
    todo = db.fetchall(
        f"""SELECT u.id FROM users u
            WHERE u.id NOT IN (SELECT user_id FROM lead_owners)
              AND EXISTS (SELECT 1 FROM leads l WHERE l.user_id = u.id)
              AND (u.created_at >= ?
                   OR EXISTS (SELECT 1 FROM sales_tasks t WHERE t.user_id = u.id AND t.status = 'open')
                   OR EXISTS (SELECT 1 FROM callback_requests c WHERE c.user_id = u.id AND c.status = 'open')
                   {older})
            ORDER BY u.id LIMIT ?""",
        (assign_from(), int(limit)),
    )
    if not todo:
        return []
    rule = conf["assignment_rule"]
    ids = [m["id"] for m in team]
    who = {m["id"]: m["name"] for m in team}
    work = _open_work() if rule == "least_loaded" else {}
    for i in ids:
        work.setdefault(i, [0, 0])
    last = int(_setting("_rr_last") or 0)
    out = []
    for r in todo:
        if rule == "least_loaded":
            mid = min(ids, key=lambda i: (work[i][0], work[i][1], i))
            work[mid][1] += 1
        else:
            nxt = [i for i in ids if i > last]
            mid = nxt[0] if nxt else ids[0]
            last = mid
        # INSERT OR IGNORE: if someone gave this lead to a person by hand in the meantime, that stays
        db.execute(
            "INSERT OR IGNORE INTO lead_owners (user_id, member_id, assigned_at, how) VALUES (?, ?, ?, 'auto')",
            (r["id"], mid, now_s()),
        )
        audit(
            actor or SYSTEM,
            "lead_assigned",
            "person",
            r["id"],
            f"{'older lead, ' if backlog else ''}automatically ({rule.replace('_', ' ')}) to {who[mid]}",
        )
        out.append((r["id"], mid))
    if rule != "least_loaded":
        _put_setting("_rr_last", str(last))
    return out


def expire_tasks():
    """Open call / WhatsApp tasks that nobody did within task_expiry_days close themselves ('expired'), so Today's
    actions shows what is still worth doing (the learner's situation has changed by then). Returns how many."""
    days = float(get_settings().get("task_expiry_days", 7) or 0)
    if days <= 0:
        return 0
    cut = (datetime.now() - timedelta(days=days)).strftime(FMT)
    old = db.fetchall("SELECT id, user_id FROM sales_tasks WHERE status='open' AND created_at < ?", (cut,))
    if not old:
        return 0
    db.execute(
        """UPDATE sales_tasks SET status='skipped', outcome=?, done_at=?
                  WHERE status='open' AND created_at < ?""",
        (f"expired: nobody did it within {days:g} days", now_s(), cut),
    )
    audit(SYSTEM, "tasks_expired", None, None, f"{len(old)} open task(s) older than {days:g} days")
    return len(old)


def release_leads(member_id):
    """A switched-off or deleted account's leads become unassigned (the next automatic run gives them out again)."""
    n = (db.fetchone("SELECT COUNT(*) AS c FROM lead_owners WHERE member_id=?", (member_id,)) or {}).get("c", 0)
    db.execute("DELETE FROM lead_owners WHERE member_id=?", (member_id,))
    return n


# how the team is doing
def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def performance(days=30):
    """One row per counsellor (plus 'Unassigned'): leads looked after (and how many of them are simulated learners),
    open and overdue tasks and callbacks, tasks done by the team and how fast (median hours from task to outcome),
    purchases and revenue in the period. Owner-centred, like a standard sales-rep report. Tasks closed by the
    starting history have no done_by and are not counted as the team's work."""
    conf = get_settings()
    task_sla, cb_sla = float(conf.get("task_sla_hours", 24)), float(conf.get("callback_sla_hours", 4))
    now = datetime.now()
    since = now - timedelta(days=int(days))
    people = db.fetchall(
        """SELECT u.id AS user_id, (u.email LIKE ?) AS sim, lo.member_id,
                  EXISTS(SELECT 1 FROM purchases p WHERE p.user_id = u.id) AS customer,
                  EXISTS(SELECT 1 FROM pipeline_overrides o WHERE o.user_id = u.id AND o.stage = 'Lost') AS lost
           FROM users u LEFT JOIN lead_owners lo ON lo.user_id = u.id
           WHERE EXISTS (SELECT 1 FROM leads l WHERE l.user_id = u.id)""",
        (SIM_LIKE,),
    )
    group = {}
    for p in people:
        group[p["user_id"]] = p["member_id"] if p["member_id"] is not None else "none"
    rows = {}

    def row(key):
        return rows.setdefault(
            key,
            {
                "leads": 0,
                "simulated_leads": 0,
                "open_leads": 0,
                "lost": 0,
                "open_tasks": 0,
                "overdue_tasks": 0,
                "tasks_done": 0,
                "_hours": [],
                "callbacks_open": 0,
                "callbacks_overdue": 0,
                "bought": 0,
                "revenue": 0.0,
            },
        )

    for p in people:
        r = row(group[p["user_id"]])
        r["leads"] += 1
        r["simulated_leads"] += 1 if p["sim"] else 0
        r["lost"] += 1 if p["lost"] else 0
        r["open_leads"] += 1 if not p["customer"] and not p["lost"] else 0
    for t in db.fetchall("SELECT user_id, status, created_at, done_at, done_by FROM sales_tasks"):
        key = group.get(t["user_id"])
        if key is None:
            continue
        r, made, done = row(key), _parse(t["created_at"]), _parse(t["done_at"])
        if t["status"] == "open":
            r["open_tasks"] += 1
            if made and (now - made).total_seconds() > task_sla * 3600:
                r["overdue_tasks"] += 1
        elif t["status"] == "done" and done and done >= since and t["done_by"]:
            r["tasks_done"] += 1
            if made:
                r["_hours"].append(max(0.0, (done - made).total_seconds() / 3600))
    for c in db.fetchall("SELECT user_id, created_at FROM callback_requests WHERE status='open'"):
        key = group.get(c["user_id"])
        if key is None:
            continue
        r, made = row(key), _parse(c["created_at"])
        r["callbacks_open"] += 1
        if made and (now - made).total_seconds() > cb_sla * 3600:
            r["callbacks_overdue"] += 1
    buyers = {}
    for b in db.fetchall("SELECT user_id, price_paid FROM purchases WHERE purchased_at >= ?", (since.strftime(FMT),)):
        buyers.setdefault(b["user_id"], 0.0)
        buyers[b["user_id"]] += float(b["price_paid"] or 0)
    for uid, paid in buyers.items():
        key = group.get(uid)
        if key is not None:
            row(key)["bought"] += 1
            row(key)["revenue"] += paid
    out = []
    accounts = members()
    for m in accounts:
        if m["role"] != "counsellor" and m["id"] not in rows:
            continue  # admins and marketing show up only if they look after leads
        if not m["active"] and m["id"] not in rows:
            continue
        out.append(
            {
                "key": m["id"],
                "name": m["name"],
                "role": m["role"],
                "active": bool(m["active"]),
                "takes_new_leads": bool(m["takes_new_leads"]),
                **row(m["id"]),
            }
        )
    known = {m["id"] for m in accounts}
    for key in [k for k in rows if isinstance(k, int) and k not in known]:
        out.append(
            {
                "key": key,
                "name": f"#{key} (account deleted)",
                "role": "counsellor",
                "active": False,
                "takes_new_leads": False,
                **row(key),
            }
        )
    out.append(
        {"key": "none", "name": "Unassigned", "role": None, "active": None, "takes_new_leads": None, **row("none")}
    )
    for r in out:
        hours = r.pop("_hours")
        r["median_hours_to_done"] = round(_median(hours), 1) if hours else None
        r["revenue"] = round(r["revenue"], 0)
        r["conversion_rate"] = round(r["bought"] / r["leads"], 3) if r["leads"] else None
    return {
        "days": int(days),
        "task_sla_hours": task_sla,
        "callback_sla_hours": cb_sla,
        "rows": out,
        "generated_at": now.strftime(FMT),
    }
