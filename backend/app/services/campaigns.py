"""
Scheduled email campaigns. Each campaign keeps a random hold-out group (crm_settings.json campaigns.holdout_share)
that gets nothing, so its report shows what the campaign added, not only who bought afterwards.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta

from app import db
from app.core import rules
from app.core.errors import BadRequest, Conflict, NotFound
from app.ml import experiments as X
from app.services import analytics, outreach
from app.services.leads import LATEST
from app.services.outreach import lead_slug, personalise, send_again, send_tracked_email

log = logging.getLogger(__name__)

TIERS = rules.tier_names()
AUDIENCES = TIERS + ["All leads"]
WINDOW_DAYS = int(rules.S["outcome_window_days"])
TS = "%Y-%m-%d %H:%M:%S"


def normalise_dt(value: str | None) -> str:
    """'2026-10-02T10:30' (browser) becomes '2026-10-02 10:30:00' (comparable in SQLite)."""
    v = (value or "").strip().replace("T", " ")
    try:
        return datetime.strptime(v[:16], "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M:00")
    except ValueError:
        raise BadRequest("Use a date and time like 2026-10-02 10:30.") from None


def recipients(tier: str) -> list[dict]:
    """Who a campaign or A/B test reaches now: open leads in the audience who accept email, not customers, not closed
    as lost, and never the untouched control group."""
    tier_sql = "" if tier == "All leads" else " AND l.recommended_action=?"
    params = () if tier == "All leads" else (tier,)
    rows = db.fetchall(
        f"""SELECT l.id AS lead_id, l.user_id, l.course_slug, l.course_type, l.recommended_action,
                                  u.email, u.name
                           FROM {LATEST} l JOIN users u ON l.user_id = u.id
                           LEFT JOIN user_profiles up ON up.user_id = l.user_id
                           WHERE COALESCE(up.do_not_email,'No') != 'Yes'
                             AND l.user_id NOT IN (SELECT user_id FROM purchases)
                             AND l.user_id NOT IN (SELECT user_id FROM pipeline_overrides WHERE stage='Lost')
                             {tier_sql}""",
        params,
    )
    return [r for r in rows if not rules.in_global_control(r["user_id"])]


def record_assignment(kind: str, exp_id: int, r: dict, arm: str, prob: float) -> None:
    """Who was in which arm, with the probability of that arm (the learning loop uses the no-email arms)."""
    row = db.fetchone(
        "SELECT features_json FROM score_snapshots WHERE user_id=? ORDER BY id DESC LIMIT 1", (r["user_id"],)
    )
    feats = row["features_json"] if row else None
    f = json.loads(feats) if feats else {}
    db.execute(
        """INSERT OR IGNORE INTO experiment_assignments (experiment_type, experiment_id, user_id, lead_id, arm,
                  probability, features_json, tier, occupation, device, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            kind,
            exp_id,
            r["user_id"],
            r.get("lead_id"),
            arm,
            prob,
            feats,
            r.get("recommended_action"),
            f.get("CurrentOccupation"),
            f.get("DeviceType"),
            f.get("LeadSource"),
        ),
    )


def get(campaign_id: int) -> dict:
    c = db.fetchone("SELECT * FROM campaign_schedules WHERE id=?", (campaign_id,))
    if not c:
        raise NotFound("Campaign not found")
    return c


def schedule(name: str, tier: str, subject: str, body: str, scheduled_at: str, holdout_share: float | None) -> dict:
    if tier not in AUDIENCES:
        raise BadRequest("Unknown audience.")
    if not name.strip() or not subject.strip() or not body.strip():
        raise BadRequest("Name, subject and body are required.")
    when = normalise_dt(scheduled_at)
    share = rules.S["campaigns"]["holdout_share"] if holdout_share is None else holdout_share
    if not 0 <= float(share) <= 0.5:
        raise BadRequest("The hold-out group must be between 0% and 50%.")
    cid = db.execute(
        """INSERT INTO campaign_schedules (name, tier, subject, body, scheduled_at, status, holdout_share)
                        VALUES (?,?,?,?,?,'scheduled',?)""",
        (name.strip(), tier, subject, body, when, float(share)),
    )
    return {"id": cid, "scheduled_at": when, "audience_now": len(recipients(tier))}


def send(campaign_id: int) -> int:
    """Send a campaign once (the every-minute job and "Send now" may collide: only one of them sends it)."""
    camp = db.fetchone("SELECT * FROM campaign_schedules WHERE id=?", (campaign_id,))
    if not camp or camp["sent"]:
        return 0
    if not db.claim(
        """UPDATE campaign_schedules SET status='sending'
                       WHERE id=? AND sent=0 AND COALESCE(status,'scheduled') != 'sending'""",
        (campaign_id,),
    ):
        return 0
    sent, held, errors = 0, 0, []
    share = camp.get("holdout_share")
    share = float(rules.S["campaigns"]["holdout_share"] if share is None else share)
    arms = X.campaign_arms(share)
    for r in recipients(camp["tier"]):
        arm, prob = X.arm_for("campaign", campaign_id, r["user_id"], arms)
        record_assignment("campaign", campaign_id, r, arm, prob)
        if arm == "holdout":  # randomly left alone: measures what the campaign adds
            held += 1
            continue
        slug = lead_slug(r)
        ok, msg = send_tracked_email(
            r["user_id"],
            r["lead_id"],
            r["email"],
            personalise(camp["subject"], r["name"], slug),
            personalise(camp["body"], r["name"], slug),
            course_slug=slug,
            campaign_id=campaign_id,
            campaign_name=camp["name"],
        )
        sent += 1 if ok else 0
        if not ok and "opted out" not in msg:
            errors.append(msg)
    db.execute(
        """UPDATE campaign_schedules SET sent=1, sent_at=datetime('now','localtime'), status=?,
                  recipients=?, held_out=?, error=? WHERE id=?""",
        ("sent" if not errors else "sent_with_errors", sent, held, "; ".join(errors[:3]) or None, campaign_id),
    )
    log.info("Campaign '%s' sent to %d recipient(s), %d held out", camp["name"], sent, held)
    return sent


