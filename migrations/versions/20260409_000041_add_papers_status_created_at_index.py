"""Add composite index on papers(status, created_at DESC) for job claiming.

The _claim_next_job query does:
  SELECT id FROM papers WHERE status = 'not_started' ORDER BY created_at DESC
  LIMIT 1 FOR UPDATE SKIP LOCKED

Without this index, Postgres does a seq scan + sort on every call. With 500
sequential calls per DAG run this exhausts the Supabase Disk IO Budget.

Revision ID: 20260409_000041
Revises: 20260409_000040
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260409_000041'
down_revision = '20260409_000040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'idx_papers_status_created_at',
        'papers',
        ['status', sa.text('created_at DESC')],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_papers_status_created_at', table_name='papers')
