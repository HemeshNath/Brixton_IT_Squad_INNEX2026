"""editable lists (official domains, trusted senders, block lists)

New table list_entries (Phase 10A step A6): admin panel additions to the trusted lists of trusted.json, switched-off
built-in entries, and the block lists (domains, senders). Row Level Security on in Supabase/Postgres.

Revision ID: a7c9e1f36b87
Revises: f6b8d0e25a76
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1f36b87"
down_revision: Union[str, Sequence[str], None] = "f6b8d0e25a76"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "list_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("list", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list", "value", name="uq_list_entries_list_value"),
    )
    op.create_index(op.f("ix_list_entries_list"), "list_entries", ["list"], unique=False)
    if op.get_context().dialect.name == "postgresql":
        op.execute('ALTER TABLE "list_entries" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_index(op.f("ix_list_entries_list"), table_name="list_entries")
    op.drop_table("list_entries")
