"""
Database operations for arXiv discovered papers.

This module provides CRUD operations for the arxiv_papers table, which stores
papers discovered from arXiv with optional Semantic Scholar enrichment data.

Why a separate file (client_temp.py)?
-------------------------------------
This is a temporary separate file to keep arXiv discovery operations isolated
from the existing paper processing operations in client.py. The two systems
serve different purposes:
- client.py: Operations for papers being processed (PDF summarization pipeline)
- client_temp.py: Operations for discovered papers (arXiv discovery pipeline)

TODO: Merge this file into client.py once the arXiv discovery feature is stable
and we have a clearer picture of how the two systems should interact.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from papers.db.models import ArxivPaperRecord
from papers.models import ArxivDiscoveredPaper, ArxivPaperFilter


logger = logging.getLogger(__name__)


# ============================================================================
# ARXIV PAPER DATABASE OPERATIONS
# ============================================================================

def create_arxiv_paper(db: Session, paper: ArxivDiscoveredPaper) -> ArxivPaperRecord:
    """
    Create a new arXiv paper record.

    Args:
        db: Database session.
        paper: Paper DTO to insert.

    Returns:
        The created ArxivPaperRecord model instance.

    Raises:
        IntegrityError: If a paper with this arxiv_id already exists.
    """
    record = paper.to_orm()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_arxiv_paper_by_id(db: Session, arxiv_id: str) -> Optional[ArxivDiscoveredPaper]:
    """
    Get a paper by its arXiv ID.

    Args:
        db: Database session.
        arxiv_id: ArXiv identifier (e.g., "2312.00752").

    Returns:
        ArxivDiscoveredPaper DTO if found, None otherwise.
    """
    record = db.query(ArxivPaperRecord).filter(
        ArxivPaperRecord.arxiv_id == arxiv_id
    ).first()

    if not record:
        return None

    return ArxivDiscoveredPaper.model_validate(record)


def list_arxiv_papers(db: Session, filters: ArxivPaperFilter) -> list[ArxivDiscoveredPaper]:
    """
    List papers with optional filters, ordered by avg_author_h_index descending.

    Args:
        db: Database session.
        filters: Filter and pagination options.

    Returns:
        List of ArxivDiscoveredPaper DTOs matching the filters.
    """
    query = db.query(ArxivPaperRecord)

    # Apply filters
    if filters.min_avg_h_index is not None:
        query = query.filter(ArxivPaperRecord.avg_author_h_index >= filters.min_avg_h_index)

    if filters.primary_category is not None:
        query = query.filter(ArxivPaperRecord.primary_category == filters.primary_category)

    if filters.published_after is not None:
        query = query.filter(ArxivPaperRecord.published_at >= filters.published_after)

    # Order by avg_author_h_index descending (nulls last)
    query = query.order_by(ArxivPaperRecord.avg_author_h_index.desc().nullslast())

    # Apply pagination
    query = query.offset(filters.offset).limit(filters.limit)

    records = query.all()
    return [ArxivDiscoveredPaper.model_validate(r) for r in records]


def save_arxiv_papers_batch(db: Session, papers: list[ArxivDiscoveredPaper]) -> int:
    """
    Upsert a batch of papers. Updates all fields unconditionally for existing papers.

    Partial success: commits papers that succeed, logs and skips papers that fail.

    Args:
        db: Database session.
        papers: List of ArxivDiscoveredPaper DTOs to upsert.

    Returns:
        Number of papers successfully upserted.
    """
    success_count = 0

    for paper in papers:
        try:
            # Check if paper already exists
            existing = db.query(ArxivPaperRecord).filter(
                ArxivPaperRecord.arxiv_id == paper.arxiv_id
            ).first()

            if existing:
                # Update existing record
                _update_arxiv_paper_record(existing, paper)
                db.add(existing)
            else:
                # Create new record
                record = paper.to_orm()
                db.add(record)

            db.commit()
            success_count += 1

        except IntegrityError as e:
            db.rollback()
            logger.warning(f"IntegrityError for paper {paper.arxiv_id}: {e}")
            continue
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving paper {paper.arxiv_id}: {e}")
            continue

    return success_count


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _update_arxiv_paper_record(record: ArxivPaperRecord, paper: ArxivDiscoveredPaper) -> None:
    """
    Update an existing ArxivPaperRecord with data from a DTO.

    Args:
        record: Existing database record to update.
        paper: DTO containing new data.
    """
    import json

    record.version = paper.version
    record.title = paper.title
    record.abstract = paper.abstract
    record.published_at = paper.published_at
    record.primary_category = paper.primary_category

    # Serialize JSON fields
    record.categories = json.dumps(paper.categories) if paper.categories else None
    record.authors = json.dumps(
        [a.model_dump() for a in paper.authors]
    ) if paper.authors else None

    record.semantic_scholar_id = paper.semantic_scholar_id
    record.citation_count = paper.citation_count
    record.influential_citation_count = paper.influential_citation_count
    record.embedding_model = paper.embedding_model
    record.embedding_vector = json.dumps(paper.embedding_vector) if paper.embedding_vector else None
    record.avg_author_h_index = paper.avg_author_h_index
    record.avg_author_citations_per_paper = paper.avg_author_citations_per_paper
    record.total_author_h_index = paper.total_author_h_index
    record.updated_at = datetime.utcnow()
