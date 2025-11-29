from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Union, List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.types.paper_processing_api_models import Paper, JobStatusResponse, MinimalPaperItem, PaginatedMinimalPapers
from api.types.paper_processing_endpoints import JobDbStatus
from paperprocessor.client import process_paper_pdf
from papers.client import build_paper_slug
from shared.db import get_session
from papers.models import Paper, PaperSlug
from papers.db.models import PaperRecord, PaperSlugRecord
from papers import client as papers_client
from shared.arxiv.client import normalize_id, parse_url, fetch_metadata, download_pdf
from shared.arxiv.models import ArxivMetadata
import os
import uuid
from datetime import datetime
from uuid import UUID
from api.background_jobs import create_job, get_job_status, update_job_status
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Simple HTTP Basic admin protection ---
security = HTTPBasic()

def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    import os, secrets
    expected_user = "admin"
    expected_pass = os.environ.get("ADMIN_BASIC_PASSWORD", "")
    ok_user = secrets.compare_digest(credentials.username, expected_user)
    ok_pass = secrets.compare_digest(credentials.password, expected_pass)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="Management"'},
        )
    return True

async def process_paper_in_background(job_id: str, contents: bytes):
    """
    A wrapper function to run the PDF processing in the background
    and update the job status upon completion or failure.
    """
    try:
        # Use new processing pipeline
        import time
        _t0 = time.perf_counter()
        
        doc = await process_paper_pdf(contents)
        
        # Convert to legacy dict format for API compatibility
        from paperprocessor.client import _calculate_usage_summary
        
        # Helper to build data URL for a base64-encoded PNG
        def _as_data_url_png(b64: str) -> str:
            return f"data:image/png;base64,{b64}"

        # Pages list in legacy format
        pages = []
        for idx, page in enumerate(doc.pages):
            pages.append({
                "page_number": idx + 1,
                "image_data_url": _as_data_url_png(page.img_base64),
            })

        # Thumbnail: use full first page image as a simple thumbnail
        thumbnail_data_url = None
        if doc.pages:
            thumbnail_data_url = _as_data_url_png(doc.pages[0].img_base64)

        # Sections: flat list of rewritten contents
        sections = []
        for s in doc.sections:
            sections.append({
                "rewritten_content": s.rewritten_content,
            })

        # Convert individual images from pages to legacy figures format
        figures = []
        for page in doc.pages:
            for processed_image in page.images:
                figures.append({
                    "figure_identifier": processed_image.uuid,
                    "location_page": processed_image.page_number,
                    "explanation": "",  # Not extracted in current pipeline
                    "image_path": "",   # Not used - we store base64 directly
                    "image_data_url": f"data:image/png;base64,{processed_image.img_base64}",
                    "referenced_on_pages": [processed_image.page_number],
                    "bounding_box": [
                        processed_image.top_left_x,
                        processed_image.top_left_y,
                        processed_image.bottom_right_x,
                        processed_image.bottom_right_y
                    ],
                    "page_image_size": None  # Unknown - not stored in ProcessedPage
                })

        # Metrics
        processing_time_seconds = max(0.0, time.perf_counter() - _t0)
        num_pages = len(doc.pages)
        
        # Calculate usage summary from collected step costs
        usage_summary = _calculate_usage_summary(doc.step_costs)
        total_cost = usage_summary.get("total_cost")
        avg_cost_per_page = (total_cost / num_pages) if total_cost and num_pages > 0 else None

        result = {
            "paper_id": job_id,
            "title": doc.title,
            "authors": doc.authors,
            "thumbnail_data_url": thumbnail_data_url,
            "sections": sections,
            "tables": [],
            "figures": figures,
            "pages": pages,
            "usage_summary": usage_summary,
            "processing_time_seconds": processing_time_seconds,
            "num_pages": num_pages,
            "total_cost": total_cost,
            "avg_cost_per_page": avg_cost_per_page,
        }
        
        update_job_status(job_id, "completed", result)
        logger.info(f"Job {job_id} completed successfully.")
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        update_job_status(job_id, "failed", str(e))

