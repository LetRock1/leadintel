"""Discount money as a priced resource, and where each coupon came from.

nba_decisions.coupon_value   what the best allowed coupon adds over the best step without a coupon (rupees of profit)
nba_decisions.coupon_cost    its expected discount: chance to buy with it x course fee x discount
nba_decisions.budget_price   the price of a rupee of discount when the decision was made (none without a budget)
coupons_issued.expected_cost the expected discount of the coupon when it was issued (counts against the budget while
                             the coupon is open)
coupons_issued.source        next-best-action | manual | ab_test | history

Revision ID: 0005_money
Revises: 0004_anchored_update
Create Date: 2026-10-25
"""

from __future__ import annotations

from alembic import op

revision = "0005_money"
down_revision = "0004_anchored_update"
branch_labels = None
depends_on = None

COLUMNS = {
    "nba_decisions": [("coupon_value", "REAL"), ("coupon_cost", "REAL"), ("budget_price", "REAL")],
    "coupons_issued": [("expected_cost", "REAL"), ("source", "TEXT")],
}


def upgrade() -> None:
    for table, cols in COLUMNS.items():
        for name, kind in cols:
            op.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def downgrade() -> None:
    for table, cols in COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for name, _ in reversed(cols):
                batch.drop_column(name)
