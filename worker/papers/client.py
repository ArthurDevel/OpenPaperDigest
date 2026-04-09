from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import re
import unicodedata
import uuid

from sqlalchemy.orm import Session

from papers.models import Paper, PaperSlug, Page, Section
from papers.db.client import (
    get_paper_record, create_paper_record, update_paper_record, list_paper_records,
    get_paper_slugs, get_all_paper_slugs, tombstone_paper_slugs,
    find_existing_paper_slug_record, find_slug_record_by_name, create_paper_slug_record
)
from papers.db.models import PaperRecord
from paperprocessor.models import ProcessedDocument
import papers.storage as storage

logger = logging.getLogger(__name__)


### HELPER FUNCTIONS ###


def build_paper_slug(title: Optional[str], authors: Optional[str]) -> str:
    """
    Generate a URL-safe slug from paper title and authors.
    
    Args:
        title: Paper title
        authors: Comma-separated author names
        
    Returns:
        str: URL-safe slug (max 120 characters)
        
    Raises:
        ValueError: If title or authors are missing
    """
    if not title or not authors:
        raise ValueError("Cannot generate slug without title and authors")
    
    # Step 1: Normalize unicode characters to ASCII
    try:
        normalized_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
        normalized_authors = unicodedata.normalize('NFKD', authors).encode('ascii', 'ignore').decode('ascii')
    except Exception:
        normalized_title, normalized_authors = title, authors
    
    # Step 2: Extract first 12 words from title
    title_words = [word for word in normalized_title.split() if word][:12]
    title_part = " ".join(title_words) if title_words else normalized_title
    
    # Step 3: Extract up to 2 author last names
    author_names = [name.strip() for name in normalized_authors.split(',') if name.strip()]
    if not author_names:
        raise ValueError("Cannot generate slug: no authors present")
    
    def _extract_last_name(full_name: str) -> str:
        name_parts = full_name.split()
        return name_parts[-1] if name_parts else full_name
    
    author_last_names = [_extract_last_name(name) for name in author_names[:2]]
    author_part = " ".join(author_last_names)
    
    # Step 4: Combine and create URL-safe slug
    combined_text = f"{title_part} {author_part}".strip()
    slug = combined_text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip('-')
    
    return slug[:120]


def find_existing_paper_slug(db: Session, paper_uuid: str) -> Optional[PaperSlug]:
    """
    Find existing non-tombstoned slug for a paper.
    
    Args:
        db: Active database session
        paper_uuid: UUID of the paper to find slug for
        
    Returns:
        Optional[PaperSlug]: Existing slug DTO if found, None otherwise
    """
    existing_slug_record = find_existing_paper_slug_record(db, paper_uuid)
    if existing_slug_record:
        return PaperSlug.model_validate(existing_slug_record)
    return None


def create_paper_slug(db: Session, paper: Paper) -> PaperSlug:
    """
    Create a unique slug for a paper, checking for collisions.
    
    Args:
        db: Active database session
        paper: Paper object with title and authors
        
    Returns:
        PaperSlug: Created or existing slug DTO
        
    Raises:
        ValueError: If slug collision occurs with different paper
    """
    # Step 1: Check if paper already has a slug
    existing_slug = find_existing_paper_slug(db, paper.paper_uuid)
    if existing_slug:
        return existing_slug
    
    # Step 2: Generate new slug from paper metadata
    new_slug_string = build_paper_slug(paper.title, paper.authors)
    
    # Step 3: Check for slug collisions
    existing_slug_record = find_slug_record_by_name(db, new_slug_string)
    
    if existing_slug_record:
        # Allow reuse if slug already maps to this same paper
        if existing_slug_record.paper_uuid != paper.paper_uuid:
            raise ValueError(f"Slug collision for '{new_slug_string}' - already used by different paper")
        return PaperSlug.model_validate(existing_slug_record)
    
    # Step 4: Create new slug record using database layer
    created_slug_record = create_paper_slug_record(db, new_slug_string, paper.paper_uuid)
    
    return PaperSlug.model_validate(created_slug_record)


def _decode_data_url(data_url: str) -> bytes:
    """Decode a base64 data URL to raw bytes.

    Strips the 'data:<mime>;base64,' prefix and base64-decodes the remainder.

    Args:
        data_url: Full data URL string (e.g. "data:image/png;base64,iVBOR...")

    Returns:
        Raw decoded bytes.
    """
    _, b64_data = data_url.split(",", 1)
    return base64.b64decode(b64_data)


