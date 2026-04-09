"""Add published_at to papers.

Revision ID: 20260409_000040
Revises: 20260409_000039
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260409_000040'
down_revision = '20260409_000039'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('papers', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('papers', 'published_at')
