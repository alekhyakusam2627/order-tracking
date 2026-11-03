"""add WhatsApp login codes

Revision ID: 20261102_02
Revises: 20261102_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20261102_02"
down_revision = "20261102_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_codes",
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("phone"),
    )


def downgrade() -> None:
    op.drop_table("login_codes")
