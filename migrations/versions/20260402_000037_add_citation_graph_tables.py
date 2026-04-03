"""Add citation graph tables and pagerank columns.

Creates the paper_citations table for storing citation edges between papers,
and adds pagerank JSONB columns to the papers and authors tables.

- paper_citations stores (source_s2_id, cited_s2_id) edges with is_influential flag
- Sentinel rows (cited_s2_id = NULL) mark papers whose references have been fetched but were empty
- Two partial unique indexes handle NULL sentinel uniqueness (Postgres treats NULL != NULL)
- pagerank JSONB on papers/authors stores computed PageRank scores and percentiles

Revision ID: 20260402_000037
Revises: 20250824_000018
Create Date: 2026-04-02 00:00:37.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '20260402_000037'
down_revision: Union[str, None] = '20260324_000036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the paper_citations table
    op.create_table(
        'paper_citations',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('source_s2_id', sa.String(64), nullable=False),
        sa.Column('cited_s2_id', sa.String(64), nullable=True),
        sa.Column('is_influential', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Regular indexes for fast lookups
    op.create_index('ix_paper_citations_source_s2_id', 'paper_citations', ['source_s2_id'])
    op.create_index('ix_paper_citations_cited_s2_id', 'paper_citations', ['cited_s2_id'])

    # Partial unique index: prevents duplicate citation edges (where cited_s2_id is not null)
    op.execute(
        "CREATE UNIQUE INDEX uq_paper_citations_edge "
        "ON paper_citations (source_s2_id, cited_s2_id) "
        "WHERE cited_s2_id IS NOT NULL"
    )

    # Partial unique index: prevents duplicate sentinel rows (where cited_s2_id is null)
    op.execute(
        "CREATE UNIQUE INDEX uq_paper_citations_sentinel "
        "ON paper_citations (source_s2_id) "
        "WHERE cited_s2_id IS NULL"
    )

    # Add pagerank JSONB column to papers and authors
    op.add_column('papers', sa.Column('pagerank', JSONB(), nullable=True))
    op.add_column('authors', sa.Column('pagerank', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('authors', 'pagerank')
    op.drop_column('papers', 'pagerank')
    op.drop_table('paper_citations')
