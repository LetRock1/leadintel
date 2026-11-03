"""
Checks a running X Education backend end to end over HTTP, the way the website and the CRM use it: every CRM page's
data, a learner's whole journey (sign-up with the emailed code, profile, a visit, wishlist, cart, enquiry, chat,
callback, question, purchase, review), the team answering the callback and the question, and finally the learner
deleting their account. Prints one line per request and exits with 1 if any request failed.

    backend/.venv/bin/python scripts/smoke_test.py                   macOS, Linux
    backend\\.venv\\Scripts\\python scripts\\smoke_test.py             Windows

Options: --api URL (default http://127.0.0.1:8000), --email (a CRM admin; default CRM_OWNER_EMAIL or
admin@xeducation.in), --db PATH (the backend's database, to read the test learner's code from its inbox).
The CRM password is asked for (or read from the CRM_PASSWORD environment variable) and never printed.

The test learner uses the reserved .test domain: it is never emailed (its code waits in the database's
simulated_inbox table) and it is deleted at the end, with everything linked to it.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRM_READS = [
    "/me",
    "/stats",
    "/stats/daily?days=30",
    "/forecast",
    "/priority-queue",
    "/model/health",
    "/nba/performance",
    "/campaign-influence",
    "/capacity",
    "/leads?limit=5",
    "/leads?tier=Customers&limit=5",
    "/leads?segment=real&limit=5",
    "/actions",
    "/callbacks",
    "/coupons",
    "/whatsapp/log",
    "/campaigns",
    "/ab-tests",
    "/ab-tests/plan",
    "/adoptions",
    "/learning/overview",
    "/latency",
    "/journeys",
    "/pipeline",
    "/pipeline?sort=score",
    "/money",
    "/planner",
    "/start",
    "/copilot",
    "/qna",
    "/team",
    "/team/performance",
    "/audit?limit=20",
    "/simulation",
]
QUESTIONS = [
    "How many leads came in this week?",
    "Who should we call today?",
    "Which leads are most likely to buy?",
    "What is a call slot worth today?",
    "Is the CRM actually making a difference?",
    "What is the pipeline worth?",
    "Should we hire another counsellor?",
]


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.failures: list[str] = []

    def call(self, method, path, body=None, token=None, expect=(200,), quiet=False):
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("POST", "PUT") else None)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                code, raw, kind = r.status, r.read().decode(), r.headers.get("content-type", "")
        except urllib.error.HTTPError as e:
            code, raw, kind = e.code, e.read().decode(), e.headers.get("content-type", "")
        except urllib.error.URLError as e:
            sys.exit(f"The API at {self.base} does not answer ({e.reason}). Start it first (start-all).")
        out = json.loads(raw) if raw and kind.startswith("application/json") else raw
        ok = code in expect
        if not quiet or not ok:
            print(f"{'ok  ' if ok else 'FAIL'} {code} {method} {path.split('?')[0]}")
        if not ok:
            self.failures.append(f"{method} {path}: {code} {str(out)[:200]}")
        return code, out


def code_from_inbox(db_path: Path, email: str, attempts: int = 20) -> str:
    for _ in range(attempts):
        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                "SELECT subject FROM simulated_inbox WHERE email=? ORDER BY id DESC LIMIT 1", (email,)
            ).fetchone()
        finally:
            con.close()
        found = re.search(r"code: (\d{6})", row[0]) if row else None
        if found:
            return found.group(1)
        time.sleep(0.5)
    return "000000"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--api", default=os.getenv("API_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--email", default=os.getenv("CRM_OWNER_EMAIL", "admin@xeducation.in"))
    default_db = Path(os.getenv("DATA_DIR") or ROOT / "backend" / "data") / "xeducation.db"
    ap.add_argument("--db", type=Path, default=default_db)
    args = ap.parse_args()
    api = Client(args.api)
    if api.call("GET", "/api/health")[0] != 200:
        return 1
    password = os.getenv("CRM_PASSWORD") or getpass.getpass(f"CRM password of {args.email}: ")

    code, r = api.call("POST", "/api/v1/crm/auth/login", {"email": args.email, "password": password})
    if code != 200:
        print("Could not sign in to the CRM with that email address and password.")
        return 1
    if r["member"].get("must_change_password"):
        print("This account still has its first password: sign in to the CRM once and choose your own.")
        return 1
    crm = r["token"]
    for path in CRM_READS:
        api.call("GET", "/api/v1/crm" + path, token=crm)
    for question in QUESTIONS:
        api.call("POST", "/api/v1/crm/copilot", {"question": question}, token=crm)

    # a learner's journey
    email = f"smoke.{int(time.time())}@checks.xeducation.test"
    password_l = f"Smoke-{int(time.time())}"
    api.call("POST", "/api/v1/auth/signup", {"name": "Smoke Tester", "email": email, "password": password_l})
    code, r = api.call("POST", "/api/v1/auth/verify-otp", {"email": email, "otp": code_from_inbox(args.db, email)})
    if code != 200:
        print("The test learner could not be verified; is --db the backend's database?")
        return 1
    learner = r["token"]
    _, courses = api.call("GET", "/api/v1/courses")
    slug = courses["courses"][0]["slug"]
    api.call("GET", f"/api/v1/courses/{slug}")
    api.call("GET", "/api/v1/faq")
    api.call("GET", "/api/v1/profile/options")
    profile = {
        "current_occupation": "Working Professional",
        "specialization": "Finance Management",
        "city": "Pune",
        "phone": "+91 98765 43210",
    }
    api.call("POST", "/api/v1/profile/complete", profile, token=learner)
    _, s = api.call("POST", "/api/v1/session/start", {"device_type": "Desktop", "lead_source": "Google"}, token=learner)
    for event, seconds in (("page_view", 120), ("pricing_view", 40), ("video_play", 200)):
        body = {"session_id": s["session_id"], "course_slug": slug, "event_type": event, "time_spent_sec": seconds}
        api.call("POST", "/api/v1/track", body, token=learner)
    api.call("POST", "/api/v1/session/ping", {"session_id": s["session_id"]}, token=learner)
    for path in ("/live-score", "/me/insights", "/recommendations", "/dashboard"):
        api.call("GET", "/api/v1" + path, token=learner)
    api.call("POST", "/api/v1/wishlist", {"course_slug": slug}, token=learner)
    api.call("POST", "/api/v1/cart", {"course_slug": slug}, token=learner)
    api.call("POST", "/api/v1/checkout/start", token=learner)
    api.call("POST", "/api/v1/coupons/check", {"code": "NOT-A-CODE"}, token=learner, expect=(400,))
    api.call("POST", "/api/v1/enquiry", {"course_slug": slug, "phone": "+91 98765 43210"}, token=learner)
    api.call("POST", "/api/v1/chat", {"message": "What are the fees?", "course_slug": slug}, token=learner)
    callback = {"phone": "+91 98765 43210", "preferred_time": "Evening", "course_slug": slug}
    api.call("POST", "/api/v1/callback", callback, token=learner)
    question = f"Is there a weekend batch? ({email})"
    api.call("POST", "/api/v1/qna", {"course_slug": slug, "question": question}, token=learner)

    # the team sees them and answers
    _, found = api.call("GET", f"/api/v1/crm/leads?search={email}", token=crm)
    if found.get("leads"):
        lead_id = found["leads"][0]["id"]
        for part in ("", "/now", "/attribution", "/explain", "/paths"):
            api.call("GET", f"/api/v1/crm/leads/{lead_id}{part}", token=crm)
        # the coupon guard, and taking a step by hand (refused only for the control group)
        uid = found["leads"][0]["user_id"]
        api.call("GET", f"/api/v1/crm/coupons/check?user_id={uid}&discount_pct=10", token=crm)
        api.call("POST", f"/api/v1/crm/leads/{lead_id}/act", {"action": "email_info"}, token=crm, expect=(200, 409))
    _, callbacks = api.call("GET", "/api/v1/crm/callbacks", token=crm)
    for c in callbacks.get("callbacks", []):
        if c.get("email") == email:
            api.call("POST", f"/api/v1/crm/callbacks/{c['id']}/done", {"note": "Smoke test"}, token=crm)
    _, questions = api.call("GET", "/api/v1/crm/qna", token=crm)
    for q in questions.get("questions", []):
        if q.get("question") == question:
            api.call("POST", "/api/v1/crm/qna/answer", {"qna_id": q["id"], "answer": "Yes, on Saturdays."}, token=crm)

    # they buy, review, and delete their account
    api.call("POST", "/api/v1/checkout", {"coupon_code": ""}, token=learner)
    api.call("GET", "/api/v1/purchases", token=learner)
    api.call("POST", "/api/v1/reviews", {"course_slug": slug, "rating": 5, "review_text": "Clear."}, token=learner)
    api.call("DELETE", "/api/v1/me", token=learner)
    api.call("GET", "/api/v1/auth/me", token=learner, expect=(401,))

    print(f"\n{len(api.failures)} failed request(s)" if api.failures else "\nEvery request answered as expected.")
    for f in api.failures:
        print("  " + f)
    return 1 if api.failures else 0


if __name__ == "__main__":
    sys.exit(main())
