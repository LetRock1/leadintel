"""
Ask the CRM: plain-English questions answered only from live data, and drafts that a person sends.

How it answers, without guessing:
  1. The question is matched to one of a fixed set of read-only data tools (who to call, hot leads, pipeline,
     learning loop, A/B tests, CRM impact, revenue, campaigns, one lead). Keyword rules do this; with GEMINI_API_KEY
     set, Gemini picks the tool when the rules are unsure.
  2. The tool reads the live database and returns its numbers plus where they came from.
  3. The answer is written from those numbers by a template. With Gemini, Gemini may re-phrase it, but if its text
     contains any number that is not in the tool's output, its text is thrown away and the template answer is used.
     So every number shown comes from the data.
  4. Drafts (an email to a lead, an A/B test plan) are only drafts: nothing is sent. A person opens them on the lead
     page or the A/B tests page and sends them.
Every question, the tools used and the answer are logged (copilot_log).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from app import db
from app.core import rules
from app.services import catalog, gemini

log = logging.getLogger(__name__)

SIM_SUFFIX = "@" + rules.SIMULATED_DOMAIN
WINDOW_DAYS = int(rules.S["outcome_window_days"])
CURRENCY = rules.S["business"].get("currency_symbol", "")

SUGGESTIONS = [
    "How many leads came in this week?",
    "Who should we call today?",
    "Which leads are most likely to buy?",
    "How is the pipeline looking?",
    "Should we hire another counsellor?",
    "Is the learning loop fooling itself?",
    "What do our emails and calls add?",
    "How are the A/B tests doing?",
    "Is the CRM actually making a difference?",
    "What is a call slot worth today?",
    "How much did we sell in the last 30 days?",
    "Draft an A/B test for a better subject line",
]

TOOLS = {
    "call_list": "Open call tasks chosen by next-best-action, the ones a call helps most first",
    "capacity": "The price of a call slot today and how it was worked out",
    "hot_leads": "Leads most likely to buy (not customers yet)",
    "pipeline": "The open pipeline in rupees: what comes in anyway and what the team can still add",
    "planner": "What one more counsellor or a bigger discount budget would add, and the discount budget now",
    "learning": "The latest learning-loop run and its honest check on the untouched control group",
    "outreach": "What each of the CRM's steps adds to the chance to buy (kept out of the lead score)",
    "ab_tests": "A/B tests (running and final) and adopted winners",
    "impact": "People the CRM worked on against the control group it never contacts",
    "revenue": "Purchases, revenue and discounts in a period",
    "counts": "How many leads, new sign-ups, customers, call-backs and tasks there are (real and simulated)",
    "campaigns": "Campaigns and their effect against their random hold-out group",
    "lead": "One lead: score, reasons, recommended next step, what-if path",
    "draft_email": "Draft an email to one lead (not sent)",
    "draft_ab_test": "Draft an A/B test plan (not created until a person does it)",
    "help": "What I can answer",
}

RULES = [  # (intent, regex): first match wins; drafts before look-ups
    (
        "draft_ab_test",
        r"\b(draft|plan|design|create|set ?up|suggest|propose)\b.*\b(a/?b|ab test|experiment|test)\b"
        r"|\b(a/?b|ab) test\b.*\b(draft|plan|design|idea)",
    ),
    ("draft_email", r"\b(draft|write|compose|prepare)\b.*\b(e-?mail|mail|message)\b"),
    (
        "planner",
        r"\b(hire|hiring|counsell?ors?|more staff|discount budget|coupon budget|budget|planner|plan the month)\b",
    ),
    ("capacity", r"\b(slot|capacity|shadow price|bid price)\b"),
    (
        "outreach",
        r"\b(outreach|own steps|natural experiment|threshold|cut-?off|decision line|anchored)\b"
        r"|\b(what|how much)\b.*\b(email|emails|coupon|coupons|call|calls|whatsapp|campaign|campaigns|steps?)\b.*"
        r"\b(add|adds|worth|effect|lift|do)\b\??$",
    ),
    ("call_list", r"\b(call|calls|phone|ring|dial)\b"),
    ("learning", r"\b(learn|learning|retrain|re-train|fool|honest|model|loop|control group check)\b"),
    ("ab_tests", r"\b(a/?b|ab test|experiment|variant|winner|adopt)\w*"),
    ("impact", r"\b(impact|difference|worth it|working|incremental|lift|without the crm|control group)\b"),
    ("revenue", r"\b(revenue|sales|sold|sell|purchase|purchases|earn|earned|money|income|bought)\b"),
    ("campaigns", r"\bcampaign"),
    ("pipeline", r"\b(pipeline|stage|stages|funnel|board|mql|sql)\b"),
    (
        "hot_leads",
        r"\b(hot|best|top|likely|ready|warm|priorit)\w*\b.*\b(lead|leads|people|learners|buy)\b"
        r"|\bwho (will|is going to|might) buy\b",
    ),
    (
        "counts",
        r"\b(how many|number of|count of|total)\b.*\b(leads?|learners?|people|persons?|customers?|buyers?|students?|"
        r"sign-?ups?|signed up|users?|contacts?|call-?backs?|tasks?)\b",
    ),
    ("help", r"\b(help|what can you|how do i use)\b"),
]


_STEP_INPUTS = ("email_info", "email_coupon_10", "email_coupon_20", "call", "whatsapp", "campaign")


def _num(x, d=0):
    return f"{x:,.{d}f}" if x is not None else "n/a"


def _pct(x, d=1):
    return f"{x * 100:.{d}f}%" if x is not None else "n/a"


def _mid(label: str) -> str:
    """A label inside a sentence: an ordinary first word in lower case, names and abbreviations as they are."""
    first = label.split(" ", 1)[0]
    return label if any(c.isupper() for c in first[1:]) else label[:1].lower() + label[1:]


def _money(x):
    return f"{CURRENCY}{x:,.0f}" if x is not None else "n/a"


def _chances(options_json, action) -> dict:
    """The chance of buying without a step and with this step, from a decision's receipt (empty when unknown)."""
    try:
        opts = {o["action"]: o for o in json.loads(options_json or "[]")}
        return {"p_without": float(opts["none"]["p_convert"]), "p_with": float(opts[action]["p_convert"])}
    except (KeyError, TypeError, ValueError):
        return {}


