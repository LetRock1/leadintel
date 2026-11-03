"""Initial schema (v7.0): learners, their activity, the CRM's decisions and learning, and the team.

One database for the whole backend. Tables in the order a learner meets them: account, profile,
visits and events, cart and wishlist, purchases; then the CRM: contact records (leads), scores,
decisions, tasks, emails, experiments, the learning loop; then the team and the audit log.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-16
"""
from __future__ import annotations

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

NOW = "(datetime('now','localtime'))"

TABLES = [
    # learners
    f"""CREATE TABLE users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        email         TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_verified   INTEGER DEFAULT 0,
        created_at    TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE otp_tokens (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        email      TEXT NOT NULL,
        otp        TEXT NOT NULL,
        purpose    TEXT DEFAULT 'signup',             -- signup | reset
        attempts   INTEGER DEFAULT 0,
        expires_at TEXT NOT NULL,
        used       INTEGER DEFAULT 0,
        created_at TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE user_profiles (
        user_id            INTEGER PRIMARY KEY REFERENCES users(id),
        current_occupation TEXT,
        specialization     TEXT,
        age_bracket        TEXT,
        city               TEXT,
        country            TEXT DEFAULT 'India',
        phone              TEXT,
        whatsapp_opt_in    INTEGER DEFAULT 0,
        do_not_email       TEXT DEFAULT 'No',
        do_not_call        TEXT DEFAULT 'No',
        how_did_you_hear   TEXT,
        profile_complete   INTEGER DEFAULT 0,
        updated_at         TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE user_sessions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER REFERENCES users(id),
        login_at    TEXT DEFAULT {NOW},
        last_active TEXT DEFAULT {NOW},
        device_type TEXT,
        lead_source TEXT DEFAULT 'Direct Traffic',
        followed_up INTEGER DEFAULT 0                -- the 'visit ended' decision was taken for this visit
    )""",
    f"""CREATE TABLE behaviour_events (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER REFERENCES users(id),
        session_id     INTEGER REFERENCES user_sessions(id),
        course_slug    TEXT,
        event_type     TEXT,
        time_spent_sec INTEGER DEFAULT 0,
        created_at     TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE cart (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id            INTEGER REFERENCES users(id),
        course_slug        TEXT NOT NULL,
        course_title       TEXT NOT NULL,
        price              REAL NOT NULL,
        added_at           TEXT DEFAULT {NOW},
        abandon_email_sent INTEGER DEFAULT 0,
        UNIQUE(user_id, course_slug)
    )""",
    f"""CREATE TABLE wishlist (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER REFERENCES users(id),
        course_slug   TEXT NOT NULL,
        course_title  TEXT NOT NULL,
        added_at      TEXT DEFAULT {NOW},
        reminder_sent INTEGER DEFAULT 0,
        UNIQUE(user_id, course_slug)
    )""",
    f"""CREATE TABLE checkout_sessions (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id            INTEGER REFERENCES users(id),
        cart_value         REAL DEFAULT 0,
        started_at         TEXT DEFAULT {NOW},
        completed          INTEGER DEFAULT 0,
        abandon_email_sent INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE purchases (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER REFERENCES users(id),
        course_slug     TEXT NOT NULL,
        course_title    TEXT NOT NULL,
        price_paid      REAL NOT NULL,
        coupon_used     TEXT,
        discount_amount REAL DEFAULT 0,
        purchased_at    TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE reviews (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER REFERENCES users(id),
        course_slug TEXT NOT NULL,
        rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        review_text TEXT,
        created_at  TEXT DEFAULT {NOW},
        UNIQUE(user_id, course_slug)
    )""",
    f"""CREATE TABLE qna (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER REFERENCES users(id),
        course_slug TEXT NOT NULL,
        question    TEXT NOT NULL,
        answer      TEXT,
        answered_by TEXT DEFAULT 'X Education Team',
        answered_at TEXT,
        created_at  TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE chat_messages (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        conversation TEXT NOT NULL,
        role         TEXT NOT NULL,                  -- user | assistant
        text         TEXT NOT NULL,
        intent       TEXT,
        course_slug  TEXT,
        created_at   TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE callback_requests (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER REFERENCES users(id),
        phone          TEXT,
        course_slug    TEXT,
        preferred_time TEXT,
        note           TEXT,
        status         TEXT DEFAULT 'open',          -- open | done
        created_at     TEXT DEFAULT {NOW},
        closed_at      TEXT,
        done_by        TEXT
    )""",
    # the CRM: contact records, scores, decisions, tasks
    f"""CREATE TABLE leads (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id                INTEGER REFERENCES users(id),
        lead_origin            TEXT,
        lead_source            TEXT,
        device_type            TEXT,
        total_visits           INTEGER DEFAULT 1,
        total_time_on_website  INTEGER DEFAULT 0,
        page_views_per_visit   REAL DEFAULT 1.0,
        sessions_count         INTEGER DEFAULT 1,
        video_watched          INTEGER DEFAULT 0,
        brochure_downloaded    INTEGER DEFAULT 0,
        chat_initiated         INTEGER DEFAULT 0,
        pricing_page_visited   INTEGER DEFAULT 0,
        testimonial_visited    INTEGER DEFAULT 0,
        webinar_attended       INTEGER DEFAULT 0,
        email_opened_count     INTEGER DEFAULT 0,
        course_type            TEXT,
        course_slug            TEXT,
        lead_score             REAL,
        conversion_probability REAL,
        plv                    REAL DEFAULT 0,
        persona                TEXT,
        customer_segment       TEXT,
        recommended_action     TEXT,
        score_factors          TEXT,
        model_version          TEXT,
        email_subject          TEXT,
        email_body             TEXT,
        whatsapp_message       TEXT,
        coupon_code            TEXT,
        call_script            TEXT,
        email_sent             INTEGER DEFAULT 0,
        email_sent_at          TEXT,
        trigger_reason         TEXT,
        nba_action             TEXT,
        nba_json               TEXT,
        tips_json              TEXT,
        last_active_at         TEXT,
        decayed                INTEGER DEFAULT 0,
        created_at             TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE live_user_state (
        user_id    INTEGER PRIMARY KEY REFERENCES users(id),
        live_score REAL,
        persona    TEXT,
        updated_at TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE lead_score_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id    INTEGER,
        user_id    INTEGER REFERENCES users(id),
        old_score  REAL,
        new_score  REAL,
        old_tier   TEXT,
        new_tier   TEXT,
        reason     TEXT,
        created_at TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE score_snapshots (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER REFERENCES users(id),
        source        TEXT,
        features_json TEXT NOT NULL,
        probability   REAL,
        lead_score    REAL,
        tier          TEXT,
        model_version TEXT,
        created_at    TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE coupons_issued (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id),
        coupon_code  TEXT NOT NULL,
        discount_pct INTEGER NOT NULL,
        tier         TEXT NOT NULL,
        used         INTEGER DEFAULT 0,
        used_at      TEXT,
        expires_at   TEXT,
        created_at   TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE email_sends (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id          INTEGER,
        user_id          INTEGER REFERENCES users(id),
        campaign_id      INTEGER,
        campaign_name    TEXT,
        ab_test_id       INTEGER,
        variant          TEXT DEFAULT 'A',
        adoption_id      INTEGER,
        adoption_arm     TEXT,
        token            TEXT UNIQUE,
        subject          TEXT,
        body             TEXT,
        sent_at          TEXT DEFAULT {NOW},
        opened_at        TEXT,
        open_count       INTEGER DEFAULT 0,
        first_clicked_at TEXT,
        click_count      INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE nba_decisions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id          INTEGER REFERENCES users(id),
        lead_id          INTEGER,
        trigger_reason   TEXT,
        action           TEXT NOT NULL,             -- what was done
        model_best       TEXT,                      -- what the model would have done
        policy           TEXT,                      -- model | explore | holdout | manual
        propensity       REAL,                      -- P(this action | logging policy)
        base_probability REAL,
        price            REAL,
        options_json     TEXT,
        features_json    TEXT,
        model_version    TEXT,
        executed_at      TEXT,
        created_at       TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE sales_tasks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER REFERENCES users(id),
        lead_id       INTEGER,
        decision_id   INTEGER,
        task_type     TEXT,                         -- call | whatsapp
        title         TEXT,
        detail        TEXT,
        expected_gain REAL,
        status        TEXT DEFAULT 'open',          -- open | done | skipped
        outcome       TEXT,
        created_at    TEXT DEFAULT {NOW},
        done_at       TEXT,
        done_by       TEXT
    )""",
    f"""CREATE TABLE experiment_assignments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_type TEXT NOT NULL,              -- ab | campaign | adoption
        experiment_id   INTEGER NOT NULL,
        user_id         INTEGER REFERENCES users(id),
        lead_id         INTEGER,
        arm             TEXT NOT NULL,              -- control | holdout | send | A | B | C | adopted | old
        probability     REAL NOT NULL,              -- chance of this arm under the assignment rule
        features_json   TEXT,                       -- what the model knew at assignment time
        tier            TEXT,
        occupation      TEXT,
        device          TEXT,
        source          TEXT,
        assigned_at     TEXT DEFAULT {NOW},
        UNIQUE(experiment_type, experiment_id, user_id)
    )""",
    f"""CREATE TABLE learning_runs (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at              TEXT DEFAULT {NOW},
        finished_at             TEXT,
        as_of                   TEXT,
        reason                  TEXT,               -- scheduled | manual | history | cli
        status                  TEXT,               -- done | skipped | error
        outcomes_known          INTEGER,
        new_outcomes            INTEGER,
        random_slice            INTEGER,
        random_slice_buyers     INTEGER,
        lead_decision           TEXT,               -- swapped | kept | not_enough_data
        lead_prob_better        REAL,
        champion_true_logloss   REAL, challenger_true_logloss REAL, naive_true_logloss REAL,
        champion_true_auc       REAL, challenger_true_auc     REAL, naive_true_auc     REAL,
        champion_live_auc       REAL, challenger_live_auc     REAL, naive_live_auc     REAL,
        challenger_live_logloss REAL, naive_live_logloss      REAL,
        naive_would_pick        INTEGER,
        own_effect_share        REAL,
        learned_json            TEXT,
        nba_decision            TEXT,
        nba_detail_json         TEXT,
        lead_version_before     TEXT, lead_version_after TEXT,
        nba_version_before      TEXT, nba_version_after  TEXT,
        note                    TEXT,
        simulated               INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE pipeline_overrides (
        user_id     INTEGER PRIMARY KEY REFERENCES users(id),
        stage       TEXT NOT NULL,                  -- Lead | Engaged | MQL | SQL | Lost
        note        TEXT,
        lost_reason TEXT,
        moved_by    TEXT,
        moved_at    TEXT DEFAULT {NOW}
    )""",
    """CREATE TABLE adopted_emails (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ab_test_id    INTEGER,
        test_name     TEXT,
        audience      TEXT,                         -- a tier name or 'All leads'
        metric        TEXT,                         -- purchase | click
        variant_key   TEXT,
        variant_label TEXT,
        subject       TEXT,
        body          TEXT,
        test_lift     REAL, test_lift_lo REAL, test_lift_hi REAL,
        check_share   REAL,
        status        TEXT DEFAULT 'active',        -- active | confirmed | reverted
        adopted_at    TEXT,
        decided_at    TEXT,
        reason        TEXT,
        check_json    TEXT,
        simulated     INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE copilot_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        asked_at    TEXT DEFAULT {NOW},
        question    TEXT,
        intent      TEXT,
        tools_json  TEXT,
        answer      TEXT,
        drafts_json TEXT,
        used_gemini INTEGER DEFAULT 0
    )""",
    # marketing: campaigns, A/B tests, the WhatsApp log
    f"""CREATE TABLE campaign_schedules (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT,
        tier          TEXT,
        subject       TEXT,
        body          TEXT,
        scheduled_at  TEXT,
        status        TEXT DEFAULT 'scheduled',     -- draft | scheduled | sending | sent | sent_with_errors
        holdout_share REAL DEFAULT 0.1,
        sent          INTEGER DEFAULT 0,
        sent_at       TEXT,
        recipients    INTEGER DEFAULT 0,
        held_out      INTEGER DEFAULT 0,
        error         TEXT,
        simulated     INTEGER DEFAULT 0,
        created_at    TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE ab_tests (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        name                TEXT,
        tier                TEXT,
        hypothesis          TEXT,
        metric              TEXT DEFAULT 'purchase',  -- purchase | click
        control_share       REAL DEFAULT 0,
        variants_json       TEXT,
        subject_a           TEXT, body_a TEXT, subject_b TEXT, body_b TEXT,
        mde                 REAL,
        planned_per_arm     INTEGER,
        status              TEXT DEFAULT 'draft',     -- draft | sending | sent
        sent_at             TEXT,
        started_at          TEXT,
        applied_campaign_id INTEGER,
        simulated           INTEGER DEFAULT 0,
        created_at          TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE sms_queue (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER,
        lead_id    INTEGER,
        phone      TEXT,
        message    TEXT,
        channel    TEXT DEFAULT 'whatsapp',
        status     TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT {NOW}
    )""",
    # the team
    f"""CREATE TABLE team_members (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        name                 TEXT NOT NULL,
        email                TEXT UNIQUE NOT NULL,
        role                 TEXT NOT NULL DEFAULT 'counsellor',   -- admin | marketing | counsellor
        password_hash        TEXT,                                 -- NULL for the owner (password in .env)
        is_owner             INTEGER DEFAULT 0,
        active               INTEGER DEFAULT 1,
        takes_new_leads      INTEGER DEFAULT 1,
        must_change_password INTEGER DEFAULT 0,
        created_at           TEXT DEFAULT {NOW},
        last_login_at        TEXT,
        password_changed_at  TEXT
    )""",
    """CREATE TABLE login_attempts (
        email           TEXT PRIMARY KEY,           -- 'crm:<address>' or 'learner:<address>'
        failures        INTEGER DEFAULT 0,
        first_failed_at TEXT,
        locked_until    TEXT
    )""",
    f"""CREATE TABLE lead_owners (
        user_id     INTEGER PRIMARY KEY REFERENCES users(id),
        member_id   INTEGER NOT NULL,
        assigned_at TEXT DEFAULT {NOW},
        how         TEXT                            -- auto | manual | claimed
    )""",
    f"""CREATE TABLE lead_notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER REFERENCES users(id),
        member_id  INTEGER,
        author     TEXT,
        kind       TEXT DEFAULT 'note',             -- note | call | whatsapp | meeting | callback | status | consent
        text       TEXT NOT NULL,
        created_at TEXT DEFAULT {NOW}
    )""",
    f"""CREATE TABLE audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        at          TEXT DEFAULT {NOW},
        member_id   INTEGER,
        member_name TEXT,
        role        TEXT,
        action      TEXT NOT NULL,
        target_type TEXT,
        target_id   INTEGER,
        detail      TEXT
    )""",
    f"""CREATE TABLE app_settings (
        key        TEXT PRIMARY KEY,
        value      TEXT,
        updated_at TEXT DEFAULT {NOW}
    )""",
]

