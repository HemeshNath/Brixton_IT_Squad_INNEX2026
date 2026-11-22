"""full WHOIS details in the domain cache

domain_cache gets a JSON column "details" (backend flow B3): the full WHOIS details (dates, status, name servers,
registrar, registrant / admin / tech contacts) shown to MIRA as "Domain Information". Rows without it are looked up
again.

Revision ID: b8d0f2a47c98
Revises: a7c9e1f36b87
Create Date: 2026-11-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d0f2a47c98"
down_revision: Union[str, Sequence[str], None] = "a7c9e1f36b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("domain_cache", sa.Column("details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("domain_cache", "details")
