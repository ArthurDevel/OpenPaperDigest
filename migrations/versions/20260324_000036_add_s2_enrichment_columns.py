"""Add S2 enrichment columns to papers table.

Adds 6 new columns for Semantic Scholar paper metadata:
- s2_ids (JSONB): All S2 identifiers
- s2_metrics (JSONB): Citation counts
- classification (JSONB): ArXiv categories + S2 fields of study
- publication_info (JSONB): Venue, journal, dates, open access info
- s2_tldr (TEXT): S2 model-generated one-line summary
- s2_embedding (vector(768)): SPECTER v2 embedding with HNSW index

Revision ID: 20260324_000036
Revises: 20260312_000035
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260324_000036'
down_revision = '20260312_000035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SET statement_timeout = '300s'"))

    # Add JSONB columns
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS s2_ids jsonb"
    ))
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS s2_metrics jsonb"
    ))
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS classification jsonb"
    ))
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS publication_info jsonb"
    ))
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS s2_tldr text"
    ))
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS s2_embedding vector(768)"
    ))

    # Create HNSW index for cosine similarity search on SPECTER v2 embeddings
    connection.execute(sa.text(
        "CREATE INDEX ix_papers_s2_embedding ON papers USING hnsw (s2_embedding vector_cosine_ops)"
    ))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_papers_s2_embedding"))
    op.drop_column('papers', 's2_embedding')
    op.drop_column('papers', 's2_tldr')
    op.drop_column('papers', 'publication_info')
    op.drop_column('papers', 'classification')
    op.drop_column('papers', 's2_metrics')
    op.drop_column('papers', 's2_ids')
