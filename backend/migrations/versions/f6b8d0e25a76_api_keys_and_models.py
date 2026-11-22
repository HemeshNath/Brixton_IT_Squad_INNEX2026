"""api keys and AI model versions

New tables (Phase 10A step A5): api_keys (encrypted OTX / WHOIS keys set in the admin panel), model_tests (test runs
of a model version on the data set), model_choices (which approved model version is in use).
Row Level Security on in Supabase/Postgres, no public policies.

Revision ID: f6b8d0e25a76
Revises: e5a7c9d14f65
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6b8d0e25a76"
down_revision: Union[str, Sequence[str], None] = "e5a7c9d14f65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("encrypted", sa.Text(), nullable=False),
        sa.Column("last4", sa.String(length=8), nullable=False),
        sa.Column("tested_ok", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        "model_tests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("started_by", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_tests_version_id"), "model_tests", ["version_id"], unique=False)
    op.create_table(
        "model_choices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("chosen_by", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    if op.get_context().dialect.name == "postgresql":
        for table in ("api_keys", "model_tests", "model_choices"):
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("model_choices")
    op.drop_index(op.f("ix_model_tests_version_id"), table_name="model_tests")
    op.drop_table("model_tests")
    op.drop_table("api_keys")
