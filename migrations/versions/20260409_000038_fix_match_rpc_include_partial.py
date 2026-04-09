"""Fix match_papers_by_embedding RPC to include partially_completed papers.

Migration 20260311_000032 accidentally reverted the status filter from
IN ('completed', 'partially_completed') back to = 'completed' when it
recreated the RPC to add the signals column. Migration 20260312_000035
carried forward the same bug. This restores the intended filter so that
partially_completed papers appear in ANN similarity search results.

Revision ID: 20260409_000038
Revises: 20260402_000037
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260409_000038'
down_revision = '20260402_000037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Recreate RPC with status IN ('completed', 'partially_completed')."""
    connection = op.get_bind()

    connection.execute(sa.text(
        "DROP FUNCTION IF EXISTS match_papers_by_embedding(vector, int, text[])"
    ))
    connection.execute(sa.text("""
        CREATE FUNCTION match_papers_by_embedding(
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
            signals jsonb,
            similarity float
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                p.paper_uuid::text, p.title::text, p.authors,
                p.finished_at::timestamptz, p.embedding,
                p.signals,
                (1.0 - (p.embedding <=> query_embedding))::double precision AS similarity
            FROM papers p
            WHERE p.status IN ('completed', 'partially_completed')
                AND p.embedding IS NOT NULL
                AND p.paper_uuid != ALL(exclude_uuids)
            ORDER BY p.embedding <=> query_embedding
            LIMIT match_count;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """))


def downgrade() -> None:
    """Revert to completed-only filter."""
    connection = op.get_bind()

    connection.execute(sa.text(
        "DROP FUNCTION IF EXISTS match_papers_by_embedding(vector, int, text[])"
    ))
    connection.execute(sa.text("""
        CREATE FUNCTION match_papers_by_embedding(
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
            signals jsonb,
            similarity float
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                p.paper_uuid::text, p.title::text, p.authors,
                p.finished_at::timestamptz, p.embedding,
                p.signals,
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
