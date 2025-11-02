"""
DAG to clean up page images from existing papers in the database.

This DAG removes page image_data_url from the pages array in processed_content
and normalizes bounding box coordinates to 0-1 range for all existing papers.

Storage savings: ~300-400KB per paper by removing page images.
"""

import sys
import pendulum
import json
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Any, Tuple

from airflow.decorators import dag, task
from sqlalchemy.orm import Session, undefer

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


def get_papers_batch(session: Session, offset: int, limit: int) -> List[PaperRecord]:
    """
    Fetch a batch of completed papers with processed_content loaded.

    Args:
        session: Database session
        offset: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List[PaperRecord]: Batch of paper records with processed_content
    """
    return (
        session.query(PaperRecord)
        .filter(PaperRecord.status == 'completed')
        .filter(PaperRecord.processed_content.isnot(None))
        .options(undefer(PaperRecord.processed_content))
        .order_by(PaperRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def normalize_bounding_box(bbox: List[int], page_width: int, page_height: int) -> List[float]:
    """
    Normalize bounding box coordinates to 0-1 range.

    Args:
        bbox: [x1, y1, x2, y2] in pixel coordinates
        page_width: Page width in pixels
        page_height: Page height in pixels

    Returns:
        List[float]: Normalized coordinates [x1, y1, x2, y2] in 0-1 range
    """
    if len(bbox) != 4:
        return bbox

    return [
        bbox[0] / page_width,
        bbox[1] / page_height,
        bbox[2] / page_width,
        bbox[3] / page_height
    ]


def cleanup_paper_images(paper_json: Dict[str, Any]) -> Tuple[Dict[str, Any], int, int]:
    """
    Remove page images and normalize bounding boxes in paper JSON.

    Args:
        paper_json: Parsed processed_content JSON

    Returns:
        tuple: (modified_json, bytes_saved, pages_cleaned)
    """
    bytes_saved = 0
    pages_cleaned = 0

    # Get page dimensions before removing images
    page_dimensions = {}
    for page in paper_json.get('pages', []):
        page_num = page.get('page_number')
        if page_num:
            # Estimate page dimensions from image or use defaults
            # Most PDFs are ~1080px wide when rendered
            page_dimensions[page_num] = {
                'width': 1080,
                'height': 1400
            }

    # Clean up pages array - remove image_data_url
    for page in paper_json.get('pages', []):
        if 'image_data_url' in page:
            # Calculate bytes saved (base64 encoded data)
            image_data = page['image_data_url']
            if isinstance(image_data, str):
                bytes_saved += len(image_data)

            # Remove the image data
            page['image_data_url'] = None
            pages_cleaned += 1

    # Normalize bounding boxes in figures
    for figure in paper_json.get('figures', []):
        if 'bounding_box' in figure and 'page_image_size' in figure:
            page_size = figure['page_image_size']
            if len(page_size) == 2:
                page_width, page_height = page_size
                old_bbox = figure['bounding_box']

                # Normalize the bounding box
                figure['bounding_box'] = normalize_bounding_box(
                    old_bbox, page_width, page_height
                )

                # Remove page_image_size as it's no longer needed
                del figure['page_image_size']

        # Remove obsolete fields
        if 'image_path' in figure:
            del figure['image_path']

    # Normalize bounding boxes in tables
    for table in paper_json.get('tables', []):
        if 'bounding_box' in table and 'page_image_size' in table:
            page_size = table['page_image_size']
            if len(page_size) == 2:
                page_width, page_height = page_size
                old_bbox = table['bounding_box']

                # Normalize the bounding box
                table['bounding_box'] = normalize_bounding_box(
                    old_bbox, page_width, page_height
                )

                # Remove page_image_size as it's no longer needed
                del table['page_image_size']

        # Remove obsolete fields
        if 'image_path' in table:
            del table['image_path']

    return paper_json, bytes_saved, pages_cleaned


### AIRFLOW TASKS ###

@task
def process_all_papers() -> Dict[str, Any]:
    """
    Process all papers sequentially to remove page images and normalize bboxes.

    MEMORY OPTIMIZATION: Process papers one at a time and commit immediately
    to avoid loading multiple 100MB+ papers into memory at once.

    Returns:
        Dict containing overall statistics
    """
    # First, count total papers
    with database_session() as session:
        total_count = (
            session.query(PaperRecord)
            .filter(PaperRecord.status == 'completed')
            .filter(PaperRecord.processed_content.isnot(None))
            .count()
        )

    print(f"📊 Total papers to clean: {total_count}")

    total_bytes_saved = 0
    total_pages_cleaned = 0
    papers_processed = 0

    # Process one paper at a time sequentially
    for paper_offset in range(total_count):
        session = SessionLocal()
        try:
            # Load ONE paper at a time
            paper = (
                session.query(PaperRecord)
                .filter(PaperRecord.status == 'completed')
                .filter(PaperRecord.processed_content.isnot(None))
                .options(undefer(PaperRecord.processed_content))
                .order_by(PaperRecord.created_at.desc())
                .offset(paper_offset)
                .limit(1)
                .first()
            )

            if not paper:
                break  # No more papers

            # Parse the processed_content JSON
            paper_json = json.loads(paper.processed_content)

            # Clean up images and normalize bboxes
            modified_json, bytes_saved, pages_cleaned = cleanup_paper_images(paper_json)

            # Save back to database
            paper.processed_content = json.dumps(modified_json, ensure_ascii=False)

            # Commit immediately and close session to free memory
            session.commit()

            total_bytes_saved += bytes_saved
            total_pages_cleaned += pages_cleaned
            papers_processed += 1

            print(f"  📄 [{papers_processed}/{total_count}] Processed paper {paper.paper_uuid}: saved {bytes_saved / 1024:.1f} KB")

        except Exception as e:
            session.rollback()
            print(f"❌ Error processing paper at offset {paper_offset}: {e}")
        finally:
            session.close()
            # Explicitly free memory
            del session
            if 'paper' in locals():
                del paper
            if 'paper_json' in locals():
                del paper_json
            if 'modified_json' in locals():
                del modified_json

    result = {
        'papers_processed': papers_processed,
        'bytes_saved': total_bytes_saved,
        'pages_cleaned': total_pages_cleaned
    }

    print(f"\n✅ Processing complete: {papers_processed} papers, "
          f"saved {total_bytes_saved / 1024 / 1024:.2f} MB, "
          f"cleaned {total_pages_cleaned} pages")

    return result


@task
def summarize_results(results: Dict[str, Any]) -> None:
    """
    Print summary of processing results.

    Args:
        results: Processing result dictionary
    """
    total_papers = results['papers_processed']
    total_bytes = results['bytes_saved']
    total_pages = results['pages_cleaned']

    print("\n" + "="*60)
    print("🎉 PAGE IMAGE CLEANUP COMPLETE")
    print("="*60)
    print(f"📄 Total papers processed: {total_papers}")
    print(f"🗑️  Total pages cleaned: {total_pages}")
    print(f"💾 Total storage saved: {total_bytes / 1024 / 1024:.2f} MB")
    print(f"📦 Average per paper: {(total_bytes / total_papers / 1024) if total_papers > 0 else 0:.2f} KB")
    print("="*60 + "\n")


### DAG DEFINITION ###

@dag(
    dag_id='cleanup_page_images',
    start_date=pendulum.datetime(2025, 1, 1, tz='UTC'),
    schedule=None,  # Manual trigger only
    catchup=False,
    tags=['maintenance', 'cleanup', 'storage'],
    description='Remove page images and normalize bounding boxes for existing papers',
)
def cleanup_page_images_workflow():
    """
    Main workflow to clean up page images from all existing papers.

    Steps:
    1. Process all papers sequentially (remove images, normalize bboxes)
    2. Summarize results
    """

    # Process all papers sequentially
    results = process_all_papers()

    # Summarize
    summarize_results(results)


# Instantiate the DAG
cleanup_page_images_dag = cleanup_page_images_workflow()