INDEXES = [
    "CREATE INDEX idx_events_user ON behaviour_events(user_id, event_type)",
    "CREATE INDEX idx_events_created ON behaviour_events(created_at)",
    "CREATE INDEX idx_snap_user ON score_snapshots(user_id, created_at)",
    "CREATE INDEX idx_leads_user ON leads(user_id)",
    "CREATE INDEX idx_purchases_user ON purchases(user_id)",
    "CREATE INDEX idx_sessions_user ON user_sessions(user_id)",
    "CREATE INDEX idx_emails_user ON email_sends(user_id)",
    "CREATE INDEX idx_emails_campaign ON email_sends(campaign_id)",
    "CREATE INDEX idx_emails_ab ON email_sends(ab_test_id)",
    "CREATE INDEX idx_nba_user ON nba_decisions(user_id, created_at)",
    "CREATE INDEX idx_nba_created ON nba_decisions(created_at)",
    "CREATE INDEX idx_coupons_user ON coupons_issued(user_id)",
    "CREATE INDEX idx_tasks_user ON sales_tasks(user_id)",
    "CREATE INDEX idx_tasks_status ON sales_tasks(status, created_at)",
    "CREATE INDEX idx_assign_exp ON experiment_assignments(experiment_type, experiment_id)",
    "CREATE INDEX idx_assign_user ON experiment_assignments(user_id)",
    "CREATE INDEX idx_callbacks_user ON callback_requests(user_id)",
    "CREATE INDEX idx_history_user ON lead_score_history(user_id)",
    "CREATE INDEX idx_owner_member ON lead_owners(member_id)",
    "CREATE INDEX idx_notes_user ON lead_notes(user_id, created_at)",
    "CREATE INDEX idx_audit_at ON audit_log(at)",
    "CREATE INDEX idx_audit_target ON audit_log(target_type, target_id)",
    "CREATE INDEX idx_otp_email ON otp_tokens(email, purpose)",
]

ALL_TABLES = [t.split("(")[0].split()[-1] for t in TABLES]


def upgrade() -> None:
    for sql in TABLES + INDEXES:
        op.execute(sql)


def downgrade() -> None:
    for name in reversed(ALL_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {name}")
