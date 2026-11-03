"""
A/B tests on emails: two or three variants, an optional no-email control group, a planned sample size, results with
confidence intervals (app.ml.experiments), and winners that the CRM adopts by itself with a hold-back check
(app.services.adoption).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from app import db
from app.core import rules
from app.core.errors import BadRequest, Conflict, NotFound
from app.ml import experiments as X
from app.services import adoption, analytics
from app.services.campaigns import AUDIENCES, recipients, record_assignment
from app.services.content import personal_suffix
from app.services.outreach import lead_slug, personalise, send_tracked_email

log = logging.getLogger(__name__)

AB = rules.S["ab_testing"]
WINDOW_DAYS = int(rules.S["outcome_window_days"])
EMAIL_COST = float(rules.S["actions"].get("email_info", {}).get("cost", 2.0))
TS = "%Y-%m-%d %H:%M:%S"


def get(test_id: int) -> dict:
    t = db.fetchone("SELECT * FROM ab_tests WHERE id=?", (test_id,))
    if not t:
        raise NotFound("A/B test not found")
    return t


def variants_of(t: dict) -> list[dict]:
    try:
        v = json.loads(t.get("variants_json") or "null")
    except ValueError:
        v = None
    if v:
        return v
    return [
        {"key": "A", "label": "Variant A", "subject": t.get("subject_a"), "body": t.get("body_a"), "offer_pct": 0},
        {"key": "B", "label": "Variant B", "subject": t.get("subject_b"), "body": t.get("body_b"), "offer_pct": 0},
    ]


def baseline_rate(metric: str) -> float:
    """The typical rate for the plan: from people randomly left alone (purchase) or past marketing emails (click)."""
    if metric == "click":
        r = db.fetchone("""SELECT COUNT(*) AS n, SUM(CASE WHEN click_count > 0 THEN 1 ELSE 0 END) AS k FROM email_sends
                           WHERE campaign_id IS NOT NULL OR ab_test_id IS NOT NULL""")
        return (r["k"] / r["n"]) if r and r["n"] and r["n"] >= 50 else 0.15
    rows = db.fetchall(
        """SELECT user_id, assigned_at AS sent_at FROM experiment_assignments
                          WHERE arm IN ('control','holdout') AND assigned_at <= datetime('now','localtime',?)""",
        (f"-{WINDOW_DAYS} days",),
    )
    if len(rows) >= 50:
        return max(analytics.conversions_after(rows) / len(rows), 0.01)
    return 0.08


def plan(tier: str, metric: str, n_variants: int, control_share: float, mde: float) -> dict:
    """How many people per arm the test needs, and how many the audience gives."""
    if tier not in AUDIENCES:
        raise BadRequest("Unknown audience.")
    metric = metric if metric in ("purchase", "click") else "purchase"
    audience = len(recipients(tier))
    base = baseline_rate(metric)
    n_var = max(int(n_variants), 1)
    k = X.n_comparisons(n_var, control_share > 0 and metric == "purchase")
    planned = X.sample_size(base, mde, AB["alpha"], AB["power"], k)
    share = (1 - control_share) / n_var if control_share > 0 else 1.0 / n_var
    smallest_share = min(control_share, share) if control_share > 0 else share
    per_arm = int(audience * smallest_share)
    return {
        "audience": audience,
        "baseline_rate": base,
        "planned_per_arm": planned,
        "per_arm_available": per_arm,
        "detectable_lift": X.detectable_effect(base, per_arm, AB["alpha"], AB["power"], k) if per_arm else None,
        "enough": per_arm >= planned,
        "mde": mde,
        "metric": metric,
    }


def create(
    name: str,
    tier: str,
    hypothesis: str,
    metric: str,
    control_share: float | None,
    mde: float | None,
    variants: list[dict],
) -> dict:
    if tier not in AUDIENCES:
        raise BadRequest("Unknown audience.")
    if not (name or "").strip():
        raise BadRequest("Give the test a name.")
    if not variants or not 2 <= len(variants) <= int(AB["max_variants"]):
        raise BadRequest(f"Add 2 to {AB['max_variants']} variants.")
    for v in variants:
        if not (v.get("subject") or "").strip() or not (v.get("body") or "").strip():
            raise BadRequest("Every variant needs a subject and a body.")
        if v.get("offer_pct") and not 0 < int(v["offer_pct"]) <= 50:
            raise BadRequest("Coupon offers must be between 1% and 50%.")
    metric = metric if metric in ("purchase", "click") else "purchase"
    control = AB["control_share"] if control_share is None else float(control_share)
    if not 0 <= control <= 0.5:
        raise BadRequest("The control group must be between 0% and 50%.")
    if metric == "click" and control:
        control = 0.0  # people who get no email cannot click: compare the variants with each other
    mde = float(mde or AB["min_detectable_effect"])
    keys = ["A", "B", "C"][: len(variants)]
    vjson = [
        {
            "key": k,
            "label": (v.get("label") or f"Variant {k}").strip(),
            "subject": v["subject"],
            "body": v["body"],
            "offer_pct": int(v.get("offer_pct") or 0),
        }
        for k, v in zip(keys, variants)
    ]
    p = plan(tier, metric, len(keys), control, mde)
    tid = db.execute(
        """INSERT INTO ab_tests (name, tier, subject_a, body_a, subject_b, body_b, hypothesis, metric,
                        control_share, variants_json, mde, planned_per_arm, status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'draft')""",
        (
            name.strip(),
            tier,
            vjson[0]["subject"],
            vjson[0]["body"],
            vjson[1]["subject"],
            vjson[1]["body"],
            (hypothesis or "").strip(),
            metric,
            control,
            json.dumps(vjson),
            mde,
            p["planned_per_arm"],
        ),
    )
    warning = (
        None
        if p["enough"]
        else (
            f"This audience gives about {p['per_arm_available']} people per arm; {p['planned_per_arm']} are needed to "
            f"detect a {mde * 100:.0f}-point lift. The test will only detect effects of about "
            f"{(p['detectable_lift'] or 0) * 100:.0f} points or more."
        )
    )
    return {"id": tid, "plan": p, "warning": warning, "variants": len(keys)}


def state_of(t: dict, now: datetime | None = None) -> str:
    now = now or datetime.now()
    if t.get("status") in ("draft", None) and not t.get("sent_at"):
        return "draft"
    if t.get("status") == "sending":
        return "sending"
    started = t.get("started_at") or t.get("sent_at")
    try:
        done = bool(started) and now >= datetime.strptime(started[:19], TS) + timedelta(days=WINDOW_DAYS)
    except ValueError:
        done = False
    return "completed" if done else "running"


def analyse(test: dict, now: datetime | None = None) -> dict:
    tid = test["id"]
    rows = db.fetchall(
        """SELECT user_id, arm, probability, assigned_at, tier, occupation, device, source
                          FROM experiment_assignments WHERE experiment_type='ab' AND experiment_id=?""",
        (tid,),
    )
    users = sorted({r["user_id"] for r in rows})
    purchases, clicks = {}, {}
    for i in range(0, len(users), 500):
        chunk = users[i : i + 500]
        q = ",".join("?" * len(chunk))
        for p in db.fetchall(
            f"""SELECT user_id, purchased_at, price_paid, discount_amount FROM purchases
                                 WHERE user_id IN ({q})""",
            chunk,
        ):
            purchases.setdefault(p["user_id"], []).append(
                (p["purchased_at"], p["price_paid"] or 0, p["discount_amount"] or 0)
            )
    for c in db.fetchall(
        """SELECT user_id, first_clicked_at FROM email_sends
                            WHERE ab_test_id=? AND first_clicked_at IS NOT NULL""",
        (tid,),
    ):
        clicks[c["user_id"]] = c["first_clicked_at"]
    t = {"id": tid, "metric": test.get("metric") or "purchase", "variants": variants_of(test)}
    return X.analyse(
        t,
        rows,
        purchases,
        clicks,
        now=now,
        window_days=WINDOW_DAYS,
        alpha=AB["alpha"],
        power=AB["power"],
        mde=float(test.get("mde") or AB["min_detectable_effect"]),
        email_cost=EMAIL_COST,
        min_segment=int(AB["min_per_segment_arm"]),
    )


def send(test_id: int) -> dict:
    test = get(test_id)
    if test["status"] in ("sent", "sending") or not db.claim(
        "UPDATE ab_tests SET status='sending' WHERE id=? AND COALESCE(status,'draft') NOT IN ('sent','sending')",
        (test_id,),
    ):
        raise Conflict("This test was already sent.")
    variants = variants_of(test)
    control = float(test.get("control_share") or 0)
    arms = X.arms_for_test(control, [v["key"] for v in variants])
    spec = {v["key"]: v for v in variants}
    counts = {k: 0 for k, _ in arms}
    for r in recipients(test["tier"]):
        arm, prob = X.arm_for("ab", test_id, r["user_id"], arms)
        record_assignment("ab", test_id, r, arm, prob)
        counts[arm] += 1
        if arm == "control":
            continue
        v = spec[arm]
        slug = lead_slug(r)
        body = personalise(v["body"], r["name"], slug)
        if v.get("offer_pct"):
            code = f"AB{test_id}{arm}-{int(v['offer_pct'])}OFF-{personal_suffix()}"  # one code per person
            db.execute(
                """INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, expires_at, source)
                          VALUES (?,?,?,?,datetime('now','localtime','+72 hours'),'ab_test')""",
                (r["user_id"], code, int(v["offer_pct"]), r.get("recommended_action") or ""),
            )
            body += f"\n\nYour personal code {code} gives {int(v['offer_pct'])}% off for the next 72 hours."
        send_tracked_email(
            r["user_id"],
            r["lead_id"],
            r["email"],
            personalise(v["subject"], r["name"], slug),
            body,
            course_slug=slug,
            ab_test_id=test_id,
            variant=arm,
        )
    db.execute(
        """UPDATE ab_tests SET status='sent', sent_at=datetime('now','localtime'),
                  started_at=datetime('now','localtime') WHERE id=?""",
        (test_id,),
    )
    return counts


def listing() -> list[dict]:
    out = []
    adopted = {a["ab_test_id"]: a for a in adoption_rows()}
    for t in db.fetchall("SELECT * FROM ab_tests ORDER BY COALESCE(started_at, sent_at, created_at) DESC"):
        t["variants"] = variants_of(t)
        t["state"] = state_of(t)
        t["adoption"] = adopted.get(t["id"])
        t["simulated"] = bool(t.get("simulated"))
        if t["state"] in ("running", "completed"):
            try:
                a = analyse(t)
                t["verdict"] = a["verdict"]
                t["people"] = sum(arm["n"] for arm in a["arms"])
            except Exception as e:  # noqa: BLE001 - one broken test must not break the list
                log.exception("A/B test %s could not be analysed", t["id"])
                t["verdict"] = {"status": "error", "headline": "Could not analyse", "detail": str(e)}
        out.append(t)
    return out


def results(test_id: int) -> dict:
    test = get(test_id)
    test["variants"] = variants_of(test)
    test["state"] = state_of(test)
    if test["state"] == "draft":
        p = plan(
            test["tier"],
            test.get("metric") or "purchase",
            len(test["variants"]),
            float(test.get("control_share") or 0),
            float(test.get("mde") or AB["min_detectable_effect"]),
        )
        return {"test": test, "plan": p, "results": None}
    return {"test": test, "results": analyse(test)}


def apply_winner(test_id: int, variant: str, tier: str | None) -> dict:
    """Turn a variant into a campaign draft (for the whole audience or one tier)."""
    test = get(test_id)
    v = next((x for x in variants_of(test) if x["key"] == variant), None)
    if not v:
        raise BadRequest("Unknown variant.")
    tier = tier or test["tier"]
    if tier not in AUDIENCES:
        raise BadRequest("Unknown audience.")
    name = f"Winner of '{test['name']}' ({v.get('label') or v['key']})"
    cid = db.execute(
        """INSERT INTO campaign_schedules (name, tier, subject, body, scheduled_at, status, holdout_share)
                        VALUES (?,?,?,?,NULL,'draft',?)""",
        (name, tier, v["subject"], v["body"], rules.S["campaigns"]["holdout_share"]),
    )
    db.execute("UPDATE ab_tests SET applied_campaign_id=? WHERE id=?", (cid, test_id))
    return {"campaign_id": cid, "tier": tier}


def delete(test_id: int) -> dict:
    test = get(test_id)
    if state_of(test) != "draft":
        raise BadRequest("Only drafts can be deleted (sent tests are part of the history).")
    db.execute("DELETE FROM ab_tests WHERE id=?", (test_id,))
    return test


# adopted winners
def adoption_job(now: datetime | None = None) -> list[dict]:
    """Adopt final content winners; keep checking adopted emails against the old one (every 5 minutes)."""
    tests = db.fetchall("SELECT * FROM ab_tests WHERE sent_at IS NOT NULL")
    return adoption.run_checks(
        tests,
        lambda t, at: analyse(t, now=at),
        variants_of,
        now or datetime.now(),
        float(AB.get("adoption_check_share", 0.10)),
        window_days=WINDOW_DAYS,
        alpha=float(AB["alpha"]),
        auto_adopt=bool(AB.get("auto_adopt", True)),
    )


def adoption_rows() -> list[dict]:
    out = []
    for a in db.fetchall("SELECT * FROM adopted_emails ORDER BY id DESC"):
        try:
            a["check"] = json.loads(a.pop("check_json") or "null")
        except ValueError:
            a["check"] = None
        a["simulated"] = bool(a.get("simulated"))
        out.append(a)
    return out


def revert_adoption(adoption_id: int) -> None:
    a = db.fetchone("SELECT id, status FROM adopted_emails WHERE id=?", (adoption_id,))
    if not a:
        raise NotFound("Adopted email not found")
    if a["status"] not in ("active", "confirmed"):
        raise BadRequest("This email is not in use any more.")
    db.execute(
        """UPDATE adopted_emails SET status='reverted', decided_at=datetime('now','localtime'), reason=?
                  WHERE id=?""",
        ("Switched back by hand from the dashboard.", adoption_id),
    )
