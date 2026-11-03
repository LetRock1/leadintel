"""
The simulated learners keep living, in real time.

The starting history (app.simulation.history) gives the CRM six months of simulated learners. This module keeps those
same people, and new ones who sign up every day, using the website while the backend runs, so the CRM always has live
work: it scores them, decides, sends emails and coupons, creates call tasks, and learns from who buys. They are part
of the CRM's one pool of learners, next to the real people who sign up on the website.

How they reach the CRM: through the website's own API over HTTP (http://127.0.0.1:8000/api/v1/...), with exactly the
requests a browser sends: start a visit, report each page and its seconds (and a "still here" every 30 s while
reading), video, pricing, brochure, chat, webinar, add to wishlist or cart, start checkout, send an enquiry, open the
course from the button in an email, pay with their best coupon, sign up with the code from their inbox. Nothing in the
CRM is written by this module directly, and the CRM's decisions have no special code for them: the only thing that
marks them is their address (on the reserved, never emailed domain demo.xeducation.test), shown as a "simulated" tag.

What the simulator decides (the same documented behaviour as the six-month history):
  who they are     profile, hidden intent and luck (app.simulation.population), and how much each CRM step changes
                   each person's chance to buy (app.simulation.effects, plus a personal deviation). The history's
                   learners are re-created exactly from the history's seed.
  coming back      chance per day sig(-2.6 + 0.7 intent - 0.05 days away + boost), only within 21 days of the last
                   visit. A call that reached them adds 0.5 for two days, a WhatsApp 0.3; a click on an email brings
                   them back a minute later.
  on the website   pages (1 + Poisson), seconds per page (log-normal) and every first-time step with its documented
                   chance (app.simulation.behaviour.EVENTS).
  emails          only the emails the CRM really sent them: clicked with chance sig(-1.7 + 0.6 intent, +0.4 with a
                   coupon), 12 minutes to 30 hours after sending.
  buying           the documented buying formula on everything they have done so far, plus the strongest effect of a
                   CRM step in the outcome window, spread evenly over the days (daily chance 1 - (1 - p14)^(1/14)),
                   only while they visited within the window. They come back, put the course in the cart and pay with
                   their best valid coupon.
  the phone        only the learners are simulated: their call and WhatsApp tasks are done by the real team in Today's
                   actions, like everyone's. Their numbers are not real, so when someone presses Call, the learner
                   answers or not as the simulator decides (World.phone_call: answered 60%, no answer 30%, not
                   interested 10%, as in the history; a WhatsApp message is delivered). The outcome is saved under that
                   person's name, and a call that reached them changes their chance to buy exactly as in the history.
  new sign-ups     about 13 a day (the history's recent rate): sign-up, emailed code, profile, visit.

Real time: a second here is a second for the CRM. While the backend is off nobody can use the website, so nothing
happens then: a visit or click that fell into that time is dropped, not replayed later. The hidden traits and the
simulator's to-do list live in its own database (backend/data/simulation_world.db), never in the CRM's database.

The backend's scheduler calls tick() every few seconds; crm_settings.json "live_simulation" switches it on or off, and
the dashboard can pause it or send a learner to the website now. From a terminal: python -m app.cli simulation status
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import threading
import time as _time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, time, timedelta

import numpy as np

from app import db
from app.core import rules, security
from app.core.config import get_settings
from app.ml import features as F
from app.ml import nba_core as N
from app.services import catalog
from app.simulation import behaviour as B
from app.simulation import effects as S
from app.simulation import population as G

TS = "%Y-%m-%d %H:%M:%S"
DOMAIN = B.DEMO_DOMAIN
LIKE = f"%@{DOMAIN}"
HISTORY_SEED = 2026  # the seed the starting history uses (its --seed default)
LIVE_SEED = HISTORY_SEED + 1_000_000  # new sign-ups: learner number k is drawn with seed LIVE_SEED + k
LATE = timedelta(minutes=15)  # a step this late fell into a time the website was off: dropped
ROLL_EVERY = timedelta(seconds=60)  # how often the dice for visits, purchases and sign-ups are rolled
WORLD_PATH = str(get_settings().simulation_db)
API_URL = get_settings().api_url.rstrip("/") + "/api/v1"
CHAT_QUESTIONS = [
    "What are the fees?",
    "How long is it?",
    "What will I learn in this course?",
    "Is there an EMI option?",
    "Do I get a certificate?",
    "Is there placement support?",
    "Which course suits me?",
]  # all answered from the course facts (no AI service needed)
DEFAULTS = {"enabled": True, "new_signups_per_day": 13, "tick_seconds": 10}
STEP_TEXT = {
    "video": "watched the overview video",
    "pricing": "read the pricing",
    "testimonial": "read testimonials",
    "brochure": "downloaded the brochure",
    "chat": "asked the chat assistant",
    "webinar": "booked a webinar seat",
    "wishlist": "wishlisted {course}",
    "cart": "put {course} in the cart",
    "checkout": "started checkout",
    "enquiry": "sent an enquiry",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    user_id     INTEGER PRIMARY KEY,     -- users.id in the CRM
    email       TEXT UNIQUE,
    name        TEXT,
    k           INTEGER,                 -- learner number: below the history's size = a history learner
    joined      TEXT,                    -- 'history' | 'live' (signed up while the servers ran)
    intent      REAL,                    -- hidden: how much they want a course (never shown to the CRM)
    luck        REAL,                    -- hidden: timing, budget, mood
    noise_json  TEXT,                    -- hidden: how this person reacts to each CRM step
    slug        TEXT,                    -- the course they are interested in
    device      TEXT, source TEXT, occ TEXT,
    dne INTEGER, dnc INTEGER, wa INTEGER, phone TEXT,
    boost       REAL DEFAULT 0,          -- after a call / WhatsApp that reached them
    boost_until TEXT,
    busy_until  TEXT,                    -- a visit is in progress until then
    session_id  INTEGER,                 -- the website session of the current visit
    bought      INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS effects (       -- each CRM step that reached someone, with its true effect
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, ref TEXT UNIQUE, kind TEXT, effect REAL,
    starts_at TEXT, until TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_effects_user ON effects(user_id, until);
CREATE TABLE IF NOT EXISTS tasks (         -- call / WhatsApp tasks of simulated learners (done by the team)
    task_id INTEGER PRIMARY KEY, user_id INTEGER, due_at TEXT, handled INTEGER DEFAULT 0,
    outcome TEXT, done_by TEXT
);
CREATE TABLE IF NOT EXISTS queue (         -- what each learner will do next, and when
    id INTEGER PRIMARY KEY AUTOINCREMENT, due_at TEXT, user_id INTEGER, visit TEXT, kind TEXT, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_queue_due ON queue(due_at);
CREATE TABLE IF NOT EXISTS log (           -- the simulated people's diary (shown on the dashboard)
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, user_id INTEGER, kind TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_log_at ON log(at);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def conf():
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (rules.S.get("live_simulation") or {}).items() if not str(k).startswith("_")})
    return c


def ts(t):
    return t.strftime(TS)


def parse(s):
    return datetime.strptime(str(s)[:19], TS)


def sig(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


class Offline(Exception):
    """The website's API did not answer (the backend is starting, stopping or down)."""


class Paused(Exception):
    pass


# the website's API, called the way a browser calls it
class HttpApi:
    def __init__(self, base=API_URL, timeout=30):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 127.0.0.1: never via a proxy

    def call(self, method, path, body=None, token=None):
        headers = {"Content-Type": "application/json", "User-Agent": "xeducation-simulated-learner/7"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("POST", "PUT") else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                raw = r.read().decode() or "null"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode() or "null")
            except ValueError:
                detail = None
            return e.code, detail
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise Offline(str(e)) from e


# who the simulated learners are
_cache = {}


def course_slugs():
    if "slugs" not in _cache:
        _cache["slugs"] = B.course_slugs()
    return _cache["slugs"]


def history_size():
    hist = rules.S.get("starting_history") or {}
    return int(hist.get("learners", 2000)), int(hist.get("days", 180))


def history_traits():
    """The history's learners exactly as the starting history made them (same seed, same draws, same order)."""
    if "history" not in _cache:
        n, days = history_size()
        by_type, all_slugs = course_slugs()
        rng = np.random.default_rng(HISTORY_SEED)
        out = B.learner_traits(n, days, HISTORY_SEED, rng, by_type, all_slugs)
        _cache["history"] = {t["email"]: t for t in out}
    return _cache["history"]


