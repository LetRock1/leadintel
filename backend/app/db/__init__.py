"""
Database access for the whole backend: one SQLite file (``backend/data/xeducation.db``), opened per call
with WAL journaling and a 30-second busy timeout, plus the small repository helpers the services share.

The schema is created and upgraded by versioned Alembic migrations (``app/db/migrations``); ``init_db``
runs them, so a new database and an older one both end at the current version.

``DB_PATH`` is a module attribute on purpose: tests and the simulators point the whole backend at a
private copy by assigning it (``app.db.DB_PATH = path``).
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH_OVERRIDE") or str(get_settings().db_path)
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_conn() -> sqlite3.Connection:
    # timeout/busy_timeout: wait up to 30 s for another writer instead of failing with "database is locked"
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _restore_seeds_if_needed(target_path: Path) -> None:
    settings = get_settings()
    if settings.environment == "test":
        return
    if target_path.exists() and target_path.stat().st_size > 0:
        return

    import gzip
    import shutil

    seeds_dir = Path(__file__).resolve().parents[2] / "seeds"
    if not seeds_dir.exists():
        return

    seed_gz = seeds_dir / "xeducation.db.gz"
    if seed_gz.exists() and target_path.name == "xeducation.db":
        log.info("Restoring database seed from %s -> %s", seed_gz, target_path)
        with gzip.open(seed_gz, "rb") as f_in, open(target_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    sim_db = settings.simulation_db
    if not sim_db.exists() or sim_db.stat().st_size == 0:
        sim_seed_gz = seeds_dir / "simulation_world.db.gz"
        if sim_seed_gz.exists():
            sim_db.parent.mkdir(parents=True, exist_ok=True)
            log.info("Restoring simulation world seed from %s -> %s", sim_seed_gz, sim_db)
            with gzip.open(sim_seed_gz, "rb") as f_in, open(sim_db, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

    models_seed_dir = seeds_dir / "models"
    target_models_dir = settings.model_dir
    if models_seed_dir.exists():
        target_models_dir.mkdir(parents=True, exist_ok=True)
        for model_file in models_seed_dir.iterdir():
            dest = target_models_dir / model_file.name
            if not dest.exists():
                shutil.copy2(model_file, dest)


def init_db(path: str | None = None) -> None:
    """Create or upgrade the database schema to the latest migration (idempotent)."""
    from alembic import command
    from alembic.config import Config

    target = str(path or DB_PATH)
    target_p = Path(target)
    target_p.parent.mkdir(parents=True, exist_ok=True)
    _restore_seeds_if_needed(target_p)
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{target}")
    command.upgrade(cfg, "head")
    log.info("Database ready at %s", target)


def schema_version(path: str | None = None) -> str | None:
    con = sqlite3.connect(str(path or DB_PATH))
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


@contextlib.contextmanager
def transaction():
    """Several writes that must succeed or fail together: ``with db.transaction() as con: con.execute(...)``."""
    con = get_conn()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def claim(query: str, params=()) -> bool:
    """Run a guarded UPDATE and say whether it changed exactly one row (so a campaign or an A/B test can
    only be sent once, even if the timer and a button press collide)."""
    con = get_conn()
    try:
        cur = con.execute(query, params)
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


# small key/value store (generated secrets, team settings, assignment state)
def app_setting(key: str) -> str | None:
    row = fetchone("SELECT value FROM app_settings WHERE key=?", (key,))
    return row["value"] if row else None


def put_app_setting(key: str, value: str) -> None:
    execute(
        """INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, datetime('now','localtime'))
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, value),
    )


# helpers
def fetchone(query: str, params=()) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def fetchall(query: str, params=()) -> list[dict]:
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def execute(query: str, params=()) -> int | None:
    """Run one write and commit it; returns the new row id (for an INSERT)."""
    conn = get_conn()
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def execute_rowcount(query: str, params=()) -> int:
    """Run one write and commit it; returns how many rows it changed."""
    conn = get_conn()
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def lost_status(user_id):
    """{'reason': ..., 'moved_at': ..., 'moved_by': ...} if the team closed this lead as lost, else None.
    A lost lead gets no automatic steps (emails, coupons, calls, WhatsApp) until someone re-opens it."""
    return fetchone(
        "SELECT lost_reason AS reason, moved_at, moved_by FROM pipeline_overrides " "WHERE user_id=? AND stage='Lost'",
        (user_id,),
    )


