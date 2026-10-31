"""pipeline schema: instruments, prices, indicators, runs, checkpoints, rejections

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(12), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("sector", sa.String(64)),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("symbols", pg.JSONB, nullable=False),
        sa.Column("params", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("stats", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("events", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_runs_status_started", "ingestion_runs", ["status", "started_at"])
    op.create_table(
        "prices",
        sa.Column("instrument_id", sa.Integer, sa.ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("interval", sa.String(8), primary_key=True, server_default="1d"),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("open", sa.Numeric(18, 4), nullable=False),
        sa.Column("high", sa.Numeric(18, 4), nullable=False),
        sa.Column("low", sa.Numeric(18, 4), nullable=False),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("adj_close", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.BigInteger, nullable=False),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL")),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=NOW),
        sa.CheckConstraint("high >= low AND low > 0 AND volume >= 0", name="ck_prices_sane"),
    )
    op.create_index("ix_prices_day", "prices", ["day"])
    op.create_table(
        "indicators",
        sa.Column("instrument_id", sa.Integer, sa.ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        *[sa.Column(c, sa.Float) for c in (
            "sma20", "sma50", "sma200", "ema12", "ema26", "rsi14", "macd", "macd_signal", "macd_hist",
            "bb_lower", "bb_mid", "bb_upper", "atr14", "roc12", "vol20")],
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=NOW),
    )
    op.create_table(
        "ingestion_checkpoints",
        sa.Column("instrument_id", sa.Integer, sa.ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_day", sa.Date, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL")),
    )
    op.create_table(
        "rejected_records",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(12), nullable=False),
        sa.Column("day", sa.Date),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
        sa.Column("raw", pg.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW),
    )
    op.create_index("ix_rejected_run", "rejected_records", ["run_id"])
    op.create_index("ix_rejected_symbol_day", "rejected_records", ["symbol", "day"])


def downgrade() -> None:
    for t in ("rejected_records", "ingestion_checkpoints", "indicators", "prices", "ingestion_runs", "instruments"):
        op.drop_table(t)
