"""The Overview's "emails, clicks and purchases after a click": a purchase counts only after a click and within the
outcome window (checked in one query since v7.1, so the page stays fast on a busy install)."""

from __future__ import annotations

from datetime import datetime, timedelta

from support import unique_email

TS = "%Y-%m-%d %H:%M:%S"


def test_a_purchase_counts_only_after_a_click_and_inside_the_window(starting_models):
    from app import db
    from app.services import analytics

    def campaign():
        return analytics.campaign_influence()["campaign_influence"].get(
            "campaign", {"emails_sent": 0, "clicks": 0, "influenced_conversions": 0}
        )

    before = campaign()
    clicked = datetime(2026, 3, 2, 10, 0, 0)
    window = analytics.WINDOW_DAYS

    def learner(bought_days_after_click: float | None) -> int:
        uid = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, 'x')", ("Influence test", unique_email())
        )
        if bought_days_after_click is not None:
            db.execute(
                """INSERT INTO purchases (user_id, course_slug, course_title, price_paid, purchased_at)
                   VALUES (?, 'test-course', 'Test course', 1000, ?)""",
                (uid, (clicked + timedelta(days=bought_days_after_click)).strftime(TS)),
            )
        return uid

    def send(uid: int, clicks: int) -> None:
        db.execute(
            """INSERT INTO email_sends (user_id, campaign_name, sent_at, click_count, first_clicked_at)
               VALUES (?, 'Influence test', ?, ?, ?)""",
            (uid, (clicked - timedelta(hours=2)).strftime(TS), clicks, clicked.strftime(TS) if clicks else None),
        )

    send(learner(1), clicks=1)  # clicked, bought the next day: counts
    send(learner(window + 1), clicks=2)  # clicked, bought after the window: a click, not a purchase after it
    send(learner(-1), clicks=1)  # bought the day before the click: not after it
    send(learner(1), clicks=0)  # bought without clicking: an email sent, nothing more

    after = campaign()
    assert after["emails_sent"] - before["emails_sent"] == 4
    assert after["clicks"] - before["clicks"] == 3
    assert after["influenced_conversions"] - before["influenced_conversions"] == 1
