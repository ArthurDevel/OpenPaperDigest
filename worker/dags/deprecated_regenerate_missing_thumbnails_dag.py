"""
Regenerate missing thumbnails and upload to Supabase Storage.

Finds completed papers that are missing thumbnail.png in storage, downloads
their PDF from arXiv, generates a thumbnail, and uploads to storage.

Responsibilities:
- Find completed papers missing thumbnails in storage
- Download PDF and generate thumbnail from first page
- Upload thumbnail.png to Supabase Storage
"""

import sys
import pendulum
from contextlib import contextmanager
from typing import List, Dict

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord
import papers.storage as storage


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


# ============================================================================
# DAG DEFINITION
# ============================================================================

@dag(
    dag_id="regenerate_missing_thumbnails",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "one-time-fix"],
    doc_md="""
    ### Regenerate Missing Thumbnails DAG

    One-time fix to regenerate thumbnails for papers missing them in Supabase Storage.

    **What it does:**
    1. Finds all completed papers missing thumbnail.png in storage
    2. Downloads PDF from arXiv
    3. Generates a 400x400 thumbnail from the first page
    4. Uploads thumbnail.png to storage
    """,
)
def regenerate_missing_thumbnails_dag():

    @task
    def find_papers_missing_thumbnails() -> List[Dict[str, str]]:
        """
        Find all completed papers missing thumbnails in storage.

        Returns:
            List[Dict]: List of dicts with paper_uuid and arxiv_url
        """
        print("Scanning for papers missing thumbnails in storage...")

        papers_to_fix = []
        bucket = storage._bucket()

        with database_session() as session:
            papers = session.query(
                PaperRecord.paper_uuid,
                PaperRecord.arxiv_url
            ).filter(
                PaperRecord.status == 'completed',
            ).all()

            print(f"Found {len(papers)} completed papers, checking storage...")

            for paper_uuid, arxiv_url in papers:
                try:
                    # Check if thumbnail exists by attempting to download
                    bucket.download(f"{paper_uuid}/thumbnail.png")
                except Exception:
                    # Thumbnail missing in storage
                    if arxiv_url:
                        papers_to_fix.append({
                            'paper_uuid': paper_uuid,
                            'arxiv_url': arxiv_url,
                        })

        print(f"Found {len(papers_to_fix)} papers missing thumbnails")
        return papers_to_fix


    @task
    def regenerate_thumbnails(papers_to_fix: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Regenerate thumbnails from PDF files and upload to storage.

        Args:
            papers_to_fix: List of dicts with paper_uuid and arxiv_url

        Returns:
            Dict with success/failure counts
        """
        import requests
        import io
        from PIL import Image
        from pdf2image import convert_from_bytes

        if not papers_to_fix:
            print("No papers to process")
            return {'success': 0, 'failed': 0}

        print(f"\nRegenerating thumbnails for {len(papers_to_fix)} papers...")

        success_count = 0
        failed_count = 0
        bucket = storage._bucket()

        for i, paper_info in enumerate(papers_to_fix, 1):
            paper_uuid = paper_info['paper_uuid']
            arxiv_url = paper_info['arxiv_url']

            try:
                print(f"[{i}/{len(papers_to_fix)}] Processing {paper_uuid}...")

                # Download PDF from arXiv
                pdf_url = arxiv_url.replace('/abs/', '/pdf/') + '.pdf'
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

                # Convert to PNG bytes
                buffer = io.BytesIO()
                thumbnail.save(buffer, format='PNG')
                thumbnail_bytes = buffer.getvalue()

                # Upload to storage
                bucket.upload(
                    f"{paper_uuid}/thumbnail.png",
                    thumbnail_bytes,
                    {"content-type": "image/png", "upsert": "true"},
                )

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


    paper_list = find_papers_missing_thumbnails()
    results = regenerate_thumbnails(paper_list)


regenerate_missing_thumbnails_dag()
