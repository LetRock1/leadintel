"""Capacity-aware next-best-action: what a call slot was worth when each decision was made.

Adds to every next-best-action decision the price of a call slot at that moment and the call's advantage over the
best step that needs no call, and keeps a log of the slot prices the CRM worked out (app.ml.capacity).

Revision ID: 0002_capacity_pricing
Revises: 0001_initial_schema
Create Date: 2026-10-17
"""
from __future__ import annotations

from alembic import op

revision = "0002_capacity_pricing"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE nba_decisions ADD COLUMN slot_price REAL")    # price of one call slot (INR), NULL = no call possible
    op.execute("ALTER TABLE nba_decisions ADD COLUMN call_value REAL")    # call's extra profit over the best non-call step
    op.execute("""CREATE TABLE call_slot_prices (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        computed_at    TEXT DEFAULT (datetime('now','localtime')),
        price          REAL NOT NULL,                -- INR a call must add, beyond the best step without a call
        policy         TEXT NOT NULL,                -- priced | fcfs
        capacity       INTEGER NOT NULL,             -- calls per day
        lookback_days  INTEGER NOT NULL,
        days_seen      INTEGER NOT NULL,             -- days with decisions in the look-back window
        candidates     INTEGER NOT NULL,             -- decisions where a call was possible
        per_day        REAL,                         -- of which worth calling (value > 0), per day
        note           TEXT
    )""")
    op.execute("CREATE INDEX idx_slot_prices_at ON call_slot_prices(computed_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS call_slot_prices")
    with op.batch_alter_table("nba_decisions") as batch:
        batch.drop_column("call_value")
        batch.drop_column("slot_price")
