"""Consolidate external_popularity_signals into signals JSONB column.

Migrates HF upvotes, sources, and fetch_info from the external_popularity_signals
JSON array into the flat signals dict. Does NOT drop the old column (safe for rolling deploys).

Revision ID: 20260312_000033
Revises: 20260311_000032
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260312_000033'
down_revision = '20260311_000032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    1) Migrate data from external_popularity_signals array into signals dict.
    2) Update match_papers_by_embedding RPC to remove external_popularity_signals.
    """
    connection = op.get_bind()

    # Migrate data: iterate per-element to handle papers with multiple sources
    connection.execute(sa.text("""
        DO $$
        DECLARE
          r RECORD;
        BEGIN
          FOR r IN
            SELECT p.id, elem
            FROM papers p,
                 jsonb_array_elements(p.external_popularity_signals::jsonb) AS elem
            WHERE p.external_popularity_signals IS NOT NULL
              AND jsonb_typeof(p.external_popularity_signals::jsonb) = 'array'
          LOOP
            UPDATE papers
            SET signals = COALESCE(signals, '{}'::jsonb)
              -- Append source to sources array
              || jsonb_build_object('sources',
                   COALESCE(signals->'sources', '[]'::jsonb) || to_jsonb((r.elem->>'source')::text))
              -- Add source-prefixed fetch_info and values
              || CASE
                   WHEN r.elem->>'source' IN ('HuggingFace', 'HuggingFaceTrending')
                     THEN jsonb_strip_nulls(jsonb_build_object(
                       'hf_upvotes', (r.elem->'values'->>'upvotes')::int,
                       'hf_github_stars', (r.elem->'values'->>'github_stars')::int,
                       'hf_fetch_info', r.elem->'fetch_info'
                     ))
                   WHEN r.elem->>'source' = 'AlphaXiv'
                     THEN jsonb_build_object('alphaxiv_fetch_info', r.elem->'fetch_info')
                   WHEN r.elem->>'source' = 'GoogleResearch'
                     THEN jsonb_build_object('google_fetch_info', r.elem->'fetch_info')
                   WHEN r.elem->>'source' = 'MicrosoftResearch'
                     THEN jsonb_build_object('microsoft_fetch_info', r.elem->'fetch_info')
                   WHEN r.elem->>'source' = 'DeepMindResearch'
                     THEN jsonb_build_object('deepmind_fetch_info', r.elem->'fetch_info')
                   WHEN r.elem->>'source' = 'NvidiaResearch'
                     THEN jsonb_build_object('nvidia_fetch_info', r.elem->'fetch_info')
                   ELSE '{}'::jsonb
                 END
            WHERE id = r.id;
          END LOOP;
        END $$;
    """))

    # Drop and recreate RPC (return type changed, CREATE OR REPLACE cannot handle that)
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


def downgrade() -> None:
    """Restore RPC with external_popularity_signals, clear migrated keys from signals."""
    connection = op.get_bind()

    # Drop and recreate RPC (return type changes back)
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

    # Clear migrated keys from signals (preserve max_author_h_index)
    connection.execute(sa.text("""
        UPDATE papers
        SET signals = signals
            - 'sources'
            - 'hf_upvotes'
            - 'hf_github_stars'
            - 'hf_fetch_info'
            - 'alphaxiv_fetch_info'
            - 'google_fetch_info'
            - 'microsoft_fetch_info'
            - 'deepmind_fetch_info'
            - 'nvidia_fetch_info'
        WHERE signals IS NOT NULL;
    """))
