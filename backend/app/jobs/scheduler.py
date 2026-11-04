"""
Background jobs, started with the API (``app.main`` lifespan) and stopped with it.

    automations          every 1 min (demo) / 5 min (live)  follow-ups for checkouts, carts, wishlists, visits
    campaigns            every minute                        send campaigns whose time has come
    team                 every minute                        expire stale tasks, give new leads to counsellors
    adoption             every 5 minutes                     adopt final A/B winners, re-check adopted emails
    score refresh        every 5 min (demo) / 60 min (live)  re-score every lead (time away changes the score)
    learning loop        every 5 min (demo) / 60 min (live)  retrain when enough new outcomes are known
    simulated learners   every 10 seconds                    the live simulation (does nothing while paused)
    housekeeping         every hour                          delete one-time codes and simulated inbox emails
                                                             older than a day
    email retry          every 10 minutes                    emails the mail server did not take, tried again
                                                             (for a day, six times at most)

One scheduler in one process: run the API with a single worker (the start scripts do).
"""

from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app.core import rules
from app.core.config import get_settings

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _safe(name: str, fn, *args):
    def run():
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 - a job must never kill the scheduler thread
            log.exception("Background job '%s' failed", name)

    run.__name__ = name
    return run


def automations_job():
    from app.jobs import automations

    automations.run_all()


def campaigns_job():
    from app.services import campaigns

    campaigns.run_due()


def team_job():
    from app.services import team

    n = team.expire_tasks()
    if n:
        log.info("%d open task(s) expired (nobody did them within the expiry time)", n)
    made = team.auto_assign()
    if made:
        log.info("%d lead(s) given to counsellors", len(made))


def adoption_job():
    from app.services import abtests

    abtests.adoption_job()


def refresh_scores_job(reason: str = "scheduled"):
    from app.services import scoring

    scoring.refresh_scores(reason)


def learning_job():
    if not get_settings().learning_loop_enabled:
        return
    from app.ml import learning

    learning.scheduled_job()


def housekeeping_job():
    from app import db
    from app.services import learner_auth

    n = learner_auth.purge_old()
    if n:
        log.info("Housekeeping: deleted %d expired one-time code(s) and simulated inbox email(s)", n)
    db.trim_memory()


def email_retry_job():
    from app.services import outreach

    outreach.retry_failed()


def simulation_job():
    from app.simulation import live

    live.tick()


def keep_alive_job():
    import os
    import urllib.request

    settings = get_settings()
    url = (settings.keep_alive_url or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not url:
        return
    target = f"{url}/api/health"
    try:
        req = urllib.request.Request(
            target,
            headers={"User-Agent": "LeadIntel-KeepAlive/1.0", "X-Keep-Alive": "true"},
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            log.info("Keep-alive self-ping sent to %s -> status %d", target, res.status)
    except Exception as exc:  # noqa: BLE001 - keep-alive failure must not crash scheduler
        log.warning("Keep-alive self-ping to %s failed: %s", target, exc)


def start() -> BackgroundScheduler | None:
    """Start every job (once per process)."""
    global _scheduler
    settings = get_settings()
    if _scheduler is not None or not settings.scheduler_enabled:
        if not settings.scheduler_enabled:
            log.info("Background jobs are switched off (SCHEDULER_ENABLED=false)")
        return _scheduler
    from app.services import team

    team.assign_from()  # leads arriving from the first start on are given out automatically
    # the computer's own time zone, like every time the CRM stores (SQLite 'localtime')
    sched = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
    every = int(rules.by_mode("automation_minutes")["job_every"])
    learn_every = int(rules.S["learning"]["check_every_minutes"][rules.MODE])
    refresh_every = int(rules.by_mode("score_refresh_minutes"))
    sched.add_job(_safe("automations", automations_job), "interval", minutes=every, id="automations")
    sched.add_job(_safe("campaigns", campaigns_job), "interval", minutes=1, id="campaigns")
    sched.add_job(_safe("team", team_job), "interval", minutes=1, id="team")
    sched.add_job(_safe("adoption", adoption_job), "interval", minutes=5, id="adoption")
    sched.add_job(_safe("score_refresh", refresh_scores_job), "interval", minutes=refresh_every, id="score_refresh")
    if settings.learning_loop_enabled:
        sched.add_job(_safe("learning", learning_job), "interval", minutes=learn_every, id="learning")
    sched.add_job(_safe("housekeeping", housekeeping_job), "interval", minutes=60, id="housekeeping")
    sched.add_job(_safe("email_retry", email_retry_job), "interval", minutes=10, id="email_retry")
    sim = rules.S.get("live_simulation") or {}
    sim_every = max(3, int(sim.get("tick_seconds", 10)))
    simulate = settings.simulation_enabled is not False  # None: crm_settings.json and the dashboard decide
    if simulate:
        sched.add_job(_safe("simulation", simulation_job), "interval", seconds=sim_every, id="simulation")
    if settings.keep_alive_enabled:
        keep_every = max(1, min(14, int(settings.keep_alive_interval_minutes)))
        sched.add_job(_safe("keep_alive", keep_alive_job), "interval", minutes=keep_every, id="keep_alive")
        threading.Timer(60.0, _safe("keep_alive_startup", keep_alive_job)).start()
    sched.start()
    _scheduler = sched
    # once right after start-up: scores saved by an older model are brought up to date
    threading.Timer(30.0, _safe("score_refresh_startup", refresh_scores_job, "startup")).start()
    log.info(
        "Background jobs started: automations every %d min, learning check every %d min, scores refreshed every "
        "%d min, simulated learners every %d s%s",
        every,
        learn_every,
        refresh_every,
        sim_every,
        "" if simulate else " (switched off by SIMULATION_ENABLED=false)",
    )
    return sched


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("Background jobs stopped")


def jobs() -> list[dict]:
    """The jobs and when each runs next (for the health page)."""
    if _scheduler is None:
        return []
    return [
        {"id": j.id, "next_run": j.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if j.next_run_time else None}
        for j in _scheduler.get_jobs()
    ]
