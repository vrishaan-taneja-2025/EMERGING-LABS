"""Add DI Snapshot table

Revision ID: 0002_add_di_snapshot
Revises: 0001_initial
Create Date: 2025-12-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_di_snapshot"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "di_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("di_id", sa.Integer, sa.ForeignKey("daily_inspections.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),

        sa.UniqueConstraint("di_id", name="uq_di_snapshot_di_id")
    )


def downgrade():
    op.drop_table("di_snapshots")
