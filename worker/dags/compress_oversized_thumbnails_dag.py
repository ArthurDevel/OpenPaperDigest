"""
Compress oversized thumbnail images in Supabase Storage.

Downloads thumbnails from storage, compresses oversized ones to JPEG, and
re-uploads the compressed versions.

Responsibilities:
- Iterate through completed papers
- Download thumbnail from storage, check size
- Compress oversized thumbnails to JPEG
- Re-upload compressed thumbnails
- Generate compression report
"""

import sys
import io
import pendulum
from contextlib import contextmanager
from typing import List, Dict, Tuple

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord
import papers.storage as storage

try:
    from PIL import Image
except ImportError:
    raise ImportError(
        "Pillow is required for thumbnail compression. "
        "Install with: pip install Pillow"
    )


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_SIZE_KB = 200          # Only compress thumbnails larger than 200 KB
TARGET_WIDTH = 800         # Resize to 800px width (maintains aspect ratio)
JPEG_QUALITY = 85          # Compression quality
BATCH_SIZE = 50            # Process 50 papers per batch


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


def compress_thumbnail(image_bytes: bytes) -> Tuple[bytes, Dict[str, any]]:
    """
    Compress and resize a thumbnail image to JPEG.

    Args:
        image_bytes: Original image bytes

    Returns:
        tuple: (compressed_bytes, stats_dict)
    """
    original_image = Image.open(io.BytesIO(image_bytes))
    original_width, original_height = original_image.size
    original_size_kb = len(image_bytes) / 1024

    if original_width > TARGET_WIDTH:
        aspect_ratio = original_height / original_width
        new_width = TARGET_WIDTH
        new_height = int(TARGET_WIDTH * aspect_ratio)
        resized_image = original_image.resize((new_width, new_height), Image.LANCZOS)
    else:
        new_width, new_height = original_width, original_height
        resized_image = original_image

    # Convert to RGB (JPEG doesn't support transparency)
    if resized_image.mode in ('RGBA', 'LA', 'P'):
        rgb_image = Image.new('RGB', resized_image.size, (255, 255, 255))
        if resized_image.mode == 'P':
            resized_image = resized_image.convert('RGBA')
        rgb_image.paste(resized_image, mask=resized_image.split()[-1] if resized_image.mode in ('RGBA', 'LA') else None)
        resized_image = rgb_image
    elif resized_image.mode != 'RGB':
        resized_image = resized_image.convert('RGB')

    output_buffer = io.BytesIO()
    resized_image.save(output_buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    compressed_bytes = output_buffer.getvalue()
    new_size_kb = len(compressed_bytes) / 1024

    reduction_percent = ((original_size_kb - new_size_kb) / original_size_kb) * 100

    stats = {
        'original_width': original_width,
        'original_height': original_height,
        'new_width': new_width,
        'new_height': new_height,
        'original_size_kb': round(original_size_kb, 2),
        'new_size_kb': round(new_size_kb, 2),
        'reduction_percent': round(reduction_percent, 2)
    }

    return compressed_bytes, stats


# ============================================================================
# DAG DEFINITION
# ============================================================================

@dag(
    dag_id="compress_oversized_thumbnails",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 0 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "optimization"],
    doc_md="""
    ### Compress Oversized Thumbnails DAG

    Finds and compresses large thumbnail images in Supabase Storage.

    **Schedule:** Daily at midnight UTC

    **Configuration:**
    - Max thumbnail size threshold: 200 KB
    - Target width: 800px (maintains aspect ratio)
    - JPEG quality: 85%
    - Batch size: 50 papers per batch

    **What it does:**
    1. Scans all completed papers
    2. Downloads thumbnail.png from storage, checks size
    3. Compresses oversized thumbnails to JPEG
    4. Re-uploads compressed version to storage
    5. Generates a summary report
    """,
)
def compress_oversized_thumbnails_dag():

    @task
    def find_oversized_thumbnails() -> List[Dict[str, any]]:
        """
        Find all papers with thumbnails larger than MAX_SIZE_KB in storage.

        Returns:
            List[Dict]: List of papers to compress with metadata
        """
        print(f"Scanning for thumbnails larger than {MAX_SIZE_KB} KB...")

        oversized_papers = []
        bucket = storage._bucket()

        with database_session() as session:
            paper_uuids = [
                row[0] for row in
                session.query(PaperRecord.paper_uuid).filter(
                    PaperRecord.status == 'completed',
                ).all()
            ]

        print(f"Found {len(paper_uuids)} completed papers, checking thumbnails...")

        for paper_uuid in paper_uuids:
            try:
                image_bytes = bucket.download(f"{paper_uuid}/thumbnail.png")
                size_kb = len(image_bytes) / 1024

                if size_kb > MAX_SIZE_KB:
                    oversized_papers.append({
                        'paper_uuid': paper_uuid,
                        'current_size_kb': round(size_kb, 2)
                    })

            except Exception:
                # Thumbnail not found in storage -- skip
                continue

        print(f"Found {len(oversized_papers)} thumbnails that need compression")

        if oversized_papers:
            sample_size = min(5, len(oversized_papers))
            print(f"\nSample of papers to compress (showing {sample_size}):")
            for paper in oversized_papers[:sample_size]:
                print(f"  - {paper['paper_uuid']}: {paper['current_size_kb']} KB")

        return oversized_papers


    @task
    def compress_thumbnails_batch(oversized_papers: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Compress thumbnails: download from storage, compress, re-upload.

        Args:
            oversized_papers: List of papers to compress

        Returns:
            List[Dict]: Compression statistics for each paper
        """
        if not oversized_papers:
            print("No thumbnails to compress")
            return []

        print(f"\nStarting compression of {len(oversized_papers)} thumbnails...")

        all_results = []
        total_papers = len(oversized_papers)
        bucket = storage._bucket()

        for batch_idx in range(0, total_papers, BATCH_SIZE):
            batch = oversized_papers[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = (batch_idx // BATCH_SIZE) + 1
            total_batches = (total_papers + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n--- Processing batch {batch_num}/{total_batches} ({len(batch)} papers) ---")

            for paper_info in batch:
                paper_uuid = paper_info['paper_uuid']

                try:
                    # Download thumbnail from storage
                    image_bytes = bucket.download(f"{paper_uuid}/thumbnail.png")

                    # Compress
                    compressed_bytes, stats = compress_thumbnail(image_bytes)

                    # Re-upload compressed version
                    bucket.upload(
                        f"{paper_uuid}/thumbnail.png",
                        compressed_bytes,
                        {"content-type": "image/jpeg", "upsert": "true"},
                    )

                    print(f"  {paper_uuid}: {stats['original_size_kb']}KB -> {stats['new_size_kb']}KB "
                          f"({stats['reduction_percent']}% reduction)")

                    result = {'paper_uuid': paper_uuid, **stats}
                    all_results.append(result)

                except Exception as e:
                    print(f"  {paper_uuid}: Error - {e}")
                    continue

        print(f"\nSuccessfully compressed {len(all_results)} thumbnails")
        return all_results


    @task
    def generate_summary_report(compression_results: List[Dict[str, any]]) -> Dict[str, any]:
        """
        Generate a summary report of compression results.

        Args:
            compression_results: List of compression statistics

        Returns:
            Dict: Summary statistics
        """
        if not compression_results:
            print("\nNo thumbnails were compressed")
            return {
                'total_processed': 0,
                'total_original_mb': 0,
                'total_compressed_mb': 0,
                'total_saved_mb': 0,
                'avg_reduction_percent': 0
            }

        total_processed = len(compression_results)
        total_original_kb = sum(r['original_size_kb'] for r in compression_results)
        total_compressed_kb = sum(r['new_size_kb'] for r in compression_results)
        total_saved_kb = total_original_kb - total_compressed_kb

        total_original_mb = total_original_kb / 1024
        total_compressed_mb = total_compressed_kb / 1024
        total_saved_mb = total_saved_kb / 1024

        avg_reduction_percent = (total_saved_kb / total_original_kb) * 100 if total_original_kb > 0 else 0
        min_reduction = min(r['reduction_percent'] for r in compression_results)
        max_reduction = max(r['reduction_percent'] for r in compression_results)

        print("\n" + "=" * 60)
        print("COMPRESSION SUMMARY REPORT")
        print("=" * 60)
        print(f"Total papers processed:     {total_processed}")
        print(f"Total original size:        {total_original_mb:.2f} MB")
        print(f"Total compressed size:      {total_compressed_mb:.2f} MB")
        print(f"Total saved:                {total_saved_mb:.2f} MB")
        print(f"Average reduction:          {avg_reduction_percent:.2f}%")
        print(f"Min/Max reduction:          {min_reduction:.2f}% / {max_reduction:.2f}%")
        print("=" * 60)

        return {
            'total_processed': total_processed,
            'total_original_mb': round(total_original_mb, 2),
            'total_compressed_mb': round(total_compressed_mb, 2),
            'total_saved_mb': round(total_saved_mb, 2),
            'avg_reduction_percent': round(avg_reduction_percent, 2),
            'min_reduction_percent': round(min_reduction, 2),
            'max_reduction_percent': round(max_reduction, 2)
        }


    oversized = find_oversized_thumbnails()
    results = compress_thumbnails_batch(oversized)
    summary = generate_summary_report(results)


compress_oversized_thumbnails_dag()
