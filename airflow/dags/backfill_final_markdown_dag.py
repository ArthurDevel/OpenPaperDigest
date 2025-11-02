import sys
import pendulum
import json
import base64
import io
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict
import asyncio

from airflow.decorators import dag, task
from sqlalchemy.orm import Session, defer

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord
from shared.arxiv.client import download_pdf

# Import the processing pipeline components
from paperprocessor.models import ProcessedDocument, ProcessedPage
from paperprocessor.internals.mistral_ocr import extract_markdown_from_pages
from paperprocessor.internals.header_formatter import format_headers, format_images


### CONSTANTS ###

BATCH_SIZE = 10  # Process 10 papers per batch to manage memory and API rate limits


### DATABASE HELPERS ###

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


### PROCESSING FUNCTIONS (simplified from process_paper_pdf) ###

async def extract_final_markdown_from_pdf(pdf_contents: bytes) -> str:
    """
    Extract final_markdown from PDF using the same pipeline as normal processing.

    This is a simplified version of process_paper_pdf that only does what we need:
    1. OCR → markdown per page
    2. Format headers (combine pages)
    3. Format image references

    Skips: metadata extraction, summary generation (we don't need those)

    Args:
        pdf_contents: Raw PDF bytes

    Returns:
        str: The final_markdown field (original OCR content with formatted images)
    """
    # Create ProcessedDocument DTO with PDF base64
    pdf_base64 = base64.b64encode(pdf_contents).decode('utf-8')

    # We need to create pages with base64 images for the image extraction to work
    # This is required by extract_markdown_from_pages
    from paperprocessor.internals.pdf_to_image import convert_pdf_to_images
    images = await convert_pdf_to_images(pdf_contents)

    pages = []
    for i, image in enumerate(images):
        page_num = i + 1

        # Convert PIL Image to base64
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

    # Step 1: OCR pages to markdown - populates ocr_markdown on each page
    await extract_markdown_from_pages(document)

    # Step 2: Format headers and combine pages into final_markdown
    # This concatenates all page OCR markdown with '\n\n'.join()
    await format_headers(document)

    # Step 3: Format inline image references
    # This replaces ![img-X.jpeg] with ![Figure shortid](shortid:xyz)
    await format_images(document)

    # Return the final_markdown (skipping metadata and summary generation)
    return document.final_markdown


### DAG DEFINITION ###

