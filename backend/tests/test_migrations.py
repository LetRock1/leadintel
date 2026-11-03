"""The database schema is made only by the versioned migrations, which go up and down cleanly."""

from __future__ import annotations

import sqlite3

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app import db

CORE_TABLES = {
    "users",
    "otp_tokens",
    "user_profiles",
    "user_sessions",
    "behaviour_events",
    "cart",
    "wishlist",
    "purchases",
    "leads",
    "nba_decisions",
    "sales_tasks",
    "email_sends",
    "learning_runs",
    "team_members",
    "audit_log",
    "call_slot_prices",
    "simulated_inbox",
}


def _config(path):
    cfg = Config()
    cfg.set_main_option("script_location", str(db.MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _tables(path):
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def test_one_linear_history_of_migrations():
    script = ScriptDirectory.from_config(_config(":memory:"))
    heads = script.get_heads()
    assert len(heads) == 1, f"more than one head: {heads}"
    revisions = list(script.walk_revisions())
    assert [r.revision for r in reversed(revisions)] == [
        "0001_initial_schema",
        "0002_capacity_pricing",
        "0003_hashed_codes",
        "0004_anchored_update",
        "0005_money",
        "0006_email_errors",
    ]


def test_a_new_database_is_created_at_the_latest_version(tmp_path):
    path = tmp_path / "fresh.db"
    db.init_db(str(path))
    assert db.schema_version(str(path)) == "0006_email_errors"
    assert _tables(path) >= CORE_TABLES
    db.init_db(str(path))  # running it again changes nothing
    assert db.schema_version(str(path)) == "0006_email_errors"


def test_every_migration_can_be_undone_and_redone(tmp_path):
    path = tmp_path / "updown.db"
    cfg = _config(path)
    command.upgrade(cfg, "head")
    emails = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(email_sends)")}
    assert {"error", "attempts"} <= emails
    command.downgrade(cfg, "0005_money")
    emails = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(email_sends)")}
    assert not {"error", "attempts"} & emails and "click_count" in emails
    con = sqlite3.connect(path)
    decisions = {r[1] for r in con.execute("PRAGMA table_info(nba_decisions)")}
    coupons = {r[1] for r in con.execute("PRAGMA table_info(coupons_issued)")}
    con.close()
    assert {"coupon_value", "coupon_cost", "budget_price"} <= decisions
    assert {"expected_cost", "source"} <= coupons
    command.downgrade(cfg, "0004_anchored_update")
    con = sqlite3.connect(path)
    decisions = {r[1] for r in con.execute("PRAGMA table_info(nba_decisions)")}
    coupons = {r[1] for r in con.execute("PRAGMA table_info(coupons_issued)")}
    con.close()
    assert not {"coupon_value", "coupon_cost", "budget_price"} & decisions and "slot_price" in decisions
    assert not {"expected_cost", "source"} & coupons and "coupon_code" in coupons
    runs = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(learning_runs)")}
    assert {"retrain_method", "anchored_true_logloss", "aware_true_logloss", "design_json"} <= runs
    command.downgrade(cfg, "0003_hashed_codes")
    runs = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(learning_runs)")}
    assert "design_json" not in runs and "challenger_true_logloss" in runs
    command.downgrade(cfg, "0002_capacity_pricing")
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(otp_tokens)")}
    assert "otp" in cols and "code_hash" not in cols
    assert "simulated_inbox" not in _tables(path)
    command.downgrade(cfg, "base")
    assert _tables(path) <= {"alembic_version", "sqlite_sequence"}  # sqlite_sequence is SQLite's own
    command.upgrade(cfg, "head")
    assert _tables(path) >= CORE_TABLES


def test_the_running_database_is_at_the_latest_version():
    assert db.schema_version() == "0006_email_errors"
