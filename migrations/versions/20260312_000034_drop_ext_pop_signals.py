"""Drop external_popularity_signals column from papers table.

Run AFTER code changes are deployed and verified. The column is no longer
read or written by any code path.

Revision ID: 20260312_000034
Revises: 20260312_000033
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260312_000034'
down_revision = '20260312_000033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the external_popularity_signals column."""
    op.drop_column('papers', 'external_popularity_signals')


def downgrade() -> None:
    """Re-add external_popularity_signals column (no data restoration -- lossy)."""
    op.add_column('papers', sa.Column('external_popularity_signals', sa.JSON(), nullable=True))
