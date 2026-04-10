"""Add research frontiers tables for autoresearch hackathon.

Revision ID: 20260409_000044
Revises: 20260409_000040
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260409_000044'
down_revision = '20260409_000040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'autoresearchhackathon_research_themes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text(), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'autoresearchhackathon_paper_themes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('paper_id', sa.Integer(), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('theme_id', sa.Integer(), sa.ForeignKey('autoresearchhackathon_research_themes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        'ix_paper_themes_theme_week',
        'autoresearchhackathon_paper_themes',
        ['theme_id', 'week'],
    )
    op.create_index(
        'ix_paper_themes_paper_id',
        'autoresearchhackathon_paper_themes',
        ['paper_id'],
    )


def downgrade() -> None:
    op.drop_table('autoresearchhackathon_paper_themes')
    op.drop_table('autoresearchhackathon_research_themes')
