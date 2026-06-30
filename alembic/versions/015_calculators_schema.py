"""Create calculators schema and core tables

Revision ID: 015_calculators_schema
Revises: 014_img_columns
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "015_calculators_schema"
down_revision = "014_img_columns"
branch_labels = None
depends_on = None

SCHEMA = "calculators"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "specialties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "calculator_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("specialty_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.specialties.id"), nullable=False),
        sa.Column("slug", sa.String(150), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("engine_type", sa.String(20), nullable=False, server_default="formula"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_calculator_definitions_specialty_status",
        "calculator_definitions",
        ["specialty_id", "status"],
        schema=SCHEMA,
    )

    op.create_table(
        "calculator_fields",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "calculator_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.calculator_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("field_type", sa.String(30), nullable=False),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("calculator_id", "key", name="uq_calculator_fields_calculator_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "calculator_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "calculator_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.calculator_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("formula_key", sa.String(150), nullable=False),
        sa.Column("interpretation_rules", JSONB, nullable=True),
        sa.Column("clinical_reference", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("calculator_id", "version_number", name="uq_calculator_versions_calculator_version"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_calculator_versions_calculator_active",
        "calculator_versions",
        ["calculator_id", "is_active"],
        schema=SCHEMA,
    )

    op.create_table(
        "calculator_executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "calculator_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.calculator_definitions.id"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.calculator_versions.id"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("public.users.id"), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("public.company.id"), nullable=True),
        sa.Column("interaction_id", UUID(as_uuid=True), sa.ForeignKey("public.interactions.id"), nullable=True),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("interpretation", sa.Text(), nullable=True),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_calculator_executions_user_createdat",
        "calculator_executions",
        ["user_id", "createdat"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_calculator_executions_calculator_user",
        "calculator_executions",
        ["calculator_id", "user_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("calculator_executions", schema=SCHEMA)
    op.drop_table("calculator_versions", schema=SCHEMA)
    op.drop_table("calculator_fields", schema=SCHEMA)
    op.drop_table("calculator_definitions", schema=SCHEMA)
    op.drop_table("specialties", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
