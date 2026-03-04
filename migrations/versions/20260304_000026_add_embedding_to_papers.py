from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260304_000026'
down_revision = '20260304_000025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add pgvector embedding column to papers table.

    - Enables the pgvector extension (idempotent).
    - Adds a vector(1536) column for storing paper embeddings.
    - Creates an HNSW index for fast approximate nearest neighbor search.
    - Creates the match_papers_by_embedding Postgres function for ANN queries.
    """
    connection = op.get_bind()
    connection.execute(sa.text("SET statement_timeout = '300s'"))

    # Enable pgvector extension
    connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Add embedding column as vector(1536) directly via raw SQL
    # (Alembic does not natively understand the pgvector type)
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    ))

    # Create HNSW index for cosine similarity search
    connection.execute(sa.text(
        "CREATE INDEX ix_papers_embedding ON papers USING hnsw (embedding vector_cosine_ops)"
    ))

    # Create match_papers_by_embedding function for ANN retrieval
    connection.execute(sa.text("""
        CREATE OR REPLACE FUNCTION match_papers_by_embedding(
            query_embedding vector(1536),
            match_count int DEFAULT 20,
            exclude_uuids text[] DEFAULT '{}'
        )
        RETURNS TABLE (
            paper_uuid text,
            title text,
            authors text,
            thumbnail_data_url text,
            finished_at timestamptz,
            embedding vector(1536),
            external_popularity_signals jsonb,
            similarity float
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                p.paper_uuid, p.title, p.authors, p.thumbnail_data_url,
                p.finished_at, p.embedding, p.external_popularity_signals,
                1.0 - (p.embedding <=> query_embedding) AS similarity
            FROM papers p
            WHERE p.status = 'completed'
                AND p.embedding IS NOT NULL
                AND p.paper_uuid != ALL(exclude_uuids)
            ORDER BY p.embedding <=> query_embedding
            LIMIT match_count;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """))


def downgrade() -> None:
    """
    Remove embedding column, HNSW index, and match function.
    """
    connection = op.get_bind()
    connection.execute(sa.text("DROP FUNCTION IF EXISTS match_papers_by_embedding"))
    connection.execute(sa.text("DROP INDEX IF EXISTS ix_papers_embedding"))
    op.drop_column('papers', 'embedding')
