"""
Command-line tasks for the backend (run from the backend folder with its virtual environment):

    python -m app.cli bootstrap                 first start: database, starting models, starting history
    python -m app.cli migrate                   create or upgrade the database schema
    python -m app.cli train lead|uplift|all     train the starting models again
    python -m app.cli history create [--n 2000 --days 180 --seed 2026]
    python -m app.cli history remove            delete every simulated learner and restore the starting models
    python -m app.cli simulation status|reset|self-check
    python -m app.cli serve [--host 127.0.0.1 --port 8000]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from app.core.config import get_settings
from app.core.logging import setup_logging


def _say(*a):
    print(*a, flush=True)


def _lead_model_state() -> tuple[bool, str]:
    """(usable, why not / version) for the saved lead model."""
    from app.ml import features as F
    from app.ml.training import lead as T

    if not os.path.exists(T.MODEL_PATH):
        return False, "not found"
    try:
        import joblib

        b = joblib.load(T.MODEL_PATH)
    except Exception as e:  # noqa: BLE001 - unreadable or another scikit-learn version
        return False, f"cannot be loaded ({e.__class__.__name__})"
    if "starter" not in b:
        return False, "is from an older version"
    if b.get("feature_version") != F.FEATURE_VERSION:
        return False, "was built for other features"
    return True, str(b.get("version"))


def _simulated_counts() -> tuple[int, int]:
    from app import db
    from app.core import rules

    learners = db.fetchone("SELECT COUNT(*) AS c FROM users WHERE email LIKE ?", (f"%@{rules.SIMULATED_DOMAIN}",))["c"]
    runs = db.fetchone("SELECT COUNT(*) AS c FROM learning_runs WHERE simulated=1")["c"]
    return learners, runs


def cmd_migrate(_args) -> int:
    from app import db

    db.init_db()
    _say(f"Database ready ({db.schema_version()}) at {db.DB_PATH}")
    return 0


def cmd_train(args) -> int:
    from app.ml.training import lead, uplift

    if args.which in ("lead", "all"):
        lead.train(say=_say)
    if args.which in ("uplift", "all"):
        uplift.train(say=_say)
    return 0


def cmd_bootstrap(args) -> int:
    """Only does what is missing, so it is quick on every start after the first."""
    from app import db
    from app.core import rules
    from app.ml.training import lead, uplift

    db.init_db()
    retrained = False
    ok, why = _lead_model_state()
    if not ok:
        _say(f"\n==== Training the lead-scoring model (the saved one {why}; about 1 minute) ====")
        lead.train(say=_say)
        retrained = True
    if retrained or not os.path.exists(uplift.NBA_PATH):
        _say("\n==== Training the next-best-action model (about 30 seconds) ====")
        uplift.train(say=_say)
    conf = rules.S.get("starting_history") or {}
    learners, runs = _simulated_counts()
    if learners and (not runs or retrained):  # made by an older version, or with older models
        _say("\n==== Removing the old simulated history (real data is kept) ====")
        from app.simulation import history

        history.with_shared_connection(history.remove)
        learners = 0
    if conf.get("create_on_first_start", True) and learners == 0 and not args.skip_history:
        n, days = int(conf.get("learners", 2000)), int(conf.get("days", 180))
        _say(
            f"\n==== Creating the starting history: {n:,} simulated learners over {days} days "
            f"(first start only, about 10 minutes) ===="
        )
        from app.simulation import history

        history.with_shared_connection(history.generate, n, days, int(args.seed))
    from app.services import team

    team.ensure_owner(get_settings().crm_owner_email, get_settings().crm_owner_name)
    _say("\nModels and data are ready.")
    return 0


def cmd_history(args) -> int:
    from app.simulation import history

    if args.action == "remove":
        n = history.with_shared_connection(history.remove)
        _say(
            f"Removed {n:,} simulated learners, their history, the simulated campaigns, A/B tests and learning runs, "
            f"and restored the starting models."
        )
    else:
        history.with_shared_connection(history.generate, args.n, args.days, args.seed)
    return 0


def cmd_simulation(args) -> int:
    from app.simulation import live

    if args.action == "self-check":
        _say(json.dumps(live.self_check(), indent=2))
    elif args.action == "reset":
        live.reset()
        _say("The simulator's own records were cleared; it re-creates them from the CRM on its next start.")
    else:
        _say(json.dumps(live.get_world().status(), indent=2, default=str))
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        workers=1,
        log_config=None,
        proxy_headers=False,
        access_log=False,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_path)
    ap = argparse.ArgumentParser(prog="python -m app.cli", description="X Education CRM backend tasks")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bootstrap", help="first start: database, starting models, starting history")
    b.add_argument("--skip-history", action="store_true", help="do not create the simulated starting history")
    b.add_argument("--seed", type=int, default=2026)
    b.set_defaults(fn=cmd_bootstrap)
    sub.add_parser("migrate", help="create or upgrade the database schema").set_defaults(fn=cmd_migrate)
    t = sub.add_parser("train", help="train the starting models again")
    t.add_argument("which", choices=["lead", "uplift", "all"])
    t.set_defaults(fn=cmd_train)
    h = sub.add_parser("history", help="the simulated six-month starting history")
    h.add_argument("action", choices=["create", "remove"])
    h.add_argument("--n", type=int, default=2000)
    h.add_argument("--days", type=int, default=180)
    h.add_argument("--seed", type=int, default=2026)
    h.set_defaults(fn=cmd_history)
    s = sub.add_parser("simulation", help="the simulated learners using the website in real time")
    s.add_argument("action", choices=["status", "reset", "self-check"])
    s.set_defaults(fn=cmd_simulation)
    v = sub.add_parser("serve", help="run the API (one worker: the background jobs run inside it)")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    v.set_defaults(fn=cmd_serve)
    args = ap.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
