"""
The numbers on the dashboard: headline counts, the revenue forecast, model calibration, how well next-best-action
is doing (off-policy estimates from the decision log), the CRM's total impact against the untouched control group,
and everything the Learning loop page shows.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

from app import db
from app.core import perf, rules
from app.core.config import get_settings
from app.ml import experiments as X
from app.ml import learning
from app.ml.predict import model_info
from app.services import catalog, scoring
from app.services.leads import CUSTOMERS, LATEST, SIM_LIKE, is_simulated, segment_sql

WINDOW_DAYS = int(rules.S["outcome_window_days"])
TIERS = rules.tier_names()
ACTION_COST = {k: float(v.get("cost", 0)) for k, v in rules.S["actions"].items()}
ACTION_DISCOUNT = {k: float(v.get("discount", 0)) for k, v in rules.S["actions"].items()}
IMPACT_DAYS = 30
MIN_MATCHED = 30
TS = "%Y-%m-%d %H:%M:%S"


def _count(sql: str, params=()) -> int:
    return int((db.fetchone(sql, params) or {}).get("c") or 0)


def card(name: str) -> dict | None:
    """A model card written by training or the learning loop (model_card.json, nba_card.json)."""
    try:
        with open(get_settings().model_dir / name, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def conversions_after(sends: list[dict]) -> int:
    """How many of these people bought within the outcome window after their email (or assignment)."""
    n = 0
    for s in sends:
        if (
            s.get("user_id")
            and s.get("sent_at")
            and db.fetchone(
                f"""SELECT 1 AS x FROM purchases WHERE user_id=? AND purchased_at >= ?
                    AND purchased_at <= datetime(?, '+{WINDOW_DAYS} days') LIMIT 1""",
                (s["user_id"], s["sent_at"], s["sent_at"]),
            )
        ):
            n += 1
    return n


# headline numbers
def stats() -> dict:
    """Tiers and scores describe people who have not bought yet; customers are counted on their own."""
    open_ = f"{LATEST} l WHERE l.user_id NOT IN {CUSTOMERS}"
    by_tier = {
        r["recommended_action"]: r["cnt"]
        for r in db.fetchall(f"SELECT l.recommended_action, COUNT(*) AS cnt FROM {open_} GROUP BY l.recommended_action")
    }
    buckets = [("0-20", 0, 20), ("20-40", 20, 40), ("40-60", 40, 60), ("60-80", 60, 80), ("80-100", 80, 101)]
    dist = {
        name: _count(f"SELECT COUNT(*) AS c FROM {open_} AND l.lead_score>=? AND l.lead_score<?", (lo, hi))
        for name, lo, hi in buckets
    }
    real = f"(SELECT id FROM users WHERE email NOT LIKE '{SIM_LIKE}')"
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "total_leads": _count(f"SELECT COUNT(*) AS c FROM {LATEST}"),
        "open_leads": _count(f"SELECT COUNT(*) AS c FROM {open_}"),
        "customers": _count(f"SELECT COUNT(*) AS c FROM {CUSTOMERS}"),
        "real_people": _count(f"SELECT COUNT(*) AS c FROM users WHERE is_verified=1 AND id IN {real}"),
        "real_customers": _count(f"SELECT COUNT(DISTINCT user_id) AS c FROM purchases WHERE user_id IN {real}"),
        "real_purchases": _count(f"SELECT COUNT(*) AS c FROM purchases WHERE user_id IN {real}"),
        "real_revenue": (
            db.fetchone(f"SELECT COALESCE(SUM(price_paid),0) AS r FROM purchases WHERE user_id IN {real}") or {}
        ).get("r", 0),
        "simulated_people": _count(f"SELECT COUNT(*) AS c FROM users WHERE is_verified=1 AND email LIKE '{SIM_LIKE}'"),
        "simulated_customers": _count(f"""SELECT COUNT(DISTINCT p.user_id) AS c FROM purchases p
                                          JOIN users u ON u.id = p.user_id WHERE u.email LIKE '{SIM_LIKE}'"""),
        "by_tier": by_tier,
        "avg_lead_score": (db.fetchone(f"SELECT ROUND(AVG(l.lead_score),1) AS a FROM {open_}") or {}).get("a") or 0,
        "total_users": _count("SELECT COUNT(*) AS c FROM users WHERE is_verified=1"),
        "total_purchases": _count("SELECT COUNT(*) AS c FROM purchases"),
        "revenue": (db.fetchone("SELECT COALESCE(SUM(price_paid),0) AS r FROM purchases") or {}).get("r", 0),
        "active_carts": _count("SELECT COUNT(DISTINCT user_id) AS c FROM cart"),
        "emails_sent": _count("SELECT COUNT(*) AS c FROM email_sends WHERE error IS NULL"),
        "email_clicks": _count("SELECT COUNT(*) AS c FROM email_sends WHERE click_count > 0"),
        "open_callbacks": _count("SELECT COUNT(*) AS c FROM callback_requests WHERE status='open'"),
        "open_tasks": _count("SELECT COUNT(*) AS c FROM sales_tasks WHERE status='open'"),
        "calls_today": _count("""SELECT COUNT(*) AS c FROM sales_tasks WHERE task_type='call'
                                 AND date(created_at)=date('now','localtime')"""),
        "purchases_today": _count("SELECT COUNT(*) AS c FROM purchases WHERE purchased_at >= ?", (today,)),
        "revenue_today": (
            db.fetchone("SELECT COALESCE(SUM(price_paid),0) AS r FROM purchases WHERE purchased_at >= ?", (today,))
            or {}
        ).get("r", 0),
        "score_distribution": dist,
    }


def daily_series(days: int = 30) -> dict:
    """Sign-ups, purchases and revenue per day (the dashboard's trend chart), oldest first."""
    since = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    signups = {
        r["d"]: r["n"]
        for r in db.fetchall(
            "SELECT date(created_at) AS d, COUNT(*) AS n FROM users WHERE created_at >= ? GROUP BY d", (since,)
        )
    }
    buys = {
        r["d"]: r
        for r in db.fetchall(
            """SELECT date(purchased_at) AS d, COUNT(*) AS n, SUM(price_paid) AS rev FROM purchases
           WHERE purchased_at >= ? GROUP BY d""",
            (since,),
        )
    }
    out = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        b = buys.get(d) or {}
        out.append(
            {"date": d, "signups": signups.get(d, 0), "purchases": b.get("n", 0), "revenue": round(b.get("rev") or 0)}
        )
    return {"days": days, "series": out}


# forecast
def forecast() -> dict:
    """Revenue to expect from people who have not bought yet: each lead's calibrated probability times the price of
    the course they are interested in; the 90% range comes from simulating who converts. Only as good as the
    calibration (see model_health)."""
    rows = db.fetchall(f"""SELECT l.conversion_probability AS p, l.course_slug, l.course_type,
                                  l.recommended_action AS tier
                           FROM {LATEST} l WHERE l.user_id NOT IN {CUSTOMERS}""")
    avg_price = catalog.average_price()
    items = []
    for r in rows:
        p = float(r["p"] or 0)
        p = p / 100 if p > 1 else p
        price = catalog.price_of(r["course_slug"] or catalog.slug_for_title(r["course_type"])) or avg_price
        items.append((min(max(p, 0.0), 1.0), float(price), r["tier"]))
    if not items:
        return {
            "open_leads": 0,
            "expected_revenue": 0,
            "expected_customers": 0,
            "by_tier": [],
            "range_90": [0, 0],
            "customers_range_90": [0, 0],
        }
    exp_rev = sum(p * price for p, price, _ in items)
    exp_n = sum(p for p, _, _ in items)
    if len(items) <= 3000:
        rng = random.Random(42)
        draws, buyers = [], []
        for _ in range(2000):
            rev = n = 0
            for p, price, _t in items:
                if rng.random() < p:
                    rev += price
                    n += 1
            draws.append(rev)
            buyers.append(n)
        draws.sort()
        buyers.sort()

        def q(xs, f):
            return xs[min(int(f * len(xs)), len(xs) - 1)]

        rev_range, n_range = [q(draws, 0.05), q(draws, 0.95)], [q(buyers, 0.05), q(buyers, 0.95)]
    else:  # many leads: the normal approximation is accurate and much faster
        sd_rev = sum(p * (1 - p) * price**2 for p, price, _ in items) ** 0.5
        sd_n = sum(p * (1 - p) for p, _, _ in items) ** 0.5
        rev_range = [max(0, round(exp_rev - 1.645 * sd_rev)), round(exp_rev + 1.645 * sd_rev)]
        n_range = [max(0, round(exp_n - 1.645 * sd_n)), round(exp_n + 1.645 * sd_n)]
    by_tier = []
    for t in TIERS:
        g = [(p, price) for p, price, tier in items if tier == t]
        if g:
            by_tier.append(
                {
                    "tier": t,
                    "leads": len(g),
                    "expected_customers": round(sum(p for p, _ in g), 1),
                    "expected_revenue": round(sum(p * price for p, price in g)),
                }
            )
    return {
        "open_leads": len(items),
        "expected_revenue": round(exp_rev),
        "range_90": rev_range,
        "expected_customers": round(exp_n, 1),
        "customers_range_90": n_range,
        "by_tier": by_tier,
        "window_days": WINDOW_DAYS,
        "note": "Assumes the scores are calibrated (compare predicted and actual rates in Model health).",
    }


# model health: calibration on people with a known outcome
def model_health(window_days: int = WINDOW_DAYS) -> dict:
    window = f"+{int(window_days)} days"
    rows = db.fetchall(f"""
        SELECT s.tier, s.probability,
               EXISTS(SELECT 1 FROM purchases p WHERE p.user_id = s.user_id AND p.purchased_at >= s.created_at
                      AND p.purchased_at <= datetime(s.created_at, '{window}')) AS converted,
               (s.created_at <= datetime('now','localtime','-{int(window_days)} days')) AS matured
        FROM score_snapshots s
        WHERE s.source != 'purchase_conversion'
          AND NOT EXISTS(SELECT 1 FROM purchases p WHERE p.user_id = s.user_id AND p.purchased_at <= s.created_at)""")
    labelled = [r for r in rows if r["converted"] or r["matured"]]
    tiers = []
    for t in TIERS:
        g = [r for r in labelled if r["tier"] == t]
        if g:
            tiers.append(
                {
                    "tier": t,
                    "snapshots": len(g),
                    "predicted_rate": round(sum(r["probability"] or 0 for r in g) / len(g), 3),
                    "actual_rate": round(sum(r["converted"] for r in g) / len(g), 3),
                }
            )
    deciles = []
    if labelled:
        srt = sorted(labelled, key=lambda r: r["probability"] or 0)
        k = 10
        for i in range(k):
            g = srt[i * len(srt) // k : (i + 1) * len(srt) // k]
            if g:
                deciles.append(
                    {
                        "bin": i + 1,
                        "n": len(g),
                        "predicted": round(sum(r["probability"] or 0 for r in g) / len(g), 4),
                        "actual": round(sum(r["converted"] for r in g) / len(g), 4),
                    }
                )
    return {
        "model": card("model_card.json"),
        "window_days": window_days,
        "snapshots_total": len(rows),
        "snapshots_labelled": len(labelled),
        "by_tier": tiers,
        "calibration": deciles,
        "retrain_hint": "The learning loop retrains automatically when enough new outcomes are known.",
    }


# next-best-action: off-policy estimates from the decision log
def nba_performance(window_days: int = WINDOW_DAYS) -> dict:
    """How well next-best-action is doing. The randomised slice (policy 'explore') is a clean experiment;
    inverse-propensity estimates compare 'follow the model' with 'do nothing' (valid because every decision's
    probability under the logging policy is stored)."""
    rows = db.fetchall(f"""
        SELECT d.action, d.model_best, d.policy, d.propensity, d.price,
               EXISTS(SELECT 1 FROM purchases p WHERE p.user_id = d.user_id AND p.purchased_at >= d.created_at
                      AND p.purchased_at <= datetime(d.created_at, '+{int(window_days)} days')) AS converted,
               (d.created_at <= datetime('now','localtime','-{int(window_days)} days')) AS matured
        FROM nba_decisions d WHERE COALESCE(d.policy,'') != 'holdout'""")
    by_action = {}
    for r in rows:
        b = by_action.setdefault(r["action"], {"decisions": 0, "explore": 0, "known_outcome": 0, "converted": 0})
        b["decisions"] += 1
        b["explore"] += 1 if r["policy"] == "explore" else 0
        if r["converted"] or r["matured"]:
            b["known_outcome"] += 1
            b["converted"] += r["converted"]
    labelled = [r for r in rows if r["converted"] or r["matured"]]
    explore = {}
    for r in labelled:
        if r["policy"] == "explore":
            e = explore.setdefault(r["action"], {"n": 0, "converted": 0})
            e["n"] += 1
            e["converted"] += r["converted"]
    for e in explore.values():
        e["rate"] = round(e["converted"] / e["n"], 3) if e["n"] else None

    def terms(target):
        """(weight, weighted profit) per labelled decision: weight = 1/propensity when the logged action is the one
        the target policy would have taken, else 0."""
        out = []
        for r in labelled:
            a_star = r["model_best"] if target == "model" else target
            if r["action"] != a_star or not r["propensity"]:
                out.append((0.0, 0.0))
                continue
            w = 1.0 / r["propensity"]
            profit = r["converted"] * (r["price"] or 0) * (1 - ACTION_DISCOUNT.get(r["action"], 0)) - ACTION_COST.get(
                r["action"], 0
            )
            out.append((w, w * profit))
        return out

    def ips(target):
        t = terms(target)
        n = len(t)
        num, den = sum(x[1] for x in t), sum(x[0] for x in t)
        matched = sum(1 for x in t if x[0] > 0)
        ci = None
        if den and matched >= 5:  # bootstrap the decisions for a 95% interval
            rng = random.Random(7)
            boots = []
            for _ in range(300):
                sample = [t[rng.randrange(n)] for _ in range(n)]
                d = sum(x[0] for x in sample)
                if d:
                    boots.append(sum(x[1] for x in sample) / d)
            boots.sort()
            if len(boots) >= 20:
                ci = [round(boots[int(0.025 * len(boots))], 1), round(boots[int(0.975 * len(boots)) - 1], 1)]
        return {
            "ips_profit_per_lead": round(num / n, 1) if n else None,
            "snips_profit_per_lead": round(num / den, 1) if den else None,
            "ci95": ci,
            "matched_decisions": matched,
            "enough": matched >= MIN_MATCHED,
        }

    est = {"follow the model": ips("model"), "do nothing": ips("none"), "information email to all": ips("email_info")}
    m, z = est["follow the model"], est["do nothing"]
    if not (m["enough"] and z["enough"] and m["ci95"] and z["ci95"]):
        verdict = (
            f"Not enough data yet: each estimate needs at least {MIN_MATCHED} matching decisions with a known "
            f"outcome (now {m['matched_decisions']} and {z['matched_decisions']})."
        )
    elif m["ci95"][0] > z["ci95"][1]:
        verdict = "Following the model earns more per lead than doing nothing (the 95% intervals do not overlap)."
    elif m["ci95"][1] < z["ci95"][0]:
        verdict = "Following the model earns less per lead than doing nothing. Check the model and its costs."
    else:
        verdict = "No clear difference yet between following the model and doing nothing: the 95% intervals overlap."
    return {
        "decisions_total": len(rows),
        "decisions_with_outcome": len(labelled),
        "by_action": by_action,
        "randomised_slice": explore,
        "verdict": verdict,
        "policy_estimates": est,
        "note": (
            "Each estimate uses only the past decisions that match that way of choosing, each counted by how "
            "likely it was to be chosen, so a wide range means there are too few of them yet."
        ),
    }


# the CRM's total impact
def crm_impact(days: int = IMPACT_DAYS) -> dict:
    """People the CRM worked on against the untouched control group: the share who bought within `days` of signing
    up (only people who signed up at least `days` ago), with a 95% interval for the difference."""
    rows = db.fetchall(
        """SELECT u.id AS user_id, u.created_at, MIN(p.purchased_at) AS first_buy FROM users u
                          LEFT JOIN purchases p ON p.user_id = u.id
                          WHERE u.created_at <= datetime('now','localtime',?) GROUP BY u.id""",
        (f"-{int(days)} days",),
    )
    groups = {"worked_on": [0, 0], "control": [0, 0]}
    for r in rows:
        g = groups["control" if rules.in_global_control(r["user_id"]) else "worked_on"]
        g[1] += 1
        try:
            if (
                r["first_buy"]
                and r["created_at"]
                and datetime.strptime(r["first_buy"][:19], TS)
                <= datetime.strptime(r["created_at"][:19], TS) + timedelta(days=days)
            ):
                g[0] += 1
        except ValueError:
            continue
    (x1, n1), (x0, n0) = groups["worked_on"], groups["control"]
    out = {
        "days": days,
        "worked_on": {"people": n1, "bought": x1, "rate": x1 / n1 if n1 else None},
        "control": {"people": n0, "bought": x0, "rate": x0 / n0 if n0 else None},
        "share": rules.S["global_control"]["share"],
    }
    if n1 and n0:
        lo, hi = X.diff_ci(x1, n1, x0, n0)
        out.update(lift=x1 / n1 - x0 / n0, lift_ci=[lo, hi], p_value=X.two_prop_p(x1, n1, x0, n0))
    return out


def campaign_influence() -> dict:
    """Emails, clicks and purchases after a click, per kind of email (automatic trigger, campaign, A/B test).

    One query: whether a clicked email was followed by a purchase within the outcome window is checked inside it
    (it used to be one extra query per clicked email, about 2.5 s on a busy install)."""
    sends = db.fetchall(f"""SELECT es.ab_test_id, es.campaign_id, es.campaign_name, es.click_count,
                                   l.trigger_reason,
                                   CASE WHEN COALESCE(es.click_count, 0) != 0 AND EXISTS (
                                       SELECT 1 FROM purchases p WHERE p.user_id = es.user_id
                                         AND p.purchased_at >= es.first_clicked_at
                                         AND p.purchased_at <= datetime(es.first_clicked_at, '+{WINDOW_DAYS} days'))
                                   THEN 1 ELSE 0 END AS bought_after_click
                            FROM email_sends es LEFT JOIN leads l ON l.id = es.lead_id
                            WHERE es.sent_at IS NOT NULL AND es.error IS NULL AND es.user_id IS NOT NULL""")
    influence = {}
    for s in sends:
        reason = (
            "ab_test"
            if s.get("ab_test_id")
            else "campaign"
            if s.get("campaign_id") or s.get("campaign_name")
            else s.get("trigger_reason") or "manual_send"
        )
        b = influence.setdefault(reason, {"emails_sent": 0, "clicks": 0, "influenced_conversions": 0})
        b["emails_sent"] += 1
        if s["click_count"]:
            b["clicks"] += 1
            b["influenced_conversions"] += s["bought_after_click"]
    return {"campaign_influence": influence}


# the Learning loop page
def learning_status() -> dict:
    ok, known, new = learning.due()
    return {
        "outcomes_known": known,
        "new_outcomes": new,
        "due": ok,
        "min_new_outcomes": learning.CONF.get("min_new_outcomes"),
        "latency": perf.summary(),
        "model": model_info(),
        "score_refresh": scoring.last_refresh(),
        "score_refresh_minutes": int(rules.by_mode("score_refresh_minutes")),
    }


def _feed(segment: str = "all") -> list[dict]:
    cond = segment_sql(segment) if segment != "all" else ""
    rows = db.fetchall(f"""SELECT * FROM (
          SELECT 'event' AS kind, b.event_type AS what, u.name, u.email, b.created_at AS at FROM behaviour_events b
            JOIN users u ON u.id = b.user_id WHERE b.event_type != 'page_view'{cond} ORDER BY b.id DESC LIMIT 15)
        UNION ALL SELECT * FROM (
          SELECT 'decision', d.trigger_reason || ': ' || d.action || CASE WHEN d.policy='explore' THEN ' (random)'
                 WHEN d.policy='manual' THEN ' (by hand)' WHEN d.policy='holdout' THEN ' (control group, nothing sent)'
                 ELSE '' END, u.name, u.email, d.created_at FROM nba_decisions d JOIN users u ON u.id = d.user_id
          WHERE 1=1{cond} ORDER BY d.id DESC LIMIT 15)
        UNION ALL SELECT * FROM (
          SELECT 'purchase', p.course_title, u.name, u.email, p.purchased_at FROM purchases p
            JOIN users u ON u.id = p.user_id WHERE 1=1{cond} ORDER BY p.id DESC LIMIT 10)
        UNION ALL SELECT * FROM (
          SELECT 'learning', 'learning run: lead model ' || COALESCE(lead_decision, 'not run')
                 || ', next-best-action ' || COALESCE(nba_decision, 'not run')
                 || CASE WHEN simulated=1 THEN ' (simulated history)' ELSE '' END,
                 NULL, NULL, COALESCE(finished_at, started_at) FROM learning_runs
          WHERE status='done' ORDER BY id DESC LIMIT 5)
        ORDER BY at DESC LIMIT 30""")
    for f in rows:
        f["simulated"] = is_simulated(f.pop("email", None))
    return rows


def learning_overview() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    counts = {
        "events_today": _count("SELECT COUNT(*) AS c FROM behaviour_events WHERE created_at >= ?", (today,)),
        "scored_today": _count("SELECT COUNT(*) AS c FROM score_snapshots WHERE created_at >= ?", (today,)),
        "decisions_total": _count("SELECT COUNT(*) AS c FROM nba_decisions"),
        "decisions_today": _count("SELECT COUNT(*) AS c FROM nba_decisions WHERE created_at >= ?", (today,)),
        "decisions_random": _count("SELECT COUNT(*) AS c FROM nba_decisions WHERE policy='explore'"),
        "emails_today": _count("SELECT COUNT(*) AS c FROM email_sends WHERE sent_at >= ? AND error IS NULL", (today,)),
        "purchases_total": _count("SELECT COUNT(*) AS c FROM purchases"),
        "left_alone": _count("""SELECT (SELECT COUNT(*) FROM nba_decisions WHERE action='none') +
                                       (SELECT COUNT(*) FROM experiment_assignments
                                        WHERE arm IN ('control','holdout')) AS c"""),
        "experiments": _count("SELECT COUNT(*) AS c FROM ab_tests WHERE sent_at IS NOT NULL"),
        "control_group": sum(1 for r in db.fetchall("SELECT id FROM users") if rules.in_global_control(r["id"])),
        "real_people": _count(f"SELECT COUNT(*) AS c FROM users WHERE is_verified=1 AND email NOT LIKE '{SIM_LIKE}'"),
        "simulated_people": _count(f"SELECT COUNT(*) AS c FROM users WHERE email LIKE '{SIM_LIKE}'"),
        "real_decisions": _count(f"""SELECT COUNT(*) AS c FROM nba_decisions d JOIN users u ON u.id = d.user_id
                                     WHERE u.email NOT LIKE '{SIM_LIKE}'"""),
        "manual_decisions": _count("SELECT COUNT(*) AS c FROM nba_decisions WHERE policy='manual'"),
    }
    runs = db.fetchall("SELECT * FROM learning_runs WHERE status='done' ORDER BY id DESC LIMIT 50")
    for r in runs:
        for k in ("learned_json", "nba_detail_json"):
            try:
                r[k.replace("_json", "")] = json.loads(r.pop(k) or "null")
            except ValueError:
                r[k.replace("_json", "")] = None
        r.pop("design_json", None)  # the research comparison (ml/experiments/anchored_check.py), not shown
    try:
        status = learning_status()
    except Exception:  # noqa: BLE001 - the page still shows the history
        status = None
    return {
        "counts": counts,
        "runs": runs,
        "status": status,
        "impact": crm_impact(),
        "lead_model": card("model_card.json"),
        "nba_model": card("nba_card.json"),
        "feed": _feed("all"),
        "settings": {
            "swap_confidence": rules.S["learning"]["swap_confidence"],
            "min_new_outcomes": rules.S["learning"]["min_new_outcomes"],
            "exploration_rate": rules.S["exploration_rate"],
            "window_days": WINDOW_DAYS,
            "control_share": rules.S["global_control"]["share"],
        },
    }