@dag(
    dag_id="backfill_final_markdown",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,  # Manual trigger only (one-time use)
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time"],
    doc_md="""
    ### Backfill Final Markdown DAG

    **ONE-TIME USE DAG**: Backfills the `final_markdown` field for papers that don't have it.

    This DAG was created to populate the `final_markdown` field (original OCR markdown)
    for papers that were processed before this field was added to the database schema.

    **What it does:**
    1. Finds all completed papers that don't have `final_markdown` in their JSON
    2. Downloads the PDF from arXiv for each paper
    3. Runs the same processing pipeline as normal (OCR + header formatting + image formatting)
    4. Extracts only the `final_markdown` field from the result
    5. Updates the database JSON with the new field
    6. Generates a summary report

    **Configuration (hardcoded constants):**
    - Batch size: 10 papers per batch

    **Safety:**
    - Only processes completed papers
    - Only processes papers without existing final_markdown
    - Batch commits for atomicity
    - Auto-rollback on errors
    - Can be re-run safely (skips papers that already have final_markdown)

    **Important:**
    - This is a one-time backfill operation
    - After all existing papers are processed, this DAG can be archived
    - New papers will have final_markdown populated automatically during processing

    **Cost Warning:**
    - This DAG calls Mistral OCR API for each paper
    - Costs will depend on the number of papers and pages
    - Monitor costs during execution
    """,
)
def backfill_final_markdown_dag():

    @task
    def find_papers_without_final_markdown() -> List[Dict[str, any]]:
        """
        Find all completed papers that don't have final_markdown in their JSON.

        Returns:
            List[Dict]: List of papers to process with metadata:
                - paper_uuid: UUID of the paper
                - arxiv_id: arXiv ID for downloading PDF
                - title: Paper title for logging
                - num_pages: Number of pages (if available)
        """
        print("Scanning for papers without final_markdown...")

        papers_to_process = []

        with database_session() as session:
            # Query all completed papers
            papers = session.query(PaperRecord).filter(
                PaperRecord.status == 'completed',
                PaperRecord.processed_content.isnot(None)
            ).all()

            print(f"Found {len(papers)} completed papers with processed content")

            # Check each paper's JSON for final_markdown field
            for paper in papers:
                try:
                    paper_json = json.loads(paper.processed_content)

                    # Check if final_markdown exists and is not None/empty
                    if not paper_json.get('final_markdown'):
                        papers_to_process.append({
                            'paper_uuid': paper.paper_uuid,
                            'arxiv_id': paper.arxiv_id,
                            'title': paper.title or 'Untitled',
                            'num_pages': paper.num_pages
                        })

                except Exception as e:
                    print(f"Error checking paper {paper.paper_uuid}: {e}")
                    continue

        print(f"Found {len(papers_to_process)} papers that need final_markdown")

        if papers_to_process:
            # Print sample of papers to process
            sample_size = min(5, len(papers_to_process))
            print(f"\nSample of papers to process (showing {sample_size}):")
            for paper in papers_to_process[:sample_size]:
                print(f"  - {paper['paper_uuid']}: {paper['arxiv_id']} - {paper['title'][:60]}...")

        return papers_to_process


    @task
    def process_papers_batch(papers_to_process: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Process papers in batches: download PDF, run processing pipeline, update database.

        Args:
            papers_to_process: List of papers from find_papers_without_final_markdown

        Returns:
            List[Dict]: Processing results for each paper
        """
        if not papers_to_process:
            print("No papers to process")
            return []

        print(f"\nStarting processing of {len(papers_to_process)} papers...")
        print(f"Configuration: Batch size={BATCH_SIZE}")

        all_results = []
        total_papers = len(papers_to_process)

        # Process in batches
        for batch_idx in range(0, total_papers, BATCH_SIZE):
            batch = papers_to_process[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = (batch_idx // BATCH_SIZE) + 1
            total_batches = (total_papers + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n--- Processing batch {batch_num}/{total_batches} ({len(batch)} papers) ---")

            with database_session() as session:
                for paper_info in batch:
                    paper_uuid = paper_info['paper_uuid']
                    arxiv_id = paper_info['arxiv_id']

                    try:
                        # Step 1: Load paper record
                        paper = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()

                        if not paper or not paper.processed_content:
                            print(f"  ⚠️  {paper_uuid}: Paper or processed content not found, skipping")
                            continue

                        # Step 2: Download PDF from arXiv
                        print(f"  Downloading PDF from arXiv ({arxiv_id})...")
                        pdf_result = asyncio.run(download_pdf(arxiv_id))
                        pdf_bytes = pdf_result.pdf_bytes

                        # Step 3: Run processing pipeline to extract final_markdown
                        print(f"  🔍 {paper_uuid}: Running processing pipeline (OCR + formatting)...")
                        final_markdown = asyncio.run(extract_final_markdown_from_pdf(pdf_bytes))

                        markdown_length = len(final_markdown)
                        print(f"  ✓ {paper_uuid}: Extracted {markdown_length} characters of markdown")

                        # Step 4: Update processed_content JSON
                        paper_json = json.loads(paper.processed_content)
                        paper_json['final_markdown'] = final_markdown

                        # Save back to database
                        paper.processed_content = json.dumps(paper_json, ensure_ascii=False)

                        # Log success
                        print(f"  💾 {paper_uuid}: Updated database with final_markdown")

                        # Save result
                        result = {
                            'paper_uuid': paper_uuid,
                            'arxiv_id': arxiv_id,
                            'title': paper_info['title'],
                            'markdown_length': markdown_length,
                            'num_pages': paper_info.get('num_pages'),
                            'status': 'success'
                        }
                        all_results.append(result)

                    except Exception as e:
                        print(f"  ✗ {paper_uuid}: Error - {e}")
                        result = {
                            'paper_uuid': paper_uuid,
                            'arxiv_id': arxiv_id,
                            'title': paper_info['title'],
                            'status': 'failed',
                            'error': str(e)
                        }
                        all_results.append(result)
                        continue

                # Commit batch
                print(f"  💾 Committing batch {batch_num}...")

        successful = len([r for r in all_results if r['status'] == 'success'])
        failed = len([r for r in all_results if r['status'] == 'failed'])
        print(f"\n✓ Successfully processed {successful} papers ({failed} failed)")

        return all_results


    @task
    def generate_summary_report(processing_results: List[Dict[str, any]]) -> Dict[str, any]:
        """
        Generate a summary report of the backfill operation.

        Args:
            processing_results: List of processing results from process_papers_batch

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

        # Calculate aggregate statistics
        total_processed = len(processing_results)
        successful = [r for r in processing_results if r['status'] == 'success']
        failed = [r for r in processing_results if r['status'] == 'failed']

        total_successful = len(successful)
        total_failed = len(failed)

        total_markdown_chars = sum(r.get('markdown_length', 0) for r in successful)
        avg_markdown_length = total_markdown_chars / total_successful if total_successful > 0 else 0

        # Print summary report
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
            for result in failed[:10]:  # Show first 10 failures
                print(f"  ✗ {result['arxiv_id']}: {result.get('error', 'Unknown error')}")
            if len(failed) > 10:
                print(f"  ... and {len(failed) - 10} more failures")

        print("=" * 70)

        summary = {
            'total_processed': total_processed,
            'total_successful': total_successful,
            'total_failed': total_failed,
            'total_markdown_chars': total_markdown_chars,
            'avg_markdown_length': round(avg_markdown_length, 0)
        }

        return summary


    # Define task dependencies
    papers = find_papers_without_final_markdown()
    results = process_papers_batch(papers)
    summary = generate_summary_report(results)


# Instantiate the DAG
backfill_final_markdown_dag()
