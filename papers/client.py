from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import json as _json
import re
import unicodedata
import uuid

from sqlalchemy.orm import Session

from papers.models import Paper, PaperSlug, Page, Section, ExternalPopularitySignal
from papers.db.client import (
    get_paper_record, create_paper_record, update_paper_record, list_paper_records,
    get_paper_slugs, get_all_paper_slugs, tombstone_paper_slugs,
    find_existing_paper_slug_record, find_slug_record_by_name, create_paper_slug_record
)
from papers.db.models import PaperRecord
from paperprocessor.models import ProcessedDocument


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


### MAIN FUNCTIONS ###

def create_paper(
    db: Session, 
    arxiv_id: str, 
    title: Optional[str] = None,
    authors: Optional[str] = None,
    external_popularity_signals: Optional[List[ExternalPopularitySignal]] = None,
    initiated_by_user_id: Optional[str] = None
) -> Paper:
    """
    Create a new paper and add it to the processing queue.
    
    IMPORTANT: This function creates a paper with status 'not_started', which means
    it will be automatically picked up by the paper processing worker for full
    PDF processing, OCR, and content extraction.
    
    Args:
        db: Active database session
        arxiv_id: ArXiv paper identifier (e.g., "2509.14233")
        title: Paper title (optional - will be extracted during processing if not provided)
        authors: Comma-separated author names (optional - will be extracted if not provided)
        external_popularity_signals: List of ExternalPopularitySignal objects with metrics
        initiated_by_user_id: User ID who requested processing (None for system jobs)
        
    Returns:
        Paper: Created paper DTO with status 'not_started' (queued for processing)
        
    Raises:
        ValueError: If paper with this arXiv ID already exists in the database
        RuntimeError: If database operation fails
    """
    # Step 1: Check for duplicates using internal database layer
    try:
        existing_paper = get_paper_record(db, arxiv_id, by_arxiv_id=True)
        raise ValueError(f"Paper with arXiv ID {arxiv_id} already exists in database")
    except FileNotFoundError:
        # This is good - paper doesn't exist yet
        pass
    
    # Step 2: Create paper DTO for queuing
    # Construct arxiv_url from arxiv_id
    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"

    paper_dto = Paper(
        paper_uuid=str(uuid.uuid4()),
        arxiv_id=arxiv_id,
        arxiv_url=arxiv_url,
        title=title,
        authors=authors,
        status='not_started',  # This queues the paper for processing!
        initiated_by_user_id=initiated_by_user_id,
        external_popularity_signals=external_popularity_signals or []
    )
    
    # Step 3: Persist to database using internal layer
    create_paper_record(db, paper_dto)
    
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
        total_count = db.query(PaperRecord).filter(PaperRecord.status == "completed").count()

        # Query paginated papers
        completed_papers = list_paper_records(db, statuses=["completed"], limit=limit, offset=offset)
    else:
        # Legacy behavior: return all papers
        completed_papers = list_paper_records(db, statuses=["completed"], limit=1000)

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
            "thumbnail_url": f"/api/papers/thumbnails/{record.paper_uuid}" if record.thumbnail_data_url else None,
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
    Delete a paper from the database.
    
    Args:
        db: Active database session
        paper_uuid: UUID of paper to delete
        
    Returns:
        bool: True if paper was deleted, False if not found
    """
    row = get_paper_record(db, str(paper_uuid))
    if not row:
        return False

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
    if not processed_content.arxiv_id:
        raise RuntimeError("ProcessedDocument must have arxiv_id")
    
    # Step 1: Determine if this is create or update
    if processed_content.paper_uuid:
        # Update existing paper
        paper_uuid = processed_content.paper_uuid
        arxiv_id = processed_content.arxiv_id
        is_update = True
    else:
        # Create new paper - check for duplicates first
        existing_paper = get_paper_record(db, processed_content.arxiv_id, by_arxiv_id=True)
        if existing_paper:
            raise ValueError(f"Paper with arXiv ID {processed_content.arxiv_id} already exists")
        
        paper_uuid = str(uuid.uuid4())
        arxiv_id = processed_content.arxiv_id
        is_update = False
    
    # Step 2: Convert ProcessedDocument to legacy JSON format
    result_dict = {
        "paper_id": paper_uuid,
        "title": processed_content.title,
        "authors": processed_content.authors,
        "thumbnail_data_url": None,  # Will be set from first page
        "five_minute_summary": processed_content.five_minute_summary,
        "final_markdown": processed_content.final_markdown,  # Original OCR markdown
        "sections": [],
        "tables": [],
        "figures": [],
        "pages": [],
        "usage_summary": {},
        "processing_time_seconds": 0.0,
        "num_pages": len(processed_content.pages),
        "total_cost": 0.0,
        "avg_cost_per_page": 0.0,
    }
    
    # Don't store page images - only keep page count for metadata
    # Page images are only needed during processing for OCR/metadata extraction
    
    # Convert individual images from pages to figures format
    for page in processed_content.pages:
        for processed_image in page.images:
            # Normalize bounding box coordinates to 0-1 range
            normalized_bbox = [
                processed_image.top_left_x / page.width,
                processed_image.top_left_y / page.height,
                processed_image.bottom_right_x / page.width,
                processed_image.bottom_right_y / page.height
            ]

            result_dict["figures"].append({
                "figure_identifier": processed_image.uuid,
                "short_id": processed_image.short_id,
                "location_page": processed_image.page_number,
                "explanation": "",  # Not extracted in current pipeline
                "image_data_url": f"data:image/png;base64,{processed_image.img_base64}",
                "referenced_on_pages": [processed_image.page_number],
                "bounding_box": normalized_bbox,  # Normalized coordinates (0-1)
            })
    
    # Set thumbnail from first page
    if processed_content.pages:
        result_dict["thumbnail_data_url"] = f"data:image/png;base64,{processed_content.pages[0].img_base64}"
    
    # Convert sections to legacy format
    for section in processed_content.sections:
        section_data = {
            "rewritten_content": section.rewritten_content,
            "summary": None,  # Not populated in current pipeline
            "subsections": []  # Flat structure for now
        }
        # Only include fields that are actually set
        if section.start_page is not None:
            section_data["start_page"] = section.start_page
        if section.end_page is not None:
            section_data["end_page"] = section.end_page
        if section.level is not None:
            section_data["level"] = section.level
        if section.section_title is not None:
            section_data["section_title"] = section.section_title
        
        result_dict["sections"].append(section_data)
    
    # Calculate usage summary and costs
    from paperprocessor.client import _calculate_usage_summary
    usage_summary = _calculate_usage_summary(processed_content.step_costs)
    result_dict["usage_summary"] = usage_summary
    result_dict["total_cost"] = usage_summary.get("total_cost")
    if result_dict["total_cost"] and result_dict["num_pages"] > 0:
        result_dict["avg_cost_per_page"] = result_dict["total_cost"] / result_dict["num_pages"]
    
    # Step 3: Convert JSON to string for database storage
    json_string = _json.dumps(result_dict, ensure_ascii=False)
    
    # Step 4: Create or update paper record in database
    paper_data = {
        'paper_uuid': paper_uuid,
        'arxiv_id': arxiv_id,
        'title': processed_content.title,
        'authors': processed_content.authors,
        'status': 'completed',
        'num_pages': len(processed_content.pages),
        'total_cost': result_dict["total_cost"],
        'avg_cost_per_page': result_dict["avg_cost_per_page"],
        'thumbnail_data_url': result_dict["thumbnail_data_url"],
        'processed_content': json_string,
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
    Loads both database metadata and full processing results from database.
    
    Returns:
        Paper: Complete paper with metadata and content (pages, sections)
        
    Raises:
        FileNotFoundError: If paper with UUID not found or no processed content
    """
    # Step 1: Get database record with processed_content loaded
    record = get_paper_record(db, paper_uuid, load_content=True)
    
    # Step 2: Check for processed content in database
    if not record.processed_content:
        raise FileNotFoundError(f"No processed content found for paper {paper_uuid}")
    
    # Step 3: Parse JSON from database
    try:
        result_dict = _json.loads(record.processed_content)
    except Exception as e:
        raise RuntimeError(f"Failed to parse processed content for paper {paper_uuid}: {e}")
    
    # Step 4: Convert database record to Paper DTO with basic metadata
    paper = Paper.model_validate(record)
    
    # Step 5: Convert legacy JSON format to our DTOs
    
    # Convert pages from legacy format
    pages = []
    for page_data in result_dict.get("pages", []):
        # Extract base64 from data URL
        image_data_url = page_data.get("image_data_url", "")
        if image_data_url.startswith("data:image/png;base64,"):
            img_base64 = image_data_url[len("data:image/png;base64,"):]
        else:
            img_base64 = ""
        
        page = Page(
            page_number=page_data.get("page_number", 0),
            img_base64=img_base64
        )
        pages.append(page)
    
    # Convert sections from legacy format
    sections = []
    for idx, section_data in enumerate(result_dict.get("sections", [])):
        section = Section(
            order_index=idx,
            rewritten_content=section_data["rewritten_content"],  # Required field - fail if missing
            start_page=section_data.get("start_page"),  # Optional - None if missing
            end_page=section_data.get("end_page"),  # Optional - None if missing
            level=section_data.get("level"),  # Optional - None if missing
            section_title=section_data.get("section_title"),  # Optional - None if missing
            summary=section_data.get("summary"),  # Optional - None if missing
            subsections=section_data.get("subsections", [])  # Default to empty list for this one
        )
        sections.append(section)
    
    # Step 6: Add content to paper DTO
    paper.pages = pages
    paper.sections = sections
    
    return paper


