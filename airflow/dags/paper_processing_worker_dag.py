import sys
import os
import pendulum
import asyncio
import fitz  # PyMuPDF
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, NamedTuple, List, Dict, Any

from airflow.decorators import dag, task
from sqlalchemy import text
from sqlalchemy.orm import Session

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.models import Paper
from papers.client import save_paper, create_paper_slug
from papers.db.models import PaperRecord
from shared.arxiv.client import fetch_pdf_for_processing
from paperprocessor.client import process_paper_pdf
from paperprocessor.models import ProcessedDocument
from users.client import set_requests_processed


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_PDF_PAGES = 70
MAX_PAPERS_PER_RUN = 10
MAX_PARALLEL_TASKS = 10


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class JobInfo(NamedTuple):
    """Simple data structure for job information (avoids SQLAlchemy session issues)."""
    id: int
    paper_uuid: str
    arxiv_id: Optional[str]
    arxiv_url: Optional[str]
    pdf_url: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert JobInfo to dictionary for Airflow task serialization.
        
        Returns:
            Dict[str, Any]: Dictionary containing all job information fields
        """
        return {
            "id": self.id,
            "paper_uuid": self.paper_uuid,
            "arxiv_id": self.arxiv_id,
            "arxiv_url": self.arxiv_url,
            "pdf_url": self.pdf_url
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobInfo":
        """
        Create JobInfo instance from dictionary.
        
        Args:
            data: Dictionary containing job information fields
            
        Returns:
            JobInfo: JobInfo instance created from dictionary data
        """
        return cls(
            id=data["id"],
            paper_uuid=data["paper_uuid"],
            arxiv_id=data.get("arxiv_id"),
            arxiv_url=data.get("arxiv_url"),
            pdf_url=data.get("pdf_url")
        )


# ============================================================================
# DATABASE HELPERS
# ============================================================================

@contextmanager
def database_session():
    """
    Create a database session with automatic commit/rollback handling.
    
    Yields:
        Session: SQLAlchemy session for database operations
        
    Raises:
        Exception: Any database error that occurs during the transaction
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================================
# PAPER PROCESSING FUNCTIONS
# ============================================================================

async def _download_and_process_paper(job: JobInfo) -> ProcessedDocument:
    """
    Download PDF and process it through the complete pipeline.

    Supports both arXiv papers and direct PDF URLs.

    Args:
        job: Paper job information with either arXiv details or PDF URL

    Returns:
        ProcessedDocument: Fully processed document with all content

    Raises:
        Exception: If PDF download or processing fails, or if PDF has too many pages
        ValueError: If neither arXiv ID nor PDF URL is provided
    """
    # Step 1: Download PDF based on source
    if job.arxiv_id:
        # arXiv paper - use existing arXiv client
        print(f"Downloading PDF for arXiv ID: {job.arxiv_id}")
        pdf_data = await fetch_pdf_for_processing(job.arxiv_url or job.arxiv_id)
        pdf_bytes = pdf_data.pdf_bytes
    elif job.pdf_url:
        # Non-arXiv paper - download from direct URL
        print(f"Downloading PDF from URL: {job.pdf_url}")
        from shared.pdf_utils import download_pdf
        pdf_bytes = download_pdf(job.pdf_url)
    else:
        raise ValueError("Job must have either arxiv_id or pdf_url")

    # Step 2: Check page count before expensive processing
    identifier = job.arxiv_id or job.pdf_url
    print(f"Checking page count for paper: {identifier}")
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = pdf_document.page_count
    pdf_document.close()

    print(f"PDF has {page_count} pages")

    if page_count > MAX_PDF_PAGES:
        raise Exception(f"Too many pages: {page_count} pages (maximum allowed: {MAX_PDF_PAGES})")

    # Step 3: Process PDF through pipeline
    print(f"Processing PDF through pipeline")
    processed_document = await process_paper_pdf(pdf_bytes)

    # Step 4: Add job metadata to processed document
    processed_document.paper_uuid = job.paper_uuid
    processed_document.arxiv_id = job.arxiv_id

    return processed_document


