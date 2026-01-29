from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250819_000001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'papers',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('paper_uuid', sa.String(length=36), nullable=False),
        sa.Column('arxiv_id', sa.String(length=64), nullable=False),
        sa.Column('arxiv_version', sa.String(length=10), nullable=True),
        sa.Column('arxiv_url', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('paper_uuid', name='uq_papers_paper_uuid'),
    )
    op.create_index('ix_papers_status_created', 'papers', ['status', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_papers_status_created', table_name='papers')
    op.drop_table('papers')


