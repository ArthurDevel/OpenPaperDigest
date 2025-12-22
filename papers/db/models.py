from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, UniqueConstraint, Float, Boolean, Index, JSON, Date
from sqlalchemy.dialects.mysql import MEDIUMTEXT, LONGTEXT

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
    # Base64 data URL of a 400x400 PNG thumbnail cropped from the top square of the first page
    thumbnail_data_url = Column(MEDIUMTEXT, nullable=True)
    # External popularity signals stored as JSON
    external_popularity_signals = Column(JSON, nullable=True)
    # Complete processed paper JSON (replaces file system storage)
    processed_content = Column(Text().with_variant(LONGTEXT, 'mysql'), nullable=True)
    # PDF content hash for non-arXiv papers (SHA-256)
    content_hash = Column(String(64), nullable=True)
    # Direct PDF URL for non-arXiv papers
    pdf_url = Column(String(512), nullable=True)

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


class ArxivPaperRecord(Base):
    """
    SQLAlchemy model for arxiv_papers table.

    Stores discovered arXiv papers with metadata, author credibility scores,
    and optional Semantic Scholar enrichment data.
    """
    __tablename__ = "arxiv_papers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    arxiv_id = Column(String(64), nullable=False)
    version = Column(Integer, nullable=True)
    title = Column(String(512), nullable=False)
    abstract = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    primary_category = Column(String(32), nullable=True)
    categories = Column(JSON, nullable=True)
    authors = Column(JSON, nullable=True)
    semantic_scholar_id = Column(String(64), nullable=True)
    citation_count = Column(Integer, nullable=True)
    influential_citation_count = Column(Integer, nullable=True)
    embedding_model = Column(String(32), nullable=True)
    embedding_vector = Column(JSON, nullable=True)
    avg_author_h_index = Column(Float, nullable=True)
    avg_author_citations_per_paper = Column(Float, nullable=True)
    total_author_h_index = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("arxiv_id", name="uq_arxiv_papers_arxiv_id"),
        Index("ix_arxiv_papers_published_at", "published_at"),
        Index("ix_arxiv_papers_primary_category", "primary_category"),
        Index("ix_arxiv_papers_avg_author_h_index", "avg_author_h_index"),
    )
