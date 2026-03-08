from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Float, Boolean, Index, JSON, Date
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
    # External popularity signals stored as JSON
    external_popularity_signals = Column(JSON, nullable=True)
    # Extracted summaries stored as JSON dict (e.g. {"five_minute_summary": "..."})
    summaries = Column(JSON, nullable=True)
    # PDF content hash for non-arXiv papers (SHA-256)
    content_hash = Column(String(64), nullable=True)
    # Direct PDF URL for non-arXiv papers
    pdf_url = Column(String(512), nullable=True)
    # 1536-dim embedding vector from text-embedding-3-small via OpenRouter
    embedding = Column(Vector(1536), nullable=True)
    abstract = Column(Text, nullable=True)

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
