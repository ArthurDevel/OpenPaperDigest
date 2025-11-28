from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BIGINT


# revision identifiers, used by Alembic.
revision = '20250120_000024'
down_revision = '20251109_000023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create paper_status_history table for daily cumulative status snapshots.
    """
    op.create_table(
        'paper_status_history',
        sa.Column('id', BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False, unique=True),
        sa.Column('total_count', sa.Integer(), nullable=False),
        sa.Column('failed_count', sa.Integer(), nullable=False),
        sa.Column('processed_count', sa.Integer(), nullable=False),
        sa.Column('not_started_count', sa.Integer(), nullable=False),
        sa.Column('processing_count', sa.Integer(), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('date', name='uq_paper_status_history_date'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_paper_status_history_date', 'paper_status_history', ['date'])


def downgrade() -> None:
    """
    Drop paper_status_history table.
    """
    op.drop_index('ix_paper_status_history_date', table_name='paper_status_history')
    op.drop_table('paper_status_history')

