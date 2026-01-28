from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, defer, undefer

from papers.db.models import PaperRecord, PaperSlugRecord




### DATABASE OPERATIONS ###

def get_paper_record(db: Session, paper_uuid: str, by_arxiv_id: bool = False, load_content: bool = False) -> PaperRecord:
    """
    Get paper record from database.

    Args:
        db: Database session
        paper_uuid: Paper UUID or arXiv ID
        by_arxiv_id: If True, search by arXiv ID instead of UUID
        load_content: If True, load the processed_content column (heavy data)

    Raises:
        FileNotFoundError: If paper not found
    """
    query = db.query(PaperRecord)

    # Defer the heavy processed_content column by default
    if not load_content:
        query = query.options(defer(PaperRecord.processed_content))

    if by_arxiv_id:
        record = query.filter(PaperRecord.arxiv_id == str(paper_uuid)).first()
        if not record:
            raise FileNotFoundError(f"Paper with arXiv ID {paper_uuid} not found")
    else:
        record = query.filter(PaperRecord.paper_uuid == str(paper_uuid)).first()
        if not record:
            raise FileNotFoundError(f"Paper with UUID {paper_uuid} not found")
    return record


def get_paper_by_content_hash(db: Session, content_hash: str) -> Optional[PaperRecord]:
    """
    Get paper by PDF content hash.

    Args:
        db: Database session
        content_hash: SHA-256 hash of PDF content

    Returns:
        Optional[PaperRecord]: Paper record if found, None otherwise
    """
    return db.query(PaperRecord).options(
        defer(PaperRecord.processed_content)
    ).filter(
        PaperRecord.content_hash == content_hash
    ).first()


def create_paper_record(db: Session, paper_data) -> PaperRecord:
    """Create new paper record in database from dict or Paper DTO."""
    from papers.models import Paper
    
    if isinstance(paper_data, Paper):
        record = paper_data.to_orm()
    else:
        # Set default timestamps if not provided
        now = datetime.utcnow()
        paper_data.setdefault('created_at', now)
        paper_data.setdefault('updated_at', now)
        record = PaperRecord(**paper_data)
    
    db.add(record)
    db.commit()
    return record


def update_paper_record(db: Session, paper_uuid: str, paper_data) -> PaperRecord:
    """Update existing paper record in database from dict or Paper DTO."""
    from papers.models import Paper
    
    record = get_paper_record(db, paper_uuid)
    
    if isinstance(paper_data, Paper):
        # Update all fields from DTO
        updated_record = paper_data.to_orm()
        updated_record.id = record.id  # Preserve database ID
        updated_record.updated_at = datetime.utcnow()
        
        db.merge(updated_record)
    else:
        # Update provided fields from dict
        for key, value in paper_data.items():
            if hasattr(record, key):
                setattr(record, key, value)
        
        # Always update timestamp
        record.updated_at = datetime.utcnow()
        db.add(record)
    
    db.commit()
    return record


def list_paper_records(db: Session, statuses: Optional[List[str]], limit: int, offset: int = 0) -> List[PaperRecord]:
    """List paper records from database (without heavy processed_content column)."""
    q = db.query(PaperRecord).options(defer(PaperRecord.processed_content))
    if statuses:
        q = q.filter(PaperRecord.status.in_(statuses))
    q = q.order_by(PaperRecord.finished_at.desc()).limit(max(1, min(limit, 1000))).offset(offset)
    return q.all()


def delete_paper_record(db: Session, paper_uuid: str) -> bool:
    """Delete paper record from database."""
    record = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()
    if not record:
        return False
    
    db.delete(record)
    db.commit()
    return True


def get_paper_slugs(db: Session, paper_uuid: str) -> List[PaperSlugRecord]:
    """Get all slugs for a paper."""
    return db.query(PaperSlugRecord).filter(PaperSlugRecord.paper_uuid == str(paper_uuid)).all()


def get_all_paper_slugs(db: Session, non_tombstone_only: bool = True) -> List[PaperSlugRecord]:
    """Get all paper slugs, optionally filtering out tombstones."""
    query = db.query(PaperSlugRecord)
    if non_tombstone_only:
        query = query.filter(PaperSlugRecord.tombstone == False)  # noqa: E712
    return query.all()


def tombstone_paper_slugs(db: Session, paper_uuid: str) -> None:
    """Mark all slugs for a paper as tombstoned."""
    from datetime import datetime
    db.query(PaperSlugRecord).filter(
        PaperSlugRecord.paper_uuid == paper_uuid,
        PaperSlugRecord.tombstone == False  # noqa: E712
    ).update({'tombstone': True, 'deleted_at': datetime.utcnow()})


def find_existing_paper_slug_record(db: Session, paper_uuid: str) -> Optional[PaperSlugRecord]:
    """
    Find existing non-tombstoned slug record for a paper.
    
    Args:
        db: Active database session
        paper_uuid: UUID of the paper to find slug for
        
    Returns:
        Optional[PaperSlugRecord]: Existing slug record if found, None otherwise
    """
    return (
        db.query(PaperSlugRecord)
        .filter(
            PaperSlugRecord.paper_uuid == paper_uuid,
            PaperSlugRecord.tombstone == False  # noqa: E712
        )
        .order_by(PaperSlugRecord.created_at.desc())
        .first()
    )


def find_slug_record_by_name(db: Session, slug: str) -> Optional[PaperSlugRecord]:
    """
    Find slug record by slug name.
    
    Args:
        db: Active database session
        slug: Slug name to search for
        
    Returns:
        Optional[PaperSlugRecord]: Slug record if found, None otherwise
    """
    return db.query(PaperSlugRecord).filter(PaperSlugRecord.slug == slug).first()


def create_paper_slug_record(db: Session, slug: str, paper_uuid: str) -> PaperSlugRecord:
    """
    Create a new paper slug record in the database.
    
    Args:
        db: Active database session
        slug: URL-safe slug string
        paper_uuid: UUID of the paper this slug belongs to
        
    Returns:
        PaperSlugRecord: Created slug record
    """
    new_slug_record = PaperSlugRecord(
        slug=slug,
        paper_uuid=paper_uuid,
        tombstone=False,
        created_at=datetime.utcnow()
    )
    db.add(new_slug_record)
    db.commit()
    return new_slug_record
