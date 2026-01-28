import sys
import pendulum
import json
from contextlib import contextmanager
from typing import List, Dict

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

# Add project root to Python path
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord


### DATABASE HELPERS ###

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


### DAG DEFINITION ###

@dag(
    dag_id="regenerate_missing_thumbnails",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "one-time-fix"],
    doc_md="""
    ### Regenerate Missing Thumbnails DAG

    One-time fix to regenerate thumbnails for papers that are missing thumbnail_data_url.

    **What it does:**
    1. Finds all completed papers missing thumbnail_data_url
    2. Extracts thumbnail from processed_content first page image
    3. Updates database with thumbnail data

    **Note:** This reads from processed_content which contains the first page image.
    """,
)
def regenerate_missing_thumbnails_dag():

    @task
    def find_papers_missing_thumbnails() -> List[str]:
        """
        Find all completed papers missing thumbnails.

        Returns:
            List[str]: List of paper UUIDs
        """
        print("Scanning for papers missing thumbnails...")

        paper_uuids = []

        with database_session() as session:
            papers = session.query(PaperRecord).filter(
                PaperRecord.status == 'completed',
                PaperRecord.processed_content.isnot(None),
                (PaperRecord.thumbnail_data_url.is_(None) | (PaperRecord.thumbnail_data_url == ''))
            ).all()

            paper_uuids = [p.paper_uuid for p in papers]

            print(f"Found {len(paper_uuids)} papers missing thumbnails")

        return paper_uuids


    @task
    def regenerate_thumbnails(paper_uuids: List[str]) -> Dict[str, int]:
        """
        Regenerate thumbnails from PDF files.

        Downloads PDFs from arXiv, converts first page to image, creates thumbnail.

        Args:
            paper_uuids: List of paper UUIDs to process

        Returns:
            Dict with success/failure counts
        """
        import requests
        import io
        import base64
        from PIL import Image
        from pdf2image import convert_from_bytes

        if not paper_uuids:
            print("No papers to process")
            return {'success': 0, 'failed': 0}

        print(f"\nRegenerating thumbnails for {len(paper_uuids)} papers...")

        success_count = 0
        failed_count = 0

        with database_session() as session:
            for i, paper_uuid in enumerate(paper_uuids, 1):
                try:
                    print(f"[{i}/{len(paper_uuids)}] Processing {paper_uuid}...")

                    paper = session.query(PaperRecord).filter(
                        PaperRecord.paper_uuid == paper_uuid
                    ).first()

                    if not paper:
                        print(f"  Paper not found, skipping")
                        failed_count += 1
                        continue

                    if not paper.arxiv_url:
                        print(f"  No arXiv URL, skipping")
                        failed_count += 1
                        continue

                    # Download PDF from arXiv
                    pdf_url = paper.arxiv_url.replace('/abs/', '/pdf/') + '.pdf'
                    response = requests.get(pdf_url, timeout=30)
                    response.raise_for_status()

                    # Convert first page to image
                    images = convert_from_bytes(response.content, first_page=1, last_page=1, dpi=150)
                    first_page_img = images[0]

                    # Crop to square from top
                    width, height = first_page_img.size
                    size = min(width, height)
                    cropped = first_page_img.crop((0, 0, size, size))

                    # Resize to 400x400
                    thumbnail = cropped.resize((400, 400), Image.Resampling.LANCZOS)

                    # Convert to PNG base64 data URL
                    buffer = io.BytesIO()
                    thumbnail.save(buffer, format='PNG')
                    buffer.seek(0)
                    encoded = base64.b64encode(buffer.read()).decode('utf-8')
                    thumbnail_data_url = f'data:image/png;base64,{encoded}'

                    # Update database
                    paper.thumbnail_data_url = thumbnail_data_url

                    success_count += 1
                    print(f"  Success")

                except Exception as e:
                    failed_count += 1
                    print(f"  Failed: {e}")
                    continue

        print(f"\nCompleted: {success_count} success, {failed_count} failed")

        return {
            'success': success_count,
            'failed': failed_count
        }


    # Define task dependencies
    paper_uuids = find_papers_missing_thumbnails()
    results = regenerate_thumbnails(paper_uuids)


# Instantiate the DAG
regenerate_missing_thumbnails_dag()
