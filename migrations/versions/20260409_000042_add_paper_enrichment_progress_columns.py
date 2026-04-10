"""Add explicit paper enrichment progress columns.

Revision ID: 20260409_000042
Revises: 20260409_000041
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260409_000042'
down_revision = '20260409_000041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('papers', sa.Column('s2_enriched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('papers', sa.Column('s2_last_attempted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('papers', sa.Column('s2_enrichment_error', sa.Text(), nullable=True))
    op.add_column('papers', sa.Column('author_links_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('papers', sa.Column('signals_refreshed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('papers', 'signals_refreshed_at')
    op.drop_column('papers', 'author_links_synced_at')
    op.drop_column('papers', 's2_enrichment_error')
    op.drop_column('papers', 's2_last_attempted_at')
    op.drop_column('papers', 's2_enriched_at')
