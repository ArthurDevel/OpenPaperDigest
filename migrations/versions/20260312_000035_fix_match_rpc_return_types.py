"""Fix match_papers_by_embedding RPC return type mismatch.

The RETURNS TABLE declared types that don't match the actual column types:
- paper_uuid: declared text, actual varchar(36)
- title: declared text, actual varchar(512)
- finished_at: declared timestamptz, actual timestamp (without tz)
PostgreSQL refuses implicit casts inside RETURNS TABLE, causing the function
to error on every call. Fix: cast mismatched columns in the SELECT.

Revision ID: 20260312_000035
Revises: 20260312_000034
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260312_000035'
down_revision = '20260312_000034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Recreate RPC with explicit text casts on varchar columns."""
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


def downgrade() -> None:
    """Restore RPC without casts (broken state)."""
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
                p.paper_uuid, p.title, p.authors,
                p.finished_at, p.embedding,
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
