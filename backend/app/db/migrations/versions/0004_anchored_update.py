"""The anchored update: each learning run records how the lead score was retrained and what the CRM's own
experiments say each step adds.

retrain_method        anchored (v7.1: each step's effect fixed at its design-based lift) | action_aware (v7.0)
anchored_* / aware_*  the two informed retraining methods side by side on the untouched control group (log-loss and
                      AUC) and on the CRM's own outcomes (log-loss); challenger_* stays the method in use
design_json           per step: the threshold contrast at next-best-action's own cut-off, the random contrasts, the
                      lift the score uses and the v7.0 model's own estimate; plus the threshold check chart

Revision ID: 0004_anchored_update
Revises: 0003_hashed_codes
Create Date: 2026-10-25
"""

from __future__ import annotations

from alembic import op

revision = "0004_anchored_update"
down_revision = "0003_hashed_codes"
branch_labels = None
depends_on = None

COLUMNS = [
    ("retrain_method", "TEXT"),
    ("anchored_true_logloss", "REAL"),
    ("anchored_true_auc", "REAL"),
    ("anchored_live_logloss", "REAL"),
    ("aware_true_logloss", "REAL"),
    ("aware_true_auc", "REAL"),
    ("aware_live_logloss", "REAL"),
    ("design_json", "TEXT"),
]


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.execute(f"ALTER TABLE learning_runs ADD COLUMN {name} {kind}")


def downgrade() -> None:
    with op.batch_alter_table("learning_runs") as batch:
        for name, _ in reversed(COLUMNS):
            batch.drop_column(name)
