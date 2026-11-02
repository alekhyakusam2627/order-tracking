"""Initial production schema."""

from alembic import op
import sqlalchemy as sa

revision = "20261102_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processed_messages",
        sa.Column("message_sid", sa.String(length=128), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_phone", sa.String(length=64), nullable=False),
        sa.Column("tracking_number", sa.String(length=128), nullable=False),
        sa.Column("carrier", sa.String(length=64), nullable=False),
        sa.Column("item_label", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("aftership_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_phone", "tracking_number"),
    )
    op.create_index("ix_shipments_user_phone", "shipments", ["user_phone"])
    op.create_index("ix_shipments_tracking_number", "shipments", ["tracking_number"])


def downgrade() -> None:
    op.drop_index("ix_shipments_tracking_number", table_name="shipments")
    op.drop_index("ix_shipments_user_phone", table_name="shipments")
    op.drop_table("shipments")
    op.drop_table("processed_messages")
