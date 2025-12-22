from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BIGINT


# revision identifiers, used by Alembic.
revision = '20251222_000025'
down_revision = '20250120_000024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create arxiv_papers table for storing discovered arXiv papers
    with metadata, author credibility scores, and S2 enrichment data.
    """
    op.create_table(
        'arxiv_papers',
        sa.Column('id', BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column('arxiv_id', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('primary_category', sa.String(32), nullable=True),
        sa.Column('categories', sa.JSON(), nullable=True),
        sa.Column('authors', sa.JSON(), nullable=True),
        sa.Column('semantic_scholar_id', sa.String(64), nullable=True),
        sa.Column('citation_count', sa.Integer(), nullable=True),
        sa.Column('influential_citation_count', sa.Integer(), nullable=True),
        sa.Column('embedding_model', sa.String(32), nullable=True),
        sa.Column('embedding_vector', sa.JSON(), nullable=True),
        sa.Column('avg_author_h_index', sa.Float(), nullable=True),
        sa.Column('avg_author_citations_per_paper', sa.Float(), nullable=True),
        sa.Column('total_author_h_index', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('arxiv_id', name='uq_arxiv_papers_arxiv_id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_arxiv_papers_published_at', 'arxiv_papers', ['published_at'])
    op.create_index('ix_arxiv_papers_primary_category', 'arxiv_papers', ['primary_category'])
    op.create_index('ix_arxiv_papers_avg_author_h_index', 'arxiv_papers', ['avg_author_h_index'])


def downgrade() -> None:
    """Drop arxiv_papers table."""
    op.drop_index('ix_arxiv_papers_avg_author_h_index', table_name='arxiv_papers')
    op.drop_index('ix_arxiv_papers_primary_category', table_name='arxiv_papers')
    op.drop_index('ix_arxiv_papers_published_at', table_name='arxiv_papers')
    op.drop_table('arxiv_papers')
