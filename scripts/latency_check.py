"""
Measures how fast the real-time loop answers on a running backend: a website event until the learner's new score
comes back (POST /api/v1/track, timed in this script and inside the server), over many events of one test learner.
The learner uses the reserved .test domain (never emailed) and is deleted at the end with everything linked to it.

    backend/.venv/bin/python scripts/latency_check.py [--events 300] [--api URL] [--db PATH] [--email ADMIN]

The CRM password (for the server-side timings on the Learning loop page) is asked for, or read from CRM_PASSWORD.
Prints the median, the 95th percentile and the maximum, in milliseconds.
"""

from __future__ import annotations

import argparse
import getpass
import os
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_test import ROOT, Client, code_from_inbox  # noqa: E402

EVENTS = ["page_view", "page_view", "page_view", "video_play", "pricing_view", "brochure_dl", "testimonial_view"]


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--api", default=os.getenv("API_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--email", default=os.getenv("CRM_OWNER_EMAIL", "admin@xeducation.in"))
    ap.add_argument("--events", type=int, default=300)
    default_db = Path(os.getenv("DATA_DIR") or ROOT / "backend" / "data") / "xeducation.db"
    ap.add_argument("--db", type=Path, default=default_db)
    args = ap.parse_args()
    api = Client(args.api)
    password = os.getenv("CRM_PASSWORD") or getpass.getpass(f"CRM password of {args.email}: ")
    code, r = api.call("POST", "/api/v1/crm/auth/login", {"email": args.email, "password": password})
    if code != 200:
        print("Could not sign in to the CRM with that email address and password.")
        return 1
    crm = r["token"]

    email = f"latency.{int(time.time())}@checks.xeducation.test"
    api.call("POST", "/api/v1/auth/signup", {"name": "Latency Check", "email": email, "password": "Latency-2026"})
    _, r = api.call("POST", "/api/v1/auth/verify-otp", {"email": email, "otp": code_from_inbox(args.db, email)})
    learner = r["token"]
    _, courses = api.call("GET", "/api/v1/courses")
    slugs = [c["slug"] for c in courses["courses"]]
    _, s = api.call("POST", "/api/v1/session/start", {"device_type": "Desktop"}, token=learner)

    rng = random.Random(7)
    timings = []
    print(f"\nSending {args.events} website events ...")
    for _ in range(args.events):
        body = {
            "session_id": s["session_id"],
            "course_slug": rng.choice(slugs),
            "event_type": rng.choice(EVENTS),
            "time_spent_sec": rng.randint(5, 240),
        }
        started = time.perf_counter()
        code, _ = api.call("POST", "/api/v1/track", body, token=learner, quiet=True)
        if code == 200:
            timings.append((time.perf_counter() - started) * 1000)
    _, server = api.call("GET", "/api/v1/crm/latency", token=crm)
    api.call("DELETE", "/api/v1/me", token=learner)

    if not timings:
        print("No event was answered.")
        return 1
    print(f"\nEvent to new score, {len(timings)} events, over HTTP on this computer:")
    print(
        f"  median {statistics.median(timings):.0f} ms, 95th percentile {quantile(timings, 0.95):.0f} ms, "
        f"max {max(timings):.0f} ms"
    )
    inside = (server or {}).get("event_to_score")
    if inside:
        print(
            f"Inside the server (scoring only, last {inside['count']} events of any learner): "
            f"median {inside['median_ms']:.0f} ms, 95th percentile {inside['p95_ms']:.0f} ms"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
