"""Add abstract column, authors/paper_authors tables, and update RPCs.

Revision ID: 20260306_000031
Revises: 20260305_000030
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260306_000031'
down_revision = '20260305_000030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- 1. Add abstract column to papers ----------------------------------------
    op.add_column('papers', sa.Column('abstract', sa.Text(), nullable=True))

    # -- 2. Create authors table -------------------------------------------------
    op.create_table(
        'authors',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('s2_author_id', sa.String(64), unique=True, nullable=False),
        sa.Column('name', sa.String(512), nullable=False),
        sa.Column('affiliations', sa.JSON(), nullable=True),
        sa.Column('homepage', sa.String(512), nullable=True),
        sa.Column('paper_count', sa.Integer(), nullable=True),
        sa.Column('citation_count', sa.Integer(), nullable=True),
        sa.Column('h_index', sa.Integer(), nullable=True),
        sa.Column('stats_updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
    )

    # -- 3. Create paper_authors junction table ----------------------------------
    op.create_table(
        'paper_authors',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('paper_id', sa.BigInteger(), sa.ForeignKey('papers.id'), nullable=False),
        sa.Column('author_id', sa.BigInteger(), sa.ForeignKey('authors.id'), nullable=False),
        sa.Column('author_order', sa.Integer(), nullable=False),
        sa.UniqueConstraint('paper_id', 'author_id', name='uq_paper_authors'),
        sa.Index('ix_paper_authors_paper_id', 'paper_id'),
        sa.Index('ix_paper_authors_author_id', 'author_id'),
    )

    # -- 4. Drop and recreate match_papers_by_embedding RPC ----------------------
    conn = op.get_bind()
    conn.execute(sa.text('DROP FUNCTION IF EXISTS match_papers_by_embedding(vector, int, text[])'))
    conn.execute(sa.text("""
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
            WHERE p.status IN ('completed', 'partially_completed')
                AND p.embedding IS NOT NULL
                AND p.paper_uuid != ALL(exclude_uuids)
            ORDER BY p.embedding <=> query_embedding
            LIMIT match_count;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """))

    # -- 5. Create set_paper_summary_if_null RPC ---------------------------------
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION set_paper_summary_if_null(p_paper_uuid TEXT, p_summary TEXT)
        RETURNS TABLE(was_set BOOLEAN) AS $$
        BEGIN
          UPDATE papers
          SET summaries = COALESCE(summaries, '{}'::jsonb) || jsonb_build_object('five_minute_summary', p_summary),
              status = 'completed'
          WHERE paper_uuid = p_paper_uuid
            AND (summaries IS NULL OR summaries->>'five_minute_summary' IS NULL);

          RETURN QUERY SELECT FOUND;
        END;
        $$ LANGUAGE plpgsql;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # -- 5. Drop set_paper_summary_if_null RPC -----------------------------------
    conn.execute(sa.text('DROP FUNCTION IF EXISTS set_paper_summary_if_null(text, text)'))

    # -- 4. Revert match_papers_by_embedding to completed-only -------------------
    conn.execute(sa.text('DROP FUNCTION IF EXISTS match_papers_by_embedding(vector, int, text[])'))
    conn.execute(sa.text("""
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

    # -- 3. Drop paper_authors table ---------------------------------------------
    op.drop_table('paper_authors')

    # -- 2. Drop authors table ---------------------------------------------------
    op.drop_table('authors')

    # -- 1. Remove abstract column -----------------------------------------------
    op.drop_column('papers', 'abstract')
