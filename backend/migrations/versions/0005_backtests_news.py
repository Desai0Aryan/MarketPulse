"""backtest runs and news articles

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("strategy", sa.String(24), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("result", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_backtest_runs_owner", "backtest_runs", ["owner", "id"])
    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dedup_key", sa.String(64), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("headline", sa.String(300), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("url", sa.String(1000)),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("symbols", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("sentiment_score", sa.Float),
        sa.Column("sentiment_category", sa.String(10)),
        sa.Column("sentiment_method", sa.String(40)),
        sa.Column("sentiment_version", sa.String(20)),
        sa.Column("sentiment_at", sa.DateTime(timezone=True)),
        sa.Column("simulated", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_news_published", "news_articles", ["published_at"])
    op.create_index("ix_news_source", "news_articles", ["source"])


def downgrade() -> None:
    op.drop_table("news_articles")
    op.drop_table("backtest_runs")