def get_user_by_email(email):
    return fetchone("SELECT * FROM users WHERE email=?", (email,))


def get_user_by_id(user_id):
    return fetchone("SELECT * FROM users WHERE id=?", (user_id,))


def get_profile(user_id):
    return fetchone("SELECT * FROM user_profiles WHERE user_id=?", (user_id,))


def get_cart(user_id):
    return fetchall("SELECT * FROM cart WHERE user_id=? ORDER BY added_at DESC", (user_id,))


def get_wishlist(user_id):
    return fetchall("SELECT * FROM wishlist WHERE user_id=? ORDER BY added_at DESC", (user_id,))


def get_purchases(user_id):
    return fetchall("SELECT * FROM purchases WHERE user_id=? ORDER BY purchased_at DESC", (user_id,))


def get_reviews(course_slug):
    return fetchall(
        """
        SELECT r.*, u.name FROM reviews r
        JOIN users u ON r.user_id=u.id
        WHERE r.course_slug=? ORDER BY r.created_at DESC
    """,
        (course_slug,),
    )


def get_qna(course_slug):
    return fetchall(
        """
        SELECT q.*, u.name as user_name FROM qna q
        JOIN users u ON q.user_id=u.id
        WHERE q.course_slug=? ORDER BY q.created_at DESC
    """,
        (course_slug,),
    )


def get_user_lead(user_id):
    return fetchone("SELECT * FROM leads WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT 1", (user_id,))


# Behaviour summary → the model's auto-tracked features
def get_behaviour_summary(user_id):
    """
    Aggregates everything the website tracked for this user into the same
    quantities the model was trained on:
      total_visits          distinct sessions that produced at least one event
                            (a new session starts after 30 min of inactivity)
      total_time_on_website seconds summed from page_view events
      page_views_per_visit  page_view events / visits
      flags                 1 if the event ever happened
    """
    conn = get_conn()
    try:
        q = lambda sql, *a: conn.execute(sql, (user_id, *a)).fetchone()

        visits = (
            q(
                "SELECT COUNT(DISTINCT session_id) AS c FROM behaviour_events "
                "WHERE user_id=? AND session_id IS NOT NULL"
            )["c"]
            or 0
        )
        visits = max(visits, 1)
        time_total = (
            q(
                "SELECT COALESCE(SUM(time_spent_sec),0) AS t FROM behaviour_events "
                "WHERE user_id=? AND event_type='page_view'"
            )["t"]
            or 0
        )
        pv = q("SELECT COUNT(*) AS c FROM behaviour_events " "WHERE user_id=? AND event_type='page_view'")["c"] or 0

        counts = {
            r["event_type"]: r["c"]
            for r in conn.execute(
                "SELECT event_type, COUNT(*) AS c FROM behaviour_events WHERE user_id=? GROUP BY event_type", (user_id,)
            ).fetchall()
        }
        has = lambda *types: int(any(counts.get(t, 0) > 0 for t in types))

        in_cart = q("SELECT COUNT(*) AS c FROM cart WHERE user_id=?")["c"]
        in_wishlist = q("SELECT COUNT(*) AS c FROM wishlist WHERE user_id=?")["c"]
        checkouts = q("SELECT COUNT(*) AS c FROM checkout_sessions WHERE user_id=?")["c"]
        enquiries = q("SELECT COUNT(*) AS c FROM leads WHERE user_id=? AND trigger_reason='enquiry'")["c"]

        # most-viewed course; ties go to the one seen most recently (the score refresh uses the same rule)
        row = q("""SELECT course_slug, COUNT(*) AS cnt FROM behaviour_events
                   WHERE user_id=? AND course_slug IS NOT NULL
                   GROUP BY course_slug ORDER BY cnt DESC, MAX(id) DESC LIMIT 1""")
        last_session = q(
            "SELECT device_type FROM user_sessions WHERE user_id=? "
            "AND device_type IS NOT NULL ORDER BY id DESC LIMIT 1"
        )
        # acquisition source = first visit that came from somewhere specific
        first_source = q(
            "SELECT lead_source FROM user_sessions WHERE user_id=? "
            "AND lead_source IS NOT NULL AND lead_source != 'Direct Traffic' "
            "ORDER BY id ASC LIMIT 1"
        )

        return {
            "total_visits": visits,
            "sessions_count": visits,
            "total_time_on_website": int(min(time_total, 6000)),
            "page_views_per_visit": round(pv / visits, 1),
            "video_watched": has("video_play"),
            "brochure_downloaded": has("brochure_dl"),
            "chat_initiated": has("chat"),
            "pricing_page_visited": has("pricing_view"),
            "testimonial_visited": has("testimonial_view"),
            "webinar_attended": has("webinar_view", "webinar_register"),
            "added_to_wishlist": int(has("wishlist_add") or in_wishlist > 0),
            "added_to_cart": int(has("cart_add") or in_cart > 0),
            "checkout_started": int(has("checkout_start") or checkouts > 0),
            "enquiry_submitted": int(has("enquiry_submit") or enquiries > 0),
            "top_course_slug": row["course_slug"] if row else None,
            "device_type": last_session["device_type"] if last_session else None,
            "lead_source": first_source["lead_source"] if first_source else None,
        }
    finally:
        conn.close()