def _upload_to_storage(paper_uuid: str, result_dict: Dict[str, Any]) -> None:
    """Upload paper assets to Supabase Storage from the processed result dict.

    Uploads thumbnail + metadata.json (with pipeline_version: 2).

    Args:
        paper_uuid: UUID of the paper.
        result_dict: The fully-built result dict from save_paper().
    """
    # Decode thumbnail from base64 data URL to raw PNG bytes
    thumbnail_data_url = result_dict.get("thumbnail_data_url")
    if not thumbnail_data_url:
        raise ValueError("Cannot upload to storage: no thumbnail_data_url in result")
    thumbnail_bytes = _decode_data_url(thumbnail_data_url)

    # Build metadata dict from usage/cost info
    metadata = {
        "usage_summary": result_dict.get("usage_summary", {}),
        "processing_time_seconds": result_dict.get("processing_time_seconds", 0.0),
        "num_pages": result_dict.get("num_pages", 0),
        "total_cost": result_dict.get("total_cost", 0.0),
        "avg_cost_per_page": result_dict.get("avg_cost_per_page", 0.0),
    }

    storage.upload_paper_assets(
        paper_uuid=paper_uuid,
        thumbnail_bytes=thumbnail_bytes,
        metadata=metadata,
    )


### MAIN FUNCTIONS ###

