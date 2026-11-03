"""
Only the learners are simulated, and they go through the same CRM as real people.

A small simulated history is made with the command-line tool, in its own data folder with this run's starting
models: every simulated learner is on the reserved .test domain, is scored by the CRM's own lead model, and is decided
for by the same next-best-action code; removing the history leaves real people alone.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import rules
from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]
LEARNERS, DAYS = 60, 21


def _cli(data_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(
        os.environ,
        DATA_DIR=str(data_dir),
        PYTHONPATH=str(BACKEND),
        SCHEDULER_ENABLED="false",
        SIMULATION_ENABLED="false",
        GMAIL_USER="",
        GMAIL_APP_PASSWORD="",
        GEMINI_API_KEY="",
    )
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=600
    )


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("history")
    shutil.copytree(get_settings().model_dir, data_dir / "models")
    done = _cli(data_dir, "history", "create", "--n", str(LEARNERS), "--days", str(DAYS), "--seed", "7")
    assert done.returncode == 0, done.stderr[-2000:]
    con = sqlite3.connect(data_dir / "xeducation.db")
    con.row_factory = sqlite3.Row
    yield data_dir, con
    con.close()


def _one(con, sql, params=()):
    return con.execute(sql, params).fetchone()[0]


def test_every_simulated_learner_is_on_the_reserved_test_domain(history):
    _, con = history
    emails = [r["email"] for r in con.execute("SELECT email FROM users")]
    assert len(emails) == LEARNERS
    assert all(rules.is_simulated_email(e) for e in emails)


def test_simulated_learners_are_scored_by_the_crms_own_lead_model(history):
    _, con = history
    unscored = _one(con, "SELECT COUNT(*) FROM users u WHERE NOT EXISTS (SELECT 1 FROM leads l WHERE l.user_id=u.id)")
    assert unscored == 0
    versions = {r[0] for r in con.execute("SELECT DISTINCT model_version FROM leads")}
    assert versions and all(v and (v.startswith("v7-base-") or v.startswith("v7.1-live-")) for v in versions)


def test_next_best_action_decides_for_them_with_logged_propensities(history):
    _, con = history
    rows = con.execute("SELECT policy, propensity, action FROM nba_decisions").fetchall()
    assert len(rows) > LEARNERS
    assert {r["policy"] for r in rows} <= {"model", "explore", "holdout"}
    assert all(0 < r["propensity"] <= 1 for r in rows if r["policy"] != "holdout")
    assert _one(con, "SELECT COUNT(*) FROM learning_runs WHERE simulated=1") >= 1


def test_simulated_call_tasks_wait_for_the_real_team(history):
    _, con = history
    # the history may contain calls made in the past, but nobody on the team is simulated: no task is done by a
    # simulated counsellor
    team = _one(con, "SELECT COUNT(*) FROM team_members")
    assert team <= 1  # at most the owner account
    names = {r[0] for r in con.execute("SELECT DISTINCT done_by FROM sales_tasks WHERE done_by IS NOT NULL")}
    assert all("simulated" not in (n or "").lower() for n in names)


def test_removing_the_history_leaves_real_people_alone(history):
    data_dir, con = history
    con.execute(
        "INSERT INTO users (name, email, password_hash, is_verified) VALUES ('Real Person', 'real@example.com', '!', 1)"
    )
    con.commit()
    done = _cli(data_dir, "history", "remove")
    assert done.returncode == 0, done.stderr[-2000:]
    assert [r[0] for r in con.execute("SELECT email FROM users")] == ["real@example.com"]
    assert _one(con, "SELECT COUNT(*) FROM nba_decisions") == 0
    assert _one(con, "SELECT COUNT(*) FROM learning_runs WHERE simulated=1") == 0
