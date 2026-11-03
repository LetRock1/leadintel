"""Emails that could not be sent are kept as such.

email_sends.error     why the mail server did not take the email (refused login, no connection, daily limit...);
                      NULL when it was sent, or recorded without email set up (demo)
email_sends.attempts  how many times it was tried (emails that could not be sent are tried again for a day)

Revision ID: 0006_email_errors
Revises: 0005_money
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op

revision = "0006_email_errors"
down_revision = "0005_money"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE email_sends ADD COLUMN error TEXT")
    op.execute("ALTER TABLE email_sends ADD COLUMN attempts INTEGER DEFAULT 1")


def downgrade() -> None:
    with op.batch_alter_table("email_sends") as batch:
        batch.drop_column("attempts")
        batch.drop_column("error")
