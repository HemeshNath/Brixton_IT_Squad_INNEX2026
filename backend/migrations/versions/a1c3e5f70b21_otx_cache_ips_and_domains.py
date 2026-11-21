"""otx cache for ips and domains

Replaces the (still empty) otx_cache table: key is now "ip:<address>" or "domain:<name>"
(up to 270 chars, domains can be 253), plus kind, whitelisted flag and an index on checked_at
for the daily OTX call limit. Keeps Row Level Security on in Supabase/Postgres.

Revision ID: a1c3e5f70b21
Revises: 5fd41bb61e2c
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f70b21"
down_revision: Union[str, Sequence[str], None] = "5fd41bb61e2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls_on(table: str) -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def upgrade() -> None:
    op.drop_table("otx_cache")
    op.create_table(
        "otx_cache",
        sa.Column("indicator", sa.String(length=270), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("pulse_count", sa.Integer(), nullable=False),
        sa.Column("whitelisted", sa.Boolean(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("indicator"),
    )
    with op.batch_alter_table("otx_cache", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_otx_cache_checked_at"), ["checked_at"], unique=False)
    _rls_on("otx_cache")


def downgrade() -> None:
    op.drop_table("otx_cache")
    op.create_table(
        "otx_cache",
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("pulse_count", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ip"),
    )
    _rls_on("otx_cache")
