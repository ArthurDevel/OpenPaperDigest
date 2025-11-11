import sys
import pendulum
import json
from datetime import datetime
from contextmanager import contextmanager
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
        Regenerate thumbnails from processed_content.

        Args:
            paper_uuids: List of paper UUIDs to process

        Returns:
            Dict with success/failure counts
        """
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

                    if not paper.processed_content:
                        print(f"  No processed_content, skipping")
                        failed_count += 1
                        continue

                    # Parse processed_content JSON
                    processed = json.loads(paper.processed_content)

                    # Extract first page image
                    if not processed.get('pages') or len(processed['pages']) == 0:
                        print(f"  No pages in processed_content, skipping")
                        failed_count += 1
                        continue

                    first_page = processed['pages'][0]
                    if not first_page.get('img_base64'):
                        print(f"  No image in first page, skipping")
                        failed_count += 1
                        continue

                    # Set thumbnail from first page
                    thumbnail_data_url = f"data:image/png;base64,{first_page['img_base64']}"
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
