"""
Backfill final_markdown for papers missing it in storage.

Downloads PDFs from arXiv, runs OCR + formatting pipeline, and uploads the
resulting content.md to Supabase Storage.

Responsibilities:
- Find completed papers missing content.md in storage
- Download PDF and run OCR pipeline
- Upload content.md to storage
- Generate summary report
"""

import sys
import pendulum
import base64
import io
from contextlib import contextmanager
from typing import List, Dict
import asyncio

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord
from shared.arxiv.client import download_pdf
import papers.storage as storage

from paperprocessor.models import ProcessedDocument, ProcessedPage
from paperprocessor.internals.mistral_ocr import extract_markdown_from_pages
from paperprocessor.internals.header_formatter import format_headers, format_images


# ============================================================================
# CONSTANTS
# ============================================================================

BATCH_SIZE = 10


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

@contextmanager
def database_session():
    """
    Create a database session with automatic commit/rollback handling.

    Yields:
        Session: SQLAlchemy session for database operations
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


async def extract_final_markdown_from_pdf(pdf_contents: bytes) -> str:
    """
    Extract final_markdown from PDF using the processing pipeline.

    Runs OCR, header formatting, and image reference formatting. Skips metadata
    extraction and summary generation.

    Args:
        pdf_contents: Raw PDF bytes

    Returns:
        str: The final_markdown field (original OCR content with formatted images)
    """
    pdf_base64 = base64.b64encode(pdf_contents).decode('utf-8')

    from paperprocessor.internals.pdf_to_image import convert_pdf_to_images
    images = await convert_pdf_to_images(pdf_contents, max_pages=999)

    pages = []
    for i, image in enumerate(images):
        page_num = i + 1
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        page = ProcessedPage(
            page_number=page_num,
            img_base64=img_base64,
            width=image.width,
            height=image.height
        )
        pages.append(page)

    document = ProcessedDocument(
        pdf_base64=pdf_base64,
        pages=pages
    )

    await extract_markdown_from_pages(document)
    await format_headers(document)
    await format_images(document)

    return document.final_markdown


# ============================================================================
# DAG DEFINITION
# ============================================================================

@dag(
    dag_id="backfill_final_markdown",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time"],
    doc_md="""
    ### Backfill Final Markdown DAG

    **ONE-TIME USE DAG**: Backfills content.md in Supabase Storage for papers
    that don't have it.

    **What it does:**
    1. Finds all completed papers missing content.md in storage
    2. Downloads the PDF from arXiv for each paper
    3. Runs the OCR + formatting pipeline
    4. Uploads content.md to storage

    **Cost Warning:**
    - This DAG calls Mistral OCR API for each paper
    - Monitor costs during execution
    """,
)
def backfill_final_markdown_dag():

    @task
    def find_papers_without_final_markdown() -> List[Dict[str, any]]:
        """
        Find all completed papers missing content.md in storage.

        Returns:
            List[Dict]: List of papers to process with metadata
        """
        print("Scanning for papers without final_markdown in storage...")

        papers_to_process = []

        with database_session() as session:
            paper_rows = session.query(
                PaperRecord.paper_uuid,
                PaperRecord.arxiv_id,
                PaperRecord.title,
                PaperRecord.num_pages
            ).filter(
                PaperRecord.status == 'completed',
            ).all()

            print(f"Found {len(paper_rows)} completed papers, checking storage...")

            for idx, (paper_uuid, arxiv_id, title, num_pages) in enumerate(paper_rows, 1):
                try:
                    markdown = storage.download_markdown(paper_uuid)
                    if markdown and markdown.strip():
                        continue
                except Exception:
                    # File missing in storage -- needs backfill
                    pass

                papers_to_process.append({
                    'paper_uuid': paper_uuid,
                    'arxiv_id': arxiv_id,
                    'title': title or 'Untitled',
                    'num_pages': num_pages
                })

                if idx % 50 == 0:
                    print(f"  [{idx}/{len(paper_rows)}] checked, {len(papers_to_process)} need backfill")

        print(f"\nTotal found: {len(papers_to_process)} papers that need final_markdown")
        return papers_to_process


    @task
    def process_papers_batch(papers_to_process: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Process papers in batches: download PDF, run pipeline, upload to storage.

        Args:
            papers_to_process: List of papers from find_papers_without_final_markdown

        Returns:
            List[Dict]: Processing results for each paper
        """
        if not papers_to_process:
            print("No papers to process")
            return []

        print(f"\nStarting processing of {len(papers_to_process)} papers...")

        all_results = []
        total_papers = len(papers_to_process)

        for batch_idx in range(0, total_papers, BATCH_SIZE):
            batch = papers_to_process[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = (batch_idx // BATCH_SIZE) + 1
            total_batches = (total_papers + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n--- Processing batch {batch_num}/{total_batches} ({len(batch)} papers) ---")

            for paper_info in batch:
                paper_uuid = paper_info['paper_uuid']
                arxiv_id = paper_info['arxiv_id']

                try:
                    # Download PDF from arXiv
                    print(f"  Downloading PDF from arXiv ({arxiv_id})...")
                    pdf_result = asyncio.run(download_pdf(arxiv_id))
                    pdf_bytes = pdf_result.pdf_bytes

                    # Run processing pipeline
                    print(f"  {paper_uuid}: Running OCR + formatting...")
                    final_markdown = asyncio.run(extract_final_markdown_from_pdf(pdf_bytes))
                    markdown_length = len(final_markdown)
                    print(f"  {paper_uuid}: Extracted {markdown_length} characters")

                    # Upload content.md to storage
                    bucket = storage._bucket()
                    bucket.upload(
                        f"{paper_uuid}/content.md",
                        final_markdown.encode("utf-8"),
                        {"content-type": "text/markdown", "upsert": "true"},
                    )
                    print(f"  {paper_uuid}: Uploaded to storage")

                    all_results.append({
                        'paper_uuid': paper_uuid,
                        'arxiv_id': arxiv_id,
                        'title': paper_info['title'],
                        'markdown_length': markdown_length,
                        'num_pages': paper_info.get('num_pages'),
                        'status': 'success'
                    })

                except Exception as e:
                    print(f"  {paper_uuid}: Error - {e}")
                    all_results.append({
                        'paper_uuid': paper_uuid,
                        'arxiv_id': arxiv_id,
                        'title': paper_info['title'],
                        'status': 'failed',
                        'error': str(e)
                    })
                    continue

        successful = len([r for r in all_results if r['status'] == 'success'])
        failed = len([r for r in all_results if r['status'] == 'failed'])
        print(f"\nSuccessfully processed {successful} papers ({failed} failed)")

        return all_results


    @task
    def generate_summary_report(processing_results: List[Dict[str, any]]) -> Dict[str, any]:
        """
        Generate a summary report of the backfill operation.

        Args:
            processing_results: List of processing results

        Returns:
            Dict: Summary statistics
        """
        if not processing_results:
            print("\nNo papers were processed")
            return {
                'total_processed': 0,
                'total_successful': 0,
                'total_failed': 0,
                'total_markdown_chars': 0,
                'avg_markdown_length': 0
            }

        total_processed = len(processing_results)
        successful = [r for r in processing_results if r['status'] == 'success']
        failed = [r for r in processing_results if r['status'] == 'failed']

        total_successful = len(successful)
        total_failed = len(failed)
        total_markdown_chars = sum(r.get('markdown_length', 0) for r in successful)
        avg_markdown_length = total_markdown_chars / total_successful if total_successful > 0 else 0

        print("\n" + "=" * 70)
        print("BACKFILL FINAL_MARKDOWN SUMMARY REPORT")
        print("=" * 70)
        print(f"Total papers processed:       {total_processed}")
        print(f"Successfully updated:         {total_successful}")
        print(f"Failed:                       {total_failed}")
        print(f"Total markdown extracted:     {total_markdown_chars:,} characters")
        print(f"Average markdown length:      {avg_markdown_length:,.0f} characters")

        if failed:
            print("\n--- Failed Papers ---")
            for result in failed[:10]:
                print(f"  {result['arxiv_id']}: {result.get('error', 'Unknown error')}")
            if len(failed) > 10:
                print(f"  ... and {len(failed) - 10} more failures")

        print("=" * 70)

        return {
            'total_processed': total_processed,
            'total_successful': total_successful,
            'total_failed': total_failed,
            'total_markdown_chars': total_markdown_chars,
            'avg_markdown_length': round(avg_markdown_length, 0)
        }


    papers = find_papers_without_final_markdown()
    results = process_papers_batch(papers)
    summary = generate_summary_report(results)


backfill_final_markdown_dag()
