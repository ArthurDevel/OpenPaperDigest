from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260305_000030'
down_revision = '20260305_000029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Update match_papers_by_embedding to remove thumbnail_data_url
    (column was dropped in 20260305_000029).
    """
    connection = op.get_bind()
    connection.execute(sa.text(
        "DROP FUNCTION IF EXISTS match_papers_by_embedding(vector, int, text[])"
    ))
    connection.execute(sa.text("""
        CREATE OR REPLACE FUNCTION match_papers_by_embedding(
            query_embedding vector(1536),
            match_count int DEFAULT 20,
            exclude_uuids text[] DEFAULT '{}'
        )
        RETURNS TABLE (
            paper_uuid varchar,
            title varchar,
            authors text,
            finished_at timestamp,
            embedding vector(1536),
            external_popularity_signals json,
            similarity double precision
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                p.paper_uuid, p.title, p.authors,
                p.finished_at, p.embedding, p.external_popularity_signals,
                (1.0 - (p.embedding <=> query_embedding))::double precision AS similarity
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
    Restore match_papers_by_embedding with thumbnail_data_url.
    """
    connection = op.get_bind()
    connection.execute(sa.text(
        "DROP FUNCTION IF EXISTS match_papers_by_embedding(vector, int, text[])"
    ))
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
