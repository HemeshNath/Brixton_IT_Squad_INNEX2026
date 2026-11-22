"""live settings versions

New table settings_versions (Phase 10A step A4): every saved version of the admin panel settings (score numbers,
time limits, on/off switches). Row Level Security on in Supabase/Postgres, no public policies.

Revision ID: e5a7c9d14f65
Revises: d4f6b8c03e54
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5a7c9d14f65"
down_revision: Union[str, Sequence[str], None] = "d4f6b8c03e54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settings_versions",
        sa.Column("number", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("restored_from", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("number"),
    )
    if op.get_context().dialect.name == "postgresql":
        op.execute('ALTER TABLE "settings_versions" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("settings_versions")