def add_score_snapshot(user_id, source, features, probability, lead_score, tier, model_version, min_gap_minutes=0):
    """Store what the model saw + what it predicted. Later labelled by purchases."""
    import json

    if min_gap_minutes:
        recent = fetchone(
            """SELECT id FROM score_snapshots WHERE user_id=? AND source=?
                             AND created_at >= datetime('now','localtime',?)""",
            (user_id, source, f"-{int(min_gap_minutes)} minutes"),
        )
        if recent:
            return None
    return execute(
        """INSERT INTO score_snapshots
        (user_id, source, features_json, probability, lead_score, tier, model_version)
        VALUES (?,?,?,?,?,?,?)""",
        (user_id, source, json.dumps(features), probability, lead_score, tier, model_version),
    )


def validate_coupon(user_id, code):
    return fetchone(
        """
        SELECT * FROM coupons_issued
        WHERE user_id=? AND coupon_code=? AND used=0
          AND (expires_at IS NULL OR expires_at > datetime('now','localtime'))
    """,
        (user_id, code),
    )


OPEN_COUPON = "COALESCE(used, 0) = 0 AND (expires_at IS NULL OR expires_at > datetime('now','localtime'))"


def open_coupon(user_id):
    """The coupon this person can still use (not used, not expired; the biggest if there are several), or None. A
    person holds at most one open coupon from next-best-action or the team."""
    return fetchone(
        f"""SELECT * FROM coupons_issued WHERE user_id=? AND {OPEN_COUPON}
             ORDER BY discount_pct DESC, expires_at DESC LIMIT 1""",
        (user_id,),
    )


def recent_coupon(user_id, days):
    """The latest coupon this person was given in the last `days` days, used or not (None if none)."""
    return fetchone(
        """SELECT * FROM coupons_issued WHERE user_id=? AND created_at >= datetime('now','localtime',?)
             ORDER BY created_at DESC LIMIT 1""",
        (user_id, f"-{int(days)} days"),
    )


def recent_coupons(days) -> dict:
    """{user_id: their latest coupon of the last `days` days} for everyone given one (see recent_coupon)."""
    out: dict = {}
    for r in fetchall(
        "SELECT * FROM coupons_issued WHERE created_at >= datetime('now','localtime',?) ORDER BY created_at",
        (f"-{int(days)} days",),
    ):
        out[r["user_id"]] = r
    return out


def open_coupons() -> dict:
    """{user_id: their open coupon} for everyone who holds one (see open_coupon)."""
    out: dict = {}
    for r in fetchall(f"SELECT * FROM coupons_issued WHERE {OPEN_COUPON} ORDER BY discount_pct, expires_at"):
        out[r["user_id"]] = r  # the last row per person wins: the biggest discount, then the latest expiry
    return out


def mark_coupon_used(coupon_id):
    execute(
        """
        UPDATE coupons_issued SET used=1, used_at=datetime('now','localtime')
        WHERE id=?
    """,
        (coupon_id,),
    )


# ============================================================
# SCHEDULER SUPPORT FUNCTIONS (NEW)
# ============================================================


