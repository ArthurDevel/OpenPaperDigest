import sys
import pendulum
import base64
import io
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Tuple

from airflow.decorators import dag, task
from sqlalchemy.orm import Session, defer

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord

# Try to import PIL, provide helpful error if missing
try:
    from PIL import Image
except ImportError:
    raise ImportError(
        "Pillow is required for thumbnail compression. "
        "Install with: pip install Pillow"
    )


### CONSTANTS ###

MAX_SIZE_KB = 200          # Only compress thumbnails larger than 200 KB
TARGET_WIDTH = 800         # Resize to 800px width (maintains aspect ratio)
JPEG_QUALITY = 85          # Compression quality (85 is good balance)
BATCH_SIZE = 50            # Process 50 papers per batch


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


### HELPER FUNCTIONS ###

def calculate_base64_size_kb(base64_str: str) -> float:
    """
    Calculate the decoded size of a base64 string in KB.

    Args:
        base64_str: Base64 encoded string (without data URL prefix)

    Returns:
        float: Size in kilobytes
    """
    # Base64 encoding inflates size by ~4/3, so decoded size is len * 3/4
    return len(base64_str) * 3 / 4 / 1024


def decode_data_url(data_url: str) -> bytes:
    """
    Extract and decode base64 data from a data URL.

    Args:
        data_url: Data URL string (e.g., "data:image/png;base64,...")

    Returns:
        bytes: Decoded image bytes

    Raises:
        ValueError: If data URL format is invalid
    """
    if not data_url or "base64," not in data_url:
        raise ValueError("Invalid data URL format")

    # Extract base64 portion after "base64,"
    base64_data = data_url.split("base64,", 1)[1]

    # Decode base64 to bytes
    return base64.b64decode(base64_data)


def encode_to_jpeg_data_url(image_bytes: bytes) -> str:
    """
    Encode image bytes to a JPEG data URL.

    Args:
        image_bytes: Raw image bytes

    Returns:
        str: Data URL string (e.g., "data:image/jpeg;base64,...")
    """
    base64_str = base64.b64encode(image_bytes).decode('utf-8')
    return f"data:image/jpeg;base64,{base64_str}"


