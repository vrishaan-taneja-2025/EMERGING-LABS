"""Initial schema for Datacenter DI System

Revision ID: 0001_initial
Revises: 
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():

    # -------------------------
    # Roles
    # -------------------------
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(30), unique=True, nullable=False),
    )

    # -------------------------
    # Users
    # -------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id")),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # -------------------------
    # Places / Locations
    # -------------------------
    op.create_table(
        "places",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255)),
    )

    # -------------------------
    # Equipment Types
    # -------------------------
    op.create_table(
        "equipment_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )

    # -------------------------
    # Equipments
    # -------------------------
    op.create_table(
        "equipments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("equipment_type_id", sa.Integer, sa.ForeignKey("equipment_types.id")),
        sa.Column("place_id", sa.Integer, sa.ForeignKey("places.id")),
        sa.Column("status", sa.String(10)),              # ON / OFF
        sa.Column("serviceability", sa.String(5)),       # S / US
        sa.Column("remarks", sa.String(255)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # -------------------------
    # Equipment Metadata
    # -------------------------
    op.create_table(
        "equipment_metadata",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("equipment_id", sa.Integer, sa.ForeignKey("equipments.id")),
        sa.Column("pressure", sa.Float),
        sa.Column("temperature", sa.Float),
        sa.Column("humidity", sa.Float),
        sa.Column("frequency", sa.Float),
        sa.Column("voltage", sa.Float),
        sa.Column("recorded_at", sa.DateTime, server_default=sa.func.now()),
    )

    # -------------------------
    # Daily Inspection (DI)
    # -------------------------
    op.create_table(
        "daily_inspections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("inspection_date", sa.Date, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(20), server_default="submitted"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # -------------------------
    # DI Equipment Logs
    # -------------------------
    op.create_table(
        "di_equipment_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("di_id", sa.Integer, sa.ForeignKey("daily_inspections.id")),
        sa.Column("equipment_id", sa.Integer, sa.ForeignKey("equipments.id")),
        sa.Column("serviceability", sa.String(5)),
        sa.Column("remarks", sa.String(255)),
    )

    # -------------------------
    # DI Workflow / Approvals
    # -------------------------
    op.create_table(
        "di_workflow",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("di_id", sa.Integer, sa.ForeignKey("daily_inspections.id")),
        sa.Column("from_role", sa.String(30)),
        sa.Column("to_role", sa.String(30)),
        sa.Column("action", sa.String(50)),  # approved / rejected
        sa.Column("comments", sa.String(255)),
        sa.Column("acted_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("acted_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("di_workflow")
    op.drop_table("di_equipment_logs")
    op.drop_table("daily_inspections")
    op.drop_table("equipment_metadata")
    op.drop_table("equipments")
    op.drop_table("equipment_types")
    op.drop_table("places")
    op.drop_table("users")
    op.drop_table("roles")
