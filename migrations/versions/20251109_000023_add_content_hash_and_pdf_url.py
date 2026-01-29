from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251109_000023'
down_revision = '20251006_000022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add support for non-arXiv papers.
    """
    op.alter_column('papers', 'arxiv_id', nullable=True)
    op.add_column('papers', sa.Column('content_hash', sa.String(64), nullable=True))
    op.add_column('papers', sa.Column('pdf_url', sa.String(512), nullable=True))


def downgrade() -> None:
    """
    Revert changes for non-arXiv paper support.
    """
    op.drop_column('papers', 'pdf_url')
    op.drop_column('papers', 'content_hash')
    op.alter_column('papers', 'arxiv_id', nullable=False)
