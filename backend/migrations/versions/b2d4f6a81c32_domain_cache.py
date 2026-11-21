"""domain cache for WHOIS/RDAP domain age

New table domain_cache: registration date, expiry date and registrar per domain (Phase 5).
Row Level Security on in Supabase/Postgres, no public policies.

Revision ID: b2d4f6a81c32
Revises: a1c3e5f70b21
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a81c32"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f70b21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_cache",
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registrar", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("domain"),
    )
    if op.get_context().dialect.name == "postgresql":
        op.execute('ALTER TABLE "domain_cache" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("domain_cache")
