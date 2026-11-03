"""One-time codes are stored as keyed hashes, and simulated learners get an inbox.

A sign-up or password-reset code is kept only as HMAC-SHA256 of the purpose, the address and the code, keyed with the
server's signing secret (app.services.learner_auth), so a copy of the database does not reveal a live code. Codes made
before this version cannot be checked any more and are marked used; asking for a new code takes one click.

Simulated learners (the reserved .test domain) are never mailed. Their account emails are put in simulated_inbox,
where the simulator reads its code the way a person reads their inbox.

Revision ID: 0003_hashed_codes
Revises: 0002_capacity_pricing
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_hashed_codes"
down_revision = "0002_capacity_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE otp_tokens SET used=1")
    with op.batch_alter_table("otp_tokens") as batch:
        batch.add_column(sa.Column("code_hash", sa.Text(), nullable=True))  # HMAC-SHA256, hex
        batch.drop_column("otp")
    op.execute("""CREATE TABLE simulated_inbox (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        email      TEXT NOT NULL,                       -- always on the reserved .test domain
        subject    TEXT NOT NULL,
        body       TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    op.execute("CREATE INDEX idx_simulated_inbox_email ON simulated_inbox(email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS simulated_inbox")
    op.execute("UPDATE otp_tokens SET used=1")
    with op.batch_alter_table("otp_tokens") as batch:
        batch.add_column(sa.Column("otp", sa.Text(), nullable=False, server_default=""))
        batch.drop_column("code_hash")
