"""watchlists and watchlist items

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("owner", "name", name="uq_watchlists_owner_name"),
    )
    op.create_index("ix_watchlists_owner", "watchlists", ["owner"])
    # At most one default list per owner, enforced by the database itself.
    op.create_index("uq_watchlists_one_default", "watchlists", ["owner"], unique=True, postgresql_where=sa.text("is_default"))
    op.create_table(
        "watchlist_items",
        sa.Column("watchlist_id", sa.Integer, sa.ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("instrument_id", sa.Integer, sa.ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