class Copilot:
    # routing
    def route(self, q: str):
        text = q.lower()
        email = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", q)
        if email and not re.search(r"\bdraft|write|compose", text):
            return "lead", {"query": email.group(0)}
        for intent, rx in RULES:
            if re.search(rx, text):
                args = {}
                if intent == "draft_email":
                    args["query"] = self._name_in(q)
                if intent == "counts":
                    args["days"] = self._period(text, default=7)
                if intent == "revenue":
                    m = re.search(r"(\d+)\s*(day|days|week|weeks|month|months)", text)
                    days = 30
                    if m:
                        n = int(m.group(1))
                        unit = m.group(2)
                        days = n * (7 if unit.startswith("week") else 30 if unit.startswith("month") else 1)
                    elif "week" in text:
                        days = 7
                    elif "today" in text:
                        days = 1
                    args["days"] = max(1, min(days, 365))
                if intent == "draft_ab_test":
                    args["text"] = text
                return intent, args
        name = self._name_in(q)
        if name:
            return "lead", {"query": name}
        return None, {}

    @staticmethod
    def _period(text: str, default: int = 30) -> int:
        """'last 3 weeks' -> 21, 'this month' -> 30, 'today' -> 1 (days)."""
        m = re.search(r"(\d+)\s*(day|days|week|weeks|month|months)", text)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            days = n * (7 if unit.startswith("week") else 30 if unit.startswith("month") else 1)
        elif "today" in text:
            days = 1
        elif "week" in text:
            days = 7
        elif "month" in text:
            days = 30
        else:
            days = default
        return max(1, min(days, 365))

    def _name_in(self, q: str):
        """A learner's name mentioned in the question ('tell me about Riya Sharma')."""
        m = re.search(r"\b(?:about|for|to|on|is|lead)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", q)
        if not m:
            return None
        cand = m.group(1).strip()
        return cand if db.fetchone("SELECT id FROM users WHERE name LIKE ? LIMIT 1", (f"%{cand}%",)) else None

    # tools
    def call_list(self, n: int = 5):
        rows = db.fetchall("""SELECT t.id, t.user_id, t.lead_id, t.expected_gain, u.name, u.email, l.lead_score,
                                     d.options_json
                              FROM sales_tasks t JOIN users u ON u.id = t.user_id LEFT JOIN leads l ON l.id = t.lead_id
                              LEFT JOIN nba_decisions d ON d.id = t.decision_id
                              WHERE t.status='open' AND t.task_type='call' ORDER BY t.expected_gain DESC""")
        cap = int(rules.S.get("daily_call_capacity", 20))
        top = rows[:n]
        facts = {
            "open_calls": len(rows),
            "daily_capacity": cap,
            "top": [
                {
                    "name": r["name"],
                    "lead_id": r["lead_id"],
                    "score": round(r["lead_score"] or 0),
                    **_chances(r["options_json"], "call"),
                    "simulated": (r["email"] or "").endswith(SIM_SUFFIX),
                }
                for r in top
            ],
        }
        if not rows:
            text = (
                "There are no open call tasks right now. Next-best-action creates a call only when it is expected "
                "to change the outcome by more than a call slot is worth today."
            )
        else:
            lines = [
                f"{i + 1}. {t['name']}: score {t['score']}"
                + (
                    f", a call raises the chance of buying from {t['p_without'] * 100:.0f}% to {t['p_with'] * 100:.0f}%"
                    if t.get("p_with") is not None
                    else ""
                )
                for i, t in enumerate(facts["top"])
            ]
            text = f"{len(rows)} open call tasks (up to {cap} new calls a day). Start with:\n" + "\n".join(lines)
        return (
            text,
            facts,
            "sales_tasks (open calls) and leads",
            [{"type": "lead", "lead_id": t["lead_id"], "label": t["name"]} for t in facts["top"] if t["lead_id"]],
        )

    def capacity(self):
        from app.ml import capacity

        s = capacity.current()
        facts = {
            k: s.get(k)
            for k in ("price", "policy", "capacity", "days_seen", "candidates", "per_day", "calls_today", "slots_left")
        }
        used = f"{s['calls_today']} of today's {s['capacity']} slots are used."
        if s["full"]:
            text = f"Today's {s['capacity']} call slots are all used: new calls wait for tomorrow."
        elif s["policy"] == "fcfs":
            text = (
                f"Call slots are not priced yet: {s['note']} Until then calls are given out first come, first "
                f"served, up to {s['capacity']} a day. {used}"
            )
        elif not s["price"]:
            text = (
                f"Call slots are not scarce right now: over the last {s['days_seen']} days about "
                f"{_num(s['per_day'], 1)} decisions a day could use a call profitably, fewer than the "
                f"{s['capacity']} slots, so a slot costs nothing and every call that adds value is made. {used}"
            )
        else:
            text = (
                f"A call slot is worth {_money(s['price'])} right now. Over the last {s['days_seen']} days about "
                f"{_num(s['per_day'], 1)} decisions a day could use a call profitably, for {s['capacity']} slots, "
                f"so a call is created only when it adds more than {_money(s['price'])} beyond the best step "
                f"without a call. {used}"
            )
        return (
            text,
            facts,
            "nba_decisions over the look-back window (capacity-aware next-best-action)",
            [{"type": "page", "to": "/actions", "label": "Open today's actions"}],
        )

    def hot_leads(self, n: int = 5):
        rows = db.fetchall(
            """SELECT l.id AS lead_id, l.user_id, l.lead_score, l.recommended_action, l.course_type,
                                     u.name, u.email
                              FROM leads l JOIN users u ON u.id = l.user_id
                              WHERE l.id IN (SELECT MAX(id) FROM leads GROUP BY user_id)
                                AND l.user_id NOT IN (SELECT user_id FROM purchases)
                              ORDER BY l.lead_score DESC LIMIT ?""",
            (n,),
        )
        facts = {
            "top": [
                {
                    "name": r["name"],
                    "lead_id": r["lead_id"],
                    "score": round(r["lead_score"] or 0, 1),
                    "tier": r["recommended_action"],
                    "course": r["course_type"],
                }
                for r in rows
            ]
        }
        if not rows:
            return "No open leads yet.", facts, "leads (latest per person)", []
        lines = [
            f"{i + 1}. {t['name']}: {t['score']:.0f}% chance to buy within {WINDOW_DAYS} days with no step "
            f"({t['tier']}), {t['course'] or 'no course yet'}"
            for i, t in enumerate(facts["top"])
        ]
        return (
            "Most likely to buy (not customers yet):\n" + "\n".join(lines),
            facts,
            "leads (latest score per person, customers excluded)",
            [{"type": "lead", "lead_id": t["lead_id"], "label": t["name"]} for t in facts["top"]],
        )

    def pipeline(self):
        from app.ml import journeys

        b = journeys.pipeline(limit=1)
        cols = {c["stage"]: c for c in b["columns"]}
        tot = b["totals"]
        facts = {s: {"people": c["count"], "anyway": c["anyway"], "add": c["add"]} for s, c in cols.items()}
        facts["totals"] = tot
        parts = ", ".join(f"{s} {cols[s]['count']:,}" for s in b["stages"])
        top = max((c for s, c in cols.items() if s not in ("Customer", "Lost")), key=lambda c: c["add"], default=None)
        text = (
            f"{parts}.\nIn the next {tot['window_days']} days about {_money(tot['anyway'])} comes in from the open "
            f"leads even if the team does nothing more, and the team can add about {_money(tot['add'])} with the "
            f"recommended step for {_num(tot['work'])} leads. {_num(tot['no_discount'])} leads are more likely "
            f"than not to buy anyway and a coupon would only give money away: they get no discount."
            + (f" The most money to add is in {top['stage']} ({_money(top['add'])})." if top and top["add"] > 0 else "")
        )
        return (
            text,
            facts,
            "pipeline board (each open lead's chance to buy with no step, and what the best step adds)",
            [{"type": "page", "to": "/pipeline", "label": "Open the pipeline"}],
        )

    def planner(self):
        from app.services import planner

        p = planner.overview()
        c, bud = p["counsellor"], p["budget"]
        facts = {
            "extra_adds_per_month": c["extra_adds_per_month"],
            "monthly_cost": c["monthly_cost"],
            "net_per_month": c["net_per_month"],
            "budget": bud.get("budget"),
            "budget_left": bud.get("left"),
        }
        if not c["enough_data"]:
            text = f"Not enough call decisions yet to price a counsellor's time: {c['note']}"
        elif c["extra_adds_per_month"] <= 0:
            text = (
                f"No: the team's {c['slots_now']} call slots a day are enough. Over the last week about "
                f"{_num(c['calls_worth_making_per_day'], 1)} decisions a day could use a call profitably."
            )
        else:
            verdict = "Yes" if c["net_per_month"] > 0 else "Not yet"
            text = (
                f"{verdict}: one more counsellor ({c['extra_slots']} more calls a day) would add about "
                f"{_money(c['extra_adds_per_month'])} a month, against {_money(c['monthly_cost'])} a month in cost "
                f"({_money(c['net_per_month'])} net). From the call decisions of the last week."
            )
        if bud.get("budget") is None:
            m = bud.get("month_without_limit") or {}
            text += "\nThere is no discount budget: a coupon goes out whenever it pays for itself" + (
                f" (about {_money(m.get('discount', 0))} of discount a month at the current pace)."
                if (bud.get("paying") or 0) >= (bud.get("min_decisions") or 30)
                else "."
            )
        else:
            text += f"\nDiscount budget: {_money(bud['budget'])} this month, {_money(max(bud['left'] or 0, 0))} left."
            if bud.get("extra"):
                text += (
                    f" {_money(bud['extra']['amount'])} more would add about "
                    f"{_money(bud['extra']['adds_per_month'])} of extra sales a month."
                )
        return (
            text,
            facts,
            "the CRM's own call and coupon decisions of the last week (planner)",
            [{"type": "page", "to": "/planner", "label": "Open the planner"}],
        )

    def learning(self):
        r = db.fetchone("SELECT * FROM learning_runs WHERE status='done' ORDER BY id DESC LIMIT 1")
        if not r:
            return (
                "The learning loop has not run yet: it needs at least "
                f"{rules.S['learning']['min_new_outcomes']} new known outcomes.",
                {},
                "learning_runs",
                [],
            )
        lj = json.loads(r.get("learned_json") or "{}")
        ctl = lj.get("control") or {}
        pred = ctl.get("predicted") or {}
        actual = ctl.get("actual")
        facts = {
            "as_of": (r["as_of"] or "")[:10],
            "decision": r["lead_decision"],
            "control_people": ctl.get("people"),
            "actual": actual,
            "ours": pred.get("challenger"),
            "naive": pred.get("naive"),
            "naive_would_pick": bool(r.get("naive_would_pick")),
            "outcomes_known": r.get("outcomes_known"),
        }
        decision = {
            "swapped": "replaced the model",
            "kept": "kept the current model",
            "not_enough_data": "waited (not enough control-group data yet)",
        }.get(r["lead_decision"], r["lead_decision"])
        text = f"Latest run ({facts['as_of']}, {_num(r.get('outcomes_known'))} known outcomes): the loop {decision}."
        if actual and pred.get("naive") is not None and pred.get("challenger") is not None:
            over_n = pred["naive"] / actual - 1
            over_o = pred["challenger"] / actual - 1
            text += (
                f"\nOn the untouched control group ({ctl.get('people')} people), {_pct(actual)} actually bought. "
                f"Our retrain expected {_pct(pred['challenger'])}, a naive retrain {_pct(pred['naive'])} "
                f"(it overstates by {over_n * 100:+.0f}%, ours by {over_o * 100:+.0f}%)."
            )
            text += (
                " The usual check (fit on the CRM's own data) would have picked the naive model."
                if facts["naive_would_pick"]
                else " The usual check would not have picked the naive model this time."
            )
        return (
            text,
            facts,
            "learning_runs (latest), honest check on the control group",
            [{"type": "page", "to": "/learning", "label": "Open the learning loop"}],
        )

    def outreach(self):
        from app.services import analytics

        card = analytics.card("model_card.json") or {}
        steps = [e for e in (card.get("own_effects") or []) if e.get("input") in _STEP_INPUTS]
        link = [{"type": "page", "to": "/learning#own-steps", "label": "Open the learning loop"}]
        if not steps:
            return (
                "Not learned yet: the first model the learning loop adopts stores what each step adds.",
                {},
                "lead model card",
                link,
            )
        steps.sort(key=lambda e: -e["points"])
        facts = {e["input"]: round(e["points"], 1) for e in steps}
        text = (
            "What the team's work adds to the chance to buy within 14 days, by step, for a lead with a 30% chance on "
            "their own (the follow-ups after each step included): "
            + "; ".join(f"{_mid(e['label'])} {e['points']:+.1f} points" for e in steps)
            + ". Measured against leads the CRM never contacts and kept out of the lead score, so the score stays "
            "the chance to buy if the team does nothing. To compare the steps on their own, see the learning steps "
            "on the Next-best-action page."
        )
        return text, facts, "lead model in use (learning loop)", link

    def ab_tests(self):
        from app.services import abtests

        tests = abtests.listing()
        ad = abtests.adoption_rows()
        live = [t for t in tests if t.get("state") in ("running", "completed")]
        facts = {
            "tests": [
                {"name": t["name"], "state": t["state"], "verdict": (t.get("verdict") or {}).get("headline")}
                for t in live[:6]
            ],
            "adopted": [
                {"email": a["variant_label"], "audience": a["audience"], "status": a["status"]} for a in ad[:4]
            ],
        }
        if not live:
            text = "No A/B tests have been sent yet."
        else:
            lines = [f"- {t['name']}: {(t.get('verdict') or {}).get('headline', t['state'])}" for t in live[:6]]
            text = "A/B tests:\n" + "\n".join(lines)
        if ad:
            text += "\nAdopted winners: " + "; ".join(
                f"'{a['variant_label']}' for {a['audience']} ({a['status']}"
                + (f": {(a.get('check') or {}).get('why')}" if a.get("check") else "")
                + ")"
                for a in ad[:3]
            )
        return (
            text,
            facts,
            "ab_tests, experiment_assignments and adopted_emails",
            [{"type": "page", "to": "/ab-tests", "label": "Open A/B tests"}],
        )

    def impact(self):
        from app.services import analytics

        i = analytics.crm_impact()
        w, c = i["worked_on"], i["control"]
        facts = {
            "days": i["days"],
            "worked_on_rate": w["rate"],
            "worked_on_people": w["people"],
            "control_rate": c["rate"],
            "control_people": c["people"],
            "lift": i.get("lift"),
            "lift_ci": i.get("lift_ci"),
        }
        if not c["people"] or not w["people"]:
            return (
                "Not enough people yet: the comparison needs learners who signed up at least "
                f"{i['days']} days ago in both groups.",
                facts,
                "users, purchases and the control group",
                [],
            )
        lo, hi = i.get("lift_ci") or (None, None)
        text = (
            f"Of people the CRM worked on, {_pct(w['rate'])} bought within {i['days']} days of signing up "
            f"({w['people']:,} people); of the control group it never contacts, {_pct(c['rate'])} "
            f"({c['people']:,} people). Difference: {i['lift'] * 100:+.1f} points (95% interval "
            f"{lo * 100:+.1f} to {hi * 100:+.1f})."
        )
        text += (
            " The interval is above zero: the CRM is making a real difference."
            if lo is not None and lo > 0
            else " The interval still includes zero: not proven yet (the control group is small)."
        )
        return text, facts, "users and purchases, split by the fixed control group", []

    def revenue(self, days: int = 30):
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        rows = db.fetchall(
            """SELECT p.course_title, p.price_paid, p.discount_amount, u.email FROM purchases p
                              JOIN users u ON u.id = p.user_id WHERE p.purchased_at >= ?""",
            (since,),
        )
        n = len(rows)
        rev = sum(r["price_paid"] or 0 for r in rows)
        disc = sum(r["discount_amount"] or 0 for r in rows)
        sim = sum(1 for r in rows if (r["email"] or "").endswith(SIM_SUFFIX))
        by = {}
        for r in rows:
            by[r["course_title"]] = by.get(r["course_title"], 0) + 1
        top = sorted(by.items(), key=lambda x: -x[1])[:3]
        facts = {
            "days": days,
            "purchases": n,
            "revenue": round(rev),
            "discounts": round(disc),
            "simulated": sim,
            "top_courses": top,
        }
        if not n:
            return f"No purchases in the last {days} days.", facts, "purchases", []
        text = f"Last {days} days: {n:,} purchases, {_money(rev)} revenue after {_money(disc)} of discounts."
        if top:
            text += " Top courses: " + ", ".join(f"{t} ({k})" for t, k in top) + "."
        if sim:
            text += f" {sim:,} of these are simulated learners."
        return text, facts, "purchases", []

    def counts(self, days: int = 7):
        """How many people the CRM has, split into real people and simulated learners."""
        now = datetime.now()
        since = (
            now.replace(hour=0, minute=0, second=0, microsecond=0) if days == 1 else now - timedelta(days=days)
        ).strftime("%Y-%m-%d %H:%M:%S")
        people = db.fetchall(
            """SELECT u.email, u.created_at, EXISTS (SELECT 1 FROM purchases p WHERE p.user_id = u.id) AS bought
               FROM users u WHERE u.id IN (SELECT user_id FROM leads)"""
        )

        def split(rows):
            sim = sum(1 for r in rows if (r["email"] or "").endswith(SIM_SUFFIX))
            return {"all": len(rows), "real": len(rows) - sim, "simulated": sim}

        leads = split(people)
        new = split([r for r in people if (r["created_at"] or "") >= since])
        customers = split([r for r in people if r["bought"]])
        callbacks = db.fetchone("SELECT COUNT(*) AS c FROM callback_requests WHERE status='open'")["c"]
        tasks = db.fetchone("SELECT COUNT(*) AS c FROM sales_tasks WHERE status='open'")["c"]
        facts = {
            "days": days,
            "leads": leads,
            "new_leads": new,
            "customers": customers,
            "open_callbacks": callbacks,
            "open_tasks": tasks,
        }
        period = "today" if days == 1 else f"in the last {days} days"

        def both(x):
            if not x["simulated"]:
                return f"{x['all']:,}"
            who = "person" if x["real"] == 1 else "people"
            return f"{x['all']:,} ({x['real']:,} real {who}, {x['simulated']:,} simulated)"

        text = (
            f"Leads: {both(leads)}. New {period}: {both(new)}. Customers: {both(customers)}. "
            f"Open call-backs: {callbacks:,}; open call and WhatsApp tasks: {tasks:,}."
        )
        return (
            text,
            facts,
            "users, leads, purchases, call-backs and tasks",
            [{"type": "page", "to": "/leads", "label": "Open the leads"}],
        )

    def campaigns(self):
        from app.services import campaigns

        sent = [c for c in campaigns.report() if c.get("sent")][:4]
        facts = {
            "campaigns": [
                {
                    "name": c["name"],
                    "delivered": c.get("delivered"),
                    "conversions": c.get("conversions"),
                    "lift": (c.get("incremental") or {}).get("lift"),
                }
                for c in sent
            ]
        }
        if not sent:
            return "No campaigns have been sent yet.", facts, "campaign_schedules and email_sends", []
        lines = []
        for c in sent:
            inc = c.get("incremental")
            line = f"- {c['name']}: {c.get('delivered', 0):,} emails, " f"{c.get('conversions', 0):,} bought"
            if inc and inc.get("lift") is not None:
                lo, hi = inc["ci"]
                line += (
                    f"; against its hold-out {inc['lift'] * 100:+.1f} points (95% interval {lo * 100:+.1f} to "
                    f"{hi * 100:+.1f})"
                )
            lines.append(line)
        return (
            "Recent campaigns:\n" + "\n".join(lines),
            facts,
            "campaign_schedules, email_sends and hold-outs",
            [{"type": "page", "to": "/campaigns", "label": "Open campaigns"}],
        )

    def _find_lead(self, query):
        if not query:
            return None
        return db.fetchone(
            """SELECT l.*, u.name, u.email FROM leads l JOIN users u ON u.id = l.user_id
               WHERE (u.email = ? OR u.name LIKE ?) AND l.id IN (SELECT MAX(id) FROM leads GROUP BY user_id)
               ORDER BY l.id DESC LIMIT 1""",
            (query, f"%{query}%"),
        )

    def lead(self, query):
        r = self._find_lead(query)
        if not r:
            return f"I could not find a lead matching '{query}'.", {}, "users and leads", []
        factors = json.loads(r.get("score_factors") or "[]")[:3]
        nba = json.loads(r.get("nba_json") or "null") or {}
        facts = {
            "name": r["name"],
            "score": round(r["lead_score"] or 0, 1),
            "tier": r["recommended_action"],
            "reasons": [f"{f['factor']} {f['impact']}" for f in factors],
            "next_step": nba.get("label"),
        }
        text = (
            f"{r['name']}: {facts['score']:.0f}% chance to buy within {WINDOW_DAYS} days with no step, "
            f"{r['recommended_action']}."
        )
        if factors:
            text += " Main reasons: " + "; ".join(f"{_mid(f['factor'])} ({f['impact']})" for f in factors) + "."
        if nba.get("label"):
            text += f" Last decision: {_mid(nba['label'])}" + (f". {nba['why']}" if nba.get("why") else ".")
        try:
            from app.ml import paths

            p = paths.plan(r["user_id"], depth=2)
            if p and p.get("summary"):
                text += f"\nWhat-if: {p['summary']}"
                facts["what_if"] = p["summary"]
        except Exception:  # noqa: BLE001 - the what-if part is optional here
            log.debug("What-if path unavailable for user %s", r["user_id"], exc_info=True)
        return (
            text,
            facts,
            "leads, nba_decisions and what-if paths",
            [{"type": "lead", "lead_id": r["id"], "label": f"Open {r['name']}"}],
        )

    def draft_email(self, query):
        from app.services.content import generate_content

        r = self._find_lead(query) if query else None
        if not r:
            return (
                "Tell me who the email is for, for example 'Draft an email to Riya Sharma'. I only write drafts; "
                "you send them from the lead page.",
                {},
                "users and leads",
                [],
            )
        slug = r.get("course_slug")
        title = catalog.title_of(slug, "our programmes") if slug else "our programmes"
        prof = db.get_profile(r["user_id"]) or {}
        content = generate_content(
            name=r["name"],
            occupation=prof.get("current_occupation"),
            specialization=prof.get("specialization"),
            course=title,
            action=r["recommended_action"],
            trigger="manual_edit",
            past_purchases=0,
            lead_score=r["lead_score"],
            course_slug=slug,
            offer_pct=0,
        )
        draft = {
            "type": "email",
            "lead_id": r["id"],
            "to": r["name"],
            "subject": content["email_subject"],
            "body": content["email_body"],
        }
        text = (
            f"Here is a draft for {r['name']} about {title}, written from the course facts. It offers no discount: "
            f"whether to offer one is next-best-action's decision. Nothing has been sent; open the lead to edit "
            f"and send it."
        )
        return text, {"lead": r["name"], "course": title}, "leads, user_profiles and the course catalogue", [draft]

    def draft_ab_test(self, text: str = ""):
        from app.services import abtests

        t = text or ""
        if re.search(r"subject|open|click", t):
            spec = (
                "Subject line: benefit vs urgency",
                "click",
                "An urgency subject line gets more people to click than a benefit-led one.",
                [
                    (
                        "Benefit-led subject",
                        "{first_name}, your next career step: {course}",
                        "Hi {first_name},\n\nSee how {course} fits your goals: curriculum, instructor and outcomes.",
                    ),
                    (
                        "Urgency subject",
                        "Last seats in the {course} batch",
                        "Hi {first_name},\n\nThe next {course} batch is filling up. Reserve your seat this week.",
                    ),
                ],
            )
        elif re.search(r"discount|coupon|offer|price", t):
            spec = (
                "EMI message vs refund guarantee",
                "purchase",
                "Removing a doubt (refund guarantee) converts more than talking about price (EMI).",
                [
                    (
                        "EMI from 2,200 a month",
                        "{course} from 2,200 a month",
                        "Hi {first_name},\n\nSpread the fee of {course} over easy monthly EMIs.",
                    ),
                    (
                        "7-day refund guarantee",
                        "Try {course} risk-free for 7 days",
                        "Hi {first_name},\n\nStart {course}; if it is not for you, get a full refund within 7 days.",
                    ),
                ],
            )
        elif re.search(r"mobile|short|long|length", t):
            spec = (
                "Short mobile email vs long email",
                "purchase",
                "A short email works better on phones.",
                [
                    (
                        "Long email",
                        "Everything about {course} in one email",
                        "Hi {first_name},\n\nModules, projects, instructor, fees, EMI and outcomes of "
                        "{course} in detail.",
                    ),
                    (
                        "Short mobile-first email",
                        "{course} in 30 seconds",
                        "Hi {first_name},\n\n{course}: 3 reasons, 1 link.",
                    ),
                ],
            )
        else:
            spec = (
                "Personalised course pick vs generic newsletter",
                "purchase",
                "A course picked for the learner's background converts better than a generic newsletter.",
                [
                    (
                        "Generic newsletter",
                        "This month at X Education",
                        "Hi {first_name},\n\nNews, new batches and learner stories from X Education.",
                    ),
                    (
                        "Personalised course pick",
                        "{first_name}, {course} fits your background",
                        "Hi {first_name},\n\nBased on what you looked at, {course} is the best next step for you.",
                    ),
                ],
            )
        name, metric, hyp, variants = spec
        ab = rules.S["ab_testing"]
        control = float(ab["control_share"]) if metric == "purchase" else 0.0
        mde = float(ab["min_detectable_effect"])
        p = abtests.plan("All leads", metric, len(variants), control, mde)
        draft = {
            "type": "ab_test",
            "name": name,
            "tier": "All leads",
            "metric": metric,
            "hypothesis": hyp,
            "control_share": control,
            "mde": mde,
            "variants": [{"label": lab, "subject": s, "body": b, "offer_pct": 0} for lab, s, b in variants],
        }
        facts = {
            "audience": p["audience"],
            "planned_per_arm": p["planned_per_arm"],
            "per_arm_available": p["per_arm_available"],
            "enough": p["enough"],
        }
        text = (
            f"Draft test: '{name}' ({'clicks' if metric == 'click' else 'purchases'} within {WINDOW_DAYS} days"
            + (f", {control * 100:.0f}% no-email control group" if control else "")
            + f"). Hypothesis: {hyp}\n"
            f"Plan: {p['planned_per_arm']:,} people per arm are needed to see a {mde * 100:.0f}-point lift; the "
            f"audience gives {p['per_arm_available']:,} per arm"
            + (
                ", which is enough."
                if p["enough"]
                else ", which is not enough, so only bigger effects could be " "detected."
            )
            + " Nothing is created yet: open it in A/B tests, review it, then create and send it."
        )
        return text, facts, "A/B planner (sample size) and the campaign audience", [draft]

    def help(self):
        text = (
            "I answer from the CRM's live data, and I only draft: a person sends. Try:\n"
            + "\n".join(f"- {s}" for s in SUGGESTIONS)
            + "\n- Tell me about <a learner's name or email>"
        )
        return text, {}, "none", []

    # answering
    def ask(self, question: str) -> dict:
        q = (question or "").strip()[:500]
        intent, args = self.route(q)
        used_gemini = False
        if intent is None and gemini.enabled():
            intent, args, used_gemini = self._gemini_route(q)
        if intent is None:
            intent, args = "help", {}
        fn = getattr(self, intent)
        try:
            text, facts, source, extras = fn(**args)
        except Exception as e:  # noqa: BLE001 - a tool failing must not break the page
            log.exception("Copilot tool %s failed", intent)
            text, facts, source, extras = (
                f"I could not read that data just now ({e.__class__.__name__}).",
                {},
                intent,
                [],
            )
        answer = text
        if gemini.enabled() and intent not in ("help", "draft_email", "draft_ab_test"):
            better = self._gemini_phrase(q, text)
            if better:
                answer, used_gemini = better, True
        drafts = [x for x in extras if x.get("type") in ("email", "ab_test")]
        links = [x for x in extras if x.get("type") in ("lead", "page")]
        out = {
            "question": q,
            "intent": intent,
            "answer": answer,
            "tools": [
                {
                    "name": intent,
                    "about": TOOLS.get(intent),
                    "source": source,
                    "read_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "data": facts,
                }
            ],
            "drafts": drafts,
            "links": links,
            "used_gemini": used_gemini,
            "suggestions": SUGGESTIONS,
        }
        try:
            db.execute(
                """INSERT INTO copilot_log (question, intent, tools_json, answer, drafts_json, used_gemini)
                          VALUES (?,?,?,?,?,?)""",
                (
                    q,
                    intent,
                    json.dumps(out["tools"], default=str),
                    answer,
                    json.dumps(drafts, default=str),
                    int(bool(used_gemini)),
                ),
            )
        except Exception:  # noqa: BLE001 - logging must not fail the answer
            log.warning("Could not log the copilot question", exc_info=True)
        return out

    # optional Gemini (never the source of a number)
    def _gemini_route(self, q: str):
        try:
            prompt = (
                "You route a CRM user's question to ONE tool. Tools:\n"
                + "\n".join(f"- {k}: {v}" for k, v in TOOLS.items())
                + '\nReply with JSON only, e.g. {"tool": "hot_leads", "query": ""}. "query" is a learner name or '
                f"email for the lead and draft_email tools, else empty.\nQuestion: {q}"
            )
            raw = gemini.generate(prompt)
            m = re.search(r"\{.*\}", raw or "", re.S)
            d = json.loads(m.group(0)) if m else {}
            tool = d.get("tool")
            if tool not in TOOLS:
                return None, {}, True
            args = {"query": d.get("query") or None} if tool in ("lead", "draft_email") else {}
            if tool == "draft_ab_test":
                args = {"text": q.lower()}
            return tool, args, True
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini routing failed: %s", e)
            return None, {}, False

    def _gemini_phrase(self, q: str, text: str):
        try:
            prompt = (
                "Rewrite this answer to the user's question so it reads naturally and briefly. Use ONLY the facts "
                "and numbers in the answer; do not add, round or change any number, and do not add advice.\n"
                f"Question: {q}\nAnswer: {text}"
            )
            out = (gemini.generate(prompt) or "").strip()

            def nums(s):
                return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}

            if out and nums(out) <= nums(text):
                return out
            log.warning("Gemini's wording changed a number: using the template answer")
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini phrasing failed: %s", e)
        return None


def ask(question: str) -> dict:
    return Copilot().ask(question)


def recent(limit: int = 10) -> list[dict]:
    return db.fetchall(
        "SELECT asked_at, question, intent, used_gemini FROM copilot_log ORDER BY id DESC LIMIT ?", (limit,)
    )
