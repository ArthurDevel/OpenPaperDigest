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


### CONSTANTS ###

BATCH_SIZE = 10  # Process 10 papers per batch


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
def get_batch_numbers() -> List[int]:
    """
    Get list of batch numbers to process based on total papers count.

    Returns:
        List[int]: List of batch numbers (0-indexed)
    """
    with database_session() as session:
        count = (
            session.query(PaperRecord)
            .filter(PaperRecord.status == 'completed')
            .filter(PaperRecord.processed_content.isnot(None))
            .count()
        )

    num_batches = (count // BATCH_SIZE) + (1 if count % BATCH_SIZE > 0 else 0)
    batch_numbers = list(range(num_batches))

    print(f"📊 Total papers to clean: {count}")
    print(f"📦 Number of batches: {num_batches}")

    return batch_numbers


@task
def process_batch(batch_num: int) -> Dict[str, Any]:
    """
    Process a single batch of papers to remove page images and normalize bboxes.

    Args:
        batch_num: Batch number (0-indexed)

    Returns:
        Dict containing batch statistics
    """
    offset = batch_num * BATCH_SIZE

    with database_session() as session:
        papers = get_papers_batch(session, offset, BATCH_SIZE)

        if not papers:
            print(f"✅ Batch {batch_num}: No papers found")
            return {
                'batch_num': batch_num,
                'papers_processed': 0,
                'bytes_saved': 0,
                'pages_cleaned': 0
            }

        total_bytes_saved = 0
        total_pages_cleaned = 0
        papers_processed = 0

        for paper in papers:
            try:
                # Parse the processed_content JSON
                paper_json = json.loads(paper.processed_content)

                # Clean up images and normalize bboxes
                modified_json, bytes_saved, pages_cleaned = cleanup_paper_images(paper_json)

                # Save back to database
                paper.processed_content = json.dumps(modified_json, ensure_ascii=False)

                total_bytes_saved += bytes_saved
                total_pages_cleaned += pages_cleaned
                papers_processed += 1

            except Exception as e:
                print(f"❌ Error processing paper {paper.paper_uuid}: {e}")
                continue

        session.commit()

        result = {
            'batch_num': batch_num,
            'papers_processed': papers_processed,
            'bytes_saved': total_bytes_saved,
            'pages_cleaned': total_pages_cleaned
        }

        print(f"✅ Batch {batch_num}: Processed {papers_processed} papers, "
              f"saved {total_bytes_saved / 1024 / 1024:.2f} MB, "
              f"cleaned {total_pages_cleaned} pages")

        return result


@task
def summarize_results(batch_results: List[Dict[str, Any]]) -> None:
    """
    Print summary of all batch processing results.

    Args:
        batch_results: List of batch result dictionaries
    """
    total_papers = sum(r['papers_processed'] for r in batch_results)
    total_bytes = sum(r['bytes_saved'] for r in batch_results)
    total_pages = sum(r['pages_cleaned'] for r in batch_results)

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
    1. Get list of batch numbers to process
    2. Process papers in batches (remove images, normalize bboxes)
    3. Summarize results
    """

    # Get batch numbers
    batch_numbers = get_batch_numbers()

    # Process all batches using task mapping
    batch_results = process_batch.expand(batch_num=batch_numbers)

    # Summarize
    summarize_results(batch_results)


# Instantiate the DAG
cleanup_page_images_dag = cleanup_page_images_workflow()
