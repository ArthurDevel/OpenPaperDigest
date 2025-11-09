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
    Add support for non-arXiv papers:
    - Make arxiv_id nullable
    - Add content_hash column for PDF deduplication
    - Add pdf_url column for non-arXiv papers
    """
    with op.batch_alter_table('papers') as batch_op:
        # Make arxiv_id nullable
        batch_op.alter_column(
            'arxiv_id',
            existing_type=sa.String(64),
            nullable=True
        )

        # Add content_hash column
        batch_op.add_column(
            sa.Column('content_hash', sa.String(64), nullable=True)
        )

        # Add pdf_url column
        batch_op.add_column(
            sa.Column('pdf_url', sa.String(512), nullable=True)
        )

        # Add unique constraint for content_hash
        batch_op.create_unique_constraint(
            'uq_papers_content_hash',
            ['content_hash']
        )

        # Add index for content_hash
        batch_op.create_index(
            'ix_papers_content_hash',
            ['content_hash']
        )


def downgrade() -> None:
    """
    Revert changes for non-arXiv paper support.
    """
    with op.batch_alter_table('papers') as batch_op:
        # Drop index
        batch_op.drop_index('ix_papers_content_hash')

        # Drop unique constraint
        batch_op.drop_constraint('uq_papers_content_hash', type_='unique')

        # Drop columns
        batch_op.drop_column('pdf_url')
        batch_op.drop_column('content_hash')

        # Make arxiv_id non-nullable again
        batch_op.alter_column(
            'arxiv_id',
            existing_type=sa.String(64),
            nullable=False
        )