def get_abandoned_carts(minutes=60):
    """
    Cart items where user added course but didn't purchase
    within X minutes.
    """
    return fetchall(
        """
        SELECT
            c.id as cart_id,
            c.user_id,
            c.course_slug,
            c.course_title,
            c.price,
            c.added_at,
            u.email,
            u.name
        FROM cart c
        JOIN users u ON u.id = c.user_id
        WHERE c.abandon_email_sent = 0
        AND c.added_at <= datetime('now','localtime', ?)
    """,
        (f"-{minutes} minutes",),
    )


def mark_cart_email_sent(cart_id):
    execute("UPDATE cart SET abandon_email_sent=1 WHERE id=?", (cart_id,))


def get_inactive_users(minutes=15, lookback_hours=48):
    """
    Visits that ended (no activity for `minutes`) and have not been handled by
    the inactivity job yet — one decision per visit. Only each user's latest
    visit counts, and only if it happened in the last `lookback_hours`.
    """
    return fetchall(
        """
        SELECT
            u.id AS user_id,
            u.email,
            u.name,
            s.id AS session_id,
            s.last_active AS last_seen
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE u.is_verified = 1
          AND s.id = (SELECT MAX(s2.id) FROM user_sessions s2 WHERE s2.user_id = s.user_id)
          AND COALESCE(s.followed_up, 0) = 0
          AND s.last_active <= datetime('now','localtime', ?)
          AND s.last_active >= datetime('now','localtime', ?)
    """,
        (f"-{minutes} minutes", f"-{lookback_hours} hours"),
    )


def mark_visit_handled(user_id, session_id):
    execute("UPDATE user_sessions SET followed_up=1 WHERE user_id=? AND id<=?", (user_id, session_id))


def get_users_with_old_wishlist(minutes=30):
    """
    Users with a wishlisted course (not bought, not reminded yet) that was
    added more than `minutes` ago — one reminder per wishlist item.
    course_slug is the oldest such item (SQLite returns the row of MIN()).
    """
    return fetchall(
        """
        SELECT
            w.user_id,
            u.email,
            u.name,
            w.course_slug,
            MIN(w.added_at) as first_added
        FROM wishlist w
        JOIN users u ON u.id = w.user_id
        LEFT JOIN purchases p
            ON p.user_id = w.user_id
            AND p.course_slug = w.course_slug
        WHERE p.id IS NULL
          AND COALESCE(w.reminder_sent, 0) = 0
        GROUP BY w.user_id
        HAVING first_added <= datetime('now','localtime', ?)
    """,
        (f"-{minutes} minutes",),
    )


def mark_wishlist_reminded(user_id):
    execute("UPDATE wishlist SET reminder_sent=1 WHERE user_id=?", (user_id,))


def recent_lead_exists(user_id, trigger, hours=6):
    """
    Prevent duplicate leads within cooldown window.
    trigger may be a single trigger, a list/tuple of triggers, or None (= any).
    """
    if trigger is None:
        triggers = None
    elif isinstance(trigger, list | tuple):
        triggers = list(trigger)
    else:
        triggers = [trigger]
    sql = "SELECT id FROM leads WHERE user_id=? AND created_at >= datetime('now','localtime', ?)"
    params = [user_id, f"-{hours} hours"]
    if triggers:
        sql += f" AND trigger_reason IN ({','.join('?' * len(triggers))})"
        params += triggers
    return fetchone(sql + " LIMIT 1", tuple(params)) is not None


def get_attribution_lead(user_id):
    """The latest lead that actually reached the user (email sent or enquiry)."""
    return fetchone(
        """SELECT * FROM leads WHERE user_id=? AND (email_sent=1 OR trigger_reason='enquiry')
                       ORDER BY created_at DESC, id DESC LIMIT 1""",
        (user_id,),
    )


# ============================================================
# CHECKOUT ABANDONMENT
# ============================================================


def start_checkout_session(user_id, cart_value):
    return execute("INSERT INTO checkout_sessions (user_id, cart_value) VALUES (?,?)", (user_id, cart_value))


def complete_latest_checkout_session(user_id):
    # Close ALL open checkout sessions for this user. If they opened /checkout
    # more than once before paying, the older sessions would otherwise stay
    # "abandoned" and trigger a recovery email AFTER they already bought.
    execute("UPDATE checkout_sessions SET completed=1 WHERE user_id=? AND completed=0", (user_id,))


