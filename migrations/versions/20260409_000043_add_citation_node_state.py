"""Add citation node state table.

Revision ID: 20260409_000043
Revises: 20260409_000042
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260409_000043'
down_revision = '20260409_000042'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'citation_node_state',
        sa.Column('s2_paper_id', sa.String(length=64), primary_key=True),
        sa.Column('paper_id', sa.BigInteger(), sa.ForeignKey('papers.id'), nullable=True),
        sa.Column('is_internal', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('hop', sa.Integer(), nullable=True),
        sa.Column('discovered_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('outbound_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('inbound_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_citation_node_state_paper_id', 'citation_node_state', ['paper_id'])
    op.create_index('ix_citation_node_state_is_internal_hop', 'citation_node_state', ['is_internal', 'hop'])
    op.create_index('ix_citation_node_state_outbound_fetched_at', 'citation_node_state', ['outbound_fetched_at'])
    op.create_index('ix_citation_node_state_inbound_fetched_at', 'citation_node_state', ['inbound_fetched_at'])


def downgrade() -> None:
    op.drop_index('ix_citation_node_state_inbound_fetched_at', table_name='citation_node_state')
    op.drop_index('ix_citation_node_state_outbound_fetched_at', table_name='citation_node_state')
    op.drop_index('ix_citation_node_state_is_internal_hop', table_name='citation_node_state')
    op.drop_index('ix_citation_node_state_paper_id', table_name='citation_node_state')
    op.drop_table('citation_node_state')