def compress_thumbnail(image_bytes: bytes) -> Tuple[bytes, Dict[str, any]]:
    """
    Compress and resize a thumbnail image.

    Args:
        image_bytes: Original image bytes

    Returns:
        tuple: (compressed_bytes, stats_dict) where stats_dict contains:
            - original_width: Original image width
            - original_height: Original image height
            - new_width: Compressed image width
            - new_height: Compressed image height
            - original_size_kb: Original size in KB
            - new_size_kb: Compressed size in KB
            - reduction_percent: Percentage reduction
    """
    # Load image from bytes
    original_image = Image.open(io.BytesIO(image_bytes))
    original_width, original_height = original_image.size
    original_size_kb = len(image_bytes) / 1024

    # Calculate new dimensions if resizing is needed
    if original_width > TARGET_WIDTH:
        # Resize maintaining aspect ratio
        aspect_ratio = original_height / original_width
        new_width = TARGET_WIDTH
        new_height = int(TARGET_WIDTH * aspect_ratio)
        resized_image = original_image.resize((new_width, new_height), Image.LANCZOS)
    else:
        # Keep original size if already smaller than target
        new_width, new_height = original_width, original_height
        resized_image = original_image

    # Convert to RGB if necessary (JPEG doesn't support transparency)
    if resized_image.mode in ('RGBA', 'LA', 'P'):
        rgb_image = Image.new('RGB', resized_image.size, (255, 255, 255))
        if resized_image.mode == 'P':
            resized_image = resized_image.convert('RGBA')
        rgb_image.paste(resized_image, mask=resized_image.split()[-1] if resized_image.mode in ('RGBA', 'LA') else None)
        resized_image = rgb_image
    elif resized_image.mode != 'RGB':
        resized_image = resized_image.convert('RGB')

    # Compress as JPEG
    output_buffer = io.BytesIO()
    resized_image.save(output_buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    compressed_bytes = output_buffer.getvalue()
    new_size_kb = len(compressed_bytes) / 1024

    # Calculate statistics
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


### DAG DEFINITION ###

@dag(
    dag_id="compress_oversized_thumbnails",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 0 * * *",  # Daily at midnight UTC
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "optimization"],
    doc_md="""
    ### Compress Oversized Thumbnails DAG

    Finds and compresses large thumbnails in the database to improve page load performance.

    **Configuration (hardcoded constants):**
    - Max thumbnail size threshold: 200 KB
    - Target width: 800px (maintains aspect ratio)
    - JPEG quality: 85%
    - Batch size: 50 papers per commit

    **What it does:**
    1. Scans all completed papers with thumbnails
    2. Identifies thumbnails larger than 200 KB
    3. Compresses them to JPEG at 800px width and 85% quality
    4. Updates the database in batches of 50
    5. Generates a summary report with compression statistics

    **Expected results:**
    - 80-90% reduction in thumbnail size
    - Typical output: ~100-200 KB per thumbnail
    - Significantly faster page load times

    **Safety:**
    - Only processes completed papers
    - Batch commits for atomicity
    - Auto-rollback on errors
    - Can be re-run safely (skips already-compressed thumbnails)
    """,
)
def compress_oversized_thumbnails_dag():

    @task
    def find_oversized_thumbnails() -> List[Dict[str, any]]:
        """
        Find all papers with thumbnails larger than MAX_SIZE_KB.

        Returns:
            List[Dict]: List of papers to compress with metadata:
                - paper_uuid: UUID of the paper
                - current_size_kb: Current thumbnail size in KB
        """
        print(f"Scanning for thumbnails larger than {MAX_SIZE_KB} KB...")

        oversized_papers = []

        with database_session() as session:
            # Query all completed papers with thumbnails
            # Defer processed_content to avoid loading huge field
            papers = session.query(PaperRecord).options(
                defer(PaperRecord.processed_content)
            ).filter(
                PaperRecord.status == 'completed',
                PaperRecord.thumbnail_data_url.isnot(None)
            ).all()

            print(f"Found {len(papers)} completed papers with thumbnails")

            # Check size of each thumbnail
            for paper in papers:
                try:
                    # Extract base64 portion from data URL
                    if not paper.thumbnail_data_url or "base64," not in paper.thumbnail_data_url:
                        continue

                    base64_data = paper.thumbnail_data_url.split("base64,", 1)[1]
                    size_kb = calculate_base64_size_kb(base64_data)

                    if size_kb > MAX_SIZE_KB:
                        oversized_papers.append({
                            'paper_uuid': paper.paper_uuid,
                            'current_size_kb': round(size_kb, 2)
                        })

                except Exception as e:
                    print(f"Error checking thumbnail size for {paper.paper_uuid}: {e}")
                    continue

        print(f"Found {len(oversized_papers)} thumbnails that need compression")

        if oversized_papers:
            # Print sample of papers to compress
            sample_size = min(5, len(oversized_papers))
            print(f"\nSample of papers to compress (showing {sample_size}):")
            for paper in oversized_papers[:sample_size]:
                print(f"  - {paper['paper_uuid']}: {paper['current_size_kb']} KB")

        return oversized_papers


    @task
    def compress_thumbnails_batch(oversized_papers: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Compress thumbnails in batches.

        Args:
            oversized_papers: List of papers to compress from find_oversized_thumbnails

        Returns:
            List[Dict]: Compression statistics for each paper
        """
        if not oversized_papers:
            print("No thumbnails to compress")
            return []

        print(f"\nStarting compression of {len(oversized_papers)} thumbnails...")
        print(f"Configuration: {TARGET_WIDTH}px width, {JPEG_QUALITY}% quality, batches of {BATCH_SIZE}")

        all_results = []
        total_papers = len(oversized_papers)

        # Process in batches
        for batch_idx in range(0, total_papers, BATCH_SIZE):
            batch = oversized_papers[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = (batch_idx // BATCH_SIZE) + 1
            total_batches = (total_papers + BATCH_SIZE - 1) // BATCH_SIZE

            print(f"\n--- Processing batch {batch_num}/{total_batches} ({len(batch)} papers) ---")

            with database_session() as session:
                for paper_info in batch:
                    paper_uuid = paper_info['paper_uuid']

                    try:
                        # Load paper record (defer processed_content)
                        paper = session.query(PaperRecord).options(
                            defer(PaperRecord.processed_content)
                        ).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()

                        if not paper or not paper.thumbnail_data_url:
                            print(f"  ⚠️  {paper_uuid}: Thumbnail not found, skipping")
                            continue

                        # Decode thumbnail
                        image_bytes = decode_data_url(paper.thumbnail_data_url)

                        # Compress thumbnail
                        compressed_bytes, stats = compress_thumbnail(image_bytes)

                        # Encode back to data URL
                        new_data_url = encode_to_jpeg_data_url(compressed_bytes)

                        # Update database
                        paper.thumbnail_data_url = new_data_url

                        # Log result
                        print(f"  ✓ {paper_uuid}: {stats['original_size_kb']}KB → {stats['new_size_kb']}KB ({stats['reduction_percent']}% reduction)")

                        # Save stats
                        result = {
                            'paper_uuid': paper_uuid,
                            **stats
                        }
                        all_results.append(result)

                    except Exception as e:
                        print(f"  ✗ {paper_uuid}: Error - {e}")
                        continue

                # Commit batch
                print(f"  Committing batch {batch_num}...")

        print(f"\n✓ Successfully compressed {len(all_results)} thumbnails")
        return all_results


    @task
    def generate_summary_report(compression_results: List[Dict[str, any]]) -> Dict[str, any]:
        """
        Generate a summary report of compression results.

        Args:
            compression_results: List of compression statistics from compress_thumbnails_batch

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

        # Calculate aggregate statistics
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

        # Print summary report
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

        summary = {
            'total_processed': total_processed,
            'total_original_mb': round(total_original_mb, 2),
            'total_compressed_mb': round(total_compressed_mb, 2),
            'total_saved_mb': round(total_saved_mb, 2),
            'avg_reduction_percent': round(avg_reduction_percent, 2),
            'min_reduction_percent': round(min_reduction, 2),
            'max_reduction_percent': round(max_reduction, 2)
        }

        return summary


    # Define task dependencies
    oversized = find_oversized_thumbnails()
    results = compress_thumbnails_batch(oversized)
    summary = generate_summary_report(results)


# Instantiate the DAG
compress_oversized_thumbnails_dag()
