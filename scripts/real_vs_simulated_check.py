"""
Does the CRM treat real people exactly like simulated learners? On a copy of your data, every simulated learner is
turned into a "real" person (only the email domain changes: @demo.xeducation.test becomes @learners.example.com), and
every CRM page's numbers and a set of Ask answers are compared before and after. Your own data is never changed.

    backend/.venv/bin/python scripts/real_vs_simulated_check.py          macOS, Linux
    backend\\.venv\\Scripts\\python scripts\\real_vs_simulated_check.py    Windows

It copies backend/data to a temporary folder (the database with SQLite's backup, so the system may keep running),
starts a second API on that copy on port 8765 with the background jobs and the simulated learners switched off (so
nothing else moves between the two readings), reads every page, relabels, restarts, reads again, and deletes the
copy. The CRM password is asked for (or read from CRM_PASSWORD) and never printed. Options: --email (a CRM admin),
--port, --keep (keep the copy and the two readings). Exits 1 if anything differs besides the real/simulated split.
"""

from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SIM, NEW = "@demo.xeducation.test", "@learners.example.com"
READS = [
    "/crm/stats", "/crm/stats/daily", "/crm/forecast", "/crm/priority-queue?limit=50", "/crm/model/health",
    "/crm/nba/performance", "/crm/campaign-influence", "/crm/capacity", "/crm/leads?limit=200&sort=score",
    "/crm/leads?limit=200&sort=plv", "/crm/actions?status=all&limit=500", "/crm/callbacks?status=all",
    "/crm/coupons?limit=100", "/crm/campaigns", "/crm/ab-tests", "/crm/adoptions", "/crm/learning/overview",
    "/crm/journeys", "/crm/pipeline?owner=all&include_simulated=true&limit=60&sort=money",
    "/crm/pipeline?owner=all&include_simulated=true&limit=60&sort=score", "/crm/planner", "/crm/money",
    "/crm/team/performance", "/crm/start", "/crm/qna",
]  # fmt: skip
QUESTIONS = [
    "Who should we call today?", "Which leads are most likely to buy?", "How is the pipeline looking?",
    "Should we hire another counsellor?", "Is the learning loop fooling itself?", "What do our emails and calls add?",
    "How are the A/B tests doing?", "Is the CRM actually making a difference?", "What is a call slot worth today?",
    "How much did we sell in the last 30 days?", "How many leads came in this week?",
]  # fmt: skip
# the real/simulated split itself, and clocks (a few minutes pass between the two readings)
SPLIT = {
    "simulated", "simulated_people", "real_people", "real_customers", "simulated_customers", "real_purchases",
    "simulated_purchases", "real_revenue", "simulated_revenue", "learners", "counts", "other_segment_count",
    "simulated_leads", "real", "email", "read_at", "as_of", "generated_at", "now", "latency", "score_refresh",
    "last_seen", "away_days", "lead_age_days", "days_left", "days_open", "age_days", "next_check", "last_tick",
}  # fmt: skip


def call(api: str, method: str, path: str, body=None, token: str | None = None):
    req = urllib.request.Request(
        api + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def copy_data(dst: Path) -> Path:
    src = BACKEND / "data"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("xeducation.db*", "logs", "initial-admin-password.txt"))
    with sqlite3.connect(src / "xeducation.db") as a, sqlite3.connect(dst / "xeducation.db") as b:
        a.backup(b)
    return dst / "xeducation.db"


def start_api(data: Path, port: int) -> subprocess.Popen:
    env = {**os.environ, "DATA_DIR": str(data), "SCHEDULER_ENABLED": "false", "SIMULATION_ENABLED": "false"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.cli", "serve", "--port", str(port)],
        cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(240):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ready", timeout=5) as r:
                if r.status == 200:
                    return proc
        except OSError:
            pass
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    proc.kill()
    raise SystemExit(f"The copy's API did not start on port {port}.")


def reading(api: str, email: str, password: str) -> dict:
    s, r = call(api, "POST", "/crm/auth/login", {"email": email, "password": password})
    if s != 200:
        raise SystemExit("Could not sign in to the CRM with that email address and password.")
    token = r["token"]
    out = {p: call(api, "GET", p, token=token) for p in READS}
    for q in QUESTIONS:
        s, r = call(api, "POST", "/crm/copilot", {"question": q}, token)
        out["Ask: " + q] = (s, {"answer": r.get("answer"), "data": (r.get("tools") or [{}])[0].get("data")})
    return out


def _plain(text: str) -> str:
    """An answer without its real/simulated breakdown ("(1 real person, 97 simulated)", "204 of these are ...")."""
    text = text.replace(NEW, SIM)
    text = re.sub(r" \([\d,]+ real (person|people), [\d,]+ simulated\)", "", text)
    return re.sub(r" [\d,]+ of these are simulated learners\.", "", text)


def walk(a, b, path: str, out: list) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in SPLIT:
                walk(a.get(k), b.get(k), f"{path}.{k}", out)
    elif isinstance(a, list | tuple) and isinstance(b, list | tuple):
        if len(a) != len(b):
            out.append((path, f"{len(a)} items", f"{len(b)} items"))
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", out)
    elif isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9):  # the same number (up to float rounding)
            out.append((path, a, b))
    elif isinstance(a, str) and isinstance(b, str):
        if _plain(a) != _plain(b) and not a[:4].isdigit():  # dates and times are clocks
            out.append((path, a[:120], b[:120]))
    elif a != b:
        out.append((path, str(a)[:120], str(b)[:120]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--email", default=os.getenv("CRM_OWNER_EMAIL", "admin@xeducation.in"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    password = os.getenv("CRM_PASSWORD") or getpass.getpass(f"CRM password of {args.email}: ")
    api = f"http://127.0.0.1:{args.port}/api/v1"
    work = Path(tempfile.mkdtemp(prefix="real-vs-simulated-"))
    try:
        db = copy_data(work / "data")
        with sqlite3.connect(db) as con:
            n = con.execute("SELECT COUNT(*) FROM users WHERE email LIKE ?", (f"%{SIM}",)).fetchone()[0]
        if not n:
            print("There are no simulated learners in this CRM, so there is nothing to compare.")
            return 0
        print(f"Copied the data to {work}; {n:,} simulated learners. Reading every page ...")
        proc = start_api(work / "data", args.port)
        try:
            before = reading(api, args.email, password)
        finally:
            proc.terminate()
            proc.wait(30)
        with sqlite3.connect(db) as con:
            con.execute("UPDATE users SET email = REPLACE(email, ?, ?) WHERE email LIKE ?", (SIM, NEW, f"%{SIM}"))
        print(f"Turned the {n:,} simulated learners into real people. Reading every page again ...")
        proc = start_api(work / "data", args.port)
        try:
            after = reading(api, args.email, password)
        finally:
            proc.terminate()
            proc.wait(30)
        if args.keep:
            (work / "before.json").write_text(json.dumps(before, default=str))
            (work / "after.json").write_text(json.dumps(after, default=str))
        failed, differences = [k for k, (s, _) in {**before, **after}.items() if s != 200], 0
        for k in before:
            out: list = []
            walk(before[k], after.get(k), "", out)
            differences += len(out)
            print(f"{'same' if not out else 'DIFFERENT'}  {k}")
            for path, x, y in out[:5]:
                print(f"      {path}: before {x!r}, after {y!r}")
        print(
            f"\n{len(before)} pages and answers compared: {differences} differences besides the real/simulated split"
            + (f"; not answered: {', '.join(sorted(set(failed)))}" if failed else "")
        )
        return 1 if differences or failed else 0
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
