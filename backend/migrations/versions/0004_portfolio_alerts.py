"""paper portfolios, transactions, alerts and alert events

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("owner", "name", name="uq_portfolios_owner_name"),
    )
    op.create_index("ix_portfolios_owner", "portfolios", ["owner"])
    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("portfolio_id", sa.Integer, sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("symbol", sa.String(16)),
        sa.Column("quantity", sa.Numeric(24, 6), nullable=False, server_default="0"),
        sa.Column("price", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("fee", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("note", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("kind in ('deposit','withdraw','buy','sell')", name="ck_txn_kind"),
        sa.CheckConstraint("quantity >= 0 and price >= 0 and fee >= 0 and amount >= 0", name="ck_txn_nonneg"),
    )
    op.create_index("ix_portfolio_txn_pf_day", "portfolio_transactions", ["portfolio_id", "day"])
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("threshold", sa.Float, nullable=False, server_default="0"),
        sa.Column("window", sa.Integer),
        sa.Column("cooldown_days", sa.Integer, nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(200), nullable=False, server_default=""),
        sa.Column("last_observed_day", sa.Date),
        sa.Column("last_condition", sa.Boolean),
        sa.Column("fired_in_episode", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_fired_day", sa.Date),
        sa.Column("created_day", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_alerts_owner", "alerts", ["owner"])
    op.create_index("ix_alerts_enabled", "alerts", ["enabled"])
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("alert_id", sa.Integer, sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("observed_day", sa.Date, nullable=False),
        sa.Column("observed_value", sa.Float, nullable=False),
        sa.Column("threshold", sa.Float, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_alert_events_owner", "alert_events", ["owner", "id"])
    op.create_index("ix_alert_events_alert", "alert_events", ["alert_id"])


def downgrade() -> None:
    for t in ("alert_events", "alerts", "portfolio_transactions", "portfolios"):
        op.drop_table(t)
