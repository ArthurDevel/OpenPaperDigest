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
    op.execute("ALTER TABLE papers MODIFY COLUMN arxiv_id VARCHAR(64) NULL")
    op.execute("ALTER TABLE papers ADD COLUMN content_hash VARCHAR(64) NULL")
    op.execute("ALTER TABLE papers ADD COLUMN pdf_url VARCHAR(512) NULL")


def downgrade() -> None:
    """
    Revert changes for non-arXiv paper support.
    """
    op.execute("ALTER TABLE papers DROP COLUMN pdf_url")
    op.execute("ALTER TABLE papers DROP COLUMN content_hash")
    op.execute("ALTER TABLE papers MODIFY COLUMN arxiv_id VARCHAR(64) NOT NULL")