@router.post("/papers/process", status_code=status.HTTP_202_ACCEPTED, response_model=JobStatusResponse)
async def process_paper(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Accepts a PDF file, starts a background processing job, and returns a job ID.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs are accepted.")

    contents = await file.read()
    job_id = create_job()
    
    background_tasks.add_task(process_paper_in_background, job_id, contents)
    
    return {"job_id": job_id, "status": "processing"}

@router.get("/papers/process/{job_id}", response_model=Union[Paper, JobStatusResponse])
async def get_paper_status(job_id: str, response: Response):
    """
    Polls for the status of a paper processing job.
    - Returns a 202 status code while the job is processing.
    - Returns the final JSON result with a 200 status code upon completion.
    - Returns an error if the job failed.
    """
    job = get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job["status"] == "processing":
        response.status_code = status.HTTP_202_ACCEPTED
        return {"job_id": job_id, "status": "processing"}
    
    if job["status"] == "failed":
        raise HTTPException(status_code=500, detail=job.get("result", "An unknown error occurred."))

    # If completed, Pydantic will automatically validate and return the Paper model
    return job["result"] 


class EnqueueArxivRequest(BaseModel):
    url: str


class EnqueueArxivResponse(BaseModel):
    job_db_id: int
    paper_uuid: str
    status: str


@router.post("/papers/enqueue_arxiv", response_model=EnqueueArxivResponse)
async def enqueue_arxiv(req: EnqueueArxivRequest, db: Session = Depends(get_session)):
    try:
        norm = await normalize_id(req.url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv URL or identifier")

    paper_uuid = str(uuid.uuid4())

    # Duplicate check
    from sqlalchemy.orm import defer
    existing = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.arxiv_id == norm.arxiv_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="A paper with this arXiv ID already exists")

    job = PaperRecord(
        paper_uuid=paper_uuid,
        arxiv_id=norm.arxiv_id,
        arxiv_version=norm.version,
        arxiv_url=req.url,
        status="not_started",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return EnqueueArxivResponse(job_db_id=job.id, paper_uuid=paper_uuid, status=job.status)


## Moved JobDbStatus to api/types/paper_processing_endpoints.py


 
@router.get("/papers/minimal")
def list_minimal_papers(
    page: Optional[int] = None,
    limit: Optional[int] = None,
    db: Session = Depends(get_session)
):
    """
    Returns a minimal list of papers: paper_uuid, title, authors, thumbnail_data_url, slug.
    Supports optional pagination with page and limit query parameters.

    If both page and limit are provided, returns paginated response.
    Otherwise, returns legacy list format.

    Delegates to papers.client.list_minimal_papers.
    """
    result = papers_client.list_minimal_papers(db, page=page, limit=limit)
    return result


class CountPapersSinceResponse(BaseModel):
    count: int


@router.get("/papers/count_since", response_model=CountPapersSinceResponse)
def count_papers_since(since: str, db: Session = Depends(get_session)):
    """
    Counts completed papers processed after the given timestamp.
    
    Args:
        since: ISO timestamp string (e.g., "2025-01-20T10:30:00.000Z")
        db: Database session
        
    Returns:
        Count of completed papers with finished_at > since
    """
    try:
        # Parse ISO timestamp and convert to naive UTC datetime for database comparison
        since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        # Database stores naive UTC datetimes, so convert timezone-aware to naive UTC
        if since_dt.tzinfo is not None:
            since_dt = since_dt.replace(tzinfo=None)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid timestamp format. Expected ISO format.")
    
    count = db.query(PaperRecord).filter(
        PaperRecord.status == "completed",
        PaperRecord.finished_at > since_dt
    ).count()
    
    return CountPapersSinceResponse(count=count)





# --- Paper existence check ---

class CheckArxivResponse(BaseModel):
    exists: bool
    viewer_url: Optional[str] = None


@router.get("/papers/check_arxiv/{arxiv_id_or_url}", response_model=CheckArxivResponse)
async def check_arxiv(arxiv_id_or_url: str, db: Session = Depends(get_session)):
    """
    Checks if an arXiv paper has been processed and is available, without side-effects.
    Returns the viewer URL if it exists.
    """
    try:
        norm = await normalize_id(arxiv_id_or_url)
        arxiv_id = norm.arxiv_id
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv URL or identifier")

    job = db.query(PaperRecord).filter(PaperRecord.arxiv_id == arxiv_id).first()
    if job and job.status == "completed" and job.processed_content:
        # Paper is completed and has processed content available
        # Resolve the latest, non-tombstoned slug for this paper
        slug_row = (
            db.query(PaperSlugRecord)
            .filter(PaperSlugRecord.paper_uuid == job.paper_uuid)
            .filter(PaperSlugRecord.tombstone == False)  # noqa: E712
            .order_by(PaperSlugRecord.created_at.desc())
            .first()
        )
        if slug_row:
            return CheckArxivResponse(exists=True, viewer_url=f"/paper/{slug_row.slug}")

    return CheckArxivResponse(exists=False, viewer_url=None)


@router.get("/arxiv-metadata/{arxiv_id_or_url}", response_model=ArxivMetadata)
async def get_arxiv_metadata(arxiv_id_or_url: str):
    """
    Fetches paper metadata directly from the arXiv API.
    """
    try:
        norm = await normalize_id(arxiv_id_or_url)
        arxiv_id = norm.arxiv_id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid arXiv URL or identifier")

    try:
        metadata = await fetch_metadata(arxiv_id)
        return metadata
    except ValueError as e:
        # fetch_metadata raises ValueError if no entry is found
        raise HTTPException(status_code=404, detail=f"Metadata not found for {arxiv_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch metadata for {arxiv_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch metadata from arXiv API")


@router.get("/papers/thumbnails/{paper_uuid}")
def get_thumbnail(paper_uuid: str, db: Session = Depends(get_session)):
    """
    Serves the thumbnail image for a paper as image bytes.
    Extracts base64 data from the database and returns it as an image.
    Supports both PNG and JPEG formats.
    Supports browser caching via HTTP headers.
    """
    from sqlalchemy.orm import defer
    import base64

    # Query only the thumbnail field to minimize data transfer
    record = db.query(PaperRecord).options(
        defer(PaperRecord.processed_content)
    ).filter(PaperRecord.paper_uuid == paper_uuid).first()

    if not record or not record.thumbnail_data_url:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    # Determine format and extract base64 from data URL
    data_url = record.thumbnail_data_url

    if data_url.startswith("data:image/png;base64,"):
        media_type = "image/png"
        base64_data = data_url.split(",", 1)[1]
    elif data_url.startswith("data:image/jpeg;base64,"):
        media_type = "image/jpeg"
        base64_data = data_url.split(",", 1)[1]
    elif data_url.startswith("data:image/jpg;base64,"):
        media_type = "image/jpeg"
        base64_data = data_url.split(",", 1)[1]
    else:
        logger.error(f"Unsupported thumbnail format for {paper_uuid}: {data_url[:50]}...")
        raise HTTPException(status_code=404, detail="Invalid thumbnail format")

    try:
        image_bytes = base64.b64decode(base64_data)
        return Response(
            content=image_bytes,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",  # Cache for 1 year
            }
        )
    except Exception as e:
        logger.error(f"Failed to decode thumbnail for {paper_uuid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to decode thumbnail")




# --- Slug generation and resolution ---


class ResolveSlugResponse(BaseModel):
    paper_uuid: Optional[str]
    slug: str
    tombstone: bool


@router.get("/papers/slug/{slug}", response_model=ResolveSlugResponse)
def resolve_slug(slug: str, db: Session = Depends(get_session)):
    logger.info("GET /papers/slug/%s", slug)
    row = db.query(PaperSlugRecord).filter(PaperSlugRecord.slug == slug).first()
    if not row:
        logger.warning("Slug not found slug=%s", slug)
        raise HTTPException(status_code=404, detail="Slug not found")
    logger.info("Resolved slug=%s -> paper_uuid=%s tombstone=%s", slug, row.paper_uuid, bool(getattr(row, 'tombstone', False)))
    return ResolveSlugResponse(paper_uuid=row.paper_uuid, slug=row.slug, tombstone=bool(getattr(row, 'tombstone', False)))


class CreateSlugRequest(BaseModel):
    paper_uuid: str


@router.post("/papers/{paper_uuid}/slug", response_model=ResolveSlugResponse)
def create_slug(paper_uuid: UUID, db: Session = Depends(get_session)):
    # Load paper and validate required metadata
    logger.info("POST /papers/%s/slug (create)", paper_uuid)
    from sqlalchemy.orm import defer
    job = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()
    if not job:
        logger.warning("Cannot create slug: paper not found paper_uuid=%s", paper_uuid)
        raise HTTPException(status_code=404, detail="Paper not found")

    # If this paper already has a non-tombstoned slug, return it (idempotent)
    existing_for_paper = (
        db.query(PaperSlugRecord)
        .filter(PaperSlugRecord.paper_uuid == str(paper_uuid))
        .filter(PaperSlugRecord.tombstone == False)  # noqa: E712
        .order_by(PaperSlugRecord.created_at.desc())
        .first()
    )
    if existing_for_paper:
        return ResolveSlugResponse(paper_uuid=existing_for_paper.paper_uuid, slug=existing_for_paper.slug, tombstone=False)

    try:
        slug = build_paper_slug(job.title, job.authors)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Enforce uniqueness strictly; allow if it already maps to this paper
    existing = db.query(PaperSlugRecord).filter(PaperSlugRecord.slug == slug).first()
    if existing:
        if existing.paper_uuid != str(paper_uuid):
            raise HTTPException(status_code=409, detail="Slug already exists")
        return ResolveSlugResponse(paper_uuid=existing.paper_uuid, slug=existing.slug, tombstone=bool(existing.tombstone))

    row = PaperSlugRecord(slug=slug, paper_uuid=paper_uuid, tombstone=False, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ResolveSlugResponse(paper_uuid=row.paper_uuid, slug=row.slug, tombstone=False)


@router.get("/papers/{paper_uuid}/slug", response_model=ResolveSlugResponse)
def get_slug_for_paper(paper_uuid: UUID, db: Session = Depends(get_session)):
    # Return latest non-tombstone slug for this paper
    logger.info("GET /papers/%s/slug", paper_uuid)
    row = (
        db.query(PaperSlugRecord)
        .filter(PaperSlugRecord.paper_uuid == str(paper_uuid))
        .filter(PaperSlugRecord.tombstone == False)  # noqa: E712
        .order_by(PaperSlugRecord.created_at.desc())
        .first()
    )
    if not row:
        logger.warning("Slug not found for paper_uuid=%s", paper_uuid)
        raise HTTPException(status_code=404, detail="Slug not found for paper")
    logger.info("Resolved latest slug for paper_uuid=%s -> slug=%s", paper_uuid, row.slug)
    return ResolveSlugResponse(paper_uuid=row.paper_uuid, slug=row.slug, tombstone=False)


@router.get("/papers/{paper_uuid}/summary")
def get_paper_summary(paper_uuid: UUID, db: Session = Depends(get_session)):
    """
    Get lightweight paper summary with metadata only.
    Returns only the essential fields needed for the paper detail page:
    title, authors, arxiv_url, five_minute_summary, page_count, thumbnail_url.

    This endpoint is much faster than /papers/{paper_uuid} because it doesn't
    include the full page images, figures, or complete section content.

    Args:
        paper_uuid: UUID of the paper to retrieve
        db: Database session

    Returns:
        dict: Paper summary with essential metadata

    Raises:
        404: If paper not found or no processed content available
        500: If JSON parsing fails
    """
    try:
        # Get paper record - defer processed_content initially to check if it exists
        from sqlalchemy.orm import defer, undefer
        record = db.query(PaperRecord).options(
            defer(PaperRecord.processed_content)
        ).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()

        if not record:
            raise HTTPException(status_code=404, detail="Paper not found")

        # Now load processed_content to extract five_minute_summary
        db.refresh(record, ['processed_content'])

        if not record.processed_content:
            raise HTTPException(status_code=404, detail="No processed content available for this paper")

        # Parse JSON to extract five_minute_summary and page count
        import json
        paper_json = json.loads(record.processed_content)

        # Build lightweight response
        summary = {
            "paper_id": str(paper_uuid),
            "title": record.title,
            "authors": record.authors,
            "arxiv_url": record.arxiv_url,
            "five_minute_summary": paper_json.get("five_minute_summary"),
            "page_count": len(paper_json.get("pages", [])),
            "thumbnail_url": f"/api/papers/thumbnails/{paper_uuid}" if record.thumbnail_data_url else None
        }

        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve paper summary for {paper_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve paper summary: {str(e)}")


@router.get("/papers/{paper_uuid}/markdown")
def get_paper_markdown(paper_uuid: UUID, db: Session = Depends(get_session)):
    """
    Get the original markdown content from OCR processing.
    Returns only the final_markdown field (concatenated OCR output from all pages).

    This is a lightweight endpoint that returns only the text content without images,
    making it suitable for copy-to-clipboard functionality.

    Args:
        paper_uuid: UUID of the paper to retrieve
        db: Database session

    Returns:
        dict: Contains paper_uuid and final_markdown

    Raises:
        404: If paper not found, no processed content, or no markdown available
        500: If JSON parsing fails
    """
    try:
        # Get paper record - defer processed_content initially
        from sqlalchemy.orm import defer
        record = db.query(PaperRecord).options(
            defer(PaperRecord.processed_content)
        ).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()

        if not record:
            raise HTTPException(status_code=404, detail="Paper not found")

        # Load processed_content to extract final_markdown
        db.refresh(record, ['processed_content'])

        if not record.processed_content:
            raise HTTPException(status_code=404, detail="No processed content available for this paper")

        # Parse JSON to extract final_markdown
        import json
        paper_json = json.loads(record.processed_content)

        final_markdown = paper_json.get("final_markdown")
        if final_markdown is None:
            raise HTTPException(
                status_code=404,
                detail="Markdown not available for this paper. It may have been processed before markdown storage was implemented."
            )

        return {
            "paper_uuid": str(paper_uuid),
            "final_markdown": final_markdown
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve paper markdown for {paper_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve paper markdown: {str(e)}")


@router.get("/papers/{paper_uuid}")
def get_paper_json(paper_uuid: UUID, db: Session = Depends(get_session)):
    """
    Get complete paper JSON including all processed content.
    Returns the raw JSON format used by the frontend viewer.

    WARNING: This endpoint returns large payloads (10-20 MB) including all page images.
    Consider using /papers/{paper_uuid}/summary for metadata-only requests.

    Args:
        paper_uuid: UUID of the paper to retrieve
        db: Database session

    Returns:
        dict: Complete paper JSON with pages, sections, figures, etc.

    Raises:
        404: If paper not found or no processed content available
        500: If JSON parsing fails
    """
    try:
        # Get the paper record from database with processed_content explicitly loaded
        from sqlalchemy.orm import undefer
        record = db.query(PaperRecord).options(undefer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()

        if not record:
            raise HTTPException(status_code=404, detail="Paper not found")

        if not record.processed_content:
            raise HTTPException(status_code=404, detail="No processed content available for this paper")

        # Parse and return the JSON directly
        import json
        paper_json = json.loads(record.processed_content)
        return paper_json

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve paper {paper_uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve paper: {str(e)}")