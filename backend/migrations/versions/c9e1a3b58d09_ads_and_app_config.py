"""ads and app control

New tables ads (Phase 10A step A9: home-screen banner ads with link check, dates, views and clicks) and app_config
(step A10: minimum app version, in-app notice, chat-apps switch). Row Level Security on in Supabase/Postgres.

Revision ID: c9e1a3b58d09
Revises: b8d0f2a47c98
Create Date: 2026-11-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e1a3b58d09"
down_revision: Union[str, Sequence[str], None] = "b8d0f2a47c98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("body", sa.String(length=200), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=True),
        sa.Column("image_type", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("link_check", sa.JSON(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    if op.get_context().dialect.name == "postgresql":
        op.execute('ALTER TABLE "ads" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "app_config" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("app_config")
    op.drop_table("ads")