def create_paper(
    db: Session,
    arxiv_id: Optional[str] = None,
    pdf_url: Optional[str] = None,
    title: Optional[str] = None,
    authors: Optional[str] = None,
    abstract: Optional[str] = None,
    signals: Optional[Dict[str, Any]] = None,
    initiated_by_user_id: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> Paper:
    """
    Create a new paper and add it to the processing queue.

    IMPORTANT: This function creates a paper with status 'not_started', which means
    it will be automatically picked up by the paper processing worker for full
    PDF processing, OCR, and content extraction.

    For arXiv papers: provide arxiv_id
    For non-arXiv papers: provide pdf_url (hash will be calculated)

    Args:
        db: Active database session
        arxiv_id: ArXiv paper identifier (e.g., "2509.14233") - optional
        pdf_url: Direct PDF URL if no arXiv ID - optional
        title: Paper title (optional - will be extracted during processing if not provided)
        authors: Comma-separated author names (optional - will be extracted if not provided)
        signals: Pre-computed scoring signals dict (e.g. {"hf_upvotes": 42, "sources": ["HuggingFace"]})
        initiated_by_user_id: User ID who requested processing (None for system jobs)

    Returns:
        Paper: Created paper DTO with status 'not_started' (queued for processing)

    Raises:
        ValueError: If paper already exists or if neither arxiv_id nor pdf_url provided
        RuntimeError: If database operation fails
    """
    # Step 1: Validate inputs
    if not arxiv_id and not pdf_url:
        raise ValueError("Must provide either arxiv_id or pdf_url")

    content_hash = None
    arxiv_url = None

    # Step 2: Check for duplicates
    if arxiv_id:
        # Check by arXiv ID (fast)
        try:
            existing_paper = get_paper_record(db, arxiv_id, by_arxiv_id=True)
            raise ValueError(f"Paper with arXiv ID {arxiv_id} already exists in database")
        except FileNotFoundError:
            # This is good - paper doesn't exist yet
            pass

        # Construct arxiv_url from arxiv_id
        arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"

    else:
        # Download PDF and check by hash
        from shared.pdf_utils import download_pdf, calculate_pdf_hash

        pdf_bytes = download_pdf(pdf_url)
        content_hash = calculate_pdf_hash(pdf_bytes)

        from papers.db.client import get_paper_by_content_hash
        existing = get_paper_by_content_hash(db, content_hash)
        if existing:
            raise ValueError(f"Paper with content hash {content_hash} already exists in database")

    # Step 3: Create paper DTO for queuing
    paper_dto = Paper(
        paper_uuid=str(uuid.uuid4()),
        arxiv_id=arxiv_id,
        arxiv_url=arxiv_url,
        pdf_url=pdf_url,
        content_hash=content_hash,
        title=title,
        authors=authors,
        status='not_started',  # This queues the paper for processing!
        initiated_by_user_id=initiated_by_user_id,
        signals=signals or {},
        published_at=published_at,
    )

    # Step 4: Persist to database using internal layer
    create_paper_record(db, paper_dto)

    # Step 5: Store abstract if provided
    if abstract:
        record = get_paper_record(db, paper_dto.paper_uuid)
        record.abstract = abstract
        db.flush()

    return paper_dto


def list_papers(db: Session, statuses: Optional[List[str]], limit: int) -> List[Paper]:
    records = list_paper_records(db, statuses, limit)
    return [Paper.model_validate(record) for record in records]


def list_minimal_papers(db: Session, page: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    List completed papers with minimal fields for overview page.
    Reads from database only.

    Args:
        db: Active database session
        page: Optional page number (1-indexed) for pagination
        limit: Optional number of items per page

    Returns:
        If paginated: Dict with items, total, page, has_more
        If not paginated: List[Dict] (legacy behavior for backward compatibility)
    """
    # Determine if we're using pagination
    use_pagination = page is not None and limit is not None

    if use_pagination:
        # Calculate offset
        offset = (page - 1) * limit

        # Get total count of completed papers
        total_count = db.query(PaperRecord).filter(PaperRecord.status.in_(["completed", "partially_completed"])).count()

        # Query paginated papers
        completed_papers = list_paper_records(db, statuses=["completed", "partially_completed"], limit=limit, offset=offset)
    else:
        # Legacy behavior: return all papers
        completed_papers = list_paper_records(db, statuses=["completed", "partially_completed"], limit=1000)

    # Step 2: Build slug mapping (latest non-tombstone per paper_uuid)
    slug_records = get_all_paper_slugs(db, non_tombstone_only=True)
    slug_dtos = [PaperSlug.model_validate(record) for record in slug_records]
    latest_by_uuid: Dict[str, Dict[str, Any]] = {}
    for slug_dto in slug_dtos:
        puid = slug_dto.paper_uuid
        if not puid:
            continue
        current = latest_by_uuid.get(puid)
        if current is None or (slug_dto.created_at and current.get("created_at") and slug_dto.created_at > current["created_at"]):
            latest_by_uuid[puid] = {"slug": slug_dto.slug, "created_at": slug_dto.created_at}

    # Step 3: Build minimal paper items with slug mapping
    items: List[Dict[str, Any]] = []
    for record in completed_papers:
        item = {
            "paper_uuid": record.paper_uuid,
            "title": record.title,
            "authors": record.authors,
            "thumbnail_url": storage.get_thumbnail_url(record.paper_uuid),
        }

        # Add slug if available
        slug_mapping = latest_by_uuid.get(record.paper_uuid)
        if slug_mapping:
            item["slug"] = slug_mapping["slug"]

        items.append(item)

    if use_pagination:
        return {
            "items": items,
            "total": total_count,
            "page": page,
            "has_more": (offset + len(items)) < total_count
        }
    else:
        # Legacy behavior: return just the list
        return items


def delete_paper(db: Session, paper_uuid: str) -> bool:
    """
    Delete a paper and its storage assets.

    Cleans up Supabase Storage files first (best-effort), then removes the
    database row and tombstones associated slugs.

    Args:
        db: Active database session
        paper_uuid: UUID of paper to delete

    Returns:
        bool: True if paper was deleted, False if not found
    """
    row = get_paper_record(db, str(paper_uuid))
    if not row:
        return False

    # Delete storage assets first (best-effort: if this fails, still delete DB row)
    try:
        storage.delete_paper_assets(str(paper_uuid))
    except Exception:
        logger.warning("Failed to delete storage assets for paper %s, proceeding with DB deletion", paper_uuid)

    # Remove DB row
    db.delete(row)
    db.flush()

    # Tombstone slugs
    try:
        tombstone_paper_slugs(db, str(paper_uuid))
    except Exception:
        # best-effort
        pass

    db.commit()
    return True


def save_paper(db: Session, processed_content: ProcessedDocument) -> Paper:
    """
    Save processed document to database.

    Args:
        db: Database session
        processed_content: ProcessedDocument with full processing results

    Returns:
        Paper: Created or updated Paper object

    Raises:
        ValueError: If creating new paper but arxiv_id already exists
        RuntimeError: If missing required fields
    """
    # Step 1: Determine if this is create or update
    if processed_content.paper_uuid:
        # Update existing paper
        paper_uuid = processed_content.paper_uuid
        arxiv_id = processed_content.arxiv_id
        is_update = True
    else:
        # Create new paper - check for duplicates first
        # Note: arxiv_id may be None for non-arXiv papers
        if processed_content.arxiv_id:
            existing_paper = get_paper_record(db, processed_content.arxiv_id, by_arxiv_id=True)
            if existing_paper:
                raise ValueError(f"Paper with arXiv ID {processed_content.arxiv_id} already exists")

        paper_uuid = str(uuid.uuid4())
        arxiv_id = processed_content.arxiv_id
        is_update = False
    
    # Step 2: Build result dict for storage upload
    result_dict = {
        "paper_id": paper_uuid,
        "title": processed_content.title,
        "authors": processed_content.authors,
        "thumbnail_data_url": None,  # Will be set from first page
        "five_minute_summary": processed_content.five_minute_summary,
        "usage_summary": {},
        "processing_time_seconds": 0.0,
        "num_pages": len(processed_content.pages),
        "total_cost": 0.0,
        "avg_cost_per_page": 0.0,
    }

    # Set thumbnail from first page
    if processed_content.pages:
        result_dict["thumbnail_data_url"] = f"data:image/png;base64,{processed_content.pages[0].img_base64}"

    # Calculate usage summary and costs
    from paperprocessor.client import _calculate_usage_summary
    usage_summary = _calculate_usage_summary(processed_content.step_costs)
    result_dict["usage_summary"] = usage_summary
    result_dict["total_cost"] = usage_summary.get("total_cost")
    if result_dict["total_cost"] and result_dict["num_pages"] > 0:
        result_dict["avg_cost_per_page"] = result_dict["total_cost"] / result_dict["num_pages"]
    
    # Step 3: Upload paper assets to Supabase Storage (must succeed)
    _upload_to_storage(paper_uuid, result_dict)

    # Step 4: Create or update paper record in database (metadata only)
    paper_data = {
        'paper_uuid': paper_uuid,
        'arxiv_id': arxiv_id,
        'title': processed_content.title,
        'authors': processed_content.authors,
        'status': 'completed' if processed_content.five_minute_summary else 'partially_completed',
        'num_pages': len(processed_content.pages),
        'total_cost': result_dict["total_cost"],
        'avg_cost_per_page': result_dict["avg_cost_per_page"],
        'summaries': {
            "five_minute_summary": processed_content.five_minute_summary,
            "abstract_summary": processed_content.abstract_summary,
        },
        'embedding': processed_content.embedding,
        'abstract': processed_content.abstract,
        'finished_at': datetime.utcnow(),
    }

    if is_update:
        record = update_paper_record(db, paper_uuid, paper_data)
    else:
        record = create_paper_record(db, paper_data)

    return Paper.model_validate(record)


def get_paper_metadata(db: Session, paper_uuid: str) -> Paper:
    """
    Get paper metadata from database only.
    
    Returns:
        Paper: Database record with metadata fields only
        
    Raises:
        FileNotFoundError: If paper with UUID not found
    """
    record = get_paper_record(db, paper_uuid)
    return Paper.model_validate(record)


def get_paper(db: Session, paper_uuid: str) -> Paper:
    """
    Get complete paper by UUID.

    Loads relational metadata from the database and full content
    (sections, figures metadata) from Supabase Storage.

    Args:
        db: Active database session.
        paper_uuid: UUID of the paper to retrieve.

    Returns:
        Paper: Complete paper with metadata, sections, and thumbnail/figure URLs.

    Raises:
        FileNotFoundError: If paper with UUID not found in DB.
        RuntimeError: If storage download fails (no fallback).
    """
    # Step 1: Load relational metadata from database
    record = get_paper_record(db, paper_uuid)
    paper = Paper.model_validate(record)

    # Step 2: Download content from Supabase Storage
    stored = storage.download_paper_content(paper_uuid)

    # Step 3: Convert stored sections to Section DTOs (empty for v2 papers)
    if stored.sections:
        sections = []
        for idx, section_data in enumerate(stored.sections):
            section = Section(
                order_index=idx,
                rewritten_content=section_data["rewritten_content"],
                start_page=section_data.get("start_page"),
                end_page=section_data.get("end_page"),
                level=section_data.get("level"),
                section_title=section_data.get("section_title"),
                summary=section_data.get("summary"),
                subsections=section_data.get("subsections", []),
            )
            sections.append(section)
        paper.sections = sections

    # Step 4: Populate paper DTO with storage data
    paper.thumbnail_url = storage.get_thumbnail_url(paper_uuid)

    return paper