def send_failed_again(campaign_id: int) -> dict:
    """Send the campaign's emails that the mail server did not take (a lost connection, a daily limit) once more.
    Everyone keeps the group they were drawn into, so the hold-out comparison stays fair."""
    camp = get(campaign_id)
    if not camp["sent"]:
        raise Conflict("This campaign has not been sent yet.")
    if outreach.mailer.paused():
        wait = max(1, round((outreach.mailer.paused_until() - time.time()) / 60))
        raise Conflict(f"The mail server could not be reached a moment ago. Try again in {wait} minute(s).")
    if not outreach.resend_lock.acquire(blocking=False):
        raise Conflict("Emails that did not go out are being sent again right now. Look again in a minute.")
    try:
        return _send_failed_again(camp)
    finally:
        outreach.resend_lock.release()


def _send_failed_again(camp: dict) -> dict:
    campaign_id = camp["id"]
    rows = db.fetchall(
        """SELECT es.id, es.user_id, es.token, es.subject, es.body, es.lead_id FROM email_sends es
           WHERE es.campaign_id=? AND es.error IS NOT NULL ORDER BY es.id""",
        (campaign_id,),
    )
    sent, errors = 0, []
    for r in rows:
        lead = db.fetchone("SELECT course_slug, course_type FROM leads WHERE id=?", (r["lead_id"],)) or {}
        ok, msg = send_again(r, lead_slug(lead))
        sent += 1 if ok else 0
        if not ok and "opted out" not in msg:
            errors.append(msg)
    left = len(rows) - sent
    db.execute(
        """UPDATE campaign_schedules SET recipients=COALESCE(recipients, 0) + ?, status=?, error=? WHERE id=?""",
        (sent, "sent_with_errors" if errors else "sent", "; ".join(errors[:3]) or None, campaign_id),
    )
    log.info("Campaign '%s': %d failed email(s) sent again, %d still not sent", camp["name"], sent, left)
    return {"sent": sent, "still_failed": left, "error": errors[0] if errors else None}


def send_now(campaign_id: int) -> int:
    camp = get(campaign_id)
    if camp["sent"] or camp.get("status") == "sending":
        raise Conflict("This campaign was already sent (or is being sent right now).")
    return send(campaign_id)


def run_due() -> None:
    """Scheduler job: send every campaign whose time has come."""
    now = datetime.now().strftime(TS)
    for camp in db.fetchall(
        """SELECT id FROM campaign_schedules WHERE sent=0 AND scheduled_at IS NOT NULL
                               AND scheduled_at <= ? AND COALESCE(status,'scheduled') NOT IN ('sending','draft')""",
        (now,),
    ):
        try:
            send(camp["id"])
        except Exception:  # noqa: BLE001 - one broken campaign must not stop the others
            log.exception("Campaign %s could not be sent", camp["id"])


def report() -> list[dict]:
    """Every campaign with delivery, clicks, purchases in the outcome window and, once sent, its effect against the
    hold-out group (difference in purchase rate with a 95% interval)."""
    out = []
    cutoff = (datetime.now() - timedelta(days=WINDOW_DAYS)).strftime(TS)
    for c in db.fetchall("SELECT * FROM campaign_schedules ORDER BY COALESCE(scheduled_at, created_at) DESC"):
        sends = db.fetchall(
            "SELECT user_id, sent_at, click_count, error FROM email_sends WHERE campaign_id=?", (c["id"],)
        )
        failed = [s for s in sends if s["error"]]
        c["delivered"] = len(sends) - len(failed)
        c["failed"] = len(failed)
        c["failed_reason"] = failed[-1]["error"] if failed else None
        c["clicks"] = sum(1 for s in sends if s["click_count"])
        c["conversions"] = analytics.conversions_after(sends)
        c["audience_now"] = len(recipients(c["tier"])) if not c["sent"] else None
        c["simulated"] = bool(c.get("simulated"))
        holdout = db.fetchall(
            """SELECT user_id, assigned_at AS sent_at FROM experiment_assignments
                                 WHERE experiment_type='campaign' AND experiment_id=? AND arm='holdout'""",
            (c["id"],),
        )
        if holdout and sends:
            hc = analytics.conversions_after(holdout)
            c["holdout"] = {"people": len(holdout), "conversions": hc}
            lo, hi = X.diff_ci(c["conversions"], len(sends), hc, len(holdout))
            c["incremental"] = {
                "lift": c["conversions"] / len(sends) - hc / len(holdout),
                "ci": [lo, hi],
                "final": bool(c.get("sent_at") and c["sent_at"] <= cutoff),
            }
        out.append(c)
    return out


def delete(campaign_id: int) -> dict:
    camp = get(campaign_id)
    if camp["sent"]:
        raise BadRequest("Sent campaigns are part of the history and cannot be deleted.")
    db.execute("DELETE FROM campaign_schedules WHERE id=?", (campaign_id,))
    return camp
