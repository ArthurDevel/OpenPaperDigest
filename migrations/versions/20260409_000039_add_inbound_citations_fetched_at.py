"""Add inbound_citations_fetched_at to papers.

Revision ID: 20260409_000039
Revises: 20260409_000038
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260409_000039'
down_revision = '20260409_000038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('papers', sa.Column('inbound_citations_fetched_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('papers', 'inbound_citations_fetched_at')
