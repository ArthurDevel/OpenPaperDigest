"""Add signals JSONB column to papers and update match_papers_by_embedding RPC.

Revision ID: 20260311_000032
Revises: 20260306_000031
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260311_000032'
down_revision = '20260306_000031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add signals JSONB column to papers table and update match_papers_by_embedding
    RPC to include it in results.

    The signals column stores pre-computed scoring signals as JSON, e.g.:
    { "max_author_h_index": 42 }
    """
    connection = op.get_bind()

    # Add signals column
    connection.execute(sa.text(
        "ALTER TABLE papers ADD COLUMN IF NOT EXISTS signals JSONB"
    ))

    # Update match_papers_by_embedding to return signals
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
            finished_at timestamptz,
            embedding vector(1536),
            external_popularity_signals jsonb,
            signals jsonb,
            similarity float
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                p.paper_uuid, p.title, p.authors,
                p.finished_at, p.embedding, p.external_popularity_signals,
                p.signals,
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
    """Remove signals column and revert match_papers_by_embedding RPC."""
    connection = op.get_bind()

    # Revert RPC to version without signals
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
            finished_at timestamptz,
            embedding vector(1536),
            external_popularity_signals jsonb,
            similarity float
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                p.paper_uuid, p.title, p.authors,
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

    op.drop_column('papers', 'signals')
