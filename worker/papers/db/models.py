from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Float, Boolean, Index, JSON, Date
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

from shared.db import Base


class PaperRecord(Base):
    """SQLAlchemy model for papers table."""
    __tablename__ = "papers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    paper_uuid = Column(String(36), nullable=False)
    arxiv_id = Column(String(64), nullable=True)
    arxiv_version = Column(String(10), nullable=True)
    arxiv_url = Column(String(255), nullable=True)
    title = Column(String(512), nullable=True)
    authors = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="not_started")
    error_message = Column(Text, nullable=True)
    # Which user initiated processing (auth provider id). Nullable for admin/system jobs.
    initiated_by_user_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    # Metrics captured after processing completes
    num_pages = Column(Integer, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    avg_cost_per_page = Column(Float, nullable=True)
    # Extracted summaries stored as JSON dict (e.g. {"five_minute_summary": "..."})
    summaries = Column(JSON, nullable=True)
    # PDF content hash for non-arXiv papers (SHA-256)
    content_hash = Column(String(64), nullable=True)
    # Direct PDF URL for non-arXiv papers
    pdf_url = Column(String(512), nullable=True)
    # 1536-dim embedding vector from text-embedding-3-small via OpenRouter
    embedding = Column(Vector(1536), nullable=True)
    abstract = Column(Text, nullable=True)
    # Pre-computed scoring signals (e.g. {"max_author_h_index": 42})
    signals = Column(JSON, nullable=True)
    # Semantic Scholar enrichment columns
    s2_ids = Column(JSONB, nullable=True)
    s2_metrics = Column(JSONB, nullable=True)
    classification = Column(JSONB, nullable=True)
    publication_info = Column(JSONB, nullable=True)
    s2_tldr = Column(Text, nullable=True)
    # 768-dim SPECTER v2 embedding from Semantic Scholar
    s2_embedding = Column(Vector(768), nullable=True)
    # PageRank score and percentile computed from citation graph
    pagerank = Column(JSONB, nullable=True)
    inbound_citations_fetched_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("paper_uuid", name="uq_papers_paper_uuid"),
        UniqueConstraint("arxiv_id", name="uq_papers_arxiv_id"),
        UniqueConstraint("content_hash", name="uq_papers_content_hash"),
        Index("ix_papers_initiated_by_user_id", "initiated_by_user_id"),
        Index("ix_papers_content_hash", "content_hash"),
    )


class PaperSlugRecord(Base):
    """SQLAlchemy model for paper_slugs table."""
    __tablename__ = "paper_slugs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(255), nullable=False, unique=True)
    paper_uuid = Column(String(36), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Tombstone preserves the slug after deletion of the paper
    tombstone = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)


class AuthorRecord(Base):
    """SQLAlchemy model for authors table (Semantic Scholar data)."""
    __tablename__ = "authors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    s2_author_id = Column(String(64), unique=True, nullable=False)
    name = Column(String(512), nullable=False)
    affiliations = Column(JSON, nullable=True)
    homepage = Column(String(512), nullable=True)
    paper_count = Column(Integer, nullable=True)
    citation_count = Column(Integer, nullable=True)
    h_index = Column(Integer, nullable=True)
    stats_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # PageRank score and percentile computed from citation graph
    pagerank = Column(JSONB, nullable=True)


class PaperAuthorRecord(Base):
    """SQLAlchemy model for paper_authors junction table."""
    __tablename__ = "paper_authors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    paper_id = Column(BigInteger, ForeignKey("papers.id"), nullable=False)
    author_id = Column(BigInteger, ForeignKey("authors.id"), nullable=False)
    author_order = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("paper_id", "author_id", name="uq_paper_authors"),
        Index("ix_paper_authors_paper_id", "paper_id"),
        Index("ix_paper_authors_author_id", "author_id"),
    )


class PaperCitationRecord(Base):
    """SQLAlchemy model for paper_citations table.

    Stores citation edges between papers using Semantic Scholar paper IDs.
    - Each row represents one citation: source_s2_id cites cited_s2_id.
    - Sentinel rows (cited_s2_id = NULL) mark papers whose references have been
      fetched but returned empty, preventing re-fetching.
    """
    __tablename__ = "paper_citations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_s2_id = Column(String(64), nullable=False)
    cited_s2_id = Column(String(64), nullable=True)
    is_influential = Column(Boolean, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_paper_citations_source_s2_id", "source_s2_id"),
        Index("ix_paper_citations_cited_s2_id", "cited_s2_id"),
    )


class PaperStatusHistory(Base):
    """SQLAlchemy model for paper_status_history table."""
    __tablename__ = "paper_status_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    total_count = Column(Integer, nullable=False)
    failed_count = Column(Integer, nullable=False)
    processed_count = Column(Integer, nullable=False)
    not_started_count = Column(Integer, nullable=False)
    processing_count = Column(Integer, nullable=False)
    snapshot_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", name="uq_paper_status_history_date"),
        Index("ix_paper_status_history_date", "date"),
    )
