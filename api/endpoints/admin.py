from __future__ import annotations

from datetime import datetime, timedelta, date as date_type
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from api.types.paper_processing_endpoints import JobDbStatus
from api.types.admin import (
    RequestedPaperItem,
    StartProcessingResponse,
    DeleteRequestedResponse,
    RestartPaperRequest,
    ImportResult,
    CumulativeDailyPaperItem,
)
from paperprocessor.client import get_processing_metrics_for_admin
from papers.client import build_paper_slug
from papers.models import Paper, PaperSlug
from papers.db.models import PaperRecord, PaperSlugRecord, PaperStatusHistory
from papers.client import get_paper_metadata
from shared.arxiv.client import normalize_id, fetch_metadata, download_pdf
from shared.db import get_session
from papers import client as papers_client
from users import client as users_client

import os
import uuid
import logging
import re


router = APIRouter()
logger = logging.getLogger(__name__)


# --- Simple HTTP Basic admin protection ---
security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    import secrets

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


# --- Pydantic response/request models imported from api/types/admin.py ---


# --- Admin: Papers list ---
@router.get("/admin/papers", response_model=List[JobDbStatus])
def admin_list_papers(status: Optional[str] = None, limit: int = 500, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    rows = papers_client.list_papers(db, statuses, limit)
    return [
        JobDbStatus(
            paper_uuid=r.paper_uuid,
            status=r.status,
            error_message=r.error_message,
            created_at=r.created_at,
            updated_at=r.updated_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
            arxiv_id=r.arxiv_id,
            arxiv_version=r.arxiv_version,
            arxiv_url=r.arxiv_url,
            title=r.title,
            authors=r.authors,
            num_pages=r.num_pages,
            thumbnail_data_url=None,  # Not needed in admin list view
            processing_time_seconds=r.processing_time_seconds,
            total_cost=r.total_cost,
            avg_cost_per_page=r.avg_cost_per_page,
        )
        for r in rows
    ]


## RestartPaperRequest imported from api/types/admin.py


@router.post("/admin/papers/{paper_uuid}/restart", status_code=200)
def admin_restart_paper(paper_uuid: uuid.UUID, _body: RestartPaperRequest | None = None, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    from sqlalchemy.orm import defer
    row = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == str(paper_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Paper not found")
    if row.status == "processing":
        raise HTTPException(status_code=409, detail="Paper is already processing")
    # Reset for reprocessing
    row.status = "not_started"
    row.error_message = None
    row.started_at = None
    row.finished_at = None
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {"paper_uuid": str(paper_uuid), "status": row.status}


@router.delete("/admin/papers/{paper_uuid}", status_code=200)
def admin_delete_paper(paper_uuid: uuid.UUID, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    ok = papers_client.delete_paper(db, str(paper_uuid))
    if not ok:
        raise HTTPException(status_code=404, detail="Paper not found")
    return {"deleted": str(paper_uuid)}


# --- Admin: Requested papers management ---
@router.get("/admin/requested_papers", response_model=List[RequestedPaperItem])
def admin_list_requested_papers(include_processed: bool = False, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    items = users_client.list_aggregated_user_requests_for_admin(db, limit=500, offset=0)
    return [RequestedPaperItem(**it) for it in items]


@router.post("/admin/requested_papers/{arxiv_id_or_url}/start_processing", response_model=StartProcessingResponse)
async def admin_start_processing_requested(arxiv_id_or_url: str, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    # Normalize to base id
    try:
        norm = await normalize_id(arxiv_id_or_url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv id or URL")
    base_id = norm.arxiv_id
    version = norm.version

    now = datetime.utcnow()

    # Check if paper already exists in DB
    from sqlalchemy.orm import defer
    job = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.arxiv_id == base_id).first()
    if job:
        # Do not modify existing job; return its identity
        return StartProcessingResponse(paper_uuid=job.paper_uuid, status=job.status)

    # Create new papers row with status 'not_started'
    paper_uuid = str(uuid.uuid4())
    new_job = PaperRecord(
        paper_uuid=paper_uuid,
        arxiv_id=base_id,
        arxiv_version=version,
        arxiv_url=f"https://arxiv.org/abs/{base_id}{version or ''}",
        status="not_started",
        created_at=now,
        updated_at=now,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return StartProcessingResponse(paper_uuid=new_job.paper_uuid, status=new_job.status)


@router.delete("/admin/requested_papers/{arxiv_id_or_url}", response_model=DeleteRequestedResponse)
async def admin_delete_requested_paper(arxiv_id_or_url: str, db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    try:
        norm = await normalize_id(arxiv_id_or_url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid arXiv id or URL")
    base_id = norm.arxiv_id
    # Delete all per-user requests for this arXiv id
    _ = users_client.delete_all_requests_for_arxiv(db, base_id)
    return DeleteRequestedResponse(deleted=base_id)


# --- Admin: Import worker-generated JSON into DB and filesystem ---


def _derive_arxiv_version_from_url(arxiv_url: Optional[str]) -> Optional[str]:
    if not arxiv_url:
        return None
    try:
        # Expect formats like https://arxiv.org/abs/<id>v3 (optional version)
        m = re.search(r"/abs/[^/]+?(v\d+)$", arxiv_url)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


@router.post("/admin/papers/import_json", response_model=JobDbStatus)
def admin_import_paper_json(paper: Dict[str, Any], db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    # Validate minimal required fields
    paper_id = paper.get("paper_id")
    arxiv_id = paper.get("arxiv_id")
    if not isinstance(paper_id, str) or not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required in JSON")
    if not isinstance(arxiv_id, str) or not arxiv_id:
        raise HTTPException(status_code=400, detail="arxiv_id is required in JSON")

    title = paper.get("title") if isinstance(paper.get("title"), str) else None
    authors = paper.get("authors") if isinstance(paper.get("authors"), str) else None
    arxiv_url_val = paper.get("arxiv_url") if isinstance(paper.get("arxiv_url"), str) else None
    arxiv_version_val = _derive_arxiv_version_from_url(arxiv_url_val)
    thumbnail_data_url = paper.get("thumbnail_data_url") if isinstance(paper.get("thumbnail_data_url"), str) else None
    pages = paper.get("pages") if isinstance(paper.get("pages"), list) else []
    num_pages = len(pages)
    processing_time_seconds = paper.get("processing_time_seconds")
    if not isinstance(processing_time_seconds, (int, float)):
        processing_time_seconds = None
    usage_summary = paper.get("usage_summary") or {}
    total_cost = usage_summary.get("total_cost") if isinstance(usage_summary, dict) else None
    if not isinstance(total_cost, (int, float)):
        total_cost = None
    avg_cost_per_page = None
    try:
        if total_cost is not None and num_pages > 0:
            avg_cost_per_page = float(total_cost) / float(num_pages)
    except Exception:
        avg_cost_per_page = None

    now = datetime.utcnow()

    # Upsert by arxiv_id
    from sqlalchemy.orm import defer
    existing = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.arxiv_id == arxiv_id).first()
    if existing:
        target_uuid = existing.paper_uuid
        # Update existing row to completed
        existing.status = "completed"
        existing.error_message = None
        existing.updated_at = now
        existing.finished_at = now
        existing.title = title
        existing.authors = authors
        existing.arxiv_url = arxiv_url_val
        existing.arxiv_version = arxiv_version_val
        existing.num_pages = num_pages
        existing.processing_time_seconds = processing_time_seconds
        existing.total_cost = total_cost
        existing.avg_cost_per_page = avg_cost_per_page
        existing.thumbnail_data_url = thumbnail_data_url
        db.add(existing)
        db.flush()
        target_paper_row = existing
    else:
        # Ensure paper_uuid uniqueness; if collides with another arxiv_id, generate a new one
        target_uuid = paper_id
        from sqlalchemy.orm import defer
        by_uuid = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == target_uuid).first()
        if by_uuid and by_uuid.arxiv_id != arxiv_id:
            target_uuid = str(uuid.uuid4())
        new_row = PaperRecord(
            paper_uuid=target_uuid,
            arxiv_id=arxiv_id,
            arxiv_version=arxiv_version_val,
            arxiv_url=arxiv_url_val,
            title=title,
            authors=authors,
            status="completed",
            error_message=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            finished_at=now,
            num_pages=num_pages,
            processing_time_seconds=processing_time_seconds,
            total_cost=total_cost,
            avg_cost_per_page=avg_cost_per_page,
            thumbnail_data_url=thumbnail_data_url,
        )
        db.add(new_row)
        db.flush()
        target_paper_row = new_row

    # Create slug on import; idempotent for same paper, strict for true collisions
    try:
        # Reuse existing non-tombstoned slug for this paper if present
        existing_for_paper = (
            db.query(PaperSlugRecord)
            .filter(PaperSlugRecord.paper_uuid == target_paper_row.paper_uuid, PaperSlugRecord.tombstone == False)  # noqa: E712
            .order_by(PaperSlugRecord.created_at.desc())
            .first()
        )
        if not existing_for_paper:
            slug = build_paper_slug(title, authors)
            exists = db.query(PaperSlugRecord).filter(PaperSlugRecord.slug == slug).first()
            if exists:
                if exists.paper_uuid != target_paper_row.paper_uuid:
                    raise HTTPException(status_code=409, detail="Slug already exists")
                # else idempotent import for same paper; do not insert
            else:
                db.add(PaperSlugRecord(slug=slug, paper_uuid=target_paper_row.paper_uuid, tombstone=False, created_at=now))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create slug for imported paper %s", target_paper_row.paper_uuid)

    db.commit()

    # Persist JSON to data/paperjsons using the chosen UUID; optionally normalize paper_id inside file
    try:
        base_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'paperjsons'))
        os.makedirs(base_dir, exist_ok=True)
        target_path = os.path.join(base_dir, f"{target_uuid}.json")
        # Ensure the internal paper_id matches the filename/DB UUID
        if paper.get('paper_id') != target_uuid:
            paper = dict(paper)
            paper['paper_id'] = target_uuid
        import json as _json
        with open(target_path, 'w', encoding='utf-8') as f:
            _json.dump(paper, f, ensure_ascii=False)
    except Exception:
        logger.exception("Failed to write imported JSON for paper_uuid=%s", target_uuid)

    # Return the DB row
    from sqlalchemy.orm import defer
    job = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == target_uuid).first()
    if not job:
        raise HTTPException(status_code=500, detail="Import completed but record not found")
    return JobDbStatus(
        paper_uuid=job.paper_uuid,
        status=job.status,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        arxiv_id=job.arxiv_id,
        arxiv_version=job.arxiv_version,
        arxiv_url=job.arxiv_url,
        title=job.title,
        authors=job.authors,
        num_pages=job.num_pages,
        thumbnail_data_url=getattr(job, 'thumbnail_data_url', None),
        processing_time_seconds=job.processing_time_seconds,
        total_cost=job.total_cost,
        avg_cost_per_page=job.avg_cost_per_page,
    )


# --- Admin: processing metrics ---
@router.get("/admin/papers/{paper_uuid}/processing_metrics")
def admin_get_processing_metrics(paper_uuid: str, _admin: bool = Depends(require_admin)):
    try:
        return get_processing_metrics_for_admin(paper_uuid)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# --- Admin: cumulative daily papers count ---
@router.get("/admin/papers/cumulative_daily", response_model=List[CumulativeDailyPaperItem])
def admin_get_cumulative_daily_papers(db: Session = Depends(get_session), _admin: bool = Depends(require_admin)):
    """
    Get cumulative daily count of papers from first paper to today.
    Uses historical snapshots for past dates and live inference for recent dates.
    Includes all dates in range, even days with zero papers.
    
    Returns:
        List of daily data with date, daily_count, cumulative_count, and cumulative counts per status
    """
    # Check if there are any papers first
    paper_count = db.query(func.count(PaperRecord.id)).scalar()
    if paper_count == 0:
        logger.info("No papers found in database")
        return []
    
    # Get latest snapshot date from history table
    # SQLAlchemy Date columns return date objects
    latest_snapshot = db.query(func.max(PaperStatusHistory.date)).scalar()
    latest_snapshot_date = latest_snapshot if latest_snapshot else None
    
    logger.info(f"Latest snapshot date: {latest_snapshot_date}, Total papers: {paper_count}")
    
    # Get earliest paper creation date
    # MySQL DATE() function returns date objects via SQLAlchemy
    earliest_date_result = db.execute(text("SELECT MIN(DATE(created_at)) FROM papers")).scalar()
    earliest_date = earliest_date_result if earliest_date_result else None
    
    if earliest_date is None:
        logger.info("No earliest date found")
        return []
    
    logger.info(f"Earliest paper date: {earliest_date}")
    
    # Generate date series from earliest date to today
    # Cast to DATE to ensure consistent return type
    date_series_query = text("""
        WITH RECURSIVE date_series AS (
            SELECT CAST(:earliest_date AS DATE) AS date
            UNION ALL
            SELECT DATE_ADD(date, INTERVAL 1 DAY)
            FROM date_series
            WHERE date < CURDATE()
        )
        SELECT CAST(date AS DATE) AS date FROM date_series ORDER BY date
    """)
    
    date_series_result = db.execute(date_series_query, {"earliest_date": earliest_date})
    all_dates = [row[0] for row in date_series_result.fetchall()]
    
    result_items = []
    history_count = 0
    live_count = 0
    
    # Process dates: use history for past dates, live inference for recent dates
    for target_date in all_dates:
        # Normalize date: raw SQL with text() returns DATE columns as strings
        if isinstance(target_date, datetime):
            target_date_obj = target_date.date()
        elif isinstance(target_date, date_type):
            target_date_obj = target_date
        elif isinstance(target_date, str):
            # MySQL DATE columns are returned as strings when using raw SQL
            target_date_obj = datetime.strptime(target_date.split()[0], '%Y-%m-%d').date()
        else:
            # Fallback: convert to string and parse
            target_date_obj = datetime.strptime(str(target_date).split()[0], '%Y-%m-%d').date()
        
        target_date_str = target_date_obj.isoformat()
        
        # Use historical snapshot if available
        if latest_snapshot_date and target_date_obj <= latest_snapshot_date:
            snapshot = db.query(PaperStatusHistory).filter(
                PaperStatusHistory.date == target_date_obj
            ).first()
            
            if snapshot:
                history_count += 1
                # Calculate daily_count from previous day's total
                prev_total = 0
                if target_date_obj > earliest_date:
                    prev_date = target_date_obj - timedelta(days=1)
                    prev_snapshot = db.query(PaperStatusHistory).filter(
                        PaperStatusHistory.date == prev_date
                    ).first()
                    if prev_snapshot:
                        prev_total = prev_snapshot.total_count
                    elif len(result_items) > 0:
                        # Fallback to last result if no snapshot found
                        prev_total = result_items[-1].cumulative_count
                
                daily_count = snapshot.total_count - prev_total
                
                result_items.append(CumulativeDailyPaperItem(
                    date=target_date_str,
                    daily_count=daily_count,
                    cumulative_count=snapshot.total_count,
                    cumulative_failed=snapshot.failed_count,
                    cumulative_processed=snapshot.processed_count,
                    cumulative_not_started=snapshot.not_started_count,
                    cumulative_processing=snapshot.processing_count
                ))
                continue
            else:
                logger.warning(f"No snapshot found for date {target_date_str} (within snapshot range)")
        
        # Use live inference for dates after latest snapshot
        # Calculate cumulative counts using timestamp inference
        target_datetime = datetime.combine(target_date_obj, datetime.min.time())
        live_query = text("""
            SELECT 
                COUNT(*) AS total_count,
                SUM(CASE 
                    WHEN (started_at IS NULL OR started_at > :target_datetime) THEN 1 
                    ELSE 0 
                END) AS not_started_count,
                SUM(CASE 
                    WHEN (started_at IS NOT NULL AND started_at <= :target_datetime 
                          AND (finished_at IS NULL OR finished_at > :target_datetime)) THEN 1 
                    ELSE 0 
                END) AS processing_count,
                SUM(CASE 
                    WHEN (finished_at IS NOT NULL AND finished_at <= :target_datetime 
                          AND error_message IS NOT NULL) THEN 1 
                    ELSE 0 
                END) AS failed_count,
                SUM(CASE 
                    WHEN (finished_at IS NOT NULL AND finished_at <= :target_datetime 
                          AND error_message IS NULL) THEN 1 
                    ELSE 0 
                END) AS processed_count
            FROM papers
            WHERE DATE(created_at) <= :target_date
        """)
        
        live_result = db.execute(live_query, {
            "target_date": target_date_obj,
            "target_datetime": target_datetime
        }).first()
        
        if live_result:
            # Calculate daily_count from previous day's total
            prev_total = 0
            if len(result_items) > 0:
                prev_total = result_items[-1].cumulative_count
            
            daily_count = (live_result.total_count or 0) - prev_total
            live_count += 1
            
            result_items.append(CumulativeDailyPaperItem(
                date=target_date_str,
                daily_count=daily_count,
                cumulative_count=int(live_result.total_count or 0),
                cumulative_failed=int(live_result.failed_count or 0),
                cumulative_processed=int(live_result.processed_count or 0),
                cumulative_not_started=int(live_result.not_started_count or 0),
                cumulative_processing=int(live_result.processing_count or 0)
            ))
    
    logger.info(f"Returning {len(result_items)} items: {history_count} from history, {live_count} from live inference")
    return result_items