def _claim_next_job(session: Session) -> Optional[JobInfo]:
    """
    Claim the next available paper job using database locking.
    
    Args:
        session: Active database session
        
    Returns:
        Optional[JobInfo]: Next job to process, or None if queue is empty
    """
    # Step 1: Find and lock next available job
    job_row = session.execute(
        text(
            """
            SELECT id FROM papers
            WHERE status = 'not_started'
            ORDER BY RAND()
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        )
    ).first()
    
    if not job_row:
        return None
    
    # Step 2: Load and update job record
    job_record: PaperRecord = session.get(PaperRecord, job_row[0], with_for_update=True)
    if not job_record:
        print(f"Warning: Job {job_row[0]} disappeared during locking")
        return None
    
    # Step 3: Mark job as processing and extract data we need
    job_record.status = 'processing'
    job_record.started_at = datetime.utcnow()
    job_record.updated_at = datetime.utcnow()
    session.add(job_record)
    session.flush()
    
    # Step 4: Create simple data structure (avoids session detachment issues)
    job_info = JobInfo(
        id=job_record.id,
        paper_uuid=job_record.paper_uuid,
        arxiv_id=job_record.arxiv_id,
        arxiv_url=job_record.arxiv_url,
        pdf_url=job_record.pdf_url
    )

    print(f"Claimed job {job_info.id} for processing (arXiv: {job_info.arxiv_id}, PDF URL: {job_info.pdf_url})")
    return job_info


def _claim_available_jobs(session: Session, max_jobs: int) -> List[JobInfo]:
    """
    Claim multiple available paper jobs using database locking.
    
    Args:
        session: Active database session
        max_jobs: Maximum number of jobs to claim
        
    Returns:
        List[JobInfo]: List of claimed jobs (may be fewer than max_jobs if queue is empty)
    """
    claimed_jobs = []
    
    for _ in range(max_jobs):
        job = _claim_next_job(session)
        if not job:
            break
        claimed_jobs.append(job)
    
    return claimed_jobs


def _mark_job_failed(session: Session, job_id: int, error_message: str) -> None:
    """
    Mark a job as failed with error details.
    
    Args:
        session: Active database session
        job_id: ID of the failed job
        error_message: Description of the failure
    """
    job_record = session.get(PaperRecord, job_id, with_for_update=True)
    if not job_record:
        print(f"Warning: Cannot mark job {job_id} as failed - not found")
        return
    
    job_record.status = 'failed'
    job_record.error_message = error_message
    job_record.finished_at = datetime.utcnow()
    job_record.updated_at = datetime.utcnow()
    session.add(job_record)
    
    print(f"Marked job {job_id} as failed: {error_message}")


async def _process_paper_job_complete(job: JobInfo) -> None:
    """
    Process a paper job through the complete pipeline and save results.
    
    Args:
        job: Paper job information to process
        
    Raises:
        Exception: If any step of processing fails
    """
    processing_start = datetime.utcnow()
    print(f"Starting processing for job {job.id} (arXiv: {job.arxiv_id})")
    
    try:
        # Step 1: Download and process PDF
        processed_document = await _download_and_process_paper(job)
        
        # Step 2: Save all results in single database transaction
        with database_session() as session:
            # Save processed document to database and JSON file
            saved_paper = save_paper(session, processed_document)
            
            # Create URL slug for the paper
            paper_slug_dto = create_paper_slug(session, saved_paper)
            
            # Mark user requests as processed
            session.flush()  # Ensure slug is committed before marking requests
            await set_requests_processed(session, saved_paper.arxiv_id, paper_slug_dto.slug)
        
        processing_time = (datetime.utcnow() - processing_start).total_seconds()
        print(f"Successfully completed job {job.id} in {processing_time:.1f} seconds")
        
    except Exception as error:
        processing_time = (datetime.utcnow() - processing_start).total_seconds()
        error_msg = f"Processing failed after {processing_time:.1f}s: {str(error)}"
        
        print(f"Job {job.id} failed: {error_msg}")
        
        # Mark job as failed in separate transaction
        with database_session() as session:
            _mark_job_failed(session, job.id, error_msg)
        
        raise Exception(error_msg)


@dag(
    dag_id="paper_processing_worker",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 2,14 * * *",  # Twice daily at 2 AM and 2 PM UTC
    catchup=False,
    max_active_runs=1,  # Prevent overlapping runs
    max_active_tasks=MAX_PARALLEL_TASKS,  # Maximum concurrent paper processing tasks
    tags=["papers", "worker"],
    doc_md="""
    ### Paper Processing Worker DAG

    This DAG processes papers from the queue that are in 'not_started' status.

    - Runs twice daily at 2 AM and 2 PM UTC
    - Processes up to 10 papers per run (randomly selected, processed in parallel)
    - Processes papers through simplified pipeline: PDF download → OCR → metadata extraction → summary generation → saving → slug creation
    - Uses database locking to prevent race conditions
    - Handles errors gracefully and marks failed jobs
    - Processes papers in parallel using Airflow dynamic task mapping

    Simplified pipeline (no section rewriting): faster processing and lower costs.
    Replaces the previous supervisord-based worker with better Airflow integration.
    """,
)
def paper_processing_worker_dag():
    
    @task
    def claim_available_jobs() -> List[Dict[str, Any]]:
        """
        Claim available paper jobs from the queue.
        
        Returns:
            List[Dict]: List of job dictionaries for parallel processing
        """
        print(f"Claiming up to {MAX_PAPERS_PER_RUN} jobs from queue...")
        
        with database_session() as session:
            jobs = _claim_available_jobs(session, MAX_PAPERS_PER_RUN)
        
        if not jobs:
            print("No papers found in queue")
            return []
        
        print(f"Claimed {len(jobs)} jobs for parallel processing")
        
        # Convert to dictionaries for Airflow serialization
        return [job.to_dict() for job in jobs]
    
    @task
    def process_single_paper(job_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single paper job through the complete pipeline.
        
        Args:
            job_dict: Job information dictionary
            
        Returns:
            dict: Processing result with status and job_id
        """
        job = JobInfo.from_dict(job_dict)
        
        try:
            # Run async processing function
            asyncio.run(_process_paper_job_complete(job))
            return {"status": "success", "job_id": job.id}
        except Exception as e:
            print(f"Failed to process job {job.id}: {e}")
            
            # Mark job as failed to prevent stuck 'processing' status
            with database_session() as session:
                _mark_job_failed(session, job.id, str(e))
            
            return {"status": "failed", "job_id": job.id, "error": str(e)}
    
    @task
    def aggregate_results(results: List[Dict[str, Any]]) -> dict:
        """
        Aggregate processing results from all parallel tasks.
        
        Args:
            results: List of result dictionaries from parallel processing tasks
            
        Returns:
            dict: Summary of processing results
        """
        processed_count = sum(1 for r in results if r.get("status") == "success")
        failed_count = sum(1 for r in results if r.get("status") == "failed")
        
        if processed_count == 0 and failed_count == 0:
            print("No papers were processed")
        else:
            print(f"Processing complete: {processed_count} successful, {failed_count} failed")
        
        return {
            "processed": processed_count,
            "failed": failed_count,
            "total": processed_count + failed_count
        }
    
    # Step 1: Claim available jobs
    claimed_jobs = claim_available_jobs()
    
    # Step 2: Process each job in parallel using dynamic task mapping
    processing_results = process_single_paper.expand(job_dict=claimed_jobs)
    
    # Step 3: Aggregate results
    aggregate_results(processing_results)


paper_processing_worker_dag()