def new_traits(k):
    """Learner number k (k >= the history's size): a new person who signs up while the CRM runs. Drawn by the
    same generator as the history's learners, with their own seed (LIVE_SEED + k)."""
    by_type, all_slugs = course_slugs()
    rng = np.random.default_rng(LIVE_SEED + int(k))
    r = G.generate(1, seed=int(rng.integers(2**31 - 1)), return_truth=True).to_dict("records")[0]
    first, last = str(rng.choice(B.FIRST)), str(rng.choice(B.LAST))
    slug = str(rng.choice(by_type.get(r["CourseType"]) or all_slugs))
    luck = float(rng.normal(0, 0.45))
    noise = {a: float(rng.normal(0, S.EFFECT_NOISE_SD)) for a in N.ACTION_LIST}
    phone = f"+91 00000 {int(k) + 1:05d}" if rng.random() < 0.85 else None
    return {
        "i": int(k),
        "name": f"{first} {last}",
        "email": f"{first}.{last}.{int(k) + 1}@{DOMAIN}".lower(),
        "occ": r["CurrentOccupation"],
        "spec": r["Specialization"],
        "intent": float(r["_intent"]),
        "luck": luck,
        "dne": int(r["DoNotEmail"]),
        "dnc": int(r["DoNotCall"]),
        "wa": int(r["WhatsAppOptIn"]),
        "device": r["DeviceType"],
        "source": r["LeadSource"],
        "slug": slug,
        "noise": noise,
        "phone": phone,
        "raw": r,
    }


def context_of(features):
    """nba_core.context() for one person at base probability 0.5 (as the history's effect_of uses it), without
    building a pandas frame: the same cleaning (features.normalize_raw), the same nine values. A test checks
    it equals nba_core.context(features.to_model_frame([features]), [0.5]) exactly."""
    f = F.normalize_raw(features)
    occ = str(f["CurrentOccupation"])
    cart, checkout, enquiry = f["AddedToCart"] == 1, f["CheckoutStarted"] == 1, f["EnquirySubmitted"] == 1
    return np.array(
        [
            1.0,
            0.0,
            float(occ in N.PRICE_SENSITIVE_OCC or (cart and not checkout)),
            float(checkout),
            float(cart or enquiry),
            float(occ in N.PROFESSIONAL_OCC),
            float(f["EmailOpenedCount"] > 0),
            float(f["WhatsAppOptIn"] == 1),
            float(f["TotalTimeOnWebsite"] < 120),
        ]
    )


def number_of(email):
    m = re.search(r"\.(\d+)@", email or "")
    return int(m.group(1)) - 1 if m else None


def traits_for(email):
    """(traits, k, joined) for a simulated learner already in the CRM."""
    k = number_of(email)
    hist = history_traits()
    if email in hist:
        return hist[email], k, "history"
    n, _ = history_size()
    if k is not None and k >= n:
        tr = new_traits(k)
        if tr["email"] == email:
            return tr, k, "live"
    # someone this simulator cannot re-create exactly (made with another seed): new hidden traits, same address
    seed_k = 10**7 + int(hashlib.sha256(email.encode()).hexdigest()[:8], 16)
    tr = dict(new_traits(seed_k), email=email)
    return tr, k, "other"


