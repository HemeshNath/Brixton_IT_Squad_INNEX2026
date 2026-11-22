"""app users: blocked flag and last seen time

profiles gets `blocked` (admin panel can block a user) and `last_seen_at` (last app request) - Phase 10A step A3.

Revision ID: d4f6b8c03e54
Revises: c3e5a7b92d43
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f6b8c03e54"
down_revision: Union[str, Sequence[str], None] = "c3e5a7b92d43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default fills existing rows with false (needed for NOT NULL on a table that has users)
    op.add_column("profiles", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("profiles", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.drop_column("last_seen_at")
        batch.drop_column("blocked")
