"""
Helpers for the experiments that run whole simulated histories: each history runs in its own temporary copy
of the project (code, crm_settings.json and the starting models), so your own database and models are never
touched, and an experiment can change a setting in its copy only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SKIP = shutil.ignore_patterns(
    "venv",
    ".venv",
    "node_modules",
    "dist",
    ".git",
    "__pycache__",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.db-journal",
    "*.previous.pkl",
    "logs",
    "frontend",
    "docs",
    "results",
    "xeducation-update-*",
    "xeducation-backup-*",
)
STARTERS = ("lead_model.starter.pkl", "nba_model.starter.pkl")


def model_dir() -> str:
    """Where this project keeps its trained models (backend/data/models, or DATA_DIR/models)."""
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from app.core.config import get_settings

    return str(get_settings().model_dir)


def require_starting_models() -> None:
    for name in STARTERS:
        if not os.path.exists(os.path.join(model_dir(), name)):
            raise SystemExit(f"{name} not found in {model_dir()}: run 'python -m app.cli bootstrap' in backend first.")


def copy_project(dest: str) -> str:
    """A copy of the project for one history, with this project's starting models."""
    shutil.copytree(ROOT, dest, ignore=SKIP)
    models = os.path.join(dest, "backend", "data", "models")
    os.makedirs(models, exist_ok=True)
    src = model_dir()
    for name in os.listdir(src):
        if name.endswith((".pkl", ".json")):
            shutil.copy2(os.path.join(src, name), os.path.join(models, name))
    return dest


def env_for(dest: str) -> dict:
    """Environment of a process working on a copy: its own data folder, no email, no Gemini, no live learners."""
    return dict(
        os.environ,
        PYTHONUTF8="1",
        OMP_NUM_THREADS="1",
        DATA_DIR=os.path.join(dest, "backend", "data"),
        GEMINI_API_KEY="",
        GMAIL_USER="",
        GMAIL_APP_PASSWORD="",
        SIMULATION_ENABLED="false",
        PYTHONPATH=os.path.join(dest, "backend"),
    )


def run_history(dest: str, n: int, days: int, seed: int, quiet: bool = True) -> None:
    """python -m app.cli history create in the copy (its own code, settings and data)."""
    subprocess.run(
        [sys.executable, "-m", "app.cli", "history", "create", "--n", str(n), "--days", str(days), "--seed", str(seed)],
        cwd=os.path.join(dest, "backend"),
        env=env_for(dest),
        check=True,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.PIPE if quiet else None,
    )


def use_copy(folder: str):
    """Inside an analysis process: import the copy's own code (or this project's, for a folder kept without code)
    and point it at the copy's database. Returns app.db."""
    code = folder if os.path.exists(os.path.join(folder, "backend", "app")) else ROOT
    os.environ["DATA_DIR"] = os.path.join(folder, "backend", "data")
    sys.path.insert(0, os.path.join(code, "backend"))
    os.chdir(os.path.join(folder, "backend"))
    from app import db

    db.DB_PATH = os.path.join(folder, "backend", "data", "xeducation.db")
    return db