# the world
class World:
    def __init__(self, api=None, path=None, rng=None, clock=None):
        self.api = api or HttpApi()
        self.path = path or WORLD_PATH
        self.rng = rng or np.random.default_rng()
        self.clock = clock or datetime.now
        self.lock = threading.RLock()
        self._busy = threading.Lock()  # one tick at a time
        self._tokens = {}
        self._con = None
        self._last_sync = None
        self.last_error = None
        self.window = int(rules.S.get("outcome_window_days", 14))
        self._pref = None  # rows read in bulk at the first start (catch_up)

    # storage
    def con(self):
        if self._con is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            self._con = c
        return self._con

    def q(self, sql, params=()):
        return [dict(r) for r in self.con().execute(sql, params).fetchall()]

    def q1(self, sql, params=()):
        r = self.con().execute(sql, params).fetchone()
        return dict(r) if r else None

    def x(self, sql, params=()):
        return self.con().execute(sql, params).lastrowid

    @contextlib.contextmanager
    def tx(self):
        """Many small writes in one transaction (thousands of rows at the first start)."""
        c = self.con()
        if c.in_transaction:
            yield
            return
        c.execute("BEGIN")
        try:
            yield
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def meta(self, key, default=None):
        r = self.q1("SELECT value FROM meta WHERE key=?", (key,))
        return r["value"] if r else default

    def set_meta(self, key, value):
        self.x(
            "INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, None if value is None else str(value)),
        )

    def learner(self, user_id):
        L = self.q1("SELECT * FROM learners WHERE user_id=?", (user_id,))
        if L:
            L["noise"] = json.loads(L["noise_json"] or "{}")
        return L

    def log(self, at, L, kind, text):
        self.x(
            "INSERT INTO log (at, user_id, kind, text) VALUES (?,?,?,?)",
            (ts(at), L["user_id"] if L else None, kind, (f"{L['name']} " if L else "") + text),
        )

    def enqueue(self, due, user_id, kind, payload=None, visit=None):
        self.x(
            "INSERT INTO queue (due_at, user_id, visit, kind, payload) VALUES (?,?,?,?,?)",
            (ts(due), user_id, visit, kind, json.dumps(payload or {})),
        )

    # switch
    @staticmethod
    def switched_off_by_settings() -> bool:
        """SIMULATION_ENABLED=false in backend/.env keeps them off whatever the dashboard says."""
        return get_settings().simulation_enabled is False

    def enabled(self):
        if self.switched_off_by_settings():
            return False
        v = self.meta("enabled")
        return bool(conf()["enabled"]) if v is None else v == "1"

    def set_enabled(self, on):
        if on and self.switched_off_by_settings():
            raise Paused(
                "The simulated learners are switched off in backend/.env (SIMULATION_ENABLED=false). Remove that "
                "line and restart to use them."
            )
        with self.lock:
            self.set_meta("enabled", "1" if on else "0")
            self.log(self.clock(), None, "info", "Simulated learners resumed." if on else "Simulated learners paused.")
        return self.status()

    # 1. keep the list of people in step with the CRM
    def sync(self, now):
        """Every verified simulated learner in the CRM has a row here (hidden traits); people removed from the
        CRM are forgotten. The first time (or after the history was re-made) the effects of the last 14 days and
        the open call tasks are picked up, so nothing the CRM did recently is lost."""
        with self.tx():
            self._sync(now)
        self._last_sync = now

    def _sync(self, now):
        crm = {
            r["id"]: r
            for r in db.fetchall(
                "SELECT id, email, name, created_at FROM users WHERE email LIKE ? " "AND is_verified=1", (LIKE,)
            )
        }
        known = {r["user_id"]: r["email"] for r in self.q("SELECT user_id, email FROM learners")}
        gone = [u for u, e in known.items() if u not in crm or crm[u]["email"] != e]
        for u in gone:
            for t in ("learners", "effects", "tasks", "queue"):
                self.x(f"DELETE FROM {t} WHERE user_id=?", (u,))
        missing = [r for u, r in crm.items() if u not in known or u in gone]
        for r in missing:
            tr, k, joined = traits_for(r["email"])
            self.x(
                """INSERT OR REPLACE INTO learners (user_id, email, name, k, joined, intent, luck, noise_json, slug,
                   device, source, occ, dne, dnc, wa, phone, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    r["id"],
                    r["email"],
                    r["name"],
                    k,
                    joined,
                    tr["intent"],
                    tr["luck"],
                    json.dumps(tr["noise"]),
                    tr["slug"],
                    tr["device"],
                    tr["source"],
                    tr["occ"],
                    tr["dne"],
                    tr["dnc"],
                    tr["wa"],
                    tr["phone"],
                    r["created_at"],
                ),
            )
        bought = {
            r["user_id"]
            for r in db.fetchall(
                "SELECT DISTINCT p.user_id FROM purchases p JOIN users u " "ON u.id=p.user_id WHERE u.email LIKE ?",
                (LIKE,),
            )
        }
        if bought:
            self.x(f"UPDATE learners SET bought=1 WHERE user_id IN ({','.join(str(int(u)) for u in bought)})")
        if self.meta("started_at") is None or len(missing) > 100:
            self.catch_up(now)
            if self.meta("started_at") is None:
                self.set_meta("started_at", ts(now))
                self.log(
                    now,
                    None,
                    "info",
                    f"Simulated learners started: {len(crm):,} people " f"({len(bought):,} of them customers).",
                )
        if self.meta("next_k") is None:
            ks = [number_of(r["email"]) for r in crm.values()]
            self.set_meta("next_k", max([k for k in ks if k is not None] + [history_size()[0] - 1]) + 1)

    def catch_up(self, now):
        """Read what it needs from the CRM in a few queries (not three per email), then pick up the recent past."""
        since = ts(now - timedelta(days=self.window))
        self._pref = {
            "dec": {
                r["lead_id"]: r
                for r in db.fetchall(
                    """SELECT d.lead_id, d.action, d.features_json FROM nba_decisions d JOIN users u ON u.id=d.user_id
                   WHERE u.email LIKE ? AND d.created_at >= ? ORDER BY d.id""",
                    (LIKE, ts(now - timedelta(days=self.window + 1))),
                )
            },
            "feat": {
                r["user_id"]: r["features_json"]
                for r in db.fetchall(
                    """SELECT s.user_id, s.features_json FROM score_snapshots s WHERE s.id IN
                   (SELECT MAX(s2.id) FROM score_snapshots s2 JOIN users u ON u.id=s2.user_id
                    WHERE u.email LIKE ? GROUP BY s2.user_id)""",
                    (LIKE,),
                )
            },
            "learner": {L["user_id"]: L for L in self.q("SELECT * FROM learners")},
            # what the CRM knew about each person when a campaign / A/B test picked them (see email_arrived)
            "assign": {
                (r["experiment_type"], r["experiment_id"], r["user_id"]): r["features_json"]
                for r in db.fetchall(
                    """SELECT x.experiment_type, x.experiment_id, x.user_id, x.features_json
                       FROM experiment_assignments x JOIN users u ON u.id=x.user_id
                       WHERE u.email LIKE ? AND x.experiment_type IN ('campaign', 'ab') AND x.assigned_at >= ?""",
                    (LIKE, ts(now - timedelta(days=self.window + 1))),
                )
            },
        }
        for L in self._pref["learner"].values():
            L["noise"] = json.loads(L["noise_json"] or "{}")
        try:
            self._catch_up(now, since)
        finally:
            self._pref = None

    def _catch_up(self, now, since):
        for e in db.fetchall(
            """SELECT e.* FROM email_sends e JOIN users u ON u.id=e.user_id
                                WHERE u.email LIKE ? AND e.sent_at >= ? ORDER BY e.id""",
            (LIKE, since),
        ):
            L = self._pref["learner"].get(e["user_id"])
            if L and not L["bought"]:
                self.email_arrived(L, e, now, click=False)
        for t in db.fetchall(
            """SELECT t.* FROM sales_tasks t JOIN users u ON u.id=t.user_id
                                WHERE u.email LIKE ? AND (t.status='open' OR t.done_at >= ?)""",
            (LIKE, since),
        ):
            L = self._pref["learner"].get(t["user_id"])
            if not L:
                continue
            if t["status"] == "open":
                self.track_task(t)
            else:
                self.x(
                    "INSERT OR IGNORE INTO tasks (task_id, user_id, due_at, handled, outcome, done_by) "
                    "VALUES (?,?,?,1,?,?)",
                    (t["id"], t["user_id"], t["done_at"], t["outcome"], t.get("done_by")),
                )
                self.task_outcome(L, t)
        self.set_meta("email_wm", (db.fetchone("SELECT COALESCE(MAX(id),0) AS m FROM email_sends") or {}).get("m", 0))
        self.set_meta("task_wm", (db.fetchone("SELECT COALESCE(MAX(id),0) AS m FROM sales_tasks") or {}).get("m", 0))

    # 2. what they have done so far (the CRM's own tracking tables)
    def behaviour(self, user_ids=None, until=None):
        """Per simulated learner: visits, seconds on the site, every first-time step, email clicks, last seen,
        as known at `until` (default: everything so far)."""
        only = ""
        params = [LIKE]
        if user_ids is not None:
            ids = [int(u) for u in user_ids] or [-1]
            only = f" AND u.id IN ({','.join(map(str, ids))})"
        cut = ts(until) if until is not None else "9999-12-31 23:59:59"
        rows = db.fetchall(
            f"""
            SELECT e.user_id,
                   COUNT(DISTINCT CASE WHEN e.event_type='page_view' THEN e.session_id END) AS visits,
                   COALESCE(SUM(CASE WHEN e.event_type='page_view' THEN e.time_spent_sec END), 0) AS secs,
                   MAX(e.event_type='video_play') AS video, MAX(e.event_type='pricing_view') AS pricing,
                   MAX(e.event_type='testimonial_view') AS testimonial, MAX(e.event_type='brochure_dl') AS brochure,
                   MAX(e.event_type='chat') AS chat, MAX(e.event_type='webinar_register') AS webinar,
                   MAX(e.event_type='wishlist_add') AS wishlist, MAX(e.event_type='cart_add') AS cart,
                   MAX(e.event_type='checkout_start') AS checkout, MAX(e.event_type='enquiry_submit') AS enquiry,
                   MAX(e.created_at) AS last_event
            FROM behaviour_events e JOIN users u ON u.id = e.user_id
            WHERE u.email LIKE ?{only} AND e.created_at <= ? GROUP BY e.user_id""",
            tuple(params + [cut]),
        )
        out = {r["user_id"]: dict(r) for r in rows}
        for r in db.fetchall(
            f"""SELECT s.user_id, MAX(MIN(COALESCE(s.last_active, s.login_at), ?)) AS seen
                                 FROM user_sessions s JOIN users u ON u.id=s.user_id
                                 WHERE u.email LIKE ?{only} AND s.login_at <= ? GROUP BY s.user_id""",
            tuple([cut] + params + [cut]),
        ):
            d = out.setdefault(r["user_id"], {"user_id": r["user_id"], "visits": 0, "secs": 0})
            d["seen"] = r["seen"]
        for r in db.fetchall(
            f"""SELECT m.user_id, COALESCE(SUM(m.click_count),0) AS clicks
                                 FROM email_sends m JOIN users u ON u.id=m.user_id
                                 WHERE u.email LIKE ?{only} AND m.first_clicked_at <= ? GROUP BY m.user_id""",
            tuple(params + [cut]),
        ):
            out.setdefault(r["user_id"], {"user_id": r["user_id"], "visits": 0, "secs": 0})["clicks"] = r["clicks"]
        for d in out.values():
            seen = [x for x in (d.get("seen"), d.get("last_event")) if x]
            d["last_seen"] = max(seen) if seen else None
            for f, *_ in B.EVENTS:
                d[f] = int(d.get(f) or 0)
            d["checkout"] = int(d.get("checkout") or 0)
            d["clicks"] = int(d.get("clicks") or 0)
            d["visits"] = int(d.get("visits") or 0)
            d["secs"] = int(d.get("secs") or 0)
        return out

    # 3. the true effect of a CRM step on one person
    def effect_of(self, L, action, features=None):
        """effects.TRUE_EFFECTS at the person's situation plus their own deviation, exactly as in the history
        (app.simulation.history.History.effect_of)."""
        if not features:
            if self._pref is not None:
                raw = self._pref["feat"].get(L["user_id"])
            else:
                row = db.fetchone(
                    "SELECT features_json FROM score_snapshots WHERE user_id=? ORDER BY id DESC LIMIT 1",
                    (L["user_id"],),
                )
                raw = row["features_json"] if row else None
            features = json.loads(raw) if raw else None
        if features:
            ctx = context_of(features)
        else:  # nothing scored yet: the same context from what they did
            b = self.behaviour([L["user_id"]]).get(L["user_id"], {})
            occ = L["occ"]
            ctx = np.array(
                [
                    1.0,
                    0.0,
                    float(occ in N.PRICE_SENSITIVE_OCC or (b.get("cart") and not b.get("checkout"))),
                    float(b.get("checkout", 0)),
                    float(b.get("cart", 0) or b.get("enquiry", 0)),
                    float(occ in N.PROFESSIONAL_OCC),
                    float(b.get("clicks", 0) > 0),
                    float(L["wa"]),
                    float(b.get("secs", 0) < 120),
                ]
            )
        return float(ctx @ np.asarray(S.TRUE_EFFECTS[action])) + float(L["noise"].get(action, 0.0))

    def add_effect(self, L, ref, kind, effect, start):
        self.x(
            "INSERT OR IGNORE INTO effects (user_id, ref, kind, effect, starts_at, until) VALUES (?,?,?,?,?,?)",
            (L["user_id"], ref, kind, float(effect), ts(start), ts(start + timedelta(days=self.window))),
        )

    def adopted_shift(self, adoption_id, arm, L):
        """An adopted A/B winner (the CRM's standard email now) keeps the documented extra effect it had in the
        history's test. A test you ran live has no documented effect: the simulator gives it none."""
        if arm != "adopted" or not adoption_id:
            return 0.0, 0.0
        row = db.fetchone(
            """SELECT a.test_name, a.variant_key, t.simulated FROM adopted_emails a
                             LEFT JOIN ab_tests t ON t.id = a.ab_test_id WHERE a.id=?""",
            (adoption_id,),
        )
        if not row or not row.get("simulated"):
            return 0.0, 0.0
        test = B.history_test(row.get("test_name"))
        if not test:
            return 0.0, 0.0
        person = {"device": L["device"]}

        def val(v, key):
            x = v.get(key, 0.0)
            return float(x(person)) if callable(x) else (float(x) if isinstance(x, int | float) else 0.0)

        win = next((v for v in test["variants"] if v["key"] == row["variant_key"]), None)
        others = [v for v in test["variants"] if v is not win]
        if not win or not others:
            return 0.0, 0.0
        return (
            val(win, "click") - max(val(v, "click") for v in others),
            val(win, "buy") - max(val(v, "buy") for v in others),
        )

    def ab_variant(self, ab_test_id, key):
        """The documented variant of one of the history's A/B tests (found by the test's name); None for a test
        created live, whose true effect the simulator does not know."""
        cache = self.__dict__.setdefault("_ab", {})
        if ab_test_id not in cache:
            row = db.fetchone("SELECT name, simulated FROM ab_tests WHERE id=?", (int(ab_test_id),))
            # one of the history's tests has documented effects; a test created live has none
            cache[ab_test_id] = B.history_test(row.get("name")) if row and row.get("simulated") else None
        test = cache[ab_test_id]
        if not test:
            return None
        return next((v for v in test["variants"] if v["key"] == key), None)

    # 4. emails the CRM sent them
    def handle_emails(self, now):
        wm = int(self.meta("email_wm") or 0)
        rows = db.fetchall(
            """SELECT e.* FROM email_sends e JOIN users u ON u.id=e.user_id
                              WHERE e.id > ? AND u.email LIKE ? ORDER BY e.id LIMIT 500""",
            (wm, LIKE),
        )
        for e in rows:
            L = self.learner(e["user_id"])
            if L and not L["bought"]:
                self.email_arrived(L, e, now, click=True)
            wm = max(wm, int(e["id"]))
        if rows:
            self.set_meta("email_wm", wm)

    def assigned_features(self, L, kind, exp_id):
        """What the CRM knew about the person when a campaign or A/B test picked them: the history and the API
        both store it with the assignment. The effect of that email is worked out on it, as the history
        does (not on what the CRM knows now: the person may have done more since)."""
        if self._pref is not None:
            raw = self._pref["assign"].get((kind, exp_id, L["user_id"]))
        else:
            row = db.fetchone(
                """SELECT features_json FROM experiment_assignments WHERE experiment_type=? AND
                                 experiment_id=? AND user_id=?""",
                (kind, exp_id, L["user_id"]),
            )
            raw = row["features_json"] if row else None
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def email_arrived(self, L, e, now, click=True):
        sent = parse(e["sent_at"])
        effect, kind, click_shift = None, "email", 0.0
        dec = None
        if e.get("lead_id") and self._pref is not None:
            dec = self._pref["dec"].get(e["lead_id"])
        elif e.get("lead_id"):
            dec = db.fetchone(
                "SELECT action, features_json FROM nba_decisions WHERE lead_id=? ORDER BY id DESC LIMIT 1",
                (e["lead_id"],),
            )
        if e.get("campaign_id"):
            feats = self.assigned_features(L, "campaign", e["campaign_id"])
            kind, effect = "campaign email", 0.7 * self.effect_of(L, "email_info", feats)
        elif e.get("ab_test_id") and self.ab_variant(e["ab_test_id"], e.get("variant")):
            v = self.ab_variant(e["ab_test_id"], e.get("variant"))
            person = {"device": L["device"]}
            click, buy = v.get("click", 0.0), v.get("buy", 0.0)
            click_shift = float(click(person) if callable(click) else click)
            if buy in ("coupon10", "coupon20"):
                effect = self.effect_of(
                    L,
                    "email_coupon_10" if buy == "coupon10" else "email_coupon_20",
                    self.assigned_features(L, "ab", e["ab_test_id"]),
                )
            else:
                effect = float(buy(person) if callable(buy) else buy)
            kind = f"A/B test email ({v.get('label')})"
        elif e.get("ab_test_id"):
            pct = (
                db.fetchone(
                    """SELECT MAX(discount_pct) AS p FROM coupons_issued WHERE user_id=? AND coupon_code LIKE 'AB%'
                                  AND created_at BETWEEN ? AND ?""",
                    (L["user_id"], ts(sent - timedelta(minutes=5)), ts(sent + timedelta(minutes=5))),
                )
                or {}
            ).get("p")
            if pct:
                kind, click_shift = f"A/B email with a {int(pct)}% coupon", 0.4
                effect = self.effect_of(L, "email_coupon_10" if pct <= 10 else "email_coupon_20")
            else:
                kind, effect = "A/B test email", 0.7 * self.effect_of(L, "email_info")
        elif dec and str(dec["action"]).startswith("email"):
            feats = json.loads(dec["features_json"]) if dec.get("features_json") else None
            kind, effect = N.ACTIONS[dec["action"]]["label"].lower(), self.effect_of(L, dec["action"], feats)
            if dec["action"] in ("email_coupon_10", "email_coupon_20"):
                click_shift = 0.4
            if e.get("adoption_id"):
                c, b = self.adopted_shift(e["adoption_id"], e.get("adoption_arm"), L)
                click_shift, effect = click_shift + c, effect + b
        if effect is not None:
            self.add_effect(L, f"email:{e['token']}", kind, effect, sent)
        if click:
            p = float(sig(-1.7 + 0.6 * L["intent"] + click_shift))
            if self.rng.random() < p:
                due = sent + timedelta(hours=float(self.rng.uniform(0.2, 30)))
                self.enqueue(due, L["user_id"], "click", {"token": e["token"], "subject": e.get("subject")})

    # 5. call and WhatsApp tasks: done by the real team; the simulated learner answers the phone
    def track_task(self, t):
        self.x(
            "INSERT OR IGNORE INTO tasks (task_id, user_id, due_at) VALUES (?,?,?)",
            (t["id"], t["user_id"], t["created_at"]),
        )

    def handle_tasks(self, now):
        """Picks up new call / WhatsApp tasks of simulated learners, and applies what a task the team has done
        caused (a call that reached them, a WhatsApp that was sent). Nobody does them by themselves: an open
        task waits for the team (Today's actions, Call), or expires (team.task_expiry_days)."""
        wm = int(self.meta("task_wm") or 0)
        new = db.fetchall(
            """SELECT t.* FROM sales_tasks t JOIN users u ON u.id=t.user_id
                             WHERE t.id > ? AND u.email LIKE ? ORDER BY t.id""",
            (wm, LIKE),
        )
        for t in new:
            self.track_task(t)
            wm = max(wm, int(t["id"]))
        if new:
            self.set_meta("task_wm", wm)
        for w in self.q("SELECT * FROM tasks WHERE handled=0"):
            t = db.fetchone("SELECT * FROM sales_tasks WHERE id=?", (w["task_id"],))
            L = self.learner(w["user_id"])
            if not t or not L or t["status"] not in ("open", "done"):
                self.x("UPDATE tasks SET handled=1 WHERE task_id=?", (w["task_id"],))
                continue
            if t["status"] == "open":
                continue  # waiting for someone on the team
            self.x(
                "UPDATE tasks SET handled=1, outcome=?, done_by=? WHERE task_id=?",
                (t["outcome"], t.get("done_by"), w["task_id"]),
            )
            self.task_outcome(L, t)

    def phone_call(self, task_id, by):
        """Someone on the team (by = their name) calls a simulated learner, or sends them the WhatsApp message,
        from Today's actions. The learner is simulated, so the simulator decides how they react, with the
        documented chances (a call: answered 60 %, no answer 30 %, not interested 10 %, as in the history; a
        WhatsApp message is delivered). The outcome is saved under the team member's name, exactly like an
        outcome typed in by hand for a real person, and its effect on the learner is applied at once."""
        with self.lock:
            now = self.clock()
            t = db.fetchone(
                "SELECT t.*, u.email FROM sales_tasks t JOIN users u ON u.id=t.user_id WHERE t.id=?", (task_id,)
            )
            if not t:
                raise LookupError("Task not found.")
            if not rules.is_simulated_email(t["email"]):
                raise PermissionError("This is a real person: call them on the phone, then record what happened.")
            if t["status"] != "open":
                return {"ok": False, "outcome": t["outcome"], "message": "This task was already done."}
            if not self.enabled():
                raise Paused(
                    "The simulated learners are paused, so nobody answers: resume them first (Simulation page)."
                )
            if self._last_sync is None:
                self.sync(now)
            L = self.learner(t["user_id"])
            if not L:
                raise LookupError("The simulator does not know this learner yet; try again in a few seconds.")
            if t["task_type"] == "call":
                outcome = str(self.rng.choice(["reached", "no_answer", "not_interested"], p=[0.6, 0.3, 0.1]))
            else:
                outcome = "sent"
            db.execute(
                """UPDATE sales_tasks SET status='done', outcome=?, done_at=?, done_by=?
                          WHERE id=? AND status='open'""",
                (outcome, ts(now), str(by or "team")[:40], task_id),
            )
            if t["decision_id"] and outcome in ("reached", "sent", "not_interested"):
                db.execute(
                    "UPDATE nba_decisions SET executed_at=COALESCE(executed_at, ?) WHERE id=?",
                    (ts(now), t["decision_id"]),
                )
            done = db.fetchone("SELECT * FROM sales_tasks WHERE id=?", (task_id,))
            self.x(
                """INSERT INTO tasks (task_id, user_id, due_at, handled, outcome, done_by) VALUES (?,?,?,1,?,?)
                   ON CONFLICT(task_id) DO UPDATE SET handled=1, outcome=excluded.outcome, done_by=excluded.done_by""",
                (task_id, t["user_id"], t["created_at"], outcome, str(by or "team")[:40]),
            )
            self.task_outcome(L, done)
            said = {
                "reached": "answered the call",
                "no_answer": "did not answer the call",
                "not_interested": "answered: not interested",
                "sent": "got the WhatsApp message",
            }[outcome]
            self.log(now, L, "team", f"{said} ({by}).")
            return {
                "ok": True,
                "outcome": outcome,
                "learner": L["name"],
                "message": f"{L['name']} {said}."
                + (
                    f" A call that reaches them raises their chance to buy for " f"{self.window} days."
                    if outcome == "reached"
                    else ""
                ),
            }

    def task_outcome(self, L, t):
        """A call that reached them or a WhatsApp that was sent changes their chance to buy for 14 days and makes
        them more likely to come back for two days (documented, as in the history)."""
        if L["bought"] or t.get("outcome") not in ("reached", "sent") or not t.get("done_at"):
            return
        action = "call" if t["task_type"] == "call" else "whatsapp"
        dec = (
            db.fetchone("SELECT features_json FROM nba_decisions WHERE id=?", (t["decision_id"],))
            if t.get("decision_id")
            else None
        )
        feats = json.loads(dec["features_json"]) if dec and dec.get("features_json") else None
        done = parse(t["done_at"])
        self.add_effect(L, f"task:{t['id']}", action, self.effect_of(L, action, feats), done)
        until = datetime.combine(done.date() + timedelta(days=3), time.min)
        self.x(
            "UPDATE learners SET boost=?, boost_until=? WHERE user_id=?",
            (0.5 if action == "call" else 0.3, ts(until), L["user_id"]),
        )

    # 6. the dice: who comes back, who buys, who signs up
    def chances(self, people, now, until=None):
        """Each person's chance per day to come back and to buy at `now` (the documented rules; see the module
        docstring), from what they had done by `until` (default: everything so far). Used for the dice and by
        the checks, so both use exactly the same calculation."""
        beh = self.behaviour(until=until)
        eff = {
            r["user_id"]: r["m"]
            for r in self.q(
                "SELECT user_id, MAX(effect) AS m FROM effects WHERE starts_at <= ? " "AND until > ? GROUP BY user_id",
                (ts(now), ts(now)),
            )
        }
        uid = [int(L["user_id"]) for L in people]
        intent = np.array([L["intent"] for L in people], dtype=float)
        luck = np.array([L["luck"] for L in people], dtype=float)
        b = [beh.get(u, {}) for u in uid]
        seen = [x.get("last_seen") or L["created_at"] for x, L in zip(b, people)]
        # days since the last visit, counted in calendar days as the history does (day of the visit = 0)
        gap = np.array([float((now.date() - parse(s).date()).days) if s else 999.0 for s in seen])
        boost = np.array(
            [((L["boost"] or 0.0) if (L["boost_until"] and parse(L["boost_until"]) > now) else 0.0) for L in people],
            dtype=float,
        )
        flag = lambda f: np.array([x.get(f, 0) for x in b], dtype=float)
        feats = dict(
            occ=np.array([L["occ"] for L in people]),
            visits=np.maximum(flag("visits"), 1),
            time_on_site=np.minimum(flag("secs"), 6000),
            video=flag("video"),
            pricing=flag("pricing"),
            testimonial=flag("testimonial"),
            brochure=flag("brochure"),
            chat=flag("chat"),
            webinar=flag("webinar"),
            wishlist=flag("wishlist"),
            cart=flag("cart"),
            checkout=flag("checkout"),
            enquiry=flag("enquiry"),
            opens=np.minimum(flag("clicks"), 10),
            whatsapp=np.array([L["wa"] for L in people], dtype=float),
            dne=np.array([L["dne"] for L in people], dtype=float),
            dnc=np.array([L["dnc"] for L in people], dtype=float),
        )
        z = np.asarray(G.true_logit(feats, intent, luck), dtype=float) + B.BASE_SHIFT
        z += (
            B.WORLD_DRIFT["WhatsAppOptIn"] * feats["whatsapp"]
            + B.WORLD_DRIFT["MobileDevice"] * np.array([L["device"] == "Mobile" for L in people], dtype=float)
            + B.WORLD_DRIFT["WebinarAttended"] * feats["webinar"]
        )
        z += np.array([float(eff.get(u, 0.0)) for u in uid])  # the strongest step of the last 14 days counts
        p14 = sig(z)
        daily_buy = np.where(gap <= self.window, 1 - (1 - p14) ** (1.0 / self.window), 0.0)
        daily_visit = np.where(gap <= 21, sig(-2.6 + 0.7 * intent - 0.05 * gap + boost), 0.0)
        return {"gap": gap, "daily_buy": daily_buy, "daily_visit": daily_visit, "p14": p14}

    def expected_rates(self, at):
        """Expected purchases and return visits per day at time `at`, from what was known then: people who had
        signed up and not bought before `at`, their behaviour up to `at`, the CRM steps still active at `at`.
        (For checks, not for the dice.)"""
        bought_then = {
            r["user_id"]
            for r in db.fetchall(
                """SELECT DISTINCT p.user_id FROM purchases p JOIN users u ON u.id=p.user_id
               WHERE u.email LIKE ? AND p.purchased_at < ?""",
                (LIKE, ts(at)),
            )
        }
        people = [
            L
            for L in self.q("SELECT * FROM learners")
            if L["user_id"] not in bought_then and str(L["created_at"] or "") <= ts(at)
        ]
        if not people:
            return {"purchases": 0.0, "visits": 0.0, "in_market": 0}
        c = self.chances(people, at, until=at)
        return {
            "purchases": float(c["daily_buy"].sum()),
            "visits": float(c["daily_visit"].sum()),
            "in_market": int((c["gap"] <= 21).sum()),
        }

    def roll(self, now, dt_days):
        people = [L for L in self.q("SELECT * FROM learners WHERE bought=0")]
        if people:
            c = self.chances(people, now, until=now)
            busy = np.array([bool(L["busy_until"]) and parse(L["busy_until"]) > now for L in people])
            p_buy = 1 - (1 - c["daily_buy"]) ** dt_days
            p_visit = np.where(~busy, 1 - (1 - c["daily_visit"]) ** dt_days, 0.0)
            buys = self.rng.random(len(people)) < p_buy
            visits = (self.rng.random(len(people)) < p_visit) & ~buys
            self.set_meta("in_market", int((c["gap"] <= 21).sum()))
            self.set_meta("expected_visits_per_day", round(float(c["daily_visit"].sum()), 1))
            self.set_meta("expected_purchases_per_day", round(float(c["daily_buy"].sum()), 1))
            for j in np.flatnonzero(buys):
                self.plan_purchase(people[j], now, busy[j])
            for j in np.flatnonzero(visits):
                start = now + timedelta(seconds=float(self.rng.uniform(0, dt_days * 86400)))
                self.enqueue(start, people[j]["user_id"], "visit", {})
        rate = float(conf().get("new_signups_per_day") or 0)
        has_people = bool(self.q1("SELECT 1 AS x FROM learners LIMIT 1"))  # no starting history: no invented people
        if has_people and rate > 0 and self.rng.random() < 1 - np.exp(-rate * dt_days):
            self.signup(now)

    # 7. a visit, step by step (the requests a browser sends)
    def plan_visit(self, L, start, came_from=None, then_buy=False, note=None):
        beh = self.behaviour([L["user_id"]]).get(L["user_id"], {})
        flags = {f: int(beh.get(f, 0)) for f, *_ in B.EVENTS} | {"checkout": int(beh.get("checkout", 0))}
        first = int(beh.get("visits", 0)) == 0
        boost = (L["boost"] or 0.0) if L["boost_until"] and parse(L["boost_until"]) > start else 0.0
        intent = L["intent"] + boost
        n_pages = int(min(10, 1 + self.rng.poisson(np.exp(0.4 + 0.25 * L["intent"]))))
        page_secs = np.maximum(
            1, np.minimum(600, self.rng.lognormal(np.log(50) + 0.25 * L["intent"], 0.6, n_pages))
        ).astype(int)
        dur = int(page_secs.sum())
        source = L["source"] if first else (came_from or "Direct Traffic")
        vid = uuid.uuid4().hex[:12]
        steps, did = [], []
        clock = start
        for k, secs in enumerate(page_secs):
            for s in range(30, int(secs), 30):  # the tracker: "still here" every 30 s while reading
                steps.append((clock + timedelta(seconds=s), "ping", {}))
            clock = clock + timedelta(seconds=int(secs))
            slug = L["slug"] if k == 0 or self.rng.random() < 0.7 else None
            steps.append((clock, "page", {"slug": slug, "secs": int(secs)}))
        for flag, etype, a, bslope in B.EVENTS:
            if flags.get(flag):
                continue
            extra = 0.5 * flags["pricing"] if flag == "cart" else 0.0
            if self.rng.random() < float(sig(a + bslope * intent + extra)):
                at = start + timedelta(seconds=int(self.rng.uniform(0.2, 1.0) * max(dur, 30)))
                flags[flag] = 1
                did.append(flag)
                kind = flag if flag in ("wishlist", "cart", "enquiry", "chat") else "event"
                steps.append((at, kind, {"etype": etype, "slug": None if flag == "webinar" else L["slug"]}))
                if flag == "cart" and self.rng.random() < float(sig(-1.0 + 0.9 * intent)):
                    steps.append((at + timedelta(minutes=2), "checkout", {}))
                    flags["checkout"] = 1
                    did.append("checkout")
        end = max(t for t, *_ in steps)
        if then_buy:
            steps.append((end + timedelta(minutes=2), "buy", {}))
            end = end + timedelta(minutes=2)
        title = catalog.title_of(L["slug"]) if catalog.get_course(L["slug"]) else L["slug"]
        doing = ", ".join(STEP_TEXT[f].format(course=title) for f in did)
        how = {"Email Campaign": "came back from an email", None: "came back"}.get(came_from, "came back")
        if first:
            how = "is on the website for the first time"
        summary = (
            f"{how}: {n_pages} page{'s' if n_pages > 1 else ''}, {max(1, round(dur / 60))} min"
            + (f"; {doing}" if doing else "")
            + ("; then buys" if then_buy else "")
            + (f" ({note})" if note else "")
        )
        self.enqueue(start, L["user_id"], "session", {"source": source, "device": L["device"], "summary": summary}, vid)
        for at, kind, payload in sorted(steps, key=lambda s: s[0]):
            self.enqueue(at, L["user_id"], kind, payload, vid)
        self.x("UPDATE learners SET busy_until=? WHERE user_id=?", (ts(end + timedelta(minutes=1)), L["user_id"]))
        return {"visit": vid, "start": ts(start), "end": ts(end), "summary": summary}

    def plan_purchase(self, L, now, busy=False):
        if busy:  # on the website right now: buys at the end of this visit
            end = parse(L["busy_until"])
            self.enqueue(end, L["user_id"], "buy", {})
        else:  # comes back to buy
            self.plan_visit(L, now + timedelta(seconds=float(self.rng.uniform(0, 60))), "Direct Traffic", then_buy=True)

    # 8. carry out what is due
    def token(self, L):
        tok = self._tokens.get(L["user_id"])
        if tok and tok[1] > _time.time():
            return tok[0]
        row = db.fetchone("SELECT password_hash FROM users WHERE id=?", (L["user_id"],))
        # the website's own tokens: the simulated learner is signed in
        t = security.create_learner_token(L["user_id"], L["email"], (row or {}).get("password_hash"))
        self._tokens[L["user_id"]] = (t, _time.time() + 6 * 3600)
        return t

    def call(self, method, path, body=None, L=None):
        return self.api.call(method, path, body, token=self.token(L) if L else None)

    def track(self, L, etype, slug=None, secs=0):
        code, r = self.call(
            "POST",
            "/track",
            {
                "session_id": int(L["session_id"] or 0),
                "course_slug": slug,
                "event_type": etype,
                "time_spent_sec": int(secs),
            },
            L,
        )
        if code != 200:
            raise RuntimeError(f"track {etype}: {code} {r}")
        return r

    def process_queue(self, now):
        steps = self.q("SELECT * FROM queue WHERE due_at <= ? ORDER BY due_at, id LIMIT 300", (ts(now),))
        dropped = set()
        for st in steps:
            self.x("DELETE FROM queue WHERE id=?", (st["id"],))
            if st["visit"] and st["visit"] in dropped:
                continue
            L = self.learner(st["user_id"])
            if not L:
                continue
            if now - parse(st["due_at"]) > LATE:
                if st["visit"]:
                    dropped.add(st["visit"])
                    self.x("DELETE FROM queue WHERE visit=?", (st["visit"],))
                    self.x("UPDATE learners SET busy_until=NULL WHERE user_id=?", (L["user_id"],))
                continue  # the website was not running then: it did not happen
            if L["bought"]:
                continue
            try:
                self.run_step(L, st, now)
            except Offline:
                self.x(
                    "INSERT INTO queue (id, due_at, user_id, visit, kind, payload) VALUES (?,?,?,?,?,?)",
                    (st["id"], st["due_at"], st["user_id"], st["visit"], st["kind"], st["payload"]),
                )
                raise
            except Exception as e:  # noqa: BLE001 - one learner's step failing must not stop the others
                self.log(now, L, "error", f"{st['kind']} failed: {e}")
                if st["kind"] == "session" and st["visit"]:
                    dropped.add(st["visit"])
                    self.x("DELETE FROM queue WHERE visit=?", (st["visit"],))
                    self.x("UPDATE learners SET busy_until=NULL WHERE user_id=?", (L["user_id"],))

    def run_step(self, L, st, now):
        kind, p = st["kind"], json.loads(st["payload"] or "{}")
        slug = L["slug"]
        if kind == "visit":
            if L["busy_until"] and parse(L["busy_until"]) > now:
                return  # already on the site
            self.plan_visit(L, now, p.get("came_from"), then_buy=bool(p.get("buy")), note=p.get("note"))
        elif kind == "session":  # the browser starts a visit
            code, r = self.call("POST", "/session/start", {"device_type": p["device"], "lead_source": p["source"]}, L)
            if code != 200 or not (r or {}).get("session_id"):
                raise RuntimeError(f"session start: {code} {r}")
            self.x("UPDATE learners SET session_id=? WHERE user_id=?", (int(r["session_id"]), L["user_id"]))
            self.log(now, L, "visit", p.get("summary") or "is on the website")
        elif kind == "page":  # time on a page, sent when they leave it
            self.track(L, "page_view", p.get("slug"), p.get("secs", 0))
        elif kind == "ping":  # the tracker: still on the page
            self.call("POST", "/session/ping", {"session_id": int(L["session_id"] or 0)}, L)
        elif kind == "event":
            self.track(L, p["etype"], p.get("slug"))
        elif kind == "wishlist":  # the course page's Save button
            code, r = self.call("POST", "/wishlist", {"course_slug": slug}, L)
            if code == 200:
                self.track(L, "wishlist_add", slug)
        elif kind == "cart":  # the course page's Add to cart button
            code, r = self.call("POST", "/cart", {"course_slug": slug}, L)
            if code == 200:
                self.track(L, "cart_add", slug)
        elif kind == "checkout":  # the checkout page opens
            self.call("POST", "/checkout/start", None, L)
            self.track(L, "checkout_start")
        elif kind == "enquiry":  # the enquiry form (phone and WhatsApp choice from the profile)
            code, r = self.call(
                "POST", "/enquiry", {"course_slug": slug, "phone": L["phone"], "whatsapp_opt_in": bool(L["wa"])}, L
            )
            if code != 200:
                raise RuntimeError(f"enquiry: {code} {r}")
        elif kind == "chat":  # the help assistant: "chat" on the first message, then the question
            self.track(L, "chat")
            self.call(
                "POST",
                "/chat",
                {
                    "message": str(self.rng.choice(CHAT_QUESTIONS)),
                    "conversation_id": uuid.uuid4().hex,
                    "course_slug": slug,
                },
                L,
            )
        elif kind == "click":  # the email's button opens the course page with ?ref=<token>
            code, r = self.api.call("POST", "/email/click", {"token": p["token"]})
            if code == 200 and (r or {}).get("ok"):
                self.log(now, L, "click", f"clicked the email '{(p.get('subject') or '')[:70]}'")
                if not (L["busy_until"] and parse(L["busy_until"]) > now):
                    self.enqueue(now + timedelta(minutes=1), L["user_id"], "visit", {"came_from": "Email Campaign"})
        elif kind == "buy":
            self.buy(L, now)

    def buy(self, L, now):
        """Cart, checkout, pay, with their best valid coupon (as the checkout page does)."""
        slug = L["slug"]
        code, r = self.call("GET", "/cart", None, L)
        if slug not in {c.get("course_slug") for c in ((r or {}).get("cart") or [])}:
            code, r = self.call("POST", "/cart", {"course_slug": slug}, L)
            if code == 200:
                self.track(L, "cart_add", slug)
        self.call("POST", "/checkout/start", None, L)
        self.track(L, "checkout_start")
        code, r = self.call("GET", "/coupons", None, L)
        nowts = ts(now)
        valid = [
            c
            for c in ((r or {}).get("coupons") or [])
            if not c.get("used") and (not c.get("expires_at") or str(c["expires_at"])[:19] > nowts)
        ]
        best = max(valid, key=lambda c: c.get("discount_pct") or 0) if valid else None
        code, r = self.call("POST", "/checkout", {"coupon_code": best["coupon_code"] if best else ""}, L)
        if code == 400 and best:  # the coupon ran out a moment ago: pay full price
            best = None
            code, r = self.call("POST", "/checkout", {"coupon_code": ""}, L)
        if code != 200:
            raise RuntimeError(f"checkout: {code} {r}")
        self.x("UPDATE learners SET bought=1, busy_until=NULL WHERE user_id=?", (L["user_id"],))
        self.x("DELETE FROM queue WHERE user_id=?", (L["user_id"],))
        title = catalog.title_of(slug) if catalog.get_course(slug) else slug
        self.log(
            now,
            L,
            "buy",
            f"bought {title}"
            + (f" with the coupon {best['coupon_code']} ({best['discount_pct']}% off)" if best else " at full price"),
        )

    # 9. new people sign up (sign-up, emailed code, profile, contact preferences)
    def signup(self, now):
        k = int(self.meta("next_k") or history_size()[0])
        for _ in range(20):  # skip any number already used
            tr = new_traits(k)
            if not db.fetchone("SELECT id FROM users WHERE email=?", (tr["email"],)):
                break
            k += 1
        self.set_meta("next_k", k + 1)
        code, r = self.api.call(
            "POST", "/auth/signup", {"name": tr["name"], "email": tr["email"], "password": uuid.uuid4().hex}
        )
        if code != 200:
            self.log(now, None, "error", f"Sign-up of {tr['email']} refused: {code} {r}")
            return None
        address = tr["email"].strip().lower()
        mail = db.fetchone(
            "SELECT subject FROM simulated_inbox WHERE email=? ORDER BY id DESC LIMIT 1", (address,)
        )  # the code from their inbox
        db.execute("DELETE FROM simulated_inbox WHERE email=?", (address,))
        found = re.search(r"code: (\d{6})", (mail or {}).get("subject", ""))
        code, r = self.api.call(
            "POST", "/auth/verify-otp", {"email": tr["email"], "otp": found.group(1) if found else ""}
        )
        if code != 200:
            self.log(now, None, "error", f"Verification of {tr['email']} failed: {code} {r}")
            return None
        uid, token = int(r["user"]["id"]), r["token"]
        raw = tr["raw"]
        known = lambda v: None if v in (None, "Unknown") else v
        if raw["CurrentOccupation"] != "Unknown":
            self.api.call(
                "POST",
                "/profile/complete",
                {
                    "current_occupation": raw["CurrentOccupation"],
                    "specialization": raw["Specialization"],
                    "age_bracket": known(raw["AgeBracket"]),
                    "city": raw["City"],
                    "country": raw["Country"],
                    "phone": tr["phone"],
                    "how_did_you_hear": raw["HowDidYouHear"],
                },
                token=token,
            )
        self.api.call(
            "PUT",
            "/profile/preferences",
            {
                "do_not_email": bool(tr["dne"]),
                "do_not_call": bool(tr["dnc"]),
                "whatsapp_opt_in": bool(tr["wa"]),
                "phone": tr["phone"],
            },
            token=token,
        )
        self.x(
            """INSERT OR REPLACE INTO learners (user_id, email, name, k, joined, intent, luck, noise_json, slug, device,
                  source, occ, dne, dnc, wa, phone, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uid,
                tr["email"],
                tr["name"],
                k,
                "live",
                tr["intent"],
                tr["luck"],
                json.dumps(tr["noise"]),
                tr["slug"],
                tr["device"],
                tr["source"],
                tr["occ"],
                tr["dne"],
                tr["dnc"],
                tr["wa"],
                tr["phone"],
                ts(now),
            ),
        )
        self._tokens[uid] = (token, _time.time() + 6 * 3600)
        L = self.learner(uid)
        occ = tr["occ"] if tr["occ"] != "Unknown" else "no profile"
        self.log(now, L, "signup", f"signed up ({occ}, came from {tr['source']})")
        self.enqueue(
            now + timedelta(seconds=float(self.rng.uniform(20, 90))), uid, "visit", {"came_from": tr["source"]}
        )
        return L

    # the clock
    def tick(self):
        """Called every few seconds by the backend's scheduler."""
        if not self._busy.acquire(blocking=False):
            return
        try:
            with self.lock:
                if not self.enabled():
                    return
                now = self.clock()
                try:
                    if self._last_sync is None or now - self._last_sync > timedelta(minutes=10):
                        self.sync(now)
                    self.process_queue(now)
                    self.handle_emails(now)
                    self.handle_tasks(now)
                    last = self.meta("last_roll")
                    last = parse(last) if last else None
                    if last is None or now - last >= ROLL_EVERY:
                        gap = (now - last) if last else ROLL_EVERY
                        if gap > 3 * ROLL_EVERY:  # the servers were off: that time is not simulated
                            gap = ROLL_EVERY
                        self.roll(now, gap.total_seconds() / 86400)
                        self.set_meta("last_roll", ts(now))
                    self.process_queue(now)
                    self.set_meta("last_tick", ts(now))
                    self.last_error = None
                    if now.minute == 0 and now.second < 20:  # keep the diary short
                        self.x("DELETE FROM log WHERE id < (SELECT COALESCE(MAX(id),0) - 5000 FROM log)")
                except Offline as e:
                    self.last_error = f"The website's API is not reachable yet ({e}); trying again in a few seconds."
        finally:
            self._busy.release()

    # the dashboard
    def visit_now(self, kind="returning"):
        """'Send a simulated learner to the website now': instead of waiting for the dice, one learner who is
        still deciding (picked with their own chance of coming back) starts a visit now. What they do there is
        drawn exactly as for any other visit. kind='signup': a new learner signs up now."""
        with self.lock:
            if not self.enabled():
                raise Paused(
                    "The simulated learners are switched off in backend/.env (SIMULATION_ENABLED=false)."
                    if self.switched_off_by_settings()
                    else "The simulated learners are paused. Resume them first."
                )
            now = self.clock()
            if self._last_sync is None:
                self.sync(now)
            L = None
            if kind != "signup":
                cand = [
                    P
                    for P in self.q("SELECT * FROM learners WHERE bought=0")
                    if not (P["busy_until"] and parse(P["busy_until"]) > now)
                ]
                w = self.chances(cand, now, until=now)["daily_visit"] if cand else np.zeros(0)
                if w.sum() > 0:  # someone still deciding, picked with their own chance of coming back
                    L = cand[int(self.rng.choice(len(cand), p=w / w.sum()))]
                    L["noise"] = json.loads(L["noise_json"] or "{}")
                    self.enqueue(now, L["user_id"], "visit", {"note": "sent to the website from the dashboard"})
            if L is None:
                try:
                    L = self.signup(now)
                except Offline as e:
                    raise Offline(str(e)) from e
                if L is None:
                    raise RuntimeError("The sign-up did not go through: see the backend log.")
                kind = "signup"
        threading.Thread(target=self.tick, daemon=True).start()  # start right away, not at the next tick
        lead = db.fetchone("SELECT MAX(id) AS id FROM leads WHERE user_id=?", (L["user_id"],)) or {}
        return {
            "user_id": L["user_id"],
            "name": L["name"],
            "lead_id": lead.get("id"),
            "kind": kind,
            "message": (
                f"{L['name']} signed up and will open the website in about a minute."
                if kind == "signup"
                else f"{L['name']} is on the website now. Their lead page updates as they go; the CRM decides "
                f"what to do about a minute after they leave (demo timing)."
            ),
        }

    def status(self):
        now = self.clock()
        with self.lock:
            tot = (
                self.q1(
                    """SELECT COUNT(*) AS n, SUM(bought) AS bought, SUM(joined='live') AS live,
                                    SUM(CASE WHEN busy_until > ? THEN 1 ELSE 0 END) AS busy FROM learners""",
                    (ts(now),),
                )
                or {}
            )
            day = ts(now - timedelta(days=1))
            counts = {
                r["kind"]: r["n"]
                for r in self.q("SELECT kind, COUNT(*) AS n FROM log WHERE at >= ? GROUP BY kind", (day,))
            }
            recent = self.q("SELECT at, user_id, kind, text FROM log WHERE kind != 'error' ORDER BY id DESC LIMIT 15")
            errors = self.q("SELECT at, text FROM log WHERE kind='error' ORDER BY id DESC LIMIT 3")
            nxt = self.q1("SELECT MIN(due_at) AS d, COUNT(*) AS n FROM queue") or {}
            waiting = (self.q1("SELECT COUNT(*) AS n FROM tasks WHERE handled=0") or {}).get("n") or 0
            out = {
                "enabled": self.enabled(),
                "switched_off_by_settings": self.switched_off_by_settings(),
                "started_at": self.meta("started_at"),
                "last_tick": self.meta("last_tick"),
                "last_error": self.last_error,
                "learners": {
                    "total": int(tot.get("n") or 0),
                    "customers": int(tot.get("bought") or 0),
                    "signed_up_live": int(tot.get("live") or 0),
                    "on_site_now": int(tot.get("busy") or 0),
                    "still_deciding": int(self.meta("in_market") or 0),
                },
                "expected_per_day": {
                    "visits": float(self.meta("expected_visits_per_day") or 0),
                    "purchases": float(self.meta("expected_purchases_per_day") or 0),
                    "signups": float(conf().get("new_signups_per_day") or 0),
                },
                "last_24h": {
                    "visits": counts.get("visit", 0),
                    "email_clicks": counts.get("click", 0),
                    "purchases": counts.get("buy", 0),
                    "signups": counts.get("signup", 0),
                    "team_tasks": counts.get("team", 0),
                    "errors": counts.get("error", 0),
                },
                "tasks_waiting_for_team": int(waiting),  # their open call / WhatsApp tasks (Today's actions)
                "recent": recent,
                "recent_errors": errors,
                "queued_steps": int(nxt.get("n") or 0),
                "next_step_at": nxt.get("d"),
            }
        return out


_world = {"w": None}
_world_lock = threading.Lock()


def get_world():
    with _world_lock:
        if _world["w"] is None:
            _world["w"] = World()
        return _world["w"]


def tick():
    get_world().tick()


class _NoApi:
    def call(self, *a, **k):
        return 200, {}


def self_check(n=200, days=60, seed=2026):
    """Proof that the live simulation continues the history exactly. Generates a small history with the real history
    generator in a temporary folder (your data and models are not touched; nothing is emailed; the CRM's models are
    not retrained), then, at the history's last moment, computes every learner's daily chance to buy twice: with the
    history generator's own formula and state, and with the live simulation, which re-creates the people from the
    seed and reads only the CRM's tables. They must be identical. 60 days, so the check includes two campaigns and an
    A/B test with coupons (their effects are worked out on what the CRM knew when it picked the person, as in the
    history), visits after email clicks and the outcome window's last day.
    Changes this process's settings, so it runs only on its own: python -m app.cli simulation self-check"""
    import shutil
    import tempfile

    from app.ml import learning
    from app.simulation import history as H

    global history_size
    tmp = tempfile.mkdtemp(prefix="xedu-selfcheck-")
    db.DB_PATH = os.path.join(tmp, "crm.db")
    db.init_db()
    learning.run = lambda **k: {"status": "skipped"}  # the CRM's models stay as they are
    history_size = lambda: (n, days)  # noqa: E731
    _cache.clear()
    from app.services import gemini

    gemini.disable()
    t0 = _time.time()
    h = H.History(n, days, seed, verbose=False)
    h.run()
    at = h.now
    d = (at.date() - h.start.date()).days
    w = World(api=_NoApi(), path=os.path.join(tmp, "world.db"), rng=np.random.default_rng(1), clock=lambda: at)
    w.sync(at)
    people = w.q("SELECT * FROM learners WHERE bought=0")
    c = w.chances(people, at, until=at)
    live = {int(L["user_id"]): float(c["daily_buy"][j]) for j, L in enumerate(people)}
    pairs = []
    for L in h.learners:
        if L["bought"] or L["uid"] not in live:
            continue
        hist = h.buy_probability_today(L, d, at) if d - L["last_visit_day"] <= h.window else 0.0
        pairs.append((hist, live[L["uid"]]))
    diff = max((abs(a - b) for a, b in pairs), default=0.0)
    if w._con is not None:
        w._con.close()
    shutil.rmtree(tmp, ignore_errors=True)  # the temporary history is thrown away
    return {
        "learners_compared": len(pairs),
        "max_difference": diff,
        "history_expects_per_day": round(sum(a for a, _ in pairs), 4),
        "live_expects_per_day": round(sum(b for _, b in pairs), 4),
        "history": {
            "learners": n,
            "days": days,
            "purchases": h.stats["purchases"],
            "decisions": h.stats["decisions"],
            "emails": h.stats["emails"],
        },
        "seconds": round(_time.time() - t0, 1),
    }


def reset() -> None:
    """Forget the simulator's own records (not the CRM's data); it re-creates them from the CRM on its next start."""
    w = get_world()
    with w.lock:
        for t in ("effects", "tasks", "queue", "log", "meta", "learners"):
            w.x(f"DELETE FROM {t}")
        w._last_sync = None