def get_abandoned_checkouts(minutes=30):
    """
    Checkout sessions started but not completed within X minutes.
    """
    return fetchall(
        """
        SELECT
            cs.id as checkout_id,
            cs.user_id,
            cs.cart_value,
            cs.started_at,
            u.email,
            u.name
        FROM checkout_sessions cs
        JOIN users u ON u.id = cs.user_id
        WHERE cs.completed = 0
          AND cs.abandon_email_sent = 0
          AND cs.started_at <= datetime('now','localtime', ?)
    """,
        (f"-{minutes} minutes",),
    )


def mark_checkout_email_sent(checkout_id):
    execute("UPDATE checkout_sessions SET abandon_email_sent=1 WHERE id=?", (checkout_id,))


# ============================================================
# EMAIL SENDS (open/click tracking)
# ============================================================


def insert_email_send(token, user_id, lead_id=None, campaign_id=None, variant="A", subject="", body=""):
    if lead_id:
        execute("UPDATE leads SET email_sent=1, email_sent_at=datetime('now','localtime') WHERE id=?", (lead_id,))
    return execute(
        """
        INSERT INTO email_sends (lead_id, user_id, campaign_id, variant, token, subject, body)
        VALUES (?,?,?,?,?,?,?)
    """,
        (lead_id, user_id, campaign_id, variant, token, subject, body),
    )


def get_email_send_by_token(token):
    return fetchone("SELECT * FROM email_sends WHERE token=?", (token,))


def get_email_engagement(user_id):
    """Real opens/clicks for a user — closes the loop between sent emails and pkl scoring."""
    row = fetchone(
        """
        SELECT COALESCE(SUM(open_count),0)  as opens,
               COALESCE(SUM(click_count),0) as clicks,
               COUNT(*)                     as emails_sent
        FROM email_sends WHERE user_id=?
    """,
        (user_id,),
    )
    return row or {"opens": 0, "clicks": 0, "emails_sent": 0}


def mark_email_opened(token):
    execute(
        """
        UPDATE email_sends
        SET open_count = open_count + 1,
            opened_at = COALESCE(opened_at, datetime('now','localtime'))
        WHERE token=?
    """,
        (token,),
    )


def mark_email_clicked(token):
    execute(
        """
        UPDATE email_sends
        SET click_count = click_count + 1,
            first_clicked_at = COALESCE(first_clicked_at, datetime('now','localtime'))
        WHERE token=?
    """,
        (token,),
    )


# ============================================================
# LEAD SCORE HISTORY
# ============================================================


def log_score_change(lead_id, user_id, old_score, new_score, old_tier, new_tier, reason):
    execute(
        """
        INSERT INTO lead_score_history (lead_id, user_id, old_score, new_score, old_tier, new_tier, reason)
        VALUES (?,?,?,?,?,?,?)
    """,
        (lead_id, user_id, old_score, new_score, old_tier, new_tier, reason),
    )


def get_score_history(lead_id):
    return fetchall("SELECT * FROM lead_score_history WHERE lead_id=? ORDER BY created_at DESC", (lead_id,))


# ============================================================
# PREDICTIVE LIFETIME VALUE (PLV)
# ============================================================


def compute_plv(user_id, recommended_action=None, conversion_probability=0.0, course_slug=None):
    """
    PLV = money already spent + expected value of the next purchase
        = spent + P(convert) × price of the course they are interested in
    (falls back to the catalogue's average price). The old version multiplied
    by a tier factor as well, which counted the probability twice.
    """
    from app.services import catalog

    spent = fetchone("SELECT COALESCE(SUM(price_paid),0) as s FROM purchases WHERE user_id=?", (user_id,))["s"]
    price = catalog.price_of(course_slug) or catalog.average_price()
    return round(spent + price * _as_fraction(conversion_probability), 2)


def _as_fraction(p):
    """predict_lead() returns conversion_probability as 0-1; accept 0-100 too."""
    p = float(p or 0)
    return p / 100.0 if p > 1 else p


def update_lead_plv(lead_id, plv):
    execute("UPDATE leads SET plv=? WHERE id=?", (plv, lead_id))


def public_user(user):
    """User row without secrets — never send password_hash to the browser."""
    if not user:
        return None
    return {k: v for k, v in user.items() if k not in ("password_hash",)}
